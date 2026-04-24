# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the funscript loader + radial 1D→2D conversion."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.funscript_loader import (
    FunscriptActions,
    StimChannels,
    load_funscript,
    load_stim_channels,
    radial_1d_to_2d,
)
from app.library.catalog import FunscriptSet


def _write_funscript(path: Path, actions: list[tuple[int, int]]) -> None:
    """Write a minimal `.funscript` JSON file. `actions` is [(at_ms, pos_0_100), ...]."""
    path.write_text(json.dumps({
        "actions": [{"at": at, "pos": pos} for at, pos in actions]
    }), encoding="utf-8")


# ── load_funscript ────────────────────────────────────────────────────────────

class TestLoadFunscript:
    def test_basic_load(self, tmp_path: Path):
        path = tmp_path / "test.funscript"
        _write_funscript(path, [(0, 0), (500, 100), (1000, 50)])

        actions = load_funscript(path)

        assert isinstance(actions, FunscriptActions)
        np.testing.assert_array_almost_equal(actions.t, [0.0, 0.5, 1.0])
        np.testing.assert_array_almost_equal(actions.p, [0.0, 1.0, 0.5])

    def test_empty_actions(self, tmp_path: Path):
        path = tmp_path / "empty.funscript"
        _write_funscript(path, [])

        actions = load_funscript(path)

        assert actions.t.size == 0
        assert actions.p.size == 0

    def test_missing_actions_key(self, tmp_path: Path):
        path = tmp_path / "no_actions.funscript"
        path.write_text(json.dumps({"metadata": {}}), encoding="utf-8")

        actions = load_funscript(path)

        assert actions.t.size == 0

    def test_unsorted_actions_get_sorted(self, tmp_path: Path):
        path = tmp_path / "unsorted.funscript"
        _write_funscript(path, [(1000, 80), (0, 20), (500, 50)])

        actions = load_funscript(path)

        np.testing.assert_array_almost_equal(actions.t, [0.0, 0.5, 1.0])
        np.testing.assert_array_almost_equal(actions.p, [0.2, 0.5, 0.8])

    def test_pos_normalized_to_unit_range(self, tmp_path: Path):
        path = tmp_path / "range.funscript"
        _write_funscript(path, [(0, 0), (1000, 100)])

        actions = load_funscript(path)

        assert actions.p[0] == 0.0
        assert actions.p[1] == 1.0


# ── radial_1d_to_2d ───────────────────────────────────────────────────────────

class TestRadial1dTo2d:
    def test_too_few_actions_returns_empty(self):
        actions = FunscriptActions(t=np.array([0.0]), p=np.array([0.5]))

        ch = radial_1d_to_2d(actions)

        assert ch.t.size == 0
        assert ch.alpha.size == 0
        assert ch.beta.size == 0
        assert ch.source == "radial_1d"

    def test_simple_two_action_segment_shape(self):
        # Stroke from pos=0.0 at t=0 to pos=1.0 at t=1s.
        # center = 0.5, r = -0.5.
        # alpha[0] = center + r·cos(0) = 0.5 + (-0.5)·1   = 0.0   (start)
        # beta[0]  = r·sin(0) + 0.5    = (-0.5)·0 + 0.5  = 0.5   (mid)
        # Half-way through (θ=π/2): alpha=center=0.5, beta=0.5 - 0.5 = 0.0
        actions = FunscriptActions(t=np.array([0.0, 1.0]), p=np.array([0.0, 1.0]))

        ch = radial_1d_to_2d(actions, points_per_second=25)

        assert ch.t.size == 25
        assert ch.alpha.size == 25
        assert ch.beta.size == 25
        # Start point: alpha = start_p, beta = 0.5
        assert ch.alpha[0] == pytest.approx(0.0, abs=1e-9)
        assert ch.beta[0] == pytest.approx(0.5, abs=1e-9)
        # Half-circle peak (θ=π/2): alpha at center, beta at 0.5+r·1 = 0.0
        mid_idx = 25 // 2
        assert ch.alpha[mid_idx] == pytest.approx(0.5, abs=0.05)
        # beta dips to ~0.0 because r is negative and sin(π/2)=1
        assert ch.beta[mid_idx] == pytest.approx(0.0, abs=0.05)

    def test_density_matches_points_per_second(self):
        actions = FunscriptActions(t=np.array([0.0, 4.0]), p=np.array([0.0, 1.0]))
        ch = radial_1d_to_2d(actions, points_per_second=25)
        # 4 seconds × 25 pps = 100 samples (endpoint=False, single segment)
        assert ch.t.size == 100

    def test_minimum_one_sample_per_segment(self):
        # Two actions 1 ms apart — too short for the rate but should still
        # produce at least one sample so we never lose actions.
        actions = FunscriptActions(t=np.array([0.0, 0.001]), p=np.array([0.0, 1.0]))
        ch = radial_1d_to_2d(actions, points_per_second=25)
        assert ch.t.size >= 1

    def test_times_are_monotonic_and_offset_correctly(self):
        actions = FunscriptActions(
            t=np.array([0.0, 1.0, 2.0]),
            p=np.array([0.2, 0.8, 0.4]),
        )
        ch = radial_1d_to_2d(actions, points_per_second=10)

        # Times should be non-decreasing and start at the first action's time
        assert ch.t[0] == pytest.approx(0.0)
        assert np.all(np.diff(ch.t) >= 0)
        # Last time should be inside the last segment, before final action's t
        assert ch.t[-1] < actions.t[-1]

    def test_source_label(self):
        actions = FunscriptActions(t=np.array([0.0, 1.0]), p=np.array([0.0, 1.0]))
        ch = radial_1d_to_2d(actions)
        assert ch.source == "radial_1d"


# ── load_stim_channels ────────────────────────────────────────────────────────

class TestLoadStimChannels:
    def test_native_stereostim_path(self, tmp_path: Path):
        alpha = tmp_path / "scene.alpha.funscript"
        beta = tmp_path / "scene.beta.funscript"
        _write_funscript(alpha, [(0, 0), (1000, 100)])
        _write_funscript(beta, [(0, 50), (1000, 50)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={"alpha": str(alpha), "beta": str(beta)},
        )

        ch = load_stim_channels(fs)

        assert ch.source == "native_stereostim"
        # Time axis should cover both files; stereostim files share times here
        assert ch.t[0] == pytest.approx(0.0)
        assert ch.t[-1] == pytest.approx(1.0)
        # Native channels are kept verbatim (interp on union times)
        assert ch.alpha[0] == pytest.approx(0.0)
        assert ch.alpha[-1] == pytest.approx(1.0)
        assert ch.beta[0] == pytest.approx(0.5)
        assert ch.beta[-1] == pytest.approx(0.5)

    def test_native_stereostim_unioned_times(self, tmp_path: Path):
        # Alpha and beta with mismatched action times — loader should
        # interpolate each onto the union of times.
        alpha = tmp_path / "scene.alpha.funscript"
        beta = tmp_path / "scene.beta.funscript"
        _write_funscript(alpha, [(0, 0), (1000, 100)])
        _write_funscript(beta, [(500, 50)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={"alpha": str(alpha), "beta": str(beta)},
        )

        ch = load_stim_channels(fs)

        # Union of times: [0.0, 0.5, 1.0]
        assert ch.t.size == 3
        np.testing.assert_array_almost_equal(ch.t, [0.0, 0.5, 1.0])
        # Beta is constant 0.5 (single-action), so np.interp pads
        np.testing.assert_array_almost_equal(ch.beta, [0.5, 0.5, 0.5])
        # Alpha linearly interpolated: 0.0 → 0.5 → 1.0
        np.testing.assert_array_almost_equal(ch.alpha, [0.0, 0.5, 1.0])

    def test_legacy_2b_radial_fallback(self, tmp_path: Path):
        main = tmp_path / "scene.funscript"
        _write_funscript(main, [(0, 0), (500, 100), (1000, 0)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=str(main),
            channels={},
        )

        ch = load_stim_channels(fs)

        assert ch.source == "radial_1d"
        assert ch.t.size > 0

    def test_alpha_only_falls_back_to_main(self, tmp_path: Path):
        """If only one of alpha/beta is present, we fall back to main funscript
        (radial 1D→2D). The picker should have surfaced the missing channel."""
        alpha = tmp_path / "scene.alpha.funscript"
        main = tmp_path / "scene.funscript"
        _write_funscript(alpha, [(0, 0), (1000, 100)])
        _write_funscript(main, [(0, 0), (1000, 100)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=str(main),
            channels={"alpha": str(alpha)},
        )

        ch = load_stim_channels(fs)

        assert ch.source == "radial_1d"

    def test_empty_set_raises(self):
        fs = FunscriptSet(base_stem="empty", main_path=None, channels={})
        with pytest.raises(ValueError, match="no playable channels"):
            load_stim_channels(fs)

    def test_main_with_one_action_raises(self, tmp_path: Path):
        main = tmp_path / "scene.funscript"
        _write_funscript(main, [(0, 50)])

        fs = FunscriptSet(base_stem="scene", main_path=str(main), channels={})

        with pytest.raises(ValueError, match="fewer than 2 actions"):
            load_stim_channels(fs)

    def test_native_stereostim_with_empty_file_raises(self, tmp_path: Path):
        alpha = tmp_path / "scene.alpha.funscript"
        beta = tmp_path / "scene.beta.funscript"
        _write_funscript(alpha, [(0, 0), (1000, 100)])
        _write_funscript(beta, [])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={"alpha": str(alpha), "beta": str(beta)},
        )

        with pytest.raises(ValueError, match="empty"):
            load_stim_channels(fs)
