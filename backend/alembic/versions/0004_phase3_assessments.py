"""phase 3: assessments, versions, attempts, attempt sections and items

Revision ID: 0004_phase3_assessments
Revises: 0003_phase2_content
Create Date: 2026-10-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_phase3_assessments"
down_revision: Union[str, None] = "0003_phase2_content"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
_FALSE = sa.text("false")
_TIME = "time_limit_s IS NULL OR (time_limit_s >= 60 AND time_limit_s <= 86400)"


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def _tstz(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("title", JSONType, nullable=False),
        sa.Column("description", JSONType, nullable=True),
        sa.Column("preset", sa.String(length=16), server_default="none", nullable=False),
        sa.Column("languages", JSONType, nullable=False),
        sa.Column("status", sa.String(length=12), server_default="draft", nullable=False),
        sa.Column("published_version_id", UUID, nullable=True),
        sa.Column("last_version_no", sa.Integer(), server_default="0", nullable=False),
        sa.Column("draft_rev", sa.Integer(), server_default="1", nullable=False),
        sa.Column("published_draft_rev", sa.Integer(), nullable=True),
        sa.Column("time_limit_s", sa.Integer(), nullable=True),
        sa.Column("allowed_attempts", sa.Integer(), server_default="1", nullable=False),
        sa.Column("score_policy", sa.String(length=8), server_default="highest", nullable=False),
        sa.Column("shuffle_items", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("shuffle_choices", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("navigation", sa.String(length=24), server_default="free", nullable=False),
        sa.Column("results_policy", sa.String(length=16), server_default="after_submit", nullable=False),
        sa.Column("show_correct_answers", sa.Boolean(), server_default=_FALSE, nullable=False),
        _tstz("available_from"), _tstz("available_until"),
        sa.Column("position", sa.Integer(), nullable=False),
        _tstz("published_at"),
        _tstz("deleted_at"),
        sa.Column("deleted_by_id", sa.String(length=64), nullable=True),
        _fk("assessments", "course_id", "courses", "RESTRICT"),
        _fk("assessments", "created_by_id", "users", "SET NULL"),
        _fk("assessments", "deleted_by_id", "users", "SET NULL"),
        sa.CheckConstraint("preset IN ('none','ort_main','ort_subject')", name=op.f("ck_assessments_preset_valid")),
        sa.CheckConstraint("status IN ('draft','published')", name=op.f("ck_assessments_status_valid")),
        sa.CheckConstraint(_TIME, name=op.f("ck_assessments_time_limit_valid")),
        sa.CheckConstraint(
            "allowed_attempts = -1 OR (allowed_attempts >= 1 AND allowed_attempts <= 100)",
            name=op.f("ck_assessments_allowed_attempts_valid"),
        ),
        sa.CheckConstraint("score_policy IN ('highest','latest','first','average')",
                           name=op.f("ck_assessments_score_policy_valid")),
        sa.CheckConstraint("navigation IN ('free','section_forward_only')",
                           name=op.f("ck_assessments_navigation_valid")),
        sa.CheckConstraint("results_policy IN ('never','after_submit','after_close')",
                           name=op.f("ck_assessments_results_policy_valid")),
        sa.CheckConstraint(
            "available_from IS NULL OR available_until IS NULL OR available_until > available_from",
            name=op.f("ck_assessments_window_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
    )
    op.create_index("ix_assessments_course_id_deleted_at_position_id", "assessments",
                    ["course_id", "deleted_at", "position", "id"])
    op.create_index("ix_assessments_course_id_status", "assessments", ["course_id", "status"])

    op.create_table(
        "assessment_sections",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("assessment_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=True),
        sa.Column("title", JSONType, nullable=True),
        sa.Column("instructions", JSONType, nullable=True),
        sa.Column("time_limit_s", sa.Integer(), nullable=True),
        sa.Column("rules", JSONType, nullable=False),
        _fk("assessment_sections", "assessment_id", "assessments", "RESTRICT"),
        sa.CheckConstraint(_TIME, name=op.f("ck_assessment_sections_time_limit_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_sections")),
    )
    op.create_index("ix_assessment_sections_assessment_id_position", "assessment_sections",
                    ["assessment_id", "position"])

    op.create_table(
        "assessment_items",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("assessment_id", UUID, nullable=False),
        sa.Column("section_id", UUID, nullable=False),
        sa.Column("parent_item_id", UUID, nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("question_id", UUID, nullable=True),
        sa.Column("passage_id", UUID, nullable=True),
        sa.Column("points", sa.Numeric(8, 2), nullable=True),
        sa.Column("pick_bank_id", UUID, nullable=True),
        sa.Column("pick_count", sa.Integer(), nullable=True),
        sa.Column("pick_filter", JSONType, nullable=True),
        _fk("assessment_items", "assessment_id", "assessments", "RESTRICT"),
        _fk("assessment_items", "section_id", "assessment_sections", "RESTRICT"),
        _fk("assessment_items", "parent_item_id", "assessment_items", "RESTRICT"),
        _fk("assessment_items", "question_id", "bank_questions", "RESTRICT"),
        _fk("assessment_items", "passage_id", "passages", "RESTRICT"),
        _fk("assessment_items", "pick_bank_id", "question_banks", "RESTRICT"),
        sa.CheckConstraint("kind IN ('question','passage','pick')", name=op.f("ck_assessment_items_kind_valid")),
        sa.CheckConstraint("kind <> 'question' OR question_id IS NOT NULL",
                           name=op.f("ck_assessment_items_question_kind_valid")),
        sa.CheckConstraint("kind <> 'passage' OR (passage_id IS NOT NULL AND parent_item_id IS NULL)",
                           name=op.f("ck_assessment_items_passage_kind_valid")),
        sa.CheckConstraint(
            "kind <> 'pick' OR (pick_bank_id IS NOT NULL AND pick_count IS NOT NULL AND parent_item_id IS NULL)",
            name=op.f("ck_assessment_items_pick_kind_valid"),
        ),
        sa.CheckConstraint("points IS NULL OR (points >= 0 AND points <= 1000)",
                           name=op.f("ck_assessment_items_points_valid")),
        sa.CheckConstraint("pick_count IS NULL OR (pick_count >= 1 AND pick_count <= 200)",
                           name=op.f("ck_assessment_items_pick_count_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_items")),
    )
    op.create_index("ix_assessment_items_assessment_id_section_id_position", "assessment_items",
                    ["assessment_id", "section_id", "position"])
    op.create_index("ix_assessment_items_parent_item_id", "assessment_items", ["parent_item_id"])
    _q = sa.text("question_id IS NOT NULL")
    op.create_index("uq_assessment_items_question", "assessment_items", ["assessment_id", "question_id"],
                    unique=True, postgresql_where=_q, sqlite_where=_q)

    op.create_table(
        "assessment_versions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("assessment_id", UUID, nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=True),
        sa.Column("snapshot", JSONType, nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("draft_rev", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("points_possible", sa.Numeric(10, 2), nullable=False),
        _ts("created_at"),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        _fk("assessment_versions", "assessment_id", "assessments", "RESTRICT"),
        _fk("assessment_versions", "created_by_id", "users", "SET NULL"),
        sa.CheckConstraint("kind IN ('published','preview')", name=op.f("ck_assessment_versions_kind_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_versions")),
        sa.UniqueConstraint("assessment_id", "version_no", name="uq_assessment_versions_assessment_version"),
    )
    op.create_index("ix_assessment_versions_assessment_id_kind_created_at", "assessment_versions",
                    ["assessment_id", "kind", "created_at"])

    with op.batch_alter_table("assessments") as b:
        b.create_foreign_key("fk_assessments_published_version_id", "assessment_versions",
                             ["published_version_id"], ["id"])

    op.create_table(
        "attempts",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("assessment_id", UUID, nullable=False),
        sa.Column("assessment_version_id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("is_preview", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("status", sa.String(length=16), server_default="in_progress", nullable=False),
        _ts("started_at"),
        _tstz("deadline_at"),
        sa.Column("extra_time_s", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_section_pos", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        _tstz("submitted_at"),
        sa.Column("submit_reason", sa.String(length=8), nullable=True),
        sa.Column("raw_score", sa.Numeric(10, 2), nullable=True),
        sa.Column("points_possible", sa.Numeric(10, 2), nullable=False),
        sa.Column("result", JSONType, nullable=True),
        _tstz("graded_at"),
        _fk("attempts", "assessment_id", "assessments", "RESTRICT"),
        _fk("attempts", "assessment_version_id", "assessment_versions", "RESTRICT"),
        _fk("attempts", "course_id", "courses", "RESTRICT"),
        _fk("attempts", "enrollment_id", "enrollments", "RESTRICT"),
        _fk("attempts", "user_id", "users", "RESTRICT"),
        sa.CheckConstraint("language IN ('en','ru','ky')", name=op.f("ck_attempts_language_valid")),
        sa.CheckConstraint("status IN ('in_progress','submitted','needs_review','graded','void')",
                           name=op.f("ck_attempts_status_valid")),
        sa.CheckConstraint("submit_reason IS NULL OR submit_reason IN ('manual','timeout','sweep','closed')",
                           name=op.f("ck_attempts_submit_reason_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempts")),
        sa.UniqueConstraint("assessment_id", "user_id", "attempt_no", name="uq_attempts_number"),
    )
    is_pg = op.get_bind().dialect.name == "postgresql"
    _open = sa.text("status = 'in_progress' AND NOT is_preview" if is_pg
                    else "status = 'in_progress' AND is_preview = 0")
    _prev = sa.text("status = 'in_progress' AND is_preview" if is_pg
                    else "status = 'in_progress' AND is_preview = 1")
    _inprog = sa.text("status = 'in_progress'")
    op.create_index("uq_attempts_open", "attempts", ["assessment_id", "user_id"], unique=True,
                    postgresql_where=_open, sqlite_where=_open)
    op.create_index("uq_attempts_open_preview", "attempts", ["assessment_id", "user_id"], unique=True,
                    postgresql_where=_prev, sqlite_where=_prev)
    op.create_index("ix_attempts_assessment_id_is_preview_status_submitted_at", "attempts",
                    ["assessment_id", "is_preview", "status", "submitted_at"])
    op.create_index("ix_attempts_user_id_created_at", "attempts", ["user_id", "created_at"])
    op.create_index("ix_attempts_open_deadline", "attempts", ["deadline_at"],
                    postgresql_where=_inprog, sqlite_where=_inprog)

    op.create_table(
        "attempt_sections",
        sa.Column("attempt_id", UUID, nullable=False),
        sa.Column("section_pos", sa.SmallInteger(), autoincrement=False, nullable=False),
        _tstz("started_at"), _tstz("deadline_at"), _tstz("closed_at"),
        sa.Column("close_reason", sa.String(length=8), nullable=True),
        _fk("attempt_sections", "attempt_id", "attempts", "RESTRICT"),
        sa.CheckConstraint("close_reason IS NULL OR close_reason IN ('manual','timeout','submit')",
                           name=op.f("ck_attempt_sections_close_reason_valid")),
        sa.PrimaryKeyConstraint("attempt_id", "section_pos", name=op.f("pk_attempt_sections")),
    )

    op.create_table(
        "attempt_items",
        sa.Column("attempt_id", UUID, nullable=False),
        sa.Column("position", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("section_pos", sa.SmallInteger(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("question_version_id", UUID, nullable=False),
        sa.Column("choice_order", JSONType, nullable=True),
        sa.Column("response", JSONType, nullable=True),
        sa.Column("flagged", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("client_ts", sa.BigInteger(), nullable=True),
        _tstz("answered_at"),
        sa.Column("correctness", sa.String(length=10), nullable=True),
        sa.Column("score", sa.Numeric(8, 2), nullable=True),
        sa.Column("manual_score", sa.Numeric(8, 2), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("graded_by_id", sa.String(length=64), nullable=True),
        _tstz("graded_at"),
        _fk("attempt_items", "attempt_id", "attempts", "RESTRICT"),
        _fk("attempt_items", "question_version_id", "question_versions", "RESTRICT"),
        _fk("attempt_items", "graded_by_id", "users", "SET NULL"),
        sa.CheckConstraint(
            "correctness IS NULL OR correctness IN ('correct','incorrect','partial','unanswered','pending')",
            name=op.f("ck_attempt_items_correctness_valid"),
        ),
        sa.PrimaryKeyConstraint("attempt_id", "position", name=op.f("pk_attempt_items")),
    )
    if is_pg:
        # Keep autosave UPDATEs HOT (design 2.7).
        op.execute("ALTER TABLE attempt_items SET (fillfactor = 85)")


def downgrade() -> None:
    for table in ("attempt_items", "attempt_sections", "attempts"):
        op.drop_table(table)
    with op.batch_alter_table("assessments") as b:
        b.drop_constraint("fk_assessments_published_version_id", type_="foreignkey")
    for table in ("assessment_versions", "assessment_items", "assessment_sections", "assessments"):
        op.drop_table(table)
