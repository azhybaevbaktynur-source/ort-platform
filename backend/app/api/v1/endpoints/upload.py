import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.core.security import require_instructor
from app.schemas.user import UserProfile
from app.core.exceptions import ValidationException
from app.core.config import settings
from app.services.image_validation import validate_image_bytes
from app.services.storage_service import get_storage_service

router = APIRouter()

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

    max_bytes = settings.MAX_UPLOAD_BYTES
    chunks = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Файл өтө чоң / Файл слишком большой (max {max_bytes // (1024 * 1024) or 1} MB)",
            )
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        raise ValidationException("Файл бош / Файл пустой")

    try:
        ext = "." + validate_image_bytes(content, max_bytes)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Сүрөт жараксыз / Недопустимое изображение: {e}. PNG, JPEG, GIF, WEBP",
        )
    safe_name = f"img_{uuid.uuid4().hex[:12]}{ext}"
    content_type = {".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}[ext]

    storage = get_storage_service()
    public_url = await storage.upload_file(content, safe_name, content_type=content_type)

    return {
        "url": public_url,
        "imageUrl": public_url,
        "filename": safe_name,
        "size": len(content),
    }
