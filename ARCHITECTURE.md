# SyncPlayer.app - Architecture

## What It Is

A timeline-based playback hub. Multiple tracks routed to multiple outputs, all synced to one seek position. The user never touches a mouse once they press play.

---

## Core Architecture

```
ControlWindow (PySide6)
    |
    v
SyncEngine
    |-- mpv[0] -> Monitor A, Audio port 1 (video + main audio)
    |-- mpv[1] -> Monitor B, Audio port 2 (companion view)
    |-- mpv[2] -> Monitor C, Audio port 3 (phone stream)
    |
    |-- RestimEngine
    |       |-- restim instance 1 -> Audio port 4 (alpha/beta/pulse_frequency)
    |       |-- restim instance 2 -> Audio port 5 (prostate pack)
    |
    |-- HapticsEngine (coming)
            |-- serial/USB device
            |-- audio-channel device (7.1 card)
```

One seek position drives all of them.

---

## The Pack Model

Everything for one scene is a named folder. SyncPlayer.app loads the folder and auto-discovers all content:

```
my-scene/
  my-scene.mp4                        <- video
  my-scene.funscript                  <- original stroke script
  my-scene.alpha.funscript            <- estim: left/right position
  my-scene.beta.funscript             <- estim: up/down position
  my-scene.pulse_frequency.funscript  <- estim: intensity
  my-scene.alpha-prostate.funscript   <- prostate channel
  my-scene.beta-prostate.funscript
  my-scene.estim.mp3                  <- pre-rendered audio (optional)
  my-scene.favorites.json             <- timestamp markers
```

Discovery rules:
- Video: any .mp4/.mkv/.webm file matching the folder name
- Funscripts: <name>.<suffix>.funscript - suffix determines routing
- Estim audio: <name>.estim.mp3 - overrides live restim if present
- Favorites: <name>.favorites.json - loaded on open, written on mark

---

## Timestamp System

Timestamps are a first-class data structure, not a bookmark system.

```json
{
  "version": 1,
  "source": "my-scene.mp4",
  "favorites": [
    { "id": "uuid", "label": "peak", "start": 183.0, "end": 210.5, "created": "2026-03-14T..." }
  ],
  "playlists": [
    { "name": "best moments", "items": [{"scene": "my-scene", "favorite_id": "uuid"}] }
  ]
}
```

Marked during playback with one tap. Shared with the pack. Fed back to FunScriptForge as phrase suggestions.

---

## Estim Integration

SyncPlayer.app embeds two restim processes. Each reads a subset of the pack's funscripts and routes audio to a user-selected port.

restim is not modified - it runs as a subprocess with a pre-written restim.ini that sets:
- additional_search_paths: the pack folder
- The audio output device

This means every restim update (new movement patterns, new algorithms) is available automatically.

For offline/portable use, estim audio can be pre-rendered to MP3 at export time using restim's bake-audio pipeline. The pre-rendered file takes precedence over live restim if present.

### Credits: restim

restim (https://github.com/diglet48/restim) by diglet48 is the estim audio engine.
It implements:
- Three-phase electrode math (alpha/beta -> L/R audio via squeeze matrix)
- 17 built-in movement patterns (Circle, Figure-8, Spirograph, Lightning Strike, etc.)
- Pulse-based and continuous waveform modes
- Dual vibration oscillators with beat frequency and organic randomness
- A/B test mode (two-state cycling effect)
- Map-to-edge transform (1D position -> arc on electrode ring)
- Carrier frequency control (500-1000 Hz default, tunable)
- Full sensor integration (IMU, magnetic encoder, pressure/EOM)
- FOCStim and NeoStim hardware support

This is years of signal processing research. SyncPlayer.app makes it accessible without requiring users to understand the interface.

---

## Phone Remote Architecture

The phone is both a display and a controller.

```
Desktop (SyncPlayer.app)
    |
    |-- WebSocket server (LAN)
    |
    v
Phone (SyncPlayer mobile)
    |-- Receives: position, duration, state
    |-- Sends: seek, play/pause, skip, mark_favorite, loop_favorite
    |-- Displays: companion video stream (HLS or direct mpv stream)
```

No cloud required. Same LAN. The phone discovers the desktop via mDNS.

---

## Multi-Screen Architecture

Each mpv instance is assigned a native window handle (HWND on Windows, NSView on macOS) and rendered fullscreen on the assigned monitor. The Qt widget is borderless and invisible - mpv owns the pixels.

Per-output AI upscaling: mpv supports --vf=vapoursynth and --vf=lavfi with upscaling filters. Each instance can apply a different filter chain appropriate for its display resolution.

---

## Sync Strategy

- Single seek bar -> seek_all() applied to every mpv instance in sequence
- Transport commands are blocking calls, applied to all instances before returning
- Poll timer (100ms) reads position from primary player (slot 0), updates seek bar
- Drift correction (coming): if secondary players drift > 100ms from primary, nudge them

---

## Haptics Architecture (coming)

Two routing modes:

**Serial/USB**: funscript actions -> T-Code commands -> serial port at 115200 baud. Real-time translation, one command per action.

**Audio-channel (7.1 card)**: funscript intensity -> sine pulses (100-300 Hz) -> audio channel. Multiple devices via multiple cards (up to 8 channels per card). Same audio routing infrastructure as estim.

---

## The Pipeline

```
FunScriptForge Explorer    analyze video, detect phrases, originate funscripts
        |
        v
FunScriptForge             edit phrases, apply transforms, shape motion
        |
        v
funscript-tools            apply ReTransform (estim character), generate output pack
        |
        v
SyncPlayer.app             play everything, sync everything, mark favorites
        |
        v
favorites.json             feed phrase suggestions back to FunScriptForge
```

The funscript is the connective tissue. Every tool reads and writes it.

---

## Technology Credits

- **mpv** (https://mpv.io) - media engine. GPL licensed.
- **python-mpv** (https://github.com/jaseg/python-mpv) - Python/mpv bindings. LGPL.
- **PySide6** (https://wiki.qt.io/Qt_for_Python) - Qt6 Python bindings. LGPL.
- **diglet48/restim** (https://github.com/diglet48/restim) - estim engine. MIT.
- **edger477/funscript-tools** (https://github.com/edger477/funscript-tools) - funscript pipeline. MIT.
