# ForgePlayer v0.0.1-alpha — user testing plan

**Target build:** main + `feature/select-picker` branch (local). Launched via `python main.py` after `source .venv/Scripts/activate`.

**How to use this doc:** work top-down. Priorities 1 and 2 are the critical path — they must pass before shipping. Priority 3 is the Library flow which is new surface. Priorities 4 and 5 are polish / robustness and can be punch-listed.

Turn **Debug ON** in the top bar at the start of each session. Hit **⚑ Mark** whenever you see something weird, add a note if you remember. **Export** at the end → attach the JSON to any bug write-up.

---

## Priority 1 — verify the fixes from this session

### ESC / X teardown

- [ ] Launch 2 slots (e.g. Slot 1 on Screen 1, Slot 2 on Screen 2) with videos loaded
- [ ] Press **ESC** while focus is on one player window — **all** players should close cleanly, neither screen frozen
- [ ] Repeat with **X button** on a windowed player's title bar — same behaviour, all close together
- [ ] After close, **Launch Players** again — should relaunch cleanly with no zombie mpv processes in Task Manager

### Windowed vs fullscreen mode

- [ ] Default launch (Fullscreen checkbox OFF) → players open as 1280×720 windows with visible title bars, centered on their chosen monitor. Desktop still visible on parts of the screen.
- [ ] Drag a windowed player by its title bar to a new position — should drag smoothly
- [ ] Resize a windowed player by its corner — video should scale, transport bar stays 48px
- [ ] Check **Fullscreen** checkbox → Launch → players cover their whole monitor (kiosk mode)
- [ ] With a player in either mode, press **F11** inside it — toggles between windowed and fullscreen for that slot only

### Debug cluster

- [ ] Toggle **Debug** ON → label turns orange
- [ ] Click some buttons (Launch, Close, Scan Folder) → counter on Mark doesn't increment yet, but events are captured
- [ ] Click **⚑ Mark** → label briefly shows "⚑ Mark (N)" with event count, then resets
- [ ] Click **Export…** → message box shows the path written; check `~/.forgeplayer/debug-<timestamp>.json` exists and contains the events

---

## Priority 2 — Live tab dogfood (sync + transport)

Use the test_media folder or any real pack from your library.

### Multi-screen sync

- [ ] Enable Slot 1 + Slot 2 with **the same video** on two different monitors → Launch → hit Play
- [ ] Scrub the seek bar mid-playback → both videos jump to the same frame, audio re-syncs
- [ ] Hit +30s / -30s buttons → both advance/rewind together
- [ ] Hit Stop → both pause and reset to 0
- [ ] Enable Slot 3 on the same monitor as Slot 1 → behaviour should still sync across all 3

### Per-slot config

- [ ] Browse Video on a slot → video loads, filename shows in the label
- [ ] Browse Audio override on a slot → playback uses that audio file instead of video's native audio
- [ ] Clear audio override (X button) → playback reverts to video's native audio
- [ ] Change Audio output dropdown to a different device → audio comes out that device after next Launch
- [ ] Volume slider — drag during playback, level changes audibly per slot

### Session management

- [ ] Save the current session (Save button) → file name defaults to session title
- [ ] Close app, reopen, load the same file (Open) → all slot configs restored
- [ ] Recent menu → session listed; click → loads

---

## Priority 3 — Library tab dogfood (new surface, mostly un-exercised)

### Scan

- [ ] Click the **Library** tab
- [ ] Click **Scan Folder…** → point at `test_media/`
- [ ] 3 scenes should appear as cards: Euphoria, Magik, ph dl (or whatever your test_media contains)
- [ ] Card fields: thumbnail placeholder, scene name, device badges

### Badges (critical — validates the scanner)

- [ ] All 3 scenes should show **m• 2b• s• foc•** (mechanical + 2b + stereostim + FOC-stim generation compatibility)
- [ ] Euphoria + Magik should additionally show **p•** (prostate channel present)
- [ ] All 3 should show the orange **pick** marker (all are ambiguous for different reasons)

### Filter chips

- [ ] Click each chip: All / Recent / Favorites / With preset / Playlists — list should filter appropriately (Recent and With preset will be empty today; All shows everything)
- [ ] Type in the search box → cards filter by name

### Select picker

- [ ] Click a scene card → picker dialog opens
- [ ] Picker title shows scene name
- [ ] Only the relevant radio groups appear (e.g. Euphoria is audio-only ambiguous; Magik has funscript + video + audio + gen-variant groups)
- [ ] If gen-variant present: yellow warning note shows
- [ ] Click **Play once** → summary dialog shows selected items, `save_as_preset=False`
- [ ] Click **Save && Play** → summary dialog shows selected items, `save_as_preset=True`
- [ ] Click **Cancel** → dialog closes, no side effects

### Known stub

- Click on a scene in Library → shows a stub summary dialog today, **does not actually play yet**. The picker → SyncEngine wire-up is the next slice. Testing this path is about the scan/badges/picker UX, not end-to-end playback from the Library.

---

## Priority 4 — robustness edges

- [ ] Rapid Launch / Close / Launch / Close cycle — no zombie processes, no memory creep after ~10 cycles
- [ ] Change a slot's video while players are running → behaviour is "Close + relaunch" (not auto-reload); confirm what happens
- [ ] Scan Folder, click Cancel → no crash
- [ ] Scan Folder at a path with no media → empty state in Library
- [ ] ESC twice quickly / X twice quickly — no double-teardown crash
- [ ] Load a `.webm` / `.mov` / `.mkv` — all should play via libmpv
- [ ] Very long filenames in Library cards — truncate with ellipsis, not overflow
- [ ] Resize the ControlWindow to a narrow width → layout doesn't break

---

## Priority 5 — known limitations, don't file as bugs

These are scoped out of v0.0.1-alpha deliberately:

- **Library → playback wire-up** (picker output doesn't actually start a session yet; stub dialog)
- **Pin persistence** — `Save && Play` captures the flag but doesn't write `{stem}.forgeplayer.json` yet
- **Setup tab** is a stub — no multi-root library, no device profile, no preferences
- **Thumbnails** — placeholder rectangles; real ffprobe-generated thumbs come later
- **Scene durations** in cards show "—:—:—"
- **Ultrawide crop / 3-wall** — deferred to v0.0.2-alpha
- **Single-decoder rewrite** — current prototype uses 3 independent mpv instances; single-decoder + GL UV shader is a later feature branch
- **Zipped funscripts** (`.funscript.zip`) — won't appear in Library yet
- **Voice commands** — parked behind v0.0.2 restim integration, no earlier than v0.0.3

---

## Session wrap-up

- [ ] **Debug → Export…** → the JSON file
- [ ] Jot down subjective notes:
  - Did sync feel tight, or did you see any frame drift?
  - Any windows that didn't feel clickable / looked wrong on first open?
  - Anything confusing about the Library card layout?
  - Badges legible at your usual viewing distance?
  - Did the picker ask for a choice you felt the player should have auto-decided?
- [ ] Drop the JSON + notes into an internal bug / feedback log
