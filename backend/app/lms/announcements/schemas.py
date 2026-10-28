"""Announcements API shapes (PHASE_8A_DESIGN 7.2, 5.4). S1 defines the shapes; S3 adds the service validation
(body length 413 `payload_too_large` above `ANNOUNCEMENT_BODY_MAX`, stale `rev` 409 `page_conflict`, publish once 409
`already_published`) and builds the outputs.

Student models are allow-lists: no `body_md`, no `rev`, no drafts, no author id. `AnnouncementHomeOut` is the
`/me/home` strip shape (design 5.4): never a body."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.lms.announcements import ids


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnnouncementCreateIn(_In):
    """`POST _C/announcements`: a draft unless `publish` (then `published_at = now`)."""
    title: str = Field(min_length=1, max_length=ids.ANNOUNCEMENT_TITLE_MAX)
    body_md: str = ""
    pinned: bool = False
    publish: bool = False


class AnnouncementUpdateIn(_In):
    """`PATCH _C/announcements/{aid}`: editing a published announcement keeps its `published_at`."""
    rev: int = Field(ge=1)
    title: Optional[str] = Field(default=None, min_length=1, max_length=ids.ANNOUNCEMENT_TITLE_MAX)
    body_md: Optional[str] = None
    pinned: Optional[bool] = None

    @model_validator(mode="after")
    def _not_null(self):
        for f in ("title", "body_md", "pinned"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class AnnouncementStaffOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    body_md: str
    body_html: str
    pinned: bool
    published_at: Optional[datetime] = None
    rev: int
    author_name: str
    created_at: datetime
    updated_at: datetime


class AnnouncementStudentOut(BaseModel):
    id: uuid.UUID
    title: str
    body_html: str
    pinned: bool
    published_at: datetime
    author_name: str


class AnnouncementHomeOut(BaseModel):
    """One row of the `/me/home` announcements strip (latest three across the student's active courses)."""
    id: uuid.UUID
    course_id: uuid.UUID
    course_title: dict
    title: str
    published_at: datetime
