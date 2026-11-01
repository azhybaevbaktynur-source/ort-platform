"""Practice sets (PHASE_10_DESIGN 3): create, list, change and delete.

Publishing lives here and not in `assessments.publish`: that module mirrors every publish onto the quiz assignment and
creates the row when it is missing, and a practice set must never have an `assignments` row."""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.assessments import builder
from app.lms.assessments import publish as pub
from app.lms.assessments import repository as repo
from app.lms.assessments import schemas as assessment_sch
from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection, AssessmentVersion
from app.lms.assessments.snapshot import build_snapshot, canonical_hash
from app.lms.attempts import timing
from app.lms.attempts.models import Attempt
from app.lms.content import repository as content_repo
from app.lms.content.models import BankQuestion
from app.lms.core import clock
from app.lms.core.errors import NotFound, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import assert_not_sandbox, paginate_rows, require_course
from app.lms.practice import schemas as sch

STAFF_ROLES = ("teacher", "assistant")
FACET_LIMIT = 200
_FINAL = ("graded", "needs_review")


def _filter_of(block: sch.PracticeBlockIn) -> dict:
    return {k: v for k, v in (("section", block.section), ("topic", block.topic), ("difficulty", block.difficulty))
            if v}


def _check_pools(db: Session, course: Course, assessment_id: Optional[uuid.UUID], languages: list[str],
                 blocks: list, allowed_types: list[str]) -> None:
    """Before any write. `blocks`: objects with bank_id, count and a pick filter. 404 `bank_not_found`; a bank private
    to another quiz is refused; 422 `pick_pool_too_small` lists every short block and language."""
    from app.lms.quiz_editor import quiz_banks as _qb

    short = []
    for i, b in enumerate(blocks):
        bank = content_repo.load_bank(db, course.id, b.bank_id)
        _qb.assert_bank_usable(bank, SimpleNamespace(id=assessment_id))
        for lang in languages:
            available = repo.pick_pool_size(db, course.id, b.bank_id, b.filter, lang, allowed_types)
            if available < b.count:
                short.append({"block": i, "language": lang, "available": available, "required": b.count})
    if short:
        raise ValidationFailed("Not enough questions for this block", code="pick_pool_too_small", details=short)


def _as_pools(blocks: list[sch.PracticeBlockIn]) -> list[SimpleNamespace]:
    return [SimpleNamespace(bank_id=b.bank_id, count=b.count, filter=_filter_of(b)) for b in blocks]


def _add_blocks(db: Session, course: Course, a: Assessment, section: AssessmentSection,
                blocks: list[sch.PracticeBlockIn]) -> None:
    position = builder._next_pos(db, section.id, None)
    for i, b in enumerate(blocks):
        pick = assessment_sch.PickIn(bank_id=b.bank_id, count=b.count, filter=_filter_of(b))
        db.add(AssessmentItem(assessment_id=a.id, section_id=section.id, position=position + i, kind="pick",
                              points=None, **builder._pick_values(db, course, section, pick, a)))
    db.flush()


def _publish(db: Session, ctx: AuthzContext, a: Assessment) -> None:
    """`assessments.publish.publish` without the assignment mirror and without `confirm_required`: an attempt keeps the
    version it started on and a practice attempt carries no grade. The caller commits."""
    snap, issues = build_snapshot(db, a, now=clock.now())
    pub._raise_invalid(issues)
    content_hash = canonical_hash(snap)
    cur = db.get(AssessmentVersion, a.published_version_id) if a.published_version_id else None
    now = clock.now()
    if cur is None or cur.content_hash != content_hash:
        a.last_version_no += 1
        v = AssessmentVersion(
            assessment_id=a.id, kind="published", version_no=a.last_version_no, snapshot=snap,
            content_hash=content_hash, draft_rev=a.draft_rev, item_count=snap["item_count"],
            points_possible=Decimal(snap["points_possible"]), created_by_id=ctx.user.id,
        )
        db.add(v)
        db.flush()
        a.published_version_id = v.id
        a.published_at = now
    elif a.published_at is None:
        a.published_at = now
    a.status = "published"
    a.published_draft_rev = a.draft_rev
    db.flush()


def _is_staff(ctx: AuthzContext, course: Course) -> bool:
    return ctx.role_for(course.id) in STAFF_ROLES


def _blocks_by_set(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[sch.PracticeBlockOut]]:
    out: dict[uuid.UUID, list[sch.PracticeBlockOut]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = db.execute(
        select(AssessmentItem.assessment_id, AssessmentItem.pick_bank_id, AssessmentItem.pick_count,
               AssessmentItem.pick_filter)
        .where(AssessmentItem.assessment_id.in_(ids), AssessmentItem.kind == "pick")
        .order_by(AssessmentItem.assessment_id, AssessmentItem.position)
    ).all()
    for aid, bank_id, count, flt in rows:
        f = flt or {}
        out[aid].append(sch.PracticeBlockOut(bank_id=bank_id, count=count or 0, section=f.get("section"),
                                             topic=f.get("topic"), difficulty=f.get("difficulty")))
    return out


def _mine(db: Session, user_id: str, course_id: uuid.UUID, ids: list[uuid.UUID]) -> tuple[dict, dict]:
    """One grouped query over `ix_attempts_user_course_final`, one over `uq_attempts_open`, for one page of sets."""
    if not ids:
        return {}, {}
    percent = case((Attempt.points_possible > 0, Attempt.raw_score * 100 / Attempt.points_possible))
    final = {r[0]: r for r in db.execute(
        select(Attempt.assessment_id, func.count(), func.max(percent), func.max(Attempt.submitted_at))
        .where(Attempt.user_id == user_id, Attempt.course_id == course_id, Attempt.assessment_id.in_(ids),
               Attempt.status.in_(_FINAL), Attempt.is_preview.is_(False))
        .group_by(Attempt.assessment_id)
    ).all()}
    open_ = {aid: tid for aid, tid in db.execute(
        select(Attempt.assessment_id, Attempt.id)
        .where(Attempt.user_id == user_id, Attempt.assessment_id.in_(ids), Attempt.status == "in_progress",
               Attempt.is_preview.is_(False))
    ).all()}
    return final, open_


def _set_out(a: Assessment, item_count: Optional[int], blocks: list[sch.PracticeBlockOut], *, staff: bool,
             final: Optional[dict] = None, open_: Optional[dict] = None) -> sch.PracticeSetOut:
    fields: dict = {}
    if not staff:
        row = (final or {}).get(a.id)
        fields = dict(
            my_attempts=int(row[1]) if row else 0,
            my_best_percent=round(float(row[2]), 2) if row and row[2] is not None else None,
            my_last_at=timing.as_utc(row[3]) if row else None,
            open_attempt_id=(open_ or {}).get(a.id),
        )
    return sch.PracticeSetOut(
        id=a.id, title=dict(a.title or {}), status=a.status, languages=list(a.languages or []),
        item_count=item_count if item_count is not None else sum(b.count for b in blocks), blocks=blocks, **fields)


def list_sets(db: Session, ctx: AuthzContext, course: Course, *, cursor: Optional[str], limit: Optional[int]):
    require_course(ctx, A.CONTENT_READ, course)
    staff = _is_staff(ctx, course)
    stmt = (select(Assessment, AssessmentVersion.item_count)
            .outerjoin(AssessmentVersion, AssessmentVersion.id == Assessment.published_version_id)
            .where(Assessment.course_id == course.id, Assessment.is_practice.is_(True),
                   Assessment.deleted_at.is_(None)))
    if not staff:
        stmt = stmt.where(Assessment.status == "published")
    rows, nxt = paginate_rows(db, stmt, sort_col=Assessment.position, id_col=Assessment.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False)
    ids = [r[0].id for r in rows]
    blocks = _blocks_by_set(db, ids)
    final, open_ = ({}, {}) if staff else _mine(db, ctx.user.id, course.id, ids)
    return [_set_out(a, n, blocks[a.id], staff=staff, final=final, open_=open_) for a, n in rows], nxt


def _out_after_write(db: Session, a: Assessment) -> sch.PracticeSetOut:
    version = db.get(AssessmentVersion, a.published_version_id) if a.published_version_id else None
    return _set_out(a, version.item_count if version is not None else None, _blocks_by_set(db, [a.id])[a.id],
                    staff=True)


def create_set(db: Session, ctx: AuthzContext, course: Course, data: sch.PracticeCreateIn) -> sch.PracticeSetOut:
    require_course(ctx, A.CONTENT_MANAGE, course)
    assert_not_sandbox(course)
    languages = list(data.languages)
    _check_pools(db, course, None, languages, _as_pools(data.blocks), builder.practice_rules()["allowed_types"])
    a = builder.create_assessment(
        db, ctx, course, assessment_sch.AssessmentCreateIn(title=data.title, languages=languages), practice=True)
    _add_blocks(db, course, a, repo.load_sections(db, a.id)[0], data.blocks)
    _publish(db, ctx, a)
    out = _out_after_write(db, a)
    db.commit()
    return out


def _load_set(db: Session, course: Course, aid: uuid.UUID, *, for_update: bool = False) -> Assessment:
    a = repo.load_assessment(db, course.id, aid, for_update=for_update)
    if not a.is_practice:
        raise NotFound("Assessment not found", code="assessment_not_found")
    return a


def _section_of(db: Session, a: Assessment) -> AssessmentSection:
    sections = repo.load_sections(db, a.id)
    if sections:
        return sections[0]
    section = AssessmentSection(assessment_id=a.id, position=1, key=None, rules=builder.practice_rules())
    db.add(section)
    db.flush()
    return section


def update_set(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID,
               data: sch.PracticeUpdateIn) -> sch.PracticeSetOut:
    require_course(ctx, A.CONTENT_MANAGE, course)
    assert_not_sandbox(course)
    a = _load_set(db, course, aid, for_update=True)
    languages = list(a.languages or [])
    if data.title is not None:
        a.title = data.title
    if data.title is None or data.blocks is not None:  # a rename alone keeps the published version and its pool
        if data.blocks is not None:
            section = _section_of(db, a)
            allowed = (section.rules or {}).get("allowed_types") or builder.practice_rules()["allowed_types"]
            _check_pools(db, course, a.id, languages, _as_pools(data.blocks), allowed)
            db.execute(delete(AssessmentItem).where(AssessmentItem.assessment_id == a.id,
                                                    AssessmentItem.kind == "pick"))
            _add_blocks(db, course, a, section, data.blocks)
            a.draft_rev += 1
        else:
            picks = [SimpleNamespace(bank_id=i.pick_bank_id, count=i.pick_count or 0, filter=i.pick_filter)
                     for i in repo.load_items(db, a.id) if i.kind == "pick"]
            _check_pools(db, course, a.id, languages, picks, builder.practice_rules()["allowed_types"])
        db.flush()
        _publish(db, ctx, a)
    db.flush()
    out = _out_after_write(db, a)
    db.commit()
    return out


def delete_set(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID) -> None:
    require_course(ctx, A.CONTENT_MANAGE, course)
    _load_set(db, course, aid)
    builder.soft_delete_assessment(db, ctx, course, aid)


def facets(db: Session, ctx: AuthzContext, course: Course, bank_id: uuid.UUID) -> sch.PracticeFacetsOut:
    require_course(ctx, A.CONTENT_MANAGE, course)
    content_repo.load_bank(db, course.id, bank_id)

    def distinct(col) -> list[str]:
        return list(db.execute(
            select(col).where(BankQuestion.bank_id == bank_id, BankQuestion.deleted_at.is_(None), col.is_not(None))
            .distinct().order_by(col).limit(FACET_LIMIT)).scalars())

    return sch.PracticeFacetsOut(sections=distinct(BankQuestion.section), topics=distinct(BankQuestion.topic),
                                 difficulties=distinct(BankQuestion.difficulty))
