"""Accommodation and override DTOs (PHASE_7A_DESIGN 2.4, 2.5, 4.4). Staff only: `note` never reaches a student
payload (students see only their effective dates and attempts, through the existing student routes)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.lms.enrollments.schemas import UserBrief


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccommodationIn(_In):
    extra_time_percent: int = Field(default=0, ge=0, le=300)
    extra_time_s: int = Field(default=0, ge=0, le=86400)
    extra_attempts: int = Field(default=0, ge=0, le=100)
    note: Optional[str] = Field(default=None, max_length=500)


class AccommodationOut(BaseModel):
    enrollment_id: uuid.UUID
    extra_time_percent: int
    extra_time_s: int
    extra_attempts: int
    note: Optional[str] = None
    updated_at: Optional[datetime] = None
    # Q1 switch (effective.APPLY_EXTRA_TIME_TO_PRESET_EXAMS): False = extra time is stored but ORT exams ignore it
    preset_exams_get_extra_time: bool


class AccommodationRowOut(BaseModel):
    """One roster row of `GET /courses/{id}/accommodations`: an active student and their accommodation (or none)."""
    enrollment_id: uuid.UUID
    user: UserBrief
    accommodation: Optional[AccommodationOut] = None


class OverrideIn(_In):
    """Full replace; NULL = no override for that field (falls back to the accommodation, then the assignment)."""
    due_at: Optional[datetime] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    extra_time_percent: Optional[int] = Field(default=None, ge=0, le=300)
    extra_time_s: Optional[int] = Field(default=None, ge=0, le=86400)
    extra_attempts: Optional[int] = Field(default=None, ge=0, le=100)
    note: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _v(self):
        if (self.available_from is not None and self.available_until is not None
                and self.available_until <= self.available_from):
            raise ValueError("available_until must be after available_from")
        return self


class OverrideOut(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    enrollment_id: uuid.UUID
    user: UserBrief
    due_at: Optional[datetime] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    extra_time_percent: Optional[int] = None
    extra_time_s: Optional[int] = None
    extra_attempts: Optional[int] = None
    note: Optional[str] = None
    updated_at: Optional[datetime] = None
    preset_exams_get_extra_time: bool
