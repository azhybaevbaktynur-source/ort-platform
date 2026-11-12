"""Course listing state (docs/phases/CATALOG_AND_TEACHERS_DESIGN.md 4.1, step 3b slice S1)

Revision ID: 0034_course_listing
Revises: 0033_course_exam_family
Create Date: 2026-11-13

`courses.listing` (`off` / `pending` / `listed` / `declined` / `blocked`, NOT NULL DEFAULT 'off', CHECK) separates "in
the platform catalog" (the platform admin decides) from `visibility` (link access, course staff). Five nullable columns
for the decision (`listing_requested_at`, `listing_decided_at`, `listing_decided_by_id` FK users ON DELETE SET NULL,
`listing_note` ≤ 500, `listing_content_changed_at`), one index for the catalog page query. Backfill, bounded UPDATEs in
this order: 1. `unlisted_by_admin_at` set → `blocked` (decided at that time); 2. `visibility = 'catalog'` in the
platform tree → `listed` (decided at `published_at`); 3. `visibility = 'catalog'`, published, any other tree →
`pending` (requested at `published_at`; owner decision D2); 4. everything else stays `off`. Then
`unlisted_by_admin_at` is dropped. Downgrade restores it from `blocked` and sets `visibility = 'catalog'` for
`listed` / `pending`, then drops the new columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034_course_listing"
down_revision: Union[str, None] = "0033_course_exam_family"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "ix_courses_listing_published_at"
CHECK = "ck_courses_listing_valid"
FK = "fk_courses_listing_decided_by_id_users"

# the course's organization lies in the platform organization's tree (a root's path is its own id, 32 hex chars)
_PLATFORM_TREE = (
    "EXISTS (SELECT 1 FROM organizations o JOIN organizations r ON r.path = substr(o.path, 1, 32) "
    "WHERE o.id = courses.organization_id AND r.kind = 'platform')"
)


def upgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("listing", sa.String(length=16), nullable=False, server_default="off"))
        b.add_column(sa.Column("listing_requested_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("listing_decided_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("listing_decided_by_id", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("listing_note", sa.String(length=500), nullable=True))
        b.add_column(sa.Column("listing_content_changed_at", sa.DateTime(timezone=True), nullable=True))
        b.create_check_constraint(op.f(CHECK), "listing IN ('off','pending','listed','declined','blocked')")
        b.create_foreign_key(op.f(FK), "users", ["listing_decided_by_id"], ["id"], ondelete="SET NULL")
        b.create_index(op.f(INDEX), ["listing", "published_at"])
    op.execute("UPDATE courses SET listing = 'blocked', listing_decided_at = unlisted_by_admin_at "
               "WHERE unlisted_by_admin_at IS NOT NULL")
    op.execute("UPDATE courses SET listing = 'listed', listing_decided_at = published_at "
               f"WHERE listing = 'off' AND visibility = 'catalog' AND {_PLATFORM_TREE}")
    op.execute("UPDATE courses SET listing = 'pending', listing_requested_at = published_at "
               "WHERE listing = 'off' AND visibility = 'catalog' AND status = 'published' "
               f"AND NOT {_PLATFORM_TREE}")
    with op.batch_alter_table("courses") as b:
        b.drop_column("unlisted_by_admin_at")


def downgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("unlisted_by_admin_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE courses SET unlisted_by_admin_at = COALESCE(listing_decided_at, updated_at) "
               "WHERE listing = 'blocked'")
    op.execute("UPDATE courses SET visibility = 'catalog' WHERE listing IN ('listed', 'pending')")
    with op.batch_alter_table("courses") as b:
        b.drop_index(op.f(INDEX))
        b.drop_constraint(op.f(FK), type_="foreignkey")
        b.drop_constraint(op.f(CHECK), type_="check")
        b.drop_column("listing_content_changed_at")
        b.drop_column("listing_note")
        b.drop_column("listing_decided_by_id")
        b.drop_column("listing_decided_at")
        b.drop_column("listing_requested_at")
        b.drop_column("listing")
