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

Student view (a test student): no invitations, no privacy state and no pass, as the routes it may not call.
A platform admin who must set up two-step login (`mfa.gate.must_enroll`): `me` only, as the shell got before when every
other part answered 403 `mfa_enrollment_required` (the gate opens this route only for that).

PERFORMANCE_AUDIT P2 (fix round 2026-11-12, §10.2 item 2): `?include=home` adds the student home's own reads, so a cold
home is one request: `home` = `GET /me/home`, and for the home's exam course (`course`, the one this device remembers,
when it is one of the student's exam-prep courses, else the first of them, as the shell picks it) `exam_prep` =
`GET /courses/{id}/exam-prep`, behind the same checks as that route. Only with `student` (never for people who teach,
never under the two-step gate). A refusal of the exam course's part leaves that part out (the page asks its route and
shows the route's answer); the home itself stays.

STUDENT_IA_DESIGN 6.2 (step 3a S1): `home` reuses the `student.courses` page (same cards, same `modules_next` rows) when
it holds every course, so the cards are read once; `activity` is the 7-day activity over all the student's courses
(`student.courses`, the `ActivityOut` of `my/activity?days=7` counted across them) under the key `"all"`
(`BOOTSTRAP_ACTIVITY_ALL`), with or without an exam course."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.lms.access import router as access_router
from app.lms.access.schemas import MyAccessOut
from app.lms.core import clock
from app.lms.core.errors import LMSError
from app.lms.courses.lesson_courses import LessonCourseOut, lesson_courses
from app.lms.courses.models import Course
from app.lms.exam_prep import router as exam_prep_router
from app.lms.exam_prep import service as exam_prep_svc
from app.lms.exam_prep.schemas import ExamPrepOut
from app.lms.home import schemas as sch
from app.lms.home import service as home_svc
from app.lms.mfa import gate as mfa_gate
from app.lms.privacy import service as privacy_svc
from app.lms.privacy.schemas import NeedOut
from app.lms.progress import service as progress_svc
from app.lms.progress.schemas import ActivityOut
from app.lms.student_view import allowlist as student_view_allowlist
from app.lms.teachers import router as teachers_router
from app.lms.teachers.schemas import MeOut
from app.models.user import User

_NS = {"MeOut": MeOut, "MyAccessOut": MyAccessOut, "LessonCourseOut": LessonCourseOut, "NeedOut": NeedOut,
       "ExamPrepOut": ExamPrepOut, "ActivityOut": ActivityOut}
sch.PrivacyBannerOut.model_rebuild(_types_namespace=_NS)
sch.BootstrapStudentOut.model_rebuild(_types_namespace=_NS)
sch.BootstrapOut.model_rebuild(_types_namespace=_NS)


def _teaches(me: MeOut) -> bool:
    return bool(me.is_teacher or me.can_create_courses or me.is_platform_admin)


def _privacy(db: Session, user: User) -> sch.PrivacyBannerOut:
    return sch.PrivacyBannerOut(age_band=user.age_band, consent_state=user.consent_state,
                                consent_due_at=user.consent_due_at, needs=privacy_svc.needs_for(db, user))


def _student(db: Session, user: User, test_student: bool) -> tuple[sch.BootstrapStudentOut, tuple]:
    page, picks = home_svc.courses_page_and_picks(db, user, limit=sch.BOOTSTRAP_COURSES_LIMIT)
    exams = [c.id for c in page.items if c.student_layout == "exam_prep"]
    lessons: dict[str, list[LessonCourseOut]] = {}
    for exam_id in exams:
        exam = db.get(Course, exam_id)  # in the session already (the page loaded it): no statement
        if exam is not None:
            lessons[str(exam_id)] = lesson_courses(db, exam, user.id)
    access = access_router._my_access(db, user) if exams and not test_student else None
    return sch.BootstrapStudentOut(courses=page.items, access=access, lesson_courses=lessons), (page, picks)


def _parse_id(raw: Optional[str]) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None  # a stale or broken remembered id: the first exam course, as the shell does


def _home(db: Session, user: User, student: sch.BootstrapStudentOut, page: tuple, course: Optional[str]) -> dict:
    """PERFORMANCE_AUDIT P2: `/me/home` and the home exam course's exam-prep page; 3a S1: the cross-course activity."""
    now = clock.now()
    activity = progress_svc.activity_in(db, [c.id for c in student.courses], user.id,
                                        days=sch.BOOTSTRAP_HOME_ACTIVITY_DAYS, now=now)
    parts: dict = {"home": home_svc.home(db, user, page=page), "exam_prep": {},
                   "activity": {sch.BOOTSTRAP_ACTIVITY_ALL: activity}}
    exams = [c.id for c in student.courses if c.student_layout == "exam_prep"]
    wanted = _parse_id(course)
    pick = wanted if wanted in exams else (exams[0] if exams else None)
    if pick is None:
        return parts
    if getattr(user, "is_test_student", False) and pick != student_view_allowlist._own_course_id(db, user):
        return parts  # Student view: course routes answer for the test student's own course only (the allow-list's rule)
    ctx = AuthzContext(user, db, enrollment_role_resolver(db, user.id))
    try:
        exam = exam_prep_router._course(ctx, pick)  # the exam-prep route's own checks
    except LMSError:
        return parts
    parts["exam_prep"][str(pick)] = exam_prep_svc.page(db, exam, user.id, now=now)
    return parts


def bootstrap(db: Session, user: User, *, include_home: bool = False, course: Optional[str] = None) -> sch.BootstrapOut:
    test_student = bool(getattr(user, "is_test_student", False))
    me = teachers_router._me(user)
    if mfa_gate.must_enroll(user):
        return sch.BootstrapOut(me=me, pending_invitations=0, privacy=None, student=None)
    # owner decision 2026-11-12 (fix round 1e): people who teach have no Learning area, whatever student enrolments they
    # still have (the same rule as `hidesLearning` in frontend/src/lib/lms/shellKind.ts), so no student data for them
    learns_here = not _teaches(me)
    student, page = _student(db, user, test_student) if learns_here else (None, None)
    return sch.BootstrapOut(
        me=me,
        pending_invitations=0 if test_student else home_svc._pending_invitations(db, user, clock.now()),
        privacy=None if test_student else _privacy(db, user),
        student=student,
        **(_home(db, user, student, page, course) if include_home and student is not None else {}),
    )
