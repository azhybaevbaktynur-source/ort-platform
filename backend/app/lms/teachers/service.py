"""Teacher requests (design 3.5). Services own the transaction."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.lms.audit import service as audit
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.lms.privacy.gate import aware
from app.lms.teachers import emails
from app.lms.teachers.models import TeacherRequest
from app.lms.teachers.schemas import MyTeacherRequestOut, TeacherRequestIn
from app.models.user import User


ME_ORGANIZATIONS_MAX = 100
REAPPLY_WAIT_DAYS = 7  # after a rejection (owner Q7)
PHONE_RETENTION_DAYS = 90  # after a rejection or a revoke (owner Q3); an approved teacher's phone stays


def admin_organizations(user: User) -> list[dict]:
    """UX rework 2: organizations the person administers directly, for the header's Organization area. A personal
    organization is never listed: the area is for schools and the platform (docs/phases/ACCOUNTS.md B)."""
    from sqlalchemy.orm import object_session

    from app.lms.organizations.models import Organization, OrganizationMember

    db = object_session(user)
    if db is None:
        return []
    rows = db.execute(
        select(Organization.id, Organization.name)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user.id, OrganizationMember.state == "active",
               OrganizationMember.role == "org_admin", Organization.deleted_at.is_(None),
               Organization.kind != "personal")
        .order_by(OrganizationMember.created_at, OrganizationMember.id)
        .limit(ME_ORGANIZATIONS_MAX)
    ).all()
    return [{"id": oid, "name": name} for oid, name in rows]


def can_create_courses(user: User) -> bool:
    """Phase 6 S1 (PHASE_6_DESIGN 2.2): from organization memberships, not from teacher_status."""
    from sqlalchemy.orm import object_session

    from app.lms.organizations.service import can_create_courses as _can

    db = object_session(user)
    return db is not None and _can(db, user)


def is_teacher(user: User) -> bool:
    """Phase 6 S8: the person teaches somewhere (shows the Teaching area; not a permission). Approved teacher_status,
    or an active org membership as teacher/org_admin, or an active staff enrollment in any course (one SQL)."""
    from sqlalchemy import exists, or_
    from sqlalchemy.orm import object_session

    from app.lms.enrollments.models import Enrollment
    from app.lms.organizations.models import Organization, OrganizationMember

    if user.teacher_status == "approved":
        return True
    db = object_session(user)
    if db is None:
        return False
    member = exists().where(
        OrganizationMember.user_id == user.id, OrganizationMember.state == "active",
        OrganizationMember.role.in_(("teacher", "org_admin")),
        Organization.id == OrganizationMember.organization_id, Organization.deleted_at.is_(None))
    staff = exists().where(Enrollment.user_id == user.id, Enrollment.state == "active",
                           Enrollment.role.in_(("teacher", "assistant")))
    return bool(db.execute(select(or_(member, staff))).scalar())


def set_locale(db: Session, user: User, locale: str) -> User:
    user.locale = locale
    db.commit()
    return user


def reapply_available_at(req: TeacherRequest) -> Optional[datetime]:
    """Rejected rows only: when the person may apply again."""
    if req.status != "rejected" or req.decided_at is None:
        return None
    return aware(req.decided_at) + timedelta(days=REAPPLY_WAIT_DAYS)


def _latest_request(db: Session, user_id: str) -> Optional[TeacherRequest]:
    return db.execute(
        select(TeacherRequest).where(TeacherRequest.user_id == user_id)
        .order_by(TeacherRequest.created_at.desc(), TeacherRequest.id.desc()).limit(1)
    ).scalar_one_or_none()


def _locked_applicant(db: Session, user: User) -> User:
    """Takes the user row lock and runs every check up to the age confirmation, in the order of ACCOUNTS.md B."""
    from app.lms.privacy import service as privacy

    locked = privacy._lock_user(db, user.id)
    if locked.teacher_status == "approved":
        raise Conflict("Already a teacher", code="already_teacher")
    pending = db.execute(
        select(TeacherRequest.id).where(TeacherRequest.user_id == locked.id, TeacherRequest.status == "pending")
    ).first()
    if pending or locked.teacher_status == "pending":
        raise Conflict("A request is already pending", code="request_pending")
    if locked.teacher_status != "revoked":  # a revoke, or an approval and a revoke, after the rejection doesn't count
        latest = _latest_request(db, locked.id)
        available_at = reapply_available_at(latest) if latest is not None else None
        if available_at is not None and clock.now() < available_at:
            raise Conflict("Wait before applying again", code="reapply_wait",
                           details={"available_at": available_at.isoformat().replace("+00:00", "Z")})
    if locked.age_band in ("under_14", "14_17"):
        raise Forbidden("Independent teachers must be 18 or older", code="teacher_age_required")
    return locked


def submit_request(db: Session, user: User, data: TeacherRequestIn) -> TeacherRequest:
    from app.lms.privacy import service as privacy

    # Rate limit first, before any write in this session (own connection, survives rollback).
    ratelimit.enforce(f"teacher_req:{user.id}", ratelimit.TEACHER_REQUEST_24H)
    locked = _locked_applicant(db, user)
    accepted = None
    if locked.age_band is None:
        refused = ValidationFailed("Confirm your age and accept the policies", code="age_confirmation_required")
        if not data.age_confirmed:
            raise refused
        try:
            accepted = privacy.accepted_policies(db, "18_plus", data.policy_version_ids)
        except ValidationFailed:
            raise refused from None
        locked = _locked_applicant(db, user)  # again: seeding missing policies commits, which frees the row lock
    if locked.age_band is None:  # never overwrites a band: only a NULL one, under the lock
        privacy.apply_age_band(db, locked, "18_plus", accepted, source="prompt", locale=None, due_at=None)
    req = TeacherRequest(user_id=locked.id, message=data.message, status="pending",
                         applicant_name=data.applicant_name, school=data.school, subject=data.subject,
                         phone=data.phone)
    db.add(req)
    locked.teacher_status = "pending"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("A request is already pending", code="request_pending")
    return req


def my_request_out(req: TeacherRequest) -> MyTeacherRequestOut:
    out = MyTeacherRequestOut.model_validate(req)
    out.reapply_available_at = reapply_available_at(req)
    return out


def my_requests(db: Session, user: User, limit: int = 10) -> list[TeacherRequest]:
    return list(db.execute(
        select(TeacherRequest).where(TeacherRequest.user_id == user.id)
        .order_by(TeacherRequest.created_at.desc(), TeacherRequest.id.desc()).limit(limit)
    ).scalars())


def _locked_request(db: Session, request_id: uuid.UUID) -> TeacherRequest:
    req = db.execute(
        select(TeacherRequest).where(TeacherRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if req is None:
        raise NotFound("Teacher request not found", code="not_found")
    if req.status != "pending":
        raise Conflict("Request is not pending", code="not_pending")
    return req


def _decision_mail(user: User, kind: str, *, reason: Optional[str] = None,
                   reapply_at: Optional[datetime] = None) -> Optional[emails.DecisionEmail]:
    """Built before the commit (the row is loaded), sent after it. None: nobody to write to, or nothing that could be
    built; the decision goes on either way."""
    try:
        return emails.for_user(user, kind, reason=reason, reapply_at=reapply_at)
    except Exception:
        emails.logger.exception("teacher decision email could not be built")
        return None


def _set_phone_purge(db: Session, user_id: str, value: Optional[datetime]) -> None:
    """On the person's latest approved request (revoke: a date; re-approval without a new request: cleared)."""
    latest = db.execute(
        select(TeacherRequest).where(TeacherRequest.user_id == user_id, TeacherRequest.status == "approved")
        .order_by(TeacherRequest.created_at.desc(), TeacherRequest.id.desc()).limit(1)
    ).scalar_one_or_none()
    if latest is not None:
        latest.phone_purge_after = value


def approve(db: Session, admin: User, request_id: uuid.UUID, note: Optional[str], request: Request) -> TeacherRequest:
    req = _locked_request(db, request_id)
    user = db.get(User, req.user_id)
    before = user.teacher_status
    req.status = "approved"
    req.decided_by_id = admin.id
    req.decided_at = clock.now()
    req.reason = note
    req.phone_purge_after = None
    user.teacher_status = "approved"
    org_id = _approve_personal_org(db, user)  # Phase 6 S1
    audit.record(
        db, actor=admin, action="teacher_request.approve", target_type="teacher_request",
        target_id=str(req.id), reason=note,
        details={"user_id": user.id, "from": before, "to": "approved",
                 "organization_id": str(org_id) if org_id else None},
        request=request,
    )
    mail = _decision_mail(user, "approved")
    db.commit()
    emails.send(mail)
    return req


def reject(db: Session, admin: User, request_id: uuid.UUID, reason: str, request: Request) -> TeacherRequest:
    req = _locked_request(db, request_id)
    user = db.get(User, req.user_id)
    before = user.teacher_status
    at = clock.now()
    req.status = "rejected"
    req.decided_by_id = admin.id
    req.decided_at = at
    req.reason = reason
    req.phone_purge_after = at + timedelta(days=PHONE_RETENTION_DAYS)
    user.teacher_status = "none"
    audit.record(
        db, actor=admin, action="teacher_request.reject", target_type="teacher_request",
        target_id=str(req.id), reason=reason,
        details={"user_id": user.id, "from": before, "to": "none"}, request=request,
    )
    mail = _decision_mail(user, "rejected", reason=reason, reapply_at=reapply_available_at(req))
    db.commit()
    emails.send(mail)
    return req


def set_teacher_status(
    db: Session, admin: User, user_id: str, status: Literal["approved", "revoked"],
    reason: Optional[str], request: Request,
) -> User:
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise NotFound("User not found", code="user_not_found")
    before = user.teacher_status
    at = clock.now()
    if status == "approved":
        if before == "approved":
            raise Conflict("Invalid transition", code="invalid_transition")
        pending = db.execute(
            select(TeacherRequest).where(TeacherRequest.user_id == user.id, TeacherRequest.status == "pending")
            .with_for_update()
        ).scalar_one_or_none()
        if pending is not None:
            pending.status = "approved"
            pending.decided_by_id = admin.id
            pending.decided_at = at
            pending.reason = reason
        db.flush()  # the row above, when there is one, is now the latest approved request
        _set_phone_purge(db, user.id, None)
    else:
        if before != "approved":
            raise Conflict("Invalid transition", code="invalid_transition")
        _set_phone_purge(db, user.id, at + timedelta(days=PHONE_RETENTION_DAYS))
    user.teacher_status = status
    # --- Phase 6 S1 begin --- approval creates (or resumes) the personal organization; revoke suspends it
    details = {"from": before, "to": status}
    if status == "approved":
        org_id = _approve_personal_org(db, user)
        details["organization_id"] = str(org_id) if org_id else None
    else:
        from app.lms.organizations.ids import personal_org_id
        from app.lms.organizations.service import suspend_personal_org

        suspend_personal_org(db, user, reason)
        details["organization_id"] = str(personal_org_id(user.id))
    # --- Phase 6 S1 end ---
    audit.record(
        db, actor=admin, action="user.teacher_status.set", target_type="user", target_id=user.id,
        reason=reason, details=details, request=request,
    )
    mail = _decision_mail(user, status)
    db.commit()
    emails.send(mail)
    return user


# --- Phase 6 S1 begin ---
def _approve_personal_org(db: Session, user: User):
    """Approval of an independent teacher: personal organization + org_admin membership, in the caller's
    transaction (PHASE_6_DESIGN 7). Platform admins get none (they create courses in the platform org)."""
    from app.lms.organizations.service import ensure_personal_org

    if user.is_platform_admin:
        return None
    return ensure_personal_org(db, user)
# --- Phase 6 S1 end ---
