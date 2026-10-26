"""ORT gradebook golden (PHASE_7A_DESIGN section 6: "ORT gradebook shows the Phase 4 numbers"; rule 9).

The ORT (ru) exam of the production seed path, two students with the deterministic answers of `test_ort_e2e_api`
(student A: PLAN of that test without the timer boundary, raw 131 of 150; student B: 10 correct per section, raw 50),
then `GET /courses/{id}/gradebook` (as a course teacher) and `GET /courses/{id}/grades/mine` (each student).
The normalized responses must equal `tests/fixtures/ort_gradebook_golden.json`, which was captured on the code
before any Phase 7a change ("frozen before 7a"). After 7a the gradebook speaks in assignments: the single column
is the ORT exam's quiz assignment (`assignment_id_for(assessment_id)`), the numbers stay identical.

Regenerate (only with the owner's reason, never to make a failing test pass): `ORT_GOLDEN_CAPTURE=1 pytest <this>`."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

from sqlalchemy import select

from app.lms.assessments.models import Assessment
from app.lms.content.models import QuestionVersion
from app.lms.core import clock as clock_module
from app.lms.ort.seed import course_id_for, ensure_ort_courses
from app.lms.courses.models import Course
from tests.lms.factories import enroll, make_user
from tests.lms.s3_support import Api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_ort_e2e_api import Clock, response_for
from tests.lms.test_ort_seed import insert_export

GOLDEN = Path(__file__).parent.parent / "fixtures" / "ort_gradebook_golden.json"
# (answered, wrong) per section; A follows test_ort_e2e_api.PLAN (raw 131), B answers 10 per section right (raw 50)
PLANS = {
    "A": {1: (30, 5), 2: (21, 0), 3: (30, 3), 4: (30, 0), 5: (30, 2)},
    "B": {1: (10, 0), 2: (10, 0), 3: (10, 0), 4: (10, 0), 5: (10, 0)},
}
COLUMN_FIELDS = ("title", "points_possible", "omit_from_total", "grade_release", "score_policy", "submission_count",
                 "released_count", "stale_count", "warnings")
CELL_FIELDS = ("state", "attempts_counted", "raw_points", "points_possible", "late_deduction", "override_points",
               "has_override", "effective_points", "display_value", "label", "percentile", "passed", "thresholds",
               "breakdown")
MINE_FIELDS = ("title", "state", "display_value", "label", "percentile", "passed", "thresholds", "effective_points",
               "points_possible", "late_deduction", "labels", "scheme_type", "breakdown")


def _num(v):
    """Decimals arrive as JSON strings or numbers; compare their value, not their scale."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)) or (isinstance(v, str) and _is_number(v)):
        return format(D(str(v)).normalize(), "f")
    if isinstance(v, dict):
        return {k: _num(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_num(x) for x in v]
    return v


def _is_number(s: str) -> bool:
    try:
        D(s)
    except Exception:
        return False
    return True


def _pick(obj: dict, fields) -> dict:
    return {f: _num(obj[f]) for f in fields if f in obj}


def _column_rows(page: dict) -> tuple[str, list[dict]]:
    """('assessments' | 'assignments', columns) of a gradebook page (the key changes in 7a, the content does not)."""
    key = "assignments" if "assignments" in page else "assessments"
    return key, page[key]


def normalize_gradebook(page: dict, assessment_id: uuid.UUID, names: dict) -> dict:
    from_key, cols = _column_rows(page)
    assert len(cols) == 1, cols
    col = cols[0]
    if from_key == "assignments":
        from app.lms.assignments.ids import assignment_id_for
        assert col["id"] == str(assignment_id_for(assessment_id)), col
    else:
        assert col["id"] == str(assessment_id), col
    rows = []
    for r in page["rows"]:
        assert set(r["cells"]) <= {col["id"]}, r["cells"]
        cell = r["cells"].get(col["id"])
        rows.append({"student": names[r["user_id"]],
                     "cell": _pick(cell, CELL_FIELDS) if cell is not None else None,
                     "total": _num(r["total"])})
    rows.sort(key=lambda x: x["student"])
    return {"column": _pick(col, COLUMN_FIELDS), "rows": rows}


def normalize_mine(body: dict) -> dict:
    items = body["items"]
    assert len(items) == 1, items
    return {"total": _num(body.get("total")), "scheme": _num(body.get("scheme")),
            "items": [_pick(i, MINE_FIELDS) for i in items]}


async def _take_exam(api: Api, student, cid, aid, qvs_cache: dict, db, plan: dict) -> None:
    base = f"/courses/{cid}/assessments/{aid}"
    st = await api.call(student, "POST", f"{base}/attempts", json={"language": "ru"})
    assert st.status_code == 201, st.text
    state = st.json()
    tid = state["id"]
    items = sorted(state["items"], key=lambda i: i["position"])
    missing = [uuid.UUID(i["qv"]) for i in items if i["qv"] not in qvs_cache]
    if missing:
        qvs_cache.update({str(v.id): v for v in db.scalars(select(QuestionVersion).where(QuestionVersion.id.in_(missing)))})
    by_sec = {p: [i for i in items if i["section_pos"] == p] for p in range(1, 6)}
    ts = 1000
    for pos in range(1, 6):
        c = await api.call(student, "GET", f"/attempts/{tid}/content?section={pos}")
        assert c.status_code == 200, c.text
        upto, wrong = plan[pos]
        sec = by_sec[pos][:upto]
        for k in range(0, upto, 20):
            batch = []
            for idx, it in enumerate(sec):
                if k <= idx < min(k + 20, upto):
                    ts += 1
                    batch.append({"position": it["position"], "client_ts": ts,
                                  "response": response_for(qvs_cache[it["qv"]], idx >= wrong)})
            r = await api.call(student, "PUT", f"/attempts/{tid}/answers", json={"answers": batch})
            assert r.status_code == 200 and r.json()["saved"] == [b["position"] for b in batch], r.text
        if pos < 5:
            r = await api.call(student, "POST", f"/attempts/{tid}/sections/{pos}/close")
            assert r.status_code == 200, r.text
    sub = await api.call(student, "POST", f"/attempts/{tid}/submit", json={})
    assert sub.status_code == 200 and sub.json()["status"] == "graded", sub.text


async def test_ort_gradebook_matches_phase4_golden(db, monkeypatch):
    clk = Clock(datetime.now(timezone.utc).replace(microsecond=0))
    monkeypatch.setattr(clock_module, "now", clk.now)
    api = Api()
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ru", language="ru", keep_images=False)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok and rep.assessments_published == 1, rep
    cid = course_id_for("ru")
    a = db.scalars(select(Assessment).where(Assessment.course_id == cid)).one()
    teacher = make_user(db, teacher_status="approved")
    enroll(db, db.get(Course, cid), teacher, role="teacher", source="staff_add")
    students = {}
    for name in PLANS:
        s = make_user(db)
        r = await api.call(s, "POST", f"/courses/{cid}/join")
        assert r.status_code == 200, r.text
        students[name] = s
    qvs: dict = {}
    for name, plan in PLANS.items():
        await _take_exam(api, students[name], cid, a.id, qvs, db, plan)

    gb = await api.call(teacher, "GET", f"/courses/{cid}/gradebook")
    assert gb.status_code == 200, gb.text
    names = {s.id: name for name, s in students.items()}
    got = {"gradebook": normalize_gradebook(gb.json(), a.id, names), "mine": {}}
    for name, s in students.items():
        m = await api.call(s, "GET", f"/courses/{cid}/grades/mine")
        assert m.status_code == 200, m.text
        got["mine"][name] = normalize_mine(m.json())

    # sanity on the numbers themselves (the oracle of test_ort_e2e_api)
    cells = {r["student"]: r["cell"] for r in got["gradebook"]["rows"]}
    assert (cells["A"]["raw_points"], cells["A"]["display_value"], cells["A"]["percentile"]) == ("131", "222", "99.2")
    assert cells["B"]["raw_points"] == "50"

    if os.environ.get("ORT_GOLDEN_CAPTURE") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(got, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert got == want
