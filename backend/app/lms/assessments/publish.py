"""Validate, publish, unpublish and preview versions (design 3.3, P3-9, P3-11, P3-18).

Lock order (3.8): courses -> assessments (FOR UPDATE) -> sections/items -> versions (insert). The course row is
never locked here; attempt tables are only read.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.assessments import repository as repo
from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.assessments.rules import Issue
from app.lms.assessments.snapshot import build_snapshot, canonical_hash
from app.lms.assignments import sync as assignment_sync  # --- Phase 7a S1 --- (quiz assignments mirror, 3.2)
from app.lms.content.models import BankQuestion
from app.lms.core import clock
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import require_course


@dataclass
class ValidationResult:
    errors: list[Issue]
    warnings: list[Issue]


@dataclass
class PublishResult:
    assessment: Assessment
    version: AssessmentVersion
    unchanged: bool


def newer_version_item_ids(db: Session, assessment: Assessment, questions: Optional[dict] = None) -> set[uuid.UUID]:
    """Question items whose current question version is newer than the one pinned in the published snapshot."""
    if assessment.published_version_id is None:
        return set()
    pub = db.get(AssessmentVersion, assessment.published_version_id)
    if pub is None:
        return set()
    pinned: dict[str, dict[str, str]] = {}
    for lang, slots in (pub.snapshot.get("slots") or {}).items():
        for s in slots:
            if s.get("kind") == "question":
                pinned.setdefault(s["item_id"], {})[lang] = s["qv"]
    items = [i for i in repo.load_items(db, assessment.id) if i.kind == "question"]
    if questions is None:
        ids = [i.question_id for i in items]
        questions = {}
        for k in range(0, len(ids), 500):
            for q in db.execute(select(BankQuestion).where(BankQuestion.id.in_(ids[k:k + 500]))).scalars():
                questions[q.id] = q
    out: set[uuid.UUID] = set()
    for it in items:
        q = questions.get(it.question_id)
        old = pinned.get(str(it.id), {}).get(q.language) if q is not None else None
        if q is not None and old is not None and q.current_version_id is not None and str(q.current_version_id) != old:
            out.add(it.id)
    return out


def validate(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID) -> ValidationResult:
    require_course(ctx, A.CONTENT_READ_ADMIN, course)
    a = repo.load_assessment(db, course.id, aid)
    _snap, issues = build_snapshot(db, a, now=clock.now())
    warnings = [i for i in issues if i.severity == "warning"]
    for iid in sorted(newer_version_item_ids(db, a), key=str):
        warnings.append(Issue("newer_version", item_id=str(iid), severity="warning"))
    return ValidationResult([i for i in issues if i.severity == "error"], warnings)


def _raise_invalid(issues: list[Issue]) -> None:
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise ValidationFailed("Assessment cannot be published", code="publish_invalid",
                               details=[e.as_dict() for e in errors])


def publish(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID, *, confirm: bool = False) -> PublishResult:
    require_course(ctx, A.CONTENT_MANAGE, course)
    a = repo.load_assessment(db, course.id, aid, for_update=True)
    snap, issues = build_snapshot(db, a, now=clock.now())
    _raise_invalid(issues)
    content_hash = canonical_hash(snap)
    cur = db.get(AssessmentVersion, a.published_version_id) if a.published_version_id else None
    if cur is not None and cur.content_hash == content_hash:
        a.status = "published"
        a.published_draft_rev = a.draft_rev
        if a.published_at is None:
            a.published_at = clock.now()
        assignment_sync.mirror_from_assessment(db, a)  # --- Phase 7a S1 --- (mirror rule, 3.2)
        db.commit()
        return PublishResult(a, cur, True)
    if cur is not None and not confirm:
        counts = repo.version_attempt_counts(db, [cur.id])[cur.id]
        if counts["in_progress"] + counts["submitted"] > 0:
            raise Conflict("Students already used the published version", code="confirm_required", details=counts)
    a.last_version_no += 1
    v = AssessmentVersion(
        assessment_id=a.id, kind="published", version_no=a.last_version_no, snapshot=snap,
        content_hash=content_hash, draft_rev=a.draft_rev, item_count=snap["item_count"],
        points_possible=Decimal(snap["points_possible"]), created_by_id=ctx.user.id,
    )
    db.add(v)
    db.flush()
    a.published_version_id = v.id
    a.status = "published"
    a.published_draft_rev = a.draft_rev
    a.published_at = clock.now()
    assignment_sync.mirror_from_assessment(db, a)  # --- Phase 7a S1 --- (mirror rule, 3.2)
    db.commit()
    return PublishResult(a, v, False)


def unpublish(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID) -> Assessment:
    require_course(ctx, A.CONTENT_MANAGE, course)
    a = repo.load_assessment(db, course.id, aid, for_update=True)
    if a.status != "published":
        raise Conflict("Assessment is not published", code="not_published")
    a.status = "draft"
    assignment_sync.mirror_from_assessment(db, a)  # --- Phase 7a S1 --- (mirror rule, 3.2)
    db.commit()
    return a


def ensure_preview_version(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID) -> AssessmentVersion:
    """Preview snapshot of the current draft (P3-18); reused while its hash matches. Commits."""
    require_course(ctx, A.CONTENT_MANAGE, course)
    a = repo.load_assessment(db, course.id, aid, for_update=True)
    snap, issues = build_snapshot(db, a, now=clock.now())
    _raise_invalid(issues)
    content_hash = canonical_hash(snap)
    existing = db.execute(
        select(AssessmentVersion).where(
            AssessmentVersion.assessment_id == a.id, AssessmentVersion.kind == "preview",
            AssessmentVersion.content_hash == content_hash)
        .order_by(AssessmentVersion.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        db.commit()   # release the row lock
        return existing
    v = AssessmentVersion(
        assessment_id=a.id, kind="preview", version_no=None, snapshot=snap, content_hash=content_hash,
        draft_rev=a.draft_rev, item_count=snap["item_count"], points_possible=Decimal(snap["points_possible"]),
        created_by_id=ctx.user.id,
    )
    db.add(v)
    db.commit()
    return v
