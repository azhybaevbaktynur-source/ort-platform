"""phase 5 (S4): R2 free-tier guard: storage_usage, storage_monthly_usage, PDF file assets

Revision ID: 0007_phase5_storage
Revises: 0006_phase5_cutover
Create Date: 2026-10-23
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_phase5_storage"
down_revision: Union[str, None] = "0006_phase5_cutover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Backfill: every blob in the db driver's table, plus every distinct storage key that assets reference but that
# table does not hold (r2/local blobs; soft-deleted assets keep their blobs, so they count too).
_BACKFILL = sa.text(
    "INSERT INTO storage_usage (id, stored_bytes, object_count, updated_at) "
    "SELECT 1, b.s + r.s, b.c + r.c, :now FROM "
    "(SELECT coalesce(sum(size), 0) AS s, count(*) AS c FROM asset_blobs) AS b, "
    "(SELECT coalesce(sum(k.bytes), 0) AS s, count(*) AS c FROM "
    " (SELECT storage_key, max(bytes) AS bytes FROM assets "
    "  WHERE storage_key NOT IN (SELECT key FROM asset_blobs) GROUP BY storage_key) AS k) AS r "
    "WHERE 1 = 1 "  # SQLite: INSERT ... SELECT ... ON CONFLICT needs a WHERE clause
    "ON CONFLICT (id) DO NOTHING"
)


def upgrade() -> None:
    op.create_table(
        "storage_usage",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("stored_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("object_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_storage_usage_singleton")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_usage")),
    )
    op.create_table(
        "storage_monthly_usage",
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("class_a", sa.Integer(), server_default="0", nullable=False),
        sa.Column("class_b", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bytes_written", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("objects_written", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("month", name=op.f("pk_storage_monthly_usage")),
    )
    with op.batch_alter_table("assets") as b:
        b.add_column(sa.Column("extension", sa.String(length=8), server_default="webp", nullable=False))
        b.drop_constraint(op.f("ck_assets_kind_valid"), type_="check")
        b.create_check_constraint(op.f("ck_assets_kind_valid"), "kind IN ('image','file')")
    op.get_bind().execute(_BACKFILL.bindparams(
        sa.bindparam("now", datetime.now(timezone.utc), type_=sa.DateTime(timezone=True))))


def downgrade() -> None:
    op.execute("DELETE FROM assets WHERE kind = 'file'")  # PDF rows cannot satisfy the old CHECK
    with op.batch_alter_table("assets") as b:
        b.drop_constraint(op.f("ck_assets_kind_valid"), type_="check")
        b.create_check_constraint(op.f("ck_assets_kind_valid"), "kind IN ('image')")
        b.drop_column("extension")
    op.drop_table("storage_monthly_usage")
    op.drop_table("storage_usage")
