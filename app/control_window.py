# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""ControlWindow — main UI panel for eHaptic Studio Player."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QSlider, QComboBox, QFileDialog,
    QGroupBox, QCheckBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QScreen

from app.player_window import PlayerWindow
from app.sync_engine import SyncEngine

_SLOT_LABELS = ["Slot 1", "Slot 2", "Slot 3"]
_POLL_MS = 100          # seek-bar refresh rate
_MEDIA_FILTER = (
    "Media files (*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.m4a *.wav *.flac *.ogg);;"
    "All files (*)"
)


def _fmt_time(seconds: float) -> str:
    s = max(0, int(seconds))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class ControlWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("eHaptic Studio Player")
        self.setMinimumWidth(900)

        self._engine = SyncEngine()
        self._player_windows: list[PlayerWindow | None] = [None, None, None]
        self._seek_dragging = False

        # Discover screens and audio devices
        self._screens: list[QScreen] = self.screen().virtualSiblings()
        raw_devices = SyncEngine.list_audio_devices()
        self._audio_devices: list[tuple[str, str]] = [
            (d["name"], d.get("description", d["name"])) for d in raw_devices
        ]

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._poll)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setSpacing(12)
        vbox.setContentsMargins(16, 16, 16, 16)

        # ── Slot panels ──
        slots_row = QHBoxLayout()
        slots_row.setSpacing(8)
        self._slot_widgets: list[QGroupBox] = []
        for i in range(3):
            w = self._build_slot(i)
            self._slot_widgets.append(w)
            slots_row.addWidget(w)
        vbox.addLayout(slots_row)

        # ── Seek bar ──
        seek_row = QHBoxLayout()
        self._time_label = QLabel("0:00")
        self._time_label.setFixedWidth(52)
        self._seek_bar = QSlider(Qt.Orientation.Horizontal)
        self._seek_bar.setRange(0, 10000)
        self._seek_bar.sliderPressed.connect(self._on_seek_press)
        self._seek_bar.sliderReleased.connect(self._on_seek_release)
        self._dur_label = QLabel("0:00")
        self._dur_label.setFixedWidth(52)
        self._dur_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        seek_row.addWidget(self._time_label)
        seek_row.addWidget(self._seek_bar)
        seek_row.addWidget(self._dur_label)
        vbox.addLayout(seek_row)

        # ── Transport controls ──
        transport = QHBoxLayout()
        transport.setSpacing(8)
        transport.addStretch()

        for label, fn in [
            ("−30s", lambda: self._skip(-30)),
            ("−10s", lambda: self._skip(-10)),
            ("−5s",  lambda: self._skip(-5)),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(36)
            b.clicked.connect(fn)
            transport.addWidget(b)

        self._btn_play = QPushButton("▶  Play")
        self._btn_play.setFixedWidth(110)
        self._btn_play.setFixedHeight(36)
        self._btn_play.setStyleSheet(
            "background: #ff4b4b; color: white; font-weight: bold; border-radius: 6px;"
        )
        self._btn_play.clicked.connect(self._on_play_pause)
        transport.addWidget(self._btn_play)

        btn_stop = QPushButton("⏹  Stop")
        btn_stop.setFixedHeight(36)
        btn_stop.clicked.connect(self._on_stop)
        transport.addWidget(btn_stop)

        for label, fn in [
            ("+5s",  lambda: self._skip(5)),
            ("+10s", lambda: self._skip(10)),
            ("+30s", lambda: self._skip(30)),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(36)
            b.clicked.connect(fn)
            transport.addWidget(b)

        transport.addStretch()
        vbox.addLayout(transport)

        # ── Launch / Close buttons ──
        action_row = QHBoxLayout()
        action_row.addStretch()

        btn_close_players = QPushButton("Close Players")
        btn_close_players.setFixedHeight(40)
        btn_close_players.clicked.connect(self._close_players)
        action_row.addWidget(btn_close_players)

        btn_launch = QPushButton("Launch Players")
        btn_launch.setFixedHeight(40)
        btn_launch.setFixedWidth(160)
        btn_launch.setStyleSheet(
            "background: #2d6a4f; color: white; font-weight: bold; border-radius: 6px;"
        )
        btn_launch.clicked.connect(self._on_launch)
        action_row.addWidget(btn_launch)

        action_row.addStretch()
        vbox.addLayout(action_row)

    def _build_slot(self, index: int) -> QGroupBox:
        box = QGroupBox(_SLOT_LABELS[index])
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        # Enable toggle
        enabled = QCheckBox("Enable this slot")
        enabled.setChecked(index == 0)   # only slot 1 on by default
        layout.addWidget(enabled)

        # File picker
        path_label = QLabel("No file selected")
        path_label.setWordWrap(False)
        path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        path_label.setStyleSheet("color: #9ba3c4; font-size: 11px;")
        path_label.setToolTip("")
        layout.addWidget(path_label)

        btn_browse = QPushButton("Browse…")
        btn_browse.setFixedHeight(30)
        layout.addWidget(btn_browse)

        # Monitor selector
        layout.addWidget(QLabel("Monitor:"))
        monitor_combo = QComboBox()
        for j, s in enumerate(self._screens):
            geo = s.geometry()
            monitor_combo.addItem(
                f"Screen {j + 1}  —  {geo.width()}×{geo.height()}  ({s.name()})",
                j,
            )
        # Default each slot to a different screen if possible
        if index < monitor_combo.count():
            monitor_combo.setCurrentIndex(index)
        layout.addWidget(monitor_combo)

        # Audio device selector
        layout.addWidget(QLabel("Audio output:"))
        audio_combo = QComboBox()
        audio_combo.addItem("System default", "")
        for name, desc in self._audio_devices:
            audio_combo.addItem(desc, name)
        layout.addWidget(audio_combo)

        slot_data: dict = {
            "enabled":       enabled,
            "path_label":    path_label,
            "path":          "",
            "monitor_combo": monitor_combo,
            "audio_combo":   audio_combo,
        }
        btn_browse.clicked.connect(lambda _, d=slot_data: self._on_browse(d))
        box._slot_data = slot_data  # type: ignore[attr-defined]
        return box

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _slot_data(self, index: int) -> dict:
        return self._slot_widgets[index]._slot_data  # type: ignore[attr-defined]

    def _on_browse(self, data: dict) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select media file", "", _MEDIA_FILTER)
        if path:
            data["path"] = path
            data["path_label"].setText(os.path.basename(path))
            data["path_label"].setToolTip(path)
            data["enabled"].setChecked(True)

    # ── Launch / close ────────────────────────────────────────────────────────

    def _close_players(self) -> None:
        self._timer.stop()
        self._engine.stop_all()
        for i, w in enumerate(self._player_windows):
            if w:
                self._engine.terminate_player(i)
                w.close()
                self._player_windows[i] = None
        self._btn_play.setText("▶  Play")
        self._seek_bar.setValue(0)
        self._time_label.setText("0:00")
        self._dur_label.setText("0:00")

    def _on_launch(self) -> None:
        self._close_players()

        launched = False
        for i in range(3):
            data = self._slot_data(i)
            if not data["enabled"].isChecked() or not data["path"]:
                continue

            screen_idx: int = data["monitor_combo"].currentData()
            screen = (
                self._screens[screen_idx]
                if screen_idx < len(self._screens)
                else self._screens[0]
            )
            audio_device: str = data["audio_combo"].currentData() or ""

            pw = PlayerWindow(i)
            pw.place_on_screen(screen, fullscreen=True)
            pw.show()
            pw.raise_()
            self._player_windows[i] = pw

            # Init mpv AFTER show() so the native window handle is valid
            self._engine.init_player(i, pw.native_wid(), audio_device)
            self._engine.load_file(i, data["path"])
            launched = True

        if launched:
            self._timer.start()
            self.raise_()   # bring control window to front

    # ── Transport ─────────────────────────────────────────────────────────────

    def _on_play_pause(self) -> None:
        if not self._engine.has_active_players():
            return
        if self._engine.is_paused():
            self._engine.play_all()
            self._btn_play.setText("⏸  Pause")
        else:
            self._engine.pause_all()
            self._btn_play.setText("▶  Play")

    def _on_stop(self) -> None:
        self._engine.stop_all()
        self._btn_play.setText("▶  Play")
        self._seek_bar.setValue(0)
        self._time_label.setText("0:00")

    def _skip(self, seconds: float) -> None:
        pos = self._engine.get_position()
        dur = self._engine.get_duration()
        new_pos = max(0.0, min(pos + seconds, dur))
        self._engine.seek_all(new_pos)

    def _on_seek_press(self) -> None:
        self._seek_dragging = True

    def _on_seek_release(self) -> None:
        dur = self._engine.get_duration()
        if dur > 0:
            pos = (self._seek_bar.value() / 10000.0) * dur
            self._engine.seek_all(pos)
        self._seek_dragging = False

    # ── Poll timer ────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        pos = self._engine.get_position()
        dur = self._engine.get_duration()
        self._time_label.setText(_fmt_time(pos))
        self._dur_label.setText(_fmt_time(dur))
        if dur > 0 and not self._seek_dragging:
            self._seek_bar.setValue(int((pos / dur) * 10000))
        paused = self._engine.is_paused()
        self._btn_play.setText("▶  Play" if paused else "⏸  Pause")

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        self._engine.terminate_all()
        super().closeEvent(event)
