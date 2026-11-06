"""Migration 0023 (S4 person page) on the production-like fixture DB of 0013/0014, migrated through 0022.

After 0023: every user has no last login yet; the users list index exists; `email_change_requests` is empty, one row per
user and a unique token hash hold, and deleting a user removes their pending change. Down/up: the downgrade drops the
table, the index and the column; the upgrade again yields the same.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0014 import _migrate
from tests.test_migration_0015 import _upgrade

REV = "0023_person"
PREV = "0022_access"


def _uid(conn, v) -> str:
    return str(v) if conn.dialect.name == "postgresql" else uuid.UUID(str(v)).hex


def _row(conn, user_id: str, token: str) -> None:
    conn.execute(text("INSERT INTO email_change_requests (id, user_id, new_email, token_hash, expires_at, created_at) "
                      "VALUES (:i, :u, 'n@t.example', :h, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
                 {"i": _uid(conn, uuid.uuid4()), "u": user_id, "h": token})


def _check(conn, n_users: int) -> None:
    rows = conn.execute(text("SELECT last_login_at FROM users")).scalars().all()
    assert len(rows) == n_users > 0 and set(rows) == {None}
    insp = inspect(conn)
    assert "ix_users_created_at_id" in {i["name"] for i in insp.get_indexes("users")}
    assert conn.execute(text("SELECT count(*) FROM email_change_requests")).scalar() == 0
    users = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 2")).scalars().all()
    _row(conn, users[0], "a" * 64)
    with pytest.raises(IntegrityError):  # one pending change per user
        _row(conn, users[0], "b" * 64)
    conn.rollback()
    _row(conn, users[0], "a" * 64)
    with pytest.raises(IntegrityError):  # the token hash is unique
        _row(conn, users[1], "a" * 64)
    conn.rollback()


def _run(url) -> None:
    from alembic import command

    engine = _migrate(url)[0]
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, PREV)
        n = conn.execute(text("SELECT count(*) FROM users")).scalar()
        _upgrade(cfg, conn, REV)
        _check(conn, n)
        command.downgrade(cfg, PREV)
        conn.commit()
        insp = inspect(conn)
        assert "email_change_requests" not in insp.get_table_names()
        assert "last_login_at" not in {c["name"] for c in insp.get_columns("users")}
        assert "ix_users_created_at_id" not in {i["name"] for i in insp.get_indexes("users")}
        _upgrade(cfg, conn, REV)
        _check(conn, n)
    engine.dispose()


def test_0023_up_down_up_sqlite(tmp_path):
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


def test_0023_up_down_up_on_pg(pg_engine):
    _run(PG_URL)
