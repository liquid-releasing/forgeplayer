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
    # Emitted from the mpv event thread (single-click on the video surface);
    # queued to the GUI thread where it flips the control bar. A plain method
    # call from mpv's thread would touch Qt widgets off the GUI thread.
    toggle_controls_requested = Signal()
    # Prev/Next chapter clicks on THIS window's overlay. Chapter state
    # (the loaded list, the "effective position" bookkeeping) lives on
    # ControlWindow, not here — these just relay the click to
    # ControlWindow's own _on_prev_chapter/_on_next_chapter so the
    # on-screen buttons and the console's Prev/Next buttons are always
    # driven by the exact same chapter-seek logic, never a second copy
    # of it that could drift.
    prev_chapter_requested = Signal()
    next_chapter_requested = Signal()
    # "Console" on this window's overlay, and Escape from a windowed player.
    # Raises the control window WITHOUT touching playback — with the console
    # usually hidden behind fullscreen players, the only way back used to be
    # closing the players, which lost your place (dogfood 2026-08-29).
    console_requested = Signal()
    # "Loop" on this window's overlay. Looping is a SESSION-wide behaviour,
    # not a per-window one: the slots share one timeline, so a per-window
    # loop would restart one screen while the others ran on and desync the
    # whole scene. The button therefore reports intent to ControlWindow,
    # which owns the state and mirrors it back to every open window via
    # set_loop_enabled().
    loop_toggled = Signal(bool)

    def __init__(self, slot_index: int, engine: SyncEngine) -> None:
        super().__init__()
        self.slot_index = slot_index
        self._engine = engine
        self._seek_dragging = False
        # Set while set_loop_enabled() writes the Loop button, so the
        # resulting `toggled` signal isn't relayed back as a user click.
        self._loop_echo_guard = False
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
        # Hidden by default — the displays read as clean video walls. A single
        # click anywhere in the window (via the mpv MBTN_LEFT binding for the
        # video surface, or mousePressEvent for the letterbox chrome) toggles
        # it; clicking again hides it. Double-click still closes all players.
        self._ctrl_bar = self._build_ctrl()
        self._ctrl_bar.setVisible(False)
        root.addWidget(self._ctrl_bar)
        self.toggle_controls_requested.connect(self._toggle_controls)

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

        # Prev / Play-pause / Next — Prev and Next flank Play directly so a
        # viewer who only ever sees this overlay (the console is usually
        # hidden) can still jump to a favorite spot without hunting for a
        # separate row of buttons. Disabled until ControlWindow confirms
        # chapters are loaded for the active scene (set_chapter_nav_enabled).
        self._btn_prev_chapter = QPushButton("⏮")
        self._btn_prev_chapter.setFixedSize(28, 28)
        self._btn_prev_chapter.setStyleSheet(
            "background: #2d3148; color: #e0e0e0; border-radius: 4px;"
            " font-size: 11px;"
        )
        self._btn_prev_chapter.setToolTip("Previous chapter")
        self._btn_prev_chapter.setEnabled(False)
        self._btn_prev_chapter.clicked.connect(self.prev_chapter_requested.emit)
        h.addWidget(self._btn_prev_chapter)

        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedSize(32, 32)
        self._btn_play.setStyleSheet(
            "background: #ff4b4b; color: white; font-weight: bold;"
            " border-radius: 4px; font-size: 12px;"
        )
        self._btn_play.clicked.connect(self._on_play_pause)
        h.addWidget(self._btn_play)

        self._btn_next_chapter = QPushButton("⏭")
        self._btn_next_chapter.setFixedSize(28, 28)
        self._btn_next_chapter.setStyleSheet(
            "background: #2d3148; color: #e0e0e0; border-radius: 4px;"
            " font-size: 11px;"
        )
        self._btn_next_chapter.setToolTip("Next chapter")
        self._btn_next_chapter.setEnabled(False)
        self._btn_next_chapter.clicked.connect(self.next_chapter_requested.emit)
        h.addWidget(self._btn_next_chapter)

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

        # Loop — restart the scene when it plays through, instead of
        # stopping on the last frame. Checkable so the state is visible at a
        # glance from the overlay alone (the console is usually buried).
        self._btn_loop = QPushButton("Loop")
        self._btn_loop.setCheckable(True)
        self._btn_loop.setFixedHeight(28)
        self._btn_loop.setStyleSheet(
            "QPushButton { background: #2d3148; color: #e0e0e0;"
            " border-radius: 4px; font-size: 11px; padding: 0 10px; }"
            "QPushButton:checked { background: #ff4b4b; color: white;"
            " font-weight: bold; }"
        )
        self._btn_loop.setToolTip(
            "Repeat the scene when it reaches the end.\n"
            "Off: playback stops on the last frame."
        )
        self._btn_loop.toggled.connect(self._on_loop_clicked)
        h.addWidget(self._btn_loop)

        # Console — bring the control window back to the front. The console
        # is normally buried under fullscreen players; without this the only
        # route back was closing them, which throws away your position.
        self._btn_console = QPushButton("Console")
        self._btn_console.setFixedHeight(28)
        self._btn_console.setStyleSheet(
            "background: #2d3148; color: #e0e0e0; border-radius: 4px;"
            " font-size: 11px; padding: 0 10px;"
        )
        self._btn_console.setToolTip(
            "Show the ForgePlayer console — playback keeps running"
        )
        self._btn_console.clicked.connect(self.console_requested.emit)
        h.addWidget(self._btn_console)

        return bar

    # ── Transport slots ────────────────────────────────────────────────────────

    def _on_loop_clicked(self, checked: bool) -> None:
        """Relay a click to ControlWindow. Suppressed while
        set_loop_enabled() is writing the button's state, so mirroring the
        session value back onto this window can't be mistaken for the user
        toggling it again (which would bounce between windows forever)."""
        if self._loop_echo_guard:
            return
        self.loop_toggled.emit(checked)

    def set_loop_enabled(self, enabled: bool) -> None:
        """Show the session's loop state on this window's button without
        emitting — ControlWindow calls this on every open window whenever
        the value changes, and on newly launched windows, so all the
        overlays agree."""
        self._loop_echo_guard = True
        try:
            self._btn_loop.setChecked(enabled)
        finally:
            self._loop_echo_guard = False

    def set_chapter_nav_enabled(self, enabled: bool) -> None:
        """Enable/disable this window's Prev/Next chapter buttons — mirrors
        ControlWindow._update_chapter_buttons_enabled so both button sets
        always agree on whether the active scene has chapters."""
        self._btn_prev_chapter.setEnabled(enabled)
        self._btn_next_chapter.setEnabled(enabled)

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

    def _request_close_all(self) -> None:
        """Ask ControlWindow to tear down all players together, deferred to
        the next event-loop turn.

        The teardown (_close_players) drops the last Python reference to
        every PlayerWindow, including this one — and when *this* window is
        the one whose event handler (closeEvent/keyPressEvent/
        mouseDoubleClickEvent) triggered the teardown, an immediate emit()
        lets that drop (and the underlying C++ QWidget destruction it
        triggers) happen while Qt's C++ virtual dispatch for that very
        handler is still unwinding on the call stack — a use-after-free of
        `self`, seen as an intermittent native crash on close. Deferring via
        singleShot(0, …) lets the originating call fully return to the event
        loop first, so the teardown runs on a clean stack.
        """
        QTimer.singleShot(0, self.close_all_requested.emit)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            # Escape means "get me out of this view", never "throw the
            # session away" (user decision, 2026-08-29). Fullscreen → drop to
            # windowed; already windowed → raise the console. Closing is X,
            # double-click, or the console's Close button — all of which go
            # through the group teardown, because closing one window alone
            # leaves the engine polling a dead mpv handle and freezes the rest.
            fullscreen = self.isFullScreen()
            DebugLog.record(
                "key.escape", slot=self.slot_index,
                action="exit_fullscreen" if fullscreen else "raise_console",
            )
            if fullscreen:
                self.showNormal()
            else:
                self.console_requested.emit()
        elif event.key() == Qt.Key.Key_F11:
            DebugLog.record("key.f11", slot=self.slot_index)
            self._toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Space:
            DebugLog.record("key.space", slot=self.slot_index)
            self._on_play_pause()
        else:
            super().keyPressEvent(event)

    def _toggle_controls(self) -> None:
        """Flip the on-screen control bar. Runs on the GUI thread (driven by
        toggle_controls_requested for video-surface clicks, or directly for
        chrome clicks)."""
        self._ctrl_bar.setVisible(not self._ctrl_bar.isVisible())
        DebugLog.record(
            "player.toggle_controls",
            slot=self.slot_index,
            visible=self._ctrl_bar.isVisible(),
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Single-click on the non-mpv chrome (letterbox bars, window
        background) toggles the control bar — mirrors the mpv MBTN_LEFT
        binding that covers clicks over the video surface itself. Clicks on
        the control bar's own buttons/slider are consumed by those child
        widgets and never reach here, so interacting with the bar doesn't
        hide it."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_controls()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """Double-click = Escape — tear all players down together. mpv owns the
        video surface (handled by an mpv MBTN_LEFT_DBL binding in
        SyncEngine.init_player); this Qt handler covers double-clicks on the
        non-mpv chrome (control bar, window frame, letterbox edges)."""
        DebugLog.record("mouse.double_click", slot=self.slot_index)
        self._request_close_all()
        event.accept()

    def closeEvent(self, event) -> None:  # noqa: N802
        """User clicked the window's X — route through the group teardown so
        the engine stops polling the dead mpv handle, same as ESC."""
        if not self._teardown_in_progress:
            DebugLog.record("player.user_close", slot=self.slot_index)
            event.ignore()
            self._request_close_all()
            return
        DebugLog.record("player.teardown_close", slot=self.slot_index)
        super().closeEvent(event)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def set_fullscreen(self, on: bool) -> None:
        """Apply fullscreen state explicitly. Driven by the Live panel's
        'Fullscreen players' toggle so flipping it acts on already-open
        windows (not just the next launch). The window is already realized
        on its target screen by now, so showFullScreen() resolves to the
        correct monitor without the windowed-flash dance place_on_screen
        needs at launch time."""
        if on and not self.isFullScreen():
            self.showFullScreen()
        elif not on and self.isFullScreen():
            self.showNormal()

    # ── Placement ─────────────────────────────────────────────────────────────

    def place_on_screen(self, screen: QScreen, fullscreen: bool = False) -> None:
        """Place this window on *screen*.

        fullscreen=True kicks into kiosk mode (used for the 3-wall rig
        configuration). fullscreen=False — the v0.0.1-alpha default — places
        a sensibly-sized, frame-decorated window centered on the target
        monitor so a user with 2 screens can still see their desktop.

        Emits two debug events bracketing Qt's show + setGeometry chain:
        ``player.placement_target`` (what we asked for) and
        ``player.placement_actual`` (where Qt actually put it). Compare
        the two when diagnosing multi-monitor placement bugs — Qt and
        the Windows DWM sometimes silently snap windows back to the
        primary screen, and only the diff between target and actual
        reveals it.
        """
        geo: QRect = screen.geometry()
        if fullscreen:
            target_x, target_y = geo.x(), geo.y()
            target_w, target_h = geo.width(), geo.height()
        else:
            target_w = min(1280, int(geo.width() * 0.9))
            target_h = min(720 + _CTRL_HEIGHT, int(geo.height() * 0.9))
            target_x = geo.x() + (geo.width() - target_w) // 2
            target_y = geo.y() + (geo.height() - target_h) // 2

        # Force the native window to exist before we try to migrate it to
        # the target screen. Without this, windowHandle() is None and Qt
        # creates the native window on the primary screen at show()-time,
        # at which point DWM clamps any negative-X coordinates back onto
        # the primary monitor. Calling create() realizes the QWindow
        # eagerly so we can setScreen() on it.
        self.create()
        handle = self.windowHandle()
        pre_show_screen = handle.screen() if handle is not None else None
        if handle is not None and pre_show_screen is not screen:
            handle.setScreen(screen)

        DebugLog.record(
            "player.placement_target",
            slot=self.slot_index,
            fullscreen=fullscreen,
            target_screen_name=screen.name(),
            target_screen_geometry={
                "x": geo.x(), "y": geo.y(),
                "w": geo.width(), "h": geo.height(),
            },
            target_window_geometry={
                "x": target_x, "y": target_y,
                "w": target_w, "h": target_h,
            },
            pre_show_screen_name=pre_show_screen.name() if pre_show_screen is not None else None,
        )

        self.setGeometry(target_x, target_y, target_w, target_h)
        if fullscreen:
            # showFullScreen() recomputes the fullscreen rect using
            # QWidget::screen() — the widget's *internal* screen association,
            # which on Windows lags behind the QWindow handle screen we
            # just migrated via setScreen(). The result: fullscreen lands
            # on the primary monitor regardless of our setScreen call,
            # stacking slot 2's window on top of slot 0's. Showing
            # windowed first realizes the QWidget on the migrated screen,
            # so the subsequent showFullScreen() resolves to the correct
            # monitor. The brief windowed flash is the cost of correctness.
            self.showNormal()
            self.showFullScreen()
        else:
            self.showNormal()
            # setGeometry positions the *client area* at target_y; Windows
            # then puts the title bar above that. On some configurations
            # (multi-monitor + DPI scaling, top-anchored taskbar) the
            # title bar lands above the visible screen top, leaving the
            # user no way to close or move the window. Defer the check
            # via singleShot so frameGeometry returns the post-show
            # frame; querying immediately after showNormal() reads the
            # stale pre-realization rect.
            QTimer.singleShot(
                50,
                lambda s=screen: self._ensure_title_bar_visible_after_show(s),
            )

        # Read back where the window actually landed. Qt may have
        # respected our setGeometry(), or it may have moved the window
        # to fit the primary screen due to DPI/DWM quirks. Capture both
        # the window's own geometry and which screen Qt now associates
        # the window with (via windowHandle().screen()).
        actual_geo = self.frameGeometry()
        handle = self.windowHandle()
        actual_screen = handle.screen() if handle is not None else None
        DebugLog.record(
            "player.placement_actual",
            slot=self.slot_index,
            fullscreen=fullscreen,
            actual_window_geometry={
                "x": actual_geo.x(), "y": actual_geo.y(),
                "w": actual_geo.width(), "h": actual_geo.height(),
            },
            actual_screen_name=actual_screen.name() if actual_screen is not None else None,
            actual_screen_matches_target=(
                actual_screen is screen if actual_screen is not None else False
            ),
        )

    def _ensure_title_bar_visible_after_show(self, screen: QScreen) -> None:
        """Defensively shift the window down if its title bar landed
        above the available screen area. Called via singleShot after
        ``showNormal()`` so frameGeometry returns the realized frame
        (not the pre-show default rect). No-op when the window already
        sits inside the screen.
        """
        avail = screen.availableGeometry()
        frame = self.frameGeometry()
        if frame.y() < avail.y():
            delta = avail.y() - frame.y()
            self.move(frame.x(), frame.y() + delta)
            DebugLog.record(
                "player.title_bar_correction",
                slot=self.slot_index,
                pre_y=frame.y(),
                post_y=frame.y() + delta,
                screen_avail_y=avail.y(),
            )
