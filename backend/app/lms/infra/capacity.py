"""How many full 6,000-student exams still fit in the database (INFRA_PANEL_DESIGN 3, D-I5-4).

Per-row sizes come from the attempt tables (PostgreSQL: one `pg_class` statement, `pg_total_relation_size` and the
planner's row estimate, no count(*)); below 1,000 rows the measured sizes are dominated by index page minimums, so the
fallbacks measured on production 2026-11-09 are used and the result is marked `estimated`. The used and limit bytes come
from the Neon snapshot when there is one."""
from __future__ import annotations

import math
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.lms.infra.providers.neon import DEFAULT_STORAGE_LIMIT_BYTES

STUDENTS = 6_000
SECTIONS_PER_EXAM = 5
ITEMS_PER_EXAM = 150
MIN_ROWS = 1_000
RESERVE = 0.9  # 10 % kept for WAL / vacuum slack and the other tables
ITEM_FLOOR_B = 200
FALLBACK_ITEM_B = 241
FALLBACK_SECTION_B = 400
FALLBACK_ATTEMPT_B = 1_500
LOCAL_SIZE_FACTOR = 1.3  # pg_database_size understates Neon's logical size

TABLES = ("attempts", "attempt_sections", "attempt_items")
# {table: (total bytes or None, rows)}
SizeProvider = Callable[[Session], dict[str, tuple[Optional[int], int]]]


def _pg_sizes(db: Session) -> dict[str, tuple[Optional[int], int]]:
    rows = db.execute(text(
        "SELECT c.relname, pg_total_relation_size(c.oid), c.reltuples FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = current_schema() AND c.relkind = 'r' "
        "AND c.relname IN ('attempts', 'attempt_sections', 'attempt_items')")).all()
    return {name: (int(size), max(0, int(tuples))) for name, size, tuples in rows}


def _sqlite_sizes(db: Session) -> dict[str, tuple[Optional[int], int]]:
    """SQLite (dev, tests): no per-table size; the row counts only, so the fallbacks apply."""
    return {t: (None, int(db.execute(text(f"SELECT count(*) FROM {t}")).scalar() or 0)) for t in TABLES}


def default_size_provider(db: Session) -> SizeProvider:
    return _pg_sizes if db.get_bind().dialect.name == "postgresql" else _sqlite_sizes


def _local_used_bytes(db: Session) -> Optional[int]:
    if db.get_bind().dialect.name == "postgresql":
        size = db.execute(text("SELECT pg_database_size(current_database())")).scalar()
    else:
        pages = db.execute(text("PRAGMA page_count")).scalar() or 0
        page_size = db.execute(text("PRAGMA page_size")).scalar() or 0
        size = pages * page_size
    return int(size * LOCAL_SIZE_FACTOR) if size else None


def _per_row(sizes: dict, table: str, fallback: int, floor: int = 0) -> tuple[int, bool]:
    total, rows = sizes.get(table, (None, 0))
    if total is None or rows < MIN_ROWS:
        return fallback, True
    return max(floor, math.ceil(total / max(rows, 1))), False


def exam_bytes(attempt_b: int, section_b: int, item_b: int) -> int:
    return STUDENTS * (attempt_b + SECTIONS_PER_EXAM * section_b + ITEMS_PER_EXAM * item_b)


def fits(limit_b: int, used_b: int, exam_b: int) -> int:
    headroom = max(0, limit_b - used_b)
    return max(0, math.floor(RESERVE * headroom / exam_b)) if exam_b > 0 else 0


def compute(db: Session, neon_payload: Optional[dict] = None, size_provider: Optional[SizeProvider] = None) -> dict:
    sizes = (size_provider or default_size_provider(db))(db)
    item_b, est_i = _per_row(sizes, "attempt_items", FALLBACK_ITEM_B, ITEM_FLOOR_B)
    section_b, est_s = _per_row(sizes, "attempt_sections", FALLBACK_SECTION_B)
    attempt_b, est_a = _per_row(sizes, "attempts", FALLBACK_ATTEMPT_B)
    neon = neon_payload or {}
    used_b, source = neon.get("storage_bytes"), "neon"
    if used_b is None:
        used_b, source = _local_used_bytes(db) or 0, "database"
    limit_b = neon.get("storage_limit_bytes") or DEFAULT_STORAGE_LIMIT_BYTES
    exam_b = exam_bytes(attempt_b, section_b, item_b)
    return {
        "fits": fits(limit_b, used_b, exam_b),
        "students": STUDENTS,
        "exam_bytes": exam_b,
        "used_bytes": used_b,
        "limit_bytes": limit_b,
        "used_source": source,
        "estimated": est_i or est_s or est_a,
        "history_seconds": neon.get("history_seconds"),
        "per_row_bytes": {"attempt": attempt_b, "section": section_b, "item": item_b},
    }
