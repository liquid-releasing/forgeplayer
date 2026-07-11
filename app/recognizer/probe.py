# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Content adjudication — resolve name-ambiguous titles by DURATION.

Names propose (canonicalize → cluster → reconcile); this module is the content
half, consulted ONLY when a title's confidence is low — i.e. an orphan funscript
that couldn't be name-matched to a video (two candidates competed, or the names
share nothing and there were several videos). The signal is unfakeable:

    a funscript's last-action timestamp ≈ the duration of the video it scripts.

So a homeless script attaches to the video whose running time matches its span,
even when the filenames agree on nothing. When two videos have near-identical
durations it stays ambiguous (left for the picker) rather than guessing.

The resolver ``probe_resolve`` is PURE — it takes ``duration_of`` and ``span_of``
callables, so it unit-tests with fakes and never needs mpv. The default I/O
providers (``mpv_duration_ms`` reusing the thumbnail duration sidecar, and the
pure-JSON ``funscript_span_ms``) live here too but are injected, not imported,
by the resolver.
"""

from __future__ import annotations

import json
import os
from typing import Callable

from app.recognizer.canonicalize import Role
from app.recognizer.cluster import TitleCluster

DurationFn = Callable[[str], "float | None"]
SpanFn = Callable[[str], "float | None"]


# ── Pure content signals ───────────────────────────────────────────────────────

_span_cache: dict[tuple[str, int, int], float | None] = {}


def funscript_span_ms(path: str) -> float | None:
    """Last action timestamp (ms) in a funscript — its content length. Pure JSON;
    cached by (path, mtime, size). None on unreadable/empty."""
    try:
        st = os.stat(path)
        ck = (os.path.abspath(path), int(st.st_mtime), st.st_size)
    except OSError:
        return None
    if ck in _span_cache:
        return _span_cache[ck]

    span: float | None = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        actions = data.get("actions") if isinstance(data, dict) else None
        if actions:
            last = 0.0
            for a in actions:
                at = a.get("at")
                if isinstance(at, (int, float)) and at > last:
                    last = float(at)
            span = last or None
    except (OSError, ValueError, AttributeError, TypeError):
        span = None
    _span_cache[ck] = span
    return span


def mpv_duration_ms(path: str) -> float | None:
    """Video running time (ms) via the shared thumbnail duration sidecar, probing
    headlessly with mpv on a miss. Reuses ``app.thumbnails`` opportunistically
    (soft import — keeps the recognizer importable without Qt/mpv); a fresh probe
    writes back to the same sidecar so a later thumbnail pass gets it free."""
    try:
        from app.thumbnails import cached_duration, duration_cache_path
    except Exception:
        cached_duration = duration_cache_path = None  # type: ignore

    if cached_duration is not None:
        secs = cached_duration(path)
        if secs is not None:
            return secs * 1000.0

    secs = _probe_duration_secs_mpv(path)
    if secs is None:
        return None
    if duration_cache_path is not None:
        try:
            p = duration_cache_path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"{secs:.3f}", encoding="utf-8")
        except OSError:
            pass
    return secs * 1000.0


def _probe_duration_secs_mpv(path: str) -> float | None:
    """Headless libmpv duration read — demux only, no frame grab. Best-effort."""
    import time

    try:
        import mpv
    except Exception:
        return None
    player = None
    try:
        player = mpv.MPV(vo="null", audio="no", hwdec="no",
                         msg_level="all=no", really_quiet=True)
        player.command("loadfile", path)
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            if player.duration:
                return float(player.duration)
            time.sleep(0.03)
        return float(player.duration) if player.duration else None
    except Exception:
        return None
    finally:
        if player is not None:
            try:
                player.terminate()
            except Exception:
                pass


# ── Tolerance ──────────────────────────────────────────────────────────────────

def _duration_matches(dur_ms: float, span_ms: float) -> tuple[bool, float]:
    """Does this funscript span fit this video? Returns (fits, gap_ms).

    A script must not run meaningfully LONGER than the video (allow 2% for
    trailing padding / rounding), and its span must land within a generous
    window of the running time — scripts often stop before the credits, so the
    window is the larger of 30 s or 8 % of the video."""
    if dur_ms <= 0 or span_ms <= 0:
        return (False, float("inf"))
    if span_ms > dur_ms * 1.02:
        return (False, abs(dur_ms - span_ms))
    tol = max(30_000.0, dur_ms * 0.08)
    gap = dur_ms - span_ms
    return (gap <= tol, abs(gap))


# ── Resolver (pure) ─────────────────────────────────────────────────────────────

def probe_resolve(
    titles: list[TitleCluster],
    *,
    duration_of: DurationFn,
    span_of: SpanFn,
    min_confidence: float = 0.7,
) -> list[TitleCluster]:
    """Attach low-confidence orphan haptics to the video they fit by duration.

    Only orphan titles (haptics, no video) below ``min_confidence`` are probed —
    high-confidence name matches are left alone (names proposed, we trust them).
    An orphan attaches to a video title when exactly one video's running time
    fits its funscript span AND no other video's duration is comparably close
    (otherwise it stays ambiguous for the picker). Pure: all I/O is injected.
    """
    video_titles = [t for t in titles if t.has_video]
    orphans = [
        t for t in titles
        if not t.has_video and t.has_haptics and t.confidence < min_confidence
    ]
    if not video_titles or not orphans:
        return titles

    # Probe each video title's default running time once.
    vid_dur: dict[int, float | None] = {}
    for vt in video_titles:
        vids = vt.videos
        vid_dur[id(vt)] = duration_of(vids[0].path) if vids else None

    attached: set[int] = set()
    for orph in orphans:
        span = _orphan_span(orph, span_of)
        if span is None:
            continue
        scored: list[tuple[float, TitleCluster]] = []
        for vt in video_titles:
            dur = vid_dur.get(id(vt))
            if dur is None:
                continue
            fits, gap = _duration_matches(dur, span)
            if fits:
                scored.append((gap, vt))
        if not scored:
            continue
        scored.sort(key=lambda s: s[0])
        best_gap, best_vt = scored[0]
        # Unique enough? Sole fit, or clearly closer than the runner-up.
        if len(scored) > 1 and scored[1][0] <= best_gap * 2 + 1:
            continue  # two videos fit comparably — leave for the picker
        best_vt.files.extend(orph.files)
        best_vt.provenance = "duration"
        # A duration-inferred attachment is strong but not name-certain, so the
        # whole title's confidence settles at the content signal (0.85) — above
        # fuzzy/singleton, below an exact name match.
        best_vt.confidence = min(best_vt.confidence, 0.85)
        attached.add(id(orph))

    if not attached:
        return titles
    result = [t for t in titles if id(t) not in attached]
    return sorted(
        result,
        key=lambda t: (t.canonical_key, t.ordinal.number if t.ordinal else -1),
    )


def _orphan_span(orph: TitleCluster, span_of: SpanFn) -> float | None:
    """Longest funscript span in an orphan title — its content length."""
    best: float | None = None
    for f in orph.files:
        if f.role is not Role.FUNSCRIPT:
            continue
        s = span_of(f.path)
        if s is not None and (best is None or s > best):
            best = s
    return best
