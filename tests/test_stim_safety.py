# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the runtime flash-guard (app/stim_safety.py).

Covers the safety invariant: near-max carrier frequency AND near-max
volume must never be commanded together, and a sudden volume rise is
slew-limited. Genuine artistic builds (slow ramps, one-axis sweeps,
sustained-but-not-co-railed loudness) must pass through untouched.
"""

from __future__ import annotations

import numpy as np

from app.funscript_loader import FunscriptActions, StimChannels
from app.stim_safety import (
    FLASH_VOL_CAP,
    MIN_RISE_TIME_S,
    VOL_RAIL,
    apply_flash_guard,
)


def _channels(vol=None, freq=None) -> StimChannels:
    t = np.linspace(0.0, 1.0, 5)
    return StimChannels(
        t=t,
        alpha=0.5 * np.ones_like(t),
        beta=0.5 * np.ones_like(t),
        source="radial_1d",
        volume=vol,
        carrier_frequency=freq,
    )


def _acts(t, p) -> FunscriptActions:
    return FunscriptActions(t=np.asarray(t, float), p=np.asarray(p, float))


class TestCoRailCap:
    def test_caps_volume_when_both_railed(self):
        # volume and frequency both pinned at max at the same instants.
        t = [0.0, 1.0, 2.0]
        ch = _channels(_acts(t, [0.5, 1.0, 1.0]), _acts(t, [0.5, 1.0, 1.0]))
        out, regions = apply_flash_guard(ch)
        # the two railed samples are capped, the first (0.5) is untouched
        np.testing.assert_allclose(out.volume.p, [0.5, FLASH_VOL_CAP, FLASH_VOL_CAP])
        assert regions and regions[0].reason == "co_rail"
        assert regions[0].peak_volume == 1.0

    def test_no_cap_when_frequency_low(self):
        # volume railed but frequency low → intentional loud passage, leave it.
        t = [0.0, 1.0, 2.0]
        ch = _channels(_acts(t, [1.0, 1.0, 1.0]), _acts(t, [0.3, 0.3, 0.3]))
        out, regions = apply_flash_guard(ch)
        np.testing.assert_allclose(out.volume.p, [1.0, 1.0, 1.0])
        assert regions == []

    def test_no_frequency_channel_means_no_co_rail(self):
        # absent carrier channel → detector default 0.5 < rail → no co-rail cap.
        t = [0.0, 1.0, 2.0]
        ch = _channels(_acts(t, [1.0, 1.0, 1.0]), None)
        out, regions = apply_flash_guard(ch)
        assert all(r.reason != "co_rail" for r in regions)


class TestSlewLimit:
    def test_instant_jump_is_ramped(self):
        # volume jumps 0→1 in 10 ms (< MIN_RISE_TIME_S) → clamped below 1.
        t = [0.0, 0.010]
        ch = _channels(_acts(t, [0.0, 1.0]), None)
        out, regions = apply_flash_guard(ch)
        assert out.volume.p[1] < 1.0
        expected = 0.0 + (1.0 / MIN_RISE_TIME_S) * 0.010
        np.testing.assert_allclose(out.volume.p[1], expected, rtol=1e-6)
        assert regions and regions[0].reason == "slew"

    def test_slow_rise_passes(self):
        # 0→1 over 1 s is well under the slew ceiling → untouched.
        t = [0.0, 1.0]
        ch = _channels(_acts(t, [0.0, 1.0]), None)
        out, regions = apply_flash_guard(ch)
        np.testing.assert_allclose(out.volume.p, [0.0, 1.0])
        assert regions == []

    def test_fast_fall_is_allowed(self):
        # dropping volume fast is always safe — never clamped.
        t = [0.0, 0.010]
        ch = _channels(_acts(t, [1.0, 0.0]), None)
        out, regions = apply_flash_guard(ch)
        np.testing.assert_allclose(out.volume.p, [1.0, 0.0])
        assert regions == []


class TestPassthrough:
    def test_no_volume_channel_returns_input_unchanged(self):
        ch = _channels(None, None)
        out, regions = apply_flash_guard(ch)
        assert out is ch
        assert regions == []

    def test_empty_volume_actions_unchanged(self):
        ch = _channels(_acts([], []), None)
        out, regions = apply_flash_guard(ch)
        assert out is ch
        assert regions == []

    def test_quiet_scene_untouched(self):
        t = [0.0, 0.5, 1.0]
        ch = _channels(_acts(t, [0.3, 0.4, 0.35]), _acts(t, [0.5, 0.6, 0.5]))
        out, regions = apply_flash_guard(ch)
        np.testing.assert_allclose(out.volume.p, [0.3, 0.4, 0.35])
        assert regions == []


class TestRegionReport:
    def test_region_dict_is_json_friendly(self):
        t = [0.0, 1.0, 2.0]
        ch = _channels(_acts(t, [0.5, 1.0, 1.0]), _acts(t, [0.5, 1.0, 1.0]))
        _out, regions = apply_flash_guard(ch)
        d = regions[0].as_dict()
        assert set(d) == {"start_s", "end_s", "reason", "peak_volume"}
        assert d["reason"] == "co_rail"
        assert isinstance(d["start_s"], float)

    def test_vol_rail_constant_is_sane(self):
        assert 0.5 < FLASH_VOL_CAP < VOL_RAIL <= 1.0
