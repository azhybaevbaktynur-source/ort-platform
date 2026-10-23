"""phase 2: assets, question banks, passages, versioned questions

Revision ID: 0003_phase2_content
Revises: 0002_phase1_courses
Create Date: 2026-10-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase2_content"
down_revision: Union[str, None] = "0002_phase1_courses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
ORIGINS = "origin IN ('create','edit','import','revert')"
TYPES = "type IN ('single_choice','multiple_answers','true_false','comparison','numeric','short_text','essay')"


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def _soft_delete(table: str) -> list:
    return [
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["deleted_by_id"], ["users.id"], name=op.f(f"fk_{table}_deleted_by_id_users"), ondelete="SET NULL"
        ),
    ]


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete
    )


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("course_id", UUID, nullable=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("visibility", sa.String(length=8), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("mime", sa.String(length=64), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("source_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        *_soft_delete("assets"),
        _fk("assets", "owner_id", "users", "RESTRICT"),
        _fk("assets", "course_id", "courses", "SET NULL"),
        sa.CheckConstraint("kind IN ('image')", name=op.f("ck_assets_kind_valid")),
        sa.CheckConstraint("visibility IN ('public','private')", name=op.f("ck_assets_visibility_valid")),
        sa.CheckConstraint("bytes > 0", name=op.f("ck_assets_bytes_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
        sa.UniqueConstraint("owner_id", "source_sha256", "visibility", name="uq_assets_owner_source"),
    )
    op.create_index("ix_assets_owner_id_created_at", "assets", ["owner_id", "created_at"])
    op.create_index("ix_assets_sha256", "assets", ["sha256"])

    op.create_table(
        "asset_blobs",
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_asset_blobs")),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE asset_blobs ALTER COLUMN data SET STORAGE EXTERNAL")

    op.create_table(
        "question_banks",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("course_id", UUID, nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_id", sa.String(length=120), nullable=True),
        sa.Column("default_language", sa.String(length=2), nullable=True),
        *_soft_delete("question_banks"),
        _fk("question_banks", "owner_id", "users", "RESTRICT"),
        _fk("question_banks", "course_id", "courses", "RESTRICT"),
        sa.CheckConstraint(
            "default_language IS NULL OR default_language IN ('en','ru','ky')",
            name=op.f("ck_question_banks_default_language_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_banks")),
    )
    _where = sa.text("source_id IS NOT NULL AND course_id IS NOT NULL AND deleted_at IS NULL")
    op.create_index(
        "uq_question_banks_course_source", "question_banks", ["course_id", "source_id"], unique=True,
        postgresql_where=_where, sqlite_where=_where,
    )
    op.create_index(
        "ix_question_banks_course_id_deleted_at_created_at", "question_banks",
        ["course_id", "deleted_at", "created_at"],
    )
    op.create_index("ix_question_banks_owner_id", "question_banks", ["owner_id"])

    op.create_table(
        "translation_groups",
        sa.Column("id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=True),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        _ts("created_at"),
        _fk("translation_groups", "course_id", "courses", "RESTRICT"),
        _fk("translation_groups", "created_by_id", "users", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_translation_groups")),
    )
    op.create_index("ix_translation_groups_course_id", "translation_groups", ["course_id"])

    op.create_table(
        "passages",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("bank_id", UUID, nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("current_version_id", UUID, nullable=True),
        sa.Column("imported_version_id", UUID, nullable=True),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        *_soft_delete("passages"),
        _fk("passages", "bank_id", "question_banks", "RESTRICT"),
        sa.CheckConstraint("language IN ('en','ru','ky')", name=op.f("ck_passages_language_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passages")),
    )
    _src = sa.text("source_ref IS NOT NULL")
    op.create_index(
        "uq_passages_bank_source_ref", "passages", ["bank_id", "source_ref"], unique=True,
        postgresql_where=_src, sqlite_where=_src,
    )
    op.create_index("ix_passages_bank_id_deleted_at", "passages", ["bank_id", "deleted_at"])

    op.create_table(
        "passage_versions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("passage_id", UUID, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("image", JSONType, nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("origin", sa.String(length=8), nullable=False),
        _ts("created_at"),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        _fk("passage_versions", "passage_id", "passages", "RESTRICT"),
        _fk("passage_versions", "created_by_id", "users", "SET NULL"),
        sa.CheckConstraint(ORIGINS, name=op.f("ck_passage_versions_origin_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passage_versions")),
        sa.UniqueConstraint("passage_id", "version_no", name="uq_passage_versions_passage_version"),
    )

    op.create_table(
        "bank_questions",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("bank_id", UUID, nullable=False),
        sa.Column("passage_id", UUID, nullable=True),
        sa.Column("translation_group_id", UUID, nullable=True),
        sa.Column("current_version_id", UUID, nullable=True),
        sa.Column("imported_version_id", UUID, nullable=True),
        sa.Column("type", sa.String(length=24), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=True),
        sa.Column("difficulty", sa.String(length=8), nullable=True),
        sa.Column("section", sa.String(length=40), nullable=True),
        sa.Column("tags", JSONType, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("q_num", sa.String(length=16), nullable=True),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        sa.Column("source_meta", JSONType, nullable=True),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        *_soft_delete("bank_questions"),
        _fk("bank_questions", "bank_id", "question_banks", "RESTRICT"),
        _fk("bank_questions", "passage_id", "passages", "RESTRICT"),
        _fk("bank_questions", "translation_group_id", "translation_groups", "SET NULL"),
        sa.CheckConstraint(TYPES, name=op.f("ck_bank_questions_type_valid")),
        sa.CheckConstraint("language IN ('en','ru','ky')", name=op.f("ck_bank_questions_language_valid")),
        sa.CheckConstraint(
            "difficulty IS NULL OR difficulty IN ('easy','medium','hard')",
            name=op.f("ck_bank_questions_difficulty_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_questions")),
    )
    op.create_index(
        "uq_bank_questions_source_ref", "bank_questions", ["bank_id", "source_ref"], unique=True,
        postgresql_where=_src, sqlite_where=_src,
    )
    _grp = sa.text("translation_group_id IS NOT NULL AND deleted_at IS NULL")
    op.create_index(
        "uq_bank_questions_group_language", "bank_questions", ["translation_group_id", "language"], unique=True,
        postgresql_where=_grp, sqlite_where=_grp,
    )
    op.create_index("ix_bank_questions_bank_id_position_id", "bank_questions", ["bank_id", "position", "id"])
    op.create_index("ix_bank_questions_passage_id", "bank_questions", ["passage_id"])
    op.create_index("ix_bank_questions_translation_group_id", "bank_questions", ["translation_group_id"])

    op.create_table(
        "question_versions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("question_id", UUID, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("type", sa.String(length=24), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("stem", sa.Text(), server_default="", nullable=False),
        sa.Column("data", JSONType, nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("default_points", sa.Numeric(8, 2), server_default="1", nullable=False),
        sa.Column("image", JSONType, nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("origin", sa.String(length=8), nullable=False),
        _ts("created_at"),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        _fk("question_versions", "question_id", "bank_questions", "RESTRICT"),
        _fk("question_versions", "created_by_id", "users", "SET NULL"),
        sa.CheckConstraint(
            "default_points >= 0 AND default_points <= 1000", name=op.f("ck_question_versions_default_points_valid")
        ),
        sa.CheckConstraint(TYPES, name=op.f("ck_question_versions_type_valid")),
        sa.CheckConstraint(ORIGINS, name=op.f("ck_question_versions_origin_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_versions")),
        sa.UniqueConstraint("question_id", "version_no", name="uq_question_versions_question_version"),
    )

    # Circular FKs (question/passage <-> version) are added after both tables exist.
    with op.batch_alter_table("passages") as b:
        b.create_foreign_key("fk_passages_current_version_id", "passage_versions", ["current_version_id"], ["id"])
        b.create_foreign_key("fk_passages_imported_version_id", "passage_versions", ["imported_version_id"], ["id"])
    with op.batch_alter_table("bank_questions") as b:
        b.create_foreign_key(
            "fk_bank_questions_current_version_id", "question_versions", ["current_version_id"], ["id"]
        )
        b.create_foreign_key(
            "fk_bank_questions_imported_version_id", "question_versions", ["imported_version_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("bank_questions") as b:
        b.drop_constraint("fk_bank_questions_imported_version_id", type_="foreignkey")
        b.drop_constraint("fk_bank_questions_current_version_id", type_="foreignkey")
    with op.batch_alter_table("passages") as b:
        b.drop_constraint("fk_passages_imported_version_id", type_="foreignkey")
        b.drop_constraint("fk_passages_current_version_id", type_="foreignkey")
    for table in ("question_versions", "bank_questions", "passage_versions", "passages",
                  "translation_groups", "question_banks", "asset_blobs", "assets"):
        op.drop_table(table)
