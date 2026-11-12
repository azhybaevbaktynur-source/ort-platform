"""Teacher application notice dismissed (docs/phases/FIX_ROUND_2026-11-12.md 1c)

Revision ID: 0032_teacher_notice_dismissed
Revises: 0031_infra
Create Date: 2026-11-12

Additive, no data step: `teacher_requests.notice_dismissed_at` (null for every existing row: the decision line keeps its
14-day window). Set by `POST /me/teacher-application/dismiss` on the person's latest decided request; the home and the
Teaching view stop showing the line once it is set. Downgrade drops the column (the line comes back until its 14 days
are over).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0032_teacher_notice_dismissed"
down_revision: Union[str, None] = "0031_infra"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("teacher_requests") as b:
        b.add_column(sa.Column("notice_dismissed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("teacher_requests") as b:
        b.drop_column("notice_dismissed_at")
