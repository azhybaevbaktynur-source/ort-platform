"""The only module that turns attempt/plan data into attempt result JSON (design 3.9).

Student review items never carry a key or an explanation unless `with_keys` builds the keyed subclass.
Staff models are explicitly named and always carry keys."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, SerializeAsAny

from app.lms.content import repository as content_repo
from app.lms.content.types import get_type
from app.lms.grading.serializers import AttemptGradeOut


class StudentPassageOut(BaseModel):
    id: uuid.UUID
    title: Optional[str] = None
    body: str
    image_url: Optional[str] = None


class StudentQuestionOut(BaseModel):
    id: uuid.UUID
    type: str
    language: str
    stem: str
    image_url: Optional[str] = None
    points: Optional[float] = None
    data: dict[str, Any]


class AttemptResultSectionOut(BaseModel):
    pos: int
    key: Optional[str] = None
    raw: Decimal
    possible: Decimal
    answered: int
    correct: int
    # Phase 7b S7: the section title of the attempt's snapshot (LocalizedText; None when untitled / unknown)
    title: Optional[Any] = None


class AttemptResultOut(BaseModel):
    raw_score: Decimal
    points_possible: Decimal
    sections: list[AttemptResultSectionOut]
    pending_review: int
    submitted_at: Optional[datetime] = None
    # Phase 4 (design 5): students only once released (P4-11); previews inline; staff always.
    grade: Optional[AttemptGradeOut] = None


class VoidResultOut(BaseModel):
    """Result of a voided attempt for its owner (P4-20): the status only, no numbers."""
    status: str = "void"


class ReviewItemOut(BaseModel):
    position: int
    section_pos: int
    question: StudentQuestionOut
    passage: Optional[StudentPassageOut] = None
    response: Optional[dict[str, Any]] = None
    flagged: bool
    correctness: Optional[str] = None
    score: Optional[Decimal] = None
    points: Decimal
    feedback: Optional[str] = None


class ReviewItemKeyedOut(ReviewItemOut):
    """Only built when the results policy and show_correct_answers allow keys (or for staff)."""
    key: dict[str, Any]
    explanation: Optional[str] = None


class ReviewOut(BaseModel):
    # SerializeAsAny: keyed items keep their `key`/`explanation`; plain items never have the fields at all
    items: list[SerializeAsAny[ReviewItemOut]]


class StaffReviewItem(ReviewItemKeyedOut):
    auto_score: Optional[Decimal] = None
    manual_score: Optional[Decimal] = None
    graded_by_id: Optional[str] = None
    graded_by_name: Optional[str] = None
    graded_at: Optional[datetime] = None


class AttemptStaffSummaryOut(BaseModel):
    id: uuid.UUID
    user_id: str
    student_name: Optional[str] = None
    attempt_no: Optional[int] = None
    status: str
    language: str
    is_preview: bool
    started_at: datetime
    submitted_at: Optional[datetime] = None
    submit_reason: Optional[str] = None
    raw_score: Optional[Decimal] = None
    points_possible: Optional[Decimal] = None
    pending_review: int = 0
    grade: Optional[AttemptGradeOut] = None


class AttemptStaffOut(AttemptStaffSummaryOut):
    assessment_id: uuid.UUID
    submission_id: Optional[uuid.UUID] = None
    result: Optional[AttemptResultOut] = None
    items: list[StaffReviewItem]


class ScoreIn(BaseModel):
    points: Decimal = Field(allow_inf_nan=False)
    feedback: Optional[str] = Field(default=None, max_length=5000)


# ------------------------------------------------------------------ builders

def result_out(attempt, plan=None) -> Optional[AttemptResultOut]:
    """Totals of a finalized attempt from the stored columns (no DB access); None while in progress."""
    if attempt.raw_score is None or not attempt.result:
        return None
    # Phase 7b S7: section titles from the attempt's snapshot (the plan), when the caller has it
    titles = {int(s["pos"]): s.get("title") for s in (plan.snapshot.get("sections", []) if plan is not None else [])}
    return AttemptResultOut(
        raw_score=attempt.raw_score, points_possible=attempt.points_possible,
        sections=[AttemptResultSectionOut(**{**s, "title": titles.get(int(s["pos"]))})
                  for s in attempt.result.get("sections", [])],
        pending_review=int(attempt.result.get("pending_review", 0)), submitted_at=attempt.submitted_at,
    )


def pending_count(attempt) -> int:
    return int((attempt.result or {}).get("pending_review", 0))


def _passage_out(pv) -> StudentPassageOut:
    d = content_repo.student_passage(pv)
    return StudentPassageOut(id=d["id"], title=d["title"], body=d["body"], image_url=d["image_url"])


def _question_out(qv, choice_order) -> StudentQuestionOut:
    d = content_repo.student_question(qv)
    data = d["data"]
    if choice_order and isinstance(data.get("choices"), list):
        pos = {cid: i for i, cid in enumerate(choice_order)}
        data = {**data, "choices": sorted(data["choices"], key=lambda c: pos.get(c.get("id"), len(pos)))}
    return StudentQuestionOut(id=d["id"], type=d["type"], language=d["language"], stem=d["stem"],
                              image_url=d["image_url"], points=d["points"], data=data)


def _effective(item) -> Optional[Decimal]:
    return item.manual_score if item.manual_score is not None else item.score


def review_item(item, qv, pv, points: Decimal, *, with_keys: bool, staff: bool = False,
                grader_names: Optional[dict] = None) -> ReviewItemOut:
    fields: dict[str, Any] = dict(
        position=item.position, section_pos=item.section_pos, question=_question_out(qv, item.choice_order),
        passage=_passage_out(pv) if pv is not None else None, response=item.response, flagged=bool(item.flagged),
        correctness=item.correctness, score=_effective(item), points=points, feedback=item.feedback,
    )
    if with_keys or staff:
        fields["key"] = content_repo.expand_images(get_type(qv.type).key_view(qv.data))
        fields["explanation"] = qv.explanation
    if staff:
        return StaffReviewItem(
            **fields, auto_score=item.score, manual_score=item.manual_score, graded_by_id=item.graded_by_id,
            graded_by_name=(grader_names or {}).get(item.graded_by_id), graded_at=item.graded_at,
        )
    if with_keys:
        return ReviewItemKeyedOut(**fields)
    return ReviewItemOut(**fields)


def staff_summary(attempt, student_name: Optional[str], grade: Optional[AttemptGradeOut] = None
                  ) -> AttemptStaffSummaryOut:
    return AttemptStaffSummaryOut(
        id=attempt.id, user_id=attempt.user_id, student_name=student_name, attempt_no=attempt.attempt_no,
        status=attempt.status, language=attempt.language, is_preview=attempt.is_preview,
        started_at=attempt.started_at, submitted_at=attempt.submitted_at, submit_reason=attempt.submit_reason,
        raw_score=attempt.raw_score, points_possible=attempt.points_possible, pending_review=pending_count(attempt),
        grade=grade,
    )
