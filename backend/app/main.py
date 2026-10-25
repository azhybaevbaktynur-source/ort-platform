import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

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


# --- Phase 6 S1 begin ---
def _ensure_organizations() -> None:
    """Phase 6 organizations bootstrap (PHASE_6_DESIGN 4), idempotent; never fatal."""
    from app.db.session import SessionLocal
    from app.lms.organizations.bootstrap import ensure_organizations

    db = SessionLocal()
    try:
        ensure_organizations(db)
    finally:
        db.close()
# --- Phase 6 S1 end ---


# --- Phase 7a S1 begin ---
def _ensure_assignments() -> None:
    """Phase 7a quiz assignments bootstrap (PHASE_7A_DESIGN 2.9), idempotent; never fatal."""
    from app.db.session import SessionLocal
    from app.lms.assignments.bootstrap import ensure_assignments

    db = SessionLocal()
    try:
        ensure_assignments(db)
    finally:
        db.close()
# --- Phase 7a S1 end ---


def _seed_ort_courses() -> None:
    """Phase 5 ORT courses and the conversion of legacy_ort_export (P5-2); never fatal (ensure_ort_courses logs
    and stores every failure itself)."""
    from app.db.session import SessionLocal
    from app.lms.ort.seed import ensure_ort_courses

    db = SessionLocal()
    try:
        ensure_ort_courses(db)
    except Exception:
        db.rollback()
        logger.exception("Seeding the ORT courses failed")
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
    _ensure_organizations()  # Phase 6 S1: after the schemes, before the ORT courses
    _ensure_assignments()  # Phase 7a S1: after the organizations, before the ORT courses
    _seed_ort_courses()
    if is_production():
        if settings.SECRET_KEY == DEFAULT_SECRET_KEY:
            logger.critical("SECRET_KEY is the public default from the repository: anyone can forge login tokens. Set SECRET_KEY.")
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
# --- Phase 6 S3 begin --- (H2: datetimes in JSON always carry a timezone; invitation routes)
from app.core.utc_json import UTCDatetimeJSONMiddleware  # noqa: E402
from app.lms.invitations.router import router as _invitations_router  # noqa: E402

# Just outside the admission gate, inside GZip: it sees the uncompressed JSON body the route produced.
app.add_middleware(UTCDatetimeJSONMiddleware)
app.include_router(_invitations_router, prefix=settings.API_V1_STR)
# --- Phase 6 S3 end ---
app.add_middleware(BodyCapMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Phase 6 S2b begin --- (GET /courses/templates; before api_router so it wins over /courses/{course_id})
from app.lms.templates.router import router as _templates_router  # noqa: E402

app.include_router(_templates_router, prefix=settings.API_V1_STR + "/courses", tags=["Courses"])
# --- Phase 6 S2b end ---
# --- Phase 6 S6a begin --- (GET /me/home, student home, PHASE_6_DESIGN 8.4)
from app.lms.home.router import router as _home_router  # noqa: E402

app.include_router(_home_router, prefix=settings.API_V1_STR)
# --- Phase 6 S6a end ---
# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)
register_error_handlers(app)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "database": "connected",
        # Deployed commit (Render sets RENDER_GIT_COMMIT), to confirm which code is live
        "commit": os.getenv("RENDER_GIT_COMMIT", "")[:7] or None,
    }
