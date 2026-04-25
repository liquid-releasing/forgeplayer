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

import numpy as np  # noqa: E402
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
        help="sounddevice target — pass an integer device index (best when "
             "multiple devices share the same name, e.g. WASAPI vs MME) or "
             "a name substring (e.g. 'USB Audio'). Default: system default.",
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
        "--waveform", choices=["continuous", "pulse"], default="continuous",
        help="Synthesis algorithm. continuous (default) matches FunscriptForge's "
             "MP3 renders — smooth carrier modulated by position. pulse uses "
             "discrete pulses with envelope shaping (clicky sound, FOC-content style).",
    )
    parser.add_argument(
        "--write-wav", default=None,
        help="Bake offline to a stereo 16-bit WAV file at this path instead of "
             "opening an audio device. Removes wall-clock drift and buffer-underrun "
             "variables so we can diagnose whether clicks are in the synth or in the "
             "real-time pipeline. Pairs with --duration and --start-at.",
    )
    parser.add_argument(
        "--play-wav", default=None,
        help="Skip the synth entirely and play an existing WAV file through the "
             "selected --device. Use to A/B against the synth: if a clean WAV also "
             "clicks, the issue is in the device / driver / portaudio layer. "
             "If clean, the synth's real-time generation has a bug.",
    )
    parser.add_argument(
        "--block-size", type=int, default=512,
        help="Sounddevice callback block size in frames. Default 512 (~11.6ms at "
             "44100). Windows + USB audio is often happier at 1024-4096; pass 0 to "
             "let PortAudio choose.",
    )
    parser.add_argument(
        "--record-output", default=None,
        help="In addition to playing live, write every audio chunk we hand to "
             "sounddevice to a WAV at this path. Captures real-time-only artifacts "
             "(GC pauses, scheduling stalls) that the offline bake doesn't see.",
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

    if args.play_wav:
        return _play_wav(args.play_wav, args.device, args.block_size)

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
    synth = StimSynth(channels=channels, media_sync=media_sync, waveform=args.waveform)
    print(f"  algorithm: {synth.waveform}")

    # Offline bake mode — short-circuit the real-time path entirely.
    if args.write_wav:
        return _bake_to_wav(
            synth=synth,
            output_path=args.write_wav,
            start_at_s=args.start_at,
            duration_s=args.duration,
        )

    # Drive media-time from the synth's own sample count, not wall clock.
    # If the audio thread stalls, _sample_count stops advancing — so the
    # funscript axes interpolate at audio-rate timestamps regardless of
    # wall-clock drift. Wall-clock drift was producing audible clicks
    # because every callback re-sampled the funscript at a jumpy `t`,
    # creating step changes in alpha/beta/volume/frequency.
    #
    # Production (with video) will use `engine.player_time(0)` — the
    # video's mpv time-pos — instead, so stim follows the video clock.
    start_offset = float(args.start_at)
    from app.stim_synth import SAMPLE_RATE  # noqa: PLC0415
    time_source = lambda: start_offset + synth._sample_count / SAMPLE_RATE  # noqa: E731,SLF001

    # Override block size before constructing the stream so we can dial
    # in Windows-friendly sizes from the CLI without editing the module.
    StimAudioStream.BLOCK_SIZE = args.block_size

    # Optional: capture every chunk we hand to sounddevice. We monkey-patch
    # the synth's `generate_block` so the recording sees exactly the bytes
    # the audio thread sends to the OS — same artifacts and all.
    recorded_chunks: list[np.ndarray] = []
    if args.record_output:
        original_generate_block = synth.generate_block

        def recording_generate_block(n_frames: int, media_time_s: float):
            block = original_generate_block(n_frames, media_time_s)
            recorded_chunks.append(block.copy())
            return block

        synth.generate_block = recording_generate_block  # type: ignore[method-assign]

    stream = StimAudioStream(
        synth=synth,
        time_source=time_source,
        device_id=None,
    )
    # Override the resolved name with whatever the user passed.
    # sounddevice accepts the `device` argument as either an integer
    # index or a name substring — the script accepts both. A purely-
    # numeric --device gets coerced to int; otherwise treated as a name.
    device_arg: int | str | None = args.device
    if isinstance(device_arg, str) and device_arg.lstrip("-").isdigit():
        device_arg = int(device_arg)
    stream._device_name = device_arg  # noqa: SLF001

    print(f"\nOpening audio device: {device_arg if device_arg is not None else '(system default)'}")
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

    if args.record_output and recorded_chunks:
        import wave  # noqa: PLC0415

        from app.stim_synth import SAMPLE_RATE  # noqa: PLC0415

        audio = np.concatenate(recorded_chunks, axis=0)
        audio16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
        with wave.open(args.record_output, "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(SAMPLE_RATE)
            f.writeframes(audio16.tobytes())
        print(f"Recorded {audio.shape[0] / SAMPLE_RATE:.2f}s ({len(recorded_chunks)} chunks) to {args.record_output}")

    return 0


def _bake_to_wav(synth, output_path: str, start_at_s: float, duration_s: float) -> int:
    """Bake the synth to a stereo WAV deterministically.

    Drives `media_time_s` directly from the running sample count so the
    funscript axes interpolate at exact audio-rate timestamps — no
    wall-clock involvement, no buffer pressure. Anything that clicks here
    came from the synth or the funscript content; anything that only
    clicks live came from the real-time path.
    """
    import wave

    import numpy as np

    from app.stim_synth import SAMPLE_RATE

    n_total = int(duration_s * SAMPLE_RATE)
    block_size = 4096
    chunks: list[np.ndarray] = []
    samples_done = 0

    print(f"\nBaking {duration_s:.1f}s ({n_total} samples) starting at t={start_at_s:.1f}s...")
    while samples_done < n_total:
        n = min(block_size, n_total - samples_done)
        media_t = start_at_s + samples_done / SAMPLE_RATE
        block = synth.generate_block(n, media_t)
        chunks.append(block)
        samples_done += n

    audio = np.concatenate(chunks, axis=0)
    peak = float(np.max(np.abs(audio)))
    nonzero = float(np.mean(audio != 0))

    audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)

    with wave.open(output_path, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)  # 16-bit
        f.setframerate(SAMPLE_RATE)
        f.writeframes(audio_int16.tobytes())

    print(f"  wrote: {output_path}")
    print(f"  duration: {audio.shape[0] / SAMPLE_RATE:.2f}s")
    print(f"  peak amplitude: {peak:.3f}")
    print(f"  non-zero samples: {nonzero * 100:.1f}%")
    return 0


def _play_wav(wav_path: str, device_arg, block_size: int) -> int:
    """A/B helper: stream an existing WAV through sounddevice using the same
    device + block-size code path the synth uses. If this clicks too, the
    issue is below the synth (device, driver, PortAudio).
    """
    import wave

    import numpy as np
    import sounddevice as sd

    if not Path(wav_path).is_file():
        print(f"error: not a file: {wav_path}", file=sys.stderr)
        return 1

    # Coerce a numeric --device to int (matches main path).
    if isinstance(device_arg, str) and device_arg.lstrip("-").isdigit():
        device_arg = int(device_arg)

    with wave.open(wav_path, "rb") as f:
        sr = f.getframerate()
        ch = f.getnchannels()
        sw = f.getsampwidth()
        n = f.getnframes()
        raw = f.readframes(n)

    if sw != 2:
        print(f"error: only 16-bit WAV supported, got {sw*8}-bit", file=sys.stderr)
        return 1

    pcm = np.frombuffer(raw, dtype=np.int16).reshape(-1, ch).astype(np.float32) / 32768.0
    if ch == 1:
        pcm = np.repeat(pcm, 2, axis=1)

    print(f"Loaded {n / sr:.2f}s @ {sr}Hz, {ch}ch from {wav_path}")
    print(f"Playing through device={device_arg if device_arg is not None else '(default)'}, "
          f"block_size={block_size}")

    cursor = [0]

    def callback(outdata, frames, time_info, status):  # type: ignore[no-untyped-def]
        if status:
            print(f"  status: {status}", file=sys.stderr)
        end = cursor[0] + frames
        chunk = pcm[cursor[0]:end]
        if chunk.shape[0] < frames:
            outdata[:chunk.shape[0]] = chunk
            outdata[chunk.shape[0]:] = 0
            raise sd.CallbackStop
        outdata[:] = chunk
        cursor[0] = end

    stream_kwargs = dict(
        samplerate=sr,
        channels=2,
        dtype="float32",
        device=device_arg,
        callback=callback,
    )
    if block_size:
        stream_kwargs["blocksize"] = block_size

    with sd.OutputStream(**stream_kwargs):
        try:
            sd.sleep(int(n / sr * 1000) + 200)
        except KeyboardInterrupt:
            print("\nStopped by user.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
