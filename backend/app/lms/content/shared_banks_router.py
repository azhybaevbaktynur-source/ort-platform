"""Phase 9 S2: organization-shared banks (PHASE_9_DESIGN 4.2, 5). Policies in `content/shared_banks_policies.py`.

`org_router` (prefix /org): reads for members of a tree (teachers and org admins of any organization of it; 404
otherwise, the platform admin included). Answer keys are included: the reader is a teacher of the tree (design 4.2,
`content.read_admin` equivalent for these banks only).
`course_router` (prefix /courses): share / unshare (`can_edit_bank`), copy into a course (`content.manage`), and
the sharing state of a course (drives the share toggle and the "From my organization" section)."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext, get_authz
from app.db.session import get_db
from app.lms.content import repository as repo
from app.lms.content import schemas as sch
from app.lms.content.models import BankQuestion, Passage, QuestionBank
from app.lms.content.permissions import can_edit_bank
from app.lms.core.deps import get_lms_user
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc
from app.lms.enrollments.schemas import user_brief
from app.lms.organizations import shared_banks as svc
from app.lms.organizations.schemas import SharedBankRowOut
from app.models.user import User

org_router = APIRouter()
course_router = APIRouter()

READ_LIMIT_MAX = 50


def _row_out(row) -> SharedBankRowOut:
    bank, qc, pc, course_title, org_name, sharer = row
    return SharedBankRowOut(
        id=bank.id, title=bank.title, description=bank.description, organization_id=bank.organization_id,
        organization_name=org_name, course_id=bank.course_id, course_title=course_title or {},
        default_language=bank.default_language, question_count=qc or 0, passage_count=pc or 0,
        shared_at=bank.shared_at, shared_by=user_brief(sharer) if sharer is not None else None,
    )


# ------------------------------------------------------------------ reads: /org/{organization_id}/shared-banks

@org_router.get("/{organization_id}/shared-banks", response_model=PageOut[SharedBankRowOut])
def list_shared_banks(organization_id: uuid.UUID, q: Optional[str] = Query(None, max_length=100),
                      cursor: Optional[str] = None, limit: int = 25,
                      user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    root = svc.reader_root(db, user, organization_id)
    rows, nxt = course_svc.paginate_rows(db, svc.visible_banks_stmt(db, user, root, q), sort_col=QuestionBank.created_at,
                                         id_col=QuestionBank.id, entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    return PageOut[SharedBankRowOut](items=[_row_out(r) for r in rows], next_cursor=nxt)


@org_router.get("/{organization_id}/shared-banks/{bank_id}", response_model=SharedBankRowOut)
def get_shared_bank(organization_id: uuid.UUID, bank_id: uuid.UUID, user: User = Depends(get_lms_user),
                    db: Session = Depends(get_db)):
    root = svc.reader_root(db, user, organization_id)
    return _row_out(svc.load_visible_bank(db, user, root, bank_id))


@org_router.get("/{organization_id}/shared-banks/{bank_id}/questions", response_model=PageOut[sch.QuestionStaffOut])
def list_shared_bank_questions(organization_id: uuid.UUID, bank_id: uuid.UUID,
                               q: Optional[str] = Query(None, max_length=200), language: Optional[str] = None,
                               cursor: Optional[str] = None, limit: int = 25,
                               user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    from app.lms.content.router import _staff_out

    root = svc.reader_root(db, user, organization_id)
    bank = svc.load_visible_bank(db, user, root, bank_id)[0]
    course = course_svc.load_course(db, bank.course_id)
    rows, nxt = course_svc.paginate_rows(
        db, repo.question_list_stmt(bank.id, repo.QuestionFilter(q=q, language=language)),
        sort_col=BankQuestion.position, id_col=BankQuestion.id, entity_of=lambda r: r[0], cursor=cursor,
        limit=min(limit, READ_LIMIT_MAX), descending=False)
    return PageOut[sch.QuestionStaffOut](items=[_staff_out(db, course, r[0]) for r in rows], next_cursor=nxt)


@org_router.get("/{organization_id}/shared-banks/{bank_id}/passages", response_model=PageOut[sch.PassageSummaryOut])
def list_shared_bank_passages(organization_id: uuid.UUID, bank_id: uuid.UUID, cursor: Optional[str] = None,
                              limit: int = 25, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    from app.lms.content.router import _passage_summary

    root = svc.reader_root(db, user, organization_id)
    bank = svc.load_visible_bank(db, user, root, bank_id)[0]
    rows, nxt = course_svc.paginate_rows(
        db, repo.passage_rows_stmt(bank.id), sort_col=Passage.created_at, id_col=Passage.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=min(limit, READ_LIMIT_MAX))
    return PageOut[sch.PassageSummaryOut](items=[_passage_summary(r) for r in rows], next_cursor=nxt)


# ------------------------------------------------------------------ course side

class BankSharingOut(BaseModel):
    """Whether this course's banks can be shared with its organization, and with which tree."""
    enabled: bool
    reason: Optional[Literal["template_locked", "personal", "setting_off"]] = None
    root_id: uuid.UUID
    root_name: str
    can_copy: bool   # the caller may copy shared banks into this course (content.manage, not ORT / sandbox)


class CopyFromIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bank_id: uuid.UUID


def _bank_out(ctx: AuthzContext, course, bank_id: uuid.UUID) -> sch.BankOut:
    row = ctx.db.execute(repo.bank_rows_stmt(course.id, bank_id=bank_id)).first()
    from app.core.authz import can

    return sch.bank_out(row, can_edit=can_edit_bank(ctx, course, row[0]), can_delete=can(ctx, A.CONTENT_MANAGE, course))


def _editable_course(ctx: AuthzContext, course_id: uuid.UUID, bank_id: uuid.UUID):
    """`course:content.manage`, or `can_edit_bank` on this bank (an org admin of the tree on a shared bank)."""
    from sqlalchemy import select

    course = course_svc.load_course(ctx.db, course_id)
    bank = ctx.db.execute(select(QuestionBank).where(
        QuestionBank.id == bank_id, QuestionBank.course_id == course.id)).scalar_one_or_none()
    if bank is not None and can_edit_bank(ctx, course, bank):
        return course
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    return course  # staff: a missing or deleted bank is the service's 404


@course_router.get("/{course_id}/bank-sharing", response_model=BankSharingOut)
def bank_sharing(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    from app.core.authz import can

    course = course_svc.load_course(ctx.db, course_id)
    course_svc.require_course(ctx, A.COURSE_READ, course)
    ok, reason, root = svc.sharing_state(ctx.db, course)
    can_copy = (can(ctx, A.CONTENT_MANAGE, course) and course.template_key != "ort"
                and course.sandbox_for_template_id is None)
    return BankSharingOut(enabled=ok, reason=reason, root_id=root.id, root_name=root.name, can_copy=can_copy)


@course_router.post("/{course_id}/banks/{bank_id}/share", response_model=sch.BankOut)
def share_bank(course_id: uuid.UUID, bank_id: uuid.UUID, request: Request, ctx: AuthzContext = Depends(get_authz)):
    course = _editable_course(ctx, course_id, bank_id)
    svc.share_bank(ctx.db, ctx, course, bank_id, request)
    return _bank_out(ctx, course, bank_id)


@course_router.delete("/{course_id}/banks/{bank_id}/share", response_model=sch.BankOut)
def unshare_bank(course_id: uuid.UUID, bank_id: uuid.UUID, request: Request, ctx: AuthzContext = Depends(get_authz)):
    course = _editable_course(ctx, course_id, bank_id)
    svc.unshare_bank(ctx.db, ctx, course, bank_id, request)
    return _bank_out(ctx, course, bank_id)


@course_router.post("/{course_id}/banks/copy-from", status_code=201, response_model=sch.BankOut)
def copy_from(course_id: uuid.UUID, body: CopyFromIn, request: Request, ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    bank = svc.copy_bank(ctx.db, ctx, course, body.bank_id, request)
    return _bank_out(ctx, course, bank.id)

