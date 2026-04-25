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
from app.stim_audio_output import (
    StimAudioStream,
    _TimeSmoother,
    query_device_sample_rate,
    resolve_audio_device,
)
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

@pytest.fixture
def fake_sd_no_devices(monkeypatch):
    """sounddevice mock that returns no matching devices — exercises the
    description-fallback path (sounddevice can't disambiguate, so caller
    relies on substring matching)."""
    fake = types.ModuleType("sounddevice")
    fake.query_devices = MagicMock(return_value=[])
    fake.query_hostapis = MagicMock(return_value={"name": "Windows WASAPI"})
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    return fake


@pytest.fixture
def fake_sd_with_devices(monkeypatch):
    """sounddevice mock with realistic Windows enumeration: same device
    name on multiple host APIs (the bug that drove the resolver fix)."""
    fake = types.ModuleType("sounddevice")
    fake.query_devices = MagicMock(return_value=[
        # idx 0-1: MME duplicates
        {"name": "Speakers (USB Audio Device)", "max_output_channels": 2, "hostapi": 0},
        {"name": "Speakers (USB Audio Device)", "max_output_channels": 2, "hostapi": 0},
        # idx 2-3: DirectSound
        {"name": "Speakers (USB Audio Device)", "max_output_channels": 2, "hostapi": 1},
        {"name": "Speakers (USB Audio Device)", "max_output_channels": 2, "hostapi": 1},
        # idx 4: WASAPI (the unique one we want)
        {"name": "Speakers (USB Audio Device)", "max_output_channels": 2, "hostapi": 2},
        # idx 5: a different device
        {"name": "Speakers (Realtek(R) Audio)", "max_output_channels": 2, "hostapi": 2},
    ])
    fake.query_hostapis = MagicMock(side_effect=lambda i: [
        {"name": "MME"},
        {"name": "Windows DirectSound"},
        {"name": "Windows WASAPI"},
    ][i])
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    return fake


class TestResolveAudioDevice:
    def test_returns_int_index_when_unique_wasapi_match(self, fake_sd_with_devices):
        mpv_devices = [
            {"name": "wasapi/{aaa}", "description": "Speakers (USB Audio Device)"},
        ]
        # Filtered by WASAPI host → only idx 4 matches.
        assert resolve_audio_device("wasapi/{aaa}", mpv_devices) == 4

    def test_picks_first_when_multiple_wasapi_matches(self, monkeypatch):
        """Two physically-identical dongles both on WASAPI — pick first
        deterministically. User can swap dongles physically if wrong one
        activates."""
        fake = types.ModuleType("sounddevice")
        fake.query_devices = MagicMock(return_value=[
            {"name": "Speakers (USB Audio Device)", "max_output_channels": 2, "hostapi": 0},
            {"name": "Speakers (USB Audio Device)", "max_output_channels": 2, "hostapi": 0},
        ])
        fake.query_hostapis = MagicMock(return_value={"name": "Windows WASAPI"})
        monkeypatch.setitem(sys.modules, "sounddevice", fake)

        mpv_devices = [
            {"name": "wasapi/{aaa}", "description": "Speakers (USB Audio Device)"},
        ]
        assert resolve_audio_device("wasapi/{aaa}", mpv_devices) == 0

    def test_position_pairs_mpv_with_sounddevice(self, monkeypatch):
        """When mpv has TWO entries sharing description on the same host
        and sounddevice also has two, pair by enumeration position so
        each mpv id resolves to a different sounddevice index."""
        fake = types.ModuleType("sounddevice")
        fake.query_devices = MagicMock(return_value=[
            {"name": "Speakers (USB Audio Device)", "max_output_channels": 2, "hostapi": 0},
            {"name": "Speakers (USB Audio Device)", "max_output_channels": 2, "hostapi": 0},
        ])
        fake.query_hostapis = MagicMock(return_value={"name": "Windows WASAPI"})
        monkeypatch.setitem(sys.modules, "sounddevice", fake)

        mpv_devices = [
            {"name": "wasapi/{aaa}", "description": "Speakers (USB Audio Device)"},
            {"name": "wasapi/{bbb}", "description": "Speakers (USB Audio Device)"},
        ]
        # Position 0 in mpv list → sounddevice index 0.
        assert resolve_audio_device("wasapi/{aaa}", mpv_devices) == 0
        # Position 1 in mpv list → sounddevice index 1 (NOT 0).
        assert resolve_audio_device("wasapi/{bbb}", mpv_devices) == 1

    def test_falls_back_to_description_when_sounddevice_unavailable(self, fake_sd_no_devices):
        """If sounddevice can't see the device (no match), return the
        description so sounddevice's substring matcher can try."""
        mpv_devices = [
            {"name": "wasapi/{aaa}", "description": "Speakers (USB Audio Device)"},
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


class TestQueryDeviceSampleRate:
    def test_returns_device_default_rate(self, monkeypatch):
        fake = types.ModuleType("sounddevice")
        fake.query_devices = MagicMock(return_value={"default_samplerate": 48000})
        monkeypatch.setitem(sys.modules, "sounddevice", fake)

        assert query_device_sample_rate(20) == 48000

    def test_falls_back_to_default_on_error(self, monkeypatch):
        fake = types.ModuleType("sounddevice")
        fake.query_devices = MagicMock(side_effect=RuntimeError("device gone"))
        monkeypatch.setitem(sys.modules, "sounddevice", fake)

        assert query_device_sample_rate(99) == 44100

    def test_falls_back_when_rate_zero(self, monkeypatch):
        fake = types.ModuleType("sounddevice")
        fake.query_devices = MagicMock(return_value={"default_samplerate": 0})
        monkeypatch.setitem(sys.modules, "sounddevice", fake)

        assert query_device_sample_rate(20) == 44100

    def test_handle_none_queries_system_default(self, monkeypatch):
        fake = types.ModuleType("sounddevice")
        fake.query_devices = MagicMock(return_value={"default_samplerate": 44100})
        monkeypatch.setitem(sys.modules, "sounddevice", fake)

        assert query_device_sample_rate(None) == 44100
        # Verify it was called with kind="output", not a device handle.
        fake.query_devices.assert_called_with(kind="output")


# ── _TimeSmoother ─────────────────────────────────────────────────────────────

class TestTimeSmoother:
    """Restim-pattern smoother for the media clock fed to the synth."""

    def _block(self, frame_offset: int, n: int, sample_rate: int = 48000) -> np.ndarray:
        return (np.arange(n) + frame_offset) / sample_rate

    def test_first_callback_adopts_observed_offset_wholesale(self):
        sm = _TimeSmoother()
        steady = self._block(0, 1024)
        # Observed offset = media_time - steady_clock[-1] = 5.0 - end
        media_time = 5.0
        out = sm.update(steady, media_time, sample_rate=48000)

        # First-call shortcut: system_time_estimate = steady + observed_offset.
        expected_offset = media_time - float(steady[-1])
        np.testing.assert_allclose(out, steady + expected_offset)
        assert sm.offset == pytest.approx(expected_offset)

    def test_jitter_is_smoothed_not_followed(self):
        """A single noisy media-time observation should NOT pull the
        smoothed offset all the way — that's the whole point."""
        sm = _TimeSmoother()
        sample_rate = 48000

        # Establish baseline at t=5.0 (steady=0..1024/sr).
        steady0 = self._block(0, 1024)
        sm.update(steady0, media_time=5.0, sample_rate=sample_rate)
        baseline_offset = sm.offset

        # Next callback: jittery media-time jumps an extra 50 ms.
        steady1 = self._block(1024, 1024)
        # Steady continues linearly. Media time jumps:
        # The "expected" media_time for this block end is 5.0 + 1024/sr ≈ 5.021.
        # We add 50 ms of jitter.
        expected_media = 5.0 + 1024 / sample_rate
        jittery_media = expected_media + 0.050
        sm.update(steady1, media_time=jittery_media, sample_rate=sample_rate)

        # The offset should have moved slightly toward the jitter, not
        # all the way to it. Max drift per block = (1024/48000) * 0.02 ≈
        # 0.43 ms — much less than the 50 ms jitter.
        delta = sm.offset - baseline_offset
        assert abs(delta) < 0.001  # well below the 50 ms jitter

    def test_seek_raises_resync_required(self):
        sm = _TimeSmoother()
        sample_rate = 48000

        steady0 = self._block(0, 1024)
        sm.update(steady0, media_time=5.0, sample_rate=sample_rate)

        # Big jump (user seeked from t=5 to t=180).
        steady1 = self._block(1024, 1024)
        with pytest.raises(_TimeSmoother.ResyncRequired):
            sm.update(steady1, media_time=180.0, sample_rate=sample_rate)

    def test_reset_returns_to_uninitialized(self):
        sm = _TimeSmoother()
        sample_rate = 48000
        steady = self._block(0, 1024)
        sm.update(steady, media_time=5.0, sample_rate=sample_rate)

        sm.reset()

        # First update after reset adopts the new offset wholesale (no
        # smoothing yet because there's no history).
        steady2 = self._block(0, 1024)
        sm.update(steady2, media_time=180.0, sample_rate=sample_rate)
        assert sm.offset == pytest.approx(180.0 - float(steady2[-1]))

    def test_notify_seek_avoids_resync_exception(self):
        """When notify_seek (via reset) is called between blocks, the
        next update adopts the new offset wholesale even if it's a
        >1 s jump — no ResyncRequired raised, no silenced block."""
        sm = _TimeSmoother()
        sample_rate = 48000

        steady0 = self._block(0, 1024)
        sm.update(steady0, media_time=5.0, sample_rate=sample_rate)

        # Caller (StimAudioStream.notify_seek) resets the smoother
        # because a seek to t=180 just happened.
        sm.reset()

        # First update after reset: the 180-second jump is fine, no
        # exception, smoother adopts new offset.
        steady1 = self._block(1024, 1024)
        out = sm.update(steady1, media_time=180.0, sample_rate=sample_rate)
        expected_offset = 180.0 - float(steady1[-1])
        assert sm.offset == pytest.approx(expected_offset)
        np.testing.assert_allclose(out, steady1 + expected_offset)

    def test_output_is_monotonic_within_block(self):
        """The system_time_estimate ramp must be monotonic (non-decreasing)
        for the synth's per-sample axis interpolation to work right."""
        sm = _TimeSmoother()
        sample_rate = 48000

        steady0 = self._block(0, 1024)
        sm.update(steady0, media_time=5.0, sample_rate=sample_rate)
        # A normal (small) clock advance.
        steady1 = self._block(1024, 1024)
        media1 = 5.0 + 1024 / sample_rate + 0.020  # 20 ms jitter
        out = sm.update(steady1, media_time=media1, sample_rate=sample_rate)

        assert np.all(np.diff(out) >= 0), "system_time_estimate must be monotonic"


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
            # blocksize=0 means "let driver pick" — more reliable on USB
            # dongles than pinning a small explicit value.
            assert kwargs["blocksize"] == 0
            assert kwargs["latency"] == "high"
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
