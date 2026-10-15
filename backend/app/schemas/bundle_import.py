from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel


class BundleIssue(BaseModel):
    """
    One error or warning found while checking a question bundle (.zip).
    `code` lets the frontend show a translated (ky/ru) message; `message` is the English fallback.
    `row` is the 1-based data row in the questions CSV (header not counted), as in manifest.json.
    """
    severity: Literal["error", "warning"]
    code: str
    message: str
    bundle: Optional[str] = None
    file: Optional[str] = None
    row: Optional[int] = None
    column: Optional[str] = None
    params: Dict[str, Any] = {}


class BundleSummary(BaseModel):
    root: str
    sourceId: Optional[str] = None
    hasManifest: bool
    language: str
    examSetId: str
    examSetTitle: str
    examSetExists: bool = False
    questionCount: int
    sections: Dict[str, int] = {}
    created: Dict[str, int] = {}
    updated: Dict[str, int] = {}
    images: int = 0


class BundleImportReport(BaseModel):
    """Returned by both the preview (committed=False) and the import (committed=True on success)."""
    ok: bool
    committed: bool = False
    bundles: List[BundleSummary] = []
    errors: List[BundleIssue] = []
    warnings: List[BundleIssue] = []
    imagesTotal: int = 0
    imagesNew: int = 0
    imagesExisting: int = 0
