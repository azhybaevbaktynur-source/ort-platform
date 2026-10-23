"""Shared world for the G2 submission / action / regrade tests (7.4, 7.5, 7.10).

Attempts are inserted directly (status `submitted`) and scored with `factories.grade_attempt`, which runs the
registered hooks like the engine does. Services are called with an AuthzContext built like `get_authz`."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.lms.attempts.models import Attempt
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import AttemptGrade, GradeEvent, Submission
from app.models.user import User
from tests.lms.factories import (
    enroll, grade_attempt, make_assessment, make_assessment_version, make_attempt, make_course, make_user,
)

TEN = Decimal("10.00")


def ctx_for(db, user) -> AuthzContext:
    u = db.get(User, user.id)
    return AuthzContext(u, db, enrollment_role_resolver(db, u.id))


def sworld(db, *, n_students: int = 1, score_policy: str = "highest", scheme_version_id=None,
           grade_release: str = "auto", due_at: Optional[datetime] = None, late_policy: Optional[dict] = None,
           course_status: str = "published") -> SimpleNamespace:
    teacher = make_user(db, teacher_status="approved", display_name="Teacher T")
    course = make_course(db, teacher, status=course_status, late_policy=late_policy)
    students = []
    for i in range(n_students):
        s = make_user(db, display_name=f"Student {i}")
        enroll(db, course, s)
        students.append(s)
    a = make_assessment(db, course, teacher, score_policy=score_policy, grading_scheme_version_id=scheme_version_id,
                        grade_release=grade_release, due_at=due_at, allowed_attempts=10)
    v = make_assessment_version(db, a, teacher, snapshot={"schema": 1, "languages": ["en"], "sections": [],
                                                         "slots": {"en": []}})
    return SimpleNamespace(teacher=teacher, course=course, students=students, student=students[0] if students else None,
                           assessment=a, version=v)


def sections_result(*secs) -> dict:
    """result JSON like Phase 3 (`[(pos, key, raw, possible), ...]`)."""
    return {"sections": [{"pos": p, "key": k, "raw": f"{Decimal(r):.2f}", "possible": f"{Decimal(n):.2f}",
                          "answered": 0, "correct": 0} for p, k, r, n in secs], "pending_review": 0}


def new_attempt(db, w, student, no: Optional[int], *, possible=TEN, preview: bool = False,
                result: Optional[dict] = None, status: str = "submitted") -> Attempt:
    return make_attempt(db, w.assessment, w.version, student, attempt_no=None if preview else no,
                        is_preview=preview, points_possible=Decimal(possible), item_count=0, status=status,
                        result=result if result is not None else sections_result((1, "a", 0, possible)))


def scored(db, w, student, no, raw, *, possible=TEN, status="graded", submitted_at=None, preview=False,
           result=None) -> Attempt:
    att = new_attempt(db, w, student, no, possible=possible, preview=preview, result=result)
    if result is None:
        att.result = sections_result((1, "a", raw, possible))
    return grade_attempt(db, att, raw, status=status, submitted_at=submitted_at)


def submission_of(db, w, student) -> Optional[Submission]:
    db.expire_all()
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == w.course.id,
                                              Enrollment.user_id == student.id)).scalar_one()
    return db.execute(select(Submission).where(Submission.enrollment_id == enr.id,
                                               Submission.assessment_id == w.assessment.id)).scalar_one_or_none()


def grades_of(db, attempt_ids) -> dict:
    db.expire_all()
    return {g.attempt_id: g for g in db.execute(
        select(AttemptGrade).where(AttemptGrade.attempt_id.in_(list(attempt_ids)))).scalars()}


def events_of(db, submission_id) -> list[GradeEvent]:
    db.expire_all()
    return list(db.execute(select(GradeEvent).where(GradeEvent.submission_id == submission_id)
                           .order_by(GradeEvent.created_at, GradeEvent.id)).scalars())
