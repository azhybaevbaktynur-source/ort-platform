"""Content repository: the one place that joins through versions (design 3.5).

Loaders implement the anti-IDOR rule: a child is always looked up *through the course*
(bank.course_id), so an id from another course is a 404.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.lms.content.models import (
    BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion,
)
from app.lms.content.types import get_type, media_url
from app.lms.core.errors import NotFound

CHUNK = 500


def _chunks(ids: list, n: int = CHUNK):
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


# --------------------------------------------------------------------------- loaders

def load_bank(db: Session, course_id: uuid.UUID, bank_id: uuid.UUID, *, include_deleted: bool = False,
              for_update: bool = False) -> QuestionBank:
    stmt = select(QuestionBank).where(QuestionBank.id == bank_id, QuestionBank.course_id == course_id)
    if not include_deleted:
        stmt = stmt.where(QuestionBank.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    bank = db.execute(stmt).scalar_one_or_none()
    if bank is None:
        raise NotFound("Bank not found", code="bank_not_found")
    return bank


def load_question(db: Session, course_id: uuid.UUID, question_id: uuid.UUID, *, include_deleted: bool = False,
                  include_deleted_bank: bool = False, for_update: bool = False) -> BankQuestion:
    stmt = (
        select(BankQuestion)
        .join(QuestionBank, QuestionBank.id == BankQuestion.bank_id)
        .where(BankQuestion.id == question_id, QuestionBank.course_id == course_id)
    )
    if not include_deleted:
        stmt = stmt.where(BankQuestion.deleted_at.is_(None))
    if not include_deleted_bank:
        stmt = stmt.where(QuestionBank.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update(of=BankQuestion).execution_options(populate_existing=True)
    q = db.execute(stmt).scalar_one_or_none()
    if q is None:
        raise NotFound("Question not found", code="question_not_found")
    return q


def load_passage(db: Session, course_id: uuid.UUID, passage_id: uuid.UUID, *, include_deleted: bool = False,
                 include_deleted_bank: bool = False, for_update: bool = False) -> Passage:
    stmt = (
        select(Passage)
        .join(QuestionBank, QuestionBank.id == Passage.bank_id)
        .where(Passage.id == passage_id, QuestionBank.course_id == course_id)
    )
    if not include_deleted:
        stmt = stmt.where(Passage.deleted_at.is_(None))
    if not include_deleted_bank:
        stmt = stmt.where(QuestionBank.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update(of=Passage).execution_options(populate_existing=True)
    p = db.execute(stmt).scalar_one_or_none()
    if p is None:
        raise NotFound("Passage not found", code="passage_not_found")
    return p


def load_question_version(db: Session, question_id: uuid.UUID, version_id: uuid.UUID) -> QuestionVersion:
    v = db.execute(
        select(QuestionVersion).where(QuestionVersion.id == version_id, QuestionVersion.question_id == question_id)
    ).scalar_one_or_none()
    if v is None:
        raise NotFound("Version not found", code="version_not_found")
    return v


def load_passage_version(db: Session, passage_id: uuid.UUID, version_id: uuid.UUID) -> PassageVersion:
    v = db.execute(
        select(PassageVersion).where(PassageVersion.id == version_id, PassageVersion.passage_id == passage_id)
    ).scalar_one_or_none()
    if v is None:
        raise NotFound("Version not found", code="version_not_found")
    return v


def load_versions(db: Session, version_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, QuestionVersion]:
    ids = list(dict.fromkeys(version_ids))
    out: dict[uuid.UUID, QuestionVersion] = {}
    for part in _chunks(ids):
        for v in db.execute(select(QuestionVersion).where(QuestionVersion.id.in_(part))).scalars():
            out[v.id] = v
    return out


def load_passage_versions(db: Session, version_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, PassageVersion]:
    ids = list(dict.fromkeys(version_ids))
    out: dict[uuid.UUID, PassageVersion] = {}
    for part in _chunks(ids):
        for v in db.execute(select(PassageVersion).where(PassageVersion.id.in_(part))).scalars():
            out[v.id] = v
    return out


# --------------------------------------------------------------------------- lists

@dataclass
class QuestionFilter:
    q: Optional[str] = None
    type: Optional[str] = None
    language: Optional[str] = None
    section: Optional[str] = None
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    tag: Optional[str] = None
    passage_id: Optional[uuid.UUID] = None
    deleted: bool = False


def like_escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def question_list_stmt(bank_id: uuid.UUID, f: QuestionFilter):
    """One statement: (BankQuestion, current stem, current version_no, current image) for a bank."""
    stmt = (
        select(BankQuestion, QuestionVersion.stem, QuestionVersion.version_no, QuestionVersion.image)
        .join(QuestionVersion, QuestionVersion.id == BankQuestion.current_version_id)
        .where(BankQuestion.bank_id == bank_id)
    )
    stmt = stmt.where(BankQuestion.deleted_at.is_not(None) if f.deleted else BankQuestion.deleted_at.is_(None))
    if f.type:
        stmt = stmt.where(BankQuestion.type == f.type)
    if f.language:
        stmt = stmt.where(BankQuestion.language == f.language)
    if f.section:
        stmt = stmt.where(BankQuestion.section == f.section)
    if f.topic:
        stmt = stmt.where(BankQuestion.topic == f.topic)
    if f.difficulty:
        stmt = stmt.where(BankQuestion.difficulty == f.difficulty)
    if f.passage_id:
        stmt = stmt.where(BankQuestion.passage_id == f.passage_id)
    if f.tag:
        # SQLite stores ASCII-escaped JSON, Postgres keeps raw unicode: match both spellings.
        pats = {json.dumps(f.tag), json.dumps(f.tag, ensure_ascii=False)}
        tags_txt = cast(BankQuestion.tags, String)
        stmt = stmt.where(or_(*[tags_txt.like(f"%{like_escape(p)}%", escape="\\") for p in pats]))
    if f.q:
        needle = f.q.strip().casefold()
        if needle:
            stmt = stmt.where(BankQuestion.search_text.like(f"%{like_escape(needle)}%", escape="\\"))
    return stmt


def bank_rows_stmt(course_id: uuid.UUID, *, deleted: bool = False, bank_id: Optional[uuid.UUID] = None,
                   kind: str = "all"):
    """(QuestionBank, live question count, live passage count, quiz title or None) in one statement.

    Phase 7c: `kind` = all | shared (assessment_id IS NULL) | quiz (assessment_id IS NOT NULL); the quiz title comes
    from an outer join on the bank's assessment (a quiz bank shows its quiz's title, PHASE_7C_DESIGN 5.1)."""
    qc = (
        select(func.count()).select_from(BankQuestion)
        .where(BankQuestion.bank_id == QuestionBank.id, BankQuestion.deleted_at.is_(None))
        .correlate(QuestionBank).scalar_subquery()
    )
    pc = (
        select(func.count()).select_from(Passage)
        .where(Passage.bank_id == QuestionBank.id, Passage.deleted_at.is_(None))
        .correlate(QuestionBank).scalar_subquery()
    )
    # --- Phase 7c S1 begin --- (quiz title through an outer join; kind filter)
    from app.lms.assessments.models import Assessment

    stmt = (
        select(QuestionBank, qc.label("question_count"), pc.label("passage_count"),
               Assessment.title.label("assessment_title"))
        .outerjoin(Assessment, Assessment.id == QuestionBank.assessment_id)
        .where(QuestionBank.course_id == course_id)
    )
    if bank_id is not None:
        return stmt.where(QuestionBank.id == bank_id)
    if kind == "shared":
        stmt = stmt.where(QuestionBank.assessment_id.is_(None))
    elif kind == "quiz":
        stmt = stmt.where(QuestionBank.assessment_id.is_not(None))
    # --- Phase 7c S1 end ---
    return stmt.where(QuestionBank.deleted_at.is_not(None) if deleted else QuestionBank.deleted_at.is_(None))


def passage_rows_stmt(bank_id: uuid.UUID, *, deleted: bool = False):
    """(Passage, version_no, title, body, live question count)."""
    qc = (
        select(func.count()).select_from(BankQuestion)
        .where(BankQuestion.passage_id == Passage.id, BankQuestion.deleted_at.is_(None))
        .correlate(Passage).scalar_subquery()
    )
    return (
        select(Passage, PassageVersion.version_no, PassageVersion.title, PassageVersion.body, qc.label("qc"))
        .join(PassageVersion, PassageVersion.id == Passage.current_version_id)
        .where(Passage.bank_id == bank_id,
               Passage.deleted_at.is_not(None) if deleted else Passage.deleted_at.is_(None))
    )


# --------------------------------------------------------------------------- student payloads (pure)

def _expand_student_image(image: Optional[dict]) -> Optional[str]:
    return media_url(image["sha256"]) if image else None


def student_question(v: QuestionVersion) -> dict:
    """Payload a student may see for a version: never the key, never the explanation."""
    t = get_type(v.type)
    return {
        "id": v.id,
        "type": v.type,
        "language": v.language,
        "stem": v.stem,
        "image_url": _expand_student_image(v.image),
        "points": float(v.default_points),
        "data": t.student_view(v.data),
    }


def student_passage(pv: PassageVersion) -> dict:
    return {
        "id": pv.id,
        "title": pv.title,
        "body": pv.body,
        "image_url": _expand_student_image(pv.image),
    }


def load_student_payloads(db: Session, version_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Student payloads (with the linked passage) for many question versions: 2 queries per 500 ids."""
    versions = load_versions(db, version_ids)
    qids = list({v.question_id for v in versions.values()})
    passages: dict[uuid.UUID, PassageVersion] = {}
    for part in _chunks(qids):
        rows = db.execute(
            select(BankQuestion.id, PassageVersion)
            .join(Passage, Passage.id == BankQuestion.passage_id)
            .join(PassageVersion, PassageVersion.id == Passage.current_version_id)
            .where(BankQuestion.id.in_(part))
        ).all()
        for qid, pv in rows:
            passages[qid] = pv
    out: dict[uuid.UUID, dict] = {}
    for vid, v in versions.items():
        payload = student_question(v)
        pv = passages.get(v.question_id)
        payload["passage"] = student_passage(pv) if pv else None
        out[vid] = payload
    return out


def expand_images(value: Any) -> Any:
    """Staff view: ImageRef dicts {asset_id, sha256} become {asset_id, url}."""
    if isinstance(value, dict):
        if set(value) == {"asset_id", "sha256"}:
            return {"asset_id": value["asset_id"], "url": media_url(value["sha256"])}
        return {k: expand_images(x) for k, x in value.items()}
    if isinstance(value, list):
        return [expand_images(x) for x in value]
    return value


# --- Phase 9 S2 begin --- (PHASE_9_DESIGN 4.2, invariants 2-3: the one SQL scope of organization-shared banks)
def shared_banks_stmt(organization_scope):
    """(QuestionBank, live question count, live passage count, home course title, organization name, sharer User or
    None) of the live banks shared with the organization (`visibility = 'organization'`, never a quiz bank) whose
    organization is in `organization_scope` (a SELECT of organization ids) and whose home course is live. A personal
    organization never matches (invariant 2), whatever the scope says."""
    from app.lms.courses.models import Course
    from app.lms.organizations.models import Organization
    from app.models.user import User

    qc = (
        select(func.count()).select_from(BankQuestion)
        .where(BankQuestion.bank_id == QuestionBank.id, BankQuestion.deleted_at.is_(None))
        .correlate(QuestionBank).scalar_subquery()
    )
    pc = (
        select(func.count()).select_from(Passage)
        .where(Passage.bank_id == QuestionBank.id, Passage.deleted_at.is_(None))
        .correlate(QuestionBank).scalar_subquery()
    )
    return (
        select(QuestionBank, qc.label("question_count"), pc.label("passage_count"), Course.title.label("course_title"),
               Organization.name.label("organization_name"), User)
        .join(Course, Course.id == QuestionBank.course_id)
        .join(Organization, Organization.id == QuestionBank.organization_id)
        .outerjoin(User, User.id == QuestionBank.shared_by_id)
        .where(QuestionBank.visibility == "organization", QuestionBank.deleted_at.is_(None),
               QuestionBank.assessment_id.is_(None), Course.deleted_at.is_(None),
               Organization.kind != "personal", Organization.deleted_at.is_(None),
               QuestionBank.organization_id.in_(organization_scope))
    )


def shared_banks_visible_to(db: Session, user_id: str, *, root_ids: Optional[Iterable] = None):
    """Invariant 3: every list of other people's banks a teacher sees comes from this scope. The banks of the
    **trees** the user belongs to (any active membership, teacher or org admin; the roots of those memberships),
    optionally narrowed to some of those roots. Never `can()` in a loop."""
    from app.lms.organizations import tree

    roots = tree.member_tree_roots(db, user_id)
    if root_ids is not None:
        wanted = {uuid.UUID(str(r)) for r in root_ids}
        roots = [r for r in roots if r in wanted]
    return shared_banks_stmt(tree.trees_scope(roots))
# --- Phase 9 S2 end ---
