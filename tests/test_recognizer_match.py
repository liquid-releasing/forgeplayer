# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for cluster reconciliation (fuzzy attach + singleton pairing).

These prove the repair heuristics rescue name-mismatched haptics WITHOUT
wrongly merging distinct works, and that genuinely ambiguous cases are left
low-confidence for the probe/picker rather than force-paired.
"""

from __future__ import annotations

from app.recognizer.canonicalize import canonicalize
from app.recognizer.cluster import cluster_files
from app.recognizer.match import _name_similarity, name_affinity, reconcile


def titles(*names: str):
    return reconcile(cluster_files([canonicalize(n) for n in names]))


def by_key(ts):
    return {t.cluster_key: t for t in ts}


# ── Exact matches stay high-confidence, untouched ─────────────────────────────

def test_exact_match_full_confidence():
    ts = titles("Magik.4k.mp4", "Magik.alpha.funscript", "Magik.beta.funscript")
    assert len(ts) == 1
    assert ts[0].confidence == 1.0
    assert ts[0].provenance == "name"
    assert len(ts[0].funscripts) == 2


# ── Fuzzy attach: name drift between video and its scripts ─────────────────────

def test_fuzzy_attaches_drifted_scripts():
    # Video name carries an extra word the scripts lack.
    ts = titles(
        "Magik XXX.4k.mp4",
        "Magik.alpha.funscript",
        "Magik.beta.funscript",
    )
    assert len(ts) == 1
    t = ts[0]
    assert t.has_video and len(t.funscripts) == 2
    assert t.provenance == "fuzzy"
    assert t.confidence == 0.7


def test_fuzzy_respects_ordinal_conflict():
    # A Vol 2 script must NOT fuzzy-attach to a Vol 1 video.
    ts = titles(
        "Magik Adventures Vol 1.mp4",
        "Magik Adventures Vol 2.alpha.funscript",
    )
    # Two distinct titles; the script does not fold into Vol 1.
    m = by_key(ts)
    assert "magik adventures#volume:1" in m
    v1 = m["magik adventures#volume:1"]
    assert len(v1.funscripts) == 0


def test_low_similarity_not_attached():
    # Completely different names + two videos → no fuzzy, no singleton.
    ts = titles(
        "Magik.mp4",
        "Prisoner.mp4",
        "Euphoria.alpha.funscript",   # matches neither
    )
    m = by_key(ts)
    assert set(m) == {"magik", "prisoner", "euphoria"}
    # The orphan script title is left low-confidence for the probe/picker.
    assert m["euphoria"].confidence <= 0.3


# ── Singleton pairing: one video, one script, names share nothing ─────────────

def test_singleton_pairs_despite_name_mismatch():
    ts = titles(
        "movie_final_export.mp4",
        "TheScene.alpha.funscript",
        "TheScene.beta.funscript",
    )
    assert len(ts) == 1
    t = ts[0]
    assert t.has_video and len(t.funscripts) == 2
    assert t.provenance == "singleton"
    assert t.confidence == 0.5


def test_singleton_pairs_bundle_to_lone_video():
    ts = titles("clip.mp4", "SomethingElse.forge")
    assert len(ts) == 1
    assert ts[0].has_video and len(ts[0].bundles) == 1


def test_no_singleton_when_two_videos_compete():
    # Two videos + one orphan script → singleton must NOT fire (ambiguous owner).
    ts = titles("A.mp4", "B.mp4", "Zzz.alpha.funscript")
    m = by_key(ts)
    assert "zzz" in m               # orphan stays separate
    assert m["zzz"].confidence <= 0.3
    assert len(m["a"].funscripts) == 0 and len(m["b"].funscripts) == 0


# ── Multi-title folders still split correctly after reconcile ─────────────────

def test_two_volumes_survive_reconcile():
    ts = titles(
        "Magik Vol 1.mp4", "Magik Vol 1.alpha.funscript",
        "Magik Vol 2.mp4", "Magik Vol 2.alpha.funscript",
    )
    assert len(ts) == 2
    for t in ts:
        assert t.confidence == 1.0
        assert len(t.funscripts) == 1


# ── similarity helper ─────────────────────────────────────────────────────────

def test_name_similarity_basic():
    assert _name_similarity("magik", "magik") == 1.0
    assert _name_similarity("magik xxx", "magik") == 0.5
    assert _name_similarity("magik", "prisoner") == 0.0


# ── Audio-companion folding (dogfood: Clutch/Optikon estim + beat tracks) ──────

def test_estim_audio_folds_into_video_title():
    ts = titles(
        "Clutch rf20.mp4", "Clutch rf20.alpha.funscript",
        "Clutch Estim Mild.mp3", "Clutch Estim Spicy.mp3",
    )
    # One card — the two estim mp3s fold in as audio companions, not own cards.
    assert len(ts) == 1
    t = ts[0]
    assert t.has_video
    assert len(t.audio) == 2


def test_beat_track_folds_in():
    ts = titles("CH Optikon Alpha.mp4", "Optikon Alpha Beats.mp3")
    assert len(ts) == 1
    assert len(ts[0].audio) == 1


def test_audio_only_folder_keeps_its_card():
    # No video anywhere → the audio stays as its own (pure-audio) card.
    ts = titles("Ambience Loop.mp3", "Ambience Loop.beats.mp3")
    assert len(ts) >= 1
    assert all(not t.has_video for t in ts)


def test_unrelated_audio_not_folded():
    # Audio whose name shares nothing with the video is left alone.
    ts = titles("Magik.mp4", "CompletelyDifferent.mp3")
    keys = {t.cluster_key for t in ts}
    assert "magik" in keys and "completelydifferent" in keys


def test_name_affinity_helper():
    assert name_affinity("victoriaoaks wet dreams", "wetdreams medium lrf") is True
    assert name_affinity("clutch", "clutch estim mild") is True
    assert name_affinity("magik", "prisoner") is False
