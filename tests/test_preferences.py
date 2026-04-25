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
    def test_audio_algorithm_default_is_continuous(self):
        # Restim's own default is continuous. Match it so the .mp3
        # baseline experience is what the user gets out of the box.
        p = Preferences()
        assert p.audio_algorithm == "continuous"

    def test_haptic_offset_default_is_zero(self):
        p = Preferences()
        assert p.haptic_offset_ms == 0


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


class TestLoadValidation:
    def test_invalid_algorithm_falls_back_to_default(self, temp_prefs_path):
        temp_prefs_path.parent.mkdir(parents=True, exist_ok=True)
        temp_prefs_path.write_text(json.dumps({"audio_algorithm": "garbage"}))

        loaded = Preferences.load()
        assert loaded.audio_algorithm == "continuous"

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
        assert loaded.audio_algorithm == "continuous"
        assert loaded.haptic_offset_ms == 0
