# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""ControlWindow — session-aware main panel for ForgePlayer."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QSlider, QComboBox, QFileDialog,
    QGroupBox, QCheckBox, QSizePolicy, QLineEdit, QSpacerItem,
    QMenu, QToolBar, QFrame, QTabWidget, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QScreen, QAction

from app.player_window import PlayerWindow
from app.sync_engine import SyncEngine
from app.session import Session, SlotConfig
from app.folder_scanner import auto_assign
from app.library_panel import LibraryPanel
from app.library.catalog import SceneCatalogEntry
from app.select_picker import SelectPicker, SelectionChoices

_SLOT_LABELS = ["Slot 1", "Slot 2", "Slot 3"]
_POLL_MS = 100
_MEDIA_FILTER = (
    "Media files (*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.m4a *.wav *.flac *.ogg);;"
    "All files (*)"
)
_VIDEO_FILTER = "Video files (*.mp4 *.mkv *.mov *.avi *.webm);;All files (*)"
_AUDIO_FILTER = "Audio files (*.mp3 *.m4a *.wav *.flac *.ogg);;All files (*)"
_SESSION_FILTER = "ForgePlayer session (*.forgeplayer-session);;All files (*)"


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
        self.setWindowTitle("ForgePlayer")
        self.setMinimumWidth(980)

        self._engine = SyncEngine()
        self._player_windows: list[PlayerWindow | None] = [None, None, None]
        self._seek_dragging = False
        self._session_path: str = ""

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

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setSpacing(8)
        vbox.setContentsMargins(14, 10, 14, 14)

        # ── Session toolbar (common across tabs) ──
        vbox.addWidget(self._build_session_bar())

        # ── Tab container (Live / Setup / Library) ──
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_live_tab(), "Live")
        self._tabs.addTab(self._build_setup_tab(), "Setup")

        self._library_panel = LibraryPanel()
        self._library_panel.scene_activated.connect(self._on_scene_activated)
        self._tabs.addTab(self._library_panel, "Library")

        vbox.addWidget(self._tabs, 1)

    def _build_live_tab(self) -> QWidget:
        """The existing prototype's slot/seek/transport UI, wrapped as a tab."""
        tab = QWidget()
        vbox = QVBoxLayout(tab)
        vbox.setSpacing(10)
        vbox.setContentsMargins(6, 6, 6, 6)

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
        self._dur_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
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

        return tab

    def _build_setup_tab(self) -> QWidget:
        """Placeholder — Setup panel (monitors / audio / library / preferences)
        is Phase 2 of the UI slice. Right now it's a stub explaining what
        will live here."""
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(40, 40, 40, 40)

        title = QLabel("Setup")
        f = title.font(); f.setPointSize(18); f.setBold(True); title.setFont(f)
        v.addWidget(title)

        body = QLabel(
            "This tab will hold Monitors, Audio routing, Library roots, and "
            "Preferences sections — each navigable via chevrons.\n\n"
            "Alpha status: stub. Use the Library tab to scan scenes, and the "
            "Live tab for playback (prototype)."
        )
        body.setStyleSheet("color: #9ba3c4;")
        body.setWordWrap(True)
        v.addWidget(body)
        v.addStretch()

        return tab

    def _on_scene_activated(self, entry: SceneCatalogEntry) -> None:
        """Called when the user picks a scene in the Library panel.

        Behavior:
        - If the scene is ambiguous (see SceneCatalogEntry.is_ambiguous),
          show the SelectPicker modal. User's choices drive the load.
        - If unambiguous, use the scanner's defaults directly.
        - In either case, for now we just show a summary dialog of what
          WOULD load (playback integration is a later slice)."""

        if entry.is_ambiguous:
            picker = SelectPicker(entry, parent=self)
            if picker.exec() != SelectPicker.Accepted:
                return  # user cancelled
            choices = picker.choices()
        else:
            choices = SelectionChoices(
                video=entry.default_video,
                audio=entry.default_audio,
                funscript_set=entry.default_funscript_set,
                subtitle=None,
                save_as_preset=False,
            )

        self._load_choices_stub(entry, choices)

    def _load_choices_stub(
        self,
        entry: SceneCatalogEntry,
        choices: SelectionChoices,
    ) -> None:
        """Summary dialog until playback integration slice lands.

        When single-decoder playback is done this becomes: hand video +
        audio + funscript-set to SyncEngine, seed Live panel, auto-switch
        to Live tab."""
        lines = [
            f"Scene: {entry.name}",
            f"Folder: {entry.folder_path}",
            "",
            f"Video: {choices.video.filename if choices.video else '(none)'}",
            f"Audio: {choices.audio.filename if choices.audio else '(none)'}",
        ]
        if choices.funscript_set:
            fset = choices.funscript_set
            channels = list(fset.channels) if fset.channels else ["(main only)"]
            lines.append(f"Funscript set: {fset.base_stem}")
            lines.append(f"  channels: {', '.join(sorted(channels))}")
        if choices.subtitle:
            lines.append(f"Subtitle: {choices.subtitle.language.upper()}")
        if choices.save_as_preset:
            lines.append("")
            lines.append("→ Save & Play selected — pin persistence is in the next slice.")
        else:
            lines.append("")
            lines.append("→ Play once — not persisted.")
        QMessageBox.information(self, entry.name, "\n".join(lines))

    def _build_session_bar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        btn_new = QPushButton("New")
        btn_new.setFixedHeight(30)
        btn_new.setToolTip("New empty session")
        btn_new.clicked.connect(self._on_session_new)
        h.addWidget(btn_new)

        btn_open = QPushButton("Open…")
        btn_open.setFixedHeight(30)
        btn_open.setToolTip("Open a session file")
        btn_open.clicked.connect(self._on_session_open)
        h.addWidget(btn_open)

        self._btn_recent = QPushButton("Recent ▾")
        self._btn_recent.setFixedHeight(30)
        self._btn_recent.clicked.connect(self._on_recent_menu)
        h.addWidget(self._btn_recent)

        btn_save = QPushButton("Save")
        btn_save.setFixedHeight(30)
        btn_save.clicked.connect(self._on_session_save)
        h.addWidget(btn_save)

        btn_save_as = QPushButton("Save As…")
        btn_save_as.setFixedHeight(30)
        btn_save_as.clicked.connect(self._on_session_save_as)
        h.addWidget(btn_save_as)

        h.addSpacing(16)
        h.addWidget(QLabel("Session:"))

        self._session_name = QLineEdit("Untitled Session")
        self._session_name.setFixedHeight(30)
        self._session_name.setFixedWidth(200)
        h.addWidget(self._session_name)

        h.addStretch()

        btn_scan = QPushButton("⬡  Scan Folder…")
        btn_scan.setFixedHeight(30)
        btn_scan.setToolTip(
            "Scan a folder for media files and auto-assign videos to slots by monitor aspect ratio"
        )
        btn_scan.setStyleSheet(
            "background: #2d4a8a; color: white; font-weight: bold; border-radius: 4px;"
        )
        btn_scan.clicked.connect(self._on_scan_folder)
        h.addWidget(btn_scan)

        return bar

    def _build_slot(self, index: int) -> QGroupBox:
        box = QGroupBox(_SLOT_LABELS[index])
        layout = QVBoxLayout(box)
        layout.setSpacing(5)

        # Enable toggle
        enabled = QCheckBox("Enable this slot")
        enabled.setChecked(index == 0)
        layout.addWidget(enabled)

        # ── Video file ──
        layout.addWidget(QLabel("Video:"))
        video_label = QLabel("No file selected")
        video_label.setWordWrap(False)
        video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        video_label.setStyleSheet("color: #9ba3c4; font-size: 11px;")
        layout.addWidget(video_label)

        btn_video = QPushButton("Browse Video…")
        btn_video.setFixedHeight(28)
        layout.addWidget(btn_video)

        # ── Audio file ──
        layout.addWidget(QLabel("Audio override:"))
        audio_label = QLabel("(uses video audio)")
        audio_label.setWordWrap(False)
        audio_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        audio_label.setStyleSheet("color: #9ba3c4; font-size: 11px;")
        layout.addWidget(audio_label)

        audio_row = QHBoxLayout()
        btn_audio = QPushButton("Browse Audio…")
        btn_audio.setFixedHeight(28)
        audio_row.addWidget(btn_audio)
        btn_clear_audio = QPushButton("✕")
        btn_clear_audio.setFixedSize(28, 28)
        btn_clear_audio.setToolTip("Clear audio override")
        audio_row.addWidget(btn_clear_audio)
        layout.addLayout(audio_row)

        # ── Monitor ──
        layout.addWidget(QLabel("Monitor:"))
        monitor_combo = QComboBox()
        for j, s in enumerate(self._screens):
            geo = s.geometry()
            monitor_combo.addItem(
                f"Screen {j + 1}  —  {geo.width()}×{geo.height()}  ({s.name()})",
                j,
            )
        if index < monitor_combo.count():
            monitor_combo.setCurrentIndex(index)
        layout.addWidget(monitor_combo)

        # ── Audio device ──
        layout.addWidget(QLabel("Audio output:"))
        audio_combo = QComboBox()
        audio_combo.addItem("System default", "")
        for name, desc in self._audio_devices:
            audio_combo.addItem(desc, name)
        layout.addWidget(audio_combo)

        # ── Volume ──
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Volume:"))
        volume_slider = QSlider(Qt.Orientation.Horizontal)
        volume_slider.setRange(0, 100)
        volume_slider.setValue(100)
        volume_slider.setFixedHeight(22)
        vol_row.addWidget(volume_slider)
        vol_lbl = QLabel("100")
        vol_lbl.setFixedWidth(28)
        vol_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        vol_row.addWidget(vol_lbl)
        layout.addLayout(vol_row)

        slot_data: dict = {
            "enabled":        enabled,
            "video_label":    video_label,
            "video_path":     "",
            "audio_label":    audio_label,
            "audio_path":     "",
            "monitor_combo":  monitor_combo,
            "audio_combo":    audio_combo,
            "volume_slider":  volume_slider,
            "vol_lbl":        vol_lbl,
        }

        btn_video.clicked.connect(lambda _, d=slot_data: self._on_browse_video(d))
        btn_audio.clicked.connect(lambda _, d=slot_data: self._on_browse_audio(d))
        btn_clear_audio.clicked.connect(lambda _, d=slot_data: self._on_clear_audio(d))
        volume_slider.valueChanged.connect(
            lambda v, idx=index, lbl=vol_lbl: self._on_volume_changed(idx, v, lbl)
        )

        box._slot_data = slot_data  # type: ignore[attr-defined]
        return box

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _slot_data(self, index: int) -> dict:
        return self._slot_widgets[index]._slot_data  # type: ignore[attr-defined]

    def _screen_sizes(self) -> list[tuple[int, int]]:
        return [(s.geometry().width(), s.geometry().height()) for s in self._screens]

    # ── Browse callbacks ───────────────────────────────────────────────────────

    def _on_browse_video(self, data: dict) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select video file", "", _VIDEO_FILTER)
        if path:
            data["video_path"] = path
            data["video_label"].setText(os.path.basename(path))
            data["video_label"].setToolTip(path)
            data["enabled"].setChecked(True)

    def _on_browse_audio(self, data: dict) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select audio file", "", _AUDIO_FILTER)
        if path:
            data["audio_path"] = path
            data["audio_label"].setText(os.path.basename(path))
            data["audio_label"].setToolTip(path)

    def _on_clear_audio(self, data: dict) -> None:
        data["audio_path"] = ""
        data["audio_label"].setText("(uses video audio)")
        data["audio_label"].setToolTip("")

    def _on_volume_changed(self, slot: int, value: int, lbl: QLabel) -> None:
        lbl.setText(str(value))
        self._engine.set_volume(slot, value)

    # ── Scan folder ────────────────────────────────────────────────────────────

    def _on_scan_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select media folder")
        if not folder:
            return
        assignments = auto_assign(folder, self._screen_sizes())
        for i, slot in enumerate(assignments):
            data = self._slot_data(i)
            vp = slot.get("video_path", "")
            ap = slot.get("audio_path", "")
            mi = slot.get("monitor_index", i)

            data["video_path"] = vp
            data["video_label"].setText(os.path.basename(vp) if vp else "No file selected")
            data["video_label"].setToolTip(vp)

            data["audio_path"] = ap
            data["audio_label"].setText(
                os.path.basename(ap) if ap else "(uses video audio)"
            )
            data["audio_label"].setToolTip(ap)

            combo: QComboBox = data["monitor_combo"]
            for idx in range(combo.count()):
                if combo.itemData(idx) == mi:
                    combo.setCurrentIndex(idx)
                    break

            data["enabled"].setChecked(bool(vp or ap))

    # ── Session ────────────────────────────────────────────────────────────────

    def _current_session(self) -> Session:
        slots: list[SlotConfig] = []
        for i in range(3):
            d = self._slot_data(i)
            slots.append(SlotConfig(
                enabled=d["enabled"].isChecked(),
                video_path=d["video_path"],
                audio_path=d["audio_path"],
                monitor_index=d["monitor_combo"].currentData() or 0,
                audio_device=d["audio_combo"].currentData() or "",
                volume=d["volume_slider"].value(),
            ))
        return Session(name=self._session_name.text(), slots=slots)

    def _apply_session(self, session: Session) -> None:
        self._session_name.setText(session.name)
        for i, cfg in enumerate(session.slots[:3]):
            d = self._slot_data(i)
            d["enabled"].setChecked(cfg.enabled)

            d["video_path"] = cfg.video_path
            d["video_label"].setText(
                os.path.basename(cfg.video_path) if cfg.video_path else "No file selected"
            )
            d["video_label"].setToolTip(cfg.video_path)

            d["audio_path"] = cfg.audio_path
            d["audio_label"].setText(
                os.path.basename(cfg.audio_path) if cfg.audio_path else "(uses video audio)"
            )
            d["audio_label"].setToolTip(cfg.audio_path)

            combo: QComboBox = d["monitor_combo"]
            for idx in range(combo.count()):
                if combo.itemData(idx) == cfg.monitor_index:
                    combo.setCurrentIndex(idx)
                    break

            a_combo: QComboBox = d["audio_combo"]
            for idx in range(a_combo.count()):
                if a_combo.itemData(idx) == cfg.audio_device:
                    a_combo.setCurrentIndex(idx)
                    break

            d["volume_slider"].setValue(cfg.volume)

    def _on_session_new(self) -> None:
        self._apply_session(Session())
        self._session_path = ""
        self.setWindowTitle("ForgePlayer — Untitled Session")

    def _on_session_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open session", "", _SESSION_FILTER
        )
        if path:
            self._load_session_from(path)

    def _on_recent_menu(self) -> None:
        recent = Session.load_recent()
        menu = QMenu(self)
        if not recent:
            menu.addAction("(no recent sessions)").setEnabled(False)
        for path in recent:
            action = menu.addAction(os.path.basename(path))
            action.setToolTip(path)
            action.triggered.connect(
                lambda checked=False, p=path: self._load_session_from(p)
            )
        menu.exec(self._btn_recent.mapToGlobal(
            self._btn_recent.rect().bottomLeft()
        ))

    def _load_session_from(self, path: str) -> None:
        try:
            session = Session.load(path)
        except Exception as exc:
            return
        self._session_path = path
        self._apply_session(session)
        Session.add_recent(path)
        self.setWindowTitle(f"ForgePlayer — {session.name}")

    def _on_session_save(self) -> None:
        if self._session_path:
            self._current_session().save(self._session_path)
            Session.add_recent(self._session_path)
        else:
            self._on_session_save_as()

    def _on_session_save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save session as", "", _SESSION_FILTER
        )
        if path:
            if not path.endswith(".forgeplayer-session"):
                path += ".forgeplayer-session"
            self._session_path = path
            self._current_session().save(path)
            Session.add_recent(path)
            self.setWindowTitle(
                f"ForgePlayer — {self._session_name.text()}"
            )

    # ── Launch / close ─────────────────────────────────────────────────────────

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
            if not data["enabled"].isChecked():
                continue
            video_path: str = data["video_path"]
            audio_path: str = data["audio_path"]
            if not (video_path or audio_path):
                continue

            screen_idx: int = data["monitor_combo"].currentData()
            screen = (
                self._screens[screen_idx]
                if screen_idx < len(self._screens)
                else self._screens[0]
            )
            audio_device: str = data["audio_combo"].currentData() or ""

            pw = PlayerWindow(i, self._engine)
            pw.place_on_screen(screen, fullscreen=True)
            pw.show()
            pw.raise_()
            self._player_windows[i] = pw

            # Init mpv AFTER show() so the native window handle is valid
            self._engine.init_player(i, pw.native_wid(), audio_device)
            # Load video (or audio-only file)
            media_path = video_path or audio_path
            self._engine.load_file(i, media_path)
            # If separate audio override, set the audio file
            if video_path and audio_path:
                try:
                    self._engine._players[i].audio_files = [audio_path]  # type: ignore[index]
                except Exception:
                    pass
            # Apply saved volume
            self._engine.set_volume(i, data["volume_slider"].value())
            launched = True

        if launched:
            self._timer.start()
            self.raise_()

    # ── Transport ──────────────────────────────────────────────────────────────

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

    # ── Poll timer ─────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        pos = self._engine.get_position()
        dur = self._engine.get_duration()
        self._time_label.setText(_fmt_time(pos))
        self._dur_label.setText(_fmt_time(dur))
        if dur > 0 and not self._seek_dragging:
            self._seek_bar.setValue(int((pos / dur) * 10000))
        paused = self._engine.is_paused()
        self._btn_play.setText("▶  Play" if paused else "⏸  Pause")

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        self._engine.terminate_all()
        super().closeEvent(event)
