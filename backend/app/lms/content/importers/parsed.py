"""Normalized intermediate results of parsing (pure data, no DB)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .schemas import ImportIssue


class Issues:
    def __init__(self) -> None:
        self.errors: list[ImportIssue] = []
        self.warnings: list[ImportIssue] = []

    def error(self, code: str, message: str, **kw: Any) -> ImportIssue:
        issue = ImportIssue(severity="error", code=code, message=message, **kw)
        self.errors.append(issue)
        return issue

    def warning(self, code: str, message: str, **kw: Any) -> ImportIssue:
        issue = ImportIssue(severity="warning", code=code, message=message, **kw)
        self.warnings.append(issue)
        return issue


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
