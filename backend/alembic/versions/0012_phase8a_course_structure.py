"""phase 8a (S1): course structure (pages, modules, items, requirements, progress, course files, announcements)

Revision ID: 0012_phase8a_course_structure
Revises: 0011_phase7c_quiz_editor
Create Date: 2026-10-28

PHASE_8A_DESIGN section 2. Schema only, no data steps: `courses.home_kind` has the server default 'assignments'
(today's layout) and `courses.home_page_id` is NULL, so every existing course, the ORT courses included, keeps its
behaviour; the ten new tables start empty.

Downgrade is lossless while no page, module, course file or announcement exists (live or soft-deleted); it is refused
with a clear error otherwise. Items, requirements, facts and progress rows cannot exist without a module.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012_phase8a_course_structure"
down_revision: Union[str, None] = "0011_phase7c_quiz_editor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
_FALSE = sa.text("false")
HOME_PAGE_FK = "fk_courses_home_page_id_pages"
HOME_KIND_CK = "ck_courses_home_kind_valid"
CONTENT_TABLES = ("pages", "course_modules", "course_files", "announcements")


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete)


def _ck(table: str, name: str, sql: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=op.f(f"ck_{table}_{name}"))


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.String(length=64), nullable=True)


def _in(col: str, values) -> str:
    return f"{col} IN (" + ",".join(f"'{v}'" for v in values) + ")"


# Copies of app/lms/modules/ids.py enumerations and models.ITEM_TARGET_CHECK (a migration never imports app code).
ITEM_KINDS = ("page", "file", "assignment", "url", "header")
REQUIREMENT_TYPES = ("view", "mark_done", "submit", "min_score", "min_percent")
PROGRESS_EVENTS = ("viewed", "marked_done", "unmarked_done")
MODULE_STATES = ("locked", "unlocked", "started", "completed")


def _target(kind: str, present) -> str:
    cols = ("page_id", "file_id", "assignment_id", "url")
    parts = [f"kind = '{kind}'"] + [f"{c} IS NOT NULL" if c == present else f"{c} IS NULL" for c in cols]
    return "(" + " AND ".join(parts) + ")"


ITEM_TARGET_CHECK = " OR ".join((
    _target("page", "page_id"), _target("file", "file_id"), _target("assignment", "assignment_id"),
    _target("url", "url"), _target("header", None),
))


def _soft(table: str) -> list:
    """TimestampMixin + SoftDeleteMixin columns (deleted_by_id with its FK to users, SET NULL)."""
    return [_ts("created_at"), _ts("updated_at"), _ts("deleted_at", True), _user("deleted_by_id"),
            _fk(table, "deleted_by_id", "users", "SET NULL")]


def upgrade() -> None:
    # 2.2 pages
    op.create_table(
        "pages",
        sa.Column("id", UUID, nullable=False),
        *_soft("pages"),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("translation_group_id", UUID, nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("published", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("rev", sa.Integer(), server_default="1", nullable=False),
        _user("created_by_id"), _user("updated_by_id"),
        _fk("pages", "course_id", "courses", "RESTRICT"),
        _fk("pages", "created_by_id", "users", "SET NULL"),
        _fk("pages", "updated_by_id", "users", "SET NULL"),
        _ck("pages", "language_valid", "language IN ('en','ru','ky')"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pages")),
    )
    op.create_index("uq_pages_group_language_live", "pages", ["translation_group_id", "language"], unique=True,
                    postgresql_where=sa.text("deleted_at IS NULL"), sqlite_where=sa.text("deleted_at IS NULL"))
    op.create_index("ix_pages_course_id_deleted_at", "pages", ["course_id", "deleted_at"])

    # 2.1 courses: home kind (server default = today's layout) and home page
    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("home_kind", sa.String(length=16), server_default="assignments", nullable=False))
        b.add_column(sa.Column("home_page_id", UUID, nullable=True))
        b.create_foreign_key(op.f(HOME_PAGE_FK), "pages", ["home_page_id"], ["id"], ondelete="SET NULL")
        b.create_check_constraint(op.f(HOME_KIND_CK), "home_kind IN ('modules','page','assignments')")

    # 2.10 course files
    op.create_table(
        "course_files",
        sa.Column("id", UUID, nullable=False),
        *_soft("course_files"),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("asset_id", UUID, nullable=False),
        sa.Column("folder", sa.String(length=200), server_default="", nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("published", sa.Boolean(), server_default=_FALSE, nullable=False),
        _user("created_by_id"),
        _fk("course_files", "course_id", "courses", "RESTRICT"),
        _fk("course_files", "asset_id", "assets", "RESTRICT"),
        _fk("course_files", "created_by_id", "users", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_files")),
    )
    op.create_index("ix_course_files_course_id_folder", "course_files", ["course_id", "folder"])

    # 2.11 announcements
    op.create_table(
        "announcements",
        sa.Column("id", UUID, nullable=False),
        *_soft("announcements"),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("author_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), server_default=_FALSE, nullable=False),
        _ts("published_at", True),
        sa.Column("rev", sa.Integer(), server_default="1", nullable=False),
        _fk("announcements", "course_id", "courses", "RESTRICT"),
        _fk("announcements", "author_id", "users", "RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcements")),
    )
    op.create_index("ix_announcements_course_id_published_at", "announcements", ["course_id", "published_at"])

    # 2.3 modules
    op.create_table(
        "course_modules",
        sa.Column("id", UUID, nullable=False),
        *_soft("course_modules"),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("title", JSONType, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("published", sa.Boolean(), server_default=_FALSE, nullable=False),
        _ts("unlock_at", True),
        sa.Column("sequential", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("completion_mode", sa.String(length=3), server_default="all", nullable=False),
        sa.Column("rules_version", sa.Integer(), server_default="1", nullable=False),
        _user("created_by_id"),
        _fk("course_modules", "course_id", "courses", "RESTRICT"),
        _fk("course_modules", "created_by_id", "users", "SET NULL"),
        _ck("course_modules", "completion_mode_valid", "completion_mode IN ('all','any')"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_modules")),
    )
    op.create_index("ix_course_modules_course_id_position", "course_modules", ["course_id", "position"])

    # 2.4 prerequisites
    op.create_table(
        "module_prerequisites",
        sa.Column("module_id", UUID, nullable=False),
        sa.Column("prerequisite_module_id", UUID, nullable=False),
        _fk("module_prerequisites", "module_id", "course_modules", "RESTRICT"),
        _fk("module_prerequisites", "prerequisite_module_id", "course_modules", "RESTRICT"),
        _ck("module_prerequisites", "not_self", "module_id <> prerequisite_module_id"),
        sa.PrimaryKeyConstraint("module_id", "prerequisite_module_id", name=op.f("pk_module_prerequisites")),
    )

    # 2.5 items
    op.create_table(
        "module_items",
        sa.Column("id", UUID, nullable=False),
        *_soft("module_items"),
        sa.Column("module_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("indent", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("title_override", JSONType, nullable=True),
        sa.Column("published", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("page_id", UUID, nullable=True),
        sa.Column("file_id", UUID, nullable=True),
        sa.Column("assignment_id", UUID, nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        _fk("module_items", "module_id", "course_modules", "RESTRICT"),
        _fk("module_items", "page_id", "pages", "RESTRICT"),
        _fk("module_items", "file_id", "course_files", "RESTRICT"),
        _fk("module_items", "assignment_id", "assignments", "RESTRICT"),
        _ck("module_items", "kind_valid", _in("kind", ITEM_KINDS)),
        _ck("module_items", "indent_valid", "indent >= 0 AND indent <= 3"),
        _ck("module_items", "item_target_matches_kind", ITEM_TARGET_CHECK),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_module_items")),
    )
    op.create_index("ix_module_items_module_id_position", "module_items", ["module_id", "position"])
    op.create_index("ix_module_items_assignment_id", "module_items", ["assignment_id"])
    op.create_index("ix_module_items_page_id", "module_items", ["page_id"])
    op.create_index("ix_module_items_file_id", "module_items", ["file_id"])

    # 2.6 requirements (one per item)
    op.create_table(
        "item_completion_requirements",
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("type", sa.String(length=12), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=8, scale=2), nullable=True),
        _fk("item_completion_requirements", "item_id", "module_items", "RESTRICT"),
        _ck("item_completion_requirements", "type_valid", _in("type", REQUIREMENT_TYPES)),
        _ck("item_completion_requirements", "threshold_matches_type",
            "(type IN ('min_score','min_percent')) = (threshold IS NOT NULL)"),
        _ck("item_completion_requirements", "threshold_nonnegative", "threshold IS NULL OR threshold >= 0"),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_item_completion_requirements")),
    )

    # 2.7 facts (append-only)
    op.create_table(
        "item_progress",
        sa.Column("id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("event", sa.String(length=14), nullable=False),
        _ts("created_at"),
        _fk("item_progress", "enrollment_id", "enrollments", "RESTRICT"),
        _fk("item_progress", "item_id", "module_items", "RESTRICT"),
        _ck("item_progress", "event_valid", _in("event", PROGRESS_EVENTS)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_progress")),
    )
    op.create_index("uq_item_progress_viewed", "item_progress", ["enrollment_id", "item_id"], unique=True,
                    postgresql_where=sa.text("event = 'viewed'"), sqlite_where=sa.text("event = 'viewed'"))
    op.create_index("ix_item_progress_enrollment_id_created_at", "item_progress", ["enrollment_id", "created_at"])

    # 2.8 module progress (derived cache)
    op.create_table(
        "module_progress",
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("module_id", UUID, nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        _ts("unlocked_at", True), _ts("completed_at", True),
        sa.Column("current_position", sa.Integer(), nullable=True),
        sa.Column("evaluated_rules_version", sa.Integer(), nullable=False),
        _ts("evaluated_at"), _ts("facts_seen_at", True), _ts("grades_seen_at", True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        _fk("module_progress", "enrollment_id", "enrollments", "RESTRICT"),
        _fk("module_progress", "module_id", "course_modules", "RESTRICT"),
        _ck("module_progress", "state_valid", _in("state", MODULE_STATES)),
        sa.PrimaryKeyConstraint("enrollment_id", "module_id", name=op.f("pk_module_progress")),
    )
    op.create_index("ix_module_progress_enrollment_id", "module_progress", ["enrollment_id"])

    # 2.9 requirement status (derived; monotone)
    op.create_table(
        "item_requirement_status",
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("item_id", UUID, nullable=False),
        sa.Column("met", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("best_score_percent", sa.Numeric(precision=6, scale=2), nullable=True),
        _ts("met_at", True), _ts("updated_at"),
        _fk("item_requirement_status", "enrollment_id", "enrollments", "RESTRICT"),
        _fk("item_requirement_status", "item_id", "module_items", "RESTRICT"),
        sa.PrimaryKeyConstraint("enrollment_id", "item_id", name=op.f("pk_item_requirement_status")),
    )


def downgrade() -> None:
    conn = op.get_bind()
    found = {t: conn.execute(sa.text(f"SELECT count(*) FROM {t}")).scalar() for t in CONTENT_TABLES}
    found = {t: n for t, n in found.items() if n}
    if found:
        listed = ", ".join(f"{n} in {t}" for t, n in found.items())
        raise RuntimeError(f"0012 downgrade refused: course structure rows exist ({listed}); this direction would "
                           "drop them")
    op.drop_table("item_requirement_status")
    op.drop_index("ix_module_progress_enrollment_id", table_name="module_progress")
    op.drop_table("module_progress")
    op.drop_index("ix_item_progress_enrollment_id_created_at", table_name="item_progress")
    op.drop_index("uq_item_progress_viewed", table_name="item_progress")
    op.drop_table("item_progress")
    op.drop_table("item_completion_requirements")
    for ix in ("ix_module_items_file_id", "ix_module_items_page_id", "ix_module_items_assignment_id",
               "ix_module_items_module_id_position"):
        op.drop_index(ix, table_name="module_items")
    op.drop_table("module_items")
    op.drop_table("module_prerequisites")
    op.drop_index("ix_course_modules_course_id_position", table_name="course_modules")
    op.drop_table("course_modules")
    op.drop_index("ix_announcements_course_id_published_at", table_name="announcements")
    op.drop_table("announcements")
    op.drop_index("ix_course_files_course_id_folder", table_name="course_files")
    op.drop_table("course_files")
    with op.batch_alter_table("courses") as b:
        b.drop_constraint(op.f(HOME_KIND_CK), type_="check")
        b.drop_constraint(op.f(HOME_PAGE_FK), type_="foreignkey")
        b.drop_column("home_page_id")
        b.drop_column("home_kind")
    op.drop_index("ix_pages_course_id_deleted_at", table_name="pages")
    op.drop_index("uq_pages_group_language_live", table_name="pages")
    op.drop_table("pages")
