# Settings

The **Preferences** tab controls how ForgePlayer turns a scene into a signal —
which form of haptics it prefers, how it synthesizes from a funscript, and
timing offset.

## Content preference

- **Sound files (.wav / .mp3)** — default. Pre-rendered stim audio
  wins when available. No synth pops, no algorithm choice. Most
  stereo-stim scenes ship a sound file.
- **Funscripts (live synth)** — synthesizes from the funscript in
  real time. Lets you pick the synthesis algorithm (continuous /
  pulse-based) and adjust haptic offset live.

Either preference falls back across forms at Haptic 1 (silent stim
is worse than wrong-form). Haptic 2 only ever plays prostate-specific
sources for the matching preference, otherwise mirrors H1.

## Generation algorithm (when preference is funscript)

- **Pulse-based** *(default)* — power-efficient waveform with shaped
  discrete pulses. Slower numbing. For modern audio-based stereostim
  hardware (Tingler, EstimHero, and similar). ForgePlayer defaults to
  this because that's what the FunscriptForge content pipeline targets.
- **Continuous** — classic restim waveform. Best for 312 / 2B-style
  hardware. Lower power efficiency. Works well at ~100 Hz. Flip to this
  once if that's your box.

(The default applies to a fresh install; an existing `preferences.json`
keeps whatever you last chose.)

## Haptic offset (s)

Shift the stim signal relative to the video. **Positive** = stim
leads video; **negative** = stim lags. Compensates for USB / driver
latency. Captured at launch — changing mid-playback applies on the
next launch.

---

## Debug mode

Top bar **Debug** toggle (off by default).

When **on**:

- Every event streams to `~/.forgeplayer/debug-stream-<timestamp>.jsonl`
  in real time (one event per line — survives a hard crash).
- The **⚑ Mark** button captures a timestamped marker. Press it
  whenever you hear / feel / see something weird during dogfood. The
  count next to the icon shows how many events have been recorded.
- **Export…** writes the in-memory event buffer to a single
  `~/.forgeplayer/debug-<timestamp>.json`.
- **Clear** wipes the in-memory buffer (the on-disk stream survives).

What's logged:

- UI clicks (transport, seek, library activate, setup changes)
- Library scan / variant resolution / pin save / pin replay
- Engine launch / teardown / fullscreen toggles
- Stim source dispatch (`stim.dispatch`), prostate resolver
  (`stim.aux_resolved`), source-probe peak / RMS at t=0 / t=30s
- Audio-thread events (auto-resync, seek envelope stages)
- mpv device list

When **off**, every recording call returns immediately. No measurable
overhead.

### Debug environment variables

For pop investigation only — set before launching ForgePlayer:

- **`FORGEPLAYER_SYNTH_ISOLATION`** — `off` (default), `constant`,
  `alpha`, `alpha_beta`, `alpha_beta_volume`. Strips funscript axes
  one at a time so you can bisect which axis (if any) drives audible
  artifacts. `constant` puts a steady carrier with no modulation at
  all; each next mode adds one axis on top.
- **`FORGEPLAYER_RECORD_STIM_DIR`** — path to a directory. When set,
  every StimAudioStream callback writes its output block to a
  per-stream `int16` WAV in that directory. Open in Audacity to
  visualize / listen to exactly what we sent the audio device.

Both are off by default. Production paths pay nothing.
