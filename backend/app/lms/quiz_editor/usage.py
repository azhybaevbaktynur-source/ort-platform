"""Question usage: "used in N quizzes" (PHASE_7C_DESIGN 5.5, P7C-5).

Live uses are question items (top-level and passage children) of live assessments of the course; picks are not uses
(their pool is re-resolved at every publish). `published_anywhere` is exact: the current published snapshot of a live
assessment of the course pins a version of this question in a question slot, including a quiz whose card was repointed
after publishing (survives `unpublish`; preview versions are ignored)."""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentVersion
from app.lms.content.models import QuestionVersion
from app.lms.quiz_editor.schemas import QuestionUsageOut, UsageAssessmentOut

_CHUNK = 500


def _pinned_versions(snapshot: dict) -> set[str]:
    out: set[str] = set()
    for slots in (snapshot.get("slots") or {}).values():
        for s in slots:
            if s.get("kind") == "question" and s.get("qv"):
                out.add(str(s["qv"]))
    return out


# M3 bounds of `published_pins`: only the latest `_PIN_VERSIONS` versions of the question are looked for (a question
# rarely has more; an older pinned version is then missed, which only lets a type change go in place), and the
# published snapshots are read `_PIN_PAGE` assessments at a time (keyset by id), never the whole course at once.
_PIN_VERSIONS = 50
_PIN_PAGE = 50


def published_pins(db: Session, course_id: uuid.UUID, q) -> bool:
    """True when the current published snapshot of a live assessment of the course pins a version of `q` in a question
    slot (picks are not uses). Covers quizzes that no longer have an item for `q` (a card repointed after publish
    still shows the old question to students). Per page of published assessments: one prefilter query (the version ids
    as text), then an exact check of the matching snapshots. Bounded as described at `_PIN_VERSIONS`."""
    mine = [str(v) for v in db.execute(
        select(QuestionVersion.id).where(QuestionVersion.question_id == q.id)
        .order_by(QuestionVersion.version_no.desc()).limit(_PIN_VERSIONS)).scalars()]
    if not mine:
        return False
    wanted = set(mine)
    text = cast(AssessmentVersion.snapshot, String)
    after: Optional[uuid.UUID] = None
    while True:
        stmt = (select(Assessment.id, Assessment.published_version_id)
                .where(Assessment.course_id == course_id, Assessment.deleted_at.is_(None),
                       Assessment.published_version_id.is_not(None))
                .order_by(Assessment.id).limit(_PIN_PAGE))
        if after is not None:
            stmt = stmt.where(Assessment.id > after)
        page = db.execute(stmt).all()
        if not page:
            return False
        after = page[-1].id
        rows = db.execute(
            select(AssessmentVersion.snapshot)
            .where(AssessmentVersion.id.in_([r.published_version_id for r in page]),
                   AssessmentVersion.kind == "published", or_(*[text.contains(v) for v in mine]))
        ).scalars()
        if any(_pinned_versions(snap or {}) & wanted for snap in rows):
            return True
        if len(page) < _PIN_PAGE:
            return False


def question_usage(db: Session, course, q, *, this_assessment_id: Optional[uuid.UUID] = None,
                   with_published: bool = True) -> QuestionUsageOut:
    """`with_published=False` skips `published_pins` (`published_anywhere` is then False); the commit path computes it
    itself only when it matters (M3)."""
    rows = db.execute(
        select(Assessment.id, Assessment.title, Assessment.status, Assessment.published_version_id)
        .join(AssessmentItem, AssessmentItem.assessment_id == Assessment.id)
        .where(AssessmentItem.question_id == q.id, Assessment.deleted_at.is_(None), Assessment.course_id == course.id)
        .distinct()
        .order_by(Assessment.id)
    ).all()
    rows = sorted(rows, key=lambda r: (r.id != this_assessment_id, str(r.id)))
    outs = [UsageAssessmentOut(id=r.id, title=r.title or {}, status=r.status, is_this=r.id == this_assessment_id)
            for r in rows]
    return QuestionUsageOut(other_count=sum(1 for o in outs if not o.is_this), assessments=outs,
                            published_anywhere=published_pins(db, course.id, q) if with_published else False)


def used_elsewhere_counts(db: Session, a: Assessment, question_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Per question of `a`: the number of other live assessments of the course using it (one grouped query per 500)."""
    ids = list(dict.fromkeys(i for i in question_ids if i is not None))
    out: dict[uuid.UUID, int] = {}
    for k in range(0, len(ids), _CHUNK):
        for qid, n in db.execute(
            select(AssessmentItem.question_id, func.count(func.distinct(AssessmentItem.assessment_id)))
            .join(Assessment, Assessment.id == AssessmentItem.assessment_id)
            .where(AssessmentItem.question_id.in_(ids[k:k + _CHUNK]), AssessmentItem.assessment_id != a.id,
                   Assessment.deleted_at.is_(None), Assessment.course_id == a.course_id)
            .group_by(AssessmentItem.question_id)
        ):
            out[qid] = int(n)
    return out
