"""Migration 0025 (F6a Pro, SUBSCRIPTION_DESIGN 2) on the production-like fixture DB of 0013/0014, migrated through 0024,
with passes and codes written at 0024: a batch of three codes (unused, given, redeemed) and three passes (from the
redeemed code, by an admin, one revoked).

After 0025: the same rows, every pre-existing column of every pass, code and batch equal to the snapshot taken before
(nothing lost or changed in meaning), `plan` null everywhere, the CHECK refuses an unknown plan, the redeemed code
still links to its pass, `platform_settings` exists and is empty, the audit log accepts `platform_setting`. Down: the
column and the table are gone and the snapshot still matches; up again: the same.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0014 import _migrate
from tests.test_migration_0015 import _upgrade

REV = "0025_pro"
PREV = "0024_course_lessons"
T0 = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
TABLES = ("access_passes", "activation_codes", "activation_code_batches")


def _uid(conn, v) -> str:
    return str(v) if conn.dialect.name == "postgresql" else uuid.UUID(str(v)).hex


def _seed(conn) -> dict:
    users = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 2")).scalars().all()
    admin, student = users[0], users[1]
    batch = _uid(conn, uuid.uuid4())
    conn.execute(text("INSERT INTO activation_code_batches (id, label, duration_days, count, note, created_by_id, "
                      "created_at) VALUES (:i, 'Autumn', 30, 3, '500 som', :a, :t)"),
                 {"i": batch, "a": admin, "t": T0})
    code_ids = [_uid(conn, uuid.uuid4()) for _ in range(3)]
    for pos, cid in enumerate(code_ids, start=1):
        conn.execute(text("INSERT INTO activation_codes (id, batch_id, position, code_hmac, code_enc, last4) "
                          "VALUES (:i, :b, :p, :h, :e, :l)"),
                     {"i": cid, "b": batch, "p": pos, "h": f"{pos:064d}", "e": f"v1.sealed{pos}", "l": f"AB{pos:02d}"})
    conn.execute(text("UPDATE activation_codes SET given_at = :t, given_note = 'Aibek' WHERE id = :i"),
                 {"t": T0, "i": code_ids[1]})
    conn.execute(text("UPDATE activation_codes SET redeemed_at = :t, redeemed_by_id = :u WHERE id = :i"),
                 {"t": T0, "u": student, "i": code_ids[2]})
    pass_ids = [_uid(conn, uuid.uuid4()) for _ in range(3)]
    rows = [
        dict(i=pass_ids[0], u=student, s=T0, e=T0 + timedelta(days=30), src="code", c=code_ids[2], g=None, r=None,
             rv=None, rb=None),
        dict(i=pass_ids[1], u=student, s=T0 + timedelta(days=30), e=T0 + timedelta(days=40), src="admin", c=None,
             g=admin, r="contest", rv=None, rb=None),
        dict(i=pass_ids[2], u=admin, s=T0, e=T0 + timedelta(days=7), src="admin", c=None, g=admin, r="test",
             rv=T0 + timedelta(hours=1), rb=admin),
    ]
    for r in rows:
        conn.execute(text("INSERT INTO access_passes (id, user_id, scope, starts_at, ends_at, source, code_id, "
                          "granted_by_id, reason, revoked_at, revoked_by_id, created_at) "
                          "VALUES (:i, :u, 'all', :s, :e, :src, :c, :g, :r, :rv, :rb, :s)"), r)
    conn.commit()
    return {"redeemed_code": code_ids[2], "code_pass": pass_ids[0]}


def _snapshot(conn) -> dict:
    """{table: {id: {column: value}}} of the pre-0025 columns, as the driver returns them."""
    out = {}
    for t in TABLES:
        cols = [c["name"] for c in inspect(conn).get_columns(t) if c["name"] != "plan"]
        rows = conn.execute(text(f"SELECT {', '.join(cols)} FROM {t}")).mappings().all()
        out[t] = {str(r["id"]): dict(r) for r in rows}
    return out


def _check(conn, before: dict, seeded: dict) -> None:
    assert _snapshot(conn) == before
    assert conn.execute(text("SELECT plan FROM access_passes")).scalars().all() == [None] * 3
    with pytest.raises(IntegrityError):
        conn.execute(text("UPDATE access_passes SET plan = 'week'"))
    conn.rollback()
    conn.execute(text("UPDATE access_passes SET plan = 'month_1' WHERE source = 'admin'"))
    conn.rollback()  # accepted; not kept
    linked = conn.execute(text("SELECT p.id FROM access_passes p JOIN activation_codes c ON c.id = p.code_id "
                               "WHERE c.id = :c AND c.redeemed_at IS NOT NULL"), {"c": seeded["redeemed_code"]})
    assert [str(x) for x in linked.scalars().all()] == [str(seeded["code_pass"])]
    assert "platform_settings" in inspect(conn).get_table_names()
    assert conn.execute(text("SELECT count(*) FROM platform_settings")).scalar() == 0
    conn.execute(text("INSERT INTO admin_audit_log (id, created_at, actor_id, action, target_type, target_id) "
                      "VALUES (:i, CURRENT_TIMESTAMP, (SELECT id FROM users ORDER BY id LIMIT 1), "
                      "'access.settings_update', 'platform_setting', 'pro')"), {"i": _uid(conn, uuid.uuid4())})
    conn.rollback()


def _run(url) -> None:
    from alembic import command

    engine = _migrate(url)[0]
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, PREV)
        seeded = _seed(conn)
        before = _snapshot(conn)
        assert [len(before[t]) for t in TABLES] == [3, 3, 1]
        _upgrade(cfg, conn, REV)
        _check(conn, before, seeded)
        command.downgrade(cfg, PREV)
        conn.commit()
        insp = inspect(conn)
        assert "platform_settings" not in insp.get_table_names()
        assert "plan" not in {c["name"] for c in insp.get_columns("access_passes")}
        assert "ck_access_passes_plan_valid" not in {c["name"] for c in insp.get_check_constraints("access_passes")}
        assert _snapshot(conn) == before
        _upgrade(cfg, conn, REV)
        _check(conn, before, seeded)
    engine.dispose()


def test_0025_up_down_up_sqlite(tmp_path):
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


def test_0025_up_down_up_on_pg(pg_engine):
    _run(PG_URL)
