# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""The video surface mpv draws into — one seam, two implementations.

**Windows and Linux** keep the long-standing approach: a plain native QWidget
whose window handle is handed to mpv as `--wid`, and mpv draws into it
directly with `vo=gpu`. That path keeps **D3D11 on Windows**, and with it HDR
passthrough (`target-colorspace-hint`, `hdr_compute_peak`, tone mapping),
which is the reason it is not being replaced. libmpv's render API offers only
`MPV_RENDER_API_TYPE_OPENGL` and `..._SW` — there is no D3D11 render type —
so "unifying" the two paths would mean moving Windows onto OpenGL and losing
HDR passthrough along the way.

**macOS** uses libmpv's render API instead: `vo=libmpv` plus an
`mpv_render_context` bound to a `QOpenGLWidget`'s GL context, so *Qt* owns
the surface and mpv just renders into a framebuffer we give it.

Why macOS had to be different: libmpv's macOS backend creates and resizes its
NSWindow on mpv's own `vo` thread, using `dispatch_sync` onto the **main
queue** — which Qt's main thread owns. Any moment the GUI thread is busy, or
is itself inside a blocking libmpv call, `vo` waits on the GUI thread, `core`
waits on `vo`, and all of it wedges at ~0% CPU and never recovers. Three
earlier fixes in `platform_video.py` each removed one instance of that
collision and each only revealed the next. With `vo=libmpv` there is no Cocoa
VO at all, so nothing ever needs the main queue and the whole class is gone —
measured, see `docs/macos_render_api.md`.

It also gives macOS back the Qt control-bar overlay, which the previous
`force_window` stopgap had cost: Qt owns the surface, so clicks over the
video are ordinary Qt mouse events rather than mpv key bindings.

Both classes present the same small interface, so `PlayerWindow` holds one
reference and never branches on platform:

    widget()        the QWidget to put in the layout
    native_wid()    the `--wid` handle, or None when rendering
    attach(player)  bind a constructed mpv instance (render path only)
    detach()        release it, in the order that doesn't crash

`platform` is a parameter throughout so Windows and Linux CI exercise this
module's decisions even though they never run its GL.
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from app.debug_log import DebugLog


# libmpv's GL renderer needs a modern core context. 3.3 is the floor we ask
# for; macOS grants 4.1, which is the newest Apple offers.
_GL_MAJOR, _GL_MINOR = 3, 3


def uses_render_api(platform: str = sys.platform) -> bool:
    """True where mpv renders through `mpv_render_context` rather than `--wid`."""
    return platform == "darwin"


def configure_surface_format(platform: str = sys.platform) -> bool:
    """Ask Qt for a GL core profile. Returns True if a format was installed.

    **Must be called before `QApplication` is constructed** — Qt reads the
    default format when it creates its first context, and on macOS otherwise
    hands out a legacy 2.1 compatibility context that libmpv's GL renderer
    cannot use at all. Calling it afterwards silently does nothing, which is
    the kind of failure that costs an afternoon.
    """
    if not uses_render_api(platform):
        return False
    from PySide6.QtGui import QSurfaceFormat

    fmt = QSurfaceFormat()
    fmt.setVersion(_GL_MAJOR, _GL_MINOR)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    # mpv draws a full-frame quad; we need no depth or stencil, and asking
    # for them only constrains which pixel formats can satisfy the request.
    fmt.setDepthBufferSize(0)
    fmt.setStencilBufferSize(0)
    QSurfaceFormat.setDefaultFormat(fmt)
    return True


class NativeWindowSurface(QWidget):
    """`--wid` embedding: mpv draws straight into this widget's native window.

    Windows and Linux. Nothing to attach or detach — mpv is given the handle
    at construction and owns the drawing from there.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setStyleSheet("background-color: black;")

    def widget(self) -> QWidget:
        return self

    def native_wid(self) -> Optional[int]:
        """Native handle for the video area (only valid after show())."""
        return int(self.winId())

    def attach(self, player) -> bool:
        return False

    def detach(self) -> None:
        return None


class _RenderBridge(QObject):
    """mpv's update callback fires on mpv's render thread. Touching a widget
    from there is a data race, so it only emits this signal, queued onto the
    GUI thread."""

    wakeup = Signal()


class RenderSurface(QOpenGLWidget):
    """Render-API surface: mpv renders into *our* GL framebuffer.

    macOS. The mpv instance must be constructed with `vo=libmpv` and then
    handed here via `attach()`; the render context cannot exist before the
    widget has a GL context, which is why this is two steps rather than one.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._player = None
        self._ctx = None
        self._gl_ready = False
        self._pending_player = None
        # The get_proc_address callback must outlive the render context —
        # see _create_context. Held here, not as a local.
        self._proc_address_fn = None
        self._bridge = _RenderBridge()
        self._bridge.wakeup.connect(self._on_mpv_update, Qt.ConnectionType.QueuedConnection)

    # ── surface interface ────────────────────────────────────────────────────

    def widget(self) -> QWidget:
        return self

    def native_wid(self) -> Optional[int]:
        """None — mpv must NOT be given a window handle on this path. Passing
        one would put us back on the Cocoa VO this class exists to avoid."""
        return None

    def attach(self, player) -> bool:
        """Bind *player* (constructed with `vo=libmpv`) to this surface.

        Safe to call before the widget has initialised GL: the player is held
        and bound from `initializeGL` instead.
        """
        self._player = player
        if not self._gl_ready:
            self._pending_player = player
            return False
        return self._create_context()

    def detach(self) -> None:
        """Free the render context — on the GL thread, with the context CURRENT.

        `mpv_render_context_free` tears down GL objects (`glDeleteFramebuffers`
        and friends). Calling it from a worker thread, or without making the
        context current, segfaults inside libmpv's own uninit path. That is not
        hypothetical: it was captured during the spike as
        `mpv_render_context_free → gl_video_uninit → glDeleteFramebuffers →
        SIGSEGV`.

        Terminating the *player* is a separate concern and stays off the GUI
        thread, in SyncEngine's existing async teardown.
        """
        if self._ctx is None:
            self._player = None
            self._pending_player = None
            return
        ctx, self._ctx = self._ctx, None
        try:
            self.makeCurrent()
            try:
                ctx.free()
            finally:
                self.doneCurrent()
            DebugLog.record("surface.render_context_freed")
        except Exception as exc:  # pragma: no cover - GL teardown is host-specific
            DebugLog.record("surface.render_context_free_failed", error=repr(exc))
        self._player = None
        self._pending_player = None

    # ── GL lifecycle ─────────────────────────────────────────────────────────

    def initializeGL(self) -> None:  # noqa: N802 - Qt override
        self._gl_ready = True
        if self._pending_player is not None:
            self._pending_player = None
            self._create_context()

    def _create_context(self) -> bool:
        import mpv

        if self._player is None or self._ctx is not None:
            return False
        try:
            # Must be a ctypes CFUNCTYPE, not a bare Python function —
            # python-mpv rejects the latter outright ("expected CFunctionType
            # instance") — and must be kept alive for the life of the context,
            # or libmpv ends up calling collected memory.
            self._proc_address_fn = mpv.MpvGlGetProcAddressFn(_get_proc_address)
            self._ctx = mpv.MpvRenderContext(
                self._player,
                api_type="opengl",
                opengl_init_params={"get_proc_address": self._proc_address_fn},
            )
            self._ctx.update_cb = self._bridge.wakeup.emit
            DebugLog.record("surface.render_context_created")
            return True
        except Exception as exc:
            # A player with no surface shows black rather than taking the app
            # down; the record is what tells us which it was.
            self._ctx = None
            self._proc_address_fn = None
            DebugLog.record("surface.render_context_failed", error=repr(exc))
            return False

    def _on_mpv_update(self) -> None:
        if self._ctx is not None and self._ctx.update():
            self.update()

    def paintGL(self) -> None:  # noqa: N802 - Qt override
        if self._ctx is None:
            return
        ratio = self.devicePixelRatioF()
        self._ctx.render(
            # Qt's framebuffer origin is top-left, mpv's is bottom-left.
            flip_y=True,
            opengl_fbo={
                "w": int(self.width() * ratio),
                "h": int(self.height() * ratio),
                "fbo": self.defaultFramebufferObject(),
            },
        )


def _get_proc_address(_ctx, name):
    """Resolve a GL symbol for libmpv against Qt's current context."""
    from PySide6.QtGui import QOpenGLContext

    glctx = QOpenGLContext.currentContext()
    if glctx is None:
        return 0
    if isinstance(name, bytes):
        name = name.decode("utf-8")
    return int(glctx.getProcAddress(name))


def create_video_surface(
    parent: Optional[QWidget] = None, *, platform: str = sys.platform,
):
    """The video surface for this platform. See the module docstring."""
    if uses_render_api(platform):
        return RenderSurface(parent)
    return NativeWindowSurface(parent)
