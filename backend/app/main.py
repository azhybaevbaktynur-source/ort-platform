import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings, is_production, DEFAULT_SECRET_KEY
from app.db.init_db import init_db
from app.db.migrate import run_migrations
from app.api.v1.router import api_router
from app.lms.core import admission
from app.lms.core.errors import register_error_handlers
import app.lms.grading  # noqa: F401,E402  (registers the Phase 4 attempt-scored hook, P4-1)

logger = logging.getLogger(__name__)


async def _configure_thread_limiter() -> None:
    """Cap sync-route worker threads at the DB pool size so threads never queue on the pool (L5)."""
    tokens = settings.LMS_THREADPOOL_TOKENS
    if tokens > 0:
        from anyio import to_thread

        to_thread.current_default_thread_limiter().total_tokens = tokens


def _seed_grading_schemes() -> None:
    """Phase 4 system grading schemes (P4-6), idempotent; a failure is logged, never fatal."""
    from app.db.session import SessionLocal
    from app.lms.grading.seeds import ensure_system_schemes

    db = SessionLocal()
    try:
        ensure_system_schemes(db)
    except Exception:
        db.rollback()
        logger.exception("Seeding system grading schemes failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI modern lifespan handler (replaces deprecated on_event)."""
    try:
        run_migrations()
    except Exception:
        logger.exception("Database migration failed; refusing to start")
        raise
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Database startup initialization notice: {e}")
    _seed_grading_schemes()
    if is_production():
        if settings.SECRET_KEY == DEFAULT_SECRET_KEY:
            logger.critical("SECRET_KEY is the public default from the repository: anyone can forge login tokens. Set SECRET_KEY.")
        if settings.ALLOW_MOCK_TOKENS:
            logger.critical("ALLOW_MOCK_TOKENS is enabled in production: 'mock_admin_token' grants admin access. Disable it.")
    await _configure_thread_limiter()
    admission.logger.info("admission gate configured", extra=admission.describe())
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Kyrgyz National Scholarship Test (ОРТ / ЖРТ) Test-Prep Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Set CORS origins from environment variable list
cors_origins = settings.ALLOWED_ORIGINS or settings.BACKEND_CORS_ORIGINS or ["*"]
from app.lms.attempts.bodycap import BodyCapMiddleware
# Innermost (added first): Content-Length 413s and CORS preflights never wait for a slot; CORS still wraps the 503 (B1).
app.add_middleware(admission.AdmissionMiddleware)
app.add_middleware(BodyCapMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure local uploads directory exists and mount static handler if local
uploads_dir = settings.LOCAL_UPLOAD_DIR or os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/uploads"))
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)
register_error_handlers(app)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "firebase_mock_mode": settings.FIREBASE_MOCK_MODE,
        "database": "connected",
        "storage": settings.STORAGE_ENV,
        # Deployed commit (Render sets RENDER_GIT_COMMIT), to confirm which code is live
        "commit": os.getenv("RENDER_GIT_COMMIT", "")[:7] or None,
    }
