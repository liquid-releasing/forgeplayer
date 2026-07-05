# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""SyncEngine — owns and coordinates all mpv player instances."""

from __future__ import annotations

import threading
from typing import Callable, Optional

import mpv


# Crop position → mpv video-align-y. -1 = flush top, +1 = flush bottom.
# top/bottom land at ∓0.75: with the video filling via panscan, that crops
# 1/8 of the vertical overflow off the near edge and 7/8 off the far edge,
# i.e. keeps the top (or bottom) of the frame with a ~1/8 margin. Mirrors the
# margins the user asked for; center (0.0) is mpv's own default.
_CROP_ALIGN_Y = {"top": -0.75, "center": 0.0, "bottom": 0.75}


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
        crop_align: str = "center",
        on_double_click: Optional[Callable[[], None]] = None,
        on_single_click: Optional[Callable[[], None]] = None,
    ) -> mpv.MPV:
        """Create an mpv instance embedded in *wid* (native window handle).

        ``fill=True`` engages mpv's panscan to fill the viewport entirely
        — the video is scaled up and cropped (top/bottom for a
        16:9-on-32:9 case) rather than letterboxed. Useful for ultrawide
        monitors (e.g. 5120×1440 Odyssey) where 16:9 4K content would
        otherwise leave large black bars on each side. ``fill=False``
        is the default fit (preserve aspect with letterbox/pillarbox).

        ``crop_align`` ("top"/"center"/"bottom") positions the kept region
        when cropping — center is classic; top/bottom back the crop off the
        opposite edge by ~1/8 (mpv video-align-y ∓0.75) so a subject high or
        low in the frame isn't sliced at the edge. Ignored unless ``fill``.
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
                # GPU-decode the video. Without this mpv defaults to
                # software decoding, and a high-bitrate 4K source (e.g. a
                # Topaz upscale) pegs the CPU — which starves BOTH the
                # control-window poll loop and the haptic sync engine, so
                # playback "freezes" at a non-deterministic spot that
                # shifts with the start position (it's CPU/cache falling
                # behind, not a bad frame). `auto-safe` only engages known-
                # good hw decoders (NVDEC/D3D11VA/…) and cleanly falls back
                # to software for codecs it can't offload, so it never makes
                # a decodable file undecodable.
                "hwdec": "auto-safe",
                # Roomier demux buffer so a big 4K file reads ahead instead
                # of stalling the decode thread on disk I/O during long
                # scenes. Bytes, not seconds — caps the readahead RAM.
                "demuxer_max_bytes": "256MiB",
                "demuxer_max_back_bytes": "64MiB",
            }
            if audio_device:
                kwargs["audio_device"] = audio_device
            if fill:
                # mpv panscan: 0.0 = letterbox (default), 1.0 = fully
                # fill the viewport via crop. Using a string for the
                # config kwarg keeps mpv happy across versions where
                # numeric vs string handling has varied.
                kwargs["panscan"] = "1.0"
                # video-align-y positions the kept region in the cropped
                # dimension: -1 = flush top, 0 = center, +1 = flush bottom.
                # top/bottom land at ∓0.75 — crop 1/8 of the overflow off
                # the near edge so the subject keeps a margin (see
                # _CROP_ALIGN_Y). center (0.0) is mpv's own default.
                align_y = _CROP_ALIGN_Y.get(crop_align, 0.0)
                if align_y:
                    kwargs["video_align_y"] = str(align_y)
            p = mpv.MPV(**kwargs)
            # Double-click the video surface = the Escape teardown. mpv owns the
            # video's native child window, so a Qt mouseDoubleClickEvent on the
            # PlayerWindow never sees clicks over the video — bind it at the mpv
            # level instead. on_key_press fires once on the press transition.
            # The callback runs on mpv's event thread; it just emits a Qt signal
            # (queued to the GUI thread), so it's safe to tear down from here.
            if on_double_click is not None:
                try:
                    @p.on_key_press("MBTN_LEFT_DBL")
                    def _on_video_double_click() -> None:
                        on_double_click()
                except Exception:
                    # python-mpv without on_key_press — fall back to the
                    # Qt-level handler (control bar / chrome only).
                    pass
            # Single-click the video surface = toggle the on-screen control
            # bar (hidden by default). Same rationale as the double-click
            # binding: mpv owns the video child window, so Qt mousePressEvent
            # never sees clicks over the video. A double-click fires MBTN_LEFT
            # then MBTN_LEFT_DBL — the stray single-toggle is invisible because
            # the double-click tears the window down immediately after.
            if on_single_click is not None:
                try:
                    @p.on_key_press("MBTN_LEFT")
                    def _on_video_single_click() -> None:
                        on_single_click()
                except Exception:
                    pass
            self._players[slot] = p
            return p

    def set_crop_align(self, slot: int, crop_align: str) -> None:
        """Re-position the crop on an already-running player. Lets the Setup
        radios act on open windows immediately. No-op on a slot that isn't a
        cropping video player (setting video-align-y on a letterboxed video
        has no visible effect anyway)."""
        p = self._players[slot]
        if p is None:
            return
        try:
            p.video_align_y = _CROP_ALIGN_Y.get(crop_align, 0.0)
        except Exception:
            # Headless/audio-only players have no video output; ignore.
            pass

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

    def get_chapter_list(self) -> list[dict]:
        """Return the primary player's chapter list as parsed by mpv.

        mpv reads embedded chapter metadata across formats — FFMETADATA1
        chapter atoms in MP4, QuickTime text-track chapters, Matroska
        chapters, Nero atoms — and exposes them as a list of dicts with
        ``time`` (seconds, float) and ``title`` (str). Returns [] when
        no primary player is active or the file has no chapter atoms.
        Used by ControlWindow as a fallback when no chapter sidecar
        exists, so embedded chapters Just Work without authoring.
        """
        p = self._primary()
        if p is None:
            return []
        try:
            chs = p.chapter_list
            return list(chs) if chs else []
        except Exception:
            return []

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
