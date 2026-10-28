"""Platform-admin course moderation (prefix /platform). The only admin entry into courses; every
mutation and every roster view is written to the audit log in the same transaction."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.audit import service as audit
from app.lms.core.deps import require_platform_admin
from app.lms.core.pagination import PageOut
from app.lms.courses import service as svc
from app.lms.courses.models import Course
from app.lms.courses.scopes import regular_courses  # Phase 8b S1
from app.lms.courses.schemas import (
    AdminCourseOut, AdminTransferIn, OptionalReasonIn, ReasonIn, admin_course_out,
)
from app.lms.enrollments import service as enr_svc
from app.lms.enrollments.models import Enrollment
from app.lms.enrollments.schemas import RosterEntryOut, roster_entry
from app.models.user import User

router = APIRouter()


def _one(db: Session, course_id: uuid.UUID) -> AdminCourseOut:
    row = db.execute(svc.admin_courses_query().where(Course.id == course_id)).first()
    if row is None:
        raise svc.not_found_course()
    return admin_course_out(row[0], row[1], row[2])


@router.get("/courses", response_model=PageOut[AdminCourseOut])
def list_courses(q: Optional[str] = Query(None, max_length=100),
                 status: Optional[Literal["draft", "published", "concluded"]] = None,
                 deleted: Optional[bool] = None, owner_id: Optional[str] = Query(None, max_length=64),
                 cursor: Optional[str] = None, limit: int = 25,
                 admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    stmt = svc.admin_courses_query().where(regular_courses())  # Phase 8b S1: sandboxes are never listed
    if q:
        needle = "%" + svc.like_escape(q.strip().lower()) + "%"
        stmt = stmt.where(or_(
            func.lower(cast(Course.title, String)).like(needle, escape="\\"),
            func.lower(User.email).like(needle, escape="\\"),
        ))
    if status:
        stmt = stmt.where(Course.status == status)
    if deleted is True:
        stmt = stmt.where(Course.deleted_at.is_not(None))
    elif deleted is False:
        stmt = stmt.where(Course.deleted_at.is_(None))
    if owner_id:
        stmt = stmt.where(Course.owner_id == owner_id)
    rows, nxt = svc.paginate_rows(db, stmt, sort_col=Course.created_at, id_col=Course.id,
                                  entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    return PageOut[AdminCourseOut](items=[admin_course_out(r[0], r[1], r[2]) for r in rows], next_cursor=nxt)


@router.get("/courses/{course_id}", response_model=AdminCourseOut)
def get_course(course_id: uuid.UUID, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return _one(db, course_id)


@router.get("/courses/{course_id}/people", response_model=PageOut[RosterEntryOut])
def course_people(course_id: uuid.UUID, request: Request, cursor: Optional[str] = None, limit: int = 25,
                  admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    course = svc.load_course(db, course_id, include_deleted=True)
    rows, nxt = svc.paginate_rows(
        db, enr_svc.roster_query(course.id), sort_col=Enrollment.created_at, id_col=Enrollment.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False,
    )
    audit.record(db, actor=admin, action="course.roster.view", target_type="course", target_id=str(course.id),
                 request=request)
    db.commit()
    return PageOut[RosterEntryOut](items=[roster_entry(e, u, course.owner_id) for e, u in rows], next_cursor=nxt)


@router.post("/courses/{course_id}/delete", response_model=AdminCourseOut)
def delete_course(course_id: uuid.UUID, data: ReasonIn, request: Request,
                  admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    course = svc.load_course(db, course_id, include_deleted=True)
    svc.soft_delete_course(db, admin, course, by_admin=True, reason=data.reason, request=request)
    return _one(db, course_id)


@router.post("/courses/{course_id}/restore", response_model=AdminCourseOut)
def restore_course(course_id: uuid.UUID, data: ReasonIn, request: Request,
                   admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    course = svc.load_course(db, course_id, include_deleted=True)
    svc.restore_course(db, admin, course, by_admin=True, reason=data.reason, request=request)
    return _one(db, course_id)


@router.post("/courses/{course_id}/unlist", response_model=AdminCourseOut)
def unlist_course(course_id: uuid.UUID, data: OptionalReasonIn, request: Request,
                  admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    course = svc.load_course(db, course_id, include_deleted=True)
    svc.set_unlisted(db, admin, course, unlisted=True, reason=data.reason, request=request)
    return _one(db, course_id)


@router.post("/courses/{course_id}/relist", response_model=AdminCourseOut)
def relist_course(course_id: uuid.UUID, data: OptionalReasonIn, request: Request,
                  admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    course = svc.load_course(db, course_id, include_deleted=True)
    svc.set_unlisted(db, admin, course, unlisted=False, reason=data.reason, request=request)
    return _one(db, course_id)


@router.post("/courses/{course_id}/transfer-ownership", response_model=AdminCourseOut)
def transfer_ownership(course_id: uuid.UUID, data: AdminTransferIn, request: Request,
                       admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    course = svc.load_course(db, course_id, include_deleted=True)
    svc.transfer_ownership(db, admin, course, data.new_owner_user_id, by_admin=True, reason=data.reason,
                           request=request)
    return _one(db, course_id)


# --- Phase 6 S2b begin --- (template lock: platform admin only, audited; PHASE_6_DESIGN 5.4)
from app.lms.templates import service as _tpl  # noqa: E402
from app.lms.templates.schemas import PlatformCoursePatchIn, PlatformCourseTemplateOut  # noqa: E402


@router.patch("/courses/{course_id}", response_model=PlatformCourseTemplateOut)
def patch_course(course_id: uuid.UUID, data: PlatformCoursePatchIn, request: Request,
                 admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    course = svc.load_course(db, course_id, include_deleted=True, for_update=True)
    _tpl.set_template_locked(db, admin, course, data.template_locked, reason=data.reason, request=request)
    db.refresh(course)
    return PlatformCourseTemplateOut(id=course.id, template_key=course.template_key,
                                     template_version=course.template_version,
                                     template_locked=bool(course.template_locked),
                                     template=_tpl.course_template_out(course))
# --- Phase 6 S2b end ---
