"""Phase 7a S2: assignment CRUD, order, rubric, staff and student read models, authorization matrix and isolation
(PHASE_7A_DESIGN 3.1-3.3, 4.1, 4.5)."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.authz import A, ROLE_GRANTS
from app.lms.assessments.models import Assessment
from app.lms.assignments import schemas as sch
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment, AssignmentOverride, AssignmentRubricCriterion, SubmissionRubricScore
from app.lms.assignments.sync import mirror_mismatches
from app.lms.core.models import utcnow
from app.lms.grading.models import Submission
from tests.lms.assignment_support import (  # noqa: F401
    api, clean_rate_limits, db, fresh_storage, make_assignment, published_quiz, world,
)
from tests.lms.factories import make_attempt, make_category, make_course
from tests.lms.s3_support import teacher

_C = "/courses/{}/assignments"


def path(w, a=None, tail=""):
    base = _C.format(w.cid)
    return f"{base}/{a.id if hasattr(a, 'id') else a}{tail}" if a is not None else base


# --------------------------------------------------------------------------- create

async def test_create_text_assignment_defaults(api, db):
    w = world(db)
    res = await api.call(w.O, "POST", path(w), json={"title": {"en": "Essay"}, "kind": "text", "points_possible": 20})
    assert res.status_code == 201, res.text
    b = res.json()
    assert (b["kind"], b["grade_release"], b["published"], b["points_possible"]) == ("text", "manual", False, 20.0)
    assert b["assessment_id"] is None and b["position"] == 1 and b["rubric"] == []
    assert b["counts"] == {"submitted": 0, "needs_grading": 0, "graded": 0, "released": 0}


@pytest.mark.parametrize("body,code", [
    ({"kind": "text"}, "points_possible_required"),
    ({"kind": "file", "points_possible": 5, "quiz": {"languages": ["en"]}}, "quiz_body_forbidden"),
    ({"kind": "quiz"}, "quiz_body_required"),
    ({"kind": "quiz", "quiz": {"languages": ["en"], "exam_template_id": str(uuid.uuid4())}},
     "exam_templates_not_available"),
    ({"kind": "quiz", "quiz": {"languages": ["en"], "preset": "none", "exam_template_id": str(uuid.uuid4())}},
     "preset_template_exclusive"),
    ({"kind": "quiz", "points_possible": 5, "quiz": {"languages": ["en"]}}, "quiz_field_not_editable"),
    ({"kind": "quiz", "quiz": {"languages": ["en"], "preset": "ort_main"}}, "preset_not_available"),
])
async def test_create_refusals(api, db, body, code):
    w = world(db)
    res = await api.call(w.O, "POST", path(w), json={"title": {"en": "X"}, **body})
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == code
    assert db.execute(select(Assessment)).first() is None  # nothing created


async def test_create_window_and_refs_validated(api, db):
    w = world(db)
    now = utcnow()
    res = await api.call(w.O, "POST", path(w), json={
        "title": {"en": "X"}, "kind": "text", "points_possible": 5,
        "available_from": now.isoformat(), "available_until": (now - timedelta(hours=1)).isoformat()})
    assert res.status_code == 422
    res = await api.call(w.O, "POST", path(w), json={"title": {"en": "X"}, "kind": "text", "points_possible": 5,
                                                     "category_id": str(uuid.uuid4())})
    assert res.status_code == 404 and res.json()["error"]["code"] == "category_not_found"


async def test_create_quiz_creates_assessment_and_mirrored_assignment(api, db):
    w = world(db)
    cat = make_category(db, w.course)
    due = (utcnow() + timedelta(days=3)).replace(microsecond=0)
    res = await api.call(w.O, "POST", path(w), json={
        "title": {"en": "Quiz 1"}, "kind": "quiz", "due_at": due.isoformat(), "category_id": str(cat.id),
        "omit_from_total": True, "quiz": {"languages": ["en"]}})
    assert res.status_code == 201, res.text
    b = res.json()
    x = db.get(Assessment, uuid.UUID(b["assessment_id"]))
    assert uuid.UUID(b["id"]) == assignment_id_for(x.id)
    assert x.grade_category_id == cat.id and x.omit_from_total is True and x.status == "draft"
    assert b["category_id"] == str(cat.id) and b["published"] is False and b["points_possible"] is None
    assert b["assessment"]["status"] == "draft" and b["assessment"]["has_access_code"] is False
    assert mirror_mismatches(db, x) == {}


async def test_ort_preset_needs_template(api, db):
    w = world(db)
    w.course.template_key, w.course.template_version = "ort", 1
    db.commit()
    res = await api.call(w.O, "POST", path(w), json={"title": {"ru": "ОРТ"}, "kind": "quiz",
                                                     "quiz": {"languages": ["en"], "preset": "ort_main"}})
    assert res.status_code == 201, res.text
    assert db.get(Assessment, uuid.UUID(res.json()["assessment_id"])).preset == "ort_main"


# --------------------------------------------------------------------------- update / delete / restore / order

async def test_patch_text_assignment(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O, published=False)
    res = await api.call(w.O, "PATCH", path(w, a), json={"published": True, "points_possible": 15,
                                                         "grade_release": "auto", "title": {"en": "New"}})
    assert res.status_code == 200, res.text
    b = res.json()
    assert b["published"] is True and b["published_at"] and b["points_possible"] == 15.0
    assert b["grade_release"] == "auto" and b["title"] == {"en": "New"}
    for body, code in (({"points_possible": None}, "points_possible_required"),
                       ({"title": None}, "validation_failed")):
        res = await api.call(w.O, "PATCH", path(w, a), json=body)
        assert res.status_code == 422 and res.json()["error"]["code"] == code, res.text
    now = utcnow()
    await api.call(w.O, "PATCH", path(w, a), json={"available_from": now.isoformat()})
    res = await api.call(w.O, "PATCH", path(w, a), json={"available_until": (now - timedelta(days=1)).isoformat()})
    assert res.status_code == 422


async def test_patch_quiz_delegates_to_builder(api, db):
    w = world(db)
    a = published_quiz(db, w.course, w.O)
    due = (utcnow() + timedelta(days=2)).replace(microsecond=0)
    res = await api.call(w.O, "PATCH", path(w, a), json={"due_at": due.isoformat(), "title": {"en": "Renamed"}})
    assert res.status_code == 200, res.text
    db.expire_all()
    x = db.get(Assessment, a.assessment_id)
    assert x.title == {"en": "Renamed"} and res.json()["title"] == {"en": "Renamed"}
    assert mirror_mismatches(db, x) == {}
    res = await api.call(w.O, "PATCH", path(w, a), json={"published": False})
    assert res.status_code == 409 and res.json()["error"]["code"] == "quiz_publish_via_assessment"
    res = await api.call(w.O, "PATCH", path(w, a), json={"points_possible": 3})
    assert res.status_code == 422 and res.json()["error"]["code"] == "quiz_field_not_editable"
    res = await api.call(w.O, "PATCH", path(w, a), json={"omit_from_total": True, "draft_rev": 999})
    assert res.status_code == 409 and res.json()["error"]["code"] == "draft_conflict"


async def test_patch_quiz_template_lock_passes_through(api, db):
    w = world(db)
    w.course.template_key, w.course.template_version, w.course.template_locked = "ort", 1, True
    db.commit()
    a = published_quiz(db, w.course, w.O, preset="ort_main")
    res = await api.call(w.O, "PATCH", path(w, a), json={"grading_scheme_version_id": str(uuid.uuid4())})
    assert res.status_code == 409 and res.json()["error"]["code"] == "template_locked", res.text


async def test_delete_and_restore(api, db):
    w = world(db)
    t = make_assignment(db, w.course, w.O)
    q = published_quiz(db, w.course, w.O)
    for a in (t, q):
        assert (await api.call(w.O, "DELETE", path(w, a))).status_code == 204
    assert db.get(Assessment, q.assessment_id).deleted_at is not None
    res = await api.call(w.O, "GET", path(w), params={"deleted": "true"})
    assert {i["id"] for i in res.json()["items"]} == {str(t.id), str(q.id)}
    assert (await api.call(w.O, "GET", path(w, t))).status_code == 404
    for a in (t, q):
        res = await api.call(w.O, "POST", path(w, a, "/restore"))
        assert res.status_code == 200 and res.json()["deleted_at"] is None, res.text
    res = await api.call(w.O, "POST", path(w, t, "/restore"))
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_deleted"
    db.expire_all()
    assert db.get(Assessment, q.assessment_id).deleted_at is None


async def test_order(api, db):
    w = world(db)
    a, b, c = (make_assignment(db, w.course, w.O) for _ in range(3))
    res = await api.call(w.O, "PUT", path(w) + "/order", json={"assignment_ids": [str(c.id), str(a.id)]})
    assert res.status_code == 422 and res.json()["error"]["code"] == "order_mismatch"
    res = await api.call(w.O, "PUT", path(w) + "/order", json={"assignment_ids": [str(x.id) for x in (c, a, b)]})
    assert res.status_code == 204
    res = await api.call(w.O, "GET", path(w))
    assert [i["id"] for i in res.json()["items"]] == [str(c.id), str(a.id), str(b.id)]


# --------------------------------------------------------------------------- rubric

async def test_rubric_replace_and_warnings(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O, points=Decimal("10"))
    res = await api.call(w.O, "PUT", path(w, a, "/rubric"), json={"criteria": [
        {"title": {"en": "Content"}, "points": 6}, {"title": {"en": "Style"}, "points": 3}]})
    assert res.status_code == 200, res.text
    b = res.json()
    assert [c["points"] for c in b["rubric"]] == [6.0, 3.0] and b["rubric_total"] == 9.0
    assert b["warnings"][0]["code"] == "rubric_total_mismatch"
    keep = b["rubric"][1]["id"]
    res = await api.call(w.O, "PUT", path(w, a, "/rubric"), json={"criteria": [
        {"id": keep, "title": {"en": "Style"}, "points": 4}, {"title": {"en": "Sources"}, "points": 6}]})
    b = res.json()
    assert b["rubric"][0]["id"] == keep and b["rubric"][0]["position"] == 1 and b["warnings"] == []
    assert db.execute(select(AssignmentRubricCriterion).where(
        AssignmentRubricCriterion.deleted_at.is_not(None))).scalars().all()  # "Content" soft-deleted
    res = await api.call(w.O, "PUT", path(w, a, "/rubric"), json={"criteria": [
        {"id": str(uuid.uuid4()), "title": {"en": "?"}, "points": 1}]})
    assert res.status_code == 422 and res.json()["error"]["code"] == "criterion_not_found"
    res = await api.call(w.O, "PUT", path(w, a, "/rubric"), json={"criteria": [
        {"title": {"en": str(i)}, "points": 1} for i in range(31)]})
    assert res.status_code == 422


async def test_rubric_locked_and_not_for_quiz(api, db):
    w = world(db)
    q = published_quiz(db, w.course, w.O)
    res = await api.call(w.O, "PUT", path(w, q, "/rubric"), json={"criteria": []})
    assert res.status_code == 422 and res.json()["error"]["code"] == "rubric_not_for_quiz"
    a = make_assignment(db, w.course, w.O)
    res = await api.call(w.O, "PUT", path(w, a, "/rubric"), json={"criteria": [{"title": {"en": "C"}, "points": 10}]})
    crit = res.json()["rubric"][0]["id"]
    sub = Submission(course_id=w.course.id, assignment_id=a.id, enrollment_id=w.enr.id, user_id=w.S.id,
                     state="graded", kept_policy="latest", computed_at=utcnow(), raw_points=Decimal("7"),
                     effective_points=Decimal("7"))
    db.add(sub)
    db.flush()
    db.add(SubmissionRubricScore(submission_id=sub.id, criterion_id=uuid.UUID(crit), points=Decimal("7")))
    db.commit()
    res = await api.call(w.O, "PUT", path(w, a, "/rubric"), json={"criteria": []})
    assert res.status_code == 409 and res.json()["error"]["code"] == "rubric_locked"


# --------------------------------------------------------------------------- read models

async def test_staff_list_filters_and_counts(api, db):
    w = world(db)
    t = make_assignment(db, w.course, w.O, kind="text")
    f = make_assignment(db, w.course, w.O, kind="file", published=False)
    db.add(Submission(course_id=w.course.id, assignment_id=t.id, enrollment_id=w.enr.id, user_id=w.S.id,
                      state="pending_review", kept_policy="latest", computed_at=utcnow()))
    db.commit()
    res = await api.call(w.T, "GET", path(w))  # assistant: staff shape
    items = {i["id"]: i for i in res.json()["items"]}
    assert set(items) == {str(t.id), str(f.id)}
    assert items[str(t.id)]["counts"] == {"submitted": 1, "needs_grading": 1, "graded": 0, "released": 0}
    res = await api.call(w.O, "GET", path(w), params={"kind": "file"})
    assert [i["id"] for i in res.json()["items"]] == [str(f.id)]
    res = await api.call(w.O, "GET", path(w), params={"published": "true"})
    assert [i["id"] for i in res.json()["items"]] == [str(t.id)]
    res = await api.call(w.O, "GET", path(w), params={"limit": 1})
    assert len(res.json()["items"]) == 1 and res.json()["next_cursor"]
    res2 = await api.call(w.O, "GET", path(w), params={"limit": 1, "cursor": res.json()["next_cursor"]})
    assert res2.json()["items"][0]["id"] == str(f.id)


async def test_student_list_status_and_effective_dates(api, db):
    w = world(db)
    now = utcnow()
    past = now - timedelta(days=1)
    t_missing = make_assignment(db, w.course, w.O, kind="text", due_at=past)
    t_open = make_assignment(db, w.course, w.O, kind="text", due_at=past)
    make_assignment(db, w.course, w.O, kind="file", published=False)  # hidden
    n = make_assignment(db, w.course, w.O, kind="none", due_at=past)
    q = published_quiz(db, w.course, w.O, allowed_attempts=2)
    later = now + timedelta(days=5)
    db.add(AssignmentOverride(assignment_id=t_open.id, enrollment_id=w.enr.id, course_id=w.course.id, due_at=later,
                              extra_attempts=None))
    db.add(AssignmentOverride(assignment_id=q.id, enrollment_id=w.enr.id, course_id=w.course.id, extra_attempts=1))
    db.commit()
    x = db.get(Assessment, q.assessment_id)
    from app.lms.assessments.models import AssessmentVersion

    v = db.get(AssessmentVersion, x.published_version_id)
    make_attempt(db, x, v, w.S, enrollment=w.enr)  # in progress
    res = await api.call(w.S, "GET", path(w))
    assert res.status_code == 200, res.text
    items = {i["id"]: i for i in res.json()["items"]}
    assert set(items) == {str(t_missing.id), str(t_open.id), str(n.id), str(q.id)}
    for i in items.values():
        assert set(i) <= sch.STUDENT_KEYS
    assert items[str(t_missing.id)]["status"] == "missing"
    assert items[str(t_open.id)]["status"] == "not_started"
    assert items[str(t_open.id)]["due_at"].startswith(later.isoformat()[:16])  # effective (override) due date
    assert items[str(n.id)]["status"] == "not_started"
    assert items[str(q.id)]["status"] == "in_progress" and items[str(q.id)]["attempts_left"] == 2  # 2 + 1 - 1
    # the second student sees the assignment's own dates, not S's override
    res = await api.call(w.S2, "GET", path(w))
    other = {i["id"]: i for i in res.json()["items"]}
    assert other[str(t_open.id)]["status"] == "missing" and other[str(q.id)]["attempts_left"] == 2


async def test_org_admin_gets_student_shape_without_status(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O)
    res = await api.call(w.OA, "GET", path(w))
    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert item["status"] is None and item["attempts_left"] is None and "counts" not in item
    res = await api.call(w.OA, "GET", path(w, a))
    assert res.status_code == 200 and res.json()["hand_ins"] == [] and res.json()["grade"] is None
    for method, p, body in (("POST", path(w), {"title": {"en": "x"}, "kind": "none", "points_possible": 1}),
                            ("PATCH", path(w, a), {"published": False}), ("DELETE", path(w, a), None),
                            ("PUT", path(w, a, "/rubric"), {"criteria": []})):
        res = await api.call(w.OA, method, p, json=body)
        assert res.status_code == 403, (method, p, res.text)


async def test_student_detail_hides_unreleased_grade_and_staff_fields(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O)
    sub = Submission(course_id=w.course.id, assignment_id=a.id, enrollment_id=w.enr.id, user_id=w.S.id,
                     state="graded", kept_policy="latest", computed_at=utcnow(), raw_points=Decimal("8"),
                     effective_points=Decimal("8"), points_possible=Decimal("10"), feedback_text="SECRET_FEEDBACK")
    db.add(sub)
    db.add(AssignmentOverride(assignment_id=a.id, enrollment_id=w.enr.id, course_id=w.course.id,
                              note="SECRET_NOTE"))
    db.commit()
    res = await api.call(w.S, "GET", path(w, a))
    assert res.status_code == 200, res.text
    b = res.json()
    assert set(b) <= sch.STUDENT_DETAIL_KEYS and b["grade"] is None and b["status"] == "not_started"
    assert "SECRET" not in res.text
    sub.released_at = utcnow()
    db.commit()
    res = await api.call(w.S, "GET", path(w, a, "/mine"))
    b = res.json()
    assert b["status"] == "graded" and b["grade"]["points"] == 8.0
    assert b["grade"]["feedback_text"] == "SECRET_FEEDBACK" and "SECRET_NOTE" not in res.text
    res = await api.call(w.S2, "GET", path(w, a, "/mine"))
    assert res.json()["grade"] is None and "SECRET" not in res.text


# --------------------------------------------------------------------------- authorization matrix, isolation

def test_actions_granted_as_designed():
    assert A.ASSIGNMENT_SUBMIT in ROLE_GRANTS["student"]
    assert A.ASSIGNMENT_SUBMIT not in ROLE_GRANTS["teacher"] | ROLE_GRANTS["assistant"]


@pytest.mark.parametrize("who,expected", [("O", 201), ("T", 201), ("S", 403), ("X", 404), ("OA", 403)])
async def test_create_matrix(api, db, who, expected):
    w = world(db)
    res = await api.call(getattr(w, who), "POST", path(w), json={"title": {"en": "x"}, "kind": "none",
                                                                 "points_possible": 1})
    assert res.status_code == expected, res.text


@pytest.mark.parametrize("status,who,expected", [
    ("draft", "S", 404), ("draft", "O", 200), ("concluded", "S", 200), ("concluded", "O", 200),
])
async def test_read_by_course_status(api, db, status, who, expected):
    w = world(db, status=status)
    make_assignment(db, w.course, w.O)
    res = await api.call(getattr(w, who), "GET", path(w))
    assert res.status_code in ((expected,) if expected != 404 else (403, 404)), res.text


async def test_cross_course_isolation(api, db):
    w = world(db)
    other_owner = teacher(db)
    other = make_course(db, other_owner, organization_id=w.course.organization_id)
    foreign = make_assignment(db, other, other_owner)
    mine = make_assignment(db, w.course, w.O)
    for method, tail, body in (("GET", "", None), ("PATCH", "", {"published": False}), ("DELETE", "", None),
                               ("POST", "/restore", None), ("PUT", "/rubric", {"criteria": []})):
        res = await api.call(w.O, method, path(w, foreign, tail), json=body)
        assert res.status_code in (404, 409) and res.status_code != 200, (method, tail, res.text)
        if res.status_code == 409:
            assert res.json()["error"]["code"] != "not_deleted"
    res = await api.call(w.O, "PUT", path(w) + "/order", json={"assignment_ids": [str(mine.id), str(foreign.id)]})
    assert res.status_code == 422
    # teacher of course B cannot see course A at all
    res = await api.call(other_owner, "GET", path(w))
    assert res.status_code == 404
    res = await api.call(other_owner, "GET", path(w, mine))
    assert res.status_code == 404
    db.expire_all()
    assert db.get(Assignment, foreign.id).deleted_at is None and db.get(Assignment, foreign.id).published
