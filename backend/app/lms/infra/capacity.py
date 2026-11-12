"""How many full 6,000-student exams still fit in the database (INFRA_PANEL_DESIGN 3, D-I5-4).

Per-row sizes come from the attempt tables (PostgreSQL: one `pg_class` statement, `pg_total_relation_size` and the
planner's row estimate, no count(*)); below 1,000 rows the measured sizes are dominated by index page minimums, so the
fallbacks measured on production 2026-11-09 are used and the result is marked `estimated`. The used and limit bytes come
from the Neon snapshot when there is one.

DB_STORAGE_REVIEW 7 (slice D1): without a Neon key the used size is the sum of every database on the server (Neon's
logical size counts them all), times 1.02; when the app role may not size the other databases, the current database plus
the fixed 23.5 MB of `postgres` and the two templates (`database_estimate`). The database has its own levels (50 / 70 /
85 %, and "no full exam fits" is at least a warning) because 80 % of 1 GiB is less than one exam day. `measure_storage`
stores the measurement in `platform_settings` for the admin overview (and the maintenance job of slice D2)."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.lms.access.models import PlatformSetting
from app.lms.core import clock
from app.lms.infra.costs import NEON_LAUNCH_STORAGE_USD_PER_GB_MONTH
from app.lms.infra.models import InfraSnapshot
from app.lms.infra.providers.neon import DEFAULT_STORAGE_LIMIT_BYTES

logger = logging.getLogger(__name__)

STUDENTS = 6_000
SECTIONS_PER_EXAM = 5
ITEMS_PER_EXAM = 150
MIN_ROWS = 1_000
RESERVE = 0.9  # 10 % kept for WAL / vacuum slack and the other tables
ITEM_FLOOR_B = 200
FALLBACK_ITEM_B = 241
FALLBACK_SECTION_B = 150  # DB_STORAGE_REVIEW 3: 72 B row + PK (was 400)
FALLBACK_ATTEMPT_B = 1_200  # DB_STORAGE_REVIEW 3: 758 B row + 10 indexes (was 1,500)
LOCAL_SIZE_FACTOR = 1.02  # the sum of pg_database_size is 1.3 % under Neon's logical size (production 2026-11-12)
SYSTEM_DATABASES_B = 23_500_000  # `postgres` + template0 + template1 on Neon, measured 2026-11-12
SQL_ALL_DATABASES = "SELECT sum(pg_database_size(datname)) FROM pg_database"
SQL_CURRENT_DATABASE = "SELECT pg_database_size(current_database())"

# Database levels (fractions of the limit); R2 and compute keep 80 / 95 % (`cards.py`)
DB_NOTICE = 0.5
DB_WARNING = 0.7
DB_CRITICAL = 0.85
LEVEL_ORDER = ("ok", "notice", "warning", "critical")

MEASUREMENT_KEY = "infra.db_storage"  # platform_settings row
MEASUREMENT_MAX_AGE = timedelta(minutes=60)

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


def _local_used_bytes(db: Session) -> tuple[Optional[int], str]:
    """(bytes or None, source). PostgreSQL: every database on the server; refused → the current one + the system ones."""
    source = "database"
    if db.get_bind().dialect.name == "postgresql":
        try:
            with db.begin_nested():  # a refused statement must not abort the request's transaction
                size = db.execute(text(SQL_ALL_DATABASES)).scalar()
        except DBAPIError as e:
            logger.info("infra capacity: sizing all databases refused (%s); estimating", type(e.orig).__name__)
            size = db.execute(text(SQL_CURRENT_DATABASE)).scalar()
            size, source = (int(size) + SYSTEM_DATABASES_B if size else None), "database_estimate"
    else:
        pages = db.execute(text("PRAGMA page_count")).scalar() or 0
        page_size = db.execute(text("PRAGMA page_size")).scalar() or 0
        size = pages * page_size
    return (int(int(size) * LOCAL_SIZE_FACTOR) if size else None), source


def db_level(percent: Optional[float], fits_n: Optional[int]) -> str:
    """The database's level: 50 / 70 / 85 % of the limit; no full exam left is at least `warning`, zero is `critical`."""
    out = "ok"
    if percent is not None:
        if percent >= 100 * DB_CRITICAL:
            out = "critical"
        elif percent >= 100 * DB_WARNING:
            out = "warning"
        elif percent >= 100 * DB_NOTICE:
            out = "notice"
    if fits_n is not None and fits_n < 1:
        out = max(out, "warning", key=LEVEL_ORDER.index)
    if fits_n == 0:
        out = "critical"
    return out


def percent_of(used_b: Optional[int], limit_b: Optional[int]) -> Optional[float]:
    return round(100.0 * used_b / limit_b, 1) if used_b is not None and limit_b else None


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


def compute(db: Session, neon_payload: Optional[dict] = None, size_provider: Optional[SizeProvider] = None,
            neon_fetched_at: Optional[datetime] = None) -> dict:
    sizes = (size_provider or default_size_provider(db))(db)
    item_b, est_i = _per_row(sizes, "attempt_items", FALLBACK_ITEM_B, ITEM_FLOOR_B)
    section_b, est_s = _per_row(sizes, "attempt_sections", FALLBACK_SECTION_B)
    attempt_b, est_a = _per_row(sizes, "attempts", FALLBACK_ATTEMPT_B)
    neon = neon_payload or {}
    used_b, source, measured = neon.get("storage_bytes"), "neon", neon_fetched_at
    if used_b is None:
        local, source = _local_used_bytes(db)
        used_b, measured = local or 0, clock.now()
    limit_b = neon.get("storage_limit_bytes") or DEFAULT_STORAGE_LIMIT_BYTES
    exam_b = exam_bytes(attempt_b, section_b, item_b)
    n = fits(limit_b, used_b, exam_b)
    percent = percent_of(used_b, limit_b)
    return {
        "fits": n,
        "students": STUDENTS,
        "exam_bytes": exam_b,
        "used_bytes": used_b,
        "limit_bytes": limit_b,
        "used_source": source,
        "percent": percent,
        "level": db_level(percent, n),
        "measured_at": measured,
        "estimated": est_i or est_s or est_a,
        "history_seconds": neon.get("history_seconds"),
        "branches": neon.get("branches"),
        "branches_limit": neon.get("branches_limit"),
        "upgrade_storage_usd_per_gb_month": NEON_LAUNCH_STORAGE_USD_PER_GB_MONTH,
        "per_row_bytes": {"attempt": attempt_b, "section": section_b, "item": item_b},
    }


# ------------------------------------------------------------------------------------- stored measurement (overview)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def neon_snapshot(db: Session) -> tuple[Optional[dict], Optional[datetime]]:
    """The stored Neon payload and its time (None when never fetched). A stored row only: no provider call."""
    row = db.execute(select(InfraSnapshot.payload, InfraSnapshot.fetched_at)
                     .where(InfraSnapshot.provider == "neon")).first()
    if row is None or row.fetched_at is None:
        return None, None
    return (row.payload or None), _aware(row.fetched_at)


def store(db: Session, cap: dict) -> dict:
    """Upsert the measurement row (the caller commits). Returns the stored value."""
    when = _aware(cap.get("measured_at")) or clock.now()
    value = {"measured_at": when.isoformat(), **{k: cap.get(k) for k in (
        "used_bytes", "limit_bytes", "used_source", "percent", "fits", "exam_bytes", "level")}}
    t = PlatformSetting.__table__
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    now = clock.now()
    stmt = insert(t).values(key=MEASUREMENT_KEY, value=value, updated_at=now, updated_by_id=None)
    db.execute(stmt.on_conflict_do_update(index_elements=[t.c.key],
                                          set_={"value": value, "updated_at": now, "updated_by_id": None}))
    return value


def measure_storage(db: Session) -> dict:
    """Measure (the stored Neon figure wins when there is one) and store; the caller commits."""
    payload, fetched_at = neon_snapshot(db)
    return store(db, compute(db, payload, neon_fetched_at=fetched_at))


def stored_measurement(db: Session) -> Optional[dict]:
    value = db.execute(select(PlatformSetting.value).where(PlatformSetting.key == MEASUREMENT_KEY)).scalar()
    return value if isinstance(value, dict) else None


def measured_at(value: dict) -> Optional[datetime]:
    try:
        return _aware(datetime.fromisoformat(value["measured_at"]))
    except (KeyError, TypeError, ValueError):
        return None
