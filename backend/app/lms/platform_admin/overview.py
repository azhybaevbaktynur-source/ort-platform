"""FB8-5 S4: the admin overview's numbers (`GET /platform/overview`, decision D-FB8-5-4).

`/platform/summary` stays light because the admin shell calls it on every page; this answer is only for the overview
page. It is cached for 60 s per process (by `clock.now()`, so tests can move time), so repeated reloads do not re-scan
the attempts table. Four statements on a miss: one with the user and attempt counts as scalar subqueries, the Pro
summary, the storage row and the code reveals of the last hour; plus the database line (DB_STORAGE_REVIEW 7.4): the
stored measurement of the Services panel (`platform_settings`), re-measured here when older than 60 minutes (SQL only,
no provider call). The database line fails alone: any error gives `database: None` and the rest of the answer stays."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from threading import Lock
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.lms.access import admin as access_admin
from app.lms.attempts.models import Attempt
from app.lms.core import clock
from app.lms.files import usage
from app.lms.infra import capacity
from app.lms.teachers.models import TeacherRequest
from app.models.user import User

logger = logging.getLogger(__name__)

CACHE_SECONDS = 60
WINDOW = timedelta(days=7)
_FINISHED = ("submitted", "needs_review", "graded")

_lock = Lock()
_cache: Optional[tuple[datetime, dict]] = None  # (computed_at, answer)


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def _database(db: Session, now: datetime) -> Optional[dict]:
    """The stored measurement, refreshed when older than an hour; None when there is none and measuring fails."""
    value = None
    try:
        value = capacity.stored_measurement(db)
        when = capacity.measured_at(value) if value else None
        if when is None or now - when >= capacity.MEASUREMENT_MAX_AGE:
            value = capacity.measure_storage(db)
            db.commit()
    except Exception as e:  # the overview's other numbers must not depend on this line
        db.rollback()
        logger.warning("overview: database measurement failed (%s)", type(e).__name__)
    if not value:
        return None
    percent, fits = value.get("percent"), value.get("fits")
    number_ok = percent is None or (isinstance(percent, (int, float)) and not isinstance(percent, bool))
    fits_ok = fits is None or (isinstance(fits, int) and not isinstance(fits, bool))
    if not (number_ok and fits_ok):
        return None
    return {
        "level": capacity.db_level(percent, fits),  # today's thresholds, not the stored level
        "percent": percent, "fits": fits, "used_bytes": value.get("used_bytes"),
        "limit_bytes": value.get("limit_bytes"), "measured_at": capacity.measured_at(value),
    }


def _compute(db: Session, now: datetime) -> dict:
    since = now - WINDOW
    real_user = (User.is_test_student.is_(False), User.deleted_at.is_(None))
    users_total = select(func.count()).select_from(User).where(*real_user).scalar_subquery()
    active = (select(func.count(func.distinct(Attempt.user_id))).select_from(Attempt)
              .join(User, User.id == Attempt.user_id)
              .where(Attempt.started_at >= since, Attempt.is_preview.is_(False), *real_user).scalar_subquery())
    submitted = (select(func.count()).select_from(Attempt).join(User, User.id == Attempt.user_id)
                 .where(Attempt.submitted_at >= since, Attempt.is_preview.is_(False), Attempt.is_practice.is_(False),
                        Attempt.status.in_(_FINISHED), User.is_test_student.is_(False)).scalar_subquery())
    pending = (select(func.count()).select_from(TeacherRequest)
               .where(TeacherRequest.status == "pending").scalar_subquery())
    from app.lms.courses import listing  # step 3b S1: pending listings; courses unlisted by a teacher revoke (D10)

    catalog_pending, catalog_revoked = listing.overview_columns(since)
    u, a, s, p, cp, cr = db.execute(select(users_total, active, submitted, pending, catalog_pending,
                                           catalog_revoked)).one()
    reveals = access_admin.reveals_last_hour(db, now)
    return {
        "users_total": int(u or 0),
        "active_students_7d": int(a or 0),
        "pro_active": access_admin.pro_summary(db, now=now)["active"],
        "attempts_submitted_7d": int(s or 0),
        "pending_teacher_requests": int(p or 0),
        "catalog_pending": int(cp or 0),
        "catalog_revoked_7d": int(cr or 0),
        "storage_level": usage.level(usage.stored_totals(db)[0]),
        "reveals_last_hour": reveals,
        "reveal_alert": reveals > access_admin.REVEAL_ALERT_PER_HOUR,
        "database": _database(db, now),
    }


def overview(db: Session) -> dict:
    global _cache
    now = clock.now()
    with _lock:
        hit = _cache
    if hit is not None and timedelta(0) <= now - hit[0] < timedelta(seconds=CACHE_SECONDS):
        return {**hit[1], "computed_at": hit[0]}
    out = _compute(db, now)
    with _lock:
        _cache = (now, out)
    return {**out, "computed_at": now}
