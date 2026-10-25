"""Phase 3 end-to-end exit test (design section 7, item 14): import an ORT bundle, build/validate/publish an ort_main
assessment, run students through it with a frozen clock (autosave, forward-only sections, leave and resume, lazy
expiry, grace), results and review policies, republish isolation, staff list and manual scoring. Every student
response is scanned for answer keys."""
import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.lms.content.models import BankQuestion, QuestionBank, QuestionVersion
from tests.lms.assessment_support import SENT_EXPL, SENT_RUBRIC, add_q, bump_version, get, mk, publish, section
from tests.lms.attempt_support import FrozenClock, frozen_clock  # noqa: F401
from tests.lms.content_support import world
from tests.lms.factories import enroll, make_bank, make_question, make_user
from tests.lms.files_support import local_storage  # noqa: F401
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_import_api import imp, zbytes

pytestmark = pytest.mark.usefixtures("local_storage")

SECTION_KEYS = ["math_1", "math_2", "analogies", "reading", "grammar"]
KEY_FIELDS = {"correct", "answers", "margin", "scoring", "case_sensitive", "rubric_note", "explanation"}  # "key" is also a section key; result sections carry a `correct` count
GRACE = 45


def walk(o, found):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in KEY_FIELDS:
                found.append(k)
            walk(v, found)
    elif isinstance(o, list):
        for v in o:
            walk(v, found)


def no_keys(res, *extra_tokens, fields=True):
    """Sentinel scan of a student response: no key-only field names and no sentinel strings anywhere."""
    found: list = []
    try:
        if fields:
            walk(res.json(), found)
    except Exception:
        pass
    assert not found, (res.request.url, found)
    for t in (SENT_EXPL, SENT_RUBRIC, *extra_tokens):
        assert t not in res.text, (res.request.url, t)


async def student(api, user, method, path, **kw):
    res = await api.call(user, method, path, **kw)
    if res.status_code < 300 and "/review" not in path:
        no_keys(res, fields=not path.endswith(("/result", "/submit")))
    return res


def correct_response(qv: QuestionVersion):
    d = qv.data
    if qv.type == "comparison":
        return {"choice": d["correct"]}
    assert qv.type == "single_choice", qv.type
    return {"choice_id": d["correct"]}


def wrong_response(qv: QuestionVersion):
    d = qv.data
    if qv.type == "comparison":
        return {"choice": next(c for c in "ABCD" if c != d["correct"])}
    return {"choice_id": next(c["id"] for c in d["choices"] if c["id"] != d["correct"])}


async def test_phase3_flow(db, api, frozen_clock):
    w = world(db, languages=("ru",))
    teacher, cid = w.O, w.cid
    w.course.template_key, w.course.template_version = "ort", 1; db.commit()  # Phase 6 S2b: ORT presets/import formats need the ORT course template
    s1, s2, s3 = make_user(db), make_user(db), make_user(db)
    for s in (s1, s2, s3):
        enroll(db, w.course, s, "student")

    # ---- 1. import the ORT bundle (150 questions) through the Phase 2 importer
    res = await imp(teacher, cid, zbytes(), exam_type="full_main")
    assert res.status_code == 200, res.text
    bank_id = res.json()["banks"][0]["bank_id"]
    db.expire_all()
    qvs = {}  # question id -> current version
    for q in db.scalars(select(BankQuestion).where(BankQuestion.bank_id == uuid.UUID(bank_id))):
        qvs[q.id] = db.get(QuestionVersion, q.current_version_id)
    assert len(qvs) == 150

    # ---- 2. build: ort_main preset, bulk add per section
    a = await mk(api, teacher, cid, title={"ru": "ОРТ"}, preset="ort_main", languages=["ru"])
    assert [s["key"] for s in a["sections"]] == SECTION_KEYS
    aid = a["id"]
    base = f"/courses/{cid}/assessments/{aid}"
    for sec in a["sections"]:
        r = await api.call(teacher, "POST", f"{base}/sections/{sec['id']}/items/bulk",
                           json={"bank_id": bank_id, "filter": {"section": sec["key"]}, "group_passages": True})
        assert r.status_code == 200, (sec["key"], r.text)
        assert r.json()["added"] == 30 and r.json()["skipped"] == []
    # comparison only in math_1: a single_choice question is rejected there
    extra_bank = make_bank(db, w.course, teacher)
    sc_qid = make_question(db, extra_bank, teacher, "single_choice", language="ru", stem="extra").id
    r = await api.call(teacher, "POST", f"{base}/sections/{a['sections'][0]['id']}/items",
                       json={"kind": "question", "question_id": str(sc_qid)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "item_type_not_allowed"

    v = await api.call(teacher, "POST", f"{base}/validate")
    assert v.status_code == 200 and v.json()["errors"] == [], v.text
    # student cannot see an unpublished assessment
    assert (await api.call(s1, "GET", base)).status_code == 404
    pub = await publish(api, teacher, cid, aid)
    assert pub.status_code == 200, pub.text
    assert pub.json()["version"]["version_no"] == 1 and pub.json()["version"]["item_count"] == 150
    assert Decimal(str(pub.json()["version"]["points_possible"])) == 150
    v1_id = pub.json()["version"]["id"]

    # ---- 3. S1: lobby, start, autosave in section 1
    lobby = await student(api, s1, "GET", base)
    assert lobby.status_code == 200 and lobby.json()["can_start"] is True
    st = await student(api, s1, "POST", f"{base}/attempts", json={"language": "ru"})
    assert st.status_code == 201, st.text
    state = st.json()
    t1 = state["id"]
    assert state["version_id"] == v1_id and state["navigation"] == "section_forward_only"
    assert state["current_section_pos"] == 1 and len(state["items"]) == 150
    # forward-only: content is served one section at a time (review finding 7)
    assert state["content_url"] == f"/attempts/{t1}/content?section=1"
    content = await student(api, s1, "GET", state["content_url"])
    assert content.status_code == 200
    items = {i["position"]: i for i in state["items"]}
    qv_of = {str(v.id): v for v in qvs.values()}
    sec1 = [p for p, i in items.items() if i["section_pos"] == 1]
    assert len(sec1) == 30
    later_qvs = {i["qv"] for i in state["items"] if i["section_pos"] > 1}
    assert {items[p]["qv"] for p in sec1} <= set(content.json()["questions"]) | set(state["extra_questions"] or {})
    assert not later_qvs & set(content.json()["questions"])
    ahead = await student(api, s1, "GET", f"/attempts/{t1}/content?section=2")
    assert ahead.status_code == 409 and ahead.json()["error"]["code"] == "section_not_current"
    ts = 1000
    answers = []
    for p in sec1[:10]:
        ts += 1
        answers.append({"position": p, "response": correct_response(qv_of[items[p]["qv"]]), "client_ts": ts})
    sv = await student(api, s1, "PUT", f"/attempts/{t1}/answers", json={"answers": answers})
    assert sv.status_code == 200 and sorted(sv.json()["saved"]) == sorted(sec1[:10]), sv.text

    # ---- 4. section 1 deadline passes (+ grace): lazy forward-only advance; leave and resume
    sec1_deadline = state["sections"][0]["deadline_at"]
    frozen_clock.advance(2700 + GRACE + 1)
    rs = await student(api, s1, "GET", f"/attempts/{t1}")
    assert rs.status_code == 200
    rj = rs.json()
    assert rj["id"] == t1 and rj["current_section_pos"] == 2 and rj["status"] == "in_progress"
    assert rj["sections"][0]["closed_at"] is not None and rj["sections"][1]["started_at"] == sec1_deadline
    assert rj["content_url"] == f"/attempts/{t1}/content?section=2"
    c2 = await student(api, s1, "GET", rj["content_url"])
    assert c2.status_code == 200 and c2.json()["section_pos"] == 2
    saved = {i["position"]: i["response"] for i in rj["items"] if i["response"]}
    assert saved == {p: a_["response"] for p, a_ in zip(sec1[:10], answers)}
    # answering the closed section 1 is refused
    late = await student(api, s1, "PUT", f"/attempts/{t1}/answers",
                         json={"answers": [{"position": sec1[11], "response": {"choice": "A"}, "client_ts": 5000}]})
    assert late.status_code == 409 and late.json()["error"]["code"] == "section_closed"
    # answer section 2 (all correct), "close the tab", resume later
    sec2 = [p for p, i in items.items() if i["section_pos"] == 2]
    ts = 6000
    batch = []
    for p in sec2:
        ts += 1
        batch.append({"position": p, "response": correct_response(qv_of[items[p]["qv"]]), "client_ts": ts})
    for k in range(0, len(batch), 20):
        r = await student(api, s1, "PUT", f"/attempts/{t1}/answers", json={"answers": batch[k:k + 20]})
        assert r.status_code == 200, r.text
    frozen_clock.advance(600)
    resumed = await student(api, s1, "POST", f"{base}/attempts", json={"language": "ru"})
    assert resumed.status_code == 200 and resumed.json()["id"] == t1
    assert sum(1 for i in resumed.json()["items"] if i["response"]) == 40
    # the lobby now shows the in-progress attempt
    lobby = await student(api, s1, "GET", base)
    assert lobby.json()["in_progress_attempt_id"] == t1

    # ---- 5. close section 2, answer sections 3-5 (wrong answers in 3), submit
    cl = await student(api, s1, "POST", f"/attempts/{t1}/sections/2/close")
    assert cl.status_code == 200 and cl.json()["current_section_pos"] == 3
    again = await student(api, s1, "POST", f"/attempts/{t1}/sections/2/close")  # retry: idempotent
    assert again.status_code == 200 and again.json()["current_section_pos"] == 3
    future = await student(api, s1, "POST", f"/attempts/{t1}/sections/4/close")
    assert future.status_code == 409 and future.json()["error"]["code"] == "section_not_current"
    expected = {1: 10, 2: 30, 3: 0, 4: 30, 5: 30}
    for pos in (3, 4, 5):
        ps = [p for p, i in items.items() if i["section_pos"] == pos]
        ts += 1000
        for k in range(0, len(ps), 20):
            chunk = []
            for p in ps[k:k + 20]:
                ts += 1
                qv = qv_of[items[p]["qv"]]
                chunk.append({"position": p, "client_ts": ts,
                              "response": wrong_response(qv) if pos == 3 else correct_response(qv)})
            r = await student(api, s1, "PUT", f"/attempts/{t1}/answers", json={"answers": chunk})
            assert r.status_code == 200, r.text
        if pos < 5:
            r = await student(api, s1, "POST", f"/attempts/{t1}/sections/{pos}/close")
            assert r.status_code == 200
    last = await student(api, s1, "POST", f"/attempts/{t1}/sections/5/close")
    assert last.status_code == 409 and last.json()["error"]["code"] == "use_submit"
    # before submit: no results, no review
    for path in ("result", "review"):
        r = await api.call(s1, "GET", f"/attempts/{t1}/{path}")
        assert r.status_code == 403 and r.json()["error"]["code"] == "results_not_available"
    sub = await student(api, s1, "POST", f"/attempts/{t1}/submit", json={})
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "graded" and sub.json()["results_available"] is True
    sub2 = await student(api, s1, "POST", f"/attempts/{t1}/submit", json={})
    assert sub2.status_code == 200 and sub2.json()["already_submitted"] is True

    res_ = await student(api, s1, "GET", f"/attempts/{t1}/result")
    assert res_.status_code == 200
    rj = res_.json()
    assert Decimal(str(rj["raw_score"])) == sum(expected.values()) and Decimal(str(rj["points_possible"])) == 150
    assert {s["key"]: s["correct"] for s in rj["sections"]} == dict(zip(SECTION_KEYS, expected.values()))
    assert all(Decimal(str(s["possible"])) == 30 for s in rj["sections"])
    rev = await api.call(s1, "GET", f"/attempts/{t1}/review")
    assert rev.status_code == 200
    ritems = rev.json()["items"]
    assert len(ritems) == 150 and all("key" in i for i in ritems)
    by_sec = {}
    for i in ritems:
        assert i["key"], i
        by_sec[i["section_pos"]] = by_sec.get(i["section_pos"], 0) + (1 if i["correctness"] == "correct" else 0)
    assert by_sec == {k: v for k, v in expected.items()}

    # ---- 6. S2 starts on v1, teacher edits a question and republishes -> S2 keeps v1
    st2 = await student(api, s2, "POST", f"{base}/attempts", json={"language": "ru"})
    assert st2.status_code == 201
    t2 = st2.json()["id"]
    i2 = {i["position"]: i for i in st2.json()["items"]}
    p_math2 = next(p for p, i in i2.items() if i["section_pos"] == 1)
    qv_old = i2[p_math2]["qv"]
    q_obj = db.scalar(select(BankQuestion).where(BankQuestion.current_version_id == uuid.UUID(qv_old)))
    first2 = [p for p, i in i2.items() if i["section_pos"] == 1][:3]
    await student(api, s2, "PUT", f"/attempts/{t2}/answers", json={"answers": [
        {"position": p, "response": correct_response(qv_of[i2[p]["qv"]]), "client_ts": 10 + p} for p in first2]})
    bump_version(db, q_obj, stem="EDITED STEM", actor=teacher)
    pub2 = await publish(api, teacher, cid, aid)
    assert pub2.status_code in (200, 409), pub2.text
    if pub2.status_code == 409:
        assert pub2.json()["error"]["code"] == "confirm_required"
        det = pub2.json()["error"].get("details") or {}
        assert det.get("in_progress") == 1
        pub2 = await publish(api, teacher, cid, aid, confirm=True)
        assert pub2.status_code == 200, pub2.text
    assert pub2.json()["version"]["version_no"] == 2 and pub2.json()["unchanged"] is False
    st2b = await student(api, s2, "GET", f"/attempts/{t2}")
    assert st2b.json()["version_id"] == v1_id
    assert {i["position"]: i["qv"] for i in st2b.json()["items"]}[p_math2] == qv_old
    # a new start (S3) gets v2
    st3 = await student(api, s3, "POST", f"{base}/attempts", json={"language": "ru"})
    assert st3.status_code == 201 and st3.json()["version_id"] == pub2.json()["version"]["id"]

    # ---- 7. S2 abandons; whole attempt deadline + grace passes -> lazy expiry finalizes on read
    frozen_clock.advance(13200 + 2 * GRACE)
    exp = await student(api, s2, "GET", f"/attempts/{t2}")
    assert exp.status_code == 200 and exp.json()["status"] == "graded"
    r2 = await student(api, s2, "GET", f"/attempts/{t2}/result")
    assert r2.status_code == 200
    assert Decimal(str(r2.json()["raw_score"])) == 3 and Decimal(str(r2.json()["points_possible"])) == 150
    late = await student(api, s2, "PUT", f"/attempts/{t2}/answers",
                         json={"answers": [{"position": 1, "response": {"choice": "A"}, "client_ts": 99999}]})
    assert late.status_code == 409 and late.json()["error"]["code"] == "attempt_closed"

    # ---- 8. staff list: both attempts, S3 in progress finalized lazily; no preview rows
    lst = await api.call(teacher, "GET", f"{base}/attempts")
    assert lst.status_code == 200, lst.text
    rows = {r["id"]: r for r in lst.json()["items"]}
    assert rows[t1]["status"] == "graded" and rows[t2]["status"] == "graded"
    assert rows[t1]["submit_reason"] == "manual" and rows[t2]["submit_reason"] in ("timeout", "sweep")
    assert all(r["is_preview"] is False for r in rows.values())
    det = await api.call(teacher, "GET", f"/courses/{cid}/attempts/{t1}")
    assert det.status_code == 200 and all("key" in i for i in det.json()["items"])
    assert (await api.call(s1, "GET", f"{base}/attempts")).status_code == 403

    # ---- 9. essay quiz with results_policy never, manual scoring
    bank = make_bank(db, w.course, teacher)
    essay = make_question(db, bank, teacher, "essay", data={"word_limit": 100, "rubric_note": SENT_RUBRIC},
                          language="ru", stem="essay stem", explanation=SENT_EXPL, default_points=Decimal("10"))
    scq = make_question(db, bank, teacher, "single_choice", language="ru", stem="sc stem", explanation=SENT_EXPL,
                        data={"choices": [{"id": "A", "text": "1"}, {"id": "B", "text": "2"}], "correct": "B"})
    b = await mk(api, teacher, cid, title={"ru": "Эссе"}, languages=["ru"])
    sec = await section(api, teacher, cid, b["id"])
    for q in (scq, essay):
        await add_q(api, teacher, cid, b["id"], sec["id"], q.id)
    r = await api.call(teacher, "PATCH", f"/courses/{cid}/assessments/{b['id']}",
                       json={"draft_rev": (await get(api, teacher, cid, b["id"]))["draft_rev"],
                             "results_policy": "never"})
    assert r.status_code == 200, r.text
    assert (await publish(api, teacher, cid, b["id"])).status_code == 200
    bb = f"/courses/{cid}/assessments/{b['id']}"
    sta = await student(api, s1, "POST", f"{bb}/attempts", json={"language": "ru"})
    assert sta.status_code == 201, sta.text
    ta = sta.json()["id"]
    pos = {i["qv"]: i["position"] for i in sta.json()["items"]}
    await student(api, s1, "PUT", f"/attempts/{ta}/answers", json={"answers": [
        {"position": pos[str(scq.current_version_id)], "response": {"choice_id": "B"}, "client_ts": 1},
        {"position": pos[str(essay.current_version_id)], "response": {"text": "an essay"}, "client_ts": 2}]})
    sub = await student(api, s1, "POST", f"/attempts/{ta}/submit", json={})
    assert sub.status_code == 200 and sub.json()["status"] == "needs_review"
    assert sub.json()["results_available"] is False and not sub.json().get("result")
    for path in ("result", "review"):
        r = await api.call(s1, "GET", f"/attempts/{ta}/{path}")
        assert r.status_code == 403 and r.json()["error"]["code"] == "results_not_available"
    stf = await api.call(teacher, "GET", f"/courses/{cid}/attempts/{ta}")
    assert stf.status_code == 200
    ep = pos[str(essay.current_version_id)]
    r = await api.call(teacher, "PUT", f"/courses/{cid}/attempts/{ta}/items/{ep}/score",
                       json={"points": 7, "feedback": "good"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "graded" and Decimal(str(r.json()["raw_score"])) == 8
    lst = await api.call(teacher, "GET", f"{bb}/attempts")
    assert lst.json()["items"][0]["status"] == "graded" and lst.json()["items"][0]["pending_review"] == 0
