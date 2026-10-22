"""Shared helpers for the S3 (courses/enrollments) tests."""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db import session as db_session
from app.db.session import SessionLocal
from app.lms.core.ratelimit import RateLimitBucket
from app.main import app
from tests.lms.factories import auth, enroll, make_course, make_user  # noqa: F401


@pytest.fixture(autouse=True)
def clean_rate_limits():
    with db_session.engine.begin() as c:
        c.execute(delete(RateLimitBucket.__table__))
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


class Api:
    """Async API caller; every Api instance uses its own client IP (via X-Forwarded-For)."""

    def __init__(self):
        self.ip = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"

    async def call(self, user, method, path, json=None, params=None, ip=None, raw=False):
        headers = auth(user) if user is not None else {}
        headers["x-forwarded-for"] = f"{ip or self.ip}, 10.255.255.1"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            res = await c.request(method, "/api/v1" + path, json=json, params=params, headers=headers)
        return res


@pytest.fixture
def api():
    return Api()


def teacher(db, **kw):
    return make_user(db, teacher_status="approved", **kw)
