"""Upload abuse corpus: everything that is not a small real raster image must be rejected."""
import io
import struct
import zlib

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.lms.files.models import Asset, AssetBlob
from tests.lms.factories import png_bytes
from tests.lms.files_support import (  # noqa: F401
    clean_rate_limits, db, db_storage, local_storage, make_course, teacher, unique_png, upload,
)


def _chunk(tag: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)


def bomb_png(w=60000, h=60000) -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(b"\x00" * 100)) + _chunk(b"IEND", b"")


def fmt(name):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (9, 9, 9)).save(buf, name)
    return buf.getvalue()


CORPUS = {
    "exe_renamed": (b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 600, "evil.png", "image/png"),
    "svg": (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            "a.svg", "image/svg+xml"),
    "svg_as_png": (b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', "a.png", "image/png"),
    "html": (b"<html><script>alert(1)</script></html>", "a.png", "image/png"),
    "bmp": (fmt("BMP"), "a.bmp", "image/bmp"),
    "tiff": (fmt("TIFF"), "a.tiff", "image/tiff"),
    "pdf": (b"%PDF-1.4\n1 0 obj<<>>endobj\n", "a.png", "image/png"),
    "truncated_png": (png_bytes(64, 64)[:60], "t.png", "image/png"),
    "truncated_data": (png_bytes(200, 200)[:-40], "t.png", "image/png"),
    "empty": (b"", "e.png", "image/png"),
    "garbage": (bytes(range(256)) * 4, "g.jpg", "image/jpeg"),
}


@pytest.mark.parametrize("case", sorted(CORPUS))
async def test_rejected_with_400_and_nothing_stored(db, local_storage, case):
    data, name, ctype = CORPUS[case]
    t = teacher(db)
    c = make_course(db, t)
    r = await upload(t, c.id, data, filename=name, ctype=ctype)
    assert r.status_code == 400, (case, r.status_code, r.text)
    assert r.json()["error"]["code"] == "image_invalid"
    assert db.scalar(select(func.count()).select_from(Asset)) == 0
    assert not any(f for _, _, fs in __import__("os").walk(local_storage.root) for f in fs)


async def test_decompression_bomb_rejected_by_header(db, local_storage):
    t = teacher(db)
    r = await upload(t, make_course(db, t).id, bomb_png())
    assert r.status_code == 400 and r.json()["error"]["code"] == "image_too_many_pixels"


async def test_pixel_cap_applies_below_pillow_bomb_limit(db, local_storage, monkeypatch):
    monkeypatch.setattr(settings, "ASSET_MAX_PIXELS", 100)
    t = teacher(db)
    r = await upload(t, make_course(db, t).id, png_bytes(11, 10))
    assert r.status_code == 400 and r.json()["error"]["code"] == "image_too_many_pixels"
    assert (await upload(t, make_course(db, t).id, png_bytes(10, 10))).status_code == 201


async def test_oversize_body_413(db, local_storage, monkeypatch):
    monkeypatch.setattr(settings, "ASSET_MAX_UPLOAD_BYTES", 2000)
    t = teacher(db)
    c = make_course(db, t)
    big = png_bytes(2, 2) + b"\x00" * 3000  # over the cap but under cap + 64 KiB: stream counter catches it
    r = await upload(t, c.id, big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "image_too_large"
    huge = png_bytes(2, 2) + b"\x00" * (2000 + 70 * 1024)  # Content-Length precheck
    r = await upload(t, c.id, huge)
    assert r.status_code == 413
    assert db.scalar(select(func.count()).select_from(Asset)) == 0


async def test_stored_size_cap_after_encode(db, local_storage, monkeypatch):
    monkeypatch.setattr(settings, "ASSET_MAX_STORED_BYTES", 200)
    t = teacher(db)
    r = await upload(t, make_course(db, t).id, __import__("tests.lms.files_support", fromlist=["noisy_png"]).noisy_png(40, 40))
    assert r.status_code == 413 and r.json()["error"]["code"] == "image_too_large"


async def test_polyglot_trailer_is_not_stored(db, local_storage):
    marker = b"<script>alert('polyglot')</script>"
    t = teacher(db)
    data = png_bytes(16, 16) + marker
    r = await upload(t, make_course(db, t).id, data)
    assert r.status_code == 201
    from app.lms.files.storage import blob_key

    stored = local_storage.get(blob_key(r.json()["sha256"]))
    assert marker not in stored and stored[:4] == b"RIFF" and stored[8:12] == b"WEBP"


async def test_client_content_type_and_extension_are_ignored(db, local_storage):
    t = teacher(db)
    r = await upload(t, make_course(db, t).id, png_bytes(8, 8), filename="x.exe", ctype="application/x-msdownload")
    assert r.status_code == 201 and r.json()["mime"] == "image/webp"


async def test_rejected_upload_does_not_leave_blob_in_db(db, db_storage):
    t = teacher(db)
    await upload(t, make_course(db, t).id, CORPUS["html"][0])
    assert db.scalar(select(func.count()).select_from(AssetBlob)) == 0
