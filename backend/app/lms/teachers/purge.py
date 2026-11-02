"""Purge of teacher applicants' phone numbers (docs/phases/ACCOUNTS.md C, owner Q3): `phone_purge_after <= now` nulls the
phone and the timestamp; the row stays. Idempotent and bounded; on PostgreSQL rows are claimed with `FOR UPDATE SKIP LOCKED`.

Scheduled like `enrollment_forms/purge.py`: production has no cron, so a successful application and the admin's queue start
a bounded run after the response, at most once per interval per process; `POST /internal/purge-applications` also runs it,
for a future scheduler. Logs counts only."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.lms.core import clock
from app.lms.core.logging import get_logger
from app.lms.enrollment_forms.ids import PURGE_OPPORTUNISTIC_INTERVAL_S
from app.lms.teachers.models import TeacherRequest

logger = get_logger("app.lms.teachers.purge")

PURGE_BATCH = 500
OPPORTUNISTIC_LIMIT = 100

_lock = threading.Lock()
_last_run = 0.0  # time.monotonic() of the last opportunistic run in this process


def run_purge(db: Optional[Session] = None, *, limit: int = PURGE_BATCH, now: Optional[datetime] = None) -> int:
    """One bounded run; returns how many rows it purged. Its own session and commit unless `db` is given (the caller's
    session is committed)."""
    own = db is None
    if own:
        from app.db.session import SessionLocal

        db = SessionLocal()
    try:
        now = now or clock.now()
        stmt = (select(TeacherRequest.id)
                .where(TeacherRequest.phone_purge_after.is_not(None), TeacherRequest.phone_purge_after <= now)
                .order_by(TeacherRequest.id).limit(max(0, min(int(limit), PURGE_BATCH))))
        if db.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        due = list(db.execute(stmt).scalars())
        if due:
            db.execute(update(TeacherRequest).where(TeacherRequest.id.in_(due))
                       .values(phone=None, phone_purge_after=None).execution_options(synchronize_session=False))
        db.commit()
        if due:
            logger.info("teacher applicant phone purge", extra={"purged": len(due)})
        return len(due)
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()


def run_task() -> None:
    """Never raises: a failed run is logged and the next one picks the rows up."""
    try:
        run_purge(limit=OPPORTUNISTIC_LIMIT)
    except Exception:
        logger.warning("teacher applicant phone purge failed", exc_info=True)


def reset_throttle() -> None:
    """Tests: forget the last opportunistic run of this process."""
    global _last_run
    with _lock:
        _last_run = 0.0


def _due_for_opportunistic_run() -> bool:
    """True at most once per interval per process (claims the slot)."""
    global _last_run
    now = time.monotonic()
    with _lock:
        if _last_run and now - _last_run < PURGE_OPPORTUNISTIC_INTERVAL_S:
            return False
        _last_run = now
        return True


def queue(background: BackgroundTasks) -> None:
    if _due_for_opportunistic_run():
        background.add_task(run_task)
