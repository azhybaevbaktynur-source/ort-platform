"""Restore drill (docs/runbooks/RESTORE.md, PHASE_11_DESIGN 7).

Run it against a Neon branch made at a past timestamp. It checks four things and prints no row contents and never
prints the database URL:
  1. `alembic current` equals the code's head revision.
  2. Row counts of the key tables.
  3. A student read through a local `uvicorn` pointed at the branch (HTTP status only).
  4. Time taken.

    DRILL_DATABASE_URL='<branch url>' backend/venv/bin/python scripts/restore_drill.py [--skip-head] [--port 8188]

`--skip-head` is for a dev database made by create_all (no alembic_version table); never use it on a restored branch.
Exit code 0 only if every check passed. The script only reads the database.
"""
from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
# Never load backend/.env (live keys): work from outside backend/, with a throwaway key shared with the local server.
WORK_DIR = tempfile.mkdtemp(prefix="restore_drill_")
os.chdir(WORK_DIR)
os.environ["SECRET_KEY"] = secrets.token_hex(32)

KEY_TABLES = [
    "users", "organizations", "courses", "enrollments", "assessments", "attempts", "attempt_items",
    "grade_events", "assets", "bank_questions", "question_versions",
]


def check_head(engine) -> tuple[bool, str]:
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current == head, f"alembic current={current} head={head}"


def count_rows(engine) -> list[tuple[str, int | None]]:
    from sqlalchemy import inspect, text

    existing = set(inspect(engine).get_table_names())
    out: list[tuple[str, int | None]] = []
    with engine.connect() as conn:
        for table in KEY_TABLES:
            out.append((table, conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() if table in existing else None))
    return out


def pick_student(engine):
    """(id, token_version) of one active, non-test student with an active enrollment. Nothing else is read."""
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT u.id, u.token_version FROM users u JOIN enrollments e ON e.user_id = u.id "
            "WHERE e.role = 'student' AND e.state = 'active' AND e.is_test_student = :f AND u.disabled_at IS NULL "
            "AND u.is_test_student = :f ORDER BY u.id LIMIT 1"), {"f": False}).first()
    return (row[0], row[1] or 0) if row else None


def student_read(url: str, student: tuple[str, int], port: int) -> tuple[bool, str]:
    from app.core.security import create_access_token

    env = {**os.environ, "DATABASE_URL": url, "ENVIRONMENT": "development", "LMS_STORAGE_DRIVER": "db", "PYTHONPATH": str(BACKEND)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "critical"],
        cwd=WORK_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/health", timeout=3).read()
                break
            except Exception:
                time.sleep(1)
        else:
            return False, "local server did not start in 60 s"
        token = create_access_token({"sub": student[0], "tv": student[1]})
        req = urllib.request.Request(base + "/api/v1/me/home", headers={"Authorization": f"Bearer {token}"})
        try:
            status = urllib.request.urlopen(req, timeout=30).status
        except urllib.error.HTTPError as exc:
            status = exc.code
        return status == 200, f"GET /me/home as one student: HTTP {status}"
    finally:
        proc.terminate()
        proc.wait(timeout=15)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-head", action="store_true")
    parser.add_argument("--port", type=int, default=8188)
    args = parser.parse_args()
    url = os.environ.get("DRILL_DATABASE_URL", "")
    if not url:
        print("Set DRILL_DATABASE_URL (the restored branch).")
        return 2
    from sqlalchemy import create_engine

    started = time.time()
    engine = create_engine(url)
    ok = True
    if args.skip_head:
        print("head check: skipped")
    else:
        good, msg = check_head(engine)
        ok &= good
        print(("OK   " if good else "FAIL ") + msg)
    for table, n in count_rows(engine):
        print(f"{'OK   ' if n is not None else 'FAIL '}rows {table}: {n if n is not None else 'table missing'}")
        ok &= n is not None
    student = pick_student(engine)
    if student is None:
        print("FAIL no active student found to read as")
        ok = False
    else:
        good, msg = student_read(url, student, args.port)
        ok &= good
        print(("OK   " if good else "FAIL ") + msg)
    print(f"time taken: {time.time() - started:.1f} s")
    print("RESULT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
