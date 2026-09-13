# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Make the frozen app load the libmpv it ships with.

**The problem.** `ForgePlayer.spec` bundles `libmpv.2.dylib` and every
dependency it needs — ffmpeg, libass, libplacebo — into the .app. None of it
was ever used. python-mpv's POSIX loader is::

    sofile = ctypes.util.find_library('mpv')
    backend = CDLL(sofile)

`find_library` searches the system, finds Homebrew's copy at
`/opt/homebrew/lib`, and loads that. Confirmed against a live process with
`lsof`, which showed `/opt/homebrew/Cellar/mpv/…/libmpv.2.dylib` loaded while
an identical dylib sat unused inside the bundle. So macOS users had to
`brew install mpv` despite downloading an app that already contained it —
"install Homebrew, then run a terminal command" being a hard stop for anyone
who isn't a developer, and the difference between a download that works and
one that appears broken.

**The fix.** On macOS, CPython's `ctypes.util.find_library` is not dyld — it
is `ctypes.macholib.dyld`, pure Python, and it reads `DYLD_LIBRARY_PATH` from
``os.environ`` **at call time**. That matters: the real dyld snapshots its
environment at process start and ignores later changes, so the usual "you
can't set DYLD_* from inside the process" rule does not apply to this lookup.
Pointing it at the bundle before python-mpv is imported is therefore enough,
with no patching of python-mpv and no launcher script.

The bundled dylib's install name is `@rpath/libmpv.2.dylib` with an
`LC_RPATH` of `@loader_path`, so once it is the one chosen its dependencies
resolve to their bundled copies too, and the app stops touching Homebrew
entirely.

**Ordering.** This must run before anything imports `mpv` — python-mpv opens
the library at import time, and the first import wins for the life of the
process. In practice that means before `app.control_window` is imported, since
that pulls in `app.sync_engine` and therefore `mpv`.

Only applies to the frozen bundle. Running from source there is nothing to
prefer, so the system libmpv stays correct (and remains what the developer
docs tell you to install).
"""

from __future__ import annotations

import os
import sys

_DYLIB_NAMES = ("libmpv.2.dylib", "libmpv.dylib")


def _bundle_dirs(meipass: str) -> list[str]:
    """Where PyInstaller may have put the dylib, best guess first.

    In a macOS .app the collected binaries land in `Contents/Frameworks`,
    which is what `sys._MEIPASS` points at for a onedir bundle — but the
    layout has moved between PyInstaller versions, and `Contents/Resources`
    carries copies too, so probe rather than assume.
    """
    return [
        meipass,
        os.path.join(meipass, "..", "Frameworks"),
        os.path.join(meipass, "..", "Resources"),
    ]


def prefer_bundled_libmpv(
    *,
    platform: str = sys.platform,
    meipass: str | None = None,
    environ: dict | None = None,
    isfile=os.path.isfile,
) -> str | None:
    """Point `ctypes.util.find_library` at the bundled libmpv.

    Returns the directory prepended to ``DYLD_LIBRARY_PATH``, or None when
    there is nothing to do (not macOS, not frozen, or no bundled dylib found).

    An existing ``DYLD_LIBRARY_PATH`` is preserved after ours rather than
    replaced, so a developer deliberately pointing at a custom libmpv build
    still has it searched — just second.
    """
    if platform != "darwin":
        return None
    if meipass is None:
        meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None  # running from source
    env = os.environ if environ is None else environ

    for raw in _bundle_dirs(meipass):
        directory = os.path.normpath(raw)
        if not any(isfile(os.path.join(directory, n)) for n in _DYLIB_NAMES):
            continue
        existing = env.get("DYLD_LIBRARY_PATH", "")
        env["DYLD_LIBRARY_PATH"] = (
            f"{directory}{os.pathsep}{existing}" if existing else directory
        )
        return directory
    return None
