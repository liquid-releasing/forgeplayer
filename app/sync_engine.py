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

    MAX_SLOTS = 3

    def __init__(self) -> None:
        self._players: list[Optional[mpv.MPV]] = [None] * self.MAX_SLOTS
        self._lock = threading.Lock()

    # ── Player lifecycle ──────────────────────────────────────────────────────

    def init_player(self, slot: int, wid: int, audio_device: str = "") -> mpv.MPV:
        """Create an mpv instance embedded in *wid* (native window handle)."""
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
            }
            if audio_device:
                kwargs["audio_device"] = audio_device
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

    def terminate_all(self) -> None:
        for i in range(self.MAX_SLOTS):
            self.terminate_player(i)

    # ── Sync transport ────────────────────────────────────────────────────────

    @property
    def _active(self) -> list[mpv.MPV]:
        return [p for p in self._players if p is not None]

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
        """Seek every active player to *position* seconds simultaneously."""
        for p in self._active:
            try:
                p.seek(position, "absolute")
            except Exception:
                pass

    # ── State queries ─────────────────────────────────────────────────────────

    def _primary(self) -> Optional[mpv.MPV]:
        """Return the first active player (used to drive the seek bar)."""
        return next(iter(self._active), None)

    def get_position(self) -> float:
        p = self._primary()
        if p:
            try:
                pos = p.time_pos
                return float(pos) if pos is not None else 0.0
            except Exception:
                return 0.0
        return 0.0

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
    def list_audio_devices() -> list[dict]:
        """Return mpv's audio device list as [{name, description}, ...]."""
        try:
            tmp = mpv.MPV()
            devices = list(tmp.audio_device_list)
            tmp.terminate()
            return devices
        except Exception:
            return []
