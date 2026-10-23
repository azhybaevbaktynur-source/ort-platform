import os

# Environment variables win over backend/.env: never send real email or run in production mode from tests
os.environ.setdefault("ENVIRONMENT", "development")
# Pin DEBUG off whatever backend/.env says: tests must see real 401s
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("EMAIL_PROVIDER", "console")
# backend/.env may hold real R2 credentials and LMS_STORAGE_DRIVER=r2: tests never talk to the real bucket
# (driver tests monkeypatch settings or stub boto3)
os.environ["LMS_STORAGE_DRIVER"] = "db"
for _r2_var in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_BASE_URL", "R2_PRIVATE_BUCKET"):
    os.environ[_r2_var] = ""

from app.core.config import settings as _settings
from tests.dev_data_guard import check_or_exit

# Never run against backend/test.db, backend/data/ or a remote database: the fixtures below delete rows
check_or_exit({"LOCAL_UPLOAD_DIR": _settings.LOCAL_UPLOAD_DIR, "LMS_LOCAL_STORAGE_DIR": _settings.LMS_LOCAL_STORAGE_DIR})

from pathlib import Path

import pytest

from app.db.init_db import init_db
from tests.auth_helpers import ensure_test_accounts


@pytest.fixture(autouse=True)
def reset_db():
    """Make sure the SQL schema exists and the two test accounts are present before each test."""
    init_db()
    ensure_test_accounts()
    yield


_LMS_TESTS_DIR = Path(__file__).resolve().parent / "lms"


@pytest.fixture(autouse=True)
def clean_lms_tables(request, reset_db):
    """LMS tests (tests/lms/**) start from a clean LMS state (`tests.lms.isolation.reset_lms_state`).

    Defined here, not in tests/lms/conftest.py: with interleaved command-line paths
    (`tests/lms/a.py tests/b.py tests/lms/c.py`) pytest creates a second `tests/lms` package node that does not
    see the fixtures of the already-imported tests/lms conftest, so `c.py` used to run without this fixture
    (no table cleanup, no system grading schemes after a drop/create, stale version cache)."""
    if _LMS_TESTS_DIR in Path(str(request.node.path)).resolve().parents:
        from tests.lms.isolation import reset_lms_state

        reset_lms_state()
    yield
