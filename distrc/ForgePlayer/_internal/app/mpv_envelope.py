# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Volume envelope for stim audio that plays through mpv.

Why this exists: seeking is hidden behind a ramp-down → settle → ramp-up
envelope so the user never feels the discontinuity at the splice
(`ControlWindow._seek_with_envelope`). That envelope was applied only to
`StimAudioStream` — the live synth — because it's the synth that owns its own
sample generation and can fade itself.

But a scene whose stim is a **pre-rendered sound file** plays through mpv
instead (H1's audio-file dispatch, and the H2 mirror of it). Those have no
`StimAudioStream`, so the envelope skipped them entirely and the seek landed
raw: mpv resumed at an arbitrary point in the waveform, and the discontinuity
came out of the dongle as a pop. That's exactly why sound-file scenes popped on
±10 s / chapter / seek-bar moves while funscript scenes didn't (user report,
2026-08-29).

mpv has no fade primitive of its own, so this steps its software `volume`
property on a timer. Two details matter for it to be inaudible:

- **Cosine easing**, not linear. The audible part of a fade is its endpoints;
  a linear ramp corners at both ends and that corner is itself a click.
- **Fine ticks** (10 ms). Coarse steps are a staircase, and a staircase in gain
  is zipper noise.

Volume is expressed as a *gain* (0.0-1.0) applied to whatever each player's
volume was when the ramp started, so a user's own volume setting survives a
seek instead of being reset to 100.

Deliberately Qt-free: `ControlWindow` owns the QTimer that calls `tick()`, and
tests drive `tick()` directly instead of waiting on real time.
"""
from __future__ import annotations

import math
from typing import Iterable

# Tick interval for the driving timer. 10 ms over a 500 ms ramp is 50 steps —
# fine enough that the gain staircase stays under the noise floor.
TICK_MS = 10


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class MpvVolumeEnvelope:
    """Ramps a set of mpv players' volume toward a target gain over time.

    Mirrors `StimAudioStream.request_envelope(target, seconds)` so the seek path
    can drive synth streams and mpv-backed stim with one shape of call.
    """

    def __init__(self) -> None:
        # id(player) -> (player, baseline_volume). Keyed by id so a player that
        # disappears mid-ramp can be dropped without needing it to be hashable.
        self._tracked: dict[int, tuple[object, float]] = {}
        self._gain = 1.0
        self._from = 1.0
        self._to = 1.0
        self._elapsed = 0.0
        self._duration = 0.0

    @property
    def gain(self) -> float:
        return self._gain

    def busy(self) -> bool:
        """True while a ramp is still in flight."""
        return self._elapsed < self._duration

    def tracks_anything(self) -> bool:
        return bool(self._tracked)

    def request(
        self, players: Iterable[object], target: float, seconds: float,
    ) -> None:
        """Ramp *players* from the current gain to *target* over *seconds*.

        Re-requesting mid-ramp is fine and is what a second seek does: the new
        ramp starts from wherever the gain currently is, so the volume never
        jumps.
        """
        self._retrack(players)
        self._from = self._gain
        self._to = _clamp01(target)
        self._duration = max(0.0, seconds)
        self._elapsed = 0.0
        if self._duration == 0.0:
            self._gain = self._to
            self._apply()

    def tick(self, dt_s: float) -> bool:
        """Advance the ramp by *dt_s* and write the new volumes.

        Returns True while more ticks are needed. Driven by real elapsed time
        rather than a fixed per-tick step so timer jitter (or a GUI thread busy
        with a seek) stretches the ramp instead of desyncing it from the synth
        streams ramping alongside it.
        """
        if not self.busy():
            return False
        self._elapsed += max(0.0, dt_s)
        t = 1.0 if self._duration <= 0.0 else min(1.0, self._elapsed / self._duration)
        # Cosine ease-in-out: flat at both ends, so neither the start nor the
        # end of the fade has a corner to click on.
        eased = 0.5 - 0.5 * math.cos(math.pi * t)
        self._gain = self._from + (self._to - self._from) * eased
        self._apply()
        return self.busy()

    def release(self) -> None:
        """Restore every tracked player to its baseline and forget them.

        Used when players are torn down mid-envelope, so a seek interrupted by
        Close can't leave a stale gain behind for a reused instance.
        """
        self._gain = 1.0
        self._from = self._to = 1.0
        self._elapsed = self._duration = 0.0
        self._apply()
        self._tracked.clear()

    # ── internals ────────────────────────────────────────────────────────────

    def _retrack(self, players: Iterable[object]) -> None:
        """Adopt the current player set, keeping baselines already captured."""
        seen: dict[int, tuple[object, float]] = {}
        for p in players:
            key = id(p)
            if key in self._tracked:
                seen[key] = self._tracked[key]
                continue
            seen[key] = (p, self._read_baseline(p))
        self._tracked = seen

    def _read_baseline(self, player: object) -> float:
        """The volume this player should return to at gain 1.0.

        Read from the player itself so a user's own volume setting is preserved.
        A player adopted *mid-duck* can't be read that way (its current volume
        is already scaled), so it falls back to full — the same value a freshly
        launched mpv instance has.
        """
        if self._gain < 1.0:
            return 100.0
        try:
            value = float(player.volume)  # type: ignore[attr-defined]
        except Exception:
            return 100.0
        return value if value > 0.0 else 100.0

    def _apply(self) -> None:
        for key, (player, baseline) in list(self._tracked.items()):
            try:
                player.volume = max(  # type: ignore[attr-defined]
                    0, min(100, round(baseline * self._gain)),
                )
            except Exception:
                # Player terminated mid-ramp (Close during a seek). Drop it
                # rather than raising into the timer that's driving the fade.
                self._tracked.pop(key, None)
