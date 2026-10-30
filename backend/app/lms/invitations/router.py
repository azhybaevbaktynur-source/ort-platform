"""Invitation routes (PHASE_6_DESIGN 2.3). Mounted under /api/v1 in app/main.py (Phase 6 S3 block)."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext, get_authz
from app.core.exceptions import UnauthorizedException
from app.db.session import get_db
from app.lms.core.deps import _user_id_from_authorization, client_ip_hash, get_lms_user
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc
from app.lms.invitations import service as svc
from app.lms.invitations.policies import OrgAdmin, require_org_admin
from app.lms.invitations.schemas import (
    InvitationAcceptOut, InvitationCreatedOut, InvitationLookupOut, InvitationOut, MyInvitationOut,
    OrgInvitationIn, StaffInvitationIn, StudentInvitationsIn, StudentInvitationsOut,
)
from app.lms.invitations import students as student_svc  # Phase 9 S3
from app.models.user import User

router = APIRouter(tags=["Invitations"])

StateFilter = Optional[Literal["pending", "accepted", "revoked", "expired"]]


def _optional_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> Optional[User]:
    """Lookup is public; a valid bearer token only adds the per-user rate limit."""
    if not authorization:
        return None
    try:
        user_id = _user_id_from_authorization(authorization)
    except UnauthorizedException:
        return None
    user = db.get(User, user_id) if user_id else None
    return user if user is not None and user.disabled_at is None else None


@router.get("/org/{organization_id}/invitations", response_model=PageOut[InvitationOut])
def list_invitations(organization_id: uuid.UUID, state: StateFilter = None, cursor: Optional[str] = None,
                     limit: int = 25, admin: OrgAdmin = Depends(require_org_admin), db: Session = Depends(get_db)):
    items, nxt = svc.list_org_invitations(db, admin.organization, state=state, cursor=cursor, limit=limit)
    return PageOut[InvitationOut](items=items, next_cursor=nxt)


@router.post("/org/{organization_id}/invitations", response_model=InvitationCreatedOut, status_code=201)
def create_invitation(organization_id: uuid.UUID, data: OrgInvitationIn, request: Request,
                      admin: OrgAdmin = Depends(require_org_admin), db: Session = Depends(get_db)):
    return svc.create_org_invitation(db, admin.user, admin.organization, email=data.email, role=data.role,
                                     message=data.message, language=data.language, request=request)


@router.post("/org/{organization_id}/invitations/{invitation_id}/revoke", response_model=InvitationOut)
def revoke_invitation(organization_id: uuid.UUID, invitation_id: uuid.UUID, request: Request,
                      user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.revoke(db, user, organization_id, invitation_id, request=request)


@router.post("/org/{organization_id}/invitations/{invitation_id}/resend", response_model=InvitationCreatedOut,
             status_code=201)
def resend_invitation(organization_id: uuid.UUID, invitation_id: uuid.UUID, request: Request,
                      user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.resend(db, user, organization_id, invitation_id, request=request)


@router.get("/invitations/{token}", response_model=InvitationLookupOut)
def lookup_invitation(token: str, request: Request, user: Optional[User] = Depends(_optional_user),
                      db: Session = Depends(get_db)):
    return svc.lookup(db, token, ip_hash=client_ip_hash(request), user=user)


@router.post("/invitations/{token}/accept", response_model=InvitationAcceptOut)
def accept_invitation(token: str, request: Request, user: User = Depends(get_lms_user),
                      db: Session = Depends(get_db)):
    return svc.accept(db, user, token, ip_hash=client_ip_hash(request), request=request)


@router.get("/me/invitations", response_model=PageOut[MyInvitationOut])
def my_invitations(cursor: Optional[str] = None, limit: int = 25, user: User = Depends(get_lms_user),
                   db: Session = Depends(get_db)):
    items, nxt = svc.my_invitations(db, user, cursor=cursor, limit=limit)
    return PageOut[MyInvitationOut](items=items, next_cursor=nxt)


@router.post("/courses/{course_id}/staff/invitations", response_model=InvitationCreatedOut, status_code=201)
def create_staff_invitation(course_id: uuid.UUID, data: StaffInvitationIn, request: Request,
                            ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return svc.create_staff_invitation(ctx.db, ctx, course, email=data.email, role=data.role,
                                       message=data.message, language=data.language, request=request)


# --- Phase 9 S3 begin --- (PHASE_9_DESIGN 4.4, 4.5: student invitations; roster imports from organizations/roster.py)
@router.post("/courses/{course_id}/students/invitations", response_model=StudentInvitationsOut, status_code=201)
def create_student_invitations(course_id: uuid.UUID, data: StudentInvitationsIn, request: Request,
                               background: BackgroundTasks, ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return student_svc.create_student_invitations(ctx.db, ctx, course, addresses=data.emails, message=data.message,
                                                  language=data.language, background=background, request=request)


@router.get("/courses/{course_id}/students/invitations", response_model=PageOut[InvitationOut])
def list_student_invitations(course_id: uuid.UUID, state: StateFilter = None, cursor: Optional[str] = None,
                             limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    items, nxt = student_svc.list_student_invitations(ctx.db, ctx, course, state=state, cursor=cursor, limit=limit)
    return PageOut[InvitationOut](items=items, next_cursor=nxt)


@router.post("/courses/{course_id}/students/invitations/{invitation_id}/revoke", response_model=InvitationOut)
def revoke_student_invitation(course_id: uuid.UUID, invitation_id: uuid.UUID, request: Request,
                              ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return student_svc.revoke_student_invitation(ctx.db, ctx, course, invitation_id, request=request)


@router.post("/courses/{course_id}/students/invitations/{invitation_id}/resend",
             response_model=InvitationCreatedOut, status_code=201)
def resend_student_invitation(course_id: uuid.UUID, invitation_id: uuid.UUID, request: Request,
                              ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return student_svc.resend_student_invitation(ctx.db, ctx, course, invitation_id, request=request)


from app.lms.organizations.roster import router as _roster_router  # noqa: E402

router.include_router(_roster_router)
# --- Phase 9 S3 end ---
