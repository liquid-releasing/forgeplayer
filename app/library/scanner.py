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
from typing import TYPE_CHECKING

from app.library.channels import classify_funscript_channel

if TYPE_CHECKING:  # annotations only — avoids a package-init import cycle
    from app.recognizer.cluster import TitleCluster


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

# FunscriptForge export OUTPUTS — a `<stem>.output/` (device-organized folders)
# or a `<stem>.forge` / `<stem>.forgeplay` bundle — are things WE produced, not
# source scenes. The raw scanner makes broken cards from them: no video to
# relink (only the bundle importer does that), and a "stim"-ish name pulled from
# the e-stim content. They open via `bundle_importer` (double-click / Open), so
# the library walk skips them. (`.forge` ZIP *files* are already ignored — only
# media/funscript/audio extensions are scanned.)
_EXPORT_BUNDLE_SUFFIXES = (".output", ".forge", ".forgeplay")


def _is_export_bundle_dir(name: str) -> bool:
    return name.lower().endswith(_EXPORT_BUNDLE_SUFFIXES)


# When a scene folder carries its haptics inside an export bundle (rather than
# as loose funscripts), we record the bundle on the entry so activation can
# import it. If several are present, prefer the richest/most-canonical form.
_BUNDLE_SUFFIX_PRIORITY = (
    (".forge", 3),       # canonical self-contained bundle (zip file or dir)
    (".forgeplay", 2),
    (".output", 1),      # loose device-organized output folder
)


def _bundle_priority(name: str) -> int:
    """Higher wins; 0 = not a bundle name. The hidden flatten subfolder named
    exactly `.forge` is NOT a bundle — callers must exclude it first."""
    low = name.lower()
    for sfx, prio in _BUNDLE_SUFFIX_PRIORITY:
        if low.endswith(sfx):
            return prio
    return 0

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

    # Collect file paths from the scene folder and any `.forge` subfolder.
    # Alongside, spot a FunscriptForge export bundle (`<stem>.forge` zip/dir or
    # `<stem>.output/` folder) — its contents are packaged, not loose, so the
    # rest of the scan won't see its funscripts. We record the best one on
    # `entry.bundle_path` for lazy import at activation time.
    all_files: list[Path] = []
    best_bundle: str | None = None
    best_bundle_prio = 0
    try:
        for item in sorted(folder_path.iterdir()):
            if item.is_file():
                all_files.append(item)
                # `.forge` / `.forgeplay` zip FILES are bundles (`.output` is
                # a folder form, handled in the dir branch).
                prio = _bundle_priority(item.name)
                if prio >= 2 and prio > best_bundle_prio:
                    best_bundle, best_bundle_prio = str(item), prio
            elif item.is_dir() and item.name == _FORGE_FLATTEN_SUBFOLDER:
                # Flatten .forge contents as additional scene files
                try:
                    for sub in sorted(item.iterdir()):
                        if sub.is_file():
                            all_files.append(sub)
                except OSError:
                    pass
            elif item.is_dir():
                # Only a `<stem>.output/` FOLDER is a usable export bundle.
                # FunscriptForge WORKING dirs are `.<stem>.forge/` (dot-prefixed,
                # hidden) — internal editor state, NOT distribution output — so
                # they must never be played. And `.forge`/`.forgeplay` bundles
                # are ZIP FILES (handled in the is_file branch above); a `.forge`
                # DIRECTORY is a working dir, not a bundle. So: skip hidden dirs,
                # and only accept a non-hidden `.output` folder here.
                if item.name.startswith("."):
                    continue
                if item.name.lower().endswith(".output"):
                    prio = _bundle_priority(item.name)
                    if prio and prio > best_bundle_prio:
                        best_bundle, best_bundle_prio = str(item), prio
    except OSError:
        return None

    entry.bundle_path = best_bundle

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


# ── Multi-title scan (recognizer-backed) ──────────────────────────────────────
#
# The classic `scan_scene_folder` above lumps a whole folder into ONE scene —
# correct when a folder holds one work in several renderings, wrong when it holds
# two distinct works (Magik Vol 1 + Vol 2). `scan_scene_titles` runs the media
# recognizer over the folder's files and emits ONE entry per detected TITLE, so
# the Library shows a card per work. The two single-entry callers (drag-drop a
# folder, find-a-playing-video's-scripts) keep using `scan_scene_folder`.

# Immediate subfolders whose NAME starts with "." are hidden/working dirs
# (`.<stem>.forge/`, `.pre_screech_backup`) — never descend into or gather from
# them (user rule 2026-07-11, feedback_recognizer_skip_dot_folders).


def _is_funscript_subfolder(d: Path) -> bool:
    """A subfolder that holds funscripts but NO video is a scripts sidecar whose
    contents belong to the parent scene (the 'funscripts live in their own
    folder' layout). A subfolder WITH a video is its own scene — left alone."""
    has_fs = has_vid = False
    try:
        for f in d.iterdir():
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext == FUNSCRIPT_EXT:
                has_fs = True
            elif ext in VIDEO_EXTS:
                has_vid = True
                break
    except OSError:
        return False
    return has_fs and not has_vid


def _gather_scene_files(folder_path: Path) -> list[Path]:
    """Collect the paths the recognizer should classify for this scene folder.

    - Top-level files (videos, funscripts, audio, subtitles, `.forge` bundles…).
    - `<stem>.output` export FOLDERS, passed through as bundle items (the
      recognizer classifies them by stem into their title).
    - Funscripts from any non-hidden scripts-only subfolder (cross-folder
      gather), skipping deeper hidden folders.
    Hidden (dot-prefixed) subfolders are never entered.
    """
    files: list[Path] = []
    try:
        for item in sorted(folder_path.iterdir()):
            name = item.name
            if item.is_file():
                files.append(item)
            elif item.is_dir():
                if name.startswith("."):
                    continue  # hidden/working dir — never descend (user rule)
                if name.lower().endswith(".output"):
                    files.append(item)  # export bundle folder → BUNDLE role
                    continue
                if _is_funscript_subfolder(item):
                    for sub in sorted(item.rglob("*.funscript")):
                        rel = sub.relative_to(item).parts[:-1]
                        if any(p.startswith(".") for p in rel):
                            continue
                        files.append(sub)
    except OSError:
        pass
    if len(files) > _MAX_FILES_PER_SCENE:
        files = files[:_MAX_FILES_PER_SCENE]
    return files


def _title_to_entry(title: TitleCluster, folder_path: Path) -> SceneCatalogEntry:
    """Map one recognized TITLE onto the SceneCatalogEntry the UI/activation
    consume. Reuses the classic scanner's audio/stem helpers so behavior matches
    the single-title path."""
    entry = SceneCatalogEntry(folder_path=str(folder_path), name=title.display_name)

    # Videos — already ordered best-default-first by the recognizer.
    video_base_stems: set[str] = set()
    for v in title.videos:
        entry.videos.append(VideoVariant(path=v.path, tags=frozenset(v.variant_tags)))
        video_base_stems.add(_video_base_stem(Path(v.path).stem))

    # Funscript sets — group the title's funscripts by base stem (edit-variants
    # become separate sets, same as the classic path).
    sets_by_stem: dict[str, FunscriptSet] = {}
    for f in title.funscripts:
        info = f.channel_info or classify_funscript_channel(Path(f.path).name)
        fset = sets_by_stem.get(info.base_stem)
        if fset is None:
            fset = FunscriptSet(base_stem=info.base_stem)
            sets_by_stem[info.base_stem] = fset
        if info.channel == "":
            if not fset.main_path:
                fset.main_path = f.path
        else:
            fset.channels[info.channel] = f.path

    def _set_sort_key(fset: FunscriptSet) -> tuple:
        stem_lower = fset.base_stem.lower()
        matches_video = any(stem_lower == v for v in (vs.lower() for vs in video_base_stems))
        return (0 if matches_video else 1, len(fset.base_stem), stem_lower)

    entry.funscript_sets = sorted(sets_by_stem.values(), key=_set_sort_key)

    # Audio — stem-matched first (reuses the classic descriptor logic).
    for a in title.audio:
        descriptor, matches = _audio_descriptor(Path(a.path).stem, video_base_stems)
        entry.audio_tracks.append(AudioVariant(
            path=a.path, stem_matches_main_video=matches, descriptor=descriptor,
        ))
    entry.audio_tracks.sort(
        key=lambda a: (0 if a.stem_matches_main_video else 1, a.filename.lower())
    )

    # Subtitles / archives / preset.
    for s in title.subtitles:
        entry.subtitles.append(SubtitleTrack(
            path=s.path, language=_extract_subtitle_language(Path(s.path).stem),
        ))
    for arc in title.archives:
        entry.archives.append(arc.path)
    if title.presets:
        entry.preset_path = title.presets[0].path

    # Bundle — a `.forge`/`.forgeplay`/`.output` that clustered into this title.
    # The best (most canonical) one wins if several are present.
    if title.bundles:
        best = max(title.bundles, key=lambda b: _bundle_priority(Path(b.path).name))
        entry.bundle_path = best.path

    return entry


def scan_scene_titles(folder: str | os.PathLike) -> list[SceneCatalogEntry]:
    """Scan one folder and return ONE entry per detected TITLE (empty if none
    playable). Multi-title aware — the Library's per-work cards come from here."""
    # Lazy import: the recognizer package pulls in app.library.channels, so
    # importing it at module top would close a package-init cycle
    # (app.library.__init__ → scanner → app.recognizer → app.library.channels).
    from app.recognizer import (
        canonicalize,
        cluster_files,
        consolidate_videos_by_duration,
        funscript_span_ms,
        probe_resolve,
        reconcile,
        scan_duration_ms,
    )

    folder_path = Path(folder).resolve()
    if not folder_path.is_dir():
        return []

    files = _gather_scene_files(folder_path)
    recs = [canonicalize(p) for p in files]
    titles = reconcile(cluster_files(recs))
    # Content only adjudicates when a name match was too weak to trust:
    #  - attach an orphan funscript to the video whose span it fits, then
    #  - fold sibling video-titles names couldn't relate but duration can
    #    (param-named renders). Both only probe on genuine ambiguity.
    titles = probe_resolve(
        titles, duration_of=scan_duration_ms, span_of=funscript_span_ms,
    )
    titles = consolidate_videos_by_duration(titles, duration_of=scan_duration_ms)

    entries: list[SceneCatalogEntry] = []
    for t in titles:
        if not t.is_playable:
            continue
        entry = _title_to_entry(t, folder_path)
        if entry.is_playable:
            entries.append(entry)

    # A folder that resolves to ONE work is named after the folder — the label
    # users expect, and what the classic single-entry scanner produced. Only a
    # genuine multi-title folder keeps the recognizer's per-work display names,
    # since one folder name can't label several works.
    if len(entries) == 1:
        entries[0].name = folder_path.name
    return entries


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
            if child.name.startswith("."):
                continue  # hidden/working dir — never scan (user rule)
            if _is_export_bundle_dir(child.name):
                continue  # standalone FSF export — opened via the importer

            child_titles = scan_scene_titles(child)
            if child_titles:
                scenes.extend(child_titles)
                has_subfolder_scenes = True

            # Level 3: subfolders-of-scene become their OWN scene cards. A
            # script-only subfolder was already folded into the parent's titles
            # (cross-folder gather) and yields nothing playable here, so there's
            # no double-count; a video-bearing subfolder is a nested scene.
            try:
                for grandchild in sorted(child.iterdir()):
                    if not grandchild.is_dir():
                        continue
                    if grandchild.name.startswith("."):
                        continue
                    if _is_export_bundle_dir(grandchild.name):
                        continue
                    if _is_funscript_subfolder(grandchild):
                        continue  # scripts already folded into the parent scene
                    for sub in scan_scene_titles(grandchild):
                        sub.name = f"{child.name} / {sub.name}"
                        scenes.append(sub)
                        has_subfolder_scenes = True
            except OSError:
                pass
    except OSError:
        pass

    # Root-as-dump (flat-dump use case) ONLY applies when the root has no scene
    # subfolders. If the user's library is "root contains many scene folders",
    # loose files at the root level are admin noise. When it IS a flat dump, the
    # recognizer splits it into one card per work (Magik Vol 1, Vol 2, …) rather
    # than one giant synthetic scene.
    if not has_subfolder_scenes:
        for i, entry in enumerate(scan_scene_titles(root_path)):
            scenes.insert(i, entry)

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
