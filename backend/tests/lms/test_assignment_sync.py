"""Phase 7a S1: every assessment has exactly one quiz assignment that mirrors it (PHASE_7A_DESIGN 2.3, 2.9, 3.2).

- `test_quiz_assignment_mirror_property`: after every builder/publisher operation (create, update of each mirrored
  field, publish, unpublish, re-publish, delete, restore) the mirrored columns are equal (P7-2).
- the ORT seed path (`ensure_ort_courses`, not edited) creates the quiz assignment of each seeded exam in the same
  transaction, with the deterministic id and mirrored fields; a second run adds nothing.
- `test_submission_assessment_id_matches_assignment`: quiz submissions written by the unchanged Phase 4 paths carry
  `assignment_id = assignment_id_for(assessment_id)` and `submissions.assessment_id = assignments.assessment_id`.
- the lifespan bootstrap `ensure_assignments` fills missing quiz assignments and is idempotent."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select

from app.lms.assessments.models import Assessment
from app.lms.assignments.bootstrap import ensure_assignments
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment
from app.lms.assignments.sync import mirror_mismatches
from app.lms.grading.models import GradingScheme, Submission
from app.lms.ort.seed import course_id_for, ensure_ort_courses
from tests.lms.assessment_support import add_q, bank_of, mk, publish, section
from tests.lms.content_support import world
from tests.lms.factories import enroll, grade_attempt, make_assessment, make_category, make_submission, make_user
from tests.lms.s3_support import Api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_ort_seed import insert_export


def _assignment(db, aid) -> Assignment:
    db.expire_all()
    return db.get(Assignment, assignment_id_for(aid))


def _mirrored(db, aid) -> dict:
    db.expire_all()
    a = db.get(Assessment, aid)
    return mirror_mismatches(db, a)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


async def test_quiz_assignment_mirror_property(db):
    api = Api()
    w = world(db)
    created = await mk(api, w.O, w.cid, title={"en": "Quiz one"}, description={"en": "Read first"})
    aid = uuid.UUID(created["id"])
    row = _assignment(db, aid)
    assert row is not None and (row.kind, row.assessment_id, row.course_id) == ("quiz", aid, w.course.id)
    assert row.created_by_id == w.O.id and row.published is False and row.points_possible is None
    assert _mirrored(db, aid) == {}
    assert db.scalar(select(func.count()).select_from(Assignment).where(Assignment.course_id == w.course.id)) == 1

    cat = make_category(db, w.course)
    vid = db.scalar(select(GradingScheme.current_version_id).where(
        GradingScheme.owner_user_id.is_(None), GradingScheme.type == "percent"))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    updates = [
        {"title": {"en": "Quiz renamed", "ru": "Тест"}},
        {"description": {"en": "New instructions"}},
        {"description": None},
        {"due_at": _iso(now + timedelta(days=3))},
        {"available_from": _iso(now - timedelta(days=1)), "available_until": _iso(now + timedelta(days=5))},
        {"available_until": None},
        {"grade_category_id": str(cat.id)},
        {"grading_scheme_version_id": str(vid)},
        {"grade_release": "manual"},
        {"omit_from_total": True},
        {"grade_release": "auto", "omit_from_total": False, "grade_category_id": None, "due_at": None},
    ]
    for body in updates:
        rev = db.get(Assessment, aid).draft_rev
        db.expire_all()
        r = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{aid}", json={"draft_rev": rev, **body})
        assert r.status_code == 200, (body, r.text)
        assert _mirrored(db, aid) == {}, body

    # publish -> points of the published version, published flag and time
    bank, qs = bank_of(db, w.course, w.O, 2)
    s = await section(api, w.O, w.cid, aid)
    for q in qs:
        await add_q(api, w.O, w.cid, aid, s["id"], q.id)
    r = await publish(api, w.O, w.cid, aid)
    assert r.status_code == 200, r.text
    assert _mirrored(db, aid) == {}
    row = _assignment(db, aid)
    assert row.published is True and row.published_at is not None and row.points_possible == Decimal("2")
    r = await publish(api, w.O, w.cid, aid)  # same content: the no-op republish path
    assert r.status_code == 200 and _mirrored(db, aid) == {}, r.text
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{aid}/unpublish")
    assert r.status_code == 200, r.text
    assert _mirrored(db, aid) == {} and _assignment(db, aid).published is False
    q3 = bank_of(db, w.course, w.O, 1)[1][0]
    await add_q(api, w.O, w.cid, aid, s["id"], q3.id)
    r = await publish(api, w.O, w.cid, aid)  # new version: 3 points
    assert r.status_code == 200, r.text
    assert _mirrored(db, aid) == {} and _assignment(db, aid).points_possible == Decimal("3")

    # soft delete / restore
    r = await api.call(w.O, "DELETE", f"/courses/{w.cid}/assessments/{aid}")
    assert r.status_code == 204, r.text
    row = _assignment(db, aid)
    assert _mirrored(db, aid) == {} and row.deleted_at is not None and row.deleted_by_id == w.O.id
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{aid}/restore")
    assert r.status_code == 200, r.text
    assert _mirrored(db, aid) == {} and _assignment(db, aid).deleted_at is None
    # still exactly one assignment, at the position it was created with
    rows = db.scalars(select(Assignment).where(Assignment.course_id == w.course.id)).all()
    assert [(r.id, r.position) for r in rows] == [(assignment_id_for(aid), 1)]
    # the check itself sees a write that bypasses the builder
    db.get(Assessment, aid).omit_from_total = True
    db.commit()
    assert set(_mirrored(db, aid)) == {"omit_from_total"}


async def test_new_quiz_assignments_go_to_the_end_of_the_course_order(db):
    api = Api()
    w = world(db)
    ids = [uuid.UUID((await mk(api, w.O, w.cid, title={"en": f"Q{i}"}))["id"]) for i in range(3)]
    db.expire_all()
    got = [(db.get(Assignment, assignment_id_for(a)).position) for a in ids]
    assert got == [1, 2, 3]


def test_ort_seed_creates_one_quiz_assignment_per_exam(db):
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ru", language="ru", keep_images=False)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok and rep.assessments_published == 1, rep
    cid = course_id_for("ru")
    a = db.scalars(select(Assessment).where(Assessment.course_id == cid)).one()
    rows = db.scalars(select(Assignment).where(Assignment.course_id == cid)).all()
    assert [(r.id, r.kind, r.assessment_id) for r in rows] == [(assignment_id_for(a.id), "quiz", a.id)]
    assert mirror_mismatches(db, a) == {}
    row = rows[0]
    assert row.published is True and row.points_possible == Decimal("150") and row.grade_release == "auto"
    assert row.title == a.title and row.grading_scheme_version_id == a.grading_scheme_version_id
    before = db.scalar(select(func.count()).select_from(Assignment))
    again = ensure_ort_courses(db, samples=False)
    assert again.ok, again
    assert db.scalar(select(func.count()).select_from(Assignment)) == before


def test_submission_assessment_id_matches_assignment(db):
    w = world(db)
    a = make_assessment(db, w.course, w.O)
    enr = enroll(db, w.course, make_user(db))
    sub = make_submission(db, a, enr)  # direct insert without assignment_id: the column default
    assert sub.assignment_id == assignment_id_for(a.id)
    from tests.lms.grading_support import make_world, new_attempt

    gw = make_world(db)
    att = new_attempt(db, gw)
    grade_attempt(db, att, 1)  # the unchanged Phase 4 hook (UPSERT) writes the submission
    db.expire_all()
    rows = db.execute(select(Submission.assessment_id, Submission.assignment_id, Assignment.assessment_id)
                      .join(Assignment, Assignment.id == Submission.assignment_id)).all()
    assert len(rows) == db.scalar(select(func.count()).select_from(Submission)) == 2
    for s_asid, s_aid, a_asid in rows:
        assert s_aid == assignment_id_for(s_asid) and s_asid == a_asid


def test_bootstrap_fills_missing_quiz_assignments_and_is_idempotent(db):
    w = world(db)
    a1 = make_assessment(db, w.course, w.O)
    a2 = make_assessment(db, w.course, w.O, deleted_at=datetime.now(timezone.utc), deleted_by_id=w.O.id)
    db.execute(delete(Assignment.__table__))
    db.commit()
    rep = ensure_assignments(db)
    assert not rep.errors and rep.assignments_created == 2, rep
    for a in (a1, a2):
        db.expire_all()
        a = db.get(Assessment, a.id)
        assert mirror_mismatches(db, a) == {}
        assert db.get(Assignment, assignment_id_for(a.id)).position == a.position
    again = ensure_assignments(db)
    assert not again.errors and (again.assignments_created, again.submissions_moved) == (0, 0)
