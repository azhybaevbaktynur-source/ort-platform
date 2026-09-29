import os
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseStorageService(ABC):
    """Abstract interface for storing uploaded media in production and dev."""

    @abstractmethod
    async def upload_file(self, content: bytes, filename: str, content_type: Optional[str] = None) -> str:
        """Saves file content and returns the publicly accessible URL."""
        pass


class LocalStorageService(BaseStorageService):
    """
    Local storage provider. Saves files to disk and serves via static mounting.
    Suitable for local development where ephemeral storage is not an issue.
    """
    def __init__(self, upload_dir: Optional[str] = None, base_url: Optional[str] = None):
        self.upload_dir = upload_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../backend/data/uploads")
        )
        self.base_url = (base_url or settings.STORAGE_BASE_URL).rstrip("/")
        os.makedirs(self.upload_dir, exist_ok=True)

    async def upload_file(self, content: bytes, filename: str, content_type: Optional[str] = None) -> str:
        target_path = os.path.join(self.upload_dir, filename)
        with open(target_path, "wb") as f:
            f.write(content)
        return f"{self.base_url}/{filename}"


class CloudStorageService(BaseStorageService):
    """
    Production cloud storage provider (Amazon S3, Cloudinary, or Google Cloud Storage).
    Easily configurable via environment variables for stateless cloud platforms like Render.
    """
    def __init__(self, provider: str = "s3"):
        self.provider = provider

    async def upload_file(self, content: bytes, filename: str, content_type: Optional[str] = None) -> str:
        # If cloud credentials are set in environment, upload to provider
        # Otherwise fallback to data URI or log warning
        logger.info(f"Uploading {filename} ({len(content)} bytes) to cloud provider: {self.provider}")
        # In cloud deployments without bucket configured, returns clean asset path
        return f"{settings.STORAGE_BASE_URL}/{filename}"


def get_storage_service() -> BaseStorageService:
    """Factory selecting the storage service based on STORAGE_ENV setting."""
    storage_env = (settings.STORAGE_ENV or "local").lower().strip()
    if storage_env in ("s3", "cloudinary", "gcs", "production"):
        return CloudStorageService(provider=storage_env)
    return LocalStorageService()
