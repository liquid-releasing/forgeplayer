# ForgePlayer User Guide

Feature-by-feature reference for v0.0.14. If you're brand new, start at
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

## Known limitations (v0.0.14)

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
- **HDR passthrough disabled (v0.0.14)** — the HDR-on-Windows renderer
  (`gpu-next` / libplacebo) crashed on teardown, so playback uses the stable
  `gpu` renderer. HDR10 content can look over-bright on an **HDR-ON** display;
  turn Windows HDR **off** for now. Re-enabling awaits an upstream fix.

See [BACKLOG.md][backlog] (on GitHub) for the full roadmap.

[backlog]: https://github.com/liquid-releasing/forgeplayer/blob/main/BACKLOG.md

---

## Troubleshooting

**A stim port is silent / reads "(unavailable — reselect in Setup)".**
The saved audio device was unplugged or its Windows name changed (common after
a reboot or a USB re-plug). Open **Setup → Audio device roles** and reselect the
device, then **Refresh devices**. ForgePlayer keeps the port silent rather than
routing e-stim to your speakers. If you only have one stim box, set **Haptic 2**
to "— not set —".

**I hear e-stim through my computer speakers.**
That shouldn't happen in v0.0.14. Check that **Haptic 1 / Haptic 2** point at
your **USB dongle** (not "Speakers"), and that **Scene Audio** is a *different*
device. Reselect and **Refresh devices**.

**HDR video looks washed-out or over-bright.**
HDR passthrough is disabled in v0.0.14 for stability. Turn **Windows HDR off**
for the playback monitor (Settings → Display → HDR) while testing.

**Bluetooth output is glitchy / laggy.** Bluetooth audio is untested — use a
**wired / USB** output, especially for stim.

**Closing a video closed the whole app.** That shouldn't happen — grab the crash
log below and file an issue. (A crash *as the app itself exits* is a known
harmless teardown quirk.)

**Filing a good bug report.** Turn on **Debug** (top bar) *before* reproducing,
then attach:

- `~/.forgeplayer/debug-stream-*.jsonl` — the event log for that session
- `~/.forgeplayer/faulthandler.log` — native crash stacks, if it crashed

---

## Where files live

- **Per-scene pin file** — `<scene-folder>/<stem>.forgeplayer.json`
- **Native crash log** — `~/.forgeplayer/faulthandler.log`
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
