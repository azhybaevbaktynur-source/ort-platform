"""Phase 7c S2: card drafts (PHASE_7C_DESIGN 5.2, 7, 10): create / autosave / conflict / discard, payload checks,
drafts never become versions or snapshot content, item and section deletes take their drafts along."""
import uuid

from sqlalchemy import func, select

from app.lms.assessments.models import Assessment, AssessmentSection
from app.lms.assessments.snapshot import build_snapshot, canonical_hash
from app.lms.content.models import QuestionVersion
from app.lms.core import clock
from app.lms.quiz_editor.models import QuestionDraft
from tests.lms.factories import make_item, make_section
from tests.lms.quiz_editor_support import (
    A, card, commit, err, new_draft, put_draft, quiz_world, staff_payload,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _rev(db, a) -> int:
    db.expire_all()
    return db.get(Assessment, a.id).draft_rev


async def test_new_card_and_existing_card_drafts(db, api):
    w = quiz_world(db, link=True)
    rev0 = _rev(db, w.quiz)
    r = await new_draft(api, w)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["item_id"] is None and d["section_id"] == str(w.s1.id) and d["after_item_id"] is None
    assert d["draft_rev"] == 1 and d["base_version_id"] is None and d["payload"]["stem"] == "What is 2 + 2?"
    assert d["updated_by_name"]
    r = await new_draft(api, w, item_id=str(w.items[0].id), payload=staff_payload(db, w.q1))
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["item_id"] == str(w.items[0].id) and e["base_version_id"] == str(w.q1.current_version_id)
    # one draft per card: the second open gets the existing one back
    again = await new_draft(api, w, user=w.T, item_id=str(w.items[0].id))
    assert again.status_code == 409 and err(again) == "draft_exists"
    assert again.json()["error"]["details"]["id"] == e["id"]
    assert _rev(db, w.quiz) == rev0  # drafts are not quiz structure (P7C-2)
    # the staff GET lists them; the item shows has_draft
    g = (await api.call(w.O, "GET", A(w))).json()
    assert {x["id"] for x in g["drafts"]} == {d["id"], e["id"]}
    flags = {i["id"]: i["has_draft"] for i in g["sections"][0]["items"]}
    assert flags == {str(w.items[0].id): True, str(w.items[1].id): False}


async def test_new_card_position_hint_and_modes(db, api):
    w = quiz_world(db, link=True)
    r = await new_draft(api, w, after_item_id=str(w.items[0].id))
    assert r.status_code == 201 and r.json()["after_item_id"] == str(w.items[0].id)
    other = make_section(db, w.quiz, rules={})
    bad = await new_draft(api, w, section_id=str(other.id), after_item_id=str(w.items[0].id))
    assert bad.status_code == 422
    missing = await new_draft(api, w, after_item_id=str(uuid.uuid4()))
    assert missing.status_code == 404 and err(missing) == "item_not_found"
    both = await new_draft(api, w, item_id=str(w.items[0].id), section_id=str(w.s1.id))
    assert both.status_code == 422
    foreign_section = await new_draft(api, w, section_id=str(w.s2.id))  # quiz B's section
    assert foreign_section.status_code == 404 and err(foreign_section) == "section_not_found"


async def test_default_section_created_lazily(db, api):
    w = quiz_world(db, sections=False)
    rev0 = _rev(db, w.quiz)
    r = await new_draft(api, w)
    assert r.status_code == 201, r.text
    secs = db.execute(select(AssessmentSection).where(AssessmentSection.assessment_id == w.quiz.id)).scalars().all()
    assert len(secs) == 1 and (secs[0].key, secs[0].title, secs[0].time_limit_s, secs[0].rules) == (None, None, None, {})
    assert r.json()["section_id"] == str(secs[0].id)
    assert _rev(db, w.quiz) == rev0 + 1  # the section is structure
    r2 = await new_draft(api, w)
    assert r2.json()["section_id"] == str(secs[0].id) and _rev(db, w.quiz) == rev0 + 1


async def test_autosave_bumps_draft_rev_only_and_never_versions(db, api):
    w = quiz_world(db, link=True)
    d = (await new_draft(api, w, item_id=str(w.items[0].id), payload=staff_payload(db, w.q1))).json()
    versions = db.scalar(select(func.count()).select_from(QuestionVersion))
    rev0 = _rev(db, w.quiz)
    rev = d["draft_rev"]
    for i in range(50):
        r = await put_draft(api, w, d["id"], rev, card(stem=f"typing {i}"))
        assert r.status_code == 200, r.text
        assert r.json()["draft_rev"] == rev + 1 and r.json()["payload"]["stem"] == f"typing {i}"
        rev += 1
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(QuestionVersion)) == versions  # test_drafts_never_version
    assert _rev(db, w.quiz) == rev0


async def test_stale_rev_gets_the_winners_state(db, api):
    w = quiz_world(db)
    d = (await new_draft(api, w)).json()
    win = await put_draft(api, w, d["id"], 1, card(stem="winner"), user=w.T)
    assert win.status_code == 200 and win.json()["draft_rev"] == 2
    lose = await put_draft(api, w, d["id"], 1, card(stem="loser"))
    assert lose.status_code == 409 and err(lose) == "draft_conflict"
    det = lose.json()["error"]["details"]
    assert det["draft_rev"] == 2 and det["payload"]["stem"] == "winner"
    assert det["updated_by_name"] == (w.T.display_name or w.T.email)
    db.expire_all()
    assert db.get(QuestionDraft, uuid.UUID(d["id"])).payload["stem"] == "winner"


async def test_payload_checks(db, api):
    w = quiz_world(db)
    big = await new_draft(api, w, payload=card(data={"blob": "x" * 300_000}))
    assert big.status_code == 413 and err(big) == "payload_too_large"
    d = (await new_draft(api, w, payload=card(data={}, stem=""))).json()  # half-typed cards are fine
    assert d["payload"]["data"] == {}
    big2 = await put_draft(api, w, d["id"], 1, card(data={"blob": "x" * 300_000}))
    assert big2.status_code == 413
    typ = await new_draft(api, w, payload=card(type="drawing"))
    assert typ.status_code == 422 and err(typ) == "unsupported_type"
    lang = await new_draft(api, w, payload=card(language="ru"))  # quiz A is en only
    assert lang.status_code == 422 and err(lang) == "item_language_mismatch"
    lang2 = await put_draft(api, w, d["id"], 1, card(language="ru"))
    assert lang2.status_code == 422 and err(lang2) == "item_language_mismatch"
    extra = await new_draft(api, w, payload={**card(), "unknown": 1})
    assert extra.status_code == 422


async def test_delete_is_idempotent_and_late_autosave_is_404(db, api):
    w = quiz_world(db)
    d = (await new_draft(api, w)).json()
    url = f"{A(w)}/drafts/{d['id']}"
    assert (await api.call(w.O, "DELETE", url)).status_code == 204
    assert (await api.call(w.O, "DELETE", url)).status_code == 204
    late = await put_draft(api, w, d["id"], 1)
    assert late.status_code == 404 and err(late) == "draft_not_found"
    assert (await commit(api, w, d["id"], 1)).status_code == 404


async def test_done_racing_autosave(db, api):
    w = quiz_world(db)
    d = (await new_draft(api, w)).json()
    r = await put_draft(api, w, d["id"], 1, card(stem="v2"))
    assert r.json()["draft_rev"] == 2
    stale = await commit(api, w, d["id"], 1)  # an autosave landed after the client's last known rev
    assert stale.status_code == 409 and err(stale) == "draft_conflict"
    assert stale.json()["error"]["details"]["draft_rev"] == 2
    ok = await commit(api, w, d["id"], 2)
    assert ok.status_code == 200, ok.text
    late = await put_draft(api, w, d["id"], 2, card(stem="v3"))
    assert late.status_code == 404 and err(late) == "draft_not_found"


async def test_drafts_never_reach_the_snapshot(db, api):
    w = quiz_world(db, link=True)
    before, issues = build_snapshot(db, db.get(Assessment, w.quiz.id), now=clock.now())
    await new_draft(api, w)
    await new_draft(api, w, item_id=str(w.items[0].id), payload=staff_payload(db, w.q1, stem="changed"))
    db.expire_all()
    after, _ = build_snapshot(db, db.get(Assessment, w.quiz.id), now=clock.now())
    assert canonical_hash(before) == canonical_hash(after)


async def test_item_and_section_delete_remove_drafts(db, api):
    w = quiz_world(db, link=True)
    d_item = (await new_draft(api, w, item_id=str(w.items[0].id), payload=staff_payload(db, w.q1))).json()
    d_after = (await new_draft(api, w, after_item_id=str(w.items[0].id))).json()
    r = await api.call(w.O, "DELETE", f"{A(w)}/items/{w.items[0].id}")
    assert r.status_code == 204, r.text
    db.expire_all()
    assert db.get(QuestionDraft, uuid.UUID(d_item["id"])) is None
    assert db.get(QuestionDraft, uuid.UUID(d_after["id"])).after_item_id is None  # hint cleared: end of section
    gone = await put_draft(api, w, d_item["id"], 1)
    assert gone.status_code == 404 and err(gone) == "draft_not_found"
    # a section with only new-card drafts can be deleted; the drafts go with it
    s2 = make_section(db, w.quiz, rules={})
    d_sec = (await new_draft(api, w, section_id=str(s2.id))).json()
    r = await api.call(w.O, "DELETE", f"{A(w)}/sections/{s2.id}")
    assert r.status_code == 204, r.text
    db.expire_all()
    assert db.get(QuestionDraft, uuid.UUID(d_sec["id"])) is None


async def test_passage_header_delete_removes_child_drafts(db, api):
    from tests.lms.factories import make_passage, make_question

    w = quiz_world(db)
    p = make_passage(db, w.shared, w.O)
    q = make_question(db, w.shared, w.O, passage_id=p.id)
    header = make_item(db, w.quiz, w.s1, passage=p, position=1)
    child = make_item(db, w.quiz, w.s1, question=q, parent=header, position=1)
    d = (await new_draft(api, w, item_id=str(child.id), payload=staff_payload(db, q))).json()
    assert (await api.call(w.O, "DELETE", f"{A(w)}/items/{header.id}")).status_code == 204
    db.expire_all()
    assert db.get(QuestionDraft, uuid.UUID(d["id"])) is None


async def test_template_upgrade_removes_drafts_of_dropped_sections(db, api):
    from tests.lms.test_exam_templates_api import create_from, published_template, tworld
    from tests.lms.test_template_upgrade import V1, V3, _bump

    w = tworld(db)
    t = await published_template(api, w.PA, spec=V1)
    a = await create_from(api, w.TA, w.cid, t["id"])
    _sa, sb = a["sections"]
    base = f"/courses/{w.cid}/assessments/{a['id']}"
    r = await api.call(w.TA, "POST", f"{base}/questions", json={"section_id": sb["id"], "payload": card()})
    assert r.status_code == 201, r.text
    d1 = await api.call(w.TA, "POST", f"{base}/drafts", json={"item_id": r.json()["item"]["id"], "payload": card()})
    d2 = await api.call(w.TA, "POST", f"{base}/drafts", json={"section_id": sb["id"], "payload": card()})
    assert d1.status_code == 201 and d2.status_code == 201
    await _bump(api, w, t, V3)
    up = await api.call(w.TA, "POST", f"{base}/template-upgrade")
    assert up.status_code == 200, up.text
    db.expire_all()
    assert db.get(QuestionDraft, uuid.UUID(d1.json()["id"])) is None
    assert db.get(QuestionDraft, uuid.UUID(d2.json()["id"])) is None


async def test_soft_deleted_quiz_keeps_drafts(db, api):
    w = quiz_world(db)
    d = (await new_draft(api, w)).json()
    assert (await api.call(w.O, "DELETE", A(w))).status_code == 204
    db.expire_all()
    assert db.get(QuestionDraft, uuid.UUID(d["id"])) is not None
    assert (await api.call(w.O, "POST", f"{A(w)}/restore")).status_code == 200
    g = (await api.call(w.O, "GET", A(w))).json()
    assert [x["id"] for x in g["drafts"]] == [d["id"]]
