"""Shapes of the enrollment forms and applications routes (PHASE_9_DESIGN 2.4, 2.5, 4.7, 4.10, 5, 6). S1 fixes the
shapes; S4 fills the services and routes and may add validators. Answer *values* are validated by
`fields.py` (S4, pure functions); errors name the field key and a code, never the submitted value.

PII (invariant 5): `ApplicationStaffOut.answers` is built only for course staff (teacher, assistant) and
`ApplicationOwnOut.answers` only for the applicant; every other payload (org admin, platform admin, lists, audit)
uses `ApplicationOut`, which has `has_answers` and no answers."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from app.lms.core.types import localized_text
from app.lms.enrollment_forms import ids
from app.lms.enrollments.schemas import UserBrief

FieldType = Literal["short_text", "long_text", "single_choice", "multi_choice", "number", "date", "email", "phone"]
PiiCategory = Literal["none", "contact", "personal"]
FormStatus = Literal["draft", "active", "retired"]
ApplicationStatus = Literal["pending", "approved", "rejected", "withdrawn"]
Label = localized_text(200)
Help = localized_text(500)
Intro = localized_text(ids.INTRO_MAX)
FormTitle = localized_text(200)
# one answer: text / option key / list of option keys / number / ISO date string
AnswerValue = Union[str, float, int, list[str], None]


# ------------------------------------------------------------------ builder (teacher; course:course.update)

class FieldOptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=ids.FIELD_KEY_RE)
    label: Label


class NumberBoundsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min: Optional[float] = None
    max: Optional[float] = None


class FieldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=ids.FIELD_KEY_RE)
    type: FieldType
    label: Label
    help: Optional[Help] = None
    options: Optional[list[FieldOptionIn]] = Field(default=None, max_length=ids.OPTIONS_PER_FIELD_MAX)
    bounds: Optional[NumberBoundsIn] = None   # number fields only (stored in `options` as {min, max})
    required: bool = False
    pii_category: PiiCategory
    max_len: Optional[int] = Field(default=None, ge=1, le=ids.LONG_TEXT_MAX)


class FormCreateIn(BaseModel):
    """Create the course's draft (409 `form_draft_exists` when one exists)."""
    model_config = ConfigDict(extra="forbid")
    title: Optional[FormTitle] = None
    intro: Optional[Intro] = None
    fields: list[FieldIn] = Field(default_factory=list, max_length=ids.FIELDS_PER_FORM_MAX)


class FormUpdateIn(BaseModel):
    """PATCH a draft: `fields` replaces all fields (design 5); 409 `form_answered` once answered."""
    model_config = ConfigDict(extra="forbid")
    title: Optional[FormTitle] = None
    intro: Optional[Intro] = None
    fields: Optional[list[FieldIn]] = Field(default=None, max_length=ids.FIELDS_PER_FORM_MAX)


class FieldOptionOut(BaseModel):
    key: str
    label: dict


class FieldOut(BaseModel):
    id: uuid.UUID
    key: str
    type: FieldType
    label: dict
    help: Optional[dict] = None
    options: Optional[list[FieldOptionOut]] = None
    bounds: Optional[dict] = None
    required: bool
    position: int
    pii_category: PiiCategory
    max_len: Optional[int] = None


class EnrollmentFormOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    version: int
    status: FormStatus
    title: Optional[dict] = None
    intro: Optional[dict] = None
    answered: bool
    fields: list[FieldOut]
    created_at: datetime
    activated_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None


class EnrollmentFormSummaryOut(BaseModel):
    """Version list row (no fields)."""
    id: uuid.UUID
    version: int
    status: FormStatus
    answered: bool
    field_count: int
    created_at: datetime
    activated_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None


class PublicFormOut(BaseModel):
    """The active form as the catalog landing and the apply page show it (no answers, no staff data)."""
    id: uuid.UUID
    version: int
    title: Optional[dict] = None
    intro: Optional[dict] = None
    fields: list[FieldOut]


# ------------------------------------------------------------------ applications

class ApplicationSubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form_id: uuid.UUID
    answers: dict[str, Any] = Field(default_factory=dict)   # {field key: AnswerValue}; unknown keys -> 422


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: Optional[str] = Field(default=None, max_length=ids.DECISION_NOTE_MAX)
    send_note: bool = False   # reject: include the note in the email to the student (design 4.8, alternative 15-7)


class MyApplicationBrief(BaseModel):
    """`my_application` on catalog cards and the landing."""
    id: uuid.UUID
    status: ApplicationStatus


class ApplicationOut(BaseModel):
    """List rows and every non-staff payload: statuses and counts, **no answers** (design 5.1, 6)."""
    id: uuid.UUID
    course_id: uuid.UUID
    form_id: uuid.UUID
    form_version: int
    applicant: UserBrief
    status: ApplicationStatus
    has_answers: bool
    submitted_at: datetime
    decided_at: Optional[datetime] = None
    decided_by: Optional[UserBrief] = None
    enrollment_id: Optional[uuid.UUID] = None
    purged_at: Optional[datetime] = None


class ApplicationStaffOut(ApplicationOut):
    """One application for course staff (teacher, assistant): answers rendered against the form's fields."""
    answers: Optional[dict[str, Any]] = None   # NULL after the purge
    fields: list[FieldOut] = Field(default_factory=list)
    decision_note: Optional[str] = None


class ApplicationOwnOut(BaseModel):
    """The applicant's own view (`/me/applications`, submit response): own answers, the course title, the note only
    when the teacher chose to send it."""
    id: uuid.UUID
    course_id: uuid.UUID
    course_title: dict
    status: ApplicationStatus
    submitted_at: datetime
    decided_at: Optional[datetime] = None
    answers: Optional[dict[str, Any]] = None
    decision_note: Optional[str] = None


class AnswerErrorOut(BaseModel):
    """One entry of `ValidationFailed.details` for a submit: the field key and a code, never the value."""
    field_key: str
    type: Literal["required", "too_long", "bad_option", "bad_format"]


class PurgeOut(BaseModel):
    purged: int
    remaining: bool
    ran_at: datetime
