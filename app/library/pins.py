# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Pin persistence — auto-save the user's picker choices per scene.

Design in ``memory/project_forgeplayer_pin_persistence.md``:

- Every successful scene play writes a pin file next to the scene's media.
- Subsequent plays look up the pin, skip the picker, jump straight to
  playback.
- Pin filenames stay scene-folder-relative so moving the folder doesn't
  invalidate the pin.
- A global index in ``~/.forgeplayer/catalog.json`` maps scene folder
  paths → last-used pin, so the Library can fast-render pinned badges
  and "recently played" ordering without rescanning every folder.

This module intentionally owns **only file I/O + resolution**. The UI
layer (picker / Library panel / ControlWindow) decides when to call save
and when to load; this file doesn't care.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.library.catalog import (
    AudioVariant,
    FunscriptSet,
    SceneCatalogEntry,
    SubtitleTrack,
    VideoVariant,
)


_CATALOG_PATH = Path.home() / ".forgeplayer" / "catalog.json"
_PIN_SUFFIX = ".forgeplayer.json"
_SANITIZE = re.compile(r'[<>:"/\\|?*]')


# ── Pin dataclass ────────────────────────────────────────────────────────────

@dataclass
class Pin:
    """The user's remembered choices for a single scene.

    All ``*_filename`` fields are basenames relative to the scene folder.
    None means "no pick made for this dimension" (e.g. the scene has no
    subtitles, so ``subtitle_filename`` stays None).
    """

    version: int = 1
    scene_name: str = ""
    video_filename: Optional[str] = None
    audio_filename: Optional[str] = None
    funscript_set_stem: Optional[str] = None
    subtitle_filename: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Pin":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── Path helpers ─────────────────────────────────────────────────────────────

def pin_path_for(entry: SceneCatalogEntry) -> Path:
    """Location of the pin file for *entry* — sits next to its media."""
    safe = _SANITIZE.sub("_", entry.name).strip() or "scene"
    return Path(entry.folder_path) / f"{safe}{_PIN_SUFFIX}"


def has_pin(entry: SceneCatalogEntry) -> bool:
    return pin_path_for(entry).is_file()


# ── Save / load a single pin ─────────────────────────────────────────────────

def save_pin(
    entry: SceneCatalogEntry,
    *,
    video: Optional[VideoVariant],
    audio: Optional[AudioVariant],
    funscript_set: Optional[FunscriptSet],
    subtitle: Optional[SubtitleTrack],
) -> Path:
    """Write the pin file next to the scene's media and update the global
    catalog index. Returns the pin path on success.

    Failures are not silent — the caller should catch and surface, since a
    failed save means the user's picks won't be remembered.
    """
    pin = Pin(
        scene_name=entry.name,
        video_filename=(Path(video.path).name if video else None),
        audio_filename=(Path(audio.path).name if audio else None),
        funscript_set_stem=(funscript_set.base_stem if funscript_set else None),
        subtitle_filename=(Path(subtitle.path).name if subtitle else None),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    path = pin_path_for(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pin.to_dict(), indent=2), encoding="utf-8")
    _update_catalog(entry, path)
    return path


def load_pin(entry: SceneCatalogEntry) -> Optional[Pin]:
    """Read the pin file for *entry* if present and well-formed."""
    path = pin_path_for(entry)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return Pin.from_dict(data)


# ── Resolve a pin back to concrete scene objects ────────────────────────────

@dataclass
class ResolvedPin:
    """Pin fields matched to the current `SceneCatalogEntry`'s variants.

    When the user added or renamed a file since the pin was written, some
    fields may be None even though the pin referenced a filename — callers
    use ``is_stale`` to fall back to the picker in that case.
    """

    video: Optional[VideoVariant] = None
    audio: Optional[AudioVariant] = None
    funscript_set: Optional[FunscriptSet] = None
    subtitle: Optional[SubtitleTrack] = None
    stale_fields: list[str] = field(default_factory=list)

    @property
    def is_stale(self) -> bool:
        return bool(self.stale_fields)


def resolve_pin(entry: SceneCatalogEntry, pin: Pin) -> ResolvedPin:
    """Walk the pin's filename references and map them to *entry*'s variants.

    If a referenced file no longer exists, that field becomes stale. The
    caller decides whether a partial match is usable or whether to fall
    back to the picker."""
    resolved = ResolvedPin()

    if pin.video_filename:
        resolved.video = _find(entry.videos, lambda v: Path(v.path).name == pin.video_filename)
        if resolved.video is None:
            resolved.stale_fields.append("video")

    if pin.audio_filename:
        resolved.audio = _find(entry.audio_tracks, lambda a: Path(a.path).name == pin.audio_filename)
        if resolved.audio is None:
            resolved.stale_fields.append("audio")

    if pin.funscript_set_stem:
        resolved.funscript_set = _find(
            entry.funscript_sets, lambda f: f.base_stem == pin.funscript_set_stem
        )
        if resolved.funscript_set is None:
            resolved.stale_fields.append("funscript_set")

    if pin.subtitle_filename:
        resolved.subtitle = _find(entry.subtitles, lambda s: Path(s.path).name == pin.subtitle_filename)
        if resolved.subtitle is None:
            resolved.stale_fields.append("subtitle")

    return resolved


def _find(items, predicate):
    for item in items:
        if predicate(item):
            return item
    return None


# ── Global catalog index ────────────────────────────────────────────────────

def load_catalog() -> dict:
    try:
        return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "pins": {}}


def _update_catalog(entry: SceneCatalogEntry, pin_file_path: Path) -> None:
    """Record that this scene has a pin, with a fresh last-played timestamp.
    Best-effort — a catalog write failure shouldn't prevent saving the pin
    itself."""
    try:
        catalog = load_catalog()
        pins = catalog.setdefault("pins", {})
        pins[str(Path(entry.folder_path))] = {
            "pin_file": pin_file_path.name,
            "scene_name": entry.name,
            "last_played": datetime.now().isoformat(timespec="seconds"),
        }
        _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CATALOG_PATH.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    except Exception:
        pass


def catalog_path() -> Path:
    return _CATALOG_PATH
