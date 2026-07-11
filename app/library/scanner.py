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
from collections import Counter
from pathlib import Path

from app.library.catalog import (
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


def _is_companion_subfolder(d: Path) -> bool:
    """A subfolder that holds funscripts and/or audio but NO video — a sidecar
    whose scripts/audio belong to the parent scene: the 'funscripts live in
    their own folder' layout, or an estim-audio variants folder like
    'Clutch spicy'. A subfolder WITH a video is its own scene — left alone."""
    has_media = has_vid = False
    try:
        for f in d.rglob("*"):
            if not f.is_file():
                continue
            if any(p.startswith(".") for p in f.relative_to(d).parts):
                continue  # ignore hidden/working subdirs
            ext = f.suffix.lower()
            if ext in VIDEO_EXTS:
                has_vid = True
                break
            if ext == FUNSCRIPT_EXT or ext in AUDIO_EXTS:
                has_media = True
    except OSError:
        return False
    return has_media and not has_vid


# Subfolder names that mark a re-encode of the PARENT scene (handbrake condense,
# same timing) — its videos are extra renders of the parent work, not a new
# scene. Folded into the parent by name so they don't spawn a duplicate card.
_REENCODE_SUBFOLDER_NAMES = frozenset({"hb", "handbrake", "handbraked", "compressed"})


def _is_reencode_subfolder(d: Path) -> bool:
    """A subfolder holding VIDEO re-encodes of the parent scene — a folder named
    EXACTLY 'hb' / 'handbrake' / 'compressed'. Its videos fold into the parent
    as variant renders. Match must be exact: a whole scene folder like
    '_Klinik Industries Vi22 hb' merely ENDS in 'hb' and is NOT a re-encode
    subfolder (folding it would slurp a real scene into its parent)."""
    n = d.name.lower().strip()
    if n not in _REENCODE_SUBFOLDER_NAMES:
        return False
    try:
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
                return True
    except OSError:
        pass
    return False


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
                companion = _is_companion_subfolder(item)
                reencode = False if companion else _is_reencode_subfolder(item)
                if companion or reencode:
                    # Pull the sidecar's media into the parent scene so it folds
                    # onto the parent by name: funscripts + audio for a companion
                    # ('Clutch spicy' estim variants, scripts-in-own-folder), and
                    # ALSO video for a re-encode folder ('hb' handbrake renders).
                    for sub in sorted(item.rglob("*")):
                        if not sub.is_file():
                            continue
                        rel = sub.relative_to(item).parts[:-1]
                        if any(p.startswith(".") for p in rel):
                            continue
                        ext = sub.suffix.lower()
                        if ext == FUNSCRIPT_EXT or ext in AUDIO_EXTS:
                            files.append(sub)
                        elif reencode and ext in VIDEO_EXTS:
                            files.append(sub)
    except OSError:
        pass
    if len(files) > _MAX_FILES_PER_SCENE:
        files = files[:_MAX_FILES_PER_SCENE]
    return files


# ── Funscript-first card assembly ─────────────────────────────────────────────
#
# The card model (user 2026-07-11): "we are not trying to find standalone videos
# or audio files. we are trying to find the main video and its associated
# funscript and/or forge file to play." The HAPTIC ASSET drives the card — the
# video is found by name. Funscripts are cleanly named and almost always match
# their video's name, so we match on the (noise-stripped) base stem.

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _bundle_stem(name: str) -> str:
    """Strip the export-bundle suffix off a bundle name → its work stem
    ('Victoria.output' → 'Victoria', 'Oaks.forge' → 'Oaks')."""
    low = name.lower()
    for sfx, _prio in _BUNDLE_SUFFIX_PRIORITY:
        if low.endswith(sfx):
            return name[: -len(sfx)]
    return name


_ESTIM_AUDIO_RE = re.compile(r"(?i)(?<![a-z])(e[-_\s]?stim|stim)(?![a-z])")


def _is_estim_audio(name: str) -> bool:
    """A sound file that is ITSELF the haptic track (pre-rendered e-stim audio),
    not music. Only such audio may FORM a card for a video with no funscript /
    bundle. Everything else (music, beat tracks) merely folds into an existing
    card as an alternate-audio option, or is dropped."""
    return bool(_ESTIM_AUDIO_RE.search(name))


# ── Work-key extraction — reduce an encoder-tagged filename to its WORK name ────
#
# Real scene folders name their renders with heavy noise: 'Klinik Industries
# Vi22 Hq Chf3 Iris3 5120x1440.mkv', 'Clutch-X265-Rf20 1 Iris3.mkv'. The estim
# MP3 that goes with them ('Klinik Industries Vi22 - Triphase.mp3') shares only
# the WORK name. To pair them we strip everything that isn't the work: codec,
# resolution, upscaler, quality/source tags, all-noise bracket groups, and
# pipeline pass-numbers. Whatever name-ish tail remains on the asset (e.g.
# 'Triphase', 'ESTIM mild') is fine — matching tolerates it.

_NOISE_WORDS = frozenset({
    "hq", "hd", "hb", "hbs", "uhd", "hdr", "sdr", "handbrake", "handbraked",
    "x264", "x265", "h264", "h265", "hevc", "avc", "topaz", "proteus",
    "4k", "4k60", "4k30", "2k", "1440p", "1080p", "720p", "480p", "360p", "fhd",
    "ultrawide", "cropped", "crop", "sbs", "lrf", "lr", "tb", "vr",
    "rf", "apo", "chf", "iris", "rhea", "nyx", "ghq",
})
_NOISE_TOKEN_RE = re.compile(
    r"(?i)^(?:iris\d*|chf\d*|rhea\d*|nyx\d*|apo\d*|apf\d*|ghq\d*|rf\d+|crf\d+"
    r"|\d{3,4}p|\d{3,5}x\d{1,4}|\d{6,}|4k\d+)$"  # \d{3,4}p = any 720p/1080p/2160p
)
_TOKEN_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|[^\s._\-]+")

# Words that introduce a real ORDINAL — a number right after one is part of the
# work identity ('Part 1', 'Vol 2'), never a render pass-number, even when a
# resolution/codec token follows it ('Part 1 4K').
_ORDINAL_MARKERS = frozenset({
    "part", "pt", "vol", "volume", "ep", "episode", "sc", "scene", "chapter",
    "ch", "number", "no", "act", "day", "round", "session", "disc",
})


def _is_noise_token(tok: str) -> bool:
    t = tok.lower()
    return t in _NOISE_WORDS or bool(_NOISE_TOKEN_RE.match(t))


def _work_tokens(stem: str) -> list[str]:
    """WORK-name tokens of a filename stem — noise, bracket/paren annotations,
    and render pass-numbers removed.

    Bracket/paren groups (`[Supermassive 2022]`, `[ESTIM - DigitalParkingLot]`,
    `[E-Stim & Popper Edit]`) are ANNOTATIONS (studio/year, source, edit type),
    not the work identity — the same video and its estim MP3 usually carry
    DIFFERENT brackets, so keeping them would break the pairing. We drop them.
    A bare number adjacent to a render token is a pass-number ('Rf20 1 Iris3' →
    drop the 1); a number after an ordinal marker ('Number 3', 'Pt 1') is kept."""
    toks = _TOKEN_RE.findall(stem)
    kinds: list[str] = []
    for t in toks:
        if t[:1] in "[(":
            kinds.append("noise")           # bracket/paren annotation → drop
        elif _is_noise_token(t):
            kinds.append("noise")
        elif t.isdigit():
            kinds.append("num")
        else:
            kinds.append("name")
    for i, k in enumerate(kinds):
        if k == "num":
            prev_word = toks[i - 1].lower() if i > 0 else ""
            if prev_word in _ORDINAL_MARKERS:
                continue  # 'Part 1' / 'Vol 2' — a real ordinal, keep it
            left = kinds[i - 1] if i > 0 else None
            right = kinds[i + 1] if i + 1 < len(kinds) else None
            if left == "noise" or right == "noise":
                kinds[i] = "noise"
    return [toks[i] for i in range(len(toks)) if kinds[i] != "noise"]


def _work_key(stem: str) -> str:
    """Normalized WORK name for matching — noise stripped, lower-cased."""
    return _norm(" ".join(_work_tokens(stem)))


def _name_word_set(stem: str) -> frozenset[str]:
    """Set of ≥2-char alphanumeric words in the work name — for token-overlap
    matching when word ORDER differs ('Rlgl Joi Ch La Luna 3' vs 'RLGL La Luna
    3')."""
    out: set[str] = set()
    for t in _work_tokens(stem):
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            if len(w) >= 2:
                out.add(w)
    return frozenset(out)


def scan_scene_titles(
    folder: str | os.PathLike,
    *,
    name_single_by_folder: bool = True,
    include_standalone: bool = False,
) -> list[SceneCatalogEntry]:
    """Scan one folder → one SceneCatalogEntry per playable HAPTIC SCENE.

    With ``include_standalone=True`` the result ALSO contains standalone-video
    cards (``is_video_only=True``) for any video with no haptic asset — used by
    the library's 'Videos' / 'All' filters. Folder naming only ever keys off the
    HAPTIC scenes, so the curated view's labels are unaffected by them.

    Funscript-first. A card is a funscript SET (or a `.forge`/`.output` bundle,
    or a pre-rendered e-stim SOUND file) plus the video whose name it matches:

      - A funscript / bundle / e-stim sound finds its video by clean name match.
        Same-name renders of that video (4k + 1080p) collapse into the ONE card
        as a video-variant choice.
      - A video with NO matching haptic asset is NOT a card — source pieces,
        upscales, and unscripted clips never become tiles.
      - Two funscript SETS with different names → two cards (Magik Vol 1 and Vol
        2 are separate works, each with its own script).
      - Audio that isn't itself a haptic track folds into its video's card as an
        alternate-audio option; a sound matching no card is dropped (a stray
        beat track never becomes a tile).

    The Library is a launcher for haptic scenes — NOT a video catalog.
    """
    folder_path = Path(folder).resolve()
    if not folder_path.is_dir():
        return []

    files = _gather_scene_files(folder_path)

    # 1) Classify files.
    videos: list[VideoVariant] = []
    funscript_files: list[Path] = []
    audio_paths: list[Path] = []
    subtitles: list[SubtitleTrack] = []
    archives: list[str] = []
    preset_path: str | None = None
    bundles: list[tuple[str, int, str]] = []  # (path, priority, work stem)

    for path in files:
        name = path.name
        prio = _bundle_priority(name)
        if prio:
            bundles.append((str(path), prio, _bundle_stem(name)))
            continue
        ext = path.suffix.lower()
        if ext in VIDEO_EXTS:
            videos.append(VideoVariant(path=str(path), tags=_extract_video_tags(name)))
        elif ext == FUNSCRIPT_EXT:
            funscript_files.append(path)
        elif ext in AUDIO_EXTS:
            audio_paths.append(path)
        elif ext in SUBTITLE_EXTS:
            subtitles.append(SubtitleTrack(
                path=str(path), language=_extract_subtitle_language(path.stem)))
        elif ext in ARCHIVE_EXTS:
            archives.append(str(path))
        elif name.endswith(PRESET_EXT):
            preset_path = str(path)

    # 2) Video index by WORK key (encoder / resolution / upscaler noise stripped
    #    so an estim MP3 named for the plain work finds its noise-tagged video).
    videos_by_base: dict[str, list[VideoVariant]] = {}
    display_of: dict[str, str] = {}
    base_words: dict[str, frozenset[str]] = {}
    for v in videos:
        stem = Path(v.path).stem
        key = _work_key(stem) or _norm(stem)
        videos_by_base.setdefault(key, []).append(v)
        if key not in display_of:
            display_of[key] = " ".join(_work_tokens(stem)) or stem
            base_words[key] = _name_word_set(stem)
    video_base_stems = set(display_of.values())

    def _match_video(asset_stem: str) -> str | None:
        """The video this haptic asset (funscript / bundle / sound) belongs to,
        by WORK name (None if none). Exact work-key first; then a prefix where
        the asset is the work name plus a descriptive tail ('Klinik…Vi22 -
        Triphase', 'Magik [E-Stim Edit]') without crossing an ordinal boundary
        ('Magik 2' vs 'Magik'); then a conservative word-overlap fallback for
        word-order differences."""
        akey = _work_key(asset_stem)
        if akey in videos_by_base:
            return akey
        best: str | None = None
        for vb in videos_by_base:
            if akey.startswith(vb):
                tail = akey[len(vb):].lstrip(" ._-")
                if tail == "" or not tail[0].isdigit():
                    if best is None or len(vb) > len(best):
                        best = vb
        if best is not None:
            return best
        # Word-order fallback: the smaller work-word set is a subset of exactly
        # one video's words (both ≥2 words). Subset (not mere overlap) keeps
        # different ordinals apart ('…Pt 1' ⊄ '…Pt 2').
        aset = _name_word_set(asset_stem)
        if len(aset) < 2:
            return None
        hits = [vb for vb, vset in base_words.items()
                if len(vset) >= 2 and (aset <= vset or vset <= aset)]
        return hits[0] if len(hits) == 1 else None

    # 3) Funscripts → sets by base stem.
    sets_by_stem: dict[str, FunscriptSet] = {}
    for path in funscript_files:
        info = classify_funscript_channel(path.name)
        fset = sets_by_stem.get(info.base_stem)
        if fset is None:
            fset = FunscriptSet(base_stem=info.base_stem)
            sets_by_stem[info.base_stem] = fset
        if info.channel == "":
            if not fset.main_path:
                fset.main_path = str(path)
        else:
            fset.channels[info.channel] = str(path)

    # 4) Assemble cards, keyed by the video the haptic asset matches (or a
    #    synthetic key for a self-contained bundle with no loose video).
    cards: dict[str, dict] = {}
    order: list[str] = []

    def _card(key: str, name: str, video_key: str | None) -> dict:
        c = cards.get(key)
        if c is None:
            c = {"name": name, "video_key": video_key,
                 "sets": [], "audio": [], "bundle": None, "bundle_prio": 0}
            cards[key] = c
            order.append(key)
        return c

    # 4a) Funscript sets → their video. An orphan (no video) isn't a playable
    #     scene — funscripts find their movies; a homeless one is dropped.
    for fset in sets_by_stem.values():
        vk = _match_video(fset.base_stem)
        if vk is None:
            continue
        _card(vk, display_of[vk], vk)["sets"].append(fset)

    # 4b) Bundles → their video, else a standalone bundle card (opens via the
    #     importer — a `.forge`/`.output` is self-contained even with no loose
    #     video).
    for path, prio, stem in bundles:
        vk = _match_video(stem)
        if vk is not None:
            c = _card(vk, display_of[vk], vk)
        else:
            c = _card("bundle::" + _norm(stem), stem, None)
        if prio > c["bundle_prio"]:
            c["bundle"], c["bundle_prio"] = path, prio

    # 4c) Audio. A sound that matches a video by name is that video's haptic
    #     track: it folds into the video's card as an alternate track, or — when
    #     the video has no funscript/bundle — it IS the haptic asset and forms
    #     the card (many scenes ship as video + e-stim MP3, no funscript). A
    #     sound matching NO video is dropped (a stray beat track never tiles).
    def _distinctive_audio_match(stem: str) -> str | None:
        """Last-resort within-folder pairing for a sound whose video keeps an
        unstrippable encoder tag ('Mistressandcontrolbox-…Apf2' vs
        'MistressAndControlBox-ESTIM-v3'): attach to the UNIQUE video sharing a
        distinctive work-word (≥6 chars, or ≥2 shared words). The uniqueness
        guard keeps Vi22/Vi89-style siblings apart."""
        aset = _name_word_set(stem)
        cands = [vb for vb, vset in base_words.items()
                 if any(len(w) >= 6 for w in (aset & vset)) or len(aset & vset) >= 2]
        return cands[0] if len(cands) == 1 else None

    for path in audio_paths:
        descriptor, matches = _audio_descriptor(path.stem, video_base_stems)
        av = AudioVariant(path=str(path), stem_matches_main_video=matches,
                          descriptor=descriptor)
        vk = _match_video(path.stem) or _distinctive_audio_match(path.stem)
        if vk is None:
            continue
        if vk in cards:
            cards[vk]["audio"].append(av)
        else:
            _card(vk, display_of[vk], vk)["audio"].append(av)

    # 5) Materialize entries.
    def _set_sort_key(fset: FunscriptSet, vk: str | None) -> tuple:
        stem = _work_key(fset.base_stem)
        return (0 if stem == vk else 1, len(fset.base_stem), fset.base_stem.lower())

    entries: list[SceneCatalogEntry] = []
    for key in order:
        c = cards[key]
        vk = c["video_key"]
        vids = sorted(videos_by_base.get(vk, []), key=_video_sort_key) if vk else []
        sets = sorted(c["sets"], key=lambda f: _set_sort_key(f, vk))
        audio = sorted(c["audio"], key=lambda a: (
            0 if a.stem_matches_main_video else 1, a.filename.lower()))
        entry = SceneCatalogEntry(
            folder_path=str(folder_path), name=c["name"],
            videos=vids, funscript_sets=sets, audio_tracks=audio,
            subtitles=list(subtitles), archives=list(archives),
            preset_path=preset_path, bundle_path=c["bundle"],
        )
        if entry.is_playable:
            entries.append(entry)

    # A folder that resolves to ONE scene is named after the folder — the label
    # users expect. Exceptions keep the content-derived name: a genuine
    # multi-scene folder (one folder name can't label several works), and a
    # '_'-prefixed staging/container folder (e.g. '_forgeplayme' holding a loose
    # 'Prisoner.mp4' + its '.output') where the folder name isn't the work.
    # Folder naming keys off the HAPTIC scenes first — a lone haptic scene takes
    # the folder's name; standalone videos never displace it.
    haptic_count = len(entries)
    name_by_folder = name_single_by_folder and not folder_path.name.startswith("_")
    if name_by_folder and haptic_count == 1:
        entries[0].name = folder_path.name

    # Standalone-video cards: any video base not claimed by a haptic asset. Its
    # same-name renders collapse into the one card (video-variant choice).
    if include_standalone:
        for key, vlist in videos_by_base.items():
            if key in cards:
                continue  # already part of a haptic card
            vids = sorted(vlist, key=_video_sort_key)
            entries.append(SceneCatalogEntry(
                folder_path=str(folder_path), name=display_of[key],
                videos=vids, subtitles=list(subtitles), archives=list(archives),
                is_video_only=True,
            ))

    # A folder that is ONLY a single standalone video takes the folder name too
    # (no haptic scene competed for it).
    if name_by_folder and haptic_count == 0 and len(entries) == 1:
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

    def _split(entries):
        return ([e for e in entries if not e.is_video_only],
                [e for e in entries if e.is_video_only])

    try:
        for child in sorted(root_path.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith("."):
                continue  # hidden/working dir — never scan (user rule)
            if _is_export_bundle_dir(child.name):
                continue  # standalone FSF export — opened via the importer

            # Top-level scenes of this folder (loose media directly inside it).
            child_h, child_v = _split(scan_scene_titles(child, include_standalone=True))

            # Level 3: a nested subfolder can hold the scene (Clutch's videos in
            # a subfolder, the_unit's 'Edited'). A script/audio-only companion
            # was already folded into the parent, so skip those.
            grand: list[SceneCatalogEntry] = []
            try:
                for gc in sorted(child.iterdir()):
                    if not gc.is_dir() or gc.name.startswith("."):
                        continue
                    if _is_export_bundle_dir(gc.name) or _is_companion_subfolder(gc):
                        continue
                    if _is_reencode_subfolder(gc):
                        continue  # handbrake re-encodes already folded into parent
                    grand.extend(scan_scene_titles(gc, include_standalone=True))
            except OSError:
                pass
            grand_h, grand_v = _split(grand)

            # HAPTIC scenes drive the curated view's names. If the folder itself
            # is a haptic scene, nested haptic scenes read as belonging to it;
            # if the scene lives entirely in ONE subfolder, name it by the parent
            # folder (rough root naming: 'Clutch', not 'Clutch / hd').
            if child_h:
                scenes.extend(child_h)
                for s in grand_h:
                    s.name = f"{child.name} / {s.name}"
                scenes.extend(grand_h)
            elif len(grand_h) == 1:
                grand_h[0].name = child.name
                scenes.extend(grand_h)
            elif grand_h:
                for s in grand_h:
                    s.name = f"{child.name} / {s.name}"
                scenes.extend(grand_h)

            # Standalone-video cards ride along tagged (hidden by default view).
            # Prefix them with the subfolder name so they read as belonging to it
            # and don't look like bare duplicates of a root-level card of the same
            # work (user rule: include the subfolder name). Skip the prefix when
            # the card is already the folder's own name (a lone video folder).
            for s in child_v:
                if s.name != child.name:
                    s.name = f"{child.name} / {s.name}"
            scenes.extend(child_v)
            for s in grand_v:
                s.name = f"{child.name} / {s.name}"
            scenes.extend(grand_v)
    except OSError:
        pass

    # Loose files living directly in the root are their own scenes too. Under the
    # funscript-first model haptic loose works are no longer buried as "admin
    # noise" (Magik Number 3, ZerO game, …); loose unscripted videos ride along
    # as standalone-video cards. name_single_by_folder=False so a lone root work
    # keeps its own name rather than the root folder's.
    root_scenes = scan_scene_titles(
        root_path, name_single_by_folder=False, include_standalone=True)
    for i, entry in enumerate(root_scenes):
        scenes.insert(i, entry)

    # Disambiguate exact duplicate display names — the same work loose at root
    # AND inside a subfolder reads as two identical tiles. Qualify the
    # subfolder-originating card with its subfolder name; the root-level copy
    # keeps the bare name (user rule: include the subfolder name).
    name_counts = Counter(s.name for s in scenes)
    for s in scenes:
        if name_counts[s.name] <= 1:
            continue
        try:
            rel = Path(s.folder_path).relative_to(root_path)
        except ValueError:
            continue
        if not rel.parts or rel.parts == (".",):
            continue  # a root-level card keeps the bare name
        sub = rel.parts[0]
        if s.name != sub and not s.name.startswith(f"{sub} / "):
            s.name = f"{sub} / {s.name}"

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
