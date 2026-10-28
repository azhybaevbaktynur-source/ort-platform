"""Per-card drafts (PHASE_7C_DESIGN 5.2, 7, P7C-1, P7C-2).

Every write: `course:content.manage` + the assessment row lock (`builder._manage`) in one transaction. Autosave never
bumps the assessment `draft_rev` (drafts are not quiz structure); content is not validated before Done (half-typed
cards are the point), only the payload size, its type and its language."""
from __future__ import annotations

import json
import uuid
from typing import Iterable, Optional

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext
from app.lms.assessments import repository as repo
from app.lms.assessments.models import Assessment
from app.lms.core import clock
from app.lms.core.errors import Conflict, NotFound, PayloadTooLarge, ValidationFailed
from app.lms.quiz_editor import ids
from app.lms.quiz_editor.models import QuestionDraft
from app.lms.quiz_editor.schemas import CardPayloadIn, CardPayloadOut, DraftCreateIn, DraftOut, DraftUpdateIn
from app.lms.quiz_editor.service import assert_quiz_editable, target_section
from app.models.user import User


# ------------------------------------------------------------------ payload checks and output

def payload_json(payload: CardPayloadIn) -> dict:
    return payload.model_dump(mode="json")


def check_payload(a: Assessment, payload: CardPayloadIn) -> dict:
    """Size cap (413), a known type and a quiz language (422). Returns the JSON to store."""
    from app.lms.content.types import TYPE_NAMES

    body = payload_json(payload)
    if len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > ids.DRAFT_PAYLOAD_MAX:
        raise PayloadTooLarge("The card is too large", code=ids.E_PAYLOAD_TOO_LARGE,
                              details={"max_bytes": ids.DRAFT_PAYLOAD_MAX})
    if payload.type not in TYPE_NAMES:
        raise ValidationFailed("Unsupported question type", code="unsupported_type",
                               details=[{"loc": ["payload", "type"], "msg": f"unsupported type: {payload.type!r}"}])
    if payload.language not in (a.languages or []):
        raise ValidationFailed("The language is not a language of this quiz", code=ids.E_ITEM_LANGUAGE_MISMATCH,
                               details=[{"loc": ["payload", "language"], "msg": ids.E_ITEM_LANGUAGE_MISMATCH}])
    return body


def _image_ids(body: dict) -> list[tuple[list, Optional[uuid.UUID]]]:
    """[(loc, asset id or None when not a UUID)] of every image a stored payload refers to (L1): the card image and
    choice images (`image_asset_id`, or `image.asset_id` as commit reads them)."""
    out: list[tuple[list, Optional[uuid.UUID]]] = []

    def add(loc: list, raw) -> None:
        if raw in (None, ""):
            return
        try:
            out.append((loc, uuid.UUID(str(raw))))
        except ValueError:
            out.append((loc, None))

    add(["payload", "image_asset_id"], body.get("image_asset_id"))
    data = body.get("data")
    choices = data.get("choices") if isinstance(data, dict) else None
    if isinstance(choices, list):
        for i, ch in enumerate(choices):
            if not isinstance(ch, dict):
                continue
            if ch.get("image_asset_id") not in (None, ""):
                add(["payload", "data", "choices", i, "image_asset_id"], ch.get("image_asset_id"))
            elif isinstance(ch.get("image"), dict):
                add(["payload", "data", "choices", i, "image", "asset_id"], ch["image"].get("asset_id"))
    return out


def check_images(db: Session, actor: User, body: dict, carried: set) -> None:
    """L1: every image id of a draft must pass commit's usability rule (`content.service.resolve_refs`: a live image
    of the actor, or carried). `carried` = the refs of the card's question version plus the ids already stored in this
    draft (a colleague co-editing the card keeps the images the other editor added). 422 `validation_failed` with the
    field's loc and msg `asset_not_usable`. One query when everything is usable."""
    from app.lms.content import service as content_svc

    found = _image_ids(body)
    if not found:
        return

    def refuse(loc: list):
        return ValidationFailed("Image is not usable", code="validation_failed",
                                details=[{"loc": loc, "msg": "asset_not_usable"}])

    for loc, aid in found:
        if aid is None:
            raise refuse(loc)
    try:
        content_svc.resolve_refs(db, actor, [aid for _, aid in found], carried=carried)
        return
    except ValidationFailed:
        pass
    for loc, aid in found:  # failure path only: find the field to point at
        try:
            content_svc.resolve_refs(db, actor, [aid], carried=carried)
        except ValidationFailed:
            raise refuse(loc) from None
    raise refuse(found[0][0])  # pragma: no cover


def _carried_for(db: Session, base_version_id: Optional[uuid.UUID], *, stored: Optional[dict] = None) -> set:
    from app.lms.content import service as content_svc
    from app.lms.content.models import QuestionVersion

    out = content_svc._carried(db.get(QuestionVersion, base_version_id)) if base_version_id else set()
    if stored:
        out |= {aid for _, aid in _image_ids(stored) if aid is not None}
    return out


def _names(db: Session, user_ids: Iterable[Optional[str]]) -> dict[str, str]:
    uids = [u for u in set(user_ids) if u]
    if not uids:
        return {}
    return {uid: (name or email) for uid, name, email in db.execute(
        select(User.id, User.display_name, User.email).where(User.id.in_(uids)))}


def draft_out(db: Session, d: QuestionDraft, names: Optional[dict] = None) -> DraftOut:
    names = names if names is not None else _names(db, [d.updated_by_id])
    return DraftOut(id=d.id, item_id=d.item_id, section_id=d.section_id, after_item_id=d.after_item_id,
                    base_version_id=d.base_version_id, payload=CardPayloadOut.model_validate(d.payload),
                    draft_rev=d.draft_rev, updated_at=d.updated_at, updated_by_name=names.get(d.updated_by_id))


def list_drafts(db: Session, a: Assessment) -> list[DraftOut]:
    """All drafts of the quiz (two queries)."""
    rows = list(db.execute(select(QuestionDraft).where(QuestionDraft.assessment_id == a.id)
                           .order_by(QuestionDraft.created_at, QuestionDraft.id)).scalars())
    names = _names(db, [d.updated_by_id for d in rows])
    return [draft_out(db, d, names) for d in rows]


def draft_item_ids(db: Session, a: Assessment) -> set[uuid.UUID]:
    return set(db.execute(select(QuestionDraft.item_id).where(
        QuestionDraft.assessment_id == a.id, QuestionDraft.item_id.is_not(None))).scalars())


def load_draft(db: Session, a: Assessment, draft_id: uuid.UUID) -> QuestionDraft:
    d = db.execute(select(QuestionDraft).where(QuestionDraft.id == draft_id, QuestionDraft.assessment_id == a.id)
                   .execution_options(populate_existing=True)).scalar_one_or_none()
    if d is None:
        raise NotFound("Draft not found", code=ids.E_DRAFT_NOT_FOUND)
    return d


def remove_drafts(db: Session, *, item_ids: Iterable[uuid.UUID] = (), section_id: Optional[uuid.UUID] = None) -> None:
    """Builder hook (2.2 lifecycle): drop the drafts of removed items and the new-card drafts of a removed section,
    and clear position hints pointing at removed items, before the rows go (the FKs are RESTRICT / SET NULL). Drafts of
    existing cards go only with their item (M2: they follow the item across sections, `move_drafts`). No commit."""
    item_ids = list(item_ids)
    conds = []
    if item_ids:
        conds.append(QuestionDraft.item_id.in_(item_ids))
    if section_id is not None:
        conds.append((QuestionDraft.section_id == section_id) & QuestionDraft.item_id.is_(None))
    if conds:
        db.execute(delete(QuestionDraft).where(or_(*conds)).execution_options(synchronize_session=False))
    if item_ids:
        db.execute(update(QuestionDraft).where(QuestionDraft.after_item_id.in_(item_ids))
                   .values(after_item_id=None).execution_options(synchronize_session=False))


def move_drafts(db: Session, *, item_ids: Iterable[uuid.UUID], section_id: uuid.UUID) -> None:
    """Builder hook (M2): an item (with its passage children) moved to another section takes its drafts along. No
    commit."""
    item_ids = list(item_ids)
    if item_ids:
        db.execute(update(QuestionDraft).where(QuestionDraft.item_id.in_(item_ids))
                   .values(section_id=section_id).execution_options(synchronize_session=False))


# ------------------------------------------------------------------ services

def _manage(db: Session, ctx: AuthzContext, course, aid: uuid.UUID) -> Assessment:
    from app.lms.assessments.builder import _manage as builder_manage

    return builder_manage(db, ctx, course, aid)


def resolve_after_item(db: Session, a: Assessment, section, after_item_id: Optional[uuid.UUID]):
    """The top-level item of `section` a new card goes after (None = end of section); 404 / 422 otherwise."""
    if after_item_id is None:
        return None
    it = repo.load_item(db, a.id, after_item_id)
    if it.section_id != section.id or it.parent_item_id is not None:
        raise ValidationFailed("after_item_id must be a top-level item of the section", code="validation_failed",
                               details=[{"loc": ["after_item_id"], "msg": "not a top-level item of the section"}])
    return it


def create_draft(db: Session, ctx: AuthzContext, course, aid: uuid.UUID, data: DraftCreateIn) -> QuestionDraft:
    from app.lms.content.models import BankQuestion

    a = _manage(db, ctx, course, aid)
    assert_quiz_editable(a)
    body = check_payload(a, data.payload)
    created_section = False
    if data.item_id is not None:
        if data.section_id is not None or data.after_item_id is not None:
            raise ValidationFailed("Give item_id or section_id/after_item_id, not both", code="validation_failed",
                                   details=[{"loc": ["item_id"], "msg": "exactly one mode"}])
        it = repo.load_item(db, a.id, data.item_id)
        if it.kind != "question" or it.question_id is None:
            raise NotFound("Item not found", code=ids.E_ITEM_NOT_FOUND)
        existing = db.execute(select(QuestionDraft).where(QuestionDraft.item_id == it.id)).scalar_one_or_none()
        if existing is not None:
            raise Conflict("This card already has a draft", code=ids.E_DRAFT_EXISTS,
                           details=draft_out(db, existing).model_dump(mode="json"))
        q = db.get(BankQuestion, it.question_id)
        check_images(db, ctx.user, body, _carried_for(db, q.current_version_id if q is not None else None))
        d = QuestionDraft(assessment_id=a.id, section_id=it.section_id, item_id=it.id, after_item_id=None,
                          base_version_id=q.current_version_id if q is not None else None, payload=body,
                          draft_rev=1, created_by_id=ctx.user.id, updated_by_id=ctx.user.id)
    else:
        section, created_section = target_section(db, a, data.section_id)
        after = resolve_after_item(db, a, section, data.after_item_id)
        check_images(db, ctx.user, body, set())
        d = QuestionDraft(assessment_id=a.id, section_id=section.id, item_id=None,
                          after_item_id=after.id if after is not None else None, base_version_id=None,
                          payload=body, draft_rev=1, created_by_id=ctx.user.id, updated_by_id=ctx.user.id)
    db.add(d)
    db.flush()
    if created_section:
        a.draft_rev += 1  # the default section is quiz structure; the draft itself is not (P7C-2)
    db.commit()
    return d


def update_draft(db: Session, ctx: AuthzContext, course, aid: uuid.UUID, draft_id: uuid.UUID,
                 data: DraftUpdateIn) -> QuestionDraft:
    """Single-statement optimistic update (`WHERE draft_rev = :rev`): the loser gets the winner's state."""
    a = _manage(db, ctx, course, aid)
    body = check_payload(a, data.payload)
    if _image_ids(body):
        cur = db.execute(select(QuestionDraft.base_version_id, QuestionDraft.payload).where(
            QuestionDraft.id == draft_id, QuestionDraft.assessment_id == a.id)).first()
        if cur is not None:  # a missing draft is answered below (404 from the conflict path)
            check_images(db, ctx.user, body, _carried_for(db, cur.base_version_id, stored=cur.payload))
    res = db.execute(
        update(QuestionDraft)
        .where(QuestionDraft.id == draft_id, QuestionDraft.assessment_id == a.id,
               QuestionDraft.draft_rev == data.draft_rev)
        .values(payload=body, draft_rev=QuestionDraft.draft_rev + 1, updated_by_id=ctx.user.id,
                updated_at=clock.now())
        .execution_options(synchronize_session=False)
    )
    if res.rowcount == 0:
        d = load_draft(db, a, draft_id)  # 404 when it is gone (committed, discarded, item removed)
        out = draft_out(db, d)
        db.rollback()
        raise Conflict("The card was changed in another tab", code=ids.E_DRAFT_CONFLICT,
                       details={"draft_rev": out.draft_rev, "payload": out.payload.model_dump(mode="json"),
                                "updated_by_name": out.updated_by_name})
    db.commit()
    return load_draft(db, a, draft_id)


def delete_draft(db: Session, ctx: AuthzContext, course, aid: uuid.UUID, draft_id: uuid.UUID) -> None:
    a = _manage(db, ctx, course, aid)
    db.execute(delete(QuestionDraft).where(QuestionDraft.id == draft_id, QuestionDraft.assessment_id == a.id)
               .execution_options(synchronize_session=False))
    db.commit()
