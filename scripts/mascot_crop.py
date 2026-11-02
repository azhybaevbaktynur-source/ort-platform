#!/usr/bin/env python3
"""Cut docs/mascot/mascot_sheet.png into frontend/public/mascot/<pose>.webp + .png (transparent, trimmed).

The sheet is 3 poses per row, 2 rows. Only white connected to the cell's edge is background, so the kalpak, belly,
book pages and clipboard stay opaque. Needs numpy, scipy and Pillow (not backend requirements; run it by hand).
Usage: python3 scripts/mascot_crop.py
"""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ni

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "docs" / "mascot" / "mascot_sheet.png"
OUT = ROOT / "frontend" / "public" / "mascot"
XS = [0, 930, 1840, 2752]  # column gaps, read from the sheet
YS = [0, 770, 1536]
POSES = [["hello", "reading", "thinking"], ["celebrating", "working", "encouraging"]]
WHITE = 236  # every channel at or above this is "white"
EDGE_PX = 3  # outline pixels this close to the background are blended with white: un-blend them
SPECK = 25  # stray islands smaller than this (source pixels) are noise; confetti is far larger
PAD = 12  # source pixels around the trimmed character
MAX_H = 400


def cut(cell: np.ndarray) -> Image.Image:
    near = cell.min(axis=2) >= WHITE
    lab, _ = ni.label(near)
    edge_ids = set(np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])) - {0}
    bg = np.isin(lab, list(edge_ids))

    rgb = cell.astype(np.float64) / 255.0
    alpha = np.where(bg, 0.0, 1.0)
    band = ni.binary_dilation(bg, iterations=EDGE_PX) & ~bg
    band_alpha = (1.0 - rgb).max(axis=2)  # colour-to-alpha against white
    alpha[band] = band_alpha[band]
    safe = np.maximum(alpha, 1e-3)[..., None]
    fg = np.where(band[..., None], np.clip((rgb - (1.0 - safe)) / safe, 0, 1), rgb)

    solid = alpha > 0.05
    lab2, n = ni.label(solid)
    sizes = ni.sum(solid, lab2, range(1, n + 1))
    for i, size in enumerate(sizes, 1):
        if size < SPECK:
            alpha[lab2 == i] = 0.0

    ys, xs = np.where(alpha > 0.05)
    y0, y1 = max(ys.min() - PAD, 0), min(ys.max() + PAD + 1, cell.shape[0])
    x0, x1 = max(xs.min() - PAD, 0), min(xs.max() + PAD + 1, cell.shape[1])
    rgba = np.dstack([fg, alpha])[y0:y1, x0:x1]
    return Image.fromarray((rgba * 255.0 + 0.5).astype(np.uint8), "RGBA")


def resized(img: Image.Image) -> Image.Image:
    if img.height <= MAX_H:
        return img
    # premultiplied, so the white under transparent pixels does not bleed into the outline
    return img.convert("RGBa").resize((round(img.width * MAX_H / img.height), MAX_H), Image.LANCZOS).convert("RGBA")


def main() -> None:
    sheet = np.array(Image.open(SHEET).convert("RGB"))
    OUT.mkdir(parents=True, exist_ok=True)
    for r, row in enumerate(POSES):
        for c, pose in enumerate(row):
            img = resized(cut(sheet[YS[r]:YS[r + 1], XS[c]:XS[c + 1]]))
            img.save(OUT / f"{pose}.webp", quality=84, alpha_quality=90, method=6)
            img.quantize(colors=128, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(OUT / f"{pose}.png", optimize=True)
            print(pose, img.size, (OUT / f"{pose}.webp").stat().st_size, (OUT / f"{pose}.png").stat().st_size)


if __name__ == "__main__":
    main()
