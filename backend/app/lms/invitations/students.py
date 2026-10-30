"""Student invitations (PHASE_9_DESIGN 4.5, 4.8, invariant 8, P9-5).

A course's staff (teacher `roster.manage`; org admins of the course's tree through `ORG_ADMIN_ACTIONS`, audited like
every invitation write; assistants 403) invite up to 50 addresses per request. Each one becomes an `invitations` row
with `role = 'student'` and the course, valid for 14 days; the student accepts it through the public invitation
routes, which enroll through `enrollments.service.accept_student_invitation` (course lock, `course_full`).

No enumeration: every address gets the same row shape whether or not it has an account; only an existing active
enrollment is reported (`already_enrolled`), and only to course staff, who already see the roster. The shared
`invite_send_1h` limit (50 per actor per hour, with staff and organization invitations) counts one per address and
refuses the whole request before any write. Emails are sent after the commit (`BackgroundTasks`)."""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from fastapi import BackgroundTasks, Request
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, Forbidden, NotFound, RateLimited, ValidationFailed
from app.lms.core.ratelimit import Limit, RateLimitBucket
from app.lms.courses.models import Course
from app.lms.courses.service import assert_not_sandbox, paginate_rows, require_course
from app.lms.enrollments.models import Enrollment
from app.lms.invitations import emails
from app.lms.invitations import service as inv
from app.lms.invitations.policies import load_organization
from app.lms.invitations.schemas import (
    InvitationCreatedOut, InvitationOut, StudentInvitationsOut, StudentInviteRowOut,
)
from app.lms.organizations.models import Invitation, Organization
from app.models.user import User

E_STUDENT_INVITATIONS_DISABLED = "student_invitations_disabled"


# ---------------------------------------------------------------- shared helpers (also used by the roster import)

def hit_many(key: str, rule: Limit, n: int) -> None:
    """Count `n` events of `rule` at once, or refuse all of them (429) when they do not fit in the current window.
    A refused request counts nothing, so a too-large batch does not lock the actor out of a smaller one."""
    if n <= 0:
        return
    engine = ratelimit._engine()
    now = ratelimit._now()
    ws = ratelimit._window(now, rule)
    expires = ws + rule.window_seconds
    t = RateLimitBucket.__table__
    bucket = ratelimit._bucket_key(key, rule)
    with engine.begin() as conn:
        current = conn.execute(
            select(t.c.count).where(t.c.key == bucket, t.c.window_start == ws)
        ).scalar_one_or_none() or 0
        if current + n > rule.limit:
            raise RateLimited("Too many requests", details={"retry_after_seconds": max(1, expires - now)})
        ins = (pg_insert if engine.dialect.name == "postgresql" else sqlite_insert)(t).values(
            key=bucket, window_start=ws, count=n, expires_at=expires)
        conn.execute(ins.on_conflict_do_update(index_elements=[t.c.key, t.c.window_start],
                                               set_={"count": t.c.count + n}))


def send_mails(mails: Iterable[emails.InvitationEmail]) -> None:
    """Background task: one email per invitation; a failed send never raises (the invitation exists either way)."""
    for mail in mails:
        emails.send_invitation_email(mail)


def users_by_email(db: Session, addresses: list[str]) -> dict[str, User]:
    if not addresses:
        return {}
    rows = db.execute(select(User).where(func.lower(User.email).in_(addresses))).scalars()
    return {(u.email or "").strip().lower(): u for u in rows}


def active_enrolled_emails(db: Session, course_id: uuid.UUID, addresses: list[str]) -> set[str]:
    """Addresses (lowercased) with an active enrollment in the course, in any role (one query)."""
    if not addresses:
        return set()
    rows = db.execute(
        select(func.lower(User.email)).join(Enrollment, Enrollment.user_id == User.id)
        .where(Enrollment.course_id == course_id, Enrollment.state == "active", func.lower(User.email).in_(addresses))
    ).scalars()
    return set(rows)


def open_invitation_emails(db: Session, organization_id: uuid.UUID, course_id: Optional[uuid.UUID],
                           addresses: list[str]) -> set[str]:
    """Addresses with a pending invitation to this target (organization + course, or the organization alone)."""
    if not addresses:
        return set()
    now = clock.now()
    course_cond = Invitation.course_id.is_(None) if course_id is None else Invitation.course_id == course_id
    rows = db.execute(
        select(Invitation.email).where(
            Invitation.organization_id == organization_id, course_cond, Invitation.email.in_(addresses),
            Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None), Invitation.expires_at > now,
        )
    ).scalars()
    return set(rows)


def ensure_student_invitations_enabled(db: Session, org: Organization) -> None:
    from app.lms.organizations.settings import settings_of

    if not settings_of(db, org).student_invitations_enabled:
        raise Conflict("Student invitations are turned off for this organization",
                       code=E_STUDENT_INVITATIONS_DISABLED)


def _course_org(ctx: AuthzContext, course: Course) -> Organization:
    """Authorization of every student-invitation route: course `roster.manage` (404 for outsiders, 403 for
    assistants), never a template sandbox; course staff of a suspended organization get the specific code."""
    db = ctx.db
    if ctx.role_for(course.id) in inv.STAFF_ROLES:
        staff_org = load_organization(db, course.organization_id)
        if staff_org is not None:
            inv._ensure_active_org(staff_org)
    require_course(ctx, A.ROSTER_MANAGE, course)
    assert_not_sandbox(course)
    org = load_organization(db, course.organization_id)
    if org is None:
        raise NotFound("Course not found", code="course_not_found")
    return org


# ---------------------------------------------------------------- create (bulk)

def create_student_invitations(db: Session, ctx: AuthzContext, course: Course, *, addresses: list[str],
                               message: Optional[str], language: str, background: Optional[BackgroundTasks],
                               request: Optional[Request] = None) -> StudentInvitationsOut:
    org = _course_org(ctx, course)
    inv._ensure_active_org(org)
    ensure_student_invitations_enabled(db, org)
    actor = ctx.user

    rows: list[tuple[str, str]] = []  # (address as shown, result) in the submitted order
    valid: list[str] = []
    seen: set[str] = set()
    for raw in addresses:
        try:
            email = inv.normalize_email(raw)
        except ValidationFailed:
            rows.append(((raw or "").strip()[:255], "invalid_email"))
            continue
        if email in seen:
            rows.append((email, "duplicate"))
            continue
        seen.add(email)
        valid.append(email)
        rows.append((email, "pending"))

    enrolled = active_enrolled_emails(db, course.id, valid)
    to_invite = [e for e in valid if e not in enrolled]
    db.rollback()  # nothing written yet; the rate-limit counter uses its own connection
    hit_many(f"invite_send:{actor.id}", inv.INVITE_SEND_1H, len(to_invite))

    now = clock.now()
    created: dict[str, tuple[Invitation, str]] = {}
    for email in to_invite:
        inv._revoke_open(db, org.id, email, course.id, actor, now)
        row, token = inv._insert(db, actor=actor, org=org, email=email, role="student", course=course,
                                 message=message, language=language, now=now)
        inv._audit(db, actor, "invitation_created", row, request, source="student_invitations")
        created[email] = (row, token)
    db.commit()

    mails = [inv.build_mail(row, token, actor, org, course) for row, token in created.values()]
    if mails:
        if background is not None:
            background.add_task(send_mails, mails)
        else:
            send_mails(mails)

    items: list[StudentInviteRowOut] = []
    for email, result in rows:
        if result != "pending":
            items.append(StudentInviteRowOut(email=email, result=result))
        elif email in enrolled:
            items.append(StudentInviteRowOut(email=email, result="already_enrolled"))
        else:
            row = created[email][0]
            items.append(StudentInviteRowOut(email=email, result="invited",
                                             invitation=inv.item_out(row, course.title, actor, now)))
    return StudentInvitationsOut(
        items=items, invited=len(created), already_enrolled=sum(1 for i in items if i.result == "already_enrolled"),
        invalid=sum(1 for i in items if i.result in ("invalid_email", "duplicate")),
    )


# ---------------------------------------------------------------- list, revoke, resend

def list_student_invitations(db: Session, ctx: AuthzContext, course: Course, *, state: Optional[str],
                             cursor: Optional[str], limit: Optional[int]) -> tuple[list[InvitationOut], Optional[str]]:
    _course_org(ctx, course)
    now = clock.now()
    stmt = (
        select(Invitation, User)
        .outerjoin(User, User.id == Invitation.invited_by_id)
        .where(Invitation.course_id == course.id, Invitation.role == "student")
    )
    if state:
        stmt = stmt.where(inv._state_condition(state, now))
    rows, nxt = paginate_rows(db, stmt, sort_col=Invitation.created_at, id_col=Invitation.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    return [inv.item_out(row, course.title, inviter, now) for row, inviter in rows], nxt


def _load(db: Session, course: Course, invitation_id: uuid.UUID) -> Invitation:
    row = db.execute(select(Invitation).where(
        Invitation.id == invitation_id, Invitation.course_id == course.id, Invitation.role == "student",
    )).scalar_one_or_none()
    if row is None:
        raise inv.not_found_invitation()
    return row


def revoke_student_invitation(db: Session, ctx: AuthzContext, course: Course, invitation_id: uuid.UUID,
                              request: Optional[Request] = None) -> InvitationOut:
    """Revoking twice is a no-op; an accepted invitation cannot be revoked (409 `invitation_not_pending`)."""
    org = _course_org(ctx, course)
    inv._ensure_active_org(org)
    row = _load(db, course, invitation_id)
    if row.accepted_at is not None:
        raise Conflict("Invitation already accepted", code="invitation_not_pending")
    if row.revoked_at is None:
        row.revoked_at = clock.now()
        row.revoked_by_id = ctx.user.id
        inv._audit(db, ctx.user, "invitation_revoked", row, request)
        db.commit()
    return inv.item_out(row, course.title, db.get(User, row.invited_by_id))


def resend_student_invitation(db: Session, ctx: AuthzContext, course: Course, invitation_id: uuid.UUID,
                              request: Optional[Request] = None) -> InvitationCreatedOut:
    """A new token and row (same email, message, language); the old one is revoked. Pending or expired only."""
    org = _course_org(ctx, course)
    inv._ensure_active_org(org)
    ensure_student_invitations_enabled(db, org)
    row = _load(db, course, invitation_id)
    if row.accepted_at is not None or row.revoked_at is not None:
        raise Conflict("Invitation is not pending", code="invitation_not_pending")
    email, message, language, old_id = row.email, row.message, row.language, row.id
    if email in active_enrolled_emails(db, course.id, [email]):
        raise Conflict("Already enrolled", code="already_enrolled")
    db.rollback()
    ratelimit.enforce(f"invite_send:{ctx.user.id}", inv.INVITE_SEND_1H)
    org = load_organization(db, course.organization_id)
    if org is None:
        raise Forbidden("Organization is suspended", code="organization_suspended")
    old = _load(db, course, old_id)
    if old.revoked_at is None:  # also when the course moved to another department since (other organization_id)
        old.revoked_at, old.revoked_by_id = clock.now(), ctx.user.id
    return inv._create_and_send(db, actor=ctx.user, org=org, email=email, role="student", course=course,
                                message=message, language=language, request=request, action="invitation_resent",
                                extra={"replaces_invitation_id": str(old_id)})
