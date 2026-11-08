"""Social sign-in: linked Google / Apple accounts (docs/phases/AUTH_SOCIAL_DESIGN.md 2.2)

Revision ID: 0029_user_identities
Revises: 0027_exam_course_link
Create Date: 2026-11-09

Additive: `user_identities` (empty). One row per (provider, subject), at most one per (user, provider). Downgrade drops
the table (linked people sign in again by password, or link again through the provider).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029_user_identities"
down_revision: Union[str, None] = "0027_exam_course_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('google','apple')", name=op.f("ck_user_identities_provider_valid")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_identities_user_id_users"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_identities")),
        sa.UniqueConstraint("provider", "subject", name="uq_user_identities_provider_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_identities_user_provider"),
    )


def downgrade() -> None:
    op.drop_table("user_identities")
