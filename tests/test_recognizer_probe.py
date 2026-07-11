# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the duration probe — the content-adjudicates half.

The resolver is pure (duration/span injected as fakes), so no mpv is needed.
The key case: two videos competed for one orphan script and the singleton rule
refused to guess — duration resolves it to the right video. Near-identical
durations stay ambiguous rather than guessing.
"""

from __future__ import annotations

import json

from app.recognizer import recognize_titles
from app.recognizer.probe import (
    _duration_matches,
    _name_affinity,
    consolidate_videos_by_duration,
    funscript_span_ms,
    probe_resolve,
)


def by_key(ts):
    return {t.cluster_key: t for t in ts}


# ── funscript_span_ms (pure JSON) ─────────────────────────────────────────────

def test_funscript_span_reads_last_action(tmp_path):
    fs = tmp_path / "clip.alpha.funscript"
    fs.write_text(json.dumps({"actions": [
        {"at": 0, "pos": 0}, {"at": 5000, "pos": 100}, {"at": 123456, "pos": 40},
    ]}), encoding="utf-8")
    assert funscript_span_ms(str(fs)) == 123456.0


def test_funscript_span_empty_or_bad(tmp_path):
    empty = tmp_path / "a.funscript"
    empty.write_text(json.dumps({"actions": []}), encoding="utf-8")
    assert funscript_span_ms(str(empty)) is None
    bad = tmp_path / "b.funscript"
    bad.write_text("not json", encoding="utf-8")
    assert funscript_span_ms(str(bad)) is None
    assert funscript_span_ms(str(tmp_path / "missing.funscript")) is None


# ── tolerance ─────────────────────────────────────────────────────────────────

def test_duration_matches_window():
    # 10-min video, script ends ~20s early → fits.
    assert _duration_matches(600_000, 580_000)[0] is True
    # script longer than video → never fits.
    assert _duration_matches(600_000, 900_000)[0] is False
    # script ends way early (5 min into a 60 min video) → outside window.
    assert _duration_matches(3_600_000, 300_000)[0] is False


# ── probe_resolve: the two-videos-competed case ───────────────────────────────

def _fakes(durations, spans):
    return (lambda p: durations.get(p), lambda p: spans.get(p))


def test_orphan_attaches_to_duration_matching_video():
    titles = recognize_titles(["Short.mp4", "Long.mp4", "Mystery.alpha.funscript"])
    # Name step leaves Mystery homeless (two videos competed).
    assert by_key(titles)["mystery"].confidence <= 0.3

    dur, span = _fakes(
        {"Short.mp4": 600_000, "Long.mp4": 3_600_000},
        {"Mystery.alpha.funscript": 595_000},   # fits Short
    )
    out = probe_resolve(titles, duration_of=dur, span_of=span)
    m = by_key(out)
    assert "mystery" not in m                     # orphan consumed
    short = m["short"]
    assert len(short.funscripts) == 1
    assert short.provenance == "duration"
    assert short.confidence == 0.85


def test_ambiguous_durations_left_for_picker():
    titles = recognize_titles(["A.mp4", "B.mp4", "Mystery.alpha.funscript"])
    dur, span = _fakes(
        {"A.mp4": 600_000, "B.mp4": 601_000},     # near-identical
        {"Mystery.alpha.funscript": 595_000},
    )
    out = probe_resolve(titles, duration_of=dur, span_of=span)
    m = by_key(out)
    assert "mystery" in m                          # stayed ambiguous
    assert len(m["a"].funscripts) == 0 and len(m["b"].funscripts) == 0


def test_orphan_matching_no_video_stays():
    titles = recognize_titles(["A.mp4", "B.mp4", "Mystery.alpha.funscript"])
    dur, span = _fakes(
        {"A.mp4": 600_000, "B.mp4": 601_000},
        {"Mystery.alpha.funscript": 7_200_000},   # fits neither
    )
    out = probe_resolve(titles, duration_of=dur, span_of=span)
    assert "mystery" in by_key(out)


def test_high_confidence_titles_not_probed():
    # Exact name match → confidence 1.0 → probe is a no-op.
    titles = recognize_titles(["Magik.mp4", "Magik.alpha.funscript"])
    called = {"n": 0}

    def dur(p):
        called["n"] += 1
        return 600_000

    out = probe_resolve(titles, duration_of=dur, span_of=lambda p: 590_000)
    assert out is titles
    assert called["n"] == 0            # no orphan → never probed


def test_probe_noop_when_no_videos():
    titles = recognize_titles(["A.alpha.funscript", "A.beta.funscript"])
    out = probe_resolve(titles, duration_of=lambda p: 1, span_of=lambda p: 1)
    assert out is titles


# ── consolidate_videos_by_duration: param-named render folds into its work ─────

def test_name_affinity():
    # 'wet dreams' ↔ 'wetdreams …' share a token via squashed containment.
    assert _name_affinity("victoriaoaks wet dreams",
                          "wetdreams medium 55 right only lrf full") is True
    assert _name_affinity("magik", "prisoner") is False


def test_param_render_merges_by_duration():
    # The real dogfood shape: clean title + a param-named SBS render, same runtime.
    titles = recognize_titles([
        "VictoriaOaks - Wet Dreams 4k.mp4",
        "wetdreams 4k60-medium_55_5_RIGHT_ONLY_auto_subject_v1.8.5_LRF_Full_SBS.mp4",
    ])
    assert len(titles) == 2   # names alone split them
    dur = {
        "VictoriaOaks - Wet Dreams 4k.mp4": 1_800_000,
        "wetdreams 4k60-medium_55_5_RIGHT_ONLY_auto_subject_v1.8.5_LRF_Full_SBS.mp4": 1_800_500,
    }
    out = consolidate_videos_by_duration(titles, duration_of=lambda p: dur.get(p))
    assert len(out) == 1
    t = out[0]
    assert len(t.videos) == 2
    assert t.provenance == "duration"
    # Clean title survives; render's noisy name doesn't become the label.
    assert "wet dreams" in t.canonical_key


def test_different_works_same_duration_not_merged():
    # Coincidental runtime match must NOT merge unrelated works (no affinity).
    titles = recognize_titles(["Magik.mp4", "Prisoner.mp4"])
    out = consolidate_videos_by_duration(
        titles, duration_of=lambda p: 1_200_000,   # identical
    )
    assert len(out) == 2


def test_ordinal_conflict_blocks_duration_merge():
    # Same duration + affinity, but Vol 1 vs Vol 2 stay separate.
    titles = recognize_titles(["Magik Vol 1.mp4", "Magik Vol 2.mp4"])
    out = consolidate_videos_by_duration(
        titles, duration_of=lambda p: 1_500_000,
    )
    assert len(out) == 2


def test_different_duration_affinity_not_merged():
    titles = recognize_titles([
        "Show.mp4", "Show extended cut bonus render.mp4",
    ])
    dur = {"Show.mp4": 600_000, "Show extended cut bonus render.mp4": 1_800_000}
    out = consolidate_videos_by_duration(titles, duration_of=lambda p: dur.get(p))
    assert len(out) == 2


def test_single_video_folder_no_probe():
    titles = recognize_titles(["Solo.mp4", "Solo.alpha.funscript"])
    called = {"n": 0}

    def dur(p):
        called["n"] += 1
        return 1

    out = consolidate_videos_by_duration(titles, duration_of=dur)
    assert out is titles
    assert called["n"] == 0
