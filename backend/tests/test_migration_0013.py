"""Migration 0013 (Phase 8b template sandbox; PHASE_8B_DESIGN 2) on the 0012 fixture DB.

Fixture: tests/test_migration_0012.py migrated through 0012 (the two ORT courses, a general course with a draft quiz
and its assignment, grades). After 0013 every existing course reads `sandbox_for_template_id IS NULL` (the ORT
courses included); the UNIQUE (one sandbox per template), the FK to exam_templates and its ON DELETE SET NULL hold.
Down/up is lossless: a sandbox course stays an ordinary course row without the column.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0008 import ORT_KY, ORT_RU, OTHER_COURSE, _uid
from tests.test_migration_0009 import T0, grade_rows, totals
from tests.test_migration_0012 import REV as PREV, _migrate as _migrate_0012

REV = "0013_phase8b_template_sandbox"
COL = "sandbox_for_template_id"
FK = "fk_courses_sandbox_for_template_id_exam_templates"
UQ = "uq_courses_sandbox_for_template_id"


def _upgrade(cfg, conn, rev):
    from alembic import command

    command.upgrade(cfg, rev)
    conn.commit()


def _courses(conn) -> dict:
    """Identity of every course row (must not move across 0013 up/down)."""
    return {str(uuid.UUID(str(r[0]))): (r[1], r[2], r[3], r[4]) for r in conn.execute(text(
        "SELECT id, status, default_language, template_key, home_kind FROM courses ORDER BY id"))}


def _check_null(conn, courses_before: dict) -> None:
    assert _courses(conn) == courses_before
    rows = conn.execute(text(f"SELECT id, {COL} FROM courses")).all()
    assert rows and all(r[1] is None for r in rows)
    ids = {str(uuid.UUID(str(r[0]))) for r in rows}
    assert {str(ORT_KY), str(ORT_RU), str(OTHER_COURSE)} <= ids
    insp = inspect(conn)
    cols = {c["name"]: c for c in insp.get_columns("courses")}
    assert cols[COL]["nullable"] is True
    assert FK in {fk["name"] for fk in insp.get_foreign_keys("courses")}
    uniques = {u["name"] for u in insp.get_unique_constraints("courses")}
    uniques |= {i["name"] for i in insp.get_indexes("courses") if i.get("unique")}
    assert UQ in uniques


def _migrate(url):
    engine, grades, _ = _migrate_0012(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        courses = _courses(conn)
        _upgrade(cfg, conn, REV)
        _check_null(conn, courses)
        assert (grade_rows(conn), totals(conn)) == grades
    return engine, grades, courses


def _template(conn) -> str:
    tid = _uid(conn, uuid.uuid4())
    conn.execute(text(
        "INSERT INTO exam_templates (id, created_at, updated_at, owner_scope, title, status, locked, draft_rev) "
        "VALUES (:id, :t, :t, 'platform', :title, 'draft', false, 1)"),
        {"id": tid, "t": T0, "title": json.dumps({"en": "Sandbox"})})
    return tid


def _set(conn, course, value) -> None:
    conn.execute(text(f"UPDATE courses SET {COL} = :v WHERE id = :c"), {"v": value, "c": _uid(conn, course)})


def _sandbox_of(conn, course):
    v = conn.execute(text(f"SELECT {COL} FROM courses WHERE id = :c"), {"c": _uid(conn, course)}).scalar()
    return None if v is None else str(uuid.UUID(str(v)))


def _rejects(conn, fn) -> None:
    with pytest.raises(IntegrityError):
        fn()
        conn.commit()
    conn.rollback()


def _fk_on(conn) -> None:
    if conn.dialect.name == "sqlite":
        conn.execute(text("PRAGMA foreign_keys = ON"))


def _constraints(conn):
    """One sandbox per template (UNIQUE), the FK to exam_templates, ON DELETE SET NULL; NULLs never collide."""
    t1, t2 = _template(conn), _template(conn)
    _set(conn, OTHER_COURSE, t1)
    conn.commit()
    assert _sandbox_of(conn, OTHER_COURSE) == str(uuid.UUID(str(t1)))
    assert _sandbox_of(conn, ORT_KY) is None and _sandbox_of(conn, ORT_RU) is None  # many NULLs are fine
    _rejects(conn, lambda: _set(conn, ORT_RU, t1))                       # second sandbox of the same template
    _rejects(conn, lambda: _set(conn, ORT_RU, _uid(conn, uuid.uuid4())))  # unknown template (FK)
    _set(conn, ORT_RU, t2)
    conn.commit()
    _set(conn, ORT_RU, None)
    conn.commit()
    conn.execute(text("DELETE FROM exam_templates WHERE id = :t"), {"t": t1})
    conn.commit()
    assert _sandbox_of(conn, OTHER_COURSE) is None                       # SET NULL: the course row stays
    assert conn.execute(text("SELECT count(*) FROM courses WHERE id = :c"),
                        {"c": _uid(conn, OTHER_COURSE)}).scalar() == 1


def test_0013_on_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    engine, _, _ = _migrate(url)
    with engine.connect() as conn:
        _fk_on(conn)
        _constraints(conn)
    engine.dispose()


def _up_down_up(url):
    from alembic import command

    engine, grades, courses = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _set(conn, OTHER_COURSE, _template(conn))  # a sandbox course becomes an ordinary course on the way down
        conn.commit()
        command.downgrade(cfg, PREV)
        conn.commit()
        insp = inspect(conn)
        assert COL not in {c["name"] for c in insp.get_columns("courses")}
        assert FK not in {fk["name"] for fk in insp.get_foreign_keys("courses")}
        assert _courses(conn) == courses
        assert (grade_rows(conn), totals(conn)) == grades
        _upgrade(cfg, conn, REV)
        _check_null(conn, courses)
        assert (grade_rows(conn), totals(conn)) == grades
    engine.dispose()


def test_0013_up_down_up_on_sqlite(tmp_path):
    _up_down_up(f"sqlite:///{tmp_path / 'udu.db'}")


def test_0013_on_fresh_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, "head")
        insp = inspect(conn)
        assert COL in {c["name"] for c in insp.get_columns("courses")}
        assert FK in {fk["name"] for fk in insp.get_foreign_keys("courses")}
    engine.dispose()


PG_URL = os.getenv("ALEMBIC_TEST_DATABASE_URL")


@pytest.fixture
def pg_engine():
    if not PG_URL:
        pytest.skip("ALEMBIC_TEST_DATABASE_URL not set")
    engine = create_engine(PG_URL)
    _wipe(engine)
    yield engine
    _wipe(engine)
    engine.dispose()


def _wipe(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def test_0013_on_pg(pg_engine):
    engine, _, _ = _migrate(PG_URL)
    with engine.connect() as conn:
        _constraints(conn)
    engine.dispose()


def test_0013_up_down_up_on_pg(pg_engine):
    _up_down_up(PG_URL)
