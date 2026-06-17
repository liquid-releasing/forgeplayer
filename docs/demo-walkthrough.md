# ForgePlayer demo — run-of-show & narration script

A ~4–6 minute walkthrough that shows what ForgePlayer is for: **one synced
player that drives many screens and e-stim/haptic outputs from a single scene
folder.** Demo content is **Big Buck Bunny** (royalty-free, safe to publish).

---

## How to capture this (read first)

**Playwright is the wrong tool.** Playwright drives web browsers through the
DOM. ForgePlayer is a native PySide6/Qt + libmpv desktop app — no HTML, no DOM,
and the video is libmpv painting onto native window handles that a browser
automation tool can't see. There's no "run it as HTML" shortcut short of
rebuilding the whole UI as a web app.

**Recommended capture: live screen recording + system-audio loopback.**

- **Video:** OBS Studio. Add a *Display Capture* (or *Window Capture* per
  player window if you want clean framing of each monitor).
- **Audio:** OBS *Application Audio Capture* on ForgePlayer, **or** a system
  loopback (Windows "Stereo Mix" / VB-CABLE) so BOTH the scene audio AND the
  e-stim carrier are recorded. The e-stim signal is just audio on the haptic
  output device — route that device into the capture so the audience can *hear*
  the carrier even though they can't feel it.
- **Narration:** either talk live from the script below, or record the app
  silent and lay a **TTS voiceover** over it afterward (same pattern as the
  FunscriptForge demofoundry tours). The right-hand "SAY" column is written to
  be read aloud as-is.

**On the audio hardware (call this out on camera):** to play e-stim you need
**one or two audio outputs beyond your speakers** — typically a small USB audio
dongle (or two) for Haptic 1 / Haptic 2, or a USB-C→3.5mm adapter feeding the
stim box. Scene sound goes to your speakers/headphones; each haptic stream goes
to its own output. That's the whole hardware story.

> If you ever want a *hands-free, repeatable* capture (e.g., for re-recording in
> other languages), the Qt-native option is `pywinauto` (Windows UI Automation)
> to click through the app on a timer — but for a one-off marketing demo, you
> driving it live is faster and looks more natural.

### Pacing & pauses

Each section ends with a **⏸ PAUSE** beat. These do two jobs: they give the
TTS/voiceover a breath between topics, and they cover the moment the UI is
switching tabs or windows are appearing (so narration never talks over a blank
transition). If you're generating the voiceover as separate clips, render each
section as its own clip and insert the pause as silence between them; if it's
one continuous read, just hold for the marked beats.

- **⏸ PAUSE ~1.5s** — between steps inside the same tab.
- **⏸ PAUSE ~2.5s** — when switching tabs or launching windows (the longer beat
  covers the UI settling: the Library scan, players appearing on the monitors).

---

## Cold open (0:00–0:20)

| ON SCREEN | SAY |
|---|---|
| ForgePlayer launches. Empty Library with the "Welcome to ForgePlayer" panel. | "This is ForgePlayer. If you've ever tried to play a scene across two monitors and an e-stim box by juggling VLC windows and hoping they stay in sync — this is the fix. One scene folder, one play button, every screen and every haptic output locked together frame-for-frame." |

> **⏸ PAUSE ~2.5s** — let the opening line land before you start clicking.

---

## 1 · Add a folder → the Library (0:20–1:00)

| ON SCREEN | SAY |
|---|---|
| Click **"Choose folder"** (or the root picker). Select the folder containing **Big Buck Bunny**. | "I point it at a folder of my scenes…" |
| Library grid fills with cards. **Thumbnails** render in as the frames are grabbed. Device badges show on the card. | "…and it scans them into a library. Each card pulls a real frame from the video, and the little badges tell me which device families that scene already has scripts for — e-stim, Handy, OSR2, SR6." |
| Hover/tap the Big Buck Bunny card. | "Everything about a scene — the video, the audio, the funscripts for every channel — travels together as one card." |

> **⏸ PAUSE ~2.5s** — switch to the **Setup** tab; let it open before the next line.

---

## 2 · Setup → screens & crop (1:00–2:00)

| ON SCREEN | SAY |
|---|---|
| Open the **Setup** tab → **Monitor roles**. | "First-time setup, done once. Setup is where I tell ForgePlayer about my rig." |
| Under **Playback screens**, check the monitors to play on. Leave the laptop unchecked so it stays free for the controls (set **Control panel screen** to the laptop). | "I pick which monitors are for playback — here, my two external screens — and keep the controls on my laptop. One decoder, several screens, all in sync." |
| Tick **Crop** on the ultrawide screen. | "My middle screen is an ultrawide. Instead of black bars, I turn on **Crop** — it scales the video to fill the monitor's aspect." |
| Show the **Crop position** radios: **Top / Center / Bottom**. Pick one. | "And I choose where the crop sits — keep the top of the frame, the center, or the bottom, each with a small margin so nobody gets sliced off at the edge. Center's the default." |

> **⏸ PAUSE ~1.5s** — stay in Setup; move across to the **Audio device roles** column.

---

## 3 · Setup → audio device roles (2:00–2:50)

| ON SCREEN | SAY |
|---|---|
| Still in **Setup**, the **Audio device roles** column. | "Now the outputs. This is the part that replaces the device-picker dance." |
| **Scene audio** → pick speakers/headphones. Hit its **Test** button (hear the tone). | "Scene audio — the video's own sound — goes to my speakers. I can Test any output right here to confirm it's alive." |
| **Haptic 1 (main stim)** → pick the USB stim dongle. Press **Test** (the gentle stim sample plays). | "Haptic 1 is my main e-stim output — the USB dongle. Test plays a short, gentle stim sample so I know the signal's reaching the box before I ever start a scene." |
| **Haptic 2 (alt stim)** → optional second dongle. | "Haptic 2 is an optional second stim output — a prostate channel, or a second device." |
| Point at **Refresh devices**. | "Plugged something in after launch? Refresh devices re-scans — no restart." |

> **⏸ PAUSE ~2.5s** — switch to the **Preferences** tab.

---

## 4 · Preferences → synthesis algorithm (2:50–3:30)

| ON SCREEN | SAY |
|---|---|
| Open **Preferences** → **Audio synthesis** → **Generation algorithm**. | "One choice matters for how the stim *feels*: the generation algorithm." |
| Show **Continuous** vs **Pulse-based** (Pulse-based is selected by default). | "**Continuous** is the classic waveform — pick it for a 312 or a 2B. **Pulse-based** is power-efficient and slower to numb — it's built for modern audio-based stereostim like the Tingler or EstimHero, and it's ForgePlayer's default. Two clicks, set once." |
| (Optional) nudge **Haptic offset**. | "If your dongle or electrode placement runs a hair ahead or behind the video, this offset nudges the stim into sync." |

> **⏸ PAUSE ~2.5s** — switch to the **Live** panel.

---

## 5 · Go Live → calibrate & launch (3:30–4:40)

| ON SCREEN | SAY |
|---|---|
| Switch to the **Live** panel. The **Video** panel shows the loaded scene + the monitors it'll use. | "Setup's done — now we go Live. ForgePlayer already knows my screens and outputs, so Live stays clean." |
| Use the **Calibrate** button(s) for Haptic 1 / Haptic 2. | "Before I launch, I calibrate each haptic output — a quick level check so the stim arrives at a comfortable strength, not a surprise." |
| Toggle **Fullscreen players** on. | "Fullscreen players takes each window edge-to-edge on its monitor — kiosk mode. And it's live: I can flip it while playing." |
| Click **Launch**. Player windows appear on the chosen monitors. | "Launch." |

> **⏸ PAUSE ~3s** — hold while the player windows open on the monitors; don't talk over the launch.

---

## 6 · Play (4:40–5:30)

| ON SCREEN | SAY |
|---|---|
| Press **Play**. Big Buck Bunny plays across both screens, the ultrawide cropped to fill, in sync. | "And there it is — one scene, every screen, in lockstep." |
| Scrub the seek bar; hit **next/previous chapter**. All windows track together. | "Seek anywhere, jump chapters — every window and every output stays frame-accurate. No resync, no drift." |
| (If audible) bring up the e-stim carrier in the capture. | "And on the haptic outputs, the stim carrier is running right alongside the picture — the same scene driving what you see and what you'd feel." |

> **⏸ PAUSE ~3s** — let the synced playback (and the carrier) play clean before the closing line.

---

## Close (5:30–6:00)

| ON SCREEN | SAY |
|---|---|
| Pull back to the Library grid. | "That's ForgePlayer. Point it at a folder, set up your screens and outputs once, and every scene plays everywhere at once — video, sound, and e-stim, perfectly in sync. One player for the whole rig." |

---

## Asset checklist

- [ ] Big Buck Bunny in a clean demo folder (ideally with at least one funscript
      channel so the device badges light up).
- [ ] 1–2 USB audio outputs (or adapters) connected and named recognizably.
- [ ] At least one extra monitor; an ultrawide makes the Crop story land.
- [ ] OBS scene: display/window capture + application-or-loopback audio.
- [ ] (Optional) TTS voiceover from the SAY column if not narrating live.
