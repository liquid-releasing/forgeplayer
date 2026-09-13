# macOS video: moving to the libmpv render API

Status: **shipped 2026-09-13.** Integrated, and verified playing on Mac Neo
(Tahoe 26, Apple Silicon) — video in-window, timeline scrubbing working from
both the scene window and the control panel. This file is now the reference
for *why* the macOS path looks the way it does; `ARCHITECTURE.md` → "The video
surface" is the shorter overview.

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
still in `app/platform_video.py`, now gated to the legacy `wid`/`force_window`
paths, but they treat instances of a class. `vo=libmpv` removes the class:
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

## How it was integrated

**macOS only. Windows and Linux stay on `wid`.** They work today and `wid`
embedding is well-trodden there; two render paths is a real maintenance
cost, but far cheaper than destabilising the platform that currently ships.
The split belongs behind one seam, not sprinkled through `PlayerWindow`.

1. `app/video_surface.py` — one interface (`widget` / `native_wid` /
   `attach` / `detach`), two implementations: `NativeWindowSurface` for
   `--wid`, `RenderSurface` for the render API, with the three rules above
   encoded and commented.
2. `PlayerWindow` holds a surface instead of a bare widget and never
   branches on platform; `attach_player` / `detach_player` are the seam.
3. `apply_platform_video_kwargs` sets `vo=libmpv` on darwin and drops both
   `wid` and `force_window`. Callers detect the path with
   `kwargs.get("vo") == "libmpv"`.
4. Teardown: `detach_player()` on the GUI thread first, while the player is
   still alive, then the existing off-thread `terminate_player_async`.
5. The two Cocoa-VO workarounds in `platform_video.py` are gated off the
   render path, including the mpv click bindings — Qt owns the surface now,
   so PlayerWindow's own mouse handlers cover the video.

Both earlier attempts remain reachable for A/B without a rebuild:
`FORGEPLAYER_MACOS_EMBED=wid` (original) and `=window` (the `force_window`
stopgap). They are controls, not fallbacks — both still hang.

## What this buys back

The `force_window` stopgap cost macOS the Qt chrome overlay — the control
bar — because mpv owned a detached window. With the render API **Qt owns
the surface**, so the overlay returns and clicks can be handled as ordinary
Qt mouse events. That retires `register_video_click_bindings` on the render
path (keep it for Windows/Linux, which still use `wid`).

## Two things the old handoff note got wrong

`MACOS_SESSION_HANDOFF.md` was deleted with this change, as it asked to be
once macOS playback was settled. Two of its conclusions are worth preserving
as corrections, because both cost time:

- It told the next session **not** to chase Vulkan/MoltenVK, calling it the
  wrong layer. The sampled stack from the real hang goes straight through
  `mac_vk_init`. The original reporter's instinct about the layer was closer
  than that note allowed.
- It presented the `force_window` stopgap as very likely the fix, pending
  verification. It was not — it moved the deadlock rather than removing it.
  Its closing suggestion, that the render API is the real fix, is the part
  that held up.

The general lesson, which is the one worth carrying: on macOS this failure
mode **moves** under partial fixes instead of disappearing, so "it got
further this time" is not evidence of progress toward a fix. Sample the hung
process and read the actual stacks.
