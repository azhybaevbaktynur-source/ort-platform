"""Refuse to run tests against the developer's data (backend/test.db, backend/data/) or a remote database.

The test fixtures delete questions, attempts and LMS rows, so a run against the dev database or Neon wipes it.
`problems()` is pure (unit-tested in tests/test_dev_data_guard.py); tests/conftest.py calls it before the app is
imported and stops the run when it returns anything."""
import os
from pathlib import Path
from typing import List, Mapping, Optional
from urllib.parse import urlsplit

BACKEND_DIR = Path(__file__).resolve().parent.parent
LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}
TEST_DB_URL_VARS = ("LMS_PG_TEST_DATABASE_URL", "ALEMBIC_TEST_DATABASE_URL")

HOW_TO = (
    'run with a scratch database and upload folder, e.g. DATABASE_URL="sqlite:////tmp/agy_t/test.db" '
    'LOCAL_UPLOAD_DIR="/tmp/agy_t/up" (Postgres test URLs must point at localhost)'
)


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _db_problem(name: str, url: str, cwd: Path, backend_dir: Path) -> Optional[str]:
    if url.startswith("sqlite"):
        raw = url.split(":///", 1)[1] if ":///" in url else ""
        if raw in ("", ":memory:") or raw.startswith(":memory:"):
            return None
        path = Path(raw)
        path = (path if path.is_absolute() else cwd / path).resolve()
        if _inside(path, backend_dir):
            return f"{name} points at a SQLite file inside backend/ ({path.name}): that is developer data"
        return None
    host = (urlsplit(url).hostname or "").lower()
    if host not in LOCAL_HOSTS:
        return f"{name} points at a non-local database host ({host}): tests delete rows"
    return None


def problems(env: Mapping[str, str], effective: Mapping[str, str], cwd: Path,
             backend_dir: Path = BACKEND_DIR) -> List[str]:
    """`env`: the process environment; `effective`: the settings values after backend/.env is applied."""
    out: List[str] = []
    dev_data = (backend_dir / "data").resolve()
    if not env.get("DATABASE_URL"):
        out.append("DATABASE_URL is not set in the environment (backend/.env or the ./test.db default would be used)")
    else:
        p = _db_problem("DATABASE_URL", env["DATABASE_URL"], cwd, backend_dir.resolve())
        if p:
            out.append(p)
    for name in TEST_DB_URL_VARS:
        if env.get(name):
            p = _db_problem(name, env[name], cwd, backend_dir.resolve())
            if p:
                out.append(p)
    if not env.get("LOCAL_UPLOAD_DIR"):
        out.append("LOCAL_UPLOAD_DIR is not set in the environment (uploads would go to backend/data/uploads)")
    for name in ("LOCAL_UPLOAD_DIR", "LMS_LOCAL_STORAGE_DIR"):
        value = effective.get(name) or ""
        if value:
            path = Path(value)
            path = (path if path.is_absolute() else cwd / path).resolve()
            if _inside(path, dev_data):
                out.append(f"{name} is inside backend/data/: that is developer data")
    return out


def check_or_exit(effective: Mapping[str, str]) -> None:
    found = problems(os.environ, effective, Path.cwd())
    if found:
        import pytest

        pytest.exit("Refusing to run tests: " + "; ".join(found) + ". " + HOW_TO, returncode=4)
