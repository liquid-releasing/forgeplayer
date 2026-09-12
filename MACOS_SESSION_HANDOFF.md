# macOS session handoff — read this first

Written 2026-09-12 from a Claude Code session on the user's **Windows** machine,
for a fresh session running on the user's **Mac** ("Mac Neo", Apple Silicon,
macOS Tahoe 26). Windows-side memory does not carry over, so this file is the
context transfer. Delete it once macOS video playback is settled.

## Why you exist

**macOS video playback has never been verified to work at all.** That is the
open question. CI has published `ForgePlayer-macos.zip` on every release and the
docs walk macOS users through a Homebrew libmpv install, but if `--wid`
embedding never worked on macOS, every macOS download to date has been broken on
first Launch.

## The reported bug

A user reported *Launch Players hangs indefinitely* on **two** Macs — M3 Max
(Sequoia 15.6.1) and M1 Air (Tahoe 26.5). Black video window, "Not Responding",
**~0.4% CPU**. Reproduces across hardware and OS versions; survives a reboot.

**Read the CPU number: 0.4% is a deadlock, not a GPU stall.** The reporter
hypothesised a Vulkan/MoltenVK GPU hang (as in Godot/RPCS3). That is the wrong
layer — do not chase it.

**How the log localises it.** Their debug stream ends at `player.gpu_adapter`
and never reaches `player.fill_mode`, which `_on_launch` records the instant
`init_player` returns — so the block is *inside* `init_player`. It is also
*after* `mpv_initialize`, because `gpu_adapter` is delivered by python-mpv's
event thread, and that thread only starts once the constructor has finished
initialising. That leaves the synchronous libmpv calls after it: python-mpv's
own `mpv_version` read at the end of `__init__`, our `target-colorspace-hint`
set, and the `on_key_press` registrations.

**Root cause (architectural, not a tunable).** Upstream mpv does not properly
support `--wid` embedding on macOS with GPU rendering — it is an X11/win32
feature. The Cocoa OpenGL backend is deprecated in favour of the render API
(`vo=libmpv` + `mpv_render_context`), and the documented failure mode is
literally *"audio with a black video surface"*. mpv's Cocoa VO needs the **main
queue** to touch an NSView while the Qt main thread sits in a blocking libmpv
call. Each waits on the other, so nothing burns CPU.

## The stopgap already in `main` (UNVERIFIED)

`apply_platform_video_kwargs()` in `app/sync_engine.py` drops `wid` on darwin
and sets `force_window=yes`, so mpv owns a detached window and never needs our
main thread to hand it an NSView mid-initialisation. Costs the Qt chrome overlay
on macOS; mpv-level click bindings still work. **Nobody has run this on a Mac.**

Platform and env are function parameters so the tests run from Windows CI; see
`tests/test_platform_video_kwargs.py`. Windows path verified unchanged.

Two env overrides exist for A/B testing without a rebuild:

```
FORGEPLAYER_MACOS_EMBED=wid      # force the OLD embedding path back on
FORGEPLAYER_HWDEC=no             # rule VideoToolbox in or out
```

Four DebugLog records name the exact blocking call if it still hangs:
`player.mpv_construct_begin` → `mpv_construct_done` → `colorspace_hint_done`
→ `key_bindings_done`.

## Running from source on macOS

```bash
brew install mpv                      # provides libmpv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# REQUIRED on Apple Silicon, or `import mpv` raises OSError at startup.
# python-mpv loads libmpv through ctypes.find_library, which honours
# DYLD_FALLBACK_LIBRARY_PATH; dyld does NOT search Homebrew's /opt/homebrew/lib
# on its own. The CI macOS job exports exactly this before running pytest.
export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib:${DYLD_FALLBACK_LIBRARY_PATH:-/usr/local/lib:/usr/lib}"

python main.py
```

Worth adding that export to `~/.zshrc` so it survives new terminals. If
startup fails with `OSError` mentioning libmpv, this is why — not a code bug.

## What to do

1. Run from source with the environment above.
2. Load a scene, press **Launch Players**.
3. Expected: a **detached window that plays**. If it hangs, whichever of the
   four records above is *missing* names the blocking call.
4. **Also run the control**: `FORGEPLAYER_MACOS_EMBED=wid python main.py` should
   hang. If it does NOT, the Mac isn't reproducing the user's bug and a passing
   result means little.

## Traps — each of these already cost real time

- **libmpv ignores `~/.config/mpv/mpv.conf`.** The client API loads no config
  files by default. The reporter's Vulkan tuning there was inert, and any "try
  setting X in mpv.conf" advice to a macOS user is wrong for the same reason.
  Options must be passed as kwargs.
- **macOS 15 Sequoia removed the right-click → Open Gatekeeper bypass.** The
  block dialog offers only *Move to Trash* and *Done*. Use
  `xattr -dr com.apple.quarantine <app>`, or System Settings → Privacy &
  Security → Open Anyway. Our docs said right-click for months; now fixed.
- **`xcode-select --install` is broken on Tahoe 26.0/26.1** (fails against
  Apple's update server; fixed in 26.2+). Use the direct Command Line Tools
  `.dmg` from developer.apple.com, or update macOS.
- **Safari auto-expands downloads**, so a GitHub artifact yields `.app`
  directly rather than the `.zip` the docs promised.
- **`zip -r` on an .app follows symlinks.** Fixed to `ditto -c -k` in
  `release.yml` on 2026-09-12; builds before that have flattened Qt framework
  symlinks and are bloated (294 MB) and possibly broken. If testing a build
  older than that commit, suspect the packaging before the code.
- **Tests must never touch real mpv.** Importing it raises `OSError` (not
  `ImportError`) and constructing one segfaults headless CI — a SIGSEGV that no
  `except` can catch, so it kills the whole suite. Stub
  `SyncEngine.list_audio_devices`; see `tests/test_control_window.py`.
- **Never call `.close()` on a ControlWindow in a test** — `closeEvent` ends in
  `os._exit(0)` by design and would kill pytest.
- Manual CI builds: `gh workflow run release.yml --ref main` builds all three
  platforms and **skips publishing** (the `release` job is guarded on a tag
  ref). Artifacts attach to the run.

## Recent related work in `main`

- **v0.1.18-alpha shipped** (2026-09-05): monitor/TV HDMI outputs are selectable
  for scene audio, plus an **e-stim routing safety fix** — stim was audible
  through an HDMI monitor with no haptic device set. That fix is one membership
  rule in `_launch_stim_synth`: a stim stream may open ONLY on a device assigned
  to Haptic 1 or Haptic 2. **Do not weaken it.** A subwoofer role (planned for
  beta) must get its OWN membership set, not join the haptic one.
- Playback screens now default to the **primary monitor**, resolved by name via
  `default_playback_screen_indices()` rather than trusting index 0.
- A Windows user reported audio with no video. Suspect:
  `_detect_nvidia_adapter()` reports NVIDIA from the *display adapter* list
  whether or not the GPU is usable, and pinning `gpu_context=d3d11` also
  disables mpv's context fallback — so a failed pick means audio-only. Escape
  hatch shipped as **Setup → Graphics → "Use the default graphics adapter"**.

## Next milestone

Beta output targets due **2026-09-30**: wire FOC-Stim (`gamma` + `e1..e4`; pulse
params already work, `abc_to_e1234()` sits unused in
`app/vendor/restim_stim_math/transforms_4.py`), subwoofer/bass-shaker (no path
exists), and vibration. See `BETA_TODO.md`.
