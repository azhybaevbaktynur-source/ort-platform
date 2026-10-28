"""phase 7c (S1): quiz banks (question_banks.assessment_id) and per-card question drafts

Revision ID: 0011_phase7c_quiz_editor
Revises: 0010_phase7b_exam_templates
Create Date: 2026-10-28

PHASE_7C_DESIGN section 2. Schema only, no data steps: `question_banks.assessment_id` is nullable (NULL = shared bank,
which every existing row stays, the ORT importer banks included) and `question_drafts` starts empty. A quiz bank has a
course and never an importer `source_id` (two CHECKs); one live quiz bank per assessment (partial unique index).

Downgrade is lossless while no quiz bank exists; it is refused with a clear error otherwise (quiz-bank questions
would silently become shared-bank questions). Drafts are dropped with their table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011_phase7c_quiz_editor"
down_revision: Union[str, None] = "0010_phase7b_exam_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
BANK_ASSESSMENT_FK = "fk_question_banks_assessment_id_assessments"
LIVE_WHERE = "assessment_id IS NOT NULL AND deleted_at IS NULL"


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete)


def upgrade() -> None:
    with op.batch_alter_table("question_banks") as b:
        b.add_column(sa.Column("assessment_id", UUID, nullable=True))
        b.create_foreign_key(op.f(BANK_ASSESSMENT_FK), "assessments", ["assessment_id"], ["id"], ondelete="RESTRICT")
        b.create_check_constraint(op.f("ck_question_banks_quiz_bank_has_course"),
                                  "assessment_id IS NULL OR course_id IS NOT NULL")
        b.create_check_constraint(op.f("ck_question_banks_quiz_bank_no_source"),
                                  "assessment_id IS NULL OR source_id IS NULL")
    op.create_index("ix_question_banks_assessment_id", "question_banks", ["assessment_id"])
    op.create_index("uq_question_banks_assessment_live", "question_banks", ["assessment_id"], unique=True,
                    postgresql_where=sa.text(LIVE_WHERE), sqlite_where=sa.text(LIVE_WHERE))

    op.create_table(
        "question_drafts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_id", UUID, nullable=False),
        sa.Column("section_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=True),
        sa.Column("after_item_id", UUID, nullable=True),
        sa.Column("base_version_id", UUID, nullable=True),
        sa.Column("payload", JSONType, nullable=False),
        sa.Column("draft_rev", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        sa.Column("updated_by_id", sa.String(length=64), nullable=True),
        _fk("question_drafts", "assessment_id", "assessments", "RESTRICT"),
        _fk("question_drafts", "section_id", "assessment_sections", "RESTRICT"),
        _fk("question_drafts", "item_id", "assessment_items", "RESTRICT"),
        _fk("question_drafts", "after_item_id", "assessment_items", "SET NULL"),
        _fk("question_drafts", "base_version_id", "question_versions", "RESTRICT"),
        _fk("question_drafts", "created_by_id", "users", "SET NULL"),
        _fk("question_drafts", "updated_by_id", "users", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_drafts")),
    )
    op.create_index("uq_question_drafts_item", "question_drafts", ["item_id"], unique=True,
                    postgresql_where=sa.text("item_id IS NOT NULL"), sqlite_where=sa.text("item_id IS NOT NULL"))
    op.create_index("ix_question_drafts_assessment_section", "question_drafts", ["assessment_id", "section_id"])


def downgrade() -> None:
    conn = op.get_bind()
    quiz_banks = conn.execute(sa.text(
        "SELECT count(*) FROM question_banks WHERE assessment_id IS NOT NULL")).scalar()
    if quiz_banks:
        raise RuntimeError(f"0011 downgrade refused: {quiz_banks} quiz bank(s) exist "
                           "(question_banks.assessment_id IS NOT NULL); this direction would turn their questions "
                           "into shared-bank questions")
    op.drop_index("ix_question_drafts_assessment_section", table_name="question_drafts")
    op.drop_index("uq_question_drafts_item", table_name="question_drafts")
    op.drop_table("question_drafts")
    op.drop_index("uq_question_banks_assessment_live", table_name="question_banks")
    op.drop_index("ix_question_banks_assessment_id", table_name="question_banks")
    with op.batch_alter_table("question_banks") as b:
        b.drop_constraint(op.f("ck_question_banks_quiz_bank_no_source"), type_="check")
        b.drop_constraint(op.f("ck_question_banks_quiz_bank_has_course"), type_="check")
        b.drop_constraint(op.f(BANK_ASSESSMENT_FK), type_="foreignkey")
        b.drop_column("assessment_id")
