"""Migration 0032 (fix round 2026-11-12 1c) on the production-like fixture DB of 0013/0014, migrated through 0031.

After 0032: `teacher_requests.notice_dismissed_at` exists, is nullable and is NULL on an existing row; the other columns,
the row and the other tables are untouched. Down: the column is gone and the row stays; up again: the same.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.migrate import _config
from tests.test_migration_0008 import _uid
from tests.test_migration_0014 import _migrate
from tests.test_migration_0015 import _upgrade

REV = "0032_teacher_notice_dismissed"
PREV = "0031_infra"
T0 = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


def _cols(conn) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns("teacher_requests")}


def _seed(conn) -> str:
    rid = _uid(conn, uuid.uuid4())
    conn.execute(text(
        "INSERT INTO teacher_requests (id, user_id, status, decided_at, created_at, updated_at) "
        "VALUES (:id, 'usr_m_tester', 'approved', :t, :t, :t)"), {"id": rid, "t": T0})
    conn.commit()
    return rid


def _check(conn, rid, before_cols) -> None:
    cols = _cols(conn)
    assert set(cols) == set(before_cols) | {"notice_dismissed_at"}
    assert cols["notice_dismissed_at"]["nullable"] is True
    row = conn.execute(text("SELECT status, notice_dismissed_at FROM teacher_requests WHERE id = :id"),
                       {"id": rid}).one()
    assert (row[0], row[1]) == ("approved", None)
    conn.execute(text("UPDATE teacher_requests SET notice_dismissed_at = :t WHERE id = :id"), {"t": T0, "id": rid})
    assert conn.execute(text("SELECT notice_dismissed_at FROM teacher_requests WHERE id = :id"),
                        {"id": rid}).scalar() is not None
    conn.rollback()


def _run(url) -> None:
    from alembic import command

    engine = _migrate(url)[0]
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, PREV)
        tables = set(inspect(conn).get_table_names())
        before_cols = _cols(conn)
        assert "notice_dismissed_at" not in before_cols
        rid = _seed(conn)
        count = conn.execute(text("SELECT count(*) FROM teacher_requests")).scalar()
        _upgrade(cfg, conn, REV)
        assert set(inspect(conn).get_table_names()) == tables
        _check(conn, rid, before_cols)
        command.downgrade(cfg, PREV)
        conn.commit()
        assert set(_cols(conn)) == set(before_cols)
        assert conn.execute(text("SELECT count(*) FROM teacher_requests")).scalar() == count
        _upgrade(cfg, conn, REV)
        _check(conn, rid, before_cols)
    engine.dispose()


def test_0032_up_down_up_sqlite(tmp_path):
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


def test_0032_up_down_up_on_pg(pg_engine):
    _run(PG_URL)
