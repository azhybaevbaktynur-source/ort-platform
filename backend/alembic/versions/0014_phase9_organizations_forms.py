"""phase 9 (S1): organization tree, shared banks, roster imports, enrollment forms and applications

Revision ID: 0014_phase9_organizations_forms
Revises: 0013_phase8b_template_sandbox
Create Date: 2026-10-31

PHASE_9_DESIGN section 2. Schema plus three bounded data steps:

1. `organizations.kind / path / depth` (Python backfill; organizations are few): the platform organization
   (`platform_org_id()`) -> `platform`; a personal organization (`personal_org_id(user)` with its
   `personal_org_slug(user)`, or the slug of an active org-admin member) -> `personal`; a row with a parent ->
   `department`; anything else -> `school`. `path` is the chain of ids from the root (32-hex segments, `/`-joined),
   `depth` its length - 1; production has no parent anywhere, so every row becomes its own root (`path = id`). A
   parent chain deeper than 2 or a cycle refuses the migration. Departments' `settings` become `{}` (root only).
2. `question_banks.visibility` = `private` for every existing bank (server default; ORT banks included).
3. `courses.catalog_search` = lowercased titles and descriptions of every course, in batches of 500 (the formula is
   a copy of `app.lms.courses.models.catalog_search_text`; keep them identical).

New tables: `organization_roster_imports`, `enrollment_forms`, `enrollment_form_fields`, `enrollment_applications`.
`invitations.role` gains `student` (+ CHECK student needs a course) and `roster_import_id`.

Downgrade (design 2.7) drops the new tables and columns and restores the three-value `role_valid`; it is lossy for
rows that used the new values (student invitations are deleted; applications, forms, roster imports, sharing state,
kinds and paths are dropped; department rows stay as plain organizations with a parent), which a rollback accepts.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0014_phase9_organizations_forms"
down_revision: Union[str, None] = "0013_phase8b_template_sandbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
TS = sa.DateTime(timezone=True)
MAX_DEPTH = 2
BATCH = 500

# Copies of app/lms/organizations/ids.py (ORG_NS, platform_org_id, personal_org_id, personal_org_slug)
ORG_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/organizations")


def _platform_org_id() -> uuid.UUID:
    return uuid.uuid5(ORG_NS, "org:platform")


def _personal_org_id(user_id: str) -> uuid.UUID:
    return uuid.uuid5(ORG_NS, f"org:personal:{user_id}")


def _personal_org_slug(user_id: str) -> str:
    import hashlib

    return "t-" + hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


def _catalog_search_text(title, description) -> str:
    """Copy of app.lms.courses.models.catalog_search_text."""
    parts = []
    for blob in (title, description):
        if isinstance(blob, dict):
            for lang in sorted(blob):
                value = blob[lang]
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
    return " ".join(parts).lower()


_orgs = sa.table(
    "organizations", sa.column("id", UUID), sa.column("slug", sa.String), sa.column("parent_id", UUID),
    sa.column("kind", sa.String), sa.column("path", sa.String), sa.column("depth", sa.SmallInteger),
    sa.column("settings", JSONType),
)
_members = sa.table(
    "organization_members", sa.column("organization_id", UUID), sa.column("user_id", sa.String),
    sa.column("role", sa.String), sa.column("state", sa.String),
)
_users = sa.table("users", sa.column("id", sa.String))
_courses = sa.table(
    "courses", sa.column("id", UUID), sa.column("title", JSONType), sa.column("description", JSONType),
    sa.column("catalog_search", sa.Text),
)


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete)


# ------------------------------------------------------------------ data steps

def _org_kinds_and_paths(conn) -> None:
    rows = {r.id: r for r in conn.execute(sa.select(_orgs.c.id, _orgs.c.slug, _orgs.c.parent_id)).all()}
    if not rows:
        return
    platform = _platform_org_id()
    personal_ids: set = set()
    for (uid,) in conn.execute(sa.select(_users.c.id)).yield_per(BATCH):
        oid = _personal_org_id(uid)
        if oid in rows and rows[oid].slug == _personal_org_slug(uid):
            personal_ids.add(oid)
    for oid, uid in conn.execute(
        sa.select(_members.c.organization_id, _members.c.user_id)
        .where(_members.c.role == "org_admin", _members.c.state == "active")
    ).all():
        if oid in rows and rows[oid].slug == _personal_org_slug(uid):
            personal_ids.add(oid)

    def chain(oid) -> list:
        out, seen = [], set()
        while oid is not None:
            if oid in seen or oid not in rows:
                raise RuntimeError(f"0014: organization {oid} has a broken or cyclic parent chain")
            seen.add(oid)
            out.append(oid)
            oid = rows[oid].parent_id
        if len(out) - 1 > MAX_DEPTH:
            raise RuntimeError(f"0014: organization {out[0]} is deeper than {MAX_DEPTH} below its root")
        return list(reversed(out))

    for oid, r in rows.items():
        ids = chain(oid)
        if r.parent_id is not None:
            if ids[0] in personal_ids:
                raise RuntimeError(f"0014: organization {oid} is a department of a personal organization")
            kind = "department"
        elif oid == platform:
            kind = "platform"
        elif oid in personal_ids:
            kind = "personal"
        else:
            kind = "school"
        values = dict(kind=kind, path="/".join(i.hex for i in ids), depth=len(ids) - 1)
        if kind == "department":
            values["settings"] = {}  # settings live on the root only (design 2.1)
        conn.execute(_orgs.update().where(_orgs.c.id == oid).values(**values))


def _catalog_search(conn) -> None:
    last = None
    while True:
        stmt = sa.select(_courses.c.id, _courses.c.title, _courses.c.description).order_by(_courses.c.id).limit(BATCH)
        if last is not None:
            stmt = stmt.where(_courses.c.id > last)
        rows = conn.execute(stmt).all()
        if not rows:
            return
        for cid, title, description in rows:
            conn.execute(_courses.update().where(_courses.c.id == cid)
                         .values(catalog_search=_catalog_search_text(title, description)))
        last = rows[-1][0]


# ------------------------------------------------------------------ upgrade

def upgrade() -> None:
    conn = op.get_bind()

    # 2.1 organizations: kind, path, depth (backfilled), CHECKs, prefix index
    with op.batch_alter_table("organizations") as b:
        b.add_column(sa.Column("kind", sa.String(length=16), server_default="school", nullable=False))
        b.add_column(sa.Column("path", sa.String(length=400), nullable=True))
        b.add_column(sa.Column("depth", sa.SmallInteger(), server_default="0", nullable=False))
    _org_kinds_and_paths(conn)
    with op.batch_alter_table("organizations") as b:
        b.alter_column("path", existing_type=sa.String(length=400), nullable=False)
        b.create_check_constraint(op.f("ck_organizations_kind_valid"),
                                  "kind IN ('platform','school','personal','department')")
        b.create_check_constraint(op.f("ck_organizations_depth_valid"), "depth >= 0 AND depth <= 2")
        b.create_check_constraint(op.f("ck_organizations_department_has_parent"),
                                  "kind <> 'department' OR parent_id IS NOT NULL")
        b.create_check_constraint(op.f("ck_organizations_root_has_no_parent"),
                                  "kind = 'department' OR parent_id IS NULL")
        b.create_check_constraint(op.f("ck_organizations_personal_is_root"), "kind <> 'personal' OR depth = 0")
        b.create_check_constraint(op.f("ck_organizations_depth_matches_parent"),
                                  "(parent_id IS NULL) = (depth = 0)")
    op.create_index("ix_organizations_path", "organizations", ["path"],
                    postgresql_ops={"path": "varchar_pattern_ops"})

    # 2.2 question banks: visibility (every existing bank private), sharing state, copy provenance
    with op.batch_alter_table("question_banks") as b:
        b.add_column(sa.Column("visibility", sa.String(length=16), server_default="private", nullable=False))
        b.add_column(sa.Column("shared_at", TS, nullable=True))
        b.add_column(sa.Column("shared_by_id", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("copied_from_bank_id", UUID, nullable=True))
        b.create_foreign_key(op.f("fk_question_banks_shared_by_id_users"), "users", ["shared_by_id"], ["id"],
                             ondelete="SET NULL")
        b.create_foreign_key(op.f("fk_question_banks_copied_from_bank_id_question_banks"), "question_banks",
                             ["copied_from_bank_id"], ["id"], ondelete="SET NULL")
        b.create_check_constraint(op.f("ck_question_banks_visibility_valid"),
                                  "visibility IN ('private','organization')")
        b.create_check_constraint(op.f("ck_question_banks_quiz_bank_private"),
                                  "assessment_id IS NULL OR visibility = 'private'")
        b.create_check_constraint(op.f("ck_question_banks_shared_bank_has_course"),
                                  "visibility = 'private' OR course_id IS NOT NULL")
    op.create_index("ix_question_banks_org_visibility", "question_banks", ["organization_id", "visibility"])
    with op.batch_alter_table("bank_questions") as b:
        b.add_column(sa.Column("copied_from_question_id", UUID, nullable=True))
        b.create_foreign_key(op.f("fk_bank_questions_copied_from_question_id_bank_questions"), "bank_questions",
                             ["copied_from_question_id"], ["id"], ondelete="SET NULL")

    # 2.3 roster imports
    applied = "status IN ('applied','partial')"
    op.create_table(
        "organization_roster_imports",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("course_id", UUID, nullable=True),
        sa.Column("department_id", UUID, nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("counts", JSONType, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("report", JSONType, server_default=sa.text("'[]'"), nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("applied_at", TS, nullable=True),
        sa.CheckConstraint("kind IN ('student','teacher')", name=op.f("ck_organization_roster_imports_kind_valid")),
        sa.CheckConstraint("status IN ('dry_run','applied','partial','failed')",
                           name=op.f("ck_organization_roster_imports_status_valid")),
        sa.CheckConstraint("kind <> 'student' OR course_id IS NOT NULL",
                           name=op.f("ck_organization_roster_imports_student_needs_course")),
        sa.CheckConstraint("kind <> 'teacher' OR department_id IS NOT NULL",
                           name=op.f("ck_organization_roster_imports_teacher_needs_department")),
        sa.CheckConstraint("kind <> 'teacher' OR course_id IS NULL",
                           name=op.f("ck_organization_roster_imports_teacher_no_course")),
        sa.CheckConstraint("row_count >= 0 AND row_count <= 500",
                           name=op.f("ck_organization_roster_imports_row_count_valid")),
        _fk("organization_roster_imports", "organization_id", "organizations", "RESTRICT"),
        _fk("organization_roster_imports", "course_id", "courses", "RESTRICT"),
        _fk("organization_roster_imports", "department_id", "organizations", "RESTRICT"),
        _fk("organization_roster_imports", "created_by_id", "users", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_roster_imports")),
    )
    op.create_index("uq_roster_imports_applied", "organization_roster_imports",
                    ["organization_id", "kind", "course_id", "file_sha256"], unique=True,
                    postgresql_where=sa.text(applied), sqlite_where=sa.text(applied))
    teachers = f"kind = 'teacher' AND {applied}"
    op.create_index("uq_roster_imports_applied_teachers", "organization_roster_imports",
                    ["organization_id", "department_id", "file_sha256"], unique=True,
                    postgresql_where=sa.text(teachers), sqlite_where=sa.text(teachers))
    op.create_index("ix_organization_roster_imports_organization_id_created_at", "organization_roster_imports",
                    ["organization_id", "created_at"])

    # 2.6 invitations: role 'student' (needs a course), roster import provenance
    with op.batch_alter_table("invitations") as b:
        b.drop_constraint(op.f("ck_invitations_role_valid"), type_="check")
        b.create_check_constraint(op.f("ck_invitations_role_valid"),
                                  "role IN ('org_admin','teacher','assistant','student')")
        b.create_check_constraint(op.f("ck_invitations_student_needs_course"),
                                  "role <> 'student' OR course_id IS NOT NULL")
        b.add_column(sa.Column("roster_import_id", UUID, nullable=True))
        b.create_foreign_key(op.f("fk_invitations_roster_import_id_organization_roster_imports"),
                             "organization_roster_imports", ["roster_import_id"], ["id"], ondelete="SET NULL")

    # 2.6 courses.catalog_search (backfilled in batches)
    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("catalog_search", sa.Text(), server_default="", nullable=False))
    _catalog_search(conn)

    # 2.4 enrollment forms and fields
    op.create_table(
        "enrollment_forms",
        sa.Column("id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", JSONType, nullable=True),
        sa.Column("intro", JSONType, nullable=True),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("activated_at", TS, nullable=True),
        sa.Column("retired_at", TS, nullable=True),
        sa.Column("answered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint("status IN ('draft','active','retired')", name=op.f("ck_enrollment_forms_status_valid")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_enrollment_forms_version_valid")),
        _fk("enrollment_forms", "course_id", "courses", "RESTRICT"),
        _fk("enrollment_forms", "created_by_id", "users", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollment_forms")),
        sa.UniqueConstraint("course_id", "version", name=op.f("uq_enrollment_forms_course_id_version")),
    )
    op.create_index("uq_enrollment_forms_active", "enrollment_forms", ["course_id"], unique=True,
                    postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))
    op.create_index("uq_enrollment_forms_draft", "enrollment_forms", ["course_id"], unique=True,
                    postgresql_where=sa.text("status = 'draft'"), sqlite_where=sa.text("status = 'draft'"))
    op.create_table(
        "enrollment_form_fields",
        sa.Column("id", UUID, nullable=False),
        sa.Column("form_id", UUID, nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("label", JSONType, nullable=False),
        sa.Column("help", JSONType, nullable=True),
        sa.Column("options", JSONType, nullable=True),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("pii_category", sa.String(length=16), nullable=False),
        sa.Column("max_len", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "type IN ('short_text','long_text','single_choice','multi_choice','number','date','email','phone')",
            name=op.f("ck_enrollment_form_fields_type_valid")),
        sa.CheckConstraint("pii_category IN ('none','contact','personal')",
                           name=op.f("ck_enrollment_form_fields_pii_category_valid")),
        sa.CheckConstraint("type NOT IN ('single_choice','multi_choice') OR options IS NOT NULL",
                           name=op.f("ck_enrollment_form_fields_choice_has_options")),
        sa.CheckConstraint("max_len IS NULL OR (max_len >= 1 AND max_len <= 2000)",
                           name=op.f("ck_enrollment_form_fields_max_len_valid")),
        _fk("enrollment_form_fields", "form_id", "enrollment_forms", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollment_form_fields")),
        sa.UniqueConstraint("form_id", "key", name=op.f("uq_enrollment_form_fields_form_id_key")),
    )
    op.create_index("ix_enrollment_form_fields_form_id_position", "enrollment_form_fields", ["form_id", "position"])

    # 2.5 applications
    op.create_table(
        "enrollment_applications",
        sa.Column("id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("form_id", UUID, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("answers", JSONType, nullable=True),
        sa.Column("submitted_at", TS, nullable=False),
        sa.Column("decided_by_id", sa.String(length=64), nullable=True),
        sa.Column("decided_at", TS, nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
        sa.Column("enrollment_id", UUID, nullable=True),
        sa.Column("purge_after", TS, nullable=True),
        sa.Column("purged_at", TS, nullable=True),
        sa.CheckConstraint("status IN ('pending','approved','rejected','withdrawn')",
                           name=op.f("ck_enrollment_applications_status_valid")),
        _fk("enrollment_applications", "course_id", "courses", "RESTRICT"),
        _fk("enrollment_applications", "user_id", "users", "RESTRICT"),
        _fk("enrollment_applications", "form_id", "enrollment_forms", "RESTRICT"),
        _fk("enrollment_applications", "decided_by_id", "users", "SET NULL"),
        _fk("enrollment_applications", "enrollment_id", "enrollments", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollment_applications")),
    )
    op.create_index("uq_enrollment_applications_pending", "enrollment_applications", ["course_id", "user_id"],
                    unique=True, postgresql_where=sa.text("status = 'pending'"),
                    sqlite_where=sa.text("status = 'pending'"))
    op.create_index("ix_enrollment_applications_course_id_status_submitted_at", "enrollment_applications",
                    ["course_id", "status", "submitted_at"])
    op.create_index("ix_enrollment_applications_user_id_status", "enrollment_applications", ["user_id", "status"])
    op.create_index("ix_enrollment_applications_purge_after", "enrollment_applications", ["purge_after"],
                    postgresql_where=sa.text("purged_at IS NULL"), sqlite_where=sa.text("purged_at IS NULL"))


# ------------------------------------------------------------------ downgrade

def downgrade() -> None:
    op.drop_index("ix_enrollment_applications_purge_after", table_name="enrollment_applications")
    op.drop_index("ix_enrollment_applications_user_id_status", table_name="enrollment_applications")
    op.drop_index("ix_enrollment_applications_course_id_status_submitted_at", table_name="enrollment_applications")
    op.drop_index("uq_enrollment_applications_pending", table_name="enrollment_applications")
    op.drop_table("enrollment_applications")
    op.drop_index("ix_enrollment_form_fields_form_id_position", table_name="enrollment_form_fields")
    op.drop_table("enrollment_form_fields")
    op.drop_index("uq_enrollment_forms_draft", table_name="enrollment_forms")
    op.drop_index("uq_enrollment_forms_active", table_name="enrollment_forms")
    op.drop_table("enrollment_forms")

    with op.batch_alter_table("courses") as b:
        b.drop_column("catalog_search")

    # student invitations cannot exist under the restored three-value CHECK (lossy by design 2.7)
    op.execute("DELETE FROM invitations WHERE role = 'student'")
    with op.batch_alter_table("invitations") as b:
        b.drop_constraint(op.f("fk_invitations_roster_import_id_organization_roster_imports"), type_="foreignkey")
        b.drop_column("roster_import_id")
        b.drop_constraint(op.f("ck_invitations_student_needs_course"), type_="check")
        b.drop_constraint(op.f("ck_invitations_role_valid"), type_="check")
        b.create_check_constraint(op.f("ck_invitations_role_valid"), "role IN ('org_admin','teacher','assistant')")

    op.drop_index("ix_organization_roster_imports_organization_id_created_at",
                  table_name="organization_roster_imports")
    op.drop_index("uq_roster_imports_applied_teachers", table_name="organization_roster_imports")
    op.drop_index("uq_roster_imports_applied", table_name="organization_roster_imports")
    op.drop_table("organization_roster_imports")

    with op.batch_alter_table("bank_questions") as b:
        b.drop_constraint(op.f("fk_bank_questions_copied_from_question_id_bank_questions"), type_="foreignkey")
        b.drop_column("copied_from_question_id")
    op.drop_index("ix_question_banks_org_visibility", table_name="question_banks")
    with op.batch_alter_table("question_banks") as b:
        b.drop_constraint(op.f("ck_question_banks_shared_bank_has_course"), type_="check")
        b.drop_constraint(op.f("ck_question_banks_quiz_bank_private"), type_="check")
        b.drop_constraint(op.f("ck_question_banks_visibility_valid"), type_="check")
        b.drop_constraint(op.f("fk_question_banks_copied_from_bank_id_question_banks"), type_="foreignkey")
        b.drop_constraint(op.f("fk_question_banks_shared_by_id_users"), type_="foreignkey")
        b.drop_column("copied_from_bank_id")
        b.drop_column("shared_by_id")
        b.drop_column("shared_at")
        b.drop_column("visibility")

    op.drop_index("ix_organizations_path", table_name="organizations")
    with op.batch_alter_table("organizations") as b:
        for name in ("depth_matches_parent", "personal_is_root", "root_has_no_parent", "department_has_parent",
                     "depth_valid", "kind_valid"):
            b.drop_constraint(op.f(f"ck_organizations_{name}"), type_="check")
        b.drop_column("depth")
        b.drop_column("path")
        b.drop_column("kind")
