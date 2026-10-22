from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.lms.files.models import Asset
from app.lms.files.storage import media_url


class AssetOut(BaseModel):
    id: uuid.UUID
    url: Optional[str] = None
    visibility: str
    mime: str
    bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    sha256: str
    original_filename: Optional[str] = None
    created_at: datetime
    deduplicated: bool = False


def asset_out(a: Asset, deduplicated: bool = False) -> AssetOut:
    return AssetOut(
        id=a.id, url=media_url(a.sha256) if a.visibility == "public" else None, visibility=a.visibility,
        mime=a.mime, bytes=a.bytes, width=a.width, height=a.height, sha256=a.sha256,
        original_filename=a.original_filename, created_at=a.created_at, deduplicated=deduplicated,
    )
