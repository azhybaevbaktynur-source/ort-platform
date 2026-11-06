"""Deny-by-default route allow-list of a test student (PUR-3), called from `core/deps.get_lms_user`.

Decided on the matched route template, never on the raw path, so every spelling of a path is the same decision. A route
that is not listed answers 403 `test_student_forbidden`, whatever its own policy says: a new route stays closed until
it is added here. `tests/lms/test_student_view.py` fails when a route a student may use is neither listed nor in its
deliberately closed set."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import route_template
from app.lms.core.errors import Forbidden
from app.lms.enrollments.models import Enrollment

_V = "/api/v1"
_C = f"{_V}/courses/{{course_id}}"  # a course route: only the test student's own course
_A = f"{_C}/assessments/{{assessment_id}}"
_G = f"{_C}/assignments/{{assignment_id}}"
_I = f"{_C}/modules/{{module_id}}/items/{{item_id}}"
_T = f"{_V}/attempts/{{attempt_id}}"  # an attempt route: `attempt_owner`, so only the test student's own attempts

TEST_STUDENT_ROUTES: frozenset[tuple[str, str]] = frozenset({
    # --- Phase 10 S4 begin --- (progress, mistakes notebook, goal: the test student sees their own)
    ("GET", f"{_C}/my/progress"),
    ("GET", f"{_C}/my/mistakes"),
    ("PUT", f"{_C}/my/goal"),
    ("DELETE", f"{_C}/my/goal"),
    # --- Phase 10 S4 end ---
    # --- Exam prep S2: the exam-prep page and the student's own target ---
    ("GET", f"{_C}/exam-prep"),
    ("GET", f"{_C}/exam-prep/library"),
    ("PUT", f"{_C}/exam-prep/goal"),
    ("DELETE", f"{_C}/exam-prep/goal"),
    # the app frame and the student home
    ("GET", f"{_V}/auth/me"),
    ("GET", f"{_V}/me/lms"),
    ("GET", f"{_V}/me/home"),
    ("GET", f"{_V}/me/home/courses"),
    ("GET", f"{_V}/courses"),
    # own course: reads of the student screens
    ("GET", _C),
    ("GET", f"{_C}/people"),
    ("GET", f"{_C}/grading"),
    ("GET", f"{_C}/grades/mine"),
    ("GET", f"{_C}/modules"),
    ("GET", f"{_C}/pages"),
    ("GET", f"{_C}/pages/{{page_id}}"),
    ("GET", f"{_C}/announcements"),
    ("GET", f"{_C}/announcements/{{announcement_id}}"),
    ("GET", f"{_C}/course-files"),
    ("GET", f"{_C}/course-files/{{file_id}}/content"),
    ("GET", f"{_C}/course-files/{{file_id}}/download"),
    ("GET", f"{_C}/assessments"),
    ("GET", _A),
    ("GET", f"{_A}/attempts/mine"),
    ("GET", f"{_C}/assignments"),
    ("GET", _G),
    ("GET", f"{_G}/mine"),
    ("GET", f"{_C}/practice"),  # Phase 10 S2
    ("GET", f"{_C}/submissions/{{submission_id}}/files/{{asset_id}}"),
    # own course: what a student does
    ("POST", f"{_A}/attempts"),
    ("POST", f"{_G}/submissions"),
    ("POST", f"{_G}/submissions/files"),
    ("POST", f"{_I}/done"),
    ("POST", f"{_I}/view"),
    # own attempts
    ("GET", _T),
    ("GET", f"{_T}/content"),
    ("GET", f"{_T}/result"),
    ("GET", f"{_T}/review"),
    ("PUT", f"{_T}/answers"),
    ("POST", f"{_T}/sections/{{pos}}/close"),
    ("POST", f"{_T}/submit"),
    ("POST", f"{_T}/items/{{position}}/check"),  # Phase 10 S2
    ("GET", f"{_T}/practice-feedback"),  # Phase 10 S2
    # images and files in course content (`/media/{name}` is public and has no user at all)
    ("GET", f"{_V}/assets/{{asset_id}}/content"),
})


def _denied() -> Forbidden:
    return Forbidden("Not available in student view", code="test_student_forbidden")


def _own_course_id(db: Session, user) -> Optional[uuid.UUID]:
    return db.execute(select(Enrollment.course_id).where(
        Enrollment.user_id == user.id, Enrollment.is_test_student.is_(True), Enrollment.state == "active")).scalar()


def enforce(request: Optional[Request], user, db: Session) -> None:
    """Raises 403 unless this request's matched route is listed and, for a course route, names the user's own course.
    A call without a request (not FastAPI's) has no route to allow."""
    template = route_template(request) if request is not None else None
    if template is None:
        raise _denied()
    method = "GET" if request.method == "HEAD" else request.method
    if (method, template) not in TEST_STUDENT_ROUTES:
        raise _denied()
    if template == _C or template.startswith(_C + "/"):
        try:
            course_id = uuid.UUID(str(request.path_params["course_id"]))
        except (KeyError, ValueError, TypeError):
            raise _denied() from None
        if course_id != _own_course_id(db, user):
            raise _denied()
