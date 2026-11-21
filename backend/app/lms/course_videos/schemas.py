"""Lesson videos API shapes (docs/phases/LESSON_VIDEOS.md V2, V3). Upload is multipart (`file`, optional `title`) and
captions a raw `text/vtt` body, so neither has a JSON input model. Outputs never carry asset ids or storage keys."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.lms.course_videos import ids


class VideoUpdateIn(BaseModel):
    """`PATCH /courses/{c}/videos/{v}`: rename."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=ids.TITLE_MAX)


class VideoOut(BaseModel):
    """Staff view of one video (V2)."""
    id: uuid.UUID
    title: str
    size_bytes: int
    sha256: str
    duration_s: int
    width: int
    height: int
    has_captions: bool
    created_at: datetime


class VideoPageOut(BaseModel):
    items: list[VideoOut] = []
    next_cursor: Optional[str] = None


class PlayOut(BaseModel):
    """`GET .../items/{i}/play` (V3): a short-lived URL (R2 presigned GET, or the dev stream with an HMAC token) and
    the captions route of the item (null without captions)."""
    url: str
    expires_at: datetime
    duration_s: int
    width: int
    height: int
    captions_url: Optional[str] = None
