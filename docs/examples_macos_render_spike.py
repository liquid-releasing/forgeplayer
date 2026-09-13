"""Spike: vo=libmpv + mpv_render_context in a QOpenGLWidget on macOS.

Premise under test -- the ENTIRE justification for option B:
  With vo=libmpv there is no Cocoa VO doing dispatch_sync onto the main
  queue, so blocking libmpv calls from the GUI thread (time_pos polling,
  property sets) stop being deadlock bait.

So this doesn't just render a video. It runs the exact stress that wedges
the shipped app:
  * a QTimer on the GUI thread reading time_pos every 16ms, and
  * a burst of main-thread busy work right after construction,
which together reproduce the current three-way deadlock 100% of the time.

STRESS=0 disables the stress for an A/B.
"""
import os
import sys
import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QOpenGLContext, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication

# libmpv's GL renderer needs a modern context. Qt on macOS gives a legacy
# 2.1 context unless a core profile is requested BEFORE the QApplication.
fmt = QSurfaceFormat()
fmt.setVersion(3, 3)
fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
fmt.setDefaultFormat(fmt)
QSurfaceFormat.setDefaultFormat(fmt)

app = QApplication(sys.argv)

from app.locale_guard import force_c_numeric_locale  # noqa: E402

force_c_numeric_locale()

import mpv  # noqa: E402

MEDIA = os.path.expanduser(
    "~/Movies/ForgePlayer Test Library/Timecode Test 01/Timecode Test 01.mp4"
)
STRESS = os.environ.get("STRESS", "1") == "1"


def _get_proc_address(_ctx, name):
    glctx = QOpenGLContext.currentContext()
    if glctx is None:
        return 0
    if isinstance(name, bytes):
        name = name.decode("utf-8")
    return int(glctx.getProcAddress(name))


class Bridge(QObject):
    """mpv's update_cb fires on mpv's render thread; hop to the GUI thread."""
    wakeup = Signal()


class VideoWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.ctx = None
        self.player = None
        self.bridge = Bridge()
        self.bridge.wakeup.connect(self.maybe_update, Qt.QueuedConnection)
        self.frames = 0

    def initializeGL(self):
        print("BREADCRUMB initializeGL", flush=True)
        self.player = mpv.MPV(
            vo="libmpv",              # <-- the whole point
            keep_open=True,
            hwdec="auto-safe",
            hr_seek="yes",
            osc=False,
            input_default_bindings=False,
            input_vo_keyboard=False,
        )
        print("BREADCRUMB mpv_constructed", flush=True)
        import traceback
        try:
            glctx = QOpenGLContext.currentContext()
            print(f"  GL current={glctx is not None} fmt={glctx.format().version() if glctx else None} "
                  f"profile={glctx.format().profile() if glctx else None}", flush=True)
            probe = _get_proc_address(None, b"glGetString")
            print(f"  getProcAddress(glGetString) -> {probe}", flush=True)
            # Must be a ctypes CFUNCTYPE, not a bare Python function, and
            # must be kept alive for the life of the context or it is GC'd
            # out from under libmpv.
            self._proc_fn = mpv.MpvGlGetProcAddressFn(_get_proc_address)
            self.ctx = mpv.MpvRenderContext(
                self.player,
                api_type="opengl",
                opengl_init_params={"get_proc_address": self._proc_fn},
            )
        except Exception:
            print("RENDER CONTEXT FAILED:", flush=True)
            traceback.print_exc()
            self.ctx = None
            return
        print("BREADCRUMB render_context_created", flush=True)
        self.ctx.update_cb = self.bridge.wakeup.emit
        QTimer.singleShot(0, self.start_playback)

    def start_playback(self):
        if STRESS:
            # The main-thread burst that reproduces the shipped deadlock.
            print("BREADCRUMB stress_busy_begin", flush=True)
            end = time.monotonic() + 2.0
            while time.monotonic() < end:
                pass
            print("BREADCRUMB stress_busy_end", flush=True)
        print("BREADCRUMB play_begin", flush=True)
        self.player.play(MEDIA)
        self.player.pause = False
        print("BREADCRUMB play_returned", flush=True)

    def maybe_update(self):
        if self.ctx is not None and self.ctx.update():
            self.update()

    def paintGL(self):
        if self.ctx is None:
            return
        ratio = self.devicePixelRatioF()
        w, h = int(self.width() * ratio), int(self.height() * ratio)
        self.ctx.render(
            flip_y=True,
            opengl_fbo={"w": w, "h": h, "fbo": self.defaultFramebufferObject()},
        )
        self.frames += 1


w = VideoWidget()
w.resize(960, 540)
w.setWindowTitle("spike: vo=libmpv render API")
w.show()

state = {"samples": [], "polls": 0}


def poll():
    """The GUI-thread property read that currently deadlocks the app."""
    state["polls"] += 1
    try:
        state["samples"].append(w.player.time_pos if w.player else None)
    except Exception as e:
        print(f"  poll error: {e}", flush=True)
    if state["polls"] < 220:
        QTimer.singleShot(16, poll)   # ~60Hz, like _poll
    else:
        finish()


def finish():
    s = [x for x in state["samples"] if x is not None]
    print(f"  polls={state['polls']} frames_painted={w.frames}", flush=True)
    print(f"  first/last time_pos: {s[:1]} .. {s[-1:]}", flush=True)
    advanced = len(s) >= 2 and s[-1] > s[0] + 1.0
    print(f"RESULT playback_advanced={advanced}", flush=True)
    print(f"RESULT frames_rendered={w.frames > 10}", flush=True)
    try:
        print(f"  vo={w.player.current_vo} hwdec={w.player.hwdec_current}", flush=True)
    except Exception:
        pass

    # mpv_render_context_free tears down GL objects (glDeleteFramebuffers),
    # so it MUST run on the thread holding the GL context, with that context
    # CURRENT. Freeing it from a worker thread segfaults -- verified, see
    # Python-2026-09-13-143034.ips.
    print("BREADCRUMB free_ctx_begin", flush=True)
    w.makeCurrent()
    try:
        w.ctx.free()
        w.ctx = None
    finally:
        w.doneCurrent()
    print("BREADCRUMB free_ctx_done", flush=True)

    # terminate() is safe off the GUI thread and stays there.
    def teardown():
        try:
            w.player.terminate()
        except Exception as e:
            print(f"  terminate raised: {e}", flush=True)
        print("BREADCRUMB teardown_done", flush=True)

    threading.Thread(target=teardown, daemon=True).start()
    QTimer.singleShot(2000, lambda: (print("PROBE COMPLETE", flush=True), app.quit()))


QTimer.singleShot(2500, poll)
sys.exit(app.exec())
