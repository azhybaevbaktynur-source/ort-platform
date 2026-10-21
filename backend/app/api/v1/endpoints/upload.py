import os
import uuid
from fastapi import APIRouter, Depends, UploadFile, File
from app.core.security import require_instructor
from app.schemas.user import UserProfile
from app.core.exceptions import ValidationException
from app.services.storage_service import get_storage_service

router = APIRouter()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.post("", response_model=dict)
@router.post("/image", response_model=dict)
async def upload_file(
    file: UploadFile = File(...),
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Accepts image file uploads (diagrams, geometry figures, reading passages)
    and saves them via the cloud-ready StorageService interface.
    Returns public access URL for frontend display.
    """
    if not file.filename:
        raise ValidationException("Файл тандалган жок / Файл не выбран")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationException(
            f"Формат колдоого алынбайт ({ext}). Колдоого алынган форматтар: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    safe_name = f"img_{uuid.uuid4().hex[:12]}{ext}"
    content = await file.read()
    if not content:
        raise ValidationException("Файл бош / Файл пустой")

    storage = get_storage_service()
    public_url = await storage.upload_file(content, safe_name, content_type=file.content_type)

    return {
        "url": public_url,
        "imageUrl": public_url,
        "filename": safe_name,
        "size": len(content),
    }
