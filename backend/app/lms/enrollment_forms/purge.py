"""D7 purge of application answers (PHASE_9_DESIGN 4.7, 6, P9-7): `answers = NULL, purged_at = now`; the row stays
for counts and history.

Due rows:
1. `purge_after <= now` (set on reject, withdraw and unenroll: now + the root's `application_retention_days`);
2. applications of **soft-deleted courses** once `deleted_at + retention_days <= now` (computed here, so a course
   restored in time keeps its applications untouched).

Bounded: at most `limit` rows per run (default `ids.PURGE_BATCH`); on PostgreSQL the rows are claimed with
`FOR UPDATE SKIP LOCKED`, so two runs never wait on each other nor purge the same row twice.

Triggers (orchestrator decision, see `ids.py`): no cron exists in production. `maybe_run()` is called from the staff
application list and from submit, at most once per `PURGE_OPPORTUNISTIC_INTERVAL_S` per process, with a small limit,
in its own session after the response (`BackgroundTasks`). `POST /internal/purge-applications` (token) runs
`run_purge()` for a future scheduler."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, null, select, update
from sqlalchemy.orm import Session

from app.lms.core import clock
from app.lms.core.logging import get_logger
from app.lms.courses.models import Course
from app.lms.enrollment_forms import ids
from app.lms.enrollment_forms.models import EnrollmentApplication
from app.lms.enrollment_forms.schemas import PurgeOut

logger = get_logger("app.lms.enrollment_forms.purge")

OPPORTUNISTIC_LIMIT = 100
DELETED_COURSES_PER_RUN = 50

_lock = threading.Lock()
_last_run = 0.0  # time.monotonic() of the last opportunistic run in this process


def _is_pg(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _claim(db: Session, where, limit: int) -> list:
    """Ids of up to `limit` unpurged rows matching `where`, locked on PostgreSQL (`SKIP LOCKED`)."""
    if limit <= 0:
        return []
    stmt = (select(EnrollmentApplication.id)
            .where(EnrollmentApplication.purged_at.is_(None), where)
            .order_by(EnrollmentApplication.id).limit(limit))
    if _is_pg(db):
        stmt = stmt.with_for_update(skip_locked=True)
    return list(db.execute(stmt).scalars())


def _null_answers(db: Session, app_ids: list, now: datetime) -> int:
    if not app_ids:
        return 0
    db.execute(update(EnrollmentApplication)
               .where(EnrollmentApplication.id.in_(app_ids), EnrollmentApplication.purged_at.is_(None))
               .values(answers=null(), purged_at=now)  # SQL NULL, not JSON 'null'
               .execution_options(synchronize_session=False))
    return len(app_ids)


def _retention_by_org(db: Session, org_ids: set) -> dict:
    from app.lms.organizations.models import Organization
    from app.lms.organizations.settings import settings_of

    out = {}
    for org in db.execute(select(Organization).where(Organization.id.in_(list(org_ids)))).scalars():
        out[org.id] = settings_of(db, org).application_retention_days
    return out


def run_purge(db: Optional[Session] = None, *, limit: int = ids.PURGE_BATCH, now: Optional[datetime] = None) -> PurgeOut:
    """One bounded purge run (its own session and commit unless `db` is given; the caller's session is committed)."""
    own = db is None
    if own:
        from app.db.session import SessionLocal

        db = SessionLocal()
    try:
        now = now or clock.now()
        limit = max(0, min(int(limit), ids.PURGE_BATCH))
        due = _claim(db, and_(EnrollmentApplication.purge_after.is_not(None),
                              EnrollmentApplication.purge_after <= now), limit)
        purged = _null_answers(db, due, now)

        left = limit - purged
        more = purged >= limit
        if left > 0:
            # soft-deleted courses: the shortest retention (30 days) bounds the candidates; the root's setting decides
            oldest = now - timedelta(days=ids.RETENTION_DAYS_MIN)
            courses = db.execute(
                select(Course.id, Course.organization_id, Course.deleted_at)
                .join(EnrollmentApplication, EnrollmentApplication.course_id == Course.id)
                .where(Course.deleted_at.is_not(None), Course.deleted_at <= oldest,
                       EnrollmentApplication.purged_at.is_(None))
                .distinct().order_by(Course.deleted_at, Course.id).limit(DELETED_COURSES_PER_RUN)
            ).all()
            retention = _retention_by_org(db, {r[1] for r in courses}) if courses else {}
            for cid, org_id, deleted_at in courses:
                if left <= 0:
                    more = True
                    break
                if deleted_at.tzinfo is None:  # SQLite returns naive UTC
                    deleted_at = deleted_at.replace(tzinfo=timezone.utc)
                days = retention.get(org_id, ids.RETENTION_DAYS_DEFAULT)
                if deleted_at + timedelta(days=days) > now:
                    continue
                n = _null_answers(db, _claim(db, EnrollmentApplication.course_id == cid, left), now)
                purged += n
                left -= n
                if left <= 0:
                    more = True
        db.commit()
        if purged:
            logger.info("application purge", extra={"purged": purged, "more": more})  # counts only
        return PurgeOut(purged=purged, remaining=more, ran_at=now)
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()


def reset_throttle() -> None:
    """Tests: forget the last opportunistic run of this process."""
    global _last_run
    with _lock:
        _last_run = 0.0


def due_for_opportunistic_run() -> bool:
    """True at most once per `PURGE_OPPORTUNISTIC_INTERVAL_S` per process (claims the slot)."""
    global _last_run
    now = time.monotonic()
    with _lock:
        if _last_run and now - _last_run < ids.PURGE_OPPORTUNISTIC_INTERVAL_S:
            return False
        _last_run = now
        return True


def maybe_run() -> Optional[PurgeOut]:
    """Opportunistic, bounded purge (no cron in production). Never raises: a failed run is logged and retried after
    the next interval."""
    if not due_for_opportunistic_run():
        return None
    try:
        return run_purge(limit=OPPORTUNISTIC_LIMIT)
    except Exception:
        logger.warning("opportunistic application purge failed", exc_info=True)
        return None
