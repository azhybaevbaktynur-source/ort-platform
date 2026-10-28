"""Phase 7c S2: edit scope `all | this` (PHASE_7C_DESIGN 5.4, 7c-2, 10)."""
import uuid

from sqlalchemy import func, select

from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentVersion
from app.lms.content.models import BankQuestion, QuestionBank, QuestionVersion
from app.lms.quiz_editor import commit as commit_mod
from app.lms.quiz_editor.models import QuestionDraft
from tests.lms.assessment_support import bump_version, publish
from tests.lms.factories import make_item, make_passage, make_question
from tests.lms.quiz_editor_support import A, commit, edit_card, err, new_draft, quiz_world, staff_payload
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _shared_in_both(db):
    w = quiz_world(db, link=True)
    b_item = make_item(db, w.quiz2, w.s2, question=w.q1, position=1)
    return w, b_item


async def test_used_only_here_edits_in_place_without_scope(db, api):
    w, _ = _shared_in_both(db)
    _, r = await edit_card(api, w, w.items[1], staff_payload(db, w.q2, stem="only here"))  # q2: quiz A only
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == "in_place" and r.json()["question"]["id"] == str(w.q2.id)
    db.expire_all()
    assert db.get(QuestionVersion, db.get(BankQuestion, w.q2.id).current_version_id).stem == "only here"


async def test_used_elsewhere_requires_scope(db, api):
    w, _ = _shared_in_both(db)
    d, r = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, stem="changed"))
    assert r.status_code == 409 and err(r) == "scope_required"
    det = r.json()["error"]["details"]
    assert det["assessment_count"] == 1 and det["can_update_all"] is True
    by_id = {x["id"]: x for x in det["assessments"]}
    assert by_id[str(w.quiz.id)]["is_this"] is True and by_id[str(w.quiz2.id)]["is_this"] is False
    assert by_id[str(w.quiz2.id)]["title"] == {"en": "Quiz B"}
    db.expire_all()
    assert db.get(QuestionDraft, uuid.UUID(d["id"])) is not None  # the draft stays for the retry
    bad = await api.call(w.O, "POST", f"{A(w)}/drafts/{d['id']}/commit", json={"draft_rev": 1, "scope": "both"})
    assert bad.status_code == 422


async def test_scope_all_new_version_reaches_both_quizzes_after_republish_only(db, api):
    w, b_item = _shared_in_both(db)
    pub = await publish(api, w.O, w.cid, w.aid2)
    assert pub.status_code == 200, pub.text
    v1 = str(w.q1.current_version_id)
    d, r = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, stem="for everyone"))
    assert err(r) == "scope_required"
    r = await commit(api, w, d["id"], d["draft_rev"], scope="all")
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == "all" and r.json()["version_created"] is True
    db.expire_all()
    q1 = db.get(BankQuestion, w.q1.id)
    assert str(q1.current_version_id) != v1
    assert db.get(AssessmentItem, w.items[0].id).question_id == w.q1.id
    assert db.get(AssessmentItem, b_item.id).question_id == w.q1.id
    b = (await api.call(w.O, "GET", A(w, w.quiz2))).json()
    assert b["sections"][0]["items"][0]["question"]["newer_version_available"] is True
    snap = db.get(AssessmentVersion, db.get(Assessment, w.quiz2.id).published_version_id).snapshot
    assert [s["qv"] for s in snap["slots"]["en"]] == [v1]  # quiz B's published snapshot is unchanged


async def test_scope_this_repoints_only_this_quiz(db, api):
    w, b_item = _shared_in_both(db)
    v1 = w.q1.current_version_id
    d, _ = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, stem="just here", points=5))
    r = await commit(api, w, d["id"], d["draft_rev"], scope="this")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["applied"] == "this" and out["version_created"] is True and out["question"]["id"] != str(w.q1.id)
    assert out["item"]["question"]["bank_kind"] == "quiz" and out["item"]["points"] == 5
    db.expire_all()
    q1 = db.get(BankQuestion, w.q1.id)
    assert q1.current_version_id == v1  # the source question is untouched
    item = db.get(AssessmentItem, w.items[0].id)
    q2 = db.get(BankQuestion, item.question_id)
    assert db.get(QuestionBank, q2.bank_id).assessment_id == w.quiz.id
    assert q2.passage_id is None and q2.translation_group_id is None
    v = db.get(QuestionVersion, q2.current_version_id)
    assert (v.stem, float(v.default_points), v.origin) == ("just here", 5.0, "create")
    assert db.get(AssessmentItem, b_item.id).question_id == w.q1.id  # quiz B untouched


async def test_scope_all_refused_without_edit_rights(db, api, monkeypatch):
    w, _ = _shared_in_both(db)
    monkeypatch.setattr(commit_mod, "can_edit_bank", lambda *a, **k: False)
    d, r = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, stem="x"))
    assert err(r) == "scope_required" and r.json()["error"]["details"]["can_update_all"] is False
    r = await commit(api, w, d["id"], d["draft_rev"], scope="all")
    assert r.status_code == 403 and err(r) == "scope_not_allowed"
    r = await commit(api, w, d["id"], d["draft_rev"], scope="this")
    assert r.status_code == 200 and r.json()["applied"] == "this"


async def test_passage_child_cannot_take_scope_this(db, api):
    w = quiz_world(db)
    p = make_passage(db, w.shared, w.O)
    q = make_question(db, w.shared, w.O, passage_id=p.id, stem="child")
    header = make_item(db, w.quiz, w.s1, passage=p, position=1)
    child = make_item(db, w.quiz, w.s1, question=q, parent=header, position=1)
    hb = make_item(db, w.quiz2, w.s2, passage=p, position=1)
    make_item(db, w.quiz2, w.s2, question=q, parent=hb, position=1)
    d, r = await edit_card(api, w, child, staff_payload(db, q, stem="child edited"))
    assert err(r) == "scope_required"
    r = await commit(api, w, d["id"], d["draft_rev"], scope="this")
    assert r.status_code == 409 and err(r) == "passage_child_scope"
    r = await commit(api, w, d["id"], d["draft_rev"], scope="all")
    assert r.status_code == 200 and r.json()["applied"] == "all"


async def test_version_conflict_on_in_place_and_all(db, api):
    w, _ = _shared_in_both(db)
    d = (await new_draft(api, w, item_id=str(w.items[1].id), payload=staff_payload(db, w.q2, stem="mine"))).json()
    bump_version(db, w.q2, stem="someone else's")
    r = await commit(api, w, d["id"], d["draft_rev"])
    assert r.status_code == 409 and err(r) == "version_conflict"
    assert r.json()["error"]["details"]["current_version_id"] == str(db.get(BankQuestion, w.q2.id).current_version_id)
    d1 = (await new_draft(api, w, item_id=str(w.items[0].id), payload=staff_payload(db, w.q1, stem="mine"))).json()
    bump_version(db, w.q1, stem="theirs")
    r = await commit(api, w, d1["id"], d1["draft_rev"], scope="all")
    assert r.status_code == 409 and err(r) == "version_conflict"
    # `this` never touches the source, so a newer source version does not block it
    r = await commit(api, w, d1["id"], d1["draft_rev"], scope="this")
    assert r.status_code == 200 and r.json()["applied"] == "this"


async def test_invalid_payload_with_scope_this_changes_nothing(db, api):
    w, _ = _shared_in_both(db)
    questions = db.scalar(select(func.count()).select_from(BankQuestion))
    d, r = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, data={"choices": [], "correct": "A"}))
    r = await commit(api, w, d["id"], d["draft_rev"], scope="this")
    assert r.status_code == 422 and err(r) == "invalid_question_data"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(BankQuestion)) == questions
    assert db.get(AssessmentItem, w.items[0].id).question_id == w.q1.id
    assert db.get(QuestionDraft, uuid.UUID(d["id"])) is not None
    assert db.scalar(select(func.count()).select_from(QuestionBank).where(QuestionBank.assessment_id.is_not(None))) == 0
