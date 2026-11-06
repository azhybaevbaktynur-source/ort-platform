"""S1 admin security: two-step login for platform admins (docs/ROADMAP_EXAM_PREP.md S1)

Revision ID: 0021_admin_mfa
Revises: 0019_teacher_applications
Create Date: 2026-11-06

Additive: four nullable columns on `users` (the encrypted TOTP secret, a pending one during setup, when it was turned on,
the last accepted time step) and `user_mfa_recovery_codes` (keyed hashes, one row per code). Nobody has two-step login
after the upgrade; with ADMIN_MFA_REQUIRED the platform admins are asked to set it up on their next admin visit.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_admin_mfa"
down_revision: Union[str, None] = "0019_teacher_applications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret_enc", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("mfa_pending_secret_enc", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))
    op.create_table(
        "user_mfa_recovery_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_mfa_recovery_codes_user_id_users"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_mfa_recovery_codes")),
    )
    op.create_index("ix_user_mfa_recovery_codes_user_id", "user_mfa_recovery_codes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_mfa_recovery_codes_user_id", table_name="user_mfa_recovery_codes")
    op.drop_table("user_mfa_recovery_codes")
    op.drop_column("users", "mfa_last_step")
    op.drop_column("users", "mfa_enabled_at")
    op.drop_column("users", "mfa_pending_secret_enc")
    op.drop_column("users", "mfa_secret_enc")
