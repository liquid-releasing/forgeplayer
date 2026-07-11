# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""End-to-end tests for the funscript-first library scan.

The card model (user 2026-07-11): the Library is a launcher for HAPTIC SCENES,
not a video catalog. A card is a funscript SET (or a `.forge`/`.output` bundle,
or a pre-rendered e-stim SOUND) plus the video whose name it matches. These
tests prove the real-world folder shapes wired through scan_scene_titles /
scan_library_root to SceneCatalogEntry:

  - a video with NO haptic asset is not a card (source pieces, unscripted clips)
  - each funscript SET finds its own video → distinct scripts = distinct cards
  - same-name video renders (4k + 1080p) collapse into ONE card as a choice
  - funscripts in a separate subfolder attach to their video
  - hidden (dot-prefixed) folders are never scanned
  - a .output / .forge export becomes the card's bundle
  - an e-stim sound with no funscript forms a card; a stray sound does not
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


# ── The core rule: haptics drive the card, videos alone do not ────────────────

def test_video_without_funscript_is_not_a_card(tmp_path):
    # darling 3/4/5 — three videos, no funscript anywhere → NO tiles. Videos are
    # not playable haptic scenes on their own.
    d = tmp_path / "the_unit"
    for n in (3, 4, 5):
        _touch(d, f"darling{n} high.mp4")
    assert scan_scene_titles(d) == []


def test_each_funscript_set_is_its_own_card(tmp_path):
    # Magik Vol 1 and Vol 2 each have their own script → TWO cards, not one
    # collapsed series. Distinct scripts = distinct works.
    d = tmp_path / "Magik"
    for f in [
        "Magik Vol 1.mp4", "Magik Vol 1.alpha.funscript", "Magik Vol 1.beta.funscript",
        "Magik Vol 2.mp4", "Magik Vol 2.alpha.funscript", "Magik Vol 2.beta.funscript",
    ]:
        _touch(d, f)

    entries = scan_scene_titles(d)
    assert len(entries) == 2
    assert _names(entries) == {"Magik Vol 1", "Magik Vol 2"}
    for e in entries:
        assert len(e.videos) == 1
        assert set(e.funscript_sets[0].channels) == {"alpha", "beta"}


def test_scripted_video_beside_unscripted_pieces(tmp_path):
    # A scripted main video sitting next to shorter unscripted source pieces:
    # only the scripted one is a card.
    d = tmp_path / "megamix"
    _touch(d, "megamix.mp4")
    _touch(d, "megamix.funscript")
    _touch(d, "piece_a.mp4")            # source piece, no script
    _touch(d, "piece_b.mp4")            # source piece, no script
    entries = scan_scene_titles(d)
    assert len(entries) == 1
    assert entries[0].name == "megamix"


def test_distinct_scripted_works_get_distinct_cards(tmp_path):
    # animopron-style: several scripted works in one folder → a card each.
    d = tmp_path / "animopron"
    for f in [
        "Breaking The Quiet.mp4", "Breaking The Quiet.funscript",
        "Lara In Trouble.mp4", "Lara In Trouble.funscript",
        "Prison Battleship.mp4", "Prison Battleship.funscript",
    ]:
        _touch(d, f)
    entries = scan_scene_titles(d)
    assert len(entries) == 3
    assert _names(entries) == {
        "Breaking The Quiet", "Lara In Trouble", "Prison Battleship"
    }


def test_same_video_renders_collapse_to_one_card(tmp_path):
    # 4k + 1080p of the same work, one script → ONE card offering both renders.
    d = tmp_path / "Mommy"
    _touch(d, "Mommy.4k.mp4")
    _touch(d, "Mommy.1080p.mp4")
    _touch(d, "Mommy.funscript")
    entries = scan_scene_titles(d)
    assert len(entries) == 1
    e = entries[0]
    assert len(e.videos) == 2
    assert e.needs_video_choice
    assert len(e.funscript_sets) == 1


def test_edit_variant_scripts_are_one_card_two_sets(tmp_path):
    # Original + a bracketed edit-variant of the SAME video → one card with two
    # funscript sets (a pick), not two cards.
    d = tmp_path / "Magik"
    _touch(d, "Magik.mp4")
    _touch(d, "Magik.funscript")
    _touch(d, "Magik [E-Stim & Popper Edit].funscript")
    entries = scan_scene_titles(d)
    assert len(entries) == 1
    e = entries[0]
    assert len(e.funscript_sets) == 2
    assert e.needs_funscript_set_choice


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
    assert e.name == "Scene"           # single scene → folder name
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
    ch = e.funscript_sets[0].channels
    all_paths = [e.funscript_sets[0].main_path or ""] + list(ch.values())
    assert not any(".Scene.forge" in p or "pre_screech" in p for p in all_paths)


# ── Export bundle → card bundle ───────────────────────────────────────────────

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
    # The .output is the bundle (lazy import at activation) — NOT loose scripts.
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


def test_bundle_without_loose_video_still_a_card(tmp_path):
    # A self-contained .output with no loose video is still playable (importer
    # relinks its video) → one card named for the work.
    d = tmp_path / "_stage"
    _touch(d / "Prisoner.output" / "E-Stim", "Prisoner.alpha.funscript")
    entries = scan_scene_titles(d)
    assert len(entries) == 1
    assert entries[0].name == "Prisoner"
    assert entries[0].bundle_path is not None


# ── e-stim sound as the haptic asset ──────────────────────────────────────────

def test_estim_sound_forms_a_card(tmp_path):
    # No funscript — the e-stim mp3 IS the haptic track → a card.
    d = tmp_path / "Clutch"
    _touch(d, "Clutch.mp4")
    _touch(d, "Clutch ESTIM mild.mp3")
    entries = scan_scene_titles(d)
    assert len(entries) == 1
    assert entries[0].name == "Clutch"
    assert len(entries[0].audio_tracks) == 1


def test_estim_audio_subfolder_folds_into_parent(tmp_path):
    # 'Clutch spicy' style: an audio-only subfolder of a scene folds its estim
    # audio into the parent's audio list, not a separate card.
    scene = tmp_path / "Clutch"
    _touch(scene, "Clutch.mp4")
    _touch(scene, "Clutch ESTIM mild.mp3")
    _touch(scene / "Clutch spicy", "Clutch ESTIM Spicy Ramp.mp3")
    _touch(scene / "Clutch spicy", "Clutch ESTIM Spicy Ramp Ending.mp3")

    scenes = scan_library_root(tmp_path)
    assert _names(scenes) == {"Clutch"}          # one card, spicy folded in
    clutch = scenes[0]
    assert len(clutch.audio_tracks) == 3         # mild + 2 spicy ramps


def test_stray_sound_without_video_is_dropped(tmp_path):
    # A beat track with no matching video is not a scene → no tile.
    d = tmp_path / "loose"
    _touch(d, "some_beat_track.mp3")
    assert scan_scene_titles(d) == []


def test_name_matched_sound_makes_a_scene(tmp_path):
    # A sound that matches a video by name is that video's haptic track (many
    # scenes ship as video + e-stim MP3, no funscript) → one card, not video-only.
    d = tmp_path / "clip"
    _touch(d, "clip.mp4")
    _touch(d, "clip estim.mp3")
    entries = scan_scene_titles(d)
    assert len(entries) == 1
    assert not entries[0].is_video_only
    assert entries[0].has_haptics
    assert len(entries[0].audio_tracks) == 1


def test_noise_tagged_video_pairs_with_plain_estim_mp3(tmp_path):
    # The real-world E:/videos shape: an encoder-noise video name pairs with an
    # estim MP3 named for the plain work.
    d = tmp_path / "_Klinik hb"
    _touch(d, "Klinik Industries Vi22 Hq Chf3 Iris3 5120x1440.mkv")
    _touch(d, "Klinik Industries Vi22 Hq Chf3 Iris3.mp4")
    _touch(d, "Klinik Industries Vi22 - Triphase.mp3")
    entries = scan_scene_titles(d)
    assert len(entries) == 1
    e = entries[0]
    assert not e.is_video_only
    assert len(e.videos) == 2           # both renders collapse into one card
    assert len(e.audio_tracks) == 1     # the estim MP3 is the haptic track


def test_ordinal_parts_stay_separate_despite_resolution_suffix(tmp_path):
    # 'Part 1 4K' / 'Part 2 4K60' — the ordinal must survive next to a
    # resolution token (it's not a render pass-number).
    d = tmp_path / "Jet Black"
    _touch(d, "Jet Black - Part 1 4K.mp4")
    _touch(d, "Jet Black - Part 1 By Fb.mp3")
    _touch(d, "Jet Black - Part 2 4K60.mp4")
    _touch(d, "Jet Black - Part 2 By Fb.mp3")
    entries = scan_scene_titles(d)
    assert {e.name for e in entries} == {"Jet Black Part 1", "Jet Black Part 2"}


# ── Library-root walk ─────────────────────────────────────────────────────────

def test_library_root_flat_dump_splits_into_cards(tmp_path):
    # A single-folder dump of two scripted works, no subfolders.
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
    cs = next(e for e in scenes if e.name == "Celestial Succubus")
    assert len(cs.funscript_sets) == 1


# ── Per-card pins ─────────────────────────────────────────────────────────────

def test_distinct_works_get_distinct_pins(tmp_path):
    from app.library.pins import pin_path_for

    d = tmp_path / "Mixed"
    for f in ["Magik.mp4", "Magik.alpha.funscript",
              "Prisoner.mp4", "Prisoner.alpha.funscript"]:
        _touch(d, f)
    entries = scan_scene_titles(d)
    assert len(entries) == 2
    paths = {str(pin_path_for(e)) for e in entries}
    assert len(paths) == 2


# ── Standalone videos (Videos / All filters) ──────────────────────────────────

def test_standalone_video_only_with_include_flag(tmp_path):
    # A video with no haptics is omitted by default but surfaces (tagged) when
    # standalone videos are requested — the 'Videos' filter's source.
    d = tmp_path / "clips"
    _touch(d, "lonely.mp4")
    assert scan_scene_titles(d) == []
    with_v = scan_scene_titles(d, include_standalone=True)
    assert len(with_v) == 1
    assert with_v[0].is_video_only
    assert not with_v[0].has_haptics


def test_standalone_collapses_same_name_renders(tmp_path):
    # 4k + 1080p of an unscripted work → ONE standalone-video card, two renders.
    d = tmp_path / "clips"
    _touch(d, "beach.4k.mp4")
    _touch(d, "beach.1080p.mp4")
    entries = scan_scene_titles(d, include_standalone=True)
    assert len(entries) == 1
    assert entries[0].is_video_only
    assert len(entries[0].videos) == 2


def test_scripted_video_not_duplicated_as_standalone(tmp_path):
    # A scripted video must NOT also appear as a standalone-video card.
    d = tmp_path / "Scene"
    _touch(d, "Scene.mp4")
    _touch(d, "Scene.funscript")
    entries = scan_scene_titles(d, include_standalone=True)
    assert len(entries) == 1
    assert not entries[0].is_video_only
    assert entries[0].has_haptics


def test_library_root_tags_standalone_videos(tmp_path):
    # End-to-end: a scripted scene and an unscripted clip folder → the clip is
    # tagged is_video_only so the default filter can hide it.
    _make = lambda folder, files: [_touch(tmp_path / folder, f) for f in files]
    _make("Scripted", ["s.mp4", "s.funscript"])
    _make("Raw", ["raw.mp4"])
    scenes = scan_library_root(tmp_path)
    by_name = {s.name: s for s in scenes}
    assert not by_name["Scripted"].is_video_only
    assert by_name["Raw"].is_video_only


def test_scenes_still_pinnable(tmp_path):
    from app.library.pins import is_pinnable

    d = tmp_path / "Solo"
    _touch(d, "Solo.mp4")
    _touch(d, "Solo.alpha.funscript")
    solo = scan_scene_titles(d)[0]
    assert is_pinnable(solo) is True
