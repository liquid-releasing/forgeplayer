# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""D3D11 adapter selection on Windows.

Context: a user reported audio playing with NO video on Windows. `vo=gpu`
failing to initialise is exactly how that presents — mpv carries on with
audio-only when no suitable GPU context comes up.

The suspect path: `_detect_nvidia_adapter()` enumerates display adapters via
EnumDisplayDevicesW and returns True if any DeviceString contains "NVIDIA",
whether or not that GPU is usable. We then pin `gpu_context=d3d11` +
`d3d11_adapter=NVIDIA` — and pinning the context ALSO disables mpv's automatic
fallback to another one. If DXGI exposes no matching adapter (muxed-off or
disabled dGPU, or stale driver registry entries on a machine with no NVIDIA
card), context creation fails and video never starts.

`FORGEPLAYER_D3D11_ADAPTER=auto` is the escape hatch that restores mpv's own
choice and its fallback.
"""

from __future__ import annotations

import pytest

from app.sync_engine import apply_d3d11_adapter_kwargs


def _k():
    return {"vo": "gpu"}


# ── Default behaviour ────────────────────────────────────────────────────────

def test_nvidia_present_pins_the_adapter():
    k = _k()
    got = apply_d3d11_adapter_kwargs(k, platform="win32", env={}, has_nvidia=True)
    assert got == "NVIDIA"
    assert k["gpu_context"] == "d3d11"
    assert k["d3d11_adapter"] == "NVIDIA"


def test_no_nvidia_leaves_mpv_to_choose():
    """An AMD-only or Intel-only machine must keep mpv's context fallback."""
    k = _k()
    assert apply_d3d11_adapter_kwargs(
        k, platform="win32", env={}, has_nvidia=False
    ) is None
    assert "gpu_context" not in k
    assert "d3d11_adapter" not in k


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_non_windows_never_pins_a_d3d11_adapter(platform):
    """D3D11 is Windows-only; pinning it elsewhere would break the VO."""
    k = _k()
    assert apply_d3d11_adapter_kwargs(
        k, platform=platform, env={}, has_nvidia=True
    ) is None
    assert k == {"vo": "gpu"}


# ── The escape hatch ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["auto", "AUTO", " none ", "default"])
def test_override_can_restore_mpv_s_own_choice(value):
    """THE mitigation for "sound but no picture": stop pinning, so mpv can
    fall back to another context."""
    k = _k()
    assert apply_d3d11_adapter_kwargs(
        k, platform="win32", env={"FORGEPLAYER_D3D11_ADAPTER": value},
        has_nvidia=True,
    ) is None
    assert "gpu_context" not in k
    assert "d3d11_adapter" not in k


def test_override_can_name_a_specific_adapter():
    k = _k()
    got = apply_d3d11_adapter_kwargs(
        k, platform="win32", env={"FORGEPLAYER_D3D11_ADAPTER": "Intel"},
        has_nvidia=True,
    )
    assert got == "Intel"
    assert k["d3d11_adapter"] == "Intel"


def test_override_applies_even_without_a_detected_nvidia():
    """Lets a user pin a working adapter on a machine we detected nothing on."""
    k = _k()
    got = apply_d3d11_adapter_kwargs(
        k, platform="win32", env={"FORGEPLAYER_D3D11_ADAPTER": "Radeon"},
        has_nvidia=False,
    )
    assert got == "Radeon"
    assert k["gpu_context"] == "d3d11"


def test_blank_override_is_ignored():
    """An exported-but-empty variable must not change the default."""
    k = _k()
    got = apply_d3d11_adapter_kwargs(
        k, platform="win32", env={"FORGEPLAYER_D3D11_ADAPTER": "   "},
        has_nvidia=True,
    )
    assert got == "NVIDIA"


# ── The user-facing escape hatch ─────────────────────────────────────────────
#
# Beta testers can't be asked to set environment variables or extract JSONL
# debug logs. Setup carries a "Use the default graphics adapter" checkbox that
# maps to Preferences.force_default_gpu, so "sound but no picture" is one tick
# and a relaunch away.

from app.preferences import Preferences
from app.sync_engine import apply_platform_video_kwargs


def test_preference_defaults_to_off():
    """The NVIDIA pin stays the default — it exists to dodge a real AMD
    teardown crash, so it must not be disabled for everyone."""
    assert Preferences().force_default_gpu is False


def test_setup_checkbox_stops_the_pinning():
    k = _k()
    assert apply_d3d11_adapter_kwargs(
        k, platform="win32", env={}, has_nvidia=True, force_default=True,
    ) is None
    assert "gpu_context" not in k
    assert "d3d11_adapter" not in k


def test_user_choice_outranks_the_env_override():
    """Someone looking at a black screen has better evidence than our
    detection or a stale env var."""
    k = _k()
    assert apply_d3d11_adapter_kwargs(
        k, platform="win32",
        env={"FORGEPLAYER_D3D11_ADAPTER": "NVIDIA"},
        has_nvidia=True, force_default=True,
    ) is None
    assert "d3d11_adapter" not in k


def test_flag_reaches_the_adapter_choice_through_the_top_level_helper():
    """Guards the wiring, not just the leaf — init_player passes the pref
    down through apply_platform_video_kwargs."""
    k = {"vo": "gpu"}
    apply_platform_video_kwargs(
        k, 42, platform="win32", env={}, has_nvidia=True,
        force_default_gpu=True,
    )
    assert "d3d11_adapter" not in k
    assert k["wid"] == "42"          # embedding is unaffected

    k = {"vo": "gpu"}
    apply_platform_video_kwargs(
        k, 42, platform="win32", env={}, has_nvidia=True,
        force_default_gpu=False,
    )
    assert k["d3d11_adapter"] == "NVIDIA"


# ── The pin only makes sense when there is an AMD adapter to avoid ───────────
#
# Reported 2026-09-13: "audio and stim play but the player screen remains black,
# but the playback buttons and timeline all display and work" — mpv alive and
# playing, presenting nothing. The user's own workaround was to DISABLE the
# NVIDIA GPU in Device Manager, which worked only because it made the old
# detection return False.
#
# Cause: the check was "is any NVIDIA adapter present", which also fires on
# Intel + NVIDIA machines. There is no AMD driver bug to dodge there, so the pin
# is pure downside — and pinning the D3D11 device to a discrete GPU that isn't
# driving the display means mpv can't get pixels into a window on the
# Intel-driven output.
#
# Confirmed across three real machines, which is why this is a table test.

from app.platform_video import should_pin_nvidia_adapter


@pytest.mark.parametrize("vendors,expected,why", [
    ({"amd", "nvidia"}, True,
     "dev box: AMD present, so route around its D3D11 teardown bug"),
    ({"intel", "nvidia"}, False,
     "THE BUG: no AMD to dodge, and pinning blacked out the video"),
    ({"intel"}, False, "Intel-only laptop: verified working, nothing to pin"),
    ({"amd"}, False, "AMD-only: no second adapter to route to"),
    ({"nvidia"}, False, "NVIDIA-only: already the only adapter"),
    ({"intel", "amd", "nvidia"}, True, "AMD present, so still worth avoiding"),
    (set(), False,
     "enumeration failed: mpv's own choice plus its fallback beats a guess"),
])
def test_pin_requires_both_nvidia_and_amd(vendors, expected, why):
    assert should_pin_nvidia_adapter(vendors) is expected, why


def test_the_reported_machine_no_longer_gets_a_forced_adapter():
    """End to end for the reporter's configuration: Intel + NVIDIA must reach
    mpv with no adapter pinned, so mpv keeps its own choice AND its context
    fallback."""
    k = _k()
    got = apply_d3d11_adapter_kwargs(
        k, platform="win32", env={},
        has_nvidia=should_pin_nvidia_adapter({"intel", "nvidia"}),
    )
    assert got is None
    assert "gpu_context" not in k
    assert "d3d11_adapter" not in k


def test_the_dev_machine_still_gets_the_pin():
    """The AMD teardown crash is real and unfixed upstream — this must not
    regress while fixing the black-screen case."""
    k = _k()
    got = apply_d3d11_adapter_kwargs(
        k, platform="win32", env={},
        has_nvidia=should_pin_nvidia_adapter({"amd", "nvidia"}),
    )
    assert got == "NVIDIA"
    assert k["d3d11_adapter"] == "NVIDIA"
