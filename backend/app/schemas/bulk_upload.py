from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.schemas.question import QuestionCreate


class RowValidationError(BaseModel):
    rowNumber: int
    field: Optional[str] = None
    errorMessage: str
    rawData: Dict[str, Any] = {}


class CsvValidationReport(BaseModel):
    totalRows: int
    validRowsCount: int
    invalidRowsCount: int
    errors: List[RowValidationError] = []
    previewQuestions: List[QuestionCreate] = []


class CsvUploadResult(BaseModel):
    success: bool
    importedCount: int
    failedCount: int
    batchCount: int
    errors: List[RowValidationError] = []
    importedIds: List[str] = []
    createdTemplateId: Optional[str] = None
    mockTestTitle: Optional[str] = None
    examSetId: Optional[str] = None
    examSetTitle: Optional[str] = None
