"""exam prep S2: a student's target score per exam-prep course (docs/ROADMAP_EXAM_PREP.md S2)

Revision ID: 0020_exam_goals
Revises: 0019_teacher_applications
Create Date: 2026-11-06

Additive: one new table. The range of `target_score` is the scale of the course template's exam preset (ORT 60..245),
checked by the service, so there is no CHECK constraint here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_exam_goals"
down_revision: Union[str, None] = "0019_teacher_applications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exam_goals",
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("target_score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("exam_goals")
