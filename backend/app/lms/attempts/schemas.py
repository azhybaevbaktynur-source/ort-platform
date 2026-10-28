"""Request/response models of the student attempt routes (design section 5). snake_case on the wire.

Student-facing DTOs never carry keys or explanations: the content payload is built by the assessments cache from
`content.repository.student_question`, and `AttemptItemStateOut` only references question versions by id."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Lang = Literal["en", "ru", "ky"]
AttemptStatus = Literal["in_progress", "submitted", "needs_review", "graded", "void"]


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Optional[Lang] = None
    # --- Phase 7a S4 --- (3.8) quiz access code; never logged, echoed or stored in plain text
    access_code: Optional[str] = Field(default=None, max_length=64, repr=False)


class AnswerIn(BaseModel):
    """One autosave entry. `response` omitted = leave the answer alone, `null` = clear it. Unknown keys are ignored so
    a client with extra bookkeeping fields never gets a whole batch rejected."""
    model_config = ConfigDict(extra="ignore")
    position: int = Field(ge=1, le=32767)
    response: Optional[dict[str, Any]] = None
    flagged: Optional[bool] = None
    client_ts: int = Field(ge=0, le=10**15)


class AnswersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The 20-entry cap is enforced by the service (422 too_many_answers); max_length here only bounds parsing work.
    answers: list[AnswerIn] = Field(max_length=200)


class SubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: Optional[list[AnswerIn]] = Field(default=None, max_length=200)


class AttemptSectionStateOut(BaseModel):
    pos: int
    started_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class AttemptItemStateOut(BaseModel):
    position: int
    section_pos: int
    qv: Optional[str] = None
    pv: Optional[str] = None
    points: str
    choice_order: Optional[list[str]] = None
    response: Optional[dict[str, Any]] = None
    flagged: bool = False


class AttemptStateOut(BaseModel):
    id: str
    assessment_id: str
    version_id: str
    status: AttemptStatus
    language: Lang
    is_preview: bool
    server_now: datetime
    grace_s: int
    started_at: datetime
    deadline_at: Optional[datetime] = None
    current_section_pos: int
    navigation: Literal["free", "section_forward_only"]
    sections: list[AttemptSectionStateOut]
    items: list[AttemptItemStateOut]
    content_url: str
    content_etag: str
    extra_questions: Optional[dict[str, Any]] = None
    results_available: bool
    # --- Phase 8b S1 begin --- (PHASE_8B_DESIGN 5.4: effective values, never NULL; attempts/display.py)
    display_mode: Literal["one_per_page", "scrolling"] = "one_per_page"
    passage_display: Literal["plain", "numbered"] = "plain"
    # --- Phase 8b S1 end ---


class SaveOut(BaseModel):
    saved: list[int]
    stale: list[int]
    server_now: datetime
    status: AttemptStatus
    current_section_pos: int


RejectReason = Literal["deadline", "already_submitted", "attempt_closed", "section_closed", "stale", "item_not_found",
                       "invalid_response", "too_many_answers"]


class RejectedAnswer(BaseModel):
    """A submit-body answer that was NOT stored (B2). Reasons reuse the autosave error codes, plus `deadline`
    (deadline + grace passed; also a timed-out section) and `already_submitted` (the attempt was already final)."""
    position: int
    reason: RejectReason


class SubmitOut(BaseModel):
    status: AttemptStatus
    submitted_at: Optional[datetime] = None
    results_available: bool
    already_submitted: bool = False
    result: Optional[Any] = None
    # B2: what happened to the answers in the submit body. Positions in neither list were not in the body.
    saved: list[int] = Field(default_factory=list)
    rejected: list[RejectedAnswer] = Field(default_factory=list)


class MyAttemptOut(BaseModel):
    id: str
    attempt_no: Optional[int] = None
    status: AttemptStatus
    started_at: datetime
    submitted_at: Optional[datetime] = None
    results_available: bool
    result: Optional[Any] = None


class SweepOut(BaseModel):
    finalized: int
