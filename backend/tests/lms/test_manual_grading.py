"""Phase 7a S3: manual grading of none/text/file assignments (PHASE_7A_DESIGN 3.6), release per assignment (3.7),
the gradebook / my grades / roster page over assignments (4.3), override and excuse on manual rows, regrade of
manual rows, the override-aware `load_context`, and the student payload contract."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace as NS

from sqlalchemy import select

from app.lms.assignments import grading as mgr
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import AssignmentOverride, AssignmentRubricCriterion, SubmissionRubricScore
from app.lms.core import clock
from app.lms.grading import submissions as subs
from app.lms.grading.models import GradeEvent, Submission
from app.lms.grading.schemes import get_version_data
from app.lms.grading.seeds import PASS_FAIL_V1_ID, PERCENT_V1_ID
from tests.lms.assignment_support import fresh_storage, make_assignment, published_quiz, world  # noqa: F401
from tests.lms.factories import enroll, make_assessment, make_course, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

FEEDBACK = "SENTINEL_FEEDBACK_TEXT"


# ------------------------------------------------------------------ helpers

async def _hand_in(api, user, w, a, text="my essay"):
    r = await api.call(user, "POST", f"/courses/{w.cid}/assignments/{a.id}/submissions", json={"body_text": text})
    assert r.status_code == 201, r.text
    return r.json()


def _grade_url(w, a, enr):
    return f"/courses/{w.cid}/assignments/{a.id}/grades/{enr.id}"


async def _grade(api, user, w, a, enr, **body):
    return await api.call(user, "PUT", _grade_url(w, a, enr), json=body)


async def _gradebook(api, user, w):
    r = await api.call(user, "GET", f"/courses/{w.cid}/gradebook")
    assert r.status_code == 200, r.text
    g = r.json()
    return g, {row["user_id"]: row for row in g["rows"]}


async def _mine(api, user, w):
    r = await api.call(user, "GET", f"/courses/{w.cid}/grades/mine")
    assert r.status_code == 200, r.text
    return r


def _criteria(db, a, points):
    rows = [AssignmentRubricCriterion(assignment_id=a.id, position=i, title={"en": f"c{i}"}, points=D(str(p)))
            for i, p in enumerate(points, start=1)]
    db.add_all(rows)
    db.commit()
    return rows


def _sub(db, a, enr) -> Submission:
    db.expire_all()
    return db.execute(select(Submission).where(Submission.assignment_id == a.id,
                                               Submission.enrollment_id == enr.id)).scalar_one()


def _events(db, sub_id):
    return [e.event for e in db.execute(select(GradeEvent).where(GradeEvent.submission_id == sub_id)
                                        .order_by(GradeEvent.created_at, GradeEvent.id)).scalars()]


# ------------------------------------------------------------------ the happy path

async def test_text_assignment_grade_release_and_views(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"), grading_scheme_version_id=PERCENT_V1_ID)
    await _hand_in(api, w.S, w, a)

    # roster page: handed in, not graded
    r = await api.call(w.O, "GET", f"/courses/{w.cid}/assignments/{a.id}/submissions")
    assert r.status_code == 200, r.text
    rows = {x["user_id"]: x for x in r.json()["rows"]}
    assert set(rows) == {w.S.id, w.S2.id} and r.json()["next_cursor"] is None
    assert rows[w.S.id]["cell"]["state"] == "pending_review" and rows[w.S.id]["hand_in_count"] == 1
    assert rows[w.S.id]["resubmitted"] is False and rows[w.S.id]["late"] is False
    assert rows[w.S2.id]["cell"] is None and rows[w.S2.id]["hand_in_count"] == 0

    # my grades: `submitted`, no numbers
    item = (await _mine(api, w.S, w)).json()["items"][0]
    assert item["state"] == "submitted" and item["kind"] == "text" and item["assignment_id"] == str(a.id)
    assert item["assessment_id"] is None and item["submitted_at"] is not None and item["late"] is False
    assert "display_value" not in item and "feedback_text" not in item

    # grade (manual release by default, P7-3)
    r = await _grade(api, w.O, w, a, w.enr, points="7", feedback_text=FEEDBACK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "graded" and D(body["raw_points"]) == 7 and D(body["effective_points"]) == 7
    assert D(body["display_value"]) == D("70.00") and body["released_at"] is None
    assert body["kind"] == "text" and body["assignment_id"] == str(a.id) and body["attempts"] == []
    assert len(body["hand_ins"]) == 1 and body["hand_ins"][0]["body_text"] == "my essay"
    assert body["feedback_text"] == FEEDBACK and body["graded_by_name"] and body["graded_at"]
    assert body["events"][0]["event"] == "manual_grade"
    assert body["events"][0]["new"]["feedback"]["text"] == FEEDBACK and body["events"][0]["new"]["rubric_scores"] == []
    assert body["events"][0]["new"]["raw_points"] == "7.00" and body["events"][0]["old"]["raw_points"] is None
    sub = _sub(db, a, w.enr)
    assert sub.graded_item_id is not None and sub.graded_by_id == w.O.id and sub.kept_policy == "latest"
    assert sub.assessment_id is None and sub.version == 3  # placeholder (1) -> hand-in (2) -> grade (3)

    # submission detail (GET) equals the PUT payload shape
    got = await api.call(w.O, "GET", f"/courses/{w.cid}/submissions/{sub.id}")
    assert got.status_code == 200 and set(got.json()) == set(body)
    assert got.json()["hand_ins"] == body["hand_ins"] and got.json()["feedback_text"] == FEEDBACK

    # gradebook: one text column, the cell and the total
    gb, by_user = await _gradebook(api, w.O, w)
    (col,) = gb["assignments"]
    assert col["id"] == str(a.id) and col["kind"] == "text" and col["assessment_id"] is None
    assert D(col["points_possible"]) == 10 and col["grade_release"] == "manual" and col["score_policy"] is None
    assert col["submission_count"] == 1 and col["released_count"] == 0 and col["stale_count"] == 0
    assert D(by_user[w.S.id]["cells"][str(a.id)]["effective_points"]) == 7
    assert D(by_user[w.S.id]["total"]["current_percent"]) == D("70.00")
    assert by_user[w.S2.id]["cells"] == {} and D(by_user[w.S2.id]["total"]["final_percent"]) == D("0.00")

    # the student: pending until release, feedback never leaks before
    r = await _mine(api, w.S, w)
    assert r.json()["items"][0]["state"] == "pending" and FEEDBACK not in r.text and r.json()["total"] is None

    rel = f"/courses/{w.cid}/assignments/{a.id}/grades"
    r = await api.call(w.O, "POST", f"{rel}/release", json={})
    assert r.status_code == 200 and r.json() == {"released": 1}, r.text
    r = await _mine(api, w.S, w)
    item = r.json()["items"][0]
    assert item["state"] == "graded" and D(item["effective_points"]) == 7 and item["feedback_text"] == FEEDBACK
    assert item["scheme_type"] == "percent" and D(r.json()["total"]["percent"]) == D("70.00")
    assert (await api.call(w.O, "POST", f"{rel}/unrelease", json={})).json() == {"unreleased": 1}
    assert (await _mine(api, w.S, w)).json()["items"][0]["state"] == "pending"
    assert _events(db, sub.id) == ["manual_grade", "released", "unreleased"]

    # auto release: released on the grade write; unrelease is refused
    auto = make_assignment(db, w.course, w.O, kind="text", points=D("5"), grade_release="auto")
    await _hand_in(api, w.S, w, auto)
    r = await _grade(api, w.O, w, auto, w.enr, points="5")
    assert r.status_code == 200 and r.json()["released_at"] is not None, r.text
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/assignments/{auto.id}/grades/unrelease", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "grade_release_auto"


async def test_rubric_scores_rules_and_replacement(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"))
    c1, c2 = _criteria(db, a, [6, 4])
    await _hand_in(api, w.S, w, a)

    def rs(p1, p2):
        return [{"criterion_id": str(c1.id), "points": str(p1), "comment": "ok"}, {"criterion_id": str(c2.id), "points": str(p2)}]

    r = await _grade(api, w.O, w, a, w.enr, points="9", rubric_scores=rs(6, 3))
    assert r.status_code == 200, r.text
    scores = r.json()["rubric_scores"]
    assert [(s["criterion_id"], D(s["points"]), s["comment"], D(s["max_points"])) for s in scores] == [
        (str(c1.id), D(6), "ok", D(6)), (str(c2.id), D(3), None, D(4))]
    assert scores[0]["title"] == {"en": "c1"}
    version = r.json()["version"]
    # P7-5: the sum must match the points
    r = await _grade(api, w.O, w, a, w.enr, points="8", rubric_scores=rs(6, 3))
    assert r.status_code == 422 and r.json()["error"]["code"] == "rubric_sum_mismatch", r.text
    # every criterion exactly once
    r = await _grade(api, w.O, w, a, w.enr, points="6", rubric_scores=rs(6, 3)[:1])
    assert r.status_code == 422 and r.json()["error"]["code"] == "rubric_criteria_mismatch"
    r = await _grade(api, w.O, w, a, w.enr, points="9", rubric_scores=rs(6, 3) + rs(0, 0)[:1])
    assert r.status_code == 422 and r.json()["error"]["code"] == "rubric_criteria_mismatch"
    # within the criterion's points, within the assignment's points
    r = await _grade(api, w.O, w, a, w.enr, points="10", rubric_scores=rs(7, 3))
    assert r.status_code == 422 and r.json()["error"]["code"] == "points_out_of_range"
    r = await _grade(api, w.O, w, a, w.enr, points="11")
    assert r.status_code == 422 and r.json()["error"]["code"] == "points_out_of_range"
    r = await _grade(api, w.O, w, a, w.enr, points="-1")
    assert r.status_code == 422 and r.json()["error"]["code"] == "points_out_of_range"
    # optimistic version
    r = await _grade(api, w.O, w, a, w.enr, points="5", version=version - 1)
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_grade"
    # a new grade replaces the rubric rows as a set; the event carries old and new scores
    r = await _grade(api, w.O, w, a, w.enr, points="10", rubric_scores=rs(6, 4), version=version)
    assert r.status_code == 200, r.text
    sub = _sub(db, a, w.enr)
    stored = db.execute(select(SubmissionRubricScore).where(SubmissionRubricScore.submission_id == sub.id)).scalars().all()
    assert sorted(D(s.points) for s in stored) == [D(4), D(6)]
    ev = r.json()["events"][0]
    assert [x["points"] for x in ev["old"]["rubric_scores"]] == ["6.00", "3.00"]
    assert [x["points"] for x in ev["new"]["rubric_scores"]] == ["6.00", "4.00"]
    # a grade without rubric scores clears them
    r = await _grade(api, w.O, w, a, w.enr, points="10")
    assert r.status_code == 200 and r.json()["rubric_scores"] == []
    assert db.execute(select(SubmissionRubricScore).where(SubmissionRubricScore.submission_id == sub.id)).first() is None


async def test_clear_grade_and_none_kind(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"))
    await _hand_in(api, w.S, w, a)
    assert (await _grade(api, w.O, w, a, w.enr, points="7")).status_code == 200
    # points: null -> back to pending review (a hand-in exists); totals ignore the row; the student sees `submitted`
    r = await _grade(api, w.O, w, a, w.enr, points=None)
    assert r.status_code == 200 and r.json()["state"] == "pending_review" and r.json()["raw_points"] is None, r.text
    assert r.json()["events"][0]["event"] == "manual_grade" and r.json()["events"][0]["old"]["raw_points"] == "7.00"
    gb, by_user = await _gradebook(api, w.O, w)
    assert by_user[w.S.id]["total"]["current_percent"] is None
    assert (await _mine(api, w.S, w)).json()["items"][0]["state"] == "submitted"

    # kind none: the teacher's grade creates the row
    n = make_assignment(db, w.course, w.O, kind="none", points=D("4"), grade_release="auto")
    r = await _grade(api, w.O, w, n, w.enr, points="3")
    assert r.status_code == 200 and r.json()["state"] == "graded" and r.json()["hand_ins"] == [], r.text
    sub = _sub(db, n, w.enr)
    assert sub.assessment_id is None and sub.assignment_id == n.id and sub.graded_item_id is None
    gb, by_user = await _gradebook(api, w.O, w)
    assert D(by_user[w.S.id]["cells"][str(n.id)]["effective_points"]) == 3
    assert D(by_user[w.S.id]["total"]["current_percent"]) == D("75.00")  # 3 / 4; the pending text row is ignored
    assert D(by_user[w.S.id]["total"]["final_percent"]) == D("75.00")    # handed in = not missing (as pending quiz rows)
    item = {i["assignment_id"]: i for i in (await _mine(api, w.S, w)).json()["items"]}[str(n.id)]
    assert item["state"] == "graded" and "submitted_at" not in item and "late" not in item
    # clearing a `none` grade: the row stays `graded` with no points and counts as nothing graded
    r = await _grade(api, w.O, w, n, w.enr, points=None)
    assert r.status_code == 200 and r.json()["state"] == "graded" and r.json()["effective_points"] is None
    gb, by_user = await _gradebook(api, w.O, w)
    assert by_user[w.S.id]["total"]["current_percent"] is None
    assert D(by_user[w.S.id]["total"]["final_percent"]) == D("0.00")
    assert gb["assignments"][1]["stale_count"] == 0  # a cleared row is never stale
    item = {i["assignment_id"]: i for i in (await _mine(api, w.S, w)).json()["items"]}[str(n.id)]
    assert item["state"] == "not_started"


# ------------------------------------------------------------------ authorization and scoping

async def test_quiz_scoping_and_role_matrix(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"))
    q = published_quiz(db, w.course, w.O)
    await _hand_in(api, w.S, w, a)
    r = await _grade(api, w.O, w, q, w.enr, points="1")
    assert r.status_code == 409 and r.json()["error"]["code"] == "quiz_grade_via_attempts", r.text
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{uuid.uuid4()}/grades/{w.enr.id}", json={"points": "1"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "assignment_not_found"
    # another course's assignment through this course's URL, and an enrollment that is not an active student here
    other = world(db)
    oa = make_assignment(db, other.course, other.O, kind="text", points=D("10"))
    r = await _grade(api, w.O, w, oa, w.enr, points="1")
    assert r.status_code == 404 and r.json()["error"]["code"] == "assignment_not_found"
    for bad in (other.enr.id, uuid.uuid4()):
        r = await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{a.id}/grades/{bad}", json={"points": "1"})
        assert r.status_code == 404 and r.json()["error"]["code"] == "enrollment_not_found", r.text
    ta_enr = db.execute(select(mgr.Enrollment).where(mgr.Enrollment.user_id == w.T.id,
                                                     mgr.Enrollment.course_id == w.course.id)).scalar_one()
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{a.id}/grades/{ta_enr.id}", json={"points": "1"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "enrollment_not_found"
    # a deleted assignment is gone for every grade route
    gone = make_assignment(db, w.course, w.O, kind="text", points=D("10"))
    gone.deleted_at = clock.now()
    db.commit()
    for method, path in (("PUT", f"/courses/{w.cid}/assignments/{gone.id}/grades/{w.enr.id}"),
                         ("POST", f"/courses/{w.cid}/assignments/{gone.id}/grades/release"),
                         ("POST", f"/courses/{w.cid}/assignments/{gone.id}/grades/regrade"),
                         ("GET", f"/courses/{w.cid}/assignments/{gone.id}/submissions")):
        r = await api.call(w.O, method, path, json={"points": "1"} if method == "PUT" else {})
        assert r.status_code == 404 and r.json()["error"]["code"] == "assignment_not_found", (method, r.text)

    routes = [
        ("PUT", _grade_url(w, a, w.enr), {"points": "2"}),
        ("POST", f"/courses/{w.cid}/assignments/{a.id}/grades/release", {}),
        ("POST", f"/courses/{w.cid}/assignments/{a.id}/grades/unrelease", {}),
        ("POST", f"/courses/{w.cid}/assignments/{a.id}/grades/regrade", None),
        ("GET", f"/courses/{w.cid}/assignments/{a.id}/submissions", None),
    ]
    expected = {"O": 200, "T": 200, "S": 403, "S2": 403, "OA": 403, "X": 404}
    for who, want in expected.items():
        for method, path, body in routes:
            r = await api.call(getattr(w, who), method, path, json=body)
            assert r.status_code == want, (who, method, path, r.status_code, r.text)
            if want == 404:
                assert r.json()["error"]["code"] == "course_not_found"
    for method, path, body in routes:
        assert (await api.call(None, method, path, json=body)).status_code == 401
    # the other course's teacher: 404 everywhere
    for method, path, body in routes:
        assert (await api.call(other.O, method, path, json=body)).status_code == 404


async def test_student_payloads_never_leak(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"))
    await _hand_in(api, w.S, w, a, text="essay of S")
    await _hand_in(api, w.S2, w, a, text="essay of S2")
    assert (await _grade(api, w.O, w, a, w.enr2, points="9", feedback_text=FEEDBACK)).status_code == 200
    sub2 = _sub(db, a, w.enr2)
    # S never sees S2's hand-in, submission id, feedback or enrollment
    r = await _mine(api, w.S, w)
    for secret in ("essay of S2", str(sub2.id), FEEDBACK, w.S2.id, str(w.enr2.id), str(w.enr.id), "graded_by"):
        assert secret not in r.text, secret
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/submissions/{sub2.id}")).status_code == 403
    # S2 sees own feedback only once released
    r = await _mine(api, w.S2, w)
    assert r.json()["items"][0]["state"] == "pending" and FEEDBACK not in r.text
    await api.call(w.O, "POST", f"/courses/{w.cid}/assignments/{a.id}/grades/release", json={})
    r = await _mine(api, w.S2, w)
    assert r.json()["items"][0]["feedback_text"] == FEEDBACK and "essay of S" not in r.text.replace("essay of S2", "")


# ------------------------------------------------------------------ override, excuse, late, regrade

async def test_override_and_excuse_keep_the_manual_grade(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"), grading_scheme_version_id=PERCENT_V1_ID)
    await _hand_in(api, w.S, w, a)
    v = (await _grade(api, w.O, w, a, w.enr, points="8")).json()["version"]
    sub = _sub(db, a, w.enr)
    base = f"/courses/{w.cid}/submissions/{sub.id}"
    r = await api.call(w.O, "PUT", f"{base}/override", json={"points": "9", "reason": "bonus", "version": v})
    assert r.status_code == 200, r.text
    body = r.json()
    assert D(body["raw_points"]) == 8 and D(body["effective_points"]) == 9 and D(body["display_value"]) == D("90.00")
    assert body["kind"] == "text" and len(body["hand_ins"]) == 1 and body["attempts"] == []
    r = await api.call(w.O, "PUT", f"{base}/excuse", json={"excused": True, "version": body["version"]})
    assert r.status_code == 200 and r.json()["state"] == "excused", r.text
    gb, by_user = await _gradebook(api, w.O, w)
    assert by_user[w.S.id]["cells"][str(a.id)]["state"] == "excused"
    assert by_user[w.S.id]["total"]["current_percent"] is None
    assert (await _mine(api, w.S, w)).json()["items"][0]["state"] == "excused"
    r = await api.call(w.O, "PUT", f"{base}/excuse", json={"excused": False, "version": r.json()["version"]})
    assert r.status_code == 200 and r.json()["state"] == "graded" and D(r.json()["effective_points"]) == 9
    r = await api.call(w.O, "PUT", f"{base}/override", json={"points": None, "version": r.json()["version"]})
    assert r.status_code == 200 and D(r.json()["effective_points"]) == 8 and r.json()["has_override"] is False
    assert _events(db, sub.id) == ["manual_grade", "override", "excused", "unexcused", "override_cleared"]
    # a quiz row through the same routes still runs the attempt path (no hand-ins, attempts list)
    q = published_quiz(db, w.course, w.O)
    from tests.lms.factories import make_submission

    qsub = make_submission(db, db.get(mgr.Assessment, q.assessment_id), w.enr, raw_points=D("1"),
                           points_possible=D("1"), effective_points=D("1"))
    r = await api.call(w.O, "GET", f"/courses/{w.cid}/submissions/{qsub.id}")
    assert r.status_code == 200 and r.json()["kind"] == "quiz" and r.json()["hand_ins"] == []
    assert r.json()["assignment_id"] == str(assignment_id_for(q.assessment_id))


async def test_late_deduction_from_hand_in_and_manual_regrade(db, api):
    w = world(db)
    w.course.late_policy = {"percent_per_day": 10, "max_percent": 50, "grace_minutes": 0}
    db.commit()
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"), grading_scheme_version_id=PERCENT_V1_ID,
                        due_at=clock.now() - timedelta(hours=2))
    h = await _hand_in(api, w.S, w, a)
    assert h["late"] is True and h["late_seconds"] >= 7200
    await _hand_in(api, w.S2, w, a)  # never graded: not a regrade target, never stale
    r = await _grade(api, w.O, w, a, w.enr, points="10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert D(body["late_deduction"]) == D("1.00") and D(body["effective_points"]) == D("9.00")
    assert D(body["display_value"]) == D("90.00")
    # the roster page marks the late hand-in
    rows = {x["user_id"]: x for x in (await api.call(w.O, "GET", f"/courses/{w.cid}/assignments/{a.id}/submissions")).json()["rows"]}
    assert rows[w.S.id]["late"] is True and rows[w.S.id]["hand_in_count"] == 1
    # scheme change on the assignment -> stale -> regrade recomputes from the stored raw points
    a.grading_scheme_version_id = PASS_FAIL_V1_ID
    db.commit()
    gb, _ = await _gradebook(api, w.O, w)
    assert gb["assignments"][0]["stale_count"] == 1 and gb["assignments"][0]["scheme"]["id"] == str(PASS_FAIL_V1_ID)
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/assignments/{a.id}/grades/regrade")
    assert r.status_code == 200 and r.json() == {"regraded": 1, "pending": 0, "scheme_version_id": str(PASS_FAIL_V1_ID)}, r.text
    sub = _sub(db, a, w.enr)
    assert sub.scheme_version_id == PASS_FAIL_V1_ID and sub.passed is True and sub.label == "pass"
    assert sub.raw_points == D("10.00") and sub.effective_points == D("9.00") and sub.late_deduction == D("1.00")
    assert _events(db, sub.id) == ["manual_grade", "regraded"]
    assert _sub(db, a, w.enr2).state == "pending_review" and _sub(db, a, w.enr2).raw_points is None
    gb, _ = await _gradebook(api, w.O, w)
    assert gb["assignments"][0]["stale_count"] == 0
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/assignments/{a.id}/grades/regrade")
    assert r.json()["regraded"] == 0 and r.json()["pending"] == 0


def test_compute_manual_values_matches_compute_values(db):
    """The manual core and the attempt core agree on the shared arithmetic (late deduction, override, scheme)."""
    now = clock.now()
    policy = {"percent_per_day": 10, "max_percent": 50, "grace_minutes": 0}
    arow = NS(score_policy="highest", grading_scheme_version_id=PERCENT_V1_ID, due_at=now - timedelta(days=1),
              grade_release="manual", points_possible=D("10"), late_policy=policy)
    attempt = NS(id=uuid.uuid4(), attempt_no=1, status="graded", raw_score=D("7"), points_possible=D("10"),
                 submitted_at=now, result={"sections": []})
    for override in (None, D("8")):
        sub = {"id": uuid.uuid4(), "state": "graded", "override_points": override, "raw_points": D("7"),
               "late_seconds": 0}
        quiz = subs.compute_values(db, sub, arow, arow, [attempt], now=now)
        hand_in = NS(id=uuid.uuid4(), late_seconds=quiz["late_seconds"])
        man = mgr.compute_manual_values(sub, arow, arow, hand_in, now, version=get_version_data(db, PERCENT_V1_ID))
        for k in ("state", "raw_points", "points_possible", "late_seconds", "late_deduction", "effective_points",
                  "scheme_version_id", "display_value", "label", "percentile", "passed", "thresholds"):
            assert man[k] == quiz[k], (k, man[k], quiz[k])
        assert man["kept_attempt_id"] is None and man["attempts_counted"] == 0 and man["breakdown"] is None
    # states: excused stays; no points -> pending_review with a hand-in, graded without one
    v = get_version_data(db, PERCENT_V1_ID)
    assert mgr.compute_manual_values({"state": "excused", "raw_points": D("1")}, arow, arow, None, now,
                                     version=v)["state"] == "excused"
    assert mgr.compute_manual_values({"state": "graded", "raw_points": None}, arow, arow, NS(late_seconds=0), now,
                                     version=v)["state"] == "pending_review"
    assert mgr.compute_manual_values({"state": "pending_review", "raw_points": None}, arow, arow, None, now,
                                     version=v)["state"] == "pending_review"
    out = mgr.compute_manual_values({"state": "graded", "raw_points": None}, arow, arow, None, now, version=v)
    assert out["state"] == "graded" and out["effective_points"] is None and out["display_value"] is None


def test_load_context_uses_the_students_due_override(db):
    """3.4: the hook's statement 1 returns coalesce(override.due_at, assessment.due_at) for one enrollment."""
    teacher = make_user(db, teacher_status="approved")
    course = make_course(db, teacher)
    due = clock.now()
    a = make_assessment(db, course, teacher, due_at=due)
    s1, s2 = make_user(db), make_user(db)
    e1, e2 = enroll(db, course, s1), enroll(db, course, s2)
    later = due + timedelta(days=3)
    db.add(AssignmentOverride(assignment_id=assignment_id_for(a.id), enrollment_id=e1.id, course_id=course.id,
                              due_at=later, set_by_id=teacher.id))
    db.commit()

    def _utc(d):
        return d.replace(tzinfo=None) if d is not None else None

    assert _utc(subs.load_context(db, a.id).due_at) == _utc(due)
    assert _utc(subs.load_context(db, a.id, e2.id).due_at) == _utc(due)
    assert _utc(subs.load_context(db, a.id, e1.id).due_at) == _utc(later)
    ctx = subs.load_context(db, a.id, e1.id)
    assert ctx.assessment_id == a.id and ctx.score_policy == a.score_policy  # every other column as before


async def test_roster_page_pagination(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"))
    extra = make_user(db)
    enroll(db, w.course, extra)
    seen, cursor = [], None
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        r = await api.call(w.O, "GET", f"/courses/{w.cid}/assignments/{a.id}/submissions", params=params)
        assert r.status_code == 200, r.text
        assert len(r.json()["rows"]) <= 2
        seen += [x["user_id"] for x in r.json()["rows"]]
        cursor = r.json()["next_cursor"]
        if not cursor:
            break
    assert seen == [w.S.id, w.S2.id, extra.id]
