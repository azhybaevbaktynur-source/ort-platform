"""Move or copy a question to a shared bank (PHASE_7C_DESIGN 5.6, P7C-9). The reuse path of 16: after a move the
question lives in a shared bank (items still point at it); a copy is a new question there (items untouched)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.content import repository as content_repo
from app.lms.content import service as content_svc
from app.lms.content.models import BankQuestion, QuestionBank, QuestionVersion
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.courses.service import require_course
from app.lms.quiz_editor import ids
from app.lms.quiz_editor.schemas import CopyToBankIn


def copy_or_move_to_bank(db: Session, ctx: AuthzContext, course, question_id: uuid.UUID,
                         data: CopyToBankIn) -> BankQuestion:
    require_course(ctx, A.CONTENT_MANAGE, course)
    q = content_repo.load_question(db, course.id, question_id)            # 404 question_not_found (live, course)
    target = content_repo.load_bank(db, course.id, data.bank_id)           # 404 bank_not_found (live, course)
    if target.assessment_id is not None:
        raise ValidationFailed("The target must be a shared bank", code=ids.E_TARGET_NOT_SHARED_BANK,
                               details=[{"loc": ["bank_id"], "msg": ids.E_TARGET_NOT_SHARED_BANK}])
    # lock order: banks (sorted by id), then the question (as content.add_translation / move_question)
    for bid in sorted({q.bank_id, target.id}, key=str):
        content_svc._lock_bank(db, target if bid == target.id else db.get(QuestionBank, bid))
    q = content_repo.load_question(db, course.id, question_id, for_update=True)
    if data.mode == "move":
        if q.bank_id == target.id:
            db.commit()
            return q
        if q.passage_id is not None:
            raise Conflict("Move the passage with its questions in the Bank tab", code=ids.E_QUESTION_HAS_PASSAGE)
        if q.source_ref and db.execute(select(BankQuestion.id).where(
                BankQuestion.bank_id == target.id, BankQuestion.source_ref == q.source_ref)).first():
            raise Conflict("A question with this source reference exists in the target bank", code="source_conflict")
        q.bank_id = target.id
        q.position = content_svc._next_position(db, target.id)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise Conflict("A question with this source reference exists in the target bank",
                           code="source_conflict") from None
        return q
    current = db.get(QuestionVersion, q.current_version_id)
    new = BankQuestion(bank_id=target.id, passage_id=None, translation_group_id=None, type=q.type, language=q.language,
                       topic=q.topic, difficulty=q.difficulty, section=q.section, tags=list(q.tags or []),
                       position=content_svc._next_position(db, target.id), q_num=q.q_num, search_text="")
    db.add(new)
    db.flush()
    # refs of the current version are accepted as-is (P2-16): they come from our own history
    content_svc.new_question_version(db, new, content_svc._version_content(current), actor_id=ctx.user.id,
                                     origin="create")
    db.commit()
    return new
