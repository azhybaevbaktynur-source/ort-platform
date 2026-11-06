"""Migration 0024 (F5a course lessons, COURSE_LESSONS_DESIGN 2) on the production-like fixture DB of 0013/0014,
migrated through 0023 with one module and one link item written at 0023.

After 0024: the existing module reads `access_tier = free`, the existing item `duration_s = null`; the CHECKs refuse a
tier outside free/paid and a duration outside 60..36000 (null allowed). Down/up: the downgrade drops both columns and
their CHECKs; the upgrade again yields the same.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0014 import _migrate
from tests.test_migration_0015 import _upgrade

REV = "0024_course_lessons"
PREV = "0023_person"
T0 = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


def _uid(conn, v) -> str:
    return str(v) if conn.dialect.name == "postgresql" else uuid.UUID(str(v)).hex


def _seed(conn) -> tuple[str, str]:
    """One module and one url item at 0023 (no new columns yet)."""
    course = conn.execute(text("SELECT id FROM courses ORDER BY id LIMIT 1")).scalar()
    mid, iid = _uid(conn, uuid.uuid4()), _uid(conn, uuid.uuid4())
    conn.execute(text("INSERT INTO course_modules (id, created_at, updated_at, course_id, title, position) "
                      "VALUES (:id, :t, :t, :c, :title, 1)"),
                 {"id": mid, "t": T0, "c": course, "title": json.dumps({"en": "Week 1"})})
    conn.execute(text("INSERT INTO module_items (id, created_at, updated_at, module_id, position, kind, url) "
                      "VALUES (:id, :t, :t, :m, 1, 'url', 'https://example.com/a')"),
                 {"id": iid, "t": T0, "m": mid})
    conn.commit()
    return mid, iid


def _check(conn, mid: str, iid: str) -> None:
    assert conn.execute(text("SELECT access_tier FROM course_modules WHERE id = :i"), {"i": mid}).scalar() == "free"
    assert conn.execute(text("SELECT duration_s FROM module_items WHERE id = :i"), {"i": iid}).scalar() is None
    for sql, params in (("UPDATE course_modules SET access_tier = :v WHERE id = :i", {"v": "gold", "i": mid}),
                        ("UPDATE course_modules SET access_tier = NULL WHERE id = :i", {"i": mid}),
                        ("UPDATE module_items SET duration_s = :v WHERE id = :i", {"v": 59, "i": iid}),
                        ("UPDATE module_items SET duration_s = :v WHERE id = :i", {"v": 36001, "i": iid})):
        with pytest.raises(IntegrityError):
            conn.execute(text(sql), params)
        conn.rollback()
    conn.execute(text("UPDATE course_modules SET access_tier = 'paid' WHERE id = :i"), {"i": mid})
    conn.execute(text("UPDATE module_items SET duration_s = 60 WHERE id = :i"), {"i": iid})
    conn.execute(text("UPDATE module_items SET duration_s = 36000 WHERE id = :i"), {"i": iid})
    conn.commit()
    conn.execute(text("UPDATE course_modules SET access_tier = 'free' WHERE id = :i"), {"i": mid})
    conn.execute(text("UPDATE module_items SET duration_s = NULL WHERE id = :i"), {"i": iid})
    conn.commit()


def _run(url) -> None:
    from alembic import command

    engine = _migrate(url)[0]
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, PREV)
        mid, iid = _seed(conn)
        _upgrade(cfg, conn, REV)
        _check(conn, mid, iid)
        command.downgrade(cfg, PREV)
        conn.commit()
        insp = inspect(conn)
        assert "access_tier" not in {c["name"] for c in insp.get_columns("course_modules")}
        assert "duration_s" not in {c["name"] for c in insp.get_columns("module_items")}
        names = {c["name"] for c in insp.get_check_constraints("course_modules")} | {
            c["name"] for c in insp.get_check_constraints("module_items")}
        assert not names & {"ck_course_modules_access_tier_valid", "ck_module_items_duration_s_range"}
        assert conn.execute(text("SELECT count(*) FROM module_items")).scalar() == 1
        _upgrade(cfg, conn, REV)
        _check(conn, mid, iid)
    engine.dispose()


def test_0024_up_down_up_sqlite(tmp_path):
    _run(f"sqlite:///{tmp_path}/m.db")


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


def test_0024_up_down_up_on_pg(pg_engine):
    _run(PG_URL)
