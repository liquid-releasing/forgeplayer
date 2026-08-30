# ForgePlayer — Milovana release announcement (alpha)

Draft post for announcing ForgePlayer on Milovana. Plain, readable prose so it
pastes cleanly into a forum post (Milovana renders BBCode, not Markdown — the
headings/bullets below are just for your editing; the ready-to-paste version is
`milovana-announcement.bbcode.txt` next to this file).

> **Reconciled to v0.1.17-alpha (2026-08-30).** Every capability claim below was
> checked against the shipped code. Two things to keep an eye on when you edit:
> the post says **alpha**, matching what the app and the download page say — it
> used to say "beta", which would have had people downloading something labelled
> differently from what they'd just read about. And ForgePlayer drives **e-stim**;
> it does not drive strokers or other mechanical toys, so don't let "haptics"
> drift into implying it does.

> **Images:** all three are live and launch-ready —
> `https://forgeplayer.app/forgeplayer_hero.png`,
> `…/forgeplayer-setup.png`, `…/forgeplayer-play.png` (all verified 200).
> For more in-app shots, drop files into the `forgeplayer-web` repo (e.g. a
> `screenshots/` folder) so Cloudflare serves them at
> `https://forgeplayer.app/screenshots/<name>.png`. A Live tab with a scene
> loaded across two monitors is still the money shot.

---

## Title

**ForgePlayer (alpha) — one player, every screen and your e‑stim, all in sync**

## Post body

Ever tried to watch a scene across two screens while an e‑stim track plays — and
spent the whole time fighting windows that drift out of sync? ForgePlayer is the
fix. It's a free desktop player that drives **your monitors and your e‑stim
hardware from one timeline**. One seek bar. Everything stays locked together —
through play, pause, scrubbing, and chapter jumps.

You point it at a scene, hit play, and:

- **Video plays across up to three monitors** at once, all in sync — main screen,
  a companion angle, a second wall, however you've set it up. Each screen can
  letterbox or crop‑to‑fill (handy for ultrawides), and go fullscreen on its own
  monitor.
- **E‑stim plays right alongside the video**, driven either from a **funscript**
  (synthesised live) or from a **pre‑rendered audio file**. It supports
  **three‑phase stereostim** output for modern e‑stim hardware, plus a classic
  continuous waveform for 312 / 2B‑style boxes.
- **Each stim output needs its own audio interface or USB dongle** — separate
  from your speakers/headphones. One audio output drives your main stim; an
  optional second drives a second device (e.g. a prostate channel). So budget for
  **one or two extra audio cards / dongles** if you want e‑stim. Tested with a
  [VENTION USB External Stereo Sound Card](https://www.amazon.com/dp/B08LGPKFN5)
  (a cheap USB‑to‑3.5mm adapter) and others — any standard USB audio output
  should work.
- **Jump around by chapter.** If a scene ships chapters, they show as markers on
  the seek bar and you can step through them — from the console *or* from the
  bar on the video window itself, so you don't have to go hunting for the
  controls mid‑scene.
- **Loop a scene** when you want it to keep going instead of stopping on the last
  frame. Every screen wraps together, and the jump back to the start is faded so
  the stim doesn't click on the restart.
- It opens **`.forge` scene bundles** straight from a double‑click — the packs
  exported by **[FunscriptForge](https://funscriptforge.com)**, our companion
  authoring app — and it also reads loose funscript / audio folders.

Point the Library at a folder of scenes and it works out which video goes with
which funscripts and stim audio, gives you a thumbnail grid to pick from, and
remembers your choices per scene. When a scene has several versions — a 4K and a
1080p, alternate funscript sets — it asks once and then replays your pick.

It's built for the cockpit‑style way people actually watch: big screen in front
of you, controls on a laptop or a little touchscreen off to the side, hands free.
Fullscreen players cover the console, so there's a **Console** button on every
video window (and Escape) to bring it back without stopping playback.

**Set up once, then play** (BBCode uses
`[img]https://forgeplayer.app/forgeplayer-setup.png[/img]` and
`…/forgeplayer-play.png`):

![Setup tab](https://forgeplayer.app/forgeplayer-setup.png)
![Playing a scene](https://forgeplayer.app/forgeplayer-play.png)

### What you need (e‑stim hardware)

Each stim box plugs into **its own USB audio dongle** (separate from your
speakers). You'll want **one or two dongles + one or two stim power boxes** —
Haptic 1 carries the three‑phase / stereostim signal, Haptic 2 an optional
prostate signal.

**Three‑phase / stereostim boxes** (use the Pulse‑based mode):
[The Tingler — StimKit I](https://www.stimkits.com/) ·
[EstimHero](https://shop.impudicus.net/products/estim-hero-stereo-basic) ·
[ZC95 MKII](https://darkmatter69.com/collections/estim)

**Classic boxes** (use Continuous mode):
[MK‑312BT](https://erostek.com/products/mk-312bt-power-unit) ·
[2B](https://estim.store/collections/2b)

**Not yet supported:** Coyote (DG‑Lab) — it's Bluetooth, which isn't tested yet.
**Mechanical toys** (strokers, Handy, Keon, OSR) aren't driven either —
ForgePlayer is an e‑stim player.

### This is an alpha

ForgePlayer is **pre‑1.0 software, actively developed** — the current build is
**v0.1.17‑alpha**. It works and it's fun, but expect rough edges and please
report anything weird.

A few honest caveats up front:

- **Windows is the tested platform.** macOS and Linux builds come out of the same
  CI pipeline but are **far less proven** — try them if you like.
- **Bluetooth devices have not been tested yet.** Today's path is audio‑based
  e‑stim (a stim box fed from an audio output). BT toys are on the roadmap, not
  validated.
- **HDR passthrough is off.** HDR10 files play, but the HDR renderer crashed on
  teardown, so it uses the stable one for now — on an HDR‑ON display that can
  look over‑bright. Turn Windows HDR off for the playback monitor.
- **It isn't code‑signed yet**, so Windows SmartScreen will call it an unknown
  publisher the first time.
- e‑stim safety: **keep electrode placement below the waist, start low, and ramp
  up.** Use the in‑app Calibrate button to set a comfortable level on the box's
  own knob before you press play — and note that a looped scene doesn't end on
  its own.

### Try it

- **Download (Windows installer):** https://forgeplayer.app
  The installer registers the `.forge` file type, so you can double‑click a scene
  bundle to play it. Portable builds for Windows / macOS / Linux are linked there
  too. *(Not code‑signed yet — if SmartScreen warns, click **More info → Run
  anyway**.)*
- **All releases:** https://github.com/liquid-releasing/forgeplayer-releases/releases/latest
- **Docs / first‑time setup:** https://liquid-releasing.github.io/forgeplayer/getting-started/
- **Full user guide:** https://liquid-releasing.github.io/forgeplayer/user-guide/

Set your audio devices up first — the app opens on the Library, but nothing can
route until Setup knows which output is your speakers and which is your stim
dongle. There's a **Test** button on each one so you can prove the dongle is live
before you commit to a scene.

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
- **Chapter markers and chapter jumps**, from the console or the video window
- **Loop a scene**, with the wrap‑around faded so stim doesn't click
- Per‑monitor crop + crop position, live fullscreen
- Opens **`.forge`** bundles with a double‑click; scene library with thumbnails,
  filters and a per‑scene variant picker
- Free · Windows‑first alpha · macOS/Linux far less proven · Bluetooth untested
