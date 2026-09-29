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

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
