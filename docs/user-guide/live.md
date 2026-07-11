# Live

## Output panel

Shows the live source → destination map for the loaded scene:

```
Scene Audio: <device>           <-- mp3 / mp4 audio of the video
  <video filename>
Haptic 1: <device>              <-- main stim port
  <funscript or .mp3 filename>
Haptic 2: <device>              <-- prostate port
  <prostate source or "(mirror H1)" or "(silent — ...)"
```

The H2 line tells you exactly what's playing there:

- `<scene-stem>-prostate.funscript` — the prostate funscript synth.
- `<scene-stem>.prostate.wav` — the pre-rendered prostate audio file.
- `(mirror H1) <stem>.funscript` or `<stem>.mp3 (mirror H1)` —
  mirrors whatever H1 is playing.
- `(silent — no device set in Setup)` — Haptic 2 unconfigured.
- `(silent — same device as Haptic 1)` — H2 set to the same device
  as H1; would conflict on the exclusive output handle.

## Timeline + scene volume

Side-by-side row above the transport buttons. **Timeline** is 75 % of
the row; **scene volume** is 25 %. Time elapsed and total duration sit
in their own small labels above the timeline; "🔊 Scene volume — 100 %"
sits above the volume slider.

The two sliders are visually distinct so you don't grab one thinking
it's the other. Volume is per-session (resets to 100 % every scene).

## Transport

`−30 s · −10 s · −5 s · ▶ Play / ⏸ Pause · +5 s · +10 s · +30 s · ■ Stop`

Plus **Calibrate H1**, **Calibrate H2** (when devices set), and a
**5 s ramp** checkbox that affects the calibration ramp-up.

## Seek behavior

Every seek runs through the same three-stage envelope to mask the
funscript-driven carrier discontinuity that would otherwise click:

1. **500 ms ramp-down** to silence
2. **mpv seek** at silence
3. **200 ms settle hold** at silence — lets mpv's decoder reach steady
   state at the new position before audio comes back
4. **500 ms ramp-up** to full output

Total perceived gap: ~1.2 s. Visible as a clean dip in the recording
waveform if you record the output.

## Fullscreen

The Video panel has a **Fullscreen players** toggle. Off → players open
as windowed 1280×720 with title bars (good for adjusting). On → players
go kiosk-mode covering the whole monitor.

The toggle is **live**: flip it while players are already open and every
open window goes fullscreen (or back to windowed) immediately — you don't
have to relaunch. New launches read the toggle's current state.

`F11` inside any player window also toggles fullscreen for that slot.

## Video playback & 4K

ForgePlayer uses GPU hardware decoding when it's available (`hwdec=auto-safe`),
falling back to the CPU for anything the GPU can't handle.

- **A GPU is not required.** Integrated graphics play 1080p and typical 4K
  fine.
- For **large / high-bitrate 4K** (e.g. AI-upscaled sources), any GPU with
  hardware video decoding — NVIDIA, AMD, or Intel — plays far more smoothly by
  offloading decode from the CPU. On CPU-only decoding, a very demanding 4K
  file can saturate the processor and stutter both the video and the haptic
  sync, so if a big 4K scene isn't smooth, that's the cause — try a machine
  with hardware decode, or play a 1080p variant of the scene.

## Calibrate

Click **Calibrate H1** (or **H2**) to send a steady carrier tone to
the haptic device. Toggle on / off. Useful for:

- Verifying the dongle is connected and powered.
- Setting your levels via the dongle's physical knob before play.
- Positioning electrodes safely (steady output you can adjust to).

The **5 s ramp** checkbox ramps the calibration carrier up over five
seconds instead of stepping in immediately — gentler on the body.

Calibration is allowed in the post-launch / pre-first-play window so
you can verify haptic levels with the player windows already up.
