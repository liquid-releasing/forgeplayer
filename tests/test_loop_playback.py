# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Loop-the-scene: the overlay button, and the end-of-file restart.

Loop is deliberately SESSION-wide rather than per-window — the slots share one
timeline, so a per-window loop would restart one screen while the others ran
on. These tests pin that (one click updates every open window), the echo guard
that keeps the mirroring from bouncing between windows, and the latch that
stops one end-of-file from firing a burst of restarts on successive poll ticks.
"""
from __future__ import annotations

import pytest

# python-mpv raises OSError (not ImportError) at import time when libmpv isn't
# on the loader path, and it is reached transitively through PlayerWindow ->
# SyncEngine. Without this guard that OSError aborts collection of the WHOLE
# suite. See tests/test_control_window.py for the same guard.
try:
    from app.player_window import PlayerWindow
except OSError as exc:  # pragma: no cover - runner without libmpv
    pytest.skip(f"libmpv unavailable: {exc}", allow_module_level=True)


class _FakeEngine:
    """PlayerWindow only touches the engine for transport polling."""

    def has_active_players(self) -> bool:
        return False

    def is_paused(self) -> bool:
        return True

    def get_position(self) -> float:
        return 0.0

    def get_duration(self) -> float:
        return 0.0


def _player(qapp) -> PlayerWindow:
    win = PlayerWindow(0, _FakeEngine())
    win._timer.stop()          # no polling needed; keeps the test quiet
    return win


# ── the button itself ────────────────────────────────────────────────────────

def test_loop_button_sits_immediately_left_of_console(qapp):
    """The user asked for it there, and it's the discoverable spot — the two
    session-level controls sit together at the right end of the bar."""
    win = _player(qapp)
    bar = win._btn_loop.parent().layout()
    order = [bar.itemAt(i).widget() for i in range(bar.count())]
    assert order.index(win._btn_loop) == order.index(win._btn_console) - 1


def test_loop_button_starts_unchecked_and_is_checkable(qapp):
    win = _player(qapp)
    assert win._btn_loop.isCheckable()
    assert not win._btn_loop.isChecked()


def test_clicking_loop_reports_intent(qapp):
    seen: list[bool] = []
    win = _player(qapp)
    win.loop_toggled.connect(seen.append)

    win._btn_loop.setChecked(True)
    win._btn_loop.setChecked(False)

    assert seen == [True, False]


def test_mirroring_state_onto_a_window_does_not_re_emit(qapp):
    """set_loop_enabled is how ControlWindow pushes the session value onto
    every window. If that re-emitted, two open windows would bounce the
    toggle back and forth at each other."""
    seen: list[bool] = []
    win = _player(qapp)
    win.loop_toggled.connect(seen.append)

    win.set_loop_enabled(True)

    assert win._btn_loop.isChecked()
    assert seen == []


def test_echo_guard_is_released_even_if_setchecked_raises(qapp):
    """A stuck guard would silently deafen the button for the rest of the
    session, so the reset lives in a finally."""
    win = _player(qapp)

    class _Boom(Exception):
        pass

    def _explode(_checked):
        raise _Boom

    win._btn_loop.setChecked = _explode
    with pytest.raises(_Boom):
        win.set_loop_enabled(True)

    assert win._loop_echo_guard is False


# ── the restart, driven from ControlWindow's poll ────────────────────────────

class _LoopHost:
    """The loop half of ControlWindow, with the real methods bound to it.

    Constructing a ControlWindow spins up mpv and probes audio hardware; this
    exercises the exact functions under test against fake engine state.
    """

    def __init__(self, *, at_end: bool, active: bool = True):
        from app.control_window import ControlWindow

        self._loop_enabled = False
        self._loop_restart_pending = False
        self._player_windows = []
        self.seeks: list[float] = []
        self.played = 0
        self._at_end = at_end
        self._active = active

        cls = ControlWindow
        self._on_loop_toggled = cls._on_loop_toggled.__get__(self)
        self._restart_for_loop = cls._restart_for_loop.__get__(self)
        # The REAL method, not a copy of it — _poll does nothing here but
        # call this, so a change to the loop rule can't pass these tests
        # while behaving differently in the app.
        self.poll_once = cls._maybe_loop_restart.__get__(self)

        host = self

        class _Engine:
            def has_active_players(self):
                return host._active

            def at_end_of_file(self):
                return host._at_end

            def play_all(self):
                host.played += 1

        self._engine = _Engine()

    # stands in for the enveloped seek; asserts we route through it, not
    # straight to seek_all
    def _seek_with_envelope(self, pos: float) -> None:
        self.seeks.append(pos)


def test_scene_at_end_does_not_restart_when_loop_is_off():
    host = _LoopHost(at_end=True)
    host.poll_once()
    assert host.seeks == []
    assert host.played == 0


def test_scene_at_end_restarts_and_resumes_when_loop_is_on():
    host = _LoopHost(at_end=True)
    host._loop_enabled = True

    host.poll_once()

    # keep_open leaves mpv paused on the last frame, so a seek alone would
    # sit there frozen at 0:00 — play_all is what actually resumes it.
    assert host.seeks == [0.0]
    assert host.played == 1


def test_restart_goes_through_the_seek_envelope():
    """end -> start is the largest discontinuity in the scene; splicing it
    raw is the pop the v0.0.16 envelope work removed."""
    host = _LoopHost(at_end=True)
    host._loop_enabled = True
    host.poll_once()
    assert host.seeks == [0.0]      # _seek_with_envelope, not seek_all


def test_one_end_of_file_restarts_exactly_once():
    """eof-reached stays set until the seek lands, and _poll keeps ticking."""
    host = _LoopHost(at_end=True)
    host._loop_enabled = True

    for _ in range(5):
        host.poll_once()

    assert host.seeks == [0.0]
    assert host.played == 1


def test_latch_rearms_once_playback_leaves_the_end():
    host = _LoopHost(at_end=True)
    host._loop_enabled = True
    host.poll_once()

    host._at_end = False            # the restart landed; playing again
    host.poll_once()
    assert host._loop_restart_pending is False

    host._at_end = True             # reached the end a second time
    host.poll_once()
    assert host.seeks == [0.0, 0.0]
    assert host.played == 2


def test_turning_loop_off_clears_a_pending_restart():
    """Otherwise the cleared latch could fire one more restart after the
    user had already switched looping off."""
    host = _LoopHost(at_end=True)
    host._loop_enabled = True
    host.poll_once()
    assert host._loop_restart_pending is True

    host._on_loop_toggled(False)

    assert host._loop_restart_pending is False
    host.poll_once()
    assert host.seeks == [0.0]      # no second restart


def test_no_restart_when_no_players_are_open():
    host = _LoopHost(at_end=True, active=False)
    host._loop_enabled = True
    host.poll_once()
    assert host.seeks == []


def test_toggle_mirrors_to_every_open_window(qapp):
    host = _LoopHost(at_end=False)
    a, b = _player(qapp), _player(qapp)
    host._player_windows = [a, None, b]

    host._on_loop_toggled(True)

    assert host._loop_enabled is True
    assert a._btn_loop.isChecked()
    assert b._btn_loop.isChecked()


def test_repeat_toggle_of_the_same_value_is_a_no_op(qapp):
    host = _LoopHost(at_end=True)
    host._loop_enabled = True
    host._loop_restart_pending = True

    host._on_loop_toggled(True)

    # must not clear the in-flight latch — that would double-restart
    assert host._loop_restart_pending is True


# ── SyncEngine.at_end_of_file ────────────────────────────────────────────────
#
# The safety-critical direction is a FALSE POSITIVE: reporting "finished" when
# playback is mid-scene would make loop yank the user back to 0:00. Every
# uncertain reading must therefore come back False, never True.

from app.sync_engine import SyncEngine  # noqa: E402


class _FakePlayer:
    def __init__(self, eof):
        self._eof = eof

    @property
    def eof_reached(self):
        if isinstance(self._eof, Exception):
            raise self._eof
        return self._eof


def test_at_end_of_file_is_false_with_no_players():
    assert SyncEngine().at_end_of_file() is False


def test_at_end_of_file_is_false_when_mpv_reports_none():
    """mpv returns None for eof-reached before a file is loaded — verified
    against python-mpv, which maps the attribute to the 'eof-reached'
    property. bool(None) is False, but pin it: a True here would restart a
    scene that had not even started."""
    e = SyncEngine()
    e._players[0] = _FakePlayer(None)
    assert e.at_end_of_file() is False


def test_at_end_of_file_is_false_when_the_property_raises():
    e = SyncEngine()
    e._players[0] = _FakePlayer(RuntimeError("mpv is shutting down"))
    assert e.at_end_of_file() is False


def test_at_end_of_file_is_true_only_when_mpv_says_so():
    e = SyncEngine()
    e._players[0] = _FakePlayer(True)
    assert e.at_end_of_file() is True

    e._players[0] = _FakePlayer(False)
    assert e.at_end_of_file() is False
