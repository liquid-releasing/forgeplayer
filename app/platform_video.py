# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Platform video quirks for embedding libmpv under Qt.

**macOS** needed three separate fixes before Launch Players worked at all,
and they are grouped here rather than scattered through `sync_engine`
because each works around the SAME underlying conflict: libmpv's macOS
backend wants the **main queue**, and Qt's main thread is sitting on it.

In the order a launch hits them:

1. `apply_platform_video_kwargs` — drop `wid`. `--wid` embedding is an
   X11/win32 feature and deadlocks mpv's constructor on macOS.
2. `pump_until_video_output_ready` — keep the main queue drained while
   mpv's `vo` thread `dispatch_sync`s onto it to build its NSWindow.
3. `register_video_click_bindings` — make the synchronous `on_key_press`
   registrations from a worker thread, never the GUI thread.

Each fixed a real block, and each only revealed the next, which is why the
macOS hang looked for months like one bug that kept "moving".

**Windows** has its own unrelated concern here — steering mpv's D3D11
context onto a non-AMD adapter to dodge a driver teardown crash — which
lives in this module because it is the same kind of decision: per-platform
adjustment of the kwargs an embedded video player is built with.

Every function takes `platform` (and the slower ones their clock and pump)
as parameters, so the module is testable from any host, with no Qt, no mpv
and no real display.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Callable, Optional


def _detect_display_adapter_vendors() -> "frozenset[str]":
    """Best-effort, once-per-process: which GPU vendors this machine reports.

    Returns a subset of {"nvidia", "amd", "intel"}. Empty off Windows, or if
    enumeration fails — callers must treat empty as "don't assume anything".

    Uses EnumDisplayDevicesW (plain ctypes, no extra dependency) rather than
    WMI, which is slow enough to notice at startup. Cached at module scope
    since the adapters present don't change mid-session. Note the same adapter
    is reported once per attached output, so vendors are collected as a set
    rather than counted.
    """
    if sys.platform != "win32":
        return frozenset()
    found: set[str] = set()
    try:
        import ctypes
        from ctypes import wintypes

        class _DisplayDeviceW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128),
                ("DeviceKey", wintypes.WCHAR * 128),
            ]

        i = 0
        while i < 16:  # bounded — a real machine never has this many adapters
            dd = _DisplayDeviceW()
            dd.cb = ctypes.sizeof(_DisplayDeviceW)
            if not ctypes.windll.user32.EnumDisplayDevicesW(
                None, i, ctypes.byref(dd), 0,
            ):
                break
            desc = dd.DeviceString.upper()
            if "NVIDIA" in desc:
                found.add("nvidia")
            if "AMD" in desc or "RADEON" in desc:
                found.add("amd")
            if "INTEL" in desc:
                found.add("intel")
            i += 1
    except Exception:
        pass
    return frozenset(found)


_ADAPTER_VENDORS = _detect_display_adapter_vendors()


def should_pin_nvidia_adapter(vendors: "frozenset[str] | set[str]") -> bool:
    """Whether to force mpv's D3D11 context onto the NVIDIA adapter.

    **Only when an AMD adapter is ALSO present.** That is the entire reason
    this pin exists: mpv's `vo=gpu` teardown hits a confirmed, unfixed access
    violation in AMD's D3D11 driver (mpv-player/mpv#14601 — "a driver bug,
    which we unfortunately are unable to fix" per mpv upstream; also #11882 for
    the matching Windows "dispose then create a new instance" crash). On a
    machine with both, routing to the better-tested NVIDIA adapter sidesteps it
    — verified on the dev machine (AMD Radeon 890M iGPU + NVIDIA RTX 5070 Ti
    dGPU) via mpv's own "Device Name:" D3D11 log line.

    The bug this condition fixes: the check used to be "is any NVIDIA adapter
    present", which fires on **Intel + NVIDIA** machines too — where there is
    no AMD driver to dodge, so the pin is pure downside. Worse, pinning the
    D3D11 device to a discrete NVIDIA GPU that is not driving the display means
    mpv cannot get pixels into a window living on the Intel-driven output. The
    result is a **black video surface with working audio, timeline and
    transport** — mpv is alive and playing, it just presents nothing.

    Confirmed across three machines (2026-09-13):

    | adapters        | old behaviour     | correct |
    |-----------------|-------------------|---------|
    | AMD + NVIDIA    | pin → works       | pin     |
    | Intel only      | no pin → works    | no pin  |
    | Intel + NVIDIA  | pin → BLACK video | no pin  |

    The reporting user's own workaround was to **disable the NVIDIA GPU in
    Device Manager**, which worked precisely because it made the old detection
    return False. Nobody should have to cripple their hardware to play a video.

    Empty `vendors` (enumeration failed, or not Windows) means don't pin: mpv's
    own adapter choice plus its context fallback is a better default than a
    guess made on no information.
    """
    return "nvidia" in vendors and "amd" in vendors


# Kept as a module-level constant for the same reason as before: enumeration
# costs a syscall loop and the answer can't change mid-session.
_HAS_NVIDIA_ADAPTER = should_pin_nvidia_adapter(_ADAPTER_VENDORS)


def apply_d3d11_adapter_kwargs(
    kwargs: dict,
    *,
    platform: str = sys.platform,
    env=None,
    has_nvidia: bool | None = None,
    force_default: bool = False,
) -> str | None:
    """Decide mpv's D3D11 adapter on Windows. Returns the adapter forced, or
    None. Mutates *kwargs*.

    On a hybrid-graphics laptop we steer mpv's D3D11 context onto the NVIDIA
    adapter, because mpv's `vo=gpu` teardown hits a confirmed, unfixed access
    violation in AMD's D3D11 driver (mpv-player/mpv#14601). mpv's own adapter
    selection ignores Windows' per-app GPU-preference registry setting, so
    naming the adapter is the only lever that moves it.

    **The risk this indirection exists to manage.** `_detect_nvidia_adapter()`
    enumerates *display adapters* through `EnumDisplayDevicesW` and returns
    True if any DeviceString contains "NVIDIA" — whether or not that GPU is
    usable, enabled, or driving anything. Setting `gpu_context` explicitly
    ALSO disables mpv's automatic fallback to another context. So if DXGI
    exposes no adapter whose description matches "NVIDIA" (a muxed-off or
    disabled dGPU, or leftover driver registry entries on a machine with no
    NVIDIA card at all), D3D11 context creation fails, `vo=gpu` fails to
    initialise, and mpv carries on playing **audio with no video** — a user
    report we have seen on Windows.

    ``FORGEPLAYER_D3D11_ADAPTER`` overrides the choice without a rebuild:
    a name is forced verbatim; ``auto`` / ``none`` / ``default`` (or an empty
    value) leaves mpv to pick, restoring its context fallback. That is the
    first thing to try on a "sound but no picture" report.
    """
    env = os.environ if env is None else env
    if not platform.startswith("win"):
        return None

    # The user's explicit Setup choice outranks our detection — they are
    # looking at whether a picture appeared, which is better evidence than
    # anything we can enumerate.
    if force_default:
        return None

    override = (env.get("FORGEPLAYER_D3D11_ADAPTER") or "").strip()
    if override:
        if override.lower() in ("auto", "none", "default"):
            # Let mpv choose, and keep its context fallback available.
            return None
        kwargs["gpu_context"] = "d3d11"
        kwargs["d3d11_adapter"] = override
        return override

    if has_nvidia is None:
        has_nvidia = _HAS_NVIDIA_ADAPTER
    if not has_nvidia:
        return None

    kwargs["gpu_context"] = "d3d11"
    kwargs["d3d11_adapter"] = "NVIDIA"
    return "NVIDIA"


def apply_platform_video_kwargs(
    kwargs: dict,
    wid: int,
    *,
    platform: str = sys.platform,
    env=None,
    has_nvidia: bool | None = None,
    force_default_gpu: bool = False,
) -> dict:
    """Platform-adjust an embedded-video player's mpv kwargs. Mutates and
    returns *kwargs*.

    **macOS: `--wid` embedding does not work.** Upstream mpv is explicit that
    window embedding via `--wid` is an X11/win32 feature, not properly
    supported on macOS with GPU rendering; the Cocoa OpenGL backend is
    deprecated in favour of the render API (`vo=libmpv` +
    `mpv_render_context`). The documented failure mode is *audio with a black
    video surface* — exactly the user report this branch exists for: on both
    an M1 and an M3 Max the window opened black and the app deadlocked at
    ~0.4% CPU, never reaching the log line that follows `init_player`.

    The deadlock shape fits. mpv's Cocoa VO needs the **main queue** to touch
    an NSView, while our Qt main thread sits inside a synchronous libmpv call
    — python-mpv reads `mpv_version` (an `mpv_get_property`) at the end of its
    constructor, and we then set `target-colorspace-hint` and register
    `on_key_press` bindings, all blocking. Each side waits on the other, so
    nothing burns CPU.

    **macOS now uses the render API** (`vo=libmpv` + `mpv_render_context`,
    see `app/video_surface.py`): we drop `wid` and set `vo=libmpv`, and Qt's
    `QOpenGLWidget` owns the surface. That removes the Cocoa VO entirely, so
    nothing ever needs the main queue and the deadlock class above is gone —
    rather than dodged one call at a time, which is what the two earlier
    macOS attempts did.

    Both earlier attempts survive as env overrides, because A/B-ing them on a
    real Mac without a rebuild is exactly how this was diagnosed:

    - ``FORGEPLAYER_MACOS_EMBED=wid`` — the ORIGINAL embedding path. Expect a
      hang inside mpv's constructor; it is the control, not a fallback.
    - ``FORGEPLAYER_MACOS_EMBED=window`` — the `force_window` stopgap: mpv
      owns a detached NSWindow. Plays, but hangs on a busy GUI thread and
      costs the Qt control-bar overlay.
    - ``FORGEPLAYER_HWDEC=<value>`` replaces ``hwdec`` on any platform
      (``no`` disables hardware decode, to rule VideoToolbox in or out as a
      secondary suspect).

    Callers tell the two macOS shapes apart by testing
    ``kwargs.get("vo") == "libmpv"``: on that path the player needs a surface
    attached, and must NOT be given the main-queue workarounds, which exist
    only for the Cocoa VO it no longer has.
    """
    env = os.environ if env is None else env
    hwdec_override = (env.get("FORGEPLAYER_HWDEC") or "").strip()
    if hwdec_override:
        kwargs["hwdec"] = hwdec_override

    apply_d3d11_adapter_kwargs(
        kwargs, platform=platform, env=env, has_nvidia=has_nvidia,
        force_default=force_default_gpu,
    )

    if not platform.startswith("darwin"):
        kwargs["wid"] = str(wid)
        return kwargs

    embed = (env.get("FORGEPLAYER_MACOS_EMBED") or "").strip().lower()

    if embed == "wid":
        kwargs["wid"] = str(wid)
        return kwargs

    if embed == "window":
        # Detached window: mpv creates and owns its NSWindow, so it never needs
        # our main thread to hand it an NSView mid-initialization.
        kwargs.pop("wid", None)
        kwargs["force_window"] = "yes"
        return kwargs

    # Render API. mpv renders into a framebuffer our QOpenGLWidget owns, so it
    # creates no window of its own — hence no `wid` and no `force_window`.
    kwargs.pop("wid", None)
    kwargs.pop("force_window", None)
    kwargs["vo"] = "libmpv"
    return kwargs


def _default_main_queue_pump() -> None:
    """Drain pending Qt events, and with them libdispatch's main queue."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def pump_until_video_output_ready(
    player,
    *,
    platform: str = sys.platform,
    pump: Optional[Callable[[], None]] = None,
    timeout: float = 8.0,
    poll_interval: float = 0.005,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """macOS: keep the main queue drained until mpv's video output exists.
    Returns True if the VO came up, False on timeout. No-op off darwin.

    **The deadlock this closes.** mpv's macOS VO creation runs on mpv's own
    `vo` thread and calls `dispatch_sync` onto the **main queue**
    (`mac_vk_init` → `MacCommon.init`) to build its NSWindow. Meanwhile mpv's
    `core` thread sits in `vo_create` → `mp_rendezvous` waiting for that VO,
    holding the core dispatch lock. If our Qt main thread is busy — or parked
    in AppKit's `nextEventMatchingMask`, which does not drain the main queue —
    that `dispatch_sync` never lands. Everything wedges at ~0% CPU, and it
    does **not** recover when the main thread later goes idle: once the window
    is missed it is missed for good (verified by posting events to a hung
    process and re-sampling — the vo thread had not moved).

    Reproduced deterministically 2026-09-13 on Tahoe 26 (Apple Silicon):
    constructing the player and then merely keeping the main thread busy for
    **0.5s** deadlocks it every time; pumping instead plays fine. That timing
    is why earlier probes "passed" — they went idle immediately after
    construction, so the main queue happened to be drained inside mpv's
    window. `_on_launch` does not: it keeps placing windows and starting
    other slots, which is exactly the busy main thread that loses the race.

    **Nothing here may touch mpv from the calling thread.** By the time this
    runs the core can already be wedged, and a property read would block on
    the same dispatch lock and deadlock the GUI thread itself. So the
    blocking read lives on a worker thread, whose completion is the signal we
    wait on; the caller only pumps. The read finishes precisely when the core
    starts servicing requests again, which is to say when the VO is up.

    Note this supersedes nothing above it — `apply_platform_video_kwargs`
    (drop `wid`) and `register_video_click_bindings` (register off the GUI
    thread) each fixed a real, separate block on the way to playback. This is
    the third and, per the sampled stacks, the one that was actually hanging
    Launch Players.

    Parameters are injectable so the tests run from any host with no Qt, no
    mpv and no real clock.
    """
    if platform != "darwin":
        return True

    # Two events, deliberately. `found` means the VO actually came up;
    # `done` only means the worker stopped looking. Collapsing them into one
    # would report success on timeout, since the worker signals either way.
    found = threading.Event()
    done = threading.Event()
    deadline = monotonic() + timeout

    def _probe() -> None:
        # Wait for `current-vo` to actually be POPULATED, not merely for a
        # read to succeed. The distinction is the whole correctness of this
        # function: right after construction the core answers reads
        # immediately and returns an empty VO, because the window is created
        # later, from mpv's idle loop (`handle_force_window`). An earlier
        # version treated "the read returned" as ready, stopped pumping
        # instantly, and deadlocked exactly as if it were not here at all.
        try:
            while monotonic() < deadline:
                try:
                    if player.current_vo:
                        found.set()
                        return
                except Exception:
                    # A dead/torn-down handle raises. Stop rather than spin
                    # the GUI thread until the timeout.
                    return
                sleep(poll_interval)
        finally:
            done.set()

    threading.Thread(target=_probe, name="fp-mpv-vo-probe", daemon=True).start()

    pump = _default_main_queue_pump if pump is None else pump
    while not done.is_set() and monotonic() < deadline:
        try:
            pump()
        except Exception:
            # A pump that raises must not convert a slow video start into a
            # crash; the bounded wait still applies.
            pass
        sleep(poll_interval)
    return found.is_set()


def register_video_click_bindings(
    player,
    on_double_click: Optional[Callable[[], None]],
    on_single_click: Optional[Callable[[], None]],
    *,
    platform: str = sys.platform,
) -> Optional[threading.Thread]:
    """Bind single/double left-click on the video surface. Returns the worker
    thread the registration ran on, or None if it ran inline.

    mpv owns the video's native child window, so a Qt mouse event on the
    PlayerWindow never sees clicks over the video — the bindings have to be
    made at the mpv level. Double-click is the Escape teardown; single-click
    toggles the on-screen control bar (a double-click fires MBTN_LEFT then
    MBTN_LEFT_DBL, and the stray single-toggle is invisible because the
    double-click tears the window down immediately after). Both callbacks run
    on mpv's event thread and only emit a queued Qt signal, so they are safe
    to tear down from.

    **macOS registers on a worker thread, and that is the whole point.**
    `on_key_press` is a synchronous libmpv call (`define-section` +
    `enable_section`). On macOS, mpv's Cocoa VO needs the **main queue** to
    build and service its NSWindow — so making that call from the GUI thread,
    which owns the main queue, deadlocks both sides at ~0% CPU. Measured
    2026-09-13 on Tahoe 26 (Apple Silicon): with the Qt event loop running,
    `init_player` blocked here forever, between the `colorspace_hint_done` and
    `key_bindings_done` DebugLog records. Moving exactly this call off the GUI
    thread let the same launch reach playback — gpu-next + videotoolbox,
    30fps, zero frame drops.

    Note this is the SECOND half of the macOS hang. Dropping `wid`
    (`apply_platform_video_kwargs`) fixed the deadlock inside the mpv
    constructor; it did not fix this one, it just moved the block one call
    later. A probe that skips these two registrations plays video fine.

    Windows and Linux keep registering inline, unchanged — neither has a
    main-queue VO, and a worker thread there would only add a race between
    registration and the first click for no benefit.

    The registration is fire-and-forget: we deliberately do NOT join the
    thread, because waiting on the GUI thread would reintroduce the very
    block this avoids. The bindings only need to exist before the user's
    first click on the video, which is many frames away.

    *platform* is a parameter so the tests run from any host.
    """

    def _register() -> None:
        # python-mpv without on_key_press (older builds) falls back to the
        # Qt-level handlers on the chrome — hence the per-binding guards.
        if on_double_click is not None:
            try:
                player.on_key_press("MBTN_LEFT_DBL")(on_double_click)
            except Exception:
                pass
        if on_single_click is not None:
            try:
                player.on_key_press("MBTN_LEFT")(on_single_click)
            except Exception:
                pass

    if platform == "darwin":
        t = threading.Thread(
            target=_register, name="fp-mpv-keybind", daemon=True,
        )
        t.start()
        return t

    _register()
    return None
