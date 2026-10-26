"""Quiz assignments mirror their assessment (PHASE_7A_DESIGN 3.2, decision P7-2).

For `kind = quiz` the assessment row is the truth; the assignment row copies the mirrored columns. Every builder
and publisher write calls `mirror_from_assessment` (one line each, `# --- Phase 7a S1 ---` blocks), and
`builder.create_assessment` calls `ensure_quiz_assignment`, all inside the caller's transaction (no commit here).
Only `position` is owned by the assignment."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment

# assignment column -> how its value is read from the assessment (published version points come separately)
MIRRORED = ("title", "description", "due_at", "available_from", "available_until", "category_id",
            "grading_scheme_version_id", "grade_release", "omit_from_total", "published", "published_at",
            "points_possible", "deleted_at", "deleted_by_id")


def _published_points(db: Session, a: Assessment):
    if a.published_version_id is None:
        return None
    v = db.get(AssessmentVersion, a.published_version_id)  # identity map hit right after publish
    return v.points_possible if v is not None else None


def mirrored_values(db: Session, a: Assessment) -> dict:
    """The assignment's mirrored columns as the assessment says (3.2)."""
    return dict(
        title=dict(a.title) if a.title is not None else {},
        description=dict(a.description) if a.description is not None else None,
        due_at=a.due_at, available_from=a.available_from, available_until=a.available_until,
        category_id=a.grade_category_id, grading_scheme_version_id=a.grading_scheme_version_id,
        grade_release=a.grade_release or "auto", omit_from_total=bool(a.omit_from_total),
        published=a.status == "published" and a.published_version_id is not None, published_at=a.published_at,
        points_possible=_published_points(db, a), deleted_at=a.deleted_at, deleted_by_id=a.deleted_by_id,
    )


def _next_position(db: Session, course_id) -> int:
    return (db.execute(select(func.max(Assignment.position)).where(Assignment.course_id == course_id)).scalar()
            or 0) + 1


def ensure_quiz_assignment(db: Session, assessment: Assessment, actor_id: Optional[str] = None) -> Assignment:
    """The assessment's quiz assignment (id `assignment_id_for(assessment.id)`), created at the end of the course's
    assignment order when missing, mirrored otherwise. Flushes; the caller commits."""
    if assessment.id is None:
        db.flush()
    row = db.get(Assignment, assignment_id_for(assessment.id))
    if row is not None:
        _apply(row, mirrored_values(db, assessment))
        return row
    row = Assignment(
        id=assignment_id_for(assessment.id), course_id=assessment.course_id, kind="quiz", assessment_id=assessment.id,
        position=_next_position(db, assessment.course_id),
        created_by_id=actor_id if actor_id is not None else assessment.created_by_id,
        **mirrored_values(db, assessment),
    )
    db.add(row)
    db.flush()
    return row


def mirror_from_assessment(db: Session, assessment: Assessment) -> Assignment:
    """Copy the mirrored columns onto the quiz assignment (creates it if missing). The caller commits."""
    row = db.get(Assignment, assignment_id_for(assessment.id))
    if row is None:
        return ensure_quiz_assignment(db, assessment)
    _apply(row, mirrored_values(db, assessment))
    return row


def _apply(row: Assignment, values: dict) -> None:
    for k, v in values.items():
        if getattr(row, k) != v:  # untouched rows keep their updated_at
            setattr(row, k, v)


def mirror_mismatches(db: Session, assessment: Assessment) -> dict:
    """{column: (assignment value, assessment value)} where the mirror differs (tests, check scripts)."""
    row = db.get(Assignment, assignment_id_for(assessment.id))
    if row is None:
        return {"missing": (None, assessment.id)}
    want = mirrored_values(db, assessment)
    out = {}
    for k in MIRRORED:
        got = getattr(row, k)
        if not _same(got, want[k]):
            out[k] = (got, want[k])
    return out


def _same(a, b) -> bool:
    from datetime import datetime, timezone

    if isinstance(a, datetime) and isinstance(b, datetime):  # SQLite returns naive UTC
        a = a if a.tzinfo else a.replace(tzinfo=timezone.utc)
        b = b if b.tzinfo else b.replace(tzinfo=timezone.utc)
    return a == b


__all__ = ["ensure_quiz_assignment", "mirror_from_assessment", "mirrored_values", "mirror_mismatches", "MIRRORED"]
