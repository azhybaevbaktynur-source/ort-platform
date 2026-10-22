"""Import options and report shapes (design section 5, snake_case)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

EXAM_TYPES = ("full_main", "subject", "practice_bank")


class ImportOptions(BaseModel):
    """exam_type set -> ORT preset (P2-20); empty -> general mode."""

    exam_type: Optional[Literal["full_main", "subject", "practice_bank"]] = None
    language: str = "ky"
    on_conflict: Literal["skip", "overwrite"] = "skip"
    target_bank_id: Optional[str] = None
    # course.languages; None disables the language_not_in_course check
    allowed_languages: Optional[list[str]] = None

    @property
    def ort(self) -> bool:
        return self.exam_type is not None


class ImportIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    bundle: Optional[str] = None
    file: Optional[str] = None
    row: Optional[int] = None
    column: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)


class ImportBankSummary(BaseModel):
    root: str
    source_id: Optional[str] = None
    has_manifest: bool
    language: str
    bank_id: Optional[str] = None
    bank_title: str
    bank_exists: bool = False
    question_count: int = 0
    sections: dict[str, int] = Field(default_factory=dict)
    created: dict[str, int] = Field(default_factory=dict)
    updated: dict[str, int] = Field(default_factory=dict)
    unchanged: dict[str, int] = Field(default_factory=dict)
    conflicts: dict[str, int] = Field(default_factory=dict)
    skipped_deleted: dict[str, int] = Field(default_factory=dict)
    images: int = 0


class ImportReport(BaseModel):
    ok: bool
    committed: bool = False
    banks: list[ImportBankSummary] = Field(default_factory=list)
    errors: list[ImportIssue] = Field(default_factory=list)
    warnings: list[ImportIssue] = Field(default_factory=list)
    images_total: int = 0
    images_new: int = 0
    images_existing: int = 0
