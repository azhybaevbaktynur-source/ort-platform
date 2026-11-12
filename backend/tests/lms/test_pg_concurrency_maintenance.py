"""Maintenance on real Postgres (DB_STORAGE_REVIEW 5, slice D2): a row another transaction holds is skipped, not
waited for (`FOR UPDATE SKIP LOCKED`); two runs at once handle every due row exactly once; the append-only guards of
grade events and consent records let only the maintenance transaction through. Set LMS_PG_TEST_DATABASE_URL (an empty
database)."""
import os
import threading
import uuid
from datetime import timedelta, timezone
from decimal import Decimal

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.attempts.models import Attempt  # noqa: E402
from app.lms.core import clock  # noqa: E402
from app.lms.core.models import utcnow  # noqa: E402
from app.lms.enrollments.models import Enrollment  # noqa: E402
from app.lms.grading.models import AttemptGrade, GradeEvent  # noqa: E402
from app.lms.maintenance import service, tasks  # noqa: E402
from app.lms.privacy.models import ConsentRecord, PolicyVersion  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.lms.factories import enroll, make_submission, make_user  # noqa: E402
from tests.lms.grading_support import make_world, new_attempt  # noqa: E402


@pytest.fixture(scope="module")
def pg_engine():
    eng = create_engine(PG_URL, pool_size=20, max_overflow=0)
    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def pg(pg_engine, monkeypatch):
    monkeypatch.setattr(db_session, "engine", pg_engine)
    return pg_engine


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _previews(s, n):
    w = make_world(s)
    for _ in range(n):
        new_attempt(s, w, user=w.teacher, preview=True, status="graded", attempt_no=None)
    return w


def _unverified(s, n):
    now = utcnow()
    pv = PolicyVersion(kind="privacy", version=int(uuid.uuid4().int % 10**8), status="approved", body_en="x",
                       body_ky="x", body_ru="x", sha256="1" * 64, requires_reconsent=False, effective_at=now,
                       created_at=now)
    s.add(pv)
    s.commit()
    ids = []
    for _ in range(n):
        u = make_user(s)
        u.email_verified = False
        u.created_at = _naive(clock.now() - timedelta(days=120))
        s.add(ConsentRecord(user_id=u.id, granted_by_id=u.id, policy_version_id=pv.id, kind="privacy", locale="en",
                            source="signup"))
        s.commit()
        ids.append(u.id)
    return ids


def test_a_locked_row_is_skipped_not_waited_for(pg):
    Factory = sessionmaker(bind=pg, autoflush=False)
    with Factory() as s:
        w = _previews(s, 3)
        ids = list(s.execute(select(Attempt.id).where(Attempt.course_id == w.course.id)).scalars())
    holder = Factory()
    try:
        holder.execute(select(Attempt).where(Attempt.id == ids[0]).with_for_update())  # a request holds this row
        out = {}

        def work():
            with Factory() as s:
                s.execute(text("SET LOCAL lock_timeout = '5s'"))
                out["r"] = tasks.preview_attempts(s, now=clock.now(), apply=True)
                s.commit()

        t = threading.Thread(target=work)
        t.start()
        t.join(timeout=20)
        assert not t.is_alive() and out["r"] == {"examined": 2, "changed": 2}
    finally:
        holder.rollback()
        holder.close()
    with Factory() as s:
        assert list(s.execute(select(Attempt.id).where(Attempt.course_id == w.course.id)).scalars()) == [ids[0]]
        assert tasks.preview_attempts(s, now=clock.now(), apply=True)["changed"] == 1
        s.commit()


@pytest.mark.parametrize("task,seed,count", [
    (tasks.preview_attempts, lambda s: _previews(s, 30), lambda s: s.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.is_preview.is_(True)))),
    (tasks.unverified_accounts, lambda s: _unverified(s, 30), lambda s: s.scalar(
        select(func.count()).select_from(User).where(User.email_verified.is_(False)))),
])
def test_two_runs_at_once_handle_each_row_once(pg, monkeypatch, task, seed, count):
    Factory = sessionmaker(bind=pg, autoflush=False)
    with Factory() as s:
        seed(s)
        assert count(s) == 30
    monkeypatch.setattr(tasks, "BATCH", 20)
    monkeypatch.setattr(tasks, "USER_BATCH", 20)
    barrier = threading.Barrier(2)
    results, errors = [], []

    def work():
        try:
            with Factory() as s:
                barrier.wait(timeout=10)
                results.append(task(s, now=clock.now(), apply=True)["changed"])
                s.commit()
        except Exception as e:  # pragma: no cover - reported below
            errors.append(repr(e))

    threads = [threading.Thread(target=work) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == [] and len(results) == 2
    with Factory() as s:
        left = count(s)
    assert sum(results) + left == 30 and sum(results) >= 20  # nobody handled a row twice, nobody waited
    with Factory() as s:
        while task(s, now=clock.now(), apply=True)["changed"]:
            s.commit()
        s.commit()
        assert count(s) == 0


def test_append_only_guards_hold_outside_maintenance_and_the_student_view_run_passes_them(pg):
    Factory = sessionmaker(bind=pg, autoflush=False)
    with Factory() as s:
        w = make_world(s)
        tester = make_user(s)
        tester.is_test_student = True
        enr = enroll(s, w.course, tester, source="admin")
        enr.is_test_student = True
        s.commit()
        a = new_attempt(s, w, user=tester, status="graded", attempt_no=1, raw_score=Decimal("1"),
                        submitted_at=clock.now() - timedelta(hours=1))
        s.add(AttemptGrade(attempt_id=a.id, computed_at=utcnow()))
        s.commit()
        sub = make_submission(s, w.assessment, enr, kept_attempt_id=a.id)
        s.add(GradeEvent(submission_id=sub.id, course_id=w.course.id, event="regraded", attempt_id=a.id))
        s.commit()
        aid, enr_id = a.id, enr.id
    with Factory() as s:  # the PG trigger refuses a plain delete
        with pytest.raises(DBAPIError):
            s.execute(text("DELETE FROM grade_events WHERE attempt_id = :a"), {"a": aid})
        s.rollback()
    out = service.run(dry_run=False, trigger="test", only=["test_student_attempts"], session_factory=Factory)
    assert out["errors"] == [] and out["counts"]["test_student_attempts"]["changed"] == 1
    with Factory() as s:
        assert s.get(Attempt, aid) is None and s.get(Enrollment, enr_id).state == "active"
        assert s.execute(text("SELECT coalesce(current_setting('lms.allow_grade_purge', true), '')")).scalar() != "on"
