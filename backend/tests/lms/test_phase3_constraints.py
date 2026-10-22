"""DB-level constraints of the Phase 3 schema (design section 2)."""
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.lms.assessments.models import (
    Assessment, AssessmentItem, AssessmentVersion, ImmutableAssessmentVersionError,
)
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.core.models import utcnow
from tests.lms.factories import (
    enroll, make_assessment, make_assessment_version, make_attempt, make_attempt_section, make_bank, make_course,
    make_item, make_passage, make_question, make_section, make_user,
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
    bank = make_bank(db, course, teacher)
    q = make_question(db, bank, teacher)
    a = make_assessment(db, course, teacher, sections=[{"key": "s1"}])
    v = make_assessment_version(db, a, teacher)
    student = make_user(db)
    enroll(db, course, student)
    return teacher, course, bank, q, a, v, student


@pytest.mark.parametrize("overrides", [
    {"preset": "x"}, {"status": "x"}, {"time_limit_s": 59}, {"time_limit_s": 86401}, {"allowed_attempts": 0},
    {"allowed_attempts": 101}, {"score_policy": "x"}, {"navigation": "x"}, {"results_policy": "x"},
])
def test_assessment_checks(db, ctx, overrides):
    teacher, course = ctx[0], ctx[1]
    with pytest.raises(IntegrityError):
        make_assessment(db, course, teacher, **overrides)


def test_assessment_allowed_attempts_unlimited_and_window(db, ctx):
    teacher, course = ctx[0], ctx[1]
    make_assessment(db, course, teacher, allowed_attempts=-1, time_limit_s=60)
    now = utcnow()
    with pytest.raises(IntegrityError):
        make_assessment(db, course, teacher, available_from=now, available_until=now)


def test_item_kind_checks(db, ctx):
    teacher, course, bank, q, a, v, _ = ctx
    section = make_section(db, a)
    with pytest.raises(IntegrityError):
        make_item(db, a, section, kind="question")  # no question_id
    db.rollback()
    with pytest.raises(IntegrityError):
        make_item(db, a, section, kind="passage")  # no passage_id
    db.rollback()
    with pytest.raises(IntegrityError):
        make_item(db, a, section, kind="pick")  # no bank / count
    db.rollback()
    with pytest.raises(IntegrityError):
        make_item(db, a, section, question=q, points=Decimal("1001"))
    db.rollback()
    with pytest.raises(IntegrityError):
        make_item(db, a, section, kind="pick", pick_bank_id=bank.id, pick_count=201)
    db.rollback()
    make_item(db, a, section, kind="pick", pick_bank_id=bank.id, pick_count=5)


def test_passage_item_cannot_have_parent_and_children_can(db, ctx):
    teacher, _, bank, q, a, _, _ = ctx
    section = make_section(db, a)
    p = make_passage(db, bank, teacher)
    head = make_item(db, a, section, passage=p)
    make_item(db, a, section, question=q, parent=head, position=1)
    with pytest.raises(IntegrityError):
        make_item(db, a, section, passage=p, parent=head)


def test_question_unique_per_assessment(db, ctx):
    _, _, _, q, a, _, _ = ctx
    section = make_section(db, a)
    make_item(db, a, section, question=q)
    with pytest.raises(IntegrityError):
        make_item(db, a, section, question=q)
    db.rollback()
    # pick items have no question_id, so any number may coexist
    bank_id = q.bank_id
    make_item(db, a, section, kind="pick", pick_bank_id=bank_id, pick_count=1)
    make_item(db, a, section, kind="pick", pick_bank_id=bank_id, pick_count=1)


def test_version_unique_number_and_preview_rows(db, ctx):
    teacher, _, _, _, a, v, _ = ctx
    assert v.version_no == 1
    dup = AssessmentVersion(
        assessment_id=a.id, kind="published", version_no=1, snapshot={}, content_hash="h", draft_rev=1,
        item_count=0, points_possible=Decimal("0"),
    )
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # preview rows have NULL version_no; several may coexist
    make_assessment_version(db, a, teacher, kind="preview")
    make_assessment_version(db, a, teacher, kind="preview")
    db.add(AssessmentVersion(assessment_id=a.id, kind="bogus", snapshot={}, content_hash="h", draft_rev=1,
                             item_count=0, points_possible=Decimal("0")))
    with pytest.raises(IntegrityError):
        db.commit()


def test_versions_are_immutable(db, ctx):
    v = ctx[5]
    v.item_count = 9
    with pytest.raises(ImmutableAssessmentVersionError):
        db.commit()
    db.rollback()
    db.delete(db.get(AssessmentVersion, v.id))
    with pytest.raises(ImmutableAssessmentVersionError):
        db.commit()


def test_one_open_real_attempt_per_user_and_assessment(db, ctx):
    teacher, course, _, _, a, v, student = ctx
    first = make_attempt(db, a, v, student)
    with pytest.raises(IntegrityError):
        make_attempt(db, a, v, student, attempt_no=2)
    db.rollback()
    first.status = "graded"
    db.commit()
    make_attempt(db, a, v, student, attempt_no=2)  # the previous one is closed
    other = make_user(db)
    enroll(db, course, other)
    make_attempt(db, a, v, other)  # another user is independent


def test_one_open_preview_attempt_and_previews_do_not_block_real(db, ctx):
    teacher, _, _, _, a, v, student = ctx
    make_attempt(db, a, v, teacher, is_preview=True)
    with pytest.raises(IntegrityError):
        make_attempt(db, a, v, teacher, is_preview=True)
    db.rollback()
    # a real attempt by the same user (partial indexes are separate) is not blocked by the preview
    make_attempt(db, a, v, teacher)
    make_attempt(db, a, v, student)


def test_attempt_number_unique_and_nullable_for_previews(db, ctx):
    teacher, _, _, _, a, v, student = ctx
    done = make_attempt(db, a, v, student, status="graded")
    assert done.attempt_no == 1
    with pytest.raises(IntegrityError):
        make_attempt(db, a, v, student, status="graded")  # attempt_no 1 again
    db.rollback()
    make_attempt(db, a, v, teacher, is_preview=True, status="void")
    make_attempt(db, a, v, teacher, is_preview=True, status="void")  # NULL attempt_no never collides


@pytest.mark.parametrize("overrides", [{"status": "x"}, {"language": "de"}, {"submit_reason": "x"}])
def test_attempt_checks(db, ctx, overrides):
    _, _, _, _, a, v, student = ctx
    with pytest.raises(IntegrityError):
        make_attempt(db, a, v, student, **overrides)


def test_attempt_items_composite_pk_and_checks(db, ctx):
    teacher, _, bank, q, a, v, student = ctx
    qv = q.current_version_id
    att = make_attempt(db, a, v, student)
    db.add(AttemptItem(attempt_id=att.id, position=1, section_pos=1, slot=1, question_version_id=qv))
    db.commit()
    db.add(AttemptItem(attempt_id=att.id, position=1, section_pos=1, slot=2, question_version_id=qv))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(AttemptItem(attempt_id=att.id, position=2, section_pos=1, slot=2, question_version_id=qv,
                       correctness="bogus"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    row = db.get(AttemptItem, (att.id, 1))
    assert row.flagged is False and row.response is None and row.client_ts is None
    make_attempt_section(db, att, 1)
    with pytest.raises(IntegrityError):
        make_attempt_section(db, att, 1)
    db.rollback()
    db.add(AttemptSection(attempt_id=att.id, section_pos=2, close_reason="bogus"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_restrict_deletes(db, ctx):
    """No cascades: attempts, versions and builder rows cannot be removed from under their children."""
    from sqlalchemy import delete

    if db.get_bind().dialect.name == "sqlite":
        pytest.skip("SQLite does not enforce foreign keys; covered by the Postgres run")
    _, _, _, q, a, v, student = ctx
    from app.lms.content.models import QuestionVersion

    att = make_attempt(db, a, v, student, items=1, question_version=db.get(QuestionVersion, q.current_version_id))
    for model, pk in ((Attempt, att.id), (AssessmentVersion, v.id), (Assessment, a.id)):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(delete(model.__table__).where(model.__table__.c.id == pk))
        db.rollback()
    assert db.get(Attempt, att.id) is not None
