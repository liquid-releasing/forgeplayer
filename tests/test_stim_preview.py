# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the haptic-preview clip synthesizer.

These tests don't open a real audio device — they exercise the
channel-synthesis + offline-render path that drives the Setup tab's
Haptic Test buttons (and will drive the v0.0.2 Calibrate button).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.funscript_loader import StimChannels
from app.stim_preview import (
    _TEST_DURATION_S,
    _TEST_PEAK_VOLUME,
    _TEST_RAMP_S,
    render_clip,
    synthesize_test_clip_channels,
)
from app.stim_synth import SAMPLE_RATE


class TestSynthesizeTestClipChannels:
    def test_default_returns_centered_position(self):
        ch = synthesize_test_clip_channels()

        # Centered = 0.5 in funscript-space (rescaled to 0 in -1..1 axis).
        assert np.allclose(ch.alpha, 0.5)
        assert np.allclose(ch.beta, 0.5)

    def test_volume_envelope_has_four_anchors(self):
        ch = synthesize_test_clip_channels()

        assert ch.volume is not None
        # 0 → peak (rise) → peak (hold) → 0 (fall)
        assert ch.volume.t.shape == (4,)
        assert ch.volume.p[0] == 0.0
        assert ch.volume.p[1] == _TEST_PEAK_VOLUME
        assert ch.volume.p[2] == _TEST_PEAK_VOLUME
        assert ch.volume.p[3] == 0.0

    def test_volume_envelope_timestamps_span_duration(self):
        ch = synthesize_test_clip_channels(duration_s=2.0, ramp_s=0.5)

        np.testing.assert_allclose(
            ch.volume.t, [0.0, 0.5, 1.5, 2.0],
        )

    def test_no_pulse_channels(self):
        ch = synthesize_test_clip_channels()

        # Pure continuous-mode preview — pulse params would dispatch us
        # to the pulse-based algorithm, which has different audible
        # character than what real scenes use by default.
        assert ch.pulse_frequency is None
        assert ch.pulse_width is None
        assert ch.pulse_rise_time is None
        assert not ch.has_pulse_params

    def test_invalid_duration_rejected(self):
        with pytest.raises(ValueError):
            synthesize_test_clip_channels(duration_s=0.5, ramp_s=0.4)

    def test_invalid_peak_volume_rejected(self):
        with pytest.raises(ValueError):
            synthesize_test_clip_channels(peak_volume=1.5)
        with pytest.raises(ValueError):
            synthesize_test_clip_channels(peak_volume=-0.1)


class TestRenderClip:
    def test_returns_stereo_float32_at_sample_rate(self):
        ch = synthesize_test_clip_channels()
        audio = render_clip(ch, duration_s=_TEST_DURATION_S)

        expected_frames = int(round(_TEST_DURATION_S * SAMPLE_RATE))
        assert audio.shape == (expected_frames, 2)
        assert audio.dtype == np.float32

    def test_output_finite_and_bounded(self):
        ch = synthesize_test_clip_channels()
        audio = render_clip(ch, duration_s=_TEST_DURATION_S)

        assert np.all(np.isfinite(audio))
        assert np.max(np.abs(audio)) <= 1.0

    def test_envelope_silent_at_edges_and_loud_in_middle(self):
        ch = synthesize_test_clip_channels()
        audio = render_clip(ch, duration_s=_TEST_DURATION_S)

        # Compare RMS amplitude at the extremes (first and last 5 ms,
        # well inside the 0.4 s ramp) with the middle (around 0.75 s).
        edge_frames = int(0.005 * SAMPLE_RATE)
        head_rms = float(np.sqrt(np.mean(audio[:edge_frames] ** 2)))
        tail_rms = float(np.sqrt(np.mean(audio[-edge_frames:] ** 2)))

        mid_start = int(0.7 * SAMPLE_RATE)
        mid_end = int(0.8 * SAMPLE_RATE)
        mid_rms = float(np.sqrt(np.mean(audio[mid_start:mid_end] ** 2)))

        assert mid_rms > head_rms * 5, (
            f"middle ({mid_rms:.4f}) should be much louder than head "
            f"({head_rms:.4f})"
        )
        assert mid_rms > tail_rms * 5, (
            f"middle ({mid_rms:.4f}) should be much louder than tail "
            f"({tail_rms:.4f})"
        )

    def test_lower_peak_volume_yields_quieter_clip(self):
        ch_quiet = synthesize_test_clip_channels(peak_volume=0.1)
        ch_loud = synthesize_test_clip_channels(peak_volume=0.5)
        audio_quiet = render_clip(ch_quiet, duration_s=_TEST_DURATION_S)
        audio_loud = render_clip(ch_loud, duration_s=_TEST_DURATION_S)

        # Compare RMS in the held-peak region (well past the ramp).
        mid = int(0.75 * SAMPLE_RATE)
        win = int(0.05 * SAMPLE_RATE)
        rms_quiet = float(np.sqrt(np.mean(audio_quiet[mid:mid + win] ** 2)))
        rms_loud = float(np.sqrt(np.mean(audio_loud[mid:mid + win] ** 2)))

        # 0.5 / 0.1 = 5x in the volume axis. Allow some tolerance for the
        # synth's other-axis interactions; we just want monotonicity + the
        # right ballpark.
        assert rms_loud > rms_quiet * 3
