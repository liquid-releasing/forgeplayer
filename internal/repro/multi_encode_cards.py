# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
r"""Reproduce: one work at several encodes becomes several library cards.

Run it:

    .venv/Scripts/python.exe internal/repro/multi_encode_cards.py

No media and no external drive needed — only the FILENAMES matter to the
scanner, so this builds empty files in a temp folder and throws them away.
That is deliberate: the original report came from a loaner drive
(`G:\funscripts\ES`) that is not part of the repo, and a repro that needs it
would rot the moment the drive goes away.

The filenames below are copied verbatim from that folder (dogfood 2026-09-16).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.library.scanner import scan_library_root  # noqa: E402

STEM = "Everything Makes You Fckin Pump Wezzam PMV"

# Three encodes of ONE work, plus that work's scripts.
FILES = [
    f"{STEM}_4K@60_AV1.mp4",                                  # the 4K encode
    f"{STEM}_60_AV1-P4-RF35.mkv",                             # a re-encode
    f"{STEM}_4K@60_AV1_100_10_BOTH_auto_v1.7.0_LRF_Full_SBS.mp4",   # an SBS render
    f"{STEM}_4K@60_AV1.funscript",                            # the script
    f"{STEM}_4K@60_AV1.R2.funscript",                         # a revision
    f"{STEM}_4K@60_AV1_SL420.funscript",                      # stroke-length variants
    f"{STEM}_4K@60_AV1_SL480.funscript",
    f"{STEM}_4K@60_AV1_SL540.funscript",
]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="forgeplayer-repro-"))
    scene = root / "ES"
    scene.mkdir()
    for name in FILES:
        (scene / name).write_bytes(b"\x00")

    cards = scan_library_root(root)

    print(f"one folder, {len(FILES)} files -> {len(cards)} library cards\n")
    for card in cards:
        videos = [os.path.basename(v.path) for v in card.videos]
        print(f"  card: {card.name!r}")
        print(f"     videos    : {videos}")
        print(f"     funscripts: {len(card.funscript_sets)}")
    print()

    playable = [c for c in cards if c.videos and c.funscript_sets]
    silent = [c for c in cards if c.videos and not c.funscript_sets]

    print(f"cards with video AND haptics : {len(playable)}")
    print(f"cards with video, NO haptics : {len(silent)}")
    for c in silent:
        print(f"     -> {c.name!r} plays silent")

    print(f"\ntemp folder: {root}")
    # WANTED: one card, three video variants, the scripts attached to it.
    return 0 if len(cards) == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
