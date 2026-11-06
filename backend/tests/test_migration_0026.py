"""Migration 0026 (F7a course cover, STUDENT_UI_FIX_PLAN 7.1) on the production-like fixture DB of 0013/0014, migrated
through 0025, with one public image asset written at 0025.

After 0026: every existing course reads `cover_asset_id = null`; a course pointed at the asset keeps it; the key refuses
an id that is not an asset; deleting the asset row sets the course's cover back to null (ON DELETE SET NULL, PostgreSQL
and SQLite with foreign keys on); the index exists. Down: the index, the key and the column are gone, courses and assets
are untouched; up again: the same.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import hashlib
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0014 import _migrate
from tests.test_migration_0015 import _upgrade

REV = "0026_course_cover"
PREV = "0025_pro"
T0 = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


def _uid(conn, v) -> str:
    return str(v) if conn.dialect.name == "postgresql" else uuid.UUID(str(v)).hex


def _asset(conn, owner: str) -> str:
    aid = _uid(conn, uuid.uuid4())
    sha = hashlib.sha256(aid.encode()).hexdigest()
    conn.execute(text(
        "INSERT INTO assets (id, created_at, updated_at, owner_id, kind, visibility, source_sha256, sha256, "
        "storage_key, mime, bytes, source_bytes, width, height, extension) VALUES "
        "(:i, :t, :t, :o, 'image', 'public', :s, :s, :k, 'image/webp', 1000, 2000, 1280, 720, 'webp')"),
        {"i": aid, "t": T0, "o": owner, "s": sha, "k": f"img/{sha}.webp"})
    conn.commit()
    return aid


def _course_ids(conn) -> list:
    return conn.execute(text("SELECT id FROM courses ORDER BY id")).scalars().all()


def _fk_on(conn) -> None:
    if conn.dialect.name == "sqlite":
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.commit()


def _check(conn, course, asset: str, owner: str) -> None:
    assert conn.execute(text("SELECT count(*) FROM courses WHERE cover_asset_id IS NOT NULL")).scalar() == 0
    conn.execute(text("UPDATE courses SET cover_asset_id = :a WHERE id = :c"), {"a": asset, "c": course})
    conn.commit()
    assert str(conn.execute(text("SELECT cover_asset_id FROM courses WHERE id = :c"), {"c": course}).scalar()
               ).replace("-", "") == asset.replace("-", "")
    _fk_on(conn)
    with pytest.raises(IntegrityError):
        conn.execute(text("UPDATE courses SET cover_asset_id = :a WHERE id = :c"),
                     {"a": _uid(conn, uuid.uuid4()), "c": course})
        conn.commit()
    conn.rollback()
    # a second asset on the course, then the row goes: the cover becomes null, the course stays
    other = _asset(conn, owner)
    conn.execute(text("UPDATE courses SET cover_asset_id = :a WHERE id = :c"), {"a": other, "c": course})
    conn.commit()
    _fk_on(conn)
    conn.execute(text("DELETE FROM assets WHERE id = :a"), {"a": other})
    conn.commit()
    assert conn.execute(text("SELECT cover_asset_id FROM courses WHERE id = :c"), {"c": course}).scalar() is None
    insp = inspect(conn)
    assert "ix_courses_cover_asset_id" in {i["name"] for i in insp.get_indexes("courses")}
    fks = [fk for fk in insp.get_foreign_keys("courses") if fk["constrained_columns"] == ["cover_asset_id"]]
    assert len(fks) == 1 and fks[0]["referred_table"] == "assets"
    if conn.dialect.name == "postgresql":
        assert fks[0]["name"] == "fk_courses_cover_asset_id_assets"
        assert (fks[0].get("options") or {}).get("ondelete") == "SET NULL"


def _run(url) -> None:
    from alembic import command

    engine = _migrate(url)[0]
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, PREV)
        owner = conn.execute(text("SELECT owner_id FROM courses ORDER BY id LIMIT 1")).scalar()
        asset = _asset(conn, owner)
        courses = _course_ids(conn)
        _upgrade(cfg, conn, REV)
        _check(conn, courses[0], asset, owner)
        if conn.dialect.name == "sqlite":
            conn.execute(text("PRAGMA foreign_keys = OFF"))  # batch mode rebuilds the table on downgrade
            conn.commit()
        command.downgrade(cfg, PREV)
        conn.commit()
        insp = inspect(conn)
        assert "cover_asset_id" not in {c["name"] for c in insp.get_columns("courses")}
        assert "ix_courses_cover_asset_id" not in {i["name"] for i in insp.get_indexes("courses")}
        assert _course_ids(conn) == courses
        assert conn.execute(text("SELECT count(*) FROM assets WHERE id = :a"), {"a": asset}).scalar() == 1
        _upgrade(cfg, conn, REV)
        _check(conn, courses[0], asset, owner)
    engine.dispose()


def test_0026_up_down_up_sqlite(tmp_path):
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


def test_0026_up_down_up_on_pg(pg_engine):
    _run(PG_URL)
