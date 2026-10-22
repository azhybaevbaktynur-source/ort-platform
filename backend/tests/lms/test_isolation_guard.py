"""Canary for the LMS isolation fixture: it must apply to every tests/lms module whatever the command-line order
(e.g. `pytest tests/lms/test_pg_concurrency_grading.py tests/test_migrations.py tests/lms/test_isolation_guard.py`
used to skip it for the last module, leaving the system grading schemes unseeded after a drop/create)."""
from sqlalchemy import func, select

from app.db import session as db_session
from app.lms.grading.models import GradingSchemeVersion
from app.lms.grading.seeds import SYSTEM_SCHEMES


def test_lms_isolation_fixture_applies(request):
    assert "clean_lms_tables" in request.fixturenames
    db = db_session.SessionLocal()
    try:
        n = db.scalar(select(func.count()).select_from(GradingSchemeVersion).where(
            GradingSchemeVersion.id.in_([s[1] for s in SYSTEM_SCHEMES])))
    finally:
        db.close()
    assert n == len(SYSTEM_SCHEMES)
