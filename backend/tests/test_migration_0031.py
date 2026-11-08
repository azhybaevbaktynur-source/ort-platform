"""Migration 0031 (I5a infrastructure panel, INFRA_PANEL_DESIGN 5) on the production-like fixture DB of 0013/0014,
migrated through 0029.

After 0031: `infra_snapshots` exists and is empty, `provider` is the primary key (a second row for the same provider is
refused), `payload` defaults to `{}`, the other tables are untouched. Down: the table is gone; up again: the same.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import json
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0014 import _migrate
from tests.test_migration_0015 import _upgrade

REV = "0031_infra"
PREV = "0029_user_identities"
T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def _tables(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _check(conn) -> None:
    insp = inspect(conn)
    assert "infra_snapshots" in insp.get_table_names()
    assert conn.execute(text("SELECT count(*) FROM infra_snapshots")).scalar() == 0
    assert insp.get_pk_constraint("infra_snapshots")["constrained_columns"] == ["provider"]
    cols = {c["name"]: c for c in insp.get_columns("infra_snapshots")}
    assert set(cols) == {"provider", "status", "fetched_at", "payload", "error", "duration_ms", "updated_at"}
    assert [n for n, c in cols.items() if not c["nullable"]] == ["provider", "status", "payload", "updated_at"]
    conn.execute(text("INSERT INTO infra_snapshots (provider, status, updated_at) VALUES ('neon', 'empty', :t)"),
                 {"t": T0})
    payload = conn.execute(text("SELECT payload FROM infra_snapshots WHERE provider = 'neon'")).scalar()
    assert (json.loads(payload) if isinstance(payload, str) else payload) == {}
    with pytest.raises(IntegrityError):
        conn.execute(text("INSERT INTO infra_snapshots (provider, status, updated_at) VALUES ('neon', 'ok', :t)"),
                     {"t": T0})
    conn.rollback()
    assert conn.execute(text("SELECT count(*) FROM infra_snapshots")).scalar() == 0


def _run(url) -> None:
    from alembic import command

    engine = _migrate(url)[0]
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, PREV)
        before = _tables(conn)
        users = conn.execute(text("SELECT count(*) FROM users")).scalar()
        assert "infra_snapshots" not in before
        _upgrade(cfg, conn, REV)
        assert _tables(conn) == before | {"infra_snapshots"}
        _check(conn)
        command.downgrade(cfg, PREV)
        conn.commit()
        assert _tables(conn) == before
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == users
        _upgrade(cfg, conn, REV)
        _check(conn)
    engine.dispose()


def test_0031_up_down_up_sqlite(tmp_path):
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


def test_0031_up_down_up_on_pg(pg_engine):
    _run(PG_URL)
