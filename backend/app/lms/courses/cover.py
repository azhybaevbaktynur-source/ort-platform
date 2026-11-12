"""Course cover image and card extras (STUDENT_UI_FIX_PLAN 7.1-7.2, slice F7a).

Cover: one public WebP asset per course (`courses.cover_asset_id`), uploaded through the image pipeline
(`files.service.ingest_image`: content validation, SHA-256 dedup, per-user quota, the free-tier guard `usage.py`, the
public bucket) with one extra step, a 16:9 crop around a focus (`files.images.encode_cover`). The dedup key is salted
with the crop, so a cover asset is never the same row as a content image of the same bytes; removing or replacing a
cover soft-deletes its asset when no other course points at it (the blob stays: content-addressed, never listed).

Who: the course's staff with `course.update`; on a platform course (the platform organization's tree) only platform
admins (`users.is_platform_admin`, read from the database on every request). Locked template (ORT) courses allow this
one write. Audited: `course.cover_set`, `course.cover_cleared`.

Card extras: cover URL, published tests and lessons of a page of courses in ONE statement (correlated counts), never
per card."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import partial
from typing import Iterable, Optional

from fastapi import Request
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.audit import service as audit
from app.lms.core.errors import Forbidden
from app.lms.courses.models import Course
from app.lms.files.models import Asset
from app.lms.files.storage import media_url

E_PLATFORM_COURSE = "platform_course_admin_only"


@dataclass(frozen=True)
class CardExtras:
    cover_url: Optional[str] = None
    tests_count: int = 0
    lessons_count: int = 0
    is_platform_course: bool = False
    student_count: int = 0
    has_paid_tests: bool = False  # a platform course with a published paid test (the card's quiet "Pro" mark)


NO_EXTRAS = CardExtras()


def _tests_count():
    """Published, live exams of the course, counted as the Tests page lists them: practice quizzes are not tests, and
    a test needs a published version."""
    from app.lms.assessments.models import Assessment

    return (select(func.count(Assessment.id))
            .where(Assessment.course_id == Course.id, Assessment.deleted_at.is_(None),
                   Assessment.status == "published", Assessment.is_practice.is_(False),
                   Assessment.published_version_id.isnot(None))
            .correlate(Course).scalar_subquery())


def _has_paid_tests():
    """A test of the Tests page (`_tests_count`'s rule) that needs a pass (S3 access: `paid`, platform courses only)."""
    from app.lms.assessments.models import Assessment

    return (select(Assessment.id)
            .where(Assessment.course_id == Course.id, Assessment.deleted_at.is_(None),
                   Assessment.status == "published", Assessment.is_practice.is_(False),
                   Assessment.published_version_id.isnot(None), Assessment.access_tier == "paid")
            .correlate(Course).exists())


def _lessons_count():
    """Lessons (F5a L2, the rows `modules.service.lesson_exists` looks for): live, published `page|file|url` items of
    live, published modules whose target is published and live. Headers and test items are not lessons."""
    from app.lms.course_files.models import CourseFile
    from app.lms.modules import ids as module_ids
    from app.lms.modules.models import CourseModule, ModuleItem
    from app.lms.pages.models import Page

    return (select(func.count(ModuleItem.id))
            .select_from(ModuleItem).join(CourseModule, CourseModule.id == ModuleItem.module_id)
            .outerjoin(Page, Page.id == ModuleItem.page_id)
            .outerjoin(CourseFile, CourseFile.id == ModuleItem.file_id)
            .where(CourseModule.course_id == Course.id, CourseModule.deleted_at.is_(None),
                   CourseModule.published.is_(True), ModuleItem.deleted_at.is_(None),
                   ModuleItem.published.is_(True), ModuleItem.kind.in_(module_ids.LESSON_KINDS),
                   or_(ModuleItem.kind == "url",
                       and_(ModuleItem.kind == "page", Page.published.is_(True), Page.deleted_at.is_(None)),
                       and_(ModuleItem.kind == "file", CourseFile.published.is_(True),
                            CourseFile.deleted_at.is_(None))))
            .correlate(Course).scalar_subquery())


def _student_count():
    from app.lms.enrollments.models import Enrollment

    return (select(func.count(Enrollment.id))
            .where(Enrollment.course_id == Course.id, Enrollment.role == "student", Enrollment.state == "active",
                   Enrollment.is_test_student.is_(False))
            .correlate(Course).scalar_subquery())


def card_extras(db: Session, course_ids: Iterable, *, students: bool = False) -> dict:
    """course id -> CardExtras for one page of cards: one statement whatever the page size (none for an empty page).
    `students`: also the active student count (the catalog's)."""
    from app.lms.access.service import is_platform_path
    from app.lms.organizations.models import Organization

    ids = list(dict.fromkeys(course_ids))
    if not ids:
        return {}
    cols = [Course.id, Asset.sha256, _tests_count(), _lessons_count(), Organization.path, _has_paid_tests()]
    if students:
        cols.append(_student_count())
    rows = db.execute(
        select(*cols)
        .outerjoin(Asset, and_(Asset.id == Course.cover_asset_id, Asset.erased_at.is_(None)))
        .outerjoin(Organization, Organization.id == Course.organization_id)
        .where(Course.id.in_(ids))
    ).all()
    return {r[0]: CardExtras(cover_url=media_url(r[1]) if r[1] else None, tests_count=int(r[2] or 0),
                             lessons_count=int(r[3] or 0), is_platform_course=is_platform_path(r[4]),
                             has_paid_tests=bool(r[5]) and is_platform_path(r[4]),
                             student_count=int(r[6] or 0) if students else 0) for r in rows}


def cover_url(db: Session, course: Course) -> Optional[str]:
    """The cover of one course (one primary-key read; none without a cover)."""
    if getattr(course, "cover_asset_id", None) is None:
        return None
    sha = db.execute(select(Asset.sha256).where(Asset.id == course.cover_asset_id,
                                                Asset.erased_at.is_(None))).scalar()
    return media_url(sha) if sha else None


# ---------------------------------------------------------------- upload and removal

def require_cover_edit(db: Session, ctx: AuthzContext, course: Course) -> None:
    """Platform course: platform admins only (a member gets 403, anyone else the usual 404). Other courses: staff with
    `course.update` (the course settings right; the organization's suspension refuses it)."""
    from app.lms.courses.service import assert_not_sandbox, require_course
    from app.lms.modules.service import is_platform_course

    if is_platform_course(db, course):
        if getattr(ctx.user, "is_platform_admin", False):
            assert_not_sandbox(course)
            return
        require_course(ctx, A.COURSE_READ, course)  # not a member: 404 as everywhere else
        raise Forbidden("Only platform administrators change the cover of a platform course", code=E_PLATFORM_COURSE)
    require_course(ctx, A.COURSE_UPDATE, course)
    assert_not_sandbox(course)


def _release(db: Session, asset_id: uuid.UUID, course_id: uuid.UUID, actor_id: str) -> None:
    """Soft-delete a cover asset no other course points at (salted dedup: it is only ever a cover)."""
    asset = db.get(Asset, asset_id)
    if asset is None or asset.deleted_at is not None:
        return
    if db.execute(select(exists().where(Course.cover_asset_id == asset_id, Course.id != course_id))).scalar():
        return
    asset.soft_delete(actor_id)


def set_cover(db: Session, ctx: AuthzContext, course: Course, raw: bytes, *, filename: Optional[str],
              focus_x: float = 0.5, focus_y: float = 0.5, request: Optional[Request] = None) -> tuple[Asset, bool]:
    """Store the cropped cover and point the course at it. Returns (asset, deduplicated). Commits."""
    from app.lms.files import service as files_svc
    from app.lms.files.images import encode_cover

    fx, fy = round(float(focus_x), 3), round(float(focus_y), 3)
    asset, dup = files_svc.ingest_image(
        db, ctx.user, raw, course_id=course.id, visibility="public", filename=filename,
        encoder=partial(encode_cover, focus_x=fx, focus_y=fy), dedup_salt=f"cover:{fx:.3f}:{fy:.3f}")
    old = course.cover_asset_id
    course.cover_asset_id = asset.id
    if old != asset.id:
        from app.lms.courses.listing import mark_content_changed

        mark_content_changed(course)  # step 3b: edited after the catalog approval
    if old is not None and old != asset.id:
        _release(db, old, course.id, ctx.user.id)
    audit.record(db, actor=ctx.user, action="course.cover_set", target_type="course", target_id=str(course.id),
                 details={"asset_id": str(asset.id), "deduplicated": dup}, request=request)
    db.commit()
    db.refresh(asset)
    return asset, dup


def clear_cover(db: Session, ctx: AuthzContext, course: Course, *, request: Optional[Request] = None) -> None:
    """Remove the cover (idempotent: nothing to remove writes nothing). Commits."""
    old = course.cover_asset_id
    if old is None:
        return
    course.cover_asset_id = None
    from app.lms.courses.listing import mark_content_changed

    mark_content_changed(course)  # step 3b: edited after the catalog approval
    db.flush()
    _release(db, old, course.id, ctx.user.id)
    audit.record(db, actor=ctx.user, action="course.cover_cleared", target_type="course", target_id=str(course.id),
                 details={"asset_id": str(old)}, request=request)
    db.commit()
