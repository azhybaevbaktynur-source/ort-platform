from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "ORT / ЖРТ Test-Prep Platform"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # CORS & Allowed Origins
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    @field_validator("ALLOWED_ORIGINS", "BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(i).strip() for i in v if str(i).strip()]
        return v

    # Relational Database (SQLite for local dev, swappable to PostgreSQL on Render)
    DATABASE_URL: str = "sqlite:///./test.db"

    # Cloud Storage (Ephemeral local storage vs S3 / Cloudinary)
    STORAGE_ENV: str = "local"  # "local", "s3", "cloudinary"
    STORAGE_BASE_URL: str = "/uploads"

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

    # SMTP Email Configuration & Reset Flow
    SMTP_SERVER: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@ort.kg"
    FRONTEND_URL: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
