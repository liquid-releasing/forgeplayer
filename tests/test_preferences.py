# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for Preferences load/save round-trip and field validation.

Focuses on the v0.0.2 audio_algorithm + haptic_offset_ms fields, which
gate StimSynth behavior. Stale or hand-edited prefs.json values must
fall back to safe defaults rather than crash the synth at launch time.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.preferences import Preferences


@pytest.fixture
def temp_prefs_path(tmp_path: Path):
    fake = tmp_path / "preferences.json"
    with patch("app.preferences._PREFS_PATH", fake):
        yield fake


class TestDefaults:
    def test_audio_algorithm_default_is_pulse(self):
        # ForgePlayer defaults to pulse-based: our content pipeline
        # (FunscriptForge + modern audio-based stereostim) lives on pulse.
        # 312/2B owners flip to Continuous once in Setup.
        p = Preferences()
        assert p.audio_algorithm == "pulse"

    def test_haptic_offset_default_is_zero(self):
        p = Preferences()
        assert p.haptic_offset_ms == 0

    def test_scene_audio_secondary_device_default_is_empty(self):
        # Empty means feature off — no mirror spawned. Makes the
        # feature opt-in for users who actually have a second
        # audio-capable stim device wired up.
        p = Preferences()
        assert p.scene_audio_secondary_device == ""


class TestRoundTrip:
    def test_save_and_load_preserves_audio_algorithm(self, temp_prefs_path):
        p = Preferences(audio_algorithm="pulse")
        p.save()

        loaded = Preferences.load()
        assert loaded.audio_algorithm == "pulse"

    def test_save_and_load_preserves_offset(self, temp_prefs_path):
        p = Preferences(haptic_offset_ms=120)
        p.save()

        loaded = Preferences.load()
        assert loaded.haptic_offset_ms == 120

    def test_save_and_load_preserves_scene_audio_secondary_device(
        self, temp_prefs_path,
    ):
        p = Preferences(scene_audio_secondary_device="wasapi/{abc-123}")
        p.save()

        loaded = Preferences.load()
        assert loaded.scene_audio_secondary_device == "wasapi/{abc-123}"


class TestLoadValidation:
    def test_invalid_algorithm_falls_back_to_default(self, temp_prefs_path):
        temp_prefs_path.parent.mkdir(parents=True, exist_ok=True)
        temp_prefs_path.write_text(json.dumps({"audio_algorithm": "garbage"}))

        loaded = Preferences.load()
        assert loaded.audio_algorithm == "pulse"

    def test_offset_clamped_to_safety_range(self, temp_prefs_path):
        # 10000ms is wildly out of range — almost certainly hand-edited
        # or corrupted. Clamp rather than reject the whole file.
        temp_prefs_path.parent.mkdir(parents=True, exist_ok=True)
        temp_prefs_path.write_text(json.dumps({"haptic_offset_ms": 10000}))

        loaded = Preferences.load()
        assert loaded.haptic_offset_ms == 500

    def test_offset_negative_clamped(self, temp_prefs_path):
        temp_prefs_path.parent.mkdir(parents=True, exist_ok=True)
        temp_prefs_path.write_text(json.dumps({"haptic_offset_ms": -10000}))

        loaded = Preferences.load()
        assert loaded.haptic_offset_ms == -500

    def test_non_int_offset_falls_back(self, temp_prefs_path):
        temp_prefs_path.parent.mkdir(parents=True, exist_ok=True)
        temp_prefs_path.write_text(json.dumps({"haptic_offset_ms": "fast"}))

        loaded = Preferences.load()
        assert loaded.haptic_offset_ms == 0

    def test_missing_file_returns_defaults(self, temp_prefs_path):
        # File doesn't exist yet — first run.
        loaded = Preferences.load()
        assert loaded.audio_algorithm == "pulse"
        assert loaded.haptic_offset_ms == 0
