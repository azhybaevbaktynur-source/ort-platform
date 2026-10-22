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
from app.lms.core.errors import register_error_handlers

logger = logging.getLogger(__name__)


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
    if is_production():
        if settings.SECRET_KEY == DEFAULT_SECRET_KEY:
            logger.critical("SECRET_KEY is the public default from the repository: anyone can forge login tokens. Set SECRET_KEY.")
        if settings.ALLOW_MOCK_TOKENS:
            logger.critical("ALLOW_MOCK_TOKENS is enabled in production: 'mock_admin_token' grants admin access. Disable it.")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Kyrgyz National Scholarship Test (ОРТ / ЖРТ) Test-Prep Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Set CORS origins from environment variable list
cors_origins = settings.ALLOWED_ORIGINS or settings.BACKEND_CORS_ORIGINS or ["*"]
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
