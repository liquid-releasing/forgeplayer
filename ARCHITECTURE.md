# ForgePlayer — Architecture

> **Rewritten 2026-08-20** to match the shipped v0.0.15 architecture. The
> prior version of this file was titled "SyncPlayer.app" (an earlier product
> name) and described a `HapticsEngine` for serial/USB devices, restim run
> as a subprocess with a `restim.ini`, and a phone-remote WebSocket
> architecture — none of which were ever built. This version describes the
> real, running system.

## What It Is

ForgePlayer is a PySide6 + python-mpv desktop app (Windows / macOS / Linux)
that plays a video across one to three monitors while synthesizing e-stim
audio from the same scene's funscripts in-process, in real time, routed to
one or two haptic audio devices. A `ControlWindow` operator console drives
transport, library browsing, and device/monitor wiring; borderless
`PlayerWindow`s carry the actual video.

---

## Process & thread model

Everything runs in one process. Threads:

- **GUI thread** — the Qt event loop. `ControlWindow`, every `PlayerWindow`,
  and all widget code live here. Nothing that touches a `QWidget` may run
  off this thread.
- **`QThreadPool` workers**, one dedicated pool per background job class so
  one job type can never starve or queue behind another:
  - Library root scan — `library_panel.py`'s `_ScanJob`, on `LibraryPanel._scan_pool`
    (max 1 thread). Walking a scene folder tree (`scan_library_root`) can block
    for a long time on a spun-down or disconnected external drive; running it
    off-thread keeps the app responsive instead of freezing on `Scan folder`.
  - Stim-source Browse scan — `control_window.py`'s `_StimFolderScanJob`, on
    `ControlWindow._stim_scan_pool` (max 1 thread). Re-walks the picked file's
    folder for channel siblings (alpha/beta/pulse_*/-prostate) via the same
    `scan_scene_folder` call the library scan uses, so it hits the same
    slow-drive risk.
  - Update check — `update_check.py`'s `UpdateCheckJob`, on
    `ControlWindow._update_pool` (max 1 thread). A network GET; never on the
    GUI thread.
  - Each job type reports back via a small `QObject` + `Signal` pair (e.g.
    `_ScanSignals.done`, `UpdateCheckSignals.done`) so the GUI-thread slot that
    consumes the result is the only place touching widgets.
- **`concurrent.futures.ThreadPoolExecutor`** — `ControlWindow._teardown_pool`,
  sized to `_NUM_SLOTS` (4). Runs mpv's stop/vo=null/terminate teardown dance
  (`SyncEngine._teardown_mpv_instance`) for every slot **off** the GUI thread
  and **in parallel**, via `SyncEngine.terminate_player_async`. See
  "The crash-fix architecture" below for why this exists.
- **mpv's own event/render thread(s)** — every `mpv.MPV()` instance owns its
  own internal threads (demux, decode, GPU-context/render). ForgePlayer never
  touches these directly; it only issues property sets and commands through
  `python-mpv`.
- **sounddevice audio callback thread(s)** — `StimAudioStream` (see
  `docs/architecture/audio-routing.md`) opens a `sounddevice.OutputStream`
  per haptic destination; the audio callback pulls PCM from whatever
  `AudioSource` (a `StimSynth` or a pre-rendered-file player) is attached.

There is no subprocess anywhere in this picture — no embedded restim, no
Node/web server, no phone client. It's one Python process, one Qt event
loop, N mpv instances, and 0-2 sounddevice output streams.

---

## Class structure

```
ControlWindow (QMainWindow)
    │
    ├── SyncEngine                  owns up to 4 mpv.MPV() slots + 2 headless
    │                                audio-mirror mpv instances; play/pause/seek
    │                                fan out to every active instance in one pass
    │
    ├── PlayerWindow  × N            one borderless window per active video/mirror
    │                                slot; embeds mpv via native wid + an overlay
    │                                control bar (Prev/Next chapter flank Play/Pause)
    │
    ├── LibraryPanel                 Library tab: LibraryModel (Qt model over
    │                                SceneCatalogEntry) + LibraryCardDelegate +
    │                                async folder scan
    │
    ├── Preferences                  ~/.forgeplayer/preferences.json — device
    │                                roles, monitor roles, synth algorithm, etc.
    │
    └── StimAudioStream × ≤2         one per haptic destination that's live;
                                     wraps a StimSynth (native synthesis) or
                                     AudioFilePlaybackSource (pre-rendered .wav)
```

### `ControlWindow` (`app/control_window.py`)

The main window and the coordinator for everything else. Owns:

- The `SyncEngine` and the list of open `PlayerWindow`s (indexed by slot).
- Five tabs, built in `_build_ui` and added to a `QTabWidget` in this order:
  **Library → Live → Setup → Preferences → About.** The order follows the
  user's actual journey — pick a scene, drive playback, wire hardware once,
  tune rare behavior, check version/credits. (There is no "Setup / Live /
  Library" 3-tab model — that was the pre-implementation SPEC's plan; five
  tabs shipped instead, and About was added since.)
- A fixed 4-slot data model (`_SLOT_LABELS` / `_SLOT_ROLES` /
  `_NUM_SLOTS = 4`): slot 0 = primary video, slot 1 = stim (haptics), slots
  2-3 = mirror (second/third monitor, muted). This is **not** a
  general N-instance video-wall — it's four fixed roles.
- `_on_scene_activated` — fires when the user taps a Library card. Resolves
  a `.forge`/`.output` bundle over loose scanned funscripts if one exists
  (`_resolve_bundle_backed`, see below), replays a saved **pin** (the user's
  remembered video/audio/funscript/subtitle picks for that scene folder,
  `app/library/pins.py`) if one exists and every referenced file still
  resolves, or shows the `SelectPicker` modal when the scene is ambiguous or
  the pin is stale.
- `_resolve_bundle_backed` — when a Library card has a `bundle_path` (a
  `.forge`/`.output` FunscriptForge export sitting next to loose scanned
  files), imports the bundle via `bundle_importer.load_bundle` and grafts the
  bundle's haptics onto the user's own loose video variants. A bundle's
  haptics always win over stray loose funscripts scanned in the same folder.
- `_on_launch` — builds/reuses `PlayerWindow`s and mpv instances for every
  slot with media, dispatches the stim slot into `StimSynth`/`StimAudioStream`
  instead of mpv, and is where the crash-fix reuse logic lives (next section).
- `_close_players` — tears every active player down, keeping any slots passed
  in `keep_slots` (the reuse path). Stops `StimAudioStream`s in parallel via a
  `ThreadPoolExecutor` first (their ~40 ms fade-out would otherwise serialize),
  *then* hands every mpv instance to `SyncEngine.terminate_player_async` on
  `_teardown_pool` and waits for every future before touching a `PlayerWindow`.
- `closeEvent` — the whole-app exit path. Stops any live sounddevice streams
  cleanly (safe on the GUI thread), then calls `os._exit(0)` — a **hard exit
  that skips libmpv's own teardown entirely**. See the crash-fix section.

### `SyncEngine` (`app/sync_engine.py`)

Owns `MAX_SLOTS = 4` `mpv.MPV()` instances plus two headless, audio-only
mirror instances (`_scene_audio_mirror` for a second Scene Audio output,
`_stim_audio_mirror` for a Haptic 2 that mirrors Haptic 1's sound file). All
three groups are combined in the `_active` property, and transport methods
(`play_all`, `pause_all`, `seek_all`) apply to every one of them in a single
pass — that's the sync mechanism: independent mpv instances, kept in lockstep
by fanning out the same command to all of them, not a single shared decoder
with multiple render contexts. `seek_all` uses `precision="exact"` (decode
forward from the keyframe) because `"default-precise"` was landing 2-12
seconds off on HandBrake-encoded sources, and briefly mutes/unmutes around
the seek to avoid an audible click from the sample discontinuity.

`init_player` is where the AMD-driver workaround lives (see below): `vo=gpu`
(not `gpu-next`), `hwdec=auto-safe`, `hr_seek=yes` for frame-accurate chapter
and slider seeks, and — on a detected hybrid-GPU Windows machine — an
explicit `gpu_context="d3d11"` / `d3d11_adapter="NVIDIA"` pair that steers
mpv's D3D11 context onto the NVIDIA adapter.

### `PlayerWindow` (`app/player_window.py`)

One borderless `QWidget` per active video/mirror slot, sized to and placed
on one `QScreen` (`place_on_screen`). mpv renders directly into the window's
native handle (`native_wid()`), embedded after `show()` so the handle is
valid. A hidden-by-default overlay control bar (48 px) has Prev-chapter /
Play-Pause / Next-chapter plus a seek bar and time labels — added the same
day as the crash-fix work. Escape or a double-click on the video surface (an
mpv-level key binding, since mpv owns that native child window) asks
`ControlWindow` to tear every player down together, deferred via
`QTimer.singleShot(0, …)` so the teardown never runs on the same call stack
as the event handler that triggered it (a same-stack teardown was an
intermittent use-after-free on close).

### Library (`app/library/`, `app/library_panel.py`)

- `scanner.py` — `scan_library_root()` walks a root two levels deep (root →
  scene folders), classifies files by extension and filename tag into
  `VideoVariant` / `AudioVariant` / `FunscriptSet` / `SubtitleTrack`, and
  flattens a `.forge` subfolder's contents into its parent scene. It
  deliberately skips `.output`/`.forge`/`.forgeplay` **export bundles** as
  scannable scene folders in their own right (they open through the bundle
  importer, not the raw scanner) — see `_is_export_bundle_dir`.
- `channels.py` — the funscript filename taxonomy: which `.suffix` maps to
  which channel, and which channel sets satisfy which `DeviceGeneration`
  (mechanical / 2B / stereostim / FOC-stim / multi-axis).
- `catalog.py` — the `SceneCatalogEntry` dataclass the scanner emits per
  scene folder, plus an ambiguity flag that gates whether `SelectPicker`
  must appear.
- `pins.py` — auto-saves the user's picker choices per scene folder to
  `<scene>.forgeplayer.json` (a `Pin`: video/audio/funscript-set/subtitle
  filenames) so the next play skips the picker. A global index at
  `~/.forgeplayer/catalog.json` maps folders to their pins for fast Library
  badges. This is the real shape of what a "per-video preset" is in this
  app — not a hand-editable crop/routing override file.
- `library_panel.py` — `LibraryPanel` composite widget: root picker, search,
  filter chips (All / Videos with Funscripts / Videos), a virtualized
  `QListView` grid with a custom `LibraryCardDelegate`, and the async scan
  (`_ScanJob`/`_ScanSignals`, described above).

### `bundle_importer.py`

Imports a FunscriptForge `.forge` ZIP (or its loose `<stem>.output/` folder)
into a scene the scanner can hand to `ControlWindow`. A bundle is
*device-organized* (`stations/estim3p/…`, `stations/tcode/…`,
`audio/stim.mp3`, `manifest.ffmeta`); importing is a normalize step — extract
the wanted members, lay the per-channel funscripts into a `.forge/`
subfolder using the same `<stem>.<channel>.funscript` naming the scanner
expects, relink the source video from the manifest if it wasn't bundled, and
hand the folder to `scan_scene_folder`. Extraction is **selective**
(`_is_wanted_member`): only `.funscript` files, `manifest.ffmeta`, and
`chapters.json` are pulled from the ZIP — bundled media and pre-rendered stim
audio (which can run into the GB range) are skipped, because unzipping all of
it on the UI thread on every activation used to freeze the app.

### `chapters.py`

Loads `<video_stem>.chapters.json` — an optional sidecar with a `chapters`
array (structural, one per section, feeds Prev/Next chapter) and a
`markers` array (hand-placed FunscriptForge navigation points, rendered as
tick marks on the seek bar). Malformed or missing sidecars yield an empty
list rather than raising; chapters are a nicety, not a precondition for
playback. When no sidecar exists, `SyncEngine.get_chapter_list()` falls back
to whatever chapter metadata mpv parsed from the file itself.

### `preferences.py`

`Preferences`, persisted to `~/.forgeplayer/preferences.json`. This is a
fixed-role model, not the SPEC's flexible source→destination table: four
audio-device-role fields (`scene_audio_device`, `scene_audio_secondary_device`,
`haptic1_audio_device`, `haptic2_audio_device`), monitor-role fields
(`control_panel_screen`, `playback_screen_indices`, `fill_screen_indices`,
`crop_align`), the synthesis algorithm choice (`audio_algorithm`:
continuous/pulse, default pulse), a haptic latency offset, a sound-vs-funscript
tie-breaker (`content_preference`), the last-scanned library root, and the
dismissed update-check tag.

---

## The real e-stim synthesis path — in-process, not a subprocess

There is no embedded restim process, no `restim.ini`, no IPC. `StimSynth`
(`app/stim_synth.py`) calls the **vendored** restim math library directly, in
the same process, on the sounddevice audio-callback thread:

- `app/vendor/restim_stim_math/audio_gen/continuous.py` → `ThreePhaseAlgorithm`
  (smooth-carrier continuous mode — the default, matching FunscriptForge's own
  MP3 render).
- `app/vendor/restim_stim_math/audio_gen/pulse_based.py` →
  `DefaultThreePhasePulseBasedAlgorithm` (discrete-pulse mode, engaged
  automatically when any `pulse_*` channel is present).
- `app/vendor/restim_stim_math/axis.py` — the axis primitives
  (`create_constant_axis`, `create_precomputed_axis`) that turn a funscript's
  sparse action samples into a continuous parameter curve the algorithm reads.

`StimSynth.generate_block()` / `generate_block_with_clocks()` synthesizes
stereo float32 PCM directly from a `StimChannels` record (loaded from the
scene's funscripts by `app/funscript_loader.py`) plus the video's current
`time_pos`; `StimAudioStream` (`app/stim_audio_output.py`, see
`docs/architecture/audio-routing.md`) pushes that PCM to a `sounddevice`
output stream. Algorithm choice is per-scene, driven by which channels are
present (any `pulse_*` channel → pulse-based; otherwise continuous), not a
device- or process-level setting.

restim itself is credited as the upstream source of this math (three-phase
electrode encoding, pulse/continuous algorithms, the funscript axis model) —
see `docs/architecture/restim-channels.md`,
`docs/architecture/stim-synthesis.md`, and `docs/architecture/audio-routing.md`
for the channel taxonomy, phase/device-support tracking, and the
source→destination audio routing model respectively. This file doesn't
duplicate that depth.

There is likewise no phone/mobile client and no WebSocket server anywhere in
the codebase — the "Phone Remote Architecture" in the old version of this
file described a product that was never built.

---

## The crash-fix architecture

mpv's `vo=gpu` D3D11 render-context teardown hits a **confirmed, currently
unfixed AMD driver bug** — an access violation inside the driver's own
context-destroy path (upstream: mpv-player/mpv#14601, and mpv-player/mpv#11882
for the matching "dispose then create a new instance" pattern on Windows).
mpv's own maintainers say it's a driver defect they can't fix from mpv's
side. Every close, relaunch, and scene switch used to exercise that exact
teardown path, so a user who switched scenes frequently hit it constantly.
The fix here is **not** patching mpv or the driver — it's minimizing how
often the crash-prone path runs at all, plus routing around the bad adapter
where a machine has a second one:

1. **Reuse instead of recreate** (`ControlWindow._on_launch`). Before
   tearing anything down, `_on_launch` computes `reusable_slots`: a slot's
   existing `PlayerWindow`/mpv instance can be kept if the target monitor and
   fullscreen state haven't changed — in which case launching just calls
   `SyncEngine.load_file()` with the new path, never touching `vo=null`/
   `terminate()`. This is the fix that protects **every** user, single-GPU
   machines included, because it simply avoids the crash-prone code path
   most of the time instead of trying to survive it.
2. **NVIDIA adapter routing** (`SyncEngine._detect_nvidia_adapter`,
   `_HAS_NVIDIA_ADAPTER`). On a hybrid-GPU Windows machine (an AMD iGPU +
   NVIDIA dGPU, detected once via `EnumDisplayDevicesW`), `init_player` sets
   `gpu_context="d3d11"` + `d3d11_adapter="NVIDIA"` on every `mpv.MPV()`
   instance — the one lever that actually steers mpv's D3D11 backend onto the
   NVIDIA adapter. **Windows' own per-app "GPU preference" registry key
   (which `main.py`'s `_prefer_high_performance_gpu` also writes, for other
   apps' benefit) does not work for mpv** — confirmed by testing, not
   assumption: mpv's d3d11 backend never queries it. This only helps
   hybrid-GPU machines; there's no second adapter to route to on an
   AMD-only or Intel-only box.
3. **Off-GUI-thread, parallel teardown.** When a real teardown is
   unavoidable, `SyncEngine._teardown_mpv_instance` (stop → set `vo=null` →
   wait up to 1s for `current-vo` to actually detach → `terminate()`) runs on
   `ControlWindow._teardown_pool` (a `ThreadPoolExecutor`) via
   `terminate_player_async`, not the GUI thread — interleaving mpv's native
   teardown with Qt's own window-management calls **on the same thread** was
   the dominant crash pattern captured in dogfood `faulthandler.log`s. Every
   slot's teardown is submitted in parallel and the caller waits for every
   future before destroying the corresponding `PlayerWindow`, so the native
   window is never yanked out from under an in-flight GPU-context release.
4. **Hard exit on whole-app close.** `ControlWindow.closeEvent` skips
   libmpv's teardown entirely via `os._exit(0)` — `mpv_terminate_destroy`
   reliably access-violates when the *whole app* is exiting concurrently
   with Qt tearing down the embedded player windows. The OS reclaims mpv
   instances, GPU contexts, and audio-device handles on process death, so a
   hard exit is actually the clean option here. Mid-session **Close Players**
   / scene-change still runs the full graceful `_close_players` dance, which
   does not crash on `vo=gpu`.
5. **`vo=gpu`, not `vo=gpu-next`.** `gpu-next` (libplacebo) was tried for its
   better HDR/color pipeline, but its D3D11 teardown reliably access-violated
   on embedded (`wid`) players — closing a video or the app crashed the whole
   process. Reverted to the stable `gpu` VO, with `tone_mapping=bt.2390` +
   `hdr_compute_peak=yes` for a perceptual HDR→SDR tone-map instead of true
   HDR passthrough.

---

## The update-check flow

On startup, `ControlWindow.__init__` schedules
`QTimer.singleShot(4000, self._check_for_update_startup)` — deferred a few
seconds so a slow or offline network can never look like the app hanging on
launch. That calls `_start_update_check`, which submits an `UpdateCheckJob`
to `_update_pool` (a 1-thread `QThreadPool`). The job's `run()` calls
`check_for_update()` (`app/update_check.py`), a synchronous `urllib` GET
against `https://forgeplayer.app/latest-version.json` (6 s timeout) — the
same version badge `forgeplayer-web`'s own CI keeps in sync with GitHub
Releases, so the in-app notice can never claim a version the marketing site
doesn't also claim. The result comes back over `UpdateCheckSignals.done` to
`_on_update_checked` on the GUI thread, which updates the About tab's status
label and — for the automatic startup check only, never a manual "Check for
updates" click — pops an "Update available" `QMessageBox` at most once per
version (`Preferences.dismissed_update_tag` suppresses repeats for a
version the user already dismissed).

---

## The pipeline

```
FunScriptForge Explorer    analyze video, detect phrases, originate funscripts
        │
        ▼
FunScriptForge             edit phrases, apply transforms, shape motion
        │
        ▼
funscript-tools            apply ReTransform (estim character), generate output pack
        │
        ▼
ForgeAssembler              (optional) concatenate clips into one combined output
        │
        ▼
ForgePlayer                 scan the library, play the scene, synthesize e-stim
                             in-process, sync every open monitor
```

The funscript — and the `.forge`/`.output` export bundle that packages a set
of them — is the connective tissue between every tool in the family.

---

## Technology credits

- **mpv** (https://mpv.io) — media engine. GPL licensed.
- **python-mpv** (https://github.com/jaseg/python-mpv) — Python/mpv bindings. LGPL.
- **PySide6** (https://wiki.qt.io/Qt_for_Python) — Qt6 Python bindings. LGPL.
- **diglet48/restim** (https://github.com/diglet48/restim) — e-stim synthesis math, vendored in-process at `app/vendor/restim_stim_math/`. MIT.
- **edger477/funscript-tools** (https://github.com/edger477/funscript-tools) — funscript pipeline. MIT.
