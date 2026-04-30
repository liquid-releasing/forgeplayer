# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Preferences — global device-role config persisted to ~/.forgeplayer/preferences.json.

The user configures which physical audio device plays each *semantic* role
(Scene Audio / Haptic 1 / Haptic 2) once, via the Setup tab. Library clicks
then auto-route: Slot 1 gets Scene Audio, Slot 2 gets Haptic 1. This
eliminates the "pick the USB dongle every time" friction users hit in the
v0.0.1 baseline.

See `project_forgeplayer_multichannel_audio.md` for the channel model
and `feedback_forgeplayer_minimize_thinking.md` for the motivation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Literal


_PREFS_PATH = Path.home() / ".forgeplayer" / "preferences.json"


# Audio synthesis algorithm. Mirrors restim's "Select generation algorithm"
# wizard: continuous is restim's default ("Best for 312/2B"); pulse-based
# targets modern audio-based stereostim hardware ("Power-efficient
# waveform. Slower numbing"). One global setting; both haptic roles use
# the same algorithm in v0.0.2 since real users don't run mixed device
# families on one rig.
AudioAlgorithm = Literal["continuous", "pulse"]

# What to play on the Haptic 2 (prostate) device when the scene has no
# prostate source (no `alpha-prostate`/`beta-prostate` funscripts and no
# `<stem>.prostate.wav` file). `silent` is the safe default — the user
# only picked Haptic 2 because they have a second dongle, not because they
# want surprise output. `mirror_h1` is the "feel the same stim everywhere"
# choice (the Haptic 2 dongle plays the main stim synth identically to
# Haptic 1). `video_soundtrack` is reserved for a later release — the
# UI accepts the value so that prefs files survive a downgrade, but the
# launch path falls through to silent until the mpv-fan-out work lands.
Haptic2Fallback = Literal["silent", "mirror_h1", "video_soundtrack"]


@dataclass
class Preferences:
    """User-configurable cross-session preferences.

    Fields are mpv `audio_device` identifiers (the same string a slot's
    audio-output combobox uses as its itemData). Empty string means the
    role is not yet configured.
    """

    scene_audio_device: str = ""
    haptic1_audio_device: str = ""
    haptic2_audio_device: str = ""
    # When the loaded scene has no prostate source (neither
    # `alpha-prostate` + `beta-prostate` funscripts nor a sibling
    # `<stem>.prostate.wav`), this controls what the Haptic 2 dongle
    # plays. See `Haptic2Fallback` above for the option semantics.
    haptic2_fallback: Haptic2Fallback = "silent"
    # Synthesis algorithm — see AudioAlgorithm above.
    audio_algorithm: AudioAlgorithm = "continuous"
    # Constant offset applied to the haptic stream's media-time. Positive
    # ms = stim leads video; negative = stim lags. Compensates for USB
    # dongle / driver / electrode-placement latency. Restim and CHPlayer
    # ship the same control under "offset [s]" — we use ms granularity.
    haptic_offset_ms: int = 0
    # Monitor roles. -1 = not set (ControlWindow uses Qt's default placement).
    control_panel_screen: int = -1
    # Which screen indices are usable for video playback. Empty list means
    # "all screens are fair game" (the v0.0.1 default — user hasn't opted in
    # to filtering).
    playback_screen_indices: List[int] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Preferences":
        try:
            data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        fields = {k for k in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in fields}
        # Coerce algorithm enum: stale or hand-edited values should fall
        # back to default rather than crash the synth at launch time.
        if clean.get("audio_algorithm") not in ("continuous", "pulse"):
            clean.pop("audio_algorithm", None)
        if clean.get("haptic2_fallback") not in (
            "silent", "mirror_h1", "video_soundtrack",
        ):
            clean.pop("haptic2_fallback", None)
        # Coerce offset to int and clamp to safety range.
        if "haptic_offset_ms" in clean:
            try:
                clean["haptic_offset_ms"] = max(-500, min(500, int(clean["haptic_offset_ms"])))
            except (TypeError, ValueError):
                clean.pop("haptic_offset_ms", None)
        return cls(**clean)

    def save(self) -> None:
        """Write preferences to disk. Best-effort — a failure here should
        never break the app (the in-memory copy still works for this
        session)."""
        try:
            _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _PREFS_PATH.write_text(
                json.dumps(asdict(self), indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    @staticmethod
    def path() -> Path:
        return _PREFS_PATH
