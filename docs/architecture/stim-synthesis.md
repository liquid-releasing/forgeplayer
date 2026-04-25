# Stim synthesis — v0.0.2 Phase 1

Living architecture doc for ForgePlayer's native funscript playback path.
Update as each device generation lands. The goal is to always be able to
answer "what's actually wired up right now?" without reading the whole
codebase.

Sibling doc: [restim-channels.md](restim-channels.md) is the canonical
list of funscript filenames and what they mean upstream. This doc is the
ForgePlayer-side perspective — which of those we consume, how, and where
the output goes.

## What Phase 1 ships (v0.0.2)

- Real-time audio synthesis from funscripts using the vendored restim
  stim_math tree (`app/vendor/restim_stim_math/`).
- Two stim synth instances per scene: **main** and **prostate**. Each
  runs its own `ThreePhaseAlgorithm` or `DefaultThreePhasePulseBasedAlgorithm`
  and streams to its own audio device (dongle).
- Continuous-mode waveform for legacy 2b and classic stereostim content.
- Pulse-based-mode waveform for modern stereostim / FOC-stim content
  (i.e. any scene that ships `pulse_*` channel funscripts) — played
  through the same audio devices.

## What is explicitly NOT in Phase 1 (and why)

| Deferred | Reason | Tracked in |
|---|---|---|
| FOC-stim hardware (protobuf serial protocol) | No rig access to test. Vendored `stim_math/` stops short of `device/focstim/`. Audio-out pulse-based covers FOC-stim *content* on ordinary dongles, which is what matters for most users. | [project_forgeplayer_restim_vendor.md](../../../.claude/projects/c--Users-bruce-Projects-funscript-updater/memory/project_forgeplayer_restim_vendor.md) |
| NeoStim hardware | No rig. `stim_math/` excludes `device/neostim/`. | same |
| 4-phase electrode intensity (`e1`..`e4`) | Only produced by FOC-stim 4-phase hardware; no rig. | same |
| Multi-axis (roll/pitch/twist/surge/sway) | SR6-class mechanical hardware — separate pipeline, not estim. | [restim-channels.md](restim-channels.md) |
| Vibration motors (`vib1_*`, `vib2_*`) | Lovense-class devices; different transport. | — |
| `pulse_interval_random` channel | Scripter-authored jitter; folded into default constant (0) for now. | — |
| Transform / calibration UI | Will land with the Calibrate button, v0.0.2 item #4. | [project_forgeplayer_calibrate_button.md](../../../.claude/projects/c--Users-bruce-Projects-funscript-updater/memory/project_forgeplayer_calibrate_button.md) |

## Audio output architecture

Video slots and audio outputs are **orthogonal**. Video slots are about
displays; audio outputs are about physical audio devices (speakers,
USB dongles). A typical setup:

```
┌─────────────┐          ┌────────────────────┐  ┌─────────────────────┐
│ Slot 1      │          │ Scene audio        │  │ Speakers / headset  │
│   Video     │────audio─▶ (video's track)    │──▶ (Setup: Scene Audio)│
│ (monitor 1) │          └────────────────────┘  └─────────────────────┘
└─────────────┘

              funscript + audio synthesis
              ┌────────────────────┐  ┌─────────────────────┐
              │ Main stim synth    │──▶ USB audio dongle #1 │
              │ (alpha+beta+       │  │ (Setup: Haptic 1)   │
              │  pulse_*+volume)   │  └─────────────────────┘
              └────────────────────┘

              funscript + audio synthesis
              ┌────────────────────┐  ┌─────────────────────┐
              │ Prostate synth     │──▶ USB audio dongle #2 │
              │ (alpha-prostate,   │  │ (Setup: Haptic 2)   │
              │  beta-prostate,    │  └─────────────────────┘
              │  volume-prostate)  │
              └────────────────────┘

┌─────────────┐   ┌─────────────┐
│ Slot 2      │   │ Slot 3      │
│  Video 2    │   │  Video 3    │
│ (monitor 2, │   │ (monitor 3, │
│  mirror,    │   │  mirror,    │
│  SILENT)    │   │  SILENT)    │
└─────────────┘   └─────────────┘
```

- **Slot 1 (Video)** carries the scene video + routes the video's own
  audio track to the Scene Audio device.
- **Slot 2 (Video 2, mirror)** and **Slot 3 (Video 3, mirror)** repeat
  the main video on secondary monitors. They never emit audio. The
  slot-card UI surfaces no audio picker for them.
- **Main stim synth** is always present when the scene has any playable
  stim source (alpha/beta or main 1D). Streams to Haptic 1.
- **Prostate stim synth** is spawned only when the scene has both
  `alpha-prostate` + `beta-prostate` funscripts. No 1D fallback (the
  main `.funscript` is for the primary electrode pair, not prostate).
  Streams to Haptic 2.

The prostate synth reads its alpha/beta/volume from the `-prostate`
variants, but **shares** the scene's carrier + pulse shape funscripts
(`frequency`, `pulse_frequency`, `pulse_width`, `pulse_rise_time`) —
those describe how the pulses are formed, not where they go. This
matches FunscriptForge's Euphoria pack, which ships `volume-prostate`
but no `pulse_frequency-prostate`.

## Algorithm dispatch

The synth's waveform algorithm is **picked per call**, not derived from
which channels exist. Default is **continuous** because that matches
what FunscriptForge's MP3 renders use ([forge/audio_synthesis.py:124](https://github.com/liquid-releasing/funscript-updater/blob/main/forge/audio_synthesis.py#L124))
— users' ears are calibrated to that waveform.

```
StimSynth(channels, media_sync, waveform=...)
  ├─ "continuous" (default) → ThreePhaseAlgorithm
  │     Smooth sine carrier modulated by alpha+beta position. Used
  │     for legacy 2b (main 1D → radial 1D→2D) and stereostim.
  │     pulse_* channels are IGNORED in this mode (same as upstream).
  │
  └─ "pulse"                → DefaultThreePhasePulseBasedAlgorithm
        Discrete pulses, envelope-shaped, alternating polarity for
        DC balance. Consumes pulse_frequency / pulse_width /
        pulse_rise_time when present. Sounds clicky on its own.
        Opt-in for users with hardware tuned for pulse-based content.
```

Channel presence is orthogonal to algorithm — Euphoria-style scenes
ship with pulse_* channels, but they only matter if the user picks
pulse mode. v0.0.2 has no UI to switch yet; future Setup work will
expose it as part of device-profile config.

## Channel consumption table

All values follow restim's `funscript_kit.py` axis ranges. Funscript
`pos` values are always 0..100 on disk; the loader normalizes to 0..1
floats; the synth rescales to each channel's native axis range.

| Funscript file (main) | Funscript file (prostate) | Synth param | Axis range | Default |
|---|---|---|---|---|
| `{stem}.funscript` | — | → radial 1D→2D → alpha + beta | — | (fallback only) |
| `{stem}.alpha.funscript` | `{stem}.alpha-prostate.funscript` | `position.alpha` | −1 .. +1 | 0 (center) |
| `{stem}.beta.funscript` | `{stem}.beta-prostate.funscript` | `position.beta` | −1 .. +1 | 0 (center) |
| `{stem}.volume.funscript` | `{stem}.volume-prostate.funscript` | `volume.api` | 0 .. 1 | 1 (full) |
| `{stem}.frequency.funscript` | (shared w/ main) | `carrier_frequency` | 500 .. 1000 Hz | 700 Hz |
| `{stem}.pulse_frequency.funscript` | (shared) | `pulse_frequency` | 0 .. 100 Hz | 50 Hz |
| `{stem}.pulse_width.funscript` | (shared) | `pulse_width` | 4 .. 10 cycles | 6 cycles |
| `{stem}.pulse_rise_time.funscript` | (shared) | `pulse_rise_time` | 2 .. 20 cycles | 10 cycles |

"Default" applies when the channel is absent from the scene folder.
Defaults match restim's out-of-the-box settings (see
`qt_ui/settings.py` in upstream restim).

## Test scenes

- `test_media/Euphoria/` — full FOC-content pack: alpha, beta,
  frequency, pulse_frequency, pulse_width, pulse_rise_time, volume,
  alpha-prostate, beta-prostate, volume-prostate, plus the main 1D
  `Euphoria.funscript`. Should route to pulse-based synthesis on both
  main and prostate.
- `test_media/Zer0 Game/stereostim/` — same channel set, slightly
  different scene, no prostate video-side. Should route to
  pulse-based synthesis on main; prostate synth spawns because of
  alpha-prostate.
- `test_media/Zer0 Game/foc/` — FOC-stim-hardware-only variant. Phase 1
  ignores this subfolder; the scene's audio pack plays on the main
  audio output.

## Phase tracking

| Phase | Scope | Status | Commit(s) |
|---|---|---|---|
| 1 — commit 1 | Funscript loader + radial 1D→2D conversion, alpha/beta only | ✅ shipped | `5e15117` |
| 1 — commit 2 | StimSynth + continuous-mode ThreePhaseAlgorithm | ✅ shipped (in-memory only) | (unreleased) |
| 1 — revision | Full channel set in StimChannels, pulse-based dispatch, prostate synth | ⬜ this doc | — |
| 1 — commit 3 | sounddevice output to Haptic 1 (main only) | ⬜ next | — |
| 1 — commit 4 | Slot 2 dispatch wiring — click Play → synth produces audio | ⬜ next | — |
| 1 — commit 5 | Prostate synth to Haptic 2 (second audio stream) | ⬜ next | — |
| 2 | Calibrate button — pre-flight device check | ⬜ later | — |
| 2 | Slot card: Haptic 2 expander UI (surfaces prostate routing + test) | ⬜ later | — |
| 3+ | FOC-stim hardware protocol (protobuf/serial) | 🔒 blocked on rig | — |
| 3+ | NeoStim hardware | 🔒 blocked on rig | — |
| 3+ | 4-phase (e1..e4) | 🔒 blocked on rig | — |

When we add a device generation, add a row here and link to the memory
file that captures the architecture decision.
