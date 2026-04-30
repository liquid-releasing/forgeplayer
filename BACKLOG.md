# ForgePlayer — Feature Backlog

Ideas and future features not yet scheduled for implementation.
Items are roughly grouped by phase but not strictly ordered.

---

## Phase 1 — Sync Foundation (in progress)

alpha

- [x] rename eHaptic Studio Player to ForgePlayer
- [x] rename syncplayer in this project to ForgePlayer (syncplayer project is the video wall industrial version)
- [ ] Loop mode (loop a single file or all slots)
- [ ] jump to next chapter or previous chapter, assign keyboard. arrow keys?
- [ ] Keyboard shortcuts in ControlWindow (Space = play/pause, Left/Right = skip ±5s)
- [ ] Drift correction — periodic re-sync for long content across MULTIPLE VIDEO PLAYERS (detect clock drift between mpv instances, nudge lagging players). Audio-vs-video drift on the stim stream is solved by `_TimeSmoother` in v002; this item is the separate multi-player problem.
- [x] Show "no mpv.dll found" friendly error dialog on Windows startup — obsolete for shipped users since PyInstaller now bundles libmpv-2.dll. Dev-from-source still gets a raw OSError.
- [ ] Per-player window title bar showing filename
- [ ] Remember control window size/position between sessions
- [ ] play representative sample for user to calibrate hardware settings without starting video or audio
- [ ] mkdocs User docs
- [ ] **Reorder + split tabs** — left-to-right: **Library** → **Live** → **Settings** (audio + video devices) → **Preferences** (pulse vs continuous, plus other behavior toggles to come). Splits the current Setup tab into a hardware-routing tab (Settings) and a behavior tab (Preferences). Natural place to also resolve the v0.0.3 "Apply Setup algorithm change without restart" item — Preferences-tab toggles should take effect mid-session.
- [ ] **Add third monitor** — light up the third output already in the v0.0.1 spec ("same video, full-screen, across up to three output monitors"). Today's build supports up to two; extend slot/window plumbing + Settings device-routing to expose monitor 3, with the same frame-perfect single-decoder / N-render-surfaces sync as monitors 1–2.

---

## Phase 1.1 - UI controller

alpha

- [ ] Review spec, discuss, make changes
- [ ] Revise architecture as needed
- [ ] Incorporate controller for app (no keyboard)
- [ ] support device selection
- [ ] support full screen video with multiple files fitting into the right window
- [ ] provide user options on how to display in ultrawide: crop to fit (high medium low), two instances side by side, or Pillarboxes
- [ ] Supports script bookmarks and chapters
- [ ] tapping or clicking in video space shows time since begin and time to end

---

## Phase 2 — Funscript Playback

- [x] Load a `.funscript` file alongside each video slot
- [x] Parse funscript actions and fire them in sync with video position
- [x] Seek sync carries funscript position too — scrub video, haptic follows
- [x] Route haptic signals to the correct USB audio port per slot (audio-as-haptic transport)
- [x] Funscripts authored and refined in **FunscriptForge**, played here
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

### Source fan-out + pluggable sources
Builds on the v0.0.3 audio-routing architecture (see [docs/architecture/audio-routing.md](docs/architecture/audio-routing.md)). A source instance can drive multiple destinations; new source kinds slot in by implementing `sample_rate` + `generate_block_with_clocks` and registering a detection branch.

- [ ] **MP4 audio fan-out** — same scene-audio source on more than one destination. Real motivation: user has a headset + a body-shaker array, wants the video sound on both simultaneously. Implementation: `MPVAudioTapSource` (or a dual-decode path) → multiple `StimAudioStream` instances. Probably feeds via mpv's `lavfi` filter chain or a duplicate audio decode.
- [ ] **`.tact` file source** — bHaptics-format vest file decoded into PCM. `BHapticsTactSource` class implementing the audio-source protocol; detection by sibling-file naming convention.
- [ ] **TCode-driven mechanical source** — render TCode v0.2/v0.3 commands as the audio waveform that audio-driven mechanical actuators expect. Rare hardware; ship after we know there's demand.
- [ ] **Beat-driven shaker source** — forgegen-side: audio track → beat tracker → shaker `.funscript`. ForgePlayer-side: just consume the funscript as another channel. The "source" classes already exist; only the channel naming/routing convention is new.
- [ ] **Live-capture source** — WASAPI loopback / BlackHole capture → real-time haptic generation (also covered in Phase 5; consolidate when implementing).
- [ ] **Pluggable source registry** — formalize the audio-source protocol as a `typing.Protocol` and add a registry so detection / dispatch isn't hard-coded in `_maybe_launch_haptic2_aux`-style methods. Defer until 4+ source classes exist; current branching is fine for 2.

---

## Phase 2a - Mechanical

v2

- [ ] Ability to generate additional motion or fill script gaps using random, script, pattern or custom curve motion providers
- [ ] support for vibe devices

## Phase 4 — Polish

v1 feature

- [x] PyInstaller packaging (Windows .exe, macOS .app)
- [ ] Multi-funscript layering (primary + accent track per slot)
- [ ] Auto-update check (point to funscriptforge-releases or dedicated release feed)
- [ ] In-app mpv.dll download helper for Windows users
- [ ] Theming / custom accent color
- [ ] Script heatmap of main funscript with range and heat visualization
- [ ] Support event.yml integration
- [ ] **forgegen handoff** — when loading a funscript that has a sibling `<stem>.analysis.json` (forgegen v0.1+ sidecar), surface its `structural.chapter_proposals` as quick-jump chapter markers; later, visualize the source-energy track alongside the heatmap. Symmetric to the FunscriptForge auto-load pattern.

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

## v0.0.3 — Dogfood Polish

- [ ] **White-screen-after-double-click intermittent** — reproduced ~3x in v0.0.2 dogfood; **not seen since (as of 2026-04-29)**. Library double-click → both video panes white, won't respond to Play. App restart only recovery. May have been incidentally fixed by v0.0.2-onward stim-audio / startup-timing work. Demoted from blocker to monitor — capture stderr if it recurs (`python main.py 2> mpv-err.txt`). Original suspects: mpv vs Qt window race, GL context loss from prior session, single+double-click double-fire in handler. Close after a clean v0.0.3 dogfood pass.
- [ ] **Apply Setup algorithm change without restart** — Continuous ↔ Pulse picker change is captured at player launch only. Mid-session change requires close + relaunch to take effect. Either restart the stim stream on prefs change or document the behavior in the picker subtitle.
- [ ] **Wire Haptic 2 routing** — Setup combo for Haptic 2 exists but the second stim channel isn't dispatched yet. Useful for prostate / second-stim-device users.
- [ ] **Verify no clicks when advancing across scene / chapter boundaries** — v002 audio quality work covers within-scene playback only. Auto-advance + chapter-end behavior is untested. Gate before any playlist or chapter-jump UI ships.
- [ ] **Residual ~7% audible click rate on stim playback** — likely device-level analog transient response in USB dongle when funscript modulation has steep edges during a fade window. Candidate fixes: freeze modulation across whole fade window (synth-side), or longer fade durations (loses haptic responsiveness). Only worth investigating if users report.
- [ ] **Right-click Mark with inline note** — pop a tiny text input on right-click of the ⚑ Mark button so the user can label the mark ("loud click", "horseshoe", etc.). Makes 40-mark debug sessions searchable. Skip if marks remain mostly "click happened here" without context.
- [ ] **Hardware feel-test of v0.0.2 release artifact** — pull the CI-built bundle on the RTX 4070 workstation, run with the haptic dongle plugged in, confirm the audio-saga fixes feel right end-to-end (not just sound right through a headphone).

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
