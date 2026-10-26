"""Assessment API schemas (design section 5). Student models are explicit allow-lists: they never carry
keys, drafts, other users' data or builder internals. Staff and student outputs are distinct classes."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings
from app.lms.assessments.rules import ORT_SUBJECT_KEYS
from app.lms.content.types import TYPE_NAMES
from app.lms.core.types import SUPPORTED_LANGUAGES, localized_text

Lang = Literal["en", "ru", "ky"]
Title = localized_text(200)
Description = localized_text(5000)
Preset = Literal["none", "ort_main", "ort_subject"]
ScorePolicy = Literal["highest", "latest", "first", "average"]
Navigation = Literal["free", "section_forward_only"]
ResultsPolicy = Literal["never", "after_submit", "after_close"]
GradeRelease = Literal["auto", "manual"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_languages(languages: list[str]) -> list[str]:
    if not languages or len(languages) > 3 or len(set(languages)) != len(languages):
        raise ValueError("languages must be 1..3 unique values")
    if any(x not in SUPPORTED_LANGUAGES for x in languages):
        raise ValueError("unsupported language")
    return languages


# --------------------------------------------------------------------------- inputs

class AssessmentCreateIn(_In):
    title: Title
    description: Optional[Description] = None
    preset: Preset = "none"
    languages: list[Lang] = Field(min_length=1, max_length=3)
    subject_key: Optional[str] = Field(default=None, max_length=40)
    # --- Phase 7b S2 begin --- (PHASE_7B_DESIGN 9.1: create from an exam template; `preset` must stay 'none',
    # checked in the builder as 422 `preset_template_exclusive`; `subject_key` only with ort_subject, unchanged)
    exam_template_id: Optional[uuid.UUID] = None
    exam_template_version_id: Optional[uuid.UUID] = None
    parameters: Optional[dict[str, str]] = None

    @field_validator("parameters")
    @classmethod
    def _parameters(cls, v):
        if v is not None and (len(v) > 5 or any(len(k) > 40 or len(val) > 40 for k, val in v.items())):
            raise ValueError("parameters: at most 5 entries of short keys and values")
        return v
    # --- Phase 7b S2 end ---

    @model_validator(mode="after")
    def _v(self):
        _check_languages(list(self.languages))
        if self.preset == "ort_subject" and self.subject_key not in ORT_SUBJECT_KEYS:
            raise ValueError("subject_key must be one of " + ", ".join(ORT_SUBJECT_KEYS))
        return self


class AssessmentUpdateIn(_In):
    draft_rev: int = Field(ge=1)
    title: Optional[Title] = None
    description: Optional[Description] = None
    languages: Optional[list[Lang]] = Field(default=None, min_length=1, max_length=3)
    time_limit_s: Optional[int] = Field(default=None, ge=60, le=86400)
    allowed_attempts: Optional[int] = Field(default=None, ge=-1, le=100)
    score_policy: Optional[ScorePolicy] = None
    shuffle_items: Optional[bool] = None
    shuffle_choices: Optional[bool] = None
    navigation: Optional[Navigation] = None
    results_policy: Optional[ResultsPolicy] = None
    show_correct_answers: Optional[bool] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    # Phase 4 grading settings (PHASE_4_DESIGN 3.3); null clears the scheme / category / due date.
    grading_scheme_version_id: Optional[uuid.UUID] = None
    grade_category_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None
    grade_release: Optional[GradeRelease] = None
    omit_from_total: Optional[bool] = None
    # --- Phase 7a S4 begin --- (PHASE_7A_DESIGN 2.7, 3.8): string sets, null clears, absent = unchanged. Stored only
    # as a bcrypt hash; never serialized (staff see `has_access_code`, students `requires_access_code`).
    access_code: Optional[str] = Field(default=None, max_length=64, repr=False)

    @model_validator(mode="after")
    def _access_code(self):
        if self.access_code is not None:
            code = self.access_code.strip()
            if len(code) > 32 or any(not (0x20 <= ord(ch) <= 0x7E) for ch in code):
                raise ValueError("access_code must be 6-32 printable ASCII characters")  # never echo the value
            self.access_code = code  # shorter than 6: 422 `access_code_too_short` from the builder
        return self
    # --- Phase 7a S4 end ---

    @model_validator(mode="after")
    def _v(self):
        if self.languages is not None:
            _check_languages(list(self.languages))
        if self.allowed_attempts == 0:
            raise ValueError("allowed_attempts must be -1 or 1..100")
        for f in ("title", "shuffle_items", "shuffle_choices", "score_policy", "navigation", "results_policy",
                  "show_correct_answers", "allowed_attempts", "languages", "grade_release", "omit_from_total"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class SectionRulesIn(_In):
    allowed_types: Optional[list[str]] = None
    max_items: Optional[int] = Field(default=None, ge=1, le=10_000)
    allow_passages: Optional[bool] = None
    min_items: Optional[int] = Field(default=None, ge=1, le=10_000)  # --- Phase 7b S1 --- (PHASE_7B_DESIGN 2.4)

    @field_validator("allowed_types")
    @classmethod
    def _types(cls, v):
        if v is not None and (not v or len(set(v)) != len(v) or any(t not in TYPE_NAMES for t in v)):
            raise ValueError("allowed_types must be a non-empty list of known question types")
        return v

    # --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 2.4)
    @model_validator(mode="after")
    def _min_max(self):
        if self.min_items is not None and self.max_items is not None and self.min_items > self.max_items:
            raise ValueError("min_items must not exceed max_items")
        return self
    # --- Phase 7b S1 end ---


class SectionIn(_In):
    title: Optional[localized_text(200)] = None
    key: Optional[str] = Field(default=None, max_length=40)
    instructions: Optional[localized_text(5000)] = None
    time_limit_s: Optional[int] = Field(default=None, ge=60, le=86400)
    rules: Optional[SectionRulesIn] = None


class PickFilterIn(_In):
    section: Optional[str] = Field(default=None, max_length=40)
    topic: Optional[str] = Field(default=None, max_length=200)
    difficulty: Optional[Literal["easy", "medium", "hard"]] = None
    type: Optional[str] = None
    tags: Optional[list[str]] = Field(default=None, max_length=5)

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v is not None and v not in TYPE_NAMES:
            raise ValueError("unknown question type")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        if v is not None and any((not isinstance(t, str)) or len(t) > 100 for t in v):
            raise ValueError("invalid tag")
        return v

    def as_json(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v not in (None, [], "")}


class PickIn(_In):
    bank_id: uuid.UUID
    count: int = Field(ge=1, le=200)
    filter: PickFilterIn = Field(default_factory=PickFilterIn)

    @field_validator("count")
    @classmethod
    def _cap(cls, v):
        if v > settings.ASSESSMENT_PICK_COUNT_MAX:
            raise ValueError("count exceeds the cap")
        return v


def _points(v):
    if v is not None and (v < 0 or v > settings.ASSESSMENT_ITEM_POINTS_MAX):
        raise ValueError(f"points must be 0..{settings.ASSESSMENT_ITEM_POINTS_MAX}")
    return v


class ItemCreateIn(_In):
    kind: Literal["question", "passage", "pick"]
    question_id: Optional[uuid.UUID] = None
    passage_id: Optional[uuid.UUID] = None
    question_ids: Optional[list[uuid.UUID]] = Field(default=None, max_length=500)
    points: Optional[Decimal] = None
    pick: Optional[PickIn] = None

    _p = field_validator("points")(_points)

    @model_validator(mode="after")
    def _v(self):
        if self.kind == "question" and self.question_id is None:
            raise ValueError("question_id is required")
        if self.kind == "passage" and self.passage_id is None:
            raise ValueError("passage_id is required")
        if self.kind == "pick" and self.pick is None:
            raise ValueError("pick is required")
        return self


class ItemUpdateIn(_In):
    points: Optional[Decimal] = None
    section_id: Optional[uuid.UUID] = None
    pick: Optional[PickIn] = None

    _p = field_validator("points")(_points)


class BulkFilterIn(PickFilterIn):
    q: Optional[str] = Field(default=None, max_length=200)
    language: Optional[Lang] = None
    passage_id: Optional[uuid.UUID] = None


class BulkAddIn(_In):
    question_ids: Optional[list[uuid.UUID]] = Field(default=None, max_length=500)
    bank_id: Optional[uuid.UUID] = None
    filter: Optional[BulkFilterIn] = None
    points: Optional[Decimal] = None
    group_passages: bool = True

    _p = field_validator("points")(_points)

    @model_validator(mode="after")
    def _v(self):
        if (self.question_ids is None) == (self.bank_id is None):
            raise ValueError("give either question_ids or bank_id")
        if self.question_ids is not None and self.filter is not None:
            raise ValueError("filter only applies with bank_id")
        return self


class ItemsOrderIn(_In):
    item_ids: list[uuid.UUID] = Field(max_length=2000)
    parent_item_id: Optional[uuid.UUID] = None


class SectionsOrderIn(_In):
    section_ids: list[uuid.UUID] = Field(max_length=100)


class PublishIn(_In):
    confirm: bool = False


class PreviewIn(_In):
    language: Optional[Lang] = None


# --------------------------------------------------------------------------- grading scheme references

class SchemeRefOut(BaseModel):
    """Staff view of an attached grading scheme version (PHASE_4_DESIGN 3.3)."""
    id: uuid.UUID
    scheme_id: uuid.UUID
    title: dict
    type: str
    version_no: int
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    # client label map of the version (`params.labels_for`): band key -> LocalizedText, lookup label -> text
    labels: dict = {}


class SchemeStudentRefOut(BaseModel):
    """Student view: no ids, no params (PHASE_4_DESIGN 3.3 / 4); `labels` only renders grade label keys."""
    type: str
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    title: dict
    labels: dict = {}


def scheme_ref(brief: Optional[dict]) -> Optional[SchemeRefOut]:
    return SchemeRefOut(**brief) if brief else None


def scheme_student_ref(brief: Optional[dict]) -> Optional[SchemeStudentRefOut]:
    if not brief:
        return None
    return SchemeStudentRefOut(type=brief["type"], scale_min=brief["scale_min"], scale_max=brief["scale_max"],
                               title=brief["title"], labels=brief.get("labels") or {})


# --------------------------------------------------------------------------- staff outputs

class AttemptCountsOut(BaseModel):
    in_progress: int = 0
    submitted: int = 0


class ItemQuestionOut(BaseModel):
    id: uuid.UUID
    type: str
    language: str
    stem_excerpt: str
    deleted: bool
    newer_version_available: bool


class ItemPassageOut(BaseModel):
    id: uuid.UUID
    title: Optional[str] = None


class ItemPickOut(BaseModel):
    bank_id: uuid.UUID
    count: int
    filter: dict
    pool_size: dict[str, int]


class ItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    position: int
    points: Optional[float] = None
    question: Optional[ItemQuestionOut] = None
    passage: Optional[ItemPassageOut] = None
    children: Optional[list["ItemOut"]] = None
    pick: Optional[ItemPickOut] = None


class SectionOut(BaseModel):
    id: uuid.UUID
    position: int
    key: Optional[str] = None
    title: Optional[dict] = None
    instructions: Optional[dict] = None
    time_limit_s: Optional[int] = None
    rules: dict
    items: list[ItemOut] = []


class AssessmentStaffSummaryOut(BaseModel):
    id: uuid.UUID
    title: dict
    preset: str
    status: str
    languages: list[str]
    item_count: int
    points_possible: float
    has_unpublished_changes: bool
    current_version_no: Optional[int] = None
    attempt_counts: AttemptCountsOut
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    has_access_code: bool = False  # --- Phase 7a S4 --- (2.7: the hash itself is never serialized)
    # --- Phase 7b S2 --- (list rows carry the template reference too, so pickers can offer template exams only)
    exam_template: Optional["ExamTemplateRefOut"] = None


# --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 9.1: the template an assessment was created from)
class ExamTemplateRefOut(BaseModel):
    template_id: uuid.UUID
    title: dict
    version_no: int
    version_id: uuid.UUID
    latest_version_no: Optional[int] = None
    locked_fields: list[str] = []
    template_locked: bool = False  # Phase 7b S6: the template is locked now ("Save as template" is refused)
# --- Phase 7b S1 end ---


class AssessmentStaffOut(AssessmentStaffSummaryOut):
    description: Optional[dict] = None
    draft_rev: int
    time_limit_s: Optional[int] = None
    allowed_attempts: int
    score_policy: str
    shuffle_items: bool
    shuffle_choices: bool
    navigation: str
    results_policy: str
    show_correct_answers: bool
    grading_scheme_version_id: Optional[uuid.UUID] = None
    grade_category_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None
    grade_release: str = "auto"
    omit_from_total: bool = False
    scheme: Optional[SchemeRefOut] = None
    sections: list[SectionOut]
    warnings: list[dict] = []
    # --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 9.1; `exam_template` is inherited from the summary, S2)
    display_mode: str = "one_per_page"
    passage_display: Optional[str] = None
    result_view: Optional[str] = None
    structure_locked: bool = False
    # --- Phase 7b S1 end ---


class IssueOut(BaseModel):
    code: str
    section_pos: Optional[int] = None
    item_id: Optional[str] = None
    language: Optional[str] = None


class ValidationOut(BaseModel):
    errors: list[IssueOut]
    warnings: list[IssueOut]


class VersionBriefOut(BaseModel):
    id: uuid.UUID
    version_no: int
    item_count: int
    points_possible: float
    created_at: datetime


class PublishOut(BaseModel):
    assessment: AssessmentStaffOut
    version: VersionBriefOut
    unchanged: bool


class VersionOut(VersionBriefOut):
    created_by_name: Optional[str] = None
    attempt_counts: AttemptCountsOut


class SkippedOut(BaseModel):
    question_id: uuid.UUID
    code: str


class BulkAddOut(BaseModel):
    added: int
    skipped: list[SkippedOut]


# --------------------------------------------------------------------------- student outputs (allow-lists)

class LastResultOut(BaseModel):
    raw_score: float
    points_possible: float


class AssessmentStudentSummaryOut(BaseModel):
    id: uuid.UUID
    title: dict
    languages: list[str]
    time_limit_s: Optional[int] = None
    item_count: int
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    allowed_attempts: int
    attempts_used: int
    in_progress_attempt_id: Optional[uuid.UUID] = None
    last_result: Optional[LastResultOut] = None
    due_at: Optional[datetime] = None
    scheme: Optional[SchemeStudentRefOut] = None


class LobbySectionOut(BaseModel):
    pos: int
    key: Optional[str] = None
    title: Optional[dict] = None
    time_limit_s: Optional[int] = None
    item_count: int


class AssessmentLobbyOut(BaseModel):
    id: uuid.UUID
    title: dict
    description: Optional[dict] = None
    languages: list[str]
    sections: list[LobbySectionOut]
    time_limit_s: Optional[int] = None
    navigation: str
    allowed_attempts: int
    attempts_used: int
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    in_progress_attempt_id: Optional[uuid.UUID] = None
    can_start: bool
    reason: Optional[str] = None
    due_at: Optional[datetime] = None
    scheme: Optional[SchemeStudentRefOut] = None
    requires_access_code: bool = False  # --- Phase 7a S4 --- (3.8: a student must enter the code at start)


# Exact key sets, asserted by the contract tests.
STUDENT_SUMMARY_KEYS = frozenset(AssessmentStudentSummaryOut.model_fields)
LOBBY_KEYS = frozenset(AssessmentLobbyOut.model_fields)

ItemOut.model_rebuild()
AssessmentStaffSummaryOut.model_rebuild()  # --- Phase 7b S2 --- (forward ref to ExamTemplateRefOut)
