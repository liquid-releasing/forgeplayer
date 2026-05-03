# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Pumps a StimSynth into a sounddevice OutputStream.

The synth produces 2-channel float32 blocks; sounddevice opens an output
callback that asks for blocks at the device's hardware rate and pushes
them to the OS audio driver. We pin the sample rate to `SAMPLE_RATE`
(44100), ask for ~512-frame blocks (~12 ms at 44.1k), and resolve the
target device by translating Setup's saved mpv device id to a
sounddevice device name.

Setup stores `wasapi/{guid}` strings (mpv's audio-device-list namespace).
sounddevice indexes physical devices by integer or by name substring.
`resolve_audio_device()` turns the mpv id into the human description
(e.g. "Speakers (USB Audio Device)") and hands that to sounddevice as
the `device` argument.

If the resolver can't find a match — empty preference, name typo, or a
removed dongle — the stream opens against the system default device and
logs a warning. The user always gets sound; they just may need to fix
Setup if it's the wrong dongle.

The module imports sounddevice lazily so unit tests can run without it
on CI (the module-level import at the bottom of the file is what matters
for normal use; `_load_sounddevice()` is called only when starting a
stream).
"""

from __future__ import annotations

import logging
import os
import threading
import wave
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from app.stim_synth import SAMPLE_RATE, StimSynth


_log = logging.getLogger(__name__)


_HOST_API_FROM_MPV_PREFIX = {
    "wasapi": "Windows WASAPI",
    "coreaudio": "Core Audio",
    "alsa": "ALSA",
    "pulse": "PulseAudio",
    "jack": "JACK Audio Connection Kit",
    "oss": "OSS",
}


def _host_api_from_mpv_id(mpv_id: str) -> str | None:
    """Translate the `wasapi/{guid}` mpv-id prefix to the sounddevice
    hostapi name. Used to filter sounddevice device lookups so a Windows
    user with the same dongle visible on MME / DirectSound / WASAPI
    doesn't get an "ambiguous match" failure."""
    prefix = mpv_id.split("/", 1)[0] if "/" in mpv_id else mpv_id
    return _HOST_API_FROM_MPV_PREFIX.get(prefix)


def query_device_sample_rate(
    handle: int | str | None,
    default: int = 44100,
) -> int:
    """Return the device's `default_samplerate` as an int.

    `handle` is whatever `resolve_audio_device` returns: a sounddevice
    integer index (preferred), a device-name string, or None for system
    default. Returns `default` on any failure (sounddevice unavailable,
    device gone, returned a non-numeric default_samplerate, etc.) so
    callers don't have to handle errors at the call site — the synth
    pipeline runs at `default` and the user gets PortAudio's own error
    if even that's wrong.
    """
    try:
        sd = _load_sounddevice()
        if handle is None:
            info = sd.query_devices(kind="output")
        else:
            info = sd.query_devices(handle)
        rate = int(info.get("default_samplerate", default))
        return rate if rate > 0 else default
    except Exception as exc:
        _log.debug("device sample-rate query failed (handle=%r): %s", handle, exc)
        return default


def _find_sounddevice_indices(sd, desc: str, target_host: str | None) -> list[int]:
    """Return ALL sounddevice integer indices matching `desc` on
    `target_host`, in enumeration order. Empty list if none match.

    Multi-match is the two-physical-dongle case: same description on
    the same host. Caller decides whether to pick the first (for a
    unique pick) or the N-th (for position-paired matching against
    mpv's list).
    """
    matches: list[int] = []
    try:
        devices = sd.query_devices()
    except Exception:
        return matches

    for idx, dev in enumerate(devices):
        if dev.get("max_output_channels", 0) <= 0:
            continue
        if dev.get("name") != desc:
            continue
        if target_host is not None:
            try:
                host_name = sd.query_hostapis(dev["hostapi"]).get("name", "")
            except Exception:
                host_name = ""
            if host_name != target_host:
                continue
        matches.append(idx)
    return matches


def _find_sounddevice_index(sd, desc: str, target_host: str | None) -> int | None:
    """Single-match lookup. Returns the unique index, the first when
    multiple match (with a warning), or None when none match. Kept for
    use sites that don't have the mpv list available — production
    `resolve_audio_device` uses the position-aware variant when it can.
    """
    matches = _find_sounddevice_indices(sd, desc, target_host)
    if not matches:
        return None
    if len(matches) > 1:
        _log.warning(
            "Multiple sounddevice indices match %r on %r; picking %d. "
            "If the wrong dongle activates, physically swap them.",
            desc, target_host, matches[0],
        )
    return matches[0]


def resolve_audio_device(
    mpv_device_id: str | None,
    mpv_devices: list[dict] | None = None,
) -> str | int | None:
    """Translate an mpv audio-device id (`wasapi/{guid}`) to a sounddevice
    device handle.

    Returns:
      - An **integer device index** when sounddevice can uniquely (or
        deterministically) identify the device for the given description
        + host api. This avoids name-substring ambiguity when the same
        device name appears on multiple host apis (MME, DirectSound,
        WASAPI all expose the same physical device on Windows).
      - The mpv device's **description string** as a fallback when
        sounddevice isn't available or doesn't recognize the device.
        sounddevice will substring-match — fragile when ambiguous, but
        good enough when it's not.
      - `None` when the input is empty / "auto" / not in `mpv_devices`.
        Caller passes None straight to sounddevice → system default.

    Pass `mpv_devices=None` (default) to query mpv at call time;
    callers that have already enumerated mpv's list should pass it in
    to avoid spinning up a second mpv instance.
    """
    if not mpv_device_id or mpv_device_id == "auto":
        return None

    if mpv_devices is None:
        mpv_devices = _query_mpv_audio_devices()

    desc: str | None = None
    for d in mpv_devices:
        if d.get("name") == mpv_device_id:
            desc = d.get("description") or ""
            break
    if not desc:
        return None

    target_host = _host_api_from_mpv_id(mpv_device_id)
    try:
        sd = _load_sounddevice()
        sd_indices = _find_sounddevice_indices(sd, desc, target_host)
        if sd_indices:
            # Position-aware match: pair the N-th mpv entry sharing
            # (desc, host) with the N-th sounddevice index sharing the
            # same. Both lists are in driver enumeration order, so on
            # WASAPI this puts two physically-identical USB dongles on
            # different sounddevice indices instead of collapsing them.
            same_host_mpv = [
                d for d in mpv_devices
                if _host_api_from_mpv_id(d.get("name", "")) == target_host
                and (d.get("description") or "") == desc
            ]
            pos = next(
                (i for i, d in enumerate(same_host_mpv)
                 if d.get("name") == mpv_device_id),
                None,
            )
            if pos is not None and pos < len(sd_indices):
                return sd_indices[pos]
            return sd_indices[0]
    except Exception as exc:
        _log.debug("sounddevice index lookup failed: %s", exc)

    return desc


class _TimeSmoother:
    """Low-pass-filtered, slew-rate-limited offset between sample clock
    and media clock — port of restim's pattern from
    device/audio/audio_stim_device.py:173-194.

    Why: our audio callback runs at audio-block rate (~46 Hz at 48k/1024
    frames); mpv updates its `time-pos` property at video-frame rate
    (~60 Hz). Reading `time-pos` once per callback gets a noisy clock —
    some callbacks see a stalled value (no update since last call),
    others see a doubled jump. Feeding that raw to the synth produces
    discontinuities at block boundaries, which the user hears as crackle
    even when the audio buffer never underruns.

    Smoothed solution: maintain `self.offset` such that
    `system_time_estimate ≈ steady_clock + offset`. Each callback,
    observe `media_time - steady_clock_end` as a noisy offset estimate,
    average over the last 8 observations, then nudge `self.offset`
    toward the average at most ±2% drift per second of audio. Within
    one block, `system_time_estimate` is a linear ramp from the previous
    offset to the new offset — guarantees monotonic, smooth time even
    when the underlying mpv clock is jittery.
    """

    HISTORY = 8
    # Slew-rate cap on the smoother's offset correction. Bumped from
    # 2% → 5% on 2026-05-02. Reasoning: the previous 2% leaves only 20 ms
    # of correction per second of audio, which is enough for mpv's
    # frame-rate jitter but not for systematic clock drift between the
    # audio device crystal and mpv's media clock. With 2%, accumulated
    # drift could push the offset past the auto-resync threshold and
    # trigger an audible click during steady playback. 5% gives the
    # smoother headroom to absorb routine drift; the per-block tempo
    # change is still small enough to be inaudible (5% on a 700 Hz
    # carrier is a 35 Hz shift, lasting one block ≈ 21 ms).
    MAX_DRIFT_PER_SEC = 0.05
    # Disagreement (seconds) between observed and tracked offset that
    # triggers a silent re-adoption. Bumped from 1.0 → 2.0 on 2026-05-02
    # because: (1) seeks now go through `_seek_with_envelope` which
    # wraps the offset jump in a 250 ms envelope, so the smoother
    # doesn't need to detect them; (2) post-seek decoder settling can
    # take 1-2 s and produced audible secondary auto-resyncs at the
    # 1.0 threshold even after the seek envelope had completed. 2.0 s
    # leaves real "something is wrong" jumps detectable while
    # absorbing routine post-seek jitter.
    AUTO_RESYNC_THRESHOLD = 2.0

    def __init__(self) -> None:
        self.offset: float = 0.0
        self.auto_resync_count: int = 0
        self.just_auto_resynced: bool = False
        self._error_history: list[float] = []
        self._initialized = False
        # When True, `update()` short-circuits: returns the held offset
        # and refuses to auto-resync even on big jumps. Set by stop()
        # before tearing down the stream so that mpv's time-pos
        # vanishing doesn't trigger an auto_resync at full output
        # volume — that produced an audible click on close
        # (debug-stream-20260503-155128.jsonl line 238: stim.auto_resync
        # at fade_gain=1.0, envelope_gain=1.0, stopping=true,
        # offset jump 154 s → carrier discontinuity → pop).
        self.frozen: bool = False

    def reset(self) -> None:
        self.offset = 0.0
        self._error_history = []
        self._initialized = False
        # auto_resync_count intentionally NOT cleared — it accumulates
        # over the stream's lifetime so the close-time DebugLog event
        # reports total auto-resyncs across the whole session.
        self.just_auto_resynced = False

    def update(
        self,
        steady_clock: np.ndarray,
        media_time: float,
        sample_rate: int,
    ) -> np.ndarray:
        """Build a smoothed `system_time_estimate` array for one audio
        block. Caller passes the perfectly-linear `steady_clock` for
        this block plus the current media-time observation.

        Returns an array same shape as `steady_clock`.

        On big jumps (`|observed - offset| > AUTO_RESYNC_THRESHOLD`)
        silently re-adopts the new offset wholesale — typically because
        mpv is paused (media_time stops advancing while steady_clock
        keeps going) or because a seek just landed. No exception, no
        block silenced. The synth's algorithm internally silences when
        `media_sync.is_playing()` is False, so no audible artifact
        comes from a "weird" smoothed offset during paused playback.
        """
        n = steady_clock.shape[0]
        steady_end = float(steady_clock[-1]) if n else 0.0
        observed_offset = media_time - steady_end

        if self.frozen:
            # Frozen by stop(): hold the offset steady so the audio
            # callback can fade out without the smoother snapping the
            # carrier's modulation parameters underneath it.
            self.just_auto_resynced = False
            return steady_clock + self.offset

        if not self._initialized:
            # First callback — adopt observed offset wholesale; nothing to
            # smooth against yet.
            self.offset = observed_offset
            self._error_history = [0.0]
            self._initialized = True
            self.just_auto_resynced = False
            return steady_clock + self.offset

        if abs(observed_offset - self.offset) > self.AUTO_RESYNC_THRESHOLD:
            # Big jump — auto-adopt the new offset and reset smoothing
            # history. Critically, we still return the PREVIOUS offset
            # for THIS block so the synth's output is continuous (carrier
            # phase + funscript modulation both advance smoothly from the
            # last block). The new offset takes effect on the NEXT block.
            #
            # The stream callback observes `just_auto_resynced` and fades
            # the synth's continuous-but-stale output OUT to silence over
            # this whole block. Then the next block, with the jumped
            # modulation, fades back IN from zero — masking the step at
            # the modulation boundary entirely. Without this two-step,
            # filling outdata with zeros produced a click because the
            # previous block ended at full carrier amplitude.
            self.auto_resync_count += 1
            self.just_auto_resynced = True
            prev_offset = self.offset
            self.offset = observed_offset
            self._error_history = [0.0]
            return steady_clock + prev_offset

        self.just_auto_resynced = False

        # Low-pass over recent observations.
        error = observed_offset - self.offset
        self._error_history.append(error)
        if len(self._error_history) > self.HISTORY:
            self._error_history = self._error_history[-self.HISTORY:]
        avg_error = sum(self._error_history) / len(self._error_history)

        # Slew-rate-limit the correction. dt is the audio time covered by
        # this block (in seconds); max correction is dt * 2%/sec.
        dt = n / sample_rate
        max_adjustment = dt * self.MAX_DRIFT_PER_SEC
        adjustment = max(-max_adjustment, min(avg_error * dt, max_adjustment))

        prev_offset = self.offset
        self.offset = prev_offset + adjustment

        # Within this block, ramp linearly from prev_offset to the new
        # offset — gives the synth a smooth monotonic clock instead of
        # a step at the block boundary.
        offset_ramp = np.linspace(prev_offset, self.offset, n, endpoint=False)
        return steady_clock + offset_ramp


class AudioFilePlaybackSource:
    """Pre-rendered audio-file source compatible with StimAudioStream.

    Mirrors StimSynth's interface — exposes a `sample_rate` attribute and
    a `generate_block_with_clocks(steady_clock, system_time_estimate)`
    method — so a `<stem>.prostate.wav` can drive the same audio output
    pipeline as live synthesis. No new StimAudioStream variant needed;
    pass an instance of this class where you'd pass a `StimSynth`.

    Loads the file once at construction. Playback is read-only and
    thread-safe across audio callbacks (the underlying numpy array is
    immutable after `__init__`).

    Sample-rate handling is **option B (require, don't resample)**:
    we raise on mismatch with a clear "re-export at <rate> Hz" message.
    Resampling is out of scope for v0.0.3 — pre-rendered prostate WAVs
    are rare (forgegen-family doesn't yet emit them; we may be the
    first tool consuming them). Adding `librosa.resample` is a future
    enhancement if real-world usage shows frequent mismatches.

    Format constraints (stdlib `wave` module):
      - Container: RIFF/WAV
      - Encoding: PCM (8/16/24/32-bit signed integer; 8-bit unsigned)
      - Channels: 1 (auto-tiled to stereo) or 2 (used as-is); 3+ takes L/R only
      - Float WAV is rejected by `wave.open` and surfaces as a clear error
    """

    # sounddevice can report the device default rate as e.g. 44099.999 vs
    # 44100; allow a tiny tolerance so off-by-rounding doesn't reject
    # legitimately-matched files.
    SAMPLE_RATE_TOLERANCE_HZ = 1

    def __init__(self, file_path: Path, target_sample_rate: int) -> None:
        # stdlib `wave` — narrow but no extra dep. Force lazy import so
        # this module loads cleanly even on environments that have a
        # broken `wave` shim (rare but possible in some embedded builds).
        import wave  # noqa: PLC0415

        with wave.open(str(file_path), "rb") as wf:
            file_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()  # bytes per sample
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if abs(file_rate - target_sample_rate) > self.SAMPLE_RATE_TOLERANCE_HZ:
            raise ValueError(
                f"Audio file sample-rate mismatch: {file_path.name} is "
                f"{file_rate} Hz, Haptic 2 device wants {target_sample_rate} Hz. "
                f"Re-export the file at {target_sample_rate} Hz to use it on "
                f"this device."
            )

        # Decode PCM → float32 in [-1, 1]. wave module guarantees PCM
        # encoding (raises on float-WAV at open time) so the only branches
        # are integer widths.
        if sample_width == 1:
            # 8-bit PCM is unsigned with bias 128 (per WAV spec).
            arr = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            arr = (arr - 128.0) / 128.0
        elif sample_width == 2:
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 3:
            # 24-bit PCM — packed as 3 bytes/sample, little-endian, signed.
            # numpy doesn't have a native int24 dtype; expand to int32.
            packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
            int32 = (
                packed[:, 0].astype(np.int32)
                | (packed[:, 1].astype(np.int32) << 8)
                | (packed[:, 2].astype(np.int32) << 16)
            )
            # Sign-extend bit 23 → bit 31.
            int32 = np.where(int32 & 0x800000, int32 | ~0xFFFFFF, int32)
            arr = int32.astype(np.float32) / float(1 << 23)
        elif sample_width == 4:
            arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
            arr /= float(1 << 31)
        else:
            raise ValueError(
                f"Unsupported sample width: {sample_width} bytes. "
                f"{file_path.name} must be 8/16/24/32-bit PCM."
            )

        # Reshape interleaved samples to (n_frames, n_channels).
        arr = arr.reshape(-1, n_channels)

        # Mono → stereo: duplicate to L+R. Multi-channel (5.1, 7.1) takes
        # the first two channels rather than refusing the file.
        if n_channels == 1:
            arr = np.tile(arr, (1, 2))
        elif n_channels >= 3:
            arr = np.ascontiguousarray(arr[:, :2])

        # Force C-contiguous so the audio callback's slice is zero-copy.
        self._audio: np.ndarray = np.ascontiguousarray(arr, dtype=np.float32)
        self.sample_rate: int = file_rate
        # Stand-in for StimSynth's `waveform` attribute used in DebugLog —
        # marks this source in logs as a non-synth playback path.
        self.waveform: str = "audio_file"

    def generate_block_with_clocks(
        self,
        steady_clock: np.ndarray,
        system_time_estimate: np.ndarray,
    ) -> np.ndarray:
        """Read `frames` of stereo PCM from the loaded file at the
        media-time position dictated by `system_time_estimate[0]`.

        Same shape contract as `StimSynth.generate_block_with_clocks` —
        returns `(frames, 2)` float32. Past end of file returns silence
        (matches the synth's behavior at end-of-funscript). Pause is
        handled outside this class by `StimAudioStream`'s fade gate.
        """
        frames = int(steady_clock.shape[0])
        if frames == 0:
            return np.zeros((0, 2), dtype=np.float32)

        # Use start-of-block media time. Within-block jitter / smoothing
        # would matter for synthesis (carrier phase) but pre-rendered
        # audio plays at its native rate — sample-accurate seek per block
        # is good enough.
        start_t = float(system_time_estimate[0])
        start_sample = max(0, int(start_t * self.sample_rate))

        if start_sample >= len(self._audio):
            return np.zeros((frames, 2), dtype=np.float32)

        end_sample = start_sample + frames
        block = self._audio[start_sample:end_sample]

        if block.shape[0] < frames:
            # File ends mid-block — pad with silence.
            pad = np.zeros((frames - block.shape[0], 2), dtype=np.float32)
            block = np.concatenate([block, pad], axis=0)

        return np.ascontiguousarray(block, dtype=np.float32)


class StimAudioStream:
    """One sounddevice OutputStream driven by one StimSynth.

    Lifecycle:
      stream = StimAudioStream(synth, time_source=lambda: video.time_pos,
                               device_id="wasapi/{...}")
      stream.start()       # opens the device, starts pulling audio
      ...
      stream.stop()        # closes the device

    The `time_source` callable is invoked from the audio callback to get
    the current media-time (in seconds) for the funscript axes. Production
    wires this to the SyncEngine's Slot 1 mpv `time-pos`. Don't do any
    expensive work in the callable — it runs on the audio thread.

    Sample rate is read from the synth (`synth.sample_rate`) so the
    stream opens at whatever rate the device's `default_samplerate` was
    when the synth was constructed. Most USB dongles default to 44100,
    a few default to 48000; PortAudio raises -9997 "Invalid sample rate"
    if asked for a rate the device doesn't accept.
    """

    # blocksize=0 lets PortAudio / the driver pick (typically the device's
    # native preferred buffer size). Pinning a small number like 512 forces
    # extra hops through the host's resampler/buffer and crackles on USB
    # dongles when CPU spikes briefly.
    BLOCK_SIZE = 0
    # 'high' targets ~50–100 ms output latency depending on host API. Trades
    # haptic-vs-video sync precision for crackle resistance — the user can
    # compensate with the haptic_offset_ms preference.
    LATENCY = "high"
    # Pause/play transition fade. A step from full carrier amplitude to
    # zero in a single sample is a click; ~5 ms ramp is below the
    # ear's transient threshold while still feeling instantaneous.
    FADE_MS = 5.0
    # Recovery envelope length when the time smoother auto-resyncs
    # (e.g. mpv time_pos jumps, audio thread starvation, etc.). The
    # original design relied on the play/pause fade gate's 5 ms ramp
    # for recovery, which users heard as click-pause-click roughly
    # once a second on Windows playback. Bumping the post-resync
    # envelope ramp to 100 ms turns each into a soft fade.
    AUTO_RESYNC_RECOVERY_S = 0.10

    def __init__(
        self,
        synth: StimSynth,
        time_source: Callable[[], float],
        device_id: str | None = None,
        *,
        mpv_devices: list[dict] | None = None,
        is_playing_source: Callable[[], bool] | None = None,
    ) -> None:
        self._synth = synth
        self._time_source = time_source
        # is_playing_source gates the output via a fade envelope at this
        # layer instead of letting the synth's algorithm internally
        # silence (a synth-internal step from full to zero is a click).
        # When None (tests, offline rendering), output is always
        # ungated — caller is responsible for pause semantics.
        self._is_playing_source = is_playing_source
        self._device_id = device_id
        self._device_name = resolve_audio_device(device_id, mpv_devices)
        self._stream: object | None = None
        self._lock = threading.Lock()
        # Underrun counter — surfaces glitch counts after the stream
        # stops, so debug-mode can tell the user "your dongle dropped 14
        # buffers during this scene" instead of just "it crackled."
        self._underrun_count = 0
        # Sample-counter for the steady_clock baseline. Independent of
        # synth's internal counter so we don't reach into private state.
        self._frame_offset = 0
        self._smoother = _TimeSmoother()
        # Pause/play fade gate state. Starts at 0 (silent) so the first
        # transition to "playing" fades up rather than punching the
        # carrier in instantly.
        self._fade_gain: float = 0.0
        # Stop-in-progress flag — set before the device is closed so the
        # last few audio callbacks force fade target to 0, ramping the
        # output down to silence. Without this, PortAudio cuts the
        # stream mid-buffer at full carrier amplitude → audible pop on
        # close.
        self._stopping: bool = False
        # Independent multiplicative envelope, layered on top of the
        # play/pause fade gate. Used for transitions where the 5 ms
        # play/pause fade is too short to mask the underlying audio
        # discontinuity:
        #   - **Seek**: pre-seek ramp to 0 over ~500 ms, mpv seeks while
        #     stream is silent, post-seek ramp back to 1.
        #   - **Calibrate stop / device close**: ramp to 0 over ~500 ms
        #     before tearing down, eliminating the close-pop a 5 ms fade
        #     can leave on some USB dongles.
        #
        # State is structured to support MULTI-BLOCK ramps. The original
        # design re-used `_cosine_ramp` from the play/pause fade gate,
        # but that helper assumes the ramp completes within one audio
        # block (true for the 5 ms play/pause case at any reasonable
        # block size, false for our 500 ms envelope case where the ramp
        # spans ~24 blocks). The 2026-05-03 dogfood pop fix is exactly
        # this: track `progress` across blocks so a request_envelope
        # actually takes its requested seconds.
        #   - `_envelope_gain`: current per-block multiplier (live value)
        #   - `_envelope_start`: gain when the current ramp began
        #   - `_envelope_target`: target gain
        #   - `_envelope_fade_samples`: total samples in the current ramp
        #   - `_envelope_progress`: 0.0 → 1.0, fraction of ramp covered
        self._envelope_gain: float = 1.0
        self._envelope_start: float = 1.0
        self._envelope_target: float = 1.0
        self._envelope_fade_samples: int = 1
        self._envelope_progress: float = 1.0
        # Pop-investigation: optional record-to-WAV per stream. Opens
        # in start() when FORGEPLAYER_RECORD_STIM_DIR is set; writes
        # int16 stereo from the audio thread. Disk I/O on the audio
        # thread is best-effort wrapped in try/except.
        self._record_wav: wave.Wave_write | None = None
        self._record_path: Path | None = None

    @property
    def device_name(self) -> str | int | None:
        """The sounddevice device handle this stream targets — an int
        index (preferred) or name string (fallback), or None when
        falling back to system default. Useful for debug logs + UI
        surfacing."""
        return self._device_name

    def start(self) -> None:
        """Open the audio device and begin pulling blocks from the synth.

        Idempotent: calling twice is a no-op after the first call.

        Stim streams open in **WASAPI exclusive mode** when the device is
        WASAPI-backed (Windows). Exclusive mode locks the device to this
        process and bypasses Windows' shared-mode mixer entirely — no
        resampling, no other-app audio bleeding into the stim output, and
        no shared-mode mixer state transitions that can produce clicks
        (2026-05-03 dogfood: pops audible across all output devices when
        stim streams ran shared with mpv, consistent with shared-mode
        mixer contention). If exclusive mode fails (non-WASAPI host,
        device busy, format unsupported), we log + retry in shared mode
        so launch still succeeds.
        """
        with self._lock:
            if self._stream is not None:
                return
            sd = _load_sounddevice()
            stream = self._open_stream_with_fallback(sd)
            stream.start()
            self._stream = stream
            self._open_recording_if_requested()

    def _open_stream_with_fallback(self, sd):
        """Try WASAPI exclusive; fall back to shared on failure.

        Lifted out of `start()` so the fallback logic stays readable.
        Returns an UNstarted stream — caller calls `.start()`.
        """
        # Best-effort exclusive mode. WasapiSettings only matters on
        # WASAPI host APIs; on other hosts sounddevice ignores it.
        try:
            wasapi = sd.WasapiSettings(exclusive=True)
        except Exception:
            wasapi = None

        if wasapi is not None:
            try:
                return sd.OutputStream(
                    samplerate=self._synth.sample_rate,
                    channels=2,
                    dtype="float32",
                    blocksize=self.BLOCK_SIZE,
                    latency=self.LATENCY,
                    device=self._device_name,
                    callback=self._callback,
                    extra_settings=wasapi,
                )
            except Exception as exc:
                _log.warning(
                    "WASAPI exclusive open failed (device=%r): %s — "
                    "retrying in shared mode",
                    self._device_name, exc,
                )

        try:
            return sd.OutputStream(
                samplerate=self._synth.sample_rate,
                channels=2,
                dtype="float32",
                blocksize=self.BLOCK_SIZE,
                latency=self.LATENCY,
                device=self._device_name,
                callback=self._callback,
            )
        except Exception as exc:
            _log.error(
                "Failed to open audio stream (device=%r): %s",
                self._device_name, exc,
            )
            raise

    # Default ramp-to-silence duration before tearing down the device.
    # 500 ms matches the seek-aware envelope (control_window's
    # _SEEK_ENVELOPE_S). User has explicitly clicked stop / close, so
    # a soft half-second fade is preferred over a click.
    STOP_FADE_SECONDS = 0.50

    def stop(self, *, fade_seconds: float | None = None) -> None:
        """Close the audio device. Safe to call multiple times.

        Ramps the secondary envelope to 0 over `fade_seconds` (default:
        STOP_FADE_SECONDS = 120 ms) BEFORE tearing down so PortAudio
        doesn't cut the stream mid-buffer at full carrier amplitude.
        Without this ramp the user hears a click on close — the
        play/pause fade gate's 5 ms fade is too fast on some USB
        dongles to fully discharge the output.

        We also flip the legacy `_stopping` flag so the play/pause
        fade gate ALSO drives target to 0 (belt + suspenders — if the
        envelope path errors for any reason, the fade gate still gets
        us to silence within FADE_MS).
        """
        with self._lock:
            if self._stream is None:
                return
            # Freeze the smoother BEFORE setting _stopping or kicking
            # off the fade envelope. Otherwise the next audio callback
            # could see mpv's time-pos already vanishing, fire an
            # auto_resync at full output volume, snap the offset, and
            # produce a carrier-modulation step that the cosine
            # fade-out can't fully mask within one block.
            self._smoother.frozen = True
            self._stopping = True

        fade = self.STOP_FADE_SECONDS if fade_seconds is None else float(fade_seconds)
        self.request_envelope(0.0, fade)

        # Block on the GUI thread until the envelope has had time to
        # complete + a small cushion for the last audio callback to
        # apply it. Acceptable because every caller of stop() is a
        # deliberate user gesture (close, calibrate-tap-off).
        import time  # noqa: PLC0415
        time.sleep(fade + 0.02)

        with self._lock:
            stream = self._stream
            self._stream = None

        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                _log.warning("Error closing audio stream: %s", exc)

        self._close_recording()

    def _open_recording_if_requested(self) -> None:
        """If `FORGEPLAYER_RECORD_STIM_DIR` is set, open a per-stream
        WAV file (int16 stereo at synth rate). Best-effort — failures
        log a warning but do NOT raise; recording is debug-only."""
        record_dir = os.environ.get("FORGEPLAYER_RECORD_STIM_DIR", "").strip()
        if not record_dir:
            return
        try:
            d = Path(record_dir)
            d.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
            tag = str(self._device_name) if self._device_name is not None else "default"
            safe_tag = "".join(
                c if c.isalnum() else "_" for c in tag
            )[:48] or "stim"
            self._record_path = d / f"stim-{stamp}-{safe_tag}.wav"
            wf = wave.open(str(self._record_path), "wb")
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(int(self._synth.sample_rate))
            self._record_wav = wf
            _log.info("Recording stim output to %s", self._record_path)
        except Exception as exc:
            _log.warning(
                "Failed to open stim recording (dir=%r): %s",
                record_dir, exc,
            )
            self._record_wav = None
            self._record_path = None

    def _close_recording(self) -> None:
        wf = self._record_wav
        self._record_wav = None
        if wf is not None:
            try:
                wf.close()
            except Exception as exc:
                _log.warning("Error closing stim recording: %s", exc)

    def _record_block(self, outdata: np.ndarray) -> None:
        """Best-effort write to the open recording. Called from the
        audio thread; failures are swallowed so a recording problem
        never breaks playback."""
        wf = self._record_wav
        if wf is None:
            return
        try:
            block_int16 = (
                np.clip(outdata, -1.0, 1.0) * 32767.0
            ).astype(np.int16, copy=False)
            wf.writeframes(block_int16.tobytes())
        except Exception:
            pass

    def is_running(self) -> bool:
        return self._stream is not None

    @property
    def underrun_count(self) -> int:
        """Number of `output_underflow` reports observed by the audio
        callback during this stream's lifetime. Non-zero means crackle —
        the device thread starved at least once. Surfaced after stop()
        so post-mortem debugging can quantify driver hiccups."""
        return self._underrun_count

    @property
    def resync_count(self) -> int:
        """Number of times the smoother auto-adopted a new media-time
        offset because the observation jumped past tolerance. Typical
        triggers: paused playback (steady_clock advances, time-pos
        stays put), seeks. Surfaced for debug export alongside
        underrun_count."""
        return self._smoother.auto_resync_count

    def request_envelope(self, target: float, seconds: float) -> None:
        """Smoothly ramp the secondary envelope toward `target` (0..1)
        over `seconds` of audio. Multiplied into the output AFTER the
        play/pause fade gate, so this can drive the carrier to silence
        WITHOUT changing the play/pause state.

        Used by callers that need a longer fade than the play/pause
        gate's 5 ms — typically:
          - SyncEngine.seek_all → request_envelope(0.0, 0.5) → seek →
            request_envelope(1.0, 0.5). Hides the funscript axis
            discontinuity on seek that otherwise pops.
          - CalibrationStream / launched-stream stop → request_envelope(
            0.0, 0.5), wait, then close the device. Gives the
            output time to slope to zero before PortAudio cuts.

        Re-entrant — calling mid-ramp restarts the ramp with the new
        target, starting from the current gain (no jump-to-start
        artifact). Reaches the new target in `seconds` regardless of
        what was happening when the call landed.

        Thread-safe: state fields are read on the audio thread and
        written on the GUI thread; Python's GIL gives us atomic
        float/int writes which is sufficient here.
        """
        clamped = max(0.0, min(1.0, float(target)))
        sample_rate = int(self._synth.sample_rate)
        # Ramp must cover at least 1 sample to avoid divide-by-zero
        # paths; in practice 500 ms × 48k = 24 000 samples so the
        # clamp-to-1 only matters on absurd inputs.
        fade_samples = max(1, int(float(seconds) * sample_rate))
        self._envelope_start = self._envelope_gain  # ramp starts from where we are
        self._envelope_target = clamped
        self._envelope_fade_samples = fade_samples
        self._envelope_progress = 0.0

    def _apply_envelope(
        self,
        block: np.ndarray,
        frames: int,
    ) -> np.ndarray:
        """Apply the secondary envelope multiplier to `block` with
        proper multi-block progress tracking.

        Why we don't reuse `_cosine_ramp`: that helper assumes the ramp
        completes within `frames` samples (true for the 5 ms play/pause
        fade at any reasonable block size, FALSE for our 500 ms envelope
        which spans ~24 audio blocks). Reusing it would compress the
        full 0→1 ramp into one block — exactly the bug that caused the
        ~50 ms post-seek pops users heard during the 2026-05-03 dogfood
        even with `_SEEK_ENVELOPE_S = 0.5` set. Here we compute per-
        sample progress through the cosine ramp explicitly.
        """
        target = self._envelope_target
        start = self._envelope_start

        # Already at target: fast paths.
        if self._envelope_progress >= 1.0 and abs(self._envelope_gain - target) < 1e-6:
            if self._envelope_gain == 1.0:
                return block
            if self._envelope_gain == 0.0:
                return np.zeros_like(block)
            return block * self._envelope_gain

        fade_samples = self._envelope_fade_samples
        # Sample-by-sample progress through the ramp. progress=0 →
        # gain=start; progress=1 → gain=target. Clamp at 1.0 for any
        # samples past the ramp's end.
        samples_into_ramp = self._envelope_progress * fade_samples
        sample_indices = np.arange(frames)
        sample_progress = np.minimum(
            (samples_into_ramp + sample_indices) / fade_samples, 1.0,
        )

        # Cosine shape: same zero-derivative-at-endpoints curve as the
        # play/pause fade gate, just spread across multiple blocks.
        phase = sample_progress * np.pi
        gain = start + (target - start) * 0.5 * (1.0 - np.cos(phase))

        # Update state for next block's call.
        self._envelope_gain = float(gain[-1])
        self._envelope_progress = float(
            min(1.0, (samples_into_ramp + frames) / fade_samples)
        )

        return (block * gain.reshape(-1, 1).astype(np.float32))

    @staticmethod
    def _cosine_ramp(
        start: float, end: float, frames: int, fade_samples: int,
    ) -> np.ndarray:
        """Hann-window-shaped ramp from `start` to `end` completing in
        `fade_samples`, then holding at `end` for the remaining frames.

        Cosine shape (`0.5 * (1 - cos(π t))`) has ZERO derivative at both
        endpoints, unlike a linear ramp which has a slope discontinuity
        at the moment it reaches the target. That kink is audible as a
        soft click at fade boundaries — especially when the synth's
        modulation amplitude is high at that moment. Cosine is smooth in
        both amplitude AND slope, so the ear gets nothing transient to
        latch onto.
        """
        if fade_samples >= frames:
            phase = np.linspace(0.0, np.pi, frames, endpoint=True)
        else:
            phase = np.minimum(
                np.arange(frames) / float(fade_samples), 1.0,
            ) * np.pi
        return start + (end - start) * 0.5 * (1.0 - np.cos(phase))

    def _apply_fade_gate(
        self,
        block: np.ndarray,
        target: float,
        frames: int,
        sample_rate: int,
    ) -> np.ndarray:
        """Multiply `block` (stereo float32) by a per-sample gain that
        cosine-ramps from `self._fade_gain` toward `target` (0.0 or 1.0)
        over FADE_MS, holding at `target` for the rest of the block.

        Steady-state (already at target) is the fast path: one scalar
        multiply. Transitions allocate a small ramp array.
        """
        if abs(self._fade_gain - target) < 1e-6:
            if self._fade_gain == 1.0:
                return block
            if self._fade_gain == 0.0:
                # Silence — skip the multiply entirely.
                return np.zeros_like(block)
            return block * self._fade_gain

        fade_samples = max(1, int(self.FADE_MS * 1e-3 * sample_rate))
        ramp = self._cosine_ramp(
            self._fade_gain, target, frames, fade_samples,
        )
        self._fade_gain = float(ramp[-1])
        return block * ramp.reshape(-1, 1)

    def _callback(self, outdata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
        """sounddevice OutputStream callback. Runs on the audio thread.

        We pull `frames` worth of stereo samples from the synth and
        write them into `outdata`. If anything goes wrong we silence
        the buffer and log — never raise, because the audio thread will
        die hard and the stream stops producing samples until restart.

        Time source is read once per callback and fed through
        `_TimeSmoother` to produce a low-pass-filtered, monotonic
        `system_time_estimate` for the synth. Without smoothing,
        mpv's time-pos jitter (block rate ≠ video frame rate) causes
        per-block discontinuities that the user hears as crackle.
        """
        if status:
            # output_underflow is the "crackle" condition — the audio
            # thread didn't get a buffer ready in time. Tally separately
            # from generic "status" so we can post-mortem.
            if getattr(status, "output_underflow", False):
                self._underrun_count += 1
            _log.debug("sounddevice status: %s", status)
        try:
            sample_rate = self._synth.sample_rate
            idx = np.arange(frames)
            steady_clock = (idx + self._frame_offset) / sample_rate
            self._frame_offset += frames

            media_t = float(self._time_source())
            system_time_estimate = self._smoother.update(
                steady_clock, media_t, sample_rate,
            )

            block = self._synth.generate_block_with_clocks(
                steady_clock, system_time_estimate,
            )
            if block.shape != (frames, 2):
                _log.warning(
                    "synth returned %s, expected %s — silencing",
                    block.shape, (frames, 2),
                )
                outdata.fill(0)
                return

            # Auto-resync: the smoother stored a new offset but returned
            # `steady_clock + prev_offset` for THIS block, so `block` is
            # continuous with the previous block (carrier phase smooth,
            # funscript modulation smooth). Fade it OUT to silence over
            # this whole block via a cosine curve (zero derivative at
            # both endpoints, no audible knee at the boundary). Next
            # block will see the jumped modulation but fade_gain=0 →
            # ramps up from zero with the same cosine shape over
            # FADE_MS = 5 ms.
            #
            # Two layers of fix on top of the original design:
            #
            # 1. Apply the secondary envelope to THIS block. The
            #    seek-aware pop fix runs request_envelope(0.0, ...)
            #    BEFORE the seek fires, so by the time auto-resync
            #    triggers the envelope is at (or near) zero. Without
            #    this multiply, one block of post-seek audio at full
            #    fade_gain amplitude leaks through — the "upside pop"
            #    on every seek.
            #
            # 2. Force the envelope to 0 and request a longer ramp
            #    back up (100 ms) for the recovery. The next block's
            #    fade_gain ramp (5 ms) alone is too fast to mask the
            #    funscript modulation step that auto-resync produces;
            #    users hear it as a click-pause-click roughly once a
            #    second during playback (78 resyncs in a 90 s scene
            #    is typical, per stim.stream_closed events). The 100 ms
            #    envelope ramp turns each click into a soft fade.
            #    Per-block envelope already covers the seek-up case
            #    (request_envelope(1.0, 0.25) from the seek QTimer
            #    just sets a longer-still target which is fine).
            if self._smoother.just_auto_resynced:
                # Diagnostic: log every resync's context so we can
                # correlate user-reported pops with smoother behavior.
                # Cheap when debug logging is off (DebugLog.record
                # returns immediately if not enabled). Read both
                # offsets via the smoother's diagnostic accessors so
                # we don't reach into private state.
                try:
                    from app.debug_log import DebugLog as _DL  # noqa: PLC0415
                    if _DL.enabled:
                        _DL.record(
                            "stim.auto_resync",
                            media_time=float(media_t),
                            steady_end=float(steady_clock[-1]) if frames else 0.0,
                            new_offset=float(self._smoother.offset),
                            envelope_gain=float(self._envelope_gain),
                            fade_gain=float(self._fade_gain),
                            stopping=bool(self._stopping),
                            resync_count=int(self._smoother.auto_resync_count),
                        )
                except Exception:
                    pass

                ramp = self._cosine_ramp(
                    self._fade_gain, 0.0, frames, fade_samples=frames,
                )
                faded = block * ramp.reshape(-1, 1)
                self._fade_gain = 0.0
                # Recovery envelope decision:
                # - During stop: do nothing — caller's request_envelope(
                #   0.0, ...) already drives output to silence before close.
                # - Steady-play auto-resync (envelope was at full output
                #   before the resync): drop envelope to 0 and ramp back
                #   up over AUTO_RESYNC_RECOVERY_S (100 ms). Without this
                #   the modulation step is audible as a click during play.
                # - Post-seek auto-resync (envelope was already at or near
                #   0 from the seek's pre-fade): leave the caller's pending
                #   request alone. The seek's QTimer set a 250 ms ramp-up
                #   target; overriding to a shorter recovery here makes
                #   the post-seek transition more abrupt than the caller
                #   requested.
                if not self._stopping:
                    if self._envelope_gain > 0.5:
                        self._envelope_gain = 0.0
                        self.request_envelope(1.0, self.AUTO_RESYNC_RECOVERY_S)
                outdata[:] = self._apply_envelope(faded, frames)
                self._record_block(outdata)
                return

            # Apply pause/play fade gate. A direct multiplication by 0/1
            # would step the carrier and click; ramping over ~5 ms makes
            # the transition inaudible. While `_stopping` is set we
            # override target to 0 so the fade ramps down before stop()
            # actually tears down the device — without this, PortAudio
            # cuts at full carrier amplitude on close = audible pop.
            if self._stopping:
                block = self._apply_fade_gate(block, 0.0, frames, sample_rate)
            elif self._is_playing_source is not None:
                target = 1.0 if bool(self._is_playing_source()) else 0.0
                block = self._apply_fade_gate(block, target, frames, sample_rate)

            # Apply the secondary envelope on top of the play/pause
            # fade gate. The two layers stack multiplicatively: pause
            # → fade gate goes to 0 (regardless of envelope); seek →
            # envelope goes to 0 (regardless of play/pause). Whichever
            # is silent wins.
            block = self._apply_envelope(block, frames)

            outdata[:] = block
            self._record_block(outdata)
        except Exception as exc:
            _log.exception("audio callback failed: %s", exc)
            outdata.fill(0)


# ── Internals ─────────────────────────────────────────────────────────────────

def _load_sounddevice():
    """Lazy import. sounddevice fails to import in some headless CI envs
    (no PortAudio binding); we want module load to succeed regardless and
    only fail when somebody actually tries to start a stream."""
    import sounddevice  # noqa: PLC0415

    return sounddevice


def _query_mpv_audio_devices() -> list[dict]:
    """One-shot enumeration of mpv's audio device list. Imported lazily
    so that audio-related unit tests don't require libmpv on CI."""
    try:
        from app.sync_engine import SyncEngine  # noqa: PLC0415
        return SyncEngine.list_audio_devices(include_hdmi=True)
    except Exception as exc:
        _log.warning("Could not query mpv for audio devices: %s", exc)
        return []
