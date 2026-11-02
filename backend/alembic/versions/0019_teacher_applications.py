"""accounts: the teacher application form's columns on teacher_requests (docs/phases/ACCOUNTS.md A)

Revision ID: 0019_teacher_applications
Revises: 0018_phase11_indexes
Create Date: 2026-11-03

Additive and nullable: older requests keep their `message`; the form requires the new fields, the database doesn't.
`phone_purge_after`: set on a rejection or a revoke; the purge job (`app/lms/teachers/purge.py`) nulls the phone after it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_teacher_applications"
down_revision: Union[str, None] = "0018_phase11_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("teacher_requests", sa.Column("applicant_name", sa.String(200), nullable=True))
    op.add_column("teacher_requests", sa.Column("school", sa.String(200), nullable=True))
    op.add_column("teacher_requests", sa.Column("subject", sa.String(200), nullable=True))
    op.add_column("teacher_requests", sa.Column("phone", sa.String(32), nullable=True))
    op.add_column("teacher_requests", sa.Column("phone_purge_after", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("teacher_requests", "phone_purge_after")
    op.drop_column("teacher_requests", "phone")
    op.drop_column("teacher_requests", "subject")
    op.drop_column("teacher_requests", "school")
    op.drop_column("teacher_requests", "applicant_name")
