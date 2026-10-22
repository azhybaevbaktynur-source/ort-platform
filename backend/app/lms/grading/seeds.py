"""System grading schemes (design P4-6): fixed UUIDs, seeded idempotently at startup and in the test fixture.

`ort_main` / `ort_subject` v1 reproduce the old `ScoringService` exactly (design section 0); `percent` v1 and
`pass_fail` v1 (60 %) cover simple courses. Versions are immutable: changing a seeded scheme later means a new
system version (and a regrade on request), never an edit of these constants for an existing id.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.lms.core import clock
from app.lms.grading.models import GradingScheme, GradingSchemeVersion
from app.lms.grading.params import validate_params
from app.lms.grading.schemes import new_version_row

logger = logging.getLogger(__name__)


def _id(n: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-4000-8000-0000000004{n:02d}")


ORT_MAIN_SCHEME_ID, ORT_MAIN_V1_ID = _id(1), _id(2)
ORT_SUBJECT_SCHEME_ID, ORT_SUBJECT_V1_ID = _id(3), _id(4)
PERCENT_SCHEME_ID, PERCENT_V1_ID = _id(5), _id(6)
PASS_FAIL_SCHEME_ID, PASS_FAIL_V1_ID = _id(7), _id(8)

# Assessment presets -> system version set at creation (P4-6).
PRESET_SCHEME_VERSIONS: dict[str, uuid.UUID] = {"ort_main": ORT_MAIN_V1_ID, "ort_subject": ORT_SUBJECT_V1_ID}


def _ort(scale_max: int, mean: int, sd: int, thresholds: list) -> dict:
    return {
        "schema": 1, "scale_min": 60, "scale_max": scale_max,
        "segments": [
            {"from_ratio": 0, "to_ratio": 0.5, "from_value": 60, "to_value": mean, "exponent": 1.05},
            {"from_ratio": 0.5, "to_ratio": 1, "from_value": mean, "to_value": scale_max, "exponent": 0.95},
        ],
        "zero_raw": {"value": 0, "percentile": 0.0},
        "rounding": {"mode": "half_even", "decimals": 0},
        "percentile": {"mean": mean, "sd": sd, "min": 1.0, "max": 99.9, "decimals": 1},
        "thresholds": thresholds,
        "apply_to_sections": True,
    }


ORT_MAIN_PARAMS = _ort(245, 150, 30, [{"key": "golden_certificate", "min_value": 219}])
ORT_SUBJECT_PARAMS = _ort(150, 105, 20, [])
PERCENT_PARAMS = {"schema": 1, "rounding": {"mode": "half_up", "decimals": 2}}
PASS_FAIL_PARAMS = {"schema": 1, "pass_threshold_percent": 60, "rounding": {"mode": "half_up", "decimals": 2}}

# (scheme id, version id, key, type, title, params)
SYSTEM_SCHEMES = (
    (ORT_MAIN_SCHEME_ID, ORT_MAIN_V1_ID, "ort_main", "piecewise_curve",
     {"en": "ORT main test (60-245)", "ru": "ОРТ: основной тест (60-245)", "ky": "ЖРТ: негизги тест (60-245)"},
     ORT_MAIN_PARAMS),
    (ORT_SUBJECT_SCHEME_ID, ORT_SUBJECT_V1_ID, "ort_subject", "piecewise_curve",
     {"en": "ORT subject test (60-150)", "ru": "ОРТ: предметный тест (60-150)",
      "ky": "ЖРТ: предметтик тест (60-150)"},
     ORT_SUBJECT_PARAMS),
    (PERCENT_SCHEME_ID, PERCENT_V1_ID, "percent", "percent",
     {"en": "Percent", "ru": "Проценты", "ky": "Пайыз"}, PERCENT_PARAMS),
    (PASS_FAIL_SCHEME_ID, PASS_FAIL_V1_ID, "pass_fail", "pass_fail",
     {"en": "Pass / fail (60%)", "ru": "Зачёт / незачёт (60%)", "ky": "Өттү / өткөн жок (60%)"},
     PASS_FAIL_PARAMS),
)


def _insert(db: Session):
    return pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert


def ensure_system_schemes(db: Session) -> None:
    """Insert missing system schemes and their v1 (ON CONFLICT DO NOTHING: safe with several workers)."""
    have = set(db.execute(select(GradingSchemeVersion.id).where(
        GradingSchemeVersion.id.in_([s[1] for s in SYSTEM_SCHEMES]))).scalars())
    linked = set(db.execute(select(GradingScheme.id).where(
        GradingScheme.id.in_([s[0] for s in SYSTEM_SCHEMES]), GradingScheme.current_version_id.is_not(None))
    ).scalars())
    if len(have) == len(SYSTEM_SCHEMES) and len(linked) == len(SYSTEM_SCHEMES):
        return
    insert = _insert(db)
    now = clock.now()
    st, vt = GradingScheme.__table__, GradingSchemeVersion.__table__
    for scheme_id, version_id, key, type_, title, params in SYSTEM_SCHEMES:
        normalized = validate_params(type_, params)
        scheme = GradingScheme(id=scheme_id, owner_user_id=None, key=key, title=title, type=type_)
        db.execute(insert(st).values(
            id=scheme_id, owner_user_id=None, key=key, title=title, type=type_, last_version_no=1,
            created_at=now, updated_at=now,
        ).on_conflict_do_nothing())
        row = new_version_row(scheme, normalized, version_no=1, created_by_id=None, version_id=version_id)
        db.execute(insert(vt).values(
            id=row.id, scheme_id=scheme_id, version_no=1, type=type_, scale_min=row.scale_min,
            scale_max=row.scale_max, params=row.params, params_hash=row.params_hash, created_at=now,
            created_by_id=None,
        ).on_conflict_do_nothing())
        db.execute(update(st).where(st.c.id == scheme_id, st.c.current_version_id.is_(None))
                   .values(current_version_id=version_id))
    db.commit()
    logger.info("system grading schemes ensured")
