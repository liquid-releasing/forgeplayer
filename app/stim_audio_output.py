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


def _find_sounddevice_index(sd, desc: str, target_host: str | None) -> int | None:
    """Look up the integer device index for `desc` in sounddevice.

    Filters by `target_host` (e.g. "Windows WASAPI") when provided, so a
    name like "Speakers (USB Audio Device)" that exists on MME +
    DirectSound + WASAPI narrows to the host api the mpv id belongs to.

    Returns the int index of the unique match, the FIRST index if
    multiple matches remain (e.g. two physically-identical dongles —
    we can't disambiguate without Windows GUIDs), or None if there's
    no match at all (caller falls back to the description string).
    """
    matches: list[int] = []
    try:
        devices = sd.query_devices()
    except Exception:
        return None

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
        idx = _find_sounddevice_index(sd, desc, target_host)
        if idx is not None:
            return idx
    except Exception as exc:
        _log.debug("sounddevice index lookup failed: %s", exc)

    return desc


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

    Sample rate is pinned to `SAMPLE_RATE` (44100); device is opened at
    that rate. If the device can't run at 44100 (rare on USB dongles),
    sounddevice raises and we let it propagate — caller decides whether
    to fall back.
    """

    BLOCK_SIZE = 512

    def __init__(
        self,
        synth: StimSynth,
        time_source: Callable[[], float],
        device_id: str | None = None,
        *,
        mpv_devices: list[dict] | None = None,
    ) -> None:
        self._synth = synth
        self._time_source = time_source
        self._device_id = device_id
        self._device_name = resolve_audio_device(device_id, mpv_devices)
        self._stream: object | None = None
        self._lock = threading.Lock()

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
                    samplerate=SAMPLE_RATE,
                    channels=2,
                    dtype="float32",
                    blocksize=self.BLOCK_SIZE,
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

    def stop(self) -> None:
        """Close the audio device. Safe to call multiple times."""
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

    def _callback(self, outdata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
        """sounddevice OutputStream callback. Runs on the audio thread.

        We pull `frames` worth of stereo samples from the synth and
        write them into `outdata`. If anything goes wrong we silence
        the buffer and log — never raise, because the audio thread will
        die hard and the stream stops producing samples until restart.
        """
        if status:
            _log.debug("sounddevice status: %s", status)
        try:
            media_t = float(self._time_source())
            block = self._synth.generate_block(frames, media_t)
            if block.shape != (frames, 2):
                _log.warning(
                    "synth returned %s, expected %s — silencing",
                    block.shape, (frames, 2),
                )
                outdata.fill(0)
                return
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
