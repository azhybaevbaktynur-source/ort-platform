"""Run the maintenance tasks (DB_STORAGE_REVIEW 5) and remember the last run.

`run()` runs the tasks in order, each in its own session and transaction; a failing task is logged (counts and its key
only), rolled back and listed in `errors`, and the others still run. The result is stored under the `platform_settings`
key `maintenance.last_run` (`{ran_at, dry_run, trigger, counts, errors}`); a token run has no actor, so it writes no audit
row (`admin_audit_log.actor_id` is NOT NULL); the admin's button is audited by its route.

Fallback when GitHub skips the schedule (Render Free has no cron): `maybe_schedule()` from the admin overview runs the
safe tasks (1-3) after the response, in production only, at most once per FALLBACK_INTERVAL per process and only when
the last applied run is older than FALLBACK_AFTER. Task 7 (measuring) is left out there: the overview measures on its
own when its stored figure is older than an hour (`platform_admin/overview.py`)."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import is_production
from app.db import session as db_session
from app.lms.access.models import PlatformSetting
from app.lms.core import clock
from app.lms.core.logging import get_logger
from app.lms.maintenance import tasks as t

logger = get_logger("app.lms.maintenance")

LAST_RUN_KEY = "maintenance.last_run"
FALLBACK_INTERVAL_S = 12 * 3600
FALLBACK_AFTER = timedelta(hours=24)

# (key, task, safe): in this order; `safe` tasks also run from the overview fallback
TASKS: list[tuple[str, Callable, bool]] = [
    ("attempt_sweep", t.attempt_sweep, True),
    ("application_purge", t.application_purge, True),
    ("phone_purge", t.phone_purge, True),
    ("code_note_purge", t.code_note_purge, True),
    ("user_tokens", t.user_tokens, True),
    ("pairing_codes", t.pairing_codes, True),
    ("email_changes", t.email_changes, True),
    ("rate_limits", t.rate_limits, True),
    ("unverified_accounts", t.unverified_accounts, False),
    ("preview_attempts", t.preview_attempts, False),
    ("test_student_attempts", t.student_view_attempts, False),
    ("test_student_files", t.student_view_files, False),
    ("retired_test_students", t.retired_student_view, False),
    ("measure_storage", t.measure_storage, False),
]
TASK_KEYS = [k for k, _, _ in TASKS]
SAFE_KEYS = [k for k, _, safe in TASKS if safe]

_lock = threading.Lock()
_last_fallback = 0.0  # time.monotonic() of the last fallback run in this process


def _store(db: Session, value: dict, now: datetime) -> None:
    t_ = PlatformSetting.__table__
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(t_).values(key=LAST_RUN_KEY, value=value, updated_at=now, updated_by_id=None)
    db.execute(stmt.on_conflict_do_update(index_elements=[t_.c.key],
                                          set_={"value": value, "updated_at": now, "updated_by_id": None}))


def last_run(db: Session) -> Optional[dict]:
    value = db.execute(select(PlatformSetting.value).where(PlatformSetting.key == LAST_RUN_KEY)).scalar()
    return value if isinstance(value, dict) and "ran_at" in value else None


def run(*, dry_run: bool, trigger: str, only: Optional[list[str]] = None,
        session_factory: Optional[Callable[[], Session]] = None, now: Optional[datetime] = None) -> dict:
    """One maintenance run. `dry_run` counts only; `only` limits the tasks (the fallback). Never raises for a task."""
    factory = session_factory or db_session.SessionLocal
    now = now or clock.now()
    counts: dict[str, dict] = {}
    errors: list[str] = []
    for key, task, _safe in TASKS:
        if only is not None and key not in only:
            continue
        db = factory()
        try:
            out = task(db, now=now, apply=not dry_run)
            db.commit()
            counts[key] = out
            logger.info("maintenance task", extra={"task": key, "dry_run": dry_run, **out})  # counts only
        except Exception as e:
            db.rollback()
            errors.append(key)
            logger.warning("maintenance task failed", extra={"task": key, "error": type(e).__name__})
        finally:
            db.close()
    value = {"ran_at": now.isoformat(), "dry_run": dry_run, "trigger": trigger, "counts": counts, "errors": errors}
    db = factory()
    try:
        _store(db, value, now)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("maintenance: storing the last run failed", extra={"error": type(e).__name__})
    finally:
        db.close()
    return value


# ------------------------------------------------------------------------------------------- overview fallback


def reset_fallback() -> None:
    """Tests: forget the last fallback run of this process."""
    global _last_fallback
    with _lock:
        _last_fallback = 0.0


def _claim_fallback_slot() -> bool:
    global _last_fallback
    now = time.monotonic()
    with _lock:
        if _last_fallback and now - _last_fallback < FALLBACK_INTERVAL_S:
            return False
        _last_fallback = now
        return True


def _recent_applied_run(db: Session, now: datetime) -> bool:
    value = last_run(db)
    if not value or value.get("dry_run"):
        return False
    try:
        ran_at = datetime.fromisoformat(value["ran_at"])
    except (TypeError, ValueError):
        return False
    return timedelta(0) <= now - ran_at < FALLBACK_AFTER


def run_fallback() -> Optional[dict]:
    """The safe tasks, applied, unless a run was applied within FALLBACK_AFTER. Never raises."""
    try:
        now = clock.now()
        db = db_session.SessionLocal()
        try:
            if _recent_applied_run(db, now):
                return None
        finally:
            db.close()
        return run(dry_run=False, trigger="fallback", only=SAFE_KEYS, now=now)
    except Exception as e:
        logger.warning("maintenance fallback failed", extra={"error": type(e).__name__})
        return None


def maybe_schedule(background: BackgroundTasks) -> bool:
    """Production only (tests and dev never clean behind a test's back); at most once per interval per process."""
    if not is_production() or not _claim_fallback_slot():
        return False
    background.add_task(run_fallback)
    return True
