import logging
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def ensure_attempt_preview_column(engine) -> None:
    """Adds test_attempts.is_preview (admin student-mode attempts); existing attempts are real (FALSE)."""
    try:
        insp = inspect(engine)
        if not insp.has_table("test_attempts"):
            return
        if "is_preview" in {c["name"] for c in insp.get_columns("test_attempts")}:
            return
        default = "0" if engine.dialect.name == "sqlite" else "FALSE"
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE test_attempts ADD COLUMN is_preview BOOLEAN NOT NULL DEFAULT {default}"))
    except Exception as e:
        logger.warning(f"Attempt preview column migration notice: {e}")
