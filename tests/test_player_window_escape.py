# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Escape and the Console button on a player window (changed 2026-08-29).

Escape used to tear down every player — the same path as X and double-click.
With the console normally buried under fullscreen players, that made it the
only way back to the console, and it cost you your position every time (and
one accidental close during the dogfood pass). Escape now means "get me out of
this view": fullscreen drops to windowed, windowed raises the console. Closing
stays on X, double-click and the console's own Close button.

These construct a real PlayerWindow but never show() it fullscreen — Qt window
state is asserted through the same isFullScreen() the handler reads.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

# python-mpv raises OSError (not ImportError) at import time when libmpv isn't
# on the loader path, and it is reached transitively through PlayerWindow ->
# SyncEngine. Without this guard that OSError aborts collection of the WHOLE
# suite, so a runner missing the library turns 451 passing tests into a red
# build. A genuinely missing libmpv still fails the release: PyInstaller can't
# bundle without it.
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


def _escape(win: PlayerWindow) -> None:
    win.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    )


def test_escape_never_closes_the_session(qapp):
    win = _player(qapp)
    closes: list[int] = []
    win.close_all_requested.connect(lambda: closes.append(1))

    _escape(win)

    assert not closes, "Escape must not tear down the players"


def test_escape_while_windowed_raises_the_console(qapp):
    win = _player(qapp)
    raised: list[int] = []
    win.console_requested.connect(lambda: raised.append(1))

    _escape(win)

    assert raised == [1]


def test_escape_while_fullscreen_returns_to_windowed(qapp):
    win = _player(qapp)
    win.showFullScreen()
    raised: list[int] = []
    win.console_requested.connect(lambda: raised.append(1))
    assert win.isFullScreen()

    _escape(win)

    assert not win.isFullScreen()
    assert not raised, "first Escape leaves fullscreen; it doesn't jump the console"
    # No win.close() — closeEvent routes to the group teardown via
    # singleShot(0), and that pending emit would fire from a later test's
    # event loop against an already-collected window.


def test_console_button_asks_for_the_console(qapp):
    win = _player(qapp)
    raised: list[int] = []
    win.console_requested.connect(lambda: raised.append(1))

    win._btn_console.click()

    assert raised == [1]


def test_double_click_still_closes_everything(qapp):
    """The close affordances the user knows must keep working."""
    win = _player(qapp)
    closes: list[int] = []
    win.close_all_requested.connect(lambda: closes.append(1))

    win.mouseDoubleClickEvent(type("_Evt", (), {
        "button": lambda self: Qt.MouseButton.LeftButton,
        "accept": lambda self: None,
    })())
    qapp.processEvents()       # _request_close_all defers via singleShot(0)

    assert closes == [1]
