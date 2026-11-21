"""Assessment placement (docs/phases/LESSON_COURSE_REQUESTS.md C1, slice lc-a-placement)

Revision ID: 0035_assessment_placement
Revises: 0034_course_listing
Create Date: 2026-11-22

`assessments.placement` (`tests` / `lesson`, NOT NULL DEFAULT 'tests'): a `lesson` quiz lives inside a lesson and is
never listed as a test (features.tests, student assignments list, home, my grades). Two checks: `placement_valid` and
`placement_lesson_plain` (a lesson quiz is never a preset or a practice quiz). Additive; every existing row is `tests`
through the server default, so behaviour is unchanged. Downgrade drops the checks and the column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035_assessment_placement"
down_revision: Union[str, None] = "0034_course_listing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CK_VALID = "ck_assessments_placement_valid"
CK_PLAIN = "ck_assessments_placement_lesson_plain"


def upgrade() -> None:
    with op.batch_alter_table("assessments") as b:
        b.add_column(sa.Column("placement", sa.String(16), nullable=False, server_default="tests"))
        b.create_check_constraint(op.f(CK_VALID), "placement IN ('tests','lesson')")
        b.create_check_constraint(op.f(CK_PLAIN), "placement = 'tests' OR (preset = 'none' AND NOT is_practice)")


def downgrade() -> None:
    with op.batch_alter_table("assessments") as b:
        b.drop_constraint(op.f(CK_PLAIN), type_="check")
        b.drop_constraint(op.f(CK_VALID), type_="check")
        b.drop_column("placement")
