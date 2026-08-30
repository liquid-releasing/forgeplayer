# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Pre-flight calibration — loop the funscript's envelope-peak window
through one haptic port so the user can dial in the dongle's volume
before hitting Play.

Calibrate is a deliberate sibling of `stim_preview.play_test_clip`:

  - **Test** (Setup tab) is a one-shot 1.5-second gentle preview at -12 dB.
    Answers "is this dongle reachable?".
  - **Calibrate** (Live tab) is a looping high-amplitude session driven by
    the actual funscript content of the loaded scene. Answers "what knob
    setting is comfortable for the peak intensity of THIS scene?"

The two stay separate modules because their lifecycles differ — Test is
fire-and-forget (sounddevice.play). Calibrate is a lifecycle (start /
stop, optional ramp-in, locked once Play is hit until Close).

`find_peak_section` picks the most-intense ~10-second window of the
funscript by integrating the volume envelope (or the alpha/beta motion
when no volume curve is present). `CalibrationStream` drives that window
in a loop on the audio thread via the same `StimSynth` + `StimAudioStream`
path the launch flow uses, with an optional 5-second cosine ramp-in to
avoid punching the user with peak intensity from sample zero.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np

from app.funscript_loader import StimChannels


_log = logging.getLogger(__name__)


# Sliding-window peak detection runs on a coarse grid; finer is wasted
# because the integral over a 10-second window changes slowly.
_PEAK_GRID_HZ = 10
_DEFAULT_WINDOW_S = 10.0


def find_peak_section(
    channels: StimChannels,
    window_s: float = _DEFAULT_WINDOW_S,
) -> tuple[float, float]:
    """Return ``(start_s, duration_s)`` of a representative high-intensity
    window in `channels`.

    Goal: find the window a heat-map visualizer (OpenFunscripter,
    FunscriptForge) would color **sustained** orange-and-red — the
    "typical hot" section — rather than the absolute peak. A scene's
    climax/payoff is often a brief 1-2 second super-spike; calibrating
    against it would have the user dial in a conservative knob setting
    that under-delivers for the rest of the scene. Calibrating against
    a sustained hot passage gives a setting that's right for the bulk
    of the active material AND has headroom for the surprise climax.

    Intensity model: ``intensity = volume × position_velocity``.

    - **position_velocity** = ``sqrt((dα/dt)² + (dβ/dt)²)`` from the
      dense alpha/beta arrays. This is what heat-map tools color
      orange/red — fast position changes drive rapid modulation of the
      synth's carrier, which is what the user perceives as intense.
    - **volume** modulates synth amplitude; absent volume curve treated
      as 1.0 so the detector still works on motion-only scenes.

    Window scoring: the **75th percentile** of intensity within the
    window. Why percentile and not integral?
    - Integral (mean × length) lets a brief 1-second peak dominate a
      10-second window. A scene with one bright climax would beat a
      sustained-hot section just because its peak value is higher.
    - 75th percentile is the level that 75% of the window stays at or
      above. A 1-second spike in a 10-second window only contributes
      to the top 10% of samples, so the 75th percentile sits in the
      window's floor level — the spike doesn't win. A sustained hot
      passage where 50%+ of samples are in the upper band scores high.

    If the funscript is shorter than `window_s` or has no measurable
    intensity (silent / static scene), returns the first ``window_s``
    of available timeline. Never raises.
    """
    if channels.t.size == 0:
        return (0.0, 0.0)

    scene_end = float(channels.t[-1])
    if scene_end <= window_s:
        return (0.0, scene_end)

    # Resample everything onto a uniform grid so np.diff produces a
    # clean per-step velocity. Funscript action grids are non-uniform
    # (sparse where the script is quiet, dense where it's busy) and
    # would make raw np.diff give misleading per-action velocities.
    n = max(2, int(round(scene_end * _PEAK_GRID_HZ)) + 1)
    t_grid = np.linspace(0.0, scene_end, n)
    dt = scene_end / (n - 1)

    alpha = np.interp(t_grid, channels.t, channels.alpha)
    beta = np.interp(t_grid, channels.t, channels.beta)
    # prepend the first sample so np.diff returns same-length output
    # and the first velocity sample is zero (no jump from "before-start").
    da = np.diff(alpha, prepend=alpha[0]) / dt
    db = np.diff(beta, prepend=beta[0]) / dt
    velocity = np.sqrt(da * da + db * db)

    if channels.volume is not None and channels.volume.t.size > 0:
        volume = np.interp(
            t_grid, channels.volume.t, channels.volume.p,
            left=0.0, right=0.0,
        )
    else:
        volume = np.ones_like(t_grid)

    intensity = velocity * volume
    if not np.any(intensity > 0):
        # Silent / static scene — the whole thing is equally
        # representative. Hand back the first window so we don't
        # bias toward "high motion" windows that don't exist.
        return (0.0, min(scene_end, window_s))

    window_samples = max(1, int(window_s * _PEAK_GRID_HZ))
    if window_samples >= n:
        return (0.0, scene_end)

    # 75th-percentile sliding score. n_windows × window_samples is
    # tiny for typical inputs (a 30-minute scene at 10 Hz grid =
    # 18000 samples × 100-sample window × O(w log w) percentile = a
    # few million ops, sub-millisecond).
    n_windows = n - window_samples + 1
    scores = np.empty(n_windows, dtype=np.float64)
    for i in range(n_windows):
        scores[i] = np.percentile(intensity[i:i + window_samples], 75)

    best_start_idx = int(np.argmax(scores))
    return (float(t_grid[best_start_idx]), window_s)


class _LoopingTimeSource:
    """Wall-clock loop over a fixed media-time window.

    Returns ``window_start + (now - started_at) % window_duration`` each
    call. Calling pattern matches the `time_source` callback that
    `StimAudioStream` invokes once per audio block. Independent of the
    media player's clock — calibration runs without mpv.

    Wraparound creates a momentary backwards jump in media-time that the
    `_TimeSmoother` inside `StimAudioStream` flags as an auto-resync,
    fading the carrier to silence for one block then back in over the
    next. The resulting brief silence at each loop boundary is acceptable
    for calibration (and useful — gives the user an audible cadence
    marker every window).
    """

    def __init__(self, window_start: float, window_duration: float) -> None:
        self._start = float(window_start)
        self._duration = float(window_duration)
        self._began_at: float | None = None

    def __call__(self) -> float:
        now = time.monotonic()
        if self._began_at is None:
            self._began_at = now
        elapsed = now - self._began_at
        if self._duration <= 0:
            return self._start
        return self._start + (elapsed % self._duration)


class _RampGain:
    """StimSynth-shaped wrapper that fades the synth's output from 0 to
    1 over `ramp_seconds` of audio playback.

    Uses the audio callback's `steady_clock` (sample-counter time since
    the stream started) as the ramp clock — guaranteed monotonic and
    independent of the media-time source, so the ramp runs reliably even
    when the inner synth is being driven by a looping `_LoopingTimeSource`.

    Cosine shape (`0.5 * (1 - cos(π · t/ramp))`) has zero derivative at
    both ramp endpoints, avoiding the audible knee that a linear ramp
    leaves at the moment it reaches full output.

    `ramp_seconds <= 0` is the no-op fast path — caller passes 0 to
    skip the wrapper entirely without changing call sites.
    """

    def __init__(self, inner, ramp_seconds: float) -> None:
        self._inner = inner
        self._ramp_seconds = float(ramp_seconds)
        # Pass through the attributes StimAudioStream reads off the synth
        # so callers can swap a `_RampGain` in for a `StimSynth` without
        # any other change.
        self.sample_rate = inner.sample_rate
        self.waveform = getattr(inner, "waveform", "continuous")

    def generate_block_with_clocks(
        self,
        steady_clock: np.ndarray,
        system_time_estimate: np.ndarray,
    ) -> np.ndarray:
        block = self._inner.generate_block_with_clocks(
            steady_clock, system_time_estimate,
        )
        if self._ramp_seconds <= 0.0 or steady_clock.size == 0:
            return block
        if float(steady_clock[0]) >= self._ramp_seconds:
            # Past the ramp window — full pass-through, no per-sample
            # multiply.
            return block
        phase = np.minimum(steady_clock / self._ramp_seconds, 1.0) * np.pi
        gain = (0.5 * (1.0 - np.cos(phase))).astype(np.float32)
        return (block * gain.reshape(-1, 1)).astype(np.float32)


class CalibrationStream:
    """One looping calibration session — funscript peak window through
    one haptic audio device.

    Build per port (Calibrate H1 makes one against the scene's main
    channels + Haptic 1 device; Calibrate H2 against prostate channels
    or main as fallback + Haptic 2 device). Tap-toggle: callers create,
    `start()`, then `stop()` when the user taps the same button again.

    Idempotent — `stop()` is safe to call without `start()` and twice in
    a row. Never raises from the audio thread — failures during
    construction or `start()` log via `_log` and propagate.
    """

    def __init__(
        self,
        channels: StimChannels,
        audio_device_id: str,
        *,
        mpv_devices: Optional[list[dict]] = None,
        waveform: str = "continuous",
        ramp_seconds: float = 0.0,
        peak_window_s: float = _DEFAULT_WINDOW_S,
    ) -> None:
        if not audio_device_id:
            raise ValueError(
                "CalibrationStream needs a non-empty audio_device_id; "
                "caller should disable the calibrate button when no "
                "device is configured for this port."
            )

        # Lazy import to keep audio-stack pull-in out of test envs that
        # don't have sounddevice.
        from app.stim_audio_output import (  # noqa: PLC0415
            StimAudioStream, query_device_sample_rate, resolve_audio_device,
        )
        from app.stim_synth import CallbackMediaSync, StimSynth  # noqa: PLC0415

        peak_start, peak_duration = find_peak_section(
            channels, window_s=peak_window_s,
        )
        # If the scene is empty / zero-length, calibrate is meaningless
        # — bail loudly so the caller can tell the user.
        if peak_duration <= 0.0:
            raise ValueError(
                "Funscript has no playable timeline; calibrate cannot run."
            )

        device_handle = resolve_audio_device(audio_device_id, mpv_devices)
        device_rate = query_device_sample_rate(device_handle)

        # Calibrate runs synth output regardless of any media player
        # state — there's no scene playing during calibrate. Pin
        # is_playing to True at the synth layer; the StimAudioStream's
        # is_playing_source also returns True throughout so the fade
        # gate stays open.
        self._media_sync = CallbackMediaSync(lambda: True)
        synth = StimSynth(
            channels, self._media_sync,
            waveform=waveform if waveform in ("continuous", "pulse") else "continuous",
            sample_rate=device_rate,
        )

        if ramp_seconds > 0:
            source = _RampGain(synth, ramp_seconds)
        else:
            source = synth

        self._time_source = _LoopingTimeSource(peak_start, peak_duration)

        self._stream = StimAudioStream(
            synth=source,
            time_source=self._time_source,
            device_id=audio_device_id,
            mpv_devices=mpv_devices,
            is_playing_source=lambda: True,
        )

        self._lock = threading.Lock()
        self._started = False
        self._stopped = False

        # Diagnostic surface — useful in debug logs and in tests.
        self.peak_start_s: float = peak_start
        self.peak_duration_s: float = peak_duration
        self.device_rate: int = device_rate
        self.device_id: str = audio_device_id
        self.ramp_seconds: float = float(ramp_seconds) if ramp_seconds > 0 else 0.0

    def start(self) -> None:
        """Open the audio device and begin pumping calibration audio.

        Idempotent: calling twice is a no-op. Raises if the device fails
        to open — the caller is the UI layer and surfaces the message.
        """
        with self._lock:
            if self._started or self._stopped:
                return
            self._started = True
        self._stream.start()

    def stop(self) -> None:
        """Close the audio device. Safe to call before start() and twice
        in a row."""
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            already_started = self._started
        if already_started:
            self._stream.stop()

    def is_running(self) -> bool:
        with self._lock:
            return self._started and not self._stopped
