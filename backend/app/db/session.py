import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

raw_db_url = os.getenv("DATABASE_URL") or settings.DATABASE_URL or "sqlite:///./test.db"

# Render, Heroku, Supabase, Neon use postgres:// which SQLAlchemy 2.0 requires as postgresql://
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

# For SQLite relative paths, ensure absolute path and directory exists
if raw_db_url.startswith("sqlite:///./"):
    subpath = raw_db_url.replace("sqlite:///./", "")
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    target_path = os.path.join(base_dir, subpath)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    db_url = f"sqlite:///{target_path}"
else:
    db_url = raw_db_url

connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

engine_kwargs = {"connect_args": connect_args, "pool_pre_ping": True}
if not db_url.startswith("sqlite"):
    # Sized per worker; keep (workers x (pool_size + max_overflow)) below the database limit.
    engine_kwargs.update(
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "5")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "300")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "10")),
    )
    # Optional cap on query time in ms. Off by default: pooled (PgBouncer) URLs reject startup options.
    statement_timeout_ms = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "0"))
    if statement_timeout_ms > 0:
        connect_args["options"] = f"-c statement_timeout={statement_timeout_ms}"

engine = create_engine(db_url, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
