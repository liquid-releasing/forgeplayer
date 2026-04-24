# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""ControlWindow — session-aware main panel for ForgePlayer."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QSlider, QComboBox, QFileDialog,
    QGroupBox, QCheckBox, QSizePolicy, QLineEdit, QSpacerItem,
    QMenu, QToolBar, QFrame, QTabWidget, QMessageBox, QScrollArea,
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
from app.library.pins import has_pin, load_pin, resolve_pin, save_pin
from app.debug_log import DebugLog
from app.widgets import ClickableSlider
from app.preferences import Preferences
from app.audio_test import play_tone_on_device

_SLOT_LABELS = ["▶ Video", "⚡ Stim", "▶ Video 2"]
_SLOT_ROLES = ["video", "stim", "mirror"]
_POLL_MS = 100
_MEDIA_FILTER = (
    "Media files (*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.m4a *.wav *.flac *.ogg);;"
    "All files (*)"
)
_VIDEO_FILTER = "Video files (*.mp4 *.mkv *.mov *.avi *.webm);;All files (*)"
_AUDIO_FILTER = "Audio files (*.mp3 *.m4a *.wav *.flac *.ogg);;All files (*)"
# Stim slot accepts native funscripts (v0.0.2 primary path) or pre-rendered
# audio files (v0.0.1 fallback). The synthesis engine picks the right
# pipeline based on file extension.
_FUNSCRIPT_FILTER = (
    "Haptic files (*.funscript *.mp3 *.m4a *.wav *.flac *.ogg);;"
    "Funscripts (*.funscript);;"
    "Audio files (*.mp3 *.m4a *.wav *.flac *.ogg);;"
    "All files (*)"
)
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

        # Apply the saved control-panel-screen preference BEFORE show()
        # lands the window. If we do this via a deferred singleShot, Qt
        # will first paint at the default position (triggering Windows'
        # "Unable to set geometry" warning as the DWM snaps the window
        # to the work area), then our move fires a frame later. Sync-
        # setting the geometry here avoids the warning entirely.
        self._apply_startup_screen_preference()

    def _apply_startup_screen_preference(self) -> None:
        idx = self._prefs.control_panel_screen
        if 0 <= idx < len(self._screens):
            self._move_to_screen(self._screens[idx])

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
        self._library_panel.scene_change_picks_requested.connect(
            lambda entry: self._on_scene_activated(entry, force_picker=True)
        )
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
        """Setup — Audio and Monitors shown side-by-side so both fit in a
        720p viewport with no scrolling (on a typical ~1000+ px wide control
        window). The user configures device roles once; Library clicks then
        auto-route Slot 1 to Scene Audio and Slot 2 to Haptic 1.
        """
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        title = QLabel("Setup")
        tf = title.font(); tf.setPointSize(18); tf.setBold(True); title.setFont(tf)
        outer.addWidget(title)

        # Save-status line (shared across both columns)
        self._setup_status = QLabel("")
        self._setup_status.setStyleSheet("color: #9ba3c4; font-size: 11px;")

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._build_setup_audio_page(), 1)
        columns.addWidget(self._build_setup_monitors_page(), 1)
        outer.addLayout(columns, 1)

        outer.addWidget(self._setup_status)
        return container

    def _build_setup_audio_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        subtitle = QLabel(
            "Pick which physical audio device handles each role. Library clicks "
            "use these to route automatically — you only set this once."
        )
        subtitle.setStyleSheet("color: #9ba3c4;")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

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

        rl.addLayout(self._labeled_row_with_test(
            "Scene audio", self._setup_scene_combo,
            "Video's embedded sound — typically your speakers or headphones.",
        ))
        rl.addLayout(self._labeled_row_with_test(
            "Haptic 1 (main stim)", self._setup_haptic1_combo,
            "Primary estim output — typically your USB audio dongle.",
        ))
        rl.addLayout(self._labeled_row_with_test(
            "Haptic 2 (prostate)", self._setup_haptic2_combo,
            "Optional second estim output for prostate channels. Leave unset if unused.",
        ))

        root.addWidget(role_box)
        root.addStretch()

        scroll.setWidget(inner)
        return scroll

    def _build_setup_monitors_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        subtitle = QLabel(
            "Which monitors host the control panel and video playback. "
            "Slot monitor pickers will only offer your checked playback screens."
        )
        subtitle.setStyleSheet("color: #9ba3c4;")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        monitor_box = QGroupBox("Monitor roles")
        ml = QVBoxLayout(monitor_box)
        ml.setSpacing(10)

        self._setup_control_screen_combo = QComboBox()
        self._setup_control_screen_combo.setMinimumHeight(32)
        self._setup_control_screen_combo.addItem("— auto —", -1)
        for idx, s in enumerate(self._screens):
            geo = s.geometry()
            self._setup_control_screen_combo.addItem(
                f"Screen {idx + 1}  —  {geo.width()}×{geo.height()}  ({s.name()})",
                idx,
            )
        for i in range(self._setup_control_screen_combo.count()):
            if self._setup_control_screen_combo.itemData(i) == self._prefs.control_panel_screen:
                self._setup_control_screen_combo.setCurrentIndex(i)
                break
        self._setup_control_screen_combo.currentIndexChanged.connect(
            self._on_control_screen_changed
        )

        ml.addLayout(self._labeled_row(
            "Control panel screen",
            self._setup_control_screen_combo,
            "Which monitor hosts this control window. Useful when you want "
            "playback on your external screens and the controls on your laptop.",
        ))

        pb_label = QLabel("Playback screens")
        pbl_font = pb_label.font(); pbl_font.setBold(True); pb_label.setFont(pbl_font)
        ml.addWidget(pb_label)

        pb_helper = QLabel(
            "Check the monitors you use for video. Slot monitor pickers will "
            "only offer these screens. Leave all unchecked to allow any screen."
        )
        pb_helper.setStyleSheet("color: #6b7280; font-size: 11px;")
        pb_helper.setWordWrap(True)
        ml.addWidget(pb_helper)

        self._setup_playback_checkboxes: list[QCheckBox] = []
        for idx, s in enumerate(self._screens):
            geo = s.geometry()
            cb = QCheckBox(
                f"Screen {idx + 1}  —  {geo.width()}×{geo.height()}  ({s.name()})"
            )
            cb.setChecked(idx in self._prefs.playback_screen_indices)
            cb.toggled.connect(self._on_playback_screens_changed)
            ml.addWidget(cb)
            self._setup_playback_checkboxes.append(cb)

        root.addWidget(monitor_box)
        root.addStretch()

        scroll.setWidget(inner)
        return scroll

    def _on_control_screen_changed(self) -> None:
        idx = self._setup_control_screen_combo.currentData()
        idx = int(idx) if idx is not None else -1
        self._prefs.control_panel_screen = idx
        self._prefs.save()
        DebugLog.record("setup.control_screen", index=idx)
        self._setup_status.setText(f"Saved to {Preferences.path()}")
        QTimer.singleShot(3000, lambda: self._setup_status.setText(""))
        # Move the window immediately if a valid screen was picked
        if 0 <= idx < len(self._screens):
            self._move_to_screen(self._screens[idx])

    def _move_to_screen(self, screen: QScreen) -> None:
        """Move the window to the target screen without forcing a resize.

        Before show(), self.width()/height() aren't reliable, and
        setGeometry(x, y, w, h) with a zeroed size makes Qt try to fit the
        layout's sizeHint at the requested position — which triggers
        'Unable to set geometry' warnings when the sizeHint slightly
        exceeds the screen's work area. Using ``move()`` with the layout's
        sizeHint lets the layout own the size and avoids the fight.
        """
        self.ensurePolished()
        hint = self.sizeHint()
        geo = screen.availableGeometry()
        x = geo.x() + max(0, (geo.width() - hint.width())) // 2
        y = geo.y() + max(0, (geo.height() - hint.height())) // 2
        self.move(x, y)

    def _on_playback_screens_changed(self) -> None:
        indices = [
            i for i, cb in enumerate(self._setup_playback_checkboxes) if cb.isChecked()
        ]
        self._prefs.playback_screen_indices = indices
        self._prefs.save()
        DebugLog.record("setup.playback_screens", indices=indices)
        self._setup_status.setText(f"Saved to {Preferences.path()}")
        QTimer.singleShot(3000, lambda: self._setup_status.setText(""))
        # Refresh slot monitor combos so they reflect the new allowed set.
        self._refresh_all_slot_monitor_combos()

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

    def _labeled_row_with_test(
        self, label_text: str, combo: QComboBox, help_text: str = "",
    ) -> QVBoxLayout:
        """Variant of _labeled_row that includes a 'Test' button which plays
        a short tone through the currently-selected device. Gives users an
        immediate, audible confirmation of whether the device actually
        outputs audio — the fastest way to diagnose 'why is my haptic silent?'
        problems (wrong device / OS-level mute / unplugged dongle)."""
        row = QVBoxLayout()
        row.setSpacing(2)

        label = QLabel(label_text)
        lf = label.font(); lf.setBold(True); label.setFont(lf)
        row.addWidget(label)

        combo_row = QHBoxLayout()
        combo_row.setSpacing(6)
        combo_row.addWidget(combo, 1)
        test_btn = QPushButton("🔊 Test")
        test_btn.setFixedHeight(32)
        test_btn.setFixedWidth(80)
        test_btn.setToolTip(
            "Play a half-second tone through this device.\n"
            "Silent? Check for OS-level per-app mute or unplugged hardware."
        )
        test_btn.clicked.connect(
            lambda _, c=combo: self._on_test_device(c)
        )
        combo_row.addWidget(test_btn)
        row.addLayout(combo_row)

        if help_text:
            helper = QLabel(help_text)
            helper.setStyleSheet("color: #6b7280; font-size: 11px;")
            helper.setWordWrap(True)
            row.addWidget(helper)
        return row

    def _on_test_device(self, combo: QComboBox) -> None:
        device_id = combo.currentData() or ""
        DebugLog.record(
            "setup.test_device",
            device=device_id or "(not set)",
        )
        if not device_id:
            self._setup_status.setText("Pick a device first, then press Test.")
            QTimer.singleShot(3000, lambda: self._setup_status.setText(""))
            return
        play_tone_on_device(device_id)
        self._setup_status.setText(
            f"Playing tone on: {combo.currentText()}"
        )
        QTimer.singleShot(2000, lambda: self._setup_status.setText(""))

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

    def _on_scene_activated(
        self, entry: SceneCatalogEntry, *, force_picker: bool = False,
    ) -> None:
        """Called when the user picks a scene in the Library panel.

        Pin-persistence flow (v0.0.1):

        - If a pin file exists for the scene and all referenced files still
          exist, skip the picker and replay the user's remembered choices.
        - Otherwise (first play, stale pin, or explicit "change picks"),
          show the picker pre-filled with defaults or the existing pin,
          then persist the new choices on accept.
        """
        choices: SelectionChoices | None = None

        pin = load_pin(entry) if not force_picker else None
        preselect: SelectionChoices | None = None

        if pin is not None:
            resolved = resolve_pin(entry, pin)
            if not resolved.is_stale:
                choices = SelectionChoices(
                    video=resolved.video,
                    audio=resolved.audio,
                    funscript_set=resolved.funscript_set,
                    subtitle=resolved.subtitle,
                )
                DebugLog.record("library.activate.pin_replayed", scene=entry.name)
            else:
                # Pin exists but some referenced file is gone — re-pick,
                # pre-selecting whatever the pin still matches.
                preselect = SelectionChoices(
                    video=resolved.video,
                    audio=resolved.audio,
                    funscript_set=resolved.funscript_set,
                    subtitle=resolved.subtitle,
                )
                DebugLog.record(
                    "library.activate.pin_stale",
                    scene=entry.name,
                    stale=resolved.stale_fields,
                )

        if choices is None:
            # Need user input — via picker if ambiguous or in change mode,
            # else scanner defaults.
            if entry.is_ambiguous or force_picker:
                picker = SelectPicker(
                    entry,
                    parent=self,
                    preselect=preselect,
                    change_mode=force_picker,
                )
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
                )

        # Persist the picks — auto-save on every successful activation.
        try:
            save_pin(
                entry,
                video=choices.video,
                audio=choices.audio,
                funscript_set=choices.funscript_set,
                subtitle=choices.subtitle,
            )
            DebugLog.record("library.pin_saved", scene=entry.name)
        except Exception as exc:
            DebugLog.record(
                "library.pin_save_failed", scene=entry.name, error=repr(exc)
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
        )

        slot1 = self._slot_data(0)
        slot2 = self._slot_data(1)
        slot3 = self._slot_data(2)

        # Mirror mode: 2+ checked playback screens + a video → same video
        # shows on Slot 1's monitor AND Slot 3's monitor in sync, with
        # Slot 3 muted (Slot 1 already carries the scene audio). One-screen
        # users and audio-only scenes keep the simpler 2-slot layout.
        playback_screens = self._prefs.playback_screen_indices
        mirror_video = (
            choices.video is not None
            and len(playback_screens) >= 2
        )

        if mirror_video:
            self._set_slot_media(
                slot1,
                video_path=choices.video.path,
                audio_path="",
            )
            self._select_slot_monitor(slot1, playback_screens[0])
            self._set_slot_media(
                slot3,
                video_path=choices.video.path,
                audio_path="",
            )
            self._select_slot_monitor(slot3, playback_screens[1])
            # Mute the mirror — Slot 1 already outputs scene audio.
            slot3["volume_slider"].setValue(0)
        else:
            # Slot 3 always clears in the non-mirror case.
            self._set_slot_media(slot3, video_path="", audio_path="")
            if choices.video:
                self._set_slot_media(
                    slot1,
                    video_path=choices.video.path,
                    audio_path="",
                )
                if playback_screens:
                    self._select_slot_monitor(slot1, playback_screens[0])
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

    def _select_slot_monitor(self, slot_data: dict, screen_index: int) -> None:
        """Pick a specific screen for a slot's monitor dropdown (used by
        library routing / mirror mode). Silently no-ops if the screen isn't
        in the slot's current combo — typically because Setup filtered it
        out of the playback pool."""
        combo: QComboBox = slot_data["monitor_combo"]
        for idx in range(combo.count()):
            if combo.itemData(idx) == screen_index:
                combo.setCurrentIndex(idx)
                return

    def _populate_monitor_combo(
        self, combo: QComboBox, *, default_index: int,
    ) -> None:
        """Fill a slot's monitor dropdown with the screens allowed for
        playback (per Setup's playback-screens checkboxes). Falls back to
        all screens when Setup hasn't explicitly opted in to filtering."""
        allowed = set(self._prefs.playback_screen_indices)
        combo.clear()
        first_added_index = -1
        for j, s in enumerate(self._screens):
            if allowed and j not in allowed:
                continue
            geo = s.geometry()
            combo.addItem(
                f"Screen {j + 1}  —  {geo.width()}×{geo.height()}  ({s.name()})",
                j,
            )
            if first_added_index < 0:
                first_added_index = j
        # Try to match the requested default; otherwise first allowed screen.
        want = default_index
        if allowed and want not in allowed and first_added_index >= 0:
            want = first_added_index
        for idx in range(combo.count()):
            if combo.itemData(idx) == want:
                combo.setCurrentIndex(idx)
                break

    def _refresh_all_slot_monitor_combos(self) -> None:
        """Re-populate each slot's monitor dropdown after Setup changes,
        preserving the current selection when possible."""
        for slot_idx in range(3):
            data = self._slot_data(slot_idx)
            combo: QComboBox = data["monitor_combo"]
            current = combo.currentData() if combo.currentData() is not None else slot_idx
            self._populate_monitor_combo(combo, default_index=int(current))

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
            data["audio_label"].setToolTip(audio_path)
        self._refresh_audio_label(data)
        self._refresh_monitor_state(data)

    @staticmethod
    def _refresh_audio_label(data: dict) -> None:
        """Render the Audio-override label from whichever of (override
        audio, embedded video audio, nothing) is currently in effect.

        When no override is set, we show ``(from <video filename>)`` so
        the user sees WHICH source the slot is actually playing — more
        informative than the old ``(uses video audio)`` placeholder.
        """
        audio = data.get("audio_path", "")
        video = data.get("video_path", "")
        if audio:
            text = os.path.basename(audio)
        elif video:
            text = f"(from {os.path.basename(video)})"
        else:
            text = "(no audio)"
        data["audio_label"].setText(text)

    def _build_session_bar(self) -> QWidget:
        """Top bar: session-name label + Debug dogfood cluster.

        The New/Open/Recent/Save/Save As/Scan Folder buttons were removed
        2026-04-24: Library tab is the only way to load content now, and
        session-file management is being superseded by auto pin persistence
        (see project_forgeplayer_pin_persistence.md). The session-name
        field remains as a read-only title display of the currently-loaded
        scene.
        """
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        h.addWidget(QLabel("Session:"))
        self._session_name = QLineEdit("Untitled Session")
        self._session_name.setFixedHeight(30)
        self._session_name.setFixedWidth(320)
        self._session_name.setReadOnly(True)
        self._session_name.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: #e0e0e0; }"
        )
        h.addWidget(self._session_name)

        h.addStretch()

        # ── Debug cluster (dogfood only — hide for release) ─────────────
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
        """Dispatch to the role-specific builder.

        v0.0.2 slot cards are role-specific, not uniform:
        - index 0 → Video slot (video file + monitor + scene audio)
        - index 1 → Stim slot (funscript + Haptic 1 device; no video, no monitor)
        - index 2 → Video 2 mirror slot (monitor picker only; inherits video
          from the Video slot at launch)

        Each builder returns a QGroupBox with a `_slot_data` attribute of
        the same shape (shared keys), so downstream callers
        (`_apply_scene_choices`, `_current_session`, `_launch_players`,
        etc.) keep working without knowing the role. Keys that a role
        doesn't expose in the UI are still present in the dict — they
        point at hidden widgets so `d["audio_combo"].currentData()` never
        raises KeyError.
        """
        role = _SLOT_ROLES[index]
        if role == "video":
            return self._build_video_slot(index)
        if role == "stim":
            return self._build_stim_slot(index)
        if role == "mirror":
            return self._build_mirror_slot(index)
        raise ValueError(f"Unknown slot role: {role!r}")

    # ── Role-specific slot builders ───────────────────────────────────────

    def _build_video_slot(self, index: int) -> QGroupBox:
        """Video slot: main video + scene audio output. No picked-audio
        override — the mp4's embedded audio IS the scene audio, routed
        through the configured audio device."""
        box = QGroupBox(_SLOT_LABELS[index])
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        # ── Video block ──────────────────────────────────────────────────
        video_block = self._build_block_frame()
        vb = QVBoxLayout(video_block)
        vb.setContentsMargins(10, 8, 10, 10)
        vb.setSpacing(4)
        vb.addWidget(self._block_heading("Video"))

        video_label = self._build_path_label("No file selected")
        vb.addWidget(video_label)

        video_row, btn_video, btn_clear_video = self._build_file_picker_row(
            "Browse Video…",
            clear_tooltip="Clear video (also disables the slot if audio is also empty)",
        )
        vb.addLayout(video_row)

        vb.addWidget(self._sub_label("Monitor"))
        monitor_combo = QComboBox()
        self._populate_monitor_combo(monitor_combo, default_index=index)
        vb.addWidget(monitor_combo)

        layout.addWidget(video_block)

        # ── Scene Audio block ───────────────────────────────────────────
        scene_audio_block = self._build_block_frame()
        sb = QVBoxLayout(scene_audio_block)
        sb.setContentsMargins(10, 8, 10, 10)
        sb.setSpacing(4)
        sb.addWidget(self._block_heading("Scene Audio"))

        sb.addWidget(self._sub_label("Device"))
        audio_combo = self._build_audio_device_combo()
        sb.addWidget(audio_combo)

        vol_row, volume_slider, vol_lbl = self._build_volume_row()
        sb.addLayout(vol_row)

        layout.addWidget(scene_audio_block)

        # Hidden widgets that keep slot_data shape stable for downstream
        # callers. The Video slot has no picked-audio override, so
        # audio_label/audio_path exist as placeholders only.
        audio_label = self._build_hidden_label(box)

        slot_data = self._make_slot_data(
            video_label=video_label,
            audio_label=audio_label,
            monitor_combo=monitor_combo,
            audio_combo=audio_combo,
            volume_slider=volume_slider,
            vol_lbl=vol_lbl,
        )

        btn_video.clicked.connect(lambda _, d=slot_data: self._on_browse_video(d))
        btn_clear_video.clicked.connect(lambda _, d=slot_data: self._on_clear_video(d))
        volume_slider.valueChanged.connect(
            lambda v, idx=index, lbl=vol_lbl: self._on_volume_changed(idx, v, lbl)
        )

        box._slot_data = slot_data  # type: ignore[attr-defined]
        return box

    def _build_stim_slot(self, index: int) -> QGroupBox:
        """Stim slot: funscript (or pre-rendered audio fallback) + Haptic 1
        device picker. No video, no monitor, no software volume — estim
        intensity is set on the hardware device, and Calibrate (v0.0.2
        item #5) is the UX for dialing it in before playback."""
        box = QGroupBox(_SLOT_LABELS[index])
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        # ── Funscript block (replaces the v0.0.1 "Audio override") ──────
        funscript_block = self._build_block_frame()
        fb = QVBoxLayout(funscript_block)
        fb.setContentsMargins(10, 8, 10, 10)
        fb.setSpacing(4)
        fb.addWidget(self._block_heading("Funscript"))

        audio_label = self._build_path_label("(no funscript)")
        fb.addWidget(audio_label)

        fs_row, btn_funscript, btn_clear_funscript = self._build_file_picker_row(
            "Browse Funscript…",
            clear_tooltip="Clear funscript / audio track",
        )
        fb.addLayout(fs_row)

        fb.addWidget(self._sub_label(
            "Primary: .funscript (real-time synthesis). "
            "Fallback: pre-rendered .mp3 / .wav."
        ))

        layout.addWidget(funscript_block)

        # ── Haptic 1 block (main estim channel) ─────────────────────────
        haptic1_block = self._build_block_frame()
        hb = QVBoxLayout(haptic1_block)
        hb.setContentsMargins(10, 8, 10, 10)
        hb.setSpacing(4)
        hb.addWidget(self._block_heading("Haptic 1 (main)"))

        hb.addWidget(self._sub_label("Device"))
        audio_combo = self._build_audio_device_combo()
        hb.addWidget(audio_combo)

        hb.addWidget(self._sub_label(
            "Intensity is set on the device itself — use Calibrate "
            "before starting the scene."
        ))

        layout.addWidget(haptic1_block)

        # '+ Add second channel' expander is wired up in a later PR
        # (project_forgeplayer_v002_slot_cards.md item 3). Kept out of the
        # UI until it actually does something, so users don't click an
        # inert button.

        layout.addStretch(1)

        # Hidden widgets — Stim slot carries no video, no monitor,
        # no software volume. Widgets exist so slot_data shape stays
        # compatible with the Video slot.
        video_label = self._build_hidden_label(box)
        monitor_combo = self._build_hidden_monitor_combo(box)
        volume_slider, vol_lbl = self._build_hidden_volume(box, default=100)

        slot_data = self._make_slot_data(
            video_label=video_label,
            audio_label=audio_label,
            monitor_combo=monitor_combo,
            audio_combo=audio_combo,
            volume_slider=volume_slider,
            vol_lbl=vol_lbl,
        )

        btn_funscript.clicked.connect(lambda _, d=slot_data: self._on_browse_audio(d))
        btn_clear_funscript.clicked.connect(lambda _, d=slot_data: self._on_clear_audio(d))

        box._slot_data = slot_data  # type: ignore[attr-defined]
        return box

    def _build_mirror_slot(self, index: int) -> QGroupBox:
        """Video 2 mirror slot: monitor picker only. Inherits the video +
        scene audio from the Video slot at launch time and plays muted
        on its own monitor. In v0.0.2 phase-2, this card gets the
        ultrawide Layout block (Crop / Letterbox / Side-by-side)."""
        box = QGroupBox(_SLOT_LABELS[index])
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        # Mirror-mode explainer
        note = QLabel("↔ Mirrors the Video slot on this monitor (muted).")
        note.setStyleSheet("color: #9ba3c4; font-size: 11px; font-style: italic;")
        note.setWordWrap(True)
        layout.addWidget(note)

        # ── Monitor block (the only real control) ───────────────────────
        monitor_block = self._build_block_frame()
        mb = QVBoxLayout(monitor_block)
        mb.setContentsMargins(10, 8, 10, 10)
        mb.setSpacing(4)
        mb.addWidget(self._block_heading("Monitor"))

        monitor_combo = QComboBox()
        self._populate_monitor_combo(monitor_combo, default_index=index)
        mb.addWidget(monitor_combo)

        layout.addWidget(monitor_block)
        layout.addStretch(1)

        # Hidden widgets — mirror carries no file picker, no audio device,
        # no volume (fixed-muted). Widgets exist so slot_data stays stable.
        video_label = self._build_hidden_label(box)
        audio_label = self._build_hidden_label(box)
        audio_combo = QComboBox(box)
        audio_combo.setVisible(False)
        for name, desc in self._audio_devices:
            audio_combo.addItem(desc, name)
        volume_slider, vol_lbl = self._build_hidden_volume(box, default=0)

        slot_data = self._make_slot_data(
            video_label=video_label,
            audio_label=audio_label,
            monitor_combo=monitor_combo,
            audio_combo=audio_combo,
            volume_slider=volume_slider,
            vol_lbl=vol_lbl,
        )

        box._slot_data = slot_data  # type: ignore[attr-defined]
        return box

    # ── Small widget factories shared by the builders ─────────────────────

    @staticmethod
    def _make_slot_data(
        *, video_label, audio_label, monitor_combo, audio_combo,
        volume_slider, vol_lbl,
    ) -> dict:
        return {
            "video_label":    video_label,
            "video_path":     "",
            "audio_label":    audio_label,
            "audio_path":     "",
            "monitor_combo":  monitor_combo,
            "audio_combo":    audio_combo,
            "volume_slider":  volume_slider,
            "vol_lbl":        vol_lbl,
        }

    @staticmethod
    def _build_path_label(placeholder: str) -> QLabel:
        lbl = QLabel(placeholder)
        lbl.setWordWrap(False)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lbl.setStyleSheet("color: #9ba3c4; font-size: 11px;")
        return lbl

    @staticmethod
    def _build_file_picker_row(
        browse_label: str, clear_tooltip: str,
    ) -> tuple[QHBoxLayout, QPushButton, QPushButton]:
        row = QHBoxLayout()
        row.setSpacing(4)
        btn_browse = QPushButton(browse_label)
        btn_browse.setFixedHeight(28)
        row.addWidget(btn_browse)
        btn_clear = QPushButton("✕")
        btn_clear.setFixedSize(28, 28)
        btn_clear.setToolTip(clear_tooltip)
        row.addWidget(btn_clear)
        return row, btn_browse, btn_clear

    def _build_audio_device_combo(self) -> QComboBox:
        combo = QComboBox()
        for name, desc in self._audio_devices:
            combo.addItem(desc, name)
        return combo

    def _build_volume_row(self) -> tuple[QHBoxLayout, "ClickableSlider", QLabel]:
        row = QHBoxLayout()
        row.addWidget(self._sub_label("Volume"))
        slider = ClickableSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(100)
        slider.setFixedHeight(22)
        row.addWidget(slider)
        lbl = QLabel("100")
        lbl.setFixedWidth(28)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(lbl)
        return row, slider, lbl

    @staticmethod
    def _build_hidden_label(parent) -> QLabel:
        lbl = QLabel(parent)
        lbl.setVisible(False)
        return lbl

    def _build_hidden_monitor_combo(self, parent) -> QComboBox:
        combo = QComboBox(parent)
        combo.setVisible(False)
        self._populate_monitor_combo(combo, default_index=0)
        return combo

    @staticmethod
    def _build_hidden_volume(parent, default: int) -> tuple["ClickableSlider", QLabel]:
        slider = ClickableSlider(Qt.Orientation.Horizontal, parent)
        slider.setRange(0, 100)
        slider.setValue(default)
        slider.setVisible(False)
        lbl = QLabel(str(default), parent)
        lbl.setVisible(False)
        return slider, lbl

    # ── Slot-card visual helpers ──────────────────────────────────────────

    @staticmethod
    def _build_block_frame() -> QFrame:
        """Subtle-contrast container for the Video / Audio sub-blocks
        inside a slot card."""
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #1a1d27; border: 1px solid #2d3148; "
            "border-radius: 6px; }"
        )
        return frame

    @staticmethod
    def _block_heading(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #ff6b30; font-size: 11px; font-weight: bold; "
            "text-transform: uppercase; letter-spacing: 1px; "
            "background: transparent; border: none;"
        )
        return lbl

    @staticmethod
    def _sub_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #9ba3c4; font-size: 10px; "
            "background: transparent; border: none;"
        )
        return lbl

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _slot_data(self, index: int) -> dict:
        return self._slot_widgets[index]._slot_data  # type: ignore[attr-defined]

    def _screen_sizes(self) -> list[tuple[int, int]]:
        return [(s.geometry().width(), s.geometry().height()) for s in self._screens]

    # ── Browse callbacks ───────────────────────────────────────────────────────

    def _on_browse_video(self, data: dict) -> None:
        DebugLog.record("browse.video.dialog_open")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select video file", "", _VIDEO_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        DebugLog.record("browse.video.dialog_closed", picked=bool(path))
        if path:
            data["video_path"] = path
            data["video_label"].setText(os.path.basename(path))
            data["video_label"].setToolTip(path)
            self._refresh_monitor_state(data)
            self._maybe_autofill_session_name(path)
            # Apply Setup's audio-device roles so the slot's audio-output
            # reflects the configured Scene / Haptic device instead of
            # mpv's Autoselect fallback.
            self._apply_setup_roles_to_slots()

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
        DebugLog.record("browse.audio.dialog_open")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select audio file", "", _AUDIO_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        DebugLog.record("browse.audio.dialog_closed", picked=bool(path))
        if path:
            data["audio_path"] = path
            data["audio_label"].setText(os.path.basename(path))
            data["audio_label"].setToolTip(path)
            self._refresh_monitor_state(data)
            if not data["video_path"]:
                self._maybe_autofill_session_name(path)

    def _on_clear_audio(self, data: dict) -> None:
        data["audio_path"] = ""
        data["audio_label"].setToolTip("")
        self._refresh_audio_label(data)
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
        folder = QFileDialog.getExistingDirectory(
            self, "Select media folder", "",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
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
            data["audio_label"].setToolTip(ap)
            self._refresh_audio_label(data)

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
            d["audio_label"].setToolTip(cfg.audio_path)
            self._refresh_audio_label(d)

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
            self, "Open session", "", _SESSION_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
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
            options=QFileDialog.Option.DontUseNativeDialog,
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
