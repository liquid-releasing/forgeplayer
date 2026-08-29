#!/usr/bin/env python3
# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""ForgePlayer — synchronized multi-monitor video/audio player."""

import sys
from pathlib import Path

# Crash diagnostics: dump the faulting thread's C-level stack to
# ~/.forgeplayer/faulthandler.log. Keep the file handle alive at module scope
# so it isn't garbage-collected.
#
# `all_threads` is deliberately FALSE, and that is load-bearing. On Windows
# faulthandler's handler runs for every FIRST-CHANCE exception carrying the
# error bit — not just fatal ones — and libmpv raises a benign 0xe24c4a02
# constantly (measured 2026-08-29: 39 per 40 thumbnail grabs; 241-295 per app
# session). With all_threads=True each of those walked the frame chain of every
# live thread — and this app runs ~290 of them — WITHOUT holding the GIL, while
# those threads kept executing and freeing the very frames being walked.
#
# That is not a theoretical race. Two crashes captured out-of-process on
# 2026-08-29 (see scripts/crash_watch.py) both faulted at python313.dll
# +0x3a1480 and +0x3a1a25, which the export table places inside the static
# functions following PyTraceBack_Print — i.e. inside _Py_DumpTraceback /
# dump_frame themselves. The crash reporter was the crash: every benign mpv
# exception rolled the dice on an unsynchronised walk of hundreds of threads,
# and the "random numpy internal" in older truncated logs was simply whichever
# thread it was printing when it lost.
#
# Dumping only the faulting thread keeps what a user's crash report actually
# needs (the stack that died) and drops the cross-thread walk entirely — the
# faulting thread is stopped inside the handler, so its own frames are stable.
# For real crash work attach scripts/crash_watch.py, which sees the fault from
# outside the process where nothing can truncate or race it.
#
# Always-on (not gated by the in-app Debug toggle), so unlike the Debug
# stream files this one grows on literally every launch forever if left
# unchecked — a session-start marker every time, plus a full per-thread
# dump on any genuine crash. _cap_faulthandler_log trims it back before
# each session so it can't grow without bound, while still keeping enough
# recent history that we can ask a user for the file after a crash.
_FAULT_LOG_MAX_BYTES = 5 * 1024 * 1024
_FAULT_LOG_KEEP_BYTES = 2 * 1024 * 1024


def _cap_faulthandler_log(path, os_mod) -> None:
    try:
        if os_mod.path.getsize(path) <= _FAULT_LOG_MAX_BYTES:
            return
        with open(path, "rb") as f:
            f.seek(-_FAULT_LOG_KEEP_BYTES, os_mod.SEEK_END)
            tail = f.read()
        # Drop a possibly-truncated partial line so the kept text starts
        # cleanly at a line boundary instead of mid-stack-frame.
        nl = tail.find(b"\n")
        if nl != -1:
            tail = tail[nl + 1:]
        kept_mb = _FAULT_LOG_KEEP_BYTES // (1024 * 1024)
        with open(path, "wb") as f:
            f.write(
                f"===== faulthandler.log truncated (kept most recent "
                f"~{kept_mb}MB) =====\n".encode("utf-8")
            )
            f.write(tail)
    except OSError:
        pass


try:
    import faulthandler
    import os as _os
    _FAULT_LOG = _os.path.join(_os.path.expanduser("~"), ".forgeplayer",
                               "faulthandler.log")
    _os.makedirs(_os.path.dirname(_FAULT_LOG), exist_ok=True)
    _cap_faulthandler_log(_FAULT_LOG, _os)
    _FAULT_FP = open(_FAULT_LOG, "a", buffering=1)
    _FAULT_FP.write("\n===== ForgePlayer session start =====\n")
    faulthandler.enable(file=_FAULT_FP, all_threads=False)
except Exception:
    pass

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


def _prefer_high_performance_gpu() -> None:
    """Register this executable for Windows' "High performance" GPU on
    hybrid-graphics laptops (an integrated GPU alongside a discrete one),
    so mpv's D3D11 context lands on the discrete GPU instead of whichever
    one Windows would otherwise default to.

    Why this matters: mpv's `vo=gpu` D3D11 teardown (context release on
    Close Players / scene switch) hits a confirmed, currently-unfixed AMD
    driver bug — an access violation inside the driver's own destroy path
    (mpv-player/mpv#14601; also mpv-player/mpv#11882 for the matching
    "dispose then create a new instance" pattern). It's a driver defect,
    not something fixable from mpv or from here — but on a machine with a
    second (often less-used, better-tested for this kind of churn) GPU
    available, routing around the buggy adapter entirely sidesteps it.
    Confirmed via mpv's own D3D11 log line ("Device Name: ...") that this
    dev machine's AMD Radeon 890M iGPU is the one being hit (2026-08-20).

    This does NOT help single-GPU machines (nothing to route around to) —
    see the reuse-instead-of-recreate change in SyncEngine/ControlWindow
    for the fix that protects those too, by minimizing how often the
    crash-prone teardown path runs at all.

    Windows reads this per-exe preference from the registry at PROCESS
    CREATION — writing it here has no effect on the already-running
    process, only on the *next* launch of this same executable. That's
    fine: it only needs to be set once. Best-effort and silent — a
    restricted account without registry write access just keeps running
    on the default-assigned GPU, exactly as today.
    """
    try:
        import winreg

        exe = sys.executable
        key_path = r"Software\Microsoft\DirectX\UserGpuPreferences"
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, key_path, access=winreg.KEY_ALL_ACCESS,
        ) as key:
            try:
                existing, _ = winreg.QueryValueEx(key, exe)
            except FileNotFoundError:
                existing = None
            # GpuPreference=2 is Windows' "High performance" tier (the
            # discrete GPU on a hybrid system). Skip the write if it's
            # already set — no need to touch the registry every launch.
            if existing != "GpuPreference=2;":
                winreg.SetValueEx(
                    key, exe, 0, winreg.REG_SZ, "GpuPreference=2;",
                )
    except Exception:
        pass


if sys.platform == "win32":
    _prefer_high_performance_gpu()

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
