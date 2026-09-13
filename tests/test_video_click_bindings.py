# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for register_video_click_bindings — the macOS GUI-thread deadlock.

`on_key_press` is a synchronous libmpv call, and on macOS mpv's Cocoa VO needs
the main queue to service its NSWindow. Making that call from the GUI thread
(which owns the main queue) deadlocks both sides at ~0% CPU — measured on Tahoe
26, between the `colorspace_hint_done` and `key_bindings_done` records. So
darwin registers on a worker thread and every other platform stays inline.

`platform` is a parameter on the helper, so all of this runs from Windows or
Linux CI as well as from a Mac.
"""

from __future__ import annotations

import threading

import pytest

from app.platform_video import register_video_click_bindings


class _FakePlayer:
    """Records key registrations, and which thread each was made from."""

    def __init__(self, raises: bool = False):
        self.raises = raises
        self.bindings: dict[str, object] = {}
        self.threads: list[int] = []

    def on_key_press(self, key):
        def decorator(fn):
            self.threads.append(threading.get_ident())
            if self.raises:
                raise AttributeError("python-mpv without on_key_press")
            self.bindings[key] = fn
            return fn

        return decorator


def _dbl():
    pass


def _single():
    pass


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_registers_inline_off_darwin(platform):
    """Windows/Linux have no main-queue VO — keep the direct call, and with it
    the guarantee that bindings exist the moment init_player returns."""
    p = _FakePlayer()

    thread = register_video_click_bindings(p, _dbl, _single, platform=platform)

    assert thread is None
    assert set(p.bindings) == {"MBTN_LEFT_DBL", "MBTN_LEFT"}
    # Registered on the calling thread, not handed off.
    assert p.threads == [threading.get_ident(), threading.get_ident()]


def test_darwin_registers_off_the_calling_thread():
    """The fix itself: on darwin the blocking call must not run on the caller's
    (GUI) thread, or libmpv and the main queue deadlock."""
    p = _FakePlayer()

    thread = register_video_click_bindings(p, _dbl, _single, platform="darwin")

    assert thread is not None
    thread.join(timeout=5)
    assert not thread.is_alive(), "registration thread did not finish"
    assert set(p.bindings) == {"MBTN_LEFT_DBL", "MBTN_LEFT"}
    assert p.threads, "no registration was attempted"
    assert all(t != threading.get_ident() for t in p.threads)


def test_darwin_does_not_block_the_caller():
    """Fire-and-forget: we must not join the worker, since waiting on the GUI
    thread would reintroduce exactly the block this avoids."""
    started = threading.Event()
    release = threading.Event()

    class _BlockingPlayer(_FakePlayer):
        def on_key_press(self, key):
            def decorator(fn):
                started.set()
                release.wait(timeout=5)  # hold the worker open
                self.bindings[key] = fn
                return fn

            return decorator

    p = _BlockingPlayer()
    thread = register_video_click_bindings(p, _dbl, _single, platform="darwin")

    # The caller returned while the registration is still in progress.
    assert started.wait(timeout=5)
    assert p.bindings == {}
    release.set()
    thread.join(timeout=5)
    assert set(p.bindings) == {"MBTN_LEFT_DBL", "MBTN_LEFT"}


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_missing_on_key_press_is_survivable(platform):
    """python-mpv without on_key_press falls back to the Qt-level chrome
    handlers rather than taking the player down."""
    p = _FakePlayer(raises=True)

    thread = register_video_click_bindings(p, _dbl, _single, platform=platform)
    if thread is not None:
        thread.join(timeout=5)

    assert p.bindings == {}


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_none_callbacks_register_nothing(platform):
    """Audio-only / headless callers pass no handlers; binding anything then
    would hand mpv a dead callback."""
    p = _FakePlayer()

    thread = register_video_click_bindings(p, None, None, platform=platform)
    if thread is not None:
        thread.join(timeout=5)

    assert p.bindings == {}
    assert p.threads == []
