# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Preferences — global device-role config persisted to ~/.forgeplayer/preferences.json.

The user configures which physical audio device plays each *semantic* role
(Scene Audio / Haptic 1 / Haptic 2) once, via the Setup tab. Library clicks
then auto-route: Slot 1 gets Scene Audio, Slot 2 gets Haptic 1. This
eliminates the "pick the USB dongle every time" friction users hit in the
v0.0.1 baseline.

See `project_forgeplayer_multichannel_audio.md` for the channel model
and `feedback_forgeplayer_minimize_thinking.md` for the motivation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


_PREFS_PATH = Path.home() / ".forgeplayer" / "preferences.json"


@dataclass
class Preferences:
    """User-configurable cross-session preferences.

    Fields are mpv `audio_device` identifiers (the same string a slot's
    audio-output combobox uses as its itemData). Empty string means the
    role is not yet configured.
    """

    scene_audio_device: str = ""
    haptic1_audio_device: str = ""
    haptic2_audio_device: str = ""

    @classmethod
    def load(cls) -> "Preferences":
        try:
            data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        fields = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in fields})

    def save(self) -> None:
        """Write preferences to disk. Best-effort — a failure here should
        never break the app (the in-memory copy still works for this
        session)."""
        try:
            _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _PREFS_PATH.write_text(
                json.dumps(asdict(self), indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    @staticmethod
    def path() -> Path:
        return _PREFS_PATH
