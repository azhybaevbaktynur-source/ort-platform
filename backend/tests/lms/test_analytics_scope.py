"""Phase 10 S0: analytics.scope predicates and the analytics.read grants."""
import pytest
from sqlalchemy import func, select

from app.core.authz import A, ALL_ACTIONS, CONCLUDED_ACTIONS, ORG_ADMIN_ACTIONS, READ_ONLY_ACTIONS, ROLE_GRANTS
from app.lms.analytics.scope import counted_attempt, final_attempt, percent_bucket
from app.lms.attempts.models import Attempt
from tests.lms.factories import (
    enroll, make_assessment, make_assessment_version, make_attempt, make_course, make_user,
)
from tests.lms.s3_support import db  # noqa: F401


def test_counted_attempt_drops_preview_void_in_progress_and_test_students(db):
    owner = make_user(db, teacher_status="approved")
    course = make_course(db, owner)
    a = make_assessment(db, course, owner)
    v = make_assessment_version(db, a, owner)
    s1, s2, s3, s4, s5, ts, rts = (make_user(db) for _ in range(7))
    keep = make_attempt(db, a, v, s1, status="graded")
    keep2 = make_attempt(db, a, v, s2, status="needs_review")
    make_attempt(db, a, v, s3, status="void")
    make_attempt(db, a, v, s4, status="in_progress")
    make_attempt(db, a, v, s5, status="graded", is_preview=True)
    for user, state in ((ts, "active"), (rts, "removed")):
        enr = enroll(db, course, user, state=state)
        enr.is_test_student = True
        db.commit()
        make_attempt(db, a, v, user, enrollment=enr, status="graded")
    t = Attempt.__table__
    counted = set(db.execute(select(t.c.id).where(counted_attempt(t))).scalars())
    assert counted == {keep.id, keep2.id}
    final = db.execute(select(func.count()).select_from(t).where(final_attempt(t))).scalar()
    assert final == 4  # graded, needs_review and the two test-student attempts; no preview, void, in-progress


@pytest.mark.parametrize("points,possible,bucket", [
    (0, 10, 0), (1, 10, 1), (9, 10, 9), (10, 10, 9), (5, 10, 5), (0, 0, 0), (19, 20, 9), (1, 20, 0),
])
def test_percent_bucket(db, points, possible, bucket):
    assert db.execute(select(percent_bucket(points, possible))).scalar() == bucket


def test_analytics_read_grants():
    assert A.ANALYTICS_READ in ALL_ACTIONS
    assert A.ANALYTICS_READ in ROLE_GRANTS["teacher"] and A.ANALYTICS_READ in ROLE_GRANTS["assistant"]
    assert A.ANALYTICS_READ not in ROLE_GRANTS["student"]
    assert A.ANALYTICS_READ in READ_ONLY_ACTIONS and A.ANALYTICS_READ in CONCLUDED_ACTIONS
    assert A.ANALYTICS_READ in ORG_ADMIN_ACTIONS
    assert A.CONTENT_READ_ADMIN not in ORG_ADMIN_ACTIONS
