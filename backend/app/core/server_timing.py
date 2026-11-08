"""Server-Timing header (PERFORMANCE_AUDIT, owner round 2026-11-09 item 1). Pure ASGI, no body read, no logging.

Every HTTP answer carries `Server-Timing: total;dur=<ms>, db;dur=<ms>;desc="n=<queries>"`: the wall time from the
request's arrival to the start of the response, the time spent inside SQLAlchemy cursor executions and how many there
were. A contextvar holds one mutable record per request; the engine's cursor events add to it (the record is shared
with the worker thread FastAPI runs sync routes and `get_db` in, because anyio copies the context into that thread).
Requests outside a record (startup, background sweeps) count nothing. `Timing-Allow-Origin` lets the browser's
developer tools show the header for the cross-origin frontend; neither header carries data."""
from __future__ import annotations

import contextvars
import time
from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_record: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("server_timing", default=None)
_STACK = "server_timing_started"


def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    if _record.get() is None:
        return
    conn.info.setdefault(_STACK, []).append(time.perf_counter())


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    rec = _record.get()
    stack = conn.info.get(_STACK)
    if rec is None or not stack:
        return
    rec["db_ms"] += (time.perf_counter() - stack.pop()) * 1000
    rec["queries"] += 1


# Class-level: every engine (the app's and the ones tests build) reports into the current request's record.
event.listen(Engine, "before_cursor_execute", _before_cursor_execute)
event.listen(Engine, "after_cursor_execute", _after_cursor_execute)


def current() -> Optional[dict]:
    """The record of the request being served (`{"db_ms": float, "queries": int}`), or None outside a request."""
    return _record.get()


def format_header(total_ms: float, rec: dict) -> str:
    return f'total;dur={total_ms:.1f}, db;dur={rec["db_ms"]:.1f};desc="n={rec["queries"]}"'


class ServerTimingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rec = {"db_ms": 0.0, "queries": 0}
        token = _record.set(rec)
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("Server-Timing", format_header((time.perf_counter() - started) * 1000, rec))
                headers.append("Timing-Allow-Origin", "*")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _record.reset(token)
