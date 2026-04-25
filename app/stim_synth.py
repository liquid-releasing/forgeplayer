# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Funscript-driven 3-phase audio synthesis driver.

Wraps the vendored restim algorithms (`ThreePhaseAlgorithm` for continuous
mode, `DefaultThreePhasePulseBasedAlgorithm` for pulse-based mode) with a
single `StimSynth` facade. Caller hands it a `StimChannels` plus a
media-sync callback; `generate_block()` returns stereo PCM ready to push
to a sounddevice output stream (next commit).

Algorithm dispatch is by channel set — see
`docs/architecture/stim-synthesis.md`:

- Any `pulse_*` channel present → pulse-based algorithm.
- Else → continuous algorithm (plain stereostim or legacy 2b).

Every parameter channel has a native axis range (see restim's
`qt_ui/models/funscript_kit.py`). Funscript files store values as 0..100
ints → loader normalizes to 0..1 → this module rescales to the channel's
axis range and feeds the result into a precomputed axis. Channels absent
from the scene get a `ConstantAxis` at a sensible default.

The synth is stateful only in the monotonic sample counter for the restim
API's `steady_clock`; all position/parameter state lives in the restim
axes, so a new scene means a new `StimSynth`.
"""

from __future__ import annotations

from typing import Callable, Literal

import numpy as np

from app.funscript_loader import FunscriptActions, StimChannels


WaveformMode = Literal["continuous", "pulse"]
from app.vendor.restim_stim_math.audio_gen.continuous import ThreePhaseAlgorithm
from app.vendor.restim_stim_math.audio_gen.params import (
    SafetyParams,
    ThreephaseCalibrationParams,
    ThreephaseContinuousAlgorithmParams,
    ThreephasePositionParams,
    ThreephasePositionTransformParams,
    ThreephasePulsebasedAlgorithmParams,
    VibrationParams,
    VolumeParams,
)
from app.vendor.restim_stim_math.audio_gen.pulse_based import (
    DefaultThreePhasePulseBasedAlgorithm,
)
from app.vendor.restim_stim_math.axis import (
    AbstractAxis,
    AbstractMediaSync,
    DummyTimestampMapper,
    create_constant_axis,
    create_precomputed_axis,
)


SAMPLE_RATE = 44100
SAFETY_MIN_HZ = 500.0
SAFETY_MAX_HZ = 1000.0

# Native axis ranges. Funscript files carry positions in 0..100 (normalized
# by the loader to 0..1). Each channel maps that 0..1 window linearly onto
# the range below. Sources:
#   - alpha/beta:   restim's funscript_kit.py (POSITION_ALPHA: -1..1)
#   - volume:       Edger's normalization table (max=1.0, already normalized)
#   - frequency:    Edger's normalization table (max=1200 Hz). NOT restim's
#                   safety range (500-1000) — restim's safety_limits clamp
#                   at synthesis time; the funscript's *intent* is 0..1200.
#   - pulse_*:      restim's funscript_kit.py
# See docs/architecture/stim-synthesis.md and the upstream
# funscript-tools/FUNDAMENTAL_OPERATIONS.md for the authoring contract.
_ALPHA_BETA_RANGE = (-1.0, 1.0)
_VOLUME_RANGE = (0.0, 1.0)
_CARRIER_RANGE = (0.0, 1200.0)
_PULSE_FREQ_RANGE = (0.0, 100.0)
_PULSE_WIDTH_RANGE = (4.0, 10.0)
_PULSE_RISE_RANGE = (2.0, 20.0)

# Defaults applied to ConstantAxis when a channel is absent from the
# scene. Match restim's out-of-the-box settings (qt_ui/settings.py).
_DEFAULT_ALPHA_BETA = 0.0
_DEFAULT_VOLUME = 1.0
_DEFAULT_CARRIER_HZ = 700.0
_DEFAULT_PULSE_FREQ = 50.0
_DEFAULT_PULSE_WIDTH = 6.0
_DEFAULT_PULSE_RISE = 10.0


class CallbackMediaSync(AbstractMediaSync):
    """`AbstractMediaSync` whose `is_playing()` delegates to a callable.

    Production wires this to the SyncEngine ("is the video player playing?").
    Tests wire it to a mutable flag.
    """

    def __init__(self, is_playing_fn: Callable[[], bool]) -> None:
        self._fn = is_playing_fn

    def is_playing(self) -> bool:
        return bool(self._fn())


class StimSynth:
    """Real-time 3-phase audio synthesizer for a single funscript scene.

    One instance covers one scene on one audio output (main OR prostate).
    The scene's channel set determines the algorithm — continuous for
    alpha+beta-only content, pulse-based when any `pulse_*` channel is
    present.

    Usage (sketch):

        sync = CallbackMediaSync(lambda: engine.is_video_playing())
        synth = StimSynth(channels, sync)
        # in audio callback (at SAMPLE_RATE):
        block = synth.generate_block(n_frames, video.time_pos)
        # block shape: (n_frames, 2), dtype float32, range ~[-1, 1]
    """

    def __init__(
        self,
        channels: StimChannels,
        media_sync: AbstractMediaSync,
        *,
        waveform: WaveformMode = "continuous",
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        """Build a synth for one channel set.

        `waveform` picks the algorithm:
          - "continuous" (default) → restim's continuous threephase, smooth
            sine carrier modulated by position. **Matches FunscriptForge's
            default MP3 render** — same waveform the user's ear is
            calibrated to.
          - "pulse" → pulse-based threephase. Discrete pulses with envelope
            shaping, alternating polarity for DC balance. Sounds clicky on
            its own; consumes pulse_frequency / pulse_width / pulse_rise_time
            channels when present.

        Channel presence is orthogonal to algorithm choice — Euphoria-style
        scenes ship with pulse_* channels but those channels are ignored in
        continuous mode (same behavior as FunscriptForge).

        `sample_rate` is the rate the audio output stream will run at —
        typically the device's `default_samplerate` (44100 on most USB
        dongles, 48000 on a few). The synth math runs at whatever rate
        the algorithm is asked for; the user's ear is calibrated to the
        funscript-defined modulation, not to the carrier sample rate.
        """
        self._channels = channels
        self._media_sync = media_sync
        self._sample_count = 0
        self.waveform: WaveformMode = waveform
        self.sample_rate: int = sample_rate

        if waveform == "pulse":
            self._algorithm = self._build_pulse_based()
        else:
            self._algorithm = self._build_continuous()

    def generate_block(self, n_frames: int, media_time_s: float) -> np.ndarray:
        """Synthesize `n_frames` of stereo PCM at the synth's sample rate.

        Simple linear time interpolation: `system_time_estimate[i] =
        media_time_s + i / sample_rate`. Used by tests and offline
        rendering where the caller has a perfectly linear time source.
        Production live playback uses `generate_block_with_clocks`
        instead, with a smoothed clock from `StimAudioStream`.

        `media_time_s` is the video player's current `time-pos` in seconds —
        the funscript axes are interpolated against this so estim follows
        the video clock. While `media_sync.is_playing()` is False the
        returned block is silenced internally by the algorithm (volume*0
        for continuous, envelope*0 for pulse-based).

        Returns: float32 ndarray, shape (n_frames, 2), values in ~[-1, 1].
        """
        if n_frames <= 0:
            return np.zeros((0, 2), dtype=np.float32)

        idx = np.arange(n_frames)
        steady_clock = (idx + self._sample_count) / self.sample_rate
        system_time_estimate = media_time_s + idx / self.sample_rate

        return self.generate_block_with_clocks(steady_clock, system_time_estimate)

    def generate_block_with_clocks(
        self,
        steady_clock: np.ndarray,
        system_time_estimate: np.ndarray,
    ) -> np.ndarray:
        """Lower-level entry point that takes both clock arrays directly.

        `steady_clock` is the audio thread's monotonic sample-counter
        clock (perfectly linear). `system_time_estimate` is the smoothed
        media-time estimate fed to the funscript axes — must be SAME
        SHAPE as steady_clock. Both are arrays of seconds.

        Used by `StimAudioStream` so the caller can low-pass-filter the
        media clock outside the synth (restim's pattern) and avoid
        per-block discontinuities from a jittery time source.

        Returns: float32 ndarray, shape (len(steady_clock), 2).
        """
        n_frames = int(steady_clock.shape[0])
        if n_frames == 0:
            return np.zeros((0, 2), dtype=np.float32)

        left, right = self._algorithm.generate_audio(
            samplerate=self.sample_rate,
            steady_clock=steady_clock,
            system_time_estimate=system_time_estimate,
        )
        self._sample_count += n_frames

        out = np.empty((n_frames, 2), dtype=np.float32)
        out[:, 0] = np.asarray(left, dtype=np.float32)
        out[:, 1] = np.asarray(right, dtype=np.float32)
        return out

    # ── Algorithm construction ────────────────────────────────────────────────

    def _build_continuous(self) -> ThreePhaseAlgorithm:
        # Continuous mode IGNORES carrier_frequency funscript and uses a
        # constant default. Reason: restim's continuous algorithm samples
        # carrier_frequency once per audio chunk (system_time_estimate[0],
        # not the array). With ~4096-frame chunks at 44.1 kHz that's a
        # frequency-step every 92.9 ms ≈ 10.7 Hz. A varying carrier
        # funscript therefore creates an audible 10 Hz "horse-hoof" buzz
        # at chunk boundaries. FunscriptForge's MP3 renderer
        # (forge/audio_synthesis.py default carrier_frequency=700.0) does
        # the same thing for the same reason — users' ears are calibrated
        # to a constant carrier in continuous mode. If the scene's intent
        # genuinely needs varying carrier, use pulse mode (which samples
        # per-sample and has no chunk-step artifact).
        params = ThreephaseContinuousAlgorithmParams(
            position=self._build_position_params(),
            transform=_neutral_transform_params(),
            calibrate=_neutral_calibrate_params(),
            vibration_1=_disabled_vibration_params(),
            vibration_2=_disabled_vibration_params(),
            volume=self._build_volume_params(),
            carrier_frequency=create_constant_axis(_DEFAULT_CARRIER_HZ),
        )
        return ThreePhaseAlgorithm(
            media=self._media_sync,
            params=params,
            safety_limits=_safety(),
        )

    def _build_pulse_based(self) -> DefaultThreePhasePulseBasedAlgorithm:
        # Pulse mode HONORS carrier_frequency funscript. restim's pulse_based
        # algorithm interpolates carrier_frequency from the full
        # system_time_estimate array (per-sample), so a varying carrier
        # plays cleanly without chunk-step artifacts.
        params = ThreephasePulsebasedAlgorithmParams(
            position=self._build_position_params(),
            transform=_neutral_transform_params(),
            calibrate=_neutral_calibrate_params(),
            vibration_1=_disabled_vibration_params(),
            vibration_2=_disabled_vibration_params(),
            volume=self._build_volume_params(),
            carrier_frequency=self._build_carrier_axis(),
            pulse_frequency=_axis_from_actions(
                self._channels.pulse_frequency, _PULSE_FREQ_RANGE, _DEFAULT_PULSE_FREQ,
            ),
            pulse_width=_axis_from_actions(
                self._channels.pulse_width, _PULSE_WIDTH_RANGE, _DEFAULT_PULSE_WIDTH,
            ),
            pulse_interval_random=create_constant_axis(0.0),
            pulse_rise_time=_axis_from_actions(
                self._channels.pulse_rise_time, _PULSE_RISE_RANGE, _DEFAULT_PULSE_RISE,
            ),
        )
        return DefaultThreePhasePulseBasedAlgorithm(
            media=self._media_sync,
            params=params,
            safety_limits=_safety(),
        )

    def _build_position_params(self) -> ThreephasePositionParams:
        return ThreephasePositionParams(
            alpha=_position_axis(self._channels.t, self._channels.alpha),
            beta=_position_axis(self._channels.t, self._channels.beta),
        )

    def _build_volume_params(self) -> VolumeParams:
        # The funscript-scripted channel feeds `api`; the other three are
        # user/automation-controlled and get constant 1 defaults here.
        return VolumeParams(
            api=_axis_from_actions(self._channels.volume, _VOLUME_RANGE, _DEFAULT_VOLUME),
            master=create_constant_axis(1.0),
            inactivity=create_constant_axis(1.0),
            external=create_constant_axis(1.0),
        )

    def _build_carrier_axis(self) -> AbstractAxis:
        return _axis_from_actions(
            self._channels.carrier_frequency,
            _CARRIER_RANGE,
            _DEFAULT_CARRIER_HZ,
        )


# ── Axis construction helpers ─────────────────────────────────────────────────

def _position_axis(t: np.ndarray, values_01: np.ndarray) -> AbstractAxis:
    """Build alpha or beta axis from dense 0..1 funscript-space values.

    Restim's ThreePhase math treats alpha/beta as unit-circle coordinates
    in [-1, 1]. Funscript files carry these as 0..1; we rescale linearly
    on load. This matches restim's own rescaling in
    `qt_ui/algorithm_factory.py:426`.
    """
    axis_min, axis_max = _ALPHA_BETA_RANGE
    y = np.clip(values_01, 0.0, 1.0) * (axis_max - axis_min) + axis_min
    return create_precomputed_axis(t, y, DummyTimestampMapper())


def _axis_from_actions(
    actions: FunscriptActions | None,
    axis_range: tuple[float, float],
    default_value: float,
) -> AbstractAxis:
    """Build a parameter axis from sparse action samples.

    If `actions` is None or empty, return a `ConstantAxis` at
    `default_value` — the synth runs against that constant for the whole
    scene. Otherwise rescale from funscript 0..1 to the channel's native
    axis range and return a precomputed (linearly-interpolated) axis.
    """
    if actions is None or actions.t.size == 0:
        return create_constant_axis(default_value)
    axis_min, axis_max = axis_range
    y = np.clip(actions.p, 0.0, 1.0) * (axis_max - axis_min) + axis_min
    return create_precomputed_axis(actions.t, y, DummyTimestampMapper())


def _safety() -> SafetyParams:
    return SafetyParams(
        minimum_carrier_frequency=SAFETY_MIN_HZ,
        maximum_carrier_frequency=SAFETY_MAX_HZ,
    )


# ── Constant-defaults for unscripted params ───────────────────────────────────

def _neutral_transform_params() -> ThreephasePositionTransformParams:
    return ThreephasePositionTransformParams(
        transform_enabled=create_constant_axis(False),
        transform_rotation_degrees=create_constant_axis(0.0),
        transform_mirror=create_constant_axis(False),
        transform_top_limit=create_constant_axis(1.0),
        transform_bottom_limit=create_constant_axis(-1.0),
        transform_left_limit=create_constant_axis(-1.0),
        transform_right_limit=create_constant_axis(1.0),
        map_to_edge_enabled=create_constant_axis(False),
        map_to_edge_start=create_constant_axis(0.0),
        map_to_edge_length=create_constant_axis(1.0),
        map_to_edge_invert=create_constant_axis(False),
        exponent=create_constant_axis(1.0),
    )


def _neutral_calibrate_params() -> ThreephaseCalibrationParams:
    return ThreephaseCalibrationParams(
        neutral=create_constant_axis(0.0),
        right=create_constant_axis(0.0),
        center=create_constant_axis(0.0),
    )


def _disabled_vibration_params() -> VibrationParams:
    return VibrationParams(
        enabled=create_constant_axis(False),
        frequency=create_constant_axis(0.0),
        strength=create_constant_axis(0.0),
        left_right_bias=create_constant_axis(0.0),
        high_low_bias=create_constant_axis(0.0),
        random=create_constant_axis(0.0),
    )
