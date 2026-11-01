"""student view: test student flags on users and enrollments

Revision ID: 0015_test_student
Revises: 0014_phase9_organizations_forms
Create Date: 2026-11-01

UX rework, UX_REWORK_DESIGN F: `users.is_test_student` and `enrollments.is_test_student` (false for every existing row)
and a partial unique index, one active test enrollment per course. No data step.

Downgrade drops both columns. Without the flags a test student would count as an ordinary one, so its enrollment is
removed and its account disabled first (the rows themselves stay: attempts and grade events reference them).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_test_student"
down_revision: Union[str, None] = "0014_phase9_organizations_forms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_enrollments_active_test_student"


def upgrade() -> None:
    op.add_column("users", sa.Column("is_test_student", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("enrollments", sa.Column("is_test_student", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_index(_INDEX, "enrollments", ["course_id"], unique=True,
                    postgresql_where=sa.text("is_test_student AND state = 'active'"),
                    sqlite_where=sa.text("is_test_student AND state = 'active'"))


def downgrade() -> None:
    op.execute("UPDATE enrollments SET state = 'removed', removed_at = CURRENT_TIMESTAMP "
               "WHERE is_test_student AND state = 'active'")
    op.execute("UPDATE users SET disabled_at = CURRENT_TIMESTAMP WHERE is_test_student AND disabled_at IS NULL")
    op.drop_index(_INDEX, table_name="enrollments")
    op.drop_column("enrollments", "is_test_student")
    op.drop_column("users", "is_test_student")
