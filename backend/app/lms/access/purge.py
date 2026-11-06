"""Retention of the buyer's name on a sold code (review of S3, docs/PERSONAL_DATA.md): `activation_codes.given_note`
is emptied GIVEN_NOTE_DAYS after the code was redeemed (it only helps the admin answer "who bought this" for a while).
Revoking a batch empties it at once (`access.admin.revoke_batch`).

Runs with the teacher applicants' phone purge (`teachers.purge.run_task`): opportunistically from the admin's queue and
from `POST /internal/purge-applications`. Idempotent and bounded; on PostgreSQL rows are claimed with
`FOR UPDATE SKIP LOCKED`. Logs counts only."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.lms.access.models import ActivationCode
from app.lms.core import clock
from app.lms.core.logging import get_logger

logger = get_logger("app.lms.access.purge")

GIVEN_NOTE_DAYS = 90
PURGE_BATCH = 500


def run_purge(db: Optional[Session] = None, *, limit: int = PURGE_BATCH, now: Optional[datetime] = None) -> int:
    own = db is None
    if own:
        from app.db.session import SessionLocal

        db = SessionLocal()
    try:
        now = now or clock.now()
        stmt = (select(ActivationCode.id)
                .where(ActivationCode.given_note.is_not(None), ActivationCode.redeemed_at.is_not(None),
                       ActivationCode.redeemed_at <= now - timedelta(days=GIVEN_NOTE_DAYS))
                .order_by(ActivationCode.id).limit(max(0, min(int(limit), PURGE_BATCH))))
        if db.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        due = list(db.execute(stmt).scalars())
        if due:
            db.execute(update(ActivationCode).where(ActivationCode.id.in_(due)).values(given_note=None)
                       .execution_options(synchronize_session=False))
        db.commit()
        if due:
            logger.info("activation code buyer note purge", extra={"purged": len(due)})
        return len(due)
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()
