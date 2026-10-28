"""Pages API shapes (PHASE_8A_DESIGN 7.2, 5.1). S1 defines the shapes; S3 adds the service validation
(`language_not_in_course`, body length 413 `payload_too_large` above `PAGE_BODY_MAX`, stale `rev` 409
`page_conflict`, group in the course) and builds the outputs.

`body_md` is accepted without a schema cap so an oversize body gets the documented 413, not a generic 422 (the request
body itself is capped by `API_MAX_BODY_BYTES`). `body_html` is never accepted from a client. Student models are
allow-lists: no `body_md`, no `rev`, no unpublished variants, no author ids."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.lms.pages import ids

Lang = Literal["en", "ru", "ky"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- inputs

class PageCreateIn(_In):
    """`POST _C/pages`. `translation_group_id` adds a language variant to an existing page group of the course."""
    title: str = Field(min_length=1, max_length=ids.PAGE_TITLE_MAX)
    language: Lang
    body_md: str = ""
    published: bool = False
    translation_group_id: Optional[uuid.UUID] = None


class PageUpdateIn(_In):
    """`PATCH _C/pages/{pid}`: `rev` is the revision the editor started from (stale: 409 `page_conflict`)."""
    rev: int = Field(ge=1)
    title: Optional[str] = Field(default=None, min_length=1, max_length=ids.PAGE_TITLE_MAX)
    body_md: Optional[str] = None
    published: Optional[bool] = None

    @model_validator(mode="after")
    def _not_null(self):
        for f in ("title", "body_md", "published"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class PagePreviewIn(_In):
    """`POST _C/pages/preview` (rate-limited; never stored)."""
    body_md: str


class PagePreviewOut(BaseModel):
    body_html: str


# --------------------------------------------------------------------------- outputs

class PageVariantOut(BaseModel):
    """A sibling language variant of the same group (students: published ones only)."""
    id: uuid.UUID
    language: str
    title: str


class PageSummaryStaffOut(BaseModel):
    """Staff list row (`GET _C/pages`, cursor-paginated)."""
    id: uuid.UUID
    translation_group_id: uuid.UUID
    language: str
    title: str
    published: bool
    rev: int
    used_in_modules: int = 0
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class PageSummaryStudentOut(BaseModel):
    """Student list row: published, live pages only."""
    id: uuid.UUID
    translation_group_id: uuid.UUID
    language: str
    title: str


class PageStaffOut(BaseModel):
    """`GET/POST/PATCH _C/pages[/{pid}]` for staff: the source, the render and the edit revision."""
    id: uuid.UUID
    course_id: uuid.UUID
    translation_group_id: uuid.UUID
    language: str
    title: str
    body_md: str
    body_html: str
    published: bool
    rev: int
    variants: list[PageVariantOut] = []
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class PageStudentOut(BaseModel):
    """`GET _C/pages/{pid}` for a student (resolved variant, after the module gate) and org admin."""
    id: uuid.UUID
    translation_group_id: uuid.UUID
    language: str
    title: str
    body_html: str
    variants: list[PageVariantOut] = []
    updated_at: datetime
