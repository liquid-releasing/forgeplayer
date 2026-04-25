# How ForgePlayer interprets funscript channels

This is a **read-along companion** to:

- [funscript-tools/FUNDAMENTAL_OPERATIONS.md](https://github.com/liquid-releasing/funscript-tools/blob/main/FUNDAMENTAL_OPERATIONS.md) (Edger) — the canonical authoring contract for funscript channels.
- [restim](https://github.com/diglet48/restim) (diglet48) — the canonical playback math.

Goal: explain how ForgePlayer's real-time playback consumes those
funscripts, so the upstream maintainers (and anyone else reviewing)
can spot if we got a nuance wrong.

If something here disagrees with what Edger or diglet intended:
**you're right, we're wrong**. Please flag it (issue or Discord), we'll
fix.

---

## What ForgePlayer is, briefly

A real-time multi-screen video player that plays funscripts straight
to estim audio devices. We do not author funscripts — we read what
FunscriptForge / ForgeAssembler / ForgeGen produce and play it.

Two architectural rules governing how we touch upstream's work:

1. **Vendor narrowly with attribution.** We import `restim/stim_math/`
   at a pinned commit, with `ATTRIBUTION.md` and a `VERSION` pin.
   Synth math is unchanged from upstream.
2. **Don't reshape upstream.** If Edger / diglet didn't ship a CLI or
   library, we don't fork to make one — we vendor what we need.

The trade-off: if upstream design says "X happens once per chunk," we
honor that even when it means losing a feature (see carrier-funscript
asymmetry below).

## Channel-by-channel mapping

Funscript files store position as `pos: 0..100` integer. Our loader
([app/funscript_loader.py](../../app/funscript_loader.py)) normalizes
that to a 0..1 float. The synth ([app/stim_synth.py](../../app/stim_synth.py))
then rescales 0..1 to each channel's native authoring unit using the
ranges from Edger's normalization table.

| Channel | 0.0 means | 1.0 means | Authoring source | Our handling |
| --- | --- | --- | --- | --- |
| `alpha`, `beta` | -1 (extreme one direction) | +1 (extreme other) | restim's `funscript_kit.py` | Honored, both modes. Per-sample interpolation. |
| `volume` | silent | full | Edger normalization (`max=1.0`) | Honored, both modes. Per-sample interpolation. Volume modulation effects (Edger's "buzz" family at 9-65 Hz on the volume axis) ride through cleanly. |
| `frequency` (carrier) | 0 Hz (clamped by safety) | 1200 Hz (clamped by safety) | Edger normalization (`max=1200`) | **Continuous mode: ignored** (see below). Pulse mode: honored. |
| `pulse_frequency` | 0 Hz | 200 Hz max in Edger; 100 Hz in restim's funscript_kit | Conflicting — see Open Questions | Currently 0..100 Hz (restim's authoring scale). |
| `pulse_width` | 0% | 100% | Edger normalization (`max=100`); restim treats as 4..10 carrier cycles | Currently 4..10 cycles (restim's scale). Possible mismatch — see Open Questions. |
| `pulse_rise_time` | (TBD) | (TBD) | Not in Edger's normalization table; restim treats as 2..20 carrier cycles | Currently 2..20 cycles (restim's scale). |

## Operation-by-operation: how we play what Edger creates

This section walks through each `apply_*` operation Edger documents
and what its output looks like by the time we play it.

### `apply_modulation` — Edger's workhorse

Edger uses this for the buzz/hum/oscillate effects on volume,
pulse_frequency, pulse_width, alpha, and beta. The output landing on
disk is a `.funscript` containing the discretized waveform sampled at
the funscript's grid rate.

By the time we read the file, we don't see "an apply_modulation call" —
we see action samples. Our pipeline's responsibility is to **not
distort what Edger baked**.

What we do:

- **Linear interpolation between actions**, the same way restim
  expects when it consumes `Timeline` objects. ForgePlayer's StimSynth
  builds a precomputed axis with linear interpolation
  ([stim_synth.py:_axis_from_actions](../../app/stim_synth.py)) which is
  what restim's continuous and pulse-based algorithms read from.
- **No additional smoothing or filtering.** If Edger authored a 15 Hz
  hum on the volume axis, the volume curve has a 15 Hz oscillation
  baked in, and we let it through to the synth. The audible "buzz" at
  15 Hz is intentional.

What we don't do (and why):

- **No upsampling beyond the action grid.** The action timestamps are
  authoritative.
- **No re-modulation in the player.** A future Calibrate / device-
  profile feature might layer a per-device volume gain on top of
  Edger's volume, but the player layer never invents new oscillations.

### `apply_linear_change` — set / boost / fade

Same story — output is action samples, we interpolate linearly between
them. No special handling needed in the player.

### Sampling-aliasing rule (Edger's Important Note 4)

Edger warns: avoid modulation frequencies at multiples of 10 Hz
(10, 20, 30, 60). The ~10 Hz funscript action grid would alias.

ForgePlayer doesn't modulate, so we don't need to apply this rule
ourselves. We do honor it transitively: if Edger's authoring respects
the rule, our linear interpolation between action samples preserves
the intended waveform shape.

A future ForgePlayer feature that DID modulate (e.g. a per-device
volume curve, or live "boost" controls) would need to obey the rule.

## Continuous vs pulse mode (the carrier-funscript asymmetry)

This is the place where we made a non-obvious choice. Worth
double-checking against your intent.

**The constraint**: restim's continuous algorithm
([continuous.py:43](../../app/vendor/restim_stim_math/audio_gen/continuous.py#L43))
samples `carrier_frequency.interpolate(system_time_estimate[0])` —
**only the first sample** of each audio chunk. The carrier runs at
that scalar frequency for the whole chunk. Phase is continuous across
chunks, but frequency steps at every chunk boundary.

**The symptom**: with audio chunks of ~4096 frames at 44.1 kHz, that's
a frequency step every 92.9 ms ≈ 10.7 Hz. A varying carrier funscript
on continuous mode produces an audible 10 Hz "horse-hoof" buzz at
chunk boundaries.

**Empirical validation**: spectral analysis of Zer0 Game's stereostim
pack played offline. With carrier funscript: hi-band (>2 kHz) mean
energy spiked from baseline 0.0002 to 0.13-0.15 in t=8-20s (where the
carrier funscript varies). Without carrier funscript (constant 700 Hz
default): back to 0.005 (noise floor).

**Our choice**:

- **Continuous mode → ignore carrier funscript**, use constant 700 Hz
  default. This matches FunscriptForge's MP3 renderer
  ([forge/audio_synthesis.py:64](https://github.com/liquid-releasing/funscript-updater/blob/main/forge/audio_synthesis.py#L64))
  which does the same — constant 700 Hz unless you explicitly hand the
  renderer a path to a carrier funscript.
- **Pulse mode → honor carrier funscript**. restim's pulse-based
  algorithm samples carrier per-sample
  ([pulse_based.py:121](../../app/vendor/restim_stim_math/audio_gen/pulse_based.py#L121)),
  no chunk artifact.

If your authoring intent is "varying carrier should play correctly,"
the answer in our system is "use pulse mode." Continuous can't honor
it without a math change to restim, which we agreed not to make.

If you'd prefer we change this — for example, by always using pulse
when carrier funscript is present — let us know.

## Per-channel sources of truth

| Channel/range/intent question | Authoritative source |
| --- | --- |
| What channels exist, what filenames | Edger's `funscript-tools/CLI_REFERENCE.md` + Edger's writeups |
| Authoring max value per channel (volume, frequency, pulse_*) | Edger's `FUNDAMENTAL_OPERATIONS.md` normalization table |
| Modulation primitives, parameters, modes | Edger's `FUNDAMENTAL_OPERATIONS.md` |
| Synth math (3-phase, pulse shaping, etc.) | restim source |
| Synth-side sampling discipline (per-chunk vs per-sample) | restim source — `audio_gen/continuous.py` and `audio_gen/pulse_based.py` |
| Restim safety limits | restim's `qt_ui/settings.py` |

We try to never make our own decisions on these — we follow upstream.
When we have to make a choice (carrier funscript handling above),
we document it.

## Open questions for upstream

If you have time and inclination, these would help us get more of it
right:

1. **Pulse-frequency authoring scale.** Edger's normalization table
   says `max=200 Hz`. restim's `funscript_kit.py` says
   `(0, 100, True, True)` — so 100 Hz max. We currently use 0..100.
   Which is right for downstream consumption? Likely the answer is
   "Edger's authoring intent is 0..200, restim's safety is 0..100,
   and the safety clamp at synth time handles the discrepancy" — but
   we'd value confirmation.
2. **Pulse-width authoring scale.** Edger says `max=100` (percent).
   restim's `funscript_kit.py` says `(4, 10, True, True)` — carrier
   cycles. The scale is fundamentally different (% vs cycles). What
   does Edger's tool actually emit in pulse_width.funscript files?
3. **Pulse-rise-time normalization.** Not in Edger's normalization
   table. restim treats as 2..20 carrier cycles. What scale does
   Edger's tool emit?
4. **Multi-modulation stacking.** When two `apply_modulation`s in
   `additive` mode overlap on the same axis, do they sum
   arithmetically, or does the second overwrite the first's region?
5. **Carrier funscript intent in continuous mode.** Is the chunk-step
   issue something you'd want to fix in restim (e.g. per-sample
   carrier in continuous), or is constant-carrier the design intent
   of continuous mode?
6. **Device-family volume scaling.** We observed that Zer0 Game's
   `foc/` and `stereostim/` subfolders ship 8 of 10 funscripts
   byte-identical, with only volume curves differing (~+6 pos median
   on stereostim). Is there documented guidance on this scaling, or
   is it scripter-by-scripter?

## How to spot us getting it wrong

- **Rendering doesn't match FunscriptForge's `*.estim.mp3`**: probable
  scaling mismatch (channel range, normalization).
- **Audible chunk-step artifacts on a channel that should be smooth**:
  probable per-chunk sampling we shouldn't be doing.
- **Effect that Edger documented as audible doesn't come through**:
  probable over-smoothing or wrong default constant.
- **Effect at multiple-of-10 Hz alias rate**: probable upstream
  authoring issue (per Edger's note); flag it so the scripter can
  fix.

## Versions

- restim vendored at commit `702e9d2` (v1.59) — see `app/vendor/restim_stim_math/VERSION`.
- funscript-tools/FUNDAMENTAL_OPERATIONS.md captured: as of writing this doc.
- ForgePlayer version: see top-level `VERSION` file.
