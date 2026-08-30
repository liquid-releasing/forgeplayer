# ForgePlayer — Reddit post

Reconciled to **v0.1.17-alpha (2026-08-30)**. Same verified claims as the
Milovana and Discord posts, written for how Reddit actually reads.

**Read this before posting — Reddit is the least forgiving of the three:**

- **Disclose that you made it, in the post itself.** Not a footnote. Every
  relevant subreddit has a self-promotion rule, and the reliable way to get
  removed (or downvoted into nothing) is to write an ad that doesn't say whose
  project it is. The body below opens with it.
- **Check each subreddit's rules and flair first.** Several require a
  `[OC]`/`Self-promotion`/`Tool` flair, some allow it only on set days, some
  ban links to Discord outright. There is no generic version that clears every
  ruleset — read the sidebar each time.
- **Reddit markdown does support `[text](url)`**, unlike a normal Discord
  message. Links below use it.
- **Images don't inline in a text post.** Either post a gallery/image post with
  the copy as a comment, or accept that a text post is text. Screenshots carry
  a lot here, so a gallery post is usually the better call — the hero plus the
  Setup and Play shots are hosted at `https://forgeplayer.app/…`.
- **Lead with the problem, not the product.** The forum post can open with a
  pitch; here that reads as an ad. This opens with the annoyance the thing
  exists to solve.
- **Expect "why not just use X".** The honest answer is in the FAQ block at the
  bottom — keep it ready as a comment rather than padding the post.

Candidate subreddits vary in tolerance and rules; check each sidebar rather
than cross-posting blind, and space the posts out.

---

## Title options

Pick one — the first is the safest, the second does better where the audience
is technical, the third only where self-promo is explicitly welcome.

1. **I built a free player that keeps video and e-stim on the same timeline across multiple monitors**
2. **ForgePlayer: one seek bar driving up to 3 monitors and two e-stim outputs (free, Windows-first, alpha)**
3. **[OC] ForgePlayer v0.1.17-alpha — synced multi-screen playback with e-stim routing**

---

## Body

I make a free desktop player called ForgePlayer — this is my own project, so
take the enthusiasm accordingly.

The problem it exists for: if you've ever tried to watch something across two
screens while an e-stim track plays alongside it, you've spent the session
babysitting windows that drift apart. Separate players, separate seek bars,
nothing agrees after the first scrub.

ForgePlayer runs it all off **one timeline**. One seek bar. Video across up to
three monitors and your stim outputs all stay locked together through play,
pause, scrubbing and chapter jumps.

**What it does**

- **Up to 3 monitors in sync**, each able to letterbox or crop-to-fill
  (genuinely useful on an ultrawide), each fullscreen on its own screen.
- **E-stim driven from a funscript, synthesised live** — or from a pre-rendered
  audio file if that's what your scene ships. **Three-phase stereostim** for
  modern hardware, or a classic continuous waveform for 312 / 2B-style boxes.
- **Two independent stim outputs.** Each needs its **own USB audio dongle**,
  separate from your speakers — one for your main box, an optional second for a
  prostate channel. Budget for the dongles; any standard USB audio output works.
- **Chapter markers and chapter jumps**, from the console or from the bar on the
  video window itself.
- **Loop a scene** when you want it to keep going. Every screen wraps together
  and the jump back to the start is faded, so the stim doesn't click on the
  restart.
- **Point the Library at a folder** and it works out which video goes with which
  funscripts and stim audio, thumbnails them, and remembers your picks per
  scene.
- Opens **`.forge` bundles** from [FunscriptForge](https://funscriptforge.com)
  (my companion authoring app) with a double-click, and reads loose
  funscript/audio folders too.

**What it is not**

It drives **e-stim**, not mechanical toys — no stroker, Handy, Keon or OSR
support, and none planned in the near term. Bluetooth devices (including
Coyote/DG-Lab) are untested. If you're after a toy-control app, this isn't it.

**Honest state of it**

It's **alpha** — v0.1.17-alpha, pre-1.0, actively developed.

- Windows is the tested platform. macOS and Linux build and run their tests on
  every release through CI, but they're far less proven in real use.
- HDR passthrough is currently off (the HDR renderer crashed on teardown, so it
  uses the stable one) — HDR10 files play, but turn Windows HDR off for the
  playback monitor or they'll look over-bright.
- Not code-signed yet, so SmartScreen will call it an unknown publisher the
  first time.

**Safety**, since it's e-stim: electrodes below the waist, start low, ramp up.
There's a Calibrate button to set your level on the box's own knob before you
press play — and note that a looped scene doesn't stop on its own.

**Links**

- Download and docs: [forgeplayer.app](https://forgeplayer.app)
- First-time setup: [getting started](https://liquid-releasing.github.io/forgeplayer/getting-started/)
- All releases: [GitHub](https://github.com/liquid-releasing/forgeplayer-releases/releases/latest)

Happy to answer anything, and bug reports are genuinely welcome — it's at the
stage where feedback still changes the design.

---

## Ready as a comment: "why not just use X?"

Don't put this in the post. Keep it for the reply.

> **Why not VLC/mpv plus something else for the stim?**
> You can, and people do — the sync is the part that falls apart. Two players
> have two clocks, so every scrub or pause puts them back out of step, and the
> stim drifting away from the picture is exactly what ruins it. Here one seek
> bar drives everything, and seeks are faded so the stim doesn't click as it
> jumps.
>
> **Why not restim directly?**
> ForgePlayer uses restim's synthesis (vendored) for the live funscript path —
> it's good and there was no reason to reinvent it. What's added is the video
> side: multiple screens on one timeline, routing per output, the scene library,
> and chapter navigation.
>
> **Do I need special hardware?**
> A stim box you already own, plus a **USB audio dongle per box** — the cheap
> USB-to-3.5mm kind. That's the part people miss: the stim signal needs its own
> audio output, separate from your speakers.
