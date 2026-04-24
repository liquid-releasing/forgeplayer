# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for ForgePlayer.
#
# Build locally with:
#     pyinstaller ForgePlayer.spec --clean
#
# Output:
#   Windows: dist/ForgePlayer/ForgePlayer.exe
#   macOS:   dist/ForgePlayer/ForgePlayer.app
#   Linux:   dist/ForgePlayer/ForgePlayer
#
# Requirements to build:
#   - PySide6 + python-mpv installed in the build environment.
#   - libmpv shared library available:
#       Windows: libmpv-2.dll next to this spec (checked into the repo? NO —
#                too big; CI fetches it. Local builds copy from the .venv.)
#       macOS:   libmpv.dylib from `brew install mpv`.
#       Linux:   libmpv.so.2 from `apt install libmpv2 libmpv-dev`.

import os
import shutil
import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()


# ── libmpv discovery ─────────────────────────────────────────────────────────
#
# python-mpv loads libmpv at import time via ctypes. PyInstaller needs the
# shared library bundled next to mpv.py in the frozen app, otherwise the
# frozen `import mpv` will fail with the same OSError users hit during
# dogfood. We locate the lib per-platform and add it as a binary so
# PyInstaller places it in the right spot.

def _find_libmpv() -> tuple[str, str] | None:
    """Return (source_path, destination_folder_in_bundle) or None.

    destination_folder is "." (the exe's directory) on all platforms —
    python-mpv falls back to `os.path.dirname(__file__)` which, in the
    frozen bundle, resolves to the _MEIPASS temp dir that contains the
    collected site-packages.
    """
    if sys.platform == "win32":
        # Prefer the DLL sitting next to this spec (developers vendor it).
        local = SPEC_DIR / "libmpv-2.dll"
        if local.is_file():
            return str(local), "."
        # Fall back to the one python-mpv expects at .venv site-packages.
        # This is what users / CI hit after extracting mpv-dev.
        try:
            import mpv  # noqa: F401
            dll = Path(os.path.dirname(__file__) if False else "") / "libmpv-2.dll"
            if dll.is_file():
                return str(dll), "."
        except Exception:
            pass
        return None

    if sys.platform == "darwin":
        # Homebrew keeps dylibs under /opt/homebrew/lib (Apple Silicon) or
        # /usr/local/lib (Intel). Pick whichever exists.
        for base in ("/opt/homebrew/lib", "/usr/local/lib"):
            for name in ("libmpv.2.dylib", "libmpv.dylib"):
                p = Path(base) / name
                if p.is_file():
                    return str(p), "."
        return None

    # Linux — apt installs to /usr/lib/x86_64-linux-gnu typically.
    for base in (
        "/usr/lib/x86_64-linux-gnu",
        "/usr/lib64",
        "/usr/lib",
    ):
        for name in ("libmpv.so.2", "libmpv.so.1", "libmpv.so"):
            p = Path(base) / name
            if p.is_file():
                return str(p), "."
    return None


_libmpv = _find_libmpv()
libmpv_binaries = [_libmpv] if _libmpv else []

if not _libmpv:
    print(
        "\n*** WARNING: libmpv not found on this build host. "
        "The built bundle will fail to start. ***\n",
        file=sys.stderr,
    )


# ── Data files ───────────────────────────────────────────────────────────────

datas = [
    # Our app package (Python sources) — PyInstaller also analyzes these
    # statically, but explicitly bundling keeps runtime resource loads (any
    # future .qss / .json that ship inside app/) intact.
    (str(SPEC_DIR / "app"), "app"),
    # Branding / app icon source (used by the generated binary + optional
    # at-runtime logo display)
    (str(SPEC_DIR / "branding"), "branding"),
    # Project files worth shipping next to the exe
    (str(SPEC_DIR / "LICENSE"), "."),
    (str(SPEC_DIR / "README.md"), "."),
]


# ── Hidden imports ───────────────────────────────────────────────────────────

hidden_imports = [
    # PySide6 submodules PyInstaller sometimes misses
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    # python-mpv
    "mpv",
    # Our own package (defensive — should be auto-picked up)
    "app",
    "app.control_window",
    "app.player_window",
    "app.sync_engine",
    "app.session",
    "app.folder_scanner",
    "app.debug_log",
    "app.preferences",
    "app.audio_test",
    "app.select_picker",
    "app.library_panel",
    "app.widgets",
    "app.widgets.clickable_slider",
    "app.library",
    "app.library.catalog",
    "app.library.channels",
    "app.library.scanner",
    "app.library.pins",
]


# ── Platform-specific icon ───────────────────────────────────────────────────

if sys.platform == "win32":
    # .ico preferred; PIL falls back to .png but Windows taskbars prefer .ico.
    _ico = SPEC_DIR / "branding" / "forgeplayer.ico"
    _icon = str(_ico) if _ico.is_file() else str(SPEC_DIR / "branding" / "forgeplayer_icon.png")
elif sys.platform == "darwin":
    _icns = SPEC_DIR / "branding" / "forgeplayer.icns"
    _icon = str(_icns) if _icns.is_file() else None
else:
    _icon = None


# ── Analysis ─────────────────────────────────────────────────────────────────

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[str(SPEC_DIR)],
    binaries=libmpv_binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ForgePlayer doesn't use these; excluding keeps the bundle lean.
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "streamlit",
        "pywebview",
        "matplotlib",
        "scipy",
        "sklearn",
        "tensorflow",
        "torch",
        "pandas",
        "notebook",
        "jupyter",
        "IPython",
        "pytest",
        "sphinx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ForgePlayer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ForgePlayer",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ForgePlayer.app",
        icon=_icon,
        bundle_identifier="com.liquidreleasing.forgeplayer",
    )
