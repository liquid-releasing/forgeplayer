# ForgePlayer — Feature Backlog

Ideas and future features not yet scheduled for implementation.
Items are roughly grouped by phase but not strictly ordered.

---

## Phase 1 — Sync Foundation (in progress)

- [ ] rename eHaptic Studio Player to ForgePlayer
- [ ] rename syncplayer in this project to ForgePlayer (syncplayer project is the video wall industrial version)
- [ ] Loop mode (loop a single file or all slots)
- [ ] jump to next chapter or previous chapter, assign keyboard. arrow keys?
- [ ] Keyboard shortcuts in ControlWindow (Space = play/pause, Left/Right = skip ±5s)
- [ ] Drift correction — periodic re-sync for long content (detect clock drift, nudge lagging players)
- [ ] Show "no mpv.dll found" friendly error dialog on Windows startup
- [ ] Per-player window title bar showing filename
- [ ] Remember control window size/position between sessions
- [ ] play representative sample for user to calibrate hardware settings without starting video or audio

---

## Phase 1.1 - UI controller

- [ ] Review spec, discuss, make changes
- [ ] Revise architecture as needed
- [ ] Incroporate controller for app (no keyboard)
- [ ] support device selection
- [ ] support full screen video with multiple files fitting into the right window
- [ ] provide user options on how to display in ultrawide: crop to fit (high medium low), two instances side by side, or Pillarboxes
- [ ] Supports script bookmarks and chapters
- [ ] tapping or clicking in video space shows time since begin and time to end

---

## Phase 2 — Funscript Playback

- [ ] Load a `.funscript` file alongside each video slot
- [ ] Parse funscript actions and fire them in sync with video position
- [ ] Seek sync carries funscript position too — scrub video, haptic follows
- [ ] Route haptic signals to the correct serial/USB port per slot
- [ ] Funscripts authored and refined in **FunscriptForge**, played here
- [ ] Script libraries to allow loading scripts not located next to the video file
---

## Phase 3 — Haptic Features

v2 features

### Serial / USB devices
- [ ] Connect to haptic devices (serial/Bluetooth/USB) per slot
- [ ] Real-time funscript → device command translation
- [ ] Per-device intensity/range calibration
- [ ] Auto-detect connected haptic devices on launch

### Audio-channel haptics (7.1 sound card approach)
- [ ] Route haptic signals as audio waveforms to individual channels of a 7.1 sound card
- [ ] Multiple devices can be daisy-chained via multiple 7.1 cards (up to 8 channels per card)
- [ ] Per-channel assignment in slot config (card + channel index)
- [ ] Funscript action → audio waveform encoder (e.g. 100–300 Hz sine pulses scaled by action intensity)
- [ ] Low-latency audio output path to keep haptic sync tight with video
- [ ] UI: "Haptic output" combo per slot — choose between serial port or audio channel

---

## Phase 2a - Mechanical

v2

- [ ] Ability to generate additional motion or fill script gaps using random, script, pattern or custom curve motion providers

## Phase 4 — Polish

v1 feature

- [ ] PyInstaller packaging (Windows .exe, macOS .app)
- [ ] Multi-funscript layering (primary + accent track per slot)
- [ ] Auto-update check (point to funscriptforge-releases or dedicated release feed)
- [ ] In-app mpv.dll download helper for Windows users
- [ ] Theming / custom accent color
- [ ] Script heatmap of main funscript with range and heat visualization
- [ ] Support event.yml integration

---

## Phase 5 — Live Audio-to-Haptic Mode

v2 

- [ ] Real-time audio analysis → haptic output without a pre-authored funscript
- [ ] WASAPI loopback capture (Windows) / BlackHole (macOS) — listen to what's playing
- [ ] Beat detection + BPM lock from live audio stream
- [ ] Motion generation: map beats/energy to haptic intensity curves in real time
- [ ] Per-slot mode toggle: "Funscript" (pre-authored) vs "Live" (audio-reactive)
- [ ] Sensitivity / intensity controls for live mode

> **Reference:** [bREadbeats](https://github.com/breadfan69-2/bREadbeats) by breadfan69-2 —
> real-time music→motion generator for Restim. Source-available (non-commercial license).
> Study the approach for inspiration; cannot use code or models commercially.
> Consider reaching out to the author about collaboration.

---

## Longer Term / Exploratory

- [ ] Network sync — multiple machines play in sync over LAN
- [ ] Timeline editor — trim/loop regions within a session
- [ ] Playlist mode — queue multiple sessions and play them sequentially
- [ ] SaaS / cloud session sharing (load session from URL)
- [ ] FOC-stim support
- [ ] Mechanical support
- [ ] Stash as script repositories
- [ ] TCode v0.2 and TCode v0.3 devices with advanced customization
- [ ] Support buttplug.io, TCP, UDP, websockets, namedpipes, serial, file and The Handy (experimental) outputs
- [ ] Real time script smoothing using pchip or makima interpolation
- [ ] French, German, and Japanese editions

### Develop architecture for haptics

- The **renderer architecture** (JSON → WAV, JSON → bHaptics) 
- The **player architecture** (timeline scheduler) to go into syncplayer 
- The **device abstraction layer**  
- The **multi‑device playback loop**  to go in syncplayer
- add to the considerations, architecture, loop playback features
