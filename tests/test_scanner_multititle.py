# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""End-to-end tests for the recognizer-backed multi-title library scan.

These prove the real-world folder shapes the recognizer was built for, wired
all the way through scan_scene_titles / scan_library_root to SceneCatalogEntry:
  - two distinct works in one folder split into two cards, scripts following
  - funscripts in a separate subfolder attach to their video
  - hidden (dot-prefixed) folders are never scanned
  - a .output export folder becomes the title's bundle
  - single-title folders stay named after the folder (unchanged behavior)
"""

from __future__ import annotations

from pathlib import Path

from app.library.scanner import scan_library_root, scan_scene_titles


def _touch(folder: Path, name: str) -> Path:
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


def _names(entries):
    return {e.name for e in entries}


# ── Two works dumped in one folder ────────────────────────────────────────────

def test_two_volumes_in_one_folder_split(tmp_path):
    d = tmp_path / "Magik"
    for f in [
        "Magik Vol 1.mp4", "Magik Vol 1.alpha.funscript", "Magik Vol 1.beta.funscript",
        "Magik Vol 2.mp4", "Magik Vol 2.alpha.funscript", "Magik Vol 2.beta.funscript",
    ]:
        _touch(d, f)

    entries = scan_scene_titles(d)
    assert len(entries) == 2
    names = _names(entries)
    assert names == {"Magik · Volume 1", "Magik · Volume 2"}
    for e in entries:
        assert len(e.videos) == 1
        assert len(e.funscript_sets) == 1
        # each volume keeps its own scripts
        set_ = e.funscript_sets[0]
        assert "alpha" in set_.channels and "beta" in set_.channels


def test_different_titles_in_one_folder_split(tmp_path):
    d = tmp_path / "Mixed"
    for f in ["Magik.mp4", "Magik.alpha.funscript",
              "Prisoner.mp4", "Prisoner.alpha.funscript"]:
        _touch(d, f)
    entries = scan_scene_titles(d)
    assert len(entries) == 2
    assert _names(entries) == {"Magik", "Prisoner"}


# ── Funscripts in their own subfolder ─────────────────────────────────────────

def test_funscripts_in_subfolder_attach(tmp_path):
    d = tmp_path / "Scene"
    _touch(d, "Scene.4k.mp4")
    _touch(d / "scripts", "Scene.alpha.funscript")
    _touch(d / "scripts", "Scene.beta.funscript")

    entries = scan_scene_titles(d)
    assert len(entries) == 1
    e = entries[0]
    assert e.name == "Scene"           # single title → folder name
    assert len(e.videos) == 1
    assert len(e.funscript_sets) == 1
    assert set(e.funscript_sets[0].channels) == {"alpha", "beta"}


# ── Hidden / working folders never scanned ────────────────────────────────────

def test_dot_folders_skipped(tmp_path):
    d = tmp_path / "Scene"
    _touch(d, "Scene.mp4")
    _touch(d, "Scene.alpha.funscript")
    # FSF working dir + a backup dir — both dot-prefixed, must be ignored.
    _touch(d / ".Scene.forge", "generated.funscript")
    _touch(d / ".Scene.forge" / "polish", "work.funscript")
    _touch(d / ".pre_screech_backup", "Scene.alpha.funscript")

    entries = scan_scene_titles(d)
    assert len(entries) == 1
    e = entries[0]
    # Only the loose top-level script — nothing pulled from dot-folders.
    assert len(e.funscript_sets) == 1
    all_paths = [e.funscript_sets[0].main_path or ""] + list(e.funscript_sets[0].channels.values())
    assert not any(".Scene.forge" in p or "pre_screech" in p for p in all_paths)


# ── .output export folder → title bundle ──────────────────────────────────────

def test_output_folder_becomes_bundle(tmp_path):
    d = tmp_path / "Victoria"
    _touch(d, "Victoria.4k.mp4")
    # Device-organized export output — its funscripts are packaged, not loose.
    _touch(d / "Victoria.output" / "E-Stim", "Victoria.alpha.funscript")
    _touch(d / "Victoria.output" / "E-Stim", "Victoria.beta.funscript")

    entries = scan_scene_titles(d)
    assert len(entries) == 1
    e = entries[0]
    assert e.name == "Victoria"
    assert len(e.videos) == 1
    # The .output is recorded as the bundle (lazy import at activation) — NOT
    # gathered as loose funscripts.
    assert e.bundle_path is not None
    assert e.bundle_path.endswith("Victoria.output")
    assert len(e.funscript_sets) == 0


def test_forge_zip_becomes_bundle(tmp_path):
    d = tmp_path / "Oaks"
    _touch(d, "Oaks.mp4")
    _touch(d, "Oaks.forge")
    entries = scan_scene_titles(d)
    assert len(entries) == 1
    assert entries[0].bundle_path.endswith("Oaks.forge")


# ── Library-root walk: multi-title + flat-dump ────────────────────────────────

def test_library_root_flat_dump_splits_into_cards(tmp_path):
    # A single-folder dump of two works, no subfolders.
    for f in ["Magik.mp4", "Magik.alpha.funscript",
              "Prisoner.mp4", "Prisoner.alpha.funscript"]:
        _touch(tmp_path, f)
    scenes = scan_library_root(tmp_path)
    assert _names(scenes) == {"Magik", "Prisoner"}


def test_library_root_per_folder_single_title_named_by_folder(tmp_path):
    _touch(tmp_path / "SceneA", "a.mp4")
    _touch(tmp_path / "SceneA", "a.funscript")
    _touch(tmp_path / "SceneB", "b.mp4")
    _touch(tmp_path / "SceneB", "b.funscript")
    scenes = scan_library_root(tmp_path)
    assert _names(scenes) == {"SceneA", "SceneB"}


# ── Per-title pins don't collide (two titles, one folder) ─────────────────────

def test_estim_audio_subfolder_folds_into_parent(tmp_path):
    # 'Clutch spicy' style: an audio-only subfolder of a video scene folds its
    # estim audio into the parent's audio picker, not a separate card.
    scene = tmp_path / "Clutch"
    _touch(scene, "Clutch.mp4")
    _touch(scene, "Clutch ESTIM mild.mp3")
    _touch(scene / "Clutch spicy", "Clutch ESTIM Spicy Ramp.mp3")
    _touch(scene / "Clutch spicy", "Clutch ESTIM Spicy Ramp Ending.mp3")

    scenes = scan_library_root(tmp_path)
    assert _names(scenes) == {"Clutch"}          # one card, spicy folded in
    clutch = scenes[0]
    assert len(clutch.audio_tracks) == 3         # mild + 2 spicy ramps


def test_underscore_staging_folder_named_by_content(tmp_path):
    # A '_'-prefixed staging folder holding a loose video + its .output keeps the
    # video's name, not the folder name.
    stage = tmp_path / "_forgeplayme"
    _touch(stage, "Prisoner.mp4")
    _touch(stage / "Prisoner.output" / "E-Stim", "Prisoner.alpha.funscript")

    entries = scan_scene_titles(stage)
    assert len(entries) == 1
    assert entries[0].name == "Prisoner"         # not '_forgeplayme'
    assert entries[0].bundle_path is not None     # .output attached


def test_scripts_subfolder_does_not_leak_a_card(tmp_path):
    # A Scripts-only subfolder folds into the parent and must NOT also appear as
    # its own empty card at library level.
    scene = tmp_path / "Celestial Succubus"
    _touch(scene, "Celestial Succubus.mp4")
    _touch(scene / "Scripts", "Celestial Succubus.alpha.funscript")
    _touch(scene / "Scripts", "Celestial Succubus.beta.funscript")

    scenes = scan_library_root(tmp_path)
    names = _names(scenes)
    assert "Celestial Succubus" in names
    assert not any("Scripts" in n for n in names)
    # And the scripts did fold into the parent.
    cs = next(e for e in scenes if e.name == "Celestial Succubus")
    assert len(cs.funscript_sets) == 1


def test_multititle_pins_are_distinct(tmp_path):
    from app.library.pins import pin_path_for

    d = tmp_path / "Magik"
    for f in ["Magik Vol 1.mp4", "Magik Vol 1.alpha.funscript",
              "Magik Vol 2.mp4", "Magik Vol 2.alpha.funscript"]:
        _touch(d, f)
    entries = scan_scene_titles(d)
    assert len(entries) == 2
    paths = {str(pin_path_for(e)) for e in entries}
    # Distinct pin files → pinning Vol 1's picks never clobbers Vol 2's.
    assert len(paths) == 2
