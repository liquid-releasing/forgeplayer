#!/usr/bin/env python3
# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""ForgePlayer — synchronized multi-monitor video/audio player."""

import sys
from pathlib import Path

# Claim a single-threaded COM apartment for the GUI thread BEFORE anything
# (libmpv, imported transitively below) can initialize COM as multi-threaded.
# The modern Windows folder/file picker (IFileDialog) requires STA; when mpv
# gets there first with MTA, Qt silently falls back to its dated non-native
# dialog (no Quick Access / drive navigation). Claiming STA here keeps the
# native picker — a later MTA request on this thread just fails harmlessly and
# the thread stays STA.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPalette, QColor
from PySide6.QtCore import QTimer
from app.control_window import ControlWindow

# Branding directory siblings main.py at runtime (dev) and ships next
# to the executable in PyInstaller bundles. Look for the multi-res ICO
# first (Windows native, also fine on macOS / Linux via Qt); fall back
# to the bare PNG if icons haven't been regenerated.
_HERE = Path(__file__).parent
_ICON_CANDIDATES = (
    _HERE / "branding" / "forgeplayer.ico",
    # Square hero source (fills the frame). The old forgeplayer_icon.png was
    # non-square and letterboxed into a tiny title-bar icon.
    _HERE / "branding" / "forgeplayer_hero_for_icon.png",
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


def _first_path_arg(args: list[str]) -> str | None:
    """The first command-line argument that points at an existing path — a
    bundle/scene to open on launch (file association passes `"%1"`)."""
    for a in args[1:]:
        if a and not a.startswith("-") and Path(a).exists():
            return a
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
    # Open a bundle/scene passed on the command line (double-click a .forge via
    # file association, or `forgeplayer <path>`). Deferred onto the event loop
    # so widgets / mpv are fully up before the scene activates.
    open_target = _first_path_arg(app.arguments())
    if open_target:
        QTimer.singleShot(0, lambda: win.open_path(open_target))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
