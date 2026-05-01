# Audio routing — sources, destinations, fan-out

> **Status:** v0.0.3 introduces aux streams (Haptic 2 prostate output).
> This doc generalizes that to the future-facing pattern so new sources
> and destinations slot in cleanly.

---

## The mental model

The control panel (Setup tab today; Library / Live / Settings / Preferences
once the tab reorder lands) is a **routing layer** that wires audio
**sources** to physical-device **destinations**.

```
   ┌──────────────┐                 ┌──────────────┐
   │   SOURCE     │   StimAudioStream│  DESTINATION │
   │              │  ───────────────▶│              │
   │ stim synth,  │                  │ USB dongle,  │
   │ audio file,  │                  │ headset,     │
   │ TCode reader,│                  │ shaker array,│
   │ ...          │                  │ ...          │
   └──────────────┘                  └──────────────┘
```

A single source can fan out to multiple destinations (one MP4 audio →
headset + shaker array). A destination can carry one source at a time
(OS-level constraint — a single audio device can't play two streams
simultaneously).

The `slot_data` dict on each ControlWindow slot holds:

- `stim_audio_stream` — the **primary** audio stream for that slot
  (Haptic 1 stim synth)
- `aux_audio_streams: list[StimAudioStream]` — additional outputs
  piggy-backing on the same slot (Haptic 2 prostate today; future
  MP4 fan-outs to headset + shaker arrays etc.)

`_close_players()` iterates both, stopping all streams in parallel via
a `ThreadPoolExecutor` so the per-stream 40 ms fade-out doesn't compound
into noticeable lag on close.

---

## The audio-source protocol

Any object that implements two members can drive a `StimAudioStream`:

```python
class AudioSource(Protocol):
    sample_rate: int  # Native rate; the OutputStream opens at this rate

    def generate_block_with_clocks(
        self,
        steady_clock: np.ndarray,        # length = frames; sample-counter time
        system_time_estimate: np.ndarray, # length = frames; smoothed media-time
    ) -> np.ndarray:                     # shape (frames, 2), float32
        ...
```

That's it. `StimAudioStream` calls `generate_block_with_clocks` on every
audio-thread callback with `frames` worth of clock data and writes the
returned stereo PCM to the device. It doesn't care what the source is.

This is structural typing — there is no explicit `Protocol` declaration;
Python's duck typing + the convention is sufficient for v0.0.3. If we
later want runtime validation, add a `typing.Protocol` to
`app/stim_audio_output.py` and annotate `StimAudioStream.synth: AudioSource`.

### Existing implementations

| Class | Source kind | File | Notes |
| --- | --- | --- | --- |
| [`StimSynth`](../../app/stim_synth.py) | Live synthesis from a `StimChannels` (alpha/beta + parameter channels) | `app/stim_synth.py` | Wraps vendored restim algorithms (continuous + pulse-based threephase). Used for Haptic 1 main stim, Haptic 2 prostate, and Haptic 2 mirror_h1 fallback. |
| [`AudioFilePlaybackSource`](../../app/stim_audio_output.py) | Pre-rendered `.wav` PCM file | `app/stim_audio_output.py` | Stdlib `wave` decoder. Option B sample-rate handling: requires file rate to match device rate, raises clean error otherwise. Mono auto-tiled to stereo. |

### Future implementations (sketch)

| Class (proposed) | Source kind | When |
| --- | --- | --- |
| `MPVAudioTapSource` | Tap of mpv's currently playing audio track | When MP4 fan-out lands (single MP4 audio → headset + shaker array). Probably feeds via mpv's `lavfi` filter chain or a duplicate decode. |
| `BHapticsTactSource` | `.tact` file decoded into stereo PCM (or device-specific waveform) | When bHaptics integration lands (Phase 3 in BACKLOG). |
| `TCodeMechanicalSource` | TCode v0.2/0.3 commands rendered as audio for audio-driven mechanical actuators | When TCode device support lands. |
| `BeatDrivenShakerSource` | Live beat detection from a sibling audio track → shaker funscript-equivalent waveform | Forgegen-family extension; could live in forgegen and emit a `.funscript` ForgePlayer just plays. |
| `LiveAudioCaptureSource` | WASAPI loopback / BlackHole capture → real-time haptic generation | Phase 5 in BACKLOG (audio-to-haptic mode). |

Each of these implements the two-method protocol and slots into the
existing `StimAudioStream` plumbing without touching it.

---

## Source-detection cascade

Per slot launch, the control window decides which source to instantiate
for each destination. The Haptic 2 cascade (`_maybe_launch_haptic2_aux`)
is the canonical pattern; the cascade itself **is** the policy — there
is no user-configurable fallback preference (the v0.0.2
`Preferences.haptic2_fallback` field has been removed).

### Haptic 2 cascade — current ordering (decided 2026-05-01)

1. **Prostate WAV** — sibling `<stem>.prostate.wav` exists →
   `AudioFilePlaybackSource`. **Wins over funscripts when both are
   present.** See "Audio over synth" below for the rationale.
2. **Prostate funscripts** — `alpha-prostate` channel present
   (`beta-prostate` and `volume-prostate` optional) → second `StimSynth`
   with `prostate=True` channels. When `beta-prostate` is missing, the
   beta carrier is synthesized as zeros — correct for single-pair
   prostate hardware. Real prostate scripts in the wild ship
   `alpha-prostate` alone (Euphoria, Zer0 Game), so this branch is the
   common case.
3. **Mirror Haptic 1** — neither prostate source available → second
   `StimSynth` with the same primary channels Haptic 1 is playing.
   Two independent synth instances (not shared state) for thread
   safety; the doubled CPU cost is acceptable.
4. **Silent** — early-returns when no Haptic 2 device is configured in
   Setup, or when the H2 device picker matches H1 (would conflict on
   the exclusive output handle).

### Audio over synth: why pre-rendered files win when both exist

Pre-rendered `.wav` files produce cleaner output than the live synth
under the conditions our users actually hit:

- **Seek behavior.** mpv / PortAudio's decoder-side resync logic is
  decades old and well-tuned for seek-without-clicks. The synth path
  recomputes modulation per-buffer; when a seek lands inside a fade
  window, the alpha/beta values that drive the carrier flip
  discontinuously. v0.0.2 dogfood measured a residual ~7% audible click
  rate on synth playback ([`BACKLOG.md`](../../BACKLOG.md) v0.0.3
  polish item). Files don't have that math at runtime — they're already
  flat PCM samples.
- **Pre-render quality.** A `<stem>.prostate.wav` only exists because
  someone deliberately rendered it. They could tune the algorithm,
  smooth the edges, and audition the result before shipping. A
  funscript played live gives us no opportunity to do that.
- **Tunability tradeoff.** The synth path lets users switch algorithm
  (continuous ↔ pulse) and adjust offset live. Files freeze those
  decisions at render time. We accept the tradeoff because the rare
  scene that ships both forms presumably had its WAV rendered with the
  right algorithm choice for the content.

The practical impact of this priority is small: pre-rendered prostate
WAVs are uncommon in the wild, and most scenes end up at tier 2
(funscript synth) regardless. But for the subset of scenes that do
ship a WAV, the user gets the cleaner playback path automatically.

The bigger leverage is **fixing the synth's pop behavior itself** —
that's the BACKLOG v0.0.3 item, and it benefits every alpha-only scene
(the common case) plus the mirror-H1 tier.

### Extending to new destinations

When extending to a new destination (e.g., shaker array):

- Add a destination preference field to `Preferences`
  (`shaker_audio_device: str`). **Don't** add a per-destination
  fallback enum — the cascade itself should be the policy. Adding a
  user-pick field re-introduces the configuration-mismatch bugs the
  cascade rewrite was designed to remove.
- Add a detection helper in `funscript_loader.py` (or wherever the
  source-class implementation lives) returning a tagged result.
- Add a `_maybe_launch_<destination>_aux` method following the same
  shape as `_maybe_launch_haptic2_aux`, called from the appropriate
  launch path. Order tiers so that pre-rendered files beat live synth
  when both are present, mirroring the Haptic 2 cascade.
- The aux stream is appended to the slot's `aux_audio_streams` list so
  `_close_players` cleans it up automatically.

---

## Sample rate / format

**Constraint:** all destinations on a single slot launch run at the same
sample rate. This avoids:

- Per-source resampling (the synth math runs at whatever rate it's
  asked for; resampling an audio file at runtime is real CPU on the
  audio thread)
- Drift compensation between streams running at different clocks
- Format conversion in the audio callback

We document this in the Setup-tab help text ("similar Haptic 2 device
recommended"). If users wire different-rate destinations, they get a
log warning and play at the destination's rate — pitch/timing on the
mismatched stream is the user's problem to fix by choosing a
matching device.

`AudioFilePlaybackSource` enforces this at construction: a sample-rate
mismatch raises `ValueError` with a clear "re-export at <rate> Hz"
message. The aux launcher catches it and logs; the destination falls
through to silent rather than playing wrong-pitch audio.

---

## Threading model

- **Audio callbacks** run on per-stream sounddevice threads. Each
  `StimAudioStream` owns one. They never share state with each other.
- **Source instances** are constructed once on the main (Qt) thread and
  read-only thereafter. `StimSynth` is safe to share between two
  `StimAudioStream` instances structurally (no mutable state in
  `generate_block_with_clocks`), **but** the vendored restim algorithms
  aren't documented as thread-safe under concurrent `generate_audio`
  calls — so for safety we instantiate a *second* synth for the
  `mirror_h1` fallback rather than sharing.
- **Time source** (`engine.get_position`) is thread-safe by mpv's API
  contract. All streams in a slot share the same `time_source` callable
  and receive identical media-time observations.
- **Pause/play gating** uses a single `is_playing_source` callable per
  slot, sampled by each stream's audio callback independently. Both
  streams fade in/out together because they observe the same engine state.
- **Stream stops** run in parallel via `ThreadPoolExecutor` in
  `_close_players` to amortize the 40 ms fade-out window.

---

## What this is NOT

- **Not a graph.** Sources aren't first-class long-lived nodes that you
  rewire dynamically. Each launch instantiates fresh sources/streams;
  `_close_players` tears them all down. The "graph" only exists for the
  duration of a launch.
- **Not a plug-in system.** Adding a new source class today means
  editing `_maybe_launch_haptic2_aux` (or its sibling for the new
  destination). If we need true runtime registration later, lift the
  detection cascade into a `SourceRegistry` and let modules register
  detectors. v0.0.3 has two source classes; not enough to justify the
  abstraction.
- **Not a DSP framework.** `StimAudioStream`'s callback does fade
  gating and clock smoothing, not arbitrary effects chains. If we need
  per-source EQ / compression / mixing, that's a separate layer between
  sources and the OutputStream.

---

## Open questions for the next iteration

1. Should `Preferences` grow a generic `aux_routings: list[AuxRouting]`
   instead of named fields per role (`haptic2_audio_device`,
   `shaker_audio_device`, etc.)? Pro: extensible without schema bumps.
   Con: harder for users to reason about ("which one is my prostate
   dongle?"). Probably stay with named fields until we have 5+ roles.
2. Where does the **sources catalog** live? `docs/architecture/sources/`
   one file per source kind? Or extend this doc with a Sources section
   for each? Defer until there are 4+ source classes.
3. **Live source registration** — if forgegen evolves to emit
   `.tact-equivalent` files we don't yet know about, should ForgePlayer
   detect them generically (file extension + sniff) or require a
   registered handler? Defer.
