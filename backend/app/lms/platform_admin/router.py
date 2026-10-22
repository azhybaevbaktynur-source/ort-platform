"""Platform admin routes: users, teacher requests, audit log. Every route requires is_platform_admin."""
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.audit.models import AdminAuditLog
from app.lms.core.deps import require_platform_admin
from app.lms.core.pagination import PageOut, paginate
from app.lms.platform_admin import users_service as us
from app.lms.platform_admin.schemas import (
    AdminUserDetailOut, AdminUserOut, ApproveIn, AuditEntryOut, DisableIn, RejectIn, SummaryOut,
    TeacherRequestAdminOut, TeacherStatusIn,
)
from app.lms.teachers import service as teacher_service
from app.lms.teachers.models import TeacherRequest
from app.models.user import User

router = APIRouter()


@router.get("/summary", response_model=SummaryOut)
def summary(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return SummaryOut(pending_teacher_requests=us.pending_request_count(db))


@router.get("/teacher-requests", response_model=PageOut[TeacherRequestAdminOut])
def list_teacher_requests(
    status: Literal["pending", "approved", "rejected", "cancelled", "all"] = "pending",
    cursor: Optional[str] = None, limit: Optional[int] = Query(None),
    admin: User = Depends(require_platform_admin), db: Session = Depends(get_db),
):
    page = paginate(us.teacher_requests_stmt(status), db, sort_col=TeacherRequest.created_at,
                    id_col=TeacherRequest.id, cursor=cursor, limit=limit)
    return PageOut(items=[us.request_out(db, r) for r in page.items], next_cursor=page.next_cursor)


@router.post("/teacher-requests/{request_id}/approve", response_model=TeacherRequestAdminOut)
def approve_request(request_id: uuid.UUID, body: ApproveIn, request: Request,
                    admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    req = teacher_service.approve(db, admin, request_id, body.note, request)
    return us.request_out(db, req)


@router.post("/teacher-requests/{request_id}/reject", response_model=TeacherRequestAdminOut)
def reject_request(request_id: uuid.UUID, body: RejectIn, request: Request,
                   admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    req = teacher_service.reject(db, admin, request_id, body.reason, request)
    return us.request_out(db, req)


@router.get("/users", response_model=PageOut[AdminUserOut])
def list_users(
    q: Optional[str] = Query(None, max_length=200),
    teacher_status: Optional[Literal["none", "pending", "approved", "revoked"]] = None,
    disabled: Optional[bool] = None, cursor: Optional[str] = None, limit: Optional[int] = Query(None),
    admin: User = Depends(require_platform_admin), db: Session = Depends(get_db),
):
    page = paginate(us.search_users(q, teacher_status, disabled), db, sort_col=User.created_at,
                    id_col=User.id, cursor=cursor, limit=limit)
    return PageOut(items=[us.user_out(u) for u in page.items], next_cursor=page.next_cursor)


@router.get("/users/{user_id}", response_model=AdminUserDetailOut)
def get_user(user_id: str, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return us.user_detail(db, us.get_user_or_404(db, user_id))


@router.post("/users/{user_id}/teacher-status", response_model=AdminUserOut)
def set_teacher_status(user_id: str, body: TeacherStatusIn, request: Request,
                       admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    user = teacher_service.set_teacher_status(db, admin, user_id, body.status, body.reason, request)
    return us.user_out(user)


@router.post("/users/{user_id}/disable", response_model=AdminUserOut)
def disable_user(user_id: str, body: DisableIn, request: Request,
                 admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return us.user_out(us.disable_user(db, admin, user_id, body.reason, request))


@router.post("/users/{user_id}/enable", response_model=AdminUserOut)
def enable_user(user_id: str, request: Request,
                admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return us.user_out(us.enable_user(db, admin, user_id, request))


@router.get("/audit-log", response_model=PageOut[AuditEntryOut])
def audit_log(
    actor_id: Optional[str] = None, action: Optional[str] = None, target_type: Optional[str] = None,
    target_id: Optional[str] = None, cursor: Optional[str] = None, limit: Optional[int] = Query(None),
    admin: User = Depends(require_platform_admin), db: Session = Depends(get_db),
):
    page = paginate(us.audit_stmt(actor_id, action, target_type, target_id), db,
                    sort_col=AdminAuditLog.created_at, id_col=AdminAuditLog.id, cursor=cursor, limit=limit)
    return PageOut(items=[us.audit_out(db, r) for r in page.items], next_cursor=page.next_cursor)
