# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""ControlWindow — session-aware main panel for ForgePlayer."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QSlider, QComboBox, QFileDialog,
    QGroupBox, QCheckBox, QSizePolicy, QLineEdit, QSpacerItem,
    QMenu, QToolBar, QFrame, QTabWidget, QMessageBox, QScrollArea,
    QRadioButton, QButtonGroup, QDoubleSpinBox,
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
from app.stim_preview import play_test_clip as play_haptic_test_clip

_SLOT_LABELS = ["▶ Video", "⚡ Stim", "▶ Video 2", "▶ Video 3"]
_SLOT_ROLES = ["video", "stim", "mirror", "mirror"]
# Single source of truth for slot count — also drives sync_engine's
# MAX_SLOTS. Iteration loops use this rather than hardcoded literals so
# adding more mirror slots later is just a label/role list edit.
_NUM_SLOTS = len(_SLOT_LABELS)
_POLL_MS = 100

# Light-touch label style for the Fullscreen toggle on Live's dark
# Video panel — default Qt indicator (preserving its built-in check
# glyph) plus a brighter label color. Earlier attempt set
# QCheckBox::indicator { border: ...; } to make the unchecked indicator
# visible, but touching ANY indicator subcontrol drops Qt's default
# check glyph: the box looked the same checked or unchecked, so users
# thought the control was disabled. Backing off to label-only styling.
_CHECKBOX_ON_DARK_STYLE = (
    "QCheckBox { color: #cbd1e0; font-size: 13px; spacing: 8px; }"
)
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
        # Initial size targets the 1090×720 touchpad as the spiritual
        # minimum + a bit of breathing room. On larger displays the
        # user can drag to resize; we don't auto-maximize.
        self.resize(1280, 760)

        self._engine = SyncEngine()
        self._player_windows: list[PlayerWindow | None] = [None] * _NUM_SLOTS
        self._seek_dragging = False
        self._session_path: str = ""

        # Discover screens and audio devices (HDMI phantom devices filtered
        # out — they confuse the Scene/Haptic role picker).
        self._screens: list[QScreen] = self.screen().virtualSiblings()
        raw_devices = SyncEngine.list_audio_devices()
        self._audio_devices: list[tuple[str, str]] = (
            self._disambiguate_audio_descriptions(raw_devices)
        )

        # Load persisted device-role preferences (Scene / Haptic 1 / Haptic 2).
        self._prefs = Preferences.load()

        # Slot data — per-mpv-player media + stream state. The 4-slot
        # grid UI is gone in v0.0.4; slots remain as the SyncEngine's
        # internal index. Populated here so _build_live_tab can wire
        # _refresh_live_panels against an initialized list.
        self._slots: list[dict] = [
            self._make_slot_data() for _ in range(_NUM_SLOTS)
        ]

        # Calibration streams — one per haptic port. None means no
        # active calibration. See _update_calibrate_buttons_enabled.
        self._calib_h1 = None  # type: object | None
        self._calib_h2 = None  # type: object | None
        # Whether Play has been hit at least once since the last Launch.
        # Calibrate is locked between first Play and Close — per spec,
        # the launched stim streams own the haptic devices once playback
        # has started. Resets on Close. Calibrate IS allowed during the
        # post-Launch / pre-Play window (windows up but paused).
        self._has_played_since_launch: bool = False

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

        # ── Tab container — Library | Live | Setup | Preferences ──
        # Order reflects the user-flow journey: Library (pick a scene)
        # → Live (drive playback) → Setup (one-time hardware wiring)
        # → Preferences (rare behavior tuning). Setup and Preferences
        # are separated so each has a focused mental model: Setup =
        # "what I plugged in", Preferences = "how I want it to behave."
        self._tabs = QTabWidget()

        self._library_panel = LibraryPanel()
        self._library_panel.scene_activated.connect(self._on_scene_activated)
        self._library_panel.scene_change_picks_requested.connect(
            lambda entry: self._on_scene_activated(entry, force_picker=True)
        )
        self._tabs.addTab(self._library_panel, "Library")
        self._tabs.addTab(self._build_live_tab(), "Live")
        self._tabs.addTab(self._build_setup_tab(), "Setup")
        self._tabs.addTab(self._build_preferences_tab(), "Preferences")

        vbox.addWidget(self._tabs, 1)

        # Default to Library on startup — returning users with a scanned
        # root want to land on their scenes, first-run users get a welcome
        # empty-state inside the Library panel pointing them at Scan Folder.
        self._tabs.setCurrentWidget(self._library_panel)

    def _build_live_tab(self) -> QWidget:
        """Live — the cockpit tab. Pure read-only display (Video panel +
        Output panel) plus the editable runtime controls (transport,
        Launch / Close, Fullscreen toggle). All routing decisions live
        in Setup; Live just shows what's resolved.

        Slots remain as an internal data model (the SyncEngine still
        addresses 4 mpv players by index) but the slot grid UI is gone.
        Slot data lives in `self._slots` and is rendered by
        `_refresh_live_panels()` whenever scene/setup state changes.
        """
        tab = QWidget()
        vbox = QVBoxLayout(tab)
        vbox.setSpacing(10)
        vbox.setContentsMargins(10, 10, 10, 10)

        # ── Video + Output panels (read-only) ──
        # Side-by-side on the 1090×720 touchpad. Stacked at narrower
        # widths is a future polish; for now both panels share the
        # window width 50/50.
        panels_row = QHBoxLayout()
        panels_row.setSpacing(10)
        panels_row.addWidget(self._build_video_panel(), 1)
        panels_row.addWidget(self._build_output_panel(), 1)
        vbox.addLayout(panels_row, 1)

        # ── Timeline + Scene volume row ──
        # Side-by-side: timeline takes ~75 %, volume the right ~25 %.
        # Each slider gets its own header label above so the two
        # controls read as visually distinct — the user was grabbing
        # the volume slider thinking it was the timeline before the
        # split layout (2026-05-03 dogfood). Volume is ephemeral
        # (per-session, default 100 %) and only touches the video
        # slot's mpv player; the synth path is on a separate device.
        controls_row = QHBoxLayout()
        controls_row.setSpacing(16)

        # Timeline column ─────────────────────────────────────────
        timeline_col = QVBoxLayout()
        timeline_col.setSpacing(4)

        timeline_header = QHBoxLayout()
        self._time_label = QLabel("0:00")
        self._time_label.setStyleSheet("color: #9ba3c4; font-size: 12px;")
        timeline_header.addWidget(self._time_label)
        timeline_header.addStretch()
        self._dur_label = QLabel("0:00")
        self._dur_label.setStyleSheet("color: #9ba3c4; font-size: 12px;")
        self._dur_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        timeline_header.addWidget(self._dur_label)
        timeline_col.addLayout(timeline_header)

        self._seek_bar = ClickableSlider(Qt.Orientation.Horizontal)
        self._seek_bar.setRange(0, 10000)
        # Tall enough for a thumb hit on a touchscreen.
        self._seek_bar.setMinimumHeight(48)
        self._seek_bar.sliderPressed.connect(self._on_seek_press)
        self._seek_bar.sliderReleased.connect(self._on_seek_release)
        timeline_col.addWidget(self._seek_bar)

        # Volume column ───────────────────────────────────────────
        volume_col = QVBoxLayout()
        volume_col.setSpacing(4)

        self._scene_volume_label = QLabel("🔊  Scene volume — 100%")
        self._scene_volume_label.setStyleSheet(
            "color: #9ba3c4; font-size: 12px;"
        )
        volume_col.addWidget(self._scene_volume_label)

        self._scene_volume_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self._scene_volume_slider.setRange(0, 100)
        self._scene_volume_slider.setValue(100)
        self._scene_volume_slider.setMinimumHeight(48)
        self._scene_volume_slider.valueChanged.connect(self._on_scene_volume_changed)
        volume_col.addWidget(self._scene_volume_slider)

        controls_row.addLayout(timeline_col, 3)
        controls_row.addLayout(volume_col, 1)
        vbox.addLayout(controls_row)

        # ── Transport controls ──
        # Touch-friendly heights (52px) optimized for the 1090×720
        # touchscreen. Prev/Next chapter and the Calibrate row land in
        # the next commit.
        transport = QHBoxLayout()
        transport.setSpacing(8)
        transport.addStretch()

        for label, fn in [
            ("−30s", lambda: self._skip(-30)),
            ("−10s", lambda: self._skip(-10)),
            ("−5s",  lambda: self._skip(-5)),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(52)
            b.setMinimumWidth(64)
            b.setStyleSheet("font-size: 13px;")
            b.clicked.connect(fn)
            transport.addWidget(b)

        self._btn_play = QPushButton("▶  Play")
        self._btn_play.setFixedWidth(140)
        self._btn_play.setFixedHeight(52)
        self._btn_play.setStyleSheet(
            "background: #ff4b4b; color: white; font-weight: bold; "
            "font-size: 16px; border-radius: 6px;"
        )
        self._btn_play.clicked.connect(self._on_play_pause)
        transport.addWidget(self._btn_play)

        btn_stop = QPushButton("⏹  Stop")
        btn_stop.setFixedHeight(52)
        btn_stop.setMinimumWidth(80)
        btn_stop.setStyleSheet("font-size: 13px;")
        btn_stop.clicked.connect(self._on_stop)
        transport.addWidget(btn_stop)

        for label, fn in [
            ("+5s",  lambda: self._skip(5)),
            ("+10s", lambda: self._skip(10)),
            ("+30s", lambda: self._skip(30)),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(52)
            b.setMinimumWidth(64)
            b.setStyleSheet("font-size: 13px;")
            b.clicked.connect(fn)
            transport.addWidget(b)

        transport.addStretch()
        vbox.addLayout(transport)

        # ── Calibrate row ──
        # Pre-flight tool: tap Calibrate H1 / H2 to loop the funscript's
        # peak-intensity window through the matching haptic dongle so
        # the user can dial in a comfortable knob setting before hitting
        # Play. Tap-toggle (tap to start, tap again to stop). Locked
        # once Launch fires (until Close) so calibration doesn't fight
        # the launched stream for the same exclusive device handle.
        # The 5s ramp checkbox fades the audio from silence to peak over
        # five seconds — useful when the dongle's volume is set high.
        calib_row = QHBoxLayout()
        calib_row.setSpacing(8)
        calib_row.addStretch()
        calib_label = QLabel("Pre-flight funscript:")
        calib_label.setStyleSheet("color: #9ba3c4; font-size: 13px;")
        calib_row.addWidget(calib_label)

        # `:checked` styling makes the active state unmistakable — Qt's
        # default pressed-look on a dark theme reads as "still idle" to
        # users mid-dogfood. Red background + bold matches the Play
        # button's "currently doing this thing" convention.
        _calib_style = (
            "QPushButton { font-size: 13px; }"
            "QPushButton:checked { background: #ff4b4b; color: white; "
            "font-weight: bold; border-radius: 6px; }"
        )

        self._btn_calibrate_h1 = QPushButton("Calibrate H1")
        self._btn_calibrate_h1.setFixedHeight(44)
        self._btn_calibrate_h1.setMinimumWidth(120)
        self._btn_calibrate_h1.setCheckable(True)
        self._btn_calibrate_h1.setStyleSheet(_calib_style)
        self._btn_calibrate_h1.clicked.connect(self._on_calibrate_h1)
        calib_row.addWidget(self._btn_calibrate_h1)

        self._btn_calibrate_h2 = QPushButton("Calibrate H2")
        self._btn_calibrate_h2.setFixedHeight(44)
        self._btn_calibrate_h2.setMinimumWidth(120)
        self._btn_calibrate_h2.setCheckable(True)
        self._btn_calibrate_h2.setStyleSheet(_calib_style)
        self._btn_calibrate_h2.clicked.connect(self._on_calibrate_h2)
        calib_row.addWidget(self._btn_calibrate_h2)
        # Tooltips explain why a button might be disabled — Qt's
        # default disabled rendering on this dark stylesheet is subtle
        # and reads as "broken click" without a hint.
        self._btn_calibrate_h1.setToolTip(
            "Loop the scene's haptic peak through the Haptic 1 device. "
            "Tap to start, tap again to stop. Available pre-Launch and "
            "post-Launch (paused). Locked once Play has been hit — "
            "close players to re-enable."
        )
        self._btn_calibrate_h2.setToolTip(
            "Loop the scene's haptic peak through the Haptic 2 device. "
            "Tap to start, tap again to stop. Available pre-Launch and "
            "post-Launch (paused). Locked once Play has been hit — "
            "close players to re-enable."
        )

        self._chk_calibrate_ramp = QCheckBox("5s ramp")
        self._chk_calibrate_ramp.setStyleSheet(_CHECKBOX_ON_DARK_STYLE)
        self._chk_calibrate_ramp.setToolTip(
            "Fade calibration audio from silence to peak intensity over "
            "five seconds. Safer when dialing in dongle volume from a "
            "high knob setting."
        )
        calib_row.addWidget(self._chk_calibrate_ramp)

        calib_row.addStretch()
        vbox.addLayout(calib_row)

        # ── Launch / Close buttons ──
        action_row = QHBoxLayout()
        action_row.addStretch()

        btn_close_players = QPushButton("Close Players")
        btn_close_players.setFixedHeight(56)
        btn_close_players.setMinimumWidth(140)
        btn_close_players.setStyleSheet("font-size: 14px;")
        btn_close_players.clicked.connect(self._close_players)
        action_row.addWidget(btn_close_players)

        btn_launch = QPushButton("Launch Players")
        btn_launch.setFixedHeight(56)
        btn_launch.setFixedWidth(200)
        btn_launch.setStyleSheet(
            "background: #2d6a4f; color: white; font-weight: bold; "
            "font-size: 16px; border-radius: 6px;"
        )
        btn_launch.clicked.connect(self._on_launch)
        action_row.addWidget(btn_launch)

        action_row.addStretch()
        vbox.addLayout(action_row)

        # Initial panel paint — show "(no scene loaded)" + Setup-derived
        # port labels rather than the empty placeholders the panel
        # builders left behind.
        self._refresh_live_panels()
        # Initial calibrate-button enable state based on currently loaded
        # scene + Setup prefs.
        self._update_calibrate_buttons_enabled()

        return tab

    # ── Live panel builders ─────────────────────────────────────────────────

    def _build_video_panel(self) -> QGroupBox:
        """Read-only Video panel. Shows: scene file (if loaded), the
        list of monitors video will play on (read from Setup's
        playback_screen_indices), per-monitor fill mode (read from
        Setup's fill_screen_indices), and the per-session Fullscreen
        toggle (the one editable in this panel — fullscreen is a
        right-now choice, not a routing decision).
        """
        box = QGroupBox("Video")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        self._video_file_label = QLabel("(no scene loaded)")
        self._video_file_label.setStyleSheet("font-size: 14px;")
        self._video_file_label.setWordWrap(True)
        layout.addWidget(self._video_file_label)

        # Monitors block — populated by _refresh_live_panels.
        self._video_monitors_label = QLabel("")
        self._video_monitors_label.setStyleSheet("color: #9ba3c4; font-size: 13px;")
        self._video_monitors_label.setWordWrap(True)
        layout.addWidget(self._video_monitors_label)

        layout.addStretch(1)

        # Fullscreen toggle lives at the bottom of the Video panel —
        # right under the monitor list it affects. Pre-redesign this
        # was an action-row checkbox between Close and Launch; the
        # video-tab home is more discoverable.
        self._fullscreen_toggle = QCheckBox("Fullscreen players")
        self._fullscreen_toggle.setToolTip(
            "When on, player windows take over their whole monitor (kiosk mode).\n"
            "When off (default), windowed players let you keep your desktop visible.\n"
            "Press F11 inside a player to toggle fullscreen at any time."
        )
        # The Video panel background is dark (~#1a1d27); a default Qt
        # checkbox border is similar grey on the same shade, so the
        # whole indicator vanishes. Just brightening the border line
        # restores visibility without changing size or any other
        # checkbox visuals.
        self._fullscreen_toggle.setStyleSheet(_CHECKBOX_ON_DARK_STYLE)
        layout.addWidget(self._fullscreen_toggle)

        return box

    def _build_output_panel(self) -> QGroupBox:
        """Read-only Output panel. One row per audio destination
        (Scene / Haptic 1 / Haptic 2). Each row shows:
          → <Role>: <Port> (set in Setup)
              <filename> or `(silent — <reason>)`
        """
        box = QGroupBox("Output")
        layout = QVBoxLayout(box)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # Each row is a (port_label, source_label) pair so refresh can
        # update the source line independently of the port assignment.
        self._output_scene_port = self._make_port_label()
        self._output_scene_source = self._make_source_label()
        layout.addLayout(self._make_output_row(
            self._output_scene_port, self._output_scene_source,
        ))

        self._output_h1_port = self._make_port_label()
        self._output_h1_source = self._make_source_label()
        layout.addLayout(self._make_output_row(
            self._output_h1_port, self._output_h1_source,
        ))

        self._output_h2_port = self._make_port_label()
        self._output_h2_source = self._make_source_label()
        layout.addLayout(self._make_output_row(
            self._output_h2_port, self._output_h2_source,
        ))

        layout.addStretch(1)
        return box

    @staticmethod
    def _make_port_label() -> QLabel:
        lbl = QLabel("")
        lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        lbl.setWordWrap(True)
        return lbl

    @staticmethod
    def _make_source_label() -> QLabel:
        lbl = QLabel("")
        lbl.setStyleSheet("color: #9ba3c4; font-size: 12px;")
        lbl.setWordWrap(True)
        lbl.setContentsMargins(16, 0, 0, 0)
        return lbl

    @staticmethod
    def _make_output_row(port_label: QLabel, source_label: QLabel) -> QVBoxLayout:
        row = QVBoxLayout()
        row.setSpacing(2)
        row.addWidget(port_label)
        row.addWidget(source_label)
        return row

    def _refresh_live_panels(self) -> None:
        """Re-render the Video and Output panel labels from current
        slot_data + prefs. Called after any state change (scene
        activation, Setup change, file clear, launch).
        """
        # Refresh the cached QScreen list from Qt — same dangling-ref
        # protection as `_on_launch`. After player windows tear down
        # (Close Players), Qt invalidates the underlying C++ QScreen
        # objects while our Python references stay live; the next
        # `s.geometry()` call raises libshiboken "Internal C++ object
        # already deleted" and the exception kills the calling slot
        # mid-execution. _apply_scene_choices's downstream funscript-
        # dispatch then never runs, so a scene picked AFTER closing
        # players appears to load (panels switch, debug log records
        # `library.activate`) but `funscript_set` never lands on the
        # stim slot — calibrate buttons stay disabled.
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
        self._screens = list(QGuiApplication.screens())

        # ── Video panel ─────────────────────────────────────────────
        slot0 = self._slots[0]
        video_path: str = slot0.get("video_path", "")
        if video_path:
            self._video_file_label.setText(os.path.basename(video_path))
            self._video_file_label.setToolTip(video_path)
        else:
            self._video_file_label.setText("(no scene loaded)")
            self._video_file_label.setToolTip("")

        # Monitor list reads from Setup's playback_screen_indices. If
        # empty, fall back to "any monitor" wording.
        playback = self._prefs.playback_screen_indices
        fill = set(self._prefs.fill_screen_indices)
        if playback:
            lines: list[str] = []
            for screen_idx in playback:
                if 0 <= screen_idx < len(self._screens):
                    s = self._screens[screen_idx]
                    geo = s.geometry()
                    aspect = "crop" if screen_idx in fill else "letterbox"
                    lines.append(
                        f"→ Screen {screen_idx + 1}  ·  "
                        f"{geo.width()}×{geo.height()}  ·  {aspect}"
                    )
                else:
                    lines.append(f"→ Screen {screen_idx + 1}  (not detected)")
            self._video_monitors_label.setText("\n".join(lines))
        else:
            self._video_monitors_label.setText(
                "→ Any available monitor (set playback screens in Setup)"
            )

        # ── Output panel ────────────────────────────────────────────
        # Scene Audio (slot 0)
        scene_device = self._prefs.scene_audio_device
        self._output_scene_port.setText(
            f"→ Scene Audio: {self._audio_device_label(scene_device)}"
        )
        if not scene_device:
            self._output_scene_source.setText("(no device — set in Setup)")
        elif video_path:
            self._output_scene_source.setText(f"{os.path.basename(video_path)}  (embedded)")
        else:
            self._output_scene_source.setText("(no scene loaded)")

        # Haptic 1 (slot 1)
        h1_device = self._prefs.haptic1_audio_device
        self._output_h1_port.setText(
            f"→ Haptic 1: {self._audio_device_label(h1_device)}"
        )
        slot1 = self._slots[1]
        h1_label = self._h1_source_label(slot1)
        if not h1_device:
            self._output_h1_source.setText("(silent — no device set in Setup)")
        else:
            self._output_h1_source.setText(h1_label)

        # Haptic 2 — uses slot 1's aux_resolved_source / aux_silent_reason
        # populated by _maybe_launch_haptic2_aux. Pre-launch we fall back
        # to a simple device-set / device-unset summary.
        h2_device = self._prefs.haptic2_audio_device
        self._output_h2_port.setText(
            f"→ Haptic 2: {self._audio_device_label(h2_device)}"
        )
        h2_text = self._h2_source_label(slot1)
        self._output_h2_source.setText(h2_text)

    def _h1_source_label(self, slot1_data: dict) -> str:
        fs = slot1_data.get("funscript_set")
        ap = slot1_data.get("audio_path", "")
        if fs is not None and getattr(fs, "main_path", None):
            return os.path.basename(fs.main_path)
        if fs is not None and getattr(fs, "channels", {}):
            # Native stereostim — name from the first channel file.
            first_path = next(iter(fs.channels.values()))
            return os.path.basename(first_path)
        if ap:
            return os.path.basename(ap)
        return "(no source loaded)"

    def _h2_source_label(self, slot1_data: dict) -> str:
        """Render Haptic 2's resolved-or-silent state for the Output
        panel. Reads `aux_resolved_source` / `aux_silent_reason` set by
        the routing code; falls back to a Setup-summary wording when
        neither is set (pre-launch state).
        """
        h2_device = self._prefs.haptic2_audio_device
        if not h2_device:
            return "(silent — no device set in Setup)"
        if h2_device == self._prefs.haptic1_audio_device:
            return "(silent — same device as Haptic 1)"
        resolved = slot1_data.get("aux_resolved_source")
        silent_reason = slot1_data.get("aux_silent_reason")
        if silent_reason:
            return f"(silent — {silent_reason})"
        if resolved:
            return resolved.get("label", "(resolved)")
        # Pre-launch: nothing has resolved yet.
        if slot1_data.get("funscript_set") or slot1_data.get("audio_path"):
            return "(resolves at launch)"
        return "(no source loaded)"

    # ── Prefs lookup helpers ────────────────────────────────────────────────

    def _audio_device_label(self, device_id: str) -> str:
        """Display string for an mpv audio-device id.

        Fallback chain:
          - empty id → "(not set)"
          - id resolves in the current device list → its description
          - id set but not in the current list → "(unavailable —
            reselect in Setup)". Hits when the saved device was
            unplugged, or was filtered out by a later
            `_is_display_audio` rule change. Showing the raw
            wasapi/{GUID} string is just confusing for users.
        """
        if not device_id:
            return "(not set)"
        for name, desc in self._audio_devices:
            if name == device_id:
                return desc
        return "(unavailable — reselect in Setup)"

    def _audio_device_for_slot(self, slot_idx: int) -> str:
        """Setup-defined device for a given slot's role."""
        role = _SLOT_ROLES[slot_idx]
        if role == "video":
            return self._prefs.scene_audio_device
        if role == "stim":
            return self._prefs.haptic1_audio_device
        # Mirror slots are muted — no device.
        return ""

    def _screen_index_for_slot(self, slot_idx: int) -> int | None:
        """Setup-defined screen index for a video/mirror slot's
        position. Stim slot has no screen."""
        role = _SLOT_ROLES[slot_idx]
        if role == "stim":
            return None
        playback = self._prefs.playback_screen_indices
        # Map slot index to position in the playback list. Slot 0 is
        # always the first checked screen; mirrors get subsequent
        # screens in checked order.
        video_position = 0
        for idx in range(slot_idx):
            if _SLOT_ROLES[idx] != "stim":
                video_position += 1
        if playback and video_position < len(playback):
            return playback[video_position]
        # Fallback: any screen, defaulting to slot index.
        if not playback and slot_idx < len(self._screens):
            return slot_idx
        return None

    def _fill_for_screen_index(self, screen_idx: int | None) -> bool:
        if screen_idx is None:
            return False
        return screen_idx in self._prefs.fill_screen_indices

    def _build_setup_tab(self) -> QWidget:
        """Setup — the wiring tab. Two columns side-by-side: Audio device
        roles, Monitor roles. The user answers "what's plugged in where?"
        once. Behavior tuning (synth algorithm, content preference,
        haptic offset) lives on the Preferences tab so this view stays
        focused and never scrolls on a 1920×720 control screen.
        """
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        title = QLabel("Setup")
        tf = title.font(); tf.setPointSize(18); tf.setBold(True); title.setFont(tf)
        outer.addWidget(title)

        # Save-status line (shared across all columns)
        self._setup_status = QLabel("")
        self._setup_status.setStyleSheet("color: #9ba3c4; font-size: 11px;")

        columns = QHBoxLayout()
        columns.setSpacing(16)
        # Two equal columns. Audio device roles on the left (the more
        # frequent reconfiguration when the user plugs in a new dongle);
        # Monitor roles on the right.
        columns.addWidget(self._build_setup_audio_page(), 1)
        columns.addWidget(self._build_setup_monitors_page(), 1)
        outer.addLayout(columns, 1)

        outer.addWidget(self._setup_status)
        return container

    def _build_preferences_tab(self) -> QWidget:
        """Preferences — the behavior-tuning tab. Synthesis algorithm,
        haptic latency offset, content preference, and (future) haptic
        feature toggles. Distinct mental model from Setup: Setup
        answers "what's wired"; Preferences answers "how should it
        behave." Users touch this tab rarely after initial config, so
        it sits last in the tab order.
        """
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        title = QLabel("Preferences")
        tf = title.font(); tf.setPointSize(18); tf.setBold(True); title.setFont(tf)
        outer.addWidget(title)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        # Two columns: Audio synthesis (algorithm + offset) on the left,
        # Content preference on the right. Both have room to grow as
        # haptic features arrive — algorithm column can host pulse-shape
        # controls; content column can host per-port content overrides.
        columns.addWidget(self._build_preferences_synth_page(), 1)
        columns.addWidget(self._build_preferences_content_page(), 1)
        # Stretch=1 plus no trailing addStretch lets the columns claim
        # all leftover vertical space, so the synth and content-pref
        # boxes grow into the room rather than huddling at the top of
        # the tab on a tall window.
        outer.addLayout(columns, 1)
        return container

    def _build_preferences_synth_page(self) -> QWidget:
        """Audio-synthesis column for the Preferences tab — algorithm
        picker + latency offset. Box is at its natural height; trailing
        stretch pushes it to the top so it doesn't grow into empty
        space.
        """
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        subtitle = self._column_subtitle(
            "How the haptic signal is synthesized. The default works for "
            "most users — flip Pulse-based only if you have modern "
            "stereostim hardware."
        )
        root.addWidget(subtitle)
        root.addWidget(self._build_setup_synth_box())
        root.addStretch(1)
        return page

    def _build_preferences_content_page(self) -> QWidget:
        """Content Preference column. Natural height — no scroll
        wrapper, no expanding box."""
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        subtitle = self._column_subtitle(
            "When a scene ships both forms for the same haptic destination, "
            "this picks the winner. With only one form available, it plays "
            "regardless of this setting."
        )
        root.addWidget(subtitle)
        root.addWidget(self._build_setup_content_pref_box())
        root.addStretch(1)
        return page

    def _build_setup_audio_page(self) -> QWidget:
        """Audio-device-roles column. Natural height — no scroll
        wrapper. Three role rows + helper text fit cleanly at the
        1090×720 minimum. Scrolling on a Setup column is unwelcome
        friction; if a future expansion blows past available height,
        we'll restructure (e.g., move haptic offset / extra haptic
        roles to Preferences) rather than reintroducing scroll.
        """
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        subtitle = self._column_subtitle(
            "Pick which physical audio device handles each role. Library "
            "clicks use these to route automatically — set this once."
        )
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
            "Video's embedded sound (speakers / headphones).",
            is_haptic=False,
        ))
        rl.addLayout(self._labeled_row_with_test(
            "Haptic 1 (main stim)", self._setup_haptic1_combo,
            "Primary estim output (USB dongle).",
            is_haptic=True,
        ))
        rl.addLayout(self._labeled_row_with_test(
            "Haptic 2 (prostate)", self._setup_haptic2_combo,
            "Optional prostate output. Same device family as Haptic 1 "
            "recommended for tight sync.",
            is_haptic=True,
        ))

        root.addWidget(role_box)
        root.addStretch()
        return page

    def _build_setup_content_pref_box(self) -> QGroupBox:
        """Content preference — sound vs funscript tie-breaker.

        Per-port resolution rule: when a scene ships BOTH a sound file
        and a funscript for the same destination, this preference picks
        the winner. When only one form exists, it plays regardless of
        preference. See `app/preferences.py` ContentPreference for the
        full rationale (sound default; funscript path is opt-in).
        """
        box = QGroupBox("Content preference")
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        self._setup_content_pref_group = QButtonGroup(self)
        self._setup_content_pref_sound = QRadioButton("Sound files (.wav / .mp3)")
        self._setup_content_pref_funscript = QRadioButton("Funscripts (live synth)")
        self._setup_content_pref_group.addButton(self._setup_content_pref_sound, 0)
        self._setup_content_pref_group.addButton(self._setup_content_pref_funscript, 1)
        if self._prefs.content_preference == "funscript":
            self._setup_content_pref_funscript.setChecked(True)
        else:
            self._setup_content_pref_sound.setChecked(True)
        self._setup_content_pref_group.idToggled.connect(
            lambda _id, checked: self._on_content_preference_changed() if checked else None
        )

        layout.addWidget(self._setup_content_pref_sound)
        layout.addWidget(self._make_help_label(
            "Pre-rendered files. No synth pops, no algorithm choice. "
            "Default — most stereo-stim scenes ship a sound file."
        ))
        layout.addSpacing(2)
        layout.addWidget(self._setup_content_pref_funscript)
        layout.addWidget(self._make_help_label(
            "Live synthesis from .funscript curves. Pick this if your "
            "library is mostly funscripts and you want the algorithm "
            "controls below to apply."
        ))
        layout.addWidget(self._make_help_label(
            "When a scene has only one form, it plays regardless of "
            "this choice. Tie-breaker only."
        ))

        return box

    def _on_content_preference_changed(self) -> None:
        pref = "funscript" if self._setup_content_pref_funscript.isChecked() else "sound"
        if pref == self._prefs.content_preference:
            return
        self._prefs.content_preference = pref
        self._prefs.save()
        DebugLog.record("setup.content_preference", value=pref)
        self._setup_status.setText(f"Saved to {Preferences.path()}")
        QTimer.singleShot(3000, lambda: self._setup_status.setText(""))

    def _build_setup_synth_box(self) -> QGroupBox:
        """Audio synthesis settings — algorithm picker + latency offset.

        Wording mirrors restim's device wizard so users who already know
        restim's UI immediately recognize the controls. Continuous is the
        default (matches FunscriptForge's MP3 baseline + restim's own
        out-of-the-box choice); modern stereostim users flip to pulse
        once.
        """
        box = QGroupBox("Audio synthesis")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        algo_label = QLabel("Generation algorithm")
        af = algo_label.font(); af.setBold(True); algo_label.setFont(af)
        layout.addWidget(algo_label)

        self._setup_algo_group = QButtonGroup(self)
        self._setup_algo_continuous = QRadioButton("Continuous")
        self._setup_algo_pulse = QRadioButton("Pulse-based")
        self._setup_algo_group.addButton(self._setup_algo_continuous, 0)
        self._setup_algo_group.addButton(self._setup_algo_pulse, 1)
        if self._prefs.audio_algorithm == "pulse":
            self._setup_algo_pulse.setChecked(True)
        else:
            self._setup_algo_continuous.setChecked(True)
        self._setup_algo_group.idToggled.connect(
            lambda _id, checked: self._on_setup_changed() if checked else None
        )

        # Restim-wizard style: short radio label + wrapped description
        # underneath. Radio buttons themselves don't word-wrap, so long
        # descriptions get clipped when the column is narrow.
        layout.addWidget(self._setup_algo_continuous)
        layout.addWidget(self._make_help_label(
            "Classic waveform. Best for 312/2B. Low power-efficiency. "
            "(~100 Hz works best with the 312.)"
        ))
        layout.addSpacing(2)
        layout.addWidget(self._setup_algo_pulse)
        layout.addWidget(self._make_help_label(
            "Power-efficient waveform. Slower numbing. For modern "
            "audio-based stereostim hardware."
        ))

        layout.addSpacing(4)

        offset_row = QHBoxLayout()
        offset_label = QLabel("Haptic offset (s)")
        of = offset_label.font(); of.setBold(True); offset_label.setFont(of)
        offset_row.addWidget(offset_label)

        # Surfaced in seconds with half-second granularity — milliseconds
        # confused users in early dogfooding ("is 200 a lot or a little?").
        # Storage stays in ms (haptic_offset_ms) so the synth path and
        # preferences.json don't churn; only the spinbox UI is in seconds.
        self._setup_offset_spin = QDoubleSpinBox()
        self._setup_offset_spin.setRange(-0.5, 0.5)
        self._setup_offset_spin.setSingleStep(0.5)
        self._setup_offset_spin.setDecimals(1)
        self._setup_offset_spin.setSuffix(" s")
        self._setup_offset_spin.setFixedWidth(110)
        self._setup_offset_spin.setValue(self._prefs.haptic_offset_ms / 1000.0)
        self._setup_offset_spin.valueChanged.connect(
            lambda _v: self._on_setup_changed()
        )
        offset_row.addWidget(self._setup_offset_spin)
        offset_row.addStretch()
        layout.addLayout(offset_row)

        layout.addWidget(self._make_help_label(
            "Shift the stim signal relative to video. Positive = stim "
            "leads; negative = stim lags. Compensates for USB / driver "
            "latency."
        ))

        return box

    @staticmethod
    def _make_help_label(text: str) -> QLabel:
        """Wrapped, muted-grey help label for sub-descriptions under
        controls. Centralized so font size + color stay consistent and
        word-wrap is on (controls like QRadioButton don't wrap their
        own text — the help label below them does the heavy lifting)."""
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        lbl.setWordWrap(True)
        # Ignored horizontal lets the label shrink below its preferred
        # text width so it actually wraps inside narrow columns.
        # Without this, a long unwrapped string forces the parent
        # widget wider than its allocated 1/3 column.
        lbl.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        lbl.setMinimumWidth(0)
        return lbl

    @staticmethod
    def _column_subtitle(text: str) -> QLabel:
        """Top-of-column subtitle. Larger than help labels but still
        word-wrapping. Same size-policy trick as `_make_help_label` so
        the column doesn't get pushed wider by the unwrapped string."""
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #9ba3c4;")
        lbl.setWordWrap(True)
        lbl.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        lbl.setMinimumWidth(0)
        return lbl

    def _build_setup_monitors_page(self) -> QWidget:
        """Monitor-roles column. Natural height — no scroll wrapper.
        Per-screen rows scale linearly with detected screen count;
        4-monitor rigs (the high-end target) fit comfortably at
        720px+. If a future rig has more screens than fit, we'll
        revisit (probably with a horizontal layout per row to halve
        the height)."""
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        subtitle = self._column_subtitle(
            "Which monitors host the control panel and video playback. "
            "Slot monitor pickers will only offer your checked playback screens."
        )
        root.addWidget(subtitle)

        monitor_box = QGroupBox("Monitor roles")
        ml = QVBoxLayout(monitor_box)
        ml.setSpacing(10)

        self._setup_control_screen_combo = QComboBox()
        self._setup_control_screen_combo.setMinimumHeight(32)
        # Same shrink policy as the audio role combos — long screen
        # labels like "Screen 1  —  3840×1080  (Odyssey G95NC)" can
        # otherwise pin the column wider than its allocation and clip
        # neighboring text.
        self._setup_control_screen_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._setup_control_screen_combo.setMinimumContentsLength(12)
        self._setup_control_screen_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
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
            "Check the monitors you use for video. Leave all unchecked to "
            "allow any screen. Crop = scale the video to fill this "
            "monitor's aspect (useful on ultrawide); off = letterbox/"
            "pillarbox to preserve the video's native aspect. "
            "(Fullscreen on Live is a separate choice — kiosk mode on/off.)"
        )
        pb_helper.setStyleSheet("color: #6b7280; font-size: 11px;")
        pb_helper.setWordWrap(True)
        ml.addWidget(pb_helper)

        self._setup_playback_checkboxes: list[QCheckBox] = []
        self._setup_fill_checkboxes: list[QCheckBox] = []
        for idx, s in enumerate(self._screens):
            geo = s.geometry()
            row = QHBoxLayout()
            row.setSpacing(8)

            cb = QCheckBox(
                f"Screen {idx + 1}  —  {geo.width()}×{geo.height()}  ({s.name()})"
            )
            cb.setChecked(idx in self._prefs.playback_screen_indices)
            cb.toggled.connect(self._on_playback_screens_changed)
            self._setup_playback_checkboxes.append(cb)
            row.addWidget(cb, 1)

            fill_cb = QCheckBox("Crop")
            fill_cb.setChecked(idx in self._prefs.fill_screen_indices)
            fill_cb.setToolTip(
                "Crop video to fill this monitor's aspect (mpv panscan).\n"
                "Useful for 16:9 content on a 32:9 ultrawide.\n"
                "Off = letterbox / pillarbox to preserve the source aspect.\n"
                "Different from Live's Fullscreen toggle, which controls "
                "whether the player window takes over the whole monitor."
            )
            fill_cb.toggled.connect(self._on_fill_screens_changed)
            self._setup_fill_checkboxes.append(fill_cb)
            row.addWidget(fill_cb)

            ml.addLayout(row)

        root.addWidget(monitor_box)
        root.addStretch()
        return page

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

        Also: realize the QWindow before moving so the migration to a
        non-primary screen takes. Same pattern as PlayerWindow's
        place_on_screen — without create()+windowHandle().setScreen(),
        Qt creates the native window on primary at show()-time and
        ignores our move(), leaving the control panel on the wrong
        monitor regardless of the Setup-tab pref.
        """
        self.ensurePolished()
        self.create()
        handle = self.windowHandle()
        if handle is not None and handle.screen() is not screen:
            handle.setScreen(screen)
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
        # Re-render Live's Video panel — its monitor list reads from prefs.
        self._refresh_live_panels()

    def _on_fill_screens_changed(self) -> None:
        """Persist the per-screen Fill (crop-to-fit) toggles. The launch
        flow reads `_prefs.fill_screen_indices` to decide whether mpv
        opens with panscan=1.0 for each playback screen."""
        indices = [
            i for i, cb in enumerate(self._setup_fill_checkboxes) if cb.isChecked()
        ]
        self._prefs.fill_screen_indices = indices
        self._prefs.save()
        DebugLog.record("setup.fill_screens", indices=indices)
        self._setup_status.setText(f"Saved to {Preferences.path()}")
        QTimer.singleShot(3000, lambda: self._setup_status.setText(""))
        # Re-render Live's Video panel so the per-monitor `fill/letterbox`
        # marker reflects the change.
        self._refresh_live_panels()

    @staticmethod
    def _disambiguate_audio_descriptions(
        raw_devices: list[dict],
    ) -> list[tuple[str, str]]:
        """Build the (mpv_id, display_label) pairs for audio dropdowns.

        When two devices share the same description (typical: two
        physically-identical USB dongles, both reporting "Speakers (USB
        Audio Device)"), prefix the display label with the PortAudio
        integer index so users can tell them apart in the picker. Single-
        occurrence descriptions stay clean (no noisy [N] prefix when
        there's nothing to disambiguate).

        The PortAudio index is what `resolve_audio_device` picks at
        runtime, so the number visible in the dropdown matches what the
        synth actually opens. Caveat: indices shift on USB replug — same
        caveat as with hardcoded indices anywhere else in the system.
        """
        from collections import Counter  # noqa: PLC0415
        from app.stim_audio_output import (  # noqa: PLC0415
            _find_sounddevice_indices,
            _host_api_from_mpv_id,
            _load_sounddevice,
        )

        base = [
            (d["name"], d.get("description", d["name"])) for d in raw_devices
        ]
        desc_counts = Counter(desc for _, desc in base)
        if all(c == 1 for c in desc_counts.values()):
            return base

        # Try to query sounddevice for indices. If unavailable, fall back
        # to plain labels — better silent than a noisy/broken dropdown.
        try:
            sd = _load_sounddevice()
        except Exception:
            return base

        # Per (desc, host) bucket: track which index in sounddevice's
        # match list is next to consume. Pairing by mpv enumeration
        # order with sounddevice enumeration order is the best we can
        # do without GUID-aware Windows lookups.
        consumed: dict[tuple[str, str], int] = {}
        out: list[tuple[str, str]] = []
        for name, desc in base:
            if desc_counts[desc] <= 1:
                out.append((name, desc))
                continue
            host = _host_api_from_mpv_id(name) or ""
            sd_indices = _find_sounddevice_indices(sd, desc, host or None)
            pos = consumed.get((desc, host), 0)
            if pos < len(sd_indices):
                idx = sd_indices[pos]
                consumed[(desc, host)] = pos + 1
                out.append((name, f"[{idx}] {desc}"))
            else:
                out.append((name, desc))
        return out

    def _build_role_combo(self, *, saved_value: str) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(32)
        # Without these, the combo's preferred width is the longest item
        # name (e.g. "[21] Speakers (USB Audio Device)") which forces the
        # whole column wider than its allocated 1/3, cropping the Test
        # button on the right. With AdjustToMinimumContentsLengthWithIcon
        # + minimum length, the combo can shrink to roughly 12 chars and
        # the dropdown still shows the full name when opened.
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(12)
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
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
        *,
        is_haptic: bool,
    ) -> QVBoxLayout:
        """Variant of _labeled_row that includes a 'Test' button which plays
        a short sample through the currently-selected device. Gives users an
        immediate, audible confirmation of whether the device actually
        outputs audio — the fastest way to diagnose 'why is my haptic silent?'
        problems (wrong device / OS-level mute / unplugged dongle).

        `is_haptic` picks the sample. Speakers get a 0.5 s 440 Hz sine; haptic
        roles get a synthesized stim clip via `stim_preview.play_test_clip`
        so the preview matches what real scene playback feels like (not a
        harsh sine into the user's electrodes).
        """
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
        if is_haptic:
            test_btn.setToolTip(
                "Play a brief stim sample through this device — "
                "centered electrode, gentle volume ramp.\n"
                "Silent? Check the dongle, the device's hardware knob, or "
                "OS-level per-app mute."
            )
        else:
            test_btn.setToolTip(
                "Play a half-second tone through this device.\n"
                "Silent? Check for OS-level per-app mute or unplugged hardware."
            )
        test_btn.clicked.connect(
            lambda _, c=combo, h=is_haptic: self._on_test_device(c, is_haptic=h)
        )
        combo_row.addWidget(test_btn)
        row.addLayout(combo_row)

        if help_text:
            helper = QLabel(help_text)
            helper.setStyleSheet("color: #6b7280; font-size: 11px;")
            helper.setWordWrap(True)
            row.addWidget(helper)
        return row

    def _on_test_device(self, combo: QComboBox, *, is_haptic: bool) -> None:
        device_id = combo.currentData() or ""
        DebugLog.record(
            "setup.test_device",
            device=device_id or "(not set)",
            role="haptic" if is_haptic else "speaker",
        )
        if not device_id:
            self._setup_status.setText("Pick a device first, then press Test.")
            QTimer.singleShot(3000, lambda: self._setup_status.setText(""))
            return
        if is_haptic:
            play_haptic_test_clip(device_id)
            label = "stim sample"
        else:
            play_tone_on_device(device_id)
            label = "tone"
        self._setup_status.setText(
            f"Playing {label} on: {combo.currentText()}"
        )
        QTimer.singleShot(2000, lambda: self._setup_status.setText(""))

    def _on_setup_changed(self) -> None:
        self._prefs.scene_audio_device = self._setup_scene_combo.currentData() or ""
        self._prefs.haptic1_audio_device = self._setup_haptic1_combo.currentData() or ""
        self._prefs.haptic2_audio_device = self._setup_haptic2_combo.currentData() or ""
        if self._setup_algo_pulse.isChecked():
            self._prefs.audio_algorithm = "pulse"
        else:
            self._prefs.audio_algorithm = "continuous"
        self._prefs.haptic_offset_ms = int(round(self._setup_offset_spin.value() * 1000))
        self._prefs.save()
        DebugLog.record(
            "setup.prefs_saved",
            scene=bool(self._prefs.scene_audio_device),
            haptic1=bool(self._prefs.haptic1_audio_device),
            haptic2=bool(self._prefs.haptic2_audio_device),
            algo=self._prefs.audio_algorithm,
            offset_ms=self._prefs.haptic_offset_ms,
        )
        self._setup_status.setText(f"Saved to {Preferences.path()}")
        QTimer.singleShot(3000, lambda: self._setup_status.setText(""))
        # Live's Output panel reads from these prefs — refresh so the
        # port labels update without waiting for a tab switch.
        self._refresh_live_panels()
        # Calibrate buttons depend on haptic1/haptic2 device prefs being
        # set; flip enable state if the user just (un)configured a port.
        self._update_calibrate_buttons_enabled()

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
        slot4 = self._slot_data(3)

        # Mirror mode: 2+ checked playback screens + a video → same video
        # shows on Slot 1's monitor PLUS each additional playback screen
        # via mirror slots (Slot 3 = Video 2, Slot 4 = Video 3) in sync,
        # with each mirror muted (Slot 1 already carries the scene audio).
        # One-screen users and audio-only scenes keep the simpler layout.
        playback_screens = self._prefs.playback_screen_indices
        mirror_video = (
            choices.video is not None
            and len(playback_screens) >= 2
        )

        if mirror_video:
            self._set_slot_media(
                slot1, video_path=choices.video.path, audio_path="",
            )
            self._set_slot_media(
                slot3, video_path=choices.video.path, audio_path="",
            )
            # Slot 4 (Video 3) only mirrors if 3+ playback screens are
            # checked. Otherwise clear it so stale state from a prior
            # scene doesn't carry over.
            if len(playback_screens) >= 3:
                self._set_slot_media(
                    slot4, video_path=choices.video.path, audio_path="",
                )
            else:
                self._set_slot_media(slot4, video_path="", audio_path="")
        else:
            # Slots 3 and 4 always clear in the non-mirror case.
            self._set_slot_media(slot3, video_path="", audio_path="")
            self._set_slot_media(slot4, video_path="", audio_path="")
            if choices.video:
                self._set_slot_media(
                    slot1, video_path=choices.video.path, audio_path="",
                )
            else:
                self._set_slot_media(slot1, video_path="", audio_path="")

        # Slot 2 is the Stim slot — its source can be either a native
        # FunscriptSet (preferred — real-time synthesis via StimSynth +
        # the user's Haptic 1 dongle) or a pre-rendered audio file
        # (legacy v0.0.1 path; mpv plays it through Slot 2's output).
        # Native funscript wins when both are available; the audio file
        # is the fallback when the scene has only pre-renders.
        if choices.funscript_set is not None and (
            choices.funscript_set.main_path or choices.funscript_set.channels
        ):
            self._set_slot_media(slot2, video_path="", audio_path="")
            slot2["funscript_set"] = choices.funscript_set
            DebugLog.record(
                "stim.dispatch",
                slot=1,
                source="funscript_set",
                base_stem=choices.funscript_set.base_stem,
                pulse_based=any(
                    ch.startswith("pulse_") for ch in choices.funscript_set.channels
                ),
            )
        elif choices.audio:
            self._set_slot_media(
                slot2,
                video_path="",
                audio_path=choices.audio.path,
            )
            slot2["funscript_set"] = None
            DebugLog.record(
                "stim.dispatch", slot=1, source="audio_file",
                path=choices.audio.path,
            )
        else:
            self._set_slot_media(slot2, video_path="", audio_path="")
            slot2["funscript_set"] = None
        # Final refresh — _set_slot_media already updated the panels
        # but at that time slot2["funscript_set"] still held the prior
        # scene's value. Re-render after the assignment.
        self._refresh_live_panels()
        # Calibrate buttons gate on funscript_set presence; refresh now
        # that the new scene's content has been applied.
        self._update_calibrate_buttons_enabled()
        # Scene volume is ephemeral — reset to 100 % on every new scene
        # so a quiet pick from the prior session doesn't carry over.
        self._scene_volume_slider.setValue(100)

        if not (choices.video or choices.audio):
            QMessageBox.information(
                self, "Nothing to play",
                f"Scene '{entry.name}' has no video or audio file to play."
            )
            return

        # Setup owns audio device roles + monitor assignments + fill.
        # The launch flow reads from `_prefs` directly; no per-slot
        # state to apply here.

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

        # Switch to Live tab and stop here — DON'T auto-launch. The
        # user needs a window between scene-pick and player-windows-up
        # to run pre-flight calibration (the launched stim stream
        # claims the haptic device handle exclusively, so calibrate
        # has to happen first). Live now shows the loaded scene's
        # video + output mapping; the user explicitly hits Launch
        # Players when ready.
        self._tabs.setCurrentIndex(0)
        DebugLog.record("library.activate.loaded", scene=entry.name)

    # _select_slot_monitor / _populate_monitor_combo / _apply_setup_roles_to_slots
    # are gone in v0.0.4 — all device + monitor routing now reads directly
    # from `_prefs` at launch time. See `_audio_device_for_slot`,
    # `_screen_index_for_slot`, `_fill_for_screen_index`.

    def _set_slot_media(
        self,
        data: dict,
        *,
        video_path: str | None = None,
        audio_path: str | None = None,
    ) -> None:
        """Set video/audio paths on a slot's data dict and trigger a
        Live-panel refresh. `None` means 'leave unchanged'; empty
        string means 'clear'. v0.0.4: no per-slot UI to update — the
        Video/Output panels read from slot_data on refresh.
        """
        if video_path is not None:
            data["video_path"] = video_path
        if audio_path is not None:
            data["audio_path"] = audio_path
        self._refresh_live_panels()

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

        self._btn_debug_clear = QPushButton("Clear")
        self._btn_debug_clear.setFixedHeight(30)
        self._btn_debug_clear.setToolTip(
            "Drop captured events and reset the t=0 timestamp. Useful when "
            "starting a fresh repro after exporting an earlier session."
        )
        self._btn_debug_clear.clicked.connect(self._on_debug_clear)
        h.addWidget(self._btn_debug_clear)

        return bar

    @staticmethod
    def _make_slot_data() -> dict:
        """Per-mpv-player media + stream state. Slots remain as the
        SyncEngine's internal index (4 mpv players addressed 0..3) but
        the per-slot UI is gone in v0.0.4. Routing/monitor/volume now
        read from `_prefs` at launch; only media paths and live stream
        handles live in slot_data.
        """
        return {
            "video_path":          "",
            "audio_path":          "",
            "funscript_set":       None,
            "stim_audio_stream":   None,
            "aux_audio_streams":   [],
            # Populated at launch by _maybe_launch_haptic2_aux:
            #   "aux_resolved_source": {"kind": str, "label": str}
            #   "aux_silent_reason": str
            # Read by _refresh_live_panels for Output-panel rendering.
        }

    # The per-role slot builders + their helpers (_build_video_slot,
    # _build_stim_slot, _build_mirror_slot, _build_audio_device_combo,
    # _build_volume_row, _build_path_label, _build_file_picker_row,
    # _build_block_frame, _block_heading, _sub_label,
    # _build_hidden_*) are gone in v0.0.4. Live's per-slot UI was
    # replaced with read-only Video and Output panels that render from
    # slot_data + _prefs via _refresh_live_panels.

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _slot_data(self, index: int) -> dict:
        return self._slots[index]

    def _screen_sizes(self) -> list[tuple[int, int]]:
        return [(s.geometry().width(), s.geometry().height()) for s in self._screens]

    # ── Session-name autofill ─────────────────────────────────────────────

    def _maybe_autofill_session_name(self, media_path: str) -> None:
        """Set the Session name from the picked media file if the user
        hasn't already customized it. Called from Library activation
        (the only scene-load path in v0.0.4 — Browse buttons on Live
        were dropped with the slot-card UI)."""
        current = self._session_name.text().strip()
        if current and current != "Untitled Session":
            return
        stem = os.path.splitext(os.path.basename(media_path))[0]
        if stem:
            self._session_name.setText(stem)
            self.setWindowTitle(f"ForgePlayer — {stem}")

    # _on_browse_video / _on_clear_video / _on_browse_audio /
    # _on_clear_audio / _refresh_monitor_state / _on_volume_changed are
    # gone — no Browse buttons or volume sliders on Live anymore.
    # Library is the only scene-load path; Setup owns routing.

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

    def _on_debug_clear(self) -> None:
        count = DebugLog.event_count()
        if count == 0:
            return
        DebugLog.reset()
        # Toast-style status using the existing setup status line area is
        # awkward here — use the Mark button label briefly so the user
        # gets visual confirmation without an extra dialog.
        self._btn_debug_clear.setText(f"Cleared {count}")
        QTimer.singleShot(1500, lambda: self._btn_debug_clear.setText("Clear"))

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
            data["video_path"] = slot.get("video_path", "")
            data["audio_path"] = slot.get("audio_path", "")
        self._refresh_live_panels()

    # ── Session ────────────────────────────────────────────────────────────────

    def _current_session(self) -> Session:
        """Save the current scene paths. v0.0.4 onwards, routing
        (audio device / monitor / volume) is Setup-owned and not
        round-tripped through session files. Old fields stay on
        `SlotConfig` for backward compatibility — written as zeros.
        """
        slots: list[SlotConfig] = []
        for i in range(_NUM_SLOTS):
            d = self._slot_data(i)
            has_media = bool(d["video_path"] or d["audio_path"])
            slots.append(SlotConfig(
                enabled=has_media,
                video_path=d["video_path"],
                audio_path=d["audio_path"],
                # Legacy fields — Setup owns these now.
                monitor_index=0,
                audio_device="",
                volume=100,
            ))
        return Session(name=self._session_name.text(), slots=slots)

    def _apply_session(self, session: Session) -> None:
        """Restore scene paths from a saved session. v0.0.4 ignores
        the legacy device/monitor/volume fields — those now live in
        Setup and Preferences."""
        self._session_name.setText(session.name)
        for i, cfg in enumerate(session.slots[:_NUM_SLOTS]):
            d = self._slot_data(i)
            d["video_path"] = cfg.video_path
            d["audio_path"] = cfg.audio_path
            # funscript_set isn't part of the session schema yet — clear
            # any leftover from a prior in-memory scene so loading an
            # old session doesn't inherit a stale stim source.
            d["funscript_set"] = None
        self._refresh_live_panels()

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
            for slot_idx in range(_NUM_SLOTS):
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
        # Stop any live StimSynth audio streams BEFORE terminating mpv —
        # the synth's media-sync callback reads mpv state, so killing
        # mpv first could let an in-flight callback see a half-torn-down
        # player. Stop streams first, then mpv.
        #
        # Parallel-stop: each StimAudioStream.stop() blocks ~40 ms on a
        # GUI-thread sleep waiting for the fade-out to complete. With one
        # primary plus one aux stream per slot (Haptic 2 prostate, future
        # MP4 fan-outs), serial stops would compound into noticeable lag
        # on close. Threadpool-parallel stops keep the overall close at
        # ~40 ms regardless of stream count.
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

        all_streams: list[tuple[int, str, object]] = []
        for i in range(_NUM_SLOTS):
            data = self._slot_data(i)
            primary = data.get("stim_audio_stream")
            if primary is not None:
                all_streams.append((i, "primary", primary))
            for aux in data.get("aux_audio_streams") or []:
                all_streams.append((i, "aux", aux))

        if all_streams:
            with ThreadPoolExecutor(max_workers=len(all_streams)) as pool:
                futures = {
                    pool.submit(s.stop): (slot, role, s)
                    for slot, role, s in all_streams
                }
                for fut in futures:
                    slot, role, stream = futures[fut]
                    try:
                        fut.result()
                    except Exception as exc:
                        DebugLog.record(
                            "stim.stream_stop_error",
                            slot=slot, role=role, error=repr(exc),
                        )
                    else:
                        DebugLog.record(
                            "stim.stream_closed",
                            slot=slot, role=role,
                            underruns=getattr(stream, "underrun_count", 0),
                            resyncs=getattr(stream, "resync_count", 0),
                        )

        # Clear references after all threads have completed. Also clear
        # the per-slot resolved-source / silent-reason so the Output
        # panel doesn't keep showing stale post-launch state after
        # close.
        for i in range(_NUM_SLOTS):
            data = self._slot_data(i)
            data["stim_audio_stream"] = None
            data["aux_audio_streams"] = []
            data.pop("aux_resolved_source", None)
            data.pop("aux_silent_reason", None)
        # Terminate every engine slot — including audio-only slots that
        # don't have a PlayerWindow — so no mpv instances leak.
        for i in range(_NUM_SLOTS):
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
        # Reset the play-since-launch flag — calibrate is unlocked
        # again after Close.
        self._has_played_since_launch = False
        # Re-render the Output panel — H2 should drop back to its
        # pre-launch summary now that there's no resolved source.
        self._refresh_live_panels()
        # Calibrate is locked while playing; closing unlocks the
        # buttons (subject to scene + device availability).
        self._update_calibrate_buttons_enabled()

    # ── Calibrate ──────────────────────────────────────────────────────────────

    def _on_calibrate_h1(self) -> None:
        self._toggle_calibrate(port="h1")

    def _on_calibrate_h2(self) -> None:
        self._toggle_calibrate(port="h2")

    def _toggle_calibrate(self, port: str) -> None:
        """Tap-toggle one calibrate session for `port` ("h1" or "h2").

        First tap on an idle port: build a CalibrationStream against the
        loaded scene's funscripts and the matching haptic device, then
        start it. Second tap (or any tap on a port whose stream is
        running): stop and clear.

        Errors (missing scene, missing device, audio open failure)
        surface via QMessageBox; the launch path is unaffected. The
        toggle button's checked state is kept in lockstep with the
        actual stream so a failed start doesn't leave the button stuck
        ON.
        """
        # Always log the click — gives us a paper trail when the user
        # reports "click did nothing" (most often: button was disabled
        # because players are launched, but that doesn't fire any
        # other event).
        DebugLog.record(
            "calibrate.click", port=port,
            running=(self._calib_h1 if port == "h1" else self._calib_h2) is not None,
            players_active=self._engine.has_active_players(),
            funscript_loaded=self._slot_data(1).get("funscript_set") is not None,
        )

        if port == "h1":
            current = self._calib_h1
            btn = self._btn_calibrate_h1
            device_id = self._prefs.haptic1_audio_device
            port_label = "Haptic 1"
        else:
            current = self._calib_h2
            btn = self._btn_calibrate_h2
            device_id = self._prefs.haptic2_audio_device
            port_label = "Haptic 2"

        # Already running on this port → stop and clear. Idempotent on
        # the stream side; the button check state is reset regardless.
        if current is not None:
            try:
                current.stop()
            finally:
                if port == "h1":
                    self._calib_h1 = None
                else:
                    self._calib_h2 = None
                btn.setChecked(False)
            DebugLog.record("calibrate.stop", port=port)
            return

        # Pre-flight checks — surface a friendly message rather than
        # raising into the click handler.
        funscript_set = self._slot_data(1).get("funscript_set")
        if funscript_set is None:
            btn.setChecked(False)
            QMessageBox.information(
                self, "No haptic content loaded",
                "Pick a scene with a .funscript from the Library tab "
                "before calibrating.\n\n"
                "Note: opening a saved session restores the video and "
                "audio paths but not the haptic content yet — re-pick "
                "the scene from Library to load its funscripts.",
            )
            return
        if not device_id:
            btn.setChecked(False)
            QMessageBox.information(
                self, f"{port_label} device not configured",
                f"Set the {port_label} audio device in Setup before "
                f"calibrating.",
            )
            return

        from app.funscript_loader import load_stim_channels  # noqa: PLC0415
        from app.stim_calibrate import CalibrationStream  # noqa: PLC0415

        try:
            if port == "h2":
                # Try prostate channels first; fall back to the main
                # channels (mirror H1) when alpha-prostate isn't present.
                # Audio-file calibrate is a future enhancement — when
                # H2 resolves to an audio file, the user falls back to
                # mirroring main funscripts.
                channels = load_stim_channels(funscript_set, prostate=True)
                if channels is None:
                    channels = load_stim_channels(funscript_set, prostate=False)
            else:
                channels = load_stim_channels(funscript_set, prostate=False)
        except ValueError as exc:
            btn.setChecked(False)
            DebugLog.record(
                "calibrate.load_failed", port=port, error=repr(exc),
                base_stem=funscript_set.base_stem,
            )
            QMessageBox.warning(
                self, "Calibration failed",
                f"Could not load haptic content for {port_label}:\n{exc}",
            )
            return
        if channels is None:
            btn.setChecked(False)
            QMessageBox.information(
                self, "No haptic content for this port",
                f"This scene has no playable funscript for {port_label}.",
            )
            return

        try:
            mpv_devices = SyncEngine.list_audio_devices(include_hdmi=True)
        except Exception:
            mpv_devices = None

        ramp_seconds = 5.0 if self._chk_calibrate_ramp.isChecked() else 0.0
        try:
            stream = CalibrationStream(
                channels, device_id,
                mpv_devices=mpv_devices,
                waveform=self._prefs.audio_algorithm,
                ramp_seconds=ramp_seconds,
            )
            stream.start()
        except Exception as exc:
            btn.setChecked(False)
            DebugLog.record(
                "calibrate.start_failed", port=port,
                device=device_id, error=repr(exc),
            )
            QMessageBox.warning(
                self, "Calibration failed",
                f"Could not open {port_label} audio device for "
                f"calibration:\n{exc}\n\n"
                f"Verify the {port_label} device in Setup.",
            )
            return

        if port == "h1":
            self._calib_h1 = stream
        else:
            self._calib_h2 = stream
        btn.setChecked(True)
        DebugLog.record(
            "calibrate.start", port=port, device=device_id,
            base_stem=funscript_set.base_stem,
            peak_start_s=stream.peak_start_s,
            peak_duration_s=stream.peak_duration_s,
            ramp_seconds=stream.ramp_seconds,
            sample_rate=stream.device_rate,
        )

    def _update_calibrate_buttons_enabled(self) -> None:
        """Sync the Calibrate button state to current scene + Setup +
        engine state.

        Calibrate is a pre-flight tool: locked between the first Play
        and Close (the launched stim streams own the haptic devices
        once playback has started; calibrate would fight them for the
        same handle). Allowed pre-Launch, allowed in the post-Launch /
        pre-first-Play window so the user can Calibrate after opening
        the player windows but before starting the scene.

        Called at __init__-time, on launch, on close, on play, on
        scene change, and on Setup change. Cheap; safe to call
        redundantly.
        """
        # Built lazily — _build_live_tab may not have run yet during
        # very-early __init__ wiring. After build the attrs always exist.
        if not hasattr(self, "_btn_calibrate_h1"):
            return

        if self._engine.has_active_players() and self._has_played_since_launch:
            # Once Play has been hit, hard-stop any in-flight calibrate
            # — the launched stim stream is now driving the device.
            for slot, stream in (
                ("h1", self._calib_h1), ("h2", self._calib_h2),
            ):
                if stream is not None:
                    try:
                        stream.stop()
                    except Exception as exc:
                        DebugLog.record(
                            "calibrate.stop_at_play_failed",
                            port=slot, error=repr(exc),
                        )
            self._calib_h1 = None
            self._calib_h2 = None
            self._btn_calibrate_h1.setChecked(False)
            self._btn_calibrate_h2.setChecked(False)
            self._btn_calibrate_h1.setEnabled(False)
            self._btn_calibrate_h2.setEnabled(False)
            return

        # Pre-launch: enable iff the matching device is set. We DON'T
        # also gate on funscript_set presence — silently disabling a
        # button when a scene has no funscripts looked like a bug to
        # the user mid-dogfood. Instead, _toggle_calibrate's click
        # handler surfaces an explicit "Pick a scene with a .funscript"
        # message when the user taps and there's nothing to play.
        self._btn_calibrate_h1.setEnabled(
            bool(self._prefs.haptic1_audio_device)
        )
        self._btn_calibrate_h2.setEnabled(
            bool(self._prefs.haptic2_audio_device)
        )

    def _launch_stim_synth(
        self,
        slot_idx: int,
        slot_data: dict,
        funscript_set,
        audio_device: str,
    ) -> bool:
        """Spawn a StimSynth + StimAudioStream for the Stim slot.

        Returns True on success. Failures (no playable channels, audio
        device couldn't open) log via DebugLog and return False — the
        rest of the launch continues so the user still sees the video
        play even if stim fails.

        Time source: `engine.get_position()` reads the primary mpv
        player's `time-pos`. Stim audio thus follows the video clock —
        seek, pause, even buffer underruns on the video propagate.

        Play state: `not engine.is_paused()` gates the synth's volume
        to zero when video is paused. Hard mute through transport.
        """
        # Lazy imports — keep the audio stack out of cold-start when the
        # user's not playing a stim scene.
        from app.funscript_loader import load_stim_channels  # noqa: PLC0415
        from app.stim_audio_output import (  # noqa: PLC0415
            StimAudioStream,
            query_device_sample_rate,
            resolve_audio_device,
        )
        from app.stim_synth import CallbackMediaSync, StimSynth  # noqa: PLC0415

        try:
            channels = load_stim_channels(funscript_set, prostate=False)
        except ValueError as exc:
            DebugLog.record(
                "stim.load_failed", slot=slot_idx, error=repr(exc),
                base_stem=funscript_set.base_stem,
            )
            return False
        if channels is None:
            DebugLog.record(
                "stim.load_failed", slot=slot_idx, error="no_playable_channels",
                base_stem=funscript_set.base_stem,
            )
            return False

        # Mirror of the aux prostate-channel diagnostic for the primary
        # path. Logging both side-by-side lets us compare H1 (audible)
        # vs H2 (silent) channel shapes — particularly useful if the
        # main `volume.funscript` curve looks meaningfully different
        # from `volume-prostate.funscript` (the dominant hypothesis for
        # the H2-silent bug as of 2026-05-01).
        import numpy as _np  # noqa: PLC0415
        _vol_main = channels.volume
        _vol_main_min = float(_np.min(_vol_main.p)) if _vol_main is not None else None
        _vol_main_max = float(_np.max(_vol_main.p)) if _vol_main is not None else None
        _vol_main_mean = float(_np.mean(_vol_main.p)) if _vol_main is not None else None
        _vol_main_first = float(_vol_main.p[0]) if _vol_main is not None and _vol_main.p.size else None
        DebugLog.record(
            "stim.primary_channels",
            slot=slot_idx,
            samples=int(channels.t.size),
            alpha_min=float(_np.min(channels.alpha)),
            alpha_max=float(_np.max(channels.alpha)),
            alpha_mean=float(_np.mean(channels.alpha)),
            beta_min=float(_np.min(channels.beta)),
            beta_max=float(_np.max(channels.beta)),
            beta_mean=float(_np.mean(channels.beta)),
            volume_present=_vol_main is not None,
            volume_min=_vol_main_min,
            volume_max=_vol_main_max,
            volume_mean=_vol_main_mean,
            volume_first=_vol_main_first,
            source=channels.source,
        )

        # Media sync stays always-true: synth generates non-silent audio
        # at all times. Pause/play gating happens in StimAudioStream via
        # a 5 ms fade envelope (a synth-internal step from full carrier
        # to zero in a single sample is a click; the fade hides it).
        # The stream's is_playing_source uses the same engine query the
        # old media_sync did.
        engine = self._engine
        media_sync = CallbackMediaSync(lambda: True)
        is_playing_source = (
            lambda: engine.has_active_players() and not engine.is_paused()
        )

        try:
            mpv_devices = engine.list_audio_devices(include_hdmi=True)
        except Exception as exc:
            DebugLog.record("stim.mpv_devices_failed", error=repr(exc))
            mpv_devices = []

        # Query the device's default sample rate BEFORE constructing the
        # synth. USB dongles vary (most run 44100, some 48000); PortAudio
        # raises -9998 "Invalid sample rate" if we ask for a rate the
        # device doesn't accept. The synth math runs at whatever rate
        # we tell it, so opening the stream at the device's preferred
        # rate is the simplest fix.
        device_handle = resolve_audio_device(
            audio_device or None, mpv_devices,
        )
        device_rate = query_device_sample_rate(device_handle)
        DebugLog.record(
            "stim.device_rate_query",
            slot=slot_idx, device=str(device_handle), rate=device_rate,
        )

        synth = StimSynth(
            channels, media_sync,
            waveform=self._prefs.audio_algorithm,
            sample_rate=device_rate,
        )

        # Apply latency offset: positive ms means stim leads video, so we
        # feed the synth a media-time SLIGHTLY AHEAD of mpv's time-pos.
        # Captured at launch since prefs changes mid-playback don't apply
        # until the next launch (matches how device pickers behave).
        offset_seconds = float(self._prefs.haptic_offset_ms) / 1000.0
        if offset_seconds == 0.0:
            time_source = engine.get_position
        else:
            def time_source(_get=engine.get_position, _off=offset_seconds):
                return _get() + _off

        stream = StimAudioStream(
            synth=synth,
            time_source=time_source,
            device_id=audio_device or None,
            mpv_devices=mpv_devices,
            is_playing_source=is_playing_source,
        )
        try:
            stream.start()
        except Exception as exc:
            DebugLog.record(
                "stim.stream_open_failed", slot=slot_idx, error=repr(exc),
                device_id=audio_device,
            )
            QMessageBox.warning(
                self, "Stim audio failed",
                f"Could not open stim audio output for "
                f"{funscript_set.base_stem}:\n{exc}\n\n"
                f"Try a different Haptic 1 device in Setup.",
            )
            return False

        slot_data["stim_audio_stream"] = stream
        DebugLog.record(
            "players.launch_slot",
            slot=slot_idx,
            mode="stim_synth",
            base_stem=funscript_set.base_stem,
            algorithm=synth.waveform,
            offset_ms=self._prefs.haptic_offset_ms,
            source=channels.source,
            device=stream.device_name or "(default)",
        )

        # Haptic 2 aux output. Best-effort — failure here logs but does
        # not fail the primary launch (user still gets Haptic 1 stim
        # working even if their H2 device is unplugged or misconfigured).
        try:
            self._maybe_launch_haptic2_aux(
                slot_idx=slot_idx,
                slot_data=slot_data,
                funscript_set=funscript_set,
                primary_channels=channels,
                primary_sample_rate=device_rate,
                mpv_devices=mpv_devices,
                time_source=time_source,
                is_playing_source=is_playing_source,
                media_sync=media_sync,
            )
        except Exception as exc:
            DebugLog.record(
                "stim.aux_launch_unexpected_error",
                slot=slot_idx, error=repr(exc),
            )

        return True

    def _maybe_launch_haptic2_aux(
        self,
        *,
        slot_idx: int,
        slot_data: dict,
        funscript_set,
        primary_channels,
        primary_sample_rate: int,
        mpv_devices: list[dict],
        time_source,
        is_playing_source,
        media_sync,
    ) -> None:
        """Spawn the Haptic 2 auxiliary audio stream when configured.

        Per-port resolution (replaces v0.0.3's hard-coded 4-tier cascade):

          1. **Prostate-specific content** — sibling `<stem>.prostate.wav`
             and/or `alpha-prostate` funscript channel. When both exist,
             the user's Setup `content_preference` picks (sound vs
             funscript). When only one exists, it plays regardless.
          2. **Mirror Haptic 1** — no prostate-specific content → a
             second StimSynth instance fed the SAME primary channels as
             Haptic 1. Two synth instances (not shared) since the
             vendored restim algorithms aren't documented as thread-safe
             under concurrent `generate_audio()` calls.
          3. **Silent** — Haptic 2 device unconfigured in Setup, or H2
             device matches H1 (refuse to open twice on the same
             exclusive handle). The Live tab's Output panel surfaces
             this state with a `(silent — no source for this port)`
             message; `slot_data["aux_silent_reason"]` carries the
             human-readable explanation.

        All failures inside this method are logged and swallowed —
        Haptic 2 is auxiliary; primary stim must keep working.
        """
        # Reset any prior session's state so the Live UI doesn't show
        # stale source/silent info from a previous scene.
        slot_data.pop("aux_resolved_source", None)
        slot_data.pop("aux_silent_reason", None)

        h2_device = self._prefs.haptic2_audio_device
        if not h2_device:
            slot_data["aux_silent_reason"] = (
                "Haptic 2 device not configured in Setup"
            )
            DebugLog.record(
                "stim.aux_resolved",
                slot=slot_idx, source_kind="silent",
                reason=slot_data["aux_silent_reason"],
            )
            return

        # Refuse to open the same device twice — would conflict with
        # primary stream's exclusive output handle.
        h1_device = self._prefs.haptic1_audio_device
        if h1_device and h1_device == h2_device:
            slot_data["aux_silent_reason"] = (
                "Haptic 2 device matches Haptic 1 — refusing to open twice"
            )
            DebugLog.record(
                "stim.aux_resolved",
                slot=slot_idx, source_kind="silent", device=h2_device,
                reason=slot_data["aux_silent_reason"],
            )
            return

        # Lazy imports — keep the audio stack out of cold-start when the
        # user's not playing a stim scene.
        from app.funscript_loader import (  # noqa: PLC0415
            detect_prostate_source, load_stim_channels,
        )
        from app.stim_audio_output import (  # noqa: PLC0415
            AudioFilePlaybackSource, StimAudioStream,
            query_device_sample_rate, resolve_audio_device,
        )
        from app.stim_synth import StimSynth  # noqa: PLC0415

        # Resolve the Haptic 2 device + its native sample rate up front.
        # We require similar devices (same family); mismatched rates just
        # log a warning and proceed — the user only sees pitch/timing
        # weirdness, not a crash.
        h2_handle = resolve_audio_device(h2_device, mpv_devices)
        h2_rate = query_device_sample_rate(h2_handle)
        # Routing diagnostic: prefs hold mpv-style "wasapi/{guid}" device
        # strings; the synth actually opens the device via PortAudio,
        # which uses numeric indices. resolve_audio_device() bridges the
        # two — if it picks the wrong index, the aux stream opens on
        # some entirely different sound card (or a disabled output),
        # which is silent without erroring. Logging the resolved handle
        # alongside the requested string distinguishes "synth produces
        # silence" from "synth audible but going to wrong device".
        DebugLog.record(
            "stim.aux_device_resolved",
            slot=slot_idx,
            requested=h2_device,
            resolved_handle=repr(h2_handle),
            resolved_rate=h2_rate,
        )
        if primary_sample_rate != h2_rate:
            DebugLog.record(
                "stim.aux_rate_mismatch",
                slot=slot_idx,
                primary_rate=primary_sample_rate, h2_rate=h2_rate,
                note="Recommended: Haptic 2 device family should match "
                     "Haptic 1 for tight sync.",
            )

        src = detect_prostate_source(
            funscript_set, self._prefs.content_preference,
        )

        # Build the source object based on the resolved detection. The
        # resolved kind ships in the `stim.aux_resolved` event AND lands
        # on slot_data so the Live Output panel can label what's
        # playing on this port (or display "(silent)" / "(mirror H1)").
        aux_source = None
        aux_kind: str = ""
        # Human-readable label for the Live Output panel. Empty for
        # mirror_h1 (caller fills in from primary channels' source).
        resolved_label: str = ""

        if src.kind == "audio_file":
            try:
                aux_source = AudioFilePlaybackSource(
                    src.audio_path, h2_rate,
                )
            except (ValueError, OSError) as exc:
                # Sample-rate mismatch, unsupported format, file IO
                # error — surface for debugging. We don't auto-fall to
                # mirror because the user explicitly placed this file;
                # silently routing around it would mask the bug.
                slot_data["aux_silent_reason"] = (
                    f"Failed to open prostate audio file: {exc}"
                )
                DebugLog.record(
                    "stim.aux_audio_file_failed",
                    slot=slot_idx,
                    path=str(src.audio_path),
                    error=repr(exc),
                )
                return
            aux_kind = "audio_file"
            resolved_label = src.audio_path.name if src.audio_path else ""

        elif src.kind == "funscripts":
            try:
                prostate_channels = load_stim_channels(funscript_set, prostate=True)
            except ValueError as exc:
                slot_data["aux_silent_reason"] = (
                    f"Failed to load prostate funscript: {exc}"
                )
                DebugLog.record(
                    "stim.aux_prostate_load_failed",
                    slot=slot_idx, error=repr(exc),
                )
                return
            if prostate_channels is None:
                # Shouldn't happen — detect_prostate_source already
                # confirmed alpha-prostate exists. Defensive guard.
                slot_data["aux_silent_reason"] = (
                    "Prostate funscript loaded as empty (unexpected)"
                )
                DebugLog.record(
                    "stim.aux_prostate_unexpected_none", slot=slot_idx,
                )
                return
            # Channel-summary diagnostic: surfaces whether what we're
            # feeding restim's threephase math is actually sensible. If
            # alpha is constant or near-zero, restim won't produce
            # audible signal regardless of device routing — and we'd
            # know to look upstream (funscript loader) rather than
            # downstream (audio device). Beta=zeros is expected for
            # alpha-only prostate scripts; alpha should span its full
            # range across the scene.
            import numpy as _np  # noqa: PLC0415
            # Surface volume curve stats too — "volume_present" alone is
            # ambiguous (is the channel loaded? at what amplitude?).
            # Stim scripts often ramp volume from zero at scene start,
            # which would zero-multiply the synth output even though the
            # alpha/beta position is varying correctly. Logging the
            # min/max/first-sample distinguishes "volume curve runs at 0
            # the whole scene" (malformed) from "volume curve starts at
            # 0 and ramps up" (probe at t=0 sees silence; later media
            # times are audible).
            _vol = prostate_channels.volume
            _vol_min = float(_np.min(_vol.p)) if _vol is not None else None
            _vol_max = float(_np.max(_vol.p)) if _vol is not None else None
            _vol_mean = float(_np.mean(_vol.p)) if _vol is not None else None
            _vol_first = float(_vol.p[0]) if _vol is not None and _vol.p.size else None
            DebugLog.record(
                "stim.aux_prostate_channels",
                slot=slot_idx,
                samples=int(prostate_channels.t.size),
                alpha_min=float(_np.min(prostate_channels.alpha)),
                alpha_max=float(_np.max(prostate_channels.alpha)),
                alpha_mean=float(_np.mean(prostate_channels.alpha)),
                beta_min=float(_np.min(prostate_channels.beta)),
                beta_max=float(_np.max(prostate_channels.beta)),
                volume_present=_vol is not None,
                volume_min=_vol_min,
                volume_max=_vol_max,
                volume_mean=_vol_mean,
                volume_first=_vol_first,
                source=prostate_channels.source,
            )
            aux_source = StimSynth(
                prostate_channels, media_sync,
                waveform=self._prefs.audio_algorithm,
                sample_rate=h2_rate,
            )
            aux_kind = "prostate_synth"
            # Funscript label uses the base stem with the prostate suffix
            # so the Live Output panel reads `magik-prostate.funscript`.
            resolved_label = f"{funscript_set.base_stem}-prostate.funscript"

        else:
            # No prostate-specific content → mirror Haptic 1. Same
            # primary channels, fresh StimSynth (the vendored restim
            # algorithms aren't documented as thread-safe under
            # concurrent generate_audio() calls, so we pay the
            # doubled-CPU cost rather than share state).
            aux_source = StimSynth(
                primary_channels, media_sync,
                waveform=self._prefs.audio_algorithm,
                sample_rate=h2_rate,
            )
            aux_kind = "mirror_h1"
            resolved_label = f"{funscript_set.base_stem}.funscript (mirror H1)"

        if aux_source is None:
            return

        # Hand the resolved source up to slot_data so the Live Output
        # panel can render it without re-running detection.
        slot_data["aux_resolved_source"] = {
            "kind": aux_kind,
            "label": resolved_label,
        }
        DebugLog.record(
            "stim.aux_resolved",
            slot=slot_idx, source_kind=aux_kind,
            resolved_label=resolved_label,
            content_preference=self._prefs.content_preference,
        )

        # Synth-output proof: pull blocks from the source before opening
        # the stream and log their amplitude. This is the "is restim
        # actually generating audio?" check — it answers whether silence
        # is coming from the synth (zero amplitude in the block) or from
        # somewhere downstream (synth produces audio but the device
        # routing / OS stack drops it). Running this consumes a small
        # amount of internal source state, accepted as debug-time cost.
        #
        # Probe at TWO media times: t=0 (scene start) and t=30s. Stim
        # scripts often ramp volume from zero at scene start; if the
        # synth is silent at t=0 but audible at t=30s, the silence is a
        # volume-ramp artifact and the synth itself is fine. If both
        # are silent, the issue is in the position math (e.g.,
        # beta-constant-zero hitting a threephase edge case) or
        # elsewhere downstream.
        for _probe_label, _probe_t0 in (("t=0", 0.0), ("t=30s", 30.0)):
            try:
                import numpy as _np  # noqa: PLC0415
                _test_frames = 1024
                _dt = 1.0 / float(h2_rate)
                _steady = _np.arange(_test_frames, dtype=_np.float64) * _dt + _probe_t0
                _sys_time = _steady.copy()
                _block = aux_source.generate_block_with_clocks(_steady, _sys_time)
                _block_arr = _np.asarray(_block, dtype=_np.float32)
                _peak = float(_np.max(_np.abs(_block_arr))) if _block_arr.size else 0.0
                _rms = float(_np.sqrt(_np.mean(_block_arr.astype(_np.float64) ** 2))) if _block_arr.size else 0.0
                DebugLog.record(
                    "stim.aux_source_probe",
                    slot=slot_idx,
                    source_kind=aux_kind,
                    resolved_label=resolved_label,
                    probe_at=_probe_label,
                    media_time_s=_probe_t0,
                    shape=list(_block_arr.shape),
                    dtype=str(_block_arr.dtype),
                    peak=_peak,
                    rms=_rms,
                    contains_nan=bool(_np.isnan(_block_arr).any()),
                    contains_inf=bool(_np.isinf(_block_arr).any()),
                )
            except Exception as _exc:  # noqa: BLE001
                DebugLog.record(
                    "stim.aux_source_probe_failed",
                    slot=slot_idx, source_kind=aux_kind,
                    resolved_label=resolved_label,
                    probe_at=_probe_label,
                    error=repr(_exc),
                )

        aux_stream = StimAudioStream(
            synth=aux_source,
            time_source=time_source,
            device_id=h2_device,
            mpv_devices=mpv_devices,
            is_playing_source=is_playing_source,
        )
        try:
            aux_stream.start()
        except Exception as exc:
            slot_data["aux_silent_reason"] = (
                f"Haptic 2 stream failed to open: {exc}"
            )
            # Detection succeeded but the device wouldn't open — clear
            # the resolved-source so the UI shows the silent reason
            # instead of "playing magik-prostate.funscript" (which it
            # isn't).
            slot_data.pop("aux_resolved_source", None)
            DebugLog.record(
                "stim.aux_stream_open_failed",
                slot=slot_idx, source_kind=aux_kind, device=h2_device,
                error=repr(exc),
            )
            return

        slot_data.setdefault("aux_audio_streams", []).append(aux_stream)
        DebugLog.record(
            "stim.aux_stream_opened",
            slot=slot_idx,
            source_kind=aux_kind,
            resolved_label=resolved_label,
            device=aux_stream.device_name or "(default)",
            sample_rate=h2_rate,
        )

    def _on_launch(self) -> None:
        # Reset the "has played" flag — calibrate is allowed in the
        # post-Launch / pre-first-Play window so the user can verify
        # haptic dongle levels with the player windows already up.
        # Calibrate streams from before launch survive into this
        # window and continue running; the next Play will stop them.
        self._has_played_since_launch = False

        # Snapshot every screen Qt currently knows about. Multi-monitor
        # placement bugs almost always trace back to either (a) Qt not
        # reporting the secondary screen, or (b) the screen reporting
        # geometry at (0,0) when it should be virtual-desktop offset.
        # Capturing both up front lets us split those hypotheses without
        # a second test run.
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
        # Refresh the screen list from Qt every launch. self._screens is
        # cached at __init__ via screen().virtualSiblings(); if a monitor
        # is reconfigured (sleep/wake, topology change, or even certain
        # internal Qt events between the first launch and a subsequent
        # one) Qt deletes the underlying C++ QScreen objects while we
        # still hold dangling Python references — the next .geometry()
        # call raises libshiboken "Internal C++ object already deleted",
        # the exception is swallowed by Qt's slot dispatcher, and Launch
        # silently no-ops. Pulling fresh QScreen pointers each call
        # sidesteps the dangling-ref class entirely.
        self._screens = list(QGuiApplication.screens())
        primary = QGuiApplication.primaryScreen()
        screens_snapshot = []
        for j, s in enumerate(self._screens):
            g = s.geometry()
            screens_snapshot.append({
                "index": j,
                "name": s.name(),
                "geometry": {
                    "x": g.x(), "y": g.y(),
                    "w": g.width(), "h": g.height(),
                },
                "is_primary": s is primary,
                "device_pixel_ratio": float(s.devicePixelRatio()),
            })
        DebugLog.record(
            "players.launch_request",
            screen_count=len(self._screens),
            screens=screens_snapshot,
        )
        self._close_players()

        # Per-slot pre-launch snapshot — diagnose "only one video
        # showed up" by surfacing exactly which slots had media at
        # launch time. Without this we can't tell whether the launch
        # flow skipped a slot (no media) or tried and failed silently.
        for i in range(_NUM_SLOTS):
            data = self._slot_data(i)
            DebugLog.record(
                "players.slot_snapshot",
                slot=i,
                role=_SLOT_ROLES[i],
                has_video=bool(data.get("video_path")),
                has_audio=bool(data.get("audio_path")),
                has_funscript=bool(data.get("funscript_set")),
                screen_idx=self._screen_index_for_slot(i),
            )

        launched = False
        for i in range(_NUM_SLOTS):
            data = self._slot_data(i)
            video_path: str = data["video_path"]
            audio_path: str = data["audio_path"]
            funscript_set = data.get("funscript_set")
            # Slot is "enabled" iff it has media. No separate checkbox anymore.
            if not (video_path or audio_path or funscript_set):
                DebugLog.record(
                    "players.slot_skipped", slot=i,
                    reason="no media",
                )
                continue

            # v0.0.4: routing reads directly from `_prefs`. Slot index
            # determines role (video / stim / mirror); role determines
            # device + screen + fill via the `_*_for_slot` helpers.
            audio_device = self._audio_device_for_slot(i)

            # Native funscript synthesis (Stim slot). Bypasses mpv
            # entirely — StimSynth produces audio from the funscript and
            # streams to the slot's audio device. Time and play/pause
            # follow the SyncEngine's primary player (Slot 1's video).
            if funscript_set is not None:
                if self._launch_stim_synth(i, data, funscript_set, audio_device):
                    launched = True
                continue

            # Audio-only: no PlayerWindow, no monitor. Headless mpv still
            # participates in sync (seek/pause/play apply via _active list).
            if audio_path and not video_path:
                DebugLog.record("players.launch_slot", slot=i, mode="audio_only")
                self._engine.init_player_audio_only(i, audio_device)
                self._engine.load_file(i, audio_path)
                launched = True
                continue

            screen_idx = self._screen_index_for_slot(i)
            if screen_idx is None or screen_idx >= len(self._screens):
                screen_idx = 0
                fell_back_to_primary = True
            else:
                fell_back_to_primary = False
            screen = self._screens[screen_idx]
            target_geo = screen.geometry()

            DebugLog.record(
                "players.launch_slot",
                slot=i,
                mode="video",
                has_audio_override=bool(audio_path),
                fullscreen=self._fullscreen_toggle.isChecked(),
                resolved_screen_idx=screen_idx,
                fell_back_to_primary=fell_back_to_primary,
                screen_name=screen.name(),
                screen_geometry={
                    "x": target_geo.x(), "y": target_geo.y(),
                    "w": target_geo.width(), "h": target_geo.height(),
                },
                source="setup_prefs",
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
            fill = self._fill_for_screen_index(screen_idx)
            self._engine.init_player(
                i, pw.native_wid(), audio_device, fill=fill,
            )
            DebugLog.record(
                "player.fill_mode",
                slot=i,
                fill=fill,
                screen_name=screen.name(),
                screen_geometry={
                    "w": target_geo.width(), "h": target_geo.height(),
                },
            )
            # Load video (or audio-only file)
            media_path = video_path or audio_path
            self._engine.load_file(i, media_path)
            # If separate audio override, set the audio file
            if video_path and audio_path:
                try:
                    self._engine._players[i].audio_files = [audio_path]  # type: ignore[index]
                except Exception:
                    pass
            # Mirror slots are muted; primary video plays at the
            # scene-volume slider value (default 100, but the user may
            # have nudged it pre-launch).
            if _SLOT_ROLES[i] == "mirror":
                self._engine.set_volume(i, 0)
            elif _SLOT_ROLES[i] == "video":
                self._engine.set_volume(i, int(self._scene_volume_slider.value()))
            launched = True

        if launched:
            self._timer.start()
            self.raise_()
        # Re-render the Live panels so the Output panel picks up
        # aux_resolved_source / aux_silent_reason set during launch.
        self._refresh_live_panels()
        # Calibrate is locked while players are active — disable both
        # buttons (and the helper hard-stops any stream that survived
        # the explicit stop above, defensively).
        self._update_calibrate_buttons_enabled()

    # ── Transport ──────────────────────────────────────────────────────────────

    def _on_play_pause(self) -> None:
        active_count = len(self._engine._active)
        if not self._engine.has_active_players():
            DebugLog.record("transport.play_pause", result="no_active_players")
            return
        if self._engine.is_paused():
            DebugLog.record("transport.play", active=active_count)
            # Lock calibrate from this point until Close. The launched
            # stim streams are about to drive the haptic devices; we
            # can't have calibrate fighting for the same handle.
            self._has_played_since_launch = True
            self._update_calibrate_buttons_enabled()
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

    def _on_scene_volume_changed(self, value: int) -> None:
        """Apply the slider's value to the video slot's mpv player.
        No-op pre-launch (engine has no player yet) — the launch flow
        re-applies the current slider value once the player is built."""
        self._scene_volume_label.setText(f"🔊  Scene volume — {value}%")
        # Slot 0 is the video slot carrying the scene audio. Mirror slots
        # (2/3) stay muted via _on_launch's set_volume(0). Slot 1 is the
        # synth path — separate device, untouched.
        self._engine.set_volume(0, int(value))

    # ── Seek with pop-fix envelope ─────────────────────────────────────────────

    # Pre-seek and post-seek ramp duration. 500 ms each side. The synth
    # recomputes alpha/beta modulation per buffer; a seek lands inside a
    # fade window and flips the carrier discontinuously without this.
    # Iteration history:
    #   - 120 ms (tried 2026-05-02): "pop on the upside" 60% of seeks
    #   - 250 ms (tried 2026-05-02): pops down but still ~1/seek
    #   - 500 ms (current): per user request "go to half second"
    _SEEK_ENVELOPE_S = 0.50

    # Hold-at-zero window inserted between the offset flip and the
    # ramp-up. Lets mpv's decoder produce a couple of stable audio
    # blocks at the new position and the time smoother converge on the
    # new offset before output is audible — without this the ramp-up
    # happens over a still-wobbling signal and "takes a few pops to
    # settle in" (user, 2026-05-03). Total seek gap is now
    # 500 + 200 + 500 = 1.2 s; predictable, user accepts the pause.
    _SEEK_SETTLE_S = 0.20

    def _all_active_stim_streams(self) -> list:
        """Return every live StimAudioStream / aux stream across slot data.

        Used by the seek-envelope path to ramp ALL stim outputs to
        silence simultaneously. Empty list means no stim is currently
        running and the seek can fire immediately without an envelope
        round-trip.
        """
        streams: list = []
        for i in range(_NUM_SLOTS):
            d = self._slot_data(i)
            primary = d.get("stim_audio_stream")
            if primary is not None:
                streams.append(primary)
            for aux in d.get("aux_audio_streams") or []:
                streams.append(aux)
        return streams

    def _seek_with_envelope(self, pos: float) -> None:
        """Seek every active player to `pos` with a three-stage
        envelope: ramp-down → settle hold → ramp-up. Hides the
        funscript-axis discontinuity AND the post-seek warm-up window
        where mpv's decoder and the time smoother are still
        converging — without the settle hold, the ramp-up happens
        over a wobbling signal and "takes a few pops to settle in"
        (user, 2026-05-03). See `project_forgeplayer_pop_fix_spec.md`.

        If nothing is currently audible (no players, paused), seeks
        immediately — no envelope dance needed when there's nothing
        to fade.
        """
        streams = self._all_active_stim_streams()
        needs_envelope = (
            bool(streams)
            and self._engine.has_active_players()
            and not self._engine.is_paused()
        )
        if not needs_envelope:
            self._engine.seek_all(pos)
            return

        DebugLog.record(
            "seek.envelope_start", target_s=pos, streams=len(streams),
            ramp_seconds=self._SEEK_ENVELOPE_S,
            settle_seconds=self._SEEK_SETTLE_S,
        )
        for s in streams:
            s.request_envelope(0.0, self._SEEK_ENVELOPE_S)

        def _do_seek() -> None:
            DebugLog.record("seek.execute", target_s=pos)
            self._engine.seek_all(pos)

            def _do_ramp_up() -> None:
                DebugLog.record("seek.ramp_up", target_s=pos)
                for s in streams:
                    s.request_envelope(1.0, self._SEEK_ENVELOPE_S)

            QTimer.singleShot(
                int(self._SEEK_SETTLE_S * 1000), _do_ramp_up,
            )

        # QTimer.singleShot keeps the GUI responsive while the audio
        # thread completes the silence ramp. After the timer fires the
        # actual seek runs; settle hold gives mpv + smoother a chance
        # to stabilize at the new position before ramp-up; sync
        # resumes naturally because the synth's time_source was never
        # stopped.
        QTimer.singleShot(int(self._SEEK_ENVELOPE_S * 1000), _do_seek)

    def _skip(self, seconds: float) -> None:
        pos = self._engine.get_position()
        dur = self._engine.get_duration()
        new_pos = max(0.0, min(pos + seconds, dur))
        self._seek_with_envelope(new_pos)

    def _on_seek_press(self) -> None:
        self._seek_dragging = True

    def _on_seek_release(self) -> None:
        dur = self._engine.get_duration()
        if dur > 0:
            pos = (self._seek_bar.value() / 10000.0) * dur
            self._seek_with_envelope(pos)
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
        # Stop any running calibrate streams so the audio thread
        # finishes its fade-out before the device is torn down — without
        # this the user gets a pop on app close mid-calibration.
        for port_attr in ("_calib_h1", "_calib_h2"):
            stream = getattr(self, port_attr, None)
            if stream is not None:
                try:
                    stream.stop()
                except Exception:
                    pass
                setattr(self, port_attr, None)
        # Auto-export captured debug events. Saves the user from the
        # "did I click Export before closing?" friction that's bitten
        # multiple dogfood sessions. Best-effort — if export fails for
        # any reason (disk full, permissions), don't block the close.
        if DebugLog.event_count() > 0:
            try:
                DebugLog.export()
            except Exception:
                pass
        self._engine.terminate_all()
        super().closeEvent(event)
