"""Phase 7c S2: create a question in the quiz and commit a card draft (PHASE_7C_DESIGN 5.3, 5.4, 10)."""
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection
from app.lms.content.models import BankQuestion, QuestionBank, QuestionVersion
from app.lms.quiz_editor.models import QuestionDraft
from tests.lms.factories import make_assessment, make_item, make_passage, make_question, make_section
from tests.lms.quiz_editor_support import (
    A, card, commit, create_q, edit_card, err, make_quiz_bank, new_draft, quiz_question, quiz_world, staff_payload,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _quiz_banks(db, a):
    return db.execute(select(QuestionBank).where(QuestionBank.assessment_id == a.id)).scalars().all()


def _top(db, section):
    db.expire_all()
    return list(db.execute(select(AssessmentItem).where(
        AssessmentItem.section_id == section.id, AssessmentItem.parent_item_id.is_(None))
        .order_by(AssessmentItem.position)).scalars())


async def test_new_card_commit_creates_question_version_item_at_position(db, api):
    w = quiz_world(db, link=True)
    rev0 = db.get(Assessment, w.quiz.id).draft_rev
    d = (await new_draft(api, w, after_item_id=str(w.items[0].id), payload=card(points=3, stem="New one"))).json()
    r = await commit(api, w, d["id"], 1)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["applied"] == "created" and out["version_created"] is True
    assert out["item"]["points"] == 3 and out["question"]["current_version"]["default_points"] == 3
    assert out["item"]["question"]["bank_kind"] == "quiz"
    banks = _quiz_banks(db, w.quiz)
    assert len(banks) == 1 and str(banks[0].id) == out["question"]["bank_id"]
    assert banks[0].title == "Quiz A" and banks[0].organization_id == w.course.organization_id
    order = [str(i.id) for i in _top(db, w.s1)]
    assert order == [str(w.items[0].id), out["item"]["id"], str(w.items[1].id)]
    assert [i.position for i in _top(db, w.s1)] == [1, 2, 3]
    assert db.get(QuestionDraft, uuid.UUID(d["id"])) is None
    assert db.get(Assessment, w.quiz.id).draft_rev == rev0 + 1
    q = db.get(BankQuestion, uuid.UUID(out["question"]["id"]))
    assert db.scalar(select(func.count()).select_from(QuestionVersion).where(QuestionVersion.question_id == q.id)) == 1


async def test_invalid_new_card_rolls_back_and_keeps_the_draft(db, api):
    w = quiz_world(db)
    d = (await new_draft(api, w, payload=card(data={"choices": []}))).json()
    r = await commit(api, w, d["id"], 1)
    assert r.status_code == 422 and err(r) == "invalid_question_data"
    assert r.json()["error"]["details"]
    db.expire_all()
    assert db.get(QuestionDraft, uuid.UUID(d["id"])) is not None
    assert _quiz_banks(db, w.quiz) == []
    assert db.scalar(select(func.count()).select_from(AssessmentItem).where(AssessmentItem.assessment_id == w.quiz.id)) == 0


async def test_direct_create_reuses_one_quiz_bank_and_default_section(db, api):
    w = quiz_world(db, sections=False)
    r1 = await create_q(api, w)
    assert r1.status_code == 201, r1.text
    r2 = await create_q(api, w, payload=card(stem="Second"))
    assert r2.status_code == 201
    assert r1.json()["question"]["bank_id"] == r2.json()["question"]["bank_id"]
    assert len(_quiz_banks(db, w.quiz)) == 1
    secs = db.execute(select(AssessmentSection).where(AssessmentSection.assessment_id == w.quiz.id)).scalars().all()
    assert len(secs) == 1 and secs[0].key is None and secs[0].rules == {}
    assert [i.position for i in _top(db, secs[0])] == [1, 2]
    # other content checks before any write
    bad = await create_q(api, w, payload=card(data={"choices": [{"id": "A", "text": "x"}], "correct": "Z"}))
    assert bad.status_code == 422 and err(bad) == "invalid_question_data"
    stray = await create_q(api, w, after_item_id=str(uuid.uuid4()))
    assert stray.status_code == 404 and err(stray) == "item_not_found"


async def test_rules_language_and_caps(db, api):
    w = quiz_world(db, sections=False)
    only_cmp = make_section(db, w.quiz, rules={"allowed_types": ["comparison"]})
    r = await create_q(api, w, section_id=str(only_cmp.id))
    assert r.status_code == 422 and err(r) == "item_type_not_allowed"
    capped = make_section(db, w.quiz, rules={"max_items": 1})
    assert (await create_q(api, w, section_id=str(capped.id))).status_code == 201
    r = await create_q(api, w, section_id=str(capped.id))
    assert r.status_code == 422 and err(r) == "too_many_items"
    r = await create_q(api, w, section_id=str(capped.id), payload=card(language="ru"))  # quiz languages: en
    assert r.status_code == 422 and err(r) == "item_language_mismatch"
    r = await create_q(api, w, payload=card(type="drawing"))
    assert r.status_code == 422
    assert db.scalar(select(func.count()).select_from(BankQuestion).join(
        QuestionBank, QuestionBank.id == BankQuestion.bank_id).where(QuestionBank.assessment_id == w.quiz.id)) == 1


async def test_template_section_rules_apply(db, api):
    """A section written by a template (allowed_types) refuses other types in the quiz editor too."""
    w = quiz_world(db, sections=False)
    s = make_section(db, w.quiz, key="cmp", title={"en": "Compare"}, rules={"allowed_types": ["comparison"]})
    r = await create_q(api, w, section_id=str(s.id))
    assert r.status_code == 422 and err(r) == "item_type_not_allowed"
    ok = await create_q(api, w, section_id=str(s.id), payload=card(
        type="comparison", data={"column_a": "1", "column_b": "2", "correct": "B"}))
    assert ok.status_code == 201, ok.text


async def test_passage_must_be_in_the_quiz_bank(db, api):
    w = quiz_world(db)
    shared_p = make_passage(db, w.shared, w.O)
    r = await create_q(api, w, payload=card(meta={"passage_id": str(shared_p.id)}))
    assert r.status_code == 422 and err(r) == "passage_not_in_quiz_bank"
    qb = make_quiz_bank(db, w, w.quiz)
    own_p = make_passage(db, qb, w.O)
    r = await create_q(api, w, payload=card(meta={"passage_id": str(own_p.id)}))
    assert r.status_code == 201, r.text
    assert r.json()["question"]["passage_id"] == str(own_p.id)
    no_pass = make_section(db, w.quiz, rules={"allow_passages": False})
    r = await create_q(api, w, section_id=str(no_pass.id), payload=card(meta={"passage_id": str(own_p.id)}))
    assert r.status_code == 422 and err(r) == "item_type_not_allowed"


async def test_existing_card_unchanged_and_points(db, api):
    w = quiz_world(db, link=True)
    # shared question: same content -> unchanged, no version; the points live on the item only
    d, r = await edit_card(api, w, w.items[0], staff_payload(db, w.q1, points=4))
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == "unchanged" and r.json()["version_created"] is False
    db.expire_all()
    assert db.get(AssessmentItem, w.items[0].id).points == Decimal("4")
    assert db.get(BankQuestion, w.q1.id).current_version_id == w.q1.current_version_id
    assert db.get(QuestionDraft, uuid.UUID(d["id"])) is None


async def test_quiz_bank_question_edits_in_place_with_default_points(db, api):
    w = quiz_world(db)
    item, q = await quiz_question(api, db, w)
    v1 = q.current_version_id
    _, r = await edit_card(api, w, item, staff_payload(db, q, stem="Edited", points=2))
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == "in_place" and r.json()["version_created"] is True
    db.expire_all()
    q = db.get(BankQuestion, q.id)
    v = db.get(QuestionVersion, q.current_version_id)
    assert q.current_version_id != v1 and v.stem == "Edited" and v.default_points == Decimal("2") and v.origin == "edit"
    assert db.get(AssessmentItem, item.id).points == Decimal("2") and db.get(AssessmentItem, item.id).question_id == q.id


async def test_meta_change_in_place(db, api):
    w = quiz_world(db)
    item, q = await quiz_question(api, db, w)
    p = staff_payload(db, q)
    p["meta"] = {**p["meta"], "topic": "Fractions", "tags": ["t1"], "difficulty": "hard"}
    _, r = await edit_card(api, w, item, p)
    assert r.status_code == 200 and r.json()["applied"] == "in_place" and r.json()["version_created"] is False
    db.expire_all()
    q = db.get(BankQuestion, q.id)
    assert (q.topic, q.tags, q.difficulty) == ("Fractions", ["t1"], "hard") and "fractions" in q.search_text


async def test_language_of_existing_card_is_locked(db, api):
    w = quiz_world(db, languages=("en", "ru"))
    w.quiz.languages = ["en", "ru"]
    db.commit()
    item, q = await quiz_question(api, db, w)
    _, r = await edit_card(api, w, item, staff_payload(db, q, language="ru"))
    assert r.status_code == 422


async def test_ort_exam_is_not_editable_here(db, api):
    w = quiz_world(db, sections=False)
    w.course.template_key, w.course.template_version = "ort", 1
    db.commit()
    ort = make_assessment(db, w.course, w.O, preset="ort_main", title={"en": "ORT"}, languages=["en"])
    make_section(db, ort, key="math_2", rules={"allowed_types": ["single_choice"], "allow_passages": False})
    r = await create_q(api, w, a=ort)
    assert r.status_code == 409 and err(r) == "template_locked"
    r = await new_draft(api, w, a=ort)
    assert r.status_code == 409 and err(r) == "template_locked"
    assert db.scalar(select(func.count()).select_from(QuestionBank).where(QuestionBank.assessment_id.is_not(None))) == 0


async def test_commit_of_new_card_after_item_that_moved_falls_back_to_end(db, api):
    w = quiz_world(db, link=True)
    d = (await new_draft(api, w, after_item_id=str(w.items[0].id))).json()
    other = make_section(db, w.quiz, rules={})
    mv = await api.call(w.O, "PATCH", f"{A(w)}/items/{w.items[0].id}", json={"section_id": str(other.id)})
    assert mv.status_code == 200, mv.text
    r = await commit(api, w, d["id"], 1)
    assert r.status_code == 200, r.text
    assert [str(i.id) for i in _top(db, w.s1)] == [str(w.items[1].id), r.json()["item"]["id"]]


async def test_pick_items_untouched_by_commit(db, api):
    w = quiz_world(db, link=True)
    make_item(db, w.quiz, w.s1, kind="pick", pick_bank_id=w.shared.id, pick_count=1, pick_filter={}, position=3)
    d = (await new_draft(api, w)).json()
    r = await commit(api, w, d["id"], 1)
    assert r.status_code == 200
    kinds = [(i.kind, i.position) for i in _top(db, w.s1)]
    assert kinds == [("question", 1), ("question", 2), ("pick", 3), ("question", 4)]
    assert make_question  # imported helper used by other files


async def test_existing_card_commit_ignores_meta_passage_id(db, api):
    """Phase 7c fix1 (M1): `meta.passage_id` of an existing card is ignored; a passage child committed with
    `passage_id: null` keeps its passage (and a null passage id alone is no change)."""
    w = quiz_world(db)
    qb = make_quiz_bank(db, w, w.quiz)
    own_p = make_passage(db, qb, w.O)
    r = await create_q(api, w, payload=card(meta={"passage_id": str(own_p.id)}))
    assert r.status_code == 201, r.text
    db.expire_all()
    item = db.get(AssessmentItem, uuid.UUID(r.json()["item"]["id"]))
    q = db.get(BankQuestion, uuid.UUID(r.json()["question"]["id"]))
    assert q.passage_id == own_p.id
    p = staff_payload(db, q)
    p["meta"] = {**p["meta"], "passage_id": None}
    _, r = await edit_card(api, w, item, p)
    assert r.status_code == 200 and r.json()["applied"] == "unchanged", r.text
    p = staff_payload(db, q, stem="Edited child")
    p["meta"] = {**p["meta"], "passage_id": None, "tags": ["t1"]}
    _, r = await edit_card(api, w, item, p)
    assert r.status_code == 200 and r.json()["applied"] == "in_place", r.text
    db.expire_all()
    q = db.get(BankQuestion, q.id)
    assert q.passage_id == own_p.id and q.tags == ["t1"]
    assert db.get(QuestionVersion, q.current_version_id).stem == "Edited child"
