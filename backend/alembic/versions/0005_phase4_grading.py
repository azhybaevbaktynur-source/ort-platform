"""phase 4: grading schemes and versions, grade categories, submissions, attempt grades, grade events, course grades

Revision ID: 0005_phase4_grading
Revises: 0004_phase3_assessments
Create Date: 2026-10-23
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase4_grading"
down_revision: Union[str, None] = "0004_phase3_assessments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
_FALSE = sa.text("false")
_TYPES = "type IN ('points','percent','bands','pass_fail','piecewise_curve','lookup_table')"
_EVENTS = ("event IN ('override','override_cleared','excused','unexcused','released','unreleased','regraded',"
           "'attempt_voided')")
_STATES = "state IN ('pending_review','graded','excused','no_attempts')"
# computed_at of a backfilled placeholder: always a regrade target (app.lms.grading.submissions.NEVER_COMPUTED)
_NEVER_COMPUTED = datetime(1970, 1, 1, tzinfo=timezone.utc)

# PostgreSQL guards (S7): grade_events append-only, grading_scheme_versions immutable. Two exceptions: the FK
# `ON DELETE SET NULL` of the user columns (a user row deleted: only that column becomes NULL), and the session
# setting `lms.allow_grade_purge = 'on'` (maintenance / test teardown only; no API path sets it). The same DDL is
# attached to the models for create_all (app/lms/grading/models.py); keep both copies identical.
_GUARD_FN = """
CREATE OR REPLACE FUNCTION lms_grading_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    col text := TG_ARGV[0];
BEGIN
    IF coalesce(current_setting('lms.allow_grade_purge', true), '') = 'on' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' AND col IS NOT NULL AND (to_jsonb(OLD) ->> col) IS NOT NULL
       AND (to_jsonb(NEW) ->> col) IS NULL AND (to_jsonb(NEW) - col) = (to_jsonb(OLD) - col) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% rows are immutable (% refused)', TG_TABLE_NAME, TG_OP USING ERRCODE = 'raise_exception';
END
$$
"""
_GUARD_TRIGGERS = (
    ("trg_grade_events_append_only", "grade_events", "BEFORE UPDATE OR DELETE", "actor_id"),
    ("trg_grading_scheme_versions_immutable", "grading_scheme_versions", "BEFORE UPDATE", "created_by_id"),
)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def _tstz(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        "grading_schemes",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        _tstz("deleted_at"),
        sa.Column("deleted_by_id", sa.String(length=64), nullable=True),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("key", sa.String(length=32), nullable=True),
        sa.Column("title", JSONType, nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("current_version_id", UUID, nullable=True),
        sa.Column("last_version_no", sa.Integer(), server_default="0", nullable=False),
        _fk("grading_schemes", "owner_user_id", "users", "RESTRICT"),
        _fk("grading_schemes", "deleted_by_id", "users", "SET NULL"),
        sa.CheckConstraint(_TYPES, name=op.f("ck_grading_schemes_type_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_schemes")),
    )
    _key = sa.text("key IS NOT NULL")
    op.create_index("uq_grading_schemes_key", "grading_schemes", ["key"], unique=True,
                    postgresql_where=_key, sqlite_where=_key)
    op.create_index("ix_grading_schemes_owner_user_id_deleted_at", "grading_schemes",
                    ["owner_user_id", "deleted_at"])

    op.create_table(
        "grading_scheme_versions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("scheme_id", UUID, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("scale_min", sa.Numeric(10, 2), nullable=True),
        sa.Column("scale_max", sa.Numeric(10, 2), nullable=True),
        sa.Column("params", JSONType, nullable=False),
        sa.Column("params_hash", sa.String(length=64), nullable=False),
        _ts("created_at"),
        sa.Column("created_by_id", sa.String(length=64), nullable=True),
        _fk("grading_scheme_versions", "scheme_id", "grading_schemes", "RESTRICT"),
        _fk("grading_scheme_versions", "created_by_id", "users", "SET NULL"),
        sa.CheckConstraint(_TYPES, name=op.f("ck_grading_scheme_versions_type_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_scheme_versions")),
        sa.UniqueConstraint("scheme_id", "version_no", name="uq_grading_scheme_versions_scheme_version"),
    )

    with op.batch_alter_table("grading_schemes") as b:
        b.create_foreign_key("fk_grading_schemes_current_version_id", "grading_scheme_versions",
                             ["current_version_id"], ["id"])

    op.create_table(
        "grade_categories",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        _tstz("deleted_at"),
        sa.Column("deleted_by_id", sa.String(length=64), nullable=True),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("title", JSONType, nullable=False),
        sa.Column("weight", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        _fk("grade_categories", "course_id", "courses", "RESTRICT"),
        _fk("grade_categories", "deleted_by_id", "users", "SET NULL"),
        sa.CheckConstraint("weight >= 0 AND weight <= 100", name=op.f("ck_grade_categories_weight_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grade_categories")),
    )
    op.create_index("ix_grade_categories_course_id_deleted_at_position", "grade_categories",
                    ["course_id", "deleted_at", "position"])

    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("grading_total_mode", sa.String(length=8), server_default="points", nullable=False))
        b.add_column(sa.Column("grading_scheme_version_id", UUID, nullable=True))
        b.add_column(sa.Column("late_policy", JSONType, nullable=True))
        b.add_column(_tstz("grading_changed_at"))
        b.add_column(_tstz("late_policy_changed_at"))
        b.create_check_constraint(op.f("ck_courses_grading_total_mode_valid"),
                                  "grading_total_mode IN ('points','weighted')")
        b.create_foreign_key(op.f("fk_courses_grading_scheme_version_id_grading_scheme_versions"),
                             "grading_scheme_versions", ["grading_scheme_version_id"], ["id"], ondelete="RESTRICT")

    with op.batch_alter_table("assessments") as b:
        b.add_column(sa.Column("grading_scheme_version_id", UUID, nullable=True))
        b.add_column(sa.Column("grade_category_id", UUID, nullable=True))
        b.add_column(_tstz("due_at"))
        b.add_column(sa.Column("grade_release", sa.String(length=8), server_default="auto", nullable=False))
        b.add_column(sa.Column("omit_from_total", sa.Boolean(), server_default=_FALSE, nullable=False))
        b.add_column(_tstz("grading_changed_at"))
        b.create_check_constraint(op.f("ck_assessments_grade_release_valid"), "grade_release IN ('auto','manual')")
        b.create_foreign_key("fk_assessments_grading_scheme_version_id",
                             "grading_scheme_versions", ["grading_scheme_version_id"], ["id"], ondelete="RESTRICT")
        b.create_foreign_key(op.f("fk_assessments_grade_category_id_grade_categories"),
                             "grade_categories", ["grade_category_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "submissions",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("assessment_id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("kept_attempt_id", UUID, nullable=True),
        sa.Column("kept_policy", sa.String(length=8), nullable=False),
        sa.Column("attempts_counted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("raw_points", sa.Numeric(10, 2), nullable=True),
        sa.Column("points_possible", sa.Numeric(10, 2), nullable=True),
        sa.Column("late_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("late_deduction", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("override_points", sa.Numeric(10, 2), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("override_by_id", sa.String(length=64), nullable=True),
        _tstz("override_at"),
        sa.Column("effective_points", sa.Numeric(10, 2), nullable=True),
        sa.Column("scheme_version_id", UUID, nullable=True),
        sa.Column("display_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("label", sa.String(length=40), nullable=True),
        sa.Column("percentile", sa.Numeric(4, 1), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("thresholds", JSONType, nullable=True),
        sa.Column("breakdown", JSONType, nullable=True),
        _tstz("released_at"),
        _ts("computed_at"),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        _fk("submissions", "course_id", "courses", "RESTRICT"),
        _fk("submissions", "assessment_id", "assessments", "RESTRICT"),
        _fk("submissions", "enrollment_id", "enrollments", "RESTRICT"),
        _fk("submissions", "user_id", "users", "RESTRICT"),
        _fk("submissions", "kept_attempt_id", "attempts", "RESTRICT"),
        _fk("submissions", "override_by_id", "users", "SET NULL"),
        _fk("submissions", "scheme_version_id", "grading_scheme_versions", "RESTRICT"),
        sa.CheckConstraint(_STATES, name=op.f("ck_submissions_state_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
        sa.UniqueConstraint("enrollment_id", "assessment_id", name="uq_submissions_enrollment_assessment"),
    )
    op.create_index("ix_submissions_assessment_id_state_released_at", "submissions",
                    ["assessment_id", "state", "released_at"])
    op.create_index("ix_submissions_course_id_enrollment_id", "submissions", ["course_id", "enrollment_id"])
    op.create_index("ix_submissions_kept_attempt_id", "submissions", ["kept_attempt_id"])

    op.create_table(
        "attempt_grades",
        sa.Column("attempt_id", UUID, nullable=False),
        sa.Column("scheme_version_id", UUID, nullable=True),
        sa.Column("display_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("label", sa.String(length=40), nullable=True),
        sa.Column("percentile", sa.Numeric(4, 1), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("thresholds", JSONType, nullable=True),
        sa.Column("sections", JSONType, nullable=True),
        _ts("computed_at"),
        _fk("attempt_grades", "attempt_id", "attempts", "RESTRICT"),
        _fk("attempt_grades", "scheme_version_id", "grading_scheme_versions", "RESTRICT"),
        sa.PrimaryKeyConstraint("attempt_id", name=op.f("pk_attempt_grades")),
    )

    op.create_table(
        "grade_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("submission_id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("event", sa.String(length=24), nullable=False),
        sa.Column("attempt_id", UUID, nullable=True),
        sa.Column("old", JSONType, nullable=True),
        sa.Column("new", JSONType, nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        _ts("created_at"),
        _fk("grade_events", "submission_id", "submissions", "RESTRICT"),
        _fk("grade_events", "course_id", "courses", "RESTRICT"),
        _fk("grade_events", "actor_id", "users", "SET NULL"),
        _fk("grade_events", "attempt_id", "attempts", "RESTRICT"),
        sa.CheckConstraint(_EVENTS, name=op.f("ck_grade_events_event_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grade_events")),
    )
    op.create_index("ix_grade_events_submission_id_created_at", "grade_events", ["submission_id", "created_at"])

    op.create_table(
        "course_grades",
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("current_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("final_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("released_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("display_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("label", sa.String(length=40), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("warnings", JSONType, nullable=True),
        _ts("computed_at"),
        _fk("course_grades", "enrollment_id", "enrollments", "RESTRICT"),
        _fk("course_grades", "course_id", "courses", "RESTRICT"),
        sa.PrimaryKeyConstraint("enrollment_id", name=op.f("pk_course_grades")),
    )
    op.create_index("ix_course_grades_course_id", "course_grades", ["course_id"])

    _backfill_submissions()
    if op.get_bind().dialect.name == "postgresql":
        op.execute(_GUARD_FN)
        for name, table, when, col in _GUARD_TRIGGERS:
            op.execute(f"CREATE TRIGGER {name} {when} ON {table} FOR EACH ROW "
                       f"EXECUTE FUNCTION lms_grading_immutable('{col}')")


def _backfill_submissions() -> None:
    """S2: one placeholder submission per (enrollment, assessment) with counted attempts (non-preview,
    graded / needs_review) that existed before this migration. `computed_at = _NEVER_COMPUTED` marks them stale:
    the gradebook counts them and the next regrade computes them. Portable INSERT ... SELECT ... ON CONFLICT DO
    NOTHING (the `WHERE true` keeps SQLite's parser from reading ON CONFLICT as a join constraint)."""
    bind = op.get_bind()
    new_id = "gen_random_uuid()" if bind.dialect.name == "postgresql" else "lower(hex(randomblob(16)))"
    stmt = sa.text(
        "INSERT INTO submissions (id, created_at, updated_at, course_id, assessment_id, enrollment_id, user_id, "
        "state, kept_policy, attempts_counted, late_seconds, late_deduction, computed_at, version) "
        f"SELECT {new_id}, :now, :now, x.course_id, x.assessment_id, x.enrollment_id, x.user_id, 'graded', "
        "x.kept_policy, 0, 0, 0, :never, 1 FROM ("
        "SELECT DISTINCT a.course_id, a.assessment_id, a.enrollment_id, a.user_id, s.score_policy AS kept_policy "
        "FROM attempts a JOIN assessments s ON s.id = a.assessment_id "
        "WHERE a.is_preview = :no AND a.status IN ('graded', 'needs_review')"
        ") x WHERE true ON CONFLICT (enrollment_id, assessment_id) DO NOTHING"
    ).bindparams(
        sa.bindparam("now", datetime.now(timezone.utc), type_=sa.DateTime(timezone=True)),
        sa.bindparam("never", _NEVER_COMPUTED, type_=sa.DateTime(timezone=True)),
        sa.bindparam("no", False, type_=sa.Boolean()),
    )
    bind.execute(stmt)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for name, table, _when, _col in _GUARD_TRIGGERS:
            op.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
        op.execute("DROP FUNCTION IF EXISTS lms_grading_immutable()")
    for table in ("course_grades", "grade_events", "attempt_grades", "submissions"):
        op.drop_table(table)
    with op.batch_alter_table("assessments") as b:
        b.drop_constraint(op.f("fk_assessments_grade_category_id_grade_categories"), type_="foreignkey")
        b.drop_constraint("fk_assessments_grading_scheme_version_id", type_="foreignkey")
        b.drop_constraint(op.f("ck_assessments_grade_release_valid"), type_="check")
        for col in ("grading_changed_at", "omit_from_total", "grade_release", "due_at", "grade_category_id",
                    "grading_scheme_version_id"):
            b.drop_column(col)
    with op.batch_alter_table("courses") as b:
        b.drop_constraint(op.f("fk_courses_grading_scheme_version_id_grading_scheme_versions"), type_="foreignkey")
        b.drop_constraint(op.f("ck_courses_grading_total_mode_valid"), type_="check")
        for col in ("late_policy_changed_at", "grading_changed_at", "late_policy", "grading_scheme_version_id",
                    "grading_total_mode"):
            b.drop_column(col)
    op.drop_table("grade_categories")
    with op.batch_alter_table("grading_schemes") as b:
        b.drop_constraint("fk_grading_schemes_current_version_id", type_="foreignkey")
    op.drop_table("grading_scheme_versions")
    op.drop_table("grading_schemes")
