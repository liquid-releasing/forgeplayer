#!/usr/bin/env python3
# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""eHaptic Studio Player — synchronized multi-screen video/audio player."""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from app.control_window import ControlWindow


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


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    win = ControlWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
