"""Startup schema migrations via Alembic.

Render's free plan has no pre-deploy hook, so migrations run at application startup.
SQLite (dev and tests) keeps using init_db()'s create_all unless RUN_MIGRATIONS=1.
"""
import logging
import os
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from app.db.session import engine as app_engine

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
BASELINE_REVISION = "0001_baseline"
ADVISORY_LOCK_KEY = 7_204_001_001  # arbitrary fixed key shared by all workers
# Fix round 2026-11-12: during a deploy the old instance still serves; a DDL statement queued behind one of its
# transactions would hold every later query of that table (and the deploy's health check) behind it. A short lock wait,
# retried, keeps the old instance answering and gives a clear log line instead of a silent hang.
LOCK_TIMEOUT = "10s"
LOCK_ATTEMPTS = 8
LOCK_RETRY_SECONDS = 5


def _config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["sqlalchemy_url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


def run_migrations(engine: Engine | None = None) -> bool:
    """Bring the database to the Alembic head. Returns True if it ran, False if skipped."""
    engine = engine or app_engine
    is_pg = engine.dialect.name == "postgresql"
    if not is_pg and os.getenv("RUN_MIGRATIONS") != "1":
        logger.info("Skipping Alembic migrations (dialect=%s, RUN_MIGRATIONS not set)", engine.dialect.name)
        return False

    url = engine.url.render_as_string(hide_password=False)
    cfg = _config(url)

    for attempt in range(1, LOCK_ATTEMPTS + 1):
        try:
            _upgrade(engine, cfg, is_pg)
            return True
        except OperationalError as e:
            if getattr(e.orig, "pgcode", None) != "55P03" or attempt == LOCK_ATTEMPTS:  # 55P03 = lock_not_available
                raise
            logger.warning("Migration waited %s for a table lock (attempt %d of %d); retrying", LOCK_TIMEOUT, attempt,
                           LOCK_ATTEMPTS)
            time.sleep(LOCK_RETRY_SECONDS)
    return True


def _upgrade(engine: Engine, cfg: Config, is_pg: bool) -> None:
    # One connection, one transaction: a transaction-scoped advisory lock is released on
    # commit/rollback, so it cannot leak behind a transaction-mode pooler (Neon -pooler).
    with engine.connect() as conn:
        if is_pg:
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": ADVISORY_LOCK_KEY})
            conn.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "alembic_version" not in tables and "users" in tables:
            logger.info("Existing unversioned database: stamping %s", BASELINE_REVISION)
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
        conn.commit()
