# ForgePlayer.app

**Synchronized multi-screen playback with device routing.**

One seek bar. Every screen. Every device. All in sync.

Play a video on your 4K monitor, companion view on your phone, estim audio to your device, haptics to whatever you have — all from the same timeline. Mark a favorite moment with one tap. Loop it. Share it. No mouse required once you're watching.

---

## Status

**v0.0.4 — preparing alpha (2026-05-03).** Current development branch:
`feat/live-redesign`. Working: synchronized multi-screen video, dual-port
stim with frame-perfect mirror or per-port prostate routing, content
preference (sound files vs live funscript synth), seek-aware pop
mitigation, scene library with pinned variant picks, debug instrumentation
streamed to JSONL. Most recent dogfood (2026-05-03) confirmed the synth
audio path is provably clean; remaining noise sources traced to Windows
shared-mode mixer contention, addressed via WASAPI exclusive mode for
stim streams. See [SPEC.md](./SPEC.md) for the full v0.0.1-alpha design,
[docs/getting-started.md](./docs/getting-started.md) for first-time
setup, and [docs/user-guide.md](./docs/user-guide.md) for the full
feature reference.

---

## The Problem It Solves

VLC plays video. restim plays estim. Your haptic device has its own app. None of them talk to each other. Syncing them is a manual nightmare and full-screen doesn't survive it.

ForgePlayer.app is the hub. It plays everything. It routes everything. It stays in sync when you seek, skip, or loop.

---

## What It Does

```
Video           → any monitor, AI upscaled to match display resolution
Estim audio     → dedicated audio port (restim embedded, two instances)
Haptics         → serial / USB / audio-channel routing
Phone           → companion view + touch remote (seek, skip, favorite, loop)
```

All driven by the same pack. All synced to the same timestamp.

---

## The Pack

Everything for one scene lives in one folder:

```
my-scene/
  my-scene.mp4
  my-scene.funscript
  my-scene.alpha.funscript
  my-scene.beta.funscript
  my-scene.pulse_frequency.funscript
  my-scene.alpha-prostate.funscript
  my-scene.beta-prostate.funscript
  my-scene.estim.mp3                  <- pre-rendered estim audio (optional)
  my-scene.favorites.json             <- your marked moments
  my-scene.forgeplayer.json           <- per-video preset (crop, routing overrides)
```

Drop the folder. Everything loads. Press play.

---

## Timestamps — A First-Class Feature

While playing, tap once to mark a favorite. Start and end. No stopping. No menus.

```json
{
  "favorites": [
    { "label": "opening", "start": 42.1, "end": 67.4 },
    { "label": "peak",    "start": 183.0, "end": 210.5 }
  ]
}
```

- **Loop a favorite** — tap it. All devices loop that section.
- **Build a playlist** — chain favorites across multiple scenes.
- **Share timestamps** — `.favorites.json` travels with the pack.
- **Feed back to Forge** — favorites become phrase suggestions in FunscriptForge.

---

## Multi-Screen Setup

Each output is optimized for its display:

```
4K monitor      - main view, upscaled
Ultrawide       - panoramic / immersive (auto-crop from 4K source)
Phone           - 1080p companion + touch remote
Touchscreen     - 1920×720 wired operator console (alpha)
VR headset      - stereoscopic 3D (ForgePlayer VR — separate future product)
```

---

## Estim Routing

Two restim instances. Same timeline. Different audio ports.

- **Instance 1**: alpha / beta / pulse_frequency pack → audio port A
- **Instance 2**: prostate pack → audio port B

User maps which pack goes to which port. restim handles the audio generation including 17 built-in movement patterns, dual vibration oscillators, A/B test mode, map-to-edge transform, and much more.

Powered by diglet48/restim: https://github.com/diglet48/restim

Alpha ships wired USB dongles + OS default for audio; full restim integration lands in Phase 2.

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
- **diglet48/restim** (https://github.com/diglet48/restim) — estim audio generation engine (Phase 2 integration)

---

## Development requirements

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

The v0.1 prototype UI (three slots, per-monitor assignment) launches.
The v0.0.1-alpha rewrite will land incrementally on feature branches —
see [BACKLOG.md](./BACKLOG.md) and [SPEC.md](./SPEC.md) for the plan.

---

## Repository layout

- [`SPEC.md`](./SPEC.md) — v0.0.1-alpha design specification
- [`BACKLOG.md`](./BACKLOG.md) — feature backlog across phases
- `main.py` — entry point
- `app/` — UI, sync engine, session management (v0.1 prototype)
- `branding/` — logo candidates, cropped assets
- `requirements.txt` — runtime Python dependencies

---

## Current State (v0.0.4 — preparing alpha)

Working today:
- **Library** — scene browser with thumbnail tiles, pinned variant picks
  (per-scene radio-button picker for funscript set, video variant, stim
  audio file, subtitles), single-click to activate.
- **Synchronized multi-screen playback** — primary video + up to two
  mirror outputs on separate monitors via three independent libmpv
  instances. Unified seek bar drives all in sub-frame sync.
- **Dual-port stim with frame-perfect mirror** — Haptic 1 (main stim
  port) + Haptic 2 (prostate port) on independent USB DACs, both
  driven from the same media clock. H2 plays a prostate-specific
  source (`.prostate.wav` or `alpha-prostate` funscript) when present,
  else mirrors H1.
- **Content preference** — Setup → "Sound files" or "Funscripts"
  routes the H1 dispatch and the H2 prostate detection. Stim mp3
  files (`<stem>[edit].mp3`) play through mpv on the H1 device when
  sound is preferred; funscripts drive a vendored restim threephase
  synth otherwise. See
  [`docs/architecture/audio-routing.md`](./docs/architecture/audio-routing.md).
- **Seek-aware pop mitigation** — pre-seek 500 ms ramp-down → mpv seek
  → 200 ms settle hold → 500 ms ramp-up. Smoother frozen on stop to
  prevent close-pop. Multi-block envelope ramp tracking.
- **WASAPI exclusive mode** for stim streams — bypasses Windows
  shared-mode mixer; falls back to shared mode if exclusive open
  fails.
- **Calibrate H1 / H2** — pre-flight hardware check with optional 5 s
  ramp-up.
- **Transport** — play/pause, ±5 s / ±10 s / ±30 s skip, scrubbable
  timeline with time / duration labels above.
- **Scene volume slider** — per-session volume for the scene audio
  track (separate from stim).
- **Debug instrumentation** — toggle in top bar streams every event
  to `~/.forgeplayer/debug-stream-<timestamp>.jsonl`. ⚑ Mark button
  records a timestamped flag for "I heard / felt / saw something
  weird here" during dogfood.
- **Session save/restore** scaffolding.

Coming next:
- About page in-app
- Library setup-summary strip + arrow-key navigation
- Prev/Next chapter transport buttons
- Empty-state hint on Live tab
- Single-decoder / multi-render-surface for true same-video walls
  (currently three independent decoders synced via mpv time-pos)
- Phone companion view + touch remote
- Timestamps / favorites
- bhaptics `.tact` integration

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
  years of estim signal processing, electrode math, pulse algorithms,
  17 movement patterns, sensor integration. An extraordinary body of
  work and the math layer ForgePlayer renders through.
- **edger477** (https://github.com/edger477) — funscript-tools: the
  1D→2D funscript conversion pipeline and the channel taxonomy that
  modern packs are authored against.
- **mpv project** (https://mpv.io) — the media engine under everything.
- **Qt / PySide6** (https://wiki.qt.io/Qt_for_Python) — the UI framework.

---

*(c) 2026 [Liquid Releasing](https://github.com/liquid-releasing). Licensed under the MIT License.*
*ForgePlayer.app is a trademark of Liquid Releasing.*
