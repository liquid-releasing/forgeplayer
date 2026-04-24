# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Test-tone playback — verify a device role actually produces sound.

Generates a short 440 Hz sine wave on first call and caches it at
`~/.forgeplayer/test_tone.wav`. The Setup tab's "🔊 Test" buttons use
this to route a half-second beep to the selected device, so users can
tell at a glance whether:

- The device is reachable (tone plays).
- The device is muted / unreachable at the OS level (tone doesn't play
  despite ForgePlayer routing to it correctly).

Intentionally NOT a full-blown audio-API: we avoid pycaw / Windows Core
Audio bindings in v0.0.1. A single 0.5s tone answers the user's
practical question without adding dependencies.
"""

from __future__ import annotations

import math
import struct
import threading
import wave
from pathlib import Path


_TEST_TONE_PATH = Path.home() / ".forgeplayer" / "test_tone.wav"
_RATE = 44100
_DURATION_SEC = 0.5
_FREQ_HZ = 440
_AMPLITUDE = 14000  # ~0.43 of int16 full-scale — audible but not painful


def ensure_test_tone() -> Path:
    """Return the path to the test tone, creating it if missing.

    20 ms fades in/out avoid the 'click' you'd otherwise hear at the edges.
    Idempotent — safe to call on every Test-button press.
    """
    if _TEST_TONE_PATH.exists():
        return _TEST_TONE_PATH
    _TEST_TONE_PATH.parent.mkdir(parents=True, exist_ok=True)

    total_frames = int(_RATE * _DURATION_SEC)
    fade_frames = int(_RATE * 0.02)  # 20 ms fade

    frames = bytearray()
    for i in range(total_frames):
        # Fade envelope (linear ramp at head/tail)
        if i < fade_frames:
            envelope = i / fade_frames
        elif i > total_frames - fade_frames:
            envelope = (total_frames - i) / fade_frames
        else:
            envelope = 1.0
        sample = int(_AMPLITUDE * envelope * math.sin(2 * math.pi * _FREQ_HZ * i / _RATE))
        frames.extend(struct.pack("<h", sample))

    with wave.open(str(_TEST_TONE_PATH), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_RATE)
        wf.writeframes(bytes(frames))
    return _TEST_TONE_PATH


def play_tone_on_device(audio_device: str) -> None:
    """Fire-and-forget test-tone playback through *audio_device*.

    *audio_device* is an mpv `audio_device` identifier (e.g. the itemData
    from Setup's device-role combobox). Empty string means the role isn't
    configured — no-op.

    Spawns a short-lived mpv instance on a background thread so the Qt UI
    doesn't block on audio device initialization.
    """
    if not audio_device:
        return

    tone_path = ensure_test_tone()

    def _run() -> None:
        try:
            import mpv
        except Exception:
            return
        try:
            p = mpv.MPV(
                audio_device=audio_device,
                force_window="no",
                keep_open=False,
                input_default_bindings=False,
                input_vo_keyboard=False,
                osc=False,
            )
            p.play(str(tone_path))
            # Wait out the tone plus a small margin, then terminate.
            p.wait_for_playback(timeout=_DURATION_SEC + 2.0)
            p.terminate()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
