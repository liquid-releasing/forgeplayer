# ForgePlayer User Guide

Feature-by-feature reference for v0.0.13. If you're brand new, start at
[Getting Started](../getting-started.md) and come back here when you
need detail.

The guide follows the app's four tabs — each has its own page:

<div class="grid cards" markdown>

-   :material-view-grid: **[Library](library.md)** — your scene browser, how
    tiles are matched, and opening `.forge` bundles.

-   :material-play-circle: **[Live](live.md)** — what's loaded, device routing,
    the timeline, transport, fullscreen, and calibration.

-   :material-tune-vertical: **[Setup](setup.md)** — audio device roles,
    monitors, and per-monitor crop.

-   :material-cog: **[Settings](settings.md)** — content preference, synthesis
    algorithm, haptic offset, and debug mode.

</div>

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
boxes**. Match the **synthesis algorithm** (Settings → Generation algorithm)
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

> Always **Calibrate** a box ([Live tab](live.md#calibrate)) and start low
> before you press play — set a comfortable level on the box's own knob first.

---

## Sessions

Top bar shows the current session name. ForgePlayer auto-saves
session state (which scene is loaded, which monitors / devices are
assigned) on changes. Re-opening ForgePlayer restores the last
session unless you explicitly start a new one via the Library scan.

---

## Known limitations (v0.0.13)

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

- **Per-scene pin file** — `<scene-folder>/<stem>.forgeplayer.json`
- **Library catalog index** — `~/.forgeplayer/catalog.json`
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
