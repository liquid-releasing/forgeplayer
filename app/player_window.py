# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""PlayerWindow — a black Qt widget that hosts an embedded mpv player."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QScreen


class PlayerWindow(QWidget):
    """Borderless black window placed on a specific monitor.

    mpv is embedded directly into this widget via its native window handle
    (HWND on Windows, NSView on macOS).  Call native_wid() after show() to
    get a valid handle.
    """

    def __init__(self, slot_index: int) -> None:
        super().__init__()
        self.slot_index = slot_index
        self.setWindowTitle(f"eHaptic Player {slot_index + 1}")
        self.setStyleSheet("background-color: black;")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setMinimumSize(320, 180)

    def place_on_screen(self, screen: QScreen, fullscreen: bool = True) -> None:
        """Move this window to fill *screen*."""
        geo: QRect = screen.geometry()
        self.setGeometry(geo)
        if fullscreen:
            self.showFullScreen()

    def native_wid(self) -> int:
        """Return the native window handle for mpv's wid option.

        Must be called after show() so the OS has assigned a real handle.
        """
        return int(self.winId())

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Let Escape close the player window
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
