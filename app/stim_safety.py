# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Runtime safety guard against e-stim "flash" glitches.

A brief loud/clipped moment in the source audio can drive the e-stim
channels to command **near-max carrier frequency and near-max volume at
the same instant** — felt by the user as a painful electrical flash (see
`funscriptforge/internal/screech_safety_architecture.md`). The generator
should not produce that, but already-shipped scripts can contain it, so
the player enforces a last line of defense at load time.

This module is a pure function over `StimChannels`: it returns a copy with
the dangerous spikes tamed plus a list of the regions it touched (for the
sidecar report / UI markers). It is deliberately conservative — a genuine
artistic build (volume rising over seconds, or sustained loud passages) is
left alone; only the glitch signature is clamped.

The safety invariant (shared with the generator-side cap):

    The device must never be commanded to near-max carrier frequency AND
    near-max volume simultaneously as a sudden jump. A sweep of one
    parameter with the other steady is allowed; a fast co-rail of both is
    the glitch signature and is clamped/ramped.

Note: in continuous mode the synth ignores the carrier_frequency funscript
(constant 700 Hz carrier), but we still read that channel here as a
*detector* — a source-audio glitch pushes every channel up at once, so a
co-spike on the frequency channel is a reliable flag even when the carrier
itself is constant.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from app.funscript_loader import FunscriptActions, StimChannels


# ── Tunables (0..1 channel space, before axis rescale) ────────────────────────
# "Near-max" rails. Set HIGH on purpose: in an intense scene the channels sit
# near-max for large stretches *by design* (measured on VictoriaOaks: volume is
# >=0.99 in 19% of samples, frequency >=0.99 in 10%). Clamping merely-loud
# content would audibly neuter the scene. Only when BOTH channels are pinned at
# the absolute ceiling at the same instant is it a genuine co-max anomaly — that
# band is rare (~8 points across a 93-min file) and is exactly the "errant near
# max frequency AND near max volume" we must never play. This guard is a
# conservative BACKSTOP; the primary screech defense is upstream (de-screech
# before analysis + the generator-side cap), where a clipped audio moment is
# still distinguishable from intended intensity. See
# funscriptforge/internal/screech_safety_architecture.md.
VOL_RAIL = 0.99
FREQ_RAIL = 0.99
# When volume AND frequency are both railed at the same instant, cap volume to
# this ceiling so the *combination* is never at absolute max.
FLASH_VOL_CAP = 0.88
# Slew limit on volume RISE: a 0→1 jump must take at least this long. Protects
# against a near-instantaneous amplitude discontinuity (the "jolt"). Normal
# strokes (~110 ms spacing, ~8/s rate) pass untouched; falls are unconstrained
# (dropping volume fast is always safe).
MIN_RISE_TIME_S = 0.040
# Co-rail regions shorter than this are reported but still capped; this only
# governs how adjacent capped samples are merged into one reported region.
REGION_MERGE_GAP_S = 0.150


@dataclass(frozen=True)
class FlashRegion:
    """A span the guard modified, for the sidecar report / UI markers."""

    start_s: float
    end_s: float
    reason: str  # "co_rail" | "slew"
    peak_volume: float  # max volume (0..1) seen in the span before clamping

    def as_dict(self) -> dict:
        return {
            "start_s": round(float(self.start_s), 3),
            "end_s": round(float(self.end_s), 3),
            "reason": self.reason,
            "peak_volume": round(float(self.peak_volume), 3),
        }


def apply_flash_guard(channels: StimChannels) -> tuple[StimChannels, list[FlashRegion]]:
    """Return a safety-clamped copy of `channels` + the regions touched.

    Operates only on the `volume` channel (the felt intensity), reading
    `carrier_frequency` as a co-detector. If there is no volume channel
    there is nothing to clamp, so the input is returned unchanged.
    """
    vol = channels.volume
    if vol is None or vol.t.size == 0:
        return channels, []

    t = np.asarray(vol.t, dtype=np.float64)
    p = np.asarray(vol.p, dtype=np.float64).copy()
    original = p.copy()

    # Frequency value sampled onto the volume timestamps (constant-0.5 stand-in
    # when absent, which never reaches FREQ_RAIL → co-rail can't false-trigger).
    freq = _sample_on(channels.carrier_frequency, t, default=0.5)

    # 1) Co-rail cap: both channels railed at the same instant.
    co_rail = (p >= VOL_RAIL) & (freq >= FREQ_RAIL)
    p = np.where(co_rail, np.minimum(p, FLASH_VOL_CAP), p)

    # 2) Slew limit on rise: walk forward, clamp how fast volume may climb.
    slew_touched = _limit_rise(t, p, MIN_RISE_TIME_S)

    touched = co_rail | slew_touched
    regions = _regions_from_mask(t, touched, co_rail, original)

    if not regions:
        return channels, []

    new_channels = dataclasses.replace(
        channels, volume=FunscriptActions(t=vol.t, p=p.astype(vol.p.dtype, copy=False))
    )
    return new_channels, regions


# ── helpers ───────────────────────────────────────────────────────────────────

def _sample_on(
    actions: FunscriptActions | None, t: np.ndarray, *, default: float
) -> np.ndarray:
    """Interpolate `actions` (0..1) onto times `t`; constant `default` if absent."""
    if actions is None or actions.t.size == 0:
        return np.full(t.shape, default, dtype=np.float64)
    return np.interp(
        t,
        np.asarray(actions.t, dtype=np.float64),
        np.asarray(actions.p, dtype=np.float64),
    )


def _limit_rise(t: np.ndarray, p: np.ndarray, min_rise_time_s: float) -> np.ndarray:
    """In-place clamp of upward slope so a full-scale rise takes >= min_rise_time_s.

    Returns a boolean mask of samples that were pulled down by the limiter.
    """
    if p.size < 2 or min_rise_time_s <= 0.0:
        return np.zeros(p.shape, dtype=bool)
    max_rate = 1.0 / float(min_rise_time_s)  # units of volume per second
    touched = np.zeros(p.shape, dtype=bool)
    for i in range(1, p.size):
        dt = t[i] - t[i - 1]
        if dt <= 0.0:
            continue
        ceiling = p[i - 1] + max_rate * dt
        if p[i] > ceiling:
            p[i] = ceiling
            touched[i] = True
    return touched


def _regions_from_mask(
    t: np.ndarray,
    touched: np.ndarray,
    co_rail: np.ndarray,
    original: np.ndarray,
) -> list[FlashRegion]:
    """Merge touched samples into contiguous reported regions."""
    if not touched.any():
        return []
    idx = np.flatnonzero(touched)
    regions: list[FlashRegion] = []
    run_start = idx[0]
    prev = idx[0]
    for j in idx[1:]:
        if t[j] - t[prev] > REGION_MERGE_GAP_S:
            regions.append(_make_region(t, run_start, prev, co_rail, original))
            run_start = j
        prev = j
    regions.append(_make_region(t, run_start, prev, co_rail, original))
    return regions


def _make_region(
    t: np.ndarray, lo: int, hi: int, co_rail: np.ndarray, original: np.ndarray
) -> FlashRegion:
    reason = "co_rail" if co_rail[lo : hi + 1].any() else "slew"
    return FlashRegion(
        start_s=float(t[lo]),
        end_s=float(t[hi]),
        reason=reason,
        peak_volume=float(original[lo : hi + 1].max()),
    )
