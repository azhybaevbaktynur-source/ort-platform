"""Image validation and re-encoding (P2-4, P2-5): always output a metadata-free WebP."""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps

from app.core.config import settings
from app.services.image_validation import validate_image_bytes


@dataclass
class EncodedImage:
    source_sha256: str
    sha256: str
    data: bytes
    width: int
    height: int
    source_bytes: int


def _is_lossless_source(fmt: str, raw: bytes) -> bool:
    if fmt in ("PNG", "GIF"):
        return True
    if fmt == "WEBP":
        return b"VP8L" in raw[12:64]
    return False


def encode_image(raw: bytes, *, max_bytes: int) -> EncodedImage:
    """Validate by content and re-encode to WebP.

    Raises ValueError with one of: "too_large", "too_many_pixels", "too_large_after_encode",
    "invalid_image"."""
    if not raw:
        raise ValueError("invalid_image")
    if len(raw) > max_bytes:
        raise ValueError("too_large")
    # Pixel count from the header, before anything is decoded.
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            w0, h0 = probe.size
    except Image.DecompressionBombError:
        raise ValueError("too_many_pixels")
    except Exception:
        raise ValueError("invalid_image")
    if w0 * h0 > settings.ASSET_MAX_PIXELS:
        raise ValueError("too_many_pixels")
    try:
        validate_image_bytes(raw, max_bytes)  # format allowlist by content (rejects SVG, BMP, ...)
    except ValueError as e:
        raise ValueError("too_many_pixels" if "dimensions" in str(e) else "invalid_image")
    try:
        with Image.open(io.BytesIO(raw)) as img:
            fmt = img.format or ""
            img.seek(0)  # first frame only (GIF / animated WebP)
            img.load()
            img = ImageOps.exif_transpose(img) or img
            has_alpha = img.mode in ("RGBA", "LA", "PA") or (
                img.mode == "P" and "transparency" in img.info
            ) or "transparency" in img.info
            img = img.convert("RGBA" if has_alpha else "RGB")
            side = settings.ASSET_MAX_SIDE
            if max(img.size) > side:
                img.thumbnail((side, side), Image.LANCZOS)
            img.info.pop("icc_profile", None)
            img.info.pop("exif", None)
            lossless = _is_lossless_source(fmt, raw)
            out = io.BytesIO()
            if lossless:
                img.save(out, "WEBP", lossless=True, quality=80, method=4)
            else:
                img.save(out, "WEBP", quality=82, method=4)
            width, height = img.size
    except Image.DecompressionBombError:
        raise ValueError("too_many_pixels")
    except ValueError:
        raise
    except Exception:
        raise ValueError("invalid_image")
    data = out.getvalue()
    if len(data) > settings.ASSET_MAX_STORED_BYTES:
        raise ValueError("too_large_after_encode")
    return EncodedImage(
        source_sha256=hashlib.sha256(raw).hexdigest(), sha256=hashlib.sha256(data).hexdigest(),
        data=data, width=width, height=height, source_bytes=len(raw),
    )
