"""Platform-admin user operations (design 3.6) and read helpers for the admin queue/audit."""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.lms.audit import service as audit
from app.lms.audit.models import AdminAuditLog
from app.lms.core.errors import Conflict, NotFound
from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.courses.scopes import regular_courses  # Phase 8b S1
from app.lms.enrollments.models import Enrollment
from app.lms.organizations.ids import personal_org_id
from app.lms.organizations.models import Organization, OrganizationMember
from app.lms.organizations.tree import within_clause
from app.lms.platform_admin.schemas import (
    AdminUserDetailOut, AdminUserOut, AuditEntryOut, OwnedCourseBrief, RevokeImpactOut, SignInMethodOut,
    TeacherRequestAdminOut, UserBrief,
)
from app.lms.teachers.models import TeacherRequest
from app.models.user import User


def get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is not None and user.is_test_student:  # Student view test students are not accounts to manage
        user = None
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
    target.token_version = (target.token_version or 0) + 1  # Phase 11 S4: enabling again does not revive old tokens
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


def search_users(q: Optional[str], teacher_status: Optional[str], disabled: Optional[bool], *,
                 email_unverified: bool = False, platform_admin: bool = False, has_access: bool = False,
                 now=None):
    """S4: email or name substring (case-insensitive), plus filters; one statement, paged by (created_at, id) on
    `ix_users_created_at_id`, so a page reads index order until it has its rows (bounded by the page, not the table).
    Past ~50k users, a pg_trgm index on lower(email) and lower(display_name) is the fix for substring search."""
    stmt = select(User).where(User.is_test_student.is_(False))
    if q:
        term = q.strip().lower()
        if term:
            stmt = stmt.where(or_(
                func.lower(User.email).contains(term, autoescape=True),
                func.lower(User.display_name).contains(term, autoescape=True),
            ))
    if teacher_status:
        stmt = stmt.where(User.teacher_status == teacher_status)
    if disabled is True:
        stmt = stmt.where(User.disabled_at.is_not(None))
    elif disabled is False:
        stmt = stmt.where(User.disabled_at.is_(None))
    if email_unverified:
        stmt = stmt.where(User.email_verified.is_(False))
    if platform_admin:
        stmt = stmt.where(User.is_platform_admin.is_(True))
    if has_access:
        from app.lms.access.models import AccessPass
        from app.lms.core import clock

        at = now or clock.now()
        stmt = stmt.where(exists().where(AccessPass.user_id == User.id, AccessPass.revoked_at.is_(None),
                                         AccessPass.starts_at <= at, AccessPass.ends_at > at))
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
               target_id: Optional[str], acting_as: Optional[str] = None):
    stmt = select(AdminAuditLog)
    if acting_as:  # item 4: `details.acting_as` (JSON path; json_extract on SQLite, ->> on PostgreSQL)
        stmt = stmt.where(AdminAuditLog.details["acting_as"].as_string() == acting_as)
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
        disabled_reason=user.disabled_reason, mfa_enabled=user.mfa_enabled_at is not None,
        last_login_at=user.last_login_at,
    )


TEACHES_AT_MAX = 5


def teaches_at(db: Session, user_ids: list[str]) -> dict[str, list[str]]:
    """Per applicant, the active schools (or the platform) they belong to, directly or through a department; at most
    `TEACHES_AT_MAX` each, whatever the page size (one query)."""
    if not user_ids:
        return {}
    root, own = aliased(Organization), aliased(Organization)
    pairs = (
        select(OrganizationMember.user_id.label("user_id"), root.name.label("name"))
        .join(own, own.id == OrganizationMember.organization_id)
        .join(root, within_clause(own.path, root.path))
        .where(OrganizationMember.user_id.in_(user_ids), OrganizationMember.state == "active",
               own.deleted_at.is_(None), root.deleted_at.is_(None), root.parent_id.is_(None),
               root.status == "active", root.kind.in_(("school", "platform")))
        .distinct().subquery()
    )
    rank = func.row_number().over(partition_by=pairs.c.user_id, order_by=pairs.c.name).label("rank")
    ranked = select(pairs.c.user_id, pairs.c.name, rank).subquery()
    out: dict[str, list[str]] = {}
    for uid, name in db.execute(select(ranked.c.user_id, ranked.c.name).where(ranked.c.rank <= TEACHES_AT_MAX)
                                .order_by(ranked.c.user_id, ranked.c.rank)):
        out.setdefault(uid, []).append(name)
    return out


def requests_out(db: Session, reqs: list[TeacherRequest]) -> list[TeacherRequestAdminOut]:
    schools = teaches_at(db, list({r.user_id for r in reqs}))
    return [request_out(db, r, schools.get(r.user_id, [])) for r in reqs]


def request_out(db: Session, req: TeacherRequest, schools: Optional[list[str]] = None) -> TeacherRequestAdminOut:
    user = db.get(User, req.user_id)
    decider = db.get(User, req.decided_by_id) if req.decided_by_id else None
    if schools is None:
        schools = teaches_at(db, [req.user_id]).get(req.user_id, [])
    return TeacherRequestAdminOut(
        id=req.id, user=brief(user), user_teacher_status=user.teacher_status, message=req.message,
        status=req.status, reason=req.reason, created_at=req.created_at, decided_at=req.decided_at,
        decided_by=brief(decider), applicant_name=req.applicant_name, school=req.school, subject=req.subject,
        phone=req.phone, teaches_at=schools,
    )


def revoke_impact(db: Session, user: User) -> RevokeImpactOut:
    """What a revoke freezes: the personal organization's courses and their students, never test students or the hidden
    preview courses of exam templates."""
    in_org = (Course.organization_id == personal_org_id(user.id), Course.deleted_at.is_(None), regular_courses())
    courses = db.execute(select(func.count()).select_from(Course).where(*in_org)).scalar_one()
    students = db.execute(
        select(func.count(Enrollment.user_id.distinct())).join(Course, Course.id == Enrollment.course_id)
        .where(*in_org, Enrollment.role == "student", Enrollment.state == "active",
               Enrollment.is_test_student.is_(False))
    ).scalar_one()
    return RevokeImpactOut(students=students, courses=courses)


def user_detail(db: Session, user: User) -> AdminUserDetailOut:
    courses = db.execute(
        select(Course).where(Course.owner_id == user.id, Course.deleted_at.is_(None),
                             regular_courses())  # Phase 8b S1
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
        teacher_requests=requests_out(db, list(reqs)),
        revoke_impact=revoke_impact(db, user),
        **person_extras(db, user),
        sign_in_methods=sign_in_methods(db, user),
        teaching=_teaching(db, user),
    )


def _teaching(db: Session, user: User):
    """Step 3b S3: the person page's «Преподавание» card (the person's Admin → Преподаватели row)."""
    from app.lms.platform_admin.teachers import teaching_of

    return teaching_of(db, user)


def sign_in_methods(db: Session, user: User) -> list[SignInMethodOut]:
    """Item 3: the password (when the account has a usable one) and the linked providers with the link date. The
    provider's email and subject are not shown."""
    from app.lms.oauth.models import PROVIDERS, UserIdentity
    from app.lms.privacy.anonymize import UNUSABLE_PASSWORD_HASH

    out = []
    if user.password_hash and user.password_hash != UNUSABLE_PASSWORD_HASH:
        out.append(SignInMethodOut(method="password"))
    rows = db.execute(
        select(UserIdentity.provider, UserIdentity.linked_at).where(UserIdentity.user_id == user.id)
    ).all()
    linked = dict(rows)
    out.extend(SignInMethodOut(method=p, linked_at=linked[p]) for p in PROVIDERS if p in linked)
    return out


def person_extras(db: Session, user: User) -> dict:
    """S4 person page: age and consent, parent links (display names only), the pending email change."""
    from app.lms.platform_admin.persons import parent_links, pending_email

    return dict(age_band=user.age_band, consent_state=user.consent_state, consent_due_at=user.consent_due_at,
                deleted=user.deleted_at is not None, parent_links=parent_links(db, user.id),
                pending_email_change=pending_email(db, user.id))


def audit_out(db: Session, row: AdminAuditLog, actor: Optional[User] = None,
              target_kind: Optional[str] = None) -> AuditEntryOut:
    return AuditEntryOut(
        id=row.id, created_at=row.created_at, actor=brief(actor or db.get(User, row.actor_id)), action=row.action,
        target_type=row.target_type, target_id=row.target_id, reason=row.reason, details=row.details,
        target_kind=target_kind,
    )


def _org_kinds(db: Session, rows: list[AdminAuditLog]) -> dict[str, str]:
    """Step 3b S3: {organization id: kind} for the page's organization targets (one statement, none without any), so
    the viewer labels a personal organization «личное пространство преподавателя» instead of an organization."""
    import uuid

    ids = set()
    for r in rows:
        if r.target_type == "organization":
            try:
                ids.add(uuid.UUID(str(r.target_id)))
            except ValueError:
                continue
    if not ids:
        return {}
    return {str(oid): kind for oid, kind in db.execute(
        select(Organization.id, Organization.kind).where(Organization.id.in_(ids))).all()}


def audit_page_out(db: Session, rows: list[AdminAuditLog]) -> list[AuditEntryOut]:
    """Fix round 2026-11-12 P1: the actors of a page in one statement (was one `db.get` per row)."""
    ids = {r.actor_id for r in rows}
    actors = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    kinds = _org_kinds(db, rows)
    return [audit_out(db, r, actors.get(r.actor_id),
                      kinds.get(str(r.target_id)) if r.target_type == "organization" else None) for r in rows]
