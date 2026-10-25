"""phase 6 (S1): organizations, memberships, template grants, invitations; courses and banks get an organization

Revision ID: 0008_phase6_organizations
Revises: 0007_phase5_storage
Create Date: 2026-10-25

Schema first, then the data steps 1-7 of PHASE_6_DESIGN section 4 (deterministic: fixed uuid5 ids, insert where
missing), then NOT NULL (step 8). The same steps live in app/lms/organizations/bootstrap.py::ensure_organizations
for SQLite dev/tests; a PostgreSQL test asserts both paths yield the same rows. The id formulas are copied here on
purpose (a migration must not import app code that can change later); keep them identical to
app/lms/organizations/ids.py and app/lms/ort/seed.py::course_id_for.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase6_organizations"
down_revision: Union[str, None] = "0007_phase5_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
_FALSE = sa.text("false")
_EMPTY = sa.text("'{}'")

# Copies of app/lms/organizations/ids.py (ORG_NS, platform_org_id, personal_org_id, personal_org_slug)
ORG_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/organizations")
# Copy of app/lms/ort/seed.py NS and course_id_for(lang)
ORT_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/ort")
ORT_LANGUAGES = ("ky", "ru")
DEMO_TEACHER_ID = "usr_ort_demo_teacher"
CREATOR_SETTINGS = {"teachers_can_create_courses": True}
OLD_SOURCES = "source IN ('owner','join_code','staff_add','admin','invite','form','open')"
NEW_SOURCES = "source IN ('owner','join_code','staff_add','admin','invite','form','open','org_admin_self')"
OLD_TARGETS = "target_type IN ('user','course','teacher_request','enrollment')"
NEW_TARGETS = "target_type IN ('user','course','teacher_request','enrollment','organization','invitation')"


def _platform_org_id() -> uuid.UUID:
    return uuid.uuid5(ORG_NS, "org:platform")


def _personal_org_id(user_id: str) -> uuid.UUID:
    return uuid.uuid5(ORG_NS, f"org:personal:{user_id}")


def _personal_org_slug(user_id: str) -> str:
    return "t-" + hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


def _ort_course_id(lang: str) -> uuid.UUID:
    return uuid.uuid5(ORT_NS, f"ort-course:{lang}")


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete)


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.String(length=64), nullable=True)


# lightweight table handles for the data steps (typed, so uuid/json/bool bind correctly on PG and SQLite)
_orgs = sa.table(
    "organizations", sa.column("id", UUID), sa.column("slug", sa.String), sa.column("name", sa.String),
    sa.column("status", sa.String), sa.column("settings", sa.JSON), sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)), sa.column("suspended_at", sa.DateTime(timezone=True)),
    sa.column("suspended_reason", sa.String),
)
_members = sa.table(
    "organization_members", sa.column("id", UUID), sa.column("organization_id", UUID), sa.column("user_id", sa.String),
    sa.column("role", sa.String), sa.column("state", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
_grants = sa.table(
    "organization_template_grants", sa.column("id", UUID), sa.column("organization_id", UUID),
    sa.column("template_key", sa.String), sa.column("granted_at", sa.DateTime(timezone=True)),
)
_users = sa.table(
    "users", sa.column("id", sa.String), sa.column("display_name", sa.String), sa.column("teacher_status", sa.String),
    sa.column("is_platform_admin", sa.Boolean), sa.column("disabled_at", sa.DateTime(timezone=True)),
    sa.column("created_at", sa.DateTime),
)
_courses = sa.table(
    "courses", sa.column("id", UUID), sa.column("owner_id", sa.String), sa.column("organization_id", UUID),
    sa.column("template_key", sa.String), sa.column("template_version", sa.Integer),
    sa.column("template_settings", sa.JSON), sa.column("template_locked", sa.Boolean),
)
_banks = sa.table(
    "question_banks", sa.column("id", UUID), sa.column("owner_id", sa.String), sa.column("course_id", UUID),
    sa.column("organization_id", UUID),
)
_enrollments = sa.table(
    "enrollments", sa.column("id", UUID), sa.column("course_id", UUID), sa.column("user_id", sa.String),
    sa.column("role", sa.String), sa.column("state", sa.String), sa.column("source", sa.String),
    sa.column("activated_at", sa.DateTime(timezone=True)), sa.column("removed_at", sa.DateTime(timezone=True)),
    sa.column("removed_by_id", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
_events = sa.table(
    "enrollment_events", sa.column("id", UUID), sa.column("enrollment_id", UUID), sa.column("course_id", UUID),
    sa.column("actor_id", sa.String), sa.column("event", sa.String), sa.column("from_role", sa.String),
    sa.column("to_role", sa.String), sa.column("from_state", sa.String), sa.column("to_state", sa.String),
    sa.column("details", sa.JSON), sa.column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    _schema()
    _data(op.get_bind(), datetime.now(timezone.utc))
    with op.batch_alter_table("courses") as b:
        b.alter_column("organization_id", existing_type=UUID, nullable=False)
    with op.batch_alter_table("question_banks") as b:
        b.alter_column("organization_id", existing_type=UUID, nullable=False)


def _schema() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("parent_id", UUID, nullable=True),
        sa.Column("settings", JSONType, server_default=_EMPTY, nullable=False),
        _user("created_by_id"),
        _ts("suspended_at", True),
        sa.Column("suspended_reason", sa.String(length=500), nullable=True),
        _ts("deleted_at", True),
        _fk("organizations", "parent_id", "organizations", "RESTRICT"),
        _fk("organizations", "created_by_id", "users", "SET NULL"),
        sa.CheckConstraint("status IN ('active','suspended')", name=op.f("ck_organizations_status_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_status", "organizations", ["status"])
    op.create_index("ix_organizations_parent_id", "organizations", ["parent_id"])

    op.create_table(
        "invitations",
        sa.Column("id", UUID, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("course_id", UUID, nullable=True),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("invited_by_id", sa.String(length=64), nullable=False),
        _ts("expires_at"),
        _ts("accepted_at", True),
        _user("accepted_user_id"),
        _ts("revoked_at", True),
        _user("revoked_by_id"),
        _ts("created_at"),
        _fk("invitations", "organization_id", "organizations", "RESTRICT"),
        _fk("invitations", "course_id", "courses", "RESTRICT"),
        _fk("invitations", "invited_by_id", "users", "RESTRICT"),
        _fk("invitations", "accepted_user_id", "users", "SET NULL"),
        _fk("invitations", "revoked_by_id", "users", "SET NULL"),
        sa.CheckConstraint("role IN ('org_admin','teacher','assistant')", name=op.f("ck_invitations_role_valid")),
        sa.CheckConstraint("role <> 'org_admin' OR course_id IS NULL", name=op.f("ck_invitations_org_admin_no_course")),
        sa.CheckConstraint("role <> 'assistant' OR course_id IS NOT NULL",
                           name=op.f("ck_invitations_assistant_needs_course")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
    )
    op.create_index("ix_invitations_email", "invitations", ["email"])
    op.create_index("ix_invitations_organization_id_created_at", "invitations", ["organization_id", "created_at"])

    op.create_table(
        "organization_members",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        _user("invited_by_id"),
        sa.Column("invitation_id", UUID, nullable=True),
        _ts("removed_at", True),
        _user("removed_by_id"),
        _fk("organization_members", "organization_id", "organizations", "RESTRICT"),
        _fk("organization_members", "user_id", "users", "RESTRICT"),
        _fk("organization_members", "invited_by_id", "users", "SET NULL"),
        _fk("organization_members", "invitation_id", "invitations", "SET NULL"),
        _fk("organization_members", "removed_by_id", "users", "SET NULL"),
        sa.CheckConstraint("role IN ('org_admin','teacher')", name=op.f("ck_organization_members_role_valid")),
        sa.CheckConstraint("state IN ('active','removed')", name=op.f("ck_organization_members_state_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_members")),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_members_organization_id_user_id"),
    )
    op.create_index("ix_organization_members_user_id_state", "organization_members", ["user_id", "state"])

    op.create_table(
        "organization_template_grants",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("template_key", sa.String(length=32), nullable=False),
        _user("granted_by_id"),
        _ts("granted_at"),
        _user("revoked_by_id"),
        _ts("revoked_at", True),
        _fk("organization_template_grants", "organization_id", "organizations", "RESTRICT"),
        _fk("organization_template_grants", "granted_by_id", "users", "SET NULL"),
        _fk("organization_template_grants", "revoked_by_id", "users", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_template_grants")),
        sa.UniqueConstraint("organization_id", "template_key",
                            name="uq_organization_template_grants_organization_id_template_key"),
    )

    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("organization_id", UUID, nullable=True))
        b.add_column(sa.Column("template_key", sa.String(length=32), nullable=True))
        b.add_column(sa.Column("template_version", sa.Integer(), nullable=True))
        b.add_column(sa.Column("template_settings", JSONType, server_default=_EMPTY, nullable=False))
        b.add_column(sa.Column("template_locked", sa.Boolean(), server_default=_FALSE, nullable=False))
        b.create_foreign_key(op.f("fk_courses_organization_id_organizations"), "organizations",
                             ["organization_id"], ["id"], ondelete="RESTRICT")
        b.create_check_constraint(op.f("ck_courses_template_version_matches_key"),
                                  "(template_key IS NULL) = (template_version IS NULL)")
        b.create_index("ix_courses_organization_id_status_deleted_at", ["organization_id", "status", "deleted_at"])
    with op.batch_alter_table("question_banks") as b:
        b.add_column(sa.Column("organization_id", UUID, nullable=True))
        b.create_foreign_key(op.f("fk_question_banks_organization_id_organizations"), "organizations",
                             ["organization_id"], ["id"], ondelete="RESTRICT")
        b.create_index("ix_question_banks_organization_id", ["organization_id"])
    with op.batch_alter_table("enrollments") as b:
        b.drop_constraint(op.f("ck_enrollments_source_valid"), type_="check")
        b.create_check_constraint(op.f("ck_enrollments_source_valid"), NEW_SOURCES)
    with op.batch_alter_table("admin_audit_log") as b:
        b.drop_constraint(op.f("ck_admin_audit_log_target_type_valid"), type_="check")
        b.create_check_constraint(op.f("ck_admin_audit_log_target_type_valid"), NEW_TARGETS)


# ------------------------------------------------------------------------------------------------- data steps

def _suspension_reason(u) -> Optional[str]:
    """Copy of organizations/defaults.py::personal_suspension_reason: a disabled user, or an owner who is not an
    approved teacher, gets a suspended personal organization (as a revoke suspends it)."""
    if u.disabled_at is not None:
        return "account disabled"
    if u.teacher_status != "approved":
        return "teacher not approved"
    return None


def _ensure_org(conn, oid, slug, name, *, reason: Optional[str], now) -> None:
    if conn.execute(sa.select(_orgs.c.id).where(_orgs.c.id == oid)).first() is not None:
        return
    conn.execute(_orgs.insert().values(
        id=oid, slug=slug, name=(name or "").strip()[:200] or slug, status="suspended" if reason else "active",
        settings=dict(CREATOR_SETTINGS), created_at=now, updated_at=now,
        suspended_at=now if reason else None, suspended_reason=reason,
    ))


def _ensure_member(conn, oid, user_id, now) -> None:
    exists = conn.execute(sa.select(_members.c.id).where(
        _members.c.organization_id == oid, _members.c.user_id == user_id)).first()
    if exists is None:
        conn.execute(_members.insert().values(id=uuid.uuid4(), organization_id=oid, user_id=user_id,
                                              role="org_admin", state="active", created_at=now, updated_at=now))


def _data(conn, now) -> None:
    from app.core.config import settings  # PLATFORM_ORG_SLUG / PLATFORM_ORG_NAME (defaults platform / Platform)

    platform = _platform_org_id()
    # step 1: the platform organization (placeholders; renamed later by the owner)
    _ensure_org(conn, platform, settings.PLATFORM_ORG_SLUG, settings.PLATFORM_ORG_NAME, reason=None, now=now)
    users = {r.id: r for r in conn.execute(sa.select(
        _users.c.id, _users.c.display_name, _users.c.teacher_status, _users.c.is_platform_admin,
        _users.c.disabled_at, _users.c.created_at))}
    # step 2: a personal organization for every approved teacher (not the demo teacher, not platform admins)
    for uid in sorted(users):
        u = users[uid]
        if u.teacher_status == "approved" and uid != DEMO_TEACHER_ID and not u.is_platform_admin:
            oid = _personal_org_id(uid)
            _ensure_org(conn, oid, _personal_org_slug(uid), u.display_name, reason=_suspension_reason(u), now=now)
            _ensure_member(conn, oid, uid, now)
    # step 3: platform admins administer the platform organization
    for uid in sorted(users):
        if users[uid].is_platform_admin and uid != DEMO_TEACHER_ID:
            _ensure_member(conn, platform, uid, now)

    # step 4: the ORT courses (and their banks below) belong to the platform organization, template 'ort' v1
    ort_ids = {_ort_course_id(lang): lang for lang in ORT_LANGUAGES}
    present = {r.id: r for r in conn.execute(sa.select(_courses.c.id, _courses.c.owner_id).where(
        _courses.c.id.in_(list(ort_ids))))}
    for cid, lang in ort_ids.items():
        if cid in present:
            conn.execute(_courses.update().where(_courses.c.id == cid).values(
                organization_id=platform, template_key="ort", template_version=1,
                template_settings={"language": lang}, template_locked=True))
    if conn.execute(sa.select(_grants.c.id).where(_grants.c.organization_id == platform,
                                                  _grants.c.template_key == "ort")).first() is None:
        conn.execute(_grants.insert().values(id=uuid.uuid4(), organization_id=platform, template_key="ort",
                                             granted_at=now))

    # step 5: ORT ownership -> the earliest-created active platform admin (nothing when there is none)
    admins = sorted((u for u in users.values() if u.is_platform_admin and u.disabled_at is None
                     and u.id != DEMO_TEACHER_ID), key=lambda u: (u.created_at or now.replace(tzinfo=None), u.id))
    if admins:
        owner = admins[0].id
        for cid in present:
            if present[cid].owner_id != DEMO_TEACHER_ID:
                continue
            conn.execute(_courses.update().where(_courses.c.id == cid).values(owner_id=owner))
            _owner_enrollment(conn, cid, owner, now)

    # step 6: every other course -> its owner's personal organization (platform admins: the platform organization)
    rest = conn.execute(sa.select(_courses.c.id, _courses.c.owner_id).where(_courses.c.organization_id.is_(None))
                        .order_by(_courses.c.id)).all()
    for cid, owner_id in rest:
        conn.execute(_courses.update().where(_courses.c.id == cid).values(
            organization_id=_owner_org(conn, users, owner_id, platform, now)))

    # step 7: banks follow their course; a bank without a course takes its owner's organization
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text(
            "UPDATE question_banks AS b SET organization_id = c.organization_id FROM courses AS c "
            "WHERE b.course_id = c.id AND b.organization_id IS NULL"))
    else:
        conn.execute(sa.text(
            "UPDATE question_banks SET organization_id = (SELECT c.organization_id FROM courses AS c "
            "WHERE c.id = question_banks.course_id) WHERE course_id IS NOT NULL AND organization_id IS NULL"))
    loose = conn.execute(sa.select(_banks.c.id, _banks.c.owner_id).where(_banks.c.organization_id.is_(None))
                         .order_by(_banks.c.id)).all()
    for bid, owner_id in loose:
        conn.execute(_banks.update().where(_banks.c.id == bid).values(
            organization_id=_owner_org(conn, users, owner_id, platform, now)))

    # step 8 (counted only, A15): ORT presets outside the two ORT courses stay general courses
    n = conn.execute(sa.text(
        "SELECT count(*) FROM assessments a JOIN courses c ON c.id = a.course_id "
        "WHERE a.preset IN ('ort_main','ort_subject') AND c.template_key IS NULL")).scalar()
    log.info("0008: %s ort_* preset assessment(s) outside ORT courses left as general courses", n)


def _owner_org(conn, users, owner_id, platform, now):
    u = users.get(owner_id)
    if u is None or u.is_platform_admin:
        return platform
    oid = _personal_org_id(owner_id)
    _ensure_org(conn, oid, _personal_org_slug(owner_id), u.display_name, reason=_suspension_reason(u), now=now)
    return oid


def _owner_enrollment(conn, course_id, user_id, now) -> None:
    """The new ORT owner's enrollment becomes teacher/active (event admin_restored)."""
    row = conn.execute(sa.select(_enrollments.c.id, _enrollments.c.role, _enrollments.c.state).where(
        _enrollments.c.course_id == course_id, _enrollments.c.user_id == user_id)).first()
    if row is None:
        eid = uuid.uuid4()
        conn.execute(_enrollments.insert().values(
            id=eid, course_id=course_id, user_id=user_id, role="teacher", state="active", source="admin",
            activated_at=now, created_at=now, updated_at=now))
        before = (None, None)
    else:
        eid, before = row.id, (row.role, row.state)
        if before != ("teacher", "active"):
            conn.execute(_enrollments.update().where(_enrollments.c.id == eid).values(
                role="teacher", state="active", activated_at=now, removed_at=None, removed_by_id=None,
                updated_at=now))
    conn.execute(_events.insert().values(
        id=uuid.uuid4(), enrollment_id=eid, course_id=course_id, actor_id=None, event="admin_restored",
        from_role=before[0], to_role="teacher", from_state=before[1], to_state="active",
        details={"reason": "ort_owner", "from_user_id": DEMO_TEACHER_ID}, created_at=now))


def downgrade() -> None:
    op.execute("DELETE FROM enrollment_events WHERE enrollment_id IN "
               "(SELECT id FROM enrollments WHERE source = 'org_admin_self')")
    op.execute("DELETE FROM enrollments WHERE source = 'org_admin_self'")
    with op.batch_alter_table("enrollments") as b:
        b.drop_constraint(op.f("ck_enrollments_source_valid"), type_="check")
        b.create_check_constraint(op.f("ck_enrollments_source_valid"), OLD_SOURCES)
    op.execute("DELETE FROM admin_audit_log WHERE target_type IN ('organization','invitation')")
    with op.batch_alter_table("admin_audit_log") as b:
        b.drop_constraint(op.f("ck_admin_audit_log_target_type_valid"), type_="check")
        b.create_check_constraint(op.f("ck_admin_audit_log_target_type_valid"), OLD_TARGETS)
    with op.batch_alter_table("question_banks") as b:
        b.drop_index("ix_question_banks_organization_id")
        b.drop_constraint(op.f("fk_question_banks_organization_id_organizations"), type_="foreignkey")
        b.drop_column("organization_id")
    with op.batch_alter_table("courses") as b:
        b.drop_index("ix_courses_organization_id_status_deleted_at")
        b.drop_constraint(op.f("ck_courses_template_version_matches_key"), type_="check")
        b.drop_constraint(op.f("fk_courses_organization_id_organizations"), type_="foreignkey")
        for col in ("template_locked", "template_settings", "template_version", "template_key", "organization_id"):
            b.drop_column(col)
    op.drop_table("organization_template_grants")
    op.drop_table("organization_members")
    op.drop_table("invitations")
    op.drop_table("organizations")

