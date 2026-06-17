# ForgePlayer — Milovana release announcement (beta)

Draft post for announcing ForgePlayer on Milovana. Plain, readable prose so it
pastes cleanly into a forum post (Milovana renders BBCode, not Markdown — the
headings/bullets below are just for your editing; bold the bits you want when
you paste, and drop in the screenshot where marked).

> **[ ADD SCREENSHOT HERE ]** — a shot of ForgePlayer running (Live tab with a
> scene loaded, ideally across two monitors, is the money shot).

---

## Title

**ForgePlayer (beta) — one player, every screen and your e‑stim, all in sync**

## Post body

Ever tried to watch a scene across two screens while an e‑stim track plays — and
spent the whole time fighting windows that drift out of sync? ForgePlayer is the
fix. It's a free desktop player that drives **your monitors and your e‑stim /
haptic devices from one timeline**. One seek bar. Everything stays locked
together, frame for frame.

You point it at a scene, hit play, and:

- **Video plays across up to three monitors** at once, all in sync — main screen,
  a companion angle, a second wall, however you've set it up. Each screen can
  letterbox or crop‑to‑fill (handy for ultrawides), and go fullscreen on its own
  monitor.
- **E‑stim / haptics play right alongside the video**, driven either from a
  **funscript** (synthesised live) or from a **pre‑rendered audio file**.
  It supports **three‑phase stereostim** output for modern e‑stim hardware, plus
  a classic continuous waveform for 312 / 2B‑style boxes.
- **Each stim output needs its own audio interface or USB dongle** — separate
  from your speakers/headphones. One audio output drives your main stim; an
  optional second drives a second device (e.g. a prostate channel). So budget for
  **one or two extra audio cards / dongles** if you want e‑stim. Tested with a
  [VENTION USB External Stereo Sound Card](https://www.amazon.com/dp/B08LGPKFN5)
  (a cheap USB‑to‑3.5mm adapter) and others — any standard USB audio output
  should work.
- It opens **`.forge` scene bundles** straight from a double‑click — the packs
  exported by **[FunscriptForge](https://funscriptforge.com)**, our companion
  authoring app — and it also reads loose funscript / audio folders.

It's built for the cockpit‑style way people actually watch: big screen in front
of you, controls on a laptop or a little touchscreen off to the side, hands free.

### This is a beta

ForgePlayer is **pre‑1.0 software, actively developed**. It works and it's fun,
but expect rough edges and please report anything weird.

A few honest caveats up front:

- **Windows is the tested platform.** macOS and Linux builds exist but are **not
  yet tested** — try them if you like, but they're unproven.
- **Bluetooth devices have not been tested yet.** Today's path is audio‑based
  e‑stim (a stim box fed from an audio output) and audio/haptic outputs. BT toys
  are on the roadmap, not validated.
- e‑stim safety: **keep electrode placement below the waist, start low, and ramp
  up.** Use the in‑app Calibrate button to set a comfortable level before you
  press play.

### Try it

- **Download (Windows installer):** https://forgeplayer.app
  The installer registers the `.forge` file type, so you can double‑click a scene
  bundle to play it. Portable builds for Windows / macOS / Linux are linked there
  too. *(It's not code‑signed yet, so Windows SmartScreen may say "unknown
  publisher" — click **More info → Run anyway**.)*
- **All releases:** https://github.com/liquid-releasing/forgeplayer-releases/releases/latest
- **Docs / first‑time setup:** https://liquid-releasing.github.io/forgeplayer/getting-started/
- **Full user guide:** https://liquid-releasing.github.io/forgeplayer/user-guide/

### Come say hi / report bugs

Feedback, ideas, and bug reports are very welcome — this is the stage where your
input shapes it. Join the Discord:

**https://discord.gg/MHucAwwRc**

---

## Quick feature list (for a TL;DR box, if you want one)

- Synced playback across **up to 3 monitors**, one seek bar
- E‑stim from **funscripts or pre‑rendered audio**, incl. **three‑phase stereostim**
- Continuous (312/2B) **or** pulse‑based (modern stereostim) synthesis
- Up to **two independent stim outputs** — each needs its own audio card/dongle
- Per‑monitor crop + crop position, live fullscreen
- Opens **`.forge`** bundles with a double‑click; scene library with thumbnails
- Free, Windows‑first beta · macOS/Linux untested · Bluetooth untested
