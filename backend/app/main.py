import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings, refuse_unsafe_secret_keys
from app.db.init_db import init_db
from app.db.migrate import run_migrations
from app.api.v1.router import api_router
from app.core.security_headers import SecurityHeadersMiddleware
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


# --- Phase 11 S1 begin ---
def _ensure_policies() -> None:
    """Phase 11 policy versions from `privacy/policies/manifest.json` (PHASE_11_DESIGN 3.1), idempotent; never fatal."""
    from app.db.session import SessionLocal
    from app.lms.privacy.seed import ensure_policies

    db = SessionLocal()
    try:
        ensure_policies(db)
    except Exception:
        db.rollback()
        logger.exception("Seeding the policy versions failed")
    finally:
        db.close()
# --- Phase 11 S1 end ---


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
    refuse_unsafe_secret_keys()  # Phase 11 S4: before anything touches the database
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
    _ensure_policies()  # Phase 11 S1
    await _configure_thread_limiter()
    admission.logger.info("admission gate configured", extra=admission.describe())
    yield


from app.core.logging import configure_logging  # noqa: E402
from app.core.request_log import RequestLogMiddleware  # noqa: E402
from app.core.sentry import init_sentry  # noqa: E402

configure_logging()
init_sentry()  # Phase 11 S6: no-op without SENTRY_DSN

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
app.add_middleware(SecurityHeadersMiddleware)  # Phase 11 S4: just inside CORS, so every route's answer carries the headers
app.add_middleware(RequestLogMiddleware)  # Phase 11 S6: outside the app, inside CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Phase 7b S5: the frontend (another origin) reads the server's file name of downloads (import-format CSV)
    expose_headers=["Content-Disposition"],
)

# --- Phase 6 S2b begin --- (GET /courses/templates; before api_router so it wins over /courses/{course_id})
from app.lms.templates.router import router as _templates_router  # noqa: E402

app.include_router(_templates_router, prefix=settings.API_V1_STR + "/courses", tags=["Courses"])
# --- Phase 6 S2b end ---
# --- Phase 6 S6a begin --- (GET /me/home, student home, PHASE_6_DESIGN 8.4)
from app.lms.home.router import router as _home_router  # noqa: E402

app.include_router(_home_router, prefix=settings.API_V1_STR)
# --- Phase 6 S6a end ---
# --- Phase 7a S4 begin --- (accommodations and overrides, PHASE_7A_DESIGN 4.4)
from app.lms.accommodations.router import router as _accommodations_router  # noqa: E402

app.include_router(_accommodations_router, prefix=settings.API_V1_STR)
# --- Phase 7a S4 end ---
# --- Phase 7a S2 begin --- (assignments, hand-ins and hand-in files, PHASE_7A_DESIGN 4.1, 4.2)
from app.lms.assignments.router import router as _assignments_router  # noqa: E402

app.include_router(_assignments_router, prefix=settings.API_V1_STR, tags=["Assignments"])
# --- Phase 7a S2 end ---
# --- Phase 11 S1 begin --- (privacy; empty routers of the parallel slices, so they never edit this wiring)
from app.lms.guardian.router import router as _guardian_router  # noqa: E402
from app.lms.practice.retention_router import router as _retention_router  # noqa: E402
from app.lms.privacy.router import router as _privacy_router  # noqa: E402
from app.lms.student_view.sweep_router import router as _sweep_router  # noqa: E402

for _r in (_privacy_router, _guardian_router, _retention_router, _sweep_router):
    app.include_router(_r, prefix=settings.API_V1_STR)
# --- Phase 11 S1 end ---
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
