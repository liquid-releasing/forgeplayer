# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Funscript channel taxonomy and device-generation classification.

ForgePlayer at its core plays funscripts (see `project_forgeplayer_core_model.md`).
Each funscript file carries one channel of intent for one device generation. This
module defines the taxonomy used everywhere: which filename suffixes map to which
channels, which channels belong to which device generation, and how to classify
a funscript filename into (base_stem, channel, generation, is_prostate).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class DeviceGeneration(str, Enum):
    """Broad categories of haptic devices the user might own.

    A scene is 'ready for' a generation if the folder contains the funscripts
    that generation needs. Stored as strings for clean JSON serialization.
    """

    MECHANICAL = "mechanical"
    """Linear actuators / strokers — OSR2, Keon, Handy, Launch. Uses the main
    `.funscript` file (and optionally multi-axis `.roll/.pitch/.twist/...`)."""

    SIMPLE_2B = "2b"
    """Legacy 2-pad simple estim. Uses the main `.funscript` as intensity."""

    STEREOSTIM = "stereostim"
    """2-channel estim (alpha + beta). Needs `.alpha.funscript` + `.beta.funscript`."""

    FOC_STIM = "foc_stim"
    """3-phase FOC-stim (newest). Needs `.alpha` + `.beta` + `.pulse_frequency`
    at minimum. Full parameter set also includes pulse_rise_time, pulse_width,
    volume, frequency."""

    MULTI_AXIS = "multi_axis"
    """Orthogonal to haptic generations — multi-axis motion data (pitch, roll,
    twist, surge, sway) for SR6-style devices or VR alignment."""


# ── Channel suffix definitions ────────────────────────────────────────────────
#
# Filename pattern:  {base_stem}.{channel_suffix}.funscript
#  - Main (no suffix): {base_stem}.funscript
#  - Channel suffix examples:
#      .alpha, .beta                                 (stereostim)
#      .pulse_frequency, .pulse_rise_time, .pulse_width,
#      .volume, .frequency                           (FOC-stim parameters)
#      .roll, .pitch, .twist, .surge, .sway          (multi-axis)
#      .alpha-prostate, .beta-prostate, .volume-prostate  (prostate side-chain)


# Canonical channel sets, aligned with restim's recognized filenames
# (see docs/architecture/restim-channels.md and memory
# reference_restim_canonical_channels.md for the authoritative list).

# Channels that signal stereostim (2-channel position-driven estim)
STEREOSTIM_CHANNELS = frozenset({"alpha", "beta"})

# Channels that are specifically FOC-stim parameters (indicate the newer
# full FOC-stim parameter set is present — includes 3-phase gamma position
# and all four pulse parameters restim knows).
FOC_STIM_CHANNELS = frozenset({
    "gamma",
    "pulse_frequency", "pulse_rise_time", "pulse_width", "pulse_interval_random",
    "volume", "frequency",
})

# 4-phase electrode intensity channels (FOCSTIM_FOUR_PHASE hardware).
# Orthogonal to STEREOSTIM/FOC_STIM — either the scripter authored
# explicit 4-phase files (e1..e4) OR 3-phase gets derived to 4-phase
# inside restim via abc_to_e1234().
FOUR_PHASE_ELECTRODE_CHANNELS = frozenset({"e1", "e2", "e3", "e4"})

# Vibration motor channels (Lovense-style dual-motor devices).
VIBRATION_1_CHANNELS = frozenset({
    "vib1_frequency", "vib1_strength",
    "vib1_left_right_bias", "vib1_up_down_bias", "vib1_random",
})
VIBRATION_2_CHANNELS = frozenset({
    "vib2_frequency", "vib2_strength",
    "vib2_left_right_bias", "vib2_up_down_bias", "vib2_random",
})
VIBRATION_CHANNELS = VIBRATION_1_CHANNELS | VIBRATION_2_CHANNELS

# Multi-axis spatial channels (SR6-class mechanical hardware / VR alignment).
# NOT consumed by restim — handled by separate downstream tooling.
MULTI_AXIS_CHANNELS = frozenset({"roll", "pitch", "twist", "surge", "sway"})

# Sub-channel modifiers — appended to channel names to indicate routing
# or generation-targeting.
#
# Routing modifier:
#   -prostate   → prostate-side electrode pair (secondary routing)
#
# Generation modifiers (which device generation this funscript targets):
#   -2b         → legacy 2b simple estim. Edger's tooling does NOT emit these;
#                 they're community-authored scripts targeting legacy hardware.
#   -stereostim → stereostim-generation (2-channel). Differentiates from the
#                 plain unsuffixed channel, which typically defaults to FOC-stim.
#   -foc-stim   → FOC-stim-generation (3-phase, newest). Explicitly marked
#                 when a scripter wants to disambiguate from `-stereostim`.
#
# Unsuffixed channels (plain `.alpha.funscript`) are the scripter's primary
# / default encoding, usually FOC-stim-compatible since that's the latest.
_ROUTING_MODIFIERS = frozenset({"prostate"})
_GENERATION_MODIFIERS = frozenset({"2b", "stereostim", "foc-stim"})

_MODIFIER_TO_GENERATION: dict[str, "DeviceGeneration"] = {
    # Populated after DeviceGeneration is defined, via _init_modifier_map()
}


# Regex to extract (base_stem, channel_core, subchannel) from a filename stem.
# channel_core is the recognized channel name; subchannel is an optional
# routing or generation modifier.
#
# Channel list is aligned with restim's canonical names — see the
# architecture doc at docs/architecture/restim-channels.md. Multi-axis
# (roll/pitch/...) are NOT restim-consumed but appear here because they're
# real filenames in the ecosystem for SR6-class hardware.
_CHANNEL_PATTERN = re.compile(
    r"""
    ^(?P<base>.+?)                                 # base stem (non-greedy)
    \.(?P<channel_core>
        # Vibration motors (restim) — longest patterns first
        vib1_frequency | vib1_strength | vib1_left_right_bias
      | vib1_up_down_bias | vib1_random
      | vib2_frequency | vib2_strength | vib2_left_right_bias
      | vib2_up_down_bias | vib2_random
        # Pulse parameters (restim)
      | pulse_frequency | pulse_rise_time | pulse_width
      | pulse_interval_random
        # Frequency / volume (restim)
      | frequency | volume
        # Position (restim 3-phase)
      | alpha | beta | gamma
        # 4-phase electrode intensity (restim)
      | e1 | e2 | e3 | e4
        # Multi-axis spatial (not restim — other tools)
      | roll | pitch | twist | surge | sway
    )
    (?:-(?P<subchannel>prostate|stereostim|foc-stim|2b))?  # optional modifier
    $
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class ChannelInfo:
    """Classification of a single funscript filename."""
    base_stem: str
    """Everything before the channel suffix. For `Euphoria.alpha.funscript`,
    base_stem is 'Euphoria'. For plain `Euphoria.funscript`, base_stem is
    also 'Euphoria' (channel is empty)."""
    channel: str
    """The full channel name as it appears in the filename suffix, or '' for
    the main (no-suffix) funscript. Includes any subchannel modifier — e.g.
    'alpha-prostate' or 'volume-stereostim'."""
    channel_core: str
    """The channel name WITHOUT any subchannel modifier — e.g. 'alpha' for
    'alpha-prostate', 'volume' for 'volume-stereostim'. Same as `channel`
    when no modifier is present. Empty for the main funscript."""
    subchannel: str
    """The modifier attached to the channel, or '' if none. Currently one
    of: 'prostate', 'stereostim', '2b', 'foc-stim'."""
    is_prostate: bool
    """True when subchannel == 'prostate'."""
    is_generation_modifier: bool
    """True when the subchannel is a generation qualifier (-2b, -stereostim,
    -foc-stim) — meaning the scripter explicitly tagged this file as
    targeting a specific device generation. A set containing generation-
    modified channels signals that the user can CHOOSE between generation-
    specific encodings, which is the primary trigger for scene ambiguity
    in `SceneCatalogEntry.is_ambiguous`."""
    generations: frozenset[DeviceGeneration]
    """Which device generations this channel contributes to. A single file
    can contribute to multiple (e.g. `.alpha.funscript` contributes to both
    stereostim AND foc_stim). When `is_generation_modifier` is True, this
    set narrows to just the tagged generation."""


def classify_funscript_channel(filename: str) -> ChannelInfo:
    """Classify one funscript filename into its base stem, channel, and generations.

    Accepts either a bare filename (`Euphoria.alpha.funscript`) or a path. The
    `.funscript` extension is stripped before analysis.

    The main `.funscript` file (no channel suffix) is classified as
    MECHANICAL + SIMPLE_2B — it's the funscript that both classes of device
    consume directly.

    Channels with a recognized subchannel modifier (`-prostate`, `-stereostim`)
    contribute to the same generation as their non-modified counterpart,
    with the relevant flag set so the scanner can surface side-channel
    badges and the select picker can present them as routing options.
    """
    # Strip the .funscript extension
    stem = filename
    if stem.endswith(".funscript"):
        stem = stem[: -len(".funscript")]

    # Strip any directory portion
    stem = stem.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    match = _CHANNEL_PATTERN.match(stem)
    if not match:
        # No recognized channel suffix → main funscript
        return ChannelInfo(
            base_stem=stem,
            channel="",
            channel_core="",
            subchannel="",
            is_prostate=False,
            is_generation_modifier=False,
            generations=frozenset({
                DeviceGeneration.MECHANICAL,
                DeviceGeneration.SIMPLE_2B,
            }),
        )

    base = match.group("base")
    core = match.group("channel_core")
    sub = match.group("subchannel") or ""
    full_channel = f"{core}-{sub}" if sub else core

    # Default generations inferred from the channel core
    gens: set[DeviceGeneration] = set()
    if core in STEREOSTIM_CHANNELS:
        gens.add(DeviceGeneration.STEREOSTIM)
        gens.add(DeviceGeneration.FOC_STIM)  # FOC-stim also uses alpha+beta
    if core in FOC_STIM_CHANNELS:
        # Gamma / pulse_* / frequency / volume are FOC-stim parameters
        gens.add(DeviceGeneration.FOC_STIM)
    if core in FOUR_PHASE_ELECTRODE_CHANNELS:
        # e1..e4 go to 4-phase FOC-stim hardware
        gens.add(DeviceGeneration.FOC_STIM)
    if core in VIBRATION_CHANNELS:
        # vib1/2_* — vibration motor (Lovense etc.); doesn't map to the
        # estim generations, no DeviceGeneration added. Still classified
        # so the scanner can surface vibration-channel badges later.
        pass
    if core in MULTI_AXIS_CHANNELS:
        gens.add(DeviceGeneration.MULTI_AXIS)

    # Generation-modifier suffixes NARROW the generation set to just the
    # tagged generation. For example, `volume-stereostim` is volume
    # specifically for stereostim-generation playback, not FOC-stim.
    is_gen_modifier = sub in _GENERATION_MODIFIERS
    if is_gen_modifier:
        target_gen = {
            "2b":         DeviceGeneration.SIMPLE_2B,
            "stereostim": DeviceGeneration.STEREOSTIM,
            "foc-stim":   DeviceGeneration.FOC_STIM,
        }[sub]
        gens = {target_gen}

    return ChannelInfo(
        base_stem=base,
        channel=full_channel,
        channel_core=core,
        subchannel=sub,
        is_prostate=(sub == "prostate"),
        is_generation_modifier=is_gen_modifier,
        generations=frozenset(gens),
    )


def has_generation_variants(channel_names: set[str]) -> bool:
    """True when the set of channel names includes any generation-modifier
    suffix (-2b, -stereostim, -foc-stim). Used by the scanner to detect
    scenes where the scripter provided device-generation-specific variants
    and the user may need to pick at select time."""
    for ch in channel_names:
        if not ch:
            continue
        # Split on last '-' to find a potential subchannel; cheap check
        for mod in _GENERATION_MODIFIERS:
            if ch.endswith(f"-{mod}"):
                return True
    return False


def device_generations_for_set(channels_present: set[str]) -> set[DeviceGeneration]:
    """Compute the generations a funscript set fully supports.

    Input: the set of channel names (without the leading `.`) present in a
    FunscriptSet, including `""` for the main funscript. Channel names may
    include subchannel modifiers (e.g. 'alpha-prostate', 'volume-stereostim').

    A generation is supported when its *required* channels are all present,
    counting subchannel-modified variants as providing the same core channel:

    - MECHANICAL / SIMPLE_2B: main `""` is enough.
    - SIMPLE_2B (explicit): any channel with `-2b` suffix.
    - STEREOSTIM: needs both `alpha` and `beta` core (plain or modified), OR
      explicit `-stereostim`-suffixed channels present.
    - FOC_STIM: needs `alpha` + `beta` + at least one FOC-stim parameter
      channel (plain or with `-foc-stim` suffix). Partial FOC-stim is
      downgraded to plain stereostim. Explicit `-foc-stim` suffix also
      counts.
    - MULTI_AXIS: any of the 5 multi-axis channels (plain or modified).
    """
    supported: set[DeviceGeneration] = set()

    def _has_core(core: str) -> bool:
        """True when any channel has this core (plain or subchannel-modified)."""
        if core in channels_present:
            return True
        return any(
            ch.startswith(f"{core}-") for ch in channels_present if ch
        )

    def _has_any_of(cores: frozenset[str]) -> bool:
        return any(_has_core(c) for c in cores)

    has_main = "" in channels_present
    has_alpha = _has_core("alpha")
    has_beta = _has_core("beta")
    has_foc_param = _has_any_of(FOC_STIM_CHANNELS)
    has_multi = _has_any_of(MULTI_AXIS_CHANNELS)

    # Explicit generation-suffix signals
    has_2b_suffix = any(ch.endswith("-2b") for ch in channels_present if ch)
    has_stereostim_suffix = any(ch.endswith("-stereostim") for ch in channels_present if ch)
    has_foc_stim_suffix = any(ch.endswith("-foc-stim") for ch in channels_present if ch)

    if has_main:
        supported.add(DeviceGeneration.MECHANICAL)
        supported.add(DeviceGeneration.SIMPLE_2B)
    if has_2b_suffix:
        supported.add(DeviceGeneration.SIMPLE_2B)
    if has_alpha and has_beta:
        supported.add(DeviceGeneration.STEREOSTIM)
    if has_stereostim_suffix:
        supported.add(DeviceGeneration.STEREOSTIM)
    if (has_alpha and has_beta and has_foc_param) or has_foc_stim_suffix:
        supported.add(DeviceGeneration.FOC_STIM)
    if has_multi:
        supported.add(DeviceGeneration.MULTI_AXIS)

    return supported


# Device-generation display badges for Library cards.
# Short text labels — see `project_forgeplayer_folder_heuristics.md` for the
# rationale (text over emojis for clarity and Windows-safety).
GENERATION_BADGES: dict[DeviceGeneration, str] = {
    DeviceGeneration.MECHANICAL: "m•",
    DeviceGeneration.SIMPLE_2B:  "2b•",
    DeviceGeneration.STEREOSTIM: "s•",
    DeviceGeneration.FOC_STIM:   "foc•",
    DeviceGeneration.MULTI_AXIS: "mx•",
}
