# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Making the frozen macOS app use the libmpv it already ships with.

The .app bundles libmpv and all its dependencies, but python-mpv's POSIX
loader is `ctypes.util.find_library('mpv')`, which searches the system and
finds Homebrew's copy — confirmed with `lsof` against a live process. So
macOS users had to `brew install mpv` despite downloading an app that already
contained it.

On macOS `find_library` is CPython's own `ctypes.macholib.dyld`, which reads
`DYLD_LIBRARY_PATH` from `os.environ` at CALL time — unlike the real dyld,
which snapshots its environment at process start. That is what makes this
fixable from inside the process.

Everything here is injected, so the behaviour is verified from Windows and
Linux CI too, with no bundle and no dylib on disk.
"""

from __future__ import annotations

import os

import pytest

from app.bundled_libmpv import prefer_bundled_libmpv


def _isfile_for(*present: str):
    """An `isfile` that reports exactly *present* as existing."""
    wanted = {os.path.normpath(p) for p in present}

    def isfile(path: str) -> bool:
        return os.path.normpath(path) in wanted

    return isfile


def test_points_dyld_at_the_bundle_when_frozen_on_macos():
    env: dict = {}

    got = prefer_bundled_libmpv(
        platform="darwin", meipass="/App.app/Contents/Frameworks", environ=env,
        isfile=_isfile_for("/App.app/Contents/Frameworks/libmpv.2.dylib"),
    )

    assert got == "/App.app/Contents/Frameworks"
    assert env["DYLD_LIBRARY_PATH"] == "/App.app/Contents/Frameworks"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_noop_off_macos(platform):
    """Windows loads its DLL by a different route and Linux users install
    libmpv from their distro; neither wants its loader steered."""
    env: dict = {}

    assert prefer_bundled_libmpv(
        platform=platform, meipass="/App/Contents/Frameworks", environ=env,
        isfile=lambda p: True,
    ) is None
    assert env == {}


def test_noop_when_not_frozen():
    """Running from source there is nothing bundled to prefer, so the system
    libmpv stays correct — and it is what the dev docs tell you to install."""
    env: dict = {}

    assert prefer_bundled_libmpv(
        platform="darwin", meipass=None, environ=env, isfile=lambda p: True,
    ) is None
    assert env == {}


def test_noop_when_no_dylib_is_bundled():
    """A build that failed to collect libmpv must not point DYLD at a
    directory without one — that would break the Homebrew fallback that is
    currently the only thing making the app work at all."""
    env: dict = {}

    assert prefer_bundled_libmpv(
        platform="darwin", meipass="/App/Contents/Frameworks", environ=env,
        isfile=lambda p: False,
    ) is None
    assert "DYLD_LIBRARY_PATH" not in env


def test_finds_the_dylib_in_a_sibling_layout():
    """PyInstaller has moved the collected-binaries directory between
    versions, so the bundle dir is probed rather than assumed."""
    env: dict = {}

    got = prefer_bundled_libmpv(
        platform="darwin", meipass="/App.app/Contents/MacOS", environ=env,
        isfile=_isfile_for("/App.app/Contents/Frameworks/libmpv.2.dylib"),
    )

    assert got == "/App.app/Contents/Frameworks"


def test_existing_dyld_path_is_kept_after_ours():
    """A developer pointing at a custom libmpv build keeps it searched — just
    second, so the bundled one still wins by default."""
    env = {"DYLD_LIBRARY_PATH": "/my/custom/libs"}

    prefer_bundled_libmpv(
        platform="darwin", meipass="/App.app/Contents/Frameworks", environ=env,
        isfile=_isfile_for("/App.app/Contents/Frameworks/libmpv.dylib"),
    )

    assert env["DYLD_LIBRARY_PATH"] == (
        f"/App.app/Contents/Frameworks{os.pathsep}/my/custom/libs"
    )
