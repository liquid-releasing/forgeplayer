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

# python-mpv raises OSError (not ImportError) at import time when libmpv isn't
# on the loader path, and it is reached transitively through PlayerWindow ->
# SyncEngine. Without this guard that OSError aborts collection of the WHOLE
# suite, so a runner missing the library turns 451 passing tests into a red
# build. A genuinely missing libmpv still fails the release: PyInstaller can't
# bundle without it.
try:
    from app.control_window import ControlWindow
except OSError as exc:  # pragma: no cover - runner without libmpv
    pytest.skip(f"libmpv unavailable: {exc}", allow_module_level=True)
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
    # ControlWindow.__init__ probes real hardware: list_audio_devices spins up
    # a live mpv instance to read audio_device_list. On a headless runner that
    # segfaults the interpreter — and its own `except Exception` can't catch a
    # SIGSEGV, so the whole suite dies. Nothing here tests device discovery, so
    # hand the constructor a fixed list instead of the machine's real one.
    monkeypatch.setattr(
        "app.sync_engine.SyncEngine.list_audio_devices",
        staticmethod(lambda include_hdmi=False: [
            {"name": "fake-scene", "description": "Fake Scene Output"},
            {"name": "fake-haptic", "description": "Fake Haptic Dongle"},
        ]),
    )
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


# ── Seek envelope covers mpv-backed stim ─────────────────────────────────────
#
# A scene whose stim is a pre-rendered sound file plays through mpv, not a
# StimAudioStream, so the seek envelope used to skip it entirely and the seek
# landed raw — the pop on sound-file scenes (user report 2026-08-29).

class _FakeMpv:
    def __init__(self, volume: float = 100.0) -> None:
        self.volume = volume


def _sound_file_scene(win, monkeypatch, *, mirror=True):
    """Wire the window up as if a sound-file stim scene were playing."""
    stim = _FakeMpv()
    video = _FakeMpv()
    mirror_player = _FakeMpv() if mirror else None
    win._slot_data(1)["primary_dispatch"] = "audio_file"
    monkeypatch.setattr(
        win._engine, "player_for_slot",
        lambda i: {0: video, 1: stim}.get(i),
    )
    monkeypatch.setattr(win._engine, "stim_audio_mirror", lambda: mirror_player)
    monkeypatch.setattr(win._engine, "has_active_players", lambda: True)
    monkeypatch.setattr(win._engine, "is_paused", lambda: False)
    return stim, video, mirror_player


def test_mpv_stim_players_finds_the_sound_file_outputs(control_window, monkeypatch):
    win = control_window
    stim, video, mirror = _sound_file_scene(win, monkeypatch)

    found = win._mpv_stim_players()

    assert stim in found and mirror in found
    assert video not in found, "scene audio must not be ducked on every seek"


def test_mpv_stim_players_ignores_synth_dispatch(control_window, monkeypatch):
    """A funscript scene drives StimAudioStream; mpv has no stim to fade."""
    win = control_window
    _sound_file_scene(win, monkeypatch, mirror=False)
    win._slot_data(1)["primary_dispatch"] = "funscript"

    assert win._mpv_stim_players() == []


def test_mpv_stim_players_always_include_the_mirror(control_window, monkeypatch):
    """The H2 mirror IS stim through mpv, whatever H1 happens to dispatch —
    if it exists at all it's playing a sound file to the dongle, so it fades."""
    win = control_window
    _stim, _video, mirror = _sound_file_scene(win, monkeypatch)
    win._slot_data(1)["primary_dispatch"] = "funscript"

    assert win._mpv_stim_players() == [mirror]


def test_seek_fades_mpv_stim_before_seeking(control_window, monkeypatch):
    win = control_window
    stim, _video, mirror = _sound_file_scene(win, monkeypatch)
    seeks: list[float] = []
    monkeypatch.setattr(win._engine, "seek_all", lambda pos: seeks.append(pos))

    win._seek_with_envelope(42.0)

    assert seeks == [], "the seek must wait for the fade, not fire immediately"
    for _ in range(200):                     # drive the fade to silence
        win._tick_mpv_envelope()
    assert stim.volume == 0
    assert mirror.volume == 0


def test_seek_without_any_stim_still_seeks_immediately(control_window, monkeypatch):
    """No stim of either kind → nothing to fade, so don't add latency."""
    win = control_window
    _sound_file_scene(win, monkeypatch, mirror=False)
    win._slot_data(1)["primary_dispatch"] = "funscript"
    seeks: list[float] = []
    monkeypatch.setattr(win._engine, "seek_all", lambda pos: seeks.append(pos))

    win._seek_with_envelope(7.5)

    assert seeks == [7.5]


def test_close_releases_a_fade_in_flight(control_window, monkeypatch):
    """Close mid-seek must not leave a ducked gain on a reused instance."""
    win = control_window
    stim, _video, _mirror = _sound_file_scene(win, monkeypatch)
    win._seek_with_envelope(10.0)
    for _ in range(20):
        win._tick_mpv_envelope()
    assert stim.volume < 100

    win._close_players()

    assert stim.volume == 100
    assert not win._mpv_envelope.tracks_anything()


def test_fade_resets_when_the_stim_players_disappear(control_window, monkeypatch):
    """Scene changed (or closed) between ramp-down and ramp-up: the envelope
    must reset, not stay parked at a partial gain the next seek would ramp
    from."""
    win = control_window
    stim, _video, _mirror = _sound_file_scene(win, monkeypatch)
    win._request_mpv_stim_gain([stim], 0.0)
    for _ in range(20):
        win._tick_mpv_envelope()
    assert win._mpv_envelope.gain < 1.0

    win._request_mpv_stim_gain([], 1.0)

    assert win._mpv_envelope.gain == 1.0
    assert not win._mpv_envelope.tracks_anything()
    assert stim.volume == 100


# ── Audio device role pickers (2026-09-05) ───────────────────────────────────
#
# Monitor / TV HDMI endpoints used to be filtered out of every picker on the
# theory that they're speakerless phantoms. Dogfooding on this rig proved the
# heuristic can't be made to work: an Odyssey G95NC (no speakers — Samsung
# didn't fit any) and a 12.3FHD (real, audible speakers) are INDISTINGUISHABLE
# from software. Both declare audio in EDID, both get a Windows endpoint, both
# accept an mpv stream without error; only one makes a sound. So the app stops
# guessing — it offers both, labels them, and lets the Test button settle it.

def _combo_device_ids(combo) -> list[str]:
    return [combo.itemData(i) for i in range(combo.count())]


@pytest.fixture
def control_window_with_display(qapp, monkeypatch, tmp_path):
    """A ControlWindow whose device list contains a display endpoint."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(
        "app.sync_engine.SyncEngine.list_audio_devices",
        staticmethod(lambda include_hdmi=False: [
            {"name": "auto", "description": "Autoselect device"},
            {"name": "spk", "description": "Speakers (Realtek(R) Audio)"},
            {"name": "tv", "description": "LG TV (NVIDIA High Definition Audio)"},
        ]),
    )
    win = ControlWindow()
    monkeypatch.setattr(win, "_reload_current_scene", lambda: None)
    yield win
    # No win.close() — see module docstring.


def test_scene_pickers_offer_display_outputs(control_window_with_display):
    """The feature: a TV on HDMI must be selectable for scene audio."""
    win = control_window_with_display
    for combo in (win._setup_scene_combo, win._setup_scene_secondary_combo):
        ids = _combo_device_ids(combo)
        assert "tv" in ids
        assert "spk" in ids
        assert "auto" not in ids  # mpv meta-entry never reaches a picker


def test_haptic_pickers_exclude_display_outputs(control_window_with_display):
    """A display is never e-stim hardware — those combos stay narrow."""
    win = control_window_with_display
    for combo in (win._setup_haptic1_combo, win._setup_haptic2_combo):
        ids = _combo_device_ids(combo)
        assert "spk" in ids
        assert "tv" not in ids


def test_display_outputs_are_labelled(control_window_with_display):
    """Silent phantoms still exist; the label is what makes one recognizable
    before the user picks it."""
    win = control_window_with_display
    labels = dict(win._audio_devices)
    assert "monitor / TV (HDMI)" in labels["tv"]
    assert "monitor / TV (HDMI)" not in labels["spk"]


def test_saved_display_device_still_resolves_a_label(control_window_with_display):
    """`_audio_devices` is the FULL list, so a display device chosen for scene
    audio reads as itself on the Live tab — not "(unavailable — reselect in
    Setup)", which is what a haptic-only device list would have produced."""
    win = control_window_with_display
    assert win._audio_device_label("tv") == dict(win._audio_devices)["tv"]


def test_refresh_preserves_the_per_role_split(control_window_with_display):
    """Refresh rebuilds both lists; the haptic combos must not silently gain
    display devices on the rebuild path."""
    win = control_window_with_display
    win._on_refresh_audio_devices()
    assert "tv" in _combo_device_ids(win._setup_scene_combo)
    assert "tv" not in _combo_device_ids(win._setup_haptic1_combo)
    assert "tv" not in _combo_device_ids(win._setup_haptic2_combo)

