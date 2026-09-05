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
- [x] **Hardware feel-test the actual release artifact** on the workstation +
      haptic dongle (not just "sounds right" through headphones).
      **Done 2026-08-29 against the real v0.0.16 installer** — not a dev-venv
      run, not the frozen dir, the installed build: "i used the real installer
      yesterday and am satisfied with the v0.0.16 build that we shipped."
      (Gate text previously said v0.0.12; it had been carried forward
      unchanged across four releases.)
- [ ] **Confirm the flagged "D29 audio-only ship-blocker"** from the setup/Live
      redesign is actually resolved against the current build.
- [ ] **Seek pop on sound-file stim — mostly fixed, residual to assess.**
      `4f862b4` put mpv-backed stim on the same seek envelope as the live
      synth. First dogfood (2026-08-29, headphones): "much much less and will
      be tolerable". The installed v0.0.16 build was then used on the real rig
      and judged satisfactory overall — but the seek pop was not called out
      separately, so treat this as "no longer reported", not as measured. If a residual
      remains, the next suspect is timing, not the envelope: the ramp ticks and
      the seek timer both live on the GUI thread, so a busy launch or thumbnail
      flood can let the seek fire before the ramp has actually reached zero.
      Gate the seek on `_mpv_envelope` reaching 0 (with a cap) instead of
      assuming the fixed 0.5 s elapsed. Distinguish from the device-level
      transient below before doing that work.
- [ ] **Residual ~7% audible click rate / hardware-side pop** — narrowed to
      device-level analog transients. Hold-on-fail; investigate only if users
      report.
- [x] **Native crashes during playback / thumbnail floods — ROOT-CAUSED AND
      FIXED (2026-08-29, `ffed0c7`).** Not mpv, not the GPU driver, not the
      stim math: **faulthandler was the crash.** On Windows its handler runs
      for every first-chance exception carrying the error bit, and libmpv
      raises a benign `0xe24c4a02` constantly (measured 241-295 per session).
      With `all_threads=True` each one walked the frame chain of every live
      thread — this app runs ~290 — without the GIL, while those threads kept
      freeing the frames being walked. Two out-of-process captures both
      faulted inside `_Py_DumpTraceback`/`dump_frame` themselves
      (`python313.dll+0x3a1480` and `+0x3a1a25`). Now dumps only the faulting
      thread. **Dogfooded clean** through a full thumbnail flood plus scene
      switching, on the exact shape that crashed it twice in ten minutes.
      Consequences worth knowing: the "different numpy internal every time"
      that read as a race in the vendored stim math was just whichever
      thread's frames the dump was printing when it lost — so the 2026-08-20
      rapid-chapter-click debounce may have been treating this same bug.
      Leave the debounce in place (harmless, unproven either way), but do not
      cite it as evidence about the stim math.
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
      the long demux wait. NOTE: the *crash* that accompanied this was the
      faulthandler bug above, now fixed; what remains is the 20 s-per-file
      hang and the silence about why. Still worth fixing before the tag.
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

- [ ] **Move pin files out of the user's media folders.** Every successful
      scene activation writes `<scene>.forgeplayer.json` next to the media
      (`app/library/pins.py`). They're tiny and they're real user data — the
      remembered picker choices — so they stay for now, and the Library docs
      page carries a note explaining them. The defect to fix for beta: the
      pin's *filename* comes from `entry.name`, which is relative to the
      **library root**, while its *location* is the scene folder. Repoint
      **📁 Root…** and the same scene gains a second pin under a new name
      while the old one is orphaned — unread, never cleaned. Observed on the
      dogfood rig 2026-09-05: two `funscriptforge_complete.forgeplayer.json`
      files in different folders, ten minutes apart. Consolidate into one
      app-owned folder (`~/.forgeplayer/pins/`, keyed by scene folder path)
      — `~/.forgeplayer/catalog.json` already maps folder path → last pin, so
      the index exists. Keep or drop the travels-with-the-folder property
      deliberately; that was the original reason for the sidecar.

- [x] **A native picker can open on a different monitor and the app reads as
      hung** — FIXED in v0.1.17-alpha (owner window + a re-centring backstop);
      dogfooded clean the same day: "nice placement of the dialog". Original
      report kept below for the reasoning.

      Dogfood 2026-08-30, and it cost the start of a test session.
      The native dialogs are shown **owner-less** (`Show(NULL)`;
      `ofn.hwndOwner = 0`), so Windows places them wherever it likes — on a
      5120-wide ultrawide the folder picker landed ~1900 px away from the
      console. Meanwhile `qt_modal_waiter` disables the console for the
      dialog's whole lifetime, by design. Net effect: a dead-looking app with
      no on-screen explanation. User: "the lib pick dialog was in a different
      window from the app so I missed it."
      Fix candidates, cheapest first: (a) pass the console HWND as the
      dialog owner so Windows centres it on the right monitor — the normal
      Win32 arrangement, and the original "owner-less" rationale (GUI thread
      parked in `join()`, not pumping) no longer holds now that the waiter
      runs a real `QEventLoop`; **verify it doesn't reintroduce
      "(Not Responding)"**, since cross-thread ownership attaches the two
      threads' input queues. (b) Failing that, show a "Waiting for the folder
      picker…" state on the disabled console so the app explains itself.
      Related: the same launch had a **stale library root on an unmounted
      drive** (`G:\ai`, the T5 EVO) — `control_window.py:313` correctly
      skips a root that fails `isdir`, but nothing tells the user their
      library root is gone; they just get the empty welcome screen.

- [ ] **A stale screen/root preference silently does nothing** — found while
      chasing the off-monitor picker, 2026-08-30. `control_panel_screen` was
      `2` on a machine with two screens (0 and 1), and
      `if 0 <= idx < len(self._screens)` just skips, so the console opens
      wherever Qt happens to put it with no hint that the saved monitor is
      gone. The stale `library_root` on an unmounted drive behaves the same
      way. Both should either fall back visibly (clamp to primary, say so in
      the status line) or tell the user their saved choice no longer resolves.
      Deliberately NOT changed at release time — moving where the console
      opens is not a change to make while cutting.

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
