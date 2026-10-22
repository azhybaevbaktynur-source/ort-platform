"""Alembic migration tests. Need a throwaway Postgres: set ALEMBIC_TEST_DATABASE_URL (an empty database)."""
import os

import pytest
from sqlalchemy import create_engine, inspect, text

TEST_URL = os.getenv("ALEMBIC_TEST_DATABASE_URL")
if not TEST_URL:
    pytest.skip("ALEMBIC_TEST_DATABASE_URL not set", allow_module_level=True)

from pytest_alembic.tests import (  # noqa: E402,F401
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)


@pytest.fixture
def alembic_config():
    from pytest_alembic.config import Config

    return Config(config_options={"file": str(_ini()), "script_location": str(_ini().parent / "alembic")})


def _ini():
    from app.db.migrate import ALEMBIC_INI

    return ALEMBIC_INI


@pytest.fixture
def alembic_engine():
    engine = create_engine(TEST_URL)
    _wipe(engine)
    yield engine
    _wipe(engine)
    engine.dispose()


def _wipe(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def test_run_migrations_stamps_existing_unversioned_db(alembic_engine):
    """A DB created by create_all (the current production state) is stamped, not re-created."""
    from alembic.script import ScriptDirectory

    from app.db.migrate import _config, run_migrations
    from app.db.session import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=alembic_engine)
    assert "alembic_version" not in inspect(alembic_engine).get_table_names()

    assert run_migrations(alembic_engine) is True

    head = ScriptDirectory.from_config(_config(TEST_URL)).get_current_head()
    with alembic_engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == head
    # idempotent
    assert run_migrations(alembic_engine) is True


def test_run_migrations_on_empty_db(alembic_engine):
    from app.db.migrate import run_migrations

    run_migrations(alembic_engine)
    assert "users" in inspect(alembic_engine).get_table_names()


def test_run_migrations_skips_sqlite_by_default(monkeypatch, tmp_path):
    from app.db.migrate import run_migrations

    monkeypatch.delenv("RUN_MIGRATIONS", raising=False)
    eng = create_engine(f"sqlite:///{tmp_path}/x.db")
    assert run_migrations(eng) is False
