# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the channel-classification taxonomy."""

from app.library.channels import (
    DeviceGeneration,
    classify_funscript_channel,
    device_generations_for_set,
)


class TestClassifyFunscriptChannel:
    def test_plain_main_funscript(self):
        info = classify_funscript_channel("Euphoria.funscript")
        assert info.base_stem == "Euphoria"
        assert info.channel == ""
        assert info.is_prostate is False
        assert DeviceGeneration.MECHANICAL in info.generations
        assert DeviceGeneration.SIMPLE_2B in info.generations

    def test_alpha_channel(self):
        info = classify_funscript_channel("Euphoria.alpha.funscript")
        assert info.base_stem == "Euphoria"
        assert info.channel == "alpha"
        assert info.is_prostate is False
        assert DeviceGeneration.STEREOSTIM in info.generations
        assert DeviceGeneration.FOC_STIM in info.generations

    def test_alpha_prostate_channel(self):
        info = classify_funscript_channel("Euphoria.alpha-prostate.funscript")
        assert info.base_stem == "Euphoria"
        assert info.channel == "alpha-prostate"
        assert info.is_prostate is True
        assert DeviceGeneration.STEREOSTIM in info.generations

    def test_pulse_frequency(self):
        info = classify_funscript_channel("Euphoria.pulse_frequency.funscript")
        assert info.base_stem == "Euphoria"
        assert info.channel == "pulse_frequency"
        assert info.is_prostate is False
        assert DeviceGeneration.FOC_STIM in info.generations
        # Not STEREOSTIM — pulse_frequency is FOC-stim-specific
        assert DeviceGeneration.STEREOSTIM not in info.generations

    def test_multi_axis_roll(self):
        info = classify_funscript_channel("Scene.roll.funscript")
        assert info.channel == "roll"
        assert DeviceGeneration.MULTI_AXIS in info.generations

    def test_volume_prostate(self):
        info = classify_funscript_channel("Magik.volume-prostate.funscript")
        assert info.base_stem == "Magik"
        assert info.channel == "volume-prostate"
        assert info.channel_core == "volume"
        assert info.subchannel == "prostate"
        assert info.is_prostate is True
        assert DeviceGeneration.FOC_STIM in info.generations

    def test_volume_stereostim_subchannel(self):
        # Real filename from Magik test_media. `-stereostim` is a GENERATION
        # modifier that narrows the channel to stereostim-only — NOT a
        # FOC-stim volume variant.
        info = classify_funscript_channel("Magik Number 3 Pt 1.volume-stereostim.funscript")
        assert info.base_stem == "Magik Number 3 Pt 1"
        assert info.channel == "volume-stereostim"
        assert info.channel_core == "volume"
        assert info.subchannel == "stereostim"
        assert info.is_prostate is False
        assert info.is_generation_modifier is True
        # Narrowed to just stereostim — NOT FOC_STIM
        assert info.generations == frozenset({DeviceGeneration.STEREOSTIM})

    def test_alpha_stereostim_subchannel(self):
        info = classify_funscript_channel("scene.alpha-stereostim.funscript")
        assert info.channel_core == "alpha"
        assert info.subchannel == "stereostim"
        assert info.is_prostate is False
        assert info.is_generation_modifier is True
        assert info.generations == frozenset({DeviceGeneration.STEREOSTIM})

    def test_foc_stim_generation_modifier(self):
        info = classify_funscript_channel("scene.volume-foc-stim.funscript")
        assert info.channel_core == "volume"
        assert info.subchannel == "foc-stim"
        assert info.is_generation_modifier is True
        assert info.generations == frozenset({DeviceGeneration.FOC_STIM})

    def test_2b_generation_modifier(self):
        info = classify_funscript_channel("scene.alpha-2b.funscript")
        assert info.channel_core == "alpha"
        assert info.subchannel == "2b"
        assert info.is_generation_modifier is True
        assert info.generations == frozenset({DeviceGeneration.SIMPLE_2B})

    def test_prostate_is_routing_not_generation(self):
        # -prostate is a ROUTING modifier, not a generation modifier.
        # The channel still contributes to the generations its core implies.
        info = classify_funscript_channel("scene.alpha-prostate.funscript")
        assert info.is_prostate is True
        assert info.is_generation_modifier is False
        # alpha-prostate still contributes to stereostim and foc_stim
        assert DeviceGeneration.STEREOSTIM in info.generations
        assert DeviceGeneration.FOC_STIM in info.generations

    def test_complex_base_stem_preserved(self):
        # Magik's real-world filename has brackets, numbers, spaces
        info = classify_funscript_channel(
            "Magik Number 3 Pt 1 [E-Stim & Popper Edit].alpha.funscript"
        )
        assert info.base_stem == "Magik Number 3 Pt 1 [E-Stim & Popper Edit]"
        assert info.channel == "alpha"

    def test_path_is_stripped(self):
        info = classify_funscript_channel(
            "/path/to/scene/Euphoria.alpha.funscript"
        )
        assert info.base_stem == "Euphoria"
        assert info.channel == "alpha"

    def test_windows_path_is_stripped(self):
        info = classify_funscript_channel(
            r"C:\Users\bruce\forgeplayer\Euphoria.alpha.funscript"
        )
        assert info.base_stem == "Euphoria"
        assert info.channel == "alpha"


class TestDeviceGenerationsForSet:
    def test_main_only_is_mechanical_and_2b(self):
        gens = device_generations_for_set({""})
        assert DeviceGeneration.MECHANICAL in gens
        assert DeviceGeneration.SIMPLE_2B in gens
        assert DeviceGeneration.STEREOSTIM not in gens
        assert DeviceGeneration.FOC_STIM not in gens

    def test_alpha_only_is_not_stereostim(self):
        # Stereostim needs BOTH alpha and beta
        gens = device_generations_for_set({"alpha"})
        assert DeviceGeneration.STEREOSTIM not in gens

    def test_alpha_and_beta_is_stereostim(self):
        gens = device_generations_for_set({"alpha", "beta"})
        assert DeviceGeneration.STEREOSTIM in gens
        # But NOT foc_stim without a pulse param
        assert DeviceGeneration.FOC_STIM not in gens

    def test_alpha_beta_plus_pulse_is_foc_stim(self):
        gens = device_generations_for_set({"alpha", "beta", "pulse_frequency"})
        assert DeviceGeneration.FOC_STIM in gens
        assert DeviceGeneration.STEREOSTIM in gens  # stereostim subset

    def test_full_foc_stim_rig(self):
        # Euphoria-style: all five FOC-stim params + alpha/beta
        gens = device_generations_for_set({
            "", "alpha", "beta",
            "pulse_frequency", "pulse_rise_time", "pulse_width",
            "volume", "frequency",
        })
        assert DeviceGeneration.MECHANICAL in gens
        assert DeviceGeneration.STEREOSTIM in gens
        assert DeviceGeneration.FOC_STIM in gens

    def test_multi_axis(self):
        gens = device_generations_for_set({"", "roll", "pitch", "twist"})
        assert DeviceGeneration.MULTI_AXIS in gens
        assert DeviceGeneration.MECHANICAL in gens  # main present too
