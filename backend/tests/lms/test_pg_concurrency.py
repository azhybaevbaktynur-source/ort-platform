"""Concurrency tests on real Postgres. Set LMS_PG_TEST_DATABASE_URL (an empty database)."""
import os
import threading

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine  # noqa: E402

from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.core import ratelimit  # noqa: E402


@pytest.fixture(scope="module")
def pg_engine():
    eng = create_engine(PG_URL, pool_size=30, max_overflow=0)
    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def pg(pg_engine, monkeypatch):
    monkeypatch.setattr(db_session, "engine", pg_engine)
    return pg_engine


def test_ratelimit_parallel_hits_never_exceed_limit(pg):
    rule = ratelimit.Limit("conc", 10, 3600)
    n = 20
    barrier = threading.Barrier(n)
    results, errors = [], []

    def worker():
        try:
            barrier.wait()
            results.append(ratelimit.hit("conc-key", rule)[0])
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == n and sum(results) == 10


def test_ratelimit_does_not_deadlock_with_tight_app_pool(pg_engine, monkeypatch):
    import time

    from sqlalchemy import create_engine as ce, select
    from sqlalchemy.orm import sessionmaker

    tight = ce(PG_URL, pool_size=10, max_overflow=0, pool_timeout=5)
    monkeypatch.setattr(db_session, "engine", tight)
    assert ratelimit._engine() is not tight
    Session = sessionmaker(bind=tight)
    n, errs = 10, []
    barrier = threading.Barrier(n)

    def worker(i):
        db = Session()
        try:
            db.execute(select(1))  # holds every app-pool connection
            barrier.wait(timeout=10)
            ratelimit.hit(f"tight{i}", ratelimit.Limit("tight", 100, 60))
        except Exception as e:  # pragma: no cover
            errs.append(e)
        finally:
            db.close()

    t0 = time.time()
    ths = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(20)
    tight.dispose()
    assert not errs and time.time() - t0 < 8


# ---------------------------------------------------------------- S3: course join concurrency

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.lms.core.errors import LMSError  # noqa: E402
from app.lms.courses import service as course_svc  # noqa: E402
from app.lms.courses.models import Course  # noqa: E402
from app.lms.courses.schemas import CourseUpdateIn  # noqa: E402
from app.lms.enrollments import service as enr_svc  # noqa: E402
from app.lms.enrollments.models import Enrollment, EnrollmentEvent  # noqa: E402
from app.models.user import User  # noqa: E402


def _mk_user(s: Session, n: int, teacher=False) -> str:
    import uuid as _u
    uid = f"usr_{_u.uuid4().hex[:12]}"
    s.add(User(id=uid, email=f"{uid}@test.example", password_hash="x", role="student", email_verified=True,
               teacher_status="approved" if teacher else "none"))
    s.commit()
    return uid


def _mk_course(pg_engine, limit, status="published"):
    with Session(pg_engine) as s:
        owner = _mk_user(s, 0, teacher=True)
        owner_user = s.get(User, owner)
        from app.lms.courses.schemas import CourseCreateIn
        c = course_svc.create_course(s, owner_user, CourseCreateIn(
            title={"en": "C"}, languages=["en"], default_language="en", enrollment_limit=limit))
        c.status = status
        s.commit()
        return c.id, c.join_code, owner


def _run_parallel(pg_engine, jobs):
    """jobs: list of callables(Session) -> result. One Session per thread, released together."""
    barrier = threading.Barrier(len(jobs))
    out = [None] * len(jobs)

    def worker(i, job):
        with Session(pg_engine) as s:
            try:
                barrier.wait()
                out[i] = ("ok", job(s))
            except LMSError as e:
                out[i] = ("lms", e.code)
            except Exception as e:  # pragma: no cover
                out[i] = ("exc", repr(e))

    ts = [threading.Thread(target=worker, args=(i, j)) for i, j in enumerate(jobs)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


def test_parallel_joins_never_exceed_limit(pg):
    cid, code, _ = _mk_course(pg, 5)
    with Session(pg) as s:
        uids = [_mk_user(s, i) for i in range(20)]

    def job(uid):
        return lambda s: enr_svc.join_by_code(s, s.get(User, uid), code, None)[2]

    out = _run_parallel(pg, [job(u) for u in uids])
    assert sum(1 for k, _ in out if k == "ok") == 5, out
    assert [v for k, v in out if k != "ok"] == ["join_code_invalid"] * 15, out
    with Session(pg) as s:
        n = s.scalar(select(func.count()).select_from(Enrollment).where(
            Enrollment.course_id == cid, Enrollment.role == "student", Enrollment.state == "active"))
    assert n == 5


def test_parallel_duplicate_joins_create_one_row(pg):
    cid, code, _ = _mk_course(pg, None)
    with Session(pg) as s:
        uid = _mk_user(s, 0)
    out = _run_parallel(pg, [lambda s: enr_svc.join_by_code(s, s.get(User, uid), code, None)[2]] * 10)
    assert all(k == "ok" for k, _ in out), out
    assert sum(1 for _, already in out if already is False) == 1, out
    with Session(pg) as s:
        rows = s.scalars(select(Enrollment).where(Enrollment.user_id == uid)).all()
        evs = s.scalars(select(EnrollmentEvent).where(EnrollmentEvent.course_id == cid,
                                                      EnrollmentEvent.event == "joined")).all()
    assert len(rows) == 1 and len(evs) == 1


def test_joins_racing_with_limit_change_respect_stored_limit(pg):
    cid, code, owner = _mk_course(pg, 10)
    with Session(pg) as s:
        uids = [_mk_user(s, i) for i in range(6)]

    def join(uid):
        return lambda s: enr_svc.join_by_code(s, s.get(User, uid), code, None)[2]

    def change(s):
        user = s.get(User, owner)
        ctx = AuthzContext(user, s, enrollment_role_resolver(s, owner))
        return course_svc.update_course(s, ctx, s.get(Course, cid), CourseUpdateIn(enrollment_limit=3)).enrollment_limit

    out = _run_parallel(pg, [join(u) for u in uids] + [change])
    assert not [o for o in out if o[0] == "exc"], out
    with Session(pg) as s:
        course = s.get(Course, cid)
        n = s.scalar(select(func.count()).select_from(Enrollment).where(
            Enrollment.course_id == cid, Enrollment.role == "student", Enrollment.state == "active"))
    assert n <= course.enrollment_limit
