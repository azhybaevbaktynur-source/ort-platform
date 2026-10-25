"""Template API shapes (PHASE_6_DESIGN 5.3). Pure pydantic, safe to import from courses.schemas."""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CourseTemplateOut(BaseModel):
    """`CourseOut.template`; null for a general course."""
    key: str
    version: int
    locked: bool
    result_view: str
    passage_display: str
    section_keys: list[str]
    assessment_presets: list[str]
    importer_profiles: list[str]
    title_key: str


class TemplateBriefOut(BaseModel):
    key: str
    title_key: str


class PlatformCoursePatchIn(BaseModel):
    """PATCH /platform/courses/{id}: only `template_locked` for now (platform admin, audited)."""
    model_config = ConfigDict(extra="forbid")
    template_locked: bool
    reason: Optional[str] = Field(default=None, max_length=500)


class PlatformCourseTemplateOut(BaseModel):
    id: uuid.UUID
    template_key: Optional[str] = None
    template_version: Optional[int] = None
    template_locked: bool
    template: Optional[CourseTemplateOut] = None
