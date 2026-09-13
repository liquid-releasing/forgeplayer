# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for pump_until_video_output_ready — the macOS main-queue deadlock.

mpv's macOS VO creation runs on mpv's `vo` thread and `dispatch_sync`s onto the
MAIN QUEUE to build its NSWindow, while mpv's `core` thread waits on that VO. If
our Qt main thread isn't draining the main queue at that moment, all of it
wedges at ~0% CPU and never recovers. Reproduced on Tahoe 26 by simply keeping
the main thread busy for 0.5s after constructing the player.

Uses a real clock with small timeouts — the function coordinates a worker
thread, so a fake clock would just deadlock the test instead.
"""

from __future__ import annotations

import threading
import time

from app.platform_video import pump_until_video_output_ready


class _FakePlayer:
    """`current_vo` is empty for the first *empty_reads* reads, then set —
    mirroring mpv, which answers immediately but only populates the VO once
    the window has actually been created from its idle loop."""

    def __init__(self, empty_reads: int = 3, never: bool = False):
        self.empty_reads = empty_reads
        self.never = never
        self.reads = 0

    @property
    def current_vo(self):
        self.reads += 1
        if self.never or self.reads <= self.empty_reads:
            return ""
        return "gpu"


class _CountingPump:
    def __init__(self, raises: bool = False):
        self.calls = 0
        self.raises = raises
        self.threads: set[int] = set()

    def __call__(self):
        self.calls += 1
        self.threads.add(threading.get_ident())
        if self.raises:
            raise RuntimeError("pump blew up")


def test_noop_off_darwin():
    """Windows/Linux have no main-queue VO — don't spin the event loop there."""
    pump = _CountingPump()
    p = _FakePlayer(never=True)

    assert pump_until_video_output_ready(
        p, platform="win32", pump=pump, timeout=0.2,
    ) is True
    assert pump.calls == 0
    assert p.reads == 0


def test_pumps_until_the_vo_is_populated():
    """The regression that matters: an earlier version stopped as soon as a
    read SUCCEEDED. mpv answers reads immediately and returns an empty VO long
    before the window exists, so that stopped pumping instantly and deadlocked
    exactly as if the fix were absent. Readiness means populated, not readable.
    """
    pump = _CountingPump()
    p = _FakePlayer(empty_reads=5)

    assert pump_until_video_output_ready(
        p, platform="darwin", pump=pump, timeout=5.0, poll_interval=0.005,
    ) is True
    # Kept pumping across the empty reads rather than returning on the first.
    assert pump.calls > 1
    assert p.reads > 5


def test_pumps_on_the_calling_thread():
    """The pump must run on the caller's thread — it is the GUI thread whose
    main queue needs draining. Pumping from anywhere else drains nothing."""
    pump = _CountingPump()

    pump_until_video_output_ready(
        _FakePlayer(empty_reads=2), platform="darwin", pump=pump,
        timeout=5.0, poll_interval=0.005,
    )

    assert pump.threads == {threading.get_ident()}


def test_returns_false_and_stops_when_the_vo_never_arrives():
    """Bounded. A VO that never appears must not hang the GUI thread forever —
    a launch that gives up beats an app the user has to force-quit."""
    pump = _CountingPump()

    assert pump_until_video_output_ready(
        _FakePlayer(never=True), platform="darwin", pump=pump,
        timeout=0.3, poll_interval=0.005,
    ) is False
    assert pump.calls > 1


def test_a_raising_pump_does_not_propagate():
    """A pump that throws must not turn a slow video start into a crash."""
    pump = _CountingPump(raises=True)

    result = pump_until_video_output_ready(
        _FakePlayer(empty_reads=2), platform="darwin", pump=pump,
        timeout=1.0, poll_interval=0.005,
    )

    assert result is True
    assert pump.calls > 1


def test_a_raising_property_read_gives_up_cleanly():
    """python-mpv raises once the handle dies (a torn-down player). Report not
    ready and return promptly, rather than spinning the GUI thread until the
    full timeout for a player that is never going to answer."""

    class _Dead:
        @property
        def current_vo(self):
            raise RuntimeError("mpv handle is gone")

    pump = _CountingPump()
    started = time.monotonic()

    assert pump_until_video_output_ready(
        _Dead(), platform="darwin", pump=pump, timeout=5.0, poll_interval=0.005,
    ) is False
    # Gave up on the raise, nowhere near the 5s timeout.
    assert time.monotonic() - started < 1.0
