"""Phase 7c S2: publishing with unfinished drafts (PHASE_7C_DESIGN 5.8, P7C-3, invariant 4.3, 10)."""
import uuid

from sqlalchemy import select

from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.attempts.models import AttemptItem
from app.lms.content.models import BankQuestion
from tests.lms.assessment_support import publish
from tests.lms.quiz_editor_support import A, commit, edit_card, new_draft, quiz_world, staff_payload
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _published_qvs(db, aid) -> list[str]:
    db.expire_all()
    a = db.get(Assessment, uuid.UUID(str(aid)))
    snap = db.get(AssessmentVersion, a.published_version_id).snapshot
    return [s["qv"] for s in snap["slots"]["en"]]


async def test_unfinished_drafts_warn_and_publish_pins_current_versions(db, api):
    w = quiz_world(db, link=True)
    d_item = (await new_draft(api, w, item_id=str(w.items[0].id), payload=staff_payload(db, w.q1, stem="later"))).json()
    d_new = (await new_draft(api, w)).json()
    v = await api.call(w.O, "POST", f"{A(w)}/validate")
    assert v.status_code == 200, v.text
    drafts = [x for x in v.json()["warnings"] if x["code"] == "unfinished_drafts"]
    assert {x["item_id"] for x in drafts} == {str(w.items[0].id), None}
    assert all(x["section_pos"] == 1 for x in drafts) and v.json()["errors"] == []
    r = await publish(api, w.O, w.cid, w.aid)
    assert r.status_code == 200, r.text
    assert _published_qvs(db, w.aid) == [str(w.q1.current_version_id), str(w.q2.current_version_id)]
    g = (await api.call(w.O, "GET", A(w))).json()
    assert {x["id"] for x in g["drafts"]} == {d_item["id"], d_new["id"]}  # drafts stay for later


async def test_running_attempt_unaffected_by_later_commits_republish_picks_new(db, api):
    w = quiz_world(db, link=True)
    make_b = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{w.aid2}/sections/{w.s2.id}/items",
                            json={"kind": "question", "question_id": str(w.q2.id)})
    assert make_b.status_code == 201  # q2 used in quiz B as well: `this` / `all` both reachable
    assert (await publish(api, w.O, w.cid, w.aid)).status_code == 200
    v_q1, v_q2 = str(w.q1.current_version_id), str(w.q2.current_version_id)
    start = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{w.aid}/attempts", json={})
    assert start.status_code in (200, 201), start.text
    att_id = uuid.UUID(start.json()["attempt_id"] if "attempt_id" in start.json() else start.json()["id"])
    # in place (q1: quiz A only) and `this` (q2: also in quiz B)
    _, r = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, stem="edited after start"))
    assert r.status_code == 200 and r.json()["applied"] == "in_place"
    d, r = await edit_card(api, w, w.items[1], staff_payload(db, w.q2, stem="only in A now"))
    r = await commit(api, w, d["id"], d["draft_rev"], scope="this")
    assert r.status_code == 200 and r.json()["applied"] == "this"
    db.expire_all()
    pinned = sorted(str(x) for x in db.execute(select(AttemptItem.question_version_id).where(
        AttemptItem.attempt_id == att_id)).scalars())
    assert pinned == sorted([v_q1, v_q2])
    assert _published_qvs(db, w.aid) == [v_q1, v_q2]
    rep = await publish(api, w.O, w.cid, w.aid, confirm=True)
    assert rep.status_code == 200, rep.text
    new_q2 = db.get(BankQuestion, uuid.UUID(r.json()["question"]["id"]))
    q1 = db.get(BankQuestion, w.q1.id)
    assert _published_qvs(db, w.aid) == [str(q1.current_version_id), str(new_q2.current_version_id)]
    assert str(q1.current_version_id) != v_q1
