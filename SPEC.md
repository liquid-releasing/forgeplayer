# ForgePlayer — v0.0.1-alpha Specification

**Last updated:** 2026-04-22
**Status:** Design complete, pre-implementation
**Supersedes:** existing eHaptic Studio Player v0.1 prototype

---

## 1. Overview

ForgePlayer is a synchronized multi-monitor video player with operator-console UX. It plays **the same video, full-screen, across up to three output monitors** at frame-perfect sync, with a separate **touchscreen controller** for transport, library, and routing. Built for video-wall / playback-rig setups.

Upstream siblings in the Liquid Releasing family:

- **FunscriptForge** — edits and polishes funscript files
- **ForgeAssembler** — concatenates many FunscriptForge clips into one long combined output
- **ForgePlayer** — plays the combined output to a multi-monitor video wall with haptic routing

### Why it exists

The current user workflow is "multiple VLC windows manually sync'd" — which doesn't really sync at all. Seeks to arbitrary points force a full manual resync. ForgePlayer replaces that with a single-decoder / N-render-surfaces architecture where seek is frame-perfect by construction, plus a touch-friendly operator console that handles transport, chapter navigation, audio routing, and library management from one place.

### v0.0.1-alpha scope — one-line summary

**Same video on one-to-three walls, frame-perfect sync, mouse-or-touch operator console, multi-destination audio (OS default + USB dongles), folder-auto-load with JSON presets.** Funscript-to-audio conversion, Bluetooth audio, fan-out routing, and haptic-device integration are all Phase 2+.

### Reference configurations

Two user setups shape the alpha design. Both must work well; both ship in the same binary.

| Config | Setup | Role |
|---|---|---|
| **Baseline** (realistic user) | Laptop + 1 external monitor + 1-2 USB audio dongles. Mouse/trackpad controls the operator console; external monitor plays fullscreen. | Alpha's shipping criterion: works great here on day 1 |
| **Flagship** (video-wall rig) | Desktop with high-end GPU (e.g. RTX 4070) driving 2-3 external walls, plus a Prechen 12.3" 1920×720 touchscreen as the operator console. Multiple USB audio dongles. | Scale-up demo / power-user configuration |

The same code handles both. Wall count adapts from detected displays (QScreen enumeration); controller = whichever display is explicitly marked `controller` (or is smallest/touch-capable as a fallback). The "laptop + 1 wall" user should not feel like a second-class citizen.

### v0.0.1-alpha shipping criteria

ForgePlayer ships when a **baseline-config user** can:

1. Load a FunscriptForge / ForgeAssembler pack folder
2. Play it fullscreen on their external monitor
3. Hear audio on their USB dongle
4. Scrub the seek bar smoothly, jump chapters
5. Have the result look and feel **noticeably better than their current VLC/WMP-wrapped workflow**

Everything above that bar is the flagship config. Everything below the bar blocks shipping.

---

## 2. Hardware assumptions

### Display setup

- Up to **three playback monitors** at a mix of resolutions. Typical target: two 4K (3840×2160) + one ultrawide (3840 × ~1120, or similar wide aspect).
- **One controller touchscreen** — nominally a wired secondary monitor like the Prechen 12.3" (1920×720, HDMI + USB-C, touch-enabled). Not a tablet; everything runs on one PC.
- All four displays connect to the same machine. No network sync, no remote control.

### Audio setup — alpha

- **OS default output** (whatever Windows / macOS / Linux reports as the current default)
- **Two wired USB audio dongles** for haptic routing

Scope for later phases: Bluetooth audio, multi-card 7.1 channel arrays, fan-out to multiple outputs from one source.

---

## 3. Architecture

### Stack

- **Python 3.11+**
- **PySide6** (Qt 6) for UI, windowing, gestures, multi-monitor management
- **libmpv** via `python-mpv` for video decode + audio output
- **PyInstaller** for 3-platform bundles (Windows / macOS / Linux)

No web UI, no browser, no Streamlit. The family's standard stack diverges here intentionally — native Qt is the only way to get frame-perfect multi-monitor video + per-device audio routing + touch UI in one process.

### Decode model — single source, multiple render surfaces

The v0.1 prototype uses **three independent libmpv instances** (one per monitor) with transport commands fanning out in a tight loop. That architecture is the root cause of the seek-desync problem: each instance seeks independently and lands on a slightly different frame.

v0.0.1-alpha architecture:

```
             ┌──────────────────────────┐
             │   single libmpv decoder  │
             │   (master clock, audio)  │
             └──────────────────────────┘
                        │
          ┌─────────────┼─────────────┬─────────────┐
          ▼             ▼             ▼             ▼
     render ctx 1  render ctx 2  render ctx 3   audio mixer
     Wall 1 (4K)   Wall 2 (4K)   Wall 3 (UW)      │
                                  + crop filter   │
                                                  ├─ OS default
                                                  ├─ Dongle 1
                                                  └─ Dongle 2
```

One decoder owns the timeline. Three render contexts pull frames from it — frame-perfect sync by construction because there's only one clock. Audio goes through a mixer that splits into the configured destinations.

libmpv's render API (`mpv_render_context`) supports multiple render contexts against a single `mpv_handle`. `python-mpv` exposes `MpvRenderContext` with the full C API surface (verified 2026-04-22 via source inspection of `jaseg/python-mpv`).

**Per-monitor crop is a GL-layer concern, not a libmpv concern.** The `vf` (video filter) property is decoder-scoped — setting it affects all render contexts uniformly. Our architecture:

- Each playback window is a `QOpenGLWidget` with its own GL context
- Each widget creates its own `MpvRenderContext` against the shared `mpv_handle`
- Full-frame walls render libmpv's output directly to their framebuffer
- **Ultrawide wall:** runs a small fragment shader that samples libmpv's output with UV coordinates computed from the active crop preset (top/middle/bottom/etc.) — producing the cropped band in-place at GPU cost negligible compared to decode

This keeps the single-decoder guarantee intact (one clock, frame-perfect sync) while enabling per-monitor aspect treatments. The crop math runs once in a tiny fragment shader per affected wall, not in the libmpv pipeline.

### Robust per-monitor window placement

Historical pain: VLC and similar players handle multi-monitor placement poorly — windows land on the wrong monitor, spill across displays, or get misplaced when the video aspect doesn't match the monitor. ForgePlayer explicitly targets better behavior:

- Each playback window is a **borderless Qt widget** sized to exactly one `QScreen`'s geometry via `setGeometry(screen.geometry())` followed by `showFullScreen()`
- Qt's screen enumeration is stable and includes DPI / aspect metadata, so wall-to-monitor assignment is by unambiguous screen ID (not index, not position)
- Render contexts inside each window let libmpv fit the video to the window's pixels — never the other way around. Aspect mismatches result in letterbox (for narrower sources) or ultrawide-crop (for 16:9 source on wide monitors), never cross-monitor spill
- No "pick a monitor by dragging the window" flow — slots are assigned once in Setup, persisted in preferences.json, honored on every launch

### Quality defaults — mpv configuration

ForgePlayer ships an `mpv-defaults.conf` baked into the bundle that configures libmpv for image-quality-over-speed. Every `mpv.MPV()` instance loads it at startup. Users can override via `~/.forgeplayer/mpv-user.conf` (loaded after defaults).

Baseline defaults:

```
vo=gpu-next
hwdec=auto-safe
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=mitchell
video-sync=display-resample
interpolation=yes
deband=yes
dither-depth=auto
target-colorspace-hint=yes
```

**Why these:**

| Setting | Purpose |
|---|---|
| `vo=gpu-next` | Newer mpv video output with modern color pipeline + HDR handling |
| `hwdec=auto-safe` | Hardware decode (NVDEC on NVIDIA, QSV on Intel, AMF on AMD, VideoToolbox on Apple) — falls back to software when unsupported |
| `scale=ewa_lanczossharp` | Best-in-class spatial upscaler for 1080p→4K, the canonical mpv recommendation |
| `cscale` / `dscale` | Matched chroma upscaler and a clean downscaler for 4K→1080p on smaller monitors |
| `video-sync=display-resample` | Frame pacing locked to display refresh → eliminates judder on non-60Hz content |
| `interpolation=yes` | Motion smoothness on 24p / 30p content |
| `deband=yes` | Kills gradient banding on HDR and 10-bit content |
| `target-colorspace-hint=yes` | Passes HDR10 metadata through to the monitor when Windows/macOS HDR is enabled |

The quality story is documented for end users in `docs/quality.md` (GPU support matrix, HDR behavior, upscaling explanation, how to override defaults).

### Independent-slots mode (secondary, less-prominent)

The v0.1 prototype's "three independent video slots" capability is retained as a secondary mode — exposed as a toggle in Setup → Preferences. Flagship mode is same-video-mirrored; independent-slots is there for users who want to run three different videos simultaneously (e.g. multi-angle playback, A/B comparison).

---

## 4. UI — panel model

Three top-level panels, switchable via a tab bar at the top of the controller screen:

- **Live** — operator transport, current state, chapter jumps
- **Setup** — monitors, audio routing, library config, preferences
- **Library** — grid of videos with thumbnails, search, filter

### Navigation rules

- **Panel switching** is explicit: tap the tab bar only. No swipe cross-panel.
- **Within-panel navigation** is gestural: edge chevrons (`◀` / `▶`) and horizontal swipe do the same panel-specific action.
- Per-panel chevron behavior:
  - **Live** → previous / next chapter
  - **Setup** → previous / next setting section (Monitors → Audio → Library → Preferences)
  - **Library** → previous / next page of video cards (10 per page)

### Controller screen dimensions

All UI is designed for 1920×720 (~2.67:1 aspect, the Prechen form factor). Any 16:9 controller screen will also work but with more vertical whitespace than needed.

---

## 5. UI — Live panel

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 🔨 FORGEPLAYER  │  [ LIVE ◉ ]   [ SETUP ]   [ LIBRARY ]       📁 Load folder…    │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Prisoner.-38 76 71 8 175.mp4 · ch 3/12  "The hallway"                            │
│ [1]●Dell 4K L   [2]●Dell 4K R   [3]●LG UW · crop: middle                         │
├───┬──────────────────────────────────────────────────────────────────────────┬───┤
│   │                                                                          │   │
│   │    ⏮⏮    ⏮⏮     ⏮                 ▶                ⏭     ⏭⏭     ⏭⏭      │   │
│ ◀ │    -30   -10    -5            PLAY ⁄ PAUSE          +5    +10    +30     │ ▶ │
│chap│                                                                         │chap│
│   │   00:12:34  ████████████████░░◆░░░░░░░░░░░░░░░░░░░░░░░░░░░  01:45:22     │   │
│   │             chap 3  "The hallway"                                        │   │
│   │                                                                          │   │
├───┴──────────────────────────────────────────────────────────────────────────┴───┤
│ Ultrawide crop:  ▣ middle     ▢ top-mid     ▢ top     ▢ bot-mid     ▢ bottom     │
│                                                                                  │
│ OS        ──────●────── 80%    Dongle 1 ──●──────────  30%    Dongle 2 ──○── 0%  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Elements

| Element | Behavior |
|---|---|
| Tab bar | Tap to switch panels. Active tab shows filled dot. |
| File line | Current filename + chapter index + chapter title |
| Wall status dots | Filled = monitor active, empty = monitor disabled. Crop preset shown inline for the ultrawide wall only. |
| Transport buttons | Skip ±5, ±10, ±30 seconds. Play/Pause in the centre (120×120 px target). |
| Seek bar | Horizontal slider, fat (50 px tall). Filled portion = played, unfilled = remaining. Chapter markers as `◆` dots. Drag handle to scrub; all three walls seek in sync. |
| Time labels | Current position (left) / total duration (right) |
| Ultrawide crop row | Five preset chips. **Hidden if no ultrawide monitor is detected.** |
| Audio-out sliders | One slider per registered audio destination (max 3 in alpha). Volume 0–100% per destination. |
| Edge chevrons | Tap to jump to previous / next chapter |

### Transport behavior

- **Play/Pause** — toggles all render contexts via the single decoder
- **Skip ±N seconds** — seek relative to current position
- **Chapter jump** — seek to next/previous chapter marker from the source video's chapter metadata

### Chapter markers

Chapters come from the source video's embedded metadata (MKV / MP4 chapter atoms, as written by ForgeAssembler). Displayed as `◆` dots on the seek bar at each chapter timestamp. Current chapter name appears as a small label below the seek bar.

---

## 6. UI — Setup panel

Four sections, navigated via chevrons (same as panel navigation but scoped within Setup). Section indicator at the top: `Setup · section 1 of 4 · Monitors`.

### Section 1 — Monitors

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 🔨 FORGEPLAYER  │  [ LIVE ]   [ SETUP ◉ ]   [ LIBRARY ]                          │
│  Setup · section 1 of 4 · Monitors                                               │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   [1] Dell 4K #1         3840 × 2160  16:9      ▾ wall slot 1                    │
│   [2] Dell 4K #2         3840 × 2160  16:9      ▾ wall slot 2                    │
│   [3] LG 38WN             3840 × 1120  3.43:1   ▾ wall slot 3  · crop ▾ middle   │
│   [4] Prechen Touch       1920 × 720   2.67:1   ▾ controller                     │
│                                                                                  │
│   Auto-detected on launch. Re-scan: [⟳]                                          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Section 2 — Audio routing

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Setup · section 2 of 4 · Audio routing                                          │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   Source                    Output                       Label                   │
│  ┌──────────────────────┐  ┌─────────────────────────┐  ┌────────────────┐       │
│  │ Video audio          │▸ │ OS default              │  │ [Big speakers] │       │
│  └──────────────────────┘  └─────────────────────────┘  └────────────────┘       │
│  ┌──────────────────────┐  ┌─────────────────────────┐  ┌────────────────┐       │
│  │ Main funscript       │▸ │ USB Audio CODEC (dev 3) │  │ [Left haptic]  │       │
│  └──────────────────────┘  └─────────────────────────┘  └────────────────┘       │
│  ┌──────────────────────┐  ┌─────────────────────────┐  ┌────────────────┐       │
│  │ Prostate funscript   │▸ │ C-Media USB (dev 5)     │  │ [Right haptic] │       │
│  └──────────────────────┘  └─────────────────────────┘  └────────────────┘       │
│                                                                                  │
│   + Add source/output pair                                                       │
│                                                                                  │
│   💾 Save as default        📁 Save as preset for current video                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Friendly labels persist in `preferences.json` keyed by the OS-level stable device identifier. OS default stays labeled "OS default" and resolves lazily at play time — so if the user unplugs headphones mid-session, the next play picks up the new OS default.

### Section 3 — Library

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Setup · section 3 of 4 · Library                                                │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   Root folders:                                                                  │
│     📂 D:\forge\sessions                        [⟳ rescan]  [✕]                  │
│     📂 E:\edger-packs                           [⟳ rescan]  [✕]                  │
│     + Add folder                                                                 │
│                                                                                  │
│   Folder-load convention:                                                        │
│     ○ Auto-match by stem       (FunscriptForge layout)                           │
│     ○ Single-file mode         (pick video, everything else manual)              │
│     ● Flexible                 (auto where possible, prompt on mismatch)         │
│                                                                                  │
│   Thumbnail cache: ~/.forgeplayer/thumbs/  (234 MB)    [Clear]                   │
│   Rescan frequency: ● On launch    ○ Weekly    ○ Manual only                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Section 4 — Preferences

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Setup · section 4 of 4 · Preferences                                            │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   Preferences file: ~/.forgeplayer/preferences.json  [Open]  [Reveal in folder]  │
│                                                                                  │
│   Default chapter jump behavior:  ● Jump & play   ○ Jump & pause                 │
│                                                                                  │
│   🔧 Debug mode  [ ]  — emit event log to help with bug reports                  │
│                                                                                  │
│   About:  ForgePlayer v0.0.1-alpha · © 2026 Liquid Releasing · MIT License       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. UI — Library panel

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 🔨 FORGEPLAYER  │  [ LIVE ]   [ SETUP ]   [ LIBRARY ◉ ]      📁 Add folder…      │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 📂 D:\forge\sessions  ·  12 videos  ·  ⟳ rescan  ·  [search ________________]    │
├───┬──────────────────────────────────────────────────────────────────────────┬───┤
│   │                                                                          │   │
│   │ ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐               │   │
│   │ │[thumb] │  │[thumb] │  │[thumb] │  │[thumb] │  │[thumb] │               │   │
│   │ │        │  │        │  │        │  │        │  │        │               │   │
│ ◀ │ └────────┘  └────────┘  └────────┘  └────────┘  └────────┘               │ ▶ │
│-10│ Prisoner    VicOats 1   Bridge      Alpha Run   Opening                  │+10│
│   │ 1:45:22     34:12       28:45       52:11       03:44                    │   │
│   │ m• mx•p•    m• mx•      m•          m• mx•p•✎   m•✎                      │   │
│   │                                                                          │   │
├───┴──────────────────────────────────────────────────────────────────────────┴───┤
│ Page 3 / 40 · showing 21-30 of 395                                               │
│ [All] [Recent] [Favorites ★] [With preset ✎] [Playlists ▶]  Sort: ▾ name · date  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Card badges

| Badge | Meaning |
|---|---|
| `m•` | Main funscript detected |
| `mx•` | Multi-axis funscript detected |
| `p•` | Prostate funscript detected |
| `✎` | Per-video preset JSON exists (tap = launch with bakedin settings) |
| `★` | User-marked favorite |

### Interactions

- **Tap card** → load video + all detected assets + preset → auto-switch to Live panel, paused at 00:00
- **Long-press** → enters multi-select mode: card gets a checkmark, bottom action bar appears with `Play now · Queue next · Add to playlist…`
- **Vertical scroll** → smooth scroll through rows
- **Chevron `◀` / `▶` or swipe** → jump one page forward/back (10 videos)
- **Search** → live filter as you type
- **Filter chips** — All / Recent / Favorites / With preset / Playlists
- **Sort** — name / date added / duration

### Scene playlists (alpha)

Ordered lists of whole scenes. Built from Library multi-select. When one finishes, the next begins automatically.

- **Create** — long-press a card → `Add to playlist…` → pick existing or type a new name
- **Browse** — tap the `Playlists ▶` filter chip; grid switches to playlist cards, each showing name + count + runtime
- **Play** — tap a playlist card → starts the first scene in Live; transport "Next chapter" crosses into the next scene when the current one ends
- **Edit** — long-press a playlist card → reorder / remove / rename / delete
- **Storage** — one file per playlist at `~/.forgeplayer/playlists/<name>.json`: `{ "name": "...", "schema_version": 1, "entries": [{ "scene": "absolute/path/to/victoriaoats.mp4" }, ...] }`

**Moments playlists** (timestamp ranges across scenes) are **Phase 2** — they need the favorites data model first.

### Scaling to hundreds of videos

- **Lazy thumbnail generation** — first time a card becomes visible, generate thumbnail (first keyframe); cache to `~/.forgeplayer/thumbs/`
- **Virtualized grid** — Qt `QAbstractItemModel` + `QListView` tile renderer; only on-screen rows have live widgets
- **Folder sections** — multiple registered roots appear as collapsible sections (`▾ D:\forge\sessions (120)`, `▾ D:\edger-packs (47)`)
- **Incremental rescan** — on launch (or manual trigger), diff current folder contents against library index; add/remove only the delta

### Library rescan triggers

- **v0.0.1-alpha:** manual `⟳ rescan` button + automatic rescan on app launch. Simple, predictable.
- **Later phase:** hot-plug detection for new drives via Windows `WM_DEVICECHANGE`, macOS `DiskArbitration`, Linux `inotify` on `/media`. Path-aware scan (if a registered folder's drive letter becomes available) can get most of the benefit without OS-level events.

---

## 8. Config model — JSON presets

Two levels, same pattern as FunscriptForge / ForgeAssembler project JSON files.

### Global preferences — `~/.forgeplayer/preferences.json`

User's default setup. Changes rarely.

```json
{
  "schema_version": 1,
  "walls": {
    "1": { "display_id": "Dell U2725Q-1", "friendly": "Dell 4K L" },
    "2": { "display_id": "Dell U2725Q-2", "friendly": "Dell 4K R" },
    "3": { "display_id": "LG 38WN95C-W",  "friendly": "LG ultrawide" },
    "controller": { "display_id": "Prechen 12.3", "friendly": "Controller" }
  },
  "default_crop": "middle",
  "audio_devices": {
    "Realtek(R) Audio": "OS default speakers",
    "USB Audio CODEC": "Left haptic",
    "C-Media USB": "Right haptic"
  },
  "routing": {
    "video_audio":       [{ "device": "OS default",      "delay_ms": 0 }],
    "main_funscript":    [{ "device": "USB Audio CODEC", "delay_ms": 0 }],
    "prostate":          [{ "device": "C-Media USB",     "delay_ms": 0 }],
    "multi_axis":        [],
    "three_phase_estim": [],
    "audio_estim":       []
  },
  "library": {
    "root_folders": ["D:\\forge\\sessions", "E:\\edger-packs"],
    "load_convention": "flexible",
    "rescan_frequency": "on_launch",
    "thumbnail_cache": "~/.forgeplayer/thumbs"
  },
  "chapter_jump_mode": "jump_and_play",
  "debug_mode": false
}
```

### Per-video preset — `<videostem>.forgeplayer.json`

Lives alongside the video. Contains only overrides; everything else inherits from global.

```json
{
  "schema_version": 1,
  "crop": "top-mid",
  "routing": {
    "main_funscript": ["USB Audio CODEC #2"]
  },
  "start_position_s": 0.0,
  "notes": "Narrator's scenes are in the upper third — use top-mid crop."
}
```

### Load order at play time

1. Start with baked-in defaults
2. Merge in `~/.forgeplayer/preferences.json`
3. Merge in `<stem>.forgeplayer.json` if present
4. Apply to session

Later writes (e.g. "Save as preset for current video") serialize the session's effective state minus the global defaults, producing a minimal per-video override.

### Fan-out (schema-only for alpha)

`routing` values are **lists**, allowing fan-out from one source to multiple destinations. v0.0.1-alpha's implementation honors only the first entry per source (libmpv plays each instance to one device). Schema is list-shaped from day one so config files don't need to change when true fan-out lands in Phase 2.

If alpha encounters multi-destination config, log a warning (`multi-destination routing is Phase 2; using first entry only`) and proceed.

---

## 9. Folder-load conventions — the "pack" model

ForgePlayer ingests the same `{stem}.{suffix}.{ext}` pack that **FunscriptForge**, **ForgeAssembler**, and **ForgeGen** already emit. No renaming required.

### Canonical pack layout

**Required:**

| File | Role |
|---|---|
| `{stem}.mp4` / `.mkv` / `.webm` | Main video |
| `{stem}.funscript` | Main stroke funscript |

**Optional multi-resolution** — player picks the highest-resolution video in the pack; one funscript set serves all resolutions (funscripts are time-based, not pixel-based):

| File | Role |
|---|---|
| `{stem}.1080p30.mp4` / `{stem}.4k60.mp4` / etc. | Alt resolutions of same scene |

**Optional channel funscripts** (FunscriptForge / ForgeAssembler):

| File | Channel |
|---|---|
| `{stem}.{roll\|pitch\|twist\|surge\|sway}.funscript` | Multi-axis (5-DoF) |
| `{stem}.alpha.funscript` / `.beta.funscript` / `.pulse_frequency.funscript` | 3-phase estim |
| `{stem}.alpha-prostate.funscript` / `.beta-prostate.funscript` | Prostate estim |

**Optional pre-rendered audio** (FunscriptForge):

| File | Role |
|---|---|
| `{stem}.estim.mp3` | Pre-rendered estim audio; overrides live synthesis |
| `{stem}.{device}.wav` | Named device pre-render (e.g. `.legacy.wav`, `.stereostim.wav`) |

**Optional player state:**

| File | Role |
|---|---|
| `{stem}.forgeplayer.json` | Per-video preset (crop, routing, notes) |
| `{stem}.favorites.json` | Timestamp favorites (Phase 2) |

**Ignored:** `{stem}.heatmap.png`, `{stem}.forgetmpl`, editor scratch files.

### Example pack

```text
victoriaoats/
  victoriaoats.mp4                              ← 4K — picked by player
  victoriaoats.1080p30.mp4                      ← alt resolution
  victoriaoats.funscript                        ← main stroke
  victoriaoats.alpha.funscript                  ← 3-phase estim
  victoriaoats.beta.funscript
  victoriaoats.pulse_frequency.funscript
  victoriaoats.alpha-prostate.funscript         ← prostate
  victoriaoats.beta-prostate.funscript
  victoriaoats.roll.funscript                   ← multi-axis
  victoriaoats.pitch.funscript
  victoriaoats.estim.mp3                        ← pre-rendered estim
  victoriaoats.legacy.wav                       ← device pre-render
  victoriaoats.forgeplayer.json                 ← per-video preset
  victoriaoats.heatmap.png                      ← ignored
```

### Three load modes

- **Auto-match by stem** — strict; unassociated files ignored.
- **Single-file mode** — minimal; only the video, user assigns everything else manually.
- **Flexible (default)** — auto-associate by stem; on mismatch (e.g. Edger-style `bg_music_track3.mp3` alongside `scene.mp4`), prompt with channel dropdowns.

### Upstream compatibility

| Tool | Output | Fit |
|---|---|---|
| FunscriptForge | Full pack (funscripts + channel variants + pre-rendered audio) | ✅ direct |
| ForgeAssembler | `{stem}.mp4` + `{stem}.funscript` + multi-axis + alpha/beta + prostate | ✅ direct |
| ForgeGen | `{stem}.funscript` only (stroke from audio beats) | ✅ as main stroke |

---

## 10. Ultrawide crop

When a video's aspect ratio is narrower than a target monitor's aspect (typically playing a 16:9 source on an ultrawide), vertical bands of the source get clipped to make the kept band match the monitor's aspect. The app computes the crop amount from aspect math; the user picks the **vertical anchor** position from five presets:

| Preset | Top crop (4K source) | Bottom crop (4K source) | Anchor |
|---|---|---|---|
| Middle band | 520 | 520 | centered |
| Top middle | 320 | 720 | upper-centered |
| Top | 120 | 920 | near top |
| Bottom middle | 720 | 320 | lower-centered |
| Bottom | 920 | 120 | near bottom |

All five presets yield the same kept-band height (1120 px from a 4K source, producing ~3.43:1 aspect). The user shifts the anchor to keep the important action in frame.

For source aspects other than 16:9, the crop numbers scale proportionally but the named anchors remain.

**"Fill the screen" priority:** when the aspect doesn't divide cleanly, tolerate small side bands rather than shrinking the image to fit.

The crop only applies per-monitor — a 16:9 source plays full-frame on 4K monitors and cropped on the ultrawide, all from the same source file and the same decoder.

**UI:** the crop preset row in the Live panel is only visible when an ultrawide monitor is registered as a wall slot. If all walls are 16:9, the row is hidden entirely.

---

## 11. Auto-adapt on launch

On first launch (and every subsequent launch, in case the user's monitor setup changed):

1. Enumerate all connected displays via Qt's `QScreen`
2. Match each display against the saved wall/controller assignments in `preferences.json` by display-id
3. For any display not previously assigned, prompt once: "Wall slot 1 / 2 / 3 / controller / ignored?"
4. Apply per-monitor rendering mode:
   - 4K → native 4K render
   - 1080p → native 1080p render
   - Ultrawide → 4K source with ultrawide crop filter applied
5. Route audio per the saved routing config

No wizard, no setup flow — once the user has configured their setup once, first-run on a fresh boot should "just work."

---

## 12. Touch UI principles

The controller runs on a wired touchscreen in a dimly-lit video-wall environment. These rules come from that context and are baked into every UI decision:

### Dark-only theme

- No light-mode toggle; ship dark only
- Background `#0e1117`, surface `#1a1d27`, borders `#2d3148`
- Text `#fafafa`, muted `#9ba3c4`
- Accent `#ff6b30` — deep orange, distinguishes from FunscriptForge's `#ff4b4b`

### No reliance on scrollbars

OS scrollbars are thin, dark, auto-hiding, and hostile to touch in low light. Never required for primary navigation.

- Vertical scroll via touch drag is fine
- Long lists pair vertical-scroll with chevron / swipe page-jumps

### Explicit panel switching, gestural within-panel nav

- Panel tab bar at top: tap only. No swipe cross-panel.
- Within-panel: chevron + swipe do the same context-sensitive action.

### Target sizes

| Control | Minimum |
|---|---|
| Primary action (Play/Pause) | 120 × 120 px |
| Secondary action (skip, chapter, tab) | 80 × 80 px |
| Tertiary (chip, toggle) | 60 × 60 px |
| Edge chevron column | 100 px wide |
| Seek bar handle | 50 px tall drag target |

On the Prechen (~155 PPI), an 80 px target = ~13 mm, comfortably above the 9 mm touch minimum.

---

## 13. Shipping pipeline

Mirrors the ForgeAssembler pattern. Only the app bundle differs in specifics due to the Qt / libmpv stack.

### Repo

`liquid-releasing/forgeplayer` (already created on GitHub).

**Open decision:** rename the local `ehaptics-studio-player/` folder to `forgeplayer/` and push as the initial commit, or keep the current folder name and rebrand the app-facing strings only. Recommended: full rename — consistency across app, repo, domain, and wordmark.

### Release artifacts

`liquid-releasing/forgeplayer-releases` (to be created). 3-platform bundles via the ForgeAssembler-pattern CI.

### PyInstaller

`ForgePlayer.spec` — modelled on `ForgeAssembler.spec` but with:

- **PySide6 + Qt plugins** collection hooks (replaces streamlit data)
- **libmpv** DLL / dylib / so bundling per platform (Windows `mpv-2.dll` next to exe; macOS `libmpv.dylib` in app bundle Resources; Linux `libmpv.so` in dist folder)
- **No streamlit, no imageio-ffmpeg** — Qt handles everything

### CI — `.github/workflows/release.yml`

Three-platform matrix (`windows-latest`, `macos-latest`, `ubuntu-latest`), same `softprops/action-gh-release` pattern, classic PAT via `RELEASES_PAT` secret on the repo. Each platform also needs to fetch libmpv:

- Windows: download mpv-2.dll from mpv.io release archive
- macOS: `brew install mpv` then pack `libmpv.dylib`
- Linux: `apt-get install libmpv-dev`

### Landing site

`liquid-releasing/forgeplayer-web` at **forgeplayer.app** (domain registered 2026-04-21 on Cloudflare). Copy the `forgeassembler-web` template:

- Cloudflare Workers Assets deploy (`wrangler.toml` + `.assetsignore`)
- Single `index.html` with hero, features, download buttons, cross-link panels to FunscriptForge / ForgeAssembler / ForgeYT
- `latest-version.json` for version-badge auto-update via `repository_dispatch` from the release workflow

### Docs

MkDocs Material under `docs/`, same as ForgeAssembler. Pages:

- Getting Started (download, launch, auto-detect flow, first play)
- Live operator console walkthrough
- Setup panel (monitors, audio, library, preferences)
- Library panel
- Presets & folder conventions
- Ultrawide crop explained
- Troubleshooting

Deploys to `liquid-releasing.github.io/forgeplayer/` via the same `docs.yml` workflow pattern.

---

## 14. Alpha phasing — v0.0.1 and v0.0.2 scope gates

Alpha ships in two stages. Each stage has its own shipping criterion. Everything in 0.0.2 is validated against a 0.0.1 user who has upgraded their rig.

### v0.0.1-alpha — "baseline works great"

**Shipping criterion:** a user with a laptop + 1 external monitor + 1 USB audio dongle can load a FunscriptForge / ForgeAssembler pack folder, play it fullscreen on their external, hear audio on their dongle, scrub the seek bar smoothly, jump chapters, and find the result **noticeably better** than their current VLC / WMP-wrapped workflow.

**Explicitly IN for 0.0.1:**

- ✅ Single-decoder architecture with one render context (laptop = controller, 1 external = wall)
- ✅ `QOpenGLWidget` + `MpvRenderContext` against a shared `mpv_handle` (foundation for 0.0.2 multi-render)
- ✅ **Quality defaults** — `mpv-defaults.conf` with gpu-next, ewa_lanczossharp, HDR pass-through, display-resample (see Section 3)
- ✅ Auto-detect monitors; "laptop internal = controller, smallest / touch-capable / explicit assignment" resolution
- ✅ Mouse-or-touch operator console — same code path, degrades from Prechen touch to laptop trackpad
- ✅ Three-panel architecture (Live / Setup / Library)
- ✅ JSON presets (global + per-video override)
- ✅ Folder-load conventions (Auto / Single-file / Flexible, default Flexible) — canonical `{stem}.{suffix}.funscript` pack
- ✅ Multi-destination audio: OS default + 1 USB dongle validated (schema supports more)
- ✅ Friendly audio-device labels, keyed by stable OS device ID
- ✅ Per-destination audio delay (ms) for latency compensation (Bluetooth, HDMI pipeline) — exposed as an "Advanced" subsection in Setup → Audio routing, default 0 ms, mapped to libmpv's `audio-delay` property
- ✅ Library with search, filters, thumbnails, virtualized grid
- ✅ **Scene playlists** — ordered lists of whole scenes, built via Library multi-select, stored as JSON per playlist
- ✅ Chapter markers on seek bar + chevron jump
- ✅ Rebrand from "eHaptic Studio Player" to "ForgePlayer"
- ✅ PyInstaller bundles for Windows / macOS / Linux (Ubuntu 24.04 LTS reference)
- ✅ 3-platform CI + release automation to `forgeplayer-releases`
- ✅ Landing site at forgeplayer.app
- ✅ MkDocs docs — includes `docs/quality.md` and `docs/hdr-content.md`

### v0.0.2-alpha — "ultrawide + scale-up"

**Shipping criterion:** a 0.0.1 user who plugs in an ultrawide monitor (or a user with the full 3-wall rig) gets proper per-monitor crop, multi-wall same-video-mirrored playback with frame-perfect sync, and can plug in the Prechen touchscreen as the controller.

**Explicitly IN for 0.0.2:**

- ✅ Ultrawide monitor support (second external display)
- ✅ Per-monitor crop via GL UV fragment shader — 5 vertical-anchor presets
- ✅ 2-3 wall same-video-mirrored architecture (N=2 and N=3 render contexts on the shared `mpv_handle`)
- ✅ Independent-slots mode (secondary toggle, carries forward from v0.1 prototype)
- ✅ Prechen 12.3" 1920×720 touchscreen as dedicated controller (touch event plumbing)
- ✅ Multi-destination audio validated up to 3 dongles
- ✅ Any 0.0.1 gaps surfaced during user testing
- ✅ Any features cut from 0.0.1 that turned out to be essential

### Explicitly OUT (Phase 2+)

- ❌ **Funscript → audio conversion (restim-style playback)** — Phase 2
- ❌ **Moments playlists** (timestamp ranges across scenes) — Phase 2; needs favorites data model first
- ❌ **Timestamp favorites** (⚑ Mark during playback, `{stem}.favorites.json`) — Phase 2; foundational for moments playlists
- ❌ **Transport state machine** (which buttons are active during load / buffering / seeking / ended states) — Phase 2; alpha uses naive "always enabled" behavior
- ❌ **bhaptics `.tact` integration** — Phase 3
- ❌ **Theme system** (Forge industrial, Neon, light modes — see `ui_design/` for prior visual language work) — Phase 3; alpha is dark-only
- ❌ **Real-time audio → haptics (live mode / bREadbeats-style)** — Phase 5
- ❌ **Bluetooth audio** — Phase 2 (latency + presence flakiness)
- ❌ **Fan-out routing** (one source → many devices) — Phase 2; schema supports it from alpha, impl doesn't
- ❌ **Drive hot-plug detection** — Phase 2; alpha ships manual rescan button
- ❌ **Playback speed control** — Phase 2; needs design work on funscript time-scaling
- ❌ **7.1 channel audio routing** — Phase 3
- ❌ **Network / LAN multi-machine sync** — no ETA
- ❌ **Timeline editor / loop regions** — no ETA

---

## 15. Open questions

1. **Chapter jump wrap** — at the first or last chapter, wrap around or hit a wall? (Suggestion: wall, with button dimmed.)
2. **Preferences file location on macOS / Linux** — `~/.forgeplayer/preferences.json` on all three, or follow XDG Base Directory on Linux (`$XDG_CONFIG_HOME/forgeplayer/`)? Suggestion: simple dot-folder on all three for consistency with FunscriptForge / ForgeAssembler.
3. **Scene playlist crossover** — when a scene in a playlist ends, should transport auto-advance to the next scene, or pause and require an explicit `▶` tap? (Suggestion: auto-advance, with a Preferences toggle to override.)

---

*© 2026 Liquid Releasing. Licensed under the MIT License.*
