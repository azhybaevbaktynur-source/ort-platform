"""Assessment repository: loaders (anti-IDOR: always through the course), pick pools and attempt counts.

`load_assessment` is shared with the attempts package; its signature is fixed (design 3.2).
"""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection, AssessmentVersion
from app.lms.attempts.models import Attempt
from app.lms.content import repository as content_repo
from app.lms.content.models import BankQuestion
from app.lms.core.errors import NotFound

CHUNK = 500
SUBMITTED_STATUSES = ("submitted", "needs_review", "graded")


def load_assessment(db: Session, course_id: uuid.UUID, aid: uuid.UUID, *, for_update: bool = False,
                    published_only: bool = False, include_deleted: bool = False) -> Assessment:
    stmt = select(Assessment).where(Assessment.id == aid, Assessment.course_id == course_id)
    if not include_deleted:
        stmt = stmt.where(Assessment.deleted_at.is_(None))
    if published_only:
        stmt = stmt.where(Assessment.status == "published")
    if for_update:
        stmt = stmt.with_for_update(of=Assessment).execution_options(populate_existing=True)
    a = db.execute(stmt).scalar_one_or_none()
    if a is None:
        raise NotFound("Assessment not found", code="assessment_not_found")
    return a


def load_section(db: Session, assessment_id: uuid.UUID, section_id: uuid.UUID) -> AssessmentSection:
    s = db.execute(select(AssessmentSection).where(
        AssessmentSection.id == section_id, AssessmentSection.assessment_id == assessment_id)).scalar_one_or_none()
    if s is None:
        raise NotFound("Section not found", code="section_not_found")
    return s


def load_item(db: Session, assessment_id: uuid.UUID, item_id: uuid.UUID) -> AssessmentItem:
    i = db.execute(select(AssessmentItem).where(
        AssessmentItem.id == item_id, AssessmentItem.assessment_id == assessment_id)).scalar_one_or_none()
    if i is None:
        raise NotFound("Item not found", code="item_not_found")
    return i


def load_sections(db: Session, assessment_id: uuid.UUID) -> list[AssessmentSection]:
    return list(db.execute(
        select(AssessmentSection).where(AssessmentSection.assessment_id == assessment_id)
        .order_by(AssessmentSection.position, AssessmentSection.id)).scalars())


def load_items(db: Session, assessment_id: uuid.UUID) -> list[AssessmentItem]:
    """All items of an assessment: top-level first by position, children by position (python regroups)."""
    return list(db.execute(
        select(AssessmentItem).where(AssessmentItem.assessment_id == assessment_id)
        .order_by(AssessmentItem.position, AssessmentItem.id)).scalars())


def group_items(items: Iterable[AssessmentItem]) -> tuple[dict[uuid.UUID, list[AssessmentItem]],
                                                         dict[uuid.UUID, list[AssessmentItem]]]:
    """(top-level items per section id, children per parent id), each in position order."""
    top: dict[uuid.UUID, list[AssessmentItem]] = {}
    kids: dict[uuid.UUID, list[AssessmentItem]] = {}
    for it in items:
        if it.parent_item_id is None:
            top.setdefault(it.section_id, []).append(it)
        else:
            kids.setdefault(it.parent_item_id, []).append(it)
    return top, kids


def item_totals(items: Iterable[AssessmentItem]) -> tuple[int, "object"]:
    """(item_count, points_possible) of builder rows; a pick counts as `pick_count` items."""
    from decimal import Decimal

    n, pts = 0, Decimal("0")
    for it in items:
        if it.kind == "question":
            n += 1
            pts += it.points or Decimal("0")
        elif it.kind == "pick":
            n += it.pick_count or 0
            pts += (it.points if it.points is not None else Decimal("1")) * (it.pick_count or 0)
    return n, pts


def draft_totals(db: Session, assessment_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, float]]:
    """Per assessment (item_count, points_possible) of the draft rows, one grouped query."""
    out: dict[uuid.UUID, tuple[int, float]] = {}
    if not assessment_ids:
        return out
    count_expr = case((AssessmentItem.kind == "question", 1), (AssessmentItem.kind == "pick",
                                                              AssessmentItem.pick_count), else_=0)
    points_expr = case(
        (AssessmentItem.kind == "question", func.coalesce(AssessmentItem.points, 0)),
        (AssessmentItem.kind == "pick", func.coalesce(AssessmentItem.points, 1) * AssessmentItem.pick_count),
        else_=0,
    )
    rows = db.execute(
        select(AssessmentItem.assessment_id, func.sum(count_expr), func.sum(points_expr))
        .where(AssessmentItem.assessment_id.in_(assessment_ids)).group_by(AssessmentItem.assessment_id)
    ).all()
    for aid, n, pts in rows:
        out[aid] = (int(n or 0), float(pts or 0))
    return out


# --------------------------------------------------------------------------- pick pools

def pick_pool_stmt(course_id: uuid.UUID, bank_id: uuid.UUID, pick_filter: Optional[dict], language: str,
                   allowed_types: Optional[list[str]] = None):
    """Live questions of a live bank of this course matching a pick filter in one language."""
    f = pick_filter or {}
    flt = content_repo.QuestionFilter(
        type=f.get("type"), language=language, section=f.get("section"), topic=f.get("topic"),
        difficulty=f.get("difficulty"), tag=(f.get("tags") or [None])[0],
    )
    stmt = content_repo.question_list_stmt(bank_id, flt).with_only_columns(
        BankQuestion.id, BankQuestion.current_version_id, BankQuestion.passage_id, BankQuestion.type,
        BankQuestion.tags, maintain_column_froms=True,
    )
    from app.lms.content.models import QuestionBank

    stmt = stmt.join(QuestionBank, QuestionBank.id == BankQuestion.bank_id).where(
        QuestionBank.course_id == course_id, QuestionBank.deleted_at.is_(None))
    if allowed_types:
        stmt = stmt.where(BankQuestion.type.in_(allowed_types))
    return stmt.order_by(BankQuestion.position, BankQuestion.id)


def pick_pool(db: Session, course_id: uuid.UUID, bank_id: uuid.UUID, pick_filter: Optional[dict], language: str,
              allowed_types: Optional[list[str]] = None, limit: Optional[int] = None) -> list:
    """Rows (id, current_version_id, passage_id, type) of the pool, at most `limit` (default cap + 1)."""
    limit = limit if limit is not None else settings.ASSESSMENT_PICK_POOL_MAX + 1
    rows = db.execute(pick_pool_stmt(course_id, bank_id, pick_filter, language, allowed_types).limit(limit)).all()
    extra_tags = (pick_filter or {}).get("tags") or []
    if len(extra_tags) > 1:
        rows = [r for r in rows if all(t in (r[4] or []) for t in extra_tags)]
    return rows


def pick_pool_size(db: Session, course_id: uuid.UUID, bank_id: uuid.UUID, pick_filter: Optional[dict],
                   language: str, allowed_types: Optional[list[str]] = None) -> int:
    return len(pick_pool(db, course_id, bank_id, pick_filter, language, allowed_types))


# --------------------------------------------------------------------------- attempt counts

def attempt_counts(db: Session, assessment_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """{assessment_id: {in_progress, submitted}} for non-preview attempts."""
    out = {a: {"in_progress": 0, "submitted": 0} for a in assessment_ids}
    if not assessment_ids:
        return out
    rows = db.execute(
        select(Attempt.assessment_id, Attempt.status, func.count())
        .where(Attempt.assessment_id.in_(assessment_ids), Attempt.is_preview.is_(False))
        .group_by(Attempt.assessment_id, Attempt.status)
    ).all()
    for aid, status, n in rows:
        if status == "in_progress":
            out[aid]["in_progress"] += n
        elif status in SUBMITTED_STATUSES:
            out[aid]["submitted"] += n
    return out


def version_attempt_counts(db: Session, version_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    out = {v: {"in_progress": 0, "submitted": 0} for v in version_ids}
    if not version_ids:
        return out
    rows = db.execute(
        select(Attempt.assessment_version_id, Attempt.status, func.count())
        .where(Attempt.assessment_version_id.in_(version_ids), Attempt.is_preview.is_(False))
        .group_by(Attempt.assessment_version_id, Attempt.status)
    ).all()
    for vid, status, n in rows:
        if status == "in_progress":
            out[vid]["in_progress"] += n
        elif status in SUBMITTED_STATUSES:
            out[vid]["submitted"] += n
    return out


def has_open_attempts(db: Session, assessment_id: uuid.UUID) -> bool:
    return db.execute(
        select(Attempt.id).where(Attempt.assessment_id == assessment_id, Attempt.status == "in_progress",
                                 Attempt.is_preview.is_(False)).limit(1)
    ).first() is not None


def load_version(db: Session, assessment_id: uuid.UUID, version_id: uuid.UUID) -> Optional[AssessmentVersion]:
    return db.execute(select(AssessmentVersion).where(
        AssessmentVersion.id == version_id, AssessmentVersion.assessment_id == assessment_id)).scalar_one_or_none()
