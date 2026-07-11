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
