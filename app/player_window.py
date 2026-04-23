# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""PlayerWindow — borderless video window with embedded transport controls."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
)
from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QScreen

from app.debug_log import DebugLog
from app.sync_engine import SyncEngine
from app.widgets import ClickableSlider

_CTRL_HEIGHT = 48
_POLL_MS = 200


def _fmt_time(seconds: float) -> str:
    s = max(0, int(seconds))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class PlayerWindow(QWidget):
    """
    Borderless window that covers one monitor.

    Layout
    ------
      ┌────────────────────────────────────┐
      │  _video_widget  (mpv renders here) │  ← stretch
      ├────────────────────────────────────┤
      │  control bar (always visible)      │  ← 48 px
      └────────────────────────────────────┘

    mpv is embedded into *_video_widget* via its native window handle so the
    control bar stays outside the mpv render surface and is always interactive.
    """

    close_all_requested = Signal()

    def __init__(self, slot_index: int, engine: SyncEngine) -> None:
        super().__init__()
        self.slot_index = slot_index
        self._engine = engine
        self._seek_dragging = False
        # Set by ControlWindow._close_players before calling close() so the
        # user's closeEvent path doesn't re-enter the group-teardown signal.
        self._teardown_in_progress = False

        self.setWindowTitle(f"ForgePlayer {slot_index + 1}")
        self.setStyleSheet("background-color: black;")
        # Normal framed window — user gets drag/resize/close chrome in
        # windowed mode. Fullscreen mode hides the chrome via showFullScreen().
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(320, 180 + _CTRL_HEIGHT)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Video area — mpv embeds here ──────────────────────────────────────
        self._video_widget = QWidget()
        self._video_widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self._video_widget.setStyleSheet("background-color: black;")
        root.addWidget(self._video_widget, stretch=1)

        # ── Control bar ───────────────────────────────────────────────────────
        root.addWidget(self._build_ctrl())

        # ── Poll timer ────────────────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ── mpv handle ────────────────────────────────────────────────────────────

    def native_wid(self) -> int:
        """Native handle for the video area (must be called after show())."""
        return int(self._video_widget.winId())

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ctrl(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(_CTRL_HEIGHT)
        bar.setStyleSheet(
            "background-color: #111318; border-top: 1px solid #2a2d3e;"
        )

        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(8)

        # Slot label
        lbl = QLabel(f"S{self.slot_index + 1}")
        lbl.setFixedWidth(20)
        lbl.setStyleSheet("color: #9ba3c4; font-size: 10px;")
        h.addWidget(lbl)

        # Play/pause
        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedSize(32, 32)
        self._btn_play.setStyleSheet(
            "background: #ff4b4b; color: white; font-weight: bold;"
            " border-radius: 4px; font-size: 12px;"
        )
        self._btn_play.clicked.connect(self._on_play_pause)
        h.addWidget(self._btn_play)

        # Time
        self._time_lbl = QLabel("0:00")
        self._time_lbl.setFixedWidth(44)
        self._time_lbl.setStyleSheet("color: #e0e0e0; font-size: 11px;")
        h.addWidget(self._time_lbl)

        # Seek bar
        self._seek = ClickableSlider(Qt.Orientation.Horizontal)
        self._seek.setRange(0, 10000)
        self._seek.sliderPressed.connect(self._on_seek_press)
        self._seek.sliderReleased.connect(self._on_seek_release)
        h.addWidget(self._seek, stretch=1)

        # Duration
        self._dur_lbl = QLabel("0:00")
        self._dur_lbl.setFixedWidth(44)
        self._dur_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._dur_lbl.setStyleSheet("color: #e0e0e0; font-size: 11px;")
        h.addWidget(self._dur_lbl)

        return bar

    # ── Transport slots ────────────────────────────────────────────────────────

    def _on_play_pause(self) -> None:
        if not self._engine.has_active_players():
            return
        if self._engine.is_paused():
            self._engine.play_all()
        else:
            self._engine.pause_all()

    def _on_seek_press(self) -> None:
        self._seek_dragging = True

    def _on_seek_release(self) -> None:
        dur = self._engine.get_duration()
        if dur > 0:
            pos = (self._seek.value() / 10000.0) * dur
            self._engine.seek_all(pos)
        self._seek_dragging = False

    # ── Poll ──────────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        pos = self._engine.get_position()
        dur = self._engine.get_duration()
        self._time_lbl.setText(_fmt_time(pos))
        self._dur_lbl.setText(_fmt_time(dur))
        if dur > 0 and not self._seek_dragging:
            self._seek.setValue(int((pos / dur) * 10000))
        paused = self._engine.is_paused()
        self._btn_play.setText("▶" if paused else "⏸")

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            DebugLog.record("key.escape", slot=self.slot_index)
            # Signal ControlWindow to tear down all players together. Closing
            # just this window leaves the engine polling a dead mpv handle,
            # which freezes the remaining player windows.
            self.close_all_requested.emit()
        elif event.key() == Qt.Key.Key_F11:
            DebugLog.record("key.f11", slot=self.slot_index)
            self._toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Space:
            DebugLog.record("key.space", slot=self.slot_index)
            self._on_play_pause()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        """User clicked the window's X — route through the group teardown so
        the engine stops polling the dead mpv handle, same as ESC."""
        if not self._teardown_in_progress:
            DebugLog.record("player.user_close", slot=self.slot_index)
            event.ignore()
            self.close_all_requested.emit()
            return
        DebugLog.record("player.teardown_close", slot=self.slot_index)
        super().closeEvent(event)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ── Placement ─────────────────────────────────────────────────────────────

    def place_on_screen(self, screen: QScreen, fullscreen: bool = False) -> None:
        """Place this window on *screen*.

        fullscreen=True kicks into kiosk mode (used for the 3-wall rig
        configuration). fullscreen=False — the v0.0.1-alpha default — places
        a sensibly-sized, frame-decorated window centered on the target
        monitor so a user with 2 screens can still see their desktop.
        """
        geo: QRect = screen.geometry()
        if fullscreen:
            self.setGeometry(geo)
            self.showFullScreen()
        else:
            target_w = min(1280, int(geo.width() * 0.9))
            target_h = min(720 + _CTRL_HEIGHT, int(geo.height() * 0.9))
            x = geo.x() + (geo.width() - target_w) // 2
            y = geo.y() + (geo.height() - target_h) // 2
            self.setGeometry(x, y, target_w, target_h)
            self.showNormal()
