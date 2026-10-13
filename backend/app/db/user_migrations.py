import logging
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

# (column, SQLite type, PostgreSQL type). email_verified defaults to TRUE so every account that
# existed before email verification keeps working; new self-registrations set it to FALSE explicitly.
USER_AUTH_COLUMNS = [
    ("email_verified", "BOOLEAN NOT NULL DEFAULT 1", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("email_code_hash", "VARCHAR", "VARCHAR"),
    ("email_code_expires", "DATETIME", "TIMESTAMP"),
    ("email_code_attempts", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
    ("email_code_sent_at", "DATETIME", "TIMESTAMP"),
    ("reset_requested_at", "DATETIME", "TIMESTAMP"),
]


def ensure_user_auth_columns(engine) -> None:
    """Adds the email-verification / password-reset columns to an existing users table (SQLite or PostgreSQL)."""
    try:
        insp = inspect(engine)
        if not insp.has_table("users"):
            return
        existing = {c["name"] for c in insp.get_columns("users")}
        missing = [c for c in USER_AUTH_COLUMNS if c[0] not in existing]
        if not missing:
            return
        is_sqlite = engine.dialect.name == "sqlite"
        with engine.begin() as conn:
            for name, sqlite_type, pg_type in missing:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sqlite_type if is_sqlite else pg_type}"))
        logger.info("Added users columns: %s", ", ".join(c[0] for c in missing))
    except Exception as e:
        logger.warning(f"User auth column migration notice: {e}")
