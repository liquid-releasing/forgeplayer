# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the recognizer's canonicalizer — the title-identity foundation.

The contract under test: two files are the SAME title iff their cluster_key
matches. Rendering differences (resolution, upscaler, aspect, codec, channel,
edit tags) must collapse; identity differences (volume/part/episode ordinal,
distinct name) must split. These are pure string tests — no I/O.
"""

from __future__ import annotations

import pytest

from app.recognizer.canonicalize import Role, canonicalize


def key(name: str) -> str:
    return canonicalize(name).cluster_key


# ── Role classification ───────────────────────────────────────────────────────

@pytest.mark.parametrize("name,role", [
    ("Magik.mp4", Role.VIDEO),
    ("Magik.wmv", Role.VIDEO),
    ("Magik.alpha.funscript", Role.FUNSCRIPT),
    ("Magik.funscript", Role.FUNSCRIPT),
    ("Magik.mp3", Role.AUDIO),
    ("Magik.en.srt", Role.SUBTITLE),
    ("Magik.forge", Role.BUNDLE),
    ("Magik.forgeplay", Role.BUNDLE),
    ("Magik.funscript.zip", Role.ARCHIVE),
    ("Magik.forgeplayer.json", Role.PRESET),
    ("notes.txt", Role.OTHER),
])
def test_role(name, role):
    assert canonicalize(name).role is role


# ── Rendering differences COLLAPSE (same title) ───────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("Magik.4k.mp4", "Magik.1080p.mp4"),
    ("Magik.mp4", "Magik.720p.mp4"),
    ("Magik.4k.mp4", "Magik_topaz_4k.mp4"),
    ("Magik.mp4", "Magik.iris3.mp4"),
    ("Euphoria.4k60.mp4", "Euphoria.1440p.mp4"),
    ("Scene.h265.mp4", "Scene.h264.mp4"),
    ("Magik [E-Stim Edit].mp4", "Magik.mp4"),
    ("Magik (final).mp4", "Magik.mp4"),
    # video ↔ its channel funscripts collapse to one title
    ("Magik.mp4", "Magik.alpha.funscript"),
    ("Magik.mp4", "Magik.pulse_frequency.funscript"),
    ("Magik.mp4", "Magik.alpha-prostate.funscript"),
])
def test_same_title_collapses(a, b):
    assert key(a) == key(b), f"{a!r} and {b!r} should be the same title"


# ── Identity differences SPLIT (different titles) ─────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("Magik Vol 1.mp4", "Magik Vol 2.mp4"),
    ("Magik Volume 1.mp4", "Magik Volume 2.mp4"),
    ("Magik Pt 1.mp4", "Magik Pt 2.mp4"),
    ("Magik Part 1.mp4", "Magik Part 2.mp4"),
    ("Show Ep 3.mp4", "Show Ep 4.mp4"),
    ("Magik 1.mp4", "Magik 2.mp4"),
    ("Magik.mp4", "Magik 2.mp4"),            # original vs sequel
    ("Magik.mp4", "Prisoner.mp4"),           # unrelated
])
def test_different_title_splits(a, b):
    assert key(a) != key(b), f"{a!r} and {b!r} should be different titles"


# ── Ordinal normalization: synonyms collapse, classes stay distinct ───────────

def test_ordinal_synonyms_collapse():
    # Vol / Volume, across resolutions, are the same title.
    assert key("Magik Vol 1.4k.mp4") == key("Magik Volume 1.1080p.mp4")


def test_ordinal_classes_stay_distinct():
    # Vol 1 and Part 1 are treated as different works (prefer splitting).
    assert key("Magik Vol 1.mp4") != key("Magik Part 1.mp4")


def test_ordinal_and_variants_together():
    # Vol 2 in 4k, Vol 2 topaz, Vol 2 alpha channel → all one title.
    a = key("Magik Vol 2.4k.mp4")
    b = key("Magik Vol 2_topaz.mp4")
    c = key("Magik Vol 2.beta.funscript")
    assert a == b == c


# ── Ordinal parsing details ───────────────────────────────────────────────────

@pytest.mark.parametrize("name,cls,num", [
    ("Magik Vol 3.mp4", "volume", 3),
    ("Magik vol.3.mp4", "volume", 3),
    ("Magik Pt 2.mp4", "part", 2),
    ("Show Episode 12.mp4", "episode", 12),
    ("Set Disc 2.mp4", "disc", 2),
    ("Magik 5.mp4", "", 5),
])
def test_ordinal_extraction(name, cls, num):
    rf = canonicalize(name)
    assert rf.ordinal is not None
    assert rf.ordinal.cls == cls
    assert rf.ordinal.number == num


def test_no_false_ordinal_from_glued_number():
    # A number glued to a word (no separator) is NOT a bare ordinal.
    assert canonicalize("Area51.mp4").ordinal is None


def test_upscaler_digits_not_ordinal():
    # iris3 is an upscaler, not "part 3" — stripped, no ordinal.
    rf = canonicalize("Magik.iris3.mp4")
    assert rf.ordinal is None
    assert "iris" in rf.variant_tags
    assert rf.canonical_key == "magik"


# ── Variant tags & resolution bucket ──────────────────────────────────────────

def test_resolution_bucket_and_tags():
    rf = canonicalize("Magik_topaz_4k.mp4")
    assert rf.resolution == "4k"
    assert "topaz" in rf.variant_tags
    assert rf.is_upscaled is True


def test_channel_recorded():
    rf = canonicalize("Magik.alpha-prostate.funscript")
    assert rf.role is Role.FUNSCRIPT
    assert rf.channel == "alpha-prostate"
    assert rf.channel_info is not None
    assert rf.channel_info.is_prostate is True
    assert rf.canonical_key == "magik"


def test_main_funscript_has_empty_channel():
    rf = canonicalize("Magik.funscript")
    assert rf.role is Role.FUNSCRIPT
    assert rf.channel == ""


# ── Robustness ────────────────────────────────────────────────────────────────

def test_key_never_empty():
    assert canonicalize("4k.mp4").canonical_key
    assert canonicalize("1080p.funscript").canonical_key


def test_path_accepted():
    a = canonicalize(r"C:\media\Magik\Magik.4k.mp4").cluster_key
    b = canonicalize("Magik.1080p.mp4").cluster_key
    assert a == b


def test_separators_normalized():
    assert key("Victoria_Oaks.4k.mp4") == key("Victoria.Oaks.1080p.mp4")
    assert key("Victoria Oaks.mp4") == key("victoria_oaks.mp4")
