import re
from typing import Any, List, Optional, Tuple

from app.core.config import settings
from app.schemas.bulk_upload import RowValidationError
from app.schemas.question import QuestionCreate
from app.services.csv_service import CsvService, get_field_value

IMAGE_NOT_INCLUDED_MESSAGE = (
    "Сүрөт кошулган эмес — zip-топтомду жүктөңүз / "
    "Изображение не включено — загрузите zip-архив (image not included — upload the zip bundle)"
)


def is_stored_image_url(value: str) -> bool:
    """A plain CSV can only point at images that are already online: http(s) links or our own /uploads/... paths."""
    base = settings.STORAGE_BASE_URL.rstrip("/") + "/"
    return bool(re.match(r"^https?://", value, re.IGNORECASE)) or value.startswith(base)


class PlainCsvService(CsvService):
    """
    CSV upload as before, plus the bundle-format rule for images (docs/BUNDLE_FORMAT.md section 6):
    an image_url that is only a file name means the image file is missing, so the row is rejected
    instead of saving a broken link.
    """

    @classmethod
    def validate_row(
        cls,
        row: Any,
        row_number: int,
        language: str = "ky",
        exam_id: Optional[str] = None,
    ) -> Tuple[Optional[QuestionCreate], List[RowValidationError]]:
        question, errors = super().validate_row(row, row_number, language=language, exam_id=exam_id)

        raw_dict = row if isinstance(row, dict) else row.to_dict()
        image_value = get_field_value(raw_dict, "image_url", language)
        if image_value and not is_stored_image_url(image_value):
            errors = list(errors) + [
                RowValidationError(
                    rowNumber=row_number,
                    field="image_url",
                    errorMessage=f"{IMAGE_NOT_INCLUDED_MESSAGE}: '{image_value}'",
                    rawData=raw_dict,
                )
            ]
            return None, errors
        return question, errors
