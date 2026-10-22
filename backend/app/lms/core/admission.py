"""Pure-ASGI admission gate per process (B1, docs/phases/PHASE_3_LOADTEST.md section 3).

FastAPI runs the sync auth dependency, the endpoint and the `get_db` teardown as separate threadpool hops and holds
the request's pool connection between them. Under overload, requests that own connections wait for a thread token
while every token belongs to a new request blocked on pool checkout: nothing moves until `pool_timeout`. The gate
admits at most N requests into the app; the rest wait in the event loop holding neither a thread nor a connection.
A slot is released only after the downstream app returns, so it covers dependency teardown and BackgroundTasks.
A request that waits longer than LMS_ADMISSION_WAIT_SECONDS gets 503 `server_busy` with Retry-After."""
from __future__ import annotations

import asyncio
import json
import time
import weakref
from typing import Optional

from sqlalchemy.pool import QueuePool

from app.core.config import settings
from app.lms.attempts.bodycap import _API, _EXEMPT, _METHODS
from app.db import session as db_session
from app.lms.core.errors import LMS_PATH_PREFIXES, ServerBusy, error_body
from app.lms.core.logging import get_logger

logger = get_logger("app.lms.admission")

RETRY_AFTER_S = 2
_BUSY_LOG_EVERY_S = 10.0
_ANYIO_DEFAULT_TOKENS = 40


def _exempt(scope) -> bool:
    """Non-HTTP scopes, CORS preflights, the health check and static uploads touch no DB connection."""
    if scope["type"] != "http" or scope.get("method") == "OPTIONS":
        return True
    path = scope.get("path", "")
    return path == "/health" or path == "/uploads" or path.startswith("/uploads/")


def thread_tokens() -> int:
    """Effective anyio worker-thread limit (main.py sets it from LMS_THREADPOOL_TOKENS at startup)."""
    if settings.LMS_THREADPOOL_TOKENS > 0:
        return settings.LMS_THREADPOOL_TOKENS
    try:
        from anyio import to_thread

        return int(to_thread.current_default_thread_limiter().total_tokens)
    except Exception:
        return _ANYIO_DEFAULT_TOKENS


def pool_capacity(engine) -> Optional[int]:
    """pool_size + max_overflow of the app engine, or None when the pool is not a bounded QueuePool."""
    pool = engine.pool
    if not isinstance(pool, QueuePool):
        return None
    overflow = pool._max_overflow
    if overflow < 0:  # unlimited overflow
        return None
    return pool.size() + overflow


def sweep_reserve(engine) -> int:
    """App-pool connections the in-process attempt sweep can hold on top of the admitted requests.

    The sweep runs as a BackgroundTask inside the slot of the request that scheduled it, and FastAPI closes that
    request's `get_db` session only after background tasks, so the request may still hold its connection.
    On Postgres the sweep uses its own two-connection engine (sweep._engine, like ratelimit) and takes nothing from
    the app pool: 0. Elsewhere it shares the app engine, one session at a time (scan, then one finalize per attempt)
    and one sweep per process per interval: 1."""
    return 0 if engine.dialect.name == "postgresql" else 1


def auto_limit(tokens: int, capacity: Optional[int], reserve: int) -> int:
    """N = min(thread tokens, pool_size + max_overflow) - sweep reserve, at least 1.

    N <= tokens: every admitted request can hold a thread at once, so no connection owner waits for a token.
    N <= pool - reserve: every admitted request (plus a sweep) can hold a connection at once, so no thread waits
    on checkout. Either side breaks the hold-and-wait cycle; both keep it safe if one setting changes."""
    base = tokens if capacity is None else min(tokens, capacity)
    return max(1, base - reserve)


def effective_limit() -> int:
    if settings.LMS_ADMISSION_LIMIT > 0:
        return settings.LMS_ADMISSION_LIMIT
    engine = db_session.engine
    return auto_limit(thread_tokens(), pool_capacity(engine), sweep_reserve(engine))


def describe() -> dict:
    """Effective settings for the startup log line ("worker_threads": the log scrubber redacts keys with "token")."""
    engine = db_session.engine
    return {"admission_limit": effective_limit(), "worker_threads": thread_tokens(),
            "pool_capacity": pool_capacity(engine), "sweep_reserve": sweep_reserve(engine),
            "configured_limit": settings.LMS_ADMISSION_LIMIT, "wait_seconds": settings.LMS_ADMISSION_WAIT_SECONDS}


def _buffered(scope) -> bool:
    """Size-capped API bodies (bodycap: <= API_MAX_BODY_BYTES) are read before a slot is taken, so a slow client
    never holds one; uploads/imports enforce their own limits and stream inside the slot."""
    path = scope.get("path", "")
    return scope.get("method") in _METHODS and bool(_API.match(path)) and not _EXEMPT.match(path)


async def _buffer_body(receive):
    """Whole request body, replayed as one message; None if the client disconnected first."""
    chunks = []
    while True:
        msg = await receive()
        if msg["type"] != "http.request":
            return None
        chunks.append(msg.get("body", b""))
        if not msg.get("more_body", False):
            break
    body = b"".join(chunks)
    replayed = False

    async def replay():
        nonlocal replayed
        if not replayed:
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


async def _send_busy(send, path: str) -> None:
    message = "Server is busy, please retry shortly"
    if path.startswith(LMS_PATH_PREFIXES):
        payload = error_body(ServerBusy(message, details={"retry_after_seconds": RETRY_AFTER_S}))
    else:
        payload = {"detail": message}
    body = json.dumps(payload).encode()
    await send({"type": "http.response.start", "status": 503,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            (b"retry-after", str(RETRY_AFTER_S).encode())]})
    await send({"type": "http.response.body", "body": body})


class AdmissionMiddleware:
    def __init__(self, app, limit: Optional[int] = None, wait_seconds: Optional[float] = None):
        self.app = app
        self._limit_override = limit
        self._wait_override = wait_seconds
        # One semaphore per event loop: production has one loop per process; TestClient may start one per request.
        self._sems: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
        self.limit = 0
        self.in_flight = 0
        self.waiting = 0
        self._last_busy_log = 0.0

    def _semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        sem = self._sems.get(loop)
        if sem is None:
            self.limit = self._limit_override or effective_limit()
            sem = asyncio.Semaphore(self.limit)
            self._sems[loop] = sem
        return sem

    def _wait_seconds(self) -> Optional[float]:
        wait = self._wait_override if self._wait_override is not None else settings.LMS_ADMISSION_WAIT_SECONDS
        return wait if wait > 0 else None

    def _log_busy(self) -> None:
        now = time.monotonic()
        if now - self._last_busy_log >= _BUSY_LOG_EVERY_S:
            self._last_busy_log = now
            logger.warning("admission gate: server_busy 503", extra={
                "admission_limit": self.limit, "in_flight": self.in_flight, "waiting": self.waiting})

    async def __call__(self, scope, receive, send):
        if _exempt(scope):
            return await self.app(scope, receive, send)
        if _buffered(scope):
            receive = await _buffer_body(receive)
            if receive is None:
                return
        sem = self._semaphore()
        if sem.locked():
            self.waiting += 1
            try:
                await asyncio.wait_for(sem.acquire(), self._wait_seconds())
            except asyncio.TimeoutError:
                self._log_busy()
                return await _send_busy(send, scope.get("path", ""))
            finally:
                self.waiting -= 1
        else:
            await sem.acquire()
        self.in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.in_flight -= 1
            sem.release()
