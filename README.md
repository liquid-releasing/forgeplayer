# eHaptic Studio Player

Synchronized multi-screen video and audio player for Windows and macOS.
Built with Python, PySide6, and libmpv.

The long-term goal is a user-friendly way to play synchronized funscripts across
multiple screens and audio outputs — a friendlier alternative to restim-style setups.

---

## Features (v0.1 prototype)

- Up to 3 synchronized video/audio slots
- Each slot assigned to a specific monitor
- Each slot routed to a specific audio output device
- Single seek bar drives all players simultaneously — sub-frame sync
- Skip controls: ±5s, ±10s, ±30s
- Dark theme

---

## Requirements

### Python packages
```
pip install -r requirements.txt
```

### libmpv (required by python-mpv)

**Windows:**
1. Download the latest mpv Windows build from https://mpv.io/installation/
2. Extract `mpv-2.dll` (or `libmpv-2.dll`) and place it:
   - Next to `main.py`, OR
   - Anywhere on your system `PATH`

**macOS:**
```bash
brew install mpv
```

---

## Running

```bash
python main.py
```

---

## Usage

1. For each slot you want active, check **Enable this slot**
2. Click **Browse…** to select a video or audio file
3. Choose which **Monitor** the player window should appear on
4. Choose which **Audio output** device to use
5. Click **Launch Players** — fullscreen windows open on the assigned monitors
6. Use **▶ Play**, **⏹ Stop**, skip buttons, or the seek bar to control all players together
7. Press **Escape** in any player window to close it
8. Click **Close Players** to tear everything down

---

## Roadmap

- [ ] Funscript sync — load `.funscript` files alongside video, drive haptic output
- [ ] Per-slot volume control
- [ ] Loop mode
- [ ] Keyboard shortcuts (Space = play/pause, Left/Right = skip)
- [ ] Session save/restore (remember last file paths and device assignments)
- [ ] Drift correction — periodic re-sync to keep players aligned over long content
- [ ] PyInstaller packaging (Windows .exe, macOS .app)

---

*© 2026 [Liquid Releasing](https://github.com/liquid-releasing). Licensed under the MIT License.*
