from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class MeAdminOrganizationOut(BaseModel):
    id: uuid.UUID
    name: str


class MeOut(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    locale: Optional[str] = None
    is_platform_admin: bool
    teacher_status: str
    can_create_courses: bool
    is_teacher: bool  # Phase 6 S8: approved, org teacher/admin, or course staff (UI area, not a permission)
    # UX rework 2: the header's areas come from this one answer, so the menu is the same on every page (UI, not permissions)
    admin_organizations: list[MeAdminOrganizationOut] = []
    is_guardian: bool = False
    # Owner feedback 2026-11-08 (item 2): an active student enrollment (Student view's test enrollments do not count)
    has_student_enrollments: bool = False


class MePatchIn(BaseModel):
    locale: Literal["en", "ru", "ky"]


_PHONE = re.compile(r"[0-9 +\-()]{5,32}")  # ASCII digits only: `\d` would also take other scripts' digits
_PHONE_MIN_DIGITS = 5
_MESSAGE_ALLOWED_CONTROLS = "\n\r\t"


def _is_control(char: str) -> bool:
    return unicodedata.category(char).startswith("C") or unicodedata.category(char) in ("Zl", "Zp")


class TeacherRequestIn(BaseModel):
    """The application form (docs/phases/ACCOUNTS.md B). Error messages never repeat the value."""
    model_config = ConfigDict(extra="forbid")

    applicant_name: str = Field(min_length=1, max_length=200)
    school: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=5, max_length=32)
    message: Optional[str] = Field(default=None, max_length=2000)
    age_confirmed: StrictBool = False
    policy_version_ids: Optional[list[str]] = Field(default=None, max_length=10)

    @field_validator("applicant_name", "school", "subject", "phone", "message", mode="before")
    @classmethod
    def _trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("applicant_name", "school", "subject")
    @classmethod
    def _one_clean_line(cls, value: str) -> str:
        if any(_is_control(c) for c in value):
            raise ValueError("control characters are not allowed")
        return value

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        if not _PHONE.fullmatch(value) or sum(c.isdigit() for c in value) < _PHONE_MIN_DIGITS:
            raise ValueError("not a phone number")
        return value

    @field_validator("message")
    @classmethod
    def _message(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        if any(_is_control(c) and c not in _MESSAGE_ALLOWED_CONTROLS for c in value):  # PostgreSQL refuses NUL as well
            raise ValueError("control characters are not allowed")
        return value


class MyTeacherRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message: Optional[str] = None
    status: str
    reason: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None
    applicant_name: Optional[str] = None
    school: Optional[str] = None
    subject: Optional[str] = None
    phone: Optional[str] = None
    reapply_available_at: Optional[datetime] = None  # rejected rows only
