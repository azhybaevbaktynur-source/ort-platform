"""Course cover image (docs/phases/STUDENT_UI_FIX_PLAN.md 7.1, slice F7a)

Revision ID: 0026_course_cover
Revises: 0025_pro
Create Date: 2026-11-07

Additive, no data step: `courses.cover_asset_id` (null for every existing course: the card shows the generated default
cover), a foreign key to `assets.id` with ON DELETE SET NULL (an asset row that disappears leaves the course without a
cover, never a dangling id) and an index on it (the SET NULL lookup). Downgrade drops the index, the key and the column
(uploaded covers stay in the asset library; only the link is lost).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026_course_cover"
down_revision: Union[str, None] = "0025_pro"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COVER_FK = "fk_courses_cover_asset_id_assets"


def upgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("cover_asset_id", sa.Uuid(), nullable=True))
        b.create_foreign_key(op.f(COVER_FK), "assets", ["cover_asset_id"], ["id"], ondelete="SET NULL")
        b.create_index(op.f("ix_courses_cover_asset_id"), ["cover_asset_id"])


def downgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.drop_index(op.f("ix_courses_cover_asset_id"))
        b.drop_constraint(op.f(COVER_FK), type_="foreignkey")
        b.drop_column("cover_asset_id")
