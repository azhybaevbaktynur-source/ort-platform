"""Lesson courses of an exam course (docs/phases/TEACHER_TO_STUDENT_MAP.md 2.2-2.3, slice S1).

A lesson course is an ordinary platform course whose `exam_course_id` names a platform exam-prep course (set by a
platform admin, `courses.service._check_exam_link`). `GET /courses/{exam}/lesson-courses` lists them for the exam's
students and staff: the published, live ones (visibility ignored: joining still goes through the normal join rules),
at most `LESSON_COURSES_MAX`, oldest published first.

Statements: one for the rows (cover, lesson count and length, Pro modules, the caller's enrollment as correlated
columns), one for the progress of the enrolled ones (`home._progress`, the stored facts), and the "continue" lookup of
the home (`home._modules_next`, two statements plus the pass check) for their next item. Allow-list: no join code, no
roster, no owner."""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext, can
from app.lms.core.errors import Forbidden
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.files.models import Asset
from app.lms.files.storage import media_url
from app.lms.home.schemas import HomeProgressOut
from app.lms.modules.schemas import ItemLinkOut

LESSON_COURSES_MAX = 20


class LessonCourseOut(BaseModel):
    id: uuid.UUID
    title: dict
    cover_url: Optional[str] = None
    is_platform_course: bool
    lessons_count: int = 0
    duration_s: int = 0  # the summed length of its lessons (lessons without a length count 0)
    enrolled: bool
    is_staff: bool = False  # the caller teaches or assists the lesson course (fb8 review fix 7): the UI offers no Join
    progress: Optional[HomeProgressOut] = None  # enrolled only; null without a requirement (as the home card)
    has_paid_modules: bool
    next_item: Optional[ItemLinkOut] = None  # enrolled only: the first item not done (the home's "continue")
    exam_family: Optional[str] = None  # STUDENT_IA_DESIGN 0.4 (S9): the card's subject/family mark
    subject: Optional[str] = None


def require_member(ctx: AuthzContext, course: Course) -> None:
    """Read access to the exam course (`course.read`, so the course status counts: a student of a draft course does
    not read it; fb8 review fix 4): enrolled (students, test students) or staff; platform and organization admins
    read it as any course. Everyone else: 403 `not_enrolled`, before any exam-prep check (fix 3)."""
    if can(ctx, A.COURSE_READ, course):
        return
    raise Forbidden("Not enrolled in this course", code="not_enrolled")


def _lessons_where():
    from app.lms.course_files.models import CourseFile
    from app.lms.modules import ids as module_ids
    from app.lms.modules.models import CourseModule, ModuleItem
    from app.lms.pages.models import Page

    return (CourseModule.course_id == Course.id, CourseModule.deleted_at.is_(None),
            CourseModule.published.is_(True), ModuleItem.deleted_at.is_(None),
            ModuleItem.published.is_(True), ModuleItem.kind.in_(module_ids.LESSON_KINDS),
            or_(ModuleItem.kind == "url",
                and_(ModuleItem.kind == "page", Page.published.is_(True), Page.deleted_at.is_(None)),
                and_(ModuleItem.kind == "file", CourseFile.published.is_(True), CourseFile.deleted_at.is_(None))))


def _lessons_agg(agg):
    """A correlated aggregate over the course's lessons (`cover._lessons_count`'s rows)."""
    from app.lms.course_files.models import CourseFile
    from app.lms.modules.models import CourseModule, ModuleItem
    from app.lms.pages.models import Page

    return (select(agg)
            .select_from(ModuleItem).join(CourseModule, CourseModule.id == ModuleItem.module_id)
            .outerjoin(Page, Page.id == ModuleItem.page_id)
            .outerjoin(CourseFile, CourseFile.id == ModuleItem.file_id)
            .where(*_lessons_where())
            .correlate(Course).scalar_subquery())


def lesson_courses(db: Session, exam: Course, user_id: str) -> list[LessonCourseOut]:
    from app.lms.access.service import is_platform_path
    from app.lms.home.service import _modules_next, _progress
    from app.lms.modules.models import CourseModule, ModuleItem
    from app.lms.organizations.models import Organization

    paid = (select(CourseModule.id)
            .where(CourseModule.course_id == Course.id, CourseModule.deleted_at.is_(None),
                   CourseModule.published.is_(True), CourseModule.access_tier == "paid")
            .correlate(Course).exists())
    enrolled = (select(Enrollment.id)
                .where(Enrollment.course_id == Course.id, Enrollment.user_id == user_id,
                       Enrollment.role == "student", Enrollment.state == "active")
                .correlate(Course).exists())
    staff = (select(Enrollment.id)
             .where(Enrollment.course_id == Course.id, Enrollment.user_id == user_id,
                    Enrollment.role.in_(("teacher", "assistant")), Enrollment.state == "active")
             .correlate(Course).exists())
    rows = db.execute(
        select(Course.id, Course.title, Asset.sha256, _lessons_agg(func.count(ModuleItem.id)),
               _lessons_agg(func.coalesce(func.sum(ModuleItem.duration_s), 0)), Organization.path,
               paid, enrolled, staff, Course.exam_family, Course.subject)
        .outerjoin(Asset, and_(Asset.id == Course.cover_asset_id, Asset.erased_at.is_(None)))
        .outerjoin(Organization, Organization.id == Course.organization_id)
        .where(Course.exam_course_id == exam.id, Course.status == "published", Course.deleted_at.is_(None))
        .order_by(Course.published_at.asc(), Course.id).limit(LESSON_COURSES_MAX)
    ).all()
    mine = [r[0] for r in rows if r[7]]
    progress = _progress(db, user_id, mine) if mine else {}
    next_items = ({n.course_id: n.link for n in _modules_next(db, user_id, course_ids=mine, max_out=len(mine))}
                  if mine else {})
    out = []
    for cid, title, sha, lessons, duration, path, has_paid, is_enrolled, is_staff, family, subject in rows:
        done_total = progress.get(cid) if is_enrolled else None
        platform = is_platform_path(path)
        out.append(LessonCourseOut(
            id=cid, title=title, cover_url=media_url(sha) if sha else None, is_platform_course=platform,
            lessons_count=int(lessons or 0), duration_s=int(duration or 0), enrolled=bool(is_enrolled),
            is_staff=bool(is_staff),
            progress=HomeProgressOut(done=done_total[0], total=done_total[1]) if done_total else None,
            has_paid_modules=bool(has_paid) and platform,
            next_item=next_items.get(cid) if is_enrolled else None, exam_family=family, subject=subject))
    return out
