"""B1: per-process admission gate (app/lms/core/admission.py)."""
import asyncio
import json
import os
import time

import anyio
import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, exc as sa_exc, text
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.cors import CORSMiddleware

from app.db import session as db_session
from app.db.session import SessionLocal, get_db
from app.lms.core import admission
from app.lms.core.admission import AdmissionMiddleware
from app.lms.core.deps import get_lms_user
from app.models.user import User
from tests.lms.factories import auth, make_user


class _Held:
    """Inner ASGI app: /block waits for an event, /boom raises, anything else answers 200 at once."""

    def __init__(self):
        self.release = asyncio.Event()
        self.entered = asyncio.Event()
        self.calls = []

    async def __call__(self, scope, receive, send):
        self.calls.append(scope.get("path"))
        if scope.get("path") == "/boom":
            raise RuntimeError("boom")
        if scope.get("path") == "/block":
            self.entered.set()
            await self.release.wait()
        if scope["type"] != "http":
            return
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _call(app, path, method="GET", scope_type="http"):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await app({"type": scope_type, "method": method, "path": path, "headers": []}, receive, send)
    start = next((m for m in sent if m["type"] == "http.response.start"), None)
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return (start["status"] if start else None), dict(start["headers"]) if start else {}, body


def test_auto_limit_formula():
    assert admission.auto_limit(20, 20, 0) == 20
    assert admission.auto_limit(20, 10, 0) == 10
    assert admission.auto_limit(8, 20, 0) == 8
    assert admission.auto_limit(20, 15, 1) == 14
    assert admission.auto_limit(20, None, 0) == 20      # unbounded pool: thread tokens
    assert admission.auto_limit(1, 1, 1) == 1           # clamped


def test_configured_limit_wins(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "LMS_ADMISSION_LIMIT", 7)
    assert admission.effective_limit() == 7
    monkeypatch.setattr(settings, "LMS_ADMISSION_LIMIT", 0)
    monkeypatch.setattr(settings, "LMS_THREADPOOL_TOKENS", 3)
    assert admission.effective_limit() == max(1, 3 - admission.sweep_reserve(db_session.engine))


def test_exempt_paths_bypass_a_full_gate_and_busy_is_503():
    async def run():
        inner = _Held()
        mw = AdmissionMiddleware(inner, limit=1, wait_seconds=0.05)
        inner_block = asyncio.create_task(_call(mw, "/block"))   # holds the only slot
        await inner.entered.wait()
        assert mw.in_flight == 1
        for path, method in (("/health", "GET"), ("/uploads/a/b.png", "GET"), ("/uploads", "GET"),
                             ("/api/v1/attempts/x", "OPTIONS")):
            status, _, _ = await asyncio.wait_for(_call(mw, path, method), 1)
            assert status == 200, (path, method)
        await asyncio.wait_for(_call(mw, "/ws", scope_type="websocket"), 1)
        assert inner.calls.count("/ws") == 1

        t0 = time.monotonic()
        status, headers, body = await _call(mw, "/api/v1/attempts/abc/answers", "PUT")
        assert time.monotonic() - t0 >= 0.04
        assert status == 503
        assert headers[b"retry-after"] == b"2"
        assert headers[b"content-type"] == b"application/json"
        assert json.loads(body) == {"error": {"code": "server_busy", "message": "Server is busy, please retry shortly",
                                              "details": {"retry_after_seconds": 2}}}
        assert "/api/v1/attempts/abc/answers" not in inner.calls
        # Old (non-LMS) routes keep their {"detail": ...} shape.
        status, headers, body = await _call(mw, "/api/v1/mock-tests", "GET")
        assert status == 503 and headers[b"retry-after"] == b"2" and "detail" in json.loads(body)
        assert mw.waiting == 0

        inner.release.set()
        await inner_block
        assert mw.in_flight == 0

    asyncio.run(run())


def test_waiter_gets_the_slot_when_it_frees():
    async def run():
        inner = _Held()
        mw = AdmissionMiddleware(inner, limit=1, wait_seconds=5)
        blocker = asyncio.create_task(_call(mw, "/block"))
        await inner.entered.wait()
        waiter = asyncio.create_task(_call(mw, "/api/v1/me/lms"))
        await asyncio.sleep(0.05)
        assert mw.waiting == 1 and not waiter.done()
        inner.release.set()
        status, _, _ = await asyncio.wait_for(waiter, 2)
        assert status == 200
        await blocker
        assert mw.waiting == 0 and mw.in_flight == 0

    asyncio.run(run())


def test_slot_released_when_the_handler_raises():
    async def run():
        inner = _Held()
        mw = AdmissionMiddleware(inner, limit=1, wait_seconds=0.05)
        with pytest.raises(RuntimeError):
            await _call(mw, "/boom")
        assert mw.in_flight == 0
        for _ in range(3):
            status, _, _ = await _call(mw, "/api/v1/me/lms")
            assert status == 200

    asyncio.run(run())


def test_cors_headers_are_on_the_503():
    async def run():
        inner = _Held()
        app = CORSMiddleware(AdmissionMiddleware(inner, limit=1, wait_seconds=0.05), allow_origins=["*"],
                             allow_methods=["*"], allow_headers=["*"])
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            blocker = asyncio.create_task(client.get("/block"))
            await inner.entered.wait()
            r = await client.get("/api/v1/attempts/x", headers={"Origin": "http://example.org"})
            assert r.status_code == 503
            assert r.headers["access-control-allow-origin"] == "*"
            assert r.headers["retry-after"] == "2"
            assert r.json()["error"]["code"] == "server_busy"
            inner.release.set()
            assert (await blocker).status_code == 200

    asyncio.run(run())


def test_main_app_registers_the_gate_inside_cors():
    from app.main import app

    names = [m.cls.__name__ for m in app.user_middleware]  # outermost first
    assert names[0] == "CORSMiddleware"
    assert names[-1] == "AdmissionMiddleware"


# --- Regression on Postgres: more than P concurrent requests through get_lms_user with a slow handler ---------------

POOL, TOKENS, REQUESTS = 2, 2, 8


def _pg_url():
    if not os.getenv("LMS_PG_TEST_DATABASE_URL") or db_session.engine.dialect.name != "postgresql":
        pytest.skip("needs LMS_PG_TEST_DATABASE_URL (Postgres)")
    return db_session.engine.url.render_as_string(hide_password=False)


def _slow_app(maker, gate: bool):
    app = FastAPI()

    def override():
        s = maker()
        try:
            yield s
        finally:
            s.close()

    @app.get("/slow")
    def slow(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        time.sleep(0.3)   # holds the session's connection and a worker thread
        return {"id": user.id}

    async def pool_timeout(request, exc):
        return JSONResponse(status_code=599, content={"pool_timeout": True})

    app.dependency_overrides[get_db] = override
    app.add_exception_handler(sa_exc.TimeoutError, pool_timeout)
    return AdmissionMiddleware(app, limit=None, wait_seconds=30) if gate else app


def _burst(gate: bool):
    url = _pg_url()
    s = SessionLocal()
    try:
        heads = [auth(make_user(s)) for _ in range(4)]
    finally:
        s.close()
    small = create_engine(url, connect_args=dict(db_session.connect_args), pool_size=POOL, max_overflow=0,
                          pool_timeout=3)
    maker = sessionmaker(bind=small, autocommit=False, autoflush=False)
    app = _slow_app(maker, gate)

    async def run():
        from anyio import to_thread

        to_thread.current_default_thread_limiter().total_tokens = TOKENS
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=60) as client:
            rs = await asyncio.gather(*(client.get("/slow", headers=heads[i % 4]) for i in range(REQUESTS)))
        return [r.status_code for r in rs]

    try:
        t0 = time.monotonic()
        codes = anyio.run(run)
        return codes, time.monotonic() - t0
    finally:
        small.dispose()


def test_without_gate_the_burst_hits_pool_timeouts():
    """Proves the regression test reproduces B1: 2 threads, 2 connections, 8 slow requests."""
    codes, _ = _burst(gate=False)
    assert 599 in codes, codes


def test_gate_prevents_pool_timeouts(monkeypatch):
    from app.core.config import settings

    # Auto limit = min(thread tokens, small pool) = 2 (set explicitly: the gate reads the app engine, not `small`).
    monkeypatch.setattr(settings, "LMS_ADMISSION_LIMIT", min(TOKENS, POOL))
    codes, elapsed = _burst(gate=True)
    assert codes == [200] * REQUESTS, codes
    assert elapsed < 3, elapsed   # no pool_timeout stall: about REQUESTS / 2 x 0.3 s


def test_slow_body_does_not_hold_a_slot_and_is_replayed_whole():
    """A capped API body is read before a slot is taken: a client trickling its body never blocks others."""
    async def run():
        got = []

        async def inner(scope, receive, send):
            msg = await receive()
            got.append(msg)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = AdmissionMiddleware(inner, limit=1, wait_seconds=0.2)
        more = asyncio.Event()
        parts = [{"type": "http.request", "body": b'{"a":', "more_body": True}]

        async def slow_receive():
            if parts:
                return parts.pop(0)
            await more.wait()
            return {"type": "http.request", "body": b"1}", "more_body": False}

        sent = []

        async def send(msg):
            sent.append(msg)

        slow = asyncio.create_task(mw({"type": "http", "method": "POST", "path": "/api/v1/attempts/x/answers",
                                       "headers": []}, slow_receive, send))
        await asyncio.sleep(0.05)
        assert mw.in_flight == 0  # still reading the body: no slot taken
        status, _, _ = await _call(mw, "/api/v1/attempts/x/answers", method="POST")
        assert status == 200
        more.set()
        await asyncio.wait_for(slow, 2)
        assert got[-1] == {"type": "http.request", "body": b'{"a":1}', "more_body": False}
        assert mw.in_flight == 0

    asyncio.run(run())
