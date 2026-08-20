# ForgePlayer — Specification

**Last updated:** 2026-08-20
**Status:** Shipping alpha, v0.0.15 (see `app/version.py`) — pre-beta. `BETA_TODO.md` tracks the remaining gate list.
**Supersedes:** the 2026-04-22 "v0.0.1-alpha" pre-implementation draft of this file.

> **Revision note:** this file previously described a pre-implementation
> design — 3-tab UI, single-decoder/multi-render-context video wall,
> scene playlists, an independent-slots toggle — dated before any of it was
> built. None of that shipped in that shape. This rewrite describes the
> **current, real behavior** of v0.0.15, cross-checked against
> `app/control_window.py`, `app/sync_engine.py`, `app/preferences.py`, and
> the other modules it names. Where the original design was cut or never
> attempted, it's called out explicitly under §14 rather than left looking
> like current behavior. For deep architectural rationale (why the crash
> fixes exist, the real thread model, the in-process e-stim path), see
> `ARCHITECTURE.md` — this file describes *what the app does*, not *why the
> code is shaped the way it is*.

---

## 1. Overview

ForgePlayer is a synchronized multi-monitor video player with an
operator-console UX, built for e-stim/haptic playback: it plays a video on
up to three monitors while synthesizing e-stim audio from the scene's
funscripts in real time (in-process — see `ARCHITECTURE.md`), routed to up
to two dedicated haptic audio devices. A `ControlWindow` operator console
(five tabs — Library, Live, Setup, Preferences, About) drives library
browsing, transport, and hardware wiring.

Upstream siblings in the Liquid Releasing family:

- **FunscriptForge** — edits and polishes funscript files
- **ForgeAssembler** — concatenates many FunscriptForge clips into one long combined output
- **ForgePlayer** — plays a scene (or a combined output) to one-to-three monitors with haptic routing

### Why it exists

VLC/WMP-style "multiple player windows manually synced" doesn't really
sync — a seek to an arbitrary point forces a manual resync across windows,
there's no shared device-role model for USB stim dongles, and there's no
library that understands a FunscriptForge/ForgeAssembler scene folder. Once
launched, four fixed slots (video / stim / mirror / mirror — see
`ARCHITECTURE.md`'s Class Structure section) are kept in lockstep by fanning
the same transport command out to every active mpv instance
(`SyncEngine.seek_all`/`play_all`/`pause_all`, with `hr_seek=yes` so a seek
lands on the exact target frame rather than the nearest keyframe), while the
Setup tab's device-role model means USB dongles only need to be picked once,
not per scene.

### Current one-line summary

**One video on one-to-three monitors, in-lockstep sync via fanned-out
transport commands, in-process e-stim synthesis to one or two haptic audio
devices, folder-scanning library with auto-remembered picks per scene.**
Serial/USB haptic devices, `.tact` (bHaptics) integration, live audio→haptic
capture, and network/LAN multi-machine sync are not built — see §14.

---

## 2. Hardware assumptions

### Display setup

- Up to **three playback monitors**, mixed resolutions supported (the
  fixed slot model is video / stim / mirror / mirror — see
  `ARCHITECTURE.md`; a "mirror" slot needs a playback screen assigned to it
  in Setup to actually show anything).
- Optionally, a separate touchscreen for the control console (Setup's
  "Control panel screen" combo assigns it explicitly, or leaves it on
  `— auto —`). Not a hardware requirement — most dogfooding runs the
  control window on the same screen as a mouse/trackpad.

### Audio setup

- **Scene Audio** — the video's own embedded track, routed to one primary
  device and, optionally, one secondary "(also)" device that mirrors it
  (`Preferences.scene_audio_device` / `scene_audio_secondary_device`).
- **Haptic 1** and **Haptic 2** — up to two dedicated e-stim/haptic audio
  devices (typically USB dongles), configured once in Setup
  (`Preferences.haptic1_audio_device` / `haptic2_audio_device`).
- HDMI/DisplayPort "display audio" phantom devices (a monitor's built-in
  audio driver, usually speakerless) are filtered out of every device
  picker automatically (`SyncEngine._is_display_audio`).

### Shipping criteria (still the bar)

A user can: load a scene from the Library, play it fullscreen (or windowed)
on their monitor(s), hear scene audio on their chosen device, hear e-stim on
their dongle without touching a config file, scrub the seek bar smoothly,
and jump chapters — noticeably better than a VLC/WMP-wrapped workflow. This
bar has been cleared and the app is in dogfooding toward a beta label (see
`BETA_TODO.md`); nothing in this document is aspirational unless explicitly
marked "not yet built" in §14.

---

## 3. Architecture

### Stack

- **Python 3.11+**
- **PySide6** (Qt 6) for UI, windowing, multi-monitor management
- **python-mpv** (`libmpv`) for video decode + audio output — one `mpv.MPV()`
  instance per active slot, not a single shared decoder
- **PyInstaller** for platform bundles (Windows shipping today; macOS/Linux
  bundling is in the CI matrix — see §16)
- **sounddevice** + the vendored `restim_stim_math` library for in-process
  e-stim synthesis (no subprocess — see `ARCHITECTURE.md`)

### Decode & sync model — independent per-slot mpv instances, kept in lockstep

The current architecture is **not** the single-decoder/multiple-render-context
design this file originally specified (which was never built — no
`QOpenGLWidget`, no `MpvRenderContext`, no shared `mpv_handle` anywhere in the
codebase). What actually ships is closer to the *simpler* model:

- `SyncEngine` owns up to `MAX_SLOTS = 4` independent `mpv.MPV()` instances
  (one per fixed slot: video / stim / mirror / mirror), each embedded into
  its own `PlayerWindow`'s native window handle.
- Transport is fan-out, not shared-clock: `play_all()` / `pause_all()` /
  `seek_all()` apply the same command to every instance in `_active` in one
  tight loop.
- The seek-desync problem the original design worried about is solved
  differently: every `init_player()` instance sets `hr_seek="yes"`, so a
  seek decodes forward from the keyframe and lands on the exact requested
  frame instead of mpv's default nearest-prior-keyframe behavior (which was
  landing 2-12 seconds short on HandBrake-encoded sources). `seek_all` also
  briefly mutes/unmutes every instance around the seek to avoid an audible
  click from the sample discontinuity.
- Two additional **headless, audio-only** mpv instances exist outside the
  4-slot grid: a Scene Audio mirror (second device gets the same video
  sound) and a Stim Audio mirror (Haptic 2 plays H1's sound file when no
  prostate-specific source exists). Both are included in `_active`, so they
  stay locked to the same transport commands.

Per-monitor crop is handled per mpv instance via `panscan` (crop-fill) and
`video-align-y` (crop anchor) — not a GL fragment shader over a shared
render context. See §12.

### mpv configuration — what's actually set (not a baked `mpv-defaults.conf`)

There is no `mpv-defaults.conf` file and no user-override conf file today —
options are set directly as `mpv.MPV()` kwargs in `SyncEngine.init_player`
(`app/sync_engine.py`). Current defaults, and why:

| Setting | Value | Purpose |
|---|---|---|
| `vo` | `gpu` | **Not** `gpu-next` — `gpu-next`'s (libplacebo) D3D11 teardown reliably access-violated on an embedded (`wid`) player. `gpu`'s teardown is stable. See `ARCHITECTURE.md`'s crash-fix section. |
| `hwdec` | `auto-safe` | Hardware decode (NVDEC/D3D11VA/etc.), falls back to software only for codecs it can't offload — never makes a decodable file undecodable. Needed because software-decoding a high-bitrate 4K source pegs the CPU badly enough to stall both the poll loop and the haptic sync engine. |
| `hr_seek` | `yes` | Frame-accurate seeking — see above. Costs 100-500 ms per seek on 1080p; imperceptible in normal use. |
| `tone_mapping` | `bt.2390` | Perceptual HDR→SDR tone-map on `gpu` (not true HDR passthrough — that was `gpu-next`'s job and got reverted with it). |
| `hdr_compute_peak` | `yes` | Paired with `tone_mapping`. |
| `target-colorspace-hint` | `yes` (best-effort, set post-construction) | Hints the display colorspace so a Windows-HDR-ON desktop composites correctly instead of blowing out to white. |
| `demuxer_max_bytes` / `demuxer_max_back_bytes` | `256MiB` / `64MiB` | Read-ahead buffer so a big 4K file doesn't stall the decode thread on disk I/O. |
| `panscan` / `video_align_y` | set per-slot when "Crop" is on for that monitor | Crop-fill instead of letterbox; see §12. |
| `gpu_context` / `d3d11_adapter` | `d3d11` / `NVIDIA`, only when a hybrid-GPU Windows machine is detected | Routes mpv's D3D11 context off a buggy AMD adapter. See `ARCHITECTURE.md`. |

Not present, and not planned near-term: `scale=ewa_lanczossharp`,
`cscale`/`dscale` upscaler tuning, `video-sync=display-resample`,
`interpolation=yes`, `deband=yes`, or a general user-override conf file.
`docs/quality.md` still documents some of this aspirational upscaling story
and should be reconciled in a separate pass — it wasn't in scope for this
rewrite.

### Robust per-monitor window placement

Each `PlayerWindow` is a borderless `QWidget` placed via
`place_on_screen(screen, fullscreen)` — `setGeometry()` to a windowed rect
first (always, even when "Fullscreen players" is checked — see
`ARCHITECTURE.md`'s reuse/launch-sequencing notes for why), then
`showFullScreen()` if requested, deferred a beat so mpv's viewport
recomputes against the already-embedded surface instead of the pre-fullscreen
rect. Placement is by explicit Setup checkbox assignment (`playback_screen_indices`),
not drag-to-monitor. `player.placement_target` / `player.placement_actual`
debug-log events bracket the placement call so a target/actual mismatch
(Qt/DWM snapping a window back to the primary monitor) is diagnosable from
the debug log rather than guesswork.

---

## 4. UI — tab model

Five tabs in a `QTabWidget`, in this order (`ControlWindow._build_ui`):

**Library → Live → Setup → Preferences → About**

The order follows the user's actual journey: pick a scene, drive playback,
wire hardware once, tune rare behavior, check version/credits. The app
opens on **Library** by default (not Live) — a returning user with a
scanned root lands on their scenes; a first-run user sees Library's
"Scan a folder" empty state.

There is no cross-tab swipe gesture and no chevron-driven within-panel
navigation model — tab switching is a plain `QTabWidget` click. (The
original design's touchscreen-console gesture model — edge chevrons,
swipe-to-page — was never implemented; see §14.)

---

## 5. UI — Live tab

`ControlWindow._build_live_tab`. Layout, top to bottom:

1. **Now-playing header** — the active scene's name, plus the origin
   `<stem>.forge` bundle name in brand orange when the scene came from a
   FunscriptForge export (`_refresh_now_playing`).
2. **Video panel** (left) / **Output panel** (right), side by side, each
   read-only except for one picker at the top:
   - **Video panel** — a "Video source" combo + Browse button (re-routes the
     live scene, one video across all assigned monitors), the resolved
     filename, the list of monitors video will play on (read from Setup's
     `playback_screen_indices`, with crop/letterbox noted per monitor), and
     the **Fullscreen players** toggle (applies live to any open
     `PlayerWindow`, not just at next launch — `_on_fullscreen_toggled`).
     Scene Audio's primary and optional secondary device + source line live
     here too (the video's own embedded audio, not haptics).
   - **Output panel** — a "Stim source" combo + Browse button (funscript set,
     audio file, or None for silent stim), then one block per haptic
     destination: **Haptic 1** (the full e-stim channel set — restim
     channel names or filenames, scrollable if long) and **Haptic 2** (the
     prostate side-chain, or a note that it mirrors Haptic 1 when no
     prostate-specific source exists for the active `content_preference`).
3. **Timeline row** — position/duration labels, a 42px-tall click-to-seek
   slider with chapter/marker ticks, and a separate Scene-volume slider
   (ephemeral, per-session, affects only the primary video's mpv volume —
   not the haptic stream).
4. **Transport row** — Prev-chapter, −30/−10/−5s, Play/Pause, Stop,
   +5/+10/+30s, Next-chapter. Play is disabled until Launch has run.
   Prev/Next-chapter are disabled until a `<stem>.chapters.json` sidecar (or
   embedded chapter metadata) resolves for the active scene.
5. **Calibrate row** — "Calibrate H1" / "Calibrate H2" tap-toggle buttons
   loop the scene's peak-intensity haptic window through the matching
   device before Play, with an optional 5-second fade-in ramp
   (`_chk_calibrate_ramp`, on by default). Locked from first Play until
   Close — once launched streams own the device handle exclusively.
6. **Launch Players / Close Players** — Launch builds (or **reuses** — see
   `ARCHITECTURE.md`) a `PlayerWindow`+mpv instance per slot with media and
   dispatches the stim slot to `StimSynth`; Close tears every active player
   down.

There is no per-monitor crop-preset chip row on Live — crop is a Setup-tab,
per-monitor concern (§12), not a Live-tab live control.

---

## 6. UI — Setup tab

Two columns side by side (`ControlWindow._build_setup_tab`), inside a
vertical scroll area so a short window scrolls rather than overlapping text:

### Audio device roles

Four fixed role rows, each a device combo + a "Test" affordance:

| Role | Preferences field | Purpose |
|---|---|---|
| Scene audio | `scene_audio_device` | Video's embedded sound |
| Scene audio (also) | `scene_audio_secondary_device` | Optional second device that mirrors scene audio — e.g. driving a stim device from music when no funscript exists |
| Haptic 1 (main stim) | `haptic1_audio_device` | Primary e-stim output |
| Haptic 2 (alt stim) | `haptic2_audio_device` | Optional second stim output — prostate side-chain, or mirrors Haptic 1 |

A device already assigned to one role is greyed out of the others
(`_apply_device_exclusions`) so the same exclusive audio handle can't be
double-claimed. A picked device applies live to the currently loaded scene
immediately (`_reload_current_scene`), not only on the next Library click. A
"Refresh devices" button re-queries the OS device list for USB dongles
plugged in after launch.

This is a **fixed 4-role model**, not the flexible arbitrary
source→destination table the original design sketched (add/remove
source/output pairs, per-source friendly labels). Four roles cover the
real hardware shapes seen in dogfooding; see `docs/architecture/audio-routing.md`
for how a fifth role (e.g. a shaker) would slot in.

### Monitor roles

- **Control panel screen** — which monitor hosts `ControlWindow` itself
  (`— auto —` or an explicit screen).
- **Playback screens** — one checkbox per detected screen
  (`playback_screen_indices`); leaving all unchecked means "any screen is
  fair game." Each row also has a **Crop** checkbox (`fill_screen_indices`)
  — crop-fill (mpv `panscan`) vs. the default letterbox/pillarbox.
- **Crop position** — one global 3-way radio (Top / Center / Bottom,
  `CropAlign`), applied only to screens with Crop on. Top/Bottom back the
  kept region off the near edge by ~1/8 rather than slicing a subject at
  the very edge.

---

## 7. UI — Preferences tab

Two columns (`ControlWindow._build_preferences_tab`):

- **Audio synthesis** — the algorithm picker (`AudioAlgorithm`: continuous
  vs. pulse-based, default **pulse** — ForgePlayer's content pipeline
  targets modern stereostim hardware) and the haptic latency offset
  (`haptic_offset_ms`, ±500ms, compensates dongle/driver/electrode-placement
  latency).
- **Content preference** — the sound-vs-funscript tie-breaker
  (`ContentPreference`, default **funscript**) used when a scene ships both
  a pre-rendered `.wav`/`.mp3` and a funscript for the same haptic
  destination. Applies only when both forms exist for a given destination —
  if only one exists, that one plays regardless of preference.

Both settings are captured **at Launch** — changing them while players are
already running does not re-route the live scene (unlike the Setup-tab
device/monitor pickers). See §14.

---

## 8. UI — Library tab

`LibraryPanel` (`app/library_panel.py`): a root-folder picker, a search box,
three filter chips (**All** / **Videos with Funscripts** — the default
view / **Videos**), and a virtualized `QListView` grid of scene cards
(`LibraryCardDelegate`). The scan runs off the GUI thread (§ Architecture
above); Scan/Rescan buttons disable while a scan is in flight.

Each card shows: a lazily-grabbed video-frame thumbnail, the scene name,
duration, device-generation badges (mechanical/2B/stereostim/FOC-stim,
`GENERATION_BADGES`) plus a `p•` badge when a prostate side-chain is
present, content-type pills (VIDEO/AUDIO/FUNSCRIPT/FORGE), a corner
"reveal in Explorer" button, and — when a saved pin exists for that scene —
a 📌 button that reopens the picker to change picks (a plain tile tap
replays the pin).

**Single-click activates.** Tapping a card either replays the scene's saved
pin (video/audio/funscript-set/subtitle choice remembered from the last
successful play, `app/library/pins.py`) or opens `SelectPicker` when the
scene is ambiguous or the pin has gone stale (a referenced file no longer
exists).

There is no multi-select, no "Add to playlist," and no separate Playlists
filter chip — see §14.

---

## 9. UI — About tab

Version string (`app/version.py`), upstream credits (mpv, python-mpv,
PySide6, restim, funscript-tools — matching `ARCHITECTURE.md`'s credits
section), and a manual "Check for updates" button. The update check itself
(`app/update_check.py`) hits `https://forgeplayer.app/latest-version.json`;
see `ARCHITECTURE.md`'s update-check-flow section for the full mechanism.
A manual check always reports live status inline and never pops the
"Update available" dialog — that dialog is reserved for the automatic
startup check, and even then at most once per version
(`Preferences.dismissed_update_tag`).

---

## 10. Config model

### Global preferences — `~/.forgeplayer/preferences.json`

The `Preferences` dataclass (`app/preferences.py`), persisted as flat JSON.
Real fields (not the nested `walls`/`routing`/`library` JSON the original
design sketched):

```json
{
  "scene_audio_device": "",
  "scene_audio_secondary_device": "",
  "haptic1_audio_device": "",
  "haptic2_audio_device": "",
  "audio_algorithm": "pulse",
  "haptic_offset_ms": 0,
  "control_panel_screen": -1,
  "playback_screen_indices": [],
  "fill_screen_indices": [],
  "crop_align": "center",
  "content_preference": "funscript",
  "library_root": "",
  "dismissed_update_tag": ""
}
```

Unknown keys are silently dropped on load (`Preferences.load` filters
against the dataclass's own field set); enum fields with stale/hand-edited
values fall back to their default rather than crashing the app at launch.
Save is best-effort — a write failure never breaks the running session.

### Per-scene state — pins, not hand-editable presets

There is no user-facing `<stem>.forgeplayer.json` preset file with crop/
routing/notes fields. What exists at that same filename is a **pin**
(`app/library/pins.py`'s `Pin` dataclass) — an auto-saved record of which
video/audio/funscript-set/subtitle the user picked for that scene folder
last time, written after every successful play and replayed automatically
on the next one (skipping `SelectPicker` entirely unless a referenced file
has since gone missing). A global index at `~/.forgeplayer/catalog.json`
maps scene folders to their pins for fast Library badge rendering. Users
never hand-edit this file; the picker (or the 📌 "change picks" button on a
Library card) is the only way to change it.

---

## 11. Folder-load conventions — the "pack" model

ForgePlayer ingests the same `{stem}.{suffix}.{ext}` pack that
**FunscriptForge**, **ForgeAssembler**, and **ForgeGen** already emit, or a
FunscriptForge `.forge`/`.forgeplay` export bundle (`app/bundle_importer.py`
— see `ARCHITECTURE.md` for the selective-extraction detail). No renaming
required either way, and a bundle's haptics always take priority over any
loose funscripts scanned in the same folder.

### Canonical pack layout

| File | Role |
|---|---|
| `{stem}.mp4` / `.mkv` / `.mov` / `.avi` / `.webm` / `.m4v` | Video (highest-resolution non-upscaled variant defaults; upscaled and aspect-remapped variants never default — see `app/library/catalog.py`'s `preference_tier`) |
| `{stem}.funscript` | Main stroke funscript (mechanical / legacy 2B intensity) |
| `{stem}.alpha.funscript` / `.beta.funscript` | Stereostim position channels |
| `{stem}.pulse_frequency.funscript` / `.pulse_width.funscript` / `.pulse_rise_time.funscript` / `.volume.funscript` / `.frequency.funscript` | FOC-stim parameter channels |
| `{stem}.alpha-prostate.funscript` / `.beta-prostate.funscript` / `.volume-prostate.funscript` | Prostate side-chain (Haptic 2) |
| `{stem}.roll.funscript` / `.pitch.funscript` / `.twist.funscript` / `.surge.funscript` / `.sway.funscript` | Multi-axis (SR6-style / VR alignment) — not consumed by e-stim synthesis |
| `{stem}.estim.mp3` / pre-rendered `.wav` | Pre-rendered stim audio; the sound-vs-funscript tie-breaker (`content_preference`) decides which plays when both exist |
| `{stem}.chapters.json` | Chapters + markers sidecar (§13) |
| `{stem}.forgeplayer.json` | Auto-saved pin (§10) — not a hand-authored preset |
| `<stem>.output/` or `<stem>.forge` / `<stem>.forgeplay` | FunscriptForge export bundle — imported via `bundle_importer`, not the raw folder scanner (see `_is_export_bundle_dir`) |

See `docs/architecture/restim-channels.md` for the authoritative, canonical
list of restim-recognized funscript filenames.

### Ambiguity and the picker

A scene is **ambiguous** — `SelectPicker` appears instead of auto-loading —
when multiple video variants share the same `preference_tier`, multiple
funscript sets exist (edit-variants), or multiple audio tracks exist with
no single stem-matched default. First play always shows the picker for an
ambiguous scene; every play after that replays the saved pin.

---

## 12. Crop / fill

There is no 5-preset (Middle / Top-mid / Top / Bottom-mid / Bottom) crop
system with per-monitor visibility gating. The real model is **per-screen
binary Crop + one global 3-way anchor**:

- Each playback screen has an independent **Crop** checkbox in Setup
  (`fill_screen_indices`) — off (default) letterboxes/pillarboxes to
  preserve the source aspect; on crop-fills via mpv `panscan=1.0`.
- **Crop position** is one global radio — Top / Center (default) / Bottom
  (`CropAlign`) — applied to every screen with Crop on. Top/Bottom offset
  the kept region by mpv `video-align-y = ∓0.75` (not a full edge flush) so
  a subject anchored high or low in frame isn't sliced at the very edge.
- Crop and crop-position changes apply live to already-open players
  (`SyncEngine.set_fill` / `set_crop_align`), not just at next launch.

---

## 13. Chapters & markers

`<video_stem>.chapters.json` (`app/chapters.py`) carries two independent
arrays:

- `chapters: [{at_ms, name}, ...]` — structural, one per section. Drives
  Prev/Next-chapter (both on the `ControlWindow` transport row and on each
  `PlayerWindow`'s overlay control bar — both routed through the same
  `_on_prev_chapter`/`_on_next_chapter` logic so they never disagree).
  "Previous" restarts the current chapter if more than 2 seconds
  (`_PREV_GRACE_MS`) into it, matching standard music-player convention.
- `markers: [{id, at_ms, name}, ...]` — hand-placed FunscriptForge
  navigation points, rendered as tick marks on the seek bar (not
  chapter-driven, no Prev/Next button).

When no sidecar exists, chapter navigation falls back to whatever chapter
metadata mpv parsed directly from the file's own container atoms
(`SyncEngine.get_chapter_list`).

---

## 14. Not yet built

Features this file (or its predecessor) described that do not exist in the
current codebase — verified absent by grep, not just "not seen in the UI":

- **Scene playlists.** No `~/.forgeplayer/playlists/<name>.json` storage,
  no multi-select in Library, no "Add to playlist" action, no auto-advance
  between scenes. Zero code hits beyond a stray planning comment in
  `_on_launch` ("the playlist case") describing the scenario the crash fix
  protects against, not a feature. Listed as deferred in `BETA_TODO.md`
  ("Research / deferred (v1+)").
- **Independent-slots toggle.** No Preferences field, no Setup UI, no code
  path for running three unrelated videos simultaneously. The shipped
  4-slot model (video / stim / mirror / mirror) always mirrors the same
  media across the mirror slots.
- **Serial/USB haptic devices** (T-Code over a serial port) and **7.1
  audio-channel haptics** (shaker arrays via individual sound-card
  channels) — both listed as deferred research in `BETA_TODO.md`. Shaker
  support (a beat-driven track as another haptic channel) is the nearest
  near-term step.
- **`.tact` (bHaptics vest) integration**, **TCode mechanical source**,
  **live-capture source** (WASAPI loopback / BlackHole → real-time
  haptics), and a general pluggable-source registry.
- **Network / LAN multi-machine sync**, and any phone/mobile client — no
  WebSocket server, no mDNS discovery, no mobile companion app anywhere in
  the codebase.
- **Loop mode**, **keyboard shortcuts beyond Space/F11/Escape** (Left/Right
  skip, chapter-key nav, Library arrow-key nav are open), **remembering
  control-window size/position**, **applying an algorithm/offset change to
  an already-launched scene without relaunching**, and a **Library
  active-picks summary strip** above the grid.
- **Timeline editor / loop regions**, **playback speed control**, **live
  audio→haptics mode**.

See `BETA_TODO.md` for the fuller, actively-maintained punch list (quality
gates, alpha-polish bugs, missing features, deferred research) — this
section only covers the items the original SPEC specifically claimed as
in-scope that turned out not to be built.

---

## 15. Status — what's shipped vs. what's gating beta

Reconciled against v0.0.15 (`BETA_TODO.md`, 2026-08-20). Already shipped
since the last time this spec was accurate: Haptic 2 dispatch, Prev/Next
chapter buttons (console + per-player overlay), seek-bar markers,
Calibrate, mkdocs docs, PyInstaller packaging, in-app auto-update check,
third-monitor support, async library/folder scanning (no more UI freeze on
a slow/attached drive), and the crash-hardening work in `_on_launch`
(player/mpv reuse across a scene switch + NVIDIA GPU routing on
hybrid-graphics laptops — see `ARCHITECTURE.md`).

Nothing currently blocks shipping v0.0.15 itself (it's published). Beta
quality gates, in priority order, per `BETA_TODO.md`:

1. Code-sign the Windows installer (currently unsigned — SmartScreen friction).
2. Verify no audible clicks across scene/chapter auto-advance boundaries.
3. Hardware feel-test the actual release artifact on real haptic dongles.
4. Confirm the "D29 audio-only ship-blocker" is resolved against the current build.
5. Residual ~7% audible click rate (device-level analog transient, hold-on-fail).
6. Intermittent white-screen-after-double-click (not reproduced recently).

---

## 16. Shipping pipeline

Mirrors the ForgeAssembler pattern; PyInstaller for the app bundle.

- **Repo:** `liquid-releasing/forgeplayer`.
- **Release artifacts:** `liquid-releasing/forgeplayer-releases`, via a
  cross-platform CI matrix (`.github/workflows/release.yml`).
- **PyInstaller spec:** `ForgePlayer.spec` — PySide6/Qt plugin collection
  hooks, `libmpv` bundled per platform (Windows `mpv-2.dll` next to the
  exe; macOS `libmpv.dylib`; Linux `libmpv.so`).
- **Landing site:** `forgeplayer.app` (`liquid-releasing/forgeplayer-web`) —
  publishes `latest-version.json` at its root, which is exactly what
  `app/update_check.py` polls; the site's own CI keeps that file in sync
  with GitHub Releases so the in-app "update available" notice can never
  claim a version the site itself doesn't.
- **Docs:** MkDocs Material under `docs/` (`mkdocs.yml`), deployed via
  `.github/workflows/docs.yml`. `docs/architecture/` is dev-facing and
  excluded from the published site; `docs/getting-started.md` and
  `docs/user-guide/` are the user-facing docs.

---

## 17. Open questions

1. **Chapter jump wrap** — at the first or last chapter, wrap around or hit
   a wall? Currently a wall (buttons stay enabled but a boundary chapter
   simply doesn't move further); no explicit design decision recorded.
2. **Preferences/pin file location on macOS/Linux** — currently
   `~/.forgeplayer/` on all platforms (no XDG Base Directory handling on
   Linux). Not yet tested on a real macOS/Linux box.
3. **Algorithm/offset hot-apply** — Setup's device/monitor pickers already
   re-route a live scene immediately; Preferences' synth algorithm and
   haptic offset don't. Worth unifying once the Setup/Preferences split
   settles further (see §14, "applying an algorithm/offset change to an
   already-launched scene without relaunching").
4. **Scene-boundary click verification** — BETA_TODO's #2 gate. The
   within-scene audio-quality work is done; multi-scene/auto-advance
   boundary behavior doesn't exist yet to test against (see §14, scene
   playlists) — this gate is really "when playlists land, verify this,"
   not an open item against today's single-scene playback.

---

*© 2026 Liquid Releasing. Licensed under the MIT License.*
