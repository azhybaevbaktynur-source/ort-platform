"""Opportunistic sweep of expired attempts (design section 3.10, P3-26): no workers needed.

`maybe_schedule_sweep` runs from student attempt routes (after the response, through BackgroundTasks) at most every
ATTEMPT_SWEEP_INTERVAL_S per process; `run_sweep` finalizes up to `limit` attempts whose deadline + grace has passed.
It uses its own two-connection engine on Postgres (like ratelimit) so it never competes with request sessions.
Finalizing is one-shot (A4), so concurrent sweeps and lazy finalizers are harmless."""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from fastapi import BackgroundTasks
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from datetime import timedelta

from app.core.config import settings
from app.db import session as db_session
from app.lms.attempts import engine as attempt_engine
from app.lms.attempts.models import Attempt
from app.lms.core import clock

logger = logging.getLogger(__name__)

SWEEP_LOCK_KEY = 3_000_001

_state_lock = threading.Lock()
_last_scheduled: Optional[float] = None
_engines: dict = {}
_FAIL_TTL_S = 600.0
_FAIL_MAX = 1000
_failed: dict = {}  # attempt id -> monotonic time of the last failed finalize (bounded, in-process)


def _recent_failed() -> set:
    cutoff = time.monotonic() - _FAIL_TTL_S
    with _state_lock:
        for k in [k for k, t in _failed.items() if t < cutoff]:
            del _failed[k]
        return set(_failed)


def _remember_failed(attempt_id) -> None:
    with _state_lock:
        if len(_failed) >= _FAIL_MAX:
            _failed.pop(min(_failed, key=_failed.get), None)
        _failed[attempt_id] = time.monotonic()


def reset_sweep_state() -> None:
    global _last_scheduled
    with _state_lock:
        _last_scheduled = None
        _failed.clear()


def _engine():
    app_engine = db_session.engine
    if app_engine.dialect.name != "postgresql":
        return app_engine
    url = app_engine.url.render_as_string(hide_password=False)
    eng = _engines.get(url)
    if eng is None:
        with _state_lock:
            eng = _engines.get(url)
            if eng is None:
                eng = create_engine(url, connect_args=dict(db_session.connect_args), pool_size=2, max_overflow=0,
                                    pool_timeout=10, pool_pre_ping=True, pool_recycle=300)
                _engines[url] = eng
    return eng


def maybe_schedule_sweep(background: BackgroundTasks) -> bool:
    """True when a sweep was scheduled (at most once per interval per process)."""
    global _last_scheduled
    now = clock.now().timestamp()
    with _state_lock:
        if _last_scheduled is not None and now - _last_scheduled < settings.ATTEMPT_SWEEP_INTERVAL_S:
            return False
        _last_scheduled = now
    background.add_task(run_sweep)
    return True


def expired_ids(db: Session, now, limit: int, skip: Optional[set] = None) -> list:
    cutoff = now - timedelta(seconds=settings.ATTEMPT_GRACE_S)
    stmt = select(Attempt.id).where(Attempt.status == "in_progress", Attempt.deadline_at.isnot(None),
                                    Attempt.deadline_at < cutoff)
    if skip:
        stmt = stmt.where(Attempt.id.notin_(skip))
    return list(db.execute(stmt.order_by(Attempt.deadline_at, Attempt.id).limit(limit)).scalars())


def run_sweep(limit: Optional[int] = None) -> int:
    """Finalize expired attempts (reason `sweep`), each in its own transaction. Never raises. Returns the number
    this call finalized."""
    limit = limit or settings.ATTEMPT_SWEEP_BATCH
    now = clock.now()
    lock_conn = None
    try:
        eng = _engine()
        if eng.dialect.name == "postgresql":
            # Session-level advisory lock on a dedicated connection, held for the whole sweep (one sweep at a time).
            lock_conn = eng.connect()
            if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SWEEP_LOCK_KEY}).scalar():
                lock_conn.rollback()
                lock_conn.close()
                return 0
            lock_conn.commit()
    except Exception:
        logger.warning("attempt sweep: lock failed", exc_info=True)
        if lock_conn is not None:
            try:
                lock_conn.close()
            except Exception:
                pass
        return 0
    try:
        return _sweep(eng, now, limit)
    finally:
        if lock_conn is not None:
            try:
                lock_conn.rollback()
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SWEEP_LOCK_KEY})
                lock_conn.commit()
            except Exception:
                logger.warning("attempt sweep: unlock failed", exc_info=True)
            finally:
                lock_conn.close()   # closing the connection also drops a session lock if unlock failed


def _sweep(eng, now, limit: int) -> int:
    try:
        with Session(bind=eng) as s:
            ids = expired_ids(s, now, limit, _recent_failed())
            s.commit()
    except Exception:
        logger.warning("attempt sweep: scan failed", exc_info=True)
        return 0
    done = 0
    for attempt_id in ids:
        try:
            with Session(bind=eng) as s:
                outcome = attempt_engine.grading_api().finalize(s, attempt_id, reason="sweep", now=now)
                s.commit()
            if attempt_engine._won(outcome, True):
                done += 1
        except Exception:
            _remember_failed(attempt_id)
            logger.warning("attempt sweep: finalize failed for %s", attempt_id, exc_info=True)
    return done
