# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the library scanner, using synthetic fixture folders.

Fixtures mirror the real-world patterns observed in the user's `test_media/`
(see project_forgeplayer_folder_heuristics.md). Everything is built from
zero-byte files in pytest's tmp_path — no binary content, no ffprobe calls,
no reliance on the user's private media.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from app.library.catalog import SceneCatalogEntry
from app.library.channels import DeviceGeneration
from app.library.scanner import (
    scan_library_root,
    scan_scene_folder,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _touch(folder: Path, filename: str) -> Path:
    """Create a zero-byte file."""
    path = folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _make_scene(root: Path, name: str, files: list[str]) -> Path:
    """Create a scene folder with the given filenames."""
    scene_dir = root / name
    scene_dir.mkdir(parents=True, exist_ok=True)
    for fname in files:
        _touch(scene_dir, fname)
    return scene_dir


# ── Pattern-specific fixtures (from real test_media) ──────────────────────────

@pytest.fixture
def euphoria_scene(tmp_path: Path) -> Path:
    """Full FOC-stim pack — mirrors test_media/Euphoria/."""
    return _make_scene(tmp_path, "Euphoria", [
        "Euphoria.mp4",
        "Euphoria.4k60.mp4",
        "Euphoria.funscript",
        "Euphoria.alpha.funscript",
        "Euphoria.beta.funscript",
        "Euphoria.pulse_frequency.funscript",
        "Euphoria.pulse_rise_time.funscript",
        "Euphoria.pulse_width.funscript",
        "Euphoria.volume.funscript",
        "Euphoria.frequency.funscript",
        "Euphoria.alpha-prostate.funscript",
        "Euphoria.volume-prostate.funscript",
        "Euphoria.mp3",
        "Euphoria_Emily's Audio.mp3",
        "Euphoria-restim funscripts.zip",
    ])


@pytest.fixture
def magik_scene(tmp_path: Path) -> Path:
    """Edit-variant scene — two parallel funscript sets in one folder."""
    return _make_scene(tmp_path, "Magik", [
        "Magik Number 3 Pt 1 [E-Stim & Popper Edit].mp4",
        "Magik Number 3 Pt 1 [E-Stim & Popper Edit]_chf3_iris3.mp4",
        "Magik Number 3 Pt 1 [E-Stim & Popper Edit]_chf3_iris3 ultrawide.mp4",
        "Magik Number 3 Pt 1 [E-Stim & Popper Edit].funscript",
        "Magik Number 3 Pt 1 [E-Stim & Popper Edit].alpha.funscript",
        "Magik Number 3 Pt 1 [E-Stim & Popper Edit].beta.funscript",
        "Magik Number 3 Pt 1 [E-Stim & Popper Edit].pulse_frequency.funscript",
        "Magik Number 3 Pt 1 [E-Stim & Popper Edit].volume.funscript",
        "Magik Number 3 Pt 1.alpha.funscript",
        "Magik Number 3 Pt 1.beta.funscript",
        "Magik Number 3 Pt 1.alpha-prostate.funscript",
        "Magik Number 3 Pt 1.beta-prostate.funscript",
        "Magik Number 3 Pt 1 [E-Stim & Popper Edit].mp3",
    ])


@pytest.fixture
def delirious_scene(tmp_path: Path) -> Path:
    """Mismatched-stem audio — `Gooning STIM.mp3` doesn't match video."""
    return _make_scene(tmp_path, "Delirious", [
        "Salon DeSade's Delerious Gooning Pleasure Nr 1 [HD 1080p].mp4",
        "Gooning STIM.mp3",
        "Salon DeSade's Delerious Gooning Pleasure Nr 1.funscript",
    ])


@pytest.fixture
def simple_mechanical_scene(tmp_path: Path) -> Path:
    """Simplest case — one video + one funscript, mechanical only."""
    return _make_scene(tmp_path, "Simple", [
        "Simple.mp4",
        "Simple.funscript",
    ])


@pytest.fixture
def multi_variant_video_scene(tmp_path: Path) -> Path:
    """Multiple video variants: original 4K + Topaz-upscaled + ultrawide."""
    return _make_scene(tmp_path, "ASinful", [
        "A Sinful XXX-perience.mp4",
        "A Sinful XXX-perience_1_iris3.mp4",
        "aSinfull-XXX-cropped-4k.mp4",
        "A Sinful XXX-perience.mp3",
        "A Sinful XXX-perience.funscript",
        "A Sinful XXX-perience.funscript.zip",
    ])


# ── Tests for scan_scene_folder ───────────────────────────────────────────────

class TestScanSceneFolder:
    def test_empty_folder_returns_none(self, tmp_path):
        scene_dir = tmp_path / "empty"
        scene_dir.mkdir()
        assert scan_scene_folder(scene_dir) is None

    def test_nonexistent_folder_returns_none(self, tmp_path):
        assert scan_scene_folder(tmp_path / "does-not-exist") is None

    def test_video_without_funscript_is_not_playable(self, tmp_path):
        scene_dir = _make_scene(tmp_path, "just_video", ["clip.mp4"])
        assert scan_scene_folder(scene_dir) is None

    def test_funscript_without_video_is_not_playable(self, tmp_path):
        scene_dir = _make_scene(tmp_path, "just_script", ["clip.funscript"])
        assert scan_scene_folder(scene_dir) is None

    def test_simple_mechanical_scene(self, simple_mechanical_scene):
        entry = scan_scene_folder(simple_mechanical_scene)
        assert entry is not None
        assert entry.name == "Simple"
        assert len(entry.videos) == 1
        assert entry.videos[0].filename == "Simple.mp4"
        assert len(entry.funscript_sets) == 1
        assert entry.funscript_sets[0].main_path is not None
        assert entry.funscript_sets[0].channels == {}
        assert DeviceGeneration.MECHANICAL in entry.supported_generations
        assert DeviceGeneration.FOC_STIM not in entry.supported_generations
        assert entry.is_ambiguous is False

    def test_euphoria_full_foc_stim(self, euphoria_scene):
        entry = scan_scene_folder(euphoria_scene)
        assert entry is not None
        assert entry.name == "Euphoria"

        # Two video variants, 4k60 preferred over plain .mp4
        assert len(entry.videos) == 2
        # 4k60 should win default — higher resolution rank
        assert "4k" in entry.default_video.tags

        # One funscript set with full FOC-stim + prostate channels
        assert len(entry.funscript_sets) == 1
        fset = entry.funscript_sets[0]
        assert fset.main_path is not None
        assert "alpha" in fset.channels
        assert "beta" in fset.channels
        assert "pulse_frequency" in fset.channels
        assert "volume" in fset.channels
        assert "alpha-prostate" in fset.channels
        assert fset.has_prostate is True

        # Supported generations
        gens = entry.supported_generations
        assert DeviceGeneration.MECHANICAL in gens
        assert DeviceGeneration.STEREOSTIM in gens
        assert DeviceGeneration.FOC_STIM in gens
        assert entry.has_prostate is True

        # Multiple audio files — one stem-matched, one mismatched
        assert len(entry.audio_tracks) == 2
        stem_matched = [a for a in entry.audio_tracks if a.stem_matches_main_video]
        assert len(stem_matched) == 1
        assert stem_matched[0].filename == "Euphoria.mp3"
        # The "Emily's Audio" track is mismatched but still detected
        alt = [a for a in entry.audio_tracks if not a.stem_matches_main_video]
        assert len(alt) == 1

        # Archive detected
        assert any(p.endswith(".zip") for p in entry.archives)

        # NOT ambiguous — single funscript set, exactly one stem-matched audio
        assert entry.is_ambiguous is False

    def test_magik_edit_variants_are_ambiguous(self, magik_scene):
        entry = scan_scene_folder(magik_scene)
        assert entry is not None

        # Two funscript sets (edit vs original)
        assert len(entry.funscript_sets) == 2
        assert entry.is_ambiguous is True

        # Stems preserved verbatim (brackets, spaces, numbers)
        stems = {fset.base_stem for fset in entry.funscript_sets}
        assert "Magik Number 3 Pt 1" in stems
        assert "Magik Number 3 Pt 1 [E-Stim & Popper Edit]" in stems

    def test_delirious_mismatched_stem_audio(self, delirious_scene):
        entry = scan_scene_folder(delirious_scene)
        assert entry is not None

        # One video, one audio, one funscript
        assert len(entry.videos) == 1
        assert len(entry.audio_tracks) == 1

        # The audio stem doesn't match the video — still detected, marked mismatched
        audio = entry.audio_tracks[0]
        assert audio.stem_matches_main_video is False
        assert audio.filename == "Gooning STIM.mp3"

        # Not ambiguous — only one audio candidate means the scanner just uses it
        # (ambiguity only kicks in when there's a genuine CHOICE to make)
        assert entry.is_ambiguous is False

    def test_multi_variant_video_default_is_original(self, multi_variant_video_scene):
        entry = scan_scene_folder(multi_variant_video_scene)
        assert entry is not None

        # 3 videos: original, upscaled, cropped
        assert len(entry.videos) == 3

        # Default is the non-upscaled non-aspect-variant — the "original" mp4
        default = entry.default_video
        assert default is not None
        assert default.is_upscaled is False
        assert default.is_aspect_variant is False
        assert default.filename == "A Sinful XXX-perience.mp4"

    def test_forge_flatten_subfolder(self, tmp_path):
        """`.forge/` inside a scene folder is flattened as additional files."""
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        _touch(scene_dir, "main.mp4")
        _touch(scene_dir, "main.funscript")

        forge_dir = scene_dir / ".forge"
        forge_dir.mkdir()
        _touch(forge_dir, "extra.funscript")
        _touch(forge_dir, "extra.alpha.funscript")
        _touch(forge_dir, "extra.beta.funscript")

        entry = scan_scene_folder(scene_dir)
        assert entry is not None

        # Both the top-level `main` set AND the `.forge/extra` set should be
        # grouped — two sets total → ambiguous
        stems = {fset.base_stem for fset in entry.funscript_sets}
        assert "main" in stems
        assert "extra" in stems
        assert entry.is_ambiguous is True

    def test_subtitle_language_detection(self, tmp_path):
        scene_dir = tmp_path / "subbed"
        scene_dir.mkdir()
        _touch(scene_dir, "scene.mp4")
        _touch(scene_dir, "scene.funscript")
        _touch(scene_dir, "scene.en.srt")
        _touch(scene_dir, "scene.es.srt")
        _touch(scene_dir, "scene.srt")  # no language tag

        entry = scan_scene_folder(scene_dir)
        assert entry is not None
        assert len(entry.subtitles) == 3
        languages = {s.language for s in entry.subtitles}
        assert "en" in languages
        assert "es" in languages
        assert "unknown" in languages

    def test_preset_file_detected(self, tmp_path):
        scene_dir = tmp_path / "pinned"
        scene_dir.mkdir()
        _touch(scene_dir, "pinned.mp4")
        _touch(scene_dir, "pinned.funscript")
        _touch(scene_dir, "pinned.forgeplayer.json")

        entry = scan_scene_folder(scene_dir)
        assert entry is not None
        assert entry.preset_path is not None
        assert entry.preset_path.endswith(".forgeplayer.json")


# ── Tests for scan_library_root ──────────────────────────────────────────────

class TestScanLibraryRoot:
    def test_empty_root_returns_empty_list(self, tmp_path):
        assert scan_library_root(tmp_path) == []

    def test_single_scene_under_root(self, tmp_path, simple_mechanical_scene):
        scenes = scan_library_root(tmp_path)
        assert len(scenes) == 1
        assert scenes[0].name == "Simple"

    def test_multiple_scenes(self, tmp_path):
        _make_scene(tmp_path, "SceneA", ["a.mp4", "a.funscript"])
        _make_scene(tmp_path, "SceneB", ["b.mp4", "b.funscript"])
        _make_scene(tmp_path, "SceneC", ["c.mp4", "c.funscript"])

        scenes = scan_library_root(tmp_path)
        names = {s.name for s in scenes}
        assert names == {"SceneA", "SceneB", "SceneC"}

    def test_nested_part_folders_become_separate_scenes(self, tmp_path):
        """Jet Black pattern: Part 1/ and Part 2/ subfolders under a scene."""
        jet_black = tmp_path / "Jet Black"
        part1 = jet_black / "Part 1"
        part2 = jet_black / "Part 2"
        part1.mkdir(parents=True)
        part2.mkdir(parents=True)
        _touch(part1, "part1.mp4")
        _touch(part1, "part1.funscript")
        _touch(part2, "part2.mp4")
        _touch(part2, "part2.funscript")

        scenes = scan_library_root(tmp_path)
        # Jet Black has no files of its own, so it should NOT be a standalone scene
        # — Part 1 and Part 2 should appear as sub-scenes.
        names = {s.name for s in scenes}
        assert "Jet Black / Part 1" in names
        assert "Jet Black / Part 2" in names

    def test_flat_dump_at_root_level(self, tmp_path):
        """User drops video+funscript directly at root, no scene folder."""
        _touch(tmp_path, "scene.mp4")
        _touch(tmp_path, "scene.funscript")

        scenes = scan_library_root(tmp_path)
        assert len(scenes) == 1
        # Scene name = root folder's name
        assert scenes[0].name == tmp_path.name

    def test_loose_root_files_ignored_when_subfolders_exist(self, tmp_path):
        """Root has both scene subfolders AND loose files: loose files are
        admin noise, not a synthetic 'root scene'. Only subfolder scenes
        appear in the library."""
        # Scene subfolder
        _make_scene(tmp_path, "RealScene", ["real.mp4", "real.funscript"])
        # Loose files at root (different scenes mixed together)
        _touch(tmp_path, "orphan1.mp4")
        _touch(tmp_path, "orphan1.funscript")
        _touch(tmp_path, "orphan2.mp4")
        _touch(tmp_path, "orphan2.funscript")

        scenes = scan_library_root(tmp_path)
        # Only the scene subfolder counts; loose root files are ignored
        assert len(scenes) == 1
        assert scenes[0].name == "RealScene"

    def test_volume_stereostim_folds_into_correct_set(self, tmp_path):
        """Verify `-stereostim` subchannel doesn't spawn spurious sets, AND
        that its presence marks the scene as ambiguous (generation variants
        present → user needs to pick at select time)."""
        scene_dir = _make_scene(tmp_path, "Magik", [
            "Magik Pt 1.funscript",
            "Magik Pt 1.alpha.funscript",
            "Magik Pt 1.beta.funscript",
            "Magik Pt 1.pulse_frequency.funscript",
            "Magik Pt 1.volume.funscript",
            "Magik Pt 1.volume-stereostim.funscript",
            "Magik Pt 1.mp4",
        ])

        entry = scan_scene_folder(scene_dir)
        assert entry is not None
        # Exactly ONE funscript set — volume-stereostim belongs to it, not a new one
        assert len(entry.funscript_sets) == 1
        fset = entry.funscript_sets[0]
        assert fset.base_stem == "Magik Pt 1"
        assert "volume-stereostim" in fset.channels
        assert "volume" in fset.channels
        # The -stereostim variant signals the scripter provided a generation-
        # specific alternative to the plain volume channel → user must choose
        assert fset.has_generation_variants is True
        assert entry.is_ambiguous is True

    def test_no_generation_variants_is_not_ambiguous(self, tmp_path):
        """A clean FOC-stim pack without generation qualifiers is unambiguous."""
        scene_dir = _make_scene(tmp_path, "Clean", [
            "clean.funscript",
            "clean.alpha.funscript",
            "clean.beta.funscript",
            "clean.pulse_frequency.funscript",
            "clean.volume.funscript",
            "clean.mp4",
        ])
        entry = scan_scene_folder(scene_dir)
        assert entry is not None
        assert len(entry.funscript_sets) == 1
        assert entry.funscript_sets[0].has_generation_variants is False
        assert entry.is_ambiguous is False

    def test_prostate_does_not_trigger_generation_ambiguity(self, tmp_path):
        """-prostate is routing, not a generation modifier → not ambiguous."""
        scene_dir = _make_scene(tmp_path, "WithProstate", [
            "scene.funscript",
            "scene.alpha.funscript",
            "scene.beta.funscript",
            "scene.alpha-prostate.funscript",
            "scene.beta-prostate.funscript",
            "scene.mp4",
        ])
        entry = scan_scene_folder(scene_dir)
        assert entry is not None
        assert entry.has_prostate is True
        assert entry.funscript_sets[0].has_generation_variants is False
        assert entry.is_ambiguous is False

    def test_nonexistent_root_returns_empty(self, tmp_path):
        assert scan_library_root(tmp_path / "missing") == []
