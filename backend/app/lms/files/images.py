"""Image validation and re-encoding (P2-4, P2-5): always output a metadata-free WebP."""
from __future__ import annotations

import hashlib
import io
import threading
from dataclasses import dataclass

from PIL import Image

from app.core.config import settings
from app.lms.files.image_validation import validate_image_bytes


_ENCODE_SLOT = threading.BoundedSemaphore(1)
_ORIENTATION_OPS = {
    2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180, 4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE, 6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


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
        with _ENCODE_SLOT:  # one decode/encode at a time per process (memory bound)
            with Image.open(io.BytesIO(raw)) as img:
                fmt = img.format or ""
                side = settings.ASSET_MAX_SIDE
                img.seek(0)  # first frame only (GIF / animated WebP)
                if fmt == "JPEG":
                    img.draft("RGB", (side, side))  # decode at reduced scale
                try:
                    orientation = int(img.getexif().get(0x0112, 1) or 1)
                except Exception:
                    orientation = 1
                img.load()
                has_alpha = img.mode in ("RGBA", "LA", "PA") or (
                    img.mode == "P" and "transparency" in img.info
                ) or "transparency" in img.info
                target = "RGBA" if has_alpha else "RGB"
                if img.mode != target:
                    img = img.convert(target)
                if max(img.size) > side:
                    # square box: the bound is orientation-independent; shrink before transposing
                    img.thumbnail((side, side), Image.LANCZOS, reducing_gap=3.0)
                op = _ORIENTATION_OPS.get(orientation)
                if op is not None:
                    img = img.transpose(op)
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


# --- F7a begin --- (STUDENT_UI_FIX_PLAN 7.1: course cover, centre crop to 16:9 before encoding; used only by covers)
COVER_FORMATS = ("JPEG", "PNG", "WEBP")
COVER_MAX_WIDTH, COVER_MAX_HEIGHT = 1280, 720


def cover_crop_box(width: int, height: int, focus_x: float = 0.5, focus_y: float = 0.5) -> tuple[int, int, int, int]:
    """The largest exact 16:9 box (a multiple of 16 x 9) inside width x height, placed by the focus (0..1 on each
    axis; 0.5 = centre). Raises ValueError("invalid_image") for an image smaller than 16 x 9."""
    units = min(width // 16, height // 9)
    if units < 1:
        raise ValueError("invalid_image")
    cw, ch = units * 16, units * 9
    fx, fy = min(max(float(focus_x), 0.0), 1.0), min(max(float(focus_y), 0.0), 1.0)
    left, top = round((width - cw) * fx), round((height - ch) * fy)
    return left, top, left + cw, top + ch


def encode_cover(raw: bytes, *, max_bytes: int, focus_x: float = 0.5, focus_y: float = 0.5) -> EncodedImage:
    """A JPEG, PNG or WebP upload, oriented, cropped to 16:9 around the focus, scaled down to at most 1280 x 720 and
    re-encoded as a lossy, metadata-free WebP.

    Raises ValueError with one of: "unsupported_type" (not a JPEG, PNG or WebP image), "too_large", "too_many_pixels",
    "too_large_after_encode", "invalid_image"."""
    if not raw:
        raise ValueError("invalid_image")
    if len(raw) > max_bytes:
        raise ValueError("too_large")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt0, (w0, h0) = probe.format or "", probe.size
    except Image.DecompressionBombError:
        raise ValueError("too_many_pixels")
    except Exception:
        raise ValueError("unsupported_type")
    if fmt0 not in COVER_FORMATS:
        raise ValueError("unsupported_type")
    if w0 * h0 > settings.ASSET_MAX_PIXELS:
        raise ValueError("too_many_pixels")
    try:
        validate_image_bytes(raw, max_bytes)
    except ValueError as e:
        raise ValueError("too_many_pixels" if "dimensions" in str(e) else "invalid_image")
    try:
        with _ENCODE_SLOT:  # one decode/encode at a time per process (memory bound)
            with Image.open(io.BytesIO(raw)) as img:
                img.seek(0)  # first frame only (animated WebP)
                if img.format == "JPEG":
                    img.draft("RGB", (COVER_MAX_WIDTH, COVER_MAX_WIDTH))  # never below the box on either axis
                try:
                    orientation = int(img.getexif().get(0x0112, 1) or 1)
                except Exception:
                    orientation = 1
                img.load()
                has_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
                target = "RGBA" if has_alpha else "RGB"
                if img.mode != target:
                    img = img.convert(target)
                op = _ORIENTATION_OPS.get(orientation)
                if op is not None:  # orient first: the crop box is chosen on the image as the viewer sees it
                    img = img.transpose(op)
                img = img.crop(cover_crop_box(img.width, img.height, focus_x, focus_y))
                if img.width > COVER_MAX_WIDTH:
                    img = img.resize((COVER_MAX_WIDTH, COVER_MAX_HEIGHT), Image.LANCZOS, reducing_gap=3.0)
                img.info.pop("icc_profile", None)
                img.info.pop("exif", None)
                out = io.BytesIO()
                img.save(out, "WEBP", quality=82, method=4)  # always lossy: a photo cover stays ~100-200 kB
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
# --- F7a end ---
