"""Phase 4 end-to-end exit test (PHASE_4_DESIGN section 7, item 9 / Integration row), all over the real HTTP routes
with a frozen clock:

teacher creates a course (weighted totals, late policy, one category) and an ORT-main assessment (system `ort_main`
scheme from the preset, due date, manual release, two attempts) -> students start / autosave / submit (one late,
one with two attempts) -> the Phase 4 hook writes submissions + attempt_grades inside the grading commit ->
gradebook cells and totals -> override (stale version 409, reason required), excuse / unexcuse, release ->
students see only their own released grade (`/grades/mine`, attempt result `grade`) -> the teacher switches to a
personal pass/fail scheme -> regrade until `pending == 0` -> values updated -> void the kept attempt -> submission
recomputed from the remaining attempt -> grade_events trail matches every action. Isolation: a student whose
enrollment was removed and another course's teacher get 404s.

Database-agnostic: the SQLite gate and the Postgres gate (`DATABASE_URL` = PG, `PGTZ=UTC`) both run it; the PG-only
part at the end (`test_phase4_flow_pg_row_counts`) is skipped unless the suite runs on Postgres."""
import json
import uuid
from collections import Counter as Multiset
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import session as db_session
from app.lms.attempts.models import Attempt
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import AttemptGrade, GradeEvent, Submission
from app.lms.grading.params import validate_params
from app.lms.grading.registry import apply, build_version_data
from app.lms.grading.seeds import ORT_MAIN_V1_ID
from tests.lms.assessment_support import add_q, get, mk, publish
from tests.lms.attempt_support import T0, frozen_clock  # noqa: F401
from tests.lms.factories import make_bank, make_question, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

D = Decimal
SECTION_KEYS = ["math_1", "math_2", "analogies", "reading", "grammar"]
PER_SECTION = 2
N = PER_SECTION * len(SECTION_KEYS)  # points_possible
CMP = {"column_a": "$x^2$", "column_b": "$x$", "correct": "D"}
SC = {"choices": [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}], "correct": "B"}
OVERRIDE_REASON = "FLOW_OVERRIDE_REASON_SENTINEL"
EXCUSE_REASON = "FLOW_EXCUSE_REASON_SENTINEL"
VOID_REASON = "FLOW_VOID_REASON_SENTINEL"
STAFF_ONLY = (OVERRIDE_REASON, EXCUSE_REASON, VOID_REASON)
FIXTURES = Path(__file__).parent / "fixtures"


def _ort(raw: int, n: int = N) -> tuple[D, D]:
    """(scaled, percentile) from the frozen oracle table (survives Phase 5, see test_ort_parity)."""
    t = json.loads((FIXTURES / "ort_parity_main.json").read_text(encoding="utf-8"))
    return D(str(t["scaled"][str(n)][raw])), D(str(t["percentile"][str(n)][raw]))


def _num(x) -> D | None:
    return None if x is None else D(str(x))


def _scheme_free(res, *extra):
    """Student payloads never carry staff-only text."""
    for token in STAFF_ONLY + extra:
        assert token not in res.text, (res.request.url, token)


async def _course(api, teacher, title):
    r = await api.call(teacher, "POST", "/courses", json={"title": {"ru": title}, "languages": ["ru"],
                                                         "default_language": "ru"})
    assert r.status_code == 201, r.text
    c = r.json()
    r = await api.call(teacher, "POST", f"/courses/{c['id']}/publish")
    assert r.status_code == 200, r.text
    return c["id"], c["join_code"]


async def _join(api, user, code):
    r = await api.call(user, "POST", "/courses/join", json={"code": code})
    assert r.status_code in (200, 201), r.text


class Exam:
    """The published ORT-main assessment and its answer key per question version."""

    def __init__(self, cid, aid, key):
        self.cid, self.aid, self.key = cid, aid, key
        self.base = f"/courses/{cid}/assessments/{aid}"

    async def take(self, api, student, correct_per_section, *, expect_status=201):
        """start -> autosave each section (forward-only: close 1..4) -> submit. Returns the attempt id."""
        st = await api.call(student, "POST", f"{self.base}/attempts", json={"language": "ru"})
        assert st.status_code == expect_status, st.text
        state = st.json()
        tid = state["id"]
        ts = 0
        for pos, n_correct in enumerate(correct_per_section, start=1):
            items = sorted((i for i in state["items"] if i["section_pos"] == pos), key=lambda i: i["position"])
            answers = []
            for k, it in enumerate(items):
                ts += 1
                right, wrong = self.key[it["qv"]]
                answers.append({"position": it["position"], "client_ts": ts,
                                "response": right if k < n_correct else wrong})
            r = await api.call(student, "PUT", f"/attempts/{tid}/answers", json={"answers": answers})
            assert r.status_code == 200 and len(r.json()["saved"]) == len(items), r.text
            if pos < len(correct_per_section):
                r = await api.call(student, "POST", f"/attempts/{tid}/sections/{pos}/close")
                assert r.status_code == 200, r.text
        r = await api.call(student, "POST", f"/attempts/{tid}/submit", json={})
        assert r.status_code == 200 and r.json()["status"] == "graded", r.text
        return tid


async def _build_exam(api, db, teacher, cid, *, category_id, due_at) -> Exam:
    a = await mk(api, teacher, cid, title={"ru": "ОРТ пробный"}, preset="ort_main", languages=["ru"])
    assert [s["key"] for s in a["sections"]] == SECTION_KEYS
    # P4-6: the ort_main preset attaches the system ORT-main scheme version
    assert a["grading_scheme_version_id"] == str(ORT_MAIN_V1_ID)
    assert a["scheme"]["type"] == "piecewise_curve" and a["scheme"]["version_no"] == 1
    bank = make_bank(db, db.get(Course, uuid.UUID(cid)), teacher)
    key = {}
    for sec in a["sections"]:
        for i in range(PER_SECTION):
            if sec["key"] == "math_1":
                q = make_question(db, bank, teacher, "comparison", data=CMP, language="ru", stem=f"cmp {i}")
                key[str(q.current_version_id)] = ({"choice": "D"}, {"choice": "A"})
            else:
                q = make_question(db, bank, teacher, "single_choice", data=SC, language="ru",
                                  stem=f"{sec['key']} {i}")
                key[str(q.current_version_id)] = ({"choice_id": "B"}, {"choice_id": "A"})
            await add_q(api, teacher, cid, a["id"], sec["id"], q.id)
    cur = await get(api, teacher, cid, a["id"])
    r = await api.call(teacher, "PATCH", f"/courses/{cid}/assessments/{a['id']}", json={
        "draft_rev": cur["draft_rev"], "allowed_attempts": 2, "grade_category_id": category_id,
        "due_at": due_at.isoformat(), "grade_release": "manual"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["grade_category_id"] == category_id and body["grade_release"] == "manual"
    assert body["grading_scheme_version_id"] == str(ORT_MAIN_V1_ID)
    pub = await publish(api, teacher, cid, a["id"])
    assert pub.status_code == 200, pub.text
    assert D(str(pub.json()["version"]["points_possible"])) == N
    return Exam(cid, a["id"], key)


def _subs(db, aid) -> dict:
    db.expire_all()
    return {s.user_id: s for s in db.execute(select(Submission).where(Submission.assessment_id == uuid.UUID(aid)))
            .scalars()}


def _events(db, sub_id) -> list[GradeEvent]:
    db.expire_all()
    return list(db.execute(select(GradeEvent).where(GradeEvent.submission_id == sub_id)
                           .order_by(GradeEvent.created_at, GradeEvent.id)).scalars())


async def _gradebook(api, teacher, cid):
    r = await api.call(teacher, "GET", f"/courses/{cid}/gradebook")
    assert r.status_code == 200, r.text
    g = r.json()
    return g, {row["user_id"]: row for row in g["rows"]}


async def _detail(api, teacher, cid, sub_id):
    r = await api.call(teacher, "GET", f"/courses/{cid}/submissions/{sub_id}")
    assert r.status_code == 200, r.text
    return r.json()


async def _mine(api, student, cid):
    r = await api.call(student, "GET", f"/courses/{cid}/grades/mine")
    assert r.status_code == 200, r.text
    _scheme_free(r)
    return r.json()


async def test_phase4_flow(db, api, frozen_clock):
    clock = frozen_clock
    teacher = make_user(db, teacher_status="approved", display_name="Teacher A")
    other_teacher = make_user(db, teacher_status="approved", display_name="Teacher B")
    s1 = make_user(db, display_name="Student One")
    s2 = make_user(db, display_name="Student Two")
    rm = make_user(db, display_name="Student Removed")

    # ---- 1. course: weighted totals, late policy, one category; students join with the code
    cid, code = await _course(api, teacher, "Курс А")
    other_cid, _ = await _course(api, other_teacher, "Курс Б")
    for s in (s1, s2, rm):
        await _join(api, s, code)
    r = await api.call(teacher, "PUT", f"/courses/{cid}/grading", json={
        "total_mode": "weighted",
        "late_policy": {"percent_per_day": 10, "max_percent": 50, "grace_minutes": 0}})
    assert r.status_code == 200, r.text
    assert r.json()["total_mode"] == "weighted" and r.json()["late_policy"]["percent_per_day"] == 10
    r = await api.call(teacher, "POST", f"/courses/{cid}/grade-categories",
                       json={"title": {"ru": "Экзамены"}, "weight": 100})
    assert r.status_code == 201, r.text
    cat_id = r.json()["id"]
    # the student view of the course grading settings: total mode and scheme only
    r = await api.call(s1, "GET", f"/courses/{cid}/grading")
    assert r.status_code == 200 and set(r.json()) <= {"total_mode", "scheme"}, r.text

    # ---- 2. ORT-main assessment: system scheme, category, due date, manual release, 2 attempts
    due = T0 + timedelta(days=1)
    exam = await _build_exam(api, db, teacher, cid, category_id=cat_id, due_at=due)
    aid = exam.aid

    # ---- 3. on time: S1 (7/10) and the soon-removed student (4/10)
    t1 = await exam.take(api, s1, [2, 1, 2, 1, 1])
    t_rm = await exam.take(api, rm, [1, 1, 1, 1, 0])
    # ---- 4. late by 12 h (1 day -> 10 %): S2 attempt 1 (10/10) and attempt 2 (5/10)
    clock.set(due + timedelta(hours=12))
    t2a = await exam.take(api, s2, [2, 2, 2, 2, 2])
    clock.advance(60)
    t2b = await exam.take(api, s2, [1, 1, 1, 1, 1])
    # the attempt limit holds
    r = await api.call(s2, "POST", f"{exam.base}/attempts", json={"language": "ru"})
    assert r.status_code in (403, 409), r.text

    # ---- 5. the hook: one submission per enrollment, one attempt_grades row per graded attempt, same commit
    subs = _subs(db, aid)
    assert set(subs) == {s1.id, s2.id, rm.id}
    sub1, sub2, sub_rm = subs[s1.id], subs[s2.id], subs[rm.id]
    atts = {a.id: a for a in db.execute(select(Attempt).where(Attempt.assessment_id == uuid.UUID(aid))).scalars()}
    ags = {g.attempt_id: g for g in db.execute(select(AttemptGrade).where(
        AttemptGrade.attempt_id.in_(list(atts)))).scalars()}
    assert set(ags) == set(atts) and all(g.scheme_version_id == ORT_MAIN_V1_ID for g in ags.values())
    assert sub1.computed_at == atts[uuid.UUID(t1)].graded_at
    assert sub2.computed_at == atts[uuid.UUID(t2b)].graded_at  # the last scoring recomputed the submission
    for sub, raw, kept in ((sub1, 7, t1), (sub2, 10, t2a), (sub_rm, 4, t_rm)):
        assert str(sub.kept_attempt_id) == kept and sub.released_at is None and sub.state == "graded"
        assert sub.raw_points == raw and sub.points_possible == N and sub.scheme_version_id == ORT_MAIN_V1_ID
    assert sub1.late_seconds == 0 and sub1.late_deduction == 0 and sub1.effective_points == 7
    assert sub2.attempts_counted == 2 and sub2.late_seconds == 12 * 3600  # kept attempt 1, submitted due + 12 h
    assert sub2.late_deduction == D("1.00") and sub2.effective_points == 9
    assert (sub1.display_value, sub1.percentile) == _ort(7)
    assert (sub2.display_value, sub2.percentile) == _ort(9)  # kept 10 - 10 % late
    assert (ags[uuid.UUID(t2a)].display_value, ags[uuid.UUID(t2a)].percentile) == _ort(10)
    assert ags[uuid.UUID(t2b)].display_value == _ort(5)[0]

    # ---- 6. gradebook: cells, totals, counts (manual release: nothing released yet)
    gb, rows = await _gradebook(api, teacher, cid)
    col = next(x for x in gb["assessments"] if x["id"] == aid)
    assert col["submission_count"] == 3 and col["released_count"] == 0 and col["stale_count"] == 0
    assert col["category_id"] == cat_id and col["grade_release"] == "manual"
    assert col["scheme"]["id"] == str(ORT_MAIN_V1_ID)
    c1, c2 = rows[s1.id]["cells"][aid], rows[s2.id]["cells"][aid]
    assert c1["submission_id"] == str(sub1.id) and _num(c1["display_value"]) == _ort(7)[0]
    assert _num(c2["late_deduction"]) == 1 and _num(c2["effective_points"]) == 9 and c2["attempts_counted"] == 2
    assert c1["released_at"] is None and c1["has_override"] is False
    assert _num(rows[s1.id]["total"]["current_percent"]) == 70
    assert _num(rows[s2.id]["total"]["current_percent"]) == 90

    # ---- 7. before release: results visible per policy, but the grade is pending
    r = await api.call(s1, "GET", f"/attempts/{t1}/result")
    assert r.status_code == 200 and r.json()["grade"] is None, r.text
    mine = await _mine(api, s1, cid)
    assert [i["state"] for i in mine["items"]] == ["pending"]
    assert set(mine["items"][0]) == {"assessment_id", "title", "state", "due_at"}

    # ---- 8. override S1 (reason required, stale version -> 409, then 8 points)
    clock.advance(60)
    base_sub = f"/courses/{cid}/submissions"
    r = await api.call(teacher, "PUT", f"{base_sub}/{sub1.id}/override", json={"points": 8, "version": sub1.version})
    assert r.status_code == 422 and r.json()["error"]["code"] == "override_reason_required", r.text
    r = await api.call(teacher, "PUT", f"{base_sub}/{sub1.id}/override",
                       json={"points": 8, "reason": OVERRIDE_REASON, "version": sub1.version + 5})
    assert r.status_code == 409 and r.json()["error"]["code"] == "grade_conflict", r.text
    r = await api.call(teacher, "PUT", f"{base_sub}/{sub1.id}/override",
                       json={"points": 11, "reason": OVERRIDE_REASON, "version": sub1.version})
    assert r.status_code == 422 and r.json()["error"]["code"] == "points_out_of_range", r.text
    r = await api.call(teacher, "PUT", f"{base_sub}/{sub1.id}/override",
                       json={"points": 8, "reason": OVERRIDE_REASON, "version": sub1.version})
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["has_override"] is True and _num(o["override_points"]) == 8 and _num(o["effective_points"]) == 8
    assert _num(o["display_value"]) == _ort(8)[0] and o["override_reason"] == OVERRIDE_REASON
    assert o["override_by_name"] == "Teacher A"

    # ---- 9. excuse S2: excused cell, no total; the student sees "excused"
    clock.advance(60)
    v2 = (await _detail(api, teacher, cid, sub2.id))["version"]
    r = await api.call(teacher, "PUT", f"{base_sub}/{sub2.id}/excuse",
                       json={"excused": True, "reason": EXCUSE_REASON, "version": v2})
    assert r.status_code == 200 and r.json()["state"] == "excused", r.text
    _, rows = await _gradebook(api, teacher, cid)
    assert rows[s2.id]["cells"][aid]["state"] == "excused" and rows[s2.id]["total"]["current_percent"] is None
    assert [i["state"] for i in (await _mine(api, s2, cid))["items"]] == ["excused"]
    clock.advance(60)
    r = await api.call(teacher, "PUT", f"{base_sub}/{sub2.id}/excuse",
                       json={"excused": False, "version": r.json()["version"]})
    assert r.status_code == 200 and r.json()["state"] == "graded", r.text

    # ---- 10. release all (idempotent)
    clock.advance(60)
    rel = f"{exam.base}/grades/release"
    r = await api.call(teacher, "POST", rel, json={})
    assert r.status_code == 200 and r.json() == {"released": 3}, r.text
    r = await api.call(teacher, "POST", rel, json={})
    assert r.status_code == 200 and r.json() == {"released": 0}, r.text

    # ---- 11. students see only their own released grade
    res1 = await api.call(s1, "GET", f"/attempts/{t1}/result")
    assert res1.status_code == 200, res1.text
    _scheme_free(res1)
    g = res1.json()["grade"]
    assert g["scheme_type"] == "piecewise_curve" and g["released"] is True and g["is_kept"] is True
    assert (_num(g["display_value"]), _num(g["percentile"])) == _ort(7)  # this attempt's own grade
    assert g["thresholds"] == {"golden_certificate": _ort(7)[0] >= 219}
    # per-section scaled values (apply_to_sections), each section on its own N
    assert [(s_["pos"], _num(s_["display_value"])) for s_ in g["sections"]] == \
        [(p, _ort(k, PER_SECTION)[0]) for p, k in enumerate([2, 1, 2, 1, 1], start=1)]
    mine1 = await _mine(api, s1, cid)
    assert len(mine1["items"]) == 1
    it = mine1["items"][0]
    assert it["state"] == "graded" and _num(it["display_value"]) == _ort(8)[0]  # kept + override
    assert _num(it["effective_points"]) == 8 and it["kept_attempt_id"] == t1
    assert _num(mine1["total"]["percent"]) == 80
    for forbidden in (s2.id, str(sub2.id), str(sub1.id), t2a, "override_reason", "user_id"):
        assert forbidden not in json.dumps(mine1), forbidden
    mine2 = await _mine(api, s2, cid)
    it2 = mine2["items"][0]
    assert _num(it2["display_value"]) == _ort(9)[0] and _num(it2["late_deduction"]) == 1
    assert it2["kept_attempt_id"] == t2a
    rb = (await api.call(s2, "GET", f"/attempts/{t2b}/result")).json()["grade"]
    assert rb["is_kept"] is False and _num(rb["display_value"]) == _ort(5)[0]
    # another student's attempt, the gradebook and submission detail are not reachable for a student
    r = await api.call(s1, "GET", f"/attempts/{t2a}/result")
    assert r.status_code == 404, r.text
    for path in (f"/courses/{cid}/gradebook", f"{base_sub}/{sub2.id}", f"{base_sub}/{sub1.id}"):
        r = await api.call(s1, "GET", path)
        assert r.status_code == 403, (path, r.text)
    r = await api.call(s1, "PUT", f"{base_sub}/{sub1.id}/override",
                       json={"points": 10, "reason": "x", "version": o["version"]})
    assert r.status_code == 403, r.text

    # ---- 12. switch to a personal pass/fail scheme (85 %): old grades stay until regrade
    clock.advance(60)
    pf_params = {"schema": 1, "pass_threshold_percent": 85}
    r = await api.call(teacher, "POST", "/grading-schemes",
                       json={"title": {"ru": "Зачёт 85"}, "type": "pass_fail", "params": pf_params})
    assert r.status_code == 201, r.text
    pf_vid = r.json()["versions"][0]["id"]
    cur = await get(api, teacher, cid, aid)
    r = await api.call(teacher, "PATCH", f"/courses/{cid}/assessments/{aid}",
                       json={"draft_rev": cur["draft_rev"], "grading_scheme_version_id": pf_vid})
    assert r.status_code == 200 and r.json()["scheme"]["type"] == "pass_fail", r.text
    gb, rows = await _gradebook(api, teacher, cid)
    col = next(x for x in gb["assessments"] if x["id"] == aid)
    assert col["stale_count"] == 3 and col["released_count"] == 3
    assert _num(rows[s1.id]["cells"][aid]["display_value"]) == _ort(8)[0]  # unchanged (D14)
    assert _num((await _mine(api, s1, cid))["items"][0]["display_value"]) == _ort(8)[0]

    clock.advance(60)
    total, calls = 0, 0
    while True:
        r = await api.call(teacher, "POST", f"{exam.base}/grades/regrade")
        assert r.status_code == 200, r.text
        calls += 1
        total += r.json()["regraded"]
        assert r.json()["scheme_version_id"] == pf_vid
        if r.json()["pending"] == 0:
            break
        assert calls < 10
    assert total == 3
    r = await api.call(teacher, "POST", f"{exam.base}/grades/regrade")
    assert r.json() == {"regraded": 0, "pending": 0, "scheme_version_id": pf_vid}, r.text

    pf = build_version_data("pass_fail", validate_params("pass_fail", pf_params))
    gb, rows = await _gradebook(api, teacher, cid)
    assert next(x for x in gb["assessments"] if x["id"] == aid)["stale_count"] == 0
    for user, eff in ((s1, 8), (s2, 9)):
        exp = apply(pf, D(eff), D(N))
        c = rows[user.id]["cells"][aid]
        assert (_num(c["display_value"]), c["label"], c["passed"]) == (exp.display_value, exp.label, exp.passed)
    assert rows[s1.id]["cells"][aid]["passed"] is False and rows[s2.id]["cells"][aid]["passed"] is True
    assert _num(rows[s1.id]["cells"][aid]["override_points"]) == 8  # the override survives the regrade
    g = (await api.call(s1, "GET", f"/attempts/{t1}/result")).json()["grade"]
    assert g["scheme_type"] == "pass_fail" and g["label"] == apply(pf, D(7), D(N)).label
    db.expire_all()
    assert all(x.scheme_version_id == uuid.UUID(pf_vid) for x in db.execute(select(AttemptGrade).where(
        AttemptGrade.attempt_id.in_(list(atts)))).scalars())

    # ---- 13. void S2's kept attempt: the submission falls back to attempt 2 (5/10, still 10 % late)
    clock.advance(60)
    r = await api.call(teacher, "POST", f"/courses/{cid}/attempts/{t2a}/void", json={"reason": VOID_REASON})
    assert r.status_code == 200 and r.json()["status"] == "void", r.text
    assert r.json()["submission_id"] == str(sub2.id)
    r = await api.call(teacher, "POST", f"/courses/{cid}/attempts/{t2a}/void", json={"reason": VOID_REASON})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_void", r.text
    d2 = await _detail(api, teacher, cid, sub2.id)
    exp = apply(pf, D("4.50"), D(N))
    assert d2["kept_attempt_id"] == t2b and d2["attempts_counted"] == 1
    assert _num(d2["raw_points"]) == 5 and _num(d2["late_deduction"]) == D("0.50")
    assert _num(d2["effective_points"]) == D("4.50") and d2["passed"] is exp.passed is False
    assert {a_["id"]: a_["status"] for a_ in d2["attempts"]}[t2a] == "void"
    db.expire_all()
    assert db.get(AttemptGrade, uuid.UUID(t2a)) is None and db.get(AttemptGrade, uuid.UUID(t2b)) is not None
    vr = await api.call(s2, "GET", f"/attempts/{t2a}/result")
    assert vr.status_code == 200 and vr.json() == {"status": "void"}, vr.text
    _scheme_free(vr)
    it2 = (await _mine(api, s2, cid))["items"][0]
    assert it2["kept_attempt_id"] == t2b and _num(it2["effective_points"]) == D("4.50") and it2["passed"] is False

    # ---- 14. grade_events trail == the actions taken (no event for rejected calls or automatic scoring)
    trail = {s1.id: ["override", "released", "regraded"],
             s2.id: ["excused", "unexcused", "released", "regraded", "attempt_voided"],
             rm.id: ["released", "regraded"]}
    for user, want in trail.items():
        evs = _events(db, subs[user].id)
        assert [e.event for e in evs] == want, (user, [e.event for e in evs])
        assert all(e.actor_id == teacher.id and e.course_id == uuid.UUID(cid) for e in evs)
    ev1 = _events(db, sub1.id)
    assert ev1[0].reason == OVERRIDE_REASON and D(str(ev1[0].new["override_points"])) == 8
    void_ev = _events(db, sub2.id)[-1]
    assert str(void_ev.attempt_id) == t2a and void_ev.reason == VOID_REASON
    api_events = (await _detail(api, teacher, cid, sub2.id))["events"]
    assert Multiset(e["event"] for e in api_events) == Multiset(trail[s2.id])
    assert all(e["actor_name"] == "Teacher A" for e in api_events)

    # ---- 15. removed enrollment: the student loses every grade route (404), the roster drops the row
    enr_rm = db.execute(select(Enrollment).where(Enrollment.course_id == uuid.UUID(cid),
                                                 Enrollment.user_id == rm.id)).scalar_one()
    r = await api.call(teacher, "DELETE", f"/courses/{cid}/enrollments/{enr_rm.id}")
    assert r.status_code == 204, r.text
    for method, path in (("GET", f"/courses/{cid}/grades/mine"), ("GET", f"/attempts/{t_rm}/result"),
                         ("GET", f"/attempts/{t_rm}"), ("POST", f"{exam.base}/attempts")):
        r = await api.call(rm, method, path, json={"language": "ru"} if method == "POST" else None)
        assert r.status_code == 404, (path, r.status_code, r.text)
    _, rows = await _gradebook(api, teacher, cid)
    assert rm.id not in rows and {s1.id, s2.id} <= set(rows)

    # ---- 16. another course's teacher: 404 on every grade route of course A
    sid = sub1.id
    probes = [
        ("GET", f"/courses/{cid}/gradebook", None),
        ("GET", f"{base_sub}/{sid}", None),
        ("PUT", f"{base_sub}/{sid}/override", {"points": 1, "reason": "x", "version": 1}),
        ("PUT", f"{base_sub}/{sid}/excuse", {"excused": True, "version": 1}),
        ("POST", f"{exam.base}/grades/release", {}),
        ("POST", f"{exam.base}/grades/unrelease", {}),
        ("POST", f"{exam.base}/grades/regrade", None),
        ("POST", f"/courses/{cid}/attempts/{t1}/void", {"reason": "x"}),
        ("GET", f"/courses/{cid}/attempts/{t1}", None),
        ("GET", f"{exam.base}/attempts", None),
        ("GET", f"/courses/{cid}/grades/mine", None),
        ("PUT", f"/courses/{cid}/grading", {"total_mode": "points"}),
    ]
    for method, path, body in probes:
        r = await api.call(other_teacher, method, path, json=body)
        assert r.status_code == 404, (method, path, r.status_code, r.text)
    # ... and course A's ids through course B's URLs are misses too
    for method, path, body in (("GET", f"/courses/{other_cid}/submissions/{sid}", None),
                               ("POST", f"/courses/{other_cid}/attempts/{t1}/void", {"reason": "x"})):
        r = await api.call(other_teacher, method, path, json=body)
        assert r.status_code == 404, (method, path, r.status_code, r.text)
    # teacher B cannot attach teacher A's personal scheme version to a course-B assessment
    b = await mk(api, other_teacher, other_cid, title={"ru": "Б"}, languages=["ru"])
    r = await api.call(other_teacher, "PATCH", f"/courses/{other_cid}/assessments/{b['id']}",
                       json={"draft_rev": b["draft_rev"], "grading_scheme_version_id": pf_vid})
    assert r.status_code == 404 and r.json()["error"]["code"] == "scheme_version_not_found", r.text
    # nothing above wrote an event
    assert [e.event for e in _events(db, sub1.id)] == trail[s1.id]


async def test_phase4_flow_pg_row_counts(db, api, frozen_clock):
    """Postgres only: the hook's upsert creates exactly one submission per (enrollment, assessment) even when the
    same student submits twice in a row, and grade_events rows are immutable at the ORM level."""
    if db_session.engine.dialect.name != "postgresql":
        pytest.skip("Postgres-only part of the Phase 4 flow (run the suite with DATABASE_URL on PG)")
    teacher = make_user(db, teacher_status="approved")
    s = make_user(db)
    cid, code = await _course(api, teacher, "PG")
    await _join(api, s, code)
    r = await api.call(teacher, "POST", f"/courses/{cid}/grade-categories", json={"title": {"ru": "К"}, "weight": 1})
    exam = await _build_exam(api, db, teacher, cid, category_id=r.json()["id"], due_at=T0 + timedelta(days=1))
    t1 = await exam.take(api, s, [1, 1, 1, 1, 1])
    t2 = await exam.take(api, s, [2, 2, 2, 2, 2])
    db.expire_all()
    n = db.execute(select(func.count()).select_from(Submission).where(
        Submission.assessment_id == uuid.UUID(exam.aid))).scalar_one()
    assert n == 1
    sub = _subs(db, exam.aid)[s.id]
    assert str(sub.kept_attempt_id) == t2 and sub.attempts_counted == 2 and t1 != t2
    r = await api.call(teacher, "POST", f"{exam.base}/grades/release", json={})
    assert r.json() == {"released": 1}
    ev = _events(db, sub.id)[0]
    ev.reason = "tampered"
    with pytest.raises(Exception):
        db.flush()
    db.rollback()
