# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Which screen (if any) a slot's player window belongs on.

Guards a Windows report: **two player windows opened on a single-monitor
machine**, stacked on top of each other. The cause was the launch loop
treating two different answers from `_screen_index_for_slot` as the same
thing:

    None                     -> no screen belongs to this slot at all
    index >= len(screens)    -> this slot has a screen, but the index is stale

Both were being clamped to screen 0. Clamping is right for the second (a
monitor was unplugged, so use the primary) and always wrong for the first:
on one monitor it stacks a second window on the real player; on several it
lands on the wrong one.

`_screen_index_for_slot` reads only `_prefs.playback_screen_indices` and
`_screens`, so it is exercised here bound to a stub — no Qt, no real
monitors, and runnable from any CI host.
"""

from __future__ import annotations

import types

from app.control_window import ControlWindow, _NUM_SLOTS, _SLOT_ROLES


class _Stub:
    """Carries only the two attributes _screen_index_for_slot reads."""

    def __init__(self, n_screens: int, playback: list[int]):
        self._prefs = types.SimpleNamespace(playback_screen_indices=list(playback))
        self._screens = [f"screen{i}" for i in range(n_screens)]


def _resolve(n_screens: int, playback: list[int], slot: int):
    return ControlWindow._screen_index_for_slot(_Stub(n_screens, playback), slot)


def test_stim_slot_never_gets_a_screen():
    """Slot 1 drives a stim box, not a display. It must report None — not 0 —
    or the launch loop opens a video window for it."""
    assert _SLOT_ROLES[1] == "stim"
    assert _resolve(1, [0], 1) is None
    assert _resolve(3, [0, 1, 2], 1) is None


def test_single_monitor_gives_exactly_one_slot_a_screen():
    """THE regression. One monitor, one checked playback screen: only the
    video slot may resolve to a screen. Every other slot returning None is
    what stops the second window from opening."""
    resolved = [_resolve(1, [0], i) for i in range(_NUM_SLOTS)]

    assert resolved[0] == 0
    assert all(r is None for r in resolved[1:]), resolved


def test_mirror_gets_the_second_checked_screen_when_there_is_one():
    """The feature the None case must not break: with two screens checked, the
    first mirror takes the second one."""
    assert _resolve(2, [0, 1], 0) == 0
    assert _resolve(2, [0, 1], 2) == 1
    # Only two screens checked, so the second mirror still has nowhere to go.
    assert _resolve(2, [0, 1], 3) is None


def test_unchecked_playback_list_falls_back_to_slot_position():
    """With nothing checked in Setup, slot 0 still plays somewhere rather than
    refusing to launch."""
    assert _resolve(2, [], 0) == 0


def test_stale_index_is_left_for_the_caller_to_decide():
    """A checked screen that no longer exists (monitor unplugged) resolves to
    its remembered index, NOT None. The launch loop decides what to do with it
    by role — clamp for the video slot, skip for a mirror — so the two cases
    must stay distinguishable here."""
    got = _resolve(1, [2], 0)

    assert got == 2
    assert got is not None


def test_two_screens_checked_but_one_attached_is_the_duplicate_window_case():
    """THE reported bug, exactly.

    Setup has two playback screens ticked; only one monitor is plugged in.
    Library activation mirrors the video into slot 2 whenever two or more
    screens are checked, so the mirror resolves to screen 1 — which does not
    exist. Clamping that to the primary put a second, MUTED window directly on
    top of the real player: users saw two windows on one monitor, the visible
    one silent.

    The resolver's job is to report 1 honestly. `_on_launch` skips mirrors
    whose screen is not attached rather than clamping them.
    """
    assert _SLOT_ROLES[2] == "mirror"

    mirror_screen = _resolve(1, [0, 1], 2)

    assert mirror_screen == 1
    assert mirror_screen >= 1  # i.e. >= len(screens): not attached
    # The real video slot is unaffected and still plays on the one monitor.
    assert _resolve(1, [0, 1], 0) == 0
