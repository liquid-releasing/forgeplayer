---
hide:
  - navigation
---

<p align="center">
  <img src="assets/forgeplayer_horizontal.png" alt="ForgePlayer" width="640">
</p>

# ForgePlayer

**Synchronized multi-screen playback with device routing.**

One seek bar. Every screen. Every device. All in sync.

Play a video on your 4K monitor, companion view on your phone, estim
audio to your device, haptics to whatever you have — all from the same
timeline. Mark a favorite moment with one tap. Loop it. Share it.

---

## Start here

<div class="grid cards" markdown>

-   :material-rocket-launch: **[Getting Started](getting-started.md)**

    First-time setup. Install, configure your audio devices, drop a
    scene folder, hit Play.

-   :material-book-open-variant: **[User Guide](user-guide/index.md)**

    Feature-by-feature reference for every tab — Library, Live, Setup,
    Preferences. Debug instrumentation, calibration, content
    preferences.

-   :material-image-frame: **[Quality](quality.md)**

    Why ForgePlayer looks great — libmpv pipeline, scaling, HDR
    handling, GPU color path.

-   :material-television: **[HDR Content](hdr-content.md)**

    Producing HDR10 content (Topaz Video AI workflows) that
    ForgePlayer plays correctly out of the box.

</div>

---

## What it does

```
Video           → any monitor, GPU-color-correct
Estim audio     → dedicated audio port (restim embedded, two instances)
Haptics         → serial / USB / audio-channel routing
```

All driven by the same pack. All synced to the same timestamp.

---

## The pack

A **pack** is one scene's playable content: the **video** plus the **haptic
tracks** that drive your devices, kept together so ForgePlayer can play them in
sync. It comes in two shapes:

### A `.forge` bundle

A single self-describing file exported from FunscriptForge. It carries the
funscripts, every device channel, the pre-rendered stim audio, events, and a
manifest — optionally the video too. **Double-click it and it plays** (no
Library scan needed). This is the shareable, "just works" form.

### A scene folder

The same content as loose files that **share the video's name**. ForgePlayer
matches them by name and shows one Library tile. A folder can hold:

- **Funscripts** (`.funscript`) — the motion tracks. ForgePlayer plays standard
  **1-D position funscripts** today: the main `my-scene.funscript`, plus named
  **stim channels** like `my-scene.alpha-prostate.funscript` routed to a second
  box (Haptic 2). Funscripts synthesize to a stim waveform live (pulse-based or
  continuous). *(Multi-axis / OSR-style axis files aren't a target yet — the
  focus is e-stim.)*
- **E-stim audio** (`.wav` / `.mp3`) — pre-rendered stim sound. When it's
  present ForgePlayer **prefers it over live synth** (no synth artifacts).
  Includes a separate prostate track (`my-scene.prostate.wav`) for Haptic 2.
- **The video** (`.mp4`, `.mkv`, …) — plus any alternate renders (4K, 1080p,
  upscaled); the picker lets you choose which to play.

```
my-scene/
  my-scene.mp4
  my-scene[E-Stim _Popper Edit].mp3      <- pre-rendered stim audio (optional)
  my-scene.funscript                     <- main funscript
  my-scene.alpha-prostate.funscript      <- prostate channel for Haptic 2 (optional)
  my-scene.prostate.wav                  <- pre-rendered prostate audio (optional)
```

Drop the folder. Refresh the Library. Click the tile. Play. — or just
double-click a `.forge`.

---

## Download

**v0.0.12 — released 2026-07-11.**

[:material-download: Download v0.0.12 (Windows / macOS / Linux)](https://github.com/liquid-releasing/forgeplayer-releases/releases/latest){ .md-button .md-button--primary }

### Windows: keeping the download

ForgePlayer isn't code-signed yet, so Windows treats it as an unknown
publisher. The file is safe — you just have to tell Windows to keep it and run
it. Two prompts, in order:

1. **Your browser blocks the download.** Edge/Chrome flags installers from
   unknown publishers. Open the downloads list, find the ForgePlayer file, and
   choose **⋯ → Keep** (Edge) or **▲ / Keep** (Chrome). If it asks again,
   pick **Keep anyway** / **Show more → Keep anyway**.

2. **SmartScreen warns when you run it.** A blue "**Windows protected your
   PC**" dialog appears. Click **More info**, then **Run anyway** to launch the
   installer.

macOS/Linux builds aren't notarized either — on macOS, right-click the app and
choose **Open** the first time to bypass Gatekeeper.

Source on GitHub:
[liquid-releasing/forgeplayer](https://github.com/liquid-releasing/forgeplayer).

---

<p align="center">
  <img src="assets/liquid-releasing-logo.svg" alt="Liquid Releasing" width="120">
</p>

<p align="center"><small>
ForgePlayer is made by <strong>Liquid Releasing</strong>.<br>
© 2026 Liquid Releasing. All rights reserved.
</small></p>
