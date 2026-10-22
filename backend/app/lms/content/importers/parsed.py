"""Normalized intermediate results of parsing (pure data, no DB)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.config import settings

from .schemas import ImportIssue


class Issues:
    """Collected issues, capped (settings.IMPORT_MAX_ISSUES each for errors and warnings).

    `n_errors` / `n_warnings` are the true counts; `finalize()` adds one `too_many_issues` entry with them."""

    def __init__(self) -> None:
        self.errors: list[ImportIssue] = []
        self.warnings: list[ImportIssue] = []
        self.n_errors = 0
        self.n_warnings = 0

    def add_error(self, issue: ImportIssue) -> ImportIssue:
        self.n_errors += 1
        if len(self.errors) < settings.IMPORT_MAX_ISSUES:
            self.errors.append(issue)
        return issue

    def add_warning(self, issue: ImportIssue) -> ImportIssue:
        self.n_warnings += 1
        if len(self.warnings) < settings.IMPORT_MAX_ISSUES:
            self.warnings.append(issue)
        return issue

    def error(self, code: str, message: str, **kw: Any) -> ImportIssue:
        return self.add_error(ImportIssue(severity="error", code=code, message=message, **kw))

    def warning(self, code: str, message: str, **kw: Any) -> ImportIssue:
        return self.add_warning(ImportIssue(severity="warning", code=code, message=message, **kw))

    def too_many_rows(self, **kw: Any) -> ImportIssue:
        cap = settings.IMPORT_MAX_ROWS
        return self.error("too_many_rows", f"The upload has more than {cap} rows; the limit is {cap}.",
                          params={"limit": cap, "got": cap + 1, "truncated": True}, **kw)

    def finalize(self) -> None:
        """Add (or refresh) the single `too_many_issues` marker when something was dropped."""
        cap = settings.IMPORT_MAX_ISSUES
        for lst, total, sev in ((self.errors, self.n_errors, "error"), (self.warnings, self.n_warnings, "warning")):
            lst[:] = [i for i in lst if i.code != "too_many_issues"]
            if total > cap:
                lst.append(ImportIssue(
                    severity=sev, code="too_many_issues",
                    message=f"Only the first {cap} {sev}s are shown ({total} in total).",
                    params={"shown": cap, "errors_total": self.n_errors, "warnings_total": self.n_warnings}))


@dataclass
class ParsedImage:
    """An image found in the zip. `content` is the ORIGINAL bytes; encoding to WebP happens in the writer."""
    path: str
    source_sha256: str
    content: bytes
    format: str          # PNG | JPEG | WEBP | GIF
    width: int
    height: int


@dataclass
class ParsedPassage:
    key: str                         # normalized passage text
    text: str
    first_row: int
    source_ref: Optional[str] = None  # "{first external_id}#passage" with a manifest


@dataclass
class ParsedItem:
    """One question row (design ImportRow), mapped to a C2 type payload."""
    row: int                              # 1-based data row (header not counted)
    position: int                         # = row (P2-25); CSV append adds max(position) in the writer
    source_ref: Optional[str]             # manifest external_id
    section: str                          # ORT section, or free label in general mode
    topic: str
    difficulty: str
    q_num: Optional[str]
    type: str                             # "comparison" | "single_choice"
    payload: dict                         # validated by get_type(type).validate(); no image refs
    stem: str
    explanation: Optional[str]
    correct: str
    tags: list[str] = field(default_factory=list)
    image: Optional[ParsedImage] = None
    passage_key: Optional[str] = None
    fixed: bool = False
    source_page: Optional[int] = None
    options: dict[str, str] = field(default_factory=dict)     # raw A..E (empty for comparison)
    column_a: str = ""
    column_b: str = ""


ImportRow = ParsedItem


@dataclass
class ParsedBundle:
    root: str                         # "" for a plain CSV
    has_manifest: bool
    source_id: Optional[str]
    language: str
    questions_path: str               # file name for a plain CSV
    title: str                        # source_id, else folder / CSV file stem
    items: list[ParsedItem] = field(default_factory=list)
    passages: list[ParsedPassage] = field(default_factory=list)
    images: dict[str, ParsedImage] = field(default_factory=dict)   # path -> image used by rows


@dataclass
class ParsedUpload:
    kind: str                         # "zip" | "csv"
    bundles: list[ParsedBundle]
    issues: Issues

    @property
    def distinct_images(self) -> dict[str, ParsedImage]:
        out: dict[str, ParsedImage] = {}
        for b in self.bundles:
            for img in b.images.values():
                out.setdefault(img.source_sha256, img)
        return out
