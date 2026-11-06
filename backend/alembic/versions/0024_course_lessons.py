"""Course lessons: lesson durations and Pro modules (docs/phases/COURSE_LESSONS_DESIGN.md, slice F5a)

Revision ID: 0024_course_lessons
Revises: 0023_person
Create Date: 2026-11-07

Additive, no data step: `module_items.duration_s` (nullable; 60..36000 seconds, set by the teacher in minutes) and
`course_modules.access_tier` (`free` for every existing module, server default; `paid` = Pro module, effective only in
platform courses for students without a pass). Downgrade drops both.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024_course_lessons"
down_revision: Union[str, None] = "0023_person"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("module_items") as b:
        b.add_column(sa.Column("duration_s", sa.Integer(), nullable=True))
        b.create_check_constraint(op.f("ck_module_items_duration_s_range"),
                                  "duration_s IS NULL OR (duration_s >= 60 AND duration_s <= 36000)")
    with op.batch_alter_table("course_modules") as b:
        b.add_column(sa.Column("access_tier", sa.String(8), nullable=False, server_default="free"))
        b.create_check_constraint(op.f("ck_course_modules_access_tier_valid"), "access_tier IN ('free','paid')")


def downgrade() -> None:
    with op.batch_alter_table("course_modules") as b:
        b.drop_constraint(op.f("ck_course_modules_access_tier_valid"), type_="check")
        b.drop_column("access_tier")
    with op.batch_alter_table("module_items") as b:
        b.drop_constraint(op.f("ck_module_items_duration_s_range"), type_="check")
        b.drop_column("duration_s")
