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

-   :material-book-open-variant: **[User Guide](user-guide.md)**

    Feature-by-feature reference for every tab — Library, Live, Setup,
    Preferences. Debug instrumentation, calibration, content
    preferences.

-   :material-image-frame: **[Quality](quality.md)**

    Why ForgePlayer looks great — libmpv pipeline, scaling, HDR
    handling, GPU color path.

-   :material-television-clean: **[HDR Content](hdr-content.md)**

    Producing HDR10 content (Topaz Video AI workflows) that
    ForgePlayer plays correctly out of the box.

</div>

---

## What it does

```
Video           → any monitor, GPU-color-correct
Estim audio     → dedicated audio port (restim embedded, two instances)
Haptics         → serial / USB / audio-channel routing
Phone           → companion view + touch remote (planned)
```

All driven by the same pack. All synced to the same timestamp.

---

## The pack

Everything for one scene lives in one folder:

```
my-scene/
  my-scene.mp4
  my-scene[E-Stim _Popper Edit].mp3      <- pre-rendered stim audio (optional)
  my-scene.funscript                     <- main funscript
  my-scene.alpha-prostate.funscript      <- prostate channel for Haptic 2 (optional)
  my-scene.prostate.wav                  <- pre-rendered prostate audio (optional)
```

Drop the folder. Refresh the Library. Click the tile. Play.

---

## Status

**v0.0.4 — preparing alpha (2026-05-03).** See the
[GitHub repository](https://github.com/liquid-releasing/forgeplayer)
for source and the latest release.
