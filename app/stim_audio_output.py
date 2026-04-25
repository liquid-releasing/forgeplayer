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
import threading
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
    MAX_DRIFT_PER_SEC = 0.02  # i.e. 20 ms per audio second of correction
    AUTO_RESYNC_THRESHOLD = 1.0  # seconds of disagreement → silent re-adoption

    def __init__(self) -> None:
        self.offset: float = 0.0
        self.auto_resync_count: int = 0
        self.just_auto_resynced: bool = False
        self._error_history: list[float] = []
        self._initialized = False

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
        """
        with self._lock:
            if self._stream is not None:
                return
            sd = _load_sounddevice()
            try:
                stream = sd.OutputStream(
                    samplerate=self._synth.sample_rate,
                    channels=2,
                    dtype="float32",
                    blocksize=self.BLOCK_SIZE,
                    latency=self.LATENCY,
                    device=self._device_name,
                    callback=self._callback,
                )
                stream.start()
            except Exception as exc:
                _log.error(
                    "Failed to open audio stream (device=%r): %s",
                    self._device_name, exc,
                )
                raise
            self._stream = stream

    # Time to leave the audio callback running while the fade-out
    # completes before tearing down the device. One block at typical
    # rates is ~21–23 ms; 40 ms covers any reasonable block size with
    # margin for OS scheduling. Short enough that a user won't notice
    # the delay between hitting close and the window disappearing.
    STOP_FADEOUT_MS = 40.0

    def stop(self) -> None:
        """Close the audio device. Safe to call multiple times.

        Sets `_stopping` so the next audio callback forces fade target
        to 0 (regardless of `is_playing_source`), then sleeps long
        enough for the fade-out to play out before actually closing
        the stream. Otherwise PortAudio cuts at full carrier amplitude
        and the user hears a pop on close.
        """
        with self._lock:
            if self._stream is None:
                return
            self._stopping = True

        # Block on the GUI thread for one fade window so the audio
        # thread completes a fade-out callback. Acceptable because
        # close-players is already a deliberate user gesture.
        import time  # noqa: PLC0415
        time.sleep(self.STOP_FADEOUT_MS * 1e-3)

        with self._lock:
            stream = self._stream
            self._stream = None

        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                _log.warning("Error closing audio stream: %s", exc)

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
            # ramps up from zero with the same cosine shape, masking
            # the step.
            if self._smoother.just_auto_resynced:
                ramp = self._cosine_ramp(
                    self._fade_gain, 0.0, frames, fade_samples=frames,
                )
                outdata[:] = block * ramp.reshape(-1, 1)
                self._fade_gain = 0.0
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

            outdata[:] = block
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
