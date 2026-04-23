# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Scan a registered library root → list of SceneCatalogEntry.

Design decisions (locked 2026-04-23, see `project_forgeplayer_folder_heuristics.md`):

  1. Scan depth: 2 levels. Root (level 1) contains scene folders (level 2).
     Subfolders inside a scene (level 3) become separate scene cards, EXCEPT
     when the subfolder is named exactly `.forge` — those contents flatten
     into the parent scene as additional playable clips.

  2. Video variant default: highest resolution, prefer non-upscaled original.
     Aspect-variants (ultrawide, cropped) never default.

  3. Audio: list all candidates. Auto-pick when exactly one is stem-matched.
     Otherwise flag ambiguous → select picker will ask.

  4. Funscript sets: grouped by base stem. Multiple sets = edit-variants =
     ambiguous.

  5. Device generations computed per-set. Scene card badges show union of
     all sets' generations.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.library.catalog import (
    VIDEO_RESOLUTION_RANK,
    AudioVariant,
    FunscriptSet,
    SceneCatalogEntry,
    SubtitleTrack,
    VideoVariant,
)
from app.library.channels import classify_funscript_channel


# ── File-type extensions ──────────────────────────────────────────────────────

VIDEO_EXTS = frozenset({".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"})
AUDIO_EXTS = frozenset({".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus"})
SUBTITLE_EXTS = frozenset({".srt", ".ass", ".ssa", ".vtt"})
ARCHIVE_EXTS = frozenset({".zip", ".7z", ".rar"})
FUNSCRIPT_EXT = ".funscript"
PRESET_EXT = ".forgeplayer.json"

# Special subfolder name — contents flatten into the parent scene as additional
# playable clips (packaged album-style).
_FORGE_FLATTEN_SUBFOLDER = ".forge"

# Configurable limit so a malicious folder with millions of files doesn't hang
# the scanner. Scenes exceeding this cap are still scanned but over-cap items
# are skipped with a deterministic ordering.
_MAX_FILES_PER_SCENE = 10_000


# ── Filename-tag extraction (no ffprobe) ──────────────────────────────────────

# Filename-tag lookarounds use (?<![a-z]) / (?![a-z]) rather than \b because
# \b treats `_` as a word character — so `scene_iris3.mp4` would not match
# `\biris\d*\b`. Real-world filenames (Topaz outputs, etc.) use `_` heavily
# as separator, and we need to catch those.
_RESOLUTION_PATTERNS = [
    (re.compile(r"(?i)(?<![a-z])(4k60|4k30|4k)(?![a-z])"),  "4k"),
    (re.compile(r"(?i)(?<![a-z])(1440p|2k)(?![a-z])"),      "1440p"),
    (re.compile(r"(?i)(?<![a-z])(1080p|fhd|hd)(?![a-z])"),  "1080p"),
    (re.compile(r"(?i)(?<![a-z])(720p)(?![a-z])"),          "720p"),
    (re.compile(r"(?i)(?<![a-z])(480p)(?![a-z])"),          "480p"),
]
# Resolution preference ranks live in catalog.py (shared with VideoVariant.preference_tier)

_ASPECT_PATTERNS = [
    (re.compile(r"(?i)(?<![a-z])ultrawide(?![a-z])"),  "ultrawide"),
    (re.compile(r"(?i)(?<![a-z])cropped(?![a-z])"),    "cropped"),
    (re.compile(r"(?i)(?<![a-z])crop(?![a-z])"),       "cropped"),
]

_UPSCALER_PATTERNS = [
    (re.compile(r"(?i)(?<![a-z])iris\d*(?![a-z])"),    "iris"),
    (re.compile(r"(?i)(?<![a-z])chf\d*(?![a-z])"),     "chf"),
    (re.compile(r"(?i)(?<![a-z])topaz(?![a-z])"),      "topaz"),
    (re.compile(r"(?i)(?<![a-z])rhea(?![a-z])"),       "rhea"),
    (re.compile(r"(?i)(?<![a-z])proteus(?![a-z])"),    "proteus"),
    (re.compile(r"(?i)(?<![a-z])nyx\d*(?![a-z])"),     "nyx"),
]


def _extract_video_tags(filename: str) -> frozenset[str]:
    """Pull resolution, aspect, and upscaler tags out of a video filename."""
    tags: set[str] = set()
    for pattern, tag in _RESOLUTION_PATTERNS:
        if pattern.search(filename):
            tags.add(tag)
            break  # one resolution tag only (first-match wins)
    for pattern, tag in _ASPECT_PATTERNS:
        if pattern.search(filename):
            tags.add(tag)
    for pattern, tag in _UPSCALER_PATTERNS:
        if pattern.search(filename):
            tags.add(tag)
    return frozenset(tags)


def _video_sort_key(v: VideoVariant) -> tuple:
    """Sort key for video variants — lower is better (preferred default).

    Algorithm (from decision: highest resolution, prefer non-upscaled original):
      1. Non-aspect-variants before aspect-variants (ultrawide/cropped fall to end)
      2. Non-upscaled before upscaled (original 4K beats Topaz 4K)
      3. Highest resolution first (4k > 1440p > 1080p > ...)
      4. Alphabetical tiebreaker for determinism
    """
    # Preference tier handles aspect / upscale / resolution; alphabetical
    # tiebreaker keeps sort order deterministic when tiers match.
    return (*v.preference_tier, v.filename.lower())


# ── Subtitle language extraction ──────────────────────────────────────────────

_LANG_SUFFIX_PATTERN = re.compile(r"\.([a-z]{2,3})$", re.IGNORECASE)


def _extract_subtitle_language(stem: str) -> str:
    """Pull a language tag out of a subtitle stem like `scene.en` → `en`.

    Only accepts 2-3 letter ISO-ish codes. Returns 'unknown' otherwise.
    """
    match = _LANG_SUFFIX_PATTERN.search(stem)
    if match:
        return match.group(1).lower()
    return "unknown"


# ── Audio descriptor extraction ───────────────────────────────────────────────

def _audio_descriptor(audio_stem: str, video_base_stems: set[str]) -> tuple[str, bool]:
    """Given an audio file's stem, return (descriptor, stem_matches_main).

    Descriptor is the portion of the audio stem that doesn't match any video
    base stem — the 'extra' tail that distinguishes this audio (e.g. '_Emily's
    Audio', '-beats', '-estim-audio'). Empty string when the audio stem
    exactly matches a video base stem (stem_matches_main=True).
    """
    audio_stem_lower = audio_stem.lower()
    for vstem in video_base_stems:
        vstem_lower = vstem.lower()
        if audio_stem_lower == vstem_lower:
            return ("", True)
        if audio_stem_lower.startswith(vstem_lower):
            descriptor = audio_stem[len(vstem):].lstrip(" ._-")
            return (descriptor, False)
    # No video-base-stem prefix → the audio is fully mismatched
    return (audio_stem, False)


# ── Core scanner ──────────────────────────────────────────────────────────────

def scan_scene_folder(folder: str | os.PathLike) -> SceneCatalogEntry | None:
    """Scan one folder as a scene and return its catalog entry.

    Returns None when the folder contains no playable content (no video AND
    no funscript). `.forge/` subfolder contents are flattened into the parent.

    The caller is responsible for only passing level-2 folders (under a
    registered library root) — see `scan_library_root` for the walk.
    """
    folder_path = Path(folder).resolve()
    if not folder_path.is_dir():
        return None

    entry = SceneCatalogEntry(
        folder_path=str(folder_path),
        name=folder_path.name,
    )

    # Collect file paths from the scene folder and any `.forge` subfolder
    all_files: list[Path] = []
    try:
        for item in sorted(folder_path.iterdir()):
            if item.is_file():
                all_files.append(item)
            elif item.is_dir() and item.name == _FORGE_FLATTEN_SUBFOLDER:
                # Flatten .forge contents as additional scene files
                try:
                    for sub in sorted(item.iterdir()):
                        if sub.is_file():
                            all_files.append(sub)
                except OSError:
                    pass
    except OSError:
        return None

    if len(all_files) > _MAX_FILES_PER_SCENE:
        all_files = all_files[:_MAX_FILES_PER_SCENE]

    # First pass: classify videos and collect their base stems for audio matching
    video_base_stems: set[str] = set()
    funscript_files: list[Path] = []

    for path in all_files:
        ext = path.suffix.lower()

        if ext in VIDEO_EXTS:
            tags = _extract_video_tags(path.name)
            entry.videos.append(VideoVariant(path=str(path), tags=tags))
            # For audio stem matching, strip resolution/aspect/upscaler tokens
            # from the video stem to get the "scene base".
            video_base_stems.add(_video_base_stem(path.stem))

        elif ext == FUNSCRIPT_EXT:
            funscript_files.append(path)

        elif ext in SUBTITLE_EXTS:
            entry.subtitles.append(SubtitleTrack(
                path=str(path),
                language=_extract_subtitle_language(path.stem),
            ))

        elif ext in ARCHIVE_EXTS:
            entry.archives.append(str(path))

        elif path.name.endswith(PRESET_EXT):
            entry.preset_path = str(path)

    # Sort videos by default-preference
    entry.videos.sort(key=_video_sort_key)

    # Second pass: audio files, using the collected video stems
    for path in all_files:
        if path.suffix.lower() in AUDIO_EXTS:
            descriptor, matches = _audio_descriptor(path.stem, video_base_stems)
            entry.audio_tracks.append(AudioVariant(
                path=str(path),
                stem_matches_main_video=matches,
                descriptor=descriptor,
            ))

    # Sort audio: stem-matched first, then alphabetical within each group
    entry.audio_tracks.sort(key=lambda a: (0 if a.stem_matches_main_video else 1, a.filename.lower()))

    # Group funscripts into sets by base stem
    sets_by_stem: dict[str, FunscriptSet] = {}
    for path in funscript_files:
        info = classify_funscript_channel(path.name)
        fset = sets_by_stem.get(info.base_stem)
        if fset is None:
            fset = FunscriptSet(base_stem=info.base_stem)
            sets_by_stem[info.base_stem] = fset

        if info.channel == "":
            fset.main_path = str(path)
        else:
            fset.channels[info.channel] = str(path)

    # Sort sets: the set whose base stem best matches a video base stem wins;
    # ties break alphabetically. This way the "plain" Magik set sorts before
    # the "Magik [E-Stim & Popper Edit]" set — the scanner's default-pick is
    # the shorter / original-name one.
    def _set_sort_key(fset: FunscriptSet) -> tuple:
        stem_lower = fset.base_stem.lower()
        matches_video = any(stem_lower == v for v in (vs.lower() for vs in video_base_stems))
        # Shorter stems first (usually the non-edit original), then matches-video,
        # then alphabetical.
        return (
            0 if matches_video else 1,
            len(fset.base_stem),
            fset.base_stem.lower(),
        )

    entry.funscript_sets = sorted(sets_by_stem.values(), key=_set_sort_key)

    # Drop empty scenes
    if not entry.is_playable:
        return None

    return entry


def scan_library_root(root: str | os.PathLike) -> list[SceneCatalogEntry]:
    """Walk a registered library root to find scene folders.

    Level 1 = root itself.
    Level 2 = immediate subdirectories of root → candidate scene folders.
    Level 3 = subdirectories of scene folders → each becomes its OWN scene
              card, EXCEPT for `.forge` subfolders which get flattened into
              the parent scene (handled by scan_scene_folder).

    Returns only playable scenes (those with at least one video + one funscript
    set).

    Level-1 files living directly in the root are also scanned as a 'virtual'
    scene named after the root folder — supports the flat-dump use case where
    the user drops everything into one folder.
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        return []

    scenes: list[SceneCatalogEntry] = []
    has_subfolder_scenes = False

    try:
        for child in sorted(root_path.iterdir()):
            if not child.is_dir():
                continue
            if child.name == _FORGE_FLATTEN_SUBFOLDER:
                continue  # reserved for flat-dump semantics

            scene = scan_scene_folder(child)
            if scene is not None:
                scenes.append(scene)
                has_subfolder_scenes = True

            # Level 3: subfolders-of-scene become their own scene cards
            # (but only if the subfolder itself contains playable content,
            # not .forge, and not a duplicate of an already-scanned parent)
            try:
                for grandchild in sorted(child.iterdir()):
                    if (
                        grandchild.is_dir()
                        and grandchild.name != _FORGE_FLATTEN_SUBFOLDER
                    ):
                        sub_scene = scan_scene_folder(grandchild)
                        if sub_scene is not None:
                            # Disambiguate name with parent prefix for UI clarity
                            sub_scene.name = f"{child.name} / {grandchild.name}"
                            scenes.append(sub_scene)
            except OSError:
                pass
    except OSError:
        pass

    # Root-as-scene (flat-dump use case) ONLY applies when the root has no
    # scene subfolders. If the user's library is "root contains many scene
    # folders", loose files at the root level are admin noise — don't lump
    # them into one giant synthetic scene.
    if not has_subfolder_scenes:
        root_as_scene = scan_scene_folder(root_path)
        if root_as_scene is not None:
            scenes.insert(0, root_as_scene)

    return scenes


# ── Helper: strip variant tokens from a video stem to get the scene base ──────

_VIDEO_STEM_NOISE = re.compile(
    r"(?i)"
    r"[\s._-]*"
    r"(?:"
    r"4k60|4k30|4k|1440p|2k|1080p|fhd|720p|480p"
    r"|ultrawide|cropped|crop"
    r"|iris\d*|chf\d*|topaz|rhea|proteus|nyx\d*"
    r")"
)


def _video_base_stem(filename_stem: str) -> str:
    """Strip resolution/aspect/upscaler tokens off a video filename stem.

    Examples:
      'Euphoria.4k60'                  → 'Euphoria'
      'Magik Pt 1_chf3_iris3 ultrawide' → 'Magik Pt 1'
      'aSinfull-XXX-cropped-4k'        → 'aSinfull-XXX'

    Used only for audio stem matching — NOT for display. Best-effort; when in
    doubt, returns the original stem unchanged.
    """
    cleaned = filename_stem
    # Run the noise pattern repeatedly to strip all tokens
    for _ in range(8):
        new = _VIDEO_STEM_NOISE.sub("", cleaned).strip(" ._-")
        if new == cleaned:
            break
        cleaned = new
    return cleaned or filename_stem
