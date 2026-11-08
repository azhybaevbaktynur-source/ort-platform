"""`GET /me/bootstrap` (PERFORMANCE_AUDIT 5.2, slice S2): what the app shell needs on load, in one request.

Composition only, read-only: every part is the existing service function of the route the shell called before, so the
answer equals those routes' answers (`tests/lms/test_bootstrap.py`). One `get_lms_user` for all of them instead of one
per request; nothing is computed per row beyond what the parts already do.

- `me`: `GET /me/lms` (`teachers.router._me`).
- `pending_invitations`: the count of `GET /me/invitations` (`home.service._pending_invitations`, as `/me/home`).
- `privacy`: `GET /me/privacy` without its `requests` list (the banner reads the state and the needs only).
- `student`: only when the person learns somewhere or teaches nowhere (the student shell can be shown):
  `courses` = `GET /me/home/courses?limit=50`, `access` = `GET /me/access` (only with an exam-prep course: the shell
  shows the pass pill only then), `lesson_courses` = `GET /courses/{exam}/lesson-courses` per exam-prep course (the
  caller is its student, so `lesson_courses.require_member` holds).

Student view (a test student): no invitations, no privacy state and no pass, as the routes it may not call."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.lms.access import router as access_router
from app.lms.access.schemas import MyAccessOut
from app.lms.core import clock
from app.lms.courses.lesson_courses import LessonCourseOut, lesson_courses
from app.lms.courses.models import Course
from app.lms.home import schemas as sch
from app.lms.home import service as home_svc
from app.lms.privacy import service as privacy_svc
from app.lms.privacy.schemas import NeedOut
from app.lms.teachers import router as teachers_router
from app.lms.teachers.schemas import MeOut
from app.models.user import User

_NS = {"MeOut": MeOut, "MyAccessOut": MyAccessOut, "LessonCourseOut": LessonCourseOut, "NeedOut": NeedOut}
sch.PrivacyBannerOut.model_rebuild(_types_namespace=_NS)
sch.BootstrapStudentOut.model_rebuild(_types_namespace=_NS)
sch.BootstrapOut.model_rebuild(_types_namespace=_NS)


def _teaches(me: MeOut) -> bool:
    return bool(me.is_teacher or me.can_create_courses or me.is_platform_admin)


def _privacy(db: Session, user: User) -> sch.PrivacyBannerOut:
    return sch.PrivacyBannerOut(age_band=user.age_band, consent_state=user.consent_state,
                                consent_due_at=user.consent_due_at, needs=privacy_svc.needs_for(db, user))


def _student(db: Session, user: User, test_student: bool) -> sch.BootstrapStudentOut:
    page = home_svc.courses_page(db, user, limit=sch.BOOTSTRAP_COURSES_LIMIT)
    exams = [c.id for c in page.items if c.student_layout == "exam_prep"]
    lessons: dict[str, list[LessonCourseOut]] = {}
    for exam_id in exams:
        exam = db.get(Course, exam_id)  # in the session already (the page loaded it): no statement
        if exam is not None:
            lessons[str(exam_id)] = lesson_courses(db, exam, user.id)
    access = access_router._my_access(db, user) if exams and not test_student else None
    return sch.BootstrapStudentOut(courses=page.items, access=access, lesson_courses=lessons)


def bootstrap(db: Session, user: User) -> sch.BootstrapOut:
    test_student = bool(getattr(user, "is_test_student", False))
    me = teachers_router._me(user)
    learns_here = me.has_student_enrollments or not _teaches(me)
    return sch.BootstrapOut(
        me=me,
        pending_invitations=0 if test_student else home_svc._pending_invitations(db, user, clock.now()),
        privacy=None if test_student else _privacy(db, user),
        student=_student(db, user, test_student) if learns_here else None,
    )
