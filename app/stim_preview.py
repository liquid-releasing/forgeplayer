# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Haptic preview clips — synthesized stim samples for haptic-device buttons.

The Setup tab's haptic Test buttons should NOT play a 440 Hz speaker tone.
The audio is going through an estim electrode pair, not a headphone — a
naked sine gives the user a harsh buzz, not a representative preview of
what scenes will feel like. Worse, the device-open / device-close pops
from spawning a fresh mpv instance per Test press dominate over the tone
itself on most USB dongles.

Instead, we route Test through the same StimSynth + sounddevice path that
real scene playback uses, with a centered electrode position and a brief
volume envelope:

    volume:  0  ──ramp──▶  peak  ──hold──▶  peak  ──ramp──▶  0
    alpha:   0.5 (centered)
    beta:    0.5 (centered)
    carrier: 700 Hz (continuous default — same as FunscriptForge MP3)

The user feels a gentle fade-in tickle, a steady moment, and a fade-out:
confirms the dongle + driver chain works and gives a true preview of the
real waveform character.

This module is also the seed for the v0.0.2 Calibrate button
(`project_forgeplayer_calibrate_button.md`). Calibrate will reuse
`synthesize_test_clip_channels` as the fallback when a scene ships no
calibration audio, and add a looping playback variant. Test = one-shot
gentle preview; Calibrate = looping high-amplitude pre-flight.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np

from app.funscript_loader import FunscriptActions, StimChannels
from app.stim_audio_output import _load_sounddevice, resolve_audio_device
from app.stim_synth import SAMPLE_RATE, CallbackMediaSync, StimSynth


_log = logging.getLogger(__name__)


# Test clip parameters. Volume cap is intentionally low — Test answers
# "is the dongle reachable?" not "how does the scene feel?". Calibrate
# (future) will run at full scene amplitude; Test stays gentle so a user
# whose hardware knob is dialed high doesn't get jolted.
_TEST_DURATION_S = 1.5
_TEST_RAMP_S = 0.4
_TEST_PEAK_VOLUME = 0.25  # in funscript-space 0..1, ≈ -12 dB on the synth volume axis


def synthesize_test_clip_channels(
    *,
    duration_s: float = _TEST_DURATION_S,
    ramp_s: float = _TEST_RAMP_S,
    peak_volume: float = _TEST_PEAK_VOLUME,
) -> StimChannels:
    """Build the StimChannels for a Test-button preview clip.

    `alpha` and `beta` are constant 0.5 (electrode centered in
    funscript-space — the synth rescales 0..1 to -1..1 internally, so
    0.5 lands on 0 = centered). `volume` follows a four-point envelope:
    0 → peak → peak → 0, with `ramp_s` for both rise and fall.
    """
    if duration_s <= 0 or ramp_s <= 0 or 2 * ramp_s >= duration_s:
        raise ValueError(
            "Need duration_s > 2*ramp_s; got "
            f"duration_s={duration_s}, ramp_s={ramp_s}"
        )
    if not (0.0 <= peak_volume <= 1.0):
        raise ValueError(f"peak_volume must be in [0, 1]; got {peak_volume}")

    # 25 samples/sec matches the radial-conversion grid. Finer is wasted —
    # the synth interpolates internally to SAMPLE_RATE.
    grid_hz = 25
    n = max(2, int(duration_s * grid_hz))
    t = np.linspace(0.0, duration_s, n)
    alpha = np.full_like(t, 0.5)
    beta = np.full_like(t, 0.5)

    # Volume as a sparse FunscriptActions, just like a real volume.funscript.
    # The synth interpolates linearly between these four points.
    vol_t = np.array([0.0, ramp_s, duration_s - ramp_s, duration_s])
    vol_p = np.array([0.0, peak_volume, peak_volume, 0.0])
    volume = FunscriptActions(t=vol_t, p=vol_p)

    return StimChannels(
        t=t,
        alpha=alpha,
        beta=beta,
        source="native_stereostim",
        volume=volume,
    )


def render_clip(channels: StimChannels, duration_s: float) -> np.ndarray:
    """Synthesize a finite stim clip into a stereo float32 buffer.

    Runs the StimSynth in continuous mode against `channels` for
    `duration_s` seconds at SAMPLE_RATE, with media_sync.is_playing()
    pinned True so the synth doesn't silence itself.

    Returns: float32 ndarray, shape (n_frames, 2), values in ~[-1, 1].
    """
    sync = CallbackMediaSync(lambda: True)
    synth = StimSynth(channels, sync, waveform="continuous")
    n_frames = int(round(duration_s * SAMPLE_RATE))
    return synth.generate_block(n_frames, media_time_s=0.0)


def play_test_clip(
    audio_device: str,
    *,
    mpv_devices: Optional[list[dict]] = None,
    duration_s: float = _TEST_DURATION_S,
    ramp_s: float = _TEST_RAMP_S,
    peak_volume: float = _TEST_PEAK_VOLUME,
) -> None:
    """Fire-and-forget Test-button playback through *audio_device*.

    *audio_device* is the mpv `audio_device` identifier saved by Setup
    (e.g. `wasapi/{guid}`). Empty string means the role isn't configured —
    no-op. The mpv id is translated to a sounddevice device-name via
    `resolve_audio_device()`; resolution failures fall back to the system
    default (and log).

    Renders the clip on the calling thread (cheap — ~520 KB), then hands
    it to sounddevice's `play()` which manages its own background thread
    and device lifecycle. Returns immediately.
    """
    if not audio_device:
        return

    try:
        channels = synthesize_test_clip_channels(
            duration_s=duration_s,
            ramp_s=ramp_s,
            peak_volume=peak_volume,
        )
        audio = render_clip(channels, duration_s=duration_s)
    except Exception as exc:
        _log.exception("Failed to synthesize test clip: %s", exc)
        return

    device_name = resolve_audio_device(audio_device, mpv_devices)

    def _run() -> None:
        try:
            sd = _load_sounddevice()
            sd.play(audio, samplerate=SAMPLE_RATE, device=device_name)
        except Exception as exc:
            _log.error(
                "Failed to play test clip (device=%r): %s", device_name, exc,
            )

    threading.Thread(target=_run, daemon=True).start()
