# ForgePlayer — Beta Punch List

Reconciled against **v0.0.12** (2026-07-11). The curated, prioritized road to a
confident **beta** label. `BACKLOG.md` is the long-horizon idea pool (phase
roadmap); this file is what's actually left near-term, folding in the still-open
backlog items.

Nothing below blocks shipping v0.0.12 (it's published). The gates are what a
first-time beta tester actually feels. Already shipped since the old backlog:
Haptic 2 dispatch, Prev/Next chapter buttons, seek-bar markers, Calibrate,
mkdocs docs, PyInstaller packaging.

---

## Beta quality gates (do these first)

- [ ] **Code-sign the Windows installer.** Currently unsigned — that's why the
      docs walk users through the SmartScreen "Keep / Run anyway" steps. Signing
      removes that friction; biggest single beta-polish win. (macOS notarization
      is the parallel item.)
- [ ] **Verify no clicks across scene / chapter auto-advance boundaries.** The
      audio-quality work covered *within-scene* playback only; boundary
      transitions are untested and gate any playlist / auto-advance UI.
- [ ] **Hardware feel-test the actual v0.0.12 release artifact** on the
      workstation + haptic dongle (not just "sounds right" through headphones).
- [ ] **Confirm the flagged "D29 audio-only ship-blocker"** from the setup/Live
      redesign is actually resolved against the current build.
- [ ] **Residual ~7% audible click rate / hardware-side pop** — narrowed to
      device-level analog transients. Hold-on-fail; investigate only if users
      report.
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
- [ ] **Auto-update check** — point at forgeplayer-releases / a release feed.
- [ ] **Apply algorithm / haptic-offset change without relaunch** — both are
      captured at launch today. (Natural fit with the Settings/Preferences tab
      split.)
- [ ] **Loop mode** — loop a single file or all slots.
- [ ] **Keyboard shortcuts** — Space = play/pause, Left/Right = skip ±5 s,
      arrow-key Prev/Next chapter, and arrow-key navigation across Library tiles.
- [ ] **Remember control-window size / position** between sessions.
- [ ] **Per-player window title bar showing filename** — the control window has
      a now-playing header (v0.0.11); the individual player windows still don't
      title themselves.
- [ ] **Library active-picks summary strip** above the grid (funscript set /
      video variant / stim audio) — only visible inside the picker today.
- [ ] **Script libraries** — load scripts that aren't sitting next to the video
      file.
- [ ] **Third monitor** — the v0.0.1 spec calls for up to three synced outputs;
      today's build supports two.
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
