# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Audio-device classification + listing.

Guards the 2026-09-05 change that made monitor / TV HDMI outputs
selectable for scene audio. Two things must hold at once: a display
endpoint has to REACH the scene pickers (a TV over HDMI has speakers),
and it has to STAY OUT of the e-stim pickers (a display is never stim
hardware).

These tests never construct an mpv instance — they exercise the pure
classifiers and stub the enumeration — so they're safe on a headless
runner. See tests/test_control_window.py for why that matters.
"""

from __future__ import annotations

import pytest

from app import sync_engine
from app.sync_engine import (
    SyncEngine,
    _is_meta_device,
    is_bluetooth_audio,
    is_display_audio,
)


def _dev(description: str, name: str = "wasapi/{guid}") -> dict:
    return {"name": name, "description": description}


# ── is_display_audio ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("description", [
    "Odyssey G95NC (NVIDIA High Definition Audio)",
    "1 - 12.3FHD (AMD High Definition Audio Device)",
    "SAMSUNG TV (Intel(R) Display Audio)",
    "LG TV (AMD High Definition Audio Device)",
    "Digital Output (HDMI)",
    "DisplayPort Audio",
])
def test_display_endpoints_are_classified_as_display(description):
    assert is_display_audio(_dev(description)) is True


@pytest.mark.parametrize("description", [
    # THE regression this change exists to prevent. The old filter matched
    # the bare phrase "high definition audio", which is also the name of
    # the single most common ONBOARD analog output on Windows — so a
    # machine's real speakers were classified as an HDMI phantom and
    # vanished from every picker.
    "Speakers (Realtek High Definition Audio)",
    "Headphones (Realtek High Definition Audio)",
    "Speakers (Realtek(R) Audio)",
    "Speakers (USB Audio Device)",
    "Headset (Jabra Evolve)",
])
def test_real_output_devices_are_not_classified_as_display(description):
    assert is_display_audio(_dev(description)) is False


# ── meta entries ─────────────────────────────────────────────────────────────

def test_auto_and_openal_are_meta():
    assert _is_meta_device({"name": "auto", "description": "Autoselect device"})
    assert _is_meta_device({"name": "openal", "description": "Default (openal)"})


def test_real_device_is_not_meta():
    assert not _is_meta_device(_dev("Speakers (Realtek(R) Audio)"))


# ── is_bluetooth_audio ───────────────────────────────────────────────────────

@pytest.mark.parametrize("description,expected", [
    ("Headphones (Bluetooth Stereo)", True),
    ("Headset (Jabra Evolve Hands-Free AG Audio)", True),
    ("Speakers (Realtek(R) Audio)", False),
    ("Odyssey G95NC (NVIDIA High Definition Audio)", False),
])
def test_bluetooth_classification(description, expected):
    assert is_bluetooth_audio(_dev(description)) is expected


# ── the two listings ─────────────────────────────────────────────────────────

_RAW = [
    {"name": "auto", "description": "Autoselect device"},
    {"name": "wasapi/{a}", "description": "Speakers (Realtek(R) Audio)"},
    {"name": "wasapi/{b}", "description": "1 - 12.3FHD (AMD High Definition Audio Device)"},
    {"name": "wasapi/{c}", "description": "Odyssey G95NC (NVIDIA High Definition Audio)"},
    {"name": "openal", "description": "Default (openal)"},
]


@pytest.fixture
def stub_enumeration(monkeypatch):
    """Stand in for the live mpv audio_device_list query."""
    monkeypatch.setattr(
        sync_engine.SyncEngine, "list_audio_devices",
        staticmethod(lambda include_hdmi=False: (
            list(_RAW) if include_hdmi
            else [d for d in _RAW if not sync_engine._is_display_audio(d)]
        )),
    )


def test_list_output_devices_keeps_displays_and_drops_meta(stub_enumeration):
    names = [d["name"] for d in SyncEngine.list_output_devices()]
    # Both displays survive — this is the whole point of the change.
    assert "wasapi/{b}" in names
    assert "wasapi/{c}" in names
    # Real speakers survive.
    assert "wasapi/{a}" in names
    # mpv's meta-entries never reach a picker.
    assert "auto" not in names
    assert "openal" not in names


def test_conservative_list_still_excludes_displays(stub_enumeration):
    """The haptic pickers' source. A display must not appear here."""
    names = [d["name"] for d in SyncEngine.list_audio_devices()]
    assert names == ["wasapi/{a}"]
