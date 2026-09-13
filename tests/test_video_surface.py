# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the video-surface seam.

macOS renders through `vo=libmpv` + `mpv_render_context`; Windows and Linux
keep `--wid` embedding, which is what preserves D3D11 and HDR passthrough on
Windows. `platform` is a parameter throughout precisely so these decisions are
verified from every CI host, even though only a Mac ever runs the GL.

Nothing here creates a real mpv instance or a real GL context — see the
warning in MACOS_SESSION_HANDOFF.md about real mpv in tests.
"""

from __future__ import annotations

import pytest

from app.video_surface import (
    NativeWindowSurface,
    RenderSurface,
    configure_surface_format,
    create_video_surface,
    uses_render_api,
)


@pytest.mark.parametrize(
    "platform,expected", [("darwin", True), ("win32", False), ("linux", False)],
)
def test_only_macos_uses_the_render_api(platform, expected):
    assert uses_render_api(platform) is expected


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_wid_embedding_off_macos(qapp, platform):
    """Windows/Linux must keep `--wid`. On Windows that is what keeps mpv on
    D3D11, and with it HDR passthrough — the render API has no D3D11 type."""
    surface = create_video_surface(platform=platform)

    assert isinstance(surface, NativeWindowSurface)
    assert surface.widget() is surface
    wid = surface.native_wid()
    assert isinstance(wid, int) and wid != 0


def test_macos_gets_a_render_surface(qapp):
    surface = create_video_surface(platform="darwin")

    assert isinstance(surface, RenderSurface)
    assert surface.widget() is surface


def test_render_surface_reports_no_wid(qapp):
    """Handing mpv a window handle on the render path would put us back on the
    Cocoa VO this class exists to avoid, so it must report None rather than a
    handle that happens to exist."""
    assert create_video_surface(platform="darwin").native_wid() is None


def test_attach_before_gl_is_deferred_not_lost(qapp):
    """`attach()` is called right after init_player, which can be before the
    widget has ever initialised GL. The player must be remembered and bound
    from initializeGL instead of dropped."""
    surface = RenderSurface()
    sentinel = object()

    # No GL context yet, so binding cannot happen now.
    assert surface.attach(sentinel) is False
    assert surface._player is sentinel
    assert surface._pending_player is sentinel


def test_detach_without_a_context_is_safe(qapp):
    """Teardown runs on every close, including for a surface whose render
    context never came up. It must not raise there."""
    surface = RenderSurface()
    surface.attach(object())

    surface.detach()

    assert surface._ctx is None
    assert surface._player is None
    assert surface._pending_player is None


def test_native_surface_attach_detach_are_inert(qapp):
    """The `--wid` path has nothing to bind — mpv got the handle at
    construction. Both calls exist only so PlayerWindow never branches."""
    surface = NativeWindowSurface()

    assert surface.attach(object()) is False
    assert surface.detach() is None


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_surface_format_not_touched_off_macos(platform):
    """Only macOS needs the core-profile request; changing the default format
    on Windows would alter how every Qt GL surface in the app is created."""
    assert configure_surface_format(platform) is False


def test_surface_format_requests_a_core_profile_on_macos():
    """Qt otherwise hands macOS a legacy 2.1 compatibility context, which
    libmpv's GL renderer cannot use at all."""
    from PySide6.QtGui import QSurfaceFormat

    previous = QSurfaceFormat.defaultFormat()
    try:
        assert configure_surface_format("darwin") is True
        fmt = QSurfaceFormat.defaultFormat()
        assert (fmt.majorVersion(), fmt.minorVersion()) >= (3, 3)
        assert fmt.profile() == QSurfaceFormat.OpenGLContextProfile.CoreProfile
    finally:
        QSurfaceFormat.setDefaultFormat(previous)
