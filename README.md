# ForgePlayer.app

**Synchronized multi-screen playback with device routing.**

One seek bar. Every screen. Every device. All in sync.

Play a video on your 4K monitor, companion view on your phone, estim audio to your device, haptics to whatever you have — all from the same timeline. Mark a favorite moment with one tap. Loop it. Share it. No mouse required once you're watching.

---

## The Problem It Solves

VLC plays video. restim plays estim. Your haptic device has its own app. None of them talk to each other. Syncing them is a manual nightmare and full-screen doesn't survive it.

SyncPlayer.app is the hub. It plays everything. It routes everything. It stays in sync when you seek, skip, or loop.

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
```

Drop the folder. Everything loads. Press play.

---

## Timestamps - A First-Class Feature

While playing, tap once to mark a favorite. Start and end. No stopping. No menus.

```json
{
  "favorites": [
    { "label": "opening", "start": 42.1, "end": 67.4 },
    { "label": "peak",    "start": 183.0, "end": 210.5 }
  ]
}
```

- **Loop a favorite** - tap it. All devices loop that section.
- **Build a playlist** - chain favorites across multiple scenes.
- **Share timestamps** - .favorites.json travels with the pack.
- **Feed back to Forge** - favorites become phrase suggestions in FunScriptForge.

---

## Multi-Screen Setup

Each output is optimized for its display:

```
4K monitor      - main view, upscaled
Ultrawide       - panoramic / immersive
Phone           - 1080p companion + touch remote
VR headset      - stereoscopic 3D (coming)
```

---

## Estim Routing

Two restim instances. Same timeline. Different audio ports.

- **Instance 1**: alpha / beta / pulse_frequency pack -> audio port A
- **Instance 2**: prostate pack -> audio port B

User maps which pack goes to which port. restim handles the audio generation including 17 built-in movement patterns, dual vibration oscillators, A/B test mode, map-to-edge transform, and much more.

Powered by diglet48/restim: https://github.com/diglet48/restim

---

## The Ecosystem

```
FunScriptForge Explorer  ->  FunScriptForge  ->  funscript-tools  ->  SyncPlayer.app
   originate                  edit/shape          estim character       play everything
```

Funscripts are the connective tissue. Every tool reads and writes them.

---

## Tech Stack

- **mpv** (https://mpv.io) - frame-accurate, cross-platform media engine
- **python-mpv** (https://github.com/jaseg/python-mpv) - Python bindings to libmpv
- **PySide6** (https://wiki.qt.io/Qt_for_Python) - Qt6 UI framework
- **diglet48/restim** (https://github.com/diglet48/restim) - estim audio generation engine

---

## Requirements

**Python packages:**
```bash
pip install -r requirements.txt
```

**libmpv:**

Windows - download from https://mpv.io/installation/, place mpv-2.dll next to main.py.

macOS:
```bash
brew install mpv
```

---

## Running

```bash
python main.py
```

---

## Current State (v0.1 prototype)

Working today:
- Up to 3 synchronized video/audio slots
- Per-slot monitor and audio device assignment
- Unified seek bar - sub-frame sync
- Transport controls: play, pause, stop, skip

Coming next:
- Pack loading (drop a folder, everything loads)
- restim integration (two instances, port routing)
- Phone remote
- Timestamps / favorites
- AI upscaling per output

---

## Credits

SyncPlayer.app builds on the work of:

- **diglet48** (https://github.com/diglet48) - restim (https://github.com/diglet48/restim): years of estim signal processing, electrode math, pulse algorithms, 17 movement patterns, sensor integration. An extraordinary body of work.
- **edger477** (https://github.com/edger477) - funscript-tools: the 1D->2D funscript conversion pipeline
- **mpv project** (https://mpv.io) - the media engine under everything
- **Qt / PySide6** (https://wiki.qt.io/Qt_for_Python) - the UI framework

---

(c) 2026 Liquid Releasing (https://github.com/liquid-releasing). MIT License.
SyncPlayer.app is a trademark of Liquid Releasing.
