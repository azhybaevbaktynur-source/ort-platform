"""Invitation use cases (PHASE_6_DESIGN 2.1, 2.3, 7).

Tokens: 32 random bytes (urlsafe); only the sha256 hex is stored, the token itself exists only in the email link.
State is derived: pending (not accepted, not revoked, not expired) -> accepted / revoked / expired.
Every create, revoke, resend and accept writes an `admin_audit_log` row with `details.organization_id`.
Email is sent after the commit; a failed send never fails the call (`email_sent: false`)."""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext, can, enrollment_role_resolver
from app.lms.audit import service as audit
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, Forbidden, NotFound, RateLimited, ValidationFailed
from app.lms.core.ratelimit import Limit
from app.lms.courses.models import Course
from app.lms.courses.service import add_event, assert_not_sandbox, get_enrollment, paginate_rows, require_course
from app.lms.enrollments.models import Enrollment
from app.lms.enrollments.service import accept_student_invitation, require_staff_power
from app.lms.invitations import emails
from app.lms.invitations.policies import forbidden_org, load_organization, org_access
from app.lms.invitations.schemas import (
    InvitationAcceptOut, InvitationCreatedOut, InvitationLookupOut, InvitationOut, MyInvitationOut,
)
from app.lms.organizations.models import Invitation, Organization, OrganizationMember
from app.models.user import User

INVITATION_TTL = timedelta(days=14)
STAFF_ROLES = ("teacher", "assistant")

# Rate limits (IP rules count and log unless settings.RATE_LIMIT_IP_ENFORCE, like every IP rule).
INVITE_SEND_1H = Limit("invite_send_1h", 50, 3600)              # create + resend, per actor (each sends an email)
INVITE_LOOKUP_IP_10M = Limit("invite_lookup_ip_10m", 60, 600, is_ip_rule=True)
INVITE_LOOKUP_USER_10M = Limit("invite_lookup_user_10m", 30, 600)
INVITE_ACCEPT_USER_10M = Limit("invite_accept_user_10m", 10, 600)
INVITE_ACCEPT_IP_FAIL_10M = Limit("invite_accept_ip_fail_10m", 30, 600, is_ip_rule=True)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NOT_FOUND_MESSAGE = "This invitation is not valid."

# admin_audit_log.target_type allows only user/course/teacher_request/enrollment (CHECK from Phase 1); course
# invitations are filed under the course, organization invitations under the acting user. The invitation id and
# organization_id are always in `details`. Switch to target_type 'invitation' once S1 adds it to the CHECK.


# ---------------------------------------------------------------- helpers

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def state_of(inv: Invitation, now: Optional[datetime] = None) -> str:
    now = now or clock.now()
    if inv.accepted_at is not None:
        return "accepted"
    if inv.revoked_at is not None:
        return "revoked"
    if _aware(inv.expires_at) <= now:
        return "expired"
    return "pending"


def _state_condition(state: str, now: datetime):
    open_ = and_(Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None))
    if state == "pending":
        return and_(open_, Invitation.expires_at > now)
    if state == "expired":
        return and_(open_, Invitation.expires_at <= now)
    if state == "accepted":
        return Invitation.accepted_at.isnot(None)
    if state == "revoked":
        return and_(Invitation.accepted_at.is_(None), Invitation.revoked_at.isnot(None))
    raise ValidationFailed("Unknown state", code="validation_failed")


def normalize_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if len(email) > 255 or not _EMAIL_RE.match(email):
        raise ValidationFailed("Invalid email", code="invalid_email")
    return email


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    name, dot, tld = domain.rpartition(".")
    if not dot:
        name, tld = domain, ""
    masked_domain = (name[:1] + "***") + (f".{tld}" if tld else "")
    return f"{local[:1]}***@{masked_domain}"


def _inviter_name(user: Optional[User]) -> str:
    if user is None:
        return "—"
    return (user.display_name or "").strip() or user.email


def _email_name(user: User, org: Organization) -> str:
    """Name used in the email and the From display name; never the inviter's address."""
    return (user.display_name or "").strip() or org.name


def not_found_invitation() -> NotFound:
    return NotFound(NOT_FOUND_MESSAGE, code="invitation_not_found")


def _audit_target(inv: Invitation, actor: User) -> tuple[str, str]:
    if inv.course_id is not None:
        return "course", str(inv.course_id)
    return "user", str(actor.id)


def _audit(db: Session, actor: User, action: str, inv: Invitation, request: Optional[Request], **extra) -> None:
    target_type, target_id = _audit_target(inv, actor)
    details = {"organization_id": str(inv.organization_id), "invitation_id": str(inv.id), "email": inv.email,
               "role": inv.role, "course_id": str(inv.course_id) if inv.course_id else None, **extra}
    audit.record(db, actor=actor, action=action, target_type=target_type, target_id=target_id, details=details,
                 request=request)


def _user_by_email(db: Session, email: str) -> Optional[User]:
    return db.execute(select(User).where(func.lower(User.email) == email)).scalars().first()


def item_out(inv: Invitation, course_title: Optional[dict], inviter: Optional[User],
             now: Optional[datetime] = None) -> InvitationOut:
    return InvitationOut(
        id=inv.id, email=inv.email, role=inv.role, course_id=inv.course_id, course_title=course_title,
        state=state_of(inv, now), invited_by_name=_inviter_name(inviter), created_at=inv.created_at,
        expires_at=inv.expires_at, accepted_at=inv.accepted_at,
    )


def _ensure_active_org(org: Organization) -> None:
    if org.status != "active":
        raise Forbidden("Organization is suspended", code="organization_suspended")


def _check_not_member(db: Session, org: Organization, email: str, course: Optional[Course],
                      role: Optional[str] = None) -> None:
    target = _user_by_email(db, email)
    if target is None:
        return
    if course is None:
        active = db.execute(select(OrganizationMember.id).where(
            OrganizationMember.organization_id == org.id, OrganizationMember.user_id == target.id,
            OrganizationMember.state == "active",
        )).first()
        if active is not None:
            raise Conflict("Already a member", code="already_member")
        return
    enr = get_enrollment(db, course.id, target.id)
    if enr is not None and enr.state == "active" and (enr.role in STAFF_ROLES or role == "student"):
        raise Conflict("Already enrolled", code="already_enrolled")  # Phase 9 S3: a student, in any active role


def _revoke_open(db: Session, org_id: uuid.UUID, email: str, course_id: Optional[uuid.UUID], actor: User,
                 now: datetime) -> None:
    """One pending invitation per (organization, email, course): older open ones are revoked."""
    course_cond = Invitation.course_id.is_(None) if course_id is None else Invitation.course_id == course_id
    db.execute(
        update(Invitation).where(
            Invitation.organization_id == org_id, Invitation.email == email, course_cond,
            Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None),
        ).values(revoked_at=now, revoked_by_id=actor.id).execution_options(synchronize_session=False)
    )


def _insert(db: Session, *, actor: User, org: Organization, email: str, role: str, course: Optional[Course],
            message: Optional[str], language: str, now: datetime,
            roster_import_id: Optional[uuid.UUID] = None) -> tuple[Invitation, str]:
    token = new_token()
    inv = Invitation(
        id=uuid.uuid4(), token_hash=hash_token(token), email=email, organization_id=org.id, role=role,
        course_id=course.id if course else None, message=(message or "").strip() or None,
        language=emails.clean_language(language), invited_by_id=actor.id, expires_at=now + INVITATION_TTL,
        created_at=now, roster_import_id=roster_import_id,
    )
    db.add(inv)
    db.flush()
    return inv, token


def build_mail(inv: Invitation, token: str, actor: User, org: Organization,
               course: Optional[Course]) -> emails.InvitationEmail:
    """The email of one invitation (Phase 9 S3: student invitations use their own template, design 4.8)."""
    if inv.role == "student":
        return emails.build_student_invitation_email(
            to_email=inv.email, token=token, lang=inv.language, inviter_name=_email_name(actor, org),
            inviter_email=actor.email, organization_name=org.name, course_title=course.title if course else None,
            message=inv.message, expires_at=_aware(inv.expires_at),
        )
    return emails.build_invitation_email(
        to_email=inv.email, token=token, lang=inv.language, inviter_name=_email_name(actor, org),
        inviter_email=actor.email, organization_name=org.name, role=inv.role,
        course_title=course.title if course else None, message=inv.message, expires_at=_aware(inv.expires_at),
    )


def _send(inv: Invitation, token: str, actor: User, org: Organization, course: Optional[Course]) -> bool:
    return emails.send_invitation_email(build_mail(inv, token, actor, org, course))


def _create_and_send(db: Session, *, actor: User, org: Organization, email: str, role: str,
                     course: Optional[Course], message: Optional[str], language: str,
                     request: Optional[Request], action: str = "invitation_created",
                     extra: Optional[dict] = None) -> InvitationCreatedOut:
    now = clock.now()
    _revoke_open(db, org.id, email, course.id if course else None, actor, now)
    inv, token = _insert(db, actor=actor, org=org, email=email, role=role, course=course, message=message,
                         language=language, now=now)
    _audit(db, actor, action, inv, request, **(extra or {}))
    db.commit()
    sent = _send(inv, token, actor, org, course)
    base = item_out(inv, course.title if course else None, actor, now)
    return InvitationCreatedOut(**base.model_dump(), email_sent=sent)


# ---------------------------------------------------------------- create

def create_org_invitation(db: Session, actor: User, org: Organization, *, email: str, role: str,
                          message: Optional[str], language: str,
                          request: Optional[Request] = None) -> InvitationCreatedOut:
    """POST /org/{id}/invitations (org admin or platform admin; `org_admin` invitations included)."""
    ratelimit.enforce(f"invite_send:{actor.id}", INVITE_SEND_1H)
    _ensure_active_org(org)
    email = normalize_email(email)
    _check_not_member(db, org, email, None)
    return _create_and_send(db, actor=actor, org=org, email=email, role=role, course=None, message=message,
                            language=language, request=request)


def create_staff_invitation(db: Session, ctx: AuthzContext, course: Course, *, email: str, role: str,
                            message: Optional[str], language: str,
                            request: Optional[Request] = None) -> InvitationCreatedOut:
    """POST /courses/{id}/staff/invitations: course `roster.manage`; a co-teacher only by the owner (as add_staff)."""
    # --- Phase 6 S4b begin --- (a suspended organization makes every write fail in authz with a generic 403;
    # course staff get the specific code instead. Non-staff still get the 404 of require_course.)
    if ctx.role_for(course.id) in ("teacher", "assistant"):
        staff_org = load_organization(db, course.organization_id)
        if staff_org is not None:
            _ensure_active_org(staff_org)
    # --- Phase 6 S4b end ---
    require_course(ctx, A.ROSTER_MANAGE, course)
    assert_not_sandbox(course)  # Phase 8b S1: sandbox staff are the template's managers, never invited
    require_staff_power(ctx, course)
    actor = ctx.user
    if role == "teacher" and course.owner_id != actor.id:
        raise Forbidden("Only the owner can do this", code="owner_only")
    ratelimit.enforce(f"invite_send:{actor.id}", INVITE_SEND_1H)
    org = load_organization(db, course.organization_id)
    if org is None:
        raise NotFound("Course not found", code="course_not_found")
    _ensure_active_org(org)
    email = normalize_email(email)
    _check_not_member(db, org, email, course)
    return _create_and_send(db, actor=actor, org=org, email=email, role=role, course=course, message=message,
                            language=language, request=request)


# ---------------------------------------------------------------- list

def list_org_invitations(db: Session, org: Organization, *, state: Optional[str], cursor: Optional[str],
                         limit: Optional[int]) -> tuple[list[InvitationOut], Optional[str]]:
    now = clock.now()
    stmt = (
        select(Invitation, Course.title, User)
        .outerjoin(Course, Course.id == Invitation.course_id)
        .outerjoin(User, User.id == Invitation.invited_by_id)
        .where(Invitation.organization_id == org.id)
        # Phase 9 S3: student invitations are listed per course (GET /courses/{id}/students/invitations)
        .where(Invitation.role != "student")
    )
    if state:
        stmt = stmt.where(_state_condition(state, now))
    rows, nxt = paginate_rows(db, stmt, sort_col=Invitation.created_at, id_col=Invitation.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    return [item_out(inv, title, inviter, now) for inv, title, inviter in rows], nxt


def my_invitations(db: Session, user: User, *, cursor: Optional[str],
                   limit: Optional[int]) -> tuple[list[MyInvitationOut], Optional[str]]:
    now = clock.now()
    email = (user.email or "").strip().lower()
    inviter = User.__table__.alias("inviter")
    stmt = (
        select(Invitation, Organization.name, Course.title, inviter.c.display_name, inviter.c.email)
        .join(Organization, Organization.id == Invitation.organization_id)
        .outerjoin(Course, Course.id == Invitation.course_id)
        .outerjoin(inviter, inviter.c.id == Invitation.invited_by_id)
        .where(Invitation.email == email, _state_condition("pending", now), Organization.deleted_at.is_(None))
    )
    rows, nxt = paginate_rows(db, stmt, sort_col=Invitation.created_at, id_col=Invitation.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    items = [
        MyInvitationOut(
            id=inv.id, organization_id=inv.organization_id, organization_name=org_name, role=inv.role,
            course_id=inv.course_id, course_title=title, invited_by_name=(name or "").strip() or (mail or "—"),
            expires_at=inv.expires_at,
        )
        for inv, org_name, title, name, mail in rows
    ]
    return items, nxt


# ---------------------------------------------------------------- revoke / resend

def _load_in_org(db: Session, organization_id: uuid.UUID, invitation_id: uuid.UUID) -> Optional[Invitation]:
    return db.execute(select(Invitation).where(
        Invitation.id == invitation_id, Invitation.organization_id == organization_id,
    )).scalar_one_or_none()


def _access(db: Session, user: User, organization_id: uuid.UUID) -> tuple[Organization, bool]:
    org, admin = org_access(db, user, organization_id)
    if org is None:
        if user.is_platform_admin:
            raise NotFound("Organization not found", code="organization_not_found")
        raise forbidden_org()
    return org, admin


def _course_of(db: Session, inv: Invitation) -> Optional[Course]:
    if inv.course_id is None:
        return None
    return db.execute(select(Course).where(Course.id == inv.course_id, Course.deleted_at.is_(None))).scalar_one_or_none()


def _inviter_can_manage(db: Session, user: User, inv: Invitation, course: Optional[Course]) -> bool:
    if inv.invited_by_id != user.id or course is None:
        return False
    ctx = AuthzContext(user, db, enrollment_role_resolver(db, user.id))
    return can(ctx, A.ROSTER_MANAGE, course)


def revoke(db: Session, user: User, organization_id: uuid.UUID, invitation_id: uuid.UUID,
           request: Optional[Request] = None) -> InvitationOut:
    """By the inviter, any org admin of that organization, or the platform admin. Revoking twice is a no-op."""
    org, admin = _access(db, user, organization_id)
    inv = _load_in_org(db, org.id, invitation_id)
    # the inviter only while they can still manage it (course roster.manage; an org invitation needs org admin)
    if not admin and (inv is None or not _inviter_can_manage(db, user, inv, _course_of(db, inv))):
        raise forbidden_org()
    if inv is None:
        raise not_found_invitation()
    if inv.accepted_at is not None:
        raise Conflict("Invitation already accepted", code="invitation_not_pending")
    if inv.revoked_at is None:
        inv.revoked_at = clock.now()
        inv.revoked_by_id = user.id
        _audit(db, user, "invitation_revoked", inv, request)
        db.commit()
    course = _course_of(db, inv)
    return item_out(inv, course.title if course else None, db.get(User, inv.invited_by_id))


def resend(db: Session, user: User, organization_id: uuid.UUID, invitation_id: uuid.UUID,
           request: Optional[Request] = None) -> InvitationCreatedOut:
    """New token and a new row (same email, role, course, message, language); the old one is revoked."""
    org, admin = _access(db, user, organization_id)
    inv = _load_in_org(db, org.id, invitation_id)
    course = _course_of(db, inv) if inv is not None else None
    if not admin and (inv is None or not _inviter_can_manage(db, user, inv, course)):
        raise forbidden_org()
    if inv is None:
        raise not_found_invitation()
    if inv.course_id is not None and course is None:
        raise not_found_invitation()
    if inv.course_id is not None and inv.role == "teacher" and course.owner_id != user.id:
        raise Forbidden("Only the owner can do this", code="owner_only")  # same rule as create
    if inv.accepted_at is not None or inv.revoked_at is not None:
        raise Conflict("Invitation is not pending", code="invitation_not_pending")
    db.rollback()  # nothing written yet; the rate-limit counter needs a session without open writes
    ratelimit.enforce(f"invite_send:{user.id}", INVITE_SEND_1H)
    inv = _load_in_org(db, org.id, invitation_id)
    org = load_organization(db, org.id)
    course = _course_of(db, inv)
    _ensure_active_org(org)
    _check_not_member(db, org, inv.email, course, inv.role)
    return _create_and_send(db, actor=user, org=org, email=inv.email, role=inv.role, course=course,
                            message=inv.message, language=inv.language, request=request,
                            action="invitation_resent", extra={"replaces_invitation_id": str(inv.id)})


# ---------------------------------------------------------------- public lookup

def _by_token(db: Session, token: str, *, for_update: bool = False) -> Optional[Invitation]:
    if not token or len(token) > 128:
        return None
    stmt = select(Invitation).where(Invitation.token_hash == hash_token(token))
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def lookup(db: Session, token: str, *, ip_hash: Optional[str], user: Optional[User]) -> InvitationLookupOut:
    """One 404 shape for unknown, expired, revoked and accepted invitations (no enumeration)."""
    if ip_hash:
        allowed, retry = ratelimit.hit(f"invite_lookup:ip:{ip_hash}", INVITE_LOOKUP_IP_10M)
        if not allowed:
            raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
    if user is not None:
        ratelimit.enforce(f"invite_lookup:u:{user.id}", INVITE_LOOKUP_USER_10M)
    inv = _by_token(db, token)
    if inv is None or state_of(inv) != "pending":
        raise not_found_invitation()
    org = load_organization(db, inv.organization_id)
    if org is None:
        raise not_found_invitation()
    course = _course_of(db, inv)
    if inv.course_id is not None and course is None:
        raise not_found_invitation()
    return InvitationLookupOut(organization_name=org.name, role=inv.role,
                               course_title=course.title if course else None,
                               masked_email=mask_email(inv.email), expires_at=inv.expires_at)


# ---------------------------------------------------------------- accept

def _parse_id(token: str) -> Optional[uuid.UUID]:
    if len(token or "") != 36:
        return None
    try:
        return uuid.UUID(token)
    except ValueError:
        return None


def _accept_failure(db: Session, ip_hash: Optional[str], exc: Exception) -> Exception:
    db.rollback()
    if ip_hash:
        ratelimit.hit(f"invite_accept:ip:{ip_hash}", INVITE_ACCEPT_IP_FAIL_10M)
    return exc


def _accept_out(inv: Invitation, org_name: str, *, already: bool) -> InvitationAcceptOut:
    return InvitationAcceptOut(organization_id=inv.organization_id, organization_name=org_name, role=inv.role,
                               course_id=inv.course_id, already_accepted=already)


def _write_membership(db: Session, user: User, inv: Invitation, now: datetime) -> None:
    m = db.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == inv.organization_id, OrganizationMember.user_id == user.id,
    ).with_for_update()).scalar_one_or_none()
    if m is None:
        db.add(OrganizationMember(
            id=uuid.uuid4(), organization_id=inv.organization_id, user_id=user.id, role=inv.role, state="active",
            invited_by_id=inv.invited_by_id, invitation_id=inv.id, created_at=now, updated_at=now,
        ))
        return
    if m.state != "active":  # revive a removed member
        m.state, m.role, m.removed_at, m.removed_by_id = "active", inv.role, None, None
    elif inv.role == "org_admin":  # never a downgrade: an active org admin stays org admin
        m.role = "org_admin"
    m.invited_by_id, m.invitation_id = inv.invited_by_id, inv.id


def _write_enrollment(db: Session, user: User, inv: Invitation, course: Course, now: datetime) -> None:
    enr = get_enrollment(db, course.id, user.id)
    details = {"invitation_id": str(inv.id)}
    if enr is None:
        enr = Enrollment(course_id=course.id, user_id=user.id, role=inv.role, state="active", source="invite",
                         activated_at=now)
        db.add(enr)
        db.flush()
        add_event(db, enr, "staff_added", inv.invited_by_id, to_role=inv.role, to_state="active", details=details)
        return
    if enr.state == "active" and (enr.role == inv.role or enr.role == "teacher"):
        return  # already staff with at least this role
    old_role, old_state = enr.role, enr.state
    enr.role, enr.state, enr.source = inv.role, "active", "invite"
    enr.activated_at, enr.removed_at, enr.removed_by_id = now, None, None
    add_event(db, enr, "staff_added", inv.invited_by_id, from_role=old_role, to_role=inv.role,
              from_state=old_state, to_state="active", details=details)


def accept(db: Session, user: User, token: str, *, ip_hash: Optional[str],
           request: Optional[Request] = None) -> InvitationAcceptOut:
    """Authenticated; the account email must equal the invitation email. Single use; a second click by the same
    user answers with the same result (`already_accepted: true`). `token` may also be an invitation id from
    GET /me/invitations (then a mismatch is the generic 404)."""
    ratelimit.enforce(f"invite_accept:u:{user.id}", INVITE_ACCEPT_USER_10M)
    if ip_hash:
        allowed, retry = ratelimit.peek(f"invite_accept:ip:{ip_hash}", INVITE_ACCEPT_IP_FAIL_10M)
        if not allowed:
            raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
    by_id = _parse_id(token)
    if by_id is not None:
        inv = db.execute(select(Invitation).where(Invitation.id == by_id).with_for_update()).scalar_one_or_none()
    else:
        inv = _by_token(db, token, for_update=True)
    if inv is None:
        raise _accept_failure(db, ip_hash, not_found_invitation())
    org = load_organization(db, inv.organization_id)
    if org is None:
        raise _accept_failure(db, ip_hash, not_found_invitation())
    if inv.accepted_at is not None:
        if inv.accepted_user_id == user.id:
            out = _accept_out(inv, org.name, already=True)
            db.rollback()
            return out
        raise _accept_failure(db, ip_hash, not_found_invitation())
    if state_of(inv) != "pending":
        raise _accept_failure(db, ip_hash, not_found_invitation())
    email_ok = (user.email or "").strip().lower() == inv.email and bool(user.email_verified)
    if not email_ok:
        if by_id is not None:
            raise _accept_failure(db, ip_hash, not_found_invitation())
        raise _accept_failure(db, ip_hash, Forbidden("This invitation is for another email address",
                                                     code="invitation_email_mismatch"))
    if org.status != "active":
        db.rollback()
        raise Forbidden("Organization is suspended", code="organization_suspended")
    course = _course_of(db, inv)
    if inv.course_id is not None and course is None:
        raise _accept_failure(db, ip_hash, not_found_invitation())
    now = clock.now()
    if course is not None and inv.role == "student":
        # --- Phase 9 S3 --- (design 4.5): the enrollments accept hook (join lock order, honest refusals); on
        # course_full / course_not_open the transaction rolls back and the invitation stays usable
        try:
            accept_student_invitation(db, user, course, invitation_id=inv.id)
        except Conflict:
            db.rollback()
            raise
    elif course is not None:
        _write_enrollment(db, user, inv, course, now)
    else:
        _write_membership(db, user, inv, now)
    inv.accepted_at, inv.accepted_user_id = now, user.id
    _audit(db, user, "invitation_accepted", inv, request)
    out = _accept_out(inv, org.name, already=False)
    try:
        db.commit()
    except IntegrityError:  # a concurrent accept by the same user won the race (membership/enrollment unique)
        db.rollback()
        again = db.get(Invitation, inv.id)
        if again is not None and again.accepted_user_id == user.id:
            return _accept_out(again, org.name, already=True)
        raise Conflict("Invitation could not be accepted", code="invitation_conflict") from None
    return out
