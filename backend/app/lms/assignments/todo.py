"""Teacher Course page "To do" panel (PHASE_8C_DESIGN 3.5, 7): `GET _C/todo`.

Bounded reads, independent of the number of students or submissions (invariant 8):

1. to grade: one grouped query over `submissions.state = 'pending_review'` of the course's live published assignments
   (`LIMIT 10` after `ORDER BY min(computed_at)`: oldest waiting first), one `COUNT(DISTINCT assignment_id)` and
   one title read for those <= 10 assignments;
2. drafts: one query for <= 10 unpublished live assignments (quizzes included; most recently changed first) and one
   `COUNT`;
3. modules: one `COUNT` of unpublished live modules and one read of the first of them (by position);
4. `active_students` as on the course page.

`needs_grading` per assignment equals `assignments.service.counts(...).needs_grading` (same predicate)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.assignments import schemas as sch
from app.lms.assignments.models import Assignment
from app.lms.core.errors import Forbidden
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.grading.models import Submission

STAFF_ROLES = ("teacher", "assistant")


def _utc(dt):
    from app.lms.modules.evaluator import utc

    return utc(dt)


def require_staff_reader(ctx: AuthzContext, course: Course) -> str:
    """Teacher or assistant of the course (any status: concluded courses read too); students and org admins 403,
    outsiders 404. Returns the caller's role."""
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    role = ctx.role_for(course.id)
    if role not in STAFF_ROLES:
        raise Forbidden("Action not permitted")
    return role


def todo(db: Session, ctx: AuthzContext, course: Course) -> sch.TodoOut:
    from app.lms.modules.models import CourseModule

    role = require_staff_reader(ctx, course)
    n = sch.TODO_GROUP_MAX

    pending = and_(Submission.course_id == course.id, Submission.state == "pending_review",
                   Assignment.course_id == course.id, Assignment.deleted_at.is_(None),
                   Assignment.published.is_(True))
    joined = select(Submission.assignment_id).join(Assignment, Assignment.id == Submission.assignment_id)
    grouped = db.execute(
        select(Submission.assignment_id, func.count(), func.min(Submission.computed_at))
        .join(Assignment, Assignment.id == Submission.assignment_id).where(pending)
        .group_by(Submission.assignment_id)
        .order_by(func.min(Submission.computed_at), Submission.assignment_id).limit(n)
    ).all()
    to_grade_total = len(grouped) if len(grouped) < n else int(db.execute(
        select(func.count(func.distinct(Submission.assignment_id))).select_from(joined.where(pending).subquery())
    ).scalar_one())
    meta = {}
    if grouped:
        meta = {aid: (title, kind) for aid, title, kind in db.execute(
            select(Assignment.id, Assignment.title, Assignment.kind)
            .where(Assignment.id.in_([g[0] for g in grouped])))}
    to_grade = [sch.TodoGradeOut(assignment_id=aid, title=dict(meta.get(aid, ({}, "none"))[0] or {}),
                                 kind=meta.get(aid, ({}, "none"))[1], needs_grading=int(cnt),
                                 oldest_submitted_at=_utc(oldest)) for aid, cnt, oldest in grouped]

    draft_where = and_(Assignment.course_id == course.id, Assignment.deleted_at.is_(None),
                       Assignment.published.is_(False))
    drafts = [sch.TodoDraftOut(assignment_id=a.id, title=dict(a.title or {}), kind=a.kind,
                               assessment_id=a.assessment_id, updated_at=_utc(a.updated_at))
              for a in db.execute(select(Assignment).where(draft_where)
                                  .order_by(Assignment.updated_at.desc(), Assignment.id).limit(n)).scalars()]
    drafts_total = len(drafts) if len(drafts) < n else int(db.execute(
        select(func.count()).select_from(Assignment).where(draft_where)).scalar_one())

    mod_where = and_(CourseModule.course_id == course.id, CourseModule.deleted_at.is_(None),
                     CourseModule.published.is_(False))
    first: Optional[uuid.UUID] = db.execute(
        select(CourseModule.id).where(mod_where).order_by(CourseModule.position, CourseModule.id).limit(1)
    ).scalar()
    unpublished = int(db.execute(select(func.count()).select_from(CourseModule).where(mod_where)).scalar_one()
                      ) if first is not None else 0

    teacher = role == "teacher"
    return sch.TodoOut(
        to_grade=to_grade, to_grade_total=to_grade_total, drafts=drafts, drafts_total=drafts_total,
        unpublished_modules=unpublished, first_unpublished_module_id=first,
        active_students=course_svc.active_student_count(db, course.id),
        join_code=course.join_code if teacher else None,
        join_code_active=course.status == "published" and course.enrollment_mode == "invite_code",
    )


__all__ = ["todo", "require_staff_reader"]
