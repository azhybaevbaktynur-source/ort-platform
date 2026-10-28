"""Create a question inside the quiz and commit a card draft ("Done") (PHASE_7C_DESIGN 5.3, 5.4, 7c-2, 7c-5).

Everything runs under the assessment row lock (`builder._manage`) in one transaction and validates before writing;
nothing commits inside `create_question_in_quiz`. Scope `this` never touches the source question; scope `all` (and in
place) never touches other items."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext
from app.lms.assessments import repository as repo
from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection
from app.lms.assessments.rules import check_item_rules
from app.lms.content import repository as content_repo
from app.lms.content import service as content_svc
from app.lms.content.models import BankQuestion, QuestionBank, QuestionVersion
from app.lms.content.permissions import can_edit_bank
from app.lms.content.schemas import QuestionContentIn, QuestionMetaIn
from app.lms.content.types import get_type
from app.lms.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.lms.quiz_editor import ids, quiz_banks, usage
from app.lms.quiz_editor.drafts import draft_out, load_draft, resolve_after_item
from app.lms.quiz_editor.models import QuestionDraft
from app.lms.quiz_editor.schemas import CardPayloadIn, CommitIn
from app.lms.quiz_editor.service import assert_quiz_editable, target_section


def _builder():
    from app.lms.assessments import builder

    return builder


def _invalid(msg: str, loc: list) -> ValidationFailed:
    return ValidationFailed("Invalid content", code=ids.E_INVALID_QUESTION_DATA, details=[{"loc": loc, "msg": msg}])


def _content_in(payload: CardPayloadIn, default_points) -> QuestionContentIn:
    try:
        return QuestionContentIn(type=payload.type, stem=payload.stem, data=payload.data,
                                 explanation=payload.explanation, default_points=default_points,
                                 image_asset_id=payload.image_asset_id)
    except ValidationError as exc:
        e = exc.errors()[0]
        raise _invalid(str(e.get("msg")), ["payload", *[str(x) for x in e.get("loc", ())]]) from None


def _prepared(db: Session, ctx: AuthzContext, payload: CardPayloadIn, default_points, carried: set) -> dict:
    """Request content -> normalized content (ImageRefs resolved); 422 before any write."""
    get_type(payload.type)  # 422 unsupported_type
    content = content_svc.prepare_content(db, ctx.user, _content_in(payload, default_points), carried)
    return content_svc.normalize_question_content(payload.language, content)


def _clean_meta(payload: CardPayloadIn) -> dict:
    m = payload.meta
    return {"topic": content_svc._clean_label(m.topic, 200), "difficulty": m.difficulty,
            "section": content_svc._clean_label(m.section, 40), "tags": content_svc._clean_tags(m.tags or [])}


def _check_language(course, a: Assessment, language: str) -> None:
    if language not in (course.languages or []) or language not in (a.languages or []):
        raise ValidationFailed("The language is not a language of this quiz", code=ids.E_ITEM_LANGUAGE_MISMATCH,
                               details=[{"loc": ["payload", "language"], "msg": ids.E_ITEM_LANGUAGE_MISMATCH}])


def _check_type(section: AssessmentSection, a: Assessment, qtype: str, language: str) -> None:
    if any(i.code == "type_not_allowed" for i in check_item_rules(section, a, qtype, language)):
        raise ValidationFailed("This question type is not allowed in the section", code=ids.E_ITEM_TYPE_NOT_ALLOWED,
                               details=[{"loc": ["payload", "type"], "msg": ids.E_ITEM_TYPE_NOT_ALLOWED}])


def _quiz_passage(db: Session, course, a: Assessment, section: AssessmentSection, passage_id: Optional[uuid.UUID]):
    """A new card may join a passage of the quiz's own bank only (5.3)."""
    if passage_id is None:
        return None
    if (section.rules or {}).get("allow_passages") is False:
        raise ValidationFailed("Passages are not allowed in this section", code=ids.E_ITEM_TYPE_NOT_ALLOWED,
                               details=[{"loc": ["payload", "meta", "passage_id"], "msg": "passages not allowed"}])
    try:
        p = content_repo.load_passage(db, course.id, passage_id)
    except NotFound:
        p = None
    bank = db.get(QuestionBank, p.bank_id) if p is not None else None
    if bank is None or bank.assessment_id != a.id:
        raise ValidationFailed("The passage is not in this quiz's bank", code=ids.E_PASSAGE_NOT_IN_QUIZ_BANK,
                               details=[{"loc": ["payload", "meta", "passage_id"], "msg": ids.E_PASSAGE_NOT_IN_QUIZ_BANK}])
    return p


def _place_item(db: Session, section: AssessmentSection, item: AssessmentItem, after) -> None:
    """Top-level position: right after `after` (following items shift by one) or at the end of the section."""
    b = _builder()
    if after is None:
        item.position = b._next_pos(db, section.id, None)
        return
    rows = list(db.execute(select(AssessmentItem).where(
        AssessmentItem.section_id == section.id, AssessmentItem.parent_item_id.is_(None))
        .order_by(AssessmentItem.position, AssessmentItem.id)).scalars())
    idx = next((i for i, r in enumerate(rows) if r.id == after.id), len(rows) - 1)
    rows.insert(idx + 1, item)
    b._renumber(rows)


def create_question_in_quiz(db: Session, ctx: AuthzContext, course, a: Assessment, *, section: AssessmentSection,
                            after_item_id: Optional[uuid.UUID], payload: CardPayloadIn,
                            strict_after: bool = True) -> tuple[AssessmentItem, BankQuestion]:
    """5.3: question (quiz bank) + version + item in the caller's transaction; validation first, no commit.
    `strict_after=False` (draft commit): an `after_item_id` that left the section falls back to the end."""
    b = _builder()
    _check_language(course, a, payload.language)
    _check_type(section, a, payload.type, payload.language)
    passage = _quiz_passage(db, course, a, section, payload.meta.passage_id)
    if strict_after:
        after = resolve_after_item(db, a, section, after_item_id)
    else:
        after = None
        if after_item_id is not None:
            cand = db.get(AssessmentItem, after_item_id)
            if cand is not None and cand.section_id == section.id and cand.parent_item_id is None:
                after = cand
    b._caps(db, a, section, 1)
    n = _prepared(db, ctx, payload, payload.points, set())
    meta = _clean_meta(payload)
    bank = quiz_banks.ensure_quiz_bank(db, ctx, course, a)
    quiz_banks.assert_bank_usable(bank, a)
    q = BankQuestion(bank_id=bank.id, passage_id=passage.id if passage is not None else None, type=n["type"],
                     language=payload.language, position=content_svc._next_position(db, bank.id), search_text="",
                     **meta)
    db.add(q)
    db.flush()
    content_svc.new_question_version(db, q, n, actor_id=ctx.user.id, origin="create")
    item = AssessmentItem(assessment_id=a.id, section_id=section.id, kind="question", question_id=q.id,
                          points=payload.points, position=1)
    _place_item(db, section, item, after)
    db.add(item)
    b._flush_unique(db)
    return item, q


# ------------------------------------------------------------------ the public create (direct, no draft)

def create_in_quiz(db: Session, ctx: AuthzContext, course, aid: uuid.UUID, *, section_id: Optional[uuid.UUID],
                   after_item_id: Optional[uuid.UUID], payload: CardPayloadIn):
    b = _builder()
    a = b._manage(db, ctx, course, aid)
    assert_quiz_editable(a)
    section, _created = target_section(db, a, section_id)
    item, q = create_question_in_quiz(db, ctx, course, a, section=section, after_item_id=after_item_id,
                                      payload=payload)
    b._commit(db, a)
    return a, item, q


# ------------------------------------------------------------------ commit a draft ("Done")

def _parse_payload(d: QuestionDraft) -> CardPayloadIn:
    try:
        return CardPayloadIn.model_validate(d.payload)
    except ValidationError as exc:
        e = exc.errors()[0]
        raise _invalid(str(e.get("msg")), ["payload", *[str(x) for x in e.get("loc", ())]]) from None


def _meta_changed(q: BankQuestion, meta: dict, passage_id) -> bool:
    return (meta["topic"] != q.topic or meta["difficulty"] != q.difficulty or meta["section"] != q.section
            or meta["tags"] != list(q.tags or []) or passage_id != q.passage_id)


def _scope_details(u, can_update_all: bool) -> dict:
    return {"assessment_count": u.other_count, "can_update_all": can_update_all,
            "assessments": [x.model_dump(mode="json") for x in u.assessments[:10]]}


def commit_draft(db: Session, ctx: AuthzContext, course, aid: uuid.UUID, draft_id: uuid.UUID, data: CommitIn):
    """5.4. Returns (assessment, item, question, applied, version_created)."""
    b = _builder()
    a = b._manage(db, ctx, course, aid)
    assert_quiz_editable(a)
    d = load_draft(db, a, draft_id)
    if d.draft_rev != data.draft_rev:
        out = draft_out(db, d)
        raise Conflict("The card was changed in another tab", code=ids.E_DRAFT_CONFLICT,
                       details={"draft_rev": out.draft_rev, "payload": out.payload.model_dump(mode="json"),
                                "updated_by_name": out.updated_by_name})
    payload = _parse_payload(d)

    # ---- new card: question + version + item, then the draft goes
    if d.item_id is None:
        section = repo.load_section(db, a.id, d.section_id)
        item, q = create_question_in_quiz(db, ctx, course, a, section=section, after_item_id=d.after_item_id,
                                          payload=payload, strict_after=False)
        db.delete(d)
        b._commit(db, a)
        return a, item, q, "created", True

    # ---- existing card
    item = repo.load_item(db, a.id, d.item_id)
    q = content_repo.load_question(db, course.id, item.question_id, for_update=True)
    bank = db.get(QuestionBank, q.bank_id)
    section = repo.load_section(db, a.id, item.section_id)
    if payload.language != q.language:
        raise ValidationFailed("The language of an existing question cannot change", code="validation_failed",
                               details=[{"loc": ["payload", "language"], "msg": "language_locked"}])
    _check_language(course, a, payload.language)
    current = db.get(QuestionVersion, q.current_version_id)
    in_quiz_bank = bank.assessment_id == a.id
    version_points = payload.points if in_quiz_bank else current.default_points
    n = _prepared(db, ctx, payload, version_points, content_svc._carried(current))
    meta = _clean_meta(payload)
    # M1: an existing card never moves between passages here; `meta.passage_id` is ignored (always present in the
    # payload, so passing it on would detach a passage child when it is null)
    type_changed = n["type"] != q.type
    # compared with the hash of the current version's content (recomputed: rows written by older code paths may carry
    # a different stored hash for the same content)
    content_changed = (content_svc.question_content_hash(q.language, n)
                       != content_svc.question_content_hash(q.language, content_svc._version_content(current)))
    meta_changed = _meta_changed(q, meta, q.passage_id)
    points = Decimal(str(payload.points))

    if not (content_changed or meta_changed or type_changed):
        item.points = points
        db.delete(d)
        b._commit(db, a)
        return a, item, q, "unchanged", False

    u = usage.question_usage(db, course, q, this_assessment_id=a.id, with_published=False)
    # M3: the published-snapshot scan runs only for a type change, and only when the cheap checks do not force `this`
    forced_this = type_changed and (u.other_count > 0 or q.translation_group_id is not None
                                    or usage.published_pins(db, course.id, q))
    can_update_all = can_edit_bank(ctx, course, bank)
    if forced_this:
        path = "this"
    elif u.other_count == 0:
        path = "in_place"
    elif data.scope is None:
        raise Conflict("Choose where the change applies", code=ids.E_SCOPE_REQUIRED,
                       details=_scope_details(u, can_update_all))
    elif data.scope == "all" and not can_update_all:
        raise Forbidden("You cannot change the source question", code=ids.E_SCOPE_NOT_ALLOWED)
    else:
        path = data.scope

    if path == "this":
        if item.parent_item_id is not None:
            raise Conflict("A passage question cannot be copied into this quiz only", code=ids.E_PASSAGE_CHILD_SCOPE)
        _check_type(section, a, n["type"], q.language)
        if not in_quiz_bank:  # the new quiz-bank question's default points are the card's points
            n = _prepared(db, ctx, payload, payload.points, content_svc._carried(current))
        own = quiz_banks.ensure_quiz_bank(db, ctx, course, a)
        q2 = BankQuestion(bank_id=own.id, passage_id=None, type=n["type"], language=q.language,
                          position=content_svc._next_position(db, own.id), search_text="", **meta)
        db.add(q2)
        db.flush()
        content_svc.new_question_version(db, q2, n, actor_id=ctx.user.id, origin="create")
        item.question_id = q2.id
        item.points = points
        db.delete(d)
        b._flush_unique(db)
        b._commit(db, a)
        return a, item, q2, "this", True

    # ---- in place / all: a new version of the source question (and its meta); items untouched except this one's points
    quiz_banks.assert_bank_usable(bank, a)
    if type_changed:
        _check_type(section, a, n["type"], q.language)
    if d.base_version_id != q.current_version_id:
        raise content_svc._version_conflict(q.current_version_id)
    if meta_changed:
        content_svc._apply_meta(db, course, q, QuestionMetaIn(
            topic=payload.meta.topic, difficulty=payload.meta.difficulty, section=payload.meta.section,
            tags=list(payload.meta.tags or [])))
    if content_changed:
        content_svc.new_question_version(db, q, n, actor_id=ctx.user.id, origin="edit")
    if meta_changed:
        content_svc._refresh_search(db, q)
    item.points = points
    db.delete(d)
    b._commit(db, a)
    return a, item, q, path, content_changed
