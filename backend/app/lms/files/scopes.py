"""SQL scopes for asset lists."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Select, select

from app.lms.files.models import Asset


def _like_escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def my_assets(user_id: str, q: Optional[str] = None) -> Select:
    stmt = select(Asset).where(Asset.owner_id == user_id, Asset.deleted_at.is_(None))
    if q:
        stmt = stmt.where(Asset.original_filename.ilike(f"%{_like_escape(q.strip())}%", escape="\\"))
    return stmt
