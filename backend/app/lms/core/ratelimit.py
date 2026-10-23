"""DB-backed fixed-window rate limiter (works across workers, no Redis).

`hit` uses its own connection and commits immediately, so the counter survives a rollback of
the request's session. Call `hit`/`peek` only when the request session has no uncommitted
writes (SQLite would otherwise wait on its own file lock).
"""
from __future__ import annotations

import hashlib
import logging
import random
import threading
import time
from dataclasses import dataclass

from sqlalchemy import BigInteger, Index, Integer, String, create_engine, delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, mapped_column

from app.db import session as db_session
from app.db.session import Base
from app.core.config import settings
from app.lms.core.errors import RateLimited

logger = logging.getLogger(__name__)


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    window_start: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (Index("ix_rate_limit_buckets_expires_at", "expires_at"),)


@dataclass(frozen=True)
class Limit:
    name: str
    limit: int
    window_seconds: int
    is_ip_rule: bool = False


JOIN_USER_10M = Limit("join_user_10m", 10, 600)
JOIN_USER_24H = Limit("join_user_24h", 30, 86400)
JOIN_IP_FAIL_10M = Limit("join_ip_fail_10m", 60, 600, is_ip_rule=True)
TEACHER_REQUEST_24H = Limit("teacher_request_24h", 3, 86400)
STAFF_ADD_1H = Limit("staff_add_1h", 30, 3600)


def attempt_start_limit() -> Limit:
    """Phase 3 (P3-28): attempt starts, per user. Built per call so settings overrides apply."""
    return Limit("attempt_start_10m", settings.ATTEMPT_START_RATE_PER_10M, 600)


def grade_item_limit() -> Limit:
    """Phase 3 (P3-28): manual item scoring, per user."""
    return Limit("grade_item_1h", settings.GRADE_ITEM_RATE_PER_HOUR, 3600)


def grades_release_limit() -> Limit:
    """Phase 4 (P4-21): release/unrelease grades, per user."""
    return Limit("grades_release_1h", settings.GRADES_RELEASE_RATE_PER_HOUR, 3600)


def grades_regrade_limit() -> Limit:
    """Phase 4 (P4-21): regrade requests, per user."""
    return Limit("grades_regrade_1h", settings.GRADES_REGRADE_RATE_PER_HOUR, 3600)


def scheme_write_limit() -> Limit:
    """Phase 4 (P4-21): grading scheme create/version/title/delete/restore, per user."""
    return Limit("scheme_write_1h", settings.SCHEME_WRITE_RATE_PER_HOUR, 3600)


def scheme_preview_limit() -> Limit:
    """Phase 4 (P4-21): scheme preview, per user."""
    return Limit("scheme_preview_1m", settings.SCHEME_PREVIEW_RATE_PER_MIN, 60)

_CLEANUP_PROBABILITY = 1 / 200
_CLEANUP_BATCH = 1000

_rl_engines: dict = {}
_rl_lock = threading.Lock()


def _engine():
    """Own small pool on Postgres so a request never waits on the app pool while holding a
    rate-limit connection (and vice versa). SQLite reuses the app engine (shared file DB)."""
    app_engine = db_session.engine
    if app_engine.dialect.name != "postgresql":
        return app_engine
    url = app_engine.url.render_as_string(hide_password=False)
    eng = _rl_engines.get(url)
    if eng is None:
        with _rl_lock:
            eng = _rl_engines.get(url)
            if eng is None:
                eng = create_engine(
                    url, connect_args=dict(db_session.connect_args),
                    pool_size=2, max_overflow=3, pool_timeout=5, pool_pre_ping=True, pool_recycle=300,
                )
                _rl_engines[url] = eng
    return eng


def _now() -> int:
    return int(time.time())


def _bucket_key(key: str, rule: Limit) -> str:
    # Distinct rules on the same key must not share a counter; the hash is never truncated.
    return f"{rule.name}:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def _window(now: int, rule: Limit) -> int:
    return now - now % rule.window_seconds


def _cleanup(engine, now: int) -> None:
    t = RateLimitBucket.__table__
    try:
        with engine.begin() as conn:
            if engine.dialect.name == "postgresql":
                conn.execute(
                    text("DELETE FROM rate_limit_buckets WHERE ctid IN (SELECT ctid FROM rate_limit_buckets "
                         "WHERE expires_at < :now LIMIT :n)"),
                    {"now": now, "n": _CLEANUP_BATCH},
                )
            else:
                conn.execute(delete(t).where(t.c.expires_at < now))
    except Exception:  # cleanup is best-effort
        logger.warning("rate limit cleanup failed", exc_info=True)


def hit(key: str, rule: Limit) -> tuple[bool, int]:
    """Count one event. Returns (allowed, retry_after_seconds).

    IP rules only count (and log) unless settings.RATE_LIMIT_IP_ENFORCE is True."""
    engine = _engine()
    now = _now()
    ws = _window(now, rule)
    expires = ws + rule.window_seconds
    t = RateLimitBucket.__table__
    ins = (pg_insert if engine.dialect.name == "postgresql" else sqlite_insert)(t).values(
        key=_bucket_key(key, rule), window_start=ws, count=1, expires_at=expires
    )
    stmt = ins.on_conflict_do_update(
        index_elements=[t.c.key, t.c.window_start], set_={"count": t.c.count + 1}
    ).returning(t.c.count)
    with engine.begin() as conn:
        count = conn.execute(stmt).scalar_one()
    if random.random() < _CLEANUP_PROBABILITY:
        _cleanup(engine, now)
    if count <= rule.limit:
        return True, 0
    if rule.is_ip_rule and not settings.RATE_LIMIT_IP_ENFORCE:
        logger.info("rate limit (log-only) rule=%s key_hash=%s count=%s", rule.name,
                    hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], count)
        return True, 0
    return False, max(1, expires - now)


def peek(key: str, rule: Limit) -> tuple[bool, int]:
    """Read only. allowed=True means the next event would still be counted below the limit."""
    engine = _engine()
    now = _now()
    ws = _window(now, rule)
    t = RateLimitBucket.__table__
    with engine.connect() as conn:
        count = conn.execute(
            select(t.c.count).where(t.c.key == _bucket_key(key, rule), t.c.window_start == ws)
        ).scalar_one_or_none() or 0
    if count < rule.limit:
        return True, 0
    if rule.is_ip_rule and not settings.RATE_LIMIT_IP_ENFORCE:
        return True, 0
    return False, max(1, ws + rule.window_seconds - now)


def enforce(key: str, rule: Limit) -> None:
    allowed, retry = hit(key, rule)
    if not allowed:
        raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
