import json
from typing import Annotated, List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "ORT / ЖРТ Test-Prep Platform"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # CORS & Allowed Origins. NoDecode: the env value reaches the validator as raw text, so both
    # "https://a.app,https://b.app" and '["https://a.app"]' work (otherwise only JSON would parse).
    ALLOWED_ORIGINS: Annotated[List[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    BACKEND_CORS_ORIGINS: Annotated[List[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    @field_validator("ALLOWED_ORIGINS", "BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = json.loads(v) if v.strip().startswith("[") else v.split(",")
        if isinstance(v, list):
            return [str(i).strip() for i in v if str(i).strip()]
        return v

    # Relational Database (SQLite for local dev, swappable to PostgreSQL on Render)
    DATABASE_URL: str = "sqlite:///./test.db"

    # Local blob directory (tests/dev); LMS_STORAGE_DRIVER below picks the real driver
    LOCAL_UPLOAD_DIR: str = ""  # Overrides backend/data/uploads (used by tests to keep dev uploads clean)

    # JWT Authentication
    SECRET_KEY: str = "ort_secret_jwt_key_2026_super_secure_academic_prep"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Number of trusted proxies appending to X-Forwarded-For (Vercel rewrite -> Render = 2); 0 = ignore the header
    RATE_LIMIT_PROXY_HOPS: int = 2
    # IP-keyed rate-limit rules count and log but never deny until the proxy chain is verified.
    RATE_LIMIT_IP_ENFORCE: bool = False

    # --- Phase 2: files and content library (docs/phases/PHASE_2_DESIGN.md) ---
    # Blob storage driver: "local" (tests/dev), "db" (asset_blobs table, production until R2), "r2".
    LMS_STORAGE_DRIVER: str = "db"
    LMS_LOCAL_STORAGE_DIR: str = ""  # empty = {LOCAL_UPLOAD_DIR}/lms
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = "ort-lms-media"
    R2_PRIVATE_BUCKET: str = ""  # private (priv/) blobs; empty = private uploads rejected on the r2 driver
    R2_PUBLIC_BASE_URL: str = ""  # CDN base for public images; empty = served by /api/v1/media
    MEDIA_BASE_URL: str = "/api/v1/media"
    MEDIA_CACHE_BYTES: int = 64 * 1024 * 1024
    # Images (P2-4, P2-6)
    ASSET_MAX_UPLOAD_BYTES: int = 2 * 1024 * 1024
    ASSET_MAX_BUNDLE_IMAGE_BYTES: int = 10 * 1024 * 1024
    ASSET_MAX_PIXELS: int = 12_000_000
    ASSET_MAX_SIDE: int = 1600
    ASSET_MAX_STORED_BYTES: int = 2 * 1024 * 1024
    ASSET_QUOTA_BYTES_PER_USER: int = 200 * 1024 * 1024
    ASSET_DB_MAX_TOTAL_BYTES: int = 300 * 1024 * 1024
    ASSET_UPLOAD_RATE_PER_HOUR: int = 300
    # Import limits (P2-22)
    IMPORT_MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024
    IMPORT_MAX_UNCOMPRESSED_BYTES: int = 150 * 1024 * 1024
    IMPORT_MAX_ZIP_ENTRIES: int = 5000
    IMPORT_MAX_ROWS: int = 5000
    IMPORT_MAX_IMAGES: int = 1000
    IMPORT_MAX_CSV_BYTES: int = 32 * 1024 * 1024
    IMPORT_MAX_MANIFEST_BYTES: int = 5 * 1024 * 1024
    IMPORT_MAX_ISSUES: int = 200
    IMPORT_MAX_CONCURRENT: int = 1
    ASSET_ORPHAN_MIN_AGE_SECONDS: int = 3600
    ASSET_ORPHAN_SWEEP_INTERVAL_SECONDS: int = 3600
    CONTENT_IMPORT_RATE_PER_HOUR: int = 60

    # --- Phase 3: assessments and attempts (docs/phases/PHASE_3_DESIGN.md) ---
    # Grace after a deadline during which writes are still accepted (D8, P3-14)
    ATTEMPT_GRACE_S: int = 45
    # Opportunistic sweep of expired attempts (P3-26); token empty = internal sweep route returns 404
    ATTEMPT_SWEEP_INTERVAL_S: int = 60
    ATTEMPT_SWEEP_BATCH: int = 100
    ATTEMPT_SWEEP_TOKEN: str = ""
    # anyio worker-thread limit per process (L5). 0 = leave anyio's default (40). Matching it to
    # DB_POOL_SIZE + DB_MAX_OVERFLOW does not prevent the overload deadlock (B1); the admission gate below does.
    LMS_THREADPOOL_TOKENS: int = 20
    # Admission gate (B1, app/lms/core/admission.py): at most N requests per process inside the app. 0 = auto:
    # min(thread tokens, DB_POOL_SIZE + DB_MAX_OVERFLOW) minus the sweep's app-pool reserve (0 on Postgres).
    LMS_ADMISSION_LIMIT: int = 0
    # Longest wait for a slot before 503 server_busy (Retry-After: 2). <= 0 waits without a limit.
    LMS_ADMISSION_WAIT_SECONDS: float = 20.0
    # Rate limits (P3-28): DB-backed start/manual scoring; in-process autosave token bucket per (worker, user)
    ATTEMPT_START_RATE_PER_10M: int = 20
    GRADE_ITEM_RATE_PER_HOUR: int = 600
    AUTOSAVE_BUCKET_REQUESTS: int = 30
    AUTOSAVE_BUCKET_WINDOW_S: int = 30
    AUTOSAVE_BUCKET_MAX_USERS: int = 20000
    # Caps (P3-29)
    ASSESSMENT_MAX_ITEMS: int = 500
    ASSESSMENT_MAX_SECTIONS: int = 20
    ASSESSMENT_PICK_POOL_MAX: int = 1000
    ASSESSMENT_PICK_COUNT_MAX: int = 200
    ASSESSMENT_ITEM_POINTS_MAX: int = 1000
    AUTOSAVE_MAX_ENTRIES: int = 20
    AUTOSAVE_MAX_BODY_BYTES: int = 256 * 1024
    API_MAX_BODY_BYTES: int = 1024 * 1024
    PAYLOAD_CACHE_BYTES: int = 48 * 1024 * 1024
    PLAN_CACHE_BYTES: int = 16 * 1024 * 1024

    # --- Phase 4: grading (docs/phases/PHASE_4_DESIGN.md) ---
    # Caps (P4-22)
    GRADING_BANDS_MAX: int = 50
    GRADING_CURVE_SEGMENTS_MAX: int = 20
    GRADING_TABLE_ROWS_MAX: int = 1000
    GRADING_THRESHOLDS_MAX: int = 10
    GRADING_LABEL_MAX_CHARS: int = 60
    GRADING_PREVIEW_MAX_POINTS: int = 1001
    GRADE_CATEGORIES_MAX: int = 30
    GRADES_REGRADE_MAX: int = 2000
    GRADES_REGRADE_CHUNK: int = 200
    GRADES_RELEASE_MAX_IDS: int = 5000
    GRADING_MAX_BODY_BYTES: int = 64 * 1024
    GRADING_VERSION_CACHE_SIZE: int = 256
    # Rate limits (P4-21); override/excuse reuse GRADE_ITEM_RATE_PER_HOUR
    GRADES_RELEASE_RATE_PER_HOUR: int = 60
    GRADES_REGRADE_RATE_PER_HOUR: int = 30
    SCHEME_WRITE_RATE_PER_HOUR: int = 100
    SCHEME_PREVIEW_RATE_PER_MIN: int = 60

    # --- Phase 5 S3 ---
    # --- Phase 5 S4 settings (storage guard) --- (R2 free-tier guard, docs/phases/PHASE_5_DESIGN.md section 6;
    # ASSET_MAX_UPLOAD_BYTES = 2 MiB is set above by S2)
    STORAGE_WARN_BYTES: int = 8 * 1024 ** 3  # 8 GiB: admin warning
    STORAGE_HARD_BYTES: int = int(9.5 * 1024 ** 3)  # 9.5 GiB: new blobs refused (storage_full, HTTP 507)
    FILE_MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024  # PDF files
    FILE_ALLOWED_MIMES: list[str] = ["application/pdf"]
    STORAGE_SMOKE_RATE_PER_HOUR: int = 5
    # --- Phase 5 S4 end ---

    # Password hashing cost (bcrypt). 10 is OWASP's minimum and ~4x faster than 12 on small servers.
    BCRYPT_ROUNDS: int = 10

    # Email delivery: "resend", "brevo", "smtp" or "console" (prints to the server log).
    # Empty = pick automatically from whichever credentials are set.
    # Note: Render free instances block outbound SMTP ports, so use an HTTP API (Resend/Brevo) there.
    EMAIL_PROVIDER: str = ""
    EMAIL_FROM: str = ""             # e.g. "noreply@yourdomain.kg" (must be verified with the provider)
    EMAIL_FROM_NAME: str = "ОРТ Платформа"
    RESEND_API_KEY: str = ""
    BREVO_API_KEY: str = ""

    # Email one-time codes (registration) and password reset
    EMAIL_CODE_TTL_MINUTES: int = 10
    EMAIL_CODE_MAX_ATTEMPTS: int = 5
    EMAIL_RESEND_COOLDOWN_SECONDS: int = 60
    PASSWORD_RESET_TTL_MINUTES: int = 60

    # SMTP Email Configuration & Reset Flow
    SMTP_SERVER: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@ort.kg"
    FRONTEND_URL: str = "http://localhost:3000"

    # --- Phase 5 S1 begin ---
    # Seed the ORT courses from sample_ort_questions{,_ru}.csv when they have no bank (P5-4).
    # None: follows the environment (on unless ENVIRONMENT=production). Never seeds in production.
    ORT_SEED_SAMPLES: bool | None = None
    # --- Phase 5 S1 end ---

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

DEFAULT_SECRET_KEY = "ort_secret_jwt_key_2026_super_secure_academic_prep"


def is_production() -> bool:
    return settings.ENVIRONMENT.strip().lower() == "production"
