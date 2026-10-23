"""P3-27: an LMS request authenticates on the request session (one pool checkout), a real JWT for a seeded account resolves it."""
import contextlib

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db import session as db_session
from app.main import app
from app.models.user import User
from tests.lms.factories import auth, make_course, make_user
from app.db.session import SessionLocal


def _client():
    """TestClient without the lifespan (startup migrations): like every other LMS test."""
    return contextlib.nullcontext(TestClient(app))


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def checkouts():
    counter = {"n": 0}

    def on_checkout(*_a, **_k):
        counter["n"] += 1

    event.listen(db_session.engine, "checkout", on_checkout)
    yield counter
    event.remove(db_session.engine, "checkout", on_checkout)


def test_lms_request_checks_out_one_connection(db, checkouts):
    user = make_user(db)
    headers, uid = auth(user), user.id
    db.close()  # an open read transaction would block the startup ALTER TABLEs on Postgres
    with _client() as client:
        checkouts["n"] = 0
        r = client.get("/api/v1/me/lms", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == uid
    assert checkouts["n"] == 1


def test_course_route_checks_out_one_connection(db, checkouts):
    teacher = make_user(db, teacher_status="approved")
    make_course(db, teacher)
    headers = auth(teacher)
    db.close()
    with _client() as client:
        checkouts["n"] = 0
        r = client.get("/api/v1/courses", headers=headers)
    assert r.status_code == 200, r.text
    assert checkouts["n"] == 1


def test_real_jwt_resolves_seeded_account(db, checkouts):
    student = db.query(User).filter(User.id == "usr_student_01").one()
    headers = auth(student)
    db.close()
    with _client() as client:
        checkouts["n"] = 0
        r = client.get("/api/v1/me/lms", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "usr_student_01"
    assert checkouts["n"] == 1


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Token abc"},
    {"Authorization": "Bearer not-a-jwt-and-not-mock"},
])
def test_bad_credentials_are_401(headers):
    with _client() as client:
        assert client.get("/api/v1/me/lms", headers=headers).status_code == 401


def test_disabled_and_unknown_users_are_401(db):
    from app.core.security import create_access_token

    disabled = make_user(db, disabled=True)
    ghost = {"Authorization": "Bearer " + create_access_token({"sub": "usr_does_not_exist"})}
    dis_headers = auth(disabled)
    db.close()
    with _client() as client:
        assert client.get("/api/v1/me/lms", headers=dis_headers).status_code == 401
        assert client.get("/api/v1/me/lms", headers=ghost).status_code == 401


def test_thread_limiter_is_set_from_settings(monkeypatch):
    from anyio import to_thread

    from app.core.config import settings
    from app.main import _configure_thread_limiter

    monkeypatch.setattr(settings, "LMS_THREADPOOL_TOKENS", 7)

    async def run():
        await _configure_thread_limiter()
        return to_thread.current_default_thread_limiter().total_tokens

    assert anyio.run(run) == 7


def test_concurrent_burst_with_tiny_pool_does_not_starve():
    """P3-27 under load: 50 parallel LMS requests on a 5-connection pool (no overflow) all succeed.

    With the old two-checkouts-per-request auth this deadlocked/timed out. Postgres only."""
    import os
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = os.getenv("LMS_PG_TEST_DATABASE_URL")
    if not url or db_session.engine.dialect.name != "postgresql":
        pytest.skip("needs LMS_PG_TEST_DATABASE_URL (Postgres)")
    from app.db.session import get_db

    small = create_engine(url, pool_size=5, max_overflow=0, pool_timeout=10)
    maker = sessionmaker(bind=small, autocommit=False, autoflush=False)

    def override():
        s = maker()
        try:
            yield s
        finally:
            s.close()

    s = SessionLocal()
    try:
        users = [make_user(s) for _ in range(5)]
        heads = [auth(u) for u in users]
    finally:
        s.close()
    app.dependency_overrides[get_db] = override
    try:
        with _client() as client:
            with ThreadPoolExecutor(max_workers=50) as pool:
                codes = list(pool.map(lambda i: client.get("/api/v1/me/lms", headers=heads[i % 5]).status_code,
                                      range(50)))
    finally:
        app.dependency_overrides.pop(get_db, None)
        small.dispose()
    assert codes == [200] * 50
