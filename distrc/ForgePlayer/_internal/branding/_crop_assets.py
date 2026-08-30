"""One-shot: split Copilot_20260322_105624.png into icon + wordmark crops."""
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).parent
SRC = HERE / "Copilot_20260322_105624.png"


def bbox_of_content(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return (left, top, right, bottom) bounding box of True pixels, or None."""
    if not mask.any():
        return None
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    return (int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1)


def pad(box: tuple[int, int, int, int], margin: int, limit: tuple[int, int]):
    l, t, r, b = box
    w, h = limit
    return (
        max(0, l - margin),
        max(0, t - margin),
        min(w, r + margin),
        min(h, b + margin),
    )


def main() -> None:
    im = Image.open(SRC).convert("RGB")
    arr = np.array(im)
    w, h = im.size
    # Background is dark gray; content is colored/brighter. Anything whose
    # brightest channel exceeds ~75 is content.
    content_mask = np.max(arr, axis=2) > 75

    # Split horizontally at ~halfway so top (icon) and bottom (wordmark)
    # get analysed independently.
    split_y = h // 2
    top_mask = content_mask.copy()
    top_mask[split_y:, :] = False
    bot_mask = content_mask.copy()
    bot_mask[:split_y, :] = False

    icon_box = bbox_of_content(top_mask)
    wm_box = bbox_of_content(bot_mask)
    if icon_box is None or wm_box is None:
        raise RuntimeError("Failed to find icon or wordmark region.")

    # 24 px breathing room on each side, clamped to the canvas.
    icon_box = pad(icon_box, 24, (w, h))
    wm_box = pad(wm_box, 24, (w, h))

    icon_out = HERE / "forgeplayer_icon.png"
    wm_out = HERE / "forgeplayer_horizontal.png"
    Image.open(SRC).crop(icon_box).save(icon_out)
    Image.open(SRC).crop(wm_box).save(wm_out)

    print(f"icon   box={icon_box}  -> {icon_out}")
    print(f"wmark  box={wm_box}  -> {wm_out}")


if __name__ == "__main__":
    main()
