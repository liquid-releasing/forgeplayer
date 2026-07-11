# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Reconcile clusters — attach orphan funscripts/bundles to their video title.

``cluster_files`` groups by exact name, which handles the common case where a
video and its scripts share a stem. This module repairs the cases where names
DON'T agree, in increasing order of aggressiveness (and decreasing confidence):

  1. **Fuzzy attach** — an orphan (haptics but no video) whose name is *similar*
     to a video title (token overlap ≥ threshold) and ordinal-compatible folds
     into it. Rescues ``Magik.alpha.funscript`` next to ``Magik XXX 4k.mp4``.
  2. **Singleton pairing** — when a scope has exactly ONE video title and some
     homeless haptics, pair them regardless of name. Handles "the names share
     nothing but it's obviously the one video and its one script."

This is still the NAME/structure half. When even the singleton rule is unsafe
(two videos, one orphan — which video owns it?), the orphan is left alone with
low confidence for the duration probe (``probe.py``) to adjudicate, and failing
that, for the picker to ask. Nothing here does I/O.
"""

from __future__ import annotations

from app.recognizer.cluster import TitleCluster


def _name_similarity(a: str, b: str) -> float:
    """Jaccard overlap of the two canonical keys' word sets (0..1)."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _ordinal_compatible(a: TitleCluster, b: TitleCluster) -> bool:
    """Two clusters can be the same work only if their ordinals don't conflict.

    Equal signatures are compatible; a present-vs-absent ordinal is treated as
    compatible (a bare script may omit the volume the video carries); two
    *different* present ordinals are NOT (Vol 1 vs Vol 2)."""
    if a.ordinal is None or b.ordinal is None:
        return True
    return a.ordinal.signature == b.ordinal.signature


def _best_fuzzy_target(
    orphan: TitleCluster, video_titles: list[TitleCluster], threshold: float
) -> TitleCluster | None:
    """Best video title to fold this orphan into, or None.

    Attaches on either signal: (a) the smaller key's words are fully CONTAINED in
    the other's — the common "video = script name + extra decoration" drift, a
    strong match regardless of threshold — or (b) Jaccard overlap ≥ threshold.
    Ordinal conflicts veto the match outright.
    """
    best: TitleCluster | None = None
    best_score = threshold
    for vt in video_titles:
        if not _ordinal_compatible(orphan, vt):
            continue
        a, b = set(orphan.canonical_key.split()), set(vt.canonical_key.split())
        if a and b and (a <= b or b <= a):
            return vt  # subset containment — decisive
        sim = _name_similarity(orphan.canonical_key, vt.canonical_key)
        if sim >= best_score:
            best_score = sim
            best = vt
    return best


def reconcile(
    clusters: list[TitleCluster], *, fuzzy_threshold: float = 0.6
) -> list[TitleCluster]:
    """Fold orphan haptics into their video title where name/structure allows.

    Returns a new title list (input clusters are mutated in place as files move,
    which is fine — they're freshly built per scan). Confidence and provenance
    are annotated so downstream can decide whether to probe or prompt.
    """
    video_titles = [c for c in clusters if c.has_video]
    orphans = [c for c in clusters if not c.has_video and c.has_haptics]
    audio_only = [c for c in clusters if not c.has_video and not c.has_haptics]

    # 1. Fuzzy attach by name similarity.
    homeless: list[TitleCluster] = []
    for orph in orphans:
        target = _best_fuzzy_target(orph, video_titles, fuzzy_threshold)
        if target is not None:
            target.files.extend(orph.files)
            target.provenance = "fuzzy"
            target.confidence = min(target.confidence, 0.7)
        else:
            homeless.append(orph)

    # 2. Singleton pairing — one video title, some homeless haptics, no ambiguity
    #    about which video they belong to. Still refuses an ordinal conflict: a
    #    Vol 2 script must never land in the lone Vol 1 video.
    if len(video_titles) == 1 and homeless:
        vt = video_titles[0]
        still_homeless: list[TitleCluster] = []
        paired = False
        for orph in homeless:
            if _ordinal_compatible(orph, vt):
                vt.files.extend(orph.files)
                paired = True
            else:
                still_homeless.append(orph)
        if paired:
            vt.provenance = "singleton"
            vt.confidence = min(vt.confidence, 0.5)
        homeless = still_homeless

    # Homeless haptics with two+ candidate videos stay separate + low-confidence;
    # the duration probe / picker resolves them. Mark them so callers can tell.
    for orph in homeless:
        orph.confidence = min(orph.confidence, 0.3)

    result = video_titles + homeless + audio_only
    return sorted(
        result,
        key=lambda t: (t.canonical_key, t.ordinal.number if t.ordinal else -1),
    )
