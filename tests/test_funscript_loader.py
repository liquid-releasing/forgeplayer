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
    detect_prostate_source,
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


# ── Parameter channels (volume / carrier / pulse_*) ──────────────────────────

class TestLoadStimChannelsWithParameters:
    def test_loads_volume_channel(self, tmp_path: Path):
        alpha = tmp_path / "scene.alpha.funscript"
        beta = tmp_path / "scene.beta.funscript"
        volume = tmp_path / "scene.volume.funscript"
        _write_funscript(alpha, [(0, 0), (1000, 100)])
        _write_funscript(beta, [(0, 50), (1000, 50)])
        _write_funscript(volume, [(0, 80), (1000, 60)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={"alpha": str(alpha), "beta": str(beta), "volume": str(volume)},
        )

        ch = load_stim_channels(fs)

        assert ch.volume is not None
        np.testing.assert_array_almost_equal(ch.volume.p, [0.8, 0.6])

    def test_loads_full_pulse_based_channel_set(self, tmp_path: Path):
        """Replicate the Euphoria pack shape — alpha/beta + all param channels."""
        names = [
            "alpha", "beta", "frequency", "volume",
            "pulse_frequency", "pulse_width", "pulse_rise_time",
        ]
        channels = {}
        for name in names:
            p = tmp_path / f"scene.{name}.funscript"
            _write_funscript(p, [(0, 50), (1000, 50)])
            channels[name] = str(p)

        fs = FunscriptSet(base_stem="scene", main_path=None, channels=channels)
        ch = load_stim_channels(fs)

        assert ch.carrier_frequency is not None
        assert ch.volume is not None
        assert ch.pulse_frequency is not None
        assert ch.pulse_width is not None
        assert ch.pulse_rise_time is not None
        assert ch.has_pulse_params is True

    def test_alpha_beta_only_has_no_pulse_params(self, tmp_path: Path):
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

        assert ch.has_pulse_params is False
        assert ch.volume is None
        assert ch.carrier_frequency is None

    def test_empty_param_file_treated_as_absent(self, tmp_path: Path):
        """An empty volume funscript should NOT override the default constant.

        FunscriptForge sometimes ships zero-action .funscript files for
        channels the scripter didn't actually author — those shouldn't
        silence the synth.
        """
        alpha = tmp_path / "scene.alpha.funscript"
        beta = tmp_path / "scene.beta.funscript"
        volume = tmp_path / "scene.volume.funscript"
        _write_funscript(alpha, [(0, 0), (1000, 100)])
        _write_funscript(beta, [(0, 50), (1000, 50)])
        _write_funscript(volume, [])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={"alpha": str(alpha), "beta": str(beta), "volume": str(volume)},
        )

        ch = load_stim_channels(fs)

        assert ch.volume is None

    def test_pulse_frequency_alone_flags_pulse_based(self, tmp_path: Path):
        alpha = tmp_path / "scene.alpha.funscript"
        beta = tmp_path / "scene.beta.funscript"
        pf = tmp_path / "scene.pulse_frequency.funscript"
        _write_funscript(alpha, [(0, 0), (1000, 100)])
        _write_funscript(beta, [(0, 50), (1000, 50)])
        _write_funscript(pf, [(0, 30), (1000, 40)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={
                "alpha": str(alpha), "beta": str(beta),
                "pulse_frequency": str(pf),
            },
        )

        ch = load_stim_channels(fs)

        assert ch.has_pulse_params is True


# ── Prostate channel loading ─────────────────────────────────────────────────

class TestLoadStimChannelsProstate:
    def test_prostate_loads_prostate_variants(self, tmp_path: Path):
        ap = tmp_path / "scene.alpha-prostate.funscript"
        bp = tmp_path / "scene.beta-prostate.funscript"
        vp = tmp_path / "scene.volume-prostate.funscript"
        _write_funscript(ap, [(0, 0), (1000, 100)])
        _write_funscript(bp, [(0, 50), (1000, 50)])
        _write_funscript(vp, [(0, 70), (1000, 70)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={
                "alpha-prostate": str(ap),
                "beta-prostate": str(bp),
                "volume-prostate": str(vp),
            },
        )

        ch = load_stim_channels(fs, prostate=True)

        assert ch is not None
        assert ch.source == "native_stereostim"
        np.testing.assert_array_almost_equal(ch.volume.p, [0.7, 0.7])

    def test_prostate_shares_pulse_params_with_main(self, tmp_path: Path):
        """Pulse shape channels are not prostate-suffixed in FunscriptForge
        packs — the prostate synth should read the same plain files the
        main synth reads.
        """
        ap = tmp_path / "scene.alpha-prostate.funscript"
        bp = tmp_path / "scene.beta-prostate.funscript"
        pf = tmp_path / "scene.pulse_frequency.funscript"
        pw = tmp_path / "scene.pulse_width.funscript"
        _write_funscript(ap, [(0, 0), (1000, 100)])
        _write_funscript(bp, [(0, 50), (1000, 50)])
        _write_funscript(pf, [(0, 30), (1000, 40)])
        _write_funscript(pw, [(0, 50), (1000, 50)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={
                "alpha-prostate": str(ap),
                "beta-prostate": str(bp),
                "pulse_frequency": str(pf),
                "pulse_width": str(pw),
            },
        )

        ch = load_stim_channels(fs, prostate=True)

        assert ch is not None
        assert ch.pulse_frequency is not None
        assert ch.pulse_width is not None

    def test_prostate_returns_none_when_no_prostate_channels(self, tmp_path: Path):
        """A main-only scene doesn't spawn a prostate synth."""
        alpha = tmp_path / "scene.alpha.funscript"
        beta = tmp_path / "scene.beta.funscript"
        _write_funscript(alpha, [(0, 0), (1000, 100)])
        _write_funscript(beta, [(0, 50), (1000, 50)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={"alpha": str(alpha), "beta": str(beta)},
        )

        assert load_stim_channels(fs, prostate=True) is None

    def test_prostate_has_no_1d_fallback(self, tmp_path: Path):
        """Even with a main .funscript, prostate=True returns None if
        there's no alpha-prostate — the main 1D is for the primary pair,
        not the prostate pair.
        """
        main = tmp_path / "scene.funscript"
        _write_funscript(main, [(0, 0), (1000, 100)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=str(main),
            channels={},
        )

        assert load_stim_channels(fs, prostate=True) is None

    def test_prostate_alpha_only_synthesizes_beta_zeros(self, tmp_path: Path):
        """Real prostate funscripts in the wild ship `alpha-prostate`
        alone (Euphoria, Zer0 Game). The cascade gates the prostate
        synth on alpha-prostate; beta is synthesized as zeros — correct
        for single-pair prostate hardware where one electrode pair is
        driven and the other is unused.
        """
        ap = tmp_path / "scene.alpha-prostate.funscript"
        _write_funscript(ap, [(0, 0), (1000, 100)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={"alpha-prostate": str(ap)},
        )

        ch = load_stim_channels(fs, prostate=True)

        assert ch is not None
        assert ch.source == "native_stereostim"
        np.testing.assert_array_equal(ch.beta, np.zeros_like(ch.alpha))
        assert ch.alpha.size == ch.beta.size

    def test_prostate_alpha_plus_volume_no_beta(self, tmp_path: Path):
        """Euphoria's actual layout: alpha-prostate + volume-prostate,
        no beta-prostate. Should produce a synth with beta=zeros and the
        volume channel populated.
        """
        ap = tmp_path / "scene.alpha-prostate.funscript"
        vp = tmp_path / "scene.volume-prostate.funscript"
        _write_funscript(ap, [(0, 0), (1000, 100)])
        _write_funscript(vp, [(0, 70), (1000, 70)])

        fs = FunscriptSet(
            base_stem="scene",
            main_path=None,
            channels={
                "alpha-prostate": str(ap),
                "volume-prostate": str(vp),
            },
        )

        ch = load_stim_channels(fs, prostate=True)

        assert ch is not None
        assert ch.source == "native_stereostim"
        np.testing.assert_array_equal(ch.beta, np.zeros_like(ch.alpha))
        np.testing.assert_array_almost_equal(ch.volume.p, [0.7, 0.7])


class TestDetectProstateSourcePerPortResolution:
    """v0.0.4 (revised 2026-05-03): asymmetric per-port resolution.

    `content_preference="sound"` is **authoritative** — no fallback to
    funscript synth. If `<stem>.prostate.wav` is missing, returns
    `kind="none"` so the caller mirrors Haptic 1.

    `content_preference="funscript"` is **best-effort** — falls back to
    `.prostate.wav` if no `alpha-prostate` channel exists; falls back
    to `kind="none"` (mirror H1) only if neither form is available.
    Real prostate scenes ship funscripts without audio; falling back
    to whatever sound exists beats silence in that case.
    """

    def _make_prostate_set(
        self,
        tmp_path: Path,
        *,
        with_audio: bool,
        with_funscript: bool,
    ) -> FunscriptSet:
        ap_path = None
        channels: dict[str, str] = {}
        main_path: str | None = None
        if with_funscript:
            ap = tmp_path / "scene.alpha-prostate.funscript"
            _write_funscript(ap, [(0, 0), (1000, 100)])
            channels["alpha-prostate"] = str(ap)
            ap_path = ap
        if with_audio:
            wav = tmp_path / "scene.prostate.wav"
            # Header-only; detect_prostate_source only checks existence.
            wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        if not channels:
            # detect_prostate_source needs base_dir derivable from
            # main_path or any channel path. With audio-only we still
            # need a hint about which directory to look in — supply
            # main_path pointing at a file we don't actually load.
            main = tmp_path / "scene.funscript"
            _write_funscript(main, [(0, 0)])
            main_path = str(main)
        return FunscriptSet(
            base_stem="scene",
            main_path=main_path,
            channels=channels,
        )

    def test_audio_only_plays_audio_regardless_of_pref(self, tmp_path: Path):
        """Audio-only is unambiguous: sound pref obviously plays it; funscript
        pref falls back to it (best-effort fallback for the funscript path).
        """
        fs = self._make_prostate_set(tmp_path, with_audio=True, with_funscript=False)
        assert detect_prostate_source(fs, "sound").kind == "audio_file"
        assert detect_prostate_source(fs, "funscript").kind == "audio_file"

    def test_funscript_only_with_funscript_pref_plays_funscript(self, tmp_path: Path):
        fs = self._make_prostate_set(tmp_path, with_audio=False, with_funscript=True)
        assert detect_prostate_source(fs, "funscript").kind == "funscripts"

    def test_funscript_only_with_sound_pref_returns_none(self, tmp_path: Path):
        """Sound preference is authoritative: with funscripts available but
        no `.prostate.wav`, do NOT fall back to funscript synth — return
        kind="none" so the caller mirrors H1. Locks in the Euphoria fix
        (2026-05-03 dogfood: user picked sound, got funscript synth, was
        confused — that fallback was wrong).
        """
        fs = self._make_prostate_set(tmp_path, with_audio=False, with_funscript=True)
        assert detect_prostate_source(fs, "sound").kind == "none"

    def test_both_available_sound_pref_picks_audio(self, tmp_path: Path):
        fs = self._make_prostate_set(tmp_path, with_audio=True, with_funscript=True)
        result = detect_prostate_source(fs, "sound")
        assert result.kind == "audio_file"
        assert result.audio_path is not None
        assert result.audio_path.name == "scene.prostate.wav"

    def test_both_available_funscript_pref_picks_funscripts(self, tmp_path: Path):
        fs = self._make_prostate_set(tmp_path, with_audio=True, with_funscript=True)
        assert detect_prostate_source(fs, "funscript").kind == "funscripts"

    def test_neither_returns_none(self, tmp_path: Path):
        fs = self._make_prostate_set(tmp_path, with_audio=False, with_funscript=False)
        assert detect_prostate_source(fs, "sound").kind == "none"
        assert detect_prostate_source(fs, "funscript").kind == "none"

    def test_default_pref_is_sound(self, tmp_path: Path):
        """The function signature defaults to content_preference='sound'.
        Calling without the argument should match the v0.0.3 cascade
        behavior (audio over funscript) for backwards compatibility.
        """
        fs = self._make_prostate_set(tmp_path, with_audio=True, with_funscript=True)
        assert detect_prostate_source(fs).kind == "audio_file"
