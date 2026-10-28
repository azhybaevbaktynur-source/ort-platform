"""Phase 7c S2: changing a card's question type (PHASE_7C_DESIGN 5.4, 7c-5, P7C-7, 10)."""
from sqlalchemy import select

from app.lms.assessments.models import AssessmentItem, AssessmentSection
from app.lms.content.models import BankQuestion, QuestionBank, QuestionVersion
from tests.lms.assessment_support import publish, translate
from tests.lms.factories import make_item, make_question
from tests.lms.quiz_editor_support import edit_card, err, quiz_question, quiz_world, staff_payload
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

TF = {"type": "true_false", "data": {"correct": True}}


async def test_type_change_used_only_here_never_published_is_in_place(db, api):
    w = quiz_world(db)
    item, q = await quiz_question(api, db, w)
    _, r = await edit_card(api, w, item, staff_payload(db, q, **TF))
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == "in_place" and r.json()["question"]["type"] == "true_false"
    db.expire_all()
    q = db.get(BankQuestion, q.id)
    assert q.type == "true_false" and db.get(QuestionVersion, q.current_version_id).type == "true_false"
    assert db.get(AssessmentItem, item.id).question_id == q.id


async def test_type_change_used_elsewhere_is_forced_this(db, api):
    w = quiz_world(db, link=True)
    make_item(db, w.quiz2, w.s2, question=w.q1, position=1)
    _, r = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, **TF))  # no scope asked
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == "this" and r.json()["question"]["type"] == "true_false"
    db.expire_all()
    assert db.get(BankQuestion, w.q1.id).type == "single_choice"
    assert db.get(AssessmentItem, w.items[0].id).question_id != w.q1.id


async def test_type_change_after_publish_even_unpublished_is_forced_this(db, api):
    w = quiz_world(db)
    item, q = await quiz_question(api, db, w)
    assert (await publish(api, w.O, w.cid, w.aid)).status_code == 200
    assert (await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{w.aid}/unpublish")).status_code == 200
    _, r = await edit_card(api, w, item, staff_payload(db, q, **TF))
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == "this"
    db.expire_all()
    assert db.get(BankQuestion, q.id).type == "single_choice"
    new_q = db.get(BankQuestion, db.get(AssessmentItem, item.id).question_id)
    assert new_q.id != q.id and db.get(QuestionBank, new_q.bank_id).assessment_id == w.quiz.id


async def test_type_change_of_translation_group_member_is_forced_this(db, api):
    w = quiz_world(db, link=True)
    ru = make_question(db, w.shared, w.O, language="ru", stem="ru variant")
    translate(db, w.O, w.q2, ru)
    _, r = await edit_card(api, w, w.items[1], staff_payload(db, w.q2, **TF))  # q2: quiz A only
    assert r.status_code == 200 and r.json()["applied"] == "this"
    db.expire_all()
    assert db.get(BankQuestion, w.q2.id).type == db.get(BankQuestion, ru.id).type == "single_choice"


async def test_new_type_not_allowed_in_section(db, api):
    w = quiz_world(db)
    item, q = await quiz_question(api, db, w)
    s = db.get(AssessmentSection, w.s1.id)
    s.rules = {"allowed_types": ["single_choice"]}
    db.commit()
    _, r = await edit_card(api, w, item, staff_payload(db, q, **TF))
    assert r.status_code == 422 and err(r) == "item_type_not_allowed"
    db.expire_all()
    assert db.get(BankQuestion, q.id).type == "single_choice"
    # forced `this` checks the section rules too
    w2 = quiz_world(db, link=True)
    make_item(db, w2.quiz2, w2.s2, question=w2.q1, position=1)
    s = db.get(AssessmentSection, w2.s1.id)
    s.rules = {"allowed_types": ["single_choice"]}
    db.commit()
    _, r = await edit_card(api, w2, w2.items[0], staff_payload(db, w2.q1, **TF))
    assert r.status_code == 422 and err(r) == "item_type_not_allowed"
    assert select  # noqa
