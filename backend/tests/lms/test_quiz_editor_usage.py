"""Phase 7c S2: "used in N quizzes" (PHASE_7C_DESIGN 5.5, P7C-5, 10)."""
from app.lms.assessments.models import AssessmentItem
from tests.lms.assessment_support import publish
from tests.lms.factories import (
    make_assessment, make_assessment_version, make_item, make_passage, make_question, make_section,
)
from tests.lms.quiz_editor_support import A, Q, commit, edit_card, quiz_world, staff_payload
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _quiz(db, w, title):
    a = make_assessment(db, w.course, w.O, title={"en": title}, languages=["en"])
    return a, make_section(db, a, rules={})


async def _usage(api, w, qid, **params):
    r = await api.call(w.O, "GET", f"{Q(w, qid)}/usage", params=params or None)
    assert r.status_code == 200, r.text
    return r.json()


async def test_counts_distinct_live_assessments_excluding_deleted_and_picks(db, api):
    w = quiz_world(db, link=True)
    make_item(db, w.quiz2, w.s2, question=w.q1, position=1)
    c, sc = _quiz(db, w, "Quiz C")
    make_item(db, c, sc, question=w.q1, position=1)
    assert (await api.call(w.O, "DELETE", f"/courses/{w.cid}/assessments/{c.id}")).status_code == 204
    d, sd = _quiz(db, w, "Quiz D")
    make_item(db, d, sd, kind="pick", pick_bank_id=w.shared.id, pick_count=1, pick_filter={}, position=1)
    u = await _usage(api, w, w.q1.id)
    assert u["other_count"] == 2 and {x["id"] for x in u["assessments"]} == {w.aid, w.aid2}
    assert u["published_anywhere"] is False
    u = await _usage(api, w, w.q1.id, assessment_id=w.aid)
    assert u["other_count"] == 1 and u["assessments"][0]["id"] == w.aid and u["assessments"][0]["is_this"] is True
    assert u["assessments"][1]["status"] == "draft"


async def test_passage_children_count(db, api):
    w = quiz_world(db)
    p = make_passage(db, w.shared, w.O)
    q = make_question(db, w.shared, w.O, passage_id=p.id)
    h = make_item(db, w.quiz2, w.s2, passage=p, position=1)
    make_item(db, w.quiz2, w.s2, question=q, parent=h, position=1)
    u = await _usage(api, w, q.id, assessment_id=w.aid)
    assert u["other_count"] == 1 and u["assessments"][0]["id"] == w.aid2


async def test_published_anywhere_is_exact_after_repoint(db, api):
    w = quiz_world(db, link=True)
    make_item(db, w.quiz2, w.s2, question=w.q1, position=1)
    assert (await publish(api, w.O, w.cid, w.aid)).status_code == 200
    assert (await _usage(api, w, w.q1.id))["published_anywhere"] is True
    d, r = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, stem="mine only"))
    r = await commit(api, w, d["id"], d["draft_rev"], scope="this")
    assert r.status_code == 200, r.text
    new_qid = r.json()["question"]["id"]
    assert (await _usage(api, w, w.q1.id))["published_anywhere"] is True     # A's snapshot still pins q1
    fresh = await _usage(api, w, new_qid)
    assert fresh["published_anywhere"] is False and fresh["other_count"] == 1  # used by A only (not this-marked)
    assert (await _usage(api, w, new_qid, assessment_id=w.aid))["other_count"] == 0


async def test_preview_versions_are_ignored(db, api):
    w = quiz_world(db, link=True)
    snap = {"schema": 1, "languages": ["en"], "sections": [],
            "slots": {"en": [{"slot": 1, "section_pos": 1, "item_id": str(w.items[0].id), "kind": "question",
                              "qv": str(w.q1.current_version_id)}]}}
    make_assessment_version(db, w.quiz, w.O, kind="preview", snapshot=snap, publish=False)
    assert (await _usage(api, w, w.q1.id))["published_anywhere"] is False


async def test_quiz_get_shows_bank_kind_and_used_elsewhere(db, api):
    w = quiz_world(db, link=True)
    make_item(db, w.quiz2, w.s2, question=w.q1, position=1)
    c, sc = _quiz(db, w, "Quiz C")
    make_item(db, c, sc, question=w.q1, position=1)
    r = await api.call(w.O, "POST", f"{A(w)}/questions", json={"payload": staff_payload(db, w.q2, stem="own")})
    assert r.status_code == 201
    g = (await api.call(w.O, "GET", A(w))).json()
    qs = {i["id"]: i["question"] for i in g["sections"][0]["items"]}
    assert qs[str(w.items[0].id)]["used_elsewhere"] == 2 and qs[str(w.items[0].id)]["bank_kind"] == "shared"
    assert qs[str(w.items[1].id)]["used_elsewhere"] == 0
    assert qs[r.json()["item"]["id"]]["bank_kind"] == "quiz" and qs[r.json()["item"]["id"]]["used_elsewhere"] == 0
    assert AssessmentItem


async def test_commit_scans_published_snapshots_only_for_a_type_change(db, api, monkeypatch):
    """Phase 7c fix1 (M3): content / meta commits never call `published_pins`; a type change calls it once, and not
    at all when the cheap checks (used elsewhere) already force `this`."""
    from app.lms.quiz_editor import usage
    from tests.lms.quiz_editor_support import quiz_question

    calls = []
    real = usage.published_pins
    monkeypatch.setattr(usage, "published_pins", lambda *a, **k: calls.append(1) or real(*a, **k))
    w = quiz_world(db, link=True)
    make_item(db, w.quiz2, w.s2, question=w.q2, position=1)
    assert (await publish(api, w.O, w.cid, w.aid)).status_code == 200
    item, q = await quiz_question(api, db, w)
    _, r = await edit_card(api, w, item, staff_payload(db, q, stem="content only"))
    assert r.status_code == 200 and r.json()["applied"] == "in_place", r.text
    p = staff_payload(db, w.q1)
    p["meta"] = {**p["meta"], "tags": ["t"]}
    _, r = await edit_card(api, w, w.items[0], p)
    assert r.status_code == 200 and r.json()["applied"] == "in_place", r.text
    assert calls == []
    tf = {"type": "true_false", "data": {"correct": True}}
    _, r = await edit_card(api, w, w.items[1], staff_payload(db, w.q2, **tf))  # used in quiz B: forced, no scan
    assert r.status_code == 200 and r.json()["applied"] == "this", r.text
    assert calls == []
    _, r = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, **tf))  # published in quiz A: one scan
    assert r.status_code == 200 and r.json()["applied"] == "this", r.text
    assert calls == [1]
    # GET /usage still reports it
    assert (await _usage(api, w, w.q1.id))["published_anywhere"] is True


async def test_published_pins_pages_through_published_quizzes(db, api, monkeypatch):
    """M3 bound: published snapshots are read a page of assessments at a time; a pin on a later page is found."""
    from app.lms.quiz_editor import usage

    monkeypatch.setattr(usage, "_PIN_PAGE", 1)
    w = quiz_world(db)
    for title in ("P1", "P2", "P3"):
        a, s = _quiz(db, w, title)
        make_item(db, a, s, question=w.q2, position=1)
        assert (await publish(api, w.O, w.cid, str(a.id))).status_code == 200
    assert usage.published_pins(db, w.course.id, w.q1) is False
    assert usage.published_pins(db, w.course.id, w.q2) is True
    a, s = _quiz(db, w, "P4")
    make_item(db, a, s, question=w.q1, position=1)
    assert (await publish(api, w.O, w.cid, str(a.id))).status_code == 200
    assert usage.published_pins(db, w.course.id, w.q1) is True
