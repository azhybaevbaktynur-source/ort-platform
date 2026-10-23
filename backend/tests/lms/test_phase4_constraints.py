"""DB-level constraints of the Phase 4 schema (PHASE_4_DESIGN section 2)."""
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.lms.core.models import utcnow
from app.lms.grading import seeds
from app.lms.grading.models import (
    AppendOnlyGradeEventError, AttemptGrade, CourseGrade, GradeEvent, GradingScheme, GradingSchemeVersion,
)
from tests.lms.factories import (
    enroll, make_assessment, make_assessment_version, make_attempt, make_category, make_course, make_scheme,
    make_submission, make_user,
)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def ctx(db):
    teacher = make_user(db, teacher_status="approved")
    course = make_course(db, teacher)
    a = make_assessment(db, course, teacher, sections=[{"key": "s1"}])
    v = make_assessment_version(db, a, teacher)
    student = make_user(db)
    enr = enroll(db, course, student)
    return teacher, course, a, v, student, enr


def test_scheme_type_and_key_constraints(db, ctx):
    teacher = ctx[0]
    with pytest.raises(IntegrityError):
        db.add(GradingScheme(owner_user_id=teacher.id, title={"en": "x"}, type="letters"))
        db.flush()
    db.rollback()
    with pytest.raises(IntegrityError):  # system keys are unique
        make_scheme(db, None, "percent", {}, key="ort_main")
    db.rollback()
    # NULL keys never collide
    make_scheme(db, teacher, "percent", {})
    make_scheme(db, teacher, "percent", {})


def test_version_unique_and_type_check(db, ctx):
    teacher = ctx[0]
    s = make_scheme(db, teacher, "percent", {})
    with pytest.raises(IntegrityError):
        db.add(GradingSchemeVersion(scheme_id=s.id, version_no=1, type="percent", params={}, params_hash="x"))
        db.flush()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.add(GradingSchemeVersion(scheme_id=s.id, version_no=2, type="nope", params={}, params_hash="x"))
        db.flush()
    db.rollback()


@pytest.mark.parametrize("weight", [Decimal("-1"), Decimal("100.01")])
def test_category_weight_range(db, ctx, weight):
    with pytest.raises(IntegrityError):
        make_category(db, ctx[1], weight=weight)


def test_category_weight_bounds_ok(db, ctx):
    make_category(db, ctx[1], weight=0)
    make_category(db, ctx[1], weight=100)


def test_assessment_and_course_grading_columns(db, ctx):
    teacher, course, a, *_ = ctx
    assert a.grade_release == "auto" and a.omit_from_total is False and a.grading_scheme_version_id is None
    assert course.grading_total_mode == "points" and course.late_policy is None
    with pytest.raises(IntegrityError):
        make_assessment(db, course, teacher, grade_release="later")
    db.rollback()
    course.grading_total_mode = "median"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    a = make_assessment(db, course, teacher, grading_scheme_version_id=seeds.ORT_MAIN_V1_ID, grade_release="manual")
    assert a.grading_scheme_version_id == seeds.ORT_MAIN_V1_ID


def test_submission_unique_and_state(db, ctx):
    _, _, a, _, _, enr = ctx
    make_submission(db, a, enr)
    with pytest.raises(IntegrityError):
        make_submission(db, a, enr)
    db.rollback()
    other = make_assessment(db, ctx[1], ctx[0])
    with pytest.raises(IntegrityError):
        make_submission(db, other, enr, state="done")
    db.rollback()
    for state in ("pending_review", "excused"):
        make_submission(db, make_assessment(db, ctx[1], ctx[0]), enr, state=state)


def test_attempt_grade_and_course_grade_rows(db, ctx):
    teacher, course, a, v, student, enr = ctx
    att = make_attempt(db, a, v, student, enrollment=enr)
    att_id = att.id
    db.add(AttemptGrade(attempt_id=att.id, scheme_version_id=seeds.PERCENT_V1_ID, display_value=Decimal("50"),
                        percentile=Decimal("50.0"), thresholds={}, computed_at=utcnow()))
    db.add(CourseGrade(enrollment_id=enr.id, course_id=course.id, current_percent=Decimal("99.99"),
                       warnings=[], computed_at=utcnow()))
    db.commit()
    db.expunge_all()
    with pytest.raises(IntegrityError):  # one row per attempt
        db.add(AttemptGrade(attempt_id=att_id, computed_at=utcnow()))
        db.flush()
    db.rollback()


def test_grade_events_append_only_and_checked(db, ctx):
    teacher, course, a, _, _, enr = ctx
    sub = make_submission(db, a, enr)
    ev = GradeEvent(submission_id=sub.id, course_id=course.id, actor_id=teacher.id, event="override",
                    old={"points": None}, new={"points": "1"}, reason="r")
    db.add(ev)
    db.commit()
    ev.reason = "changed"
    with pytest.raises(AppendOnlyGradeEventError):
        db.flush()
    db.rollback()
    db.delete(db.get(GradeEvent, ev.id))
    with pytest.raises(AppendOnlyGradeEventError):
        db.flush()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.add(GradeEvent(submission_id=sub.id, course_id=course.id, event="graded"))
        db.flush()
    db.rollback()


def test_partial_unique_index_exists(db):
    if db.get_bind().dialect.name != "postgresql":
        rows = db.execute(text("SELECT sql FROM sqlite_master WHERE name = 'uq_grading_schemes_key'")).scalar()
        assert "WHERE key IS NOT NULL" in rows
    else:
        rows = db.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_grading_schemes_key'")).scalar()
        assert "WHERE (key IS NOT NULL)" in rows
