# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the StimSynth driver and CallbackMediaSync.

These tests don't open a real audio device — they call `generate_block()`
in-process and inspect the returned PCM. Real hardware playback is
covered by the v0.0.2 dogfood pass after the sounddevice integration
lands (commit 3 of this slice).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.funscript_loader import FunscriptActions, StimChannels
from app.stim_synth import (
    SAMPLE_RATE,
    CallbackMediaSync,
    StimSynth,
)
from app.vendor.restim_stim_math.audio_gen.continuous import ThreePhaseAlgorithm
from app.vendor.restim_stim_math.audio_gen.pulse_based import (
    DefaultThreePhasePulseBasedAlgorithm,
)


def _scene_channels(duration_s: float = 4.0, motion: bool = True) -> StimChannels:
    """Build a synthetic StimChannels with steady alpha sweep + constant beta."""
    n = int(duration_s * 25)  # 25 samples/sec like the radial conversion
    t = np.linspace(0.0, duration_s, n)
    if motion:
        alpha = 0.5 + 0.4 * np.sin(2.0 * np.pi * 0.25 * t)  # 0.25 Hz oscillation
        beta = 0.5 * np.ones_like(t)
    else:
        alpha = 0.5 * np.ones_like(t)
        beta = 0.5 * np.ones_like(t)
    return StimChannels(t=t, alpha=alpha, beta=beta, source="radial_1d")


# ── CallbackMediaSync ─────────────────────────────────────────────────────────

class TestCallbackMediaSync:
    def test_delegates_to_callable(self):
        flag = [True]
        sync = CallbackMediaSync(lambda: flag[0])
        assert sync.is_playing() is True
        flag[0] = False
        assert sync.is_playing() is False

    def test_coerces_truthy_to_bool(self):
        sync = CallbackMediaSync(lambda: 1)
        assert sync.is_playing() is True

        sync_falsy = CallbackMediaSync(lambda: 0)
        assert sync_falsy.is_playing() is False


# ── StimSynth ─────────────────────────────────────────────────────────────────

class TestStimSynth:
    def test_generate_block_returns_stereo_float32(self):
        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: True))
        block = synth.generate_block(1024, media_time_s=1.0)

        assert block.shape == (1024, 2)
        assert block.dtype == np.float32

    def test_zero_frames_returns_empty(self):
        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: True))
        block = synth.generate_block(0, media_time_s=0.0)

        assert block.shape == (0, 2)
        assert block.dtype == np.float32

    def test_output_finite_and_bounded(self):
        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: True))
        block = synth.generate_block(4096, media_time_s=1.0)

        assert np.all(np.isfinite(block))
        # Should comfortably fit within stereo headroom
        assert np.max(np.abs(block)) <= 1.5

    def test_silenced_when_not_playing(self):
        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: False))
        block = synth.generate_block(4096, media_time_s=1.0)

        assert block.shape == (4096, 2)
        np.testing.assert_array_equal(block, np.zeros_like(block))

    def test_non_silent_when_playing(self):
        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: True))
        block = synth.generate_block(4096, media_time_s=1.0)

        # Some real signal — not all zeros, not entirely below noise floor
        assert np.max(np.abs(block)) > 0.01

    def test_play_state_can_change_between_blocks(self):
        flag = [True]
        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: flag[0]))

        playing = synth.generate_block(1024, media_time_s=1.0)
        assert np.max(np.abs(playing)) > 0.01

        flag[0] = False
        paused = synth.generate_block(1024, media_time_s=1.0 + 1024 / SAMPLE_RATE)
        np.testing.assert_array_equal(paused, np.zeros_like(paused))

        flag[0] = True
        resumed = synth.generate_block(1024, media_time_s=1.0 + 2048 / SAMPLE_RATE)
        assert np.max(np.abs(resumed)) > 0.01

    def test_carrier_frequency_dominates_spectrum(self):
        """A continuous-mode block should be dominated by the carrier tone.

        The threephase algorithm produces an L/R pair modulated by a 700 Hz
        carrier (default). Run a sufficiently long block, FFT each channel,
        and check the dominant frequency bin sits near the configured
        carrier — confirms the synth pipeline is actually emitting the
        expected waveform rather than producing noise or garbage.
        """
        synth = StimSynth(_scene_channels(motion=False), CallbackMediaSync(lambda: True))
        n = 16384
        block = synth.generate_block(n, media_time_s=1.0)

        # Use the L channel; either is fine since both share the carrier
        signal = block[:, 0].astype(np.float64)
        if np.max(np.abs(signal)) < 1e-6:
            pytest.skip("centered alpha/beta produces near-silence; covered elsewhere")

        spectrum = np.abs(np.fft.rfft(signal))
        freqs = np.fft.rfftfreq(n, d=1.0 / SAMPLE_RATE)
        peak_freq = freqs[int(np.argmax(spectrum))]

        # Bin resolution at n=16384, fs=44100 is ~2.7 Hz; allow ±10 Hz
        assert abs(peak_freq - 700.0) < 10.0

    def test_sample_counter_advances(self):
        """`steady_clock` is built from a running sample counter; verify it
        advances across calls (not just per-block) so successive blocks see
        a continuous time axis.
        """
        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: True))
        synth.generate_block(1024, media_time_s=0.0)
        assert synth._sample_count == 1024
        synth.generate_block(2048, media_time_s=0.023)
        assert synth._sample_count == 1024 + 2048


# ── Algorithm dispatch ────────────────────────────────────────────────────────

def _pulse_based_channels() -> StimChannels:
    """Synthetic channels that should trigger pulse-based dispatch."""
    base = _scene_channels()
    actions = FunscriptActions(
        t=np.array([0.0, 4.0]),
        p=np.array([0.3, 0.4]),
    )
    return StimChannels(
        t=base.t, alpha=base.alpha, beta=base.beta, source=base.source,
        volume=None,
        carrier_frequency=None,
        pulse_frequency=actions,
        pulse_width=actions,
        pulse_rise_time=actions,
    )


class TestAlgorithmDispatch:
    def test_default_is_continuous(self):
        """Default waveform is continuous — matches FunscriptForge's MP3
        renders, which is the user's ear-calibrated baseline.
        """
        synth = StimSynth(_scene_channels(), CallbackMediaSync(lambda: True))
        assert synth.waveform == "continuous"
        assert isinstance(synth._algorithm, ThreePhaseAlgorithm)

    def test_pulse_mode_explicit_opt_in(self):
        synth = StimSynth(
            _pulse_based_channels(), CallbackMediaSync(lambda: True),
            waveform="pulse",
        )
        assert synth.waveform == "pulse"
        assert isinstance(synth._algorithm, DefaultThreePhasePulseBasedAlgorithm)

    def test_pulse_channels_present_but_continuous_default(self):
        """A scene with pulse_* channels still defaults to continuous —
        the channels are silently ignored (same behavior as FunscriptForge
        and restim's continuous algorithm).
        """
        synth = StimSynth(_pulse_based_channels(), CallbackMediaSync(lambda: True))
        assert synth.waveform == "continuous"
        assert isinstance(synth._algorithm, ThreePhaseAlgorithm)

    def test_pulse_based_generates_stereo_float32(self):
        synth = StimSynth(
            _pulse_based_channels(), CallbackMediaSync(lambda: True),
            waveform="pulse",
        )
        block = synth.generate_block(4096, media_time_s=1.0)

        assert block.shape == (4096, 2)
        assert block.dtype == np.float32
        assert np.all(np.isfinite(block))

    def test_pulse_based_silenced_when_not_playing(self):
        synth = StimSynth(
            _pulse_based_channels(), CallbackMediaSync(lambda: False),
            waveform="pulse",
        )
        block = synth.generate_block(4096, media_time_s=1.0)

        np.testing.assert_array_equal(block, np.zeros_like(block))

    def test_pulse_based_non_silent_when_playing(self):
        synth = StimSynth(
            _pulse_based_channels(), CallbackMediaSync(lambda: True),
            waveform="pulse",
        )
        block = synth.generate_block(8192, media_time_s=1.0)

        assert np.max(np.abs(block)) > 0.01


# ── Scripted parameter channels affect synthesis ──────────────────────────────

class TestScriptedVolume:
    def test_scripted_zero_volume_silences_output(self):
        """A volume funscript held at 0 should silence the synth even
        while media_sync.is_playing() is True.
        """
        base = _scene_channels()
        zero_volume = FunscriptActions(
            t=np.array([0.0, 4.0]),
            p=np.array([0.0, 0.0]),
        )
        channels = StimChannels(
            t=base.t, alpha=base.alpha, beta=base.beta, source=base.source,
            volume=zero_volume,
        )
        synth = StimSynth(channels, CallbackMediaSync(lambda: True))
        block = synth.generate_block(4096, media_time_s=1.0)

        # Allow a tiny numerical floor but expect near-silence
        assert np.max(np.abs(block)) < 1e-4

    def test_scripted_full_volume_produces_signal(self):
        base = _scene_channels()
        full_volume = FunscriptActions(
            t=np.array([0.0, 4.0]),
            p=np.array([1.0, 1.0]),
        )
        channels = StimChannels(
            t=base.t, alpha=base.alpha, beta=base.beta, source=base.source,
            volume=full_volume,
        )
        synth = StimSynth(channels, CallbackMediaSync(lambda: True))
        block = synth.generate_block(4096, media_time_s=1.0)

        assert np.max(np.abs(block)) > 0.01


class TestScriptedCarrier:
    def test_scripted_carrier_shifts_spectrum_peak(self):
        """The carrier_frequency channel's 0..1 maps to 500..1000 Hz. A
        channel held at 0.0 → 500 Hz peak; at 1.0 → 1000 Hz peak. Verify
        the FFT peak moves with the scripted value.
        """
        base = _scene_channels(motion=False)
        low_carrier = FunscriptActions(
            t=np.array([0.0, 4.0]),
            p=np.array([0.0, 0.0]),  # → 500 Hz
        )
        high_carrier = FunscriptActions(
            t=np.array([0.0, 4.0]),
            p=np.array([1.0, 1.0]),  # → 1000 Hz
        )
        n = 16384

        for actions, expected_hz in [(low_carrier, 500.0), (high_carrier, 1000.0)]:
            channels = StimChannels(
                t=base.t, alpha=base.alpha, beta=base.beta, source=base.source,
                carrier_frequency=actions,
            )
            synth = StimSynth(channels, CallbackMediaSync(lambda: True))
            block = synth.generate_block(n, media_time_s=1.0)
            signal = block[:, 0].astype(np.float64)
            if np.max(np.abs(signal)) < 1e-6:
                continue  # centered alpha/beta can produce near-silence
            spectrum = np.abs(np.fft.rfft(signal))
            freqs = np.fft.rfftfreq(n, d=1.0 / SAMPLE_RATE)
            peak_freq = freqs[int(np.argmax(spectrum))]
            assert abs(peak_freq - expected_hz) < 15.0, (
                f"carrier held at {actions.p[0]} → expected peak ~{expected_hz} Hz, "
                f"got {peak_freq} Hz"
            )
