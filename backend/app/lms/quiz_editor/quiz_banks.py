"""Quiz banks (PHASE_7C_DESIGN 5.1, 16): the bank a quiz writes its own questions into.

A quiz bank is a `question_banks` row with `assessment_id` set. It is created on first use (while the caller holds the
assessment row lock), soft-deleted and restored together with its quiz, never deleted/restored/renamed directly, and
private to its quiz: no other assessment may reference its questions, passages or the bank itself (16)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext
from app.lms.assessments.models import Assessment
from app.lms.content.models import QuestionBank
from app.lms.core.errors import ValidationFailed
from app.lms.core.types import localized
from app.lms.quiz_editor import ids


def is_quiz_bank(bank) -> bool:
    return getattr(bank, "assessment_id", None) is not None


def shareable(bank) -> bool:
    """Phase 9 (org-shared banks, `visibility`) must call this before sharing a bank: a quiz bank is never shared
    (invariant 4.5). `test_quiz_bank_not_shareable` fails as soon as a `visibility` column appears, as a reminder."""
    return not is_quiz_bank(bank)


def assert_bank_usable(bank, a: Assessment) -> None:
    """16: an assessment may reference a shared bank or its own quiz bank, never another quiz's bank."""
    if bank is not None and bank.assessment_id is not None and bank.assessment_id != a.id:
        raise ValidationFailed("This question belongs to another quiz", code=ids.E_QUIZ_BANK_PRIVATE,
                               details=[{"loc": ["bank_id"], "msg": ids.E_QUIZ_BANK_PRIVATE}])


def assert_question_usable(db: Session, q, a: Assessment) -> None:
    assert_bank_usable(db.get(QuestionBank, q.bank_id), a)


def live_quiz_bank(db: Session, a: Assessment, *, for_update: bool = False) -> Optional[QuestionBank]:
    stmt = select(QuestionBank).where(QuestionBank.assessment_id == a.id, QuestionBank.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.execute(stmt).scalar_one_or_none()


def ensure_quiz_bank(db: Session, ctx: AuthzContext, course, a: Assessment) -> QuestionBank:
    """The live quiz bank of `a`, created on first use. The caller holds `load_assessment(for_update=True)`, which
    serializes first use; `uq_question_banks_assessment_live` is the backstop. No commit."""
    bank = live_quiz_bank(db, a, for_update=True)
    if bank is not None:
        return bank
    title = (localized(a.title, course.default_language or "en") or "")[:200] or "Quiz"
    bank = QuestionBank(owner_id=ctx.user.id, course_id=course.id, assessment_id=a.id, title=title,
                        default_language=course.default_language)
    db.add(bank)
    db.flush()
    return bank


def soft_delete_with_quiz(db: Session, a: Assessment, actor_id: Optional[str]) -> None:
    bank = live_quiz_bank(db, a, for_update=True)
    if bank is not None:
        bank.soft_delete(actor_id)


def restore_with_quiz(db: Session, a: Assessment) -> None:
    """Restores the quiz's (latest) deleted quiz bank unless a live one exists (at most one exists per quiz)."""
    if live_quiz_bank(db, a) is not None:
        return
    bank = db.execute(
        select(QuestionBank).where(QuestionBank.assessment_id == a.id, QuestionBank.deleted_at.is_not(None))
        .order_by(QuestionBank.deleted_at.desc()).limit(1).with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if bank is not None:
        bank.restore()
