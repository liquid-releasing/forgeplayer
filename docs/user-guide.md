# ForgePlayer User Guide

Feature-by-feature reference for v0.0.5. If you're brand new, start at
[Getting Started](./getting-started.md) and come back here when you
need detail.

---

## Window layout

The main control window has four tabs across the top:

- **Library** — your scene browser. Click a tile to activate.
- **Live** — what's currently loaded, what's routing to which device,
  the timeline, transport, and scene-volume slider.
- **Setup** — physical-device assignments (which audio device handles
  which role, which monitor each player goes on, and per-monitor crop
  + crop position).
- **Preferences** — content preference (sound vs funscript), synthesis
  algorithm, haptic offset.

Top bar (right side): **⚑ Mark**, **Debug** toggle, **Export…**, **Clear**.

---

## Supported e-stim hardware

ForgePlayer drives e-stim by sending an **audio signal to a stim power box**.
Each box plugs into **its own audio output — a USB sound-card dongle**
(e.g. a [VENTION USB sound card](https://www.amazon.com/dp/B08LGPKFN5); any
standard USB audio output works), kept separate from your speakers. You assign
which dongle handles each role in **Setup → Audio device roles**:

- **Haptic 1 (main stim)** carries the optional **three-phase / stereostim**
  signal.
- **Haptic 2 (optional)** carries an optional **prostate** signal to a second
  box.

So a full e-stim setup is **one or two USB audio dongles + one or two stim
boxes**. Match the **synthesis algorithm** (Preferences → Generation algorithm)
to your box:

### Three-phase / stereostim boxes — use **Pulse-based**

Modern, audio-driven hardware:

- [The Tingler — StimKit I](https://www.stimkits.com/)
- [EstimHero (Stereo Basic)](https://shop.impudicus.net/products/estim-hero-stereo-basic)
- [ZC95 MKII E-stim Box](https://darkmatter69.com/collections/estim)

### Classic boxes — use **Continuous**

- [MK-312BT](https://erostek.com/products/mk-312bt-power-unit)
- [2B](https://estim.store/collections/2b)

### Not yet supported

- **Coyote (DG-Lab)** — Bluetooth-based; Bluetooth devices haven't been tested
  yet.

> Always **Calibrate** a box (Live tab) and start low before you press play —
> set a comfortable level on the box's own knob first.

---

## Library tab

### Scene tiles

Each tile shows the scene's video thumbnail, name, and small badges for
"has funscript", "has stim audio", "has prostate". A green dot in the
corner means there's a saved pin (your variant picks).

Thumbnails are real frames pulled from the scene's video (one frame ~12 %
in), generated **lazily** — only for tiles you actually scroll past — and
cached to `~/.forgeplayer/thumb_cache/`, so the grid stays responsive even
on a large library and the frames are instant on the next visit. A tile
shows a flat placeholder until its frame is ready (or for audio-only
scenes that have no video).

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

## Opening a `.forge` bundle

A `.forge` is a self-describing scene bundle exported from FunscriptForge —
the motion track, every device channel, the stim audio, events, and a
manifest, all in one file.

### Double-click to play

On Windows, the ForgePlayer **installer** registers the `.forge` file type,
so **double-clicking a `.forge` opens it straight in ForgePlayer and plays**
("Play in ForgePlayer"). Right-clicking offers "Edit in FunscriptForge" to
re-open it for editing. (The portable zip build doesn't register the type —
use the installer if you want the double-click association, or launch
ForgePlayer with the bundle path, e.g. `ForgePlayer.exe "Scene.forge"`.)

`.forge` bundles don't appear as Library tiles — they're single files you
open directly, not scanned scene folders.

### How it finds the video

A bundle is lean by default: it carries the funscripts, the channels, and
the stim audio, but **not** the (potentially multi-GB) source video. When
you open one, ForgePlayer relinks the video in this order:

1. **Inside the bundle** — if it was exported with **"include media"**, the
   video rides inside the `.forge` and plays directly. Fully self-contained;
   works on any machine, no external file needed.
2. **The original location** — the absolute path the video lived at when it
   was exported (recorded in the bundle's manifest). On the same machine,
   this resolves wherever the bundle itself happens to sit — the `.forge`
   does **not** have to be next to the video.
3. **Next to the bundle** — a video with the recorded filename sitting in
   the same folder as the `.forge` (or its parent). This is the case that
   needs adjacency: it's how a **shared** lean bundle finds its video on
   someone else's disk.

If none of those resolve, the scene **still opens and plays** — funscripts,
stim, everything — just with no picture, and ForgePlayer prompts you to
attach a video manually.

**Sharing tip:** for a bundle that "just plays" anywhere with zero setup,
export it with **include media** (option 1 — video inside). To share lean
bundles, keep the video file beside the `.forge` (option 3). For your own
machine, it finds the original wherever it is (option 2).

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

The Video panel has a **Fullscreen players** toggle. Off → players open
as windowed 1280×720 with title bars (good for adjusting). On → players
go kiosk-mode covering the whole monitor.

The toggle is **live**: flip it while players are already open and every
open window goes fullscreen (or back to windowed) immediately — you don't
have to relaunch. New launches read the toggle's current state.

`F11` inside any player window also toggles fullscreen for that slot.

### Video playback & 4K

ForgePlayer uses GPU hardware decoding when it's available (`hwdec=auto-safe`),
falling back to the CPU for anything the GPU can't handle.

- **A GPU is not required.** Integrated graphics play 1080p and typical 4K
  fine.
- For **large / high-bitrate 4K** (e.g. AI-upscaled sources), any GPU with
  hardware video decoding — NVIDIA, AMD, or Intel — plays far more smoothly by
  offloading decode from the CPU. On CPU-only decoding, a very demanding 4K
  file can saturate the processor and stutter both the video and the haptic
  sync, so if a big 4K scene isn't smooth, that's the cause — try a machine
  with hardware decode, or play a 1080p variant of the scene.

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

### Crop (per monitor)

Under **Monitor roles**, each playback screen has a **Crop** checkbox. Off
→ the video is letterboxed/pillarboxed to preserve its native aspect. On →
the video is scaled up to fill that monitor's aspect (mpv panscan) — useful
for 16:9 content on a 32:9 ultrawide instead of leaving black bars.

(This is distinct from the Live tab's **Fullscreen players** toggle, which
controls whether the *window* takes over the whole monitor.)

### Crop position

When a screen is cropping, the **Crop position** radios choose which part of
the frame to keep in the cropped dimension:

- **Center** (default) — keep the middle, trim equally top and bottom.
- **Top** — keep the top of the frame (with about a ⅛ margin so a subject
  near the top edge isn't sliced off).
- **Bottom** — keep the bottom of the frame (same ⅛ margin off the bottom).

One choice applies to every cropping screen, and it applies **live** to any
open players whose monitor is cropping.

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

- **Pulse-based** *(default)* — power-efficient waveform with shaped
  discrete pulses. Slower numbing. For modern audio-based stereostim
  hardware (Tingler, EstimHero, and similar). ForgePlayer defaults to
  this because that's what the FunscriptForge content pipeline targets.
- **Continuous** — classic restim waveform. Best for 312 / 2B-style
  hardware. Lower power efficiency. Works well at ~100 Hz. Flip to this
  once if that's your box.

(The default applies to a fresh install; an existing `preferences.json`
keeps whatever you last chose.)

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

## Known limitations (v0.0.5)

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
- **Library thumbnails (cache)** — `~/.forgeplayer/thumb_cache/*.jpg`
- **Session state** — `~/.forgeplayer/<session-name>.session.json`
- **Debug logs (when enabled)** — `~/.forgeplayer/debug-stream-*.jsonl`
- **Stim recordings (when env var set)** — `<your-chosen-dir>/stim-*.wav`

---

## Where to ask

- Bugs / behavior issues — open an issue in the repo.
- Architecture questions — read [`docs/architecture/`][archdir] (on
  GitHub) first; that's the dev-facing set, deeper than this guide.

[archdir]: https://github.com/liquid-releasing/forgeplayer/tree/main/docs/architecture
