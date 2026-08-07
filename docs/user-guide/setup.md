# Setup

## Audio device roles

Three dropdowns:

- **Scene Audio** — the video's own audio → your speakers / headphones.
- **Haptic 1** — the main stim port → your USB stim dongle.
- **Haptic 2** — an *optional* second stim port (prostate side-chain, or it
  mirrors Haptic 1). **Leave it "— not set —" if you only have one stim box.**

Dropdowns list every audio output Windows reports through mpv. If a dongle
isn't there, plug it in and press **Refresh devices**.

!!! danger "E-stim never plays through your speakers"
    A stim port only outputs to a device that resolves. If a Haptic device
    reads **"(unavailable — reselect in Setup)"** — the saved device was
    unplugged or its name changed — that port stays **silent** rather than
    falling back to the default output. ForgePlayer will not route the raw
    e-stim waveform to your speakers. If a stim port is unexpectedly silent,
    open Setup and **reselect the device** (its name may have shifted after a
    reboot or a USB re-plug).

!!! note "Bluetooth audio is untested"
    The tested path is **wired / USB** audio outputs. Bluetooth audio devices
    (BT headphones/speakers for scene audio, or a BT-connected stim box)
    **haven't been tested** — expect added latency and possible dropouts. Use
    a USB dongle for stim.

## Test device buttons

Each row has a **Test** button that routes a brief tone to the picked
device so you can verify the dongle is wired up before launching a
scene. (Stim test routes to the haptic device; scene-audio test plays
through the scene-audio device.)

## Monitors

For each player slot, pick which monitor it lands on. The dropdown
auto-populates with whatever Qt enumerates. Helpful labels include
the model name where the monitor reports it.

## Crop (per monitor)

Under **Monitor roles**, each playback screen has a **Crop** checkbox. Off
→ the video is letterboxed/pillarboxed to preserve its native aspect. On →
the video is scaled up to fill that monitor's aspect (mpv panscan) — useful
for 16:9 content on a 32:9 ultrawide instead of leaving black bars.

(This is distinct from the [Live tab's](live.md#fullscreen) **Fullscreen
players** toggle, which controls whether the *window* takes over the whole
monitor.)

## Crop position

When a screen is cropping, the **Crop position** radios choose which part of
the frame to keep in the cropped dimension:

- **Center** (default) — keep the middle, trim equally top and bottom.
- **Top** — keep the top of the frame (with about a ⅛ margin so a subject
  near the top edge isn't sliced off).
- **Bottom** — keep the bottom of the frame (same ⅛ margin off the bottom).

One choice applies to every cropping screen, and it applies **live** to any
open players whose monitor is cropping.
