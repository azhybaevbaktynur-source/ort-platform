"""phase 11: two indexes proven by the EXPLAIN review (docs/phases/PHASE_11_EXPLAIN.md)

Revision ID: 0018_phase11_indexes
Revises: 0017_phase11_privacy
Create Date: 2026-11-02

`ix_enrollments_test_student`: `not_test_enrollment` (in every staff aggregate over attempts) read all of `enrollments`.
The predicate must stay `IS TRUE`: PostgreSQL does not prove `is_test_student IS TRUE` implies `is_test_student`.
`ix_grade_events_attempt_id`: the RESTRICT foreign key check scanned `grade_events` once per deleted practice attempt.

Plain CREATE INDEX, not CONCURRENTLY: `app.db.migrate.run_migrations` runs every migration at startup in one transaction
holding the advisory lock, and CONCURRENTLY cannot run inside a transaction. The build blocks writes to these two tables
only; measured on the perf seed (21k enrollments, 200k grade events, busy machine): 0.5 s and 1.9 s.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_phase11_indexes"
down_revision: Union[str, None] = "0017_phase11_privacy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_enrollments_test_student", "enrollments", ["id"],
                    postgresql_where=sa.text("is_test_student IS TRUE"), sqlite_where=sa.text("is_test_student = 1"))
    op.create_index("ix_grade_events_attempt_id", "grade_events", ["attempt_id"],
                    postgresql_where=sa.text("attempt_id IS NOT NULL"), sqlite_where=sa.text("attempt_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("ix_grade_events_attempt_id", table_name="grade_events")
    op.drop_index("ix_enrollments_test_student", table_name="enrollments")
