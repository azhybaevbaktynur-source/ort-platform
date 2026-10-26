"""General import format v1 (PHASE_7B_DESIGN 8, EXAM_TEMPLATES_DESIGN 5): one CSV / zip format for all 7 question
types, optionally validated against an exam template version (`TemplateProfile`).

Pure (no DB, no storage): produces the same `ParsedBundle` / `ParsedItem` objects as the ORT parser, so the writer
(`service.py::_process_bundle`), image handling and the bank upsert are shared. The ORT files (`ort_csv.py`,
`bundle.py`, `rules.py`) are only imported, never changed.

- Plain CSV: header-driven (columns by name, any order, `image_url` = `image`, unknown columns are a warning).
  Rows whose first cell starts with `#` are comments (the downloadable example rows).
- Zip: `manifest.json` with `format: "lms-bundle"`, `format_version: 1`, `source_id`, optional `language`,
  `questions_file` (default `questions.csv`), `images_dir` (default `images/`), `question_count`; same `zipsafe`
  limits as the ORT bundle.
- Dispatch (`parse_general`, called first by `parse.py::parse_upload`): an `lms-bundle` manifest, a CSV with a
  `type` column, or a template profile select this format. Otherwise the upload goes to the ORT / legacy parser
  unchanged. An ORT file where the general format is required (and the reverse) fails with `format_mismatch`.
"""
from __future__ import annotations

import csv
import io
import json
import posixpath
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from app.core.config import settings
from app.lms.content.richtext import EXPLANATION_MAX, PASSAGE_BODY_MAX, STEM_MAX, clean_text
from app.lms.content.types import REGISTRY, TYPE_NAMES
from app.lms.content.types.base import ImportRowError
from app.lms.core.errors import ValidationFailed
from app.lms.core.types import SUPPORTED_LANGUAGES

from .bundle import (
    BUNDLE_FORMAT, IMAGE_EXTENSIONS, check_image, display_root, image_base_name, is_external_image, join, resolve_image,
)
from .ort_csv import BUNDLE_COLUMNS, DIFFICULTY_ALIASES, VALID_DIFFICULTIES, _clean_import_tags, decode_bytes, read_records
from .parsed import Issues, ParsedBundle, ParsedImage, ParsedItem, ParsedPassage
from .schemas import ImportOptions
from .zipsafe import BundleError, SafeZip

GENERAL_FORMAT = "lms-bundle"
GENERAL_FORMAT_VERSION = 1

COMMON_COLUMNS = ("section", "type", "stem", "explanation", "topic", "difficulty", "tags", "image", "external_id")
PASSAGE_COLUMNS = ("passage_text", "passage_ref")
COLUMN_ALIASES = {"image_url": "image"}
SECTION_LABEL_MAX = 40
EXTERNAL_ID_MAX = 180          # bank_questions.source_ref is 200; passages use "<external_id>#passage"
POINTS_MAX = Decimal("1000")
# C0 controls except \n and \t, and DEL: stripped from every cell (PostgreSQL text refuses NUL; same set as
# richtext.clean_text, applied to metadata cells too)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

E_FORMAT_MISMATCH = "format_mismatch"
E_SECTION_NOT_IN_TEMPLATE = "section_not_in_template"
E_TYPE_NOT_ALLOWED = "type_not_allowed_in_section"
E_PASSAGE_NOT_ALLOWED = "passage_not_allowed"
E_TYPE_REQUIRED = "type_required"
E_COUNT_BELOW_MIN = "count_below_min"
E_COUNT_ABOVE_MAX = "count_above_max"


def type_columns() -> tuple[str, ...]:
    """Union of every type's `import_columns`, in registry order."""
    out: list[str] = []
    for t in REGISTRY.values():
        for c in t.import_columns:
            if c not in out:
                out.append(c)
    return tuple(out)


KNOWN_COLUMNS = frozenset(COMMON_COLUMNS) | frozenset(type_columns()) | frozenset(PASSAGE_COLUMNS)


# ------------------------------------------------------------------------------------------------ template profile

@dataclass(frozen=True)
class ProfileSection:
    """One section of a template version as the importer sees it (built by `exam_templates/import_format.py`)."""
    index: int                              # 0-based position in the template / assessment
    key: Optional[str]                      # section key (assessment key for parameter-bound sections)
    options: tuple[str, ...] = ()           # parameter options when the key is supplied at instantiate
    titles: tuple[str, ...] = ()            # titles in every language
    allowed_types: tuple[str, ...] = TYPE_NAMES
    allow_passages: bool = True
    min_items: Optional[int] = None
    max_items: Optional[int] = None

    @property
    def fallback_label(self) -> str:
        return f"section_{self.index + 1}"

    def label_for(self, raw: str) -> str:
        """The `bank_questions.section` label stored for a row matched to this section."""
        if self.key:
            return self.key[:SECTION_LABEL_MAX]
        low = raw.strip().casefold()
        for o in self.options:
            if o.casefold() == low:
                return o
        if self.titles:
            return self.titles[0].strip()[:SECTION_LABEL_MAX]
        return self.fallback_label

    def matches(self, raw: str) -> bool:
        low = raw.strip().casefold()
        if not low:
            return False
        if self.key and self.key.casefold() == low:
            return True
        if any(o.casefold() == low for o in self.options):
            return True
        if any(t.strip().casefold() == low for t in self.titles if t):
            return True
        return not self.key and not self.options and not self.titles and low == self.fallback_label


@dataclass(frozen=True)
class TemplateProfile:
    version_id: str
    sections: tuple[ProfileSection, ...]

    def match(self, raw: str) -> Optional[ProfileSection]:
        for s in self.sections:
            if s.matches(raw):
                return s
        return None


@dataclass
class GeneralItem(ParsedItem):
    """A ParsedItem with the row's `max_points` (the question's default points; None = 1 as for ORT)."""
    default_points: Optional[Decimal] = None
    profile_index: Optional[int] = None


# ------------------------------------------------------------------------------------------------ header and rows

def normalize_header(raw_header: list[str]) -> list[str]:
    out = []
    for c in raw_header:
        h = str(c).strip().lstrip("﻿").lower().replace(" ", "_").replace("-", "_")
        out.append(COLUMN_ALIASES.get(h, h))
    return out


def _is_ort_header(raw_header: list[str]) -> bool:
    return [str(c).strip() for c in raw_header] == BUNDLE_COLUMNS


def _is_comment(rec: list[str]) -> bool:
    return bool(rec) and str(rec[0]).lstrip().startswith("#")


@dataclass
class _RowCtx:
    issues: Issues
    file: str
    bundle: Optional[str]
    language: str
    profile: Optional[TemplateProfile]
    image_for: Callable[[str, int], Optional[ParsedImage]]
    seen_external: dict[str, int] = field(default_factory=dict)

    def error(self, code: str, message: str, row: Optional[int] = None, column: Optional[str] = None,
              **params) -> None:
        self.issues.error(code, message, row=row, column=column, file=self.file, bundle=self.bundle,
                          params=params)


def _points(value: str) -> Decimal:
    try:
        p = Decimal(value.replace(",", "."))
    except InvalidOperation:
        raise ValueError("max_points must be a number") from None
    if not p.is_finite() or p < 0 or p > POINTS_MAX:
        raise ValueError("max_points must be between 0 and 1000")
    return p


def _parse_row(c: _RowCtx, raw: dict, n: int) -> tuple[Optional[GeneralItem], Optional[str], Optional[str],
                                                         Optional[str]]:
    """(item | None, passage text, passage_ref, external_id). Errors go to `c.issues`."""
    g = lambda k: (raw.get(k) or "").strip()  # noqa: E731
    errors_before = c.issues.n_errors
    sec_raw = g("section")
    psec: Optional[ProfileSection] = None
    if c.profile is not None:
        if not sec_raw and len(c.profile.sections) == 1:
            psec = c.profile.sections[0]
        else:
            psec = c.profile.match(sec_raw)
        if psec is None:
            c.error(E_SECTION_NOT_IN_TEMPLATE, f"Section '{sec_raw[:60]}' is not a section of the exam template.",
                    n, "section", section=sec_raw[:60])
            return None, None, None, None
        section = psec.label_for(sec_raw)
    else:
        section = sec_raw
        if len(section) > SECTION_LABEL_MAX:
            c.error("row_invalid", f"section must be at most {SECTION_LABEL_MAX} characters.", n, "section")
            return None, None, None, None

    tname = g("type").lower()
    if not tname:
        if psec is not None and len(psec.allowed_types) == 1:
            tname = psec.allowed_types[0]
        else:
            c.error(E_TYPE_REQUIRED, "type is required (" + ", ".join(psec.allowed_types if psec else TYPE_NAMES)
                    + ").", n, "type")
            return None, None, None, None
    if tname not in REGISTRY:
        c.error("type_unknown", f"Unknown type '{tname[:40]}'. Must be one of: {', '.join(TYPE_NAMES)}.", n, "type",
                type=tname[:40])
        return None, None, None, None
    if psec is not None and tname not in psec.allowed_types:
        c.error(E_TYPE_NOT_ALLOWED, f"Type '{tname}' is not allowed in section '{section}'.", n, "type",
                type=tname, section=section, allowed=list(psec.allowed_types))
        return None, None, None, None
    qt = REGISTRY[tname]

    ptext, pref = g("passage_text"), g("passage_ref")
    if ptext or pref:
        col = "passage_text" if ptext else "passage_ref"
        if ptext and pref:
            c.error("row_invalid", "Use passage_text or passage_ref, not both.", n, "passage_ref")
        elif psec is not None and not psec.allow_passages:
            c.error(E_PASSAGE_NOT_ALLOWED, f"Section '{section}' does not allow passages.", n, col, section=section)
        elif not qt.supports_passages:
            c.error(E_PASSAGE_NOT_ALLOWED, f"Questions of type '{tname}' cannot belong to a passage.", n, col,
                    type=tname)

    stem = g("stem")
    if not stem and tname != "comparison":
        c.error("row_invalid", "Required field 'stem' is missing or empty.", n, "stem")

    try:
        payload = qt.validate(qt.from_import_row(raw))
    except ImportRowError as e:
        c.error("row_invalid", e.message, n, e.column)
        payload = None
    except ValidationFailed as exc:
        for d in exc.details or [{"loc": [], "msg": exc.message}]:
            loc = [str(p) for p in d.get("loc", [])]
            c.error("row_invalid", f"{'.'.join(loc)}: {d.get('msg')}".strip(": "), n, None, loc=loc)
        payload = None

    points: Optional[Decimal] = None
    if g("max_points"):
        try:
            points = _points(g("max_points"))
        except ValueError as e:
            c.error("row_invalid", str(e) + ".", n, "max_points")

    ext = g("external_id") or None
    if ext is not None:
        if len(ext) > EXTERNAL_ID_MAX:
            c.error("row_invalid", f"external_id must be at most {EXTERNAL_ID_MAX} characters.", n, "external_id")
            ext = None
        elif ext in c.seen_external:
            c.error("duplicate_external_id", f"external_id '{ext}' is used by rows {c.seen_external[ext]} and {n}.",
                    n, "external_id", external_id=ext)
            ext = None
        else:
            c.seen_external[ext] = n

    try:
        stem = clean_text(stem, STEM_MAX)
        explanation = clean_text(g("explanation"), EXPLANATION_MAX) if g("explanation") else None
        ptext = clean_text(ptext, PASSAGE_BODY_MAX) if ptext else ""
    except ValueError as e:
        c.error("row_invalid", str(e), n, "stem")
        return None, None, None, None

    image = None
    image_value = g("image")
    if image_value:
        image = c.image_for(image_value, n)

    if c.issues.n_errors != errors_before or payload is None:
        return None, None, None, None
    diff_raw = g("difficulty").lower()
    difficulty = DIFFICULTY_ALIASES.get(diff_raw, diff_raw)
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = "medium"
    item = GeneralItem(
        row=n, position=n, source_ref=ext, section=section, topic=g("topic") or "General", difficulty=difficulty,
        q_num=None, type=tname, payload=payload, stem=stem, explanation=explanation,
        correct=str(payload.get("correct", "")) if isinstance(payload, dict) else "",
        tags=_clean_import_tags(g("tags")), image=image,
        options={ch["id"]: ch["text"] for ch in payload.get("choices", [])} if isinstance(payload, dict) else {},
        column_a=payload.get("column_a", "") if isinstance(payload, dict) else "",
        column_b=payload.get("column_b", "") if isinstance(payload, dict) else "",
        default_points=points, profile_index=psec.index if psec is not None else None,
    )
    return item, ptext or None, pref or None, ext


def parse_rows(header: list[str], records: list[list[str]], bundle: ParsedBundle, issues: Issues,
               profile: Optional[TemplateProfile], image_for: Callable[[str, int], Optional[ParsedImage]],
               *, broot: Optional[str] = None) -> None:
    """Fill `bundle.items` / `bundle.passages` from header-driven records (comment rows skipped)."""
    c = _RowCtx(issues, bundle.questions_path, broot, bundle.language, profile, image_for)
    cols = normalize_header(header)
    seen: set[str] = set()
    for i, h in enumerate(cols):
        if h in seen:
            c.error("csv_header_duplicate", f"Column '{h[:40]}' appears twice in the header.", column=h[:40])
        seen.add(h)
        if h and h not in KNOWN_COLUMNS:
            issues.warning("unknown_column", f"Unknown column '{h[:40]}' is ignored.", column=h[:40],
                           file=bundle.questions_path, bundle=broot)
    if issues.errors:
        return
    if "type" not in seen and profile is None:
        c.error(E_TYPE_REQUIRED, "The header needs a 'type' column (or choose an exam template to validate against).",
                column="type")
        return
    passages: dict[str, ParsedPassage] = {}
    by_ref: dict[str, str] = {}           # "<external_id>#passage" -> passage key
    pending: list[tuple[GeneralItem, str]] = []
    n = 0
    for rec in records:
        if _is_comment(rec):
            continue
        n += 1
        raw = {h: _CONTROL_RE.sub("", v) for h, v in zip(cols, (rec + [""] * len(cols))[: len(cols)])
               if h in KNOWN_COLUMNS}
        item, ptext, pref, ext = _parse_row(c, raw, n)
        if item is None:
            continue
        if ptext:
            p = passages.get(ptext)
            if p is None:
                p = ParsedPassage(key=ptext, text=ptext, first_row=n, source_ref=f"{ext}#passage" if ext else None)
                passages[ptext] = p
                bundle.passages.append(p)
            item.passage_key = ptext
            if ext:
                by_ref[f"{ext}#passage"] = ptext
        elif pref:
            pending.append((item, pref if pref.endswith("#passage") else f"{pref}#passage"))
        bundle.items.append(item)
    dropped: set[int] = set()
    for item, ref in pending:
        key = by_ref.get(ref)
        if key is None:
            c.error("passage_ref_unknown", f"passage_ref '{ref[:80]}' does not name a row with passage_text.",
                    item.row, "passage_ref", passage_ref=ref[:80])
            dropped.add(id(item))
        else:
            item.passage_key = key
    if dropped:
        bundle.items[:] = [it for it in bundle.items if id(it) not in dropped]
    if profile is not None:
        _check_counts(bundle, issues, profile, broot)


def _check_counts(bundle: ParsedBundle, issues: Issues, profile: TemplateProfile, broot: Optional[str]) -> None:
    counts: dict[int, int] = {}
    for it in bundle.items:
        idx = getattr(it, "profile_index", None)
        if idx is not None:
            counts[idx] = counts.get(idx, 0) + 1
    for s in profile.sections:
        got = counts.get(s.index, 0)
        label = s.key or (s.titles[0] if s.titles else s.fallback_label)
        if s.min_items is not None and got < s.min_items:
            issues.warning(E_COUNT_BELOW_MIN, f"Section '{label}' has {got} question(s) in this file; the template "
                           f"asks for at least {s.min_items}.", file=bundle.questions_path, bundle=broot,
                           params={"section": label, "count": got, "min": s.min_items})
        if s.max_items is not None and got > s.max_items:
            issues.warning(E_COUNT_ABOVE_MAX, f"Section '{label}' has {got} question(s) in this file; the template "
                           f"allows at most {s.max_items}.", file=bundle.questions_path, bundle=broot,
                           params={"section": label, "count": got, "max": s.max_items})


# ------------------------------------------------------------------------------------------------ plain CSV

def _prefix_text(raw: bytes, n: int = 256 * 1024) -> str:
    """The first `n` bytes as text, for format detection only (never parsed as data)."""
    return raw[:n].decode("utf-8-sig", errors="ignore")


def _first_record_type(text: str) -> Optional[str]:
    """`type` cell of the first non-comment data row (None without a `type` column)."""
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if not header:
        return None
    cols = normalize_header(header)
    if "type" not in cols:
        return None
    i = cols.index("type")
    for k, rec in enumerate(reader):
        if k > 50:
            break
        if not rec or all(not x.strip() for x in rec) or _is_comment(rec):
            continue
        return (rec[i] if i < len(rec) else "").strip().lower()
    return ""


def _csv_header(text: str) -> list[str]:
    try:
        return next(csv.reader(io.StringIO(text[: 64 * 1024], newline="")), None) or []
    except csv.Error:
        return []


def _too_large(issues: Issues, filename: str, bundle: Optional[str] = None) -> None:
    mb = settings.IMPORT_MAX_CSV_BYTES // (1024 * 1024)
    issues.error("csv_too_large", f"The CSV is larger than {mb} MB.", file=filename, bundle=bundle,
                 params={"limit_mb": mb})


def _mismatch(issues: Issues, ort_file: bool, **kw) -> list:
    if ort_file:
        issues.error(E_FORMAT_MISMATCH, "This is an ORT file; choose the ORT format.", params={"expected": "general"},
                     **kw)
    else:
        issues.error(E_FORMAT_MISMATCH, "This is a general-format file; choose the general format.",
                     params={"expected": "ort"}, **kw)
    return []


def _parse_csv(raw: bytes, filename: str, opts: ImportOptions, profile: Optional[TemplateProfile],
               issues: Issues, text: str) -> list[ParsedBundle]:
    if opts.allowed_languages is not None and opts.language not in opts.allowed_languages:
        issues.error("language_not_in_course", f"Language '{opts.language}' is not enabled for this course.",
                     params={"language": opts.language})
        return []
    try:
        header, records, truncated = read_records(text, settings.IMPORT_MAX_ROWS, plain=True)
    except csv.Error as e:
        issues.error("csv_unreadable", f"CSV file parsing failed: {e}", file=filename)
        return []
    if truncated:
        issues.too_many_rows()
        return []
    stem = posixpath.splitext(posixpath.basename(filename or "questions.csv"))[0] or "questions"
    bundle = ParsedBundle(root="", has_manifest=False, source_id=None, language=opts.language,
                          questions_path=filename or "questions.csv", title=stem)

    def image_for(value: str, n: int) -> None:
        if is_external_image(value):
            issues.error("image_external_url", f"image '{value[:200]}' is an external link; external images are "
                         "not imported.", row=n, column="image", file=bundle.questions_path, params={"image": value[:200]})
        else:
            issues.error("image_not_included", f"Image not included - upload the zip bundle: "
                         f"'{image_base_name(value)[:200]}'.", row=n, column="image", file=bundle.questions_path,
                         params={"image": value[:200]})
        return None

    parse_rows(header, records, bundle, issues, profile, image_for)
    return [bundle]


# ------------------------------------------------------------------------------------------------ zip

def _manifests(zf: SafeZip, issues: Issues) -> tuple[list[tuple[str, dict]], bool]:
    """(lms-bundle manifests as (path, dict), whether an ORT manifest exists). Unreadable manifests are skipped
    here (the ORT parser reports them when it runs)."""
    general: list[tuple[str, dict]] = []
    ort = False
    for path in sorted(p for p in zf.entries if posixpath.basename(p) == "manifest.json"):
        if zf.entries[path].file_size > settings.IMPORT_MAX_MANIFEST_BYTES:
            continue
        try:
            m = json.loads(decode_bytes(zf.read(path), lenient=False) or "")
        except (ValueError, TypeError, RecursionError):
            continue
        finally:
            zf.drop(path)
        if isinstance(m, dict) and m.get("format") == GENERAL_FORMAT:
            general.append((path, m))
        elif isinstance(m, dict) and m.get("format") == BUNDLE_FORMAT:
            ort = True
    return general, ort


def _ort_csv_in_zip(zf: SafeZip) -> bool:
    from .bundle import csv_header

    return any(p.lower().endswith(".csv") and csv_header(zf.read_prefix(p, 64 * 1024)) == BUNDLE_COLUMNS
               for p in sorted(zf.entries))


def _parse_general_zip(zf: SafeZip, manifests: list[tuple[str, dict]], opts: ImportOptions,
                       profile: Optional[TemplateProfile], issues: Issues) -> list[ParsedBundle]:
    found: list[tuple[ParsedBundle, dict]] = []
    for path, m in manifests:
        root = posixpath.dirname(path)
        bd = display_root(root)
        version = m.get("format_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            issues.error("manifest_invalid", "manifest.json has no valid format_version.", bundle=bd, file=path)
            continue
        if version > GENERAL_FORMAT_VERSION:
            issues.error("manifest_version_unsupported",
                         f"Bundle format_version {version} is newer than this platform supports "
                         f"(max {GENERAL_FORMAT_VERSION}).", bundle=bd, file=path,
                         params={"version": version, "supported": GENERAL_FORMAT_VERSION})
            continue
        source_id = m.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip() or len(source_id.strip()) > 120:
            issues.error("manifest_invalid", "manifest.json needs a source_id of 1-120 characters.", bundle=bd,
                         file=path)
            continue
        language = m.get("language", opts.language)
        if language not in SUPPORTED_LANGUAGES:
            issues.error("manifest_language_invalid",
                         f"manifest.json language must be one of {list(SUPPORTED_LANGUAGES)}.", bundle=bd, file=path,
                         params={"language": str(language)[:10]})
            continue
        if opts.allowed_languages is not None and language not in opts.allowed_languages:
            issues.error("language_not_in_course", f"Language '{language}' is not enabled for this course.",
                         bundle=bd, file=path, params={"language": language})
            continue
        qf = m.get("questions_file") or "questions.csv"
        qpath = join(root, qf) if isinstance(qf, str) else None
        if not qpath or qpath not in zf.entries:
            issues.error("questions_file_missing", f"Questions file '{str(qf)[:120]}' named in manifest.json was "
                         "not found.", bundle=bd, file=path)
            continue
        found.append((ParsedBundle(root=root, has_manifest=True, source_id=source_id.strip(), language=language,
                                   questions_path=qpath, title=source_id.strip()), m))
    seen: dict[str, str] = {}
    for b, _ in found:
        if b.source_id in seen:
            issues.error("duplicate_source_id", f"Two bundles in this zip have the same source_id '{b.source_id}'.",
                         bundle=display_root(b.root), params={"source_id": b.source_id})
        seen[b.source_id] = b.root
    if issues.errors:
        return [b for b, _ in found]

    used: set[str] = set()
    cache: dict[str, Optional[ParsedImage]] = {}
    rows_left = settings.IMPORT_MAX_ROWS
    for b, m in found:
        broot = display_root(b.root)
        qfile = b.questions_path
        if zf.entries[qfile].file_size > settings.IMPORT_MAX_CSV_BYTES:
            _too_large(issues, qfile, broot)
            continue
        text = decode_bytes(zf.read(qfile), lenient=False)
        zf.drop(qfile)
        if text is None:
            issues.error("csv_not_utf8", "The questions CSV is not UTF-8 text.", bundle=broot, file=qfile)
            continue
        try:
            header, records, truncated = read_records(text, rows_left, plain=True)
        except csv.Error as e:
            issues.error("csv_unreadable", f"The questions CSV could not be parsed ({e}).", bundle=broot, file=qfile)
            continue
        del text
        if _is_ort_header(header):
            _mismatch(issues, True, bundle=broot, file=qfile)
            continue
        if truncated:
            issues.too_many_rows(bundle=broot, file=qfile)
            break
        images_dir = m.get("images_dir") if isinstance(m.get("images_dir"), str) else "images"
        m_images = {str(i["file"]): i for i in (m.get("images") or []) if isinstance(i, dict) and i.get("file")}

        def image_for(value: str, n: int, _b=b, _broot=broot, _dir=images_dir, _mi=m_images) -> Optional[ParsedImage]:
            ctx = {"bundle": _broot, "row": n}
            if is_external_image(value):
                issues.error("image_external_url", f"image '{value[:200]}' is an external link; images must be "
                             "included in the zip.", column="image", params={"image": value[:200]}, file=_b.questions_path,
                             **ctx)
                return None
            base = image_base_name(value)
            if not base:
                issues.error("image_missing", f"image '{value[:200]}' has no file name.", column="image",
                             params={"image": value[:200]}, **ctx)
                return None
            p = resolve_image(zf, _b.root, _dir, base, issues, ctx)
            if not p:
                return None
            used.add(p)
            img = check_image(zf, p, _mi, issues, ctx, cache)
            if img is not None:
                _b.images[p] = img
            return img

        parse_rows(header, records, b, issues, profile, image_for, broot=broot)
        data_rows = sum(1 for r in records if not _is_comment(r))
        qc = m.get("question_count")
        if qc is not None and qc != data_rows:
            issues.error("manifest_count_mismatch", f"manifest.json says {qc} questions, the CSV has {data_rows}.",
                         bundle=broot, file=qfile, params={"expected": qc, "got": data_rows})
        missing_ids = sum(1 for it in b.items if it.source_ref is None)
        if missing_ids:
            issues.warning("external_id_missing", f"{missing_ids} row(s) have no external_id; they are added again "
                           "on every re-import.", bundle=broot, file=qfile, params={"count": missing_ids})
        rows_left -= len(records)
    for path in sorted(zf.entries):
        if path.lower().endswith(IMAGE_EXTENSIONS) and path not in used:
            issues.warning("image_unused", f"Image '{path}' is not used by any question.", file=path)
    return [b for b, _ in found]


# ------------------------------------------------------------------------------------------------ dispatch

def parse_general(raw: bytes, filename: str, is_csv: bool, opts: ImportOptions, profile: Optional[TemplateProfile],
                  issues: Issues) -> Optional[list[ParsedBundle]]:
    """The general-format bundles, `[]` after a fatal error, or None when the upload belongs to the ORT / legacy
    parser (which then runs exactly as before). Never raises for bad content."""
    if opts.exam_type is not None:
        return _ort_mode_check(raw, is_csv, issues)
    if is_csv:
        if len(raw) > settings.IMPORT_MAX_CSV_BYTES:
            if profile is None:
                return None          # the legacy path reports csv_too_large exactly as before
            _too_large(issues, filename)
            return []
        header = _csv_header(_prefix_text(raw))
        has_type = "type" in normalize_header(header)
        if not has_type and profile is None:
            return None              # legacy general CSV (ORT columns, free sections), unchanged
        text = decode_bytes(raw, lenient=False)
        if text is None:
            issues.error("csv_not_utf8", "The CSV is not UTF-8 text.", file=filename)
            return []
        if _is_ort_header(header):
            return _mismatch(issues, True, file=filename)
        return _parse_csv(raw, filename, opts, profile, issues, text)
    try:
        zf = SafeZip(raw)
    except BundleError as e:
        if profile is None:
            return None
        issues.error(e.code, e.message, params=e.params)
        return []
    try:
        manifests, ort_manifest = _manifests(zf, issues)
        if manifests:
            if ort_manifest:
                return _mismatch(issues, True)
            return _parse_general_zip(zf, manifests, opts, profile, issues)
        if profile is None:
            return None              # ORT bundle / legacy zip in general mode, unchanged
        if ort_manifest or _ort_csv_in_zip(zf):
            return _mismatch(issues, True)
        issues.error("no_bundle_found", f"no manifest.json with format '{GENERAL_FORMAT}' found")
        return []
    except BundleError as e:
        issues.error(e.code, e.message, params=e.params)
        return []


def _ort_mode_check(raw: bytes, is_csv: bool, issues: Issues) -> Optional[list]:
    """ORT format chosen: a general-format file fails with `format_mismatch`; everything else (including every
    error) is left to the ORT parser."""
    try:
        if is_csv:
            if len(raw) > settings.IMPORT_MAX_CSV_BYTES:
                return None
            t = _first_record_type(_prefix_text(raw))
            if t and t in REGISTRY:
                return _mismatch(issues, False)
            return None
        zf = SafeZip(raw)
        manifests, _ = _manifests(zf, Issues())
        if manifests:
            return _mismatch(issues, False)
    except Exception:  # noqa: BLE001 - the ORT parser reports the real problem
        return None
    return None
