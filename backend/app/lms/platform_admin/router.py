"""Platform admin routes: users, teacher requests, audit log. Every route requires is_platform_admin."""
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.audit.models import AdminAuditLog
from app.lms.core.deps import require_platform_admin
from app.lms.core.pagination import PageOut, paginate
from app.lms.files import usage
from app.lms.platform_admin import users_service as us
from app.lms.platform_admin.schemas import (
    AdminUserDetailOut, AdminUserOut, ApproveIn, AuditEntryOut, DisableIn, EndSessionsIn, PlatformAdminIn, RejectIn,
    SummaryOut, TeacherRequestAdminOut, TeacherStatusIn,
)
from app.lms.platform_admin import admins
from app.lms.platform_admin import persons  # S4
from app.lms.platform_admin.schemas import AdminAttemptOut, PasswordResetSentOut, ReasonIn  # S4
from app.lms.email_change import service as email_change  # S4
from app.lms.email_change.schemas import AdminEmailChangeIn  # S4
from app.lms.platform_admin.health import PlatformHealthOut, platform_health
from app.lms.platform_admin import overview as overview_service  # FB8-5 S4
from app.lms.platform_admin.schemas import OverviewOut  # FB8-5 S4
from app.lms.teachers import purge as teacher_purge
from app.lms.teachers import service as teacher_service
from app.lms.teachers.models import TeacherRequest
from app.models.user import User

router = APIRouter()


@router.get("/summary", response_model=SummaryOut)
def summary(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return SummaryOut(pending_teacher_requests=us.pending_request_count(db),
                      storage_level=usage.level(usage.stored_totals(db)[0]))


@router.get("/overview", response_model=OverviewOut)
def overview(background: BackgroundTasks, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    """FB8-5 S4: the overview page's numbers; 60 s per-process cache (`platform_admin/overview.py`). D2: the safe
    maintenance tasks run after the response when the daily schedule was skipped (`maintenance/service.py`)."""
    from app.lms.maintenance import service as maintenance

    maintenance.maybe_schedule(background)
    return overview_service.overview(db)


@router.get("/teacher-requests", response_model=PageOut[TeacherRequestAdminOut])
def list_teacher_requests(
    background: BackgroundTasks,
    status: Literal["pending", "approved", "rejected", "cancelled", "all"] = "pending",
    cursor: Optional[str] = None, limit: Optional[int] = Query(None),
    admin: User = Depends(require_platform_admin), db: Session = Depends(get_db),
):
    page = paginate(us.teacher_requests_stmt(status), db, sort_col=TeacherRequest.created_at,
                    id_col=TeacherRequest.id, cursor=cursor, limit=limit)
    teacher_purge.queue(background)
    return PageOut(items=us.requests_out(db, list(page.items)), next_cursor=page.next_cursor)


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
    email_unverified: bool = False, platform_admin: bool = False, has_access: bool = False,  # S4 filters
    admin: User = Depends(require_platform_admin), db: Session = Depends(get_db),
):
    stmt = us.search_users(q, teacher_status, disabled, email_unverified=email_unverified,
                           platform_admin=platform_admin, has_access=has_access)
    page = paginate(stmt, db, sort_col=User.created_at, id_col=User.id, cursor=cursor, limit=limit)
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


# --- S1 admin security begin ---
@router.post("/users/{user_id}/platform-admin", response_model=AdminUserOut)
def set_platform_admin(user_id: str, body: PlatformAdminIn, request: Request,
                       admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return us.user_out(admins.set_platform_admin(db, admin, user_id, body.platform_admin, body.reason, body.code,
                                                 request))


@router.post("/users/{user_id}/end-sessions", response_model=AdminUserOut)
def end_sessions(user_id: str, body: EndSessionsIn, request: Request,
                 admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return us.user_out(admins.end_sessions(db, admin, user_id, body.reason, request))


# --- S4 person page begin ---
@router.get("/users/{user_id}/attempts", response_model=PageOut[AdminAttemptOut])
def user_attempts(user_id: str, cursor: Optional[str] = None, limit: Optional[int] = Query(None),
                  admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return persons.attempts_page(db, user_id, cursor, limit)


@router.post("/users/{user_id}/password-reset", response_model=PasswordResetSentOut)
def user_password_reset(user_id: str, body: ReasonIn, request: Request,
                        admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return persons.send_password_reset(db, admin, user_id, body.reason, request)


@router.post("/users/{user_id}/email-change", response_model=AdminUserDetailOut)
def user_email_change(user_id: str, body: AdminEmailChangeIn, request: Request,
                      admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    email_change.request_by_admin(db, admin, user_id, str(body.new_email), body.reason, request)
    return us.user_detail(db, us.get_user_or_404(db, user_id))
@router.post("/users/{user_id}/email-change/cancel", response_model=AdminUserDetailOut)
def user_email_change_cancel(user_id: str, body: ReasonIn, request: Request,
                             admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    email_change.cancel_by_admin(db, admin, user_id, body.reason, request)
    return us.user_detail(db, us.get_user_or_404(db, user_id))
# --- S4 person page end ---


@router.get("/health", response_model=PlatformHealthOut)
def health(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return platform_health(db)
# --- S1 admin security end ---


@router.get("/audit-log", response_model=PageOut[AuditEntryOut])
def audit_log(
    actor_id: Optional[str] = None, action: Optional[str] = None, target_type: Optional[str] = None,
    target_id: Optional[str] = None, cursor: Optional[str] = None, limit: Optional[int] = Query(None),
    acting_as: Optional[Literal["org_admin", "platform_admin"]] = None,  # item 4: details.acting_as
    admin: User = Depends(require_platform_admin), db: Session = Depends(get_db),
):
    page = paginate(us.audit_stmt(actor_id, action, target_type, target_id, acting_as), db,
                    sort_col=AdminAuditLog.created_at, id_col=AdminAuditLog.id, cursor=cursor, limit=limit)
    return PageOut(items=us.audit_page_out(db, page.items), next_cursor=page.next_cursor)
