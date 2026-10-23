"""Concurrent publishes on real Postgres (design 7.9, publish part): never a duplicate or skipped version number.
Set LMS_PG_TEST_DATABASE_URL (and DATABASE_URL) to an empty Postgres database to run."""
import os
import threading

import pytest
from sqlalchemy import select

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.lms.assessments import publish as pub  # noqa: E402
from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentVersion  # noqa: E402
from app.lms.courses.models import Course  # noqa: E402
from tests.lms.factories import make_assessment, make_bank, make_course, make_question, make_user  # noqa: E402


def run_publishers(course_id, aid, owner_id, n=6, confirm=True):
    results, errors = [], []
    barrier = threading.Barrier(n)

    def work():
        s = SessionLocal()
        try:
            from app.models.user import User

            user = s.get(User, owner_id)
            ctx = AuthzContext(user, s, enrollment_role_resolver(s, user.id))
            course = s.get(Course, course_id)
            barrier.wait()
            r = pub.publish(s, ctx, course, aid, confirm=confirm)
            results.append((r.version.version_no, r.unchanged))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            s.close()

    ts = [threading.Thread(target=work) for _ in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return results, errors


def test_concurrent_publish_numbers_are_dense():
    s = SessionLocal()
    try:
        owner = make_user(s, teacher_status="approved")
        course = make_course(s, owner, status="published", languages=["en"], default_language="en")
        bank = make_bank(s, course, owner)
        q1, q2 = make_question(s, bank, owner), make_question(s, bank, owner)
        a = make_assessment(s, course, owner, sections=[{}], items=[q1], languages=["en"])
        aid, cid, oid = a.id, course.id, owner.id
        section_id = s.execute(select(AssessmentItem.section_id).where(AssessmentItem.assessment_id == aid)).scalar_one()

        results, errors = run_publishers(cid, aid, oid)
        assert not errors, errors
        assert {r[0] for r in results} == {1} and sum(1 for r in results if not r[1]) == 1
        s.expire_all()
        assert s.execute(select(AssessmentVersion.version_no).where(AssessmentVersion.assessment_id == aid)).scalars().all() == [1]

        s.add(AssessmentItem(assessment_id=aid, section_id=section_id, position=2, kind="question", question_id=q2.id,
                             points=1))
        s.commit()
        results, errors = run_publishers(cid, aid, oid)
        assert not errors, errors
        assert {r[0] for r in results} == {2} and sum(1 for r in results if not r[1]) == 1
        s.expire_all()
        nos = sorted(s.execute(select(AssessmentVersion.version_no).where(AssessmentVersion.assessment_id == aid)).scalars())
        assert nos == [1, 2] and s.get(Assessment, aid).last_version_no == 2
    finally:
        s.close()
