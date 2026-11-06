"""S1 admin security: the real health check, for the admin overview only (`GET /platform/health`). The public `/health`
stays a no-database answer: Render pings it, and Neon must be allowed to sleep.

Nothing here sends an email, writes, or lists R2 objects: configuration is checked, never exercised (the storage
smoke check on the storage page does that, on demand)."""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


class DatabaseHealth(BaseModel):
    ok: bool
    latency_ms: Optional[float] = None
    dialect: str


class MigrationsHealth(BaseModel):
    ok: bool
    current: list[str]
    expected: list[str]


class EmailHealth(BaseModel):
    ok: bool
    provider: str
    configured: bool


class StorageHealth(BaseModel):
    ok: bool
    driver: str
    r2_configured: bool


class PlatformHealthOut(BaseModel):
    ok: bool
    database: DatabaseHealth
    migrations: MigrationsHealth
    email: EmailHealth
    storage: StorageHealth
    commit: Optional[str] = None


@lru_cache(maxsize=1)
def expected_heads() -> tuple[str, ...]:
    """The Alembic head(s) this code expects, read once from the migration files."""
    from alembic.script import ScriptDirectory

    from app.db.migrate import _config

    return tuple(sorted(ScriptDirectory.from_config(_config("sqlite://")).get_heads()))


def _database(db: Session) -> DatabaseHealth:
    dialect = db.get_bind().dialect.name
    start = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.warning("health: database check failed", exc_info=True)
        db.rollback()
        return DatabaseHealth(ok=False, dialect=dialect)
    return DatabaseHealth(ok=True, latency_ms=round((time.perf_counter() - start) * 1000, 1), dialect=dialect)


def _migrations(db: Session, dialect: str) -> MigrationsHealth:
    expected = list(expected_heads())
    try:
        current = sorted(db.execute(text("SELECT version_num FROM alembic_version")).scalars())
    except Exception:  # SQLite dev/tests build the schema with create_all and have no version table
        db.rollback()
        current = []
    ok = current == expected if dialect == "postgresql" else (not current or current == expected)
    return MigrationsHealth(ok=ok, current=current, expected=expected)


def _email() -> EmailHealth:
    from app.services.email_service import active_provider

    provider = active_provider()
    sender = bool(settings.EMAIL_FROM or settings.SMTP_FROM_EMAIL or settings.SMTP_USER)
    configured = {
        "resend": bool(settings.RESEND_API_KEY) and sender,
        "brevo": bool(settings.BREVO_API_KEY) and sender,
        "smtp": bool(settings.SMTP_SERVER and settings.SMTP_USER and settings.SMTP_PASSWORD),
    }.get(provider, False)  # "console" only writes to the server log: no one receives the email
    return EmailHealth(ok=configured, provider=provider, configured=configured)


def _storage() -> StorageHealth:
    driver = (settings.LMS_STORAGE_DRIVER or "").strip().lower()
    r2 = all((settings.R2_ACCOUNT_ID, settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY, settings.R2_BUCKET,
              settings.R2_PRIVATE_BUCKET))
    ok = r2 if driver == "r2" else driver in ("db", "local")
    return StorageHealth(ok=ok, driver=driver, r2_configured=r2)


def platform_health(db: Session) -> PlatformHealthOut:
    import os

    database = _database(db)
    migrations = _migrations(db, database.dialect) if database.ok else MigrationsHealth(
        ok=False, current=[], expected=list(expected_heads()))
    email, storage = _email(), _storage()
    return PlatformHealthOut(ok=database.ok and migrations.ok and email.ok and storage.ok, database=database,
                             migrations=migrations, email=email, storage=storage,
                             commit=os.getenv("RENDER_GIT_COMMIT", "")[:7] or None)
