"""phase 8b (S1): exam template sandbox course (courses.sandbox_for_template_id)

Revision ID: 0013_phase8b_template_sandbox
Revises: 0012_phase8a_course_structure
Create Date: 2026-10-28

PHASE_8B_DESIGN section 2. Schema only, no data step: the new column is NULL for every existing course (the ORT
courses included), so nothing changes for them. One sandbox course per exam template (UNIQUE; NULLs are not
compared on PostgreSQL or SQLite). No FK cycle: exam_templates never references courses.

Downgrade drops the constraint and the column; lossless (a sandbox course becomes an ordinary draft course, which
the design accepts on a rollback only).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_phase8b_template_sandbox"
down_revision: Union[str, None] = "0012_phase8a_course_structure"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SANDBOX_FK = "fk_courses_sandbox_for_template_id_exam_templates"
SANDBOX_UQ = "uq_courses_sandbox_for_template_id"


def upgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("sandbox_for_template_id", sa.Uuid(as_uuid=True), nullable=True))
        b.create_foreign_key(op.f(SANDBOX_FK), "exam_templates", ["sandbox_for_template_id"], ["id"],
                             ondelete="SET NULL")
        b.create_unique_constraint(op.f(SANDBOX_UQ), ["sandbox_for_template_id"])


def downgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.drop_constraint(op.f(SANDBOX_UQ), type_="unique")
        b.drop_constraint(op.f(SANDBOX_FK), type_="foreignkey")
        b.drop_column("sandbox_for_template_id")
