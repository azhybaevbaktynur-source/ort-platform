"""Migration 0015 (Student view test student, UX_REWORK_DESIGN F) on the 0014 fixture DB.

Every existing user and enrollment reads `is_test_student = false`; the partial unique index allows one active test
enrollment per course and any number of retired ones; downgrade removes active test enrollments and disables test users,
so nobody counts as an ordinary student afterwards.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0008 import OTHER_COURSE, _uid
from tests.test_migration_0009 import T0
from tests.test_migration_0014 import REV as PREV, _migrate as _migrate_0014, _wipe

REV = "0015_test_student"
INDEX = "uq_enrollments_active_test_student"


def _upgrade(cfg, conn, rev):
    from alembic import command

    command.upgrade(cfg, rev)
    conn.commit()


def _user(conn, uid: str, *, test: bool) -> None:
    conn.execute(text(
        "INSERT INTO users (id, email, password_hash, email_verified, email_code_attempts, created_at, "
        "is_platform_admin, teacher_status, is_test_student) "
        "VALUES (:id, :e, '!', :t, 0, :c, :f, 'none', :test)"),
        {"id": uid, "e": f"{uid}@student-view.invalid", "t": True, "c": T0, "f": False, "test": test})


def _enrollment(conn, uid: str, *, state="active", test=True):
    eid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO enrollments (id, created_at, updated_at, course_id, user_id, role, state, source, is_test_student) "
        "VALUES (:id, :t, :t, :c, :u, 'student', :s, 'admin', :test)"),
        {"id": _uid(conn, eid), "t": T0, "c": _uid(conn, OTHER_COURSE), "u": uid, "s": state, "test": test})
    return eid


def _migrate(url):
    engine, _grades, _orgs, _courses = _migrate_0014(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        n_users = conn.execute(text("SELECT count(*) FROM users")).scalar()
        n_enr = conn.execute(text("SELECT count(*) FROM enrollments")).scalar()
        _upgrade(cfg, conn, REV)
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == REV
        # every existing row is false
        assert conn.execute(text("SELECT count(*) FROM users WHERE is_test_student")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM enrollments WHERE is_test_student")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == n_users
        assert conn.execute(text("SELECT count(*) FROM enrollments")).scalar() == n_enr
        ix = {i["name"]: i for i in inspect(conn).get_indexes("enrollments")}
        assert INDEX in ix and ix[INDEX]["unique"]

        # one active test enrollment per course; retired ones and real students do not collide
        for uid in ("usr_t_active", "usr_t_retired", "usr_t_second"):
            _user(conn, uid, test=True)
        _enrollment(conn, "usr_t_retired", state="removed")
        _enrollment(conn, "usr_t_active")
        conn.commit()
        with pytest.raises(IntegrityError):
            _enrollment(conn, "usr_t_second")
        conn.rollback()

        # downgrade: nobody counts as an ordinary student afterwards
        from alembic import command

        command.downgrade(cfg, PREV)
        conn.commit()
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == PREV
        assert "is_test_student" not in {c["name"] for c in inspect(conn).get_columns("users")}
        assert "is_test_student" not in {c["name"] for c in inspect(conn).get_columns("enrollments")}
        assert conn.execute(text("SELECT count(*) FROM enrollments WHERE user_id = 'usr_t_active' AND state = 'active'")
                            ).scalar() == 0
        assert conn.execute(text("SELECT disabled_at FROM users WHERE id = 'usr_t_active'")).scalar() is not None
        # and up again
        _upgrade(cfg, conn, REV)
        assert conn.execute(text("SELECT count(*) FROM users WHERE is_test_student")).scalar() == 0
    engine.dispose()


def test_0015_on_sqlite(tmp_path):
    _migrate(f"sqlite:///{tmp_path}/m.db")


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


def test_0015_on_pg(pg_engine):
    _migrate(PG_URL)
