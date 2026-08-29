# ForgePlayer — release-candidate user testing

**Build under test:** `dist\ForgePlayer\ForgePlayer.exe` — a **frozen PyInstaller
build**, made 2026-08-29 from `main` @ `72f9187`, stamped **0.0.16-dev**.
This is deliberately *not* `python main.py`: every fix since v0.0.15 has only ever
been tested through the dev venv, and BETA_TODO gate #3 is "feel-test the actual
built artifact."

**Confirm you're on the right build first:** the session bar must read
**0.0.16-dev**. If it reads 0.0.15 you're running the *installed* v0.0.15 —
close it and relaunch from `dist\ForgePlayer\ForgePlayer.exe`.

**Ground rules for the session**

- Only ONE ForgePlayer instance at a time — multiple instances silently fight
  over exclusive WASAPI handles and look exactly like an audio-routing bug.
- Turn **Debug ON** in the top bar before you start. Hit **⚑ Mark** the moment
  anything feels wrong, then keep going. **Export** at the end.
- Logs to grab for any bug: `~/.forgeplayer/debug-stream-*.jsonl`,
  `~/.forgeplayer/faulthandler.log`, and the captured stderr file (path at the
  bottom of this doc).
- In `faulthandler.log`, `Windows fatal exception: code 0xe24c4a02` is **benign
  noise**. A real crash reads `access violation` followed by `Current thread`.

Automated state going in: **420/420 tests pass**; working tree clean apart from
the local version stamp.

---

## Gate 1 — hardware feel-test of the built artifact  *(release blocker)*

The point is that the *frozen* build behaves like the dev build on real hardware.

- [ ] App opens from a cold start; **Setup** tab shows Scene Audio, Haptic 1 and
      Haptic 2 all resolved to real devices (no "(unavailable — reselect in Setup)").
- [ ] **Calibrate H1** before wiring up: steady test tone on the dongle, levels
      set at the box. Click again to stop.
- [ ] **Calibrate H2** the same way (if the second dongle is connected).
- [ ] Play a funscript-driven scene on real hardware for a few minutes.
      Does the stim feel the same as the dev build — same intensity for the same
      knob position, same rhythm, no dropouts, no stutter under video load?
- [ ] Routing is right at the body, not just on screen: scene audio in the
      headphones, stim on the dongle, **nothing** stim-like out of the speakers.
- [ ] Seek mid-scene: stim re-syncs and comes back at the same level.
- [ ] Let a scene run 10+ minutes uninterrupted. Any drift, creep in intensity, or
      memory growth (Task Manager) over that stretch?

---

## Gate 2 — D29 "audio-only" slots  *(release blocker)*

The original D29 report is lost, so the gate is now "exercise audio-only playback
thoroughly." Three shapes:

**A. Pre-rendered stim audio instead of live synth**

- [ ] **Preferences → Sound files (.wav/.mp3)**.
- [ ] Play `test_media\Mistress And Box` (three estim mp3 variants — the picker
      should let you choose which).
- [ ] Play `test_media\Magik` (`[E-Stim & Popper Edit].mp3`) and
      `test_media\CH-Jia VS Michelle` (`-estim-audio.mp3`).
- [ ] For each: H1 plays the mp3, video stays in sync, **seek keeps them locked**,
      pause/resume doesn't drift.

**B. Scene with no video at all**

- [ ] Play `test_media\Salon DeSade's JOY` and `test_media\Twisted Tales 1`
      (audio-only folders — no mp4).
- [ ] No player window opens; transport (play / pause / ±10 s / seek bar) still
      works; Close tears down cleanly with no window to close.

**C. The safety refusal**

- [ ] Still on **Sound files**, point **Haptic 1** at your *scene-audio* device
      (or clear it), then play a scene with a stim mp3.
- [ ] The app must **refuse** and say why — it must never play the raw e-stim mp3
      through the speakers. *(Take your headphones off first.)*
- [ ] Restore Haptic 1, then set **Preferences → Funscripts** back before Gate 3.

---

## Gate 3 — white-screen-after-double-click  *(release blocker)*

Seen ~3× in early dogfood, never since. This gate closes on a clean pass.

- [ ] Double-click library tiles rapidly — the same tile twice, then two different
      tiles back to back.
- [ ] Double-click the player window body while playing, while paused, while
      seeking, and right at end-of-file.
- [ ] Double-click the player title bar / the overlay bar area.
- [ ] Double-click a tile while players from a previous scene are still running.
- [ ] 20+ double-clicks across those states with no white screen → gate closed.
- [ ] If it *does* go white: ⚑ Mark it, note what was playing, and keep the stderr
      file (below) plus `faulthandler.log`.

---

## Regression pass — everything that changed since v0.0.15

**1. Close / relaunch (the AMD-driver crash class)**

- [ ] Close players via **X**, via **Escape**, via **double-click**, and via the
      **Close** button — all players close together every time.
- [ ] Relaunch after each. Do ~10 launch/close cycles.
- [ ] Task Manager: no orphaned `ForgePlayer.exe` processes left behind.
- [ ] Fullscreen sticks on the **2nd and later** launches, not just the first.

**2. Scene switching reuses players**

- [ ] With players running, click a different library scene (same monitors, same
      fullscreen state) — the windows should **not blink**; the new scene loads
      into the live windows.
- [ ] Do that 5+ times in a row. No crash, no black window left over.

**3. Haptic 2 / `.forge` bundle reporting accuracy**

Library root is `funscriptforge_complete` (Prisoner, Victoria Oaks and Katie all
have `.forge` / `.output` bundles).

- [ ] Pick a bundle-backed scene. The Output panel's **Haptic 2** wording before
      Launch and after Launch describes the same thing in the same words.
- [ ] The stim-source combo labels bundle entries **"(forge)"**, not "(funscript)".
- [ ] With players running, click a *different* scene: H2's source line updates to
      the new scene immediately — no stale text from the previous one.
- [ ] A scene with both a bundle and loose funscripts on disk uses the **bundle**.

**4. Chapter navigation + the rapid-click debounce**

- [ ] Load `test_media\chapters` (or `big buck bunny`). Seek-bar markers show.
- [ ] **Prev/Next** work from the console *and* from the buttons on the player
      window overlay, and agree on where chapters are.
- [ ] **Mash Next as fast as you can.** Extra clicks inside ~1.35 s are meant to be
      swallowed. It must not crash. *(This is the crash fixed in `5d0e897` — the
      highest-value regression check on the list.)*
- [ ] Buttons grey out correctly at the first / last chapter.

**5. Async scanning (no more "slow drive = frozen app")**

- [ ] **Setup → Root / Rescan** on a large folder: buttons disable and read
      "Scanning…", the rest of the UI stays responsive.
- [ ] Change the root again mid-scan — the older scan's results must not clobber
      the newer pick.
- [ ] Restart the app with that root saved: startup doesn't freeze.

**6. Update check**

- [ ] **About** tab → **Check for updates**. Published latest is v0.0.15 and you're
      on 0.0.16-dev, so it must say you're current — never offer a "downgrade".
- [ ] About shows version, credits and doc links.

**7. Video paths**

- [ ] `test_media\LongandCut_hdr.mp4` plays with correct brightness (Windows HDR
      off on that monitor).
- [ ] Two and three playback screens mirror in sync; ±5/10/30 s and seek move all
      of them together.

---

**8. Pickers — every selector, native chrome, no freeze** *(fixed 2026-08-29)*

`2d0dddf` moved the Live-tab **file** browse buttons onto a native STA dialog
thread, but the **folder** pickers and the session open/save dialogs were never
migrated — so they still showed Qt's old chrome (no Quick Access / Videos) and
still froze the window. All of them now route through `app/native_dialog.py`,
and the GUI thread keeps pumping while a dialog is open.

- [ ] **Library → Root**: modern Explorer dialog with **Quick Access, Videos,
      This PC and drive navigation** in the left rail.
- [ ] Click **Root** repeatedly — open and cancel five or six times in a row.
      The window never greys out and the title bar never says **Not Responding**.
- [ ] Do the same **while a scene is playing** (this is the case that used to
      hang hard enough to need a kill).
- [ ] While the folder dialog is open, the control window still repaints and
      video keeps playing; the control window ignores clicks until you close it.
- [ ] Same native chrome on: **Live → Browse** (video / audio / stim source),
      **Scan folder**, **Session → Open**, **Session → Save As**.
- [ ] Save As pre-fills the session name and appends `.forgeplayer-session`.

## Known — do **not** file these

- **Unsigned build / SmartScreen warning** — code-signing deliberately deferred.
- **No `ForgePlayer-Setup.exe` locally** — NSIS isn't installed on this machine, so
  the installer is a CI-only artifact. This pass tests the portable/frozen app.
- Residual ~7 % audible click rate (device-level analog transient).
- Control panel taller than a 1280×720 secondary monitor.
- **+10 s while stopped** jumps to 0.
- Empty Live tab has no "pick a scene" hint.
- HDR **thumbnail** renders white (player HDR itself is fine).

---

## Wrap-up

- [ ] **Debug → Export…** and keep the JSON.
- [ ] Subjective notes: did the frozen build feel any different from the dev build?
      Anything slower to start, slower to scan, or different in the stim itself?
- [ ] Report back — then the release cut is: real version bump, CHANGELOG, tag, CI
      build, forgeplayer.app badge.

**Captured stderr for this session:**
`%LOCALAPPDATA%\Temp\claude\c--Users-bruce-Projects--lqr-funscriptforge\3ac4bdb2-3aa6-46d7-9ec6-200df3f9bdda\scratchpad\forgeplayer-stderr.txt`
