"""Portable SQL helpers for the statistics queries."""
from __future__ import annotations

from sqlalchemy import Float, cast, func, text


def seconds_between(dialect_name: str, later, earlier):
    """Seconds from `earlier` to `later` (floats). PostgreSQL EXTRACT(EPOCH), SQLite julianday."""
    if dialect_name == "postgresql":
        return func.extract("epoch", later - earlier)
    return (func.julianday(later) - func.julianday(earlier)) * 86400.0


def set_statement_timeout(db, seconds: int) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text(f"SET LOCAL statement_timeout = '{int(seconds)}s'"))


def fl(col):
    return cast(col, Float)
