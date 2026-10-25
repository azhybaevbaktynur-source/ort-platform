from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MeOut(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    locale: Optional[str] = None
    is_platform_admin: bool
    teacher_status: str
    can_create_courses: bool
    is_teacher: bool  # Phase 6 S8: approved, org teacher/admin, or course staff (UI area, not a permission)


class MePatchIn(BaseModel):
    locale: Literal["en", "ru", "ky"]


class TeacherRequestIn(BaseModel):
    message: Optional[str] = Field(default=None, max_length=2000)


class MyTeacherRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message: Optional[str] = None
    status: str
    reason: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None
