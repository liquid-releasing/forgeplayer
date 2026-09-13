# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Browse must load the funscript the user picked, wherever it lives.

User report 2026-09-13: "funscript files must be in the same directory or a
subdirectory somewhere below the one where the video file is stored to be found
by the app. If the funscripts are stored in a directory outside the video's
directory they are not found. And strangely they can't even be loaded manually
via the Browse button."

The second half was a real bug. `_funscript_set_from_path` called
`scan_scene_folder`, which answers "is this folder a library scene?" and returns
None unless the folder holds a video, an audio track or an export bundle
(`SceneCatalogEntry.is_playable` — funscripts alone deliberately do not count,
because a folder of bare scripts is not a scene tile). Browse inherited that
gate even though it asks a completely different question: the user has already
said which file they want.

The first half is by design: the Library scans folders as scenes, so
auto-discovery is folder-scoped. Cross-directory matching is a separate feature,
not covered here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.library.scanner import (
    funscript_sets_in_folder,
    group_funscript_sets,
    scan_scene_folder,
)


def _fs(path: Path) -> Path:
    path.write_text(
        json.dumps({"actions": [{"at": 0, "pos": 0}, {"at": 1000, "pos": 100}]}),
        encoding="utf-8",
    )
    return path


# ── The gate that caused it, pinned so nobody reuses it for Browse ───────────

def test_scan_scene_folder_still_rejects_a_scripts_only_folder(tmp_path):
    """Not a bug — a folder of bare scripts is not a library scene, and the
    Library is right to skip it. This is pinned so the distinction stays
    visible: the fix was to stop Browse depending on this answer, NOT to
    loosen it."""
    d = tmp_path / "scripts_only"
    d.mkdir()
    _fs(d / "MyScene.funscript")
    assert scan_scene_folder(d) is None


# ── The Browse scanner ───────────────────────────────────────────────────────

def test_funscript_sets_found_in_a_folder_with_no_video(tmp_path):
    """THE reported case."""
    d = tmp_path / "scripts_only"
    d.mkdir()
    _fs(d / "MyScene.funscript")
    _fs(d / "MyScene.alpha.funscript")
    _fs(d / "MyScene.beta.funscript")

    sets = funscript_sets_in_folder(d)
    assert len(sets) == 1
    assert sets[0].base_stem == "MyScene"
    # Channel siblings come along — the whole reason Browse scans the folder
    # rather than just wrapping the one file.
    assert sorted(sets[0].channels) == ["alpha", "beta"]


def test_a_single_lonely_funscript_is_still_a_set(tmp_path):
    d = tmp_path / "lonely"
    d.mkdir()
    _fs(d / "Solo.funscript")
    sets = funscript_sets_in_folder(d)
    assert len(sets) == 1 and sets[0].base_stem == "Solo"


def test_multiple_unrelated_scripts_become_separate_sets(tmp_path):
    d = tmp_path / "many"
    d.mkdir()
    _fs(d / "A.funscript")
    _fs(d / "B.funscript")
    assert {s.base_stem for s in funscript_sets_in_folder(d)} == {"A", "B"}


def test_non_funscripts_are_ignored(tmp_path):
    d = tmp_path / "mixed"
    d.mkdir()
    _fs(d / "Real.funscript")
    (d / "notes.txt").write_text("hi", encoding="utf-8")
    (d / "clip.mp4").write_bytes(b"\x00")
    assert [s.base_stem for s in funscript_sets_in_folder(d)] == ["Real"]


def test_missing_or_empty_folder_returns_empty(tmp_path):
    assert funscript_sets_in_folder(tmp_path / "nope") == []
    empty = tmp_path / "empty"
    empty.mkdir()
    assert funscript_sets_in_folder(empty) == []


def test_a_file_path_instead_of_a_folder_returns_empty(tmp_path):
    f = _fs(tmp_path / "X.funscript")
    assert funscript_sets_in_folder(f) == []


# ── group_funscript_sets ordering ────────────────────────────────────────────

def test_video_matching_stem_sorts_first(tmp_path):
    """Ordering behaviour carried over from scan_scene_folder, kept because the
    Library still depends on it."""
    paths = [tmp_path / "Magik [E-Stim Edit].funscript", tmp_path / "Magik.funscript"]
    for p in paths:
        _fs(p)
    out = group_funscript_sets(paths, video_base_stems={"Magik"})
    assert out[0].base_stem == "Magik"


def test_shorter_stem_wins_when_no_video_to_match(tmp_path):
    """The browse path passes no video stems at all, so the tiebreak has to
    work without them."""
    paths = [tmp_path / "Scene [Edit].funscript", tmp_path / "Scene.funscript"]
    for p in paths:
        _fs(p)
    out = group_funscript_sets(paths)
    assert out[0].base_stem == "Scene"


# ── End to end through the Browse entry point ────────────────────────────────

def test_browse_resolves_a_script_outside_any_video_folder(tmp_path):
    """What the user actually does: point the file dialog at a script that
    lives nowhere near a video."""
    from app.control_window import ControlWindow

    scripts = tmp_path / "my_scripts"
    scripts.mkdir()
    picked = _fs(scripts / "Whatever.funscript")
    _fs(scripts / "Whatever.alpha.funscript")
    # A video somewhere else entirely — deliberately unrelated.
    videos = tmp_path / "my_videos"
    videos.mkdir()
    (videos / "Whatever.mp4").write_bytes(b"\x00")

    fset = ControlWindow._funscript_set_from_path(str(picked))
    assert fset is not None, "Browse must load the file the user picked"
    assert fset.base_stem == "Whatever"
    assert "alpha" in fset.channels


def test_browse_returns_the_set_containing_the_picked_file(tmp_path):
    """With several unrelated sets in one folder, the pick decides — not
    whichever happens to sort first."""
    from app.control_window import ControlWindow

    d = tmp_path / "d"
    d.mkdir()
    _fs(d / "Aaa.funscript")
    picked = _fs(d / "Zzz.funscript")
    fset = ControlWindow._funscript_set_from_path(str(picked))
    assert fset is not None and fset.base_stem == "Zzz"


def test_browse_honours_an_explicit_pick_even_if_the_scan_misses_it(tmp_path):
    """Belt and braces: an explicit pick is never answered with None while the
    file exists. Browse doing nothing is the failure being fixed."""
    from app.control_window import ControlWindow

    d = tmp_path / "d"
    d.mkdir()
    picked = _fs(d / "Odd.funscript")

    import app.library.scanner as scanner
    real = scanner.funscript_sets_in_folder
    try:
        scanner.funscript_sets_in_folder = lambda _folder: []   # simulate a miss
        fset = ControlWindow._funscript_set_from_path(str(picked))
    finally:
        scanner.funscript_sets_in_folder = real
    assert fset is not None and fset.base_stem == "Odd"


def test_browse_on_a_nonexistent_path_returns_none(tmp_path):
    from app.control_window import ControlWindow
    assert ControlWindow._funscript_set_from_path(str(tmp_path / "ghost.funscript")) is None
