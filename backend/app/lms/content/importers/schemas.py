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
    # --- Phase 7b S3 begin --- (general format validated against an exam template version, PHASE_7B_DESIGN 8;
    # the ORT branch (exam_type set) never reads these)
    exam_template_version_id: Optional[str] = None
    assessment_id: Optional[str] = None             # validate against this assessment's template version
    attach_to_assessment_id: Optional[str] = None   # commit only: add the imported questions to its sections
    # --- Phase 7b S3 end ---

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


# --- Phase 7b S3 begin --- (attach step result, PHASE_7B_DESIGN 8; the route returns ImportResult)
class ImportAttachSummary(BaseModel):
    assessment_id: str
    added: int = 0
    sections: dict[str, int] = Field(default_factory=dict)   # section label -> questions added
    skipped: dict[str, int] = Field(default_factory=dict)    # skip code -> count (item_duplicate, too_many_items...)
    # --- Phase 7b S7 --- section label -> 0-based section position (the UI shows the exam's section title);
    # too_many_items per section: {code, section, position, max, scope: "section" | "exam", count}
    section_positions: dict[str, int] = Field(default_factory=dict)
    skip_details: list[dict] = Field(default_factory=list)


class ImportResult(ImportReport):
    """ImportReport plus the attach summary (null unless `attach_to_assessment_id` was committed)."""
    attached: Optional[ImportAttachSummary] = None
# --- Phase 7b S3 end ---
