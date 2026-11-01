from __future__ import annotations

import uuid

from pydantic import BaseModel


class StudentViewOut(BaseModel):
    access_token: str
    expires_in: int  # seconds
    course_id: uuid.UUID
