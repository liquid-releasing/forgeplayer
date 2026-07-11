"""Regenerate platform icon bundles from `forgeplayer_icon.png`.

Run when the source PNG changes:

    python branding/_make_icons.py

Outputs (committed to the repo so CI builds don't need Pillow):
    branding/forgeplayer.ico     -> Windows (multi-res 16/32/48/64/128/256)
    branding/forgeplayer.icns    -> macOS    (multi-res via Pillow)

The source PNG is padded to a square 1024x1024 canvas with a transparent
border so platforms that crop hard (Windows taskbar at very small sizes)
still get the full design centered. The PyInstaller spec already
prefers .ico / .icns over the bare .png; once these files exist, the
generated binaries pick them up automatically.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
SRC = HERE / "forgeplayer_icon.png"
ICO = HERE / "forgeplayer.ico"
ICNS = HERE / "forgeplayer.icns"

# Multi-resolution Windows ICO. Including 256x256 gives Windows Explorer
# the high-res variant on the desktop / file dialogs; 16/32/48 cover
# taskbar / system tray / Start menu.
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# Pillow's .icns writer accepts a list of sizes via `sizes=`. Standard
# Apple icon set; macOS picks per surface (Dock = 128 / 256 typically,
# Finder large = 512, retina = 1024).
ICNS_SIZES = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)]


def center_square(im: Image.Image) -> Image.Image:
    """Center-crop `im` to a square on its shorter side.

    The source art is a WIDE scene (coil tower flanked by devices). Padding it
    to a square letterboxed it into a tiny squashed strip at taskbar sizes; a
    centre crop keeps the coil filling the icon. Transparency is preserved.
    """
    src = im.convert("RGBA")
    w, h = src.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return src.crop((left, top, left + side, top + side))


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"Source not found: {SRC}")

    src = Image.open(SRC)
    print(f"Source: {SRC.name} {src.size} {src.mode}")

    square = center_square(src)

    # Pillow auto-generates the multi-res variants from a single
    # input when given `sizes=`.
    square.save(ICO, format="ICO", sizes=ICO_SIZES)
    print(f"Wrote   {ICO.name}  sizes={ICO_SIZES}")

    square.save(ICNS, format="ICNS", sizes=ICNS_SIZES)
    print(f"Wrote   {ICNS.name} sizes={ICNS_SIZES}")


if __name__ == "__main__":
    main()
