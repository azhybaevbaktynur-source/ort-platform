"""Helpers for the A2 assessment tests: content seeding with key sentinels and API shortcuts."""
from __future__ import annotations

import hashlib
from decimal import Decimal

from app.lms.content.models import BankQuestion, QuestionVersion, TranslationGroup
from tests.lms.content_support import world  # noqa: F401
from tests.lms.factories import make_bank, make_passage, make_question

SENT_EXPL = "SENTINEL_EXPLANATION_4417"
SENT_NUM = "73917391.5"
SENT_SHORT = "SENTINEL_SHORT_ANSWER_5520"
SENT_RUBRIC = "SENTINEL_RUBRIC_8802"
SENT_SCORING = "partial"
SENTINELS = (SENT_EXPL, SENT_NUM, SENT_SHORT, SENT_RUBRIC)

SC = {"choices": [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}], "correct": "B"}
CMP = {"column_a": "$x^2$", "column_b": "$x$", "correct": "D"}
NUM = {"answers": [{"kind": "exact", "value": SENT_NUM, "margin": "0"}]}
SHORT = {"answers": [SENT_SHORT], "case_sensitive": False}
ESSAY = {"word_limit": 100, "rubric_note": SENT_RUBRIC}
TF = {"correct": True}
MA = {"choices": [{"id": "A", "text": "1"}, {"id": "B", "text": "2"}, {"id": "C", "text": "3"}],
      "correct": ["A", "C"], "scoring": "partial"}

TYPE_DATA = {"single_choice": SC, "comparison": CMP, "multiple_answers": MA, "true_false": TF, "essay": ESSAY}


def sc(db, bank, actor, **kw):
    kw.setdefault("explanation", SENT_EXPL)
    return make_question(db, bank, actor, "single_choice", **kw)


def cmp_q(db, bank, actor, **kw):
    kw.setdefault("explanation", SENT_EXPL)
    return make_question(db, bank, actor, "comparison", data=CMP, **kw)


def bank_of(db, course, actor, n: int, qtype: str = "single_choice", language: str = "en", **kw):
    bank = make_bank(db, course, actor)
    data = TYPE_DATA[qtype]
    qs = [make_question(db, bank, actor, qtype, data=data, language=language, stem=f"{qtype} {language} {i}",
                        explanation=SENT_EXPL, **kw) for i in range(n)]
    return bank, qs


def translate(db, actor, *questions):
    """Put the questions (different languages) in one translation group."""
    g = TranslationGroup(course_id=None, created_by_id=actor.id)
    db.add(g)
    db.flush()
    for q in questions:
        q.translation_group_id = g.id
    db.commit()
    return g


def bump_version(db, q, stem="edited stem", actor=None):
    """New immutable version for a question (what the content service does on edit)."""
    cur = db.get(QuestionVersion, q.current_version_id)
    v = QuestionVersion(
        question_id=q.id, version_no=cur.version_no + 1, language=cur.language, type=cur.type, stem=stem,
        data=cur.data, explanation=cur.explanation, default_points=cur.default_points,
        content_hash=hashlib.sha256(f"{q.id}:{stem}".encode()).hexdigest(), origin="edit",
        created_by_id=actor.id if actor else None)
    db.add(v)
    db.flush()
    q.current_version_id = v.id
    db.commit()
    return v


async def mk(api, user, cid, **body):
    body.setdefault("title", {"en": "Quiz"})
    body.setdefault("preset", "none")
    body.setdefault("languages", ["en"])
    res = await api.call(user, "POST", f"/courses/{cid}/assessments", json=body)
    assert res.status_code == 201, res.text
    return res.json()


async def section(api, user, cid, aid, **body):
    res = await api.call(user, "POST", f"/courses/{cid}/assessments/{aid}/sections", json=body)
    assert res.status_code == 201, res.text
    return res.json()


async def add_q(api, user, cid, aid, sid, qid, **kw):
    res = await api.call(user, "POST", f"/courses/{cid}/assessments/{aid}/sections/{sid}/items",
                         json={"kind": "question", "question_id": str(qid), **kw})
    assert res.status_code == 201, res.text
    return res.json()


async def get(api, user, cid, aid):
    res = await api.call(user, "GET", f"/courses/{cid}/assessments/{aid}")
    assert res.status_code == 200, res.text
    return res.json()


async def publish(api, user, cid, aid, **body):
    return await api.call(user, "POST", f"/courses/{cid}/assessments/{aid}/publish", json=body)


async def simple_published(api, db, w, n=3, **create):
    """Course world `w` -> published single-section assessment with n single_choice questions. Returns (a, qs)."""
    bank, qs = bank_of(db, w.course, w.O, n)
    a = await mk(api, w.O, w.cid, **create)
    s = await section(api, w.O, w.cid, a["id"])
    for q in qs:
        await add_q(api, w.O, w.cid, a["id"], s["id"], q.id)
    res = await publish(api, w.O, w.cid, a["id"])
    assert res.status_code == 200, res.text
    return res.json(), qs
