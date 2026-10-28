"""Shared helpers for the Phase 7c quiz editor tests (S1; S2 reuses them; PHASE_7C_DESIGN 10).

- `quiz_world(db)`: the `content_support.world` course (O owner, T co-teacher, AS assistant, S student, X outsider)
  plus a shared bank with two single_choice questions, quiz A and quiz B (general, `preset = 'none'`). Each quiz has
  one default section (key/title/time NULL, `rules = {}`, PHASE_7C_DESIGN 2.3) unless `sections=False`; with
  `link=True` both shared questions are items of quiz A.
- `make_quiz_bank(db, w, a)` / `make_draft(db, a, section, ...)`: rows written directly (not through the S2 services),
  for tests that need a quiz bank or a draft without exercising the API.
- `card(**over)`: a valid `CardPayloadIn` body (single_choice, en).
- Route helpers `A(w, a)` / `Q(w, qid)` for the 6.1 paths (relative to /api/v1, as `api.call` expects)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

from app.lms.assessments.models import Assessment, AssessmentSection
from app.lms.content.models import QuestionBank
from app.lms.quiz_editor.models import QuestionDraft
from tests.lms.assessment_support import SC
from tests.lms.content_support import world
from tests.lms.factories import make_assessment, make_bank, make_item, make_question, make_section


def card(**over) -> dict:
    """A complete, valid card payload (the whole form of one card)."""
    body = {"type": "single_choice", "language": "en", "stem": "What is 2 + 2?", "data": SC, "explanation": None,
            "default_points": 1, "image_asset_id": None, "points": 1,
            "meta": {"topic": None, "difficulty": None, "section": None, "tags": [], "passage_id": None}}
    body.update(over)
    return body


def default_section(db, a: Assessment) -> AssessmentSection:
    """The hidden default section of a general quiz (2.3): no key, title or time limit, empty rules."""
    return make_section(db, a, position=1, key=None, title=None, time_limit_s=None, rules={})


def quiz_world(db, *, sections: bool = True, link: bool = False, languages=("en", "ru", "ky")):
    w = world(db, languages=languages)
    shared = make_bank(db, w.course, w.O, title="Shared bank")
    q1 = make_question(db, shared, w.O, "single_choice", data=SC, stem="Shared question 1")
    q2 = make_question(db, shared, w.O, "single_choice", data=SC, stem="Shared question 2")
    quiz = make_assessment(db, w.course, w.O, title={"en": "Quiz A"}, languages=["en"])
    quiz2 = make_assessment(db, w.course, w.O, title={"en": "Quiz B"}, languages=["en"])
    s1 = default_section(db, quiz) if sections else None
    s2 = default_section(db, quiz2) if sections else None
    items = []
    if link:
        assert s1 is not None, "link=True needs sections=True"
        items = [make_item(db, quiz, s1, question=q, position=i) for i, q in enumerate((q1, q2), start=1)]
    return SimpleNamespace(**vars(w), shared=shared, q1=q1, q2=q2, quiz=quiz, quiz2=quiz2, s1=s1, s2=s2,
                           items=items, aid=str(quiz.id), aid2=str(quiz2.id))


def make_quiz_bank(db, w, a: Assessment, **over) -> QuestionBank:
    """The quiz bank of `a` written directly (what `quiz_banks.ensure_quiz_bank` does in S2)."""
    fields = dict(assessment_id=a.id, title=(a.title or {}).get("en") or "Quiz")
    fields.update(over)
    return make_bank(db, w.course, w.O, **fields)


def make_draft(db, a: Assessment, section: AssessmentSection, *, item=None, after_item=None,
               payload: Optional[dict] = None, actor=None, **over) -> QuestionDraft:
    base = None
    if item is not None and item.question_id is not None:
        from app.lms.content.models import BankQuestion

        base = db.get(BankQuestion, item.question_id).current_version_id
    d = QuestionDraft(
        assessment_id=a.id, section_id=section.id, item_id=item.id if item is not None else None,
        after_item_id=after_item.id if after_item is not None else None, base_version_id=base,
        payload=payload or card(), created_by_id=actor.id if actor else None,
        updated_by_id=actor.id if actor else None, **over,
    )
    db.add(d)
    db.commit()
    return d


def A(w, a=None) -> str:
    """`_A` of PHASE_7C_DESIGN 6.1 for quiz `a` (default: quiz A)."""
    return f"/courses/{w.cid}/assessments/{(a or w.quiz).id}"


def Q(w, qid) -> str:
    return f"/courses/{w.cid}/questions/{qid}"


# --- Phase 7c S2 begin --- (API shortcuts for the quiz editor route tests)
def err(res) -> Optional[str]:
    try:
        return res.json()["error"]["code"]
    except Exception:  # pragma: no cover
        return None


async def create_q(api, w, user=None, a=None, **body):
    """POST _A/questions (direct create); `body` overrides {section_id, after_item_id, payload}."""
    body.setdefault("payload", card())
    return await api.call(user or w.O, "POST", f"{A(w, a)}/questions", json=body)


async def new_draft(api, w, user=None, a=None, **body):
    body.setdefault("payload", card())
    return await api.call(user or w.O, "POST", f"{A(w, a)}/drafts", json=body)


async def put_draft(api, w, did, rev, payload=None, user=None, a=None):
    return await api.call(user or w.O, "PUT", f"{A(w, a)}/drafts/{did}",
                          json={"draft_rev": rev, "payload": payload or card()})


async def commit(api, w, did, rev, scope=None, user=None, a=None):
    body = {"draft_rev": rev}
    if scope is not None:
        body["scope"] = scope
    return await api.call(user or w.O, "POST", f"{A(w, a)}/drafts/{did}/commit", json=body)


async def edit_card(api, w, item, payload, scope=None, user=None, a=None):
    """Open an existing card (draft with `payload`), then Done. Returns (draft json, commit response)."""
    r = await new_draft(api, w, user=user, a=a, item_id=str(item.id), payload=payload)
    assert r.status_code == 201, r.text
    d = r.json()
    return d, await commit(api, w, d["id"], d["draft_rev"], scope=scope, user=user, a=a)


def staff_payload(db, q, **over) -> dict:
    """The card payload of an existing question's current version (what the client seeds the form with)."""
    from app.lms.content.models import QuestionVersion

    db.refresh(q)
    v = db.get(QuestionVersion, q.current_version_id)
    body = card(type=v.type, language=q.language, stem=v.stem, data=v.data, explanation=v.explanation,
                default_points=float(v.default_points), points=float(v.default_points),
                meta={"topic": q.topic, "difficulty": q.difficulty, "section": q.section, "tags": list(q.tags or []),
                      "passage_id": str(q.passage_id) if q.passage_id else None})
    body.update(over)
    return body


async def quiz_question(api, db, w, a=None, **payload_over):
    """A question written in quiz `a` (direct create). Returns (item row, question row)."""
    from app.lms.assessments.models import AssessmentItem
    from app.lms.content.models import BankQuestion
    import uuid as _uuid

    r = await create_q(api, w, a=a, payload=card(**payload_over))
    assert r.status_code == 201, r.text
    db.expire_all()
    return (db.get(AssessmentItem, _uuid.UUID(r.json()["item"]["id"])),
            db.get(BankQuestion, _uuid.UUID(r.json()["question"]["id"])))
# --- Phase 7c S2 end ---
