# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Session — serializable configuration for a playback setup."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict


@dataclass
class SlotConfig:
    enabled: bool = False
    video_path: str = ""
    audio_path: str = ""       # optional separate audio file (overrides video audio)
    monitor_index: int = 0
    audio_device: str = ""     # mpv audio-device string; "" = system default
    volume: int = 100          # 0–100

    def is_ready(self) -> bool:
        """True if this slot has at least one media file and is enabled."""
        return self.enabled and bool(self.video_path or self.audio_path)


@dataclass
class Session:
    version: int = 1
    name: str = "Untitled Session"
    slots: list[SlotConfig] = field(
        default_factory=lambda: [SlotConfig() for _ in range(3)]
    )

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "name": self.name,
            "slots": [asdict(s) for s in self.slots],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        raw_slots = data.get("slots", [])
        slots: list[SlotConfig] = []
        for raw in raw_slots:
            # Tolerate missing keys from older versions
            slots.append(SlotConfig(**{k: v for k, v in raw.items() if k in SlotConfig.__dataclass_fields__}))
        while len(slots) < 3:
            slots.append(SlotConfig())
        return cls(
            version=data.get("version", 1),
            name=data.get("name", "Untitled Session"),
            slots=slots[:3],
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "Session":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    # ── Recent sessions list ──────────────────────────────────────────────────

    _RECENT_PATH = os.path.join(
        os.path.expanduser("~"), ".forgeplayer", "recent_sessions.json"
    )
    _MAX_RECENT = 10

    @classmethod
    def add_recent(cls, path: str) -> None:
        recent = cls.load_recent()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[: cls._MAX_RECENT]
        os.makedirs(os.path.dirname(cls._RECENT_PATH), exist_ok=True)
        with open(cls._RECENT_PATH, "w", encoding="utf-8") as fh:
            json.dump(recent, fh, indent=2)

    @classmethod
    def load_recent(cls) -> list[str]:
        try:
            with open(cls._RECENT_PATH, encoding="utf-8") as fh:
                paths: list[str] = json.load(fh)
            # Filter out paths that no longer exist
            return [p for p in paths if os.path.isfile(p)]
        except Exception:
            return []
