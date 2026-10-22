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

    # Cloud Storage (Ephemeral local storage vs S3 / Cloudinary)
    STORAGE_ENV: str = "local"  # "local", "s3", "cloudinary"
    STORAGE_BASE_URL: str = "/uploads"
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # Hard cap for image uploads
    LOCAL_UPLOAD_DIR: str = ""  # Overrides backend/data/uploads (used by tests to keep dev uploads clean)

    # Firebase (Legacy compatibility / Auth)
    FIREBASE_PROJECT_ID: str = "ort-platform-dev"
    FIREBASE_CREDENTIALS_PATH: str = ""
    FIREBASE_MOCK_MODE: bool = True

    # JWT Authentication
    SECRET_KEY: str = "ort_secret_jwt_key_2026_super_secure_academic_prep"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Test settings
    GOLDEN_CERTIFICATE_MIN_SCORE: int = 219
    TOTAL_ORT_QUESTIONS: int = 150

    # Dev/test shortcut tokens ("mock_admin_token" etc.). NEVER enable in production:
    # anyone who knows the token string would get that role.
    ALLOW_MOCK_TOKENS: bool = False

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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

DEFAULT_SECRET_KEY = "ort_secret_jwt_key_2026_super_secure_academic_prep"


def is_production() -> bool:
    return settings.ENVIRONMENT.strip().lower() == "production"
