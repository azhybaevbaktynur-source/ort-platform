"""Two managers open a template's sandbox at the same time on real Postgres (PHASE_8B_DESIGN 5.1, 11): `ensure` runs
under `SELECT ... FOR UPDATE` of the template row and `uq_courses_sandbox_for_template_id` backs it, so every
racer ends with the same course, the same sample quiz and its own teacher enrollment. Set LMS_PG_TEST_DATABASE_URL
(an empty database)."""
import os
import threading

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.assessments.models import Assessment  # noqa: E402
from app.lms.audit.models import AdminAuditLog  # noqa: E402
from app.lms.courses.models import Course  # noqa: E402
from app.lms.enrollments.models import Enrollment  # noqa: E402
from app.lms.exam_templates import ids, sandbox  # noqa: E402
from app.lms.exam_templates import schemas as tsch  # noqa: E402
from app.lms.exam_templates import service  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.lms.exam_template_support import general_spec  # noqa: E402
from tests.lms.factories import make_user  # noqa: E402
from tests.lms.org_support import add_member, make_org  # noqa: E402


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


def test_parallel_ensure_yields_one_sandbox(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    n = 6
    with Session() as s:
        org = make_org(s, "Race school")
        admins = [make_user(s) for _ in range(n)]
        for u in admins:
            add_member(s, org, u, "org_admin")
        ctx = AuthzContext(admins[0], s, enrollment_role_resolver(s, admins[0].id))
        t = service.create(ctx, tsch.ExamTemplateCreateIn(owner_scope="organization", organization_id=org.id,
                                                          title={"en": "Race"}, draft_spec=general_spec()))
        tid, uids = t.id, [u.id for u in admins]
    barrier = threading.Barrier(n)
    results, errors = [], []

    def work(uid):
        with Session() as s:
            user = s.get(User, uid)
            ctx = AuthzContext(user, s, enrollment_role_resolver(s, uid))
            try:
                barrier.wait()
                out = sandbox.open_sandbox(ctx, tid, tsch.SandboxIn(language="en"))
                results.append((out.course_id, out.assessment_id))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

    ts = [threading.Thread(target=work, args=(uid,)) for uid in uids]
    for th in ts:
        th.start()
    for th in ts:
        th.join()
    assert not errors, errors
    assert len(results) == n and len(set(results)) == 1          # everyone got the same course and sample
    with Session() as s:
        courses = s.execute(select(Course).where(Course.sandbox_for_template_id == tid)).scalars().all()
        assert len(courses) == 1 and courses[0].id == results[0][0]
        samples = s.execute(select(Assessment).where(Assessment.course_id == courses[0].id)).scalars().all()
        assert len(samples) == 1 and samples[0].id == results[0][1]
        enr = s.execute(select(Enrollment).where(Enrollment.course_id == courses[0].id)).scalars().all()
        assert {e.user_id for e in enr} == set(uids)
        assert all((e.role, e.state, e.source) == ("teacher", "active", ids.SANDBOX_ENROLLMENT_SOURCE) for e in enr)
        assert s.execute(select(func.count()).select_from(AdminAuditLog).where(
            AdminAuditLog.action == ids.AUDIT_SANDBOX_CREATE, AdminAuditLog.target_id == str(tid))).scalar() == 1
        # the sample mirrors the draft (two sections, counts dropped) exactly once
        from app.lms.assessments.models import AssessmentSection

        secs = s.execute(select(AssessmentSection).where(AssessmentSection.assessment_id == samples[0].id)
                         .order_by(AssessmentSection.position)).scalars().all()
        assert [x.key for x in secs] == ["part_a", "part_b"]
        assert "min_items" not in secs[0].rules and "max_items" not in secs[0].rules
