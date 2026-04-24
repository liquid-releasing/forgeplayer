# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Funscript file loader + 1D→2D radial conversion.

The Stim slot in v0.0.2 plays funscripts via the vendored restim stim_math
synthesis engine. Two input paths feed the same `ThreePhaseAlgorithm`:

  - **Native stereostim**: scene folder has `{stem}.alpha.funscript` +
    `{stem}.beta.funscript`. We load both and feed alpha/beta arrays
    directly — no conversion.

  - **Legacy 2b / mechanical**: scene folder has only `{stem}.funscript`
    (1-D position). We run a radial-half-circle conversion (per restim's
    `funscript_1d_to_2d.py`) to synthesize alpha + beta sample arrays.

Both paths produce a `StimChannels` record holding dense `(t, alpha, beta)`
arrays that the synth driver feeds into restim's `WriteProtectedAxis`.

Position values throughout are normalized to floats in the natural funscript
range (0.0 .. 1.0 maps to the 0..100 integer `pos` field on disk). Times
are seconds.

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
    """Dense alpha + beta arrays ready for the threephase synthesis engine.

    Both arrays share the same `t` time base. `source` records which path
    produced them so the synth driver / debug log can tell legacy 2b
    apart from native stereostim.
    """
    t: np.ndarray
    alpha: np.ndarray
    beta: np.ndarray
    source: Literal["radial_1d", "native_stereostim"]


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


def load_stim_channels(funscript_set: FunscriptSet) -> StimChannels:
    """Load alpha+beta from a FunscriptSet, picking the right path.

    Picks native stereostim if both `alpha.funscript` and `beta.funscript`
    are present; else falls back to radial 1-D→2-D from the main funscript.

    Raises `ValueError` if the set has neither path — caller should have
    already filtered via `FunscriptSet.supported_generations`.

    Subchannel-modified channels (`alpha-stereostim`, `alpha-prostate`)
    are not consumed here. The select picker collapses the user's chosen
    generation variant down to plain `alpha` / `beta` channel names before
    we reach this loader (per docs/architecture/restim-channels.md).
    Prostate is a separate slot and goes through this same loader against
    a FunscriptSet whose channels were filtered to the prostate variants.
    """
    alpha_path = funscript_set.channels.get("alpha")
    beta_path = funscript_set.channels.get("beta")
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
        return StimChannels(
            t=t, alpha=alpha_dense, beta=beta_dense,
            source="native_stereostim",
        )

    if funscript_set.main_path:
        actions = load_funscript(funscript_set.main_path)
        if actions.t.size < 2:
            raise ValueError(
                f"Main funscript has fewer than 2 actions, can't synthesize: "
                f"{funscript_set.main_path}"
            )
        return radial_1d_to_2d(actions)

    raise ValueError(
        f"FunscriptSet has no playable channels (need alpha+beta or main): "
        f"{funscript_set.base_stem}"
    )
