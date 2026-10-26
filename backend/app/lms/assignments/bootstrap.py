"""`ensure_assignments(db)`: data steps 2-3 of migration 0009 (PHASE_7A_DESIGN 2.3, 2.9), idempotent.

Runs in the lifespan after `ensure_organizations` and before `ensure_ort_courses`, on SQLite (dev/tests, no Alembic)
and PostgreSQL (production: the migration already did the work, so nothing changes). Step 2: one quiz assignment
per assessment (soft-deleted included) with the fixed id `assignment_id_for(assessment_id)` and the mirrored
columns, `position = assessments.position`. Step 3: submissions without an assignment get their assessment's.
A PostgreSQL test asserts that the migration path and this path yield the same rows. Never fatal."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment
from app.lms.core.models import utcnow
from app.lms.grading.models import Submission

log = logging.getLogger(__name__)
BATCH = 500


@dataclass
class BootstrapReport:
    assignments_created: int = 0
    submissions_moved: int = 0
    errors: list[str] = field(default_factory=list)


def ensure_assignments(db: Session) -> BootstrapReport:
    report = BootstrapReport()
    try:
        _run(db, report)
        db.commit()
    except Exception as exc:  # noqa: BLE001  (the lifespan must keep starting)
        db.rollback()
        report.errors.append(f"{type(exc).__name__}: {exc}"[:500])
        log.exception("Assignment bootstrap failed")
    return report


def quiz_assignment_row(a, points_possible, now) -> dict:
    """Values of the quiz assignment of assessment row `a` (Core row or ORM object), as migration 0009 writes them."""
    return dict(
        id=assignment_id_for(a.id), course_id=a.course_id, kind="quiz", assessment_id=a.id,
        title=a.title, description=a.description, points_possible=points_possible,
        due_at=a.due_at, available_from=a.available_from, available_until=a.available_until,
        category_id=a.grade_category_id, grading_scheme_version_id=a.grading_scheme_version_id,
        grade_release=a.grade_release or "auto", omit_from_total=bool(a.omit_from_total),
        published=a.status == "published" and a.published_version_id is not None, published_at=a.published_at,
        position=a.position, created_by_id=a.created_by_id, deleted_by_id=a.deleted_by_id,
        created_at=now, updated_at=now, deleted_at=a.deleted_at,
    )


def _run(db: Session, report: BootstrapReport) -> None:
    now = utcnow()
    asm = Assessment.__table__
    ver = AssessmentVersion.__table__
    asg = Assignment.__table__
    # step 2: quiz assignments of assessments that have none (keyset over assessments.id)
    last = None
    while True:
        stmt = (select(asm, ver.c.points_possible.label("pv_points"))
                .select_from(asm.outerjoin(ver, ver.c.id == asm.c.published_version_id))
                .where(~select(asg.c.id).where(asg.c.assessment_id == asm.c.id).exists())
                .order_by(asm.c.id).limit(BATCH))
        if last is not None:
            stmt = stmt.where(asm.c.id > last)
        rows = db.execute(stmt).all()
        if not rows:
            break
        db.execute(asg.insert(), [quiz_assignment_row(r, r.pv_points, now) for r in rows])
        report.assignments_created += len(rows)
        last = rows[-1].id
    # step 3: submissions without an assignment (only rows of a database where the column is still nullable)
    sub = Submission.__table__
    for (asid,) in db.execute(select(sub.c.assessment_id).where(
            sub.c.assignment_id.is_(None), sub.c.assessment_id.is_not(None)).distinct()).all():
        res = db.execute(update(sub).where(sub.c.assessment_id == asid, sub.c.assignment_id.is_(None))
                         .values(assignment_id=assignment_id_for(asid)))
        report.submissions_moved += res.rowcount or 0
    if report.assignments_created or report.submissions_moved:
        log.info("Assignment bootstrap: %s", report)


__all__ = ["ensure_assignments", "BootstrapReport", "quiz_assignment_row"]
