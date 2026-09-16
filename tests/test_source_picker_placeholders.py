# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
r"""A loaded scene must never be described as "no scene loaded".

Dogfood 2026-09-16. The tester opened a card from `G:\funscripts\ES`, the
video played, the title bar read "Now playing: ES / Everything Makes You Fckin
Pump Wezzam PMV 60 AV1 P4" - and the Stim source picker said
"- load a scene -". They reasonably read that as the folder's funscripts
failing to load.

They hadn't. That folder holds three encodes of one work, so the title splitter
produced three cards, and the five funscripts attached to the card whose stem
matched them (`PMV_4K@60_AV1`) rather than to the `.mkv` (`PMV_60_AV1-P4-RF35`)
the tester opened. That card really has no stim source of its own - which is a
grouping question, logged for beta.

What was plainly wrong was the message. Both source pickers used one
placeholder for two different states, and only one of them is "no scene":

    entry is None                 -> nothing is loaded
    entry loaded, no sources      -> loaded, but nothing of this kind here

The second needs to name the situation and point at Browse, which sits beside
the combo and can reach any folder on disk.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QComboBox

from app.control_window import ControlWindow
from app.library.catalog import AudioVariant, FunscriptSet, SceneCatalogEntry, VideoVariant


def _win(entry, choices=None):
    """A stub carrying only what _refresh_source_combos touches."""
    win = ControlWindow.__new__(ControlWindow)
    win._setup_video_source_combo = QComboBox()
    win._setup_stim_source_combo = QComboBox()
    win._current_entry = entry
    win._current_choices = choices
    win._stim_source_path_label = None       # _set_source_path_label no-ops
    return win


def _refresh(win):
    ControlWindow._refresh_source_combos(win)
    return win._setup_video_source_combo, win._setup_stim_source_combo


def _scene(tmp_path, *, video=True, funscript=False, audio=False):
    folder = tmp_path / "ES"
    folder.mkdir(exist_ok=True)
    entry = SceneCatalogEntry(folder_path=str(folder), name="ES")
    if video:
        entry.videos.append(VideoVariant(path=str(folder / "clip.mkv")))
    if funscript:
        entry.funscript_sets.append(
            FunscriptSet(base_stem="clip", channels={"alpha": str(folder / "a.funscript")})
        )
    if audio:
        entry.audio_tracks.append(AudioVariant(path=str(folder / "stim.mp3")))
    return entry


# ── The reported message ─────────────────────────────────────────────────────

def test_a_loaded_scene_with_no_stim_source_does_not_say_load_a_scene(qapp,
                                                                      tmp_path):
    """THE reported wording. The scene is loaded and playing."""
    _, sc = _refresh(_win(_scene(tmp_path)))

    assert sc.currentText() != "— load a scene —"
    assert "Browse" in sc.currentText(), (
        "the message should point at the control that fixes it"
    )


def test_no_scene_at_all_still_says_load_a_scene(qapp):
    """The other state keeps its original, correct message."""
    _, sc = _refresh(_win(None))
    assert sc.currentText() == "— load a scene —"


def test_an_audio_only_scene_does_not_claim_no_scene_in_the_video_picker(qapp,
                                                                         tmp_path):
    """Same bug, same fix, other combo."""
    entry = _scene(tmp_path, video=False, audio=True)
    vc, _ = _refresh(_win(entry))

    assert vc.currentText() != "— load a scene —"
    assert "Browse" in vc.currentText()


def test_the_video_picker_still_says_load_a_scene_with_no_entry(qapp):
    vc, _ = _refresh(_win(None))
    assert vc.currentText() == "— load a scene —"


# ── Both placeholders stay unselectable ──────────────────────────────────────

@pytest.mark.parametrize("kwargs", [
    dict(video=True),                      # no stim source
    dict(video=False, audio=True),         # no video
])
def test_placeholders_are_disabled(qapp, tmp_path, kwargs):
    """They are statements, not choices - there is nothing to pick."""
    entry = _scene(tmp_path, **kwargs)
    vc, sc = _refresh(_win(entry))
    empty = vc if not entry.videos else sc
    assert empty.isEnabled() is False


def test_a_scene_with_sources_is_unaffected(qapp, tmp_path):
    """The normal case must still populate both combos."""
    entry = _scene(tmp_path, video=True, funscript=True)
    win = _win(entry, SimpleNamespace(video=entry.videos[0], audio=None,
                                      funscript_set=entry.funscript_sets[0]))
    vc, sc = _refresh(win)

    assert vc.isEnabled() and sc.isEnabled()
    assert "Browse" not in sc.currentText()
    assert sc.currentText().startswith("clip")
