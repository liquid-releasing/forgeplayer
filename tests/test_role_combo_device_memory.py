# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""A saved audio device must survive not being plugged in.

User report 2026-09-16: *"the settings did not seem to be saved between
sessions... saving settings seems unstable either in the update or between
starts."*

The mechanism, which is data loss rather than a display glitch:

1. A role combo restored its saved device by matching the stored mpv id
   against the devices enumerated **this** session. A device that is simply
   not here right now — a sleeping TV over HDMI, an unplugged USB dongle,
   disconnected Bluetooth — matched nothing and the combo fell through to
   "— not set —", whose data is `""`.
2. `_on_setup_changed` is connected to `currentIndexChanged` on ALL FOUR role
   combos and rewrites ALL FOUR preferences from `currentData()`.
3. So the moment the user touched *any* setting, the absent device's
   preference was overwritten with `""` — a role they never went near. Replug
   the device and the choice was gone for good.

The fix keeps the id on an explicit "— not connected" entry, which also stops
the UI claiming a role is unconfigured when it is configured and merely
unplugged (`feedback_forgeplayer_reporting_must_match_actual`).

These tests drive `_populate_role_combo`, the single function both the initial
build and the "Refresh devices" rebuild now share. They had drifted apart:
only the refresh path canonicalized driver aliases.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QComboBox

from app.control_window import ControlWindow


PRESENT = [
    ("wasapi/realtek", "Speakers (Realtek High Definition Audio)"),
    ("wasapi/usb-dongle", "USB Advanced Audio Device"),
]
ABSENT = "wasapi/tv-hdmi"        # the TV is asleep this session


def _combo(qapp, saved, devices=PRESENT):
    combo = QComboBox()
    ControlWindow._populate_role_combo(combo, saved, list(devices))
    return combo


# ── The reported bug ─────────────────────────────────────────────────────────

def test_an_absent_device_is_still_the_current_selection(qapp):
    """THE bug. `currentData()` is what gets written back to preferences, so
    this assertion IS the difference between remembering and destroying the
    user's choice."""
    combo = _combo(qapp, ABSENT)
    assert combo.currentData() == ABSENT


def test_an_absent_device_is_labelled_not_connected(qapp):
    """The UI has to say why the device isn't working, rather than claiming
    the role was never configured."""
    combo = _combo(qapp, ABSENT)
    assert "not connected" in combo.currentText()
    assert combo.currentText() != "— not set —"


def test_touching_another_role_cannot_erase_an_absent_device(qapp):
    """The actual sequence the user hit: four combos are rebuilt at startup,
    one device is missing, and saving reads `currentData()` off all four."""
    scene = _combo(qapp, ABSENT)
    haptic1 = _combo(qapp, "wasapi/usb-dongle")

    # What `_on_setup_changed` writes to preferences.
    saved_scene = scene.currentData() or ""
    saved_haptic1 = haptic1.currentData() or ""

    assert saved_scene == ABSENT, "the sleeping TV's setting was destroyed"
    assert saved_haptic1 == "wasapi/usb-dongle"


def test_the_device_rebinds_once_it_comes_back(qapp):
    """Plugging the TV back in and hitting Refresh must select the REAL entry,
    not leave a duplicate 'not connected' row behind."""
    back = PRESENT + [(ABSENT, "Samsung TV (HDMI)")]
    combo = _combo(qapp, ABSENT, devices=back)

    assert combo.currentData() == ABSENT
    assert combo.currentText() == "Samsung TV (HDMI)"
    assert "not connected" not in combo.currentText()
    # Exactly one row carries that id.
    ids = [combo.itemData(i) for i in range(combo.count())]
    assert ids.count(ABSENT) == 1


# ── Unset really is unset ────────────────────────────────────────────────────

def test_an_unset_role_stays_unset(qapp):
    """The fix must not invent a phantom entry for a role the user never
    configured."""
    combo = _combo(qapp, "")
    assert combo.currentData() == ""
    assert combo.currentText() == "— not set —"
    assert combo.count() == len(PRESENT) + 1


def test_a_present_device_is_selected_normally(qapp):
    combo = _combo(qapp, "wasapi/usb-dongle")
    assert combo.currentData() == "wasapi/usb-dongle"
    assert combo.currentText() == "USB Advanced Audio Device"
    assert combo.count() == len(PRESENT) + 1, "no extra row for a present device"


# ── Driver aliases: the half that only worked after a manual refresh ────────

def test_a_driver_alias_matches_the_listed_twin(qapp):
    """mpv lists the same macOS hardware as coreaudio/ and avfoundation/. A
    preference saved under one must select the other rather than being treated
    as absent — this ran only in the refresh path before, so at startup macOS
    users saw their haptic routing as "— not set —"."""
    devices = [("coreaudio/BuiltInSpeaker", "Built-in Speakers")]
    combo = _combo(qapp, "avfoundation/BuiltInSpeaker", devices=devices)

    assert combo.currentData() == "coreaudio/BuiltInSpeaker"
    assert "not connected" not in combo.currentText()


def test_an_unknown_id_with_no_twin_is_reported_absent(qapp):
    combo = _combo(qapp, "coreaudio/SomethingElse", devices=PRESENT)
    assert combo.currentData() == "coreaudio/SomethingElse"
    assert "not connected" in combo.currentText()


# ── Rebuilding must not lose it either ──────────────────────────────────────

def test_repopulating_is_idempotent(qapp):
    """'Refresh devices' can be pressed repeatedly; each pass must leave one
    row per device and the same selection."""
    combo = QComboBox()
    for _ in range(3):
        ControlWindow._populate_role_combo(combo, ABSENT, list(PRESENT))

    assert combo.currentData() == ABSENT
    assert combo.count() == len(PRESENT) + 2  # not set + devices + absent row


def test_repopulating_emits_no_signals(qapp):
    """`_on_setup_changed` writes preferences from every combo, so a rebuild
    that emitted currentIndexChanged would itself trigger the clobbering save
    this fix exists to prevent."""
    combo = QComboBox()
    fired = []
    combo.currentIndexChanged.connect(fired.append)

    ControlWindow._populate_role_combo(combo, "wasapi/usb-dongle", list(PRESENT))

    assert fired == []
    assert combo.currentData() == "wasapi/usb-dongle"


@pytest.mark.parametrize("saved", ["", "wasapi/realtek", ABSENT])
def test_an_empty_device_list_never_loses_the_preference(qapp, saved):
    """The audio subsystem can return nothing at all (driver reload, a hiccup
    during an update). That must not wipe all four roles at once."""
    combo = _combo(qapp, saved, devices=[])
    assert combo.currentData() == saved
