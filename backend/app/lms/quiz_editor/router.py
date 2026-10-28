"""Quiz editor routes (prefix /courses; PHASE_7C_DESIGN 6.1). Policies: quiz_editor/policies.py."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Response

from app.core.authz import A, AuthzContext, get_authz
from app.lms.assessments import builder
from app.lms.content import repository as content_repo
from app.lms.content.schemas import QuestionStaffOut
from app.lms.courses import service as course_svc
from app.lms.quiz_editor import bank_ops, commit, drafts, usage
from app.lms.quiz_editor.schemas import (
    CommitIn, CommitOut, CopyToBankIn, DraftCreateIn, DraftOut, DraftUpdateIn, QuestionUsageOut, QuizQuestionCreateIn,
)

router = APIRouter()
_A = "/{course_id}/assessments/{assessment_id}"


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    return course_svc.load_course(ctx.db, course_id)


def _question_out(ctx: AuthzContext, course, q):
    from app.lms.content.router import _staff_out

    return _staff_out(ctx.db, course, q)


def _commit_out(ctx: AuthzContext, course, a, item, q, applied: str, version_created: bool) -> CommitOut:
    return CommitOut(item=builder.item_out(ctx.db, a, item), question=_question_out(ctx, course, q),
                     applied=applied, version_created=version_created)


@router.post(_A + "/questions", status_code=201, response_model=CommitOut)
def create_quiz_question(course_id: uuid.UUID, assessment_id: uuid.UUID, data: QuizQuestionCreateIn,
                         ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    a, item, q = commit.create_in_quiz(ctx.db, ctx, course, assessment_id, section_id=data.section_id,
                                       after_item_id=data.after_item_id, payload=data.payload)
    return _commit_out(ctx, course, a, item, q, "created", True)


@router.post(_A + "/drafts", status_code=201, response_model=DraftOut)
def create_draft(course_id: uuid.UUID, assessment_id: uuid.UUID, data: DraftCreateIn,
                 ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    d = drafts.create_draft(ctx.db, ctx, course, assessment_id, data)
    return drafts.draft_out(ctx.db, d)


@router.put(_A + "/drafts/{draft_id}", response_model=DraftOut)
def update_draft(course_id: uuid.UUID, assessment_id: uuid.UUID, draft_id: uuid.UUID, data: DraftUpdateIn,
                 ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    d = drafts.update_draft(ctx.db, ctx, course, assessment_id, draft_id, data)
    return drafts.draft_out(ctx.db, d)


@router.delete(_A + "/drafts/{draft_id}", status_code=204, response_class=Response)
def delete_draft(course_id: uuid.UUID, assessment_id: uuid.UUID, draft_id: uuid.UUID,
                 ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    drafts.delete_draft(ctx.db, ctx, course, assessment_id, draft_id)
    return Response(status_code=204)


@router.post(_A + "/drafts/{draft_id}/commit", response_model=CommitOut)
def commit_draft(course_id: uuid.UUID, assessment_id: uuid.UUID, draft_id: uuid.UUID, data: CommitIn,
                 ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    a, item, q, applied, created = commit.commit_draft(ctx.db, ctx, course, assessment_id, draft_id, data)
    return _commit_out(ctx, course, a, item, q, applied, created)


@router.get("/{course_id}/questions/{question_id}/usage", response_model=QuestionUsageOut)
def question_usage(course_id: uuid.UUID, question_id: uuid.UUID, assessment_id: Optional[uuid.UUID] = None,
                   ctx: AuthzContext = Depends(get_authz)):
    """`assessment_id` (optional): the quiz asking, marked `is_this` and left out of `other_count`."""
    course = _course(ctx, course_id)
    course_svc.require_course(ctx, A.CONTENT_READ_ADMIN, course)
    q = content_repo.load_question(ctx.db, course.id, question_id)
    return usage.question_usage(ctx.db, course, q, this_assessment_id=assessment_id)


@router.post("/{course_id}/questions/{question_id}/copy-to-bank", response_model=QuestionStaffOut)
def copy_to_bank(course_id: uuid.UUID, question_id: uuid.UUID, data: CopyToBankIn,
                 ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    q = bank_ops.copy_or_move_to_bank(ctx.db, ctx, course, question_id, data)
    return _question_out(ctx, course, q)
