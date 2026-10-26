"""phase 7b (S1): exam templates and immutable template versions; assessments gain the template link and display fields

Revision ID: 0010_phase7b_exam_templates
Revises: 0009_phase7a_assignments
Create Date: 2026-10-26

PHASE_7B_DESIGN section 2. Schema only, no data steps: every new column is nullable or has a server default, so
existing assessments (all ORT and general exams) keep their behaviour (`exam_template_version_id` NULL,
`display_mode` 'one_per_page', `passage_display`/`result_view` NULL = the course template's values,
`structure_locked` false). `exam_templates.current_version_id` -> `exam_template_versions` is circular and added after
both tables exist (named constraint). `admin_audit_log.target_type` gains 'exam_template' and 'assessment' (the
template audit actions and `assessment.structure_unlock`).

Downgrade is lossless while no assessment was created from a template; it is refused with a clear error otherwise
(the structure link would be lost). Audit rows of the two new target types are removed (as 0008 does).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_phase7b_exam_templates"
down_revision: Union[str, None] = "0009_phase7a_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
_FALSE = sa.text("false")
CURRENT_VERSION_FK = "fk_exam_templates_current_version_id_exam_template_versions"
VERSION_SCHEME_FK = "fk_exam_template_versions_grading_scheme_version_id"  # <= 63 chars (PG)
ASSESSMENT_VERSION_FK = "fk_assessments_exam_template_version_id"
OLD_TARGETS = "target_type IN ('user','course','teacher_request','enrollment','organization','invitation')"
NEW_TARGETS = ("target_type IN ('user','course','teacher_request','enrollment','organization','invitation',"
               "'exam_template','assessment')")


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete)


def _ck(table: str, name: str, sql: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=op.f(f"ck_{table}_{name}"))


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.String(length=64), nullable=True)


def upgrade() -> None:
    op.create_table(
        "exam_templates",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"), _ts("deleted_at", True),
        _user("deleted_by_id"),
        sa.Column("owner_scope", sa.String(length=16), nullable=False),
        sa.Column("organization_id", UUID, nullable=True),
        _user("owner_user_id"),
        sa.Column("key", sa.String(length=64), nullable=True),
        sa.Column("title", JSONType, nullable=False),
        sa.Column("description", JSONType, nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("locked", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("current_version_id", UUID, nullable=True),
        sa.Column("draft_spec", JSONType, nullable=True),
        sa.Column("draft_rev", sa.Integer(), server_default="1", nullable=False),
        _user("created_by_id"),
        _fk("exam_templates", "organization_id", "organizations", "RESTRICT"),
        _fk("exam_templates", "owner_user_id", "users", "RESTRICT"),
        _fk("exam_templates", "created_by_id", "users", "SET NULL"),
        _fk("exam_templates", "deleted_by_id", "users", "SET NULL"),
        _ck("exam_templates", "owner_scope_valid", "owner_scope IN ('platform','organization','teacher')"),
        _ck("exam_templates", "org_matches_scope", "(owner_scope = 'platform') = (organization_id IS NULL)"),
        _ck("exam_templates", "owner_matches_scope", "(owner_scope = 'teacher') = (owner_user_id IS NOT NULL)"),
        _ck("exam_templates", "status_valid", "status IN ('draft','published','archived')"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_templates")),
        sa.UniqueConstraint("key", name="uq_exam_templates_key"),
    )
    op.create_index("ix_exam_templates_scope_org_status", "exam_templates",
                    ["owner_scope", "organization_id", "status"])
    op.create_index("ix_exam_templates_owner_user_id", "exam_templates", ["owner_user_id"])

    op.create_table(
        "exam_template_versions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("template_id", UUID, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("spec", JSONType, nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("grading_scheme_version_id", UUID, nullable=True),
        _ts("published_at"),
        _user("published_by_id"),
        _fk("exam_template_versions", "template_id", "exam_templates", "RESTRICT"),
        sa.ForeignKeyConstraint(["grading_scheme_version_id"], ["grading_scheme_versions.id"],
                                name=VERSION_SCHEME_FK, ondelete="RESTRICT"),
        _fk("exam_template_versions", "published_by_id", "users", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_template_versions")),
        sa.UniqueConstraint("template_id", "version_no", name="uq_exam_template_versions_template_version"),
    )
    op.create_index("ix_exam_template_versions_template_id_version_no", "exam_template_versions",
                    ["template_id", "version_no"])

    # the circular FK (use_alter in the model), added once both tables exist
    with op.batch_alter_table("exam_templates") as b:
        b.create_foreign_key(CURRENT_VERSION_FK, "exam_template_versions", ["current_version_id"], ["id"],
                             ondelete="SET NULL")

    with op.batch_alter_table("assessments") as b:
        b.add_column(sa.Column("exam_template_version_id", UUID, nullable=True))
        b.add_column(sa.Column("display_mode", sa.String(length=16), server_default="one_per_page", nullable=False))
        b.add_column(sa.Column("passage_display", sa.String(length=16), nullable=True))
        b.add_column(sa.Column("result_view", sa.String(length=32), nullable=True))
        b.add_column(sa.Column("structure_locked", sa.Boolean(), server_default=_FALSE, nullable=False))
        b.create_foreign_key(ASSESSMENT_VERSION_FK, "exam_template_versions", ["exam_template_version_id"], ["id"],
                             ondelete="RESTRICT")
        b.create_check_constraint(op.f("ck_assessments_display_mode_valid"),
                                  "display_mode IN ('one_per_page','scrolling')")
        b.create_check_constraint(op.f("ck_assessments_passage_display_valid"),
                                  "passage_display IS NULL OR passage_display IN ('plain','numbered')")
        b.create_check_constraint(op.f("ck_assessments_preset_template_exclusive"),
                                  "preset = 'none' OR exam_template_version_id IS NULL")
        b.create_index("ix_assessments_exam_template_version_id", ["exam_template_version_id"])

    with op.batch_alter_table("admin_audit_log") as b:
        b.drop_constraint(op.f("ck_admin_audit_log_target_type_valid"), type_="check")
        b.create_check_constraint(op.f("ck_admin_audit_log_target_type_valid"), NEW_TARGETS)


def downgrade() -> None:
    conn = op.get_bind()
    linked = conn.execute(sa.text(
        "SELECT count(*) FROM assessments WHERE exam_template_version_id IS NOT NULL")).scalar()
    if linked:
        raise RuntimeError(f"0010 downgrade refused: {linked} assessment(s) were created from an exam template "
                           "(assessments.exam_template_version_id IS NOT NULL); this direction would lose the link")
    op.execute("DELETE FROM admin_audit_log WHERE target_type IN ('exam_template','assessment')")
    with op.batch_alter_table("admin_audit_log") as b:
        b.drop_constraint(op.f("ck_admin_audit_log_target_type_valid"), type_="check")
        b.create_check_constraint(op.f("ck_admin_audit_log_target_type_valid"), OLD_TARGETS)
    with op.batch_alter_table("assessments") as b:
        b.drop_index("ix_assessments_exam_template_version_id")
        b.drop_constraint(op.f("ck_assessments_preset_template_exclusive"), type_="check")
        b.drop_constraint(op.f("ck_assessments_passage_display_valid"), type_="check")
        b.drop_constraint(op.f("ck_assessments_display_mode_valid"), type_="check")
        b.drop_constraint(ASSESSMENT_VERSION_FK, type_="foreignkey")
        for col in ("structure_locked", "result_view", "passage_display", "display_mode",
                    "exam_template_version_id"):
            b.drop_column(col)
    with op.batch_alter_table("exam_templates") as b:
        b.drop_constraint(CURRENT_VERSION_FK, type_="foreignkey")
    op.drop_index("ix_exam_template_versions_template_id_version_no", table_name="exam_template_versions")
    op.drop_table("exam_template_versions")
    op.drop_index("ix_exam_templates_owner_user_id", table_name="exam_templates")
    op.drop_index("ix_exam_templates_scope_org_status", table_name="exam_templates")
    op.drop_table("exam_templates")
