# restim canonical channels

[restim](https://github.com/diglet48/restim) is the estim audio engine that converts funscripts into electrical signals driving estim hardware. ForgePlayer plays restim's pre-rendered audio output alongside the video (see [core model](../../SPEC.md#9-folder-load-conventions--the-pack-model)). When ForgePlayer matures to Phase 2 and embeds restim directly for real-time synthesis, this doc becomes the integration contract.

For now, this is the authoritative list of **which funscript filenames restim actually recognizes** — so the scanner's taxonomy, the select picker's routing, and future restim plumbing all stay aligned with what the engine downstream expects.

## Canonical channel list

restim auto-detects funscript files by matching the pattern `{stem}.{channel}.funscript`. Everything restim knows:

| Group | Channels |
|---|---|
| Position (3-phase) | `alpha`, `beta`, `gamma` |
| Pulse parameters | `pulse_frequency`, `pulse_width`, `pulse_rise_time`, `pulse_interval_random` |
| Frequency / volume | `frequency` (carrier), `volume` |
| 4-phase electrode intensity | `e1`, `e2`, `e3`, `e4` |
| Vibration motor 1 | `vib1_frequency`, `vib1_strength`, `vib1_left_right_bias`, `vib1_up_down_bias`, `vib1_random` |
| Vibration motor 2 | `vib2_frequency`, `vib2_strength`, `vib2_left_right_bias`, `vib2_up_down_bias`, `vib2_random` |

Parsed in restim by `qt_ui/models/funscript_kit.py` + `funscript/collect_funscripts.py`.

## Not restim — real channels, other tools

**Multi-axis spatial** (`roll`, `pitch`, `twist`, `surge`, `sway`) is consumed by SR6-style mechanical hardware and VR alignment tools — NOT by restim. ForgePlayer still detects these channels because users with SR6 / VR hardware need the classification; we just don't route them through restim's estim pipeline.

## Subchannel modifiers — our layer, not restim's

The community convention `-prostate`, `-stereostim`, `-foc-stim`, `-2b` (e.g. `scene.volume-stereostim.funscript`) is **content-organization metadata**, not a restim-recognized format.

restim's filename parser splits on the last dot and would treat `volume-stereostim` as an unknown channel name — **it would fail to match `volume`**. These suffixes are consumed by a layer ABOVE restim (ForgePlayer, ForgeAssembler, the select picker).

Flow when a scene has generation variants:

```
content folder contains:
  scene.volume.funscript             ← default encoding (often FOC-stim)
  scene.volume-stereostim.funscript  ← explicit stereostim variant

  user's device profile: stereostim
       ↓
  ForgePlayer's select picker shows ambiguity
       ↓
  user picks "stereostim variant"
       ↓
  ForgePlayer copies / renames to plain:
       scene.volume.funscript (contents from the -stereostim file)
       ↓
  restim consumes plain `.volume.funscript` and plays it
```

ForgePlayer's `ChannelInfo.channel_core` is the plain name restim wants. `ChannelInfo.channel` is the community-organization form. When we eventually route to restim, we strip to the core.

## Legacy `.funscript` → 1D-to-2D conversion

`restim/funscript_1d_to_2d.py` converts a plain `.funscript` (1D position) into `.alpha` + `.beta` via radial interpolation in stim-math's 2D coordinate space. That's how a pure-mechanical funscript becomes playable on estim hardware via restim.

ForgePlayer's scanner classifies plain `.funscript` as both MECHANICAL and SIMPLE_2B for this reason — the 2b device accepts the 1D→2D-converted output path.

## Device type vs channel availability

restim has a unified pipeline. Device type selection picks the algorithm, not the file list:

| Device type | Role |
|---|---|
| `AUDIO_THREE_PHASE` | 3-phase stereo (alpha + beta) |
| `FOCSTIM_THREE_PHASE` | 3-phase FOC-stim hardware |
| `FOCSTIM_FOUR_PHASE` | 4-phase FOC-stim (uses e1–e4, or derives from alpha+beta+gamma) |
| `NEOSTIM_THREE_PHASE` | NeoStim hardware |

**No "stereostim mode" vs "foc-stim mode" toggle inside restim.** The upstream tool configures device type before the engine runs. In ForgePlayer, that's the user's device profile in Setup → Audio routing.

## Implications for ForgePlayer

### Scanner taxonomy

- Recognize every channel restim recognizes (alpha/beta/gamma, pulse_*, frequency, volume, e1–e4, vib1/2_*)
- PLUS multi-axis (roll/pitch/twist/surge/sway) for non-estim hardware
- PLUS subchannel modifiers (-prostate routing, -stereostim/-foc-stim/-2b generation) as metadata

### Library card badges

Device-generation badges (`m•` / `2b•` / `s•` / `foc•` / `mx•`) reflect what the scene supports. A scene with restim-canonical channels but no modifiers is unambiguous for a device with compatible hardware. A scene with suffix variants gets the ambiguity flag — user picks in the select overlay.

### Routing to restim (Phase 2)

When ForgePlayer embeds restim (Phase 2 — alpha ships with pre-rendered audio only), the plumbing takes the user's selected variant per channel and feeds it to restim under the plain core name. The `-stereostim` / `-foc-stim` layer is ours to collapse; restim doesn't need to know.

### What ForgePlayer must NOT do

- Pass suffixed filenames to restim — would fail silently
- Assume `-prostate` routes to a different physical device without explicit user setup — it's a SIDE channel, not automatically a different hardware output (that's configured in Setup → Audio routing)
- Attempt to reconstruct 4-phase from 3-phase, or vice versa — that's restim's math, not ours

## Re-derivation

If restim updates its channel list (adds new parameters, changes names), re-derive from:

- `qt_ui/models/funscript_kit.py` — default channel enum members
- `qt_ui/device_wizard/axes.py` — `AxisEnum` full list
- `funscript/collect_funscripts.py` — filename-suffix parsing (`split_funscript_path()`)

Any changes → update this doc + the sibling doc in FunscriptForge (`docs/architecture/ARCHITECTURE_restim_channels.md`) + memory `reference_restim_canonical_channels.md`.
