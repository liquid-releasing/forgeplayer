# ForgePlayer — Discord announcement post

Reconciled to **v0.1.17-alpha (2026-08-30)**. Same verified claims as the
Milovana post; rewritten for Discord's constraints rather than trimmed.

**What's different about Discord, and why this reads the way it does:**

- **2000 characters per message** (4000 with Nitro). The post below is the
  short version and fits in one message — the character count is in the
  section heading, keep an eye on it if you edit.
- **Masked links don't work** in a normal user message — `[text](url)` renders
  as literal text. Only bots and webhooks get them. So every link here is a
  bare URL. (If you post it through a webhook instead, you *can* switch to
  masked links and save ~120 characters.)
- **Bare image URLs auto-embed**, so put the hero on its own line at the end and
  Discord makes a preview card out of it. Only the *first* embeds if you paste
  several on one line.
- **Headers (`#`, `##`) work** but eat vertical space in a channel. One is
  plenty for an announcement.
- The audience here is warmer than a forum — many already know FunscriptForge —
  so this leads with what's new rather than re-explaining the product.

---

## Short version — announcement channel (1 message, 1,743 chars of 2,000)

# ForgePlayer v0.1.17-alpha is out

One player driving your monitors and your e-stim from a single timeline. Point it at a scene, hit play, and video + stim stay locked together through play, pause, scrubbing and chapter jumps.

**New in this build**
- **Loop** — repeat a scene instead of stopping on the last frame. Every screen wraps together, and the jump back to the start is faded so the stim doesn't click.
- **Pickers open on the right monitor.** On a wide multi-monitor desktop a file dialog could open far from the console, and since the console greys out while a dialog is up, the app looked hung. Fixed.
- **Docs pass.** Every capability claim on the site and in the docs was checked against the code and the ones that didn't hold were corrected.

**The basics, if you're new**
- Up to 3 monitors in sync, one seek bar, per-monitor crop for ultrawides
- E-stim from a funscript (synthesised live) or pre-rendered audio — three-phase stereostim, or continuous for 312/2B boxes
- Each stim box needs its own USB audio dongle, separate from your speakers
- Opens `.forge` bundles from FunscriptForge with a double-click
- Chapter markers + chapter jumps from the console or the video window

**Alpha, honestly:** Windows is the tested platform, macOS/Linux are far less proven, Bluetooth is untested, HDR passthrough is off, and it isn't code-signed yet (SmartScreen will grumble — More info → Run anyway).

⚠️ e-stim safety: electrodes below the waist, start low, ramp up. Use **Calibrate** to set your level before you press play — and a looped scene doesn't end on its own.

Download: https://forgeplayer.app
Setup guide: https://liquid-releasing.github.io/forgeplayer/getting-started/

https://forgeplayer.app/forgeplayer_hero.png

---

## Even shorter — a #releases or #changelog one-liner (303 chars)

**ForgePlayer v0.1.17-alpha** — new **Loop** (repeat a scene, faded wrap so stim doesn't click), file pickers now open on the same monitor as the console instead of somewhere off-screen, and a full docs accuracy pass. Windows installer + portable builds for all three platforms:

https://forgeplayer.app

---

## Follow-up post, if the channel wants detail

Worth its own message a little later rather than padding the announcement —
people who care will ask, and it gives the thread a second beat:

> **How Loop actually works, for the curious**
>
> Looping is session-wide rather than per-window, because all the screens ride
> one timeline — looping one player and not the others would just desync the
> scene. So the toggle sets it for everything, and every Loop button (console
> and each video window) shows the same state.
>
> The wrap-around runs through the same ramp-down / settle / ramp-up envelope
> as a manual seek. End-to-start is the biggest discontinuity in a scene, so
> splicing it raw would pop — the fade is why it doesn't.
>
> It's off at every launch and never written to your preferences. An endless
> loop drives e-stim, and a setting you turned on last week shouldn't be able
> to arm one on a session you thought was fresh.
