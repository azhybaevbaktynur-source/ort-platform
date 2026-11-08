"""Infrastructure panel snapshots (docs/phases/INFRA_PANEL_DESIGN.md 5, slice I5a)

Revision ID: 0031_infra
Revises: 0029_user_identities
Create Date: 2026-11-09

Additive, no data step: `infra_snapshots`, one cached row per provider (neon, render, vercel, r2, email) with its status,
the allow-listed usage payload, the last fetch time, a short error code and the duration. No personal data, no keys.
The rows are a cache: downgrade drops the table and nothing is lost that a refresh does not rebuild.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0031_infra"
down_revision: Union[str, None] = "0029_user_identities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "infra_snapshots",
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False,
                  server_default=sa.text("'{}'")),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider", name=op.f("pk_infra_snapshots")),
    )


def downgrade() -> None:
    op.drop_table("infra_snapshots")
