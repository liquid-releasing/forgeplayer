# ForgePlayer.app

**Synchronized multi-screen playback with device routing.**

One seek bar. Every screen. Every device. All in sync.

Play a video across your monitors and drive e-stim from the **same
timeline and seek bar** — video and haptics stay in sync through every
play, pause, seek, and skip. No mouse required once you're watching.

### ▶ Download & try it at [forgeplayer.app](https://forgeplayer.app) · [Discord](https://discord.gg/MHucAwwRc) · [Docs](https://liquid-releasing.github.io/forgeplayer/)

---

## Links

- **Download / try it:** [forgeplayer.app](https://forgeplayer.app) —
  Windows / macOS / Linux builds.
- **User docs:** [getting started](https://liquid-releasing.github.io/forgeplayer/getting-started/)
  · [user guide](https://liquid-releasing.github.io/forgeplayer/user-guide/)
  · [docs home](https://liquid-releasing.github.io/forgeplayer/)
- **Discord:** [discord.gg/MHucAwwRc](https://discord.gg/MHucAwwRc) — feedback,
  ideas, bug reports.

---

## Status

**v0.0.15 — alpha.** Windows is the most-tested platform; macOS and
Linux builds ship from the same CI pipeline but are less battle-tested,
and Bluetooth audio devices are untested on any platform (use wired /
USB). Not code-signed yet, so Windows SmartScreen and macOS Gatekeeper
both need a one-time "trust this anyway" click — see
[docs/getting-started.md](./docs/getting-started.md).

Working today: synchronized multi-monitor video, dual-port stim
(Haptic 1 / Haptic 2) with either pre-rendered stim audio or live
funscript synthesis, `.forge` bundle import (double-click and play),
scene-folder library scanning with a variant picker, chapter
navigation with seek-bar markers, hardware calibration, and an in-app
update check against forgeplayer.app. See [SPEC.md](./SPEC.md) for the
full alpha design spec, [BETA_TODO.md](./BETA_TODO.md) for what's left
before a beta label, and [docs/getting-started.md](./docs/getting-started.md)
for first-time setup.

---

## Supported e-stim hardware

ForgePlayer drives e-stim by sending an audio signal to a stim power box
through an audio output. Each stim box plugs into **its own audio output —
a USB sound-card dongle** (e.g. a [VENTION USB sound
card](https://www.amazon.com/dp/B08LGPKFN5); any standard USB audio output
works), separate from your speakers. You assign which dongle each role uses in
**Setup**:

- **Haptic 1 (main stim)** — the optional **three-phase / stereostim** signal.
- **Haptic 2 (optional)** — an optional **prostate** signal to a second box.

So you'll want **one or two USB audio dongles + one or two stim boxes.**

**Three-phase / stereostim boxes** (modern, audio-driven — use the **Pulse-based**
algorithm):

- [The Tingler — StimKit I](https://www.stimkits.com/)
- [EstimHero (Stereo Basic)](https://shop.impudicus.net/products/estim-hero-stereo-basic)
- [ZC95 MKII E-stim Box](https://darkmatter69.com/collections/estim)

**Classic boxes** (use the **Continuous** algorithm):

- [MK-312BT](https://erostek.com/products/mk-312bt-power-unit)
- [2B](https://estim.store/collections/2b)

**Not yet supported:** Coyote (DG-Lab) — it's Bluetooth-based, and Bluetooth
devices haven't been tested yet.

---

## The Problem It Solves

VLC plays video. restim plays estim. Your haptic device has its own app. None of them talk to each other. Syncing them is a manual nightmare and full-screen doesn't survive it.

ForgePlayer.app is the hub. It plays everything. It routes everything. It stays in sync when you seek, skip, or loop.

---

## What It Does

```
Video     → any monitor, up to two synced mirror outputs, GPU decode
Estim     → dedicated USB audio port(s), Haptic 1 + Haptic 2, live synth or pre-rendered audio
Chapters  → Prev/Next transport + seek-bar markers, on the console and each player window
```

All driven by the same pack. All synced to the same timestamp.

Video plays through **one mpv instance per output** (primary + up to two
mirrors), each locked to the same media clock so seeks land in
sub-frame sync across every monitor. Chapter navigation and markers
come from an optional `<video_stem>.chapters.json` sidecar — the kind
FunscriptForge produces — and appear both as tick marks on the seek
bar and as Prev/Next buttons on the control window and on every player
window's own overlay.

---

## The Pack

A **pack** is one scene's playable content: the video plus the haptic
tracks that drive your devices. It comes in two shapes.

**A `.forge` bundle** — a single file exported from FunscriptForge.
Double-click it (after installing) and it plays — no Library scan
needed.

**A scene folder** — loose files that share the video's name:

```
my-scene/
  my-scene.mp4                                    <- main video
  my-scene[E-Stim _Popper Edit].mp3               <- pre-rendered stim audio (optional)
  my-scene.funscript                              <- main funscript (1D position track)
  my-scene.alpha-prostate.funscript               <- prostate channel for Haptic 2 (optional)
  my-scene.prostate.wav                           <- pre-rendered prostate audio (optional)
  my-scene.chapters.json                          <- chapter sidecar (optional)
```

Drop the folder anywhere readable. ForgePlayer scans it on the next
Library refresh, shows one tile per scene, and offers a picker when a
scene has more than one funscript set, video variant, or stim-audio
file to choose from. Picks are remembered per scene.

---

## Estim Routing

Two independent stim paths, one per haptic role, both driven from the
same media clock:

- **Haptic 1** — main stim.
- **Haptic 2** — optional prostate channel; mirrors Haptic 1 when a
  scene doesn't ship a dedicated prostate source.

Each scene can drive stim two ways, and you choose which one ForgePlayer
prefers in **Preferences**:

- **Live funscript synthesis** — real-time audio synthesis from the
  funscript using ForgePlayer's vendored copy of restim's `stim_math`
  waveform engine (continuous mode for classic 312/2B-era boxes,
  pulse-based mode for modern stereostim / FOC-stim content).
- **Pre-rendered stim audio** (`.wav` / `.mp3`) — plays the file
  directly through mpv when a scene ships one, avoiding any synth
  artifacts.

When the preferred form isn't available for a scene, ForgePlayer falls
back to the other one rather than going silent. WASAPI exclusive mode
is used for stim streams on Windows to sidestep shared-mixer
contention, falling back to shared mode if exclusive open fails.

Powered by diglet48/restim: https://github.com/diglet48/restim

---

## HDR video

HDR10 files play, but HDR **passthrough** is disabled in v0.0.15 —
mpv's HDR renderer (`gpu-next`) crashed on teardown, so this build uses
the stable `gpu` renderer, which tone-maps HDR down to SDR instead of
passing it through. On a display with Windows/macOS HDR turned **on**
this can look over-bright; turn HDR off for the playback monitor until
passthrough returns. See [docs/hdr-content.md](./docs/hdr-content.md)
and [docs/quality.md](./docs/quality.md) for the full story and how to
produce HDR10 content that's ready once passthrough is back.

---

## The Ecosystem

```
FunscriptForge Explorer → FunscriptForge → funscript-tools → ForgeAssembler → ForgePlayer.app
   originate                edit/shape       estim character    assemble          play everything
```

Funscripts are the connective tissue. Every tool reads and writes them.

Sibling repositories:

- **syncplayer** — the video-wall industrial variant of this same player (separate project)
- **eHaptics engine + Studio** — the canonical haptics library and authoring tool (separate projects)

---

## Tech Stack

- **mpv** (https://mpv.io) — frame-accurate, cross-platform media engine
- **python-mpv** (https://github.com/jaseg/python-mpv) — Python bindings to libmpv
- **PySide6** (https://wiki.qt.io/Qt_for_Python) — Qt6 UI framework (native, touch-capable)
- **diglet48/restim's `stim_math`** (https://github.com/diglet48/restim) — vendored estim
  waveform synthesis engine, driving the live funscript-synth path

---

## Development requirements

Requires Python 3.11+ (3.12 / 3.13 fine) and libmpv.

```bash
pip install -r requirements.txt
```

### libmpv (required by python-mpv)

**Windows:** Download the latest mpv build from
[mpv.io/installation](https://mpv.io/installation/) and place
`mpv-2.dll` (or `libmpv-2.dll`) next to `main.py` or anywhere on
`PATH`.

**macOS:** `brew install mpv`

**Linux:** `sudo apt-get install libmpv-dev` (Debian / Ubuntu) or
equivalent for your distro.

---

## Running (development)

```bash
python main.py
```

Opens the control window with five tabs — **Library**, **Live**,
**Setup**, **Preferences**, **About** — the same build that ships in
the packaged releases. See [SPEC.md](./SPEC.md) for the design spec
and [BACKLOG.md](./BACKLOG.md) for the feature backlog across phases.

---

## Repository layout

- [`SPEC.md`](./SPEC.md) — alpha design specification
- [`BACKLOG.md`](./BACKLOG.md) — feature backlog across phases
- [`BETA_TODO.md`](./BETA_TODO.md) — the near-term punch list to a beta label
- `main.py` — entry point
- `app/` — UI, sync engine, stim synthesis, library scanning, chapters
- `docs/` — mkdocs user + architecture documentation
- `branding/` — logo candidates, cropped assets
- `requirements.txt` — runtime Python dependencies

---

## What's next

Not a roadmap baked into this file — it changes too often. See
[BETA_TODO.md](./BETA_TODO.md) for the live punch list toward a beta
label (code-signing, boundary-transition testing, hardware feel-tests)
and [BACKLOG.md](./BACKLOG.md) for the longer-horizon phase roadmap.

---

## Credits

Standing on the shoulders of giants. ForgePlayer.app exists because the
people below already did the hard part:

- **puste1** — **CHPlayer**: a monumental achievement, and the prior art
  this whole space lives downstream of. Synchronized video + funscript
  playback with device routing, in a single coherent player, before the
  rest of the ecosystem caught up. Years before "multi-screen with
  device sync" became table stakes, CHPlayer shipped it. Anyone building
  a player today is, knowingly or not, completing patterns puste1 set.
- **diglet48** (https://github.com/diglet48) — restim (https://github.com/diglet48/restim):
  years of estim signal processing, electrode math, and pulse algorithms.
  An extraordinary body of work — ForgePlayer's live-synth path is built
  on a vendored copy of its `stim_math` engine.
- **edger477** (https://github.com/edger477) — funscript-tools: the
  1D→2D funscript conversion pipeline and the channel taxonomy that
  modern packs are authored against.
- **mpv project** (https://mpv.io) — the media engine under everything.
- **Qt / PySide6** (https://wiki.qt.io/Qt_for_Python) — the UI framework.

---

*(c) 2026 [Liquid Releasing](https://github.com/liquid-releasing). Licensed under the MIT License.*
*ForgePlayer.app is a trademark of Liquid Releasing.*
