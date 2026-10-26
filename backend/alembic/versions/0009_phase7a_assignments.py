"""phase 7a (S1): assignments, hand-ins, overrides, rubrics, accommodations; submissions keyed by assignment

Revision ID: 0009_phase7a_assignments
Revises: 0008_phase6_organizations
Create Date: 2026-10-26

PHASE_7A_DESIGN section 2. Schema first (new tables, the new nullable submissions columns, assessments.access_code_hash),
then the data steps of 2.3: (2) one quiz assignment per assessment, soft-deleted included, with the fixed id
uuid5(ASSIGN_NS, "assignment:assessment:<assessment_id>") and the mirrored columns of 3.2; (3) every submission gets
its assessment's assignment; then (4) assignment_id NOT NULL, assessment_id nullable (P7-1: kept as a denormalized
shortcut), the new unique/check/index, and (5) grade_events.event_valid gains 'manual_grade'. Steps are idempotent
(insert where missing, update where NULL). The same steps 2-3 live in app/lms/assignments/bootstrap.py for SQLite
dev/tests; a PostgreSQL test asserts both paths yield the same rows. The id formula is copied on purpose (a
migration must not import app code that can change later); keep it identical to app/lms/assignments/ids.py.

Downgrade is lossless while every submission is a quiz grade. One-way cases (refused with a clear error): a
submission without an assessment (a none/text/file grade) or a 'manual_grade' grade event exists.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_phase7a_assignments"
down_revision: Union[str, None] = "0008_phase6_organizations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
_FALSE = sa.text("false")
WINDOW = "available_from IS NULL OR available_until IS NULL OR available_until > available_from"
OLD_EVENTS = ("override", "override_cleared", "excused", "unexcused", "released", "unreleased", "regraded",
              "attempt_voided")
NEW_EVENTS = OLD_EVENTS + ("manual_grade",)

# Copy of app/lms/assignments/ids.py (ASSIGN_NS, assignment_id_for)
ASSIGN_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/assignments")


def _assignment_id_for(assessment_id) -> uuid.UUID:
    return uuid.uuid5(ASSIGN_NS, f"assignment:assessment:{uuid.UUID(str(assessment_id))}")


def _events_check(events) -> str:
    return "event IN (" + ",".join(f"'{e}'" for e in events) + ")"


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _fk(table: str, col: str, ref: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"), ondelete=ondelete)


def _ck(table: str, name: str, sql: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=op.f(f"ck_{table}_{name}"))


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.String(length=64), nullable=True)


# lightweight table handles for the data steps (typed, so uuid/json/bool bind correctly on PG and SQLite)
_TS = sa.DateTime(timezone=True)
_assessments = sa.table(
    "assessments", sa.column("id", UUID), sa.column("course_id", UUID), sa.column("title", sa.JSON),
    sa.column("description", sa.JSON), sa.column("due_at", _TS), sa.column("available_from", _TS),
    sa.column("available_until", _TS), sa.column("grade_category_id", UUID),
    sa.column("grading_scheme_version_id", UUID), sa.column("grade_release", sa.String),
    sa.column("omit_from_total", sa.Boolean), sa.column("status", sa.String), sa.column("published_version_id", UUID),
    sa.column("published_at", _TS), sa.column("position", sa.Integer), sa.column("created_by_id", sa.String),
    sa.column("deleted_at", _TS), sa.column("deleted_by_id", sa.String),
)
_versions = sa.table("assessment_versions", sa.column("id", UUID), sa.column("points_possible", sa.Numeric(10, 2)))
_assignments = sa.table(
    "assignments", sa.column("id", UUID), sa.column("course_id", UUID), sa.column("kind", sa.String),
    sa.column("assessment_id", UUID), sa.column("title", sa.JSON), sa.column("description", sa.JSON),
    sa.column("points_possible", sa.Numeric(10, 2)), sa.column("due_at", _TS), sa.column("available_from", _TS),
    sa.column("available_until", _TS), sa.column("category_id", UUID), sa.column("grading_scheme_version_id", UUID),
    sa.column("grade_release", sa.String), sa.column("omit_from_total", sa.Boolean), sa.column("published", sa.Boolean),
    sa.column("published_at", _TS), sa.column("position", sa.Integer), sa.column("created_by_id", sa.String),
    sa.column("deleted_by_id", sa.String), sa.column("created_at", _TS), sa.column("updated_at", _TS),
    sa.column("deleted_at", _TS),
)
_submissions = sa.table("submissions", sa.column("assessment_id", UUID), sa.column("assignment_id", UUID))


def upgrade() -> None:
    _schema()
    _data(op.get_bind(), datetime.now(timezone.utc))
    # step 4: assignment_id is the identity; assessment_id stays as the quiz shortcut (P7-1)
    with op.batch_alter_table("submissions") as b:
        b.alter_column("assignment_id", existing_type=UUID, nullable=False)
        b.alter_column("assessment_id", existing_type=UUID, nullable=True)
        b.create_unique_constraint("uq_submissions_enrollment_assignment_id", ["enrollment_id", "assignment_id"])
        b.create_check_constraint(op.f("ck_submissions_quiz_link_valid"),
                                  "kept_attempt_id IS NULL OR assessment_id IS NOT NULL")
        b.create_index("ix_submissions_assignment_id_state_released_at", ["assignment_id", "state", "released_at"])
    # step 5: grade events gain manual_grade (the PG append-only trigger is untouched: inserts only)
    with op.batch_alter_table("grade_events") as b:
        b.drop_constraint(op.f("ck_grade_events_event_valid"), type_="check")
        b.create_check_constraint(op.f("ck_grade_events_event_valid"), _events_check(NEW_EVENTS))


def _schema() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"), _ts("deleted_at", True),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("assessment_id", UUID, nullable=True),
        sa.Column("title", JSONType, nullable=False),
        sa.Column("description", JSONType, nullable=True),
        sa.Column("points_possible", sa.Numeric(10, 2), nullable=True),
        _ts("due_at", True), _ts("available_from", True), _ts("available_until", True),
        sa.Column("category_id", UUID, nullable=True),
        sa.Column("grading_scheme_version_id", UUID, nullable=True),
        sa.Column("grade_release", sa.String(length=8), server_default="manual", nullable=False),
        sa.Column("omit_from_total", sa.Boolean(), server_default=_FALSE, nullable=False),
        sa.Column("published", sa.Boolean(), server_default=_FALSE, nullable=False),
        _ts("published_at", True),
        sa.Column("position", sa.Integer(), nullable=False),
        _user("created_by_id"),
        _user("deleted_by_id"),
        _fk("assignments", "course_id", "courses", "RESTRICT"),
        _fk("assignments", "assessment_id", "assessments", "RESTRICT"),
        _fk("assignments", "category_id", "grade_categories", "SET NULL"),
        sa.ForeignKeyConstraint(["grading_scheme_version_id"], ["grading_scheme_versions.id"],  # <= 63 chars (PG)
                                name="fk_assignments_grading_scheme_version_id", ondelete="RESTRICT"),
        _fk("assignments", "created_by_id", "users", "SET NULL"),
        _fk("assignments", "deleted_by_id", "users", "SET NULL"),
        _ck("assignments", "kind_valid", "kind IN ('none','text','file','quiz')"),
        _ck("assignments", "quiz_link_valid", "(kind = 'quiz') = (assessment_id IS NOT NULL)"),
        _ck("assignments", "points_possible_valid",
            "points_possible IS NULL OR (points_possible >= 0 AND points_possible <= 10000)"),
        _ck("assignments", "window_valid", WINDOW),
        _ck("assignments", "grade_release_valid", "grade_release IN ('auto','manual')"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
        sa.UniqueConstraint("assessment_id", name="uq_assignments_assessment_id"),
    )
    op.create_index("ix_assignments_course_id_deleted_at_position_id", "assignments",
                    ["course_id", "deleted_at", "position", "id"])
    op.create_index("ix_assignments_course_id_published_due_at", "assignments", ["course_id", "published", "due_at"])

    op.create_table(
        "assignment_submissions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("submission_id", UUID, nullable=False),
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=4), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("asset_id", UUID, nullable=True),
        _ts("submitted_at"),
        sa.Column("late_seconds", sa.Integer(), server_default="0", nullable=False),
        _fk("assignment_submissions", "submission_id", "submissions", "RESTRICT"),
        _fk("assignment_submissions", "assignment_id", "assignments", "RESTRICT"),
        _fk("assignment_submissions", "enrollment_id", "enrollments", "RESTRICT"),
        _fk("assignment_submissions", "user_id", "users", "RESTRICT"),
        _fk("assignment_submissions", "asset_id", "assets", "RESTRICT"),
        _ck("assignment_submissions", "kind_valid", "kind IN ('text','file')"),
        _ck("assignment_submissions", "text_body_valid", "(kind = 'text') = (body_text IS NOT NULL)"),
        _ck("assignment_submissions", "file_asset_valid", "(kind = 'file') = (asset_id IS NOT NULL)"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_submissions")),
        sa.UniqueConstraint("submission_id", "attempt_no", name="uq_assignment_submissions_submission_id_attempt_no"),
    )
    op.create_index("ix_assignment_submissions_assignment_enrollment_attempt_no", "assignment_submissions",
                    ["assignment_id", "enrollment_id", "attempt_no"])

    op.create_table(
        "assignment_overrides",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        _ts("due_at", True), _ts("available_from", True), _ts("available_until", True),
        sa.Column("extra_time_percent", sa.Integer(), nullable=True),
        sa.Column("extra_time_s", sa.Integer(), nullable=True),
        sa.Column("extra_attempts", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        _user("set_by_id"),
        _fk("assignment_overrides", "assignment_id", "assignments", "RESTRICT"),
        _fk("assignment_overrides", "enrollment_id", "enrollments", "RESTRICT"),
        _fk("assignment_overrides", "course_id", "courses", "RESTRICT"),
        _fk("assignment_overrides", "set_by_id", "users", "SET NULL"),
        _ck("assignment_overrides", "window_valid", WINDOW),
        _ck("assignment_overrides", "extra_time_percent_valid",
            "extra_time_percent IS NULL OR (extra_time_percent >= 0 AND extra_time_percent <= 300)"),
        _ck("assignment_overrides", "extra_time_s_valid",
            "extra_time_s IS NULL OR (extra_time_s >= 0 AND extra_time_s <= 86400)"),
        _ck("assignment_overrides", "extra_attempts_valid",
            "extra_attempts IS NULL OR (extra_attempts >= 0 AND extra_attempts <= 100)"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_overrides")),
        sa.UniqueConstraint("assignment_id", "enrollment_id", name="uq_assignment_overrides_assignment_id_enrollment_id"),
    )
    op.create_index("ix_assignment_overrides_enrollment_id", "assignment_overrides", ["enrollment_id"])

    op.create_table(
        "assignment_rubric_criteria",
        sa.Column("id", UUID, nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", JSONType, nullable=False),
        sa.Column("description", JSONType, nullable=True),
        sa.Column("points", sa.Numeric(8, 2), nullable=False),
        _ts("deleted_at", True),
        _fk("assignment_rubric_criteria", "assignment_id", "assignments", "RESTRICT"),
        _ck("assignment_rubric_criteria", "points_valid", "points >= 0 AND points <= 1000"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_rubric_criteria")),
    )
    op.create_index("ix_assignment_rubric_criteria_assignment_id_deleted_at_position", "assignment_rubric_criteria",
                    ["assignment_id", "deleted_at", "position"])

    op.create_table(
        "submission_rubric_scores",
        sa.Column("submission_id", UUID, nullable=False),
        sa.Column("criterion_id", UUID, nullable=False),
        sa.Column("points", sa.Numeric(8, 2), nullable=False),
        sa.Column("comment", sa.String(length=1000), nullable=True),
        _fk("submission_rubric_scores", "submission_id", "submissions", "RESTRICT"),
        sa.ForeignKeyConstraint(["criterion_id"], ["assignment_rubric_criteria.id"],  # <= 63 chars (PG)
                                name="fk_submission_rubric_scores_criterion_id", ondelete="RESTRICT"),
        _ck("submission_rubric_scores", "points_valid", "points >= 0"),
        sa.PrimaryKeyConstraint("submission_id", "criterion_id", name=op.f("pk_submission_rubric_scores")),
    )

    op.create_table(
        "enrollment_accommodations",
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("course_id", UUID, nullable=False),
        sa.Column("extra_time_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("extra_time_s", sa.Integer(), server_default="0", nullable=False),
        sa.Column("extra_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        _user("set_by_id"),
        _ts("created_at"), _ts("updated_at"),
        _fk("enrollment_accommodations", "enrollment_id", "enrollments", "RESTRICT"),
        _fk("enrollment_accommodations", "course_id", "courses", "RESTRICT"),
        _fk("enrollment_accommodations", "set_by_id", "users", "SET NULL"),
        _ck("enrollment_accommodations", "extra_time_percent_valid",
            "extra_time_percent >= 0 AND extra_time_percent <= 300"),
        _ck("enrollment_accommodations", "extra_time_s_valid", "extra_time_s >= 0 AND extra_time_s <= 86400"),
        _ck("enrollment_accommodations", "extra_attempts_valid", "extra_attempts >= 0 AND extra_attempts <= 100"),
        sa.PrimaryKeyConstraint("enrollment_id", name=op.f("pk_enrollment_accommodations")),
    )
    op.create_index("ix_enrollment_accommodations_course_id", "enrollment_accommodations", ["course_id"])

    with op.batch_alter_table("assessments") as b:
        b.add_column(sa.Column("access_code_hash", sa.String(length=100), nullable=True))

    # step 1: the new submissions columns (assignment_id nullable until the data steps ran)
    with op.batch_alter_table("submissions") as b:
        b.add_column(sa.Column("assignment_id", UUID, nullable=True))
        b.add_column(sa.Column("feedback_text", sa.Text(), nullable=True))
        b.add_column(sa.Column("feedback_asset_id", UUID, nullable=True))
        b.add_column(sa.Column("graded_item_id", UUID, nullable=True))
        b.add_column(sa.Column("graded_by_id", sa.String(length=64), nullable=True))
        b.add_column(_ts("graded_at", True))
        b.create_foreign_key(op.f("fk_submissions_assignment_id_assignments"), "assignments",
                             ["assignment_id"], ["id"], ondelete="RESTRICT")
        b.create_foreign_key(op.f("fk_submissions_feedback_asset_id_assets"), "assets",
                             ["feedback_asset_id"], ["id"], ondelete="SET NULL")
        b.create_foreign_key("fk_submissions_graded_item_id_assignment_submissions", "assignment_submissions",
                             ["graded_item_id"], ["id"], ondelete="SET NULL")
        b.create_foreign_key(op.f("fk_submissions_graded_by_id_users"), "users",
                             ["graded_by_id"], ["id"], ondelete="SET NULL")


# ------------------------------------------------------------------------------------------------- data steps

def _data(conn, now) -> None:
    a, v, asg = _assessments, _versions, _assignments
    # step 2: one quiz assignment per assessment (soft-deleted included), fixed id, mirrored columns (3.2)
    have = {r[0] for r in conn.execute(sa.select(asg.c.assessment_id).where(asg.c.assessment_id.is_not(None)))}
    rows = conn.execute(
        sa.select(a, v.c.points_possible.label("pv_points"))
        .select_from(a.outerjoin(v, v.c.id == a.c.published_version_id)).order_by(a.c.id)).all()
    new = [dict(
        id=_assignment_id_for(r.id), course_id=r.course_id, kind="quiz", assessment_id=r.id,
        title=r.title, description=r.description, points_possible=r.pv_points,
        due_at=r.due_at, available_from=r.available_from, available_until=r.available_until,
        category_id=r.grade_category_id, grading_scheme_version_id=r.grading_scheme_version_id,
        grade_release=r.grade_release or "auto", omit_from_total=bool(r.omit_from_total),
        published=r.status == "published" and r.published_version_id is not None, published_at=r.published_at,
        position=r.position, created_by_id=r.created_by_id, deleted_by_id=r.deleted_by_id,
        created_at=now, updated_at=now, deleted_at=r.deleted_at,
    ) for r in rows if r.id not in have]
    if new:
        conn.execute(asg.insert(), new)
    # step 3: submissions move to their assessment's assignment (N = number of assessments with grades)
    s = _submissions
    asids = [r[0] for r in conn.execute(sa.select(s.c.assessment_id).where(
        s.c.assignment_id.is_(None), s.c.assessment_id.is_not(None)).distinct())]
    if asids:
        conn.execute(
            s.update().where(s.c.assessment_id == sa.bindparam("asid"), s.c.assignment_id.is_(None))
            .values(assignment_id=sa.bindparam("aid")),
            [{"asid": x, "aid": _assignment_id_for(x)} for x in asids])
    left = conn.execute(sa.text("SELECT count(*) FROM submissions WHERE assignment_id IS NULL")).scalar()
    if left:
        raise RuntimeError(f"0009: {left} submission(s) without an assessment cannot get an assignment")
    log.info("0009: %s quiz assignment(s) created, %s assessment(s) with submissions moved", len(new), len(asids))


def downgrade() -> None:
    conn = op.get_bind()
    orphans = conn.execute(sa.text("SELECT count(*) FROM submissions WHERE assessment_id IS NULL")).scalar()
    if orphans:
        raise RuntimeError(f"0009 downgrade refused: {orphans} grade(s) of none/text/file assignments exist "
                           "(submissions.assessment_id IS NULL); this direction would lose them")
    manual = conn.execute(sa.text("SELECT count(*) FROM grade_events WHERE event = 'manual_grade'")).scalar()
    if manual:
        raise RuntimeError(f"0009 downgrade refused: {manual} 'manual_grade' grade event(s) exist (append-only)")
    with op.batch_alter_table("grade_events") as b:
        b.drop_constraint(op.f("ck_grade_events_event_valid"), type_="check")
        b.create_check_constraint(op.f("ck_grade_events_event_valid"), _events_check(OLD_EVENTS))
    op.drop_table("submission_rubric_scores")
    op.drop_index("ix_assignment_rubric_criteria_assignment_id_deleted_at_position",
                  table_name="assignment_rubric_criteria")
    op.drop_table("assignment_rubric_criteria")
    op.drop_index("ix_assignment_overrides_enrollment_id", table_name="assignment_overrides")
    op.drop_table("assignment_overrides")
    op.drop_index("ix_enrollment_accommodations_course_id", table_name="enrollment_accommodations")
    op.drop_table("enrollment_accommodations")
    with op.batch_alter_table("submissions") as b:
        b.drop_index("ix_submissions_assignment_id_state_released_at")
        b.drop_constraint(op.f("ck_submissions_quiz_link_valid"), type_="check")
        b.drop_constraint("uq_submissions_enrollment_assignment_id", type_="unique")
        b.drop_constraint(op.f("fk_submissions_graded_by_id_users"), type_="foreignkey")
        b.drop_constraint("fk_submissions_graded_item_id_assignment_submissions", type_="foreignkey")
        b.drop_constraint(op.f("fk_submissions_feedback_asset_id_assets"), type_="foreignkey")
        b.drop_constraint(op.f("fk_submissions_assignment_id_assignments"), type_="foreignkey")
        for col in ("graded_at", "graded_by_id", "graded_item_id", "feedback_asset_id", "feedback_text",
                    "assignment_id"):
            b.drop_column(col)
        b.alter_column("assessment_id", existing_type=UUID, nullable=False)
    op.drop_index("ix_assignment_submissions_assignment_enrollment_attempt_no",
                  table_name="assignment_submissions")
    op.drop_table("assignment_submissions")
    op.drop_index("ix_assignments_course_id_published_due_at", table_name="assignments")
    op.drop_index("ix_assignments_course_id_deleted_at_position_id", table_name="assignments")
    op.drop_table("assignments")
    with op.batch_alter_table("assessments") as b:
        b.drop_column("access_code_hash")
