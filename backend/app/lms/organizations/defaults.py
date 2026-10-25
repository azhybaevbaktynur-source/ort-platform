"""Connection-level helpers shared by the bootstrap and the insert defaults (PHASE_6_DESIGN section 4).

Everything here is Core on a Connection, insert-where-missing with fixed uuid5 ids, so it can run inside a mapper
`before_insert` hook, in the lifespan bootstrap and in tests alike."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.core.config import settings
from app.lms.core.models import utcnow
from app.lms.organizations.ids import personal_org_id, personal_org_slug, platform_org_id
from app.lms.organizations.models import Organization, OrganizationMember

DEMO_TEACHER_ID = "usr_ort_demo_teacher"  # same value as app.lms.ort.seed.DEMO_TEACHER_ID
CREATOR_SETTINGS = {"teachers_can_create_courses": True}


def insert_ignore(conn: Connection, table, values: dict) -> bool:
    """INSERT ... ON CONFLICT DO NOTHING on PostgreSQL and SQLite; True when a row was written."""
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    res = conn.execute(insert(table).values(**values).on_conflict_do_nothing())
    return bool(res.rowcount)


def ensure_platform_org(conn: Connection) -> uuid.UUID:
    oid = platform_org_id()
    if conn.execute(select(Organization.id).where(Organization.id == oid)).first() is None:
        now = utcnow()
        insert_ignore(conn, Organization.__table__, dict(
            id=oid, slug=settings.PLATFORM_ORG_SLUG, name=settings.PLATFORM_ORG_NAME, status="active",
            settings=dict(CREATOR_SETTINGS), created_at=now, updated_at=now,
        ))
    return oid


def ensure_membership(conn: Connection, organization_id: uuid.UUID, user_id: str, role: str = "org_admin") -> bool:
    """Insert where missing; an existing row (also a removed one) is left as it is."""
    now = utcnow()
    return insert_ignore(conn, OrganizationMember.__table__, dict(
        id=uuid.uuid4(), organization_id=organization_id, user_id=user_id, role=role, state="active",
        created_at=now, updated_at=now,
    ))


def personal_suspension_reason(disabled: bool, approved: bool) -> Optional[str]:
    """Why a new personal organization starts suspended (None: active). A disabled user, or an owner who is not an
    approved teacher, gets a suspended one (as a revoke suspends it). Migration 0008 copies this rule."""
    if disabled:
        return "account disabled"
    if not approved:
        return "teacher not approved"
    return None


def ensure_personal_org(conn: Connection, user_id: str, display_name: Optional[str], disabled: bool, *,
                        with_membership: bool, approved: bool = True) -> uuid.UUID:
    """The personal organization of an independent teacher (fixed id and slug); suspended when the user is
    disabled or not an approved teacher. `with_membership` adds the org_admin membership (approved teachers)."""
    oid = personal_org_id(user_id)
    if conn.execute(select(Organization.id).where(Organization.id == oid)).first() is None:
        now = utcnow()
        slug = personal_org_slug(user_id)
        reason = personal_suspension_reason(disabled, approved)
        insert_ignore(conn, Organization.__table__, dict(
            id=oid, slug=slug, name=(display_name or "").strip()[:200] or slug,
            status="suspended" if reason else "active", settings=dict(CREATOR_SETTINGS),
            created_by_id=None, created_at=now, updated_at=now,
            suspended_at=now if reason else None, suspended_reason=reason,
        ))
    if with_membership:
        ensure_membership(conn, oid, user_id)
    return oid


def default_org_for_owner(conn: Connection, owner_id: str) -> uuid.UUID:
    """Organization of a course or bank written without one (migration steps 6 and 7): platform admins -> the
    platform organization, everybody else -> their personal organization (created when missing)."""
    from app.models.user import User

    row = conn.execute(select(User.is_platform_admin, User.disabled_at, User.display_name, User.teacher_status)
                       .where(User.id == owner_id)).first()
    if row is None or row.is_platform_admin:
        return ensure_platform_org(conn)
    approved = row.teacher_status == "approved"
    return ensure_personal_org(conn, owner_id, row.display_name, row.disabled_at is not None,
                               with_membership=approved and owner_id != DEMO_TEACHER_ID, approved=approved)


def course_org_listener(mapper, conn: Connection, target) -> None:
    """before_insert on courses: a course written without an organization gets its owner's (design 4 step 6)."""
    if getattr(target, "organization_id", None) is None and target.owner_id:
        target.organization_id = default_org_for_owner(conn, target.owner_id)


def bank_org_listener(mapper, conn: Connection, target) -> None:
    """before_insert on question_banks: a bank copies its course's organization, else its owner's (step 7)."""
    if getattr(target, "organization_id", None) is not None:
        return
    if target.course_id is not None:
        from app.lms.courses.models import Course

        oid = conn.execute(select(Course.organization_id).where(Course.id == target.course_id)).scalar()
        if oid is not None:
            target.organization_id = oid
            return
    if target.owner_id:
        target.organization_id = default_org_for_owner(conn, target.owner_id)


def ort_course_fields(conn: Connection, lang: str) -> dict:
    """Columns of a new ORT course (design 4 step 4): platform organization, locked ORT template v1."""
    return dict(organization_id=ensure_platform_org(conn), template_key="ort", template_version=1,
                template_settings={"language": lang}, template_locked=True)
