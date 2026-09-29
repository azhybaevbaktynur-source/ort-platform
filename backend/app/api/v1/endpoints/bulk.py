import logging
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from app.core.security import require_instructor
from app.schemas.user import UserProfile
from app.schemas.bulk_upload import CsvValidationReport, CsvUploadResult, RowValidationError
from app.services.csv_service import CsvService

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
