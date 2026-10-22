"""DB-backed fixed-window rate limiter (works across workers, no Redis).

`hit` uses its own connection and commits immediately, so the counter survives a rollback of
the request's session. Call `hit`/`peek` only when the request session has no uncommitted
writes (SQLite would otherwise wait on its own file lock).
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from sqlalchemy import BigInteger, Index, Integer, String, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, mapped_column

from app.db import session as db_session
from app.db.session import Base
from app.lms.core.errors import RateLimited


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


JOIN_USER_10M = Limit("join_user_10m", 10, 600)
JOIN_USER_24H = Limit("join_user_24h", 30, 86400)
JOIN_IP_FAIL_10M = Limit("join_ip_fail_10m", 60, 600)
TEACHER_REQUEST_24H = Limit("teacher_request_24h", 3, 86400)
STAFF_ADD_1H = Limit("staff_add_1h", 30, 3600)

_CLEANUP_PROBABILITY = 1 / 200


def _now() -> int:
    return int(time.time())


def _bucket_key(key: str, rule: Limit) -> str:
    # Distinct rules on the same key (e.g. 10m and 24h) must not share a counter.
    return f"{key}|{rule.name}"[:128]


def _window(now: int, rule: Limit) -> int:
    return now - now % rule.window_seconds


def hit(key: str, rule: Limit) -> tuple[bool, int]:
    """Count one event. Returns (allowed, retry_after_seconds)."""
    engine = db_session.engine
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
            conn.execute(delete(t).where(t.c.expires_at < now))
    if count <= rule.limit:
        return True, 0
    return False, max(1, expires - now)


def peek(key: str, rule: Limit) -> tuple[bool, int]:
    """Read only. allowed=True means the next event would still be counted below the limit."""
    engine = db_session.engine
    now = _now()
    ws = _window(now, rule)
    t = RateLimitBucket.__table__
    with engine.connect() as conn:
        count = conn.execute(
            select(t.c.count).where(t.c.key == _bucket_key(key, rule), t.c.window_start == ws)
        ).scalar_one_or_none() or 0
    if count < rule.limit:
        return True, 0
    return False, max(1, ws + rule.window_seconds - now)


def enforce(key: str, rule: Limit) -> None:
    allowed, retry = hit(key, rule)
    if not allowed:
        raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
