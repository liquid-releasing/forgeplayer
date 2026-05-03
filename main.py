#!/usr/bin/env python3
# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""ForgePlayer — synchronized multi-monitor video/audio player."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPalette, QColor
from app.control_window import ControlWindow

# Branding directory siblings main.py at runtime (dev) and ships next
# to the executable in PyInstaller bundles. Look for the multi-res ICO
# first (Windows native, also fine on macOS / Linux via Qt); fall back
# to the bare PNG if icons haven't been regenerated.
_HERE = Path(__file__).parent
_ICON_CANDIDATES = (
    _HERE / "branding" / "forgeplayer.ico",
    _HERE / "branding" / "forgeplayer_icon.png",
)


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(14, 17, 23))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(250, 250, 250))
    p.setColor(QPalette.ColorRole.Base,            QColor(26, 29, 39))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(14, 17, 23))
    p.setColor(QPalette.ColorRole.Text,            QColor(250, 250, 250))
    p.setColor(QPalette.ColorRole.Button,          QColor(45, 49, 72))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(250, 250, 250))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(255, 75, 75))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Mid,             QColor(45, 49, 72))
    p.setColor(QPalette.ColorRole.Dark,            QColor(10, 12, 18))
    return p


def _resolve_icon() -> QIcon | None:
    for path in _ICON_CANDIDATES:
        if path.is_file():
            return QIcon(str(path))
    return None


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    icon = _resolve_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    win = ControlWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
