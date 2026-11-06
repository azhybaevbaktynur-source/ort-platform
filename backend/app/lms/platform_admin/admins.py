"""S1 admin security: who is a platform admin (docs/DISCUSSION_ADMIN_CENTER.md A3). Shared by the admin user page and
`make_admin.py`. The platform is never left without an active platform admin."""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.lms.audit import service as audit
from app.lms.core.errors import Conflict
from app.lms.core.models import utcnow
from app.lms.mfa import service as mfa
from app.lms.platform_admin.users_service import get_user_or_404
from app.models.user import User


def active_admin_ids(db: Session, *, lock: bool = False) -> list[str]:
    """Active platform admins; `lock` takes their rows FOR UPDATE (PostgreSQL), so two removals at once cannot both see
    the other as the one left."""
    stmt = select(User.id).where(User.is_platform_admin.is_(True), User.disabled_at.is_(None),
                                 User.deleted_at.is_(None), User.is_test_student.is_(False))
    if lock:
        stmt = stmt.order_by(User.id).with_for_update()
    return list(db.execute(stmt).scalars())


def is_last_active_admin(db: Session, user: User) -> bool:
    ids = active_admin_ids(db, lock=True)
    return user.id in ids and len(ids) <= 1


def ensure_platform_membership(db: Session, user_id: str) -> None:
    """Platform admins administer the platform organization (Phase 6 S1). Insert where missing; a removed row revives."""
    from app.lms.organizations.defaults import ensure_membership, ensure_platform_org
    from app.lms.organizations.models import OrganizationMember

    conn = db.connection()
    org_id = ensure_platform_org(conn)
    if not ensure_membership(conn, org_id, user_id):
        conn.execute(update(OrganizationMember.__table__).where(
            OrganizationMember.organization_id == org_id, OrganizationMember.user_id == user_id,
            OrganizationMember.state != "active").values(state="active", role="org_admin", removed_at=None,
                                                         removed_by_id=None))


def remove_platform_membership(db: Session, user_id: str) -> None:
    from app.lms.organizations.ids import platform_org_id
    from app.lms.organizations.models import OrganizationMember

    db.connection().execute(update(OrganizationMember.__table__).where(
        OrganizationMember.organization_id == platform_org_id(), OrganizationMember.user_id == user_id,
        OrganizationMember.state == "active").values(state="removed", removed_at=utcnow()))


def grant(db: Session, target: User) -> None:
    """Not committed. Not a teacher by this: the new admin is only an admin (and sets up two-step login first)."""
    target.is_platform_admin = True
    ensure_platform_membership(db, target.id)


def revoke(db: Session, target: User) -> None:
    """Not committed. Refuses (409 `last_platform_admin`) to remove the last active platform admin."""
    if is_last_active_admin(db, target):
        raise Conflict("The platform needs at least one active platform admin", code="last_platform_admin")
    target.is_platform_admin = False
    remove_platform_membership(db, target.id)


def set_platform_admin(db: Session, admin: User, user_id: str, make_admin: bool, reason: str, code: str,
                       request: Optional[Request]) -> User:
    """The admin user page: make or remove a platform admin, confirmed with the acting admin's current code."""
    target = get_user_or_404(db, user_id)
    if make_admin:
        if target.is_platform_admin:
            raise Conflict("Already a platform admin", code="already_platform_admin")
        if not target.email_verified:
            raise Conflict("The email address is not confirmed", code="target_email_not_verified")
        if target.disabled_at is not None or target.deleted_at is not None:
            raise Conflict("This account is disabled", code="target_disabled")
    elif not target.is_platform_admin:
        raise Conflict("Not a platform admin", code="not_platform_admin")
    else:
        # Security review: lock every active admin row first (ordered by id), before the code check writes the acting
        # admin's own row; two admins removing each other at once then wait in turn instead of deadlocking.
        active_admin_ids(db, lock=True)
    mfa.require_code(db, admin, code)
    if make_admin:
        grant(db, target)
    else:
        revoke(db, target)
    audit.record(db, actor=admin, action="user.platform_admin.grant" if make_admin else "user.platform_admin.revoke",
                 target_type="user", target_id=target.id, reason=reason, request=request)
    db.commit()
    return target


def end_sessions(db: Session, admin: User, user_id: str, reason: str, request: Optional[Request]) -> User:
    """Every token of the account stops working (token_version); the account itself stays as it is."""
    target = get_user_or_404(db, user_id)
    target.token_version = (target.token_version or 0) + 1
    audit.record(db, actor=admin, action="user.end_sessions", target_type="user", target_id=target.id, reason=reason,
                 request=request)
    db.commit()
    return target
