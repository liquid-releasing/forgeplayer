# ForgePlayer User Guide

Feature-by-feature reference for v0.0.4. If you're brand new, start at
[Getting Started](./getting-started.md) and come back here when you
need detail.

---

## Window layout

The main control window has four tabs across the top:

- **Library** — your scene browser. Click a tile to activate.
- **Live** — what's currently loaded, what's routing to which device,
  the timeline, transport, and scene-volume slider.
- **Setup** — physical-device assignments (which audio device handles
  which role, which monitor each player goes on, fullscreen vs windowed).
- **Preferences** — content preference (sound vs funscript), synthesis
  algorithm, haptic offset.

Top bar (right side): **⚑ Mark**, **Debug** toggle, **Export…**, **Clear**.

---

## Library tab

### Scene tiles

Each tile shows the scene's video thumbnail, name, and small badges for
"has funscript", "has stim audio", "has prostate". A green dot in the
corner means there's a saved pin (your variant picks).

### Activating a scene

**Single-click** a tile to activate. If the scene has multiple variants
(more than one funscript set, or alternate video edits), a **picker
dialog** opens:

- **Funscript set** — for scenes with multiple authoring versions
  (e.g. "Magik Number 3 Pt 1 (6 channels)" vs "Magik Number 3 Pt 1
  (10 channels, prostate)"). Pick the one you want playing.
- **Video variant** — original vs upscaled vs ultrawide-crop, etc.
- **Stim audio** — the pre-rendered `.mp3` files in the folder that
  drive the stim port when content preference is "sound".
- **Subtitles** — None / language picks.

Defaults are sensible: highest-numbered set, original video, first
matched stim audio, no subtitle. Click **OK**.

Your picks are saved as a `.forgeplayer.pin.json` in the scene folder.
Next time you single-click the tile, ForgePlayer skips the picker and
re-uses the pinned choices.

### Re-opening the picker

Click the **Change picks…** menu on a tile (or the title-bar button on
the Live tab) to re-open the picker for the active scene. New picks
overwrite the pin.

### Refresh

If you add or remove files in a scene folder while ForgePlayer is
running, click **Refresh** to re-scan.

---

## Live tab

### Output panel

Shows the live source → destination map for the loaded scene:

```
Scene Audio: <device>           <-- mp3 / mp4 audio of the video
  <video filename>
Haptic 1: <device>              <-- main stim port
  <funscript or .mp3 filename>
Haptic 2: <device>              <-- prostate port
  <prostate source or "(mirror H1)" or "(silent — ...)"
```

The H2 line tells you exactly what's playing there:

- `<scene-stem>-prostate.funscript` — the prostate funscript synth.
- `<scene-stem>.prostate.wav` — the pre-rendered prostate audio file.
- `(mirror H1) <stem>.funscript` or `<stem>.mp3 (mirror H1)` —
  mirrors whatever H1 is playing.
- `(silent — no device set in Setup)` — Haptic 2 unconfigured.
- `(silent — same device as Haptic 1)` — H2 set to the same device
  as H1; would conflict on the exclusive output handle.

### Timeline + scene volume

Side-by-side row above the transport buttons. **Timeline** is 75 % of
the row; **scene volume** is 25 %. Time elapsed and total duration sit
in their own small labels above the timeline; "🔊 Scene volume — 100 %"
sits above the volume slider.

The two sliders are visually distinct so you don't grab one thinking
it's the other. Volume is per-session (resets to 100 % every scene).

### Transport

`−30 s · −10 s · −5 s · ▶ Play / ⏸ Pause · +5 s · +10 s · +30 s · ■ Stop`

Plus **Calibrate H1**, **Calibrate H2** (when devices set), and a
**5 s ramp** checkbox that affects the calibration ramp-up.

### Seek behavior

Every seek runs through the same three-stage envelope to mask the
funscript-driven carrier discontinuity that would otherwise click:

1. **500 ms ramp-down** to silence
2. **mpv seek** at silence
3. **200 ms settle hold** at silence — lets mpv's decoder reach steady
   state at the new position before audio comes back
4. **500 ms ramp-up** to full output

Total perceived gap: ~1.2 s. Visible as a clean dip in the recording
waveform if you record the output.

### Fullscreen

The Video panel has a **Fullscreen** toggle. Off → players open as
windowed 1280×720 with title bars (good for adjusting). On → players
go kiosk-mode covering the whole monitor.

`F11` inside any player window also toggles fullscreen for that slot.

---

## Setup tab

### Audio device roles

Three dropdowns:

- **Scene Audio** — the video's audio.
- **Haptic 1** — main stim port.
- **Haptic 2** — prostate / second stim port (optional).

Dropdowns list every audio output Windows reports through mpv. If a
dongle isn't there, plug it in. ForgePlayer doesn't open these for
exclusive mode automatically; only stim streams (H1 / H2) attempt
exclusive on launch.

### Test device buttons

Each row has a **Test** button that routes a brief tone to the picked
device so you can verify the dongle is wired up before launching a
scene. (Stim test routes to the haptic device; scene-audio test plays
through the scene-audio device.)

### Monitors

For each player slot, pick which monitor it lands on. The dropdown
auto-populates with whatever Qt enumerates. Helpful labels include
the model name where the monitor reports it.

### Fullscreen / Crop

The Setup tab's "Fill" / "Crop" toggle determines how each video slot
renders — letterboxed within window vs cropped to fill. (The Live tab
has its own Fullscreen toggle for the kiosk-mode behaviour.)

---

## Preferences tab

### Content preference

- **Sound files (.wav / .mp3)** — default. Pre-rendered stim audio
  wins when available. No synth pops, no algorithm choice. Most
  stereo-stim scenes ship a sound file.
- **Funscripts (live synth)** — synthesizes from the funscript in
  real time. Lets you pick the synthesis algorithm (continuous /
  pulse-based) and adjust haptic offset live.

Either preference falls back across forms at Haptic 1 (silent stim
is worse than wrong-form). Haptic 2 only ever plays prostate-specific
sources for the matching preference, otherwise mirrors H1.

### Generation algorithm (when preference is funscript)

- **Continuous** — classic restim waveform. Best for 312 / 2B-style
  hardware. Lower power efficiency. Works well at ~100 Hz.
- **Pulse-based** — power-efficient waveform with shaped discrete
  pulses. Slower numbing. For modern audio-based stereostim hardware.

### Haptic offset (s)

Shift the stim signal relative to the video. **Positive** = stim
leads video; **negative** = stim lags. Compensates for USB / driver
latency. Captured at launch — changing mid-playback applies on the
next launch.

---

## Calibrate

Click **Calibrate H1** (or **H2**) to send a steady carrier tone to
the haptic device. Toggle on / off. Useful for:

- Verifying the dongle is connected and powered.
- Setting your levels via the dongle's physical knob before play.
- Positioning electrodes safely (steady output you can adjust to).

The **5 s ramp** checkbox ramps the calibration carrier up over five
seconds instead of stepping in immediately — gentler on the body.

Calibration is allowed in the post-launch / pre-first-play window so
you can verify haptic levels with the player windows already up.

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

---

## Sessions

Top bar shows the current session name. ForgePlayer auto-saves
session state (which scene is loaded, which monitors / devices are
assigned) on changes. Re-opening ForgePlayer restores the last
session unless you explicitly start a new one via the Library scan.

---

## Known limitations (v0.0.4)

- **Control panel sizing on monitor change** — moving the control
  window to a smaller secondary screen can leave it taller than
  720 px. Cosmetic. Post-alpha fix.
- **Click +10 s while stopped** — timeline jumps to 0 instead of
  staying at the seeked position. Post-alpha fix.
- **Empty Live tab when nothing is loaded** — currently looks empty;
  hint text coming.
- **Single-decoder for video walls** — currently three independent
  decoders synced via mpv time-pos. Frame-perfect single-decoder
  rendering is a future feature for true video-wall use cases.

See [BACKLOG.md][backlog] (on GitHub) for the full roadmap.

[backlog]: https://github.com/liquid-releasing/forgeplayer/blob/main/BACKLOG.md

---

## Where files live

- **Per-scene pin file** — `<scene-folder>/<stem>.forgeplayer.pin.json`
- **App preferences** — `~/.forgeplayer/preferences.json`
- **Session state** — `~/.forgeplayer/<session-name>.session.json`
- **Debug logs (when enabled)** — `~/.forgeplayer/debug-stream-*.jsonl`
- **Stim recordings (when env var set)** — `<your-chosen-dir>/stim-*.wav`

---

## Where to ask

- Bugs / behavior issues — open an issue in the repo.
- Architecture questions — read [`docs/architecture/`][archdir] (on
  GitHub) first; that's the dev-facing set, deeper than this guide.

[archdir]: https://github.com/liquid-releasing/forgeplayer/tree/main/docs/architecture
