# Setup

## Audio device roles

**Do this before you scan a library** — the Library opens first, but a scene
can't route anything until these are assigned.

Four dropdowns:

- **Scene audio** — the video's own audio → your speakers, headphones, or a
  **monitor / TV over HDMI**.
- **Scene audio (also)** — an *optional* second port that receives the **same
  video sound**. It exists to drive a stim box that accepts a plain audio input
  when a scene has no funscript to synthesize from. Leave it unset to disable.
- **Haptic 1 (main stim)** — the main stim port → your USB stim dongle.
- **Haptic 2 (alt stim)** — an *optional* second stim port (prostate
  side-chain, or it mirrors Haptic 1). **Leave it "— not set —" if you only
  have one stim box.**

The two **Scene audio** dropdowns list every audio output Windows reports
through mpv, including HDMI / DisplayPort displays — a TV or monitor with
speakers is a perfectly good place to send scene audio, and those rows label
them `monitor / TV (HDMI)`. The **Haptic** dropdowns deliberately list only
e-stim-capable outputs; a display is never a stim box. If a dongle isn't
there, plug it in and press **Refresh devices**.

Be aware that some displays advertise an audio path and have **no speakers
wired behind it** — a manufacturer can expose HDMI audio and simply not fit
any. Software cannot tell that apart from a working output: the device
appears, Windows accepts the stream, and playback runs normally into silence.
The **Test** button below is the only way to know.

A device assigned to one role is **greyed out in the others**, so e-stim and
your scene audio can't be sent to the same port by accident.

!!! danger "E-stim leaves only by a port you assigned to a haptic role"
    A stim stream may open **only** on the device set as **Haptic 1** or
    **Haptic 2**. If neither is set, the haptic side stays **silent** — it
    does not fall back to your speakers, a monitor, or whatever Windows
    currently calls the default output. The same applies when a saved device
    stops resolving: if a Haptic row reads **"(unavailable — reselect in
    Setup)"** because the device was unplugged or renamed, that port goes
    silent rather than finding somewhere else to play.

    If a stim port is unexpectedly quiet, that is the safety rule doing its
    job. Open Setup, **reselect the device** (names can shift after a reboot
    or a USB re-plug), and press **Test**.

!!! note "Bluetooth works for scene audio; use wired for stim"
    Bluetooth outputs are selectable for every role and will play. For **scene
    audio** that's fine — A2DP's latency is roughly constant, which is what
    the offset control exists to absorb.

    For **stim**, prefer a wired / USB dongle. Bluetooth re-encodes audio with
    a lossy codec, and for stereostim that waveform *is* the drive signal, not
    merely its fidelity — so the codec is altering what you feel. Bluetooth
    latency also drifts rather than holding steady, so the offset can cancel
    the average lag but not the wander around it.

    Note that a **BT-connected stim box** such as the DG-Lab Coyote is a
    different thing again: those speak their own wireless protocol rather than
    taking an audio signal, and ForgePlayer does not drive them at all.

## Test device buttons

Each row has a **🔊 Test** button that plays a short sample through the picked
device, so you can verify the dongle is wired up before launching a scene. The
sample matches the role: the scene-audio rows get a half-second 440 Hz tone,
the haptic rows get a synthesized stim clip with a gentle volume ramp — so a
haptic test feels like real playback rather than a harsh sine into your
electrodes.

Silent? Check the dongle, the box's own hardware knob, and any OS-level
per-app mute.

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
