# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""The seek-time volume envelope for stim that plays through mpv.

Scenes whose stim is a pre-rendered sound file play through mpv, not through a
StimAudioStream, so the seek envelope skipped them and the seek landed raw —
an audible pop on the stim line, present on sound files and absent on
funscripts (user report, 2026-08-29, chased for a long time before that).

These drive `tick()` directly rather than waiting on the real timer, so the
shape of the fade is asserted exactly instead of approximately.
"""
from __future__ import annotations

import pytest

from app.mpv_envelope import MpvVolumeEnvelope


class _FakePlayer:
    def __init__(self, volume: float = 100.0) -> None:
        self.volume = volume
        self.history: list[float] = []

    def __setattr__(self, name, value):
        if name == "volume" and "history" in self.__dict__:
            self.__dict__["history"].append(value)
        super().__setattr__(name, value)


def _run(env: MpvVolumeEnvelope, seconds: float, step: float = 0.01) -> None:
    ticks = int(round(seconds / step))
    for _ in range(ticks):
        env.tick(step)


def test_ramp_down_reaches_silence():
    p = _FakePlayer()
    env = MpvVolumeEnvelope()
    env.request([p], 0.0, 0.5)

    _run(env, 0.5)

    assert env.gain == pytest.approx(0.0, abs=1e-6)
    assert p.volume == 0


def test_ramp_up_restores_the_users_own_volume():
    """A seek must not reset volume to full for someone who set it to 60."""
    p = _FakePlayer(volume=60.0)
    env = MpvVolumeEnvelope()

    env.request([p], 0.0, 0.5)
    _run(env, 0.5)
    assert p.volume == 0

    env.request([p], 1.0, 0.5)
    _run(env, 0.5)

    assert p.volume == 60


def test_fade_is_monotonic_and_gentle_at_the_ends():
    """Cosine easing, not linear: the endpoints are where a fade clicks."""
    p = _FakePlayer()
    env = MpvVolumeEnvelope()
    env.request([p], 0.0, 0.5)
    _run(env, 0.5)

    steps = p.history
    assert steps == sorted(steps, reverse=True), "gain must never rise mid-fade"
    first_delta = steps[0] - steps[1]
    middle = len(steps) // 2
    mid_delta = steps[middle] - steps[middle + 1]
    assert first_delta < mid_delta, "the fade should start flat, not corner"


def test_second_seek_mid_fade_continues_from_where_it_is():
    """Rapid ±10 s clicks must not make the volume jump."""
    p = _FakePlayer()
    env = MpvVolumeEnvelope()
    env.request([p], 0.0, 0.5)
    _run(env, 0.25)
    mid = env.gain
    assert 0.0 < mid < 1.0

    env.request([p], 1.0, 0.5)
    assert env.gain == pytest.approx(mid), "no jump at the hand-off"
    _run(env, 0.5)
    assert p.volume == 100


def test_player_terminated_mid_fade_is_dropped_not_raised():
    """Close during a seek kills mpv out from under the running fade."""
    class _Dead:
        @property
        def volume(self):
            return 100.0

        @volume.setter
        def volume(self, _value):
            raise RuntimeError("mpv core has been destroyed")

    env = MpvVolumeEnvelope()
    env.request([_Dead()], 0.0, 0.5)

    _run(env, 0.5)  # must not raise

    assert not env.tracks_anything()


def test_release_restores_baselines_and_forgets_players():
    p = _FakePlayer(volume=80.0)
    env = MpvVolumeEnvelope()
    env.request([p], 0.0, 0.5)
    _run(env, 0.25)

    env.release()

    assert p.volume == 80
    assert not env.tracks_anything()
    assert env.gain == 1.0


def test_zero_duration_applies_immediately():
    p = _FakePlayer()
    env = MpvVolumeEnvelope()

    env.request([p], 0.0, 0.0)

    assert p.volume == 0
    assert not env.busy()
