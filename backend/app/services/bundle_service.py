"""
Import of ORT question bundles (.zip) produced by ort-digitizer.
Format and rules: docs/BUNDLE_FORMAT.md.

Flow: open the zip safely -> find bundle roots -> parse and validate every row and image
(reusing CsvService.validate_row) -> if anything is wrong, save nothing -> upload images under
content-addressed keys -> create/update questions and exam sets in ONE SQL transaction ->
mirror the result into Firestore.
"""
import csv
import hashlib
import io
import json
import logging
import posixpath
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.bundle_import import BundleImportReport, BundleIssue, BundleSummary
from app.schemas.question import SectionType
from app.services.csv_image_rule import is_stored_image_url
from app.services.csv_service import CsvService
from app.services.question_order import sql_order_by
from app.services.storage_service import get_storage_service

logger = logging.getLogger(__name__)

BUNDLE_FORMAT = "ort-question-bundle"
BUNDLE_FORMAT_VERSION = 1
BUNDLE_COLUMNS = [
    "section", "topic", "difficulty", "stem", "column_a", "column_b",
    "option_a", "option_b", "option_c", "option_d", "option_e",
    "correct_option", "passage_text", "image_url", "explanation",
]

MAX_ZIP_BYTES = 200 * 1024 * 1024        # compressed upload and total uncompressed size
MAX_ZIP_FILES = 5000
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
IMAGE_FORMATS = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "WEBP": ("webp", "image/webp")}
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
STORAGE_PREFIX = "question-images"
FIRESTORE_BATCH_SIZE = 450

MAIN_SECTIONS = {"math_1", "math_2", "analogies", "reading", "grammar"}


class BundleError(Exception):
    """Fatal problem with the zip itself (nothing else can be checked)."""

    def __init__(self, code: str, message: str, **params: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.params = params


@dataclass
class ResolvedImage:
    sha256: str
    ext: str
    mime: str
    content: bytes

    @property
    def key(self) -> str:
        return f"{STORAGE_PREFIX}/{self.sha256}.{self.ext}"


@dataclass
class BundleRow:
    row: int
    question: Any                       # QuestionCreate
    external_id: Optional[str] = None
    q_num: Optional[str] = None
    fixed: bool = False
    image: Optional[ResolvedImage] = None
    image_url: Optional[str] = None     # kept as-is (http(s) or /uploads/...) when not resolved from the zip


@dataclass
class Bundle:
    root: str
    has_manifest: bool
    source_id: Optional[str]
    language: str
    questions_path: str
    exam_set_id: str
    exam_set_title: str
    rows: List[BundleRow] = field(default_factory=list)


class _Issues:
    def __init__(self):
        self.errors: List[BundleIssue] = []
        self.warnings: List[BundleIssue] = []

    def error(self, code: str, message: str, **kw: Any):
        self.errors.append(BundleIssue(severity="error", code=code, message=message, **kw))

    def warning(self, code: str, message: str, **kw: Any):
        self.warnings.append(BundleIssue(severity="warning", code=code, message=message, **kw))


# ---------------------------------------------------------------------------
# Zip access
# ---------------------------------------------------------------------------

class _SafeZip:
    """Read-only view of the zip with junk entries removed and size limits enforced."""

    def __init__(self, data: bytes):
        if len(data) > MAX_ZIP_BYTES:
            raise BundleError("zip_too_large", f"The zip is larger than {MAX_ZIP_BYTES // (1024 * 1024)} MB.",
                              limitMb=MAX_ZIP_BYTES // (1024 * 1024))
        try:
            self._zf = zipfile.ZipFile(io.BytesIO(data))
            infos = self._zf.infolist()
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as e:
            raise BundleError("zip_invalid", f"The file is not a valid zip archive ({e}).")

        if len(infos) > MAX_ZIP_FILES:
            raise BundleError("zip_too_many_files", f"The zip contains more than {MAX_ZIP_FILES} files.",
                              limit=MAX_ZIP_FILES)
        if sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
            raise BundleError("zip_too_large", f"The zip unpacks to more than {MAX_ZIP_BYTES // (1024 * 1024)} MB.",
                              limitMb=MAX_ZIP_BYTES // (1024 * 1024))

        self.entries: Dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            name = info.filename.replace("\\", "/")
            parts = [p for p in name.split("/") if p not in ("", ".")]
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in parts:
                raise BundleError("zip_unsafe_path", f"Unsafe path in zip: '{info.filename}'.", path=info.filename)
            if info.is_dir() or not parts:
                continue
            base = parts[-1]
            if "__MACOSX" in parts or base.startswith("._") or base.lower() in JUNK_NAMES:
                continue
            if info.flag_bits & 0x1:
                raise BundleError("zip_encrypted", f"Encrypted file in zip: '{info.filename}'.", path=info.filename)
            self.entries["/".join(parts)] = info

        self._cache: Dict[str, bytes] = {}

    def read(self, path: str) -> bytes:
        if path not in self._cache:
            info = self.entries[path]
            with self._zf.open(info) as f:
                data = f.read(info.file_size + 1)
            if len(data) > info.file_size:
                raise BundleError("zip_invalid", f"Size mismatch for '{path}' in zip.", path=path)
            self._cache[path] = data
        return self._cache[path]

    def files_named(self, base_name: str) -> List[str]:
        low = base_name.lower()
        return [p for p in self.entries if posixpath.basename(p).lower() == low]


def _join(root: str, rel: str) -> Optional[str]:
    """Join a manifest-relative path to the bundle root; None if it escapes the root."""
    rel = (rel or "").replace("\\", "/").strip("/")
    joined = posixpath.normpath(posixpath.join(root, rel)) if root else posixpath.normpath(rel)
    if joined in (".", "") or joined.startswith("../") or joined == "..":
        return None
    return joined


def _display_root(root: str) -> str:
    return root + "/" if root else "/"


def _decode_text(data: bytes) -> Optional[str]:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _csv_header(data: bytes) -> Optional[List[str]]:
    text = _decode_text(data)
    if text is None:
        return None
    try:
        return next(csv.reader(io.StringIO(text, newline="")), None)
    except csv.Error:
        return None


def _image_base_name(value: str) -> str:
    value = value.split("?", 1)[0].split("#", 1)[0]
    return re.split(r"[\\/]", value.strip())[-1].strip()


def _safe_id(source_id: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", source_id.strip().lower()).strip("_") or "source"


def _section_time_limit(section: str) -> int:
    # Same defaults as CSV import (CsvService.ingest_csv)
    return 30 if "math" in section or "analog" in section else (45 if "reading" in section else 35)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class BundleService:

    # ----- discovery --------------------------------------------------------

    @classmethod
    def _find_bundles(cls, zf: _SafeZip, issues: _Issues, default_language: str) -> List[Tuple[Bundle, Optional[dict]]]:
        found: List[Tuple[Bundle, Optional[dict]]] = []

        for path in sorted(p for p in zf.entries if posixpath.basename(p) == "manifest.json"):
            root = posixpath.dirname(path)
            try:
                manifest = json.loads(_decode_text(zf.read(path)) or "")
            except (ValueError, TypeError):
                issues.error("manifest_invalid_json", "manifest.json is not valid JSON.",
                             bundle=_display_root(root), file=path)
                continue
            if not isinstance(manifest, dict) or manifest.get("format") != BUNDLE_FORMAT:
                continue

            version = manifest.get("format_version")
            if not isinstance(version, int) or version < 1:
                issues.error("manifest_invalid", "manifest.json has no valid format_version.",
                             bundle=_display_root(root), file=path)
                continue
            if version > BUNDLE_FORMAT_VERSION:
                issues.error("manifest_version_unsupported",
                             f"Bundle format_version {version} is newer than this platform supports "
                             f"(max {BUNDLE_FORMAT_VERSION}). Update the platform or re-export the bundle.",
                             bundle=_display_root(root), file=path, params={"version": version,
                                                                           "supported": BUNDLE_FORMAT_VERSION})
                continue

            source_id = manifest.get("source_id")
            if not isinstance(source_id, str) or not source_id.strip():
                issues.error("manifest_invalid", "manifest.json has no source_id.",
                             bundle=_display_root(root), file=path)
                continue
            source_id = source_id.strip()

            language = manifest.get("language")
            if language not in ("ky", "ru"):
                issues.error("manifest_language_invalid",
                             f"manifest.json language must be 'ky' or 'ru' (got {language!r}).",
                             bundle=_display_root(root), file=path, params={"language": language})
                continue

            questions_path = _join(root, manifest.get("questions_file") or "questions.csv")
            if not questions_path or questions_path not in zf.entries:
                issues.error("questions_file_missing",
                             f"Questions file '{manifest.get('questions_file') or 'questions.csv'}' "
                             f"named in manifest.json was not found.",
                             bundle=_display_root(root), file=path)
                continue

            found.append((Bundle(
                root=root, has_manifest=True, source_id=source_id, language=language,
                questions_path=questions_path,
                exam_set_id=f"exam_bundle_{_safe_id(source_id)}",
                exam_set_title=f"ОРТ: {source_id}",
            ), manifest))

        if found or issues.errors:
            seen: Dict[str, str] = {}
            for b, _ in found:
                if b.source_id in seen:
                    issues.error("duplicate_source_id",
                                 f"Two bundles in this zip have the same source_id '{b.source_id}' "
                                 f"({_display_root(seen[b.source_id])} and {_display_root(b.root)}).",
                                 bundle=_display_root(b.root), params={"sourceId": b.source_id})
                seen[b.source_id] = b.root
            return found

        # Fallback: no manifest anywhere -> every folder with a CSV whose header is exactly the 15 columns.
        by_folder: Dict[str, List[str]] = {}
        for path in sorted(zf.entries):
            if path.lower().endswith(".csv") and _csv_header(zf.read(path)) == BUNDLE_COLUMNS:
                by_folder.setdefault(posixpath.dirname(path), []).append(path)

        for root, paths in by_folder.items():
            if len(paths) > 1:
                issues.error("multiple_question_csvs",
                             f"Folder {_display_root(root)} has several question CSVs ({', '.join(paths)}); "
                             f"keep one per folder or add manifest.json.",
                             bundle=_display_root(root), params={"files": paths})
                continue
            stem = posixpath.splitext(posixpath.basename(paths[0]))[0]
            found.append((Bundle(
                root=root, has_manifest=False, source_id=None, language=default_language,
                questions_path=paths[0],
                exam_set_id=f"exam_bundle_upload_{uuid.uuid4().hex[:10]}",
                exam_set_title=f"ОРТ: {stem}",
            ), None))

        if not found and not issues.errors:
            issues.error("no_bundle_found", "no questions.csv / manifest.json found")
        return found

    # ----- images -------------------------------------------------------------

    @classmethod
    def _check_image(cls, zf: _SafeZip, path: str, manifest_images: Dict[str, dict],
                     issues: _Issues, ctx: Dict[str, Any], cache: Dict[str, Optional[ResolvedImage]]) -> Optional[ResolvedImage]:
        if path in cache:
            return cache[path]
        info = zf.entries[path]
        result: Optional[ResolvedImage] = None
        if info.file_size > MAX_IMAGE_BYTES:
            issues.error("image_too_large", f"Image '{path}' is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
                         file=path, params={"limitMb": MAX_IMAGE_BYTES // (1024 * 1024)}, **ctx)
        else:
            content = zf.read(path)
            sha = hashlib.sha256(content).hexdigest()
            listed = manifest_images.get(posixpath.basename(path))
            expected = (listed or {}).get("sha256")
            if expected and str(expected).lower() != sha:
                issues.error("image_sha_mismatch",
                             f"Image '{path}' does not match the sha256 in manifest.json (file changed or damaged).",
                             file=path, **ctx)
            else:
                fmt = None
                try:
                    from PIL import Image
                    with Image.open(io.BytesIO(content)) as img:
                        fmt = img.format
                        img.verify()
                except Exception:
                    fmt = None
                if fmt not in IMAGE_FORMATS:
                    issues.error("image_invalid", f"'{path}' is not a readable PNG, JPEG or WebP image.",
                                 file=path, **ctx)
                else:
                    ext, mime = IMAGE_FORMATS[fmt]
                    result = ResolvedImage(sha256=sha, ext=ext, mime=mime, content=content)
        cache[path] = result
        return result

    @classmethod
    def _resolve_image(cls, zf: _SafeZip, bundle: Bundle, images_dir: Optional[str], base: str,
                       issues: _Issues, ctx: Dict[str, Any]) -> Optional[str]:
        """Steps 4.2-4.5 of the spec: images_dir, images/, bundle root, then anywhere (case-insensitive)."""
        dirs = []
        if images_dir:
            d = _join(bundle.root, images_dir)
            if d:
                dirs.append(d)
        d = _join(bundle.root, "images")
        if d and d not in dirs:
            dirs.append(d)
        for d in dirs:
            if f"{d}/{base}" in zf.entries:
                return f"{d}/{base}"
        at_root = f"{bundle.root}/{base}" if bundle.root else base
        if at_root in zf.entries:
            return at_root

        matches = zf.files_named(base)
        if not matches:
            issues.error("image_missing", f"Image file '{base}' was not found in the zip.",
                         column="image_url", params={"image": base}, **ctx)
            return None
        if len(matches) > 1:
            digests = {hashlib.sha256(zf.read(m)).hexdigest() for m in matches if zf.entries[m].file_size <= MAX_IMAGE_BYTES}
            if len(digests) > 1:
                issues.error("image_ambiguous",
                             f"Several different files are named '{base}' ({', '.join(matches)}).",
                             column="image_url", params={"image": base, "files": matches}, **ctx)
                return None
        return matches[0]

    # ----- parsing & validation ----------------------------------------------

    @classmethod
    def _parse_bundle(cls, zf: _SafeZip, bundle: Bundle, manifest: Optional[dict], issues: _Issues,
                      used_images: set, image_cache: Dict[str, Optional[ResolvedImage]]) -> None:
        broot = _display_root(bundle.root)
        qfile = bundle.questions_path
        text = _decode_text(zf.read(qfile))
        if text is None:
            issues.error("csv_not_utf8", "The questions CSV is not UTF-8 text.", bundle=broot, file=qfile)
            return

        try:
            records = list(csv.reader(io.StringIO(text, newline="")))
        except csv.Error as e:
            issues.error("csv_unreadable", f"The questions CSV could not be parsed ({e}).", bundle=broot, file=qfile)
            return
        if not records or records[0] != BUNDLE_COLUMNS:
            issues.error("csv_header_mismatch",
                         "The questions CSV header must be exactly: " + ",".join(BUNDLE_COLUMNS),
                         bundle=broot, file=qfile, params={"expected": BUNDLE_COLUMNS,
                                                           "got": records[0] if records else []})
            return
        data_rows = [r for r in records[1:] if r]

        m_questions: Dict[int, dict] = {}
        m_images: Dict[str, dict] = {}
        images_dir: Optional[str] = None
        if manifest is not None:
            images_dir = manifest.get("images_dir") or "images"
            for img in manifest.get("images") or []:
                if isinstance(img, dict) and img.get("file"):
                    m_images[str(img["file"])] = img
            mq_list = manifest.get("questions") or []
            for pos, mq in enumerate(mq_list, start=1):
                if isinstance(mq, dict):
                    m_questions[mq.get("row") if isinstance(mq.get("row"), int) else pos] = mq
            if manifest.get("question_count") != len(data_rows):
                issues.error("manifest_count_mismatch",
                             f"manifest.json says {manifest.get('question_count')} questions, "
                             f"the CSV has {len(data_rows)}.",
                             bundle=broot, file=qfile,
                             params={"expected": manifest.get("question_count"), "got": len(data_rows)})

        seen_external: Dict[str, int] = {}
        for n, record in enumerate(data_rows, start=1):
            ctx = {"bundle": broot, "row": n}
            if len(record) != len(BUNDLE_COLUMNS):
                issues.error("csv_field_count", f"Row has {len(record)} fields, expected {len(BUNDLE_COLUMNS)}.",
                             file=qfile, params={"got": len(record)}, **ctx)
                continue
            raw = dict(zip(BUNDLE_COLUMNS, record))

            question, row_errors = CsvService.validate_row(
                row=raw, row_number=n, language=bundle.language, exam_id=bundle.exam_set_id,
            )
            for err in row_errors:
                issues.error("row_invalid", err.errorMessage, file=qfile, column=err.field, **ctx)

            if question is not None and question.correct_option == "E" and not (question.option_e or "").strip():
                issues.error("correct_option_not_allowed",
                             "correct_option is E but the question has only 4 options (A-D).",
                             file=qfile, column="correct_option", **ctx)

            image_value = raw["image_url"].strip()
            brow = BundleRow(row=n, question=question)

            if manifest is not None:
                mq = m_questions.get(n)
                if mq is None:
                    issues.error("manifest_row_missing", "manifest.json has no entry for this row.", file=qfile, **ctx)
                else:
                    if str(mq.get("section") or "") != raw["section"].strip():
                        issues.error("manifest_section_mismatch",
                                     f"Section '{raw['section']}' does not match manifest.json ('{mq.get('section')}').",
                                     file=qfile, column="section",
                                     params={"csv": raw["section"], "manifest": mq.get("section")}, **ctx)
                    m_img = mq.get("image") or ""
                    if (_image_base_name(image_value) if image_value else "") != m_img:
                        issues.error("manifest_image_mismatch",
                                     f"image_url '{image_value}' does not match manifest.json ('{m_img or 'none'}').",
                                     file=qfile, column="image_url",
                                     params={"csv": image_value, "manifest": m_img}, **ctx)
                    ext_id = mq.get("external_id")
                    if not isinstance(ext_id, str) or not ext_id.strip():
                        issues.error("manifest_invalid", "manifest.json entry has no external_id.", file=qfile, **ctx)
                    elif ext_id in seen_external:
                        issues.error("duplicate_external_id",
                                     f"external_id '{ext_id}' is used by rows {seen_external[ext_id]} and {n}.",
                                     file=qfile, params={"externalId": ext_id}, **ctx)
                    else:
                        seen_external[ext_id] = n
                        brow.external_id = ext_id
                        brow.q_num = str(mq.get("q_num")) if mq.get("q_num") is not None else None
                        brow.fixed = bool(mq.get("fixed"))

            if image_value:
                if is_stored_image_url(image_value):
                    brow.image_url = image_value
                else:
                    base = _image_base_name(image_value)
                    path = cls._resolve_image(zf, bundle, images_dir, base, issues, ctx) if base else None
                    if not base:
                        issues.error("image_missing", f"image_url '{image_value}' has no file name.",
                                     column="image_url", params={"image": image_value}, **ctx)
                    if path:
                        used_images.add(path)
                        brow.image = cls._check_image(zf, path, m_images, issues, ctx, image_cache)

            bundle.rows.append(brow)

    @classmethod
    def _validate(cls, file_bytes: bytes, language: str) -> Tuple[List[Bundle], _Issues]:
        issues = _Issues()
        lang = "ru" if "ru" in (language or "ky").lower() else "ky"
        try:
            zf = _SafeZip(file_bytes)
            found = cls._find_bundles(zf, issues, lang)
            used_images: set = set()
            image_cache: Dict[str, Optional[ResolvedImage]] = {}
            for bundle, manifest in found:
                cls._parse_bundle(zf, bundle, manifest, issues, used_images, image_cache)
        except BundleError as e:
            issues.error(e.code, e.message, params=e.params)
            return [], issues

        for path in sorted(zf.entries):
            if path.lower().endswith(IMAGE_EXTENSIONS) and path not in used_images:
                issues.warning("image_unused", f"Image '{path}' is not used by any question.", file=path)
        return [b for b, _ in found], issues

    # ----- DB lookups -----------------------------------------------------------

    @staticmethod
    def _ensure_tables() -> None:
        from app.db.session import engine
        from app.models.question_source import QuestionSource
        QuestionSource.__table__.create(bind=engine, checkfirst=True)

    @classmethod
    def _existing_mappings(cls, session, external_ids: List[str]) -> Dict[str, Any]:
        from app.models.question_source import QuestionSource
        out: Dict[str, Any] = {}
        for i in range(0, len(external_ids), 500):
            chunk = external_ids[i:i + 500]
            for m in session.query(QuestionSource).filter(QuestionSource.external_id.in_(chunk)).all():
                out[m.external_id] = m
        return out

    @classmethod
    def _plan(cls, session, bundles: List[Bundle], issues: _Issues) -> List[BundleSummary]:
        """Works out per bundle what will be created vs updated and warns about questions missing from a re-upload."""
        from app.models.exam_set import ExamSet
        from app.models.question import Question
        from app.models.question_source import QuestionSource

        summaries = []
        for b in bundles:
            ext_ids = [r.external_id for r in b.rows if r.external_id]
            mappings = cls._existing_mappings(session, ext_ids) if b.has_manifest else {}
            existing_q_ids = set()
            if mappings:
                ids = [m.question_id for m in mappings.values()]
                for i in range(0, len(ids), 500):
                    existing_q_ids.update(q for (q,) in session.query(Question.id).filter(Question.id.in_(ids[i:i + 500])))

            sections: Dict[str, int] = {}
            created: Dict[str, int] = {}
            updated: Dict[str, int] = {}
            for r in b.rows:
                sec = r.question.section.value if r.question is not None else "?"
                sections[sec] = sections.get(sec, 0) + 1
                m = mappings.get(r.external_id) if r.external_id else None
                target = updated if (m is not None and m.question_id in existing_q_ids) else created
                target[sec] = target.get(sec, 0) + 1

            if b.has_manifest:
                in_bundle = set(ext_ids)
                missing = [
                    ext for (ext,) in session.query(QuestionSource.external_id).filter(QuestionSource.source_id == b.source_id)
                    if ext not in in_bundle
                ]
                if missing:
                    issues.warning("questions_missing_from_bundle",
                                   f"{len(missing)} question(s) of source '{b.source_id}' imported earlier are not in "
                                   f"this bundle; they are kept unchanged: {', '.join(sorted(missing)[:10])}"
                                   f"{' …' if len(missing) > 10 else ''}",
                                   bundle=_display_root(b.root),
                                   params={"count": len(missing), "sourceId": b.source_id, "externalIds": sorted(missing)[:50]})

            exists = session.query(ExamSet.id).filter(ExamSet.id == b.exam_set_id).first() is not None
            summaries.append(BundleSummary(
                root=_display_root(b.root), sourceId=b.source_id, hasManifest=b.has_manifest, language=b.language,
                examSetId=b.exam_set_id, examSetTitle=b.exam_set_title, examSetExists=exists,
                questionCount=len(b.rows), sections=sections, created=created, updated=updated,
                images=len({r.image.sha256 for r in b.rows if r.image}),
            ))
        return summaries

    @staticmethod
    def _distinct_images(bundles: List[Bundle]) -> Dict[str, ResolvedImage]:
        out: Dict[str, ResolvedImage] = {}
        for b in bundles:
            for r in b.rows:
                if r.image:
                    out.setdefault(r.image.key, r.image)
        return out

    # ----- public API -------------------------------------------------------------

    @classmethod
    def preview(cls, file_bytes: bytes, language: str = "ky") -> BundleImportReport:
        """Validate the zip and report what an import would do. Saves nothing."""
        bundles, issues = cls._validate(file_bytes, language)
        return cls._report(bundles, issues, committed=False)

    @classmethod
    def _report(cls, bundles: List[Bundle], issues: _Issues, committed: bool,
                uploaded: Optional[int] = None, reused: Optional[int] = None) -> BundleImportReport:
        from app.db.session import SessionLocal
        summaries: List[BundleSummary] = []
        images = cls._distinct_images(bundles)
        storage = get_storage_service()
        if bundles:
            cls._ensure_tables()
            session = SessionLocal()
            try:
                summaries = cls._plan(session, bundles, issues) if not committed else []
            finally:
                session.close()
        if uploaded is None:
            reused = sum(1 for key in images if storage.exists(key))
            uploaded = len(images) - reused
        return BundleImportReport(
            ok=not issues.errors, committed=committed, bundles=summaries,
            errors=issues.errors, warnings=issues.warnings,
            imagesTotal=len(images), imagesNew=uploaded, imagesExisting=reused or 0,
        )

    @classmethod
    async def import_bundle(cls, file_bytes: bytes, language: str = "ky",
                            created_by_user_id: str = "instructor_admin") -> BundleImportReport:
        """Validate, then upload images and create/update questions in one SQL transaction. All or nothing."""
        from app.db.session import SessionLocal

        bundles, issues = cls._validate(file_bytes, language)
        if issues.errors or not bundles:
            return cls._report(bundles, issues, committed=False)

        cls._ensure_tables()
        session = SessionLocal()
        try:
            summaries = cls._plan(session, bundles, issues)
        finally:
            session.close()

        # 1. Images: content-addressed keys, uploaded once, skipped when already stored.
        storage = get_storage_service()
        images = cls._distinct_images(bundles)
        urls: Dict[str, str] = {}
        uploaded = reused = 0
        try:
            for key, img in images.items():
                if storage.exists(key):
                    reused += 1
                    urls[key] = storage.public_url(key)
                else:
                    urls[key] = await storage.upload_file(img.content, key, content_type=img.mime)
                    uploaded += 1
        except Exception as e:
            logger.exception("Bundle image upload failed")
            issues.error("storage_error", f"Image upload failed, nothing was imported ({e}).")
            return BundleImportReport(ok=False, committed=False, bundles=summaries, errors=issues.errors,
                                      warnings=issues.warnings, imagesTotal=len(images),
                                      imagesNew=uploaded, imagesExisting=reused)

        # 2. Questions + exam sets: one transaction.
        session = SessionLocal()
        try:
            written = cls._write_sql(session, bundles, urls, created_by_user_id)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.exception("Bundle import transaction failed")
            issues.error("database_error", f"Saving to the database failed, nothing was imported ({e}).")
            return BundleImportReport(ok=False, committed=False, bundles=summaries, errors=issues.errors,
                                      warnings=issues.warnings, imagesTotal=len(images),
                                      imagesNew=uploaded, imagesExisting=reused)
        finally:
            session.close()

        # 3. Mirror into Firestore (read by the mock test runner). SQL is already committed.
        try:
            cls._mirror_firestore(written)
        except Exception as e:
            logger.exception("Bundle Firestore mirror failed")
            issues.warning("firestore_mirror_failed",
                           f"Questions were saved, but copying them to Firestore failed ({e}).")

        return BundleImportReport(ok=True, committed=True, bundles=summaries, errors=[],
                                  warnings=issues.warnings, imagesTotal=len(images),
                                  imagesNew=uploaded, imagesExisting=reused)

    # ----- writing ------------------------------------------------------------------

    @classmethod
    def _write_sql(cls, session, bundles: List[Bundle], urls: Dict[str, str], user_id: str) -> List[Dict[str, Any]]:
        from app.models.exam_set import ExamSet
        from app.models.question import Question
        from app.models.question_source import QuestionSource

        now = datetime.now(timezone.utc)
        written: List[Dict[str, Any]] = []

        for b in bundles:
            mappings = cls._existing_mappings(session, [r.external_id for r in b.rows if r.external_id]) if b.has_manifest else {}
            exam = session.get(ExamSet, b.exam_set_id)
            new_exam = exam is None
            if new_exam:
                exam = ExamSet(id=b.exam_set_id, title=b.exam_set_title, language=b.language,
                               status="published", created_by=user_id, created_at=now, updated_at=now)
                session.add(exam)
                session.flush()

            created_ids: List[str] = []
            bundle_ids: List[str] = []
            for position, r in enumerate(b.rows, start=1):
                q = r.question
                image_url = urls[r.image.key] if r.image else r.image_url
                # Document order = row order in questions.csv (manifest questions[].row); q_num from the manifest
                fields = dict(
                    language=b.language, section=q.section.value, topic=q.topic, difficulty=q.difficulty.value,
                    column_a=q.column_a, column_b=q.column_b, stem=q.stem or "",
                    option_a=q.option_a or "", option_b=q.option_b or "", option_c=q.option_c or "",
                    option_d=q.option_d or "", option_e=q.option_e, correct_option=q.correct_option,
                    explanation=q.explanation, image_url=image_url, passage_text=q.passage_text,
                    exam_set_id=b.exam_set_id, position=position, q_num=r.q_num,
                )
                mapping = mappings.get(r.external_id) if r.external_id else None
                row_obj = session.get(Question, mapping.question_id) if mapping is not None else None
                if row_obj is not None:
                    for k, v in fields.items():
                        setattr(row_obj, k, v)
                    row_obj.updated_at = now
                else:
                    row_obj = Question(id=f"q_{uuid.uuid4().hex[:12]}", tags=list(q.tags or []), created_by=user_id,
                                       created_at=now, updated_at=now, **fields)
                    session.add(row_obj)
                    created_ids.append(row_obj.id)

                if r.external_id:
                    if mapping is None:
                        mapping = QuestionSource(external_id=r.external_id, question_id=row_obj.id,
                                                 source_id=b.source_id, created_at=now)
                        session.add(mapping)
                    mapping.question_id = row_obj.id
                    mapping.section = q.section.value
                    mapping.q_num = r.q_num
                    mapping.fixed = r.fixed
                    mapping.image_sha256 = r.image.sha256 if r.image else None
                    mapping.updated_at = now
                bundle_ids.append(row_obj.id)
            session.flush()

            # Exam set: bundle questions in official order, then any earlier questions not in this bundle.
            in_bundle = set(bundle_ids)
            old_ids = [i for i in (exam.question_ids or []) if i not in in_bundle]
            # Questions of this set that are not in the bundle keep their relative order after it
            leftovers = (session.query(Question).filter(Question.exam_set_id == b.exam_set_id,
                                                        Question.id.notin_(bundle_ids))
                         .order_by(*sql_order_by(Question)).all())
            for offset, q_row in enumerate(leftovers, start=len(bundle_ids) + 1):
                q_row.position = offset
            old_ids = list(dict.fromkeys(old_ids + [q_row.id for q_row in leftovers]))
            all_ids = bundle_ids + old_ids
            counts: Dict[str, int] = {}
            for r in b.rows:
                counts[r.question.section.value] = counts.get(r.question.section.value, 0) + 1
            for i in range(0, len(old_ids), 500):
                for (sec,) in session.query(Question.section).filter(Question.id.in_(old_ids[i:i + 500])):
                    counts[sec] = counts.get(sec, 0) + 1
            # Official test order = order of first appearance in the bundle; older leftovers after that.
            order = list(dict.fromkeys(r.question.section.value for r in b.rows)) + [s.value for s in SectionType]
            sections = [
                {"section": s, "questionCount": counts[s], "timeLimitMinutes": _section_time_limit(s)}
                for s in sorted(counts, key=lambda s: order.index(s) if s in order else len(order))
            ]
            exam.question_ids = all_ids
            exam.total_questions = len(all_ids)
            exam.sections = sections
            exam.updated_at = now
            if new_exam:
                is_main = any(s["section"] in MAIN_SECTIONS for s in sections)
                exam.exam_type = "full_main" if is_main else "subject"
                exam.max_attempts = 1
                exam.total_time_minutes = sum(s["timeLimitMinutes"] for s in sections) or 170
                exam.description = f"{b.exam_set_title} ({len(all_ids)} суроо / вопросов)."

            written.append({"bundle": b, "exam_id": exam.id, "question_ids": bundle_ids,
                            "created_ids": set(created_ids), "new_exam": new_exam})
        return written

    @classmethod
    def _mirror_firestore(cls, written: List[Dict[str, Any]]) -> None:
        from app.db.firebase import get_firestore_client
        from app.db.session import SessionLocal
        from app.models.exam_set import ExamSet
        from app.models.question import Question

        db = get_firestore_client()
        session = SessionLocal()
        try:
            ops: List[Tuple[Any, Dict[str, Any], bool]] = []
            for w in written:
                for i in range(0, len(w["question_ids"]), 500):
                    for q in session.query(Question).filter(Question.id.in_(w["question_ids"][i:i + 500])):
                        doc = q.to_dict()
                        if q.id in w["created_ids"]:
                            ops.append((db.collection("questions").document(q.id), doc, False))
                        else:
                            doc.pop("stats", None)
                            doc.pop("createdAt", None)
                            doc.pop("createdBy", None)
                            ops.append((db.collection("questions").document(q.id), doc, True))

                exam = session.get(ExamSet, w["exam_id"])
                template = {
                    "id": exam.id, "title": exam.title, "description": exam.description, "language": exam.language,
                    "exam_type": exam.exam_type, "type": "fixed_full", "status": exam.status,
                    "available_from": exam.available_from, "available_until": exam.available_until,
                    "access_code": exam.access_code, "max_attempts": exam.max_attempts,
                    "sections": exam.sections or [], "totalQuestions": exam.total_questions,
                    "totalTimeMinutes": exam.total_time_minutes, "questionIds": exam.question_ids or [],
                    "createdBy": exam.created_by,
                    "createdAt": exam.created_at.isoformat() if exam.created_at else None,
                    "updatedAt": exam.updated_at.isoformat() if exam.updated_at else None,
                }
                ref = db.collection("mock_test_templates").document(exam.id)
                if w["new_exam"]:
                    template["completionsCount"] = 0
                    ops.append((ref, template, False))
                else:
                    ops.append((ref, {k: template[k] for k in ("questionIds", "totalQuestions", "sections", "updatedAt")}, True))
        finally:
            session.close()

        for i in range(0, len(ops), FIRESTORE_BATCH_SIZE):
            batch = db.batch()
            for ref, data, merge in ops[i:i + FIRESTORE_BATCH_SIZE]:
                batch.set(ref, data, merge=merge)
            batch.commit()
