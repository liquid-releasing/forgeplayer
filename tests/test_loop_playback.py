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

class _FakeButton:
    """Stands in for the console's Loop QPushButton (constructing the real
    ControlWindow would spin up mpv and probe audio hardware)."""

    def __init__(self):
        self.checked = False
        self.text = "Loop"

    def setChecked(self, value):   # noqa: N802 - Qt API shape
        self.checked = value

    def setText(self, value):      # noqa: N802 - Qt API shape
        self.text = value


class _LoopHost:
    """The loop half of ControlWindow, with the real methods bound to it.

    Constructing a ControlWindow spins up mpv and probes audio hardware; this
    exercises the exact functions under test against fake engine state.
    """

    def __init__(self, *, at_end: bool, active: bool = True,
                 paused: bool = True):
        from app.control_window import ControlWindow

        self._loop_enabled = False
        self._loop_restart_pending = False
        self._console_loop_echo_guard = False
        self._btn_loop = _FakeButton()
        self._player_windows = []
        self.seeks: list[float] = []
        self.played = 0
        self._at_end = at_end
        self._active = active
        self._paused = paused
        self._pending_cb = None

        cls = ControlWindow
        self._on_loop_toggled = cls._on_loop_toggled.__get__(self)
        self._restart_for_loop = cls._restart_for_loop.__get__(self)
        self._resume_after_loop_seek = cls._resume_after_loop_seek.__get__(self)
        self._paint_console_loop = cls._paint_console_loop.__get__(self)
        self._on_console_loop_clicked = (
            cls._on_console_loop_clicked.__get__(self)
        )
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

            def is_paused(self):
                return host._paused

            def play_all(self):
                host.played += 1
                host._paused = False

        self._engine = _Engine()

    def _seek_with_envelope(self, pos, on_seeked=None) -> None:
        """Stands in for the real enveloped seek — and, critically, models it
        as ASYNCHRONOUS.

        With stim live the real one ramps down for ~0.5 s and only then
        seeks, so it returns long before the position actually moves.
        Holding the callback here instead of running it inline is what makes
        these tests able to fail the way the app failed.
        """
        self.seeks.append(pos)
        self._pending_cb = on_seeked

    def land_seek(self) -> None:
        """The deferred seek finally executes."""
        cb, self._pending_cb = self._pending_cb, None
        self._at_end = False
        if cb is not None:
            cb()


def test_scene_at_end_does_not_restart_when_loop_is_off():
    host = _LoopHost(at_end=True)
    host.poll_once()
    assert host.seeks == []
    assert host.played == 0


def test_scene_at_end_restarts_and_resumes_when_loop_is_on():
    host = _LoopHost(at_end=True)
    host._loop_enabled = True

    host.poll_once()
    host.land_seek()

    # keep_open leaves mpv paused on the last frame, so a seek alone would
    # sit there frozen at 0:00 — play_all is what actually resumes it.
    assert host.seeks == [0.0]
    assert host.played == 1


def test_resume_waits_for_the_seek_to_land():
    """THE 2026-08-30 BUG. The enveloped seek returns ~0.5s before it moves
    the position; resuming inline landed while mpv was still parked at EOF,
    where unpausing does nothing, and the scene rewound but never played.
    Nothing may resume playback until the seek has actually executed."""
    host = _LoopHost(at_end=True)
    host._loop_enabled = True

    host.poll_once()
    assert host.seeks == [0.0]
    assert host.played == 0, "resumed before the seek landed"

    host.land_seek()
    assert host.played == 1


def test_catch_up_resumes_if_the_seek_landed_still_paused():
    """mpv applies a seek asynchronously even after the command is issued,
    so the on_seeked resume can still be swallowed. The next tick notices
    playback is parked and re-issues it."""
    host = _LoopHost(at_end=True)
    host._loop_enabled = True
    host.poll_once()

    # seek lands, but the resume is lost (mpv still at EOF when it arrived)
    host._pending_cb = None
    host._at_end = False
    assert host.played == 0

    host.poll_once()
    assert host.played == 1
    assert host._paused is False


def test_catch_up_fires_at_most_once():
    """It must never fight a user who deliberately pauses after a wrap."""
    host = _LoopHost(at_end=True)
    host._loop_enabled = True
    host.poll_once()
    host._pending_cb = None
    host._at_end = False

    host.poll_once()            # catch-up resumes
    host._paused = True         # user pauses
    host.poll_once()
    host.poll_once()

    assert host.played == 1     # not resumed out from under them


def test_no_catch_up_when_playback_already_resumed():
    host = _LoopHost(at_end=True)
    host._loop_enabled = True
    host.poll_once()
    host.land_seek()            # on_seeked resumed it
    assert host.played == 1

    host.poll_once()            # latch clears; no second play
    assert host.played == 1


def test_switching_loop_on_at_the_end_restarts_immediately():
    """Dogfood 2026-08-30 asked for this explicitly: flipping Loop on while
    parked on the last frame should restart rather than sit dead."""
    host = _LoopHost(at_end=True)

    host._on_loop_toggled(True)
    host.poll_once()

    assert host.seeks == [0.0]


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


def test_latch_rearms_once_playback_leaves_the_end():
    host = _LoopHost(at_end=True)
    host._loop_enabled = True
    host.poll_once()
    host.land_seek()                # restart landed; playing again

    host.poll_once()
    assert host._loop_restart_pending is False

    host._at_end = True             # reached the end a second time
    host.poll_once()
    host.land_seek()
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


# ── console button ───────────────────────────────────────────────────────────
#
# The overlay bar is hidden until you click the video, and loop persists across
# scene changes — so without a console control a scene can be looping with
# nothing on screen explaining why.

def test_console_button_mirrors_a_toggle_from_an_overlay(qapp):
    host = _LoopHost(at_end=False)
    win = _player(qapp)
    host._player_windows = [win]

    win._btn_loop.setChecked(True)      # click on the overlay
    host._on_loop_toggled(True)         # ControlWindow receives it

    assert host._btn_loop.checked is True
    assert host._btn_loop.text == "✓ Loop"


def test_console_button_drives_the_session_and_the_overlays(qapp):
    host = _LoopHost(at_end=False)
    win = _player(qapp)
    host._player_windows = [win]

    host._on_console_loop_clicked(True)

    assert host._loop_enabled is True
    assert win._btn_loop.isChecked()
    assert win._btn_loop.text() == "✓ Loop"


def test_console_mirror_does_not_re_enter_as_a_click():
    """Painting the console button emits `toggled`; without the guard that
    would re-enter _on_loop_toggled and bounce between the two controls."""
    host = _LoopHost(at_end=False)
    host._loop_enabled = True

    host._paint_console_loop(True)

    # guard released, and no spurious state change
    assert host._console_loop_echo_guard is False
    assert host._loop_enabled is True


def test_console_guard_is_released_even_if_the_button_raises():
    host = _LoopHost(at_end=False)

    class _Boom(Exception):
        pass

    def _explode(_v):
        raise _Boom

    host._btn_loop.setChecked = _explode
    with pytest.raises(_Boom):
        host._paint_console_loop(True)

    assert host._console_loop_echo_guard is False
