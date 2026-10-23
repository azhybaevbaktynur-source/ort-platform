"""Content-based image validation (never trust file names or client content types)."""
import io

from PIL import Image

# Pillow format name -> file extension
ALLOWED_IMAGE_FORMATS = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "WEBP": "webp"}


def validate_image_bytes(data: bytes, max_bytes: int) -> str:
    """Returns the file extension (no dot) for a valid PNG/JPEG/GIF/WEBP image; raises ValueError otherwise."""
    if not data:
        raise ValueError("Empty file")
    if len(data) > max_bytes:
        raise ValueError(f"File is larger than {max_bytes} bytes")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
    except Image.DecompressionBombError:
        raise ValueError("Image dimensions are too large")
    except Exception:
        raise ValueError("File is not a valid image")
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise ValueError("Unsupported image format; allowed: PNG, JPEG, GIF, WEBP")
    return ALLOWED_IMAGE_FORMATS[fmt]
