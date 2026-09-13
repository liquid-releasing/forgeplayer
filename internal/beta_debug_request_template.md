# Beta debug request — template

Reusable primer for asking a beta tester for a debug log. Written 2026-09-13 for
the Windows "audio plays but video is black / missing" report.

**Before sending, check two things against the build the tester will run:**

1. Is `Setup → Graphics → "Use the default graphics adapter"` in that release?
   (`git show <tag>:app/control_window.py | grep -c "Use the default graphics adapter"`)
2. Is Debug on by default in that release?
   (`git show <tag>:app/control_window.py | grep -c "_debug_toggle.setChecked"`)

As of **v0.1.19-alpha** the answers are **yes** and **NO** — the Debug
default-on fix (`88596e8`) landed after the tag. So the text below tells the
tester to tick Debug manually. **Once a release ships with `setChecked`, drop
step 2.1 and say the log is captured automatically.**

---

## Copy-paste text

Thanks for such a thorough report — testing on two machines saved us a lot of
guessing.

v0.1.19-alpha is now out, and it includes a setting that may fix this outright.
Please grab it first: https://forgeplayer.app  (Windows: ForgePlayer-Setup.exe)

STEP 1 — Try this first, it takes about 30 seconds

  1. Open ForgePlayer and go to the Setup tab
  2. In the "Monitor roles" box, scroll to the bottom, to "Graphics"
  3. Tick "Use the default graphics adapter"
  4. Go back to the Live tab and press Launch Players again

Why this might be the whole problem: ForgePlayer normally forces video onto an
NVIDIA GPU, to avoid a known crash in AMD's display driver. On some machines
that choice cannot be resolved, and when it fails the video output never starts
while the audio keeps playing — which is exactly what you are seeing. That
checkbox hands the choice back to the player.

If that fixes it, just reply and say so. No log needed, and thank you.

STEP 2 — If the picture is still black, we need a debug log

  1. On the Live tab, tick the "Debug" checkbox (top row, near the version
     number). It is OFF by default in this build, so this step matters.
  2. Load your scene and press Launch Players — let it fail the way it
     normally does.
  3. Click "Export..." next to Debug. It writes a file to:
         C:\Users\<your name>\.forgeplayer\debug-<date>.json
  4. Send us that file. If the forum will not accept .json, put it in a zip.

If the app freezes before you can click Export, there is a live log that
survives a force-quit. Press Windows+R, paste this, and press Enter:

     %USERPROFILE%\.forgeplayer

Send the newest file named debug-stream-....jsonl

ALSO HELPFUL, if you don't mind

  - Does a video window open at all, or does nothing appear? A black window
    and no window point at completely different causes for us.
  - Your graphics hardware: press Windows+R, type dxdiag, press Enter, then
    click "Save All Information..." and send that text file. The "Display"
    section is the part we need.

This one is hard for us to reproduce because it depends on how your particular
graphics hardware reports itself to Windows — so your log is genuinely the
fastest route to a real fix rather than a guess. Much appreciated.

---

## What we're looking for in the log

The decisive pair of events:

```
player.mpv_construct_begin   gpu_context=d3d11  d3d11_adapter=NVIDIA  detected_nvidia=true
player.gpu_adapter           device=Device Name: ...
```

If `mpv_construct_begin` shows a forced adapter and **no `player.gpu_adapter`
follows**, D3D11 context creation failed and video was never going to appear —
that confirms the diagnosis and the Graphics checkbox is the fix.

If `player.gpu_adapter` IS present (so the GPU resolved) and video is still
black, the cause is elsewhere — check `players.launch_slot` for `mode`
(`audio_only` means the scene had no video at all) and
`player.placement_actual` for a window placed on a screen that isn't attached.
