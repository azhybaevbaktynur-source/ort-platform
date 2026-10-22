"""Migration 0005 data step (S2 backfill) on a throwaway SQLite file, plus the PG guard DDL kept identical to the
models' copy (S7). The PostgreSQL run of the same seed lives in tests/test_migrations.py."""
import importlib.util
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, text

from app.db.migrate import BACKEND_DIR, _config

REV = "0005_phase4_grading"
PREV = "0004_phase3_assessments"


def load_0005():
    path = BACKEND_DIR / "alembic" / "versions" / f"{REV}.py"
    spec = importlib.util.spec_from_file_location("mig_0005", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def seed_0004(conn) -> dict:
    """Minimal pre-Phase-4 rows (FK checks off: SQLite does not enforce them here; PG callers set
    session_replication_role = replica first): one assessment, attempts of four enrollments."""
    h = lambda: uuid.uuid4().hex  # noqa: E731
    course, assessment, version = h(), h(), h()
    e_counted, e_open, e_preview, e_void = h(), h(), h(), h()
    conn.execute(text(
        "INSERT INTO assessments (id, created_at, updated_at, course_id, title, languages, position, score_policy) "
        "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :c, '{\"en\": \"a\"}', '[\"en\"]', 1, 'latest')"),
        {"id": assessment, "c": course})
    rows = [  # (enrollment, attempt_no, status, preview)
        (e_counted, 1, "graded", False), (e_counted, 2, "needs_review", False), (e_open, 1, "in_progress", False),
        (e_preview, None, "graded", True), (e_void, 1, "void", False),
    ]
    for enr, no, status, preview in rows:
        conn.execute(text(
            "INSERT INTO attempts (id, created_at, updated_at, assessment_id, assessment_version_id, course_id, "
            "enrollment_id, user_id, language, started_at, item_count, points_possible, attempt_no, status, "
            "is_preview) VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :a, :v, :c, :e, :u, 'en', "
            "CURRENT_TIMESTAMP, 0, 10, :no, :st, :pv)"),
            {"id": h(), "a": assessment, "v": version, "c": course, "e": enr, "u": f"u_{enr[:8]}", "no": no,
             "st": status, "pv": preview})
    return {"assessment": assessment, "counted": e_counted}


def check_backfill(conn, seeded: dict) -> None:
    rows = conn.execute(text("SELECT enrollment_id, assessment_id, state, kept_policy, attempts_counted, "
                             "computed_at, version FROM submissions")).mappings().all()
    assert len(rows) == 1, rows
    r = rows[0]
    assert uuid.UUID(str(r["enrollment_id"])) == uuid.UUID(seeded["counted"])
    assert uuid.UUID(str(r["assessment_id"])) == uuid.UUID(seeded["assessment"])
    assert r["state"] == "graded" and r["kept_policy"] == "latest" and r["attempts_counted"] == 0
    assert r["version"] == 1 and str(r["computed_at"]).startswith("1970-01-01")  # stale placeholder


def test_0005_backfills_submissions_on_sqlite(tmp_path):
    from alembic import command

    url = f"sqlite:///{tmp_path / 'mig.db'}"
    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, PREV)
        conn.commit()
        seeded = seed_0004(conn)
        conn.commit()
        command.upgrade(cfg, REV)
        conn.commit()
        check_backfill(conn, seeded)
        assert "late_policy_changed_at" in {c["name"] for c in inspect(conn).get_columns("courses")}
        command.downgrade(cfg, PREV)
        conn.commit()
        assert "submissions" not in inspect(conn).get_table_names()
        command.upgrade(cfg, REV)
        conn.commit()
        check_backfill(conn, seeded)
    engine.dispose()


def test_guard_ddl_matches_models():
    from app.lms.grading.models import GUARD_FN_SQL, GUARD_TRIGGERS

    mig = load_0005()
    assert mig._GUARD_FN == GUARD_FN_SQL
    assert {t: (n, w, c) for n, t, w, c in mig._GUARD_TRIGGERS} == GUARD_TRIGGERS
    from app.lms.grading.submissions import NEVER_COMPUTED

    assert mig._NEVER_COMPUTED == NEVER_COMPUTED == datetime(1970, 1, 1, tzinfo=timezone.utc)
