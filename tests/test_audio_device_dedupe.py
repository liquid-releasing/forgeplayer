# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Collapsing the same hardware seen through two mpv audio drivers.

Found while dogfooding on macOS 2026-09-13: every device appeared twice in the
pickers with an identical description, because mpv enumerates all of them under
both `coreaudio/` and `avfoundation/`. A single USB stim dongle showed up as two
indistinguishable entries. Linux duplicates the same way across
pulse/pipewire/alsa/jack; Windows has only `wasapi/`, which is why this was
never seen there.

The dangerous mistake this guards against is collapsing by DESCRIPTION. Two
identical USB dongles — exactly the Haptic 1 + Haptic 2 setup ForgePlayer is
built for — report the same description, so that would merge two real boxes
into one and leave the second unroutable.
"""

from __future__ import annotations

from app.sync_engine import canonical_device_name, dedupe_driver_duplicates


def _d(name, desc):
    return {"name": name, "description": desc}


# The real list captured from the dev Mac, dongle plugged in.
MAC_DEVICES = [
    _d("coreaudio/AppleUSBAudioEngine:C-Media Electronics Inc.:USB Advanced "
       "Audio Device:110000:2,1", "USB Advanced Audio Device"),
    _d("coreaudio/BuiltInSpeakerDevice", "MacBook Neo Speakers"),
    _d("avfoundation/AppleUSBAudioEngine:C-Media Electronics Inc.:USB Advanced "
       "Audio Device:110000:2,1", "USB Advanced Audio Device"),
    _d("avfoundation/BuiltInSpeakerDevice", "MacBook Neo Speakers"),
]


def test_macos_duplicates_collapse_to_coreaudio():
    """coreaudio is mpv's default and native macOS output; avfoundation is the
    alternative, so the pair collapses onto coreaudio."""
    out = dedupe_driver_duplicates(MAC_DEVICES)

    assert [d["name"] for d in out] == [
        "coreaudio/AppleUSBAudioEngine:C-Media Electronics Inc.:USB Advanced "
        "Audio Device:110000:2,1",
        "coreaudio/BuiltInSpeakerDevice",
    ]


def test_avfoundation_first_still_yields_coreaudio():
    """Priority, not list order, decides the winner."""
    out = dedupe_driver_duplicates(list(reversed(MAC_DEVICES)))

    assert all(d["name"].startswith("coreaudio/") for d in out)


def test_two_identical_dongles_are_never_merged():
    """THE regression that matters. Both report the same description and differ
    only in USB location; merging them would make Haptic 2 unroutable."""
    devices = [
        _d("coreaudio/AppleUSBAudioEngine:C-Media:USB Advanced Audio Device:"
           "110000:2,1", "USB Advanced Audio Device"),
        _d("coreaudio/AppleUSBAudioEngine:C-Media:USB Advanced Audio Device:"
           "120000:2,1", "USB Advanced Audio Device"),
        _d("avfoundation/AppleUSBAudioEngine:C-Media:USB Advanced Audio Device:"
           "110000:2,1", "USB Advanced Audio Device"),
        _d("avfoundation/AppleUSBAudioEngine:C-Media:USB Advanced Audio Device:"
           "120000:2,1", "USB Advanced Audio Device"),
    ]

    out = dedupe_driver_duplicates(devices)

    assert len(out) == 2
    assert {d["name"] for d in out} == {
        "coreaudio/AppleUSBAudioEngine:C-Media:USB Advanced Audio Device:"
        "110000:2,1",
        "coreaudio/AppleUSBAudioEngine:C-Media:USB Advanced Audio Device:"
        "120000:2,1",
    }


def test_windows_list_is_unchanged():
    """Only one driver, so there is nothing to collapse — and Windows is the
    platform that currently ships."""
    devices = [
        _d("wasapi/{0.0.0.1}", "Speakers (Realtek High Definition Audio)"),
        _d("wasapi/{0.0.0.2}", "Odyssey G95NC (NVIDIA High Definition Audio)"),
    ]

    assert dedupe_driver_duplicates(devices) == devices


def test_linux_collapses_only_drivers_that_share_a_device_id():
    """Linux is helped but NOT fully fixed, and that is deliberate.

    `alsa/hw:0,0` and `jack/hw:0,0` name the same card the same way, so they
    collapse (alsa outranks jack). PulseAudio invents its own id
    (`alsa_output.pci-…`) for that same card, so it cannot be matched by id and
    survives as a second entry.

    Collapsing those by description instead would fix the cosmetics and
    reintroduce the two-identical-dongles bug, which is the worse trade for an
    app whose whole point is routing two stim boxes independently. Linux users
    may still see one duplicate pair; macOS, where both drivers use the same
    device id, is fully collapsed.
    """
    devices = [
        _d("alsa/hw:0,0", "Built-in Audio"),
        _d("pulse/alsa_output.pci-0000_00_1f.3", "Built-in Audio"),
        _d("jack/hw:0,0", "Built-in Audio"),
    ]

    out = dedupe_driver_duplicates(devices)

    assert [d["name"] for d in out] == [
        "alsa/hw:0,0",
        "pulse/alsa_output.pci-0000_00_1f.3",
    ]


def test_order_is_preserved_by_first_appearance():
    """The picker must not reshuffle under the user when a device is added."""
    out = dedupe_driver_duplicates(MAC_DEVICES)

    assert out[0]["description"] == "USB Advanced Audio Device"
    assert out[1]["description"] == "MacBook Neo Speakers"


def test_entries_without_a_driver_prefix_pass_through():
    devices = [_d("auto", "Autoselect device"), _d("coreaudio/X", "X")]

    assert dedupe_driver_duplicates(devices) == devices


# ── canonical_device_name ────────────────────────────────────────────────────

def test_saved_avfoundation_id_maps_onto_the_listed_coreaudio_one():
    """A preference saved before dedup names a driver the picker no longer
    offers. Without this the combo silently reads "— not set —" and the user's
    haptic routing looks forgotten."""
    listed = dedupe_driver_duplicates(MAC_DEVICES)

    got = canonical_device_name("avfoundation/BuiltInSpeakerDevice", listed)

    assert got == "coreaudio/BuiltInSpeakerDevice"


def test_an_id_already_present_is_returned_unchanged():
    listed = dedupe_driver_duplicates(MAC_DEVICES)

    assert canonical_device_name(
        "coreaudio/BuiltInSpeakerDevice", listed,
    ) == "coreaudio/BuiltInSpeakerDevice"


def test_an_unplugged_device_is_left_alone():
    """No equivalent present — return it unchanged rather than guessing, so the
    caller's own "not present" handling decides what to show."""
    listed = dedupe_driver_duplicates(MAC_DEVICES)

    assert canonical_device_name("coreaudio/GoneAway", listed) == "coreaudio/GoneAway"


def test_empty_selection_stays_empty():
    """"— not set —" must never resolve to a real device."""
    assert canonical_device_name("", dedupe_driver_duplicates(MAC_DEVICES)) == ""
