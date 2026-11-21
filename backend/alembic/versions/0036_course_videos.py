"""Lesson videos (docs/phases/LESSON_VIDEOS.md V1, slice lv-a-backend)

Revision ID: 0036_course_videos
Revises: 0035_assessment_placement
Create Date: 2026-11-22

New table `course_videos` (an MP4 over a private `assets` row, optional captions asset, probed duration and size,
soft delete; one live row per course and sha256) and `module_items.video_id` (nullable FK, indexed) for the new item
kind `video`. The two module item checks are widened: `kind_valid` gains `video`, `item_target_matches_kind` gains
the `video` clause and `video_id IS NULL` for every other kind (true for every existing row). Additive: no existing row
changes, nothing is backfilled.

Downgrade restores the old checks and drops the column and the table; it is refused while a `video` item exists.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0036_course_videos"
down_revision: Union[str, None] = "0035_assessment_placement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = sa.Uuid(as_uuid=True)
CK_KIND = "ck_module_items_kind_valid"
CK_TARGET = "ck_module_items_item_target_matches_kind"
FK_VIDEO = "fk_module_items_video_id_course_videos"
IX_VIDEO = "ix_module_items_video_id"


def _in(col: str, values) -> str:
    return f"{col} IN (" + ",".join(f"'{v}'" for v in values) + ")"


# Copies of app/lms/modules/ids.py ITEM_KINDS and models.ITEM_TARGET_CHECK (a migration never imports app code).
OLD_KINDS = ("page", "file", "assignment", "url", "header")
NEW_KINDS = OLD_KINDS + ("video",)


def _target_check(cols: tuple, kinds: list) -> str:
    def one(kind: str, present) -> str:
        parts = [f"kind = '{kind}'"] + [f"{c} IS NOT NULL" if c == present else f"{c} IS NULL" for c in cols]
        return "(" + " AND ".join(parts) + ")"

    return " OR ".join(one(k, p) for k, p in kinds)


_OLD_COLS = ("page_id", "file_id", "assignment_id", "url")
_KINDS = [("page", "page_id"), ("file", "file_id"), ("assignment", "assignment_id"), ("url", "url"),
          ("header", None)]
OLD_TARGET = _target_check(_OLD_COLS, _KINDS)
NEW_TARGET = _target_check(_OLD_COLS + ("video_id",), _KINDS + [("video", "video_id")])


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        "course_videos",
        sa.Column("id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.String(length=64), nullable=True),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("asset_id", UUID, nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("captions_asset_id", UUID, nullable=True),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        _fk("course_videos", "course_id", "courses", "RESTRICT"),
        _fk("course_videos", "asset_id", "assets", "RESTRICT"),
        _fk("course_videos", "captions_asset_id", "assets", "RESTRICT"),
        _fk("course_videos", "created_by_id", "users", "SET NULL"),
        _fk("course_videos", "deleted_by_id", "users", "SET NULL"),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_course_videos_size_positive")),
        sa.CheckConstraint("duration_s > 0 AND width > 0 AND height > 0",
                           name=op.f("ck_course_videos_dimensions_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_videos")),
    )
    op.create_index("ix_course_videos_course_id_created_at", "course_videos", ["course_id", "created_at"])
    op.create_index("uq_course_videos_course_sha_live", "course_videos", ["course_id", "sha256"], unique=True,
                    postgresql_where=sa.text("deleted_at IS NULL"), sqlite_where=sa.text("deleted_at IS NULL"))

    with op.batch_alter_table("module_items") as b:
        b.add_column(sa.Column("video_id", UUID, nullable=True))
        b.create_foreign_key(op.f(FK_VIDEO), "course_videos", ["video_id"], ["id"], ondelete="RESTRICT")
        b.drop_constraint(op.f(CK_KIND), type_="check")
        b.drop_constraint(op.f(CK_TARGET), type_="check")
        b.create_check_constraint(op.f(CK_KIND), _in("kind", NEW_KINDS))
        b.create_check_constraint(op.f(CK_TARGET), NEW_TARGET)
    op.create_index(IX_VIDEO, "module_items", ["video_id"])


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT count(*) FROM module_items WHERE kind = 'video'")).scalar()
    if n:
        raise RuntimeError(f"0036 downgrade refused: {n} video module item(s) exist; delete them first")
    op.drop_index(IX_VIDEO, table_name="module_items")
    with op.batch_alter_table("module_items") as b:
        b.drop_constraint(op.f(CK_TARGET), type_="check")
        b.drop_constraint(op.f(CK_KIND), type_="check")
        b.create_check_constraint(op.f(CK_KIND), _in("kind", OLD_KINDS))
        b.create_check_constraint(op.f(CK_TARGET), OLD_TARGET)
        b.drop_constraint(op.f(FK_VIDEO), type_="foreignkey")
        b.drop_column("video_id")
    op.drop_index("uq_course_videos_course_sha_live", table_name="course_videos")
    op.drop_index("ix_course_videos_course_id_created_at", table_name="course_videos")
    op.drop_table("course_videos")
