"""phase 10: practice flag, final-attempt indexes, course goals, quiz statistics tables

Revision ID: 0016_phase10_practice_analytics
Revises: 0015_test_student
Create Date: 2026-11-01

Additive. `assessments.is_practice` / `attempts.is_practice` (false for every existing row), three partial indexes on
final non-preview attempts, `ix_module_progress_module_id_state`, `course_goals`, `assessment_version_stats`,
`assessment_item_stats`. See docs/phases/PHASE_10_DESIGN.md section 1.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_phase10_practice_analytics"
down_revision: Union[str, None] = "0015_test_student"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FINAL_PG = sa.text("status IN ('graded','needs_review') AND NOT is_preview")
_FINAL_SQLITE = sa.text("status IN ('graded','needs_review') AND is_preview = 0")
_JSON = sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql")


def _final_index(name: str, cols: list[str]) -> None:
    op.create_index(name, "attempts", cols, postgresql_where=_FINAL_PG, sqlite_where=_FINAL_SQLITE)


_OLD_TYPES = "('single_choice','multiple_answers','true_false','comparison','numeric','short_text','essay')"
_NEW_TYPES = "('single_choice','multiple_answers','true_false','comparison','numeric','short_text','essay','matching','fill_blank','ordering')"


def _swap_type_checks(types: str) -> None:
    """S1: the question type CHECKs list the three structured types (the constraint names are unchanged)."""
    for table in ("bank_questions", "question_versions"):
        with op.batch_alter_table(table) as b:
            b.drop_constraint(op.f(f"ck_{table}_type_valid"), type_="check")
            b.create_check_constraint(op.f(f"ck_{table}_type_valid"), f"type IN {types}")


def upgrade() -> None:
    _swap_type_checks(_NEW_TYPES)
    with op.batch_alter_table("assessments") as b:
        b.add_column(sa.Column("is_practice", sa.Boolean(), server_default=sa.false(), nullable=False))
        b.create_check_constraint("ck_assessments_practice_preset_none", "NOT is_practice OR preset = 'none'")
    op.add_column("attempts", sa.Column("is_practice", sa.Boolean(), server_default=sa.false(), nullable=False))
    _final_index("ix_attempts_version_final", ["assessment_version_id", "user_id", "attempt_no"])
    _final_index("ix_attempts_user_course_final", ["user_id", "course_id", "submitted_at"])
    _final_index("ix_attempts_course_final", ["course_id", "assessment_id"])
    op.create_index("ix_module_progress_module_id_state", "module_progress", ["module_id", "state"])

    op.create_table(
        "course_goals",
        sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("enrollments.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("target_percent", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target_percent >= 1 AND target_percent <= 100", name="ck_course_goals_target_percent_valid"),
    )
    op.create_table(
        "assessment_version_stats",
        sa.Column("assessment_version_id", sa.Uuid(),
                  sa.ForeignKey("assessment_versions.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("assessment_id", sa.Uuid(), sa.ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refreshing_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column("attempts_counted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mean_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("median_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("stddev_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("min_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("max_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("distribution", _JSON, nullable=True),
    )
    op.create_index("ix_assessment_version_stats_assessment_id", "assessment_version_stats", ["assessment_id"])
    op.create_table(
        "assessment_item_stats",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assessment_version_id", sa.Uuid(),
                  sa.ForeignKey("assessment_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("question_version_id", sa.Uuid(),
                  sa.ForeignKey("question_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("points", sa.Numeric(8, 2), nullable=False),
        sa.Column("accuracy", sa.Numeric(6, 2), nullable=False),
        sa.Column("point_biserial", sa.Numeric(5, 3), nullable=True),
        sa.Column("avg_seconds", sa.Integer(), nullable=True),
        sa.Column("correct", sa.Integer(), nullable=False),
        sa.Column("partial", sa.Integer(), nullable=False),
        sa.Column("incorrect", sa.Integer(), nullable=False),
        sa.Column("unanswered", sa.Integer(), nullable=False),
        sa.Column("distractors", _JSON, nullable=True),
        sa.UniqueConstraint("assessment_version_id", "slot", "question_version_id", name="uq_assessment_item_stats_slot"),
    )
    op.create_index("ix_assessment_item_stats_hardest", "assessment_item_stats",
                    ["assessment_version_id", "accuracy", "id"])


def downgrade() -> None:
    _swap_type_checks(_OLD_TYPES)
    op.drop_table("assessment_item_stats")
    op.drop_table("assessment_version_stats")
    op.drop_table("course_goals")
    op.drop_index("ix_module_progress_module_id_state", table_name="module_progress")
    for n in ("ix_attempts_course_final", "ix_attempts_user_course_final", "ix_attempts_version_final"):
        op.drop_index(n, table_name="attempts")
    op.drop_column("attempts", "is_practice")
    with op.batch_alter_table("assessments") as b:
        b.drop_constraint("ck_assessments_practice_preset_none", type_="check")
        b.drop_column("is_practice")
