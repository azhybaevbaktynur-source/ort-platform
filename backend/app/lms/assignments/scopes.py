"""SQL scopes of the assignment routes (PHASE_7A_DESIGN 3.3, 4.1). Every statement is bound to one course; nothing
here crosses courses, so a foreign id is simply "not found"."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Select, and_, select

from app.lms.assignments.models import Assignment, AssignmentRubricCriterion, AssignmentSubmission


def staff_list(course_id: uuid.UUID, *, deleted: bool = False, kind: Optional[str] = None,
               published: Optional[bool] = None, category_id: Optional[uuid.UUID] = None) -> Select:
    stmt = select(Assignment).where(
        Assignment.course_id == course_id,
        Assignment.deleted_at.is_not(None) if deleted else Assignment.deleted_at.is_(None))
    if kind is not None:
        stmt = stmt.where(Assignment.kind == kind)
    if published is not None:
        stmt = stmt.where(Assignment.published.is_(published))
    if category_id is not None:
        stmt = stmt.where(Assignment.category_id == category_id)
    return stmt


def visible_condition():
    """What students and org admins see (3.3): published and live. A quiz assignment's `published` mirrors
    `status = 'published' AND published_version_id IS NOT NULL` (sync.py)."""
    return and_(Assignment.published.is_(True), Assignment.deleted_at.is_(None))


def student_list(course_id: uuid.UUID) -> Select:
    return select(Assignment).where(Assignment.course_id == course_id, visible_condition())


def one(course_id: uuid.UUID, assignment_id: uuid.UUID, *, include_deleted: bool = False) -> Select:
    stmt = select(Assignment).where(Assignment.id == assignment_id, Assignment.course_id == course_id)
    if not include_deleted:
        stmt = stmt.where(Assignment.deleted_at.is_(None))
    return stmt


def live_criteria(assignment_id: uuid.UUID) -> Select:
    return (select(AssignmentRubricCriterion)
            .where(AssignmentRubricCriterion.assignment_id == assignment_id,
                   AssignmentRubricCriterion.deleted_at.is_(None))
            .order_by(AssignmentRubricCriterion.position, AssignmentRubricCriterion.id))


def own_hand_ins(assignment_id: uuid.UUID, enrollment_id: uuid.UUID) -> Select:
    return (select(AssignmentSubmission)
            .where(AssignmentSubmission.assignment_id == assignment_id,
                   AssignmentSubmission.enrollment_id == enrollment_id)
            .order_by(AssignmentSubmission.attempt_no))


__all__ = ["staff_list", "student_list", "visible_condition", "one", "live_criteria", "own_hand_ins"]
