# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Video / Stim source rows show WHERE the selected file came from.

Request 2026-09-13: "can we show the path to the sources underneath the video
source and stim source selection boxes? so the user can tell which ones have
been selected?"

Both combos label a selection by NAME — a variant label for video, a base stem
for a funscript set — neither of which says anything about location. That was
adequate while every source lived in the scene folder. It stopped being adequate
in this same release, when Browse gained the ability to load a funscript from any
directory on disk: two sets can share a stem and differ only by where they live.

The video row already had a confirm line, but it showed `os.path.basename()` —
the filename, with the folder only in the tooltip, which is precisely the part
that was invisible.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.control_window import ControlWindow


# ── _elide_path ──────────────────────────────────────────────────────────────

def test_short_paths_are_untouched():
    p = r"C:\short.mp4"
    assert ControlWindow._elide_path(p) == p


def test_long_paths_are_shortened_from_the_middle():
    p = (r"C:\Users\bruce\Projects\_lqr\my_scripts_elsewhere"
         r"\Victoriaoaks - Wet Dreams 1080p 30fps.alpha.funscript")
    out = ControlWindow._elide_path(p)
    assert len(out) <= 73
    assert "…" in out


def test_the_tail_survives_because_it_identifies_the_file():
    """Keeping the END is the whole point — the folder and filename identify a
    file, the drive letter does not."""
    p = "C:" + (r"\padpadpad" * 12) + r"\my_scripts_elsewhere\Target.funscript"
    out = ControlWindow._elide_path(p)
    assert out.endswith("Target.funscript")
    assert "my_scripts_elsewhere" in out


def test_a_head_is_kept_for_orientation():
    p = "C:" + (r"\padpadpad" * 12) + r"\Target.funscript"
    assert ControlWindow._elide_path(p).startswith("C:\\")


@pytest.mark.parametrize("limit", [20, 40, 72, 200])
def test_never_exceeds_the_limit(limit):
    p = "C:" + (r"\longdirname" * 30) + r"\File.funscript"
    assert len(ControlWindow._elide_path(p, limit=limit)) <= limit + 1


# ── _current_stim_source_path ────────────────────────────────────────────────

def _win(choices):
    """A bare object with just the attribute the method reads — constructing a
    real ControlWindow needs Qt and probes hardware."""
    # ControlWindow.__new__, not object.__new__ — Qt refuses the latter for
    # its own types ("not safe"). This skips __init__ entirely, which is the
    # point: the method under test reads one plain attribute and nothing Qt.
    w = ControlWindow.__new__(ControlWindow)
    w._current_choices = choices
    return w


def test_no_scene_has_no_path():
    assert _win(None)._current_stim_source_path() is None


def test_an_audio_pick_reports_its_own_file():
    choices = SimpleNamespace(
        audio=SimpleNamespace(path=r"C:\x\stim.mp3"), funscript_set=None,
    )
    assert _win(choices)._current_stim_source_path() == r"C:\x\stim.mp3"


def test_audio_wins_over_a_funscript_set():
    """Matches the dispatch order the combo itself reflects."""
    choices = SimpleNamespace(
        audio=SimpleNamespace(path=r"C:\x\stim.mp3"),
        funscript_set=SimpleNamespace(main_path=r"C:\y\s.funscript", channels={}),
    )
    assert _win(choices)._current_stim_source_path() == r"C:\x\stim.mp3"


def test_a_funscript_set_reports_its_main_track():
    choices = SimpleNamespace(
        audio=None,
        funscript_set=SimpleNamespace(main_path=r"C:\y\s.funscript", channels={}),
    )
    assert _win(choices)._current_stim_source_path() == r"C:\y\s.funscript"


def test_a_set_with_no_main_track_falls_back_to_a_channel():
    """THE normal case for a browsed e-stim export: all channels, no main track.
    Returning None here would leave the new label blank exactly when it is most
    useful — a set loaded from outside the scene folder."""
    choices = SimpleNamespace(
        audio=None,
        funscript_set=SimpleNamespace(
            main_path=None,
            channels={"beta": r"C:\z\s.beta.funscript",
                      "alpha": r"C:\z\s.alpha.funscript"},
        ),
    )
    got = _win(choices)._current_stim_source_path()
    # Deterministic: channels are consulted in sorted order, so alpha wins.
    assert got == r"C:\z\s.alpha.funscript"


def test_a_set_with_nothing_usable_reports_nothing():
    choices = SimpleNamespace(
        audio=None,
        funscript_set=SimpleNamespace(main_path=None, channels={"alpha": ""}),
    )
    assert _win(choices)._current_stim_source_path() is None


def test_silent_stim_reports_nothing():
    assert _win(
        SimpleNamespace(audio=None, funscript_set=None)
    )._current_stim_source_path() is None
