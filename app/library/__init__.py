# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""ForgePlayer library subsystem.

Public API:

- `scan_library_root(root)` — walk a registered root folder, return scene entries
- `scan_scene_folder(folder)` — classify one folder as a scene (or None if not one)
- `SceneCatalogEntry` — the per-scene classification result
- `DeviceGeneration` — the device-generation taxonomy
"""

from app.library.catalog import (
    SceneCatalogEntry,
    VideoVariant,
    AudioVariant,
    FunscriptSet,
    SubtitleTrack,
)
from app.library.channels import DeviceGeneration, classify_funscript_channel
from app.library.scanner import scan_library_root, scan_scene_folder

__all__ = [
    "DeviceGeneration",
    "SceneCatalogEntry",
    "VideoVariant",
    "AudioVariant",
    "FunscriptSet",
    "SubtitleTrack",
    "classify_funscript_channel",
    "scan_library_root",
    "scan_scene_folder",
]
