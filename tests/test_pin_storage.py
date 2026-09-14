# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Where pins are stored, and what a pin is able to remember.

Two user reports from 2026-09-14, which turned out to share one cause — the
pin format could not describe a source the scanner hadn't found:

1. "For every video I select in the library there is a `*.forgeplayer.json`
   file created adjacent to the video file — which I don't like because I don't
   want to get my media volume / directory structure filled with other stuff."

2. "I can select a funscript file but it doesn't get loaded/accepted." Browse
   could load a funscript from outside the scene folder, but the pin recorded
   only a **base stem**, and `resolve_pin` matched stems against the scene
   folder's own sets. A browsed set is not in that list, so the pick could never
   come back — and nothing persisted it in the first place.

Pins had no test coverage at all before this file, which is how both shipped.
"""

from __future__ import annotations

import json

import pytest

from app.library import pins as pins_mod
from app.library.catalog import (
    AudioVariant,
    FunscriptSet,
    SceneCatalogEntry,
    VideoVariant,
)
from app.library.pins import (
    Pin,
    has_pin,
    legacy_pin_path_for,
    load_pin,
    pin_path_for,
    resolve_pin,
    save_pin,
)


@pytest.fixture(autouse=True)
def app_home(tmp_path, monkeypatch):
    """Redirect the app-owned pin store so tests never touch ~/.forgeplayer."""
    home = tmp_path / "_apphome"
    monkeypatch.setattr(pins_mod, "_PINS_DIR", home / "pins")
    monkeypatch.setattr(pins_mod, "_CATALOG_PATH", home / "catalog.json")
    return home


def _fs(path):
    path.write_text(
        json.dumps({"actions": [{"at": 0, "pos": 0}, {"at": 900, "pos": 90}]}),
        encoding="utf-8",
    )
    return path


def _scene(tmp_path, name="SomeScene"):
    """A video-only scene folder — the reporter's case: no funscripts found."""
    folder = tmp_path / "Media" / name
    folder.mkdir(parents=True)
    video = folder / (name + ".mp4")
    video.write_bytes(b"\x00")
    entry = SceneCatalogEntry(folder_path=str(folder), name=name)
    entry.videos.append(VideoVariant(path=str(video)))
    return entry


def _scene_like(entry):
    """A freshly-scanned entry for the same scene — what the next activation
    actually sees, holding only what the folder itself contains."""
    from app.library.scanner import scan_scene_folder
    fresh = scan_scene_folder(entry.folder_path)
    if fresh is None:
        fresh = SceneCatalogEntry(folder_path=entry.folder_path, name=entry.name)
    fresh.name = entry.name
    return fresh


# ── Report 1: stop writing into the user's media ─────────────────────────────

def test_saving_a_pin_writes_nothing_into_the_media_folder(tmp_path):
    """THE reported complaint."""
    entry = _scene(tmp_path)
    media = tmp_path / "Media" / "SomeScene"
    before = {p.name for p in media.iterdir()}

    save_pin(entry, video=entry.videos[0], audio=None,
             funscript_set=None, subtitle=None)

    after = {p.name for p in media.iterdir()}
    assert after == before, "media folder gained files: " + str(after - before)
    assert not any(n.endswith(".forgeplayer.json") for n in after)


def test_the_pin_lands_in_the_app_folder(tmp_path, app_home):
    entry = _scene(tmp_path)
    path = save_pin(entry, video=entry.videos[0], audio=None,
                    funscript_set=None, subtitle=None)
    assert path.is_file()
    assert app_home / "pins" in path.parents


def test_distinct_works_in_one_folder_get_distinct_pins(tmp_path):
    """`scan_scene_titles` can return several works from a single folder, so
    the key cannot be the folder alone or they overwrite each other."""
    folder = tmp_path / "Mixed"
    folder.mkdir()
    a = SceneCatalogEntry(folder_path=str(folder), name="Magik")
    b = SceneCatalogEntry(folder_path=str(folder), name="Prisoner")
    assert pin_path_for(a) != pin_path_for(b)


def test_the_same_scene_resolves_to_one_pin_regardless_of_path_spelling(tmp_path):
    """A library root repointed at a differently-spelled path is the same
    scene, not a second one whose pin is orphaned."""
    folder = tmp_path / "Media" / "Scene"
    folder.mkdir(parents=True)
    plain = SceneCatalogEntry(folder_path=str(folder), name="Scene")
    trailing = SceneCatalogEntry(folder_path=str(folder / "."), name="Scene")
    assert pin_path_for(plain) == pin_path_for(trailing)


# ── Legacy sidecars are migrated, not abandoned ──────────────────────────────

def test_a_legacy_sidecar_is_read_and_then_removed(tmp_path):
    """Existing users keep their picks and stop accumulating sidecars."""
    entry = _scene(tmp_path)
    legacy = legacy_pin_path_for(entry)
    legacy.write_text(
        json.dumps(Pin(scene_name="SomeScene",
                       video_filename="SomeScene.mp4").to_dict()),
        encoding="utf-8",
    )

    pin = load_pin(entry)

    assert pin is not None and pin.video_filename == "SomeScene.mp4"
    assert pin_path_for(entry).is_file(), "should migrate to the app folder"
    assert not legacy.exists(), "the sidecar should be gone after migration"


def test_saving_retires_an_existing_sidecar(tmp_path):
    entry = _scene(tmp_path)
    legacy = legacy_pin_path_for(entry)
    legacy.write_text(json.dumps(Pin(scene_name="SomeScene").to_dict()),
                      encoding="utf-8")

    save_pin(entry, video=entry.videos[0], audio=None,
             funscript_set=None, subtitle=None)

    assert not legacy.exists()
    assert pin_path_for(entry).is_file()


def test_has_pin_sees_an_unmigrated_sidecar(tmp_path):
    """The Library's pinned badge must not blink off before migration runs."""
    entry = _scene(tmp_path)
    assert not has_pin(entry)
    legacy_pin_path_for(entry).write_text(
        json.dumps(Pin(scene_name="SomeScene").to_dict()), encoding="utf-8")
    assert has_pin(entry)


def test_a_v1_pin_without_path_fields_still_loads(tmp_path):
    """Old pins predate every *_path field; missing and unknown keys must not
    raise."""
    target = pin_path_for(entry_of := _scene(tmp_path))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "version": 1,
        "scene_name": "SomeScene",
        "video_filename": "SomeScene.mp4",
        "funscript_set_stem": "SomeScene",
        "unknown_future_key": 1,
    }), encoding="utf-8")

    pin = load_pin(entry_of)
    assert pin is not None
    assert pin.funscript_set_stem == "SomeScene"
    assert pin.funscript_set_path is None


# ── Report 2: a browsed funscript has to come back ───────────────────────────

def test_a_browsed_out_of_folder_set_round_trips(tmp_path):
    """THE fix. Save the pick, rescan the scene (which still finds no
    funscripts of its own), and the browsed set must resolve anyway."""
    from app.library.scanner import funscript_set_for_file

    entry = _scene(tmp_path)
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    _fs(scripts / "SomeScene.funscript")
    _fs(scripts / "SomeScene.alpha.funscript")

    browsed = funscript_set_for_file(str(scripts / "SomeScene.funscript"))
    assert browsed is not None

    save_pin(entry, video=entry.videos[0], audio=None,
             funscript_set=browsed, subtitle=None)

    fresh = _scene_like(entry)
    assert fresh.funscript_sets == [], "the scene folder still has no scripts"

    resolved = resolve_pin(fresh, load_pin(fresh))

    assert not resolved.is_stale, resolved.stale_fields
    assert resolved.funscript_set is not None
    assert resolved.funscript_set.base_stem == "SomeScene"
    # Channel siblings come back too, not just the one file that was picked.
    assert "alpha" in resolved.funscript_set.channels


def test_a_browsed_set_that_was_deleted_is_reported_stale(tmp_path):
    """The fallback must not invent a set for a file that is gone — being
    honest here is what sends the user back to the picker."""
    from app.library.scanner import funscript_set_for_file

    entry = _scene(tmp_path)
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    picked = _fs(scripts / "SomeScene.funscript")
    browsed = funscript_set_for_file(str(picked))
    save_pin(entry, video=entry.videos[0], audio=None,
             funscript_set=browsed, subtitle=None)

    picked.unlink()

    resolved = resolve_pin(entry, load_pin(entry))
    assert "funscript_set" in resolved.stale_fields
    assert resolved.funscript_set is None


def test_an_in_folder_set_still_matches_by_stem(tmp_path):
    """The path fallback must not displace the in-folder match: a scene whose
    files moved keeps working because the scanned stem still matches."""
    folder = tmp_path / "Media" / "Scene"
    folder.mkdir(parents=True)
    entry = SceneCatalogEntry(folder_path=str(folder), name="Scene")
    entry.funscript_sets.append(
        FunscriptSet(base_stem="Scene", main_path=str(folder / "Scene.funscript"))
    )

    save_pin(entry, video=None, audio=None,
             funscript_set=entry.funscript_sets[0], subtitle=None)
    pin = load_pin(entry)

    # Rescanned with the set now living somewhere else: the recorded absolute
    # path is dead, but the scanned set is right there.
    moved = SceneCatalogEntry(folder_path=str(folder), name="Scene")
    moved.funscript_sets.append(
        FunscriptSet(base_stem="Scene",
                     main_path=str(tmp_path / "Elsewhere" / "Scene.funscript"))
    )

    resolved = resolve_pin(moved, pin)
    assert not resolved.is_stale
    assert resolved.funscript_set is moved.funscript_sets[0]


def test_a_browsed_video_outside_the_scene_folder_round_trips(tmp_path):
    """Browse reaches a video anywhere too, and had the same blind spot."""
    entry = _scene(tmp_path)
    other = tmp_path / "Elsewhere"
    other.mkdir()
    far = other / "Alternate.mp4"
    far.write_bytes(b"\x00")

    save_pin(entry, video=VideoVariant(path=str(far)), audio=None,
             funscript_set=None, subtitle=None)

    fresh = _scene_like(entry)
    resolved = resolve_pin(fresh, load_pin(fresh))

    assert not resolved.is_stale, resolved.stale_fields
    assert resolved.video is not None
    assert resolved.video.path == str(far)


def test_a_browsed_audio_track_outside_the_scene_folder_round_trips(tmp_path):
    entry = _scene(tmp_path)
    other = tmp_path / "Elsewhere"
    other.mkdir()
    far = other / "stim.mp3"
    far.write_bytes(b"\x00")

    save_pin(entry, video=None, audio=AudioVariant(path=str(far)),
             funscript_set=None, subtitle=None)

    fresh = _scene_like(entry)
    resolved = resolve_pin(fresh, load_pin(fresh))

    assert not resolved.is_stale, resolved.stale_fields
    assert resolved.audio is not None
    assert resolved.audio.path == str(far)
