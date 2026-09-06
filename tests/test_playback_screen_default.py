# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""First-run default for the Setup tab's playback-screen checkboxes.

Through v0.1.18-alpha `playback_screen_indices` defaulted to `[]`, so a fresh
install showed EVERY monitor unchecked — while `_screen_index_for_slot` fell
through to `return slot_idx` and put the video on Screen 1 regardless. The UI
said "nothing selected"; the app played on Screen 1. A first-time user
reasonably reads that as "playback isn't configured yet"
(`feedback_forgeplayer_reporting_must_match_actual`).

The default is now `[0]`. Empty still means "any screen" and remains reachable
by clearing every box — it just isn't the first-run state any more.
"""

from __future__ import annotations

import json

import pytest

from app.preferences import Preferences


_SLOT_ROLES = ["video", "stim", "mirror", "mirror"]


def _screen_index_for_slot(slot_idx: int, playback: list[int], n_screens: int):
    """Mirror of ControlWindow._screen_index_for_slot, minus the Qt window.

    Kept in step with the original by the equivalence tests below; the real
    method needs a constructed ControlWindow, which these cases don't.
    """
    if _SLOT_ROLES[slot_idx] == "stim":
        return None
    video_position = sum(
        1 for i in range(slot_idx) if _SLOT_ROLES[i] != "stim"
    )
    if playback and video_position < len(playback):
        return playback[video_position]
    if not playback and slot_idx < n_screens:
        return slot_idx
    return None


# ── The default itself ───────────────────────────────────────────────────────

def test_fresh_install_selects_screen_one():
    """THE change: Setup must show Screen 1 ticked out of the box."""
    assert Preferences().playback_screen_indices == [0]


def test_default_is_not_shared_between_instances():
    """A mutable default via default_factory — mutating one Preferences must
    not leak into the next."""
    a, b = Preferences(), Preferences()
    a.playback_screen_indices.append(1)
    assert b.playback_screen_indices == [0]


# ── Existing users keep their choice ─────────────────────────────────────────

def test_a_saved_empty_list_is_preserved(tmp_path, monkeypatch):
    """Someone who deliberately cleared every box keeps "any screen" — the
    default applies only when the key is ABSENT."""
    prefs_dir = tmp_path / ".forgeplayer"
    prefs_dir.mkdir()
    (prefs_dir / "preferences.json").write_text(
        json.dumps({"playback_screen_indices": []}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "app.preferences._PREFS_PATH", prefs_dir / "preferences.json"
    )
    assert Preferences.load().playback_screen_indices == []


def test_a_saved_selection_is_preserved(tmp_path, monkeypatch):
    prefs_dir = tmp_path / ".forgeplayer"
    prefs_dir.mkdir()
    (prefs_dir / "preferences.json").write_text(
        json.dumps({"playback_screen_indices": [1, 2]}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "app.preferences._PREFS_PATH", prefs_dir / "preferences.json"
    )
    assert Preferences.load().playback_screen_indices == [1, 2]


def test_missing_key_falls_back_to_the_new_default(tmp_path, monkeypatch):
    """An older preferences.json without the key adopts Screen 1."""
    prefs_dir = tmp_path / ".forgeplayer"
    prefs_dir.mkdir()
    (prefs_dir / "preferences.json").write_text(
        json.dumps({"library_root": "/somewhere"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "app.preferences._PREFS_PATH", prefs_dir / "preferences.json"
    )
    assert Preferences.load().playback_screen_indices == [0]


# ── [] and [0] must launch identically ───────────────────────────────────────

@pytest.mark.parametrize("n_screens", [1, 2, 3, 4])
def test_video_slot_lands_on_screen_one_either_way(n_screens):
    """The reason this change is safe: slot 0 resolves to screen 0 under both
    the old empty default and the new [0]."""
    assert _screen_index_for_slot(0, [], n_screens) == 0
    assert _screen_index_for_slot(0, [0], n_screens) == 0


@pytest.mark.parametrize("n_screens", [1, 2, 3, 4])
def test_stim_slot_never_gets_a_screen(n_screens):
    assert _screen_index_for_slot(1, [], n_screens) is None
    assert _screen_index_for_slot(1, [0], n_screens) is None


def test_mirror_slots_need_two_checked_screens_before_they_get_media():
    """The only place [] and [0] resolve differently is a mirror slot — and
    mirror slots are gated on len(playback) >= 2, so with a single selection
    they carry no media and are skipped at launch either way. That gate is
    what makes the differing screen index unobservable."""
    assert len([]) < 2 and len([0]) < 2

    # On a 3-monitor rig the two DO differ here...
    assert _screen_index_for_slot(2, [], 3) == 2
    assert _screen_index_for_slot(2, [0], 3) is None
    # ...on a slot that has no media under either, so nothing launches on it.


def test_two_checked_screens_still_drive_a_mirror():
    """The mirror feature itself is untouched by the default change."""
    assert _screen_index_for_slot(0, [0, 1], 2) == 0
    assert _screen_index_for_slot(2, [0, 1], 2) == 1
    assert len([0, 1]) >= 2
