# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for two ControlWindow behaviors added/changed 2026-08-20:

- _resolve_bundle_backed: a .forge/.output export bundle now always wins
  over loose scanned funscripts for the same scene (previously loose files
  could win even when the bundle was more complete). It never touches
  `self`, so it's called directly as ControlWindow._resolve_bundle_backed
  (self=None, entry) — no QApplication/ControlWindow instance needed.

- _on_stim_folder_scanned: the Live tab's Stim-source Browse button scans
  the picked file's folder on a worker thread now instead of blocking the
  GUI thread; this is the guard that drops a scan result if the user
  switched scenes before it returned. This DOES need a real ControlWindow
  instance (it reads self._current_entry / self._stim_scan_target_entry /
  etc.), so these tests use the `qapp` fixture and construct one directly.

IMPORTANT: never call .close() on a ControlWindow built in a test.
closeEvent's teardown path ends in a hard os._exit(0) (by design, so the
GUI thread can't hang waiting on mpv teardown on real quit) — calling it
here would silently kill the entire pytest process, not just the window.
An unshown, never-closed QMainWindow is fine to just let the garbage
collector reclaim.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.control_window import ControlWindow
from app.library.catalog import FunscriptSet, SceneCatalogEntry, VideoVariant
from app.select_picker import SelectionChoices


# ── _resolve_bundle_backed ───────────────────────────────────────────────────

def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _make_bundle_tree(root: Path, stem: str = "Scene") -> Path:
    _touch(root / "motion.funscript")
    for ch in ("alpha", "beta", "alpha-prostate"):
        _touch(root / "stations" / "estim3p" / f"{stem}.{ch}.funscript")
    manifest = {
        "version": 1, "schema": "ffmeta/v1", "stem": stem,
        "created_with": "FunscriptForge", "media": {},
    }
    (root / "manifest.ffmeta").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _loose_entry(tmp_path: Path, *, bundle_path: str | None) -> SceneCatalogEntry:
    """A card as the folder scanner would build it: its own loose funscript
    set (possibly motion-only, no e-stim), plus a bundle_path if an export
    sits beside it."""
    loose_fs = FunscriptSet(
        base_stem="Scene", main_path=str(tmp_path / "Scene.funscript"),
    )
    return SceneCatalogEntry(
        folder_path=str(tmp_path),
        name="Scene",
        videos=[VideoVariant(path=str(tmp_path / "Scene.mp4"), tags=frozenset())],
        funscript_sets=[loose_fs],
        bundle_path=bundle_path,
    )


def test_resolve_bundle_backed_passthrough_when_no_bundle(tmp_path):
    entry = _loose_entry(tmp_path, bundle_path=None)
    result = ControlWindow._resolve_bundle_backed(None, entry)
    assert result is entry


def test_resolve_bundle_backed_prefers_bundle_haptics_over_loose(tmp_path):
    bundle_dir = _make_bundle_tree(tmp_path / "Scene.output")
    entry = _loose_entry(tmp_path, bundle_path=str(bundle_dir))

    result = ControlWindow._resolve_bundle_backed(None, entry)

    # The bundle's richer e-stim set wins, not the loose motion-only one.
    sets_by_stem = {s.base_stem: s for s in result.funscript_sets}
    assert "Scene" in sets_by_stem
    fset = sets_by_stem["Scene"]
    assert "alpha" in fset.channels
    assert "alpha-prostate" in fset.channels
    # The loose set (no channels) must not be what got returned.
    assert fset.channels  # i.e. it's the bundle's set, not entry.funscript_sets[0]


def test_resolve_bundle_backed_keeps_users_loose_video(tmp_path):
    """The user's own real video file (their chosen resolution/variant) is
    preserved even though the bundle wins on haptics."""
    bundle_dir = _make_bundle_tree(tmp_path / "Scene.output")
    entry = _loose_entry(tmp_path, bundle_path=str(bundle_dir))

    result = ControlWindow._resolve_bundle_backed(None, entry)

    assert result.videos == entry.videos


def test_resolve_bundle_backed_preserves_scene_identity(tmp_path):
    """name/folder_path must stay the scanned folder's, not the bundle
    cache's — pins persist against the scene folder."""
    bundle_dir = _make_bundle_tree(tmp_path / "Scene.output")
    entry = _loose_entry(tmp_path, bundle_path=str(bundle_dir))

    result = ControlWindow._resolve_bundle_backed(None, entry)

    assert result.name == entry.name
    assert result.folder_path == entry.folder_path


def test_resolve_bundle_backed_falls_back_when_bundle_unreadable(tmp_path):
    entry = _loose_entry(tmp_path, bundle_path=str(tmp_path / "does-not-exist.output"))
    result = ControlWindow._resolve_bundle_backed(None, entry)
    assert result is entry


def test_resolve_bundle_backed_falls_back_when_bundle_has_no_haptics(tmp_path):
    # A bundle dir that exists but carries no funscripts at all.
    empty_bundle = tmp_path / "Scene.output"
    empty_bundle.mkdir()
    (empty_bundle / "manifest.ffmeta").write_text(
        json.dumps({"stem": "Scene", "media": {}}), encoding="utf-8",
    )
    entry = _loose_entry(tmp_path, bundle_path=str(empty_bundle))

    result = ControlWindow._resolve_bundle_backed(None, entry)

    assert result is entry  # unreadable/no-haptics bundle -> keep the loose card


# ── _on_stim_folder_scanned ──────────────────────────────────────────────────

@pytest.fixture
def control_window(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    win = ControlWindow()
    # The real reload re-launches players against the SyncEngine/mpv — out
    # of scope for this guard, and no scene has actually been Launched in
    # these tests. Stub it so we can assert on the state mutation alone.
    monkeypatch.setattr(win, "_reload_current_scene", lambda: None)
    yield win
    # Deliberately no win.close() — see module docstring.


def _scene(name: str) -> SceneCatalogEntry:
    return SceneCatalogEntry(folder_path=f"/scenes/{name}", name=name)


def test_stim_folder_scanned_applies_when_scene_unchanged(control_window):
    win = control_window
    entry = _scene("Scene A")
    win._current_entry = entry
    win._current_choices = SelectionChoices()
    win._stim_scan_target_entry = entry  # the scan was launched for THIS entry

    fset = FunscriptSet(base_stem="Scene A", channels={"alpha": "/x/a.funscript"})
    win._on_stim_folder_scanned("/x/a.funscript", fset)

    assert fset in win._current_entry.funscript_sets
    assert win._current_choices.funscript_set is fset
    assert win._current_choices.audio is None
    assert win._stim_browse_btn.isEnabled() is True


def test_stim_folder_scanned_drops_result_for_superseded_scene(control_window):
    win = control_window
    original_entry = _scene("Scene A")
    win._stim_scan_target_entry = original_entry  # scan was launched for Scene A

    # User picked a different scene before the scan returned.
    new_entry = _scene("Scene B")
    win._current_entry = new_entry
    original_choices = SelectionChoices()
    win._current_choices = original_choices

    fset = FunscriptSet(base_stem="Scene A", channels={"alpha": "/x/a.funscript"})
    win._on_stim_folder_scanned("/x/a.funscript", fset)

    assert fset not in new_entry.funscript_sets
    assert win._current_choices is original_choices  # untouched
    assert win._stim_browse_btn.isEnabled() is True  # still re-enables


def test_stim_folder_scanned_none_result_does_not_mutate_state(control_window):
    win = control_window
    entry = _scene("Scene A")
    win._current_entry = entry
    original_choices = SelectionChoices()
    win._current_choices = original_choices
    win._stim_scan_target_entry = entry

    win._on_stim_folder_scanned("/x/bad.funscript", None)  # scan failed to classify

    assert entry.funscript_sets == []
    assert win._current_choices is original_choices
    assert win._stim_browse_btn.isEnabled() is True


def test_stim_folder_scanned_no_current_scene_does_not_raise(control_window):
    win = control_window
    win._current_entry = None
    win._current_choices = None
    win._stim_scan_target_entry = None

    fset = FunscriptSet(base_stem="Scene A", channels={"alpha": "/x/a.funscript"})
    win._on_stim_folder_scanned("/x/a.funscript", fset)  # Close landed mid-scan

    assert win._stim_browse_btn.isEnabled() is True


def test_stim_folder_scanned_does_not_duplicate_existing_set(control_window):
    win = control_window
    existing = FunscriptSet(base_stem="Scene A", channels={"alpha": "/old.funscript"})
    entry = SceneCatalogEntry(
        folder_path="/scenes/Scene A", name="Scene A", funscript_sets=[existing],
    )
    win._current_entry = entry
    win._current_choices = SelectionChoices()
    win._stim_scan_target_entry = entry

    rescanned = FunscriptSet(base_stem="Scene A", channels={"alpha": "/x/a.funscript"})
    win._on_stim_folder_scanned("/x/a.funscript", rescanned)

    # Same base_stem already present -> not appended a second time.
    assert entry.funscript_sets == [existing]
    assert win._current_choices.funscript_set is rescanned


# ── Close tears down the stim-audio mirror ───────────────────────────────────
#
# Dogfood 2026-08-29 (sound-file scenes): after closing the players, Play was
# still enabled and pressing it resumed e-stim on the Haptic 2 dongle with no
# window open and nothing on screen saying anything was running. _close_players
# terminated every slot and the scene-audio mirror but never the stim-audio
# mirror, and that mirror counts toward the engine's active list.

class _FakeMirror:
    """Stands in for the headless mpv that mirrors H1's sound file to H2."""

    def __init__(self) -> None:
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True


def test_close_players_terminates_the_stim_audio_mirror(control_window):
    win = control_window
    mirror = _FakeMirror()
    win._engine._stim_audio_mirror = mirror

    win._close_players()

    assert mirror.terminated, "e-stim mirror survived Close"
    assert win._engine._stim_audio_mirror is None


def test_close_players_leaves_nothing_playable_behind(control_window):
    """The user-visible half: Play must go dead after Close."""
    win = control_window
    win._engine._stim_audio_mirror = _FakeMirror()
    win._engine._scene_audio_mirror = _FakeMirror()

    win._close_players()

    assert not win._engine.has_active_players()
    assert not win._btn_play.isEnabled()
    assert win._btn_play.text() == "▶  Play"
