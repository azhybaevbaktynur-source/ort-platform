"""Public media route: headers, ETag/304, LRU, private blobs unreachable, no gzip."""
import hashlib

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.lms.files import media
from app.lms.files.models import Asset
from app.lms.files.storage import blob_key
from tests.lms.files_support import (  # noqa: F401
    clean_rate_limits, db, db_storage, get, local_storage, make_course, noisy_png, teacher, unique_png, upload,
)


async def _public(db, size=40):
    t = teacher(db)
    c = make_course(db, t)
    # large enough (>1 KiB) that GZipMiddleware would normally consider compressing it
    a = (await upload(t, c.id, noisy_png(size, size, seed=size))).json()
    return t, c, a


async def test_headers_etag_and_body(db, local_storage):
    _, _, a = await _public(db)
    r = await get(a["url"], headers={"accept-encoding": "gzip, br"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert r.headers["etag"] == f'"{a["sha256"]}"'
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == "default-src 'none'"
    assert r.headers["content-disposition"] == "inline"
    assert "content-encoding" not in r.headers
    assert len(r.content) > 1024
    assert hashlib.sha256(r.content).hexdigest() == a["sha256"]
    assert len(r.content) == a["bytes"]


@pytest.mark.parametrize("inm", ['"{sha}"', 'W/"{sha}"', '"zzz", "{sha}"', "*"])
async def test_if_none_match_304(db, local_storage, inm):
    _, _, a = await _public(db)
    r = await get(a["url"], headers={"if-none-match": inm.replace("{sha}", a["sha256"])})
    assert r.status_code == 304 and r.content == b""
    assert r.headers["etag"] == f'"{a["sha256"]}"' and "immutable" in r.headers["cache-control"]


async def test_wrong_etag_returns_200(db, local_storage):
    _, _, a = await _public(db)
    assert (await get(a["url"], headers={"if-none-match": '"nope"'})).status_code == 200


async def test_no_auth_needed(db, local_storage):
    _, _, a = await _public(db)
    assert (await get(a["url"])).status_code == 200


@pytest.mark.parametrize("name", [
    "x.webp", "A" * 64 + ".webp", "a" * 64, "a" * 64 + ".png", "a" * 63 + ".webp", "a" * 64 + ".webp.png",
    "..%2f" + "a" * 60 + ".webp", "a" * 64 + ".WEBP",
])
async def test_bad_names_404(db, local_storage, name):
    r = await get(f"/api/v1/media/{name}")
    assert r.status_code == 404


async def test_unknown_sha_404(db, local_storage):
    assert (await get(f"/api/v1/media/{'a' * 64}.webp")).status_code == 404


async def test_private_blob_never_served_via_media(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    a = (await upload(t, c.id, unique_png(), visibility="private")).json()
    assert local_storage.exists(blob_key(a["sha256"], "private"))
    assert (await get(f"/api/v1/media/{a['sha256']}.webp")).status_code == 404
    assert (await get(f"/api/v1/media/{a['sha256']}.webp", t)).status_code == 404
    assert (await get(f"/api/v1/media/priv/{a['sha256']}.webp")).status_code == 404


async def test_lru_hit_needs_no_storage_or_db(db, local_storage, monkeypatch):
    _, _, a = await _public(db)
    first = await get(a["url"])
    assert first.status_code == 200
    import os

    os.unlink(local_storage._path(blob_key(a["sha256"])))
    second = await get(a["url"])  # served from the in-process LRU
    assert second.status_code == 200 and second.content == first.content
    media.reset_media_cache()
    assert (await get(a["url"])).status_code == 404


def test_lru_is_byte_bounded_and_evicts_least_recent():
    lru = media._LRU(10)
    lru.put("a", b"1234")
    lru.put("b", b"1234")
    assert lru.get("a") == b"1234"  # a is now most recent
    lru.put("c", b"1234")  # 12 > 10 -> evict b
    assert lru.get("b") is None and lru.get("a") and lru.get("c")
    assert lru.size <= 10
    lru.put("huge", b"x" * 11)
    assert lru.get("huge") is None and lru.size <= 10
    lru.put("a", b"12")
    assert lru.size == 6


async def test_route_cache_respects_setting(db, local_storage, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_CACHE_BYTES", 10)
    media.reset_media_cache()
    _, _, a = await _public(db)
    assert (await get(a["url"])).status_code == 200
    assert len(media.get_media_cache()) == 0  # image larger than the cache: not cached
