# macOS video: moving to the libmpv render API

Status: **spike validated 2026-09-13, integration not started.**

This is the design note for replacing the macOS video path with
`vo=libmpv` + `mpv_render_context`. It exists because the spike that proved
the approach cost several wrong turns, and none of that is obvious from the
resulting code.

## Why, in one paragraph

libmpv's macOS backend builds and resizes its NSWindow on mpv's own `vo`
thread, and does it with `dispatch_sync` onto the **main queue**. Qt's main
thread owns that queue. So any moment the GUI thread is busy — or is itself
inside a blocking libmpv call — mpv's `vo` thread waits on the GUI thread,
mpv's `core` thread waits on `vo`, and everything wedges at ~0% CPU and
never recovers. Three separate fixes (drop `wid`, register key bindings off
the GUI thread, pump the main queue during VO creation) each removed one
instance of that collision and each only revealed the next. They are all
still in `app/platform_video.py` and all still necessary for the current
path, but they treat instances of a class. `vo=libmpv` removes the class:
there is no Cocoa VO, so nothing ever needs the main queue, and ordinary
GUI-thread property reads become safe again.

## What the spike measured

Same harness, the one that deadlocks the shipped build 100% of the time:
2s of main-thread burn right after construction, plus 220 GUI-thread
`time_pos` reads at 60Hz.

| | shipped (`force_window`) | `vo=libmpv` spike |
| --- | --- | --- |
| GUI-thread `time_pos` polls | deadlocks | 220/220 completed |
| frames rendered | 0 | 198–285 across runs |
| playback advanced | no | yes |
| hwdec | — | videotoolbox |
| teardown | — | clean, no crash report |

Qt hands out a **4.1 Core** context on this hardware, comfortably above
libmpv's requirement.

## Three rules the spike paid for

1. **Request the GL core profile before `QApplication` is constructed.**
   `QSurfaceFormat.setDefaultFormat(...)` with 3.3+ core. Qt otherwise gives
   a legacy 2.1 context on macOS and libmpv's GL renderer cannot use it.

2. **`get_proc_address` must be a ctypes `CFUNCTYPE`, not a bare Python
   function**, and must be **kept alive** for the life of the context.
   Passing a plain function fails at creation with
   `expected CFunctionType instance, got function`; letting it be collected
   leaves libmpv calling freed memory. Wrap it in `mpv.MpvGlGetProcAddressFn`
   and store it on the widget.

3. **`mpv_render_context_free` must run on the GL thread with the context
   CURRENT.** It tears down GL objects (`glDeleteFramebuffers`), so freeing
   it from a worker thread segfaults — captured as
   `Python-2026-09-13-143034.ips`:
   `mpv_render_context_free → gl_video_uninit → glDeleteFramebuffers → SIGSEGV`.
   Free it inside `makeCurrent()` / `doneCurrent()` on the GUI thread.
   `player.terminate()` is separate and stays off the GUI thread.

`update_cb` fires on mpv's render thread and must hop to the GUI thread
before touching any widget — a queued Qt signal is the cheap way.

## Integration plan

**macOS only. Windows and Linux stay on `wid`.** They work today and `wid`
embedding is well-trodden there; two render paths is a real maintenance
cost, but far cheaper than destabilising the platform that currently ships.
The split belongs behind one seam, not sprinkled through `PlayerWindow`.

1. `app/video_surface.py` — a `QOpenGLWidget` owning the render context,
   with the three rules above encoded and commented. Exposes create /
   render / free and nothing else.
2. `PlayerWindow` gains a video-surface seam: on darwin it embeds the
   widget; elsewhere it keeps handing `native_wid()` to `init_player`.
3. `SyncEngine.init_player` learns a render-context mode that sets
   `vo=libmpv` and skips the `wid` path.
4. Teardown ordering: free the render context on the GUI thread first, then
   the existing off-thread `terminate_player_async` dance.

## What this buys back

The `force_window` stopgap cost macOS the Qt chrome overlay — the control
bar — because mpv owned a detached window. With the render API **Qt owns
the surface**, so the overlay returns and clicks can be handled as ordinary
Qt mouse events. That retires `register_video_click_bindings` on the render
path (keep it for Windows/Linux, which still use `wid`).

## Correction to MACOS_SESSION_HANDOFF.md

That doc tells the next session **not** to chase Vulkan/MoltenVK, calling it
the wrong layer. The sampled stack from the real hang goes straight through
`mac_vk_init`, so the original reporter's instinct about the layer was
closer than that note allows. The doc's own closing suggestion — that the
render API is the real fix — is the part that held up.
