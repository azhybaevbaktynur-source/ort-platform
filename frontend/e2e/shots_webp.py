#!/usr/bin/env python3
"""PNG screenshots to WebP at their own width, each at most 300 KB (lower quality steps until it fits; a page taller
than WebP allows is cut at 16383 px). System python3 with Pillow (Playwright cannot write WebP).

Usage: shots_webp.py <png dir> <output dir>. Run by frontend/e2e/lesson-course.spec.ts (LC_SHOTS=1)."""
import sys
from pathlib import Path

from PIL import Image

LIMIT = 300_000
MAX_SIDE = 16_383


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for png in sorted(src.glob("*.png")):
        img = Image.open(png).convert("RGB")
        if img.height > MAX_SIDE:
            img = img.crop((0, 0, img.width, MAX_SIDE))
        target = out / f"{png.stem}.webp"
        for quality in (80, 70, 60, 50, 40):
            img.save(target, "WEBP", quality=quality, method=6)
            if target.stat().st_size <= LIMIT:
                break
        print(f"{target.name}: {img.width}x{img.height}, {target.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
