# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""PlayerWindow — borderless video window with embedded transport controls."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
)
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QScreen

from app.sync_engine import SyncEngine

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

    def __init__(self, slot_index: int, engine: SyncEngine) -> None:
        super().__init__()
        self.slot_index = slot_index
        self._engine = engine
        self._seek_dragging = False

        self.setWindowTitle(f"ForgePlayer {slot_index + 1}")
        self.setStyleSheet("background-color: black;")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
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
        self._seek = QSlider(Qt.Orientation.Horizontal)
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
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            self._on_play_pause()
        else:
            super().keyPressEvent(event)

    # ── Placement ─────────────────────────────────────────────────────────────

    def place_on_screen(self, screen: QScreen, fullscreen: bool = True) -> None:
        """Move this window to fill *screen*."""
        geo: QRect = screen.geometry()
        self.setGeometry(geo)
        if fullscreen:
            self.showFullScreen()
