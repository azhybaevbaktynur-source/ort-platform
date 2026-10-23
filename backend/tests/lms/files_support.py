"""Helpers for the C3 files tests."""
from __future__ import annotations

import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core.config import settings
from app.lms.files import media, storage
from app.main import app
from tests.lms.factories import auth
from tests.lms.s3_support import Api, api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


@pytest.fixture
def local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "local")
    monkeypatch.setattr(settings, "LMS_LOCAL_STORAGE_DIR", str(tmp_path / "blobs"))
    storage.reset_blob_storage()
    media.reset_media_cache()
    yield storage.get_blob_storage()
    storage.reset_blob_storage()
    media.reset_media_cache()


@pytest.fixture
def db_storage(monkeypatch):
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "db")
    storage.reset_blob_storage()
    media.reset_media_cache()
    yield storage.get_blob_storage()
    storage.reset_blob_storage()
    media.reset_media_cache()


async def upload(user, course_id, data: bytes, *, filename="pic.png", ctype="image/png", visibility=None,
                 ip=None, headers=None):
    h = auth(user) if user is not None else {}
    h["x-forwarded-for"] = f"{ip or '10.1.2.3'}, 10.255.255.1"
    h.update(headers or {})
    form = {"visibility": visibility} if visibility else None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post(f"/api/v1/courses/{course_id}/assets", files={"file": (filename, data, ctype)},
                            data=form, headers=h)


async def get(path, user=None, headers=None):
    h = auth(user) if user is not None else {}
    h.update(headers or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.get(path, headers=h)


def noisy_png(w=32, h=32, seed=1) -> bytes:
    import random

    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(w * h)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def unique_png(n: int | None = None) -> bytes:
    n = uuid.uuid4().int % 255 if n is None else n
    return noisy_png(12, 12, seed=uuid.uuid4().int % 10**9)
