"""tests/dev_data_guard.py: tests refuse the developer database, backend/data/ and remote databases."""
import os
import subprocess
import sys
from pathlib import Path

from tests.dev_data_guard import BACKEND_DIR, problems

SCRATCH = {"DATABASE_URL": "sqlite:////tmp/agy_t/test.db", "LOCAL_UPLOAD_DIR": "/tmp/agy_t/up"}
SAFE_EFFECTIVE = {"LOCAL_UPLOAD_DIR": "/tmp/agy_t/up", "LMS_LOCAL_STORAGE_DIR": ""}


def _p(env, effective=SAFE_EFFECTIVE, cwd=BACKEND_DIR):
    return problems(env, effective, cwd, BACKEND_DIR)


def test_scratch_setup_passes():
    assert _p(SCRATCH) == []
    assert _p({**SCRATCH, "LMS_PG_TEST_DATABASE_URL": "postgresql+psycopg2://postgres@127.0.0.1:55432/x",
               "ALEMBIC_TEST_DATABASE_URL": "postgresql+psycopg2://postgres:postgres@localhost:5432/y"}) == []
    assert _p({**SCRATCH, "DATABASE_URL": "sqlite:///:memory:"}) == []


def test_dev_database_refused():
    for url in ("sqlite:///./test.db", "sqlite:///test.db", f"sqlite:///{BACKEND_DIR}/test.db"):
        found = _p({**SCRATCH, "DATABASE_URL": url})
        assert found and "backend/" in found[0], url
    # relative path from the repo root still resolves into backend/
    assert _p({**SCRATCH, "DATABASE_URL": "sqlite:///backend/test.db"}, cwd=BACKEND_DIR.parent)


def test_missing_env_refused():
    assert any("DATABASE_URL is not set" in p for p in _p({"LOCAL_UPLOAD_DIR": "/tmp/x"}))
    assert any("LOCAL_UPLOAD_DIR is not set" in p for p in _p({"DATABASE_URL": SCRATCH["DATABASE_URL"]}))


def test_remote_database_refused():
    neon = "postgresql://u:p@ep-cool-firefly.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    assert _p({**SCRATCH, "DATABASE_URL": neon})
    assert _p({**SCRATCH, "LMS_PG_TEST_DATABASE_URL": neon})
    assert _p({**SCRATCH, "ALEMBIC_TEST_DATABASE_URL": neon})


def test_dev_upload_dirs_refused():
    data = BACKEND_DIR / "data"
    assert _p(SCRATCH, {"LOCAL_UPLOAD_DIR": str(data / "uploads"), "LMS_LOCAL_STORAGE_DIR": ""})
    assert _p(SCRATCH, {"LOCAL_UPLOAD_DIR": "/tmp/up", "LMS_LOCAL_STORAGE_DIR": str(data / "lms")})
    assert _p(SCRATCH, {"LOCAL_UPLOAD_DIR": "data/uploads", "LMS_LOCAL_STORAGE_DIR": ""})


def test_pytest_run_inside_backend_stops_before_any_test(tmp_path):
    """End to end through conftest: a SQLite file inside backend/ makes pytest exit with code 4 and run nothing.
    Uses a throwaway name (not test.db) so a broken guard cannot touch the developer database."""
    probe = BACKEND_DIR / "guard_probe_never_created.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{probe}", "LOCAL_UPLOAD_DIR": str(tmp_path)}
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_scoring.py"],
                           cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120)
        assert r.returncode == 4, r.stdout[-2000:] + r.stderr[-2000:]
        assert "Refusing to run tests" in r.stdout + r.stderr
        assert not probe.exists()
    finally:
        if probe.exists():
            probe.unlink()
