"""Grade events (design 2.6, P4-16): append-only audit of human and regrade actions only.

Writes are Core INSERTs (one multi-row executemany per chunk); rows are never updated or deleted
(the ORM listeners in `models.py` raise). Automatic computations write no event."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.lms.grading.models import GRADE_EVENTS, GradeEvent
from app.models.user import User

EVENTS_LIMIT = 100
_T = GradeEvent.__table__


def jsonable(v: Any) -> Any:
    """Event payloads are JSON: Decimals as strings, datetimes ISO, UUIDs as strings."""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def event_row(*, submission_id, course_id, actor_id: Optional[str], event: str, now: datetime,
              attempt_id=None, old: Optional[dict] = None, new: Optional[dict] = None,
              reason: Optional[str] = None) -> dict:
    if event not in GRADE_EVENTS:
        raise ValueError(f"unknown grade event {event!r}")
    return {
        "id": uuid.uuid4(), "submission_id": submission_id, "course_id": course_id, "actor_id": actor_id,
        "event": event, "attempt_id": attempt_id, "old": None if old is None else jsonable(old),
        "new": None if new is None else jsonable(new), "reason": reason, "created_at": now,
    }


def insert_events(db: Session, rows: list[dict]) -> None:
    """One INSERT (executemany) for all rows."""
    if rows:
        db.execute(insert(_T), rows)


def list_events(db: Session, submission_id, *, limit: int = EVENTS_LIMIT) -> list[dict]:
    """Newest first, with the actor's display name (one statement)."""
    rows = db.execute(
        select(_T, User.display_name, User.email)
        .outerjoin(User, User.id == _T.c.actor_id)
        .where(_T.c.submission_id == submission_id)
        .order_by(_T.c.created_at.desc(), _T.c.id.desc())
        .limit(limit)
    ).all()
    out = []
    for r in rows:
        m = r._mapping
        out.append({
            "id": m[_T.c.id], "event": m[_T.c.event],
            "actor_name": (m[User.display_name] or m[User.email]) if m[_T.c.actor_id] else None,
            "attempt_id": m[_T.c.attempt_id], "old": m[_T.c.old], "new": m[_T.c.new], "reason": m[_T.c.reason],
            "created_at": m[_T.c.created_at],
        })
    return out
