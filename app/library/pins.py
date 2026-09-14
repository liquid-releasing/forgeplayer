# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Pin persistence — auto-save the user's picker choices per scene.

Design in ``memory/project_forgeplayer_pin_persistence.md``:

- Every successful scene play writes a pin recording the user's picks.
- Subsequent plays look up the pin, skip the picker, jump straight to
  playback.
- Pins live in an app-owned folder, ``~/.forgeplayer/pins/``, keyed by
  scene folder path + scene name. They used to be written as sidecars
  *next to the user's media*, which was wrong on two counts:

  1. It littered media volumes the user doesn't want us writing to
     ("I don't want to get my media volume / directory structure filled
     with other stuff" — user report 2026-09-14).
  2. The sidecar's *filename* came from ``entry.name`` while its
     *location* was the scene folder, so repointing the library root
     could strand a pin under a name nothing looked up again.

  Keying on folder path **and** name is what makes this safe: one folder
  can hold several distinct works (``scan_scene_titles``), and they must
  not share a pin.

  The trade-off, taken deliberately: a pin no longer travels with the
  folder. Moving media to a new path forgets the picks. Pins cache picker
  choices, not content, so that costs one re-pick — cheaper than writing
  into someone's library.

- Legacy sidecars are still **read**, and migrated to the new location on
  first use, so nobody loses their picks.
- A global index in ``~/.forgeplayer/catalog.json`` maps scene folder
  paths → last-used pin, so the Library can fast-render pinned badges
  and "recently played" ordering without rescanning every folder.

This module intentionally owns **only file I/O + resolution**. The UI
layer (picker / Library panel / ControlWindow) decides when to call save
and when to load; this file doesn't care.
"""

from __future__ import annotations

import hashlib
import json
import os
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
from app.library.scanner import funscript_set_for_file


_CATALOG_PATH = Path.home() / ".forgeplayer" / "catalog.json"
_PINS_DIR = Path.home() / ".forgeplayer" / "pins"
_PIN_SUFFIX = ".forgeplayer.json"
_SANITIZE = re.compile(r'[<>:"/\\|?*]')


# ── Pin dataclass ────────────────────────────────────────────────────────────

@dataclass
class Pin:
    """The user's remembered choices for a single scene.

    Each pick is recorded twice, and both halves matter:

    - ``*_filename`` / ``funscript_set_stem`` — the basename or base stem,
      matched against the scene folder's own variants. This is what makes a
      pin survive the folder being moved or re-scanned.
    - ``*_path`` — the absolute path actually chosen. Required for anything
      picked with **Browse**, which can reach any directory on disk: a source
      outside the scene folder does not appear in ``entry``'s variants at all,
      so the basename has nothing to match and the pick would silently vanish
      on the next activation (user report 2026-09-14 — Browse "doesn't get
      loaded/accepted").

    ``resolve_pin`` tries the in-folder match first and falls back to the
    recorded path, so an in-folder pick keeps travelling with its folder while
    a browsed one still resolves.

    None means "no pick made for this dimension" (e.g. the scene has no
    subtitles, so ``subtitle_filename`` stays None). ``Pin.from_dict`` drops
    unknown keys, so a v1 pin (no ``*_path`` fields) loads unchanged.
    """

    version: int = 2
    scene_name: str = ""
    video_filename: Optional[str] = None
    audio_filename: Optional[str] = None
    funscript_set_stem: Optional[str] = None
    subtitle_filename: Optional[str] = None
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    funscript_set_path: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Pin":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── Path helpers ─────────────────────────────────────────────────────────────

def _scene_key(entry: SceneCatalogEntry) -> str:
    r"""Stable identity for a scene: its folder path AND its name.

    The name is not optional. ``scan_scene_titles`` can return several
    distinct works from a single folder, and keying on the folder alone would
    collapse them onto one shared pin — so two different works would overwrite
    each other's picks.

    Normalised with ``normcase``/``normpath`` so ``D:\Media\Scene`` and
    ``d:/media/scene`` are one scene on Windows rather than two.
    """
    folder = os.path.normcase(os.path.normpath(str(entry.folder_path)))
    raw = f"{folder}\x00{entry.name}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def pin_path_for(entry: SceneCatalogEntry) -> Path:
    """Where *entry*'s pin is written — inside the app's own folder, never in
    the user's media.

    The readable prefix is for a human opening ``~/.forgeplayer/pins/``; the
    hash is what actually identifies the scene. The name alone cannot: two
    libraries can each hold a "Scene 1".
    """
    safe = _SANITIZE.sub("_", entry.name).strip() or "scene"
    return _PINS_DIR / f"{safe[:60]}-{_scene_key(entry)}{_PIN_SUFFIX}"


def legacy_pin_path_for(entry: SceneCatalogEntry) -> Path:
    """Where pins were written before v0.1.23 — a sidecar next to the media.

    Still read (and migrated) so an existing library keeps its picks, but
    never written again.
    """
    safe = _SANITIZE.sub("_", entry.name).strip() or "scene"
    return Path(entry.folder_path) / f"{safe}{_PIN_SUFFIX}"


def has_pin(entry: SceneCatalogEntry) -> bool:
    """True if *entry* has a pin in either location — so the Library's pinned
    badge keeps showing for a scene whose sidecar hasn't been migrated yet."""
    return pin_path_for(entry).is_file() or legacy_pin_path_for(entry).is_file()


# ── Save / load a single pin ─────────────────────────────────────────────────

def save_pin(
    entry: SceneCatalogEntry,
    *,
    video: Optional[VideoVariant],
    audio: Optional[AudioVariant],
    funscript_set: Optional[FunscriptSet],
    subtitle: Optional[SubtitleTrack],
) -> Path:
    """Write the pin into the app's own pins folder and update the global
    catalog index. Returns the pin path on success.

    Also retires the scene's legacy sidecar, if it has one: the replacement is
    written first, and the old file is removed only once that has succeeded, so
    a failure anywhere leaves the user's picks readable from the old location.

    Failures to write the pin itself are not silent — the caller should catch
    and surface, since a failed save means the user's picks won't be
    remembered.
    """
    pin = Pin(
        scene_name=entry.name,
        video_filename=(Path(video.path).name if video else None),
        audio_filename=(Path(audio.path).name if audio else None),
        funscript_set_stem=(funscript_set.base_stem if funscript_set else None),
        subtitle_filename=(Path(subtitle.path).name if subtitle else None),
        video_path=(str(video.path) if video else None),
        audio_path=(str(audio.path) if audio else None),
        funscript_set_path=_representative_path(funscript_set),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    path = pin_path_for(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pin.to_dict(), indent=2), encoding="utf-8")
    _retire_legacy_sidecar(entry)
    _update_catalog(entry, path)
    return path


def _representative_path(funscript_set: Optional[FunscriptSet]) -> Optional[str]:
    """One concrete file that identifies a funscript set.

    A set is several files — a main track plus channels — but they share a
    folder, which is the part that lets the set be rebuilt later. Prefer the
    main track; fall back to a channel, because a set browsed in from outside
    the scene folder is often all channels and no main track (an e-stim export
    is the normal case, not an edge case).
    """
    if funscript_set is None:
        return None
    if funscript_set.main_path:
        return str(funscript_set.main_path)
    for _channel, cpath in sorted(funscript_set.channels.items()):
        if cpath:
            return str(cpath)
    return None


def _retire_legacy_sidecar(entry: SceneCatalogEntry) -> None:
    """Delete the old in-media sidecar once its replacement exists.

    Best-effort by design: a read-only or disconnected media volume must not
    break saving a pin. The data is not lost — it has already been written to
    the app-owned location by the time this runs.
    """
    legacy = legacy_pin_path_for(entry)
    try:
        if legacy.is_file():
            legacy.unlink()
    except OSError:
        pass


def load_pin(entry: SceneCatalogEntry) -> Optional[Pin]:
    """Read *entry*'s pin, preferring the app-owned location.

    Falls back to a legacy in-media sidecar and migrates it on the spot, so an
    existing library keeps every remembered pick without the user doing
    anything — and stops accumulating new sidecars.
    """
    pin = _read_pin_file(pin_path_for(entry))
    if pin is not None:
        return pin

    legacy = _read_pin_file(legacy_pin_path_for(entry))
    if legacy is None:
        return None
    try:
        target = pin_path_for(entry)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(legacy.to_dict(), indent=2), encoding="utf-8",
        )
        _retire_legacy_sidecar(entry)
    except OSError:
        # Migration is a convenience; the pick still resolves from what we
        # just read either way.
        pass
    return legacy


def _read_pin_file(path: Path) -> Optional[Pin]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
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
        if resolved.video is None and pin.video_path and os.path.isfile(pin.video_path):
            resolved.video = VideoVariant(path=pin.video_path)
        if resolved.video is None:
            resolved.stale_fields.append("video")

    if pin.audio_filename:
        resolved.audio = _find(entry.audio_tracks, lambda a: Path(a.path).name == pin.audio_filename)
        if resolved.audio is None and pin.audio_path and os.path.isfile(pin.audio_path):
            resolved.audio = AudioVariant(path=pin.audio_path)
        if resolved.audio is None:
            resolved.stale_fields.append("audio")

    if pin.funscript_set_stem:
        resolved.funscript_set = _find(
            entry.funscript_sets, lambda f: f.base_stem == pin.funscript_set_stem
        )
        if resolved.funscript_set is None and pin.funscript_set_path:
            # Nothing in the scene folder matches, which is the normal case for
            # a set the user reached with Browse — it lives somewhere else
            # entirely, so it was never scanned into `entry`. Rebuild it from
            # the recorded path, channel siblings and all, using the same
            # function Browse itself uses.
            resolved.funscript_set = funscript_set_for_file(pin.funscript_set_path)
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
