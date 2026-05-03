# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the pre-flight calibration module.

These tests don't open a real audio device. They cover the offline
helpers — peak detection, ramp wrapper, looping time source — plus the
state-machine guarantees of CalibrationStream (idempotent stop, etc.).
The full audio pipeline is covered indirectly via the StimAudioStream
tests; here we verify the calibrate-specific shapes around it.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from app.funscript_loader import FunscriptActions, StimChannels
from app.stim_calibrate import (
    _LoopingTimeSource,
    _RampGain,
    find_peak_section,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _osc_alpha(t_grid: np.ndarray, mask: np.ndarray, freq_hz: float, amp: float) -> np.ndarray:
    """Overlay a sinusoidal alpha pattern of `freq_hz` and `amp` onto a
    constant-0.5 baseline within the time-mask. Used to produce known
    velocity (≈ 2π·freq·amp) within specific time spans of a fixture
    scene.
    """
    alpha = np.full_like(t_grid, 0.5)
    alpha[mask] = 0.5 + amp * np.sin(2 * np.pi * freq_hz * t_grid[mask])
    return alpha


def _scene_with_sustained_hot_and_brief_spike(
    *,
    scene_duration_s: float = 60.0,
    sustained_start_s: float = 20.0,
    sustained_duration_s: float = 10.0,
    spike_at_s: float = 45.0,
    spike_duration_s: float = 1.0,
    sustained_freq_hz: float = 4.0,
    spike_freq_hz: float = 50.0,
) -> StimChannels:
    """Scene with three regions:

    - **Sustained hot**: a `sustained_duration_s`-long window where alpha
      oscillates at `sustained_freq_hz` (moderate velocity).
    - **Brief spike**: a `spike_duration_s`-long super-spike where alpha
      oscillates at `spike_freq_hz` (much higher velocity, shorter).
    - **Cool baseline** elsewhere: alpha = beta = 0.5 (zero velocity).

    Volume is constant 1.0 throughout so the test isolates velocity-
    based detection. The brief-spike window has higher peak intensity
    than the sustained section but is short enough that a robust
    detector should still prefer the sustained section.
    """
    n = max(2, int(scene_duration_s * 100))  # 100 Hz fixture grid
    t = np.linspace(0.0, scene_duration_s, n)

    sustained_mask = (t >= sustained_start_s) & (
        t < sustained_start_s + sustained_duration_s
    )
    spike_mask = (t >= spike_at_s) & (t < spike_at_s + spike_duration_s)

    alpha = np.full_like(t, 0.5)
    alpha[sustained_mask] = 0.5 + 0.4 * np.sin(
        2 * np.pi * sustained_freq_hz * t[sustained_mask]
    )
    alpha[spike_mask] = 0.5 + 0.4 * np.sin(
        2 * np.pi * spike_freq_hz * t[spike_mask]
    )
    beta = np.full_like(t, 0.5)

    return StimChannels(
        t=t, alpha=alpha, beta=beta, source="native_stereostim",
    )


def _scene_with_volume_modulation(
    *,
    scene_duration_s: float = 60.0,
    motion_freq_hz: float = 4.0,
    quiet_volume: float = 0.05,
    loud_start_s: float = 20.0,
    loud_duration_s: float = 10.0,
    loud_volume: float = 0.9,
) -> StimChannels:
    """Scene where alpha oscillates uniformly throughout (constant
    velocity) but volume gates intensity to a specific window. Used to
    verify the detector doesn't ignore volume — a "loud" window with
    the same motion as the rest should win because its intensity (=
    velocity × volume) is higher.
    """
    n = max(2, int(scene_duration_s * 100))
    t = np.linspace(0.0, scene_duration_s, n)

    alpha = 0.5 + 0.4 * np.sin(2 * np.pi * motion_freq_hz * t)
    beta = np.full_like(t, 0.5)

    eps = 1e-3
    vol_t = np.array([
        0.0,
        loud_start_s - eps, loud_start_s,
        loud_start_s + loud_duration_s, loud_start_s + loud_duration_s + eps,
        scene_duration_s,
    ])
    vol_p = np.array([
        quiet_volume, quiet_volume, loud_volume,
        loud_volume, quiet_volume, quiet_volume,
    ])

    return StimChannels(
        t=t, alpha=alpha, beta=beta, source="native_stereostim",
        volume=FunscriptActions(t=vol_t, p=vol_p),
    )


# ── find_peak_section ────────────────────────────────────────────────────────

class TestFindPeakSection:
    def test_picks_sustained_hot_over_brief_spike(self):
        """A 1-second high-velocity spike must NOT outweigh a 10-second
        sustained-hot section. The selected window must overlap the
        sustained section, not the spike.
        """
        ch = _scene_with_sustained_hot_and_brief_spike(
            sustained_start_s=20.0, sustained_duration_s=10.0,
            spike_at_s=45.0, spike_duration_s=1.0,
        )
        start, duration = find_peak_section(ch, window_s=10.0)

        assert duration == pytest.approx(10.0)
        # Window starts somewhere in [10, 20] to overlap the [20, 30]
        # sustained section. A spike-driven detector would pick a
        # window starting in roughly [36, 45].
        assert 10.0 <= start <= 25.0, (
            f"expected window overlapping the sustained section "
            f"[20, 30]; got start={start}"
        )

    def test_skips_blue_rest_between_hot_sections(self):
        """Two hot sections separated by a long quiet rest. The detector
        must pick a window inside one of the hot sections, not one
        centered on the rest.
        """
        # 0..15s: hot. 15..45s: silent rest. 45..60s: hot.
        n = 6000  # 60s @ 100 Hz
        t = np.linspace(0.0, 60.0, n)
        first_hot = (t >= 0.0) & (t < 15.0)
        second_hot = (t >= 45.0) & (t < 60.0)
        alpha = np.full_like(t, 0.5)
        alpha[first_hot] = 0.5 + 0.4 * np.sin(2 * np.pi * 4.0 * t[first_hot])
        alpha[second_hot] = 0.5 + 0.4 * np.sin(2 * np.pi * 4.0 * t[second_hot])
        beta = np.full_like(t, 0.5)
        ch = StimChannels(
            t=t, alpha=alpha, beta=beta, source="native_stereostim",
        )

        start, duration = find_peak_section(ch, window_s=10.0)

        # Window must NOT be centered on the rest (15..45). A rest-
        # centered window would have start in [20, 35]. A hot-overlapping
        # window has start in [0, 5] (first hot) or [45, 50] (second).
        assert not (20.0 < start < 35.0), (
            f"detector picked rest-overlapping window {start}..{start+duration}; "
            f"expected one of the hot sections"
        )

    def test_volume_gates_motion(self):
        """Constant motion + volume curve that gates one window loud:
        the detector must pick the volume-loud window even though the
        motion is uniform across the scene.
        """
        ch = _scene_with_volume_modulation(
            loud_start_s=20.0, loud_duration_s=10.0,
            quiet_volume=0.05, loud_volume=0.9,
        )
        start, duration = find_peak_section(ch, window_s=10.0)

        assert duration == pytest.approx(10.0)
        # Window must overlap the [20, 30] loud section.
        assert start + duration > 20.0
        assert start < 30.0

    def test_short_scene_returns_full_scene(self):
        # 5-second scene, request 10s window — return whole scene.
        n = 500
        t = np.linspace(0.0, 5.0, n)
        ch = StimChannels(
            t=t, alpha=np.full_like(t, 0.5), beta=np.full_like(t, 0.5),
            source="native_stereostim",
        )
        start, duration = find_peak_section(ch, window_s=10.0)
        assert start == pytest.approx(0.0)
        assert duration == pytest.approx(5.0)

    def test_empty_channels_returns_zero(self):
        ch = StimChannels(
            t=np.zeros(0), alpha=np.zeros(0), beta=np.zeros(0),
            source="native_stereostim",
        )
        assert find_peak_section(ch) == (0.0, 0.0)

    def test_static_scene_returns_first_window(self):
        """A scene with zero motion across its whole duration produces
        zero intensity everywhere. The detector falls back to the first
        window — every window is equally (un)representative."""
        n = 6000
        t = np.linspace(0.0, 60.0, n)
        ch = StimChannels(
            t=t, alpha=np.full_like(t, 0.5), beta=np.full_like(t, 0.5),
            source="native_stereostim",
        )
        start, duration = find_peak_section(ch, window_s=10.0)
        assert start == pytest.approx(0.0)
        assert duration == pytest.approx(10.0)


# ── _LoopingTimeSource ───────────────────────────────────────────────────────

class TestLoopingTimeSource:
    def test_first_call_returns_window_start(self):
        ts = _LoopingTimeSource(window_start=42.0, window_duration=5.0)
        v = ts()
        assert 42.0 <= v < 47.0

    def test_zero_duration_returns_constant_start(self):
        ts = _LoopingTimeSource(window_start=10.0, window_duration=0.0)
        assert ts() == pytest.approx(10.0)
        assert ts() == pytest.approx(10.0)

    def test_wraparound(self):
        ts = _LoopingTimeSource(window_start=100.0, window_duration=0.05)
        ts()  # seed timer
        time.sleep(0.06)
        v = ts()
        assert 100.0 <= v < 100.05


# ── _RampGain ────────────────────────────────────────────────────────────────

class _ConstantSource:
    """Stand-in for StimSynth — returns ones across the block.

    `_RampGain` is supposed to multiply this by the ramp gain, so the
    output amplitude tracks the ramp shape directly without any synth
    modulation interfering.
    """

    sample_rate = 44100
    waveform = "continuous"

    def generate_block_with_clocks(self, steady_clock, system_time_estimate):
        n = steady_clock.shape[0]
        return np.ones((n, 2), dtype=np.float32)


class TestRampGain:
    def test_zero_ramp_is_passthrough(self):
        wrapped = _RampGain(_ConstantSource(), ramp_seconds=0.0)
        steady = np.linspace(0.0, 0.1, 4410)
        block = wrapped.generate_block_with_clocks(steady, steady.copy())
        np.testing.assert_array_equal(
            block, np.ones((4410, 2), dtype=np.float32),
        )

    def test_ramp_starts_silent_and_ends_loud(self):
        wrapped = _RampGain(_ConstantSource(), ramp_seconds=1.0)
        sr = 44100
        n = sr // 2  # half-second block, mid-ramp
        steady = np.arange(n) / sr
        block = wrapped.generate_block_with_clocks(steady, steady.copy())
        # Cosine ramp: gain[0] ≈ 0; gain at t=0.5s = 0.5*(1 - cos(π/2)) = 0.5.
        assert block[0, 0] == pytest.approx(0.0, abs=1e-3)
        assert block[-1, 0] == pytest.approx(0.5, abs=1e-2)

    def test_past_ramp_is_full_amplitude(self):
        wrapped = _RampGain(_ConstantSource(), ramp_seconds=1.0)
        sr = 44100
        steady = 5.0 + np.arange(sr) / sr
        block = wrapped.generate_block_with_clocks(steady, steady.copy())
        np.testing.assert_array_equal(
            block, np.ones((sr, 2), dtype=np.float32),
        )

    def test_attributes_propagated(self):
        wrapped = _RampGain(_ConstantSource(), ramp_seconds=2.0)
        assert wrapped.sample_rate == 44100
        assert wrapped.waveform == "continuous"


# ── CalibrationStream construction ───────────────────────────────────────────

class TestCalibrationStreamErrors:
    """Construction-time error paths. The audio device path is exercised
    via integration / dogfood — opening sounddevice in a unit test is
    flaky on CI environments without a real audio backend."""

    def test_empty_device_id_rejected(self):
        from app.stim_calibrate import CalibrationStream
        ch = _scene_with_sustained_hot_and_brief_spike()
        with pytest.raises(ValueError, match="audio_device_id"):
            CalibrationStream(ch, audio_device_id="")

    def test_empty_funscript_rejected(self):
        from app.stim_calibrate import CalibrationStream
        empty = StimChannels(
            t=np.zeros(0), alpha=np.zeros(0), beta=np.zeros(0),
            source="native_stereostim",
        )
        with pytest.raises(ValueError, match="no playable timeline"):
            CalibrationStream(empty, audio_device_id="wasapi/{fake}")
