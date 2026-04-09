#!/usr/bin/env python3
"""Crop Chrome screenshot to green ASCII bounds; paste centered on 920×N #050505 canvas."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def is_banner_green(r: int, g: int, b: int) -> bool:
    return g > 30 and g > r + 8 and g > b + 8


def bbox_green(im: Image.Image) -> tuple[int, int, int, int] | None:
    w, h = im.size
    min_x, min_y = w, h
    max_x, max_y = 0, 0
    found = False
    px = im.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y][:3]
            if is_banner_green(r, g, b):
                found = True
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if not found:
        return None
    return (min_x, min_y, max_x + 1, max_y + 1)


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: crop_readme_banner.py <screenshot.png> <out.png>", file=sys.stderr)
        sys.exit(2)
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    im = Image.open(src).convert("RGB")
    box = bbox_green(im)
    if box is None:
        print("crop_readme_banner: no green pixels found", file=sys.stderr)
        sys.exit(1)
    min_x, min_y, max_x, max_y = box
    margin_y = 10
    margin_x = 8
    crop = im.crop(
        (
            max(0, min_x - margin_x),
            max(0, min_y - margin_y),
            min(im.width, max_x + margin_x),
            min(im.height, max_y + margin_y),
        )
    )
    cw, ch = crop.size
    target_w = 920
    pad_top = 12
    pad_bottom = 14
    target_h = ch + pad_top + pad_bottom
    canvas = Image.new("RGB", (target_w, target_h), (5, 5, 5))
    paste_x = (target_w - cw) // 2
    canvas.paste(crop, (paste_x, pad_top))
    canvas.save(out, "PNG", optimize=True)
    print(f"Wrote {out} ({target_w}x{target_h}) from crop {cw}x{ch}")


if __name__ == "__main__":
    main()
