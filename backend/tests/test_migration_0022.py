"""Migration 0022 (S3 free and paid exams, docs/phases/S3_ACCESS_DESIGN.md 2) on the production-like fixture DB of
0013/0014 (ORT courses with a published exam, a general course with a draft quiz, grades), migrated through 0021.

After 0022: every existing assessment is `free` (nothing locks on deploy); the three new tables are empty and their
CHECKs and the unique code hash hold; the audit log accepts the new target types. Down/up: the downgrade drops the
tables and the column; the upgrade again yields the same.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0014 import _migrate
from tests.test_migration_0015 import _upgrade

REV = "0022_access"
PREV = "0021_admin_mfa"
TABLES = ("access_passes", "activation_codes", "activation_code_batches")


def _uid(conn, v) -> str:
    return str(v) if conn.dialect.name == "postgresql" else uuid.UUID(str(v)).hex


def _check(conn, n_assessments: int) -> None:
    rows = conn.execute(text("SELECT access_tier FROM assessments")).scalars().all()
    assert len(rows) == n_assessments and n_assessments > 0 and set(rows) == {"free"}
    for t in TABLES:
        assert conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0
    insp = inspect(conn)
    assert {"ix_access_passes_user_id_ends_at", "ix_access_passes_code_id"} <= {
        i["name"] for i in insp.get_indexes("access_passes")}
    with pytest.raises(IntegrityError):
        conn.execute(text("UPDATE assessments SET access_tier = 'gold'"))
    conn.rollback()
    with pytest.raises(IntegrityError):  # a batch needs exactly one length
        conn.execute(text("INSERT INTO activation_code_batches (id, label, count, created_at) "
                          "VALUES (:i, 'x', 1, CURRENT_TIMESTAMP)"), {"i": _uid(conn, uuid.uuid4())})
    conn.rollback()
    bid = _uid(conn, uuid.uuid4())
    conn.execute(text("INSERT INTO activation_code_batches (id, label, duration_days, count, created_at) "
                      "VALUES (:i, 'x', 30, 2, CURRENT_TIMESTAMP)"), {"i": bid})
    for pos in (1, 2):
        stmt = text("INSERT INTO activation_codes (id, batch_id, position, code_hmac, code_enc, last4) "
                    "VALUES (:i, :b, :p, 'same', 'v1.x', 'ABCD')")
        if pos == 1:
            conn.execute(stmt, {"i": _uid(conn, uuid.uuid4()), "b": bid, "p": pos})
        else:
            with pytest.raises(IntegrityError):  # the keyed hash is unique
                conn.execute(stmt, {"i": _uid(conn, uuid.uuid4()), "b": bid, "p": pos})
    conn.rollback()
    conn.execute(text("INSERT INTO admin_audit_log (id, created_at, actor_id, action, target_type, target_id) "
                      "VALUES (:i, CURRENT_TIMESTAMP, (SELECT id FROM users LIMIT 1), 'access.batch_create', "
                      "'access_batch', 'x')"), {"i": _uid(conn, uuid.uuid4())})
    conn.rollback()


def _run(url) -> None:
    from alembic import command

    engine = _migrate(url)[0]
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, PREV)
        n = conn.execute(text("SELECT count(*) FROM assessments")).scalar()
        _upgrade(cfg, conn, REV)
        _check(conn, n)
        command.downgrade(cfg, PREV)
        conn.commit()
        insp = inspect(conn)
        assert not set(TABLES) & set(insp.get_table_names())
        assert "access_tier" not in {c["name"] for c in insp.get_columns("assessments")}
        _upgrade(cfg, conn, REV)
        _check(conn, n)
    engine.dispose()


def test_0022_up_down_up_sqlite(tmp_path):
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


def test_0022_up_down_up_on_pg(pg_engine):
    _run(PG_URL)
