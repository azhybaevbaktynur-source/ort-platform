"""ORT API end-to-end (PHASE_6_DESIGN section 6, "ORT API e2e"; rule 9: ORT must not change).

The real ORT path at API level, frozen as today's engine behaves: the tsoomo19 export row becomes the published
`ort_main` exam of `ORT (ru)` (seed), a student joins and starts it -> the math_1 comparison card (A-D, no key in the
student payload) -> autosave (saved / stale / invalid) -> finish a section (forward-only: the closed section refuses
answers, later sections are not served) -> the timer boundary of section 2 (inside the grace an answer is stored, past
deadline + grace it is refused and the engine has auto-advanced to section 3 at the section deadline) -> submit with
section 5 still open -> result: raw score, the ORT scaled score and percentile of the frozen oracle table
(`ort_parity_main.json`), five section rows in ORT order, the golden certificate rule (scaled >= 219).

Extends the pattern of `test_ort_cutover_flow.py` (which stays unchanged)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.lms.assessments.models import Assessment
from app.lms.content.models import QuestionVersion
from app.lms.core import clock as clock_module
from app.lms.ort.seed import course_id_for, ensure_ort_courses
from tests.lms.factories import make_user
from tests.lms.s3_support import Api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_ort_seed import OLD_MINUTES, insert_export

FIXTURES = Path(__file__).parent / "fixtures"
N = 150
ORT_ORDER = ["math_1", "math_2", "analogies", "reading", "grammar"]
# answers per section: (answered, wrong); section 2 is cut by its deadline after 21 answers
PLAN = {1: (30, 5), 2: (21, 0), 3: (30, 3), 4: (30, 0), 5: (30, 2)}
RAW = sum(a - w for a, w in PLAN.values())  # 131


class Clock:
    def __init__(self, t: datetime):
        self.t = t

    def now(self) -> datetime:
        return self.t


def oracle(raw: int) -> tuple[D, D]:
    t = json.loads((FIXTURES / "ort_parity_main.json").read_text(encoding="utf-8"))
    return D(str(t["scaled"][str(N)][raw])), D(str(t["percentile"][str(N)][raw]))


def response_for(qv: QuestionVersion, correct: bool) -> dict:
    d = qv.data
    if qv.type == "comparison":
        return {"choice": d["correct"] if correct else next(c for c in "ABCD" if c != d["correct"])}
    assert qv.type == "single_choice", qv.type
    if correct:
        return {"choice_id": d["correct"]}
    return {"choice_id": next(c["id"] for c in d["choices"] if c["id"] != d["correct"])}


def iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def test_ort_main_exam_end_to_end(db, monkeypatch):
    clk = Clock(datetime.now(timezone.utc).replace(microsecond=0))
    monkeypatch.setattr(clock_module, "now", clk.now)
    grace = settings.ATTEMPT_GRACE_S
    api = Api()

    # ---- the ORT (ru) course with the published ort_main exam (production seed path)
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ru", language="ru", keep_images=False)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok and rep.assessments_published == 1, rep
    cid = course_id_for("ru")
    a = db.scalars(select(Assessment).where(Assessment.course_id == cid)).one()
    assert (a.preset, a.navigation, a.status) == ("ort_main", "section_forward_only", "published")
    student = make_user(db)
    r = await api.call(student, "POST", f"/courses/{cid}/join")
    assert r.status_code == 200, r.text

    # ---- start
    base = f"/courses/{cid}/assessments/{a.id}"
    lobby = await api.call(student, "GET", base)
    assert lobby.status_code == 200 and lobby.json()["can_start"] is True, lobby.text
    st = await api.call(student, "POST", f"{base}/attempts", json={"language": "ru"})
    assert st.status_code == 201, st.text
    state = st.json()
    tid = state["id"]
    assert state["status"] == "in_progress" and state["navigation"] == "section_forward_only"
    assert state["current_section_pos"] == 1 and len(state["items"]) == N and state["grace_s"] == grace
    assert [s["pos"] for s in state["sections"]] == [1, 2, 3, 4, 5]
    assert iso(state["deadline_at"]) == clk.t + timedelta(minutes=sum(OLD_MINUTES.values()))  # 170 min
    s1 = state["sections"][0]
    assert iso(s1["started_at"]) == clk.t
    assert iso(s1["deadline_at"]) == clk.t + timedelta(minutes=OLD_MINUTES["math_1"])
    assert all(s["started_at"] is None and s["closed_at"] is None for s in state["sections"][1:])
    again = await api.call(student, "POST", f"{base}/attempts", json={"language": "ru"})
    assert again.status_code == 200 and again.json()["id"] == tid  # resume, not a second attempt

    items = sorted(state["items"], key=lambda i: i["position"])
    by_sec = {p: [i for i in items if i["section_pos"] == p] for p in range(1, 6)}
    assert [len(v) for v in by_sec.values()] == [30] * 5
    qvs = {str(v.id): v for v in db.scalars(select(QuestionVersion).where(
        QuestionVersion.id.in_([uuid.UUID(i["qv"]) for i in items])))}
    ts = [1000]

    def nxt() -> int:
        ts[0] += 1
        return ts[0]

    async def put(answers: list[dict]):
        return await api.call(student, "PUT", f"/attempts/{tid}/answers", json={"answers": answers})

    async def answer_section(pos: int, upto: int, wrong: int, start: int = 0):
        sec = by_sec[pos]
        for k in range(start, upto, 20):
            batch = [{"position": i["position"], "client_ts": nxt(),
                      "response": response_for(qvs[i["qv"]], idx >= wrong)}
                     for idx, i in enumerate(sec[:upto]) if k <= idx < min(k + 20, upto)]
            r = await put(batch)
            assert r.status_code == 200, r.text
            assert r.json()["saved"] == [b["position"] for b in batch] and r.json()["stale"] == []

    # ---- section 1: the math_1 comparison card
    ahead = await api.call(student, "GET", f"/attempts/{tid}/content?section=2")
    assert ahead.status_code == 409 and ahead.json()["error"]["code"] == "section_not_current"
    content = await api.call(student, "GET", f"/attempts/{tid}/content?section=1")
    assert content.status_code == 200, content.text
    payload = content.json()
    sec1_q = [payload["questions"][i["qv"]] for i in by_sec[1]]
    assert all(q["type"] == "comparison" for q in sec1_q)
    for q in sec1_q:
        assert set(q["data"]) == {"column_a", "column_b"} and q["data"]["column_a"] and q["data"]["column_b"]
        assert "correct" not in json.dumps(q["data"]) and "explanation" not in q
    first = by_sec[1][0]
    p1 = first["position"]
    good = response_for(qvs[first["qv"]], True)
    assert good["choice"] in "ABCD"
    # autosave: saved, then an older client_ts is stale (the newer answer stays), then an invalid comparison answer
    r = await put([{"position": p1, "client_ts": 5000, "response": good}])
    assert r.status_code == 200 and r.json()["saved"] == [p1] and r.json()["stale"] == [], r.text
    r = await put([{"position": p1, "client_ts": 4000, "response": {"choice": "A" if good["choice"] != "A" else "B"}}])
    assert r.status_code == 200 and r.json()["saved"] == [] and r.json()["stale"] == [p1], r.text
    r = await put([{"position": p1, "client_ts": 6000, "response": {"choice": "E"}}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_response", r.text
    got = await api.call(student, "GET", f"/attempts/{tid}")
    assert next(i for i in got.json()["items"] if i["position"] == p1)["response"] == good
    ts[0] = 7000
    await answer_section(1, *PLAN[1])

    # ---- finish section 1 -> forward-only
    r = await api.call(student, "POST", f"/attempts/{tid}/sections/1/close")
    assert r.status_code == 200 and r.json()["current_section_pos"] == 2, r.text
    state = r.json()
    s2 = state["sections"][1]
    assert iso(state["sections"][0]["closed_at"]) == clk.t and iso(s2["started_at"]) == clk.t
    s2_deadline = iso(s2["deadline_at"])
    assert s2_deadline == clk.t + timedelta(minutes=OLD_MINUTES["math_2"])
    back = await put([{"position": p1, "client_ts": nxt(), "response": good}])
    assert back.status_code == 409 and back.json()["error"]["code"] == "section_closed", back.text
    reclose = await api.call(student, "POST", f"/attempts/{tid}/sections/1/close")
    # closing it again is idempotent (today: 200, nothing moves)
    assert reclose.status_code == 200 and reclose.json()["current_section_pos"] == 2, reclose.text[:300]
    assert reclose.json()["sections"] == state["sections"]

    # ---- section 2: timer boundary
    await answer_section(2, 20, 0)
    clk.t = s2_deadline + timedelta(seconds=grace - 1)   # past the deadline, inside the grace: still stored
    p21 = by_sec[2][20]
    r = await put([{"position": p21["position"], "client_ts": nxt(), "response": response_for(qvs[p21["qv"]], True)}])
    assert r.status_code == 200 and r.json()["saved"] == [p21["position"]], r.text
    clk.t = s2_deadline + timedelta(seconds=grace + 1)   # deadline + grace passed: refused, auto-advanced
    p22 = by_sec[2][21]
    late = await put([{"position": p22["position"], "client_ts": nxt(), "response": response_for(qvs[p22["qv"]], True)}])
    assert late.status_code == 409 and late.json()["error"]["code"] == "section_closed", late.text
    state = (await api.call(student, "GET", f"/attempts/{tid}")).json()
    assert state["current_section_pos"] == 3 and state["status"] == "in_progress"
    s2, s3 = state["sections"][1], state["sections"][2]
    assert iso(s2["closed_at"]) == s2_deadline
    assert iso(s3["started_at"]) == s2_deadline   # the next section starts at the previous deadline
    assert iso(s3["deadline_at"]) == s2_deadline + timedelta(minutes=OLD_MINUTES["analogies"])

    # ---- sections 3-5, submit with section 5 open
    for pos in (3, 4, 5):
        c = await api.call(student, "GET", f"/attempts/{tid}/content?section={pos}")
        assert c.status_code == 200, c.text
        await answer_section(pos, *PLAN[pos])
        if pos < 5:
            r = await api.call(student, "POST", f"/attempts/{tid}/sections/{pos}/close")
            assert r.status_code == 200 and r.json()["current_section_pos"] == pos + 1, r.text
    sub = await api.call(student, "POST", f"/attempts/{tid}/submit", json={})
    assert sub.status_code == 200 and sub.json()["status"] == "graded" and sub.json()["results_available"], sub.text
    resub = await api.call(student, "POST", f"/attempts/{tid}/submit", json={})
    assert resub.status_code == 200 and resub.json()["already_submitted"] is True, resub.text

    # ---- result
    res = await api.call(student, "GET", f"/attempts/{tid}/result")
    assert res.status_code == 200, res.text
    rj = res.json()
    assert RAW == 131
    assert D(str(rj["raw_score"])) == RAW and D(str(rj["points_possible"])) == N and rj["pending_review"] == 0
    rows = rj["sections"]
    assert [s["key"] for s in rows] == ORT_ORDER and [s["pos"] for s in rows] == [1, 2, 3, 4, 5]
    assert [(s["answered"], s["correct"]) for s in rows] == [(a_, a_ - w) for a_, w in PLAN.values()]
    assert [D(str(s["raw"])) for s in rows] == [D(a_ - w) for a_, w in PLAN.values()]
    assert all(D(str(s["possible"])) == 30 for s in rows)
    g = rj["grade"]
    assert g is not None and g["scheme_type"] == "piecewise_curve", rj
    scaled, pct = oracle(RAW)
    assert (scaled, pct) == (D("222"), D("99.2"))  # frozen oracle row for raw 131 of 150
    assert (D(str(g["display_value"])), D(str(g["percentile"]))) == (scaled, pct)
    assert g["thresholds"] == {"golden_certificate": True}  # scaled >= 219
    # review: keys after submit (ORT preset), the cut-off section-2 items unanswered
    rev = await api.call(student, "GET", f"/attempts/{tid}/review")
    assert rev.status_code == 200, rev.text
    ritems = {i["position"]: i for i in rev.json()["items"]}
    assert sum(1 for i in ritems.values() if i["correctness"] == "correct") == RAW
    assert [ritems[i["position"]]["correctness"] for i in by_sec[2][21:]] == ["unanswered"] * 9
    assert all(i.get("key") for i in ritems.values())


def test_golden_certificate_rule_at_the_boundary():
    """The golden certificate rule on the frozen oracle table: scaled >= 219, the boundary raw scores are frozen."""
    from app.lms.grading.seeds import ORT_MAIN_PARAMS

    assert [{"key": "golden_certificate", "min_value": 219}] == [
        {k: v for k, v in th.items() if k in ("key", "min_value")} for th in ORT_MAIN_PARAMS["thresholds"]]
    t = json.loads((FIXTURES / "ort_parity_main.json").read_text(encoding="utf-8"))
    scaled = [D(str(x)) for x in t["scaled"][str(N)]]
    first_golden = next(raw for raw, s in enumerate(scaled) if s >= 219)
    assert all(s < 219 for s in scaled[:first_golden]) and all(s >= 219 for s in scaled[first_golden:])
    assert (first_golden, scaled[first_golden - 1], scaled[first_golden]) == FROZEN_GOLDEN_BOUNDARY


FROZEN_GOLDEN_BOUNDARY = (129, D("218"), D("220"))  # raw 128 -> 218 (no certificate), raw 129 -> 220
