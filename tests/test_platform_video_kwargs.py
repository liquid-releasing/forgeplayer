# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Platform adjustment of the embedded-video player's mpv kwargs.

Guards the macOS branch, which has now been through three shapes. Launch
Players hung indefinitely on an M1, an M3 Max and this dev Mac at ~0.4% CPU —
a deadlock, not a busy loop — because libmpv's macOS backend builds and
resizes its NSWindow on mpv's `vo` thread via `dispatch_sync` onto the main
queue that Qt's main thread owns. `--wid` embedding hung in mpv's constructor;
the `force_window` stopgap hung slightly later, whenever the GUI thread was
busy. Neither is the default any more: darwin now sets `vo=libmpv` and renders
through `mpv_render_context`, so mpv has no window and needs no main queue.
Both older shapes survive as env overrides for A/B testing on a real Mac.

Windows and Linux keep `--wid`, which is what preserves D3D11 and HDR
passthrough on Windows — see `docs/macos_render_api.md`.

Pure-function tests: `apply_platform_video_kwargs` takes platform and env as
parameters precisely so this can be verified from Windows/Linux CI without a
Mac and without constructing a real mpv instance (see
`feedback_forgeplayer_tests_never_touch_real_mpv`).
"""

from __future__ import annotations

import pytest

from app.sync_engine import apply_platform_video_kwargs


def _kwargs(**over):
    base = {"keep_open": True, "hwdec": "auto-safe", "vo": "gpu"}
    base.update(over)
    return base


# ── macOS: embedding is dropped ──────────────────────────────────────────────

def test_macos_defaults_to_the_render_api():
    """The fix that actually holds: `vo=libmpv` means mpv has no window of its
    own, so there is no Cocoa VO to want the main queue. No `wid`, and no
    `force_window` either — either one would give mpv a window back."""
    out = apply_platform_video_kwargs(
        _kwargs(), 12345, platform="darwin", env={},
    )
    assert out["vo"] == "libmpv"
    assert "wid" not in out
    assert "force_window" not in out


def test_macos_render_path_overrides_the_default_vo():
    """Callers pass vo=gpu in their base kwargs; darwin must win, or mpv opens
    a Cocoa window and the deadlock class comes straight back."""
    out = apply_platform_video_kwargs(
        _kwargs(vo="gpu"), 1, platform="darwin", env={},
    )
    assert out["vo"] == "libmpv"


def test_macos_embed_override_restores_wid():
    """A/B switch so the ORIGINAL embedding path can be compared on a real Mac
    without a rebuild. Expected to hang — it is the control, not a fallback."""
    out = apply_platform_video_kwargs(
        _kwargs(), 12345,
        platform="darwin", env={"FORGEPLAYER_MACOS_EMBED": "wid"},
    )
    assert out["wid"] == "12345"
    assert out["vo"] != "libmpv"


def test_macos_window_override_restores_the_force_window_stopgap():
    """The second attempt, kept for A/B: mpv owns a detached NSWindow. Plays,
    but wedges on a busy GUI thread and has no Qt overlay."""
    out = apply_platform_video_kwargs(
        _kwargs(), 12345,
        platform="darwin", env={"FORGEPLAYER_MACOS_EMBED": "window"},
    )
    assert "wid" not in out
    assert out["force_window"] == "yes"
    assert out["vo"] != "libmpv"


@pytest.mark.parametrize("value", ["", "WID_NOT", "0", "render"])
def test_macos_unrecognised_override_keeps_the_render_api(value):
    """Anything but an exact opt-in stays on the path that works."""
    out = apply_platform_video_kwargs(
        _kwargs(), 12345,
        platform="darwin", env={"FORGEPLAYER_MACOS_EMBED": value},
    )
    assert out["vo"] == "libmpv"
    assert "wid" not in out


def test_macos_embed_override_is_case_insensitive_and_trimmed():
    out = apply_platform_video_kwargs(
        _kwargs(), 7, platform="darwin", env={"FORGEPLAYER_MACOS_EMBED": "  WID "},
    )
    assert out["wid"] == "7"


# ── Other platforms are untouched ────────────────────────────────────────────

@pytest.mark.parametrize("platform", ["win32", "linux", "linux2"])
def test_non_macos_keeps_embedding(platform):
    """Windows and X11 embed correctly and must not regress — this is the
    shipping path for every current user."""
    out = apply_platform_video_kwargs(
        _kwargs(), 999, platform=platform, env={},
    )
    assert out["wid"] == "999"
    assert "force_window" not in out


def test_wid_is_stringified():
    """mpv wants the handle as a string; python-mpv passes it through."""
    out = apply_platform_video_kwargs(_kwargs(), 4242, platform="win32", env={})
    assert out["wid"] == "4242"
    assert isinstance(out["wid"], str)


# ── hwdec override ───────────────────────────────────────────────────────────

def test_hwdec_override_applies_on_any_platform():
    """Lets a tester rule VideoToolbox in or out as a secondary suspect."""
    for platform in ("darwin", "win32"):
        out = apply_platform_video_kwargs(
            _kwargs(), 1, platform=platform, env={"FORGEPLAYER_HWDEC": "no"},
        )
        assert out["hwdec"] == "no"


def test_absent_hwdec_override_leaves_the_default():
    out = apply_platform_video_kwargs(_kwargs(), 1, platform="win32", env={})
    assert out["hwdec"] == "auto-safe"


def test_blank_hwdec_override_is_ignored():
    """An exported-but-empty env var must not blank out hardware decode."""
    out = apply_platform_video_kwargs(
        _kwargs(), 1, platform="win32", env={"FORGEPLAYER_HWDEC": "   "},
    )
    assert out["hwdec"] == "auto-safe"


def test_returns_the_same_dict_it_mutates():
    k = _kwargs()
    assert apply_platform_video_kwargs(k, 1, platform="win32", env={}) is k
