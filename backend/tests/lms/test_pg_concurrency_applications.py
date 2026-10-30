"""Phase 9 S4 races on real Postgres (PHASE_9_DESIGN 4.7, 7, invariant 6): two approvals of one application, approvals
racing the enrollment limit (and a code join), submit racing withdraw, parallel submits of one user, and two purge
runs claiming rows with SKIP LOCKED. Set LMS_PG_TEST_DATABASE_URL (an empty database)."""
import os
import threading
import uuid
from datetime import timedelta

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine, delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.core import clock  # noqa: E402
from app.lms.core.errors import LMSError  # noqa: E402
from app.lms.core.models import utcnow  # noqa: E402
from app.lms.core.ratelimit import RateLimitBucket  # noqa: E402
from app.lms.courses import service as course_svc  # noqa: E402
from app.lms.courses.models import Course  # noqa: E402
from app.lms.courses.schemas import CourseCreateIn  # noqa: E402
from app.lms.enrollment_forms import applications as apps  # noqa: E402
from app.lms.enrollment_forms import purge  # noqa: E402
from app.lms.enrollment_forms import service as form_svc  # noqa: E402
from app.lms.enrollment_forms.models import EnrollmentApplication  # noqa: E402
from app.lms.enrollment_forms.schemas import ApplicationSubmitIn, DecisionIn, FormCreateIn  # noqa: E402
from app.lms.enrollments import service as enr_svc  # noqa: E402
from app.lms.enrollments.models import Enrollment  # noqa: E402
from app.models.user import User  # noqa: E402

FIELDS = [{"key": "full_name", "type": "short_text", "label": {"en": "Name"}, "required": True,
           "pii_category": "personal"}]


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
    with pg_engine.begin() as c:
        c.execute(delete(RateLimitBucket.__table__))
    return pg_engine


def _ctx(s, uid):
    return AuthzContext(s.get(User, uid), s, enrollment_role_resolver(s, uid))


def _mk_user(s: Session, teacher=False) -> str:
    uid = f"usr_{uuid.uuid4().hex[:12]}"
    s.add(User(id=uid, email=f"{uid}@test.example", password_hash="x", email_verified=True,
               teacher_status="approved" if teacher else "none"))
    s.commit()
    if teacher:
        from app.lms.organizations.defaults import ensure_personal_org

        ensure_personal_org(s.connection(), uid, None, False, with_membership=True)
        s.commit()
    return uid


def _form_course(pg, *, limit=None, mode="form_review"):
    """(course_id, form_id, owner_id, join_code): published catalog course with an active form."""
    with Session(pg) as s:
        owner = _mk_user(s, teacher=True)
        c = course_svc.create_course(s, s.get(User, owner), CourseCreateIn(
            title={"en": "C"}, languages=["en"], default_language="en", enrollment_limit=limit))
        cid, code = c.id, c.join_code
        c.status, c.visibility, c.published_at = "published", "catalog", utcnow()
        s.commit()
        ctx = _ctx(s, owner)
        course = course_svc.load_course(s, cid)
        form = form_svc.create_draft(s, ctx, course, FormCreateIn.model_validate({"fields": FIELDS}))
        form_svc.activate(s, ctx, course_svc.load_course(s, cid), form.id)
        course = course_svc.load_course(s, cid)
        course.enrollment_mode = mode
        s.commit()
        return cid, form.id, owner, code


def _submit(s, uid, cid, fid):
    return apps.submit(s, _ctx(s, uid), cid, ApplicationSubmitIn(form_id=fid, answers={"full_name": "N"}), None)


def _run(pg, jobs):
    barrier = threading.Barrier(len(jobs))
    out = [None] * len(jobs)

    def worker(i, job):
        with Session(pg) as s:
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


def _students(pg, cid) -> int:
    with Session(pg) as s:
        return s.scalar(select(func.count()).select_from(Enrollment).where(
            Enrollment.course_id == cid, Enrollment.role == "student", Enrollment.state == "active"))


def _status(pg, app_id) -> str:
    with Session(pg) as s:
        return s.get(EnrollmentApplication, app_id).status


def test_two_approvals_of_one_application_give_one_enrollment(pg):
    """Each round: two parallel approvals of the same fresh application (two tabs); exactly one wins."""
    cid, fid, owner, _ = _form_course(pg)
    for _ in range(5):
        with Session(pg) as s:
            uid = _mk_user(s)
            app_id = _submit(s, uid, cid, fid).id

        def approve(s, app_id=app_id):
            return apps.approve(s, _ctx(s, owner), course_svc.load_course(s, cid), app_id, DecisionIn()).status

        out = _run(pg, [approve, approve])
        assert sorted(out) == [("lms", "application_decided"), ("ok", "approved")], out
    assert _students(pg, cid) == 5


def test_approvals_racing_the_enrollment_limit_and_code_joins(pg):
    """Six pending applications, then the course leaves the form mode (pending applications stay decidable) for
    invite_code: six approvals and four code joins race for five seats under the same course lock."""
    cid, fid, owner, code = _form_course(pg, limit=5)
    app_ids = []
    with Session(pg) as s:
        for _ in range(6):
            app_ids.append(_submit(s, _mk_user(s), cid, fid).id)
        joiners = [_mk_user(s) for _ in range(4)]
        s.get(Course, cid).enrollment_mode = "invite_code"
        s.commit()

    def approve(app_id):
        return lambda s: apps.approve(s, _ctx(s, owner), course_svc.load_course(s, cid), app_id, DecisionIn()).status

    def join(uid):
        return lambda s: enr_svc.join_by_code(s, s.get(User, uid), code, None)[2]

    out = _run(pg, [approve(a) for a in app_ids] + [join(u) for u in joiners])
    assert not [r for r in out if r[0] == "exc"], out
    wins = [r for r in out if r[0] == "ok"]
    assert len(wins) == 5, out
    assert {r for r in out[:6] if r[0] == "lms"} <= {("lms", "course_full")}
    assert _students(pg, cid) == 5
    approved = sum(1 for r in out[:6] if r == ("ok", "approved"))
    statuses = sorted(_status(pg, a) for a in app_ids)
    assert statuses == ["approved"] * approved + ["pending"] * (6 - approved)  # course_full leaves it pending


def test_form_auto_submits_racing_the_limit(pg):
    cid, fid, owner, _ = _form_course(pg, limit=2, mode="form_auto")
    with Session(pg) as s:
        uids = [_mk_user(s) for _ in range(8)]
    out = _run(pg, [(lambda s, u=u: _submit(s, u, cid, fid).status) for u in uids])
    assert sorted(v for _, v in out) == ["approved"] * 2 + ["pending"] * 6, out
    assert _students(pg, cid) == 2


def test_submit_racing_withdraw(pg):
    cid, fid, owner, _ = _form_course(pg)
    for _ in range(5):
        with Session(pg) as s:
            uid = _mk_user(s)
            first = _submit(s, uid, cid, fid).id

        def withdraw(s, first=first, uid=uid):
            return apps.withdraw(s, _ctx(s, uid), cid, first).status

        def resubmit(s, uid=uid):
            return _submit(s, uid, cid, fid).status

        out = _run(pg, [withdraw, resubmit])
        assert out[0] == ("ok", "withdrawn"), out
        assert out[1] in (("ok", "pending"), ("lms", "application_pending")), out
        with Session(pg) as s:
            pending = s.scalar(select(func.count()).select_from(EnrollmentApplication).where(
                EnrollmentApplication.course_id == cid, EnrollmentApplication.user_id == uid,
                EnrollmentApplication.status == "pending"))
        assert pending == (1 if out[1][0] == "ok" else 0)


def test_parallel_submits_of_one_user_give_one_pending(pg):
    cid, fid, owner, _ = _form_course(pg)
    with Session(pg) as s:
        uid = _mk_user(s)
    out = _run(pg, [(lambda s: _submit(s, uid, cid, fid).status) for _ in range(6)])
    assert sorted(out) == [("lms", "application_pending")] * 5 + [("ok", "pending")], out


def test_two_purge_runs_never_purge_a_row_twice(pg):
    cid, fid, owner, _ = _form_course(pg)
    with Session(pg) as s:
        ids_ = [_submit(s, _mk_user(s), cid, fid).id for _ in range(30)]
        for a in s.execute(select(EnrollmentApplication).where(EnrollmentApplication.id.in_(ids_))).scalars():
            a.status, a.purge_after = "rejected", utcnow() - timedelta(minutes=1)
        s.commit()
    later = clock.now()
    out = _run(pg, [(lambda s: purge.run_purge(s, limit=20, now=later).purged) for _ in range(3)])
    assert all(k == "ok" for k, _ in out), out
    assert sum(v for _, v in out) == 30
    with Session(pg) as s:
        left = s.scalar(select(func.count()).select_from(EnrollmentApplication).where(
            EnrollmentApplication.id.in_(ids_), EnrollmentApplication.answers.is_not(None)))
    assert left == 0
