"""Fix round 2026-11-12: startup migrations retry a lock wait instead of hanging the deploy."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from app.db import migrate


class _PgError(Exception):
    def __init__(self, pgcode):
        super().__init__(pgcode)
        self.pgcode = pgcode


def _engine():
    eng = create_engine("sqlite://")
    eng.dialect.name = "postgresql"  # only the dialect check matters; _upgrade is replaced below
    return eng


def test_a_lock_wait_is_retried(monkeypatch):
    calls = []

    def flaky(engine, cfg, is_pg):
        calls.append(is_pg)
        if len(calls) < 3:
            raise OperationalError("ALTER TABLE", {}, _PgError("55P03"))

    monkeypatch.setattr(migrate, "_upgrade", flaky)
    monkeypatch.setattr(migrate, "LOCK_RETRY_SECONDS", 0)
    assert migrate.run_migrations(_engine()) is True
    assert calls == [True, True, True]


def test_other_errors_and_the_last_attempt_raise(monkeypatch):
    monkeypatch.setattr(migrate, "LOCK_RETRY_SECONDS", 0)

    def broken(engine, cfg, is_pg):
        raise OperationalError("SELECT", {}, _PgError("42P01"))

    monkeypatch.setattr(migrate, "_upgrade", broken)
    with pytest.raises(OperationalError):
        migrate.run_migrations(_engine())

    calls = []

    def locked(engine, cfg, is_pg):
        calls.append(1)
        raise OperationalError("ALTER TABLE", {}, _PgError("55P03"))

    monkeypatch.setattr(migrate, "_upgrade", locked)
    with pytest.raises(OperationalError):
        migrate.run_migrations(_engine())
    assert len(calls) == migrate.LOCK_ATTEMPTS
