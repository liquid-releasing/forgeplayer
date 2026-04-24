# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the audio-output streaming wrapper.

These tests stub sounddevice so the suite can run on machines (and CI)
without PortAudio. Real-hardware playback gets exercised by the
`scripts/test_stim_audio.py` dogfood utility, not the test suite.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.funscript_loader import StimChannels
from app.stim_audio_output import StimAudioStream, resolve_audio_device
from app.stim_synth import CallbackMediaSync, StimSynth


# ── Test fixtures ─────────────────────────────────────────────────────────────

def _scene_channels() -> StimChannels:
    n = 100
    t = np.linspace(0.0, 4.0, n)
    return StimChannels(
        t=t,
        alpha=0.5 + 0.4 * np.sin(2.0 * np.pi * 0.25 * t),
        beta=0.5 * np.ones_like(t),
        source="radial_1d",
    )


@pytest.fixture
def fake_sounddevice(monkeypatch):
    """Replace `sounddevice` import inside stim_audio_output with a mock.

    The mock captures OutputStream construction args, exposes start/stop
    as no-ops, and lets tests fire the callback by hand to verify the
    synth → buffer write path.
    """
    fake = types.ModuleType("sounddevice")
    fake.OutputStream = MagicMock()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    return fake


# ── resolve_audio_device ──────────────────────────────────────────────────────

class TestResolveAudioDevice:
    def test_returns_description_for_matching_id(self):
        mpv_devices = [
            {"name": "wasapi/{aaa}", "description": "Speakers (USB Audio Device)"},
            {"name": "wasapi/{bbb}", "description": "Speakers (Realtek(R) Audio)"},
        ]
        assert resolve_audio_device("wasapi/{aaa}", mpv_devices) == "Speakers (USB Audio Device)"

    def test_returns_none_for_empty_id(self):
        assert resolve_audio_device("", []) is None
        assert resolve_audio_device(None, []) is None

    def test_returns_none_for_auto(self):
        assert resolve_audio_device("auto", []) is None

    def test_returns_none_when_id_not_in_list(self):
        mpv_devices = [{"name": "wasapi/{aaa}", "description": "Speakers"}]
        assert resolve_audio_device("wasapi/{ccc}", mpv_devices) is None

    def test_returns_none_when_description_blank(self):
        """A device with a blank description should fall through to default
        rather than asking sounddevice to match against an empty string."""
        mpv_devices = [{"name": "wasapi/{aaa}", "description": ""}]
        assert resolve_audio_device("wasapi/{aaa}", mpv_devices) is None


# ── StimAudioStream ───────────────────────────────────────────────────────────

class TestStimAudioStream:
    def test_resolves_device_name_at_construction(self):
        stream = StimAudioStream(
            synth=StimSynth(_scene_channels(), CallbackMediaSync(lambda: True)),
            time_source=lambda: 0.0,
            device_id="wasapi/{aaa}",
            mpv_devices=[
                {"name": "wasapi/{aaa}", "description": "USB Audio CODEC"},
            ],
        )
        assert stream.device_name == "USB Audio CODEC"
        assert stream.is_running() is False

    def test_falls_back_to_default_when_no_pref(self):
        stream = StimAudioStream(
            synth=StimSynth(_scene_channels(), CallbackMediaSync(lambda: True)),
            time_source=lambda: 0.0,
            device_id=None,
            mpv_devices=[],
        )
        assert stream.device_name is None

    def test_start_opens_output_stream(self, fake_sounddevice):
        stream = StimAudioStream(
            synth=StimSynth(_scene_channels(), CallbackMediaSync(lambda: True)),
            time_source=lambda: 0.0,
            device_id=None,
            mpv_devices=[],
        )
        stream.start()
        try:
            fake_sounddevice.OutputStream.assert_called_once()
            kwargs = fake_sounddevice.OutputStream.call_args.kwargs
            assert kwargs["samplerate"] == 44100
            assert kwargs["channels"] == 2
            assert kwargs["dtype"] == "float32"
            assert kwargs["blocksize"] == 512
            assert kwargs["device"] is None
            assert callable(kwargs["callback"])
            assert stream.is_running() is True
        finally:
            stream.stop()

    def test_start_is_idempotent(self, fake_sounddevice):
        stream = StimAudioStream(
            synth=StimSynth(_scene_channels(), CallbackMediaSync(lambda: True)),
            time_source=lambda: 0.0,
        )
        stream.start()
        stream.start()
        assert fake_sounddevice.OutputStream.call_count == 1
        stream.stop()

    def test_stop_closes_stream(self, fake_sounddevice):
        stream = StimAudioStream(
            synth=StimSynth(_scene_channels(), CallbackMediaSync(lambda: True)),
            time_source=lambda: 0.0,
        )
        stream.start()
        mock_stream = fake_sounddevice.OutputStream.return_value
        stream.stop()
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert stream.is_running() is False

    def test_stop_without_start_is_safe(self):
        stream = StimAudioStream(
            synth=StimSynth(_scene_channels(), CallbackMediaSync(lambda: True)),
            time_source=lambda: 0.0,
        )
        stream.stop()  # should not raise

    def test_callback_pulls_from_synth(self, fake_sounddevice):
        time_calls: list[float] = []
        media_t = 1.5

        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: True))
        stream = StimAudioStream(
            synth=synth,
            time_source=lambda: (time_calls.append(media_t), media_t)[1],
            device_id=None,
            mpv_devices=[],
        )
        stream.start()

        callback = fake_sounddevice.OutputStream.call_args.kwargs["callback"]
        outdata = np.zeros((512, 2), dtype=np.float32)
        callback(outdata, 512, None, None)

        assert time_calls == [media_t], "time_source should be invoked exactly once per callback"
        assert outdata.shape == (512, 2)
        assert np.any(outdata != 0), "synth should have written non-zero samples"

        stream.stop()

    def test_callback_silences_on_synth_error(self, fake_sounddevice):
        """If the synth's `generate_block` raises (e.g. transient stale
        time_source), the callback must still write to outdata — sounddevice
        keeps the previous buffer otherwise, producing buzz.
        """
        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: True))
        broken_time = MagicMock(side_effect=RuntimeError("boom"))

        stream = StimAudioStream(
            synth=synth, time_source=broken_time, device_id=None, mpv_devices=[],
        )
        stream.start()
        callback = fake_sounddevice.OutputStream.call_args.kwargs["callback"]
        outdata = np.full((512, 2), 0.5, dtype=np.float32)

        callback(outdata, 512, None, None)

        np.testing.assert_array_equal(outdata, np.zeros_like(outdata))
        stream.stop()
