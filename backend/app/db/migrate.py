"""Startup schema migrations via Alembic.

Render's free plan has no pre-deploy hook, so migrations run at application startup.
SQLite (dev and tests) keeps using init_db()'s create_all unless RUN_MIGRATIONS=1.
"""
import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.session import engine as app_engine

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
BASELINE_REVISION = "0001_baseline"
ADVISORY_LOCK_KEY = 7_204_001_001  # arbitrary fixed key shared by all workers


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

    # One connection, one transaction: a transaction-scoped advisory lock is released on
    # commit/rollback, so it cannot leak behind a transaction-mode pooler (Neon -pooler).
    with engine.connect() as conn:
        if is_pg:
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": ADVISORY_LOCK_KEY})
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "alembic_version" not in tables and "users" in tables:
            logger.info("Existing unversioned database: stamping %s", BASELINE_REVISION)
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
        conn.commit()
    return True
