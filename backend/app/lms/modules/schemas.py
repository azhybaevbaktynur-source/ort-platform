"""Modules API shapes (PHASE_8A_DESIGN 7.1, 6.5). S1 defines the shapes and basic field limits; S2 adds the service
validation (same-course targets, caps, prerequisites, `url_invalid`, `requirement_kind_mismatch`, min_percent <= 100
against the item kind) and builds the outputs.

Student models are explicit allow-lists (design 7.3, invariant 9): no `rules_version`, no warnings, no unpublished
modules or items, no `created_by_id`, no other enrollment's rows. Staff and student outputs are distinct classes.

Titles: module titles and `title_override` are LocalizedText (`{lang: str}`). Targets with a plain-string title
(pages, course files) are wrapped as `{language: title}` (a page's own language; a file: the course default language),
so every `title` in these outputs is a LocalizedText dict the client resolves with its usual fallback."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.lms.assignments.schemas import AssignmentStaffOut
from app.lms.core.types import localized_text
from app.lms.modules import ids

ModuleTitle = localized_text(ids.MODULE_TITLE_MAX)
ItemKind = Literal["page", "file", "assignment", "url", "header"]
RequirementType = Literal["view", "mark_done", "submit", "min_score", "min_percent"]
ModuleState = Literal["locked", "unlocked", "started", "completed"]
CompletionMode = Literal["all", "any"]
WarningCode = Literal[
    "target_unpublished", "target_deleted", "prerequisite_unpublished", "prerequisite_deleted",
    "requirement_on_unpublished_target", "unlock_in_past_with_locked_students",
]
LockReasonKind = Literal["unlock_at", "prerequisite", "sequential"]

_TARGET_FIELDS = {"page": "page_id", "file": "file_id", "assignment": "assignment_id", "url": "url"}


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- inputs

class ModuleIn(_In):
    """`POST _C/modules`."""
    title: ModuleTitle
    published: bool = False
    unlock_at: Optional[datetime] = None
    sequential: bool = False
    completion_mode: CompletionMode = "all"


class ModuleUpdateIn(_In):
    """`PATCH _C/modules/{mid}`: only the fields sent change; `unlock_at: null` clears the date."""
    title: Optional[ModuleTitle] = None
    published: Optional[bool] = None
    unlock_at: Optional[datetime] = None
    sequential: Optional[bool] = None
    completion_mode: Optional[CompletionMode] = None

    @model_validator(mode="after")
    def _not_null(self):
        for f in ("title", "published", "sequential", "completion_mode"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class OrderIn(_In):
    """`PUT _C/modules/order` and `PUT _C/modules/{mid}/items/order`: every live id exactly once (422
    `order_incomplete` otherwise)."""
    ids: list[uuid.UUID] = Field(max_length=ids.ITEMS_PER_MODULE_MAX)


class PrerequisitesIn(_In):
    """`PUT _C/modules/{mid}/prerequisites`: replaces the set."""
    module_ids: list[uuid.UUID] = Field(default_factory=list, max_length=ids.PREREQUISITES_PER_MODULE_MAX)


class RequirementIn(_In):
    """`PUT .../items/{iid}/requirement` (and `ItemIn.requirement`). `threshold` iff `min_score|min_percent`."""
    type: RequirementType
    threshold: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("999999.99"), decimal_places=2)

    @model_validator(mode="after")
    def _threshold(self):
        needs = self.type in ids.THRESHOLD_REQUIREMENTS
        if needs and self.threshold is None:
            raise ValueError(f"threshold is required for {self.type}")
        if not needs and self.threshold is not None:
            raise ValueError(f"threshold is not allowed for {self.type}")
        if self.type == "min_percent" and self.threshold is not None and self.threshold > ids.MIN_PERCENT_MAX:
            raise ValueError("min_percent threshold must be at most 100")
        return self


class ItemIn(_In):
    """`POST _C/modules/{mid}/items`. Exactly the target field of `kind` is set (`header`: none). The service checks
    that the target belongs to the course (404), the `http(s)` scheme of `url` (422 `url_invalid`) and that
    `submit|min_*` sit on an assignment item (422 `requirement_kind_mismatch`); a header takes no requirement."""
    kind: ItemKind
    page_id: Optional[uuid.UUID] = None
    file_id: Optional[uuid.UUID] = None
    assignment_id: Optional[uuid.UUID] = None
    url: Optional[str] = Field(default=None, min_length=1, max_length=ids.URL_MAX)
    title_override: Optional[ModuleTitle] = None
    indent: int = Field(default=0, ge=0, le=ids.INDENT_MAX)
    published: bool = False
    position: Optional[int] = Field(default=None, ge=1)  # None = append at the end
    requirement: Optional[RequirementIn] = None

    @model_validator(mode="after")
    def _target(self):
        want = _TARGET_FIELDS.get(self.kind)
        for f in _TARGET_FIELDS.values():
            value = getattr(self, f)
            if f == want and value is None:
                raise ValueError(f"{f} is required for kind {self.kind}")
            if f != want and value is not None:
                raise ValueError(f"{f} is not allowed for kind {self.kind}")
        if self.kind == "header" and self.requirement is not None:
            raise ValueError("a header has no completion requirement")
        return self


class ItemUpdateIn(_In):
    """`PATCH _C/modules/{mid}/items/{iid}`: the target and kind never change (delete and add instead); `url` only on
    a `url` item (service). `title_override: null` clears the override."""
    title_override: Optional[ModuleTitle] = None
    indent: Optional[int] = Field(default=None, ge=0, le=ids.INDENT_MAX)
    published: Optional[bool] = None
    url: Optional[str] = Field(default=None, min_length=1, max_length=ids.URL_MAX)

    @model_validator(mode="after")
    def _not_null(self):
        for f in ("indent", "published", "url"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class ItemMoveIn(_In):
    """`PUT .../items/{iid}/move`: within or across modules of the same course; positions are re-densed."""
    module_id: uuid.UUID
    position: int = Field(ge=1)


class DoneIn(_In):
    """`POST .../items/{iid}/done`: the student's own checkbox (`marked_done` / `unmarked_done`)."""
    done: bool


# --------------------------------------------------------------------------- shared small outputs

class WarningOut(BaseModel):
    """A computed staff-outline warning (5.2); never stored, never in a student payload."""
    code: WarningCode
    module_id: Optional[uuid.UUID] = None
    item_id: Optional[uuid.UUID] = None


class LockReasonOut(BaseModel):
    """One reason a module or item is locked (6.5): `unlock_at` {at}, `prerequisite` {module_id, title},
    `sequential` {item_id, title}. Titles of published modules/items only."""
    kind: LockReasonKind
    at: Optional[datetime] = None
    module_id: Optional[uuid.UUID] = None
    item_id: Optional[uuid.UUID] = None
    title: Optional[dict] = None


class ModuleLockedDetails(BaseModel):
    """`details` of 423 `module_locked` (6.5)."""
    module_id: uuid.UUID
    module_title: dict
    reasons: list[LockReasonOut] = []


# --------------------------------------------------------------------------- staff outputs

class RequirementStaffOut(BaseModel):
    type: RequirementType
    threshold: Optional[float] = None


class ItemTargetOut(BaseModel):
    """What a staff item points to (kind detail): page language, assignment kind and quiz assessment id."""
    title: Optional[dict] = None
    published: bool = True
    deleted: bool = False
    language: Optional[str] = None            # page
    assignment_kind: Optional[str] = None     # assignment: none | text | file | quiz
    assessment_id: Optional[uuid.UUID] = None  # quiz assignment: opens /assessments/{id}/edit


class ItemStaffOut(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    kind: ItemKind
    position: int
    indent: int
    title_override: Optional[dict] = None
    published: bool
    page_id: Optional[uuid.UUID] = None
    file_id: Optional[uuid.UUID] = None
    assignment_id: Optional[uuid.UUID] = None
    url: Optional[str] = None
    requirement: Optional[RequirementStaffOut] = None
    target: Optional[ItemTargetOut] = None    # None for url and header
    warnings: list[WarningOut] = []


class ModuleStaffOut(BaseModel):
    id: uuid.UUID
    title: dict
    position: int
    published: bool
    unlock_at: Optional[datetime] = None
    sequential: bool
    completion_mode: CompletionMode
    rules_version: int
    prerequisites: list[uuid.UUID] = []
    items: list[ItemStaffOut] = []
    warnings: list[WarningOut] = []
    deleted_at: Optional[datetime] = None


class ModulesStaffOut(BaseModel):
    """`GET _C/modules` for teachers and assistants (no evaluation; `?deleted` may include deleted modules)."""
    modules: list[ModuleStaffOut] = []


class QuizItemOut(BaseModel):
    """`POST _C/modules/{mid}/quiz`: the new item, its quiz assignment and the assessment the 7c editor opens."""
    item: ItemStaffOut
    assignment: AssignmentStaffOut
    assessment_id: uuid.UUID


class ReapplyOut(BaseModel):
    cleared_students: int


# --------------------------------------------------------------------------- student outputs (allow-lists)

class RequirementStudentOut(BaseModel):
    type: RequirementType
    threshold: Optional[float] = None
    met: bool = False
    best_score_percent: Optional[float] = None


class ItemLinkOut(BaseModel):
    """Where tapping the item goes; exactly the fields of the item's kind are set (header: no link)."""
    page_id: Optional[uuid.UUID] = None
    file_id: Optional[uuid.UUID] = None
    assignment_id: Optional[uuid.UUID] = None
    assessment_id: Optional[uuid.UUID] = None
    assignment_kind: Optional[str] = None
    url: Optional[str] = None


class ItemStudentOut(BaseModel):
    id: uuid.UUID
    kind: ItemKind
    title: dict
    indent: int
    locked: bool
    requirement: Optional[RequirementStudentOut] = None
    link: Optional[ItemLinkOut] = None


class ModuleStudentOut(BaseModel):
    """`state` is None for an org admin (student shape, never evaluated). `lock_reasons` explain a `locked` state
    (same shape as the 423 details)."""
    id: uuid.UUID
    title: dict
    state: Optional[ModuleState] = None
    unlock_at: Optional[datetime] = None
    sequential: bool
    completion_mode: CompletionMode
    current_position: Optional[int] = None
    lock_reasons: list[LockReasonOut] = []
    items: list[ItemStudentOut] = []


class ItemRefOut(BaseModel):
    """"Up next": the first unlocked item with an unmet requirement (one primary action)."""
    module_id: uuid.UUID
    module_title: dict
    item_id: uuid.UUID
    kind: ItemKind
    title: dict
    link: Optional[ItemLinkOut] = None


class ModulesStudentOut(BaseModel):
    """`GET _C/modules` for a student (evaluates), an org admin (state None) and `GET _C/modules/progress/{eid}`;
    the facts routes return one `ModuleStudentOut`."""
    modules: list[ModuleStudentOut] = []
    up_next: Optional[ItemRefOut] = None


# --- Phase 8c S1 begin --- (PHASE_8C_DESIGN 7: the "Unsorted" group of the teacher Course page)
UnsortedKind = Literal["assignment", "page", "file"]


class UnsortedVariantOut(BaseModel):
    id: uuid.UUID
    language: str


class UnsortedItemOut(BaseModel):
    """A live assignment, page group or course file that no live item of a live module references. `title` is a
    LocalizedText for assignments and a plain string for pages (the listed variant's) and files."""
    kind: UnsortedKind
    id: uuid.UUID
    title: Union[dict, str]
    published: bool
    assignment_kind: Optional[str] = None        # assignment: none | text | file | quiz
    assessment_id: Optional[uuid.UUID] = None    # quiz assignment
    language: Optional[str] = None               # page: the listed variant's language
    translation_group_id: Optional[uuid.UUID] = None
    variants: Optional[list[UnsortedVariantOut]] = None  # page: every live variant of the group
    folder: Optional[str] = None                 # file
    updated_at: Optional[datetime] = None


class UnsortedPageOut(BaseModel):
    items: list[UnsortedItemOut] = []
    next_cursor: Optional[str] = None
    total: int = 0


class UnsortedOut(BaseModel):
    """`GET _C/modules/unsorted`: one page per kind; with `?kind=` only that kind is set (the others are null)."""
    assignments: Optional[UnsortedPageOut] = None
    pages: Optional[UnsortedPageOut] = None
    files: Optional[UnsortedPageOut] = None
# --- Phase 8c S1 end ---
