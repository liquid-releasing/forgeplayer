# ForgePlayer — Beta Punch List

Reconciled against **v0.0.15** (2026-08-20). The curated, prioritized road to a
confident **beta** label. `BACKLOG.md` is the long-horizon idea pool (phase
roadmap); this file is what's actually left near-term, folding in the still-open
backlog items.

Nothing below blocks shipping v0.0.15 (it's published). The gates are what a
first-time beta tester actually feels. Already shipped since the old backlog:
Haptic 2 dispatch, Prev/Next chapter buttons (console + per-player overlay),
seek-bar markers, Calibrate, mkdocs docs, PyInstaller packaging, in-app
auto-update check, third-monitor support, async library/folder scanning
(no more UI freeze on a slow/attached drive), and the crash-hardening work
in `_on_launch` (player/mpv reuse across a scene switch + NVIDIA GPU
routing on hybrid-graphics laptops).

---

## Beta quality gates (do these first)

- [ ] **Code-sign the Windows installer.** Currently unsigned — that's why the
      docs walk users through the SmartScreen "Keep / Run anyway" steps. Signing
      removes that friction; biggest single beta-polish win. (macOS notarization
      is the parallel item.)
- [x] **Verify no clicks across scene / chapter auto-advance boundaries.**
      **Dogfooded 2026-08-20** (both H1 and H2, real hardware, many Prev/Next
      chapter transitions): only minor, occasional clicks — same low
      background rate as the residual click-rate item below, not a new
      boundary-specific issue. Also surfaced and fixed a real crash: rapid
      Prev/Next clicking (~1/s) raced the live-synth math into an access
      violation; fixed via a debounce on the trigger (commit `5d0e897`),
      not a patch to the vendored math itself.
- [ ] **Hardware feel-test the actual v0.0.12 release artifact** on the
      workstation + haptic dongle (not just "sounds right" through headphones).
- [ ] **Confirm the flagged "D29 audio-only ship-blocker"** from the setup/Live
      redesign is actually resolved against the current build.
- [ ] **Residual ~7% audible click rate / hardware-side pop** — narrowed to
      device-level analog transients. Hold-on-fail; investigate only if users
      report.
- [ ] **Native crash while a big new library root thumbnails during playback**
      — dogfood 2026-08-29, **not reproduced since, no root cause**. Sequence
      from `debug-stream-20260829-152833.jsonl`: root changed to `E:i`
      (177 videos) → activated a video-only scene → Play (2 video slots, one
      filling an ultrawide) → the grid kept generating thumbnails for ~13 s →
      process died. `faulthandler.log` ends in an `access violation` that is
      **truncated mid-write** (severe enough to kill the process before the
      dump finished), so there is no usable crashing frame. Ruled out: the
      thumbnail grabber on its own — 40 grabs, 2 concurrent, same folder,
      headless, zero crashes; and the stim path — that scene had no stim of
      any kind (slot 1 skipped, "no media"). Remaining suspicion is the known
      mpv/D3D11 crash class, newly exercised by two live players plus a
      thumbnail flood. **Next step is a repro on the current build with Debug
      ON**, not a speculative fix. A candidate mitigation if it recurs: hold
      thumbnail generation while players are active.
- [ ] **An unreadable drive takes the app down instead of saying so** —
      dogfood 2026-08-29, and the FIRST complete crash dump we've got
      (`Current thread` marker present): the GUI thread died in native code
      while **two thumbnail threads sat blocked in `_grab_frame_to`'s 20 s
      demux wait** on files whose device had stopped responding. Root cause of
      the symptoms was NOT ForgePlayer — a Samsung T5 EVO on `G:` was dropping
      off the bus: directory entries still enumerated from cache while every
      read failed ("The device is not ready" / "No medium found"), VLC couldn't
      open the same files either, the pin write failed with `PermissionError`,
      and minutes later the identical file read back fine three times in a row.
      But the app should surface that, not hang 20 s per file and then die.
      Proposed fix: probe readability (open + read a block) before `loadfile`
      and before a thumbnail grab; on failure skip fast and surface a
      user-actionable "can't read this file — drive disconnected?" instead of
      the long demux wait. See [[feedback_user_actionable_errors]].
- [ ] **Prev/Next chapter enabled on a scene that reported 0 chapters** —
      dogfood 2026-08-29, user rates it harmless. Probably correct behavior
      rather than a bug: the sidecar pass logged `chapter_count: 0`, but
      `_maybe_populate_chapters_from_mpv` re-checks after launch and a
      compilation almost certainly carries embedded chapter atoms. Confirm
      which it was before touching the enable logic.
- [ ] **White-screen-after-double-click (intermittent)** — reproduced ~3× in
      early dogfood, not seen since; capture stderr if it recurs
      (`python main.py 2> mpv-err.txt`). Close after a clean dogfood pass.

## Alpha-polish bugs (non-blocking, but visible)

- [ ] **Control panel taller than a small secondary monitor** — moving the
      control window to a 1280×720 screen leaves it overflowing. Cosmetic.
- [ ] **+10 s while stopped jumps to 0** instead of holding the seeked position
      (transport-state ordering bug).
- [ ] **Empty Live tab when nothing is loaded** — add a "Click a scene in
      Library to get started" hint.
- [ ] **HDR white *thumbnail*** (Optikon) — the headless frame-grab can't
      tone-map a raw screenshot. Player HDR is fixed and confirmed; this is the
      thumbnail path only.

## Missing features (verified absent in v0.0.12)

- [ ] **Shaker support** — consume a beat-driven shaker track as another haptic
      channel and route it to a shaker device (audio-channel output). Pipeline:
      forgegen produces the shaker `.funscript` from the audio beat track;
      ForgePlayer plays it like any channel + adds a shaker destination in the
      device routing. First step toward body-shaker / 7.1 audio-channel haptics.
- [x] **In-app About page** — version, credits, and upstream attribution
      (mpv, restim, funscript-tools), links to docs. **Shipped: About tab.**
- [x] **Auto-update check** — point at forgeplayer-releases / a release feed.
      **Shipped: checks forgeplayer.app/latest-version.json on startup +
      manual "Check for updates" on the About tab (2026-08-20).**
- [ ] **Apply algorithm / haptic-offset change without relaunch** — both are
      captured at launch today. (Natural fit with the Settings/Preferences tab
      split.)
- [ ] **Loop mode** — loop a single file or all slots.
- [ ] **Keyboard shortcuts** — Space = play/pause, Left/Right = skip ±5 s,
      arrow-key Prev/Next chapter, and arrow-key navigation across Library
      tiles. **Partially shipped**: Space (play/pause), F11 (fullscreen), and
      Escape (leave fullscreen / raise the console — 2026-08-29; it used to
      close every player) already work on the player window. Left/Right skip,
      chapter-key nav, and Library arrow-key nav are still open.
- [ ] **Remember control-window size / position** between sessions.
- [ ] **Per-player window title bar showing filename** — the control window has
      a now-playing header (v0.0.11); the individual player windows still don't
      title themselves.
- [ ] **Library active-picks summary strip** above the grid (funscript set /
      video variant / stim audio) — only visible inside the picker today.
- [ ] **Script libraries** — load scripts that aren't sitting next to the video
      file.
- [x] **Third monitor** — the v0.0.1 spec calls for up to three synced outputs.
      **Shipped**: a third mirror slot ("Video 3") is available once a third
      playback screen is configured.
- [ ] **Main-funscript heatmap** (range + heat visualization).
- [ ] **Full `event.yml` integration** in playback — only the bundle importer
      reads events now; nothing surfaces them in the player.
- [ ] **In-app mpv.dll download helper** — only matters for dev-from-source;
      shipped builds bundle libmpv-2.dll. Low priority.
- [ ] **Right-click ⚑ Mark with inline note** — label a debug mark ("loud
      click", etc.) so 40-mark sessions are searchable.

## Research / deferred (v1+)

- [ ] **`alpha-prostate` fallback research** — is a scene's main funscript ever
      the prostate signal? If so, add a Haptic-2 fallback tier (use main
      funscript as prostate when no `alpha-prostate` present).
- [ ] **Single-decoder video wall** (frame-perfect sync) + multi-player **drift
      correction** for long content across mpv instances.
- [ ] **Multi-funscript layering** (primary + accent track per slot).
- [ ] **Serial / USB haptic devices** — connect per slot, real-time funscript →
      device command, per-device calibration, auto-detect.
- [ ] **7.1 audio-channel haptics** — route waveforms to individual sound-card
      channels; per-channel slot assignment; daisy-chain multiple cards. (Shaker
      support above is the entry point.)
- [ ] **`.tact` (bHaptics vest) source**, **TCode mechanical source**,
      **live-capture source** (WASAPI loopback / BlackHole), and a **pluggable
      source registry** once 4+ source kinds exist.
- [ ] **Mechanical**: fill script gaps via random / pattern / custom-curve motion
      providers; vibe-device support.
- [ ] Live audio→haptic mode; network LAN sync; playlist mode.
