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
from app.debug_log import DebugLog
from app.widgets import ClickableSlider
from app.preferences import Preferences

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

        # Discover screens and audio devices (HDMI phantom devices filtered
        # out — they confuse the Scene/Haptic role picker).
        self._screens: list[QScreen] = self.screen().virtualSiblings()
        raw_devices = SyncEngine.list_audio_devices()
        self._audio_devices: list[tuple[str, str]] = [
            (d["name"], d.get("description", d["name"])) for d in raw_devices
        ]

        # Load persisted device-role preferences (Scene / Haptic 1 / Haptic 2).
        self._prefs = Preferences.load()

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

        # Default to Library on startup — returning users with a scanned
        # root want to land on their scenes, first-run users get a welcome
        # empty-state inside the Library panel pointing them at Scan Folder.
        self._tabs.setCurrentWidget(self._library_panel)

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
        self._seek_bar = ClickableSlider(Qt.Orientation.Horizontal)
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

        self._fullscreen_toggle = QCheckBox("Fullscreen")
        self._fullscreen_toggle.setToolTip(
            "When on, player windows take over their whole monitor (kiosk mode).\n"
            "When off (default), windowed players let you keep your desktop visible.\n"
            "Press F11 inside a player to toggle fullscreen at any time."
        )
        self._fullscreen_toggle.setStyleSheet("color: #9ba3c4;")
        action_row.addWidget(self._fullscreen_toggle)

        action_row.addSpacing(12)

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
        """Setup — device-role configuration. Set this up once; Library
        clicks then auto-route Slot 1 to Scene Audio and Slot 2 to Haptic 1.

        The v0.0.2 redesign will layer monitors, library roots, and preferences
        sections under chevrons. For v0.0.1 alpha, audio device roles are the
        minimum viable Setup — they close the "why did my haptic go to the
        wrong device?" loop from library clicks.
        """
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(16)

        title = QLabel("Setup")
        tf = title.font(); tf.setPointSize(18); tf.setBold(True); title.setFont(tf)
        root.addWidget(title)

        subtitle = QLabel(
            "Pick which physical audio device handles each role. Library clicks "
            "use these to route automatically — you only set this once."
        )
        subtitle.setStyleSheet("color: #9ba3c4;")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # Device-role group
        role_box = QGroupBox("Audio device roles")
        rl = QVBoxLayout(role_box)
        rl.setSpacing(10)

        self._setup_scene_combo = self._build_role_combo(
            saved_value=self._prefs.scene_audio_device,
        )
        self._setup_haptic1_combo = self._build_role_combo(
            saved_value=self._prefs.haptic1_audio_device,
        )
        self._setup_haptic2_combo = self._build_role_combo(
            saved_value=self._prefs.haptic2_audio_device,
        )

        self._setup_scene_combo.currentIndexChanged.connect(self._on_setup_changed)
        self._setup_haptic1_combo.currentIndexChanged.connect(self._on_setup_changed)
        self._setup_haptic2_combo.currentIndexChanged.connect(self._on_setup_changed)

        rl.addLayout(self._labeled_row(
            "Scene audio", self._setup_scene_combo,
            "Video's embedded sound — typically your speakers or headphones.",
        ))
        rl.addLayout(self._labeled_row(
            "Haptic 1 (main stim)", self._setup_haptic1_combo,
            "Primary estim output — typically your USB audio dongle.",
        ))
        rl.addLayout(self._labeled_row(
            "Haptic 2 (prostate)", self._setup_haptic2_combo,
            "Optional second estim output for prostate channels. Leave unset if unused.",
        ))

        root.addWidget(role_box)

        # Save-status line
        self._setup_status = QLabel("")
        self._setup_status.setStyleSheet("color: #9ba3c4; font-size: 11px;")
        root.addWidget(self._setup_status)

        root.addStretch()
        return tab

    def _build_role_combo(self, *, saved_value: str) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(32)
        combo.addItem("— not set —", "")
        for name, desc in self._audio_devices:
            combo.addItem(desc, name)
        # Restore previous selection if the device is still available.
        for idx in range(combo.count()):
            if combo.itemData(idx) == saved_value:
                combo.setCurrentIndex(idx)
                break
        return combo

    @staticmethod
    def _labeled_row(
        label_text: str, widget: QWidget, help_text: str = "",
    ) -> QVBoxLayout:
        row = QVBoxLayout()
        row.setSpacing(2)
        label = QLabel(label_text)
        lf = label.font(); lf.setBold(True); label.setFont(lf)
        row.addWidget(label)
        row.addWidget(widget)
        if help_text:
            helper = QLabel(help_text)
            helper.setStyleSheet("color: #6b7280; font-size: 11px;")
            helper.setWordWrap(True)
            row.addWidget(helper)
        return row

    def _on_setup_changed(self) -> None:
        self._prefs.scene_audio_device = self._setup_scene_combo.currentData() or ""
        self._prefs.haptic1_audio_device = self._setup_haptic1_combo.currentData() or ""
        self._prefs.haptic2_audio_device = self._setup_haptic2_combo.currentData() or ""
        self._prefs.save()
        DebugLog.record(
            "setup.prefs_saved",
            scene=bool(self._prefs.scene_audio_device),
            haptic1=bool(self._prefs.haptic1_audio_device),
            haptic2=bool(self._prefs.haptic2_audio_device),
        )
        self._setup_status.setText(f"Saved to {Preferences.path()}")
        QTimer.singleShot(3000, lambda: self._setup_status.setText(""))

    def _on_scene_activated(self, entry: SceneCatalogEntry) -> None:
        """Called when the user picks a scene in the Library panel.

        If ambiguous, ask the user via SelectPicker; otherwise use scanner
        defaults. Then route the resulting video/audio into Live slots,
        switch to the Live tab, and launch the players (paused — user
        still hits Play for the two-step workflow)."""
        if entry.is_ambiguous:
            picker = SelectPicker(entry, parent=self)
            if picker.exec() != SelectPicker.Accepted:
                DebugLog.record("library.activate.cancelled", scene=entry.name)
                return
            choices = picker.choices()
        else:
            choices = SelectionChoices(
                video=entry.default_video,
                audio=entry.default_audio,
                funscript_set=entry.default_funscript_set,
                subtitle=None,
                save_as_preset=False,
            )
        self._apply_scene_choices(entry, choices)

    def _apply_scene_choices(
        self,
        entry: SceneCatalogEntry,
        choices: SelectionChoices,
    ) -> None:
        """Populate Live slots from a scene + the user's picker choices,
        then switch to Live and launch.

        Routing model (user-confirmed 2026-04-23):

        - **Video** → Slot 1. Slot 1's audio output (user-configured, defaults
          to Realtek/system speakers) carries the video's embedded scene
          audio. No audio override on Slot 1 — the mp4's own audio IS the
          scene audio, routed by Slot 1's device setting.
        - **Picked audio file** → Slot 2 as audio-only. The user's mental
          model: picked audio = the haptic/estim track. Slot 2's audio
          output (user-configured, defaults to their USB dongle) carries
          that track to the estim device.
        - **Audio-only scene** (no video) → picked audio goes to Slot 1
          audio-only. Still routes via Slot 1's configured output.
        - Slot 3 is always cleared.

        Device roles (which physical device is "Scene audio" vs "Haptic 1")
        live in the Setup tab in v0.0.2 — for v0.0.1, the user sets each
        slot's audio-output dropdown once, and library clicks just fill in
        media around that setup.
        """
        DebugLog.record(
            "library.activate",
            scene=entry.name,
            has_video=bool(choices.video),
            has_audio=bool(choices.audio),
            save_as_preset=choices.save_as_preset,
        )

        slot1 = self._slot_data(0)
        slot2 = self._slot_data(1)
        slot3 = self._slot_data(2)

        # Slot 3 always clears — library clicks are one- or two-slot loads.
        self._set_slot_media(slot3, video_path="", audio_path="")

        # Video (if any) → Slot 1, embedded scene audio via Slot 1's device.
        if choices.video:
            self._set_slot_media(
                slot1,
                video_path=choices.video.path,
                audio_path="",
            )
        else:
            self._set_slot_media(slot1, video_path="", audio_path="")

        # Picked audio → Slot 2 audio-only, heading to the user's haptic
        # device (Slot 2's audio output — typically the USB dongle). This is
        # true whether or not there's a video: Slot 2 is the "stim" slot.
        if choices.audio:
            self._set_slot_media(
                slot2,
                video_path="",
                audio_path=choices.audio.path,
            )
        else:
            self._set_slot_media(slot2, video_path="", audio_path="")

        if not (choices.video or choices.audio):
            QMessageBox.information(
                self, "Nothing to play",
                f"Scene '{entry.name}' has no video or audio file to play."
            )
            return

        # Apply Setup's device roles to the slots. Scene audio → Slot 1,
        # Haptic 1 → Slot 2. Users who haven't configured Setup yet keep
        # whatever device the slot's combo is currently showing.
        self._apply_setup_roles_to_slots()

        # Library activation always starts a fresh unsaved session. Without
        # this, clicking a different scene while a loaded session file was
        # still active would let Save silently overwrite the old file with
        # the new scene's slot config. See 2026-04-23 dogfood: user loaded
        # Magik from Library with Euphoria.4k60 session still active, hit
        # Save, and overwrote Euphoria's session file.
        self._session_path = ""
        name_seed = (
            choices.video.path if choices.video
            else (choices.audio.path if choices.audio else entry.name)
        )
        new_name = (
            os.path.splitext(os.path.basename(name_seed))[0]
            if os.path.sep in name_seed or os.path.altsep and os.path.altsep in name_seed
            else entry.name
        )
        self._session_name.setText(new_name)
        self.setWindowTitle(f"ForgePlayer — {new_name}")

        # Name the session from the primary media file.
        primary = choices.video.path if choices.video else (
            choices.audio.path if choices.audio else ""
        )
        if primary:
            self._maybe_autofill_session_name(primary)

        # Switch to Live tab and launch (paused — user still hits Play).
        self._tabs.setCurrentIndex(0)
        self._on_launch()

    def _apply_setup_roles_to_slots(self) -> None:
        """Set Slot 1 and Slot 2's audio-output combos from Setup's roles.
        No-op for a role that isn't configured yet — the slot keeps whatever
        was there, so a partial Setup (only Haptic 1 configured, for example)
        still helps without clobbering the Scene slot."""
        role_to_slot = (
            (self._prefs.scene_audio_device, 0),
            (self._prefs.haptic1_audio_device, 1),
        )
        for device_id, slot_idx in role_to_slot:
            if not device_id:
                continue
            data = self._slot_data(slot_idx)
            combo: QComboBox = data["audio_combo"]
            for idx in range(combo.count()):
                if combo.itemData(idx) == device_id:
                    combo.setCurrentIndex(idx)
                    break

    def _set_slot_media(
        self,
        data: dict,
        *,
        video_path: str | None = None,
        audio_path: str | None = None,
    ) -> None:
        """Set video/audio paths on a slot's data dict + refresh labels.
        `None` means 'leave unchanged'; empty string means 'clear'."""
        if video_path is not None:
            data["video_path"] = video_path
            data["video_label"].setText(
                os.path.basename(video_path) if video_path else "No file selected"
            )
            data["video_label"].setToolTip(video_path)
        if audio_path is not None:
            data["audio_path"] = audio_path
            data["audio_label"].setText(
                os.path.basename(audio_path) if audio_path else "(uses video audio)"
            )
            data["audio_label"].setToolTip(audio_path)
        self._refresh_monitor_state(data)

    def _build_session_bar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        btn_new = QPushButton("New")
        btn_new.setFixedHeight(30)
        btn_new.setToolTip("New empty session")
        btn_new.clicked.connect(self._wrap_click("session.new", self._on_session_new))
        h.addWidget(btn_new)

        btn_open = QPushButton("Open…")
        btn_open.setFixedHeight(30)
        btn_open.setToolTip("Open a session file")
        btn_open.clicked.connect(self._wrap_click("session.open", self._on_session_open))
        h.addWidget(btn_open)

        self._btn_recent = QPushButton("Recent ▾")
        self._btn_recent.setFixedHeight(30)
        self._btn_recent.clicked.connect(self._wrap_click("session.recent", self._on_recent_menu))
        h.addWidget(self._btn_recent)

        btn_save = QPushButton("Save")
        btn_save.setFixedHeight(30)
        btn_save.clicked.connect(self._wrap_click("session.save", self._on_session_save))
        h.addWidget(btn_save)

        btn_save_as = QPushButton("Save As…")
        btn_save_as.setFixedHeight(30)
        btn_save_as.clicked.connect(self._wrap_click("session.save_as", self._on_session_save_as))
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
        btn_scan.clicked.connect(
            self._wrap_click("scan_folder", self._on_scan_folder)
        )
        h.addWidget(btn_scan)

        # ── Debug cluster ────────────────────────────────────────────────
        h.addSpacing(12)

        self._debug_toggle = QCheckBox("Debug")
        self._debug_toggle.setToolTip(
            "Record clicks, key events, and player lifecycle to an event log.\n"
            "Use Mark to flag a moment, then Export to write the log to\n"
            "~/.forgeplayer/debug-<timestamp>.json for bug reports."
        )
        self._debug_toggle.setStyleSheet("color: #9ba3c4;")
        self._debug_toggle.toggled.connect(self._on_debug_toggled)
        h.addWidget(self._debug_toggle)

        self._btn_mark = QPushButton("⚑ Mark")
        self._btn_mark.setFixedHeight(30)
        self._btn_mark.setToolTip("Insert a marker in the debug event log")
        self._btn_mark.clicked.connect(self._on_debug_mark)
        h.addWidget(self._btn_mark)

        self._btn_debug_export = QPushButton("Export…")
        self._btn_debug_export.setFixedHeight(30)
        self._btn_debug_export.setToolTip(
            "Write the captured debug events to ~/.forgeplayer/debug-<ts>.json"
        )
        self._btn_debug_export.clicked.connect(self._on_debug_export)
        h.addWidget(self._btn_debug_export)

        return bar

    def _build_slot(self, index: int) -> QGroupBox:
        box = QGroupBox(_SLOT_LABELS[index])
        layout = QVBoxLayout(box)
        layout.setSpacing(5)

        # ── Video file ──
        layout.addWidget(QLabel("Video:"))
        video_label = QLabel("No file selected")
        video_label.setWordWrap(False)
        video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        video_label.setStyleSheet("color: #9ba3c4; font-size: 11px;")
        layout.addWidget(video_label)

        video_row = QHBoxLayout()
        btn_video = QPushButton("Browse Video…")
        btn_video.setFixedHeight(28)
        video_row.addWidget(btn_video)
        btn_clear_video = QPushButton("✕")
        btn_clear_video.setFixedSize(28, 28)
        btn_clear_video.setToolTip("Clear video (also disables the slot if audio is also empty)")
        video_row.addWidget(btn_clear_video)
        layout.addLayout(video_row)

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
        # Drop "System default" — forces explicit device pick so haptic
        # output never silently lands on the wrong device.
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
        btn_clear_video.clicked.connect(lambda _, d=slot_data: self._on_clear_video(d))
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
            self._refresh_monitor_state(data)
            self._maybe_autofill_session_name(path)

    def _on_clear_video(self, data: dict) -> None:
        data["video_path"] = ""
        data["video_label"].setText("No file selected")
        data["video_label"].setToolTip("")
        self._refresh_monitor_state(data)

    def _maybe_autofill_session_name(self, media_path: str) -> None:
        """Set the Session name from the picked media file if the user
        hasn't already customized it."""
        current = self._session_name.text().strip()
        if current and current != "Untitled Session":
            return
        stem = os.path.splitext(os.path.basename(media_path))[0]
        if stem:
            self._session_name.setText(stem)
            self.setWindowTitle(f"ForgePlayer — {stem}")

    def _on_browse_audio(self, data: dict) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select audio file", "", _AUDIO_FILTER)
        if path:
            data["audio_path"] = path
            data["audio_label"].setText(os.path.basename(path))
            data["audio_label"].setToolTip(path)
            self._refresh_monitor_state(data)
            if not data["video_path"]:
                self._maybe_autofill_session_name(path)

    def _on_clear_audio(self, data: dict) -> None:
        data["audio_path"] = ""
        data["audio_label"].setText("(uses video audio)")
        data["audio_label"].setToolTip("")
        self._refresh_monitor_state(data)

    def _refresh_monitor_state(self, data: dict) -> None:
        """Dim the monitor dropdown for audio-only slots — there's no video
        surface to route, so picking a monitor is meaningless."""
        has_video = bool(data["video_path"])
        combo: QComboBox = data["monitor_combo"]
        combo.setEnabled(has_video)
        if has_video:
            combo.setToolTip("")
        else:
            combo.setToolTip(
                "Audio-only slot — no monitor is used. "
                "Load a video to enable monitor selection."
            )

    def _on_volume_changed(self, slot: int, value: int, lbl: QLabel) -> None:
        lbl.setText(str(value))
        self._engine.set_volume(slot, value)

    # ── Scan folder ────────────────────────────────────────────────────────────

    # ── Debug instrumentation ─────────────────────────────────────────────────

    def _wrap_click(self, name: str, fn):
        """Wrap a button handler so clicks land in DebugLog before firing."""
        def wrapped(*args, **kwargs):
            DebugLog.record("click", target=name)
            return fn(*args, **kwargs)
        return wrapped

    def _on_debug_toggled(self, checked: bool) -> None:
        DebugLog.set_enabled(bool(checked))
        DebugLog.record("debug.toggled", enabled=bool(checked))
        self._debug_toggle.setStyleSheet(
            "color: #ff6b30; font-weight: bold;" if checked else "color: #9ba3c4;"
        )
        if checked and DebugLog.stream_path():
            self._debug_toggle.setToolTip(
                f"Debug events are also streaming live to:\n{DebugLog.stream_path()}"
            )

    def _on_debug_mark(self) -> None:
        DebugLog.mark(note=f"user-marked (events so far: {DebugLog.event_count()})")
        self._btn_mark.setText(f"⚑ Mark ({DebugLog.event_count()})")
        QTimer.singleShot(1200, lambda: self._btn_mark.setText("⚑ Mark"))

    def _on_debug_export(self) -> None:
        if DebugLog.event_count() == 0:
            QMessageBox.information(
                self, "Debug log",
                "No events captured. Toggle Debug on, reproduce the issue, then Export."
            )
            return
        path = DebugLog.export()
        QMessageBox.information(
            self, "Debug log exported",
            f"Wrote {DebugLog.event_count()} events to:\n{path}"
        )

    # ── Folder scan ──────────────────────────────────────────────────────────

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

            self._refresh_monitor_state(data)

    # ── Session ────────────────────────────────────────────────────────────────

    def _current_session(self) -> Session:
        slots: list[SlotConfig] = []
        for i in range(3):
            d = self._slot_data(i)
            # Enabled state is now derived from whether the slot has media.
            # Kept on SlotConfig for backward-compat with older session files.
            has_media = bool(d["video_path"] or d["audio_path"])
            slots.append(SlotConfig(
                enabled=has_media,
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
            # No explicit enabled flag in UI — cfg.enabled is derived from
            # paths at save time; loading just trusts the paths we set below.

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
            self._refresh_monitor_state(d)

    def _on_session_new(self) -> None:
        self._apply_session(Session())
        self._session_path = ""
        self.setWindowTitle("ForgePlayer — Untitled Session")

    def _on_session_open(self) -> None:
        DebugLog.record("session.open.dialog_open")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open session", "", _SESSION_FILTER
        )
        DebugLog.record("session.open.dialog_closed", picked=bool(path))
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
        DebugLog.record("session.load.enter", path=path)
        try:
            session = Session.load(path)
        except Exception as exc:
            DebugLog.record("session.load.failed", path=path, error=repr(exc))
            QMessageBox.warning(
                self, "Could not open session",
                f"Failed to read {path}:\n\n{exc}"
            )
            return
        DebugLog.record(
            "session.load.parsed",
            path=path,
            name=session.name,
            slots=sum(1 for s in session.slots if s.video_path or s.audio_path),
        )
        self._session_path = path
        self._apply_session(session)
        DebugLog.record("session.load.slots_applied", path=path)
        # add_recent writes to ~/.forgeplayer/recent_sessions.json — wrap
        # so a disk hiccup doesn't block the UI after a successful load.
        try:
            Session.add_recent(path)
        except Exception as exc:
            DebugLog.record("session.add_recent.failed", error=repr(exc))
        self.setWindowTitle(f"ForgePlayer — {session.name}")
        DebugLog.record("session.load.exit", path=path)

    def _default_session_save_path(self) -> str:
        """Pre-fill the Save dialog with `<scene folder>/<session name>.forgeplayer-session`.

        Priority for folder: the loaded session's folder → Slot 1's video
        folder → Slot 1's audio folder → empty (dialog uses last-used dir).
        Filename: the current session name, sanitized for Windows reserved
        characters.
        """
        folder = ""
        if self._session_path:
            folder = os.path.dirname(self._session_path)
        if not folder:
            for slot_idx in range(3):
                d = self._slot_data(slot_idx)
                p = d.get("video_path", "") or d.get("audio_path", "")
                if p:
                    folder = os.path.dirname(p)
                    break
        name = (self._session_name.text() or "Untitled Session").strip()
        # Strip Windows reserved characters so the dialog accepts the suggestion
        for ch in r'<>:"/\|?*':
            name = name.replace(ch, "_")
        filename = f"{name}.forgeplayer-session"
        return os.path.join(folder, filename) if folder else filename

    def _on_session_save(self) -> None:
        DebugLog.record("session.save.enter", has_path=bool(self._session_path))
        if self._session_path:
            self._current_session().save(self._session_path)
            Session.add_recent(self._session_path)
            DebugLog.record("session.save.exit", path=self._session_path)
        else:
            self._on_session_save_as()

    def _on_session_save_as(self) -> None:
        DebugLog.record("session.save_as.dialog_open")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save session as", self._default_session_save_path(),
            _SESSION_FILTER,
        )
        DebugLog.record("session.save_as.dialog_closed", picked=bool(path))
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
        DebugLog.record(
            "players.close_all",
            active=sum(1 for w in self._player_windows if w),
        )
        self._timer.stop()
        self._engine.stop_all()
        # Terminate every engine slot — including audio-only slots that
        # don't have a PlayerWindow — so no mpv instances leak.
        for i in range(3):
            w = self._player_windows[i]
            if w:
                # Mark the window so its closeEvent doesn't re-enter our
                # close-all signal path — this close is the teardown itself.
                w._teardown_in_progress = True
            self._engine.terminate_player(i)
            if w:
                w.close()
                self._player_windows[i] = None
        self._btn_play.setText("▶  Play")
        self._seek_bar.setValue(0)
        self._time_label.setText("0:00")
        self._dur_label.setText("0:00")

    def _on_launch(self) -> None:
        DebugLog.record("players.launch_request")
        self._close_players()

        launched = False
        for i in range(3):
            data = self._slot_data(i)
            video_path: str = data["video_path"]
            audio_path: str = data["audio_path"]
            # Slot is "enabled" iff it has media. No separate checkbox anymore.
            if not (video_path or audio_path):
                continue

            audio_device: str = data["audio_combo"].currentData() or ""

            # Audio-only: no PlayerWindow, no monitor. Headless mpv still
            # participates in sync (seek/pause/play apply via _active list).
            if audio_path and not video_path:
                DebugLog.record("players.launch_slot", slot=i, mode="audio_only")
                self._engine.init_player_audio_only(i, audio_device)
                self._engine.load_file(i, audio_path)
                self._engine.set_volume(i, data["volume_slider"].value())
                launched = True
                continue

            screen_idx: int = data["monitor_combo"].currentData()
            screen = (
                self._screens[screen_idx]
                if screen_idx < len(self._screens)
                else self._screens[0]
            )

            DebugLog.record(
                "players.launch_slot",
                slot=i,
                mode="video",
                has_audio_override=bool(audio_path),
                fullscreen=self._fullscreen_toggle.isChecked(),
            )

            pw = PlayerWindow(i, self._engine)
            pw.close_all_requested.connect(self._close_players)
            pw.place_on_screen(
                screen,
                fullscreen=self._fullscreen_toggle.isChecked(),
            )
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
        active_count = len(self._engine._active)
        if not self._engine.has_active_players():
            DebugLog.record("transport.play_pause", result="no_active_players")
            return
        if self._engine.is_paused():
            DebugLog.record("transport.play", active=active_count)
            self._engine.play_all()
            self._btn_play.setText("⏸  Pause")
        else:
            DebugLog.record("transport.pause", active=active_count)
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
