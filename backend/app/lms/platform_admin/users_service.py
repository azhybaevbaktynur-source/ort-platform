"""Platform-admin user operations (design 3.6) and read helpers for the admin queue/audit."""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.lms.audit import service as audit
from app.lms.audit.models import AdminAuditLog
from app.lms.core.errors import Conflict, NotFound
from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.platform_admin.schemas import (
    AdminUserDetailOut, AdminUserOut, AuditEntryOut, OwnedCourseBrief, TeacherRequestAdminOut, UserBrief,
)
from app.lms.teachers.models import TeacherRequest
from app.models.user import User


def get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User not found", code="user_not_found")
    return user


def disable_user(db: Session, admin: User, user_id: str, reason: str, request: Request) -> User:
    if user_id == admin.id:
        raise Conflict("Cannot disable yourself", code="cannot_disable_self")
    target = get_user_or_404(db, user_id)
    if target.is_platform_admin:
        raise Conflict("Cannot disable a platform admin", code="cannot_disable_admin")
    target.disabled_at = utcnow()
    target.disabled_by_id = admin.id
    target.disabled_reason = reason
    audit.record(db, actor=admin, action="user.disable", target_type="user", target_id=target.id,
                 reason=reason, request=request)
    db.commit()
    return target


def enable_user(db: Session, admin: User, user_id: str, request: Request) -> User:
    target = get_user_or_404(db, user_id)
    target.disabled_at = None
    target.disabled_by_id = None
    target.disabled_reason = None
    audit.record(db, actor=admin, action="user.enable", target_type="user", target_id=target.id,
                 request=request)
    db.commit()
    return target


def search_users(q: Optional[str], teacher_status: Optional[str], disabled: Optional[bool]):
    stmt = select(User)
    if q:
        term = q.strip().lower()
        if term:
            stmt = stmt.where(or_(
                func.lower(User.email).startswith(term, autoescape=True),
                func.lower(User.display_name).contains(term, autoescape=True),
            ))
    if teacher_status:
        stmt = stmt.where(User.teacher_status == teacher_status)
    if disabled is True:
        stmt = stmt.where(User.disabled_at.is_not(None))
    elif disabled is False:
        stmt = stmt.where(User.disabled_at.is_(None))
    return stmt


def pending_request_count(db: Session) -> int:
    return db.execute(
        select(func.count()).select_from(TeacherRequest).where(TeacherRequest.status == "pending")
    ).scalar_one()


def teacher_requests_stmt(status: str):
    stmt = select(TeacherRequest)
    if status != "all":
        stmt = stmt.where(TeacherRequest.status == status)
    return stmt


def audit_stmt(actor_id: Optional[str], action: Optional[str], target_type: Optional[str],
               target_id: Optional[str]):
    stmt = select(AdminAuditLog)
    if actor_id:
        stmt = stmt.where(AdminAuditLog.actor_id == actor_id)
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    if target_type:
        stmt = stmt.where(AdminAuditLog.target_type == target_type)
    if target_id:
        stmt = stmt.where(AdminAuditLog.target_id == target_id)
    return stmt


# --- serializers -------------------------------------------------------------------------------

def brief(user: Optional[User]) -> Optional[UserBrief]:
    if user is None:
        return None
    return UserBrief(id=user.id, display_name=user.display_name, email=user.email)


def user_out(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id, email=user.email, display_name=user.display_name, created_at=user.created_at,
        email_verified=bool(user.email_verified), is_platform_admin=bool(user.is_platform_admin),
        teacher_status=user.teacher_status, disabled_at=user.disabled_at,
        disabled_reason=user.disabled_reason,
    )


def request_out(db: Session, req: TeacherRequest) -> TeacherRequestAdminOut:
    user = db.get(User, req.user_id)
    decider = db.get(User, req.decided_by_id) if req.decided_by_id else None
    return TeacherRequestAdminOut(
        id=req.id, user=brief(user), user_teacher_status=user.teacher_status, message=req.message,
        status=req.status, reason=req.reason, created_at=req.created_at, decided_at=req.decided_at,
        decided_by=brief(decider),
    )


def user_detail(db: Session, user: User) -> AdminUserDetailOut:
    courses = db.execute(
        select(Course).where(Course.owner_id == user.id, Course.deleted_at.is_(None))
        .order_by(Course.created_at.desc()).limit(50)
    ).scalars().all()
    active = db.execute(
        select(func.count()).select_from(Enrollment).where(Enrollment.user_id == user.id, Enrollment.state == "active")
    ).scalar_one()
    reqs = db.execute(
        select(TeacherRequest).where(TeacherRequest.user_id == user.id)
        .order_by(TeacherRequest.created_at.desc()).limit(10)
    ).scalars().all()
    base = user_out(user).model_dump()
    return AdminUserDetailOut(
        **base,
        owned_courses=[OwnedCourseBrief(id=c.id, title=c.title, status=c.status, deleted_at=c.deleted_at)
                       for c in courses],
        active_enrollment_count=active,
        teacher_requests=[request_out(db, r) for r in reqs],
    )


def audit_out(db: Session, row: AdminAuditLog) -> AuditEntryOut:
    return AuditEntryOut(
        id=row.id, created_at=row.created_at, actor=brief(db.get(User, row.actor_id)), action=row.action,
        target_type=row.target_type, target_id=row.target_id, reason=row.reason, details=row.details,
    )
