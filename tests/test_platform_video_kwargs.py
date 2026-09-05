# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Platform adjustment of the embedded-video player's mpv kwargs.

Guards the macOS branch added 2026-09-05 after a user report: Launch Players
hung indefinitely on both an Apple M1 and an M3 Max, at ~0.4% CPU (a deadlock,
not a busy loop), with a black video window. Upstream mpv does not properly
support `--wid` embedding on macOS with GPU rendering — the documented symptom
is "audio with a black video surface" — so on darwin we drop `wid` and let mpv
own its window.

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

def test_macos_drops_wid_and_forces_its_own_window():
    """THE fix. `wid` on darwin is what deadlocks the main thread."""
    out = apply_platform_video_kwargs(
        _kwargs(), 12345, platform="darwin", env={},
    )
    assert "wid" not in out
    assert out["force_window"] == "yes"


def test_macos_embed_override_restores_wid():
    """A/B switch so the old path can be compared on a real Mac without a
    rebuild."""
    out = apply_platform_video_kwargs(
        _kwargs(), 12345,
        platform="darwin", env={"FORGEPLAYER_MACOS_EMBED": "wid"},
    )
    assert out["wid"] == "12345"


@pytest.mark.parametrize("value", ["window", "", "WID_NOT", "0"])
def test_macos_only_the_exact_wid_value_re_enables_embedding(value):
    """Anything but the exact opt-in keeps the safe detached path."""
    out = apply_platform_video_kwargs(
        _kwargs(), 12345,
        platform="darwin", env={"FORGEPLAYER_MACOS_EMBED": value},
    )
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
