"""Phase 7c S2: move / copy a question to a shared bank (PHASE_7C_DESIGN 5.6, P7C-9, 16, 10)."""
import uuid

from app.lms.assessments.models import AssessmentItem
from app.lms.content.models import BankQuestion, QuestionVersion
from tests.lms.assessment_support import translate
from tests.lms.content_support import world
from tests.lms.factories import make_bank, make_passage, make_question
from tests.lms.quiz_editor_support import A, Q, err, make_quiz_bank, quiz_question, quiz_world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


async def _to_bank(api, w, qid, bank_id, mode, user=None):
    return await api.call(user or w.O, "POST", f"{Q(w, qid)}/copy-to-bank", json={"bank_id": str(bank_id), "mode": mode})


async def test_move_keeps_items_and_translation_group_and_unlocks_reuse(db, api):
    w = quiz_world(db)
    item, q = await quiz_question(api, db, w)
    other = make_question(db, w.shared, w.O, language="ru")
    g = translate(db, w.O, q, other)
    r = await _to_bank(api, w, q.id, w.shared.id, "move")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == str(q.id) and r.json()["bank_id"] == str(w.shared.id)
    db.expire_all()
    q = db.get(BankQuestion, q.id)
    assert q.bank_id == w.shared.id and q.translation_group_id == g.id
    assert db.get(AssessmentItem, item.id).question_id == q.id
    # now in a shared bank: quiz B may link it (16)
    res = await api.call(w.O, "POST", f"{A(w, w.quiz2)}/sections/{w.s2.id}/items",
                         json={"kind": "question", "question_id": str(q.id)})
    assert res.status_code == 201, res.text


async def test_move_refuses_passages_and_non_shared_targets(db, api):
    w = quiz_world(db)
    qb = make_quiz_bank(db, w, w.quiz)
    p = make_passage(db, qb, w.O)
    q = make_question(db, qb, w.O, passage_id=p.id)
    r = await _to_bank(api, w, q.id, w.shared.id, "move")
    assert r.status_code == 409 and err(r) == "question_has_passage"
    qb2 = make_quiz_bank(db, w, w.quiz2)
    plain = make_question(db, qb, w.O)
    for mode in ("move", "copy"):
        r = await _to_bank(api, w, plain.id, qb2.id, mode)
        assert r.status_code == 422 and err(r) == "target_not_shared_bank"


async def test_move_source_conflict(db, api):
    w = quiz_world(db)
    qb = make_quiz_bank(db, w, w.quiz)
    q = make_question(db, qb, w.O, source_ref="ext:1")
    make_question(db, w.shared, w.O, source_ref="ext:1")
    r = await _to_bank(api, w, q.id, w.shared.id, "move")
    assert r.status_code == 409 and err(r) == "source_conflict"
    db.expire_all()
    assert db.get(BankQuestion, q.id).bank_id == qb.id


async def test_copy_leaves_items_and_never_joins_a_group(db, api):
    w = quiz_world(db)
    item, q = await quiz_question(api, db, w, stem="Copy me")
    translate(db, w.O, q, make_question(db, w.shared, w.O, language="ru"))
    r = await _to_bank(api, w, q.id, w.shared.id, "copy")
    assert r.status_code == 200, r.text
    new_id = uuid.UUID(r.json()["id"])
    assert new_id != q.id and r.json()["bank_id"] == str(w.shared.id)
    db.expire_all()
    new = db.get(BankQuestion, new_id)
    assert new.translation_group_id is None and new.passage_id is None
    assert db.get(QuestionVersion, new.current_version_id).stem == "Copy me"
    assert db.get(AssessmentItem, item.id).question_id == q.id


async def test_cross_course_target_and_question_are_404(db, api):
    w = quiz_world(db)
    other = world(db)
    foreign = make_bank(db, other.course, other.O)
    item, q = await quiz_question(api, db, w)
    r = await _to_bank(api, w, q.id, foreign.id, "copy")
    assert r.status_code == 404 and err(r) == "bank_not_found"
    fq = make_question(db, foreign, other.O)
    r = await _to_bank(api, w, fq.id, w.shared.id, "move")
    assert r.status_code == 404 and err(r) == "question_not_found"
    bad = await api.call(w.O, "POST", f"{Q(w, q.id)}/copy-to-bank", json={"bank_id": str(w.shared.id), "mode": "x"})
    assert bad.status_code == 422
