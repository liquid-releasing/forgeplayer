#!/usr/bin/env python3
"""Smoke-test the stim-audio path on real hardware.

Loads a scene's funscripts, builds a StimSynth, opens a sounddevice
output stream, and pumps audio through it with a wall-clock fake
media-time so the funscript advances naturally.

Use this to verify a USB dongle on the dev machine before wiring the
synth into the player UI. Not a unit test — runs against actual audio
hardware and only stops when you Ctrl-C or the wall clock reaches
`--duration`.

Usage:
    # Auto-discover a 1-channel pack in test_media/
    python scripts/test_stim_audio.py "test_media/Euphoria"

    # Pick a specific dongle (substring match on sounddevice device name)
    python scripts/test_stim_audio.py "test_media/Euphoria" --device "USB Audio"

    # List sounddevice output devices and exit
    python scripts/test_stim_audio.py --list

    # Test the prostate channel pack
    python scripts/test_stim_audio.py "test_media/Euphoria" --prostate
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Make project importable when run as a script
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
# libmpv DLL discovery (Windows): SyncEngine import below indirectly
# pulls in mpv.py which checks PATH
os.environ["PATH"] = str(REPO_ROOT) + os.pathsep + os.environ.get("PATH", "")

import sounddevice as sd  # noqa: E402

from app.funscript_loader import load_stim_channels  # noqa: E402
from app.library.scanner import scan_scene_folder  # noqa: E402
from app.stim_audio_output import StimAudioStream  # noqa: E402
from app.stim_synth import CallbackMediaSync, StimSynth  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scene_folder", nargs="?",
        help="Path to a scene folder containing funscripts.",
    )
    parser.add_argument(
        "--device", default=None,
        help="sounddevice device name substring (e.g. 'USB Audio'). Default: system default.",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List sounddevice output devices and exit.",
    )
    parser.add_argument(
        "--prostate", action="store_true",
        help="Load prostate channels (alpha-prostate / beta-prostate / volume-prostate).",
    )
    parser.add_argument(
        "--duration", type=float, default=20.0,
        help="Seconds to play. Ctrl-C stops earlier. (default: 20)",
    )
    parser.add_argument(
        "--start-at", type=float, default=0.0,
        help="Media time (s) to start the funscript at. Useful when probing a "
             "specific section. (default: 0)",
    )
    args = parser.parse_args()

    if args.list:
        print(f"sounddevice {sd.__version__}")
        print(f"Host APIs: {[a['name'] for a in sd.query_hostapis()]}")
        print("\nOutput devices:")
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0:
                print(f"  [{i:3d}] {d['name']:60s}  ch={d['max_output_channels']}  "
                      f"sr={d['default_samplerate']:.0f}  hostapi={d['hostapi']}")
        return 0

    if not args.scene_folder:
        parser.error("scene_folder is required (or pass --list).")

    folder = Path(args.scene_folder)
    if not folder.is_dir():
        print(f"error: not a directory: {folder}", file=sys.stderr)
        return 1

    # Pull a FunscriptSet via the existing scanner — single-set folder
    # is the common case; if the scanner finds multiple, we use the
    # first one and warn so the user knows to disambiguate.
    print(f"Scanning {folder}...")
    entry = scan_scene_folder(folder)
    if entry is None:
        print(f"error: no playable funscript set in {folder}", file=sys.stderr)
        return 1
    if len(entry.funscript_sets) == 0:
        print(f"error: no funscript sets discovered in {folder}", file=sys.stderr)
        return 1
    if len(entry.funscript_sets) > 1:
        print(f"note: multiple funscript sets present, using first ({entry.funscript_sets[0].base_stem})")
    fs = entry.funscript_sets[0]
    print(f"  base_stem: {fs.base_stem}")
    print(f"  channels:  {sorted(fs.channels.keys())}")
    print(f"  main:      {fs.main_path is not None}")

    channels = load_stim_channels(fs, prostate=args.prostate)
    if channels is None:
        suffix = "prostate" if args.prostate else "main"
        print(f"error: no playable {suffix} channels in this scene", file=sys.stderr)
        return 1
    print(f"  source:    {channels.source}")
    print(f"  pulse-based: {channels.has_pulse_params}")
    print(f"  duration:  {channels.t[-1]:.1f}s")

    # Synth + media sync. Wall-clock-driven media-time so the funscript
    # actually advances; is_playing always True for this smoke test.
    media_sync = CallbackMediaSync(lambda: True)
    synth = StimSynth(channels=channels, media_sync=media_sync)
    print(f"  algorithm: {synth.mode}")

    t0 = time.monotonic()
    start_offset = float(args.start_at)
    time_source = lambda: start_offset + (time.monotonic() - t0)  # noqa: E731

    stream = StimAudioStream(
        synth=synth,
        time_source=time_source,
        device_id=None,
    )
    # Override the resolved name so the user can pass any sounddevice
    # device-name substring directly (skipping the mpv lookup chain).
    stream._device_name = args.device  # noqa: SLF001

    print(f"\nOpening audio device: {args.device or '(system default)'}")
    print(f"Playing for up to {args.duration}s (Ctrl-C to stop early)\n")

    try:
        stream.start()
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        stream.stop()
        print("Stream closed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
