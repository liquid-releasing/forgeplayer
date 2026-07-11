# ForgePlayer — Beta Punch List

Reconciled against **v0.0.12** (2026-07-11). This is the current, curated
road to a confident **beta** label. `BACKLOG.md` is the older phase roadmap
(May 2026) and lists work that has since shipped (Haptic 2 dispatch, prev/next
chapter buttons, seek-bar markers, PyInstaller packaging) — use *this* file for
what's actually left.

Nothing below blocks shipping v0.0.12 (it's published). The gates are what a
first-time beta tester actually feels.

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

- [ ] **In-app About page** — version, credits, and upstream attribution
      (mpv, restim, funscript-tools), links to docs.
- [ ] **Auto-update check** — point at forgeplayer-releases / a release feed.
- [ ] **Apply algorithm / haptic-offset change without relaunch** — both are
      captured at launch today.
- [ ] **Library arrow-key navigation** across tiles.
- [ ] **Library active-picks summary strip** above the grid (funscript set /
      video variant / stim audio) — only visible inside the picker today.
- [ ] **Main-funscript heatmap** (range + heat visualization).
- [ ] **Full `event.yml` integration** in playback — only the bundle importer
      reads events now; nothing surfaces them in the player.

## Research / deferred (v1+)

- [ ] **`alpha-prostate` fallback research** — is a scene's main funscript ever
      the prostate signal? If so, add a Haptic-2 fallback tier (use main
      funscript as prostate when no `alpha-prostate` present).
- [ ] Single-decoder video wall (frame-perfect sync).
- [ ] Multi-funscript layering (primary + accent per slot).
- [ ] Live audio→haptic mode; network LAN sync; playlist mode.
