import io

import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image

from app.core.config import settings
from app.main import app
from app.services.image_validation import validate_image_bytes

HEADERS = {"Authorization": "Bearer mock_instructor_token"}


def make_image(fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 10, 10)).save(buf, format=fmt)
    return buf.getvalue()


async def post(name: str, data: bytes, ctype: str = "image/png"):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/v1/upload", headers=HEADERS, files={"file": (name, io.BytesIO(data), ctype)})


@pytest.mark.parametrize("fmt,ext", [("PNG", ".png"), ("JPEG", ".jpg"), ("WEBP", ".webp"), ("GIF", ".gif")])
async def test_valid_images_accepted_with_detected_extension(fmt, ext):
    # Client filename deliberately lies about the format.
    res = await post("whatever.bin", make_image(fmt))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["filename"].endswith(ext)
    assert body["url"].endswith(ext)


@pytest.mark.parametrize("name,data,ctype", [
    ("a.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/svg+xml"),
    ("a.png", b"MZ\x90\x00" + b"\x00" * 200, "image/png"),
    ("a.png", b"<html><script>alert(1)</script></html>", "image/png"),
    ("a.png", b"just some text", "text/plain"),
    ("a.png", make_image("PNG")[:40], "image/png"),
])
async def test_non_images_rejected(name, data, ctype):
    res = await post(name, data, ctype)
    assert res.status_code == 400, res.text


async def test_oversize_returns_413(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 100)
    res = await post("big.png", make_image("PNG") + b"\x00" * 500)
    assert res.status_code == 413


def test_validate_image_bytes_unit():
    assert validate_image_bytes(make_image("PNG"), 10_000) == "png"
    assert validate_image_bytes(make_image("JPEG"), 10_000) == "jpg"
    with pytest.raises(ValueError):
        validate_image_bytes(b"", 10)
    with pytest.raises(ValueError):
        validate_image_bytes(make_image("PNG"), 10)
    with pytest.raises(ValueError):
        validate_image_bytes(b"MZ" + b"\x00" * 50, 1000)
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="BMP")
    with pytest.raises(ValueError):
        validate_image_bytes(buf.getvalue(), 10_000)
