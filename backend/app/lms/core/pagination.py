"""Keyset (cursor) pagination."""
from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.lms.core.errors import ValidationFailed

T = TypeVar("T")


class PageOut(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: Optional[str] = None


@dataclass
class Page:
    items: list = field(default_factory=list)
    next_cursor: Optional[str] = None


def _default(o: Any):
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"unsupported cursor value: {type(o)}")


def encode_cursor(values: dict) -> str:
    raw = json.dumps(values, default=_default, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> dict:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except Exception:
        raise ValidationFailed("Invalid cursor", code="invalid_cursor")
    if not isinstance(data, dict):
        raise ValidationFailed("Invalid cursor", code="invalid_cursor")
    return data


def clamp_limit(limit: Optional[int], default: int = 25, maximum: int = 100) -> int:
    if limit is None:
        return default
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, maximum))


def _coerce(col, raw):
    """Convert a decoded JSON value back to the column's python type."""
    try:
        py = col.type.python_type
    except NotImplementedError:
        return raw
    if raw is None:
        return None
    bad = ValidationFailed("Invalid cursor", code="invalid_cursor")
    try:
        if py is uuid.UUID:
            if not isinstance(raw, str):
                raise bad
            return uuid.UUID(raw)
        if py is datetime:
            if not isinstance(raw, str):
                raise bad
            return datetime.fromisoformat(raw)
    except (ValueError, TypeError, AttributeError):
        raise bad
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
        raise bad
    if py is str and not isinstance(raw, str):
        raise bad
    if py is int and not isinstance(raw, int):
        raise bad
    return raw


def paginate(stmt, session: Session, *, sort_col, id_col, cursor: Optional[str] = None,
             limit: Optional[int] = None, descending: bool = True) -> Page:
    limit = clamp_limit(limit)
    if cursor:
        c = decode_cursor(cursor)
        if "s" not in c or "i" not in c:
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        s_val = _coerce(sort_col, c["s"])
        i_val = _coerce(id_col, c["i"])
        if descending:
            cond = or_(sort_col < s_val, and_(sort_col == s_val, id_col < i_val))
        else:
            cond = or_(sort_col > s_val, and_(sort_col == s_val, id_col > i_val))
        stmt = stmt.where(cond)
    if descending:
        stmt = stmt.order_by(sort_col.desc(), id_col.desc())
    else:
        stmt = stmt.order_by(sort_col.asc(), id_col.asc())
    rows = list(session.execute(stmt.limit(limit + 1)).scalars().all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor({
            "s": getattr(last, sort_col.key),
            "i": getattr(last, id_col.key),
        })
    return Page(items=rows, next_cursor=next_cursor)
