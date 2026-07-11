# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for name-based title clustering.

cluster_files groups by exact cluster_key — the bulletproof core. The harder
repair heuristics are match.py's job and are tested separately. These tests
prove: variants of one title collapse into a single cluster (with its
funscripts/audio attached), and distinct works (Vol 1 / Vol 2, unrelated names)
split — regardless of which folder the files came from.
"""

from __future__ import annotations

from app.recognizer.canonicalize import Role, canonicalize
from app.recognizer.cluster import TitleCluster, cluster_files


def rec(*names: str):
    return [canonicalize(n) for n in names]


def by_key(clusters: list[TitleCluster]) -> dict[str, TitleCluster]:
    return {c.cluster_key: c for c in clusters}


# ── One title: video variants + channel funscripts collapse ───────────────────

def test_single_title_gathers_variants_and_channels():
    clusters = cluster_files(rec(
        "Magik.4k.mp4",
        "Magik.1080p.mp4",
        "Magik_topaz_4k.mp4",
        "Magik.alpha.funscript",
        "Magik.beta.funscript",
        "Magik.pulse_frequency.funscript",
        "Magik.mp3",
    ))
    assert len(clusters) == 1
    t = clusters[0]
    assert len(t.videos) == 3
    assert len(t.funscripts) == 3
    assert len(t.audio) == 1
    assert t.has_video and t.has_haptics and t.is_playable


def test_video_default_pick_is_best_variant():
    clusters = cluster_files(rec(
        "Magik.720p.mp4",
        "Magik_topaz_4k.mp4",   # upscaled 4k
        "Magik.4k.mp4",         # original 4k — should win
        "Magik.cropped.4k.mp4", # aspect variant — should lose
    ))
    assert len(clusters) == 1
    assert clusters[0].videos[0].filename == "Magik.4k.mp4"


# ── Two titles in one folder: Vol 1 / Vol 2 split, scripts follow ─────────────

def test_two_volumes_split_with_their_own_scripts():
    clusters = cluster_files(rec(
        "Magik Vol 1.mp4",
        "Magik Vol 1.alpha.funscript",
        "Magik Vol 1.beta.funscript",
        "Magik Vol 2.mp4",
        "Magik Vol 2.alpha.funscript",
        "Magik Vol 2.beta.funscript",
    ))
    assert len(clusters) == 2
    m = by_key(clusters)
    v1 = m["magik#volume:1"]
    v2 = m["magik#volume:2"]
    assert len(v1.videos) == 1 and len(v1.funscripts) == 2
    assert len(v2.videos) == 1 and len(v2.funscripts) == 2
    # Each script stays with its own volume's video.
    assert all("Vol 1" in f.filename for f in v1.funscripts)
    assert all("Vol 2" in f.filename for f in v2.funscripts)


def test_unrelated_titles_split():
    clusters = cluster_files(rec(
        "Magik.mp4", "Magik.alpha.funscript",
        "Prisoner.mp4", "Prisoner.alpha.funscript",
    ))
    assert len(clusters) == 2


# ── Folder-independent: funscripts in a separate subfolder still attach ────────

def test_funscripts_from_separate_folder_attach_by_name():
    # The walker gathers video from the scene folder and scripts from a
    # `scripts/` subfolder; clustering is by name, so they still join.
    clusters = cluster_files(rec(
        r"scene/Magik.4k.mp4",
        r"scene/scripts/Magik.alpha.funscript",
        r"scene/scripts/Magik.beta.funscript",
    ))
    assert len(clusters) == 1
    assert len(clusters[0].videos) == 1
    assert len(clusters[0].funscripts) == 2


# ── Bundles & misc ────────────────────────────────────────────────────────────

def test_bundle_attaches_to_matching_video_title():
    clusters = cluster_files(rec(
        "VictoriaOaks.4k.mp4",
        "VictoriaOaks.forge",
    ))
    assert len(clusters) == 1
    t = clusters[0]
    assert len(t.videos) == 1 and len(t.bundles) == 1
    assert t.has_haptics and t.is_playable


def test_other_files_dropped():
    clusters = cluster_files(rec("Magik.mp4", "notes.txt", "thumbs.db"))
    assert len(clusters) == 1
    assert all(f.role is not Role.OTHER for f in clusters[0].files)


def test_display_name_keeps_case_and_appends_ordinal():
    clusters = cluster_files(rec("Magik Vol 2.4k.mp4", "Magik Vol 2.alpha.funscript"))
    assert len(clusters) == 1
    assert clusters[0].display_name == "Magik · Volume 2"


def test_display_name_plain_title():
    clusters = cluster_files(rec("Victoria Oaks.1080p.mp4"))
    assert clusters[0].display_name == "Victoria Oaks"


def test_deterministic_order():
    a = cluster_files(rec("Prisoner.mp4", "Magik Vol 2.mp4", "Magik Vol 1.mp4"))
    keys = [c.cluster_key for c in a]
    assert keys == ["magik#volume:1", "magik#volume:2", "prisoner"]
