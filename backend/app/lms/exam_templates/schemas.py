"""Exam template API schemas (PHASE_7B_DESIGN 9.1). Two output shapes: `ExamTemplateOut` for people who manage the
template (draft, owner, revision) and `ExamTemplatePickerOut` for course pickers (published structure only: no
`draft_spec`, no `owner_user_id`, no `draft_rev`; the serializer contract test asserts the key set)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.lms.assessments.schemas import AssessmentStaffOut, IssueOut
from app.lms.core.types import localized_text

OwnerScope = Literal["platform", "organization", "teacher"]
Title = localized_text(200)
Description = localized_text(5000)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- inputs

class ExamTemplateCreateIn(_In):
    owner_scope: OwnerScope
    organization_id: Optional[uuid.UUID] = None   # required unless platform; teacher: an org the caller belongs to
    title: Title
    description: Optional[Description] = None
    draft_spec: Optional[dict] = None             # validated fully (422 spec_invalid)

    @model_validator(mode="after")
    def _v(self):
        if (self.owner_scope == "platform") != (self.organization_id is None):
            raise ValueError("organization_id is required for organization and teacher templates and must be "
                             "absent for platform templates")
        return self


class ExamTemplatePatchIn(_In):
    draft_rev: int = Field(ge=1)
    title: Optional[Title] = None
    description: Optional[Description] = None
    draft_spec: Optional[dict] = None             # explicit null clears the draft; absent = unchanged

    @model_validator(mode="after")
    def _v(self):
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self


class ReasonIn(_In):
    reason: Optional[str] = Field(default=None, max_length=500)


class SectionCountIn(_In):
    position: int = Field(ge=1, le=100)
    min_items: Optional[int] = Field(default=None, ge=1, le=10_000)
    max_items: Optional[int] = Field(default=None, ge=1, le=10_000)

    @model_validator(mode="after")
    def _v(self):
        if self.min_items is not None and self.max_items is not None and self.min_items > self.max_items:
            raise ValueError("min_items must not exceed max_items")
        return self


class SaveAsTemplateIn(_In):
    """`POST .../assessments/{id}/save-as-template` (5.5)."""
    owner_scope: OwnerScope
    organization_id: Optional[uuid.UUID] = None   # default: the course's organization (not for platform)
    title: Title
    description: Optional[Description] = None
    lock_scope: Optional[list[str]] = Field(default=None, max_length=20)
    display_mode: Optional[str] = None
    sections_counts: Optional[list[SectionCountIn]] = Field(default=None, max_length=100)


class ListQuery(_In):
    scope: Optional[OwnerScope] = None
    organization_id: Optional[uuid.UUID] = None
    course_id: Optional[uuid.UUID] = None
    status: Optional[Literal["draft", "published", "archived"]] = None


# --------------------------------------------------------------------------- outputs

class ExamTemplateVersionBriefOut(BaseModel):
    id: uuid.UUID
    version_no: int
    published_at: datetime


class ExamTemplateVersionOut(ExamTemplateVersionBriefOut):
    template_id: uuid.UUID
    spec: dict
    spec_hash: str
    grading_scheme_version_id: Optional[uuid.UUID] = None
    published_by_id: Optional[str] = None


class ExamTemplatePickerOut(BaseModel):
    """Picker payload: the published structure (`current_spec`), nothing about drafts or owners (B11)."""
    id: uuid.UUID
    owner_scope: str
    organization_id: Optional[uuid.UUID] = None
    title: dict
    description: Optional[dict] = None
    status: str
    locked: bool
    current_version_id: Optional[uuid.UUID] = None
    current_version_no: Optional[int] = None
    current_spec: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class ExamTemplateOut(ExamTemplatePickerOut):
    """Management payload (owner, org admin of its org, platform admin)."""
    owner_user_id: Optional[str] = None
    key: Optional[str] = None
    draft_spec: Optional[dict] = None
    draft_rev: int
    created_by_id: Optional[str] = None
    can_lock: bool = False       # the caller is the owner (9.2 lock / unlock)
    can_promote: bool = False    # teacher scope and the caller administers its organization


class ExamTemplatePublishOut(BaseModel):
    template: ExamTemplateOut
    version: ExamTemplateVersionOut
    unchanged: bool


# ---- block catalog (7)

class QuestionTypeBlockOut(BaseModel):
    key: str
    title_key: str
    supports_passages: bool
    import_columns: list[str]


class SchemeVersionBlockOut(BaseModel):
    id: uuid.UUID
    scheme_id: uuid.UUID
    title: dict
    type: str
    version_no: int
    scope: Literal["system", "mine"]


class BlocksOut(BaseModel):
    question_types: list[QuestionTypeBlockOut]
    result_views: list[str]
    passage_displays: list[str]
    display_modes: list[str]
    navigations: list[str]
    importer_profiles: list[str]
    lock_scope_keys: list[str]
    scheme_versions: list[SchemeVersionBlockOut]


# ---- assessment-bound routes

class TemplateUpgradeOut(BaseModel):
    assessment: AssessmentStaffOut
    issues: list[IssueOut]


PICKER_KEYS = frozenset(ExamTemplatePickerOut.model_fields)
MANAGE_ONLY_KEYS = frozenset(ExamTemplateOut.model_fields) - PICKER_KEYS
