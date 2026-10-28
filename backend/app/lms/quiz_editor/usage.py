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


def published_pins(db: Session, course_id: uuid.UUID, q) -> bool:
    """True when the current published snapshot of a live assessment of the course pins a version of `q` in a question
    slot (picks are not uses). Covers quizzes that no longer have an item for `q` (a card repointed after publish
    still shows the old question to students). One prefilter query (the version ids as text), then an exact check."""
    mine = [str(v) for v in db.execute(select(QuestionVersion.id).where(QuestionVersion.question_id == q.id)).scalars()]
    if not mine:
        return False
    text = cast(AssessmentVersion.snapshot, String)
    rows = db.execute(
        select(AssessmentVersion.snapshot)
        .join(Assessment, Assessment.published_version_id == AssessmentVersion.id)
        .where(Assessment.course_id == course_id, Assessment.deleted_at.is_(None),
               AssessmentVersion.kind == "published", or_(*[text.contains(v) for v in mine]))
    ).scalars()
    wanted = set(mine)
    return any(_pinned_versions(snap or {}) & wanted for snap in rows)


def question_usage(db: Session, course, q, *, this_assessment_id: Optional[uuid.UUID] = None) -> QuestionUsageOut:
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
                            published_anywhere=published_pins(db, course.id, q))


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
