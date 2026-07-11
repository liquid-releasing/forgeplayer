# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Thumbnail service for the Library grid.

The Library shipped with a flat placeholder rectangle per card (the scanner
docstring called real thumbnails a "polish pass that needs ffprobe + caching").
This is that pass — done with mpv (already the decoder) rather than ffmpeg,
matching SPEC.md's "no imageio-ffmpeg, Qt handles everything" stance.

How it works
------------
- A card's paint() asks ``ThumbnailService.pixmap_for(video_path)``.
- If a scaled JPEG is already cached on disk (and in memory), it returns the
  QPixmap immediately and the delegate paints it.
- Otherwise it returns None (delegate draws the placeholder) and enqueues a
  one-off background job: a headless libmpv instance grabs a single frame
  ~12% into the video, Qt scales it down, and it's written to
  ``~/.forgeplayer/thumb_cache/<key>.jpg``. When the job finishes the service
  emits ``ready(video_path)`` and the panel repaints — the card swaps its
  placeholder for the frame.

Generation is paint-driven, so only cards the user actually scrolls past get a
thumbnail; a 500-scene library doesn't decode 500 videos up front. The pool is
capped low (2) so we never spin up a swarm of decoders.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import (
    QObject, QRunnable, QThreadPool, Qt, Signal, Slot,
)
from PySide6.QtGui import QImage, QPixmap


_CACHE_DIR = Path.home() / ".forgeplayer" / "thumb_cache"

# Stored thumbnail width. 2x the on-card thumb (~210px) so it stays crisp on
# HiDPI displays without bloating the cache (a 448px JPEG is a few KB).
_THUMB_W = 448

# Bump when the frame-SELECTION logic changes so old cached thumbnails (grabbed
# by a prior algorithm — e.g. the single fixed 12% frame) regenerate instead of
# serving a stale dark/flat frame. Folded into the cache key.
_THUMB_ALGO = 3

# Preferred early grab point — ~10s in usually clears the intro/leader and
# lands on the first real content, which is the frame users expect on the card.
# Tried first; the body samples below are fallbacks so a dark/flat 10s frame
# (fade-in, title card) can lose to a better one rather than becoming the thumb.
_SEEK_EARLY_S = 10.0

# Candidate seek points (fractions of duration) sampled across the body of the
# clip. We grab a frame at each, score it, and keep the best — so a dark shot or
# a face-against-black at any one point doesn't become the card thumbnail. The
# spread skips intros/leaders (≥15%) and outros/credits (≤78%) and otherwise
# walks the middle where representative content lives.
_SEEK_FRACS = (0.15, 0.30, 0.45, 0.60, 0.78)
_SEEK_MIN_S = 3.0

# When the early 10s frame is decent (not a near-black/flat title card), prefer
# it even if a busier mid-clip frame scores marginally higher — the user asked
# for "about 10 seconds in". This is the score it must clear to win outright.
_EARLY_GOOD_SCORE = 12.0


def _cache_key(video_path: str) -> str:
    """Stable key from path + mtime + size, so a re-encoded/replaced file at
    the same path regenerates instead of serving a stale frame."""
    try:
        st = os.stat(video_path)
        sig = f"{os.path.abspath(video_path)}|{int(st.st_mtime)}|{st.st_size}|{_THUMB_W}|{_THUMB_ALGO}"
    except OSError:
        sig = f"{os.path.abspath(video_path)}|0|0|{_THUMB_W}|{_THUMB_ALGO}"
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()


def duration_cache_path(video_path: str) -> Path:
    """Sidecar holding the probed duration (seconds) for this video. Written in
    the same mpv pass that grabs the thumbnail, so the Library card can show the
    real running time instead of the `—:—:—` placeholder — no extra decode."""
    return _CACHE_DIR / f"{_cache_key(video_path)}.dur"


def cached_duration(video_path: str) -> float | None:
    """Read the cached duration (seconds), or None if not probed yet."""
    try:
        raw = duration_cache_path(video_path).read_text(encoding="utf-8").strip()
        val = float(raw)
        return val if val > 0 else None
    except (OSError, ValueError):
        return None


def cached_path(video_path: str) -> Path:
    # PNG, not JPEG: Qt's PNG codec is built into QtGui, while JPEG read/write
    # needs the `qjpeg` imageformats plugin — which isn't always bundled in the
    # PyInstaller build (thumbnails worked in the dev venv but not the packaged
    # app). PNG works everywhere; for a 448px frame the size cost is negligible.
    return _CACHE_DIR / f"{_cache_key(video_path)}.png"


def _frame_score(img: QImage) -> float:
    """Heuristic 'is this a good thumbnail' score for a decoded frame.

    Rewards detail/contrast (luma standard deviation) so flat near-black
    leaders, fade-to-black cuts, and uniform shots score near zero. Penalises
    frames that are too dark or blown out — a face lit against black reads as a
    low mean with modest spread, which loses to a brighter, busier frame
    elsewhere in the clip. Computed on a tiny downscaled copy so it's cheap to
    run on every candidate.
    """
    if img.isNull():
        return -1.0
    # 32×18 ≈ 576 samples — enough to characterise brightness/detail, trivial
    # to iterate in Python on the worker thread.
    small = img.scaled(32, 18, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    w, h = small.width(), small.height()
    if w == 0 or h == 0:
        return -1.0
    n = w * h
    total = 0.0
    total_sq = 0.0
    for y in range(h):
        for x in range(w):
            c = small.pixelColor(x, y)
            luma = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
            total += luma
            total_sq += luma * luma
    mean = total / n
    var = max(0.0, total_sq / n - mean * mean)
    std = var ** 0.5
    # Brightness gate: a soft window centred on mid-tones. Frames whose mean
    # luma sits in [40, 220] keep their full detail score; darker/brighter
    # frames are scaled down so a black-with-a-face frame can't win on the
    # little contrast its highlight carries.
    if mean < 40:
        bright = mean / 40.0
    elif mean > 220:
        bright = max(0.0, (255 - mean) / 35.0)
    else:
        bright = 1.0
    return std * (0.35 + 0.65 * bright)


def _grab_frame_to(video_path: str, out_path: Path) -> bool:
    """Headless multi-candidate frame grab via libmpv. Returns True on success.

    Grabs a frame at each of several seek points across the body of the clip,
    scores them (see ``_frame_score``), and writes the best one — so a dark or
    flat frame at any single offset doesn't become the card thumbnail.

    vo='null' + screenshot-to-file 'video' renders just the decoded frame (no
    OSD, no window). Kept fully self-contained so it can run on a worker
    thread without touching Qt or the app's SyncEngine players.
    """
    import mpv  # local import: keeps Qt-only paths free of the mpv dependency

    player = None
    try:
        player = mpv.MPV(
            vo="null", audio="no", hwdec="no",
            msg_level="all=no", really_quiet=True,
        )
        player.command("loadfile", video_path)
        # Wait for the demuxer to expose dimensions + a clock, or bail. Generous
        # so a large 4K/mkv on a slow/external drive still demuxes in time (a
        # too-short deadline was blacklisting big files → permanently blank card).
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if player.width and player.time_pos is not None:
                break
            time.sleep(0.03)
        else:
            return False

        dur = player.duration or 0.0
        # Cache the running time now that mpv has demuxed it — same pass, so the
        # Library card gets a real duration for free (see duration_cache_path).
        if dur > 0:
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                duration_cache_path(video_path).write_text(f"{dur:.3f}", encoding="utf-8")
            except OSError:
                pass
        # Build the candidate seek list, early frame FIRST. ~10s in is the
        # preferred grab; the body samples are fallbacks for when 10s is a
        # near-black fade-in / title card. With no known duration (some
        # streams) we fall back to a single grab a few seconds in.
        if dur:
            targets = []
            if dur > _SEEK_EARLY_S + 2.0:
                targets.append(_SEEK_EARLY_S)
            targets += [
                min(max(_SEEK_MIN_S, dur * f), max(0.0, dur - 0.5))
                for f in _SEEK_FRACS
            ]
        else:
            targets = [_SEEK_MIN_S]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mktemp(suffix=".png", dir=str(out_path.parent)))

        best_img: QImage | None = None
        best_score = -1.0
        for idx, target in enumerate(targets):
            try:
                player.command("seek", target, "absolute", "exact")
                seek_deadline = time.monotonic() + 5.0
                while time.monotonic() < seek_deadline:
                    if player.time_pos is not None and player.time_pos >= target - 1.0:
                        break
                    time.sleep(0.03)
            except Exception:
                pass  # un-seekable / very short clip: shoot wherever we are

            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            try:
                player.command("screenshot-to-file", str(tmp), "video")
            except Exception:
                continue
            # screenshot-to-file is async-ish in libmpv — wait for the file.
            shot_deadline = time.monotonic() + 5.0
            while time.monotonic() < shot_deadline:
                if tmp.exists() and tmp.stat().st_size > 0:
                    break
                time.sleep(0.03)
            if not (tmp.exists() and tmp.stat().st_size > 0):
                continue

            img = QImage(str(tmp))
            if img.isNull():
                continue
            score = _frame_score(img)
            if score > best_score:
                best_score = score
                # Keep the scaled copy now; the next iteration overwrites tmp.
                best_img = img.scaledToWidth(_THUMB_W, Qt.SmoothTransformation)

            # The first candidate is the preferred ~10s frame (when duration
            # allowed it). If it's decent, take it and skip the body samples —
            # honours "about 10 seconds in" and avoids decoding 5 more frames.
            if idx == 0 and target == _SEEK_EARLY_S and score >= _EARLY_GOOD_SCORE:
                break

        try:
            tmp.unlink()
        except OSError:
            pass

        if best_img is None or best_img.isNull():
            return False
        return bool(best_img.save(str(out_path), "PNG"))
    except Exception:
        return False
    finally:
        if player is not None:
            try:
                player.terminate()
            except Exception:
                pass


class _GrabSignals(QObject):
    done = Signal(str, object)  # (video_path, QImage | None)


class _GrabJob(QRunnable):
    def __init__(self, video_path: str, signals: _GrabSignals) -> None:
        super().__init__()
        self._video_path = video_path
        self._signals = signals

    def run(self) -> None:  # noqa: D401 — QRunnable entry point
        out = cached_path(self._video_path)
        img = None
        if out.exists() or _grab_frame_to(self._video_path, out):
            loaded = QImage(str(out))
            if not loaded.isNull():
                img = loaded
        self._signals.done.emit(self._video_path, img)


class ThumbnailService(QObject):
    """Lazy, cached, async thumbnails keyed by video path.

    ``pixmap_for`` is the only call a delegate needs: it returns a ready
    QPixmap or None (and kicks off generation on a miss). ``ready`` fires when
    a previously-missing thumbnail becomes available — connect it to the
    view's viewport().update so the card repaints.
    """

    ready = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pixmaps: dict[str, QPixmap] = {}
        self._durations: dict[str, float] = {}
        self._inflight: set[str] = set()
        self._failed: set[str] = set()
        self._pool = QThreadPool(self)
        # A small cap: decoding is the expensive bit, and the user only ever
        # sees a screenful of cards at once. 2 keeps scroll responsive without
        # spinning up a decoder swarm.
        self._pool.setMaxThreadCount(2)
        self._signals = _GrabSignals(self)
        self._signals.done.connect(self._on_done)

    def pixmap_for(self, video_path: str | None) -> QPixmap | None:
        """Ready pixmap, or None (enqueueing generation on first miss)."""
        if not video_path:
            return None
        hit = self._pixmaps.get(video_path)
        if hit is not None:
            return hit
        if video_path in self._failed or video_path in self._inflight:
            return None
        self._inflight.add(video_path)
        self._pool.start(_GrabJob(video_path, self._signals))
        return None

    def duration_for(self, video_path: str | None) -> float | None:
        """Cached running time (seconds) for a video, or None if not probed
        yet. Probed in the same pass as the thumbnail, so it becomes available
        when the card's thumbnail does (the `ready` signal triggers a repaint).
        Reading `pixmap_for` first kicks off generation on a miss."""
        if not video_path:
            return None
        hit = self._durations.get(video_path)
        if hit is not None:
            return hit
        disk = cached_duration(video_path)
        if disk is not None:
            self._durations[video_path] = disk
        return disk

    @Slot(str, object)
    def _on_done(self, video_path: str, image: object) -> None:
        self._inflight.discard(video_path)
        ok = isinstance(image, QImage) and not image.isNull()
        if ok:
            # QPixmap must be built on the GUI thread — we're there now.
            self._pixmaps[video_path] = QPixmap.fromImage(image)
            self.ready.emit(video_path)
        else:
            self._failed.add(video_path)
        # Diagnostic breadcrumb (enable Debug to capture): tells us whether
        # generation succeeded per scene, so a "no thumbnails" report is
        # actionable instead of a guess.
        try:
            from app.debug_log import DebugLog
            DebugLog.record(
                "thumbnail.done",
                ok=ok,
                cached=str(cached_path(video_path)),
                video=video_path,
            )
        except Exception:
            pass
