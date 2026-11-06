"""S4 person page: last login, the admin users list index, pending email changes (docs/ROADMAP_EXAM_PREP.md S4)

Revision ID: 0023_person
Revises: 0022_access
Create Date: 2026-11-06

Additive: `users.last_login_at` (nullable; nobody has one until their next sign-in), an index on
`users (created_at, id)` for the admin users list, and `email_change_requests` (empty; one pending change per user, the
token only as a keyed hash). Downgrade drops all three (pending changes are lost: their links stop working).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023_person"
down_revision: Union[str, None] = "0022_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_created_at_id", "users", ["created_at", "id"])
    op.create_table(
        "email_change_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("new_email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_email_change_requests_user_id_users"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"],
                                name=op.f("fk_email_change_requests_requested_by_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_change_requests")),
        sa.UniqueConstraint("user_id", name="uq_email_change_requests_user_id"),
        sa.UniqueConstraint("token_hash", name="uq_email_change_requests_token_hash"),
    )
    op.create_index("ix_email_change_requests_expires_at", "email_change_requests", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_email_change_requests_expires_at", table_name="email_change_requests")
    op.drop_table("email_change_requests")
    op.drop_index("ix_users_created_at_id", table_name="users")
    op.drop_column("users", "last_login_at")
