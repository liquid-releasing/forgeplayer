# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Catalog dataclasses — what the scanner emits per scene folder.

A `SceneCatalogEntry` is the classification of one scene folder. It contains:
  - Detected video variants (possibly multiple: 4K original, Topaz-upscaled, ultrawide-cropped, etc.)
  - Detected audio tracks (possibly multiple with mismatched stems)
  - Detected funscript sets (possibly multiple when a folder has edit-variants)
  - Detected subtitles
  - Detected per-scene preset JSON
  - Computed device-generation support
  - Computed ambiguity flag (true → select picker must appear)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.library.channels import DeviceGeneration


# Resolution preference ranks — lower is better. Used by VideoVariant
# ordering and by the ambiguity check to decide when two variants are
# "equally valid" defaults.
VIDEO_RESOLUTION_RANK: dict[str, int] = {
    "4k": 0,
    "1440p": 1,
    "1080p": 2,
    "720p": 3,
    "480p": 4,
}


@dataclass(frozen=True)
class VideoVariant:
    """One video file in a scene folder, classified by filename tags.

    Filename-tag parsing is best-effort and fast (no ffprobe). The `tags`
    field captures human-readable hints like '4k60', 'ultrawide', 'iris3'
    for UI badging and for the default-variant picker algorithm.
    """
    path: str
    tags: frozenset[str] = frozenset()
    """Lower-case normalized tags extracted from the filename: resolution
    ('1080p', '4k60'), aspect ('ultrawide', 'cropped'), upscaler ('iris3',
    'chf3', 'topaz', 'rhea')."""

    @property
    def filename(self) -> str:
        return Path(self.path).name

    @property
    def is_upscaled(self) -> bool:
        return bool(self.tags & {"iris", "iris3", "chf", "chf3", "topaz", "rhea", "proteus", "nyx"})

    @property
    def is_aspect_variant(self) -> bool:
        """True for ultrawide-cropped or otherwise aspect-remapped variants."""
        return bool(self.tags & {"ultrawide", "cropped"})

    @property
    def preference_tier(self) -> tuple[int, int, int]:
        """Tuple identifying this variant's default-pick tier (lower is
        preferred). Two variants with the same tier are genuinely
        interchangeable defaults and their coexistence is what triggers
        scene ambiguity — not mere file multiplicity.

        Order: (is_aspect_variant, is_upscaled, resolution_rank).
        """
        res_rank = 99
        for tag in self.tags:
            if tag in VIDEO_RESOLUTION_RANK:
                res_rank = min(res_rank, VIDEO_RESOLUTION_RANK[tag])
        return (int(self.is_aspect_variant), int(self.is_upscaled), res_rank)


@dataclass(frozen=True)
class AudioVariant:
    """One audio file in a scene folder. Stem-match to the scene's main video
    is recorded so the select picker can surface mismatched-stem tracks
    ('alternate audio' from a different contributor, etc.)."""
    path: str
    stem_matches_main_video: bool = False
    descriptor: str = ""
    """Human-readable hint extracted from the filename — the tail after the
    main stem, if any. Examples: '_Emily's Audio', '-beats', '-estim-audio',
    'By Fb'. Empty string if the filename is just the scene stem."""

    @property
    def filename(self) -> str:
        return Path(self.path).name


@dataclass
class FunscriptSet:
    """One group of funscripts sharing the same base stem.

    A scene folder commonly has ONE set. Folders with edit-variants (like
    Magik's original vs `[E-Stim & Popper Edit]`) have two or more sets.
    Each set maps channel name → funscript file path.

    The `main_path` is the base `.funscript` (no channel suffix) if present.
    The `channels` dict holds every other channel variant, keyed by channel
    name (e.g. `'alpha'`, `'pulse_frequency'`, `'alpha-prostate'`).
    """
    base_stem: str
    main_path: str | None = None
    channels: dict[str, str] = field(default_factory=dict)
    """Channel name → file path. Channel name is the suffix without the
    leading dot, e.g. 'alpha', 'beta', 'pulse_frequency', 'alpha-prostate'."""

    @property
    def has_prostate(self) -> bool:
        return any(ch.endswith("-prostate") for ch in self.channels)

    @property
    def has_generation_variants(self) -> bool:
        """True when the set contains generation-modifier-suffixed channels
        (-2b / -stereostim / -foc-stim). These mark the scripter's explicit
        per-generation variants and trigger scene ambiguity — the user may
        need to pick which generation's encoding to use at select time."""
        from app.library.channels import has_generation_variants
        return has_generation_variants(set(self.channels))

    @property
    def all_channels(self) -> set[str]:
        """Every channel name present, including '' for the main funscript."""
        out: set[str] = set(self.channels)
        if self.main_path is not None:
            out.add("")
        return out

    @property
    def supported_generations(self) -> set[DeviceGeneration]:
        from app.library.channels import device_generations_for_set
        return device_generations_for_set(self.all_channels)


@dataclass(frozen=True)
class SubtitleTrack:
    """One subtitle file alongside the scene."""
    path: str
    language: str = "unknown"
    """Language tag extracted from filename pattern `{stem}.{lang}.srt`,
    e.g. 'en', 'es', 'fr'. Defaults to 'unknown' when no tag is parseable
    (e.g. plain `{stem}.srt`)."""

    @property
    def filename(self) -> str:
        return Path(self.path).name


@dataclass
class SceneCatalogEntry:
    """A classified scene folder — the scanner's per-folder output.

    This is the library's source of truth for one scene until the user pins
    choices via the select picker, at which point the pinned choices are
    written to `{base_stem}.forgeplayer.json` in the scene folder.
    """
    folder_path: str
    """Absolute path to the scene folder."""
    name: str
    """Display name for the Library card — derived from the folder name."""

    videos: list[VideoVariant] = field(default_factory=list)
    """All video files in the folder, ordered by default-pick preference
    (scanner's heuristic: highest-resolution non-upscaled non-aspect-variant
    first, then fallbacks)."""

    audio_tracks: list[AudioVariant] = field(default_factory=list)
    """All audio files in the folder. Stem-matched ones first, then
    mismatched-stem 'alternate' tracks."""

    funscript_sets: list[FunscriptSet] = field(default_factory=list)
    """All funscript groups. One set in the common case; 2+ when the folder
    has edit-variants."""

    subtitles: list[SubtitleTrack] = field(default_factory=list)

    archives: list[str] = field(default_factory=list)
    """Paths to `.zip` / `.7z` archives found in the folder (typically
    `{stem}.funscript.zip`). Scanner does not auto-extract in alpha; the
    UI can offer a one-click extract."""

    preset_path: str | None = None
    """Path to `{base_stem}.forgeplayer.json` if present in the folder.
    When loaded, its pinned choices override the scanner's defaults."""

    @property
    def default_video(self) -> VideoVariant | None:
        """First entry in self.videos — the scanner's default-pick."""
        return self.videos[0] if self.videos else None

    @property
    def default_audio(self) -> AudioVariant | None:
        return self.audio_tracks[0] if self.audio_tracks else None

    @property
    def default_funscript_set(self) -> FunscriptSet | None:
        return self.funscript_sets[0] if self.funscript_sets else None

    @property
    def supported_generations(self) -> set[DeviceGeneration]:
        """Union of generations supported by any funscript set in this scene."""
        out: set[DeviceGeneration] = set()
        for fset in self.funscript_sets:
            out |= fset.supported_generations
        return out

    @property
    def has_prostate(self) -> bool:
        return any(fset.has_prostate for fset in self.funscript_sets)

    @property
    def is_ambiguous(self) -> bool:
        """True when the select picker must be shown at tap time.

        A scene is ambiguous if ANY of:
        - more than one video with the SAME preference tier (i.e. the default
          isn't clearly best — see scanner ordering for tiers)
        - more than one audio track without an obvious primary (i.e. more
          than one stem-matched, or zero stem-matched with multiple mismatched)
        - more than one funscript set (edit-variants, like Magik)
        """
        if len(self.funscript_sets) > 1:
            return True

        # A set with generation-modifier-suffixed channels (-stereostim, -2b,
        # -foc-stim) signals the scripter explicitly authored per-generation
        # variants. The user may need to pick which encoding to use at select
        # time, even when there's only one set by base-stem.
        if any(fset.has_generation_variants for fset in self.funscript_sets):
            return True

        if len(self.audio_tracks) > 1:
            # If there's exactly one stem-matched + N mismatched, the
            # stem-matched is the obvious default; not ambiguous.
            stem_matched = sum(1 for a in self.audio_tracks if a.stem_matches_main_video)
            if stem_matched != 1:
                return True

        if len(self.videos) > 1:
            # Ambiguous only when 2+ videos share the BEST preference tier
            # (same aspect-variant / upscale / resolution bucket). A 4K
            # original plus its Topaz-upscaled twin have clearly different
            # tiers → not ambiguous. But two 4K originals (from different
            # sources / encodes) genuinely tie → ambiguous.
            best_tier = self.videos[0].preference_tier
            tied_at_best = sum(
                1 for v in self.videos if v.preference_tier == best_tier
            )
            if tied_at_best > 1:
                return True

        return False

    @property
    def is_playable(self) -> bool:
        """True when there's at least one video AND at least one funscript set
        (may have just the main `.funscript` for mechanical devices)."""
        return bool(self.videos) and bool(self.funscript_sets)
