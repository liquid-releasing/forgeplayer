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
