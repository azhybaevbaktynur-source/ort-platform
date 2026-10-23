import logging

from app.db.session import engine, Base
import app.models  # noqa: F401  (registers every model on Base.metadata)

logger = logging.getLogger(__name__)


def init_db():
    """Create missing tables (SQLite dev/tests). Postgres schema comes from Alembic; no seeds, no ALTERs."""
    Base.metadata.create_all(bind=engine)
