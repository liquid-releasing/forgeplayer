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

# Where in the clip to grab — 12% in skips intros/black leaders and lands on
# representative content for most scenes. Clamped to a few seconds minimum so
# very long files don't seek past a slow-to-decode keyframe needlessly.
_SEEK_FRAC = 0.12
_SEEK_MIN_S = 3.0


def _cache_key(video_path: str) -> str:
    """Stable key from path + mtime + size, so a re-encoded/replaced file at
    the same path regenerates instead of serving a stale frame."""
    try:
        st = os.stat(video_path)
        sig = f"{os.path.abspath(video_path)}|{int(st.st_mtime)}|{st.st_size}|{_THUMB_W}"
    except OSError:
        sig = f"{os.path.abspath(video_path)}|0|0|{_THUMB_W}"
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()


def cached_path(video_path: str) -> Path:
    # PNG, not JPEG: Qt's PNG codec is built into QtGui, while JPEG read/write
    # needs the `qjpeg` imageformats plugin — which isn't always bundled in the
    # PyInstaller build (thumbnails worked in the dev venv but not the packaged
    # app). PNG works everywhere; for a 448px frame the size cost is negligible.
    return _CACHE_DIR / f"{_cache_key(video_path)}.png"


def _grab_frame_to(video_path: str, out_path: Path) -> bool:
    """Headless single-frame grab via libmpv. Returns True on success.

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
        # Wait for the demuxer to expose dimensions + a clock, or bail.
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if player.width and player.time_pos is not None:
                break
            time.sleep(0.03)
        else:
            return False

        dur = player.duration or 0.0
        target = max(_SEEK_MIN_S, dur * _SEEK_FRAC) if dur else _SEEK_MIN_S
        if dur:
            target = min(target, max(0.0, dur - 0.5))
        try:
            player.command("seek", target, "absolute", "exact")
            # Let the seek settle on a decoded frame before the screenshot.
            seek_deadline = time.monotonic() + 3.0
            while time.monotonic() < seek_deadline:
                if player.time_pos is not None and player.time_pos >= target - 1.0:
                    break
                time.sleep(0.03)
        except Exception:
            pass  # un-seekable / very short clip: screenshot wherever we are

        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mktemp(suffix=".png", dir=str(out_path.parent)))
        player.command("screenshot-to-file", str(tmp), "video")
        # screenshot-to-file is async-ish in libmpv — wait for the file.
        shot_deadline = time.monotonic() + 3.0
        while time.monotonic() < shot_deadline:
            if tmp.exists() and tmp.stat().st_size > 0:
                break
            time.sleep(0.03)
        if not (tmp.exists() and tmp.stat().st_size > 0):
            return False

        # Scale down (QImage is safe off the GUI thread) and write the small
        # cache file, then drop the full-res temp.
        img = QImage(str(tmp))
        ok = False
        if not img.isNull():
            scaled = img.scaledToWidth(_THUMB_W, Qt.SmoothTransformation)
            ok = scaled.save(str(out_path), "PNG")
        try:
            tmp.unlink()
        except OSError:
            pass
        return ok
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
