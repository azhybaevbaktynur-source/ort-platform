"""Student view races on real Postgres (UX_REWORK_DESIGN F): parallel entries and resets of one course end with exactly
one active test student, and every token the racers got belongs to a test student of that course. Set
LMS_PG_TEST_DATABASE_URL (an empty database)."""
import os
import threading

import jwt
import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.enrollments.models import Enrollment  # noqa: E402
from app.lms.student_view import service  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.lms.factories import enroll, make_course, make_user  # noqa: E402


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


def _race(pg, fn_for):
    """`n` staff of one course call `fn_for(i)` at the same moment. Returns (course_id, the token users)."""
    Session = sessionmaker(bind=pg, autoflush=False)
    n = 8
    with Session() as s:
        owner = make_user(s, teacher_status="approved")
        course = make_course(s, owner, status="published")
        cid = course.id
        staff = [owner.id]
        for _ in range(n - 1):
            ta = make_user(s)
            enroll(s, course, ta, role="assistant", source="owner")
            staff.append(ta.id)
    barrier = threading.Barrier(n)
    tokens, errors = [], []

    def work(i, uid):
        with Session() as s:
            ctx = AuthzContext(s.get(User, uid), s, enrollment_role_resolver(s, uid))
            try:
                barrier.wait()
                tokens.append(fn_for(i)(ctx, cid, None).access_token)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

    threads = [threading.Thread(target=work, args=(i, uid)) for i, uid in enumerate(staff)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert len(tokens) == n
    subs = {jwt.decode(t, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])["sub"] for t in tokens}
    return Session, cid, subs


def test_parallel_entries_make_one_test_student(pg):
    Session, cid, subs = _race(pg, lambda _i: service.enter)
    assert len(subs) == 1
    with Session() as s:
        rows = s.execute(select(Enrollment).where(Enrollment.course_id == cid,
                                                  Enrollment.is_test_student.is_(True))).scalars().all()
        assert [(e.state, e.user_id) for e in rows] == [("active", next(iter(subs)))]


def test_parallel_resets_and_entries_leave_one_active(pg):
    Session, cid, subs = _race(pg, lambda i: service.reset if i % 2 else service.enter)
    with Session() as s:
        rows = s.execute(select(Enrollment, User).join(User, User.id == Enrollment.user_id).where(
            Enrollment.course_id == cid, Enrollment.is_test_student.is_(True))).all()
        active = [(e, u) for e, u in rows if e.state == "active"]
        assert len(active) == 1 and active[0][1].disabled_at is None
        for e, u in rows:
            assert u.is_test_student
            assert (e.state == "active") == (u.disabled_at is None)  # retired on both sides, or on neither
        assert subs <= {u.id for _e, u in rows}
