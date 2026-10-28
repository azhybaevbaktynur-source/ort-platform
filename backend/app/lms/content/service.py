"""Content service (design 3.6): banks, questions, passages, versions, translations.

Services take `db` and the AuthzContext, own the transaction (one commit at the end) and raise
`LMSError` before it. Authorization (`require_course`) is done by the routes.

Public helpers for the importer (slice C5), no commit inside:
    new_question_version(db, q, content, *, actor_id, origin) -> QuestionVersion
    new_passage_version(db, p, content, *, actor_id, origin) -> PassageVersion
    question_content_hash(language, content) -> str
    passage_content_hash(language, content) -> str
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext
from app.lms.content import repository as repo
from app.lms.content.models import (
    BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion, TranslationGroup,
)
from app.lms.content.richtext import (
    EXPLANATION_MAX, PASSAGE_BODY_MAX, PASSAGE_TITLE_MAX, STEM_MAX, clean_text,
)
from app.lms.content.schemas import (
    BankCreateIn, BankUpdateIn, PassageCreateIn, PassageUpdateIn, QuestionContentIn, QuestionCreateIn,
    QuestionMetaIn, QuestionUpdateIn, TranslationCreateIn,
)
from app.lms.content.types import get_type
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.models.user import User

SEARCH_MAX = 8000
_TWO_DP = Decimal("0.01")


# ----------------------------------------------------------------------------- hashing / normalising

def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _is_ref(x: Any) -> bool:
    return isinstance(x, dict) and set(x) == {"asset_id", "sha256"}


def reduce_refs(value: Any) -> Any:
    """ImageRefs -> their asset_id (hash input)."""
    if _is_ref(value):
        return value["asset_id"]
    if isinstance(value, dict):
        return {k: reduce_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [reduce_refs(v) for v in value]
    return value


def collect_refs(value: Any, out: Optional[set] = None) -> set:
    """asset ids referenced anywhere inside `value`."""
    out = set() if out is None else out
    if _is_ref(value):
        try:
            out.add(uuid.UUID(str(value["asset_id"])))
        except ValueError:
            pass
    elif isinstance(value, dict):
        for v in value.values():
            collect_refs(v, out)
    elif isinstance(value, list):
        for v in value:
            collect_refs(v, out)
    return out


def _bad(loc: str, msg: str, code: str = "invalid_question_data") -> ValidationFailed:
    return ValidationFailed("Invalid content", code=code, details=[{"loc": [loc], "msg": msg}])


def _clean(value: Any, max_len: int, loc: str, code: str = "invalid_question_data") -> str:
    try:
        return clean_text(value, max_len)
    except ValueError as exc:
        raise _bad(loc, str(exc), code) from None


def _points(raw: Any) -> Decimal:
    try:
        p = Decimal(str(raw if raw is not None else 1))
    except (InvalidOperation, ValueError):
        raise _bad("default_points", "must be a number") from None
    if not p.is_finite() or p < 0 or p > 1000:
        raise _bad("default_points", "must be between 0 and 1000")
    return p.quantize(_TWO_DP)


def _image_ref(raw: Any, loc: str = "image") -> Optional[dict]:
    if not raw:
        return None
    from app.lms.content.types.base import ImageRef

    try:
        return ImageRef(**raw).model_dump()
    except Exception:
        raise _bad(loc, "invalid image reference") from None


def normalize_question_content(language: str, content: dict) -> dict:
    """Clean text, validate `data` with the type registry, quantize points. Idempotent."""
    t = get_type(content.get("type"))
    data = t.validate(content.get("data") if content.get("data") is not None else {})
    expl = content.get("explanation")
    return {
        "type": t.name,
        "stem": _clean(content.get("stem") or "", STEM_MAX, "stem"),
        "data": data,
        "explanation": _clean(expl, EXPLANATION_MAX, "explanation") if expl else None,
        "default_points": _points(content.get("default_points", 1)),
        "image": _image_ref(content.get("image")),
    }


def question_content_hash(language: str, content: dict) -> str:
    n = normalize_question_content(language, content)
    t = get_type(n["type"])
    payload = {
        "type": n["type"], "schema_version": t.schema_version, "language": language, "stem": n["stem"],
        "data": reduce_refs(n["data"]), "explanation": n["explanation"],
        "default_points": str(n["default_points"]),
        "image": n["image"]["asset_id"] if n["image"] else None,
    }
    return hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()


def normalize_passage_content(content: dict) -> dict:
    title = content.get("title")
    title = _clean(title, PASSAGE_TITLE_MAX, "title", "validation_failed").strip() if title else None
    body = _clean(content.get("body") or "", PASSAGE_BODY_MAX, "body", "validation_failed")
    if not body.strip():
        raise _bad("body", "must not be empty", "validation_failed")
    return {"title": title or None, "body": body, "image": _image_ref(content.get("image"))}


def passage_content_hash(language: str, content: dict) -> str:
    n = normalize_passage_content(content)
    payload = {"language": language, "title": n["title"], "body": n["body"],
               "image": n["image"]["asset_id"] if n["image"] else None}
    return hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()


def build_search_text(stem: str, qtype: str, data: dict, topic: Optional[str], q_num: Optional[str]) -> str:
    parts = [stem, *get_type(qtype).search_strings(data), topic or "", q_num or ""]
    return "\n".join(p for p in parts if p).casefold()[:SEARCH_MAX]


# ----------------------------------------------------------------------------- version creation (shared)

def new_question_version(db: Session, q: BankQuestion, content: dict, *, actor_id: Optional[str],
                         origin: str) -> QuestionVersion:
    """Insert the next immutable version of `q` and point `q` at it. Caller holds the row lock and commits.

    `content`: type, stem, data, explanation, default_points, image (ImageRef dict with sha256 or None).
    The question row must exist (flushed). Language is fixed by the row.
    """
    db.flush()
    n = normalize_question_content(q.language, content)
    t = get_type(n["type"])
    version_no = (db.execute(
        select(func.max(QuestionVersion.version_no)).where(QuestionVersion.question_id == q.id)
    ).scalar() or 0) + 1
    v = QuestionVersion(
        question_id=q.id, version_no=version_no, language=q.language, type=n["type"],
        schema_version=t.schema_version, stem=n["stem"], data=n["data"], explanation=n["explanation"],
        default_points=n["default_points"], image=n["image"],
        content_hash=question_content_hash(q.language, n), origin=origin, created_by_id=actor_id,
    )
    db.add(v)
    db.flush()
    q.current_version_id = v.id
    q.type = n["type"]
    q.search_text = build_search_text(n["stem"], n["type"], n["data"], q.topic, q.q_num)
    db.flush()
    return v


def new_passage_version(db: Session, p: Passage, content: dict, *, actor_id: Optional[str],
                        origin: str) -> PassageVersion:
    """Insert the next immutable version of passage `p` (content: title, body, image). No commit."""
    db.flush()
    n = normalize_passage_content(content)
    version_no = (db.execute(
        select(func.max(PassageVersion.version_no)).where(PassageVersion.passage_id == p.id)
    ).scalar() or 0) + 1
    v = PassageVersion(
        passage_id=p.id, version_no=version_no, language=p.language, title=n["title"], body=n["body"],
        image=n["image"], content_hash=passage_content_hash(p.language, n), origin=origin, created_by_id=actor_id,
    )
    db.add(v)
    db.flush()
    p.current_version_id = v.id
    db.flush()
    return v


# ----------------------------------------------------------------------------- images (P2-16)

def _files_resolver():
    """C3's resolve_image_refs when present, else the local equivalent below."""
    import importlib

    for mod in ("app.lms.files", "app.lms.files.service", "app.lms.files.images"):
        try:
            fn = getattr(importlib.import_module(mod), "resolve_image_refs", None)
        except ImportError:
            continue
        if callable(fn):
            return fn
    return None


def _local_resolve(db: Session, actor: User, ids: Iterable[uuid.UUID], *, carried: set) -> dict:
    from app.lms.files.models import Asset

    ids = list(dict.fromkeys(ids))
    out: dict = {}
    rows = db.execute(select(Asset).where(Asset.id.in_(ids))).scalars().all() if ids else []
    for a in rows:
        if a.id in carried or (a.deleted_at is None and a.owner_id == actor.id):
            out[a.id] = {"asset_id": str(a.id), "sha256": a.sha256}
    for i in ids:
        if i not in out:
            raise ValidationFailed("Asset not usable", code="asset_not_usable",
                                   details=[{"loc": ["image_asset_id"], "msg": "asset_not_usable"}])
    return out


def resolve_refs(db: Session, actor: User, ids: Iterable[uuid.UUID], *, carried: set) -> dict:
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {}
    fn = _files_resolver() or _local_resolve
    return fn(db, actor, ids, carried=carried)


def _choice_image_pairs(data: Any) -> list:
    """[(choice dict, asset UUID)] for choices carrying an image reference by id."""
    pairs = []
    if not isinstance(data, dict) or not isinstance(data.get("choices"), list):
        return pairs
    for ch in data["choices"]:
        if not isinstance(ch, dict):
            continue
        raw = ch.pop("image_asset_id", None)
        img = ch.pop("image", None)
        if raw is None and isinstance(img, dict):
            raw = img.get("asset_id")
        if raw in (None, ""):
            continue
        try:
            aid = uuid.UUID(str(raw))
        except ValueError:
            raise ValidationFailed("Asset not usable", code="asset_not_usable",
                                   details=[{"loc": ["image_asset_id"], "msg": "asset_not_usable"}]) from None
        pairs.append((ch, aid))
    return pairs


def prepare_content(db: Session, actor: User, c: QuestionContentIn, carried: set) -> dict:
    """Request content -> content dict with resolved ImageRefs (not yet normalised)."""
    data = copy.deepcopy(c.data)
    pairs = _choice_image_pairs(data)
    ids = {a for _, a in pairs}
    if c.image_asset_id:
        ids.add(c.image_asset_id)
    refs = resolve_refs(db, actor, ids, carried=carried)
    for ch, aid in pairs:
        ch["image"] = refs[aid]
    return {
        "type": c.type, "stem": c.stem, "data": data, "explanation": c.explanation,
        "default_points": c.default_points, "image": refs[c.image_asset_id] if c.image_asset_id else None,
    }


def _version_content(v: QuestionVersion) -> dict:
    return {"type": v.type, "stem": v.stem, "data": copy.deepcopy(v.data), "explanation": v.explanation,
            "default_points": v.default_points, "image": copy.deepcopy(v.image) if v.image else None}


def _carried(v: Optional[QuestionVersion], *more: Optional[QuestionVersion]) -> set:
    out: set = set()
    for x in (v, *more):
        if x is not None:
            collect_refs(x.data, out)
            collect_refs(x.image, out)
    return out


# ----------------------------------------------------------------------------- small helpers

def _check_language(course, language: Optional[str], loc: str = "language") -> None:
    if language is not None and language not in (course.languages or []):
        raise ValidationFailed("Language not in course", code="language_not_in_course",
                               details=[{"loc": [loc], "msg": "language_not_in_course"}])


def _version_conflict(current_version_id: Optional[uuid.UUID]) -> Conflict:
    return Conflict("The content was changed by someone else", code="version_conflict",
                    details={"current_version_id": str(current_version_id) if current_version_id else None})


def _clean_label(value: Optional[str], max_len: int) -> Optional[str]:
    if value is None:
        return None
    v = _clean(value, max_len * 4, "meta", "validation_failed").strip()
    if len(v) > max_len:
        raise _bad("meta", f"exceeds {max_len} characters", "validation_failed")
    return v or None


def _clean_tags(tags: Iterable[str]) -> list:
    out: list = []
    for t in tags:
        t = _clean_label(t, 40)
        if t and t not in out:
            out.append(t)
    if len(out) > 20:
        raise _bad("tags", "at most 20 tags", "validation_failed")
    return out


def _lock_bank(db: Session, bank: QuestionBank) -> QuestionBank:
    db.refresh(bank, with_for_update=True)
    if bank.deleted_at is not None:
        raise NotFound("Bank not found", code="bank_not_found")
    return bank


def _next_position(db: Session, bank_id: uuid.UUID) -> int:
    return (db.execute(select(func.max(BankQuestion.position)).where(BankQuestion.bank_id == bank_id)).scalar()
            or 0) + 1


def _commit_translating(db: Session) -> None:
    """Commit; the group/language unique index race becomes 409 translation_language_taken."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "group_language" in str(exc.orig) or "translation_group_id" in str(exc.orig):
            raise Conflict("A variant in this language already exists", code="translation_language_taken") from None
        raise


def _flush_translating(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if "group_language" in str(exc.orig) or "translation_group_id" in str(exc.orig):
            raise Conflict("A variant in this language already exists", code="translation_language_taken") from None
        raise


def _passage_for(db: Session, course, bank_id: uuid.UUID, passage_id: uuid.UUID) -> Passage:
    p = repo.load_passage(db, course.id, passage_id)
    if p.bank_id != bank_id:
        raise NotFound("Passage not found", code="passage_not_found")
    # FOR SHARE: serializes with soft_delete_passage (FOR UPDATE); re-check after the lock
    db.refresh(p, with_for_update={"read": True})
    if p.deleted_at is not None:
        raise NotFound("Passage not found", code="passage_not_found")
    return p


# ----------------------------------------------------------------------------- banks

def create_bank(db: Session, ctx: AuthzContext, course, data: BankCreateIn) -> QuestionBank:
    _check_language(course, data.default_language, "default_language")
    bank = QuestionBank(
        owner_id=ctx.user.id, course_id=course.id, title=data.title.strip(),
        description=data.description, default_language=data.default_language,
    )
    db.add(bank)
    db.commit()
    return bank


# --- Phase 7c S2 begin --- (PHASE_7C_DESIGN 5.1: a quiz bank is deleted, restored and titled by its quiz)
def _refuse_quiz_bank(bank: QuestionBank) -> None:
    if bank.assessment_id is not None:
        from app.lms.quiz_editor.ids import E_QUIZ_BANK_FOLLOWS_QUIZ

        raise Conflict("This bank belongs to a quiz and follows it", code=E_QUIZ_BANK_FOLLOWS_QUIZ)
# --- Phase 7c S2 end ---


def update_bank(db: Session, ctx: AuthzContext, course, bank_id: uuid.UUID, data: BankUpdateIn) -> QuestionBank:
    bank = repo.load_bank(db, course.id, bank_id, for_update=True)
    fields = data.model_fields_set
    if "title" in fields:  # --- Phase 7c S2 --- (the quiz bank title follows the quiz, Q3)
        _refuse_quiz_bank(bank)
    if "title" in fields and data.title is not None:
        bank.title = data.title.strip()
    if "description" in fields:
        bank.description = data.description
    if "default_language" in fields:
        _check_language(course, data.default_language, "default_language")
        bank.default_language = data.default_language
    db.commit()
    return bank


def soft_delete_bank(db: Session, ctx: AuthzContext, course, bank_id: uuid.UUID) -> None:
    bank = repo.load_bank(db, course.id, bank_id, include_deleted=True, for_update=True)
    _refuse_quiz_bank(bank)  # --- Phase 7c S2 ---
    if bank.deleted_at is not None:
        raise Conflict("Bank already deleted", code="already_deleted")
    bank.soft_delete(ctx.user.id)
    db.commit()


def restore_bank(db: Session, ctx: AuthzContext, course, bank_id: uuid.UUID) -> QuestionBank:
    bank = repo.load_bank(db, course.id, bank_id, include_deleted=True, for_update=True)
    _refuse_quiz_bank(bank)  # --- Phase 7c S2 ---
    if bank.deleted_at is None:
        raise Conflict("Bank is not deleted", code="not_deleted")
    if bank.source_id:
        clash = db.execute(select(QuestionBank.id).where(
            QuestionBank.course_id == course.id, QuestionBank.source_id == bank.source_id,
            QuestionBank.deleted_at.is_(None), QuestionBank.id != bank.id)).first()
        if clash:
            raise Conflict("A live bank with this source exists", code="source_conflict")
    bank.restore()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("A live bank with this source exists", code="source_conflict") from None
    return bank


# ----------------------------------------------------------------------------- questions

def create_question(db: Session, ctx: AuthzContext, course, bank: QuestionBank, data: QuestionCreateIn,
                    *, origin: str = "create") -> BankQuestion:
    actor = ctx.user
    _check_language(course, data.language)
    content = prepare_content(db, actor, data, set())
    normalize_question_content(data.language, content)  # validate before any write
    topic = _clean_label(data.topic, 200)
    section = _clean_label(data.section, 40)
    tags = _clean_tags(data.tags)
    bank = _lock_bank(db, bank)
    if data.passage_id:
        _passage_for(db, course, bank.id, data.passage_id)
    q = BankQuestion(
        bank_id=bank.id, passage_id=data.passage_id, type=data.type, language=data.language, topic=topic,
        difficulty=data.difficulty, section=section, tags=tags, position=_next_position(db, bank.id),
        search_text="",
    )
    db.add(q)
    db.flush()
    new_question_version(db, q, content, actor_id=actor.id, origin=origin)
    db.commit()
    return q


def _apply_meta(db: Session, course, q: BankQuestion, meta: QuestionMetaIn) -> bool:
    changed = False
    f = meta.model_fields_set
    if "topic" in f:
        v = _clean_label(meta.topic, 200)
        changed |= v != q.topic
        q.topic = v
    if "difficulty" in f:
        changed |= meta.difficulty != q.difficulty
        q.difficulty = meta.difficulty
    if "section" in f:
        v = _clean_label(meta.section, 40)
        changed |= v != q.section
        q.section = v
    if "tags" in f:
        v = _clean_tags(meta.tags or [])
        changed |= v != list(q.tags or [])
        q.tags = v
    if "passage_id" in f:
        if meta.passage_id is not None:
            _passage_for(db, course, q.bank_id, meta.passage_id)
        changed |= meta.passage_id != q.passage_id
        q.passage_id = meta.passage_id
    return changed


def _refresh_search(db: Session, q: BankQuestion) -> None:
    v = db.get(QuestionVersion, q.current_version_id)
    q.search_text = build_search_text(v.stem, v.type, v.data, q.topic, q.q_num)


def update_question(db: Session, ctx: AuthzContext, course, question_id: uuid.UUID,
                    data: QuestionUpdateIn) -> tuple[BankQuestion, bool]:
    actor = ctx.user
    q = repo.load_question(db, course.id, question_id, for_update=True)
    new_version = False
    meta_changed = False
    if data.content is not None:
        if data.base_version_id is None:
            raise ValidationFailed("base_version_id is required to change content", code="validation_failed",
                                   details=[{"loc": ["base_version_id"], "msg": "required"}])
        if data.base_version_id != q.current_version_id:
            raise _version_conflict(q.current_version_id)
        current = db.get(QuestionVersion, q.current_version_id)
        content = prepare_content(db, actor, data.content, _carried(current))
        n = normalize_question_content(q.language, content)
        if question_content_hash(q.language, n) != current.content_hash:
            new_version = True
            new_question_version(db, q, n, actor_id=actor.id, origin="edit")
    if data.meta is not None:
        meta_changed = _apply_meta(db, course, q, data.meta)
        if meta_changed:
            _refresh_search(db, q)
    db.commit()
    return q, not (new_version or meta_changed)


def revert_question(db: Session, ctx: AuthzContext, course, question_id: uuid.UUID, version_id: uuid.UUID,
                    base_version_id: uuid.UUID) -> BankQuestion:
    q = repo.load_question(db, course.id, question_id, for_update=True)
    if base_version_id != q.current_version_id:
        raise _version_conflict(q.current_version_id)
    target = repo.load_question_version(db, q.id, version_id)
    current = db.get(QuestionVersion, q.current_version_id)
    if target.id != current.id:
        content = _version_content(target)
        # refs of the target are accepted as-is (P2-16): they come from our own history
        new_question_version(db, q, content, actor_id=ctx.user.id, origin="revert")
    db.commit()
    return q


def soft_delete_question(db: Session, ctx: AuthzContext, course, question_id: uuid.UUID) -> None:
    q = repo.load_question(db, course.id, question_id, include_deleted=True, for_update=True)
    if q.deleted_at is not None:
        raise Conflict("Question already deleted", code="already_deleted")
    q.soft_delete(ctx.user.id)
    db.commit()


def restore_question(db: Session, ctx: AuthzContext, course, question_id: uuid.UUID) -> BankQuestion:
    q = repo.load_question(db, course.id, question_id, include_deleted=True, include_deleted_bank=True,
                           for_update=True)
    if q.deleted_at is None:
        raise Conflict("Question is not deleted", code="not_deleted")
    bank = db.get(QuestionBank, q.bank_id)
    if bank.deleted_at is not None:
        raise Conflict("The bank is deleted", code="bank_deleted")
    if q.passage_id is not None:
        pas = db.get(Passage, q.passage_id)
        if pas is not None:
            db.refresh(pas, with_for_update={"read": True})
            if pas.deleted_at is not None:
                raise Conflict("The passage is deleted", code="passage_deleted")
    q.restore()
    _commit_translating(db)
    return q


def move_question(db: Session, ctx: AuthzContext, course, question_id: uuid.UUID, direction: str) -> BankQuestion:
    q = repo.load_question(db, course.id, question_id)
    _lock_bank(db, db.get(QuestionBank, q.bank_id))
    q = repo.load_question(db, course.id, question_id, for_update=True)
    for _ in range(2):  # second pass after renumbering ties
        stmt = select(BankQuestion).where(
            BankQuestion.bank_id == q.bank_id, BankQuestion.deleted_at.is_(None), BankQuestion.id != q.id,
            BankQuestion.section.is_(None) if q.section is None else BankQuestion.section == q.section,
        )
        key = (BankQuestion.position, BankQuestion.id)
        if direction == "up":
            stmt = stmt.where((BankQuestion.position < q.position) |
                              ((BankQuestion.position == q.position) & (BankQuestion.id < q.id)))
            stmt = stmt.order_by(BankQuestion.position.desc(), BankQuestion.id.desc())
        else:
            stmt = stmt.where((BankQuestion.position > q.position) |
                              ((BankQuestion.position == q.position) & (BankQuestion.id > q.id)))
            stmt = stmt.order_by(BankQuestion.position.asc(), BankQuestion.id.asc())
        nb = db.execute(stmt.limit(1)).scalar_one_or_none()
        if nb is None:
            raise Conflict("Cannot move further", code="invalid_move")
        if nb.position != q.position:
            q.position, nb.position = nb.position, q.position
            db.commit()
            return q
        rows = db.execute(select(BankQuestion).where(BankQuestion.bank_id == q.bank_id)
                          .order_by(BankQuestion.position, BankQuestion.id)).scalars().all()
        for i, r in enumerate(rows, start=1):
            r.position = i
        db.flush()
    raise Conflict("Cannot move", code="invalid_move")  # pragma: no cover


# ----------------------------------------------------------------------------- translations

def _group_member_languages(db: Session, group_id: uuid.UUID, exclude: Optional[uuid.UUID] = None) -> set:
    stmt = select(BankQuestion.language).where(BankQuestion.translation_group_id == group_id,
                                               BankQuestion.deleted_at.is_(None))
    if exclude is not None:
        stmt = stmt.where(BankQuestion.id != exclude)
    return set(db.execute(stmt).scalars())


def add_translation(db: Session, ctx: AuthzContext, course, question_id: uuid.UUID,
                    data: TranslationCreateIn) -> BankQuestion:
    actor = ctx.user
    src = repo.load_question(db, course.id, question_id)
    target_bank_id = data.bank_id or src.bank_id
    bank = repo.load_bank(db, course.id, target_bank_id)
    # lock order: banks (sorted by id), then the question (same as move_question)
    for bid in sorted({src.bank_id, bank.id}, key=str):
        _lock_bank(db, bank if bid == bank.id else db.get(QuestionBank, bid))
    src = repo.load_question(db, course.id, question_id, for_update=True)
    _check_language(course, data.language)
    if data.language == src.language:
        raise Conflict("Variant language equals the source language", code="translation_language_taken")
    if src.translation_group_id and data.language in _group_member_languages(db, src.translation_group_id):
        raise Conflict("A variant in this language already exists", code="translation_language_taken")
    current = db.get(QuestionVersion, src.current_version_id)
    content = _version_content(current)
    if src.translation_group_id is None:
        group = TranslationGroup(course_id=course.id, created_by_id=actor.id)
        db.add(group)
        db.flush()
        src.translation_group_id = group.id
    _lock_bank(db, bank)
    new = BankQuestion(
        bank_id=bank.id, passage_id=None, translation_group_id=src.translation_group_id, type=src.type,
        language=data.language, topic=src.topic, difficulty=src.difficulty, section=src.section,
        tags=list(src.tags or []), position=_next_position(db, bank.id), q_num=src.q_num, search_text="",
    )
    db.add(new)
    _flush_translating(db)
    new_question_version(db, new, content, actor_id=actor.id, origin="create")
    _commit_translating(db)
    return new


def link_translation(db: Session, ctx: AuthzContext, course, question_id: uuid.UUID, other_id: uuid.UUID) -> None:
    if question_id == other_id:
        raise Conflict("Cannot link a question to itself", code="translation_scope_mismatch")
    loaded = {i: repo.load_question(db, course.id, i, for_update=True) for i in sorted({question_id, other_id}, key=str)}
    q, other = loaded[question_id], loaded[other_id]
    if q.type != other.type:
        raise Conflict("Variants must have the same type", code="translation_type_mismatch")
    if q.language == other.language:
        raise Conflict("Variants need different languages", code="translation_language_taken")
    if q.translation_group_id and q.translation_group_id == other.translation_group_id:
        return
    if q.translation_group_id and other.translation_group_id:
        raise Conflict("Both questions already belong to different groups", code="translation_language_taken")
    gid = q.translation_group_id or other.translation_group_id
    if gid is None:
        group = TranslationGroup(course_id=course.id, created_by_id=ctx.user.id)
        db.add(group)
        db.flush()
        gid = group.id
    else:
        joining = other if q.translation_group_id else q
        if joining.language in _group_member_languages(db, gid):
            raise Conflict("A variant in this language already exists", code="translation_language_taken")
    q.translation_group_id = gid
    other.translation_group_id = gid
    _commit_translating(db)


def unlink_translation(db: Session, ctx: AuthzContext, course, question_id: uuid.UUID) -> None:
    q = repo.load_question(db, course.id, question_id, for_update=True)
    gid = q.translation_group_id
    if gid is None:
        return
    q.translation_group_id = None
    db.flush()
    rest = db.execute(select(BankQuestion).where(BankQuestion.translation_group_id == gid)).scalars().all()
    if len(rest) <= 1:
        for r in rest:
            r.translation_group_id = None
        db.flush()
        g = db.get(TranslationGroup, gid)
        if g is not None:
            db.delete(g)
    db.commit()


# ----------------------------------------------------------------------------- passages

def _prepare_passage(db: Session, actor: User, title, body, image_asset_id, carried: set) -> dict:
    refs = resolve_refs(db, actor, [image_asset_id] if image_asset_id else [], carried=carried)
    return {"title": title, "body": body, "image": refs[image_asset_id] if image_asset_id else None}


def create_passage(db: Session, ctx: AuthzContext, course, bank: QuestionBank, data: PassageCreateIn) -> Passage:
    actor = ctx.user
    _check_language(course, data.language)
    content = _prepare_passage(db, actor, data.title, data.body, data.image_asset_id, set())
    normalize_passage_content(content)
    bank = _lock_bank(db, bank)
    p = Passage(bank_id=bank.id, language=data.language)
    db.add(p)
    db.flush()
    new_passage_version(db, p, content, actor_id=actor.id, origin="create")
    db.commit()
    return p


def update_passage(db: Session, ctx: AuthzContext, course, passage_id: uuid.UUID,
                   data: PassageUpdateIn) -> tuple[Passage, bool]:
    actor = ctx.user
    p = repo.load_passage(db, course.id, passage_id, for_update=True)
    if data.base_version_id != p.current_version_id:
        raise _version_conflict(p.current_version_id)
    current = db.get(PassageVersion, p.current_version_id)
    carried = set()
    collect_refs(current.image, carried)
    content = _prepare_passage(db, actor, data.title, data.body, data.image_asset_id, carried)
    n = normalize_passage_content(content)
    unchanged = passage_content_hash(p.language, n) == current.content_hash
    if not unchanged:
        new_passage_version(db, p, n, actor_id=actor.id, origin="edit")
    db.commit()
    return p, unchanged


def revert_passage(db: Session, ctx: AuthzContext, course, passage_id: uuid.UUID, version_id: uuid.UUID,
                   base_version_id: uuid.UUID) -> Passage:
    p = repo.load_passage(db, course.id, passage_id, for_update=True)
    if base_version_id != p.current_version_id:
        raise _version_conflict(p.current_version_id)
    target = repo.load_passage_version(db, p.id, version_id)
    if target.id != p.current_version_id:
        new_passage_version(db, p, {"title": target.title, "body": target.body,
                                    "image": copy.deepcopy(target.image) if target.image else None},
                            actor_id=ctx.user.id, origin="revert")
    db.commit()
    return p


def soft_delete_passage(db: Session, ctx: AuthzContext, course, passage_id: uuid.UUID) -> None:
    p = repo.load_passage(db, course.id, passage_id, include_deleted=True, for_update=True)
    if p.deleted_at is not None:
        raise Conflict("Passage already deleted", code="already_deleted")
    in_use = db.execute(select(func.count()).select_from(BankQuestion).where(
        BankQuestion.passage_id == p.id, BankQuestion.deleted_at.is_(None))).scalar()
    if in_use:
        raise Conflict("Passage is used by questions", code="passage_in_use", details={"question_count": in_use})
    p.soft_delete(ctx.user.id)
    db.commit()


def restore_passage(db: Session, ctx: AuthzContext, course, passage_id: uuid.UUID) -> Passage:
    p = repo.load_passage(db, course.id, passage_id, include_deleted=True, include_deleted_bank=True,
                          for_update=True)
    if p.deleted_at is None:
        raise Conflict("Passage is not deleted", code="not_deleted")
    if db.get(QuestionBank, p.bank_id).deleted_at is not None:
        raise Conflict("The bank is deleted", code="bank_deleted")
    p.restore()
    db.commit()
    return p
