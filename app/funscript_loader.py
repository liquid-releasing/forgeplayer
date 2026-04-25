# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Funscript file loader + 1D→2D radial conversion.

The Stim slot in v0.0.2 plays funscripts via the vendored restim stim_math
synthesis engine. Two input paths feed into the same channel carrier:

  - **Native stereostim / FOC-content**: scene folder has
    `{stem}.alpha.funscript` + `{stem}.beta.funscript` (and optionally
    `frequency`, `pulse_frequency`, `pulse_width`, `pulse_rise_time`,
    `volume`). Loaded directly — no conversion.

  - **Legacy 2b / mechanical**: scene folder has only `{stem}.funscript`
    (1-D position). We run a radial-half-circle conversion (per restim's
    `funscript_1d_to_2d.py`) to synthesize alpha + beta sample arrays.
    Optional parameter channels load the same way as the native path if
    present alongside the 1D file.

Both paths produce a `StimChannels` record carrying dense alpha/beta
sample arrays plus optional parameter channels in their sparse action
form. The synth driver ([app/stim_synth.py](app/stim_synth.py)) decides
between continuous and pulse-based synthesis based on which parameter
channels are present and rescales values from funscript-space 0..1 to
each parameter's native axis range.

See `docs/architecture/stim-synthesis.md` for the full device-support
matrix and the channel consumption table.

Position values throughout are normalized to floats in the natural
funscript range (0.0 .. 1.0 maps to the 0..100 integer `pos` field on
disk). Times are seconds.

The radial conversion is a port of `restim/funscript_1d_to_2d.py` at the
pinned commit (see `app/vendor/restim_stim_math/VERSION`). The math is
small and pure; we reimplement here rather than vendoring a non-stim_math
file so the vendor boundary stays clean.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from app.library.catalog import FunscriptSet


@dataclass(frozen=True)
class FunscriptActions:
    """Sparse action samples loaded from a single .funscript file.

    `t` is times in seconds (float64). `p` is positions normalized to
    0.0–1.0 (float64). Same length. Sorted by time, ascending.
    """
    t: np.ndarray
    p: np.ndarray


@dataclass(frozen=True)
class StimChannels:
    """Channel set ready for one stim synth instance.

    `t` + `alpha` + `beta` are the required dense arrays that carry
    position data (from either the native stereostim path or radial
    1D→2D conversion). All other channels are optional; a `None` field
    means "use the synth's per-parameter default constant."

    Parameter channels stay in sparse `FunscriptActions` form and are
    rescaled + turned into precomputed axes by the synth driver — each
    channel has its own native axis range (see
    `docs/architecture/stim-synthesis.md`).
    """
    # Required dense arrays (shared time axis)
    t: np.ndarray
    alpha: np.ndarray
    beta: np.ndarray
    source: Literal["radial_1d", "native_stereostim"]

    # Optional parameter channels (raw action form)
    volume: FunscriptActions | None = None
    carrier_frequency: FunscriptActions | None = None
    pulse_frequency: FunscriptActions | None = None
    pulse_width: FunscriptActions | None = None
    pulse_rise_time: FunscriptActions | None = None

    @property
    def has_pulse_params(self) -> bool:
        """True when any `pulse_*` channel is present.

        The synth driver uses this to dispatch between the continuous
        waveform algorithm (no pulse shaping) and the pulse-based
        algorithm (shaped discrete pulses driven by pulse_frequency /
        pulse_width / pulse_rise_time).
        """
        return any(
            p is not None
            for p in (self.pulse_frequency, self.pulse_width, self.pulse_rise_time)
        )


def load_funscript(path: str | Path) -> FunscriptActions:
    """Parse a `.funscript` (JSON) into a `FunscriptActions` record.

    Empty action lists return zero-length arrays — caller decides how to
    handle a silent funscript (likely: skip the slot).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    actions = data.get("actions") or []
    if not actions:
        return FunscriptActions(t=np.zeros(0), p=np.zeros(0))

    t = np.fromiter((float(a["at"]) / 1000.0 for a in actions), dtype=np.float64)
    p = np.fromiter((float(a["pos"]) * 0.01 for a in actions), dtype=np.float64)

    if not np.all(np.diff(t) >= 0):
        order = np.argsort(t, kind="stable")
        t = t[order]
        p = p[order]

    return FunscriptActions(t=t, p=p)


def radial_1d_to_2d(
    actions: FunscriptActions,
    points_per_second: int = 25,
) -> StimChannels:
    """Convert a 1-D position funscript into dense alpha+beta arrays.

    Between every consecutive action pair `(start_t, start_p) → (end_t, end_p)`
    the position traces a half-circle in the alpha/beta plane:

        alpha = center + r·cos(θ)        θ ∈ [0, π)
        beta  = r·sin(θ) + 0.5
        center = (start_p + end_p) / 2
        r      = (start_p - end_p) / 2

    Sampled at `points_per_second` between each pair (minimum 1 sample).
    The final action's instant is not emitted — the next pair picks it up.
    """
    src_t = actions.t
    src_p = actions.p
    if src_t.size < 2:
        return StimChannels(
            t=np.zeros(0), alpha=np.zeros(0), beta=np.zeros(0),
            source="radial_1d",
        )

    t_chunks: list[np.ndarray] = []
    a_chunks: list[np.ndarray] = []
    b_chunks: list[np.ndarray] = []

    for i in range(src_t.size - 1):
        start_t = src_t[i]
        end_t = src_t[i + 1]
        start_p = src_p[i]
        end_p = src_p[i + 1]
        dt = end_t - start_t
        n = int(np.clip(dt * points_per_second, 1, None))

        local_t = np.linspace(0.0, dt, n, endpoint=False)
        theta = np.linspace(0.0, np.pi, n, endpoint=False)
        center = (start_p + end_p) / 2.0
        r = (start_p - end_p) / 2.0

        t_chunks.append(local_t + start_t)
        a_chunks.append(center + r * np.cos(theta))
        b_chunks.append(r * np.sin(theta) + 0.5)

    return StimChannels(
        t=np.concatenate(t_chunks),
        alpha=np.concatenate(a_chunks),
        beta=np.concatenate(b_chunks),
        source="radial_1d",
    )


def load_stim_channels(
    funscript_set: FunscriptSet,
    *,
    prostate: bool = False,
) -> StimChannels | None:
    """Build a `StimChannels` for the main or prostate stim synth.

    When `prostate=False` (default), loads the scene's main-stim channels
    — the `-prostate`-less channel names, falling back to radial 1D→2D
    from the main `.funscript` if explicit alpha+beta aren't present.

    When `prostate=True`, loads `alpha-prostate` / `beta-prostate` /
    `volume-prostate`. Returns **None** (no synth needed) when those
    aren't present — the main `.funscript` is NOT used as a 1D fallback
    for the prostate pair, it's scripted for the primary electrode pair.

    Carrier + pulse-shape channels (`frequency`, `pulse_frequency`,
    `pulse_width`, `pulse_rise_time`) are scene-wide — both main and
    prostate synths read them from the same plain-named funscripts. Only
    alpha/beta/volume diverge via the `-prostate` suffix. This matches
    what FunscriptForge emits (Euphoria ships `volume-prostate` but no
    `pulse_frequency-prostate`).

    Raises `ValueError` for the main path when the set has no playable
    position source — caller should have already filtered via
    `FunscriptSet.supported_generations`.
    """
    alpha_name = "alpha-prostate" if prostate else "alpha"
    beta_name = "beta-prostate" if prostate else "beta"
    volume_name = "volume-prostate" if prostate else "volume"

    alpha_path = funscript_set.channels.get(alpha_name)
    beta_path = funscript_set.channels.get(beta_name)

    if alpha_path and beta_path:
        a = load_funscript(alpha_path)
        b = load_funscript(beta_path)
        if a.t.size == 0 or b.t.size == 0:
            raise ValueError(
                f"Native stereostim funscripts are empty: "
                f"alpha={alpha_path}, beta={beta_path}"
            )
        t = np.unique(np.concatenate([a.t, b.t]))
        alpha_dense = np.interp(t, a.t, a.p)
        beta_dense = np.interp(t, b.t, b.p)
        source: Literal["radial_1d", "native_stereostim"] = "native_stereostim"
    elif prostate:
        return None
    elif funscript_set.main_path:
        actions = load_funscript(funscript_set.main_path)
        if actions.t.size < 2:
            raise ValueError(
                f"Main funscript has fewer than 2 actions, can't synthesize: "
                f"{funscript_set.main_path}"
            )
        radial = radial_1d_to_2d(actions)
        t = radial.t
        alpha_dense = radial.alpha
        beta_dense = radial.beta
        source = "radial_1d"
    else:
        raise ValueError(
            f"FunscriptSet has no playable channels (need alpha+beta or main): "
            f"{funscript_set.base_stem}"
        )

    def _opt(name: str) -> FunscriptActions | None:
        path = funscript_set.channels.get(name)
        if not path:
            return None
        actions = load_funscript(path)
        return actions if actions.t.size > 0 else None

    return StimChannels(
        t=t,
        alpha=alpha_dense,
        beta=beta_dense,
        source=source,
        volume=_opt(volume_name),
        carrier_frequency=_opt("frequency"),
        pulse_frequency=_opt("pulse_frequency"),
        pulse_width=_opt("pulse_width"),
        pulse_rise_time=_opt("pulse_rise_time"),
    )
