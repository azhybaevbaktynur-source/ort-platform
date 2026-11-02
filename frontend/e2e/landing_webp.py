#!/usr/bin/env python3
"""PNG screenshots to the landing page's WebP files (Playwright cannot write WebP). System python3 with Pillow.

Usage: landing_webp.py <png dir> <output dir>. Run by frontend/e2e/landing-screens.spec.ts."""
import sys
from pathlib import Path

from PIL import Image

WIDTH = 1200
QUALITY = 78
SOFT_LIMIT = 90_000


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for png in sorted(src.glob("*.png")):
        img = Image.open(png).convert("RGB")
        if img.width != WIDTH:
            img = img.resize((WIDTH, round(img.height * WIDTH / img.width)), Image.LANCZOS)
        target = out / f"{png.stem}.webp"
        img.save(target, "WEBP", quality=QUALITY, method=6)
        size = target.stat().st_size
        print(f"{target.name}: {img.width}x{img.height}, {size} bytes{' (over the soft limit)' if size > SOFT_LIMIT else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
