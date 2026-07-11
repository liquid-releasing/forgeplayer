# Setup

## Audio device roles

Three dropdowns:

- **Scene Audio** — the video's audio.
- **Haptic 1** — main stim port.
- **Haptic 2** — prostate / second stim port (optional).

Dropdowns list every audio output Windows reports through mpv. If a
dongle isn't there, plug it in. ForgePlayer doesn't open these for
exclusive mode automatically; only stim streams (H1 / H2) attempt
exclusive on launch.

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
