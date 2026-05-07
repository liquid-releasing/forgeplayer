# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""SyncEngine — owns and coordinates all mpv player instances."""

from __future__ import annotations

import threading
from typing import Optional

import mpv


class SyncEngine:
    """Manages up to 3 mpv instances.

    All transport commands (play, pause, seek) are applied to every active
    player in a tight loop so they stay frame-accurate.
    """

    MAX_SLOTS = 4

    def __init__(self) -> None:
        self._players: list[Optional[mpv.MPV]] = [None] * self.MAX_SLOTS
        self._lock = threading.Lock()
        # Last good time_pos reading. mpv's time_pos is None during
        # transient states (between frames, during seeks, while a buffer
        # is being filled); without this cache the audio thread reads
        # 0.0 → its time smoother thinks the clock just jumped backward
        # → auto-resync → audible click. Cache the last numeric value
        # and return it instead.
        self._last_position: float = 0.0
        # Optional headless mpv instance that mirrors the video's audio
        # to a second output device. Loaded with the same media as the
        # primary video slot but rendered audio-only. Lives outside the
        # slot grid because it has no role in the slot/screen routing
        # model — it's a parallel listener, configured per-user via
        # Preferences.scene_audio_secondary_device. Included in
        # _active so play_all/pause_all/seek_all keep it in sync.
        self._scene_audio_mirror: Optional[mpv.MPV] = None

    # ── Player lifecycle ──────────────────────────────────────────────────────

    def init_player(
        self,
        slot: int,
        wid: int,
        audio_device: str = "",
        *,
        fill: bool = False,
    ) -> mpv.MPV:
        """Create an mpv instance embedded in *wid* (native window handle).

        ``fill=True`` engages mpv's panscan to fill the viewport entirely
        — the video is scaled up and cropped (top/bottom for a
        16:9-on-32:9 case) rather than letterboxed. Useful for ultrawide
        monitors (e.g. 5120×1440 Odyssey) where 16:9 4K content would
        otherwise leave large black bars on each side. ``fill=False``
        is the default fit (preserve aspect with letterbox/pillarbox).
        """
        with self._lock:
            if self._players[slot]:
                self._players[slot].terminate()  # type: ignore[union-attr]
            kwargs: dict = {
                "wid": str(wid),
                "keep_open": True,
                "pause": True,
                "input_default_bindings": False,
                "input_vo_keyboard": False,
                "osc": False,
                # Frame-accurate seeking. mpv's default lands on the
                # nearest prior keyframe (typically -2..-12s with
                # HandBrake-encoded sources). With chapter-nav + slider
                # scrub the drift was visible — chapter targets landed
                # short and the next click could re-target the same
                # chapter. hr-seek=yes decodes forward from the keyframe
                # to land exactly on the target. Adds 100-500ms per
                # seek for 1080p; imperceptible on this hardware.
                # Re-encoding with `-force_key_frames` at chapter
                # boundaries (forgeassembler's job) is the alternative;
                # this is the runtime fix for arbitrary source files.
                "hr_seek": "yes",
            }
            if audio_device:
                kwargs["audio_device"] = audio_device
            if fill:
                # mpv panscan: 0.0 = letterbox (default), 1.0 = fully
                # fill the viewport via crop. Using a string for the
                # config kwarg keeps mpv happy across versions where
                # numeric vs string handling has varied.
                kwargs["panscan"] = "1.0"
            p = mpv.MPV(**kwargs)
            self._players[slot] = p
            return p

    def init_player_audio_only(self, slot: int, audio_device: str = "") -> mpv.MPV:
        """Create a headless mpv instance with no window.

        Used for audio-only slots (the user loaded an audio override but no
        video). `force_window=no` stops mpv from opening its own stub window
        for audio files. Participates in sync just like video slots —
        seek_all, pause_all, etc. all apply — but doesn't take over a monitor.
        """
        with self._lock:
            if self._players[slot]:
                self._players[slot].terminate()  # type: ignore[union-attr]
            kwargs: dict = {
                "force_window": "no",
                "keep_open": True,
                "pause": True,
                "input_default_bindings": False,
                "input_vo_keyboard": False,
                "osc": False,
            }
            if audio_device:
                kwargs["audio_device"] = audio_device
            p = mpv.MPV(**kwargs)
            self._players[slot] = p
            return p

    def load_file(self, slot: int, path: str) -> None:
        """Load *path* into *slot* (paused at start)."""
        p = self._players[slot]
        if p:
            p.pause = True
            p.play(path)

    def terminate_player(self, slot: int) -> None:
        with self._lock:
            p = self._players[slot]
            if p:
                p.terminate()
                self._players[slot] = None
        # Drop cached position so the next scene starts fresh — last
        # scene's final time_pos is meaningless to a new file.
        if not any(self._players):
            self._last_position = 0.0

    def terminate_all(self) -> None:
        for i in range(self.MAX_SLOTS):
            self.terminate_player(i)
        self.terminate_scene_audio_mirror()
        self._last_position = 0.0

    # ── Scene-audio mirror ────────────────────────────────────────────────────

    def init_scene_audio_mirror(
        self,
        media_path: str,
        audio_device: str,
    ) -> Optional[mpv.MPV]:
        """Spawn a headless mpv loading *media_path* audio-only on
        *audio_device*. Used to fan video audio out to a second output
        (e.g. a stim device that accepts an audio input). Idempotent:
        terminates any prior mirror before creating the new one.

        Returns the mpv instance, or None if creation failed (e.g. the
        device is busy or not present). Failures are non-fatal — the
        primary scene audio path keeps working.
        """
        with self._lock:
            if self._scene_audio_mirror is not None:
                try:
                    self._scene_audio_mirror.terminate()
                except Exception:
                    pass
                self._scene_audio_mirror = None
            kwargs: dict = {
                "force_window": "no",
                "vid": "no",
                "keep_open": True,
                "pause": True,
                "input_default_bindings": False,
                "input_vo_keyboard": False,
                "osc": False,
                "hr_seek": "yes",
            }
            if audio_device:
                kwargs["audio_device"] = audio_device
            try:
                p = mpv.MPV(**kwargs)
                p.play(media_path)
                self._scene_audio_mirror = p
                return p
            except Exception:
                self._scene_audio_mirror = None
                return None

    def terminate_scene_audio_mirror(self) -> None:
        with self._lock:
            if self._scene_audio_mirror is not None:
                try:
                    self._scene_audio_mirror.terminate()
                except Exception:
                    pass
                self._scene_audio_mirror = None

    def has_scene_audio_mirror(self) -> bool:
        return self._scene_audio_mirror is not None

    # ── Sync transport ────────────────────────────────────────────────────────

    @property
    def _active(self) -> list[mpv.MPV]:
        out = [p for p in self._players if p is not None]
        if self._scene_audio_mirror is not None:
            out.append(self._scene_audio_mirror)
        return out

    def play_all(self) -> None:
        for p in self._active:
            p.pause = False

    def pause_all(self) -> None:
        for p in self._active:
            p.pause = True

    def stop_all(self) -> None:
        for p in self._active:
            p.pause = True
            try:
                p.seek(0, "absolute")
            except Exception:
                pass

    def seek_all(self, position: float) -> None:
        """Seek every active player to *position* seconds simultaneously.

        Uses ``precision="exact"`` so mpv decodes forward from the prior
        keyframe to land on the exact target frame. With ``precision=
        "default-precise"`` (mpv's default for absolute seeks) we were
        seeing -2..-12s drift on HandBrake-encoded sources because mpv
        was rounding to the nearest keyframe. Adds ~100-500ms per seek
        for 1080p — imperceptible during normal use, and worth it for
        chapter-nav and slider scrub landing where the user expects.

        Audio duck: briefly mutes each player around the seek so the
        sample discontinuity at the new playhead doesn't pop. Without
        this, ``precision="exact"`` lands the seek mid-sample and the
        waveform jump is audible on USB / external DAC outputs. 50 ms
        is enough to mask the click without being heard as a gap.
        Each player's prior mute state is preserved so a user-set mute
        survives the seek.
        """
        active = self._active
        prior_mute_state: list[tuple[mpv.MPV, bool]] = []
        for p in active:
            try:
                prior_mute_state.append((p, bool(p.mute)))
                p.mute = True
            except Exception:
                pass
        for p in active:
            try:
                p.seek(position, "absolute", "exact")
            except Exception:
                pass

        def _restore_mute() -> None:
            for p, was_muted in prior_mute_state:
                if not was_muted:
                    try:
                        p.mute = False
                    except Exception:
                        pass

        threading.Timer(0.05, _restore_mute).start()

    # ── State queries ─────────────────────────────────────────────────────────

    def _primary(self) -> Optional[mpv.MPV]:
        """Return the first active player (used to drive the seek bar)."""
        return next(iter(self._active), None)

    def get_position(self) -> float:
        """Return current playback position in seconds.

        Cached: mpv's `time_pos` returns None during transient internal
        states (between frames, during seeks, mid-buffer-fill).
        Uncached, the audio thread would see those Nones as 0.0 and
        the time smoother would auto-resync (audible click). Return
        the last numeric reading whenever the live one is None.

        Reset on player init so a new scene doesn't carry over the
        previous scene's position.
        """
        p = self._primary()
        if p:
            try:
                pos = p.time_pos
                if pos is not None:
                    self._last_position = float(pos)
            except Exception:
                pass
        return self._last_position

    def get_duration(self) -> float:
        p = self._primary()
        if p:
            try:
                dur = p.duration
                return float(dur) if dur is not None else 0.0
            except Exception:
                return 0.0
        return 0.0

    def is_paused(self) -> bool:
        p = self._primary()
        if p:
            try:
                return bool(p.pause)
            except Exception:
                return True
        return True

    def set_volume(self, slot: int, value: int) -> None:
        """Set volume 0–100 for a single slot."""
        p = self._players[slot]
        if p:
            try:
                p.volume = max(0, min(100, value))
            except Exception:
                pass

    def has_active_players(self) -> bool:
        return bool(self._active)

    # ── Device discovery ──────────────────────────────────────────────────────

    @staticmethod
    def list_audio_devices(include_hdmi: bool = False) -> list[dict]:
        """Return mpv's audio device list as [{name, description}, ...].

        HDMI/DisplayPort display-audio devices (e.g. a monitor's built-in
        audio driver, which often has no speakers) are filtered out by
        default — they appear in Windows' device list but confuse the
        Scene/Haptic role picker. Pass ``include_hdmi=True`` to see the
        full raw list.
        """
        try:
            tmp = mpv.MPV()
            devices = list(tmp.audio_device_list)
            tmp.terminate()
        except Exception:
            return []
        if include_hdmi:
            return devices
        return [d for d in devices if not _is_display_audio(d)]


def _is_display_audio(device: dict) -> bool:
    """Heuristically identify devices the user almost never wants to
    route to: the mpv 'auto' / 'openal' meta-entries and HDMI / DP
    phantom outputs.

    HDMI/DP phantoms: mpv's WASAPI backend exposes devices like
    'Odyssey G95NC (NVIDIA High Definition Audio)' or '1 - 12.3FHD
    (AMD High Definition Audio Device)'. These are the GPU-driven
    display audio outputs — most monitors don't have speakers, so
    routing here ends up silent. The 'High Definition Audio' phrase
    is the canonical Microsoft Class Driver name for HDMI/DP audio
    paths; any device with that descriptor is overwhelmingly likely
    to be a phantom. Real speaker devices use names like 'Speakers
    (Realtek(R) Audio)' or 'Speakers (USB Audio Device)' — the
    'Speakers' prefix is the tell.

    'auto' (Autoselect device): mpv's "let me pick the OS default"
    meta-entry. Redundant with our role-combo "— not set —" sentinel;
    a user who picks Autoselect in our UI is doing the same thing
    they'd do by leaving the role unset, just with extra confusion
    about what the option does. Filter it.

    openal: mpv's alternate audio backend. Higher latency than
    WASAPI on Windows and frequently broken; we standardize on
    WASAPI for stim routing where timing matters.
    """
    desc = (device.get("description", "") or "").lower()
    name = (device.get("name", "") or "").lower()
    haystack = desc + " " + name

    # mpv's "auto" entry — surfaces as name='auto' description='Autoselect device'.
    if name == "auto":
        return True

    # OpenAL backend — different audio abstraction layer; not what we want.
    if name.startswith("openal") or name == "openal":
        return True

    # HDMI / DisplayPort phantom audio.
    needles = (
        "display audio",
        "displayport",
        "hdmi",
        "dp audio",
        "high definition audio",  # NVIDIA/AMD/Intel HDMI/DP class driver
    )
    return any(n in haystack for n in needles)
