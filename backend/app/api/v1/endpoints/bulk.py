import logging
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from app.core.security import require_instructor
from app.schemas.user import UserProfile
from app.schemas.bulk_upload import CsvValidationReport, CsvUploadResult, RowValidationError
from app.schemas.bundle_import import BundleImportReport, BundleIssue
from app.services.bundle_service import BundleService, MAX_ZIP_BYTES
from app.services.csv_image_rule import PlainCsvService as CsvService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/validate-csv", response_model=CsvValidationReport)
async def validate_csv_upload(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    exam_id: Optional[str] = Form(None),
    exam_set_id: Optional[str] = Form(None),
    lang: Optional[str] = Query(None),
    query_language: Optional[str] = Query(None, alias="language"),
    query_exam_id: Optional[str] = Query(None, alias="exam_id"),
    query_exam_set_id: Optional[str] = Query(None, alias="exam_set_id"),
    query_examId: Optional[str] = Query(None, alias="examId"),
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Dry-run validation for 12,000+ question bulk CSV uploads.
    Validates UTF-8 encoding, Cyrillic letters (Ң, Ө, Ү), LaTeX formatting,
    and schema correctness without writing to the database.
    Never throws a 500 error; returns a 200 OK with detailed validation results.
    """
    filename = (file.filename or "").lower()
    if not (filename.endswith(".csv") or filename.endswith(".txt") or file.content_type in ("text/csv", "text/plain", "application/vnd.ms-excel")):
        return CsvValidationReport(
            totalRows=0,
            validRowsCount=0,
            invalidRowsCount=0,
            errors=[
                RowValidationError(
                    rowNumber=0,
                    field="file",
                    errorMessage="Only CSV files (.csv) are accepted.",
                    rawData={},
                )
            ],
            previewQuestions=[],
        )

    try:
        contents = await file.read()
    except Exception as e:
        logger.warning(f"Error reading uploaded CSV file: {e}")
        return CsvValidationReport(
            totalRows=0,
            validRowsCount=0,
            invalidRowsCount=0,
            errors=[
                RowValidationError(
                    rowNumber=0,
                    field="file",
                    errorMessage=f"Could not read uploaded file: {str(e)}",
                    rawData={},
                )
            ],
            previewQuestions=[],
        )

    if not contents:
        return CsvValidationReport(
            totalRows=0,
            validRowsCount=0,
            invalidRowsCount=0,
            errors=[
                RowValidationError(
                    rowNumber=0,
                    field="file",
                    errorMessage="The uploaded CSV file is empty.",
                    rawData={},
                )
            ],
            previewQuestions=[],
        )

    target_language = language or query_language or lang or "ky"
    target_exam_id = (exam_id or exam_set_id or query_exam_id or query_exam_set_id or query_examId or "").strip() or None

    try:
        return CsvService.validate_csv(
            file_bytes=contents,
            language=target_language,
            exam_id=target_exam_id,
            max_preview=25,
        )
    except Exception as e:
        logger.exception(f"Unexpected error in validate_csv: {e}")
        return CsvValidationReport(
            totalRows=0,
            validRowsCount=0,
            invalidRowsCount=0,
            errors=[
                RowValidationError(
                    rowNumber=0,
                    field="system",
                    errorMessage=f"Validation failed: {str(e)}",
                    rawData={},
                )
            ],
            previewQuestions=[],
        )


@router.post("/upload-csv", response_model=CsvUploadResult)
async def upload_csv_batch(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    exam_id: Optional[str] = Form(None),
    exam_set_id: Optional[str] = Form(None),
    mock_test_title: Optional[str] = Form(None),
    exam_type: Optional[str] = Form("full_main"),
    lang: Optional[str] = Query(None),
    query_language: Optional[str] = Query(None, alias="language"),
    query_exam_id: Optional[str] = Query(None, alias="exam_id"),
    query_exam_set_id: Optional[str] = Query(None, alias="exam_set_id"),
    query_examId: Optional[str] = Query(None, alias="examId"),
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Commits valid CSV questions to Firestore in chunked batches of 450 operations.
    All questions are strictly bound to an ExamSet.
    Never throws a 500 error; returns a 200 OK with success/failure report.
    """
    filename = (file.filename or "").lower()
    target_exam_id = (exam_id or exam_set_id or query_exam_id or query_exam_set_id or query_examId or "").strip() or None
    target_language = language or query_language or lang or "ky"

    if not (filename.endswith(".csv") or filename.endswith(".txt") or file.content_type in ("text/csv", "text/plain", "application/vnd.ms-excel")):
        return CsvUploadResult(
            success=False,
            importedCount=0,
            failedCount=0,
            batchCount=0,
            errors=[
                RowValidationError(
                    rowNumber=0,
                    field="file",
                    errorMessage="Only CSV files (.csv) are accepted.",
                    rawData={},
                )
            ],
            importedIds=[],
            createdTemplateId=target_exam_id,
            mockTestTitle=mock_test_title,
            examSetId=target_exam_id,
            examSetTitle=mock_test_title,
        )

    try:
        contents = await file.read()
    except Exception as e:
        logger.warning(f"Error reading uploaded CSV file: {e}")
        return CsvUploadResult(
            success=False,
            importedCount=0,
            failedCount=0,
            batchCount=0,
            errors=[
                RowValidationError(
                    rowNumber=0,
                    field="file",
                    errorMessage=f"Could not read uploaded file: {str(e)}",
                    rawData={},
                )
            ],
            importedIds=[],
            createdTemplateId=target_exam_id,
            mockTestTitle=mock_test_title,
            examSetId=target_exam_id,
            examSetTitle=mock_test_title,
        )

    if not contents:
        return CsvUploadResult(
            success=False,
            importedCount=0,
            failedCount=0,
            batchCount=0,
            errors=[
                RowValidationError(
                    rowNumber=0,
                    field="file",
                    errorMessage="The uploaded CSV file is empty.",
                    rawData={},
                )
            ],
            importedIds=[],
            createdTemplateId=target_exam_id,
            mockTestTitle=mock_test_title,
            examSetId=target_exam_id,
            examSetTitle=mock_test_title,
        )

    try:
        return CsvService.ingest_csv(
            file_bytes=contents,
            created_by_user_id=current_user.id,
            batch_size=450,
            mock_test_title=mock_test_title,
            exam_set_id=target_exam_id,
            exam_id=target_exam_id,
            exam_type=exam_type or "full_main",
            language=target_language,
        )
    except Exception as e:
        logger.exception(f"Unexpected error in upload_csv_batch: {e}")
        return CsvUploadResult(
            success=False,
            importedCount=0,
            failedCount=0,
            batchCount=0,
            errors=[
                RowValidationError(
                    rowNumber=0,
                    field="system",
                    errorMessage=f"Upload failed: {str(e)}",
                    rawData={},
                )
            ],
            importedIds=[],
            createdTemplateId=target_exam_id,
            mockTestTitle=mock_test_title,
            examSetId=target_exam_id,
            examSetTitle=mock_test_title,
        )


def _bundle_file_error(code: str, message: str) -> BundleImportReport:
    return BundleImportReport(
        ok=False,
        committed=False,
        errors=[BundleIssue(severity="error", code=code, message=message)],
    )


async def _read_bundle_upload(file: UploadFile):
    """Reads an uploaded zip. The file name is never trusted; the content must be a zip archive."""
    try:
        contents = await file.read(MAX_ZIP_BYTES + 1)
    except Exception as e:
        logger.warning(f"Error reading uploaded bundle: {e}")
        return None, _bundle_file_error("file_unreadable", f"Could not read uploaded file: {e}")
    if not contents:
        return None, _bundle_file_error("file_empty", "The uploaded file is empty.")
    if len(contents) > MAX_ZIP_BYTES:
        return None, _bundle_file_error("zip_too_large", "The zip is larger than 200 MB.")
    if not contents.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return None, _bundle_file_error("zip_invalid", "The file is not a zip archive.")
    return contents, None


@router.post("/validate-bundle", response_model=BundleImportReport)
async def validate_bundle_upload(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Dry run for an ort-digitizer question bundle (.zip): finds the bundles, validates every row and
    image, and reports what an import would create or update. Nothing is saved.
    `language` is used only for bundles without manifest.json.
    """
    contents, error = await _read_bundle_upload(file)
    if error:
        return error
    try:
        return BundleService.preview(contents, language=language or "ky")
    except Exception as e:
        logger.exception(f"Unexpected error in validate_bundle_upload: {e}")
        return _bundle_file_error("system", f"Validation failed: {e}")


@router.post("/import-bundle", response_model=BundleImportReport)
async def import_bundle_upload(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Imports an ort-digitizer question bundle (.zip). Validates everything first; if any error exists,
    nothing is saved. Images go to content-addressed storage keys; questions are created or updated
    (matched by manifest external_id) in one database transaction, one exam set per source.
    """
    contents, error = await _read_bundle_upload(file)
    if error:
        return error
    try:
        return await BundleService.import_bundle(
            contents, language=language or "ky", created_by_user_id=current_user.id
        )
    except Exception as e:
        logger.exception(f"Unexpected error in import_bundle_upload: {e}")
        return _bundle_file_error("system", f"Import failed: {e}")
