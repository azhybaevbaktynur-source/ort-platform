"""Bundle discovery, image resolution and manifest checks (copy of the frozen bundle_service logic).

Pure: reads from a SafeZip, returns ParsedBundle objects and collects issues. No DB, no storage.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import posixpath
import re
from typing import Any, Optional

from app.core.config import settings
from app.lms.core.types import SUPPORTED_LANGUAGES

from .ort_csv import BUNDLE_COLUMNS, decode_bytes, parse_row, read_records
from .parsed import Issues, ParsedBundle, ParsedImage, ParsedPassage
from .schemas import ImportOptions
from .zipsafe import BundleError, SafeZip

BUNDLE_FORMAT = "ort-question-bundle"
BUNDLE_FORMAT_VERSION = 1
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
ACCEPTED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}


def join(root: str, rel: str) -> Optional[str]:
    rel = (rel or "").replace("\\", "/").strip("/")
    joined = posixpath.normpath(posixpath.join(root, rel)) if root else posixpath.normpath(rel)
    if joined in (".", "") or joined.startswith("../") or joined == "..":
        return None
    return joined


def display_root(root: str) -> str:
    return root + "/" if root else "/"


def csv_header(data: bytes) -> Optional[list[str]]:
    """Header of a (possibly truncated) CSV prefix; only the first record is read."""
    try:
        text = data.decode("utf-8-sig", errors="ignore")
    except Exception:
        return None
    try:
        return next(csv.reader(io.StringIO(text, newline="")), None)
    except csv.Error:
        return None


def image_base_name(value: str) -> str:
    value = value.split("?", 1)[0].split("#", 1)[0]
    return re.split(r"[\\/]", value.strip())[-1].strip()


def is_external_image(value: str) -> bool:
    return bool(re.match(r"^https?://", value, re.IGNORECASE)) or value.startswith("/uploads/")


# ----- discovery ------------------------------------------------------------------------------

def find_bundles(zf: SafeZip, issues: Issues, opts: ImportOptions) -> list[tuple[ParsedBundle, Optional[dict]]]:
    found: list[tuple[ParsedBundle, Optional[dict]]] = []
    for path in sorted(p for p in zf.entries if posixpath.basename(p) == "manifest.json"):
        root = posixpath.dirname(path)
        bd = display_root(root)
        if zf.entries[path].file_size > settings.IMPORT_MAX_MANIFEST_BYTES:
            issues.error("manifest_invalid", "manifest.json is too large.", bundle=bd, file=path,
                         params={"limit_mb": settings.IMPORT_MAX_MANIFEST_BYTES // (1024 * 1024)})
            continue
        try:
            manifest = json.loads(decode_bytes(zf.read(path), lenient=False) or "")
        except (ValueError, TypeError, RecursionError):
            issues.error("manifest_invalid_json", "manifest.json is not valid JSON.", bundle=bd, file=path)
            continue
        finally:
            zf.drop(path)
        if not isinstance(manifest, dict) or manifest.get("format") != BUNDLE_FORMAT:
            continue
        version = manifest.get("format_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            issues.error("manifest_invalid", "manifest.json has no valid format_version.", bundle=bd, file=path)
            continue
        if version > BUNDLE_FORMAT_VERSION:
            issues.error("manifest_version_unsupported",
                         f"Bundle format_version {version} is newer than this platform supports "
                         f"(max {BUNDLE_FORMAT_VERSION}). Update the platform or re-export the bundle.",
                         bundle=bd, file=path, params={"version": version, "supported": BUNDLE_FORMAT_VERSION})
            continue
        if isinstance(manifest.get("questions"), list) and len(manifest["questions"]) > settings.IMPORT_MAX_ROWS:
            issues.too_many_rows(bundle=bd, file=path)
            continue
        source_id = manifest.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            issues.error("manifest_invalid", "manifest.json has no source_id.", bundle=bd, file=path)
            continue
        language = manifest.get("language")
        if language is None:
            language = opts.language
        if language not in SUPPORTED_LANGUAGES:
            issues.error("manifest_language_invalid",
                         f"manifest.json language must be one of {list(SUPPORTED_LANGUAGES)} (got {language!r}).",
                         bundle=bd, file=path, params={"language": language})
            continue
        if opts.allowed_languages is not None and language not in opts.allowed_languages:
            issues.error("language_not_in_course", f"Language '{language}' is not enabled for this course.",
                         bundle=bd, file=path, params={"language": language})
            continue
        qpath = join(root, manifest.get("questions_file") or "questions.csv")
        if not qpath or qpath not in zf.entries:
            issues.error("questions_file_missing",
                         f"Questions file '{manifest.get('questions_file') or 'questions.csv'}' named in manifest.json was not found.",
                         bundle=bd, file=path)
            continue
        found.append((ParsedBundle(root=root, has_manifest=True, source_id=source_id.strip(), language=language,
                                   questions_path=qpath, title=source_id.strip()), manifest))

    if found or issues.errors:
        seen: dict[str, str] = {}
        for b, _ in found:
            if b.source_id in seen:
                issues.error("duplicate_source_id",
                             f"Two bundles in this zip have the same source_id '{b.source_id}' "
                             f"({display_root(seen[b.source_id])} and {display_root(b.root)}).",
                             bundle=display_root(b.root), params={"source_id": b.source_id})
            seen[b.source_id] = b.root
        return found

    # Fallback: every folder with a CSV whose header is exactly the 15 columns.
    by_folder: dict[str, list[str]] = {}
    for path in sorted(zf.entries):
        if path.lower().endswith(".csv") and csv_header(zf.read_prefix(path, 64 * 1024)) == BUNDLE_COLUMNS:
            by_folder.setdefault(posixpath.dirname(path), []).append(path)
    for root, paths in by_folder.items():
        if len(paths) > 1:
            issues.error("multiple_question_csvs",
                         f"Folder {display_root(root)} has several question CSVs ({', '.join(paths)}); keep one per folder or add manifest.json.",
                         bundle=display_root(root), params={"files": paths})
            continue
        if opts.allowed_languages is not None and opts.language not in opts.allowed_languages:
            issues.error("language_not_in_course", f"Language '{opts.language}' is not enabled for this course.",
                         bundle=display_root(root), params={"language": opts.language})
            continue
        stem = posixpath.splitext(posixpath.basename(paths[0]))[0]
        found.append((ParsedBundle(root=root, has_manifest=False, source_id=None, language=opts.language,
                                   questions_path=paths[0], title=posixpath.basename(root) or stem), None))
    if not found and not issues.errors:
        issues.error("no_bundle_found", "no questions.csv / manifest.json found")
    return found


# ----- images ---------------------------------------------------------------------------------

def check_image(zf: SafeZip, path: str, manifest_images: dict[str, dict], issues: Issues, ctx: dict[str, Any],
                cache: dict[str, Optional[ParsedImage]]) -> Optional[ParsedImage]:
    """sha256 is checked against the manifest on the ORIGINAL bytes; then format and pixel cap from the header."""
    if path in cache:
        return cache[path]
    info = zf.entries[path]
    result: Optional[ParsedImage] = None
    if info.file_size > MAX_IMAGE_BYTES:
        issues.error("image_too_large", f"Image '{path}' is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
                     file=path, params={"limit_mb": MAX_IMAGE_BYTES // (1024 * 1024)}, **ctx)
    else:
        content = zf.read(path)
        zf.drop(path)
        sha = hashlib.sha256(content).hexdigest()
        expected = (manifest_images.get(posixpath.basename(path)) or {}).get("sha256")
        if expected and str(expected).lower() != sha:
            issues.error("image_sha_mismatch",
                         f"Image '{path}' does not match the sha256 in manifest.json (file changed or damaged).",
                         file=path, **ctx)
        else:
            fmt, w, h = None, 0, 0
            try:
                from PIL import Image
                with Image.open(io.BytesIO(content)) as img:
                    fmt, (w, h) = img.format, img.size
                    if fmt in ACCEPTED_FORMATS and w * h <= settings.ASSET_MAX_PIXELS:
                        img.verify()
            except Exception:
                fmt = None
            if fmt not in ACCEPTED_FORMATS:
                issues.error("image_invalid", f"'{path}' is not a readable PNG, JPEG, GIF or WebP image.", file=path, **ctx)
            elif w * h > settings.ASSET_MAX_PIXELS:
                issues.error("image_too_many_pixels", f"Image '{path}' has more than {settings.ASSET_MAX_PIXELS // 1_000_000} megapixels.",
                             file=path, params={"width": w, "height": h}, **ctx)
            else:
                result = ParsedImage(path=path, source_sha256=sha, content=content, format=fmt, width=w, height=h)
    cache[path] = result
    return result


def resolve_image(zf: SafeZip, root: str, images_dir: Optional[str], base: str, issues: Issues,
                  ctx: dict[str, Any]) -> Optional[str]:
    """images_dir, images/, bundle root, then anywhere (case-insensitive)."""
    dirs: list[str] = []
    if images_dir:
        d = join(root, images_dir)
        if d:
            dirs.append(d)
    d = join(root, "images")
    if d and d not in dirs:
        dirs.append(d)
    for d in dirs:
        if f"{d}/{base}" in zf.entries:
            return f"{d}/{base}"
    at_root = f"{root}/{base}" if root else base
    if at_root in zf.entries:
        return at_root
    matches = zf.files_named(base)
    if not matches:
        issues.error("image_missing", f"Image file '{base}' was not found in the zip.",
                     column="image_url", params={"image": base}, **ctx)
        return None
    if len(matches) > 1:
        digests = set()
        for m in matches:
            if zf.entries[m].file_size <= MAX_IMAGE_BYTES:
                digests.add(hashlib.sha256(zf.read(m)).hexdigest())
                zf.drop(m)
        if len(digests) > 1:
            issues.error("image_ambiguous", f"Several different files are named '{base}' ({', '.join(matches)}).",
                         column="image_url", params={"image": base, "files": matches}, **ctx)
            return None
    return matches[0]


# ----- parsing --------------------------------------------------------------------------------

def parse_bundle(zf: SafeZip, bundle: ParsedBundle, manifest: Optional[dict], issues: Issues, opts: ImportOptions,
                 used_images: set[str], image_cache: dict[str, Optional[ParsedImage]], row_limit: Optional[int] = None) -> bool:
    """Returns False when the upload-wide row limit was hit (the caller stops)."""
    broot = display_root(bundle.root)
    qfile = bundle.questions_path
    if zf.entries[qfile].file_size > settings.IMPORT_MAX_CSV_BYTES:
        mb = settings.IMPORT_MAX_CSV_BYTES // (1024 * 1024)
        issues.error("csv_too_large", f"The questions CSV is larger than {mb} MB.", bundle=broot, file=qfile,
                     params={"limit_mb": mb})
        return True
    text = decode_bytes(zf.read(qfile), lenient=False)
    zf.drop(qfile)
    if text is None:
        issues.error("csv_not_utf8", "The questions CSV is not UTF-8 text.", bundle=broot, file=qfile)
        return True
    limit = settings.IMPORT_MAX_ROWS if row_limit is None else row_limit
    try:
        header, data_rows, truncated = read_records(text, limit, plain=False)
    except csv.Error as e:
        issues.error("csv_unreadable", f"The questions CSV could not be parsed ({e}).", bundle=broot, file=qfile)
        return True
    del text
    if header != BUNDLE_COLUMNS:
        got = [str(c)[:40] for c in (header or [])[:20]]
        issues.error("csv_header_mismatch", "The questions CSV header must be exactly: " + ",".join(BUNDLE_COLUMNS),
                     bundle=broot, file=qfile, params={"expected": BUNDLE_COLUMNS, "got": got})
        return True
    if truncated:
        issues.too_many_rows(bundle=broot, file=qfile)
        return False

    m_questions: dict[int, dict] = {}
    m_images: dict[str, dict] = {}
    images_dir: Optional[str] = None
    if manifest is not None:
        images_dir = manifest.get("images_dir") or "images"
        for img in manifest.get("images") or []:
            if isinstance(img, dict) and img.get("file"):
                m_images[str(img["file"])] = img
        for pos, mq in enumerate(manifest.get("questions") or [], start=1):
            if isinstance(mq, dict):
                m_questions[mq.get("row") if isinstance(mq.get("row"), int) else pos] = mq
        if manifest.get("question_count") != len(data_rows):
            issues.error("manifest_count_mismatch",
                         f"manifest.json says {manifest.get('question_count')} questions, the CSV has {len(data_rows)}.",
                         bundle=broot, file=qfile, params={"expected": manifest.get("question_count"), "got": len(data_rows)})

    seen_external: dict[str, int] = {}
    passage_index: dict[str, ParsedPassage] = {}
    for n, record in enumerate(data_rows, start=1):
        ctx = {"bundle": broot, "row": n}
        if len(record) != len(BUNDLE_COLUMNS):
            issues.error("csv_field_count", f"Row has {len(record)} fields, expected {len(BUNDLE_COLUMNS)}.",
                         file=qfile, params={"got": len(record)}, **ctx)
            continue
        raw = dict(zip(BUNDLE_COLUMNS, record))
        item, row_errors, image_value = parse_row(raw, n, bundle.language, opts.ort)
        for err in row_errors:
            issues.add_error(err.model_copy(update={"bundle": broot, "file": qfile}))

        ext_id: Optional[str] = None
        if manifest is not None:
            mq = m_questions.get(n)
            if mq is None:
                issues.error("manifest_row_missing", "manifest.json has no entry for this row.", file=qfile, **ctx)
            else:
                if str(mq.get("section") or "") != raw["section"].strip():
                    issues.error("manifest_section_mismatch",
                                 f"Section '{raw['section']}' does not match manifest.json ('{mq.get('section')}').",
                                 file=qfile, column="section", params={"csv": raw["section"], "manifest": mq.get("section")}, **ctx)
                m_img = mq.get("image") or ""
                if (image_base_name(image_value) if image_value else "") != m_img:
                    issues.error("manifest_image_mismatch",
                                 f"image_url '{image_value}' does not match manifest.json ('{m_img or 'none'}').",
                                 file=qfile, column="image_url", params={"csv": image_value, "manifest": m_img}, **ctx)
                eid = mq.get("external_id")
                if not isinstance(eid, str) or not eid.strip():
                    issues.error("manifest_invalid", "manifest.json entry has no external_id.", file=qfile, **ctx)
                elif eid in seen_external:
                    issues.error("duplicate_external_id", f"external_id '{eid}' is used by rows {seen_external[eid]} and {n}.",
                                 file=qfile, params={"external_id": eid}, **ctx)
                else:
                    seen_external[eid] = n
                    ext_id = eid
                    if item is not None:
                        item.source_ref = eid
                        item.q_num = str(mq.get("q_num")) if mq.get("q_num") is not None else None
                        item.fixed = bool(mq.get("fixed"))
                        sp = mq.get("source_page")
                        item.source_page = sp if isinstance(sp, int) and not isinstance(sp, bool) else None

        if image_value:
            if is_external_image(image_value):
                issues.error("image_external_url",
                             f"image_url '{image_value}' is an external link; images must be included in the zip.",
                             column="image_url", params={"image": image_value}, file=qfile, **ctx)
            else:
                base = image_base_name(image_value)
                if not base:
                    issues.error("image_missing", f"image_url '{image_value}' has no file name.",
                                 column="image_url", params={"image": image_value}, **ctx)
                else:
                    path = resolve_image(zf, bundle.root, images_dir, base, issues, ctx)
                    if path:
                        used_images.add(path)
                        img = check_image(zf, path, m_images, issues, ctx, image_cache)
                        if img is not None:
                            bundle.images[path] = img
                            if item is not None:
                                item.image = img

        if item is not None:
            if item.passage_key:
                key = item.passage_key
                p = passage_index.get(key)
                if p is None:
                    p = ParsedPassage(key=key, text=key, first_row=n,
                                      source_ref=f"{ext_id}#passage" if ext_id else None)
                    passage_index[key] = p
                    bundle.passages.append(p)
            bundle.items.append(item)
    return True


def parse_zip(data: bytes, opts: ImportOptions, issues: Issues) -> list[ParsedBundle]:
    try:
        zf = SafeZip(data)
        found = find_bundles(zf, issues, opts)
        used: set[str] = set()
        cache: dict[str, Optional[ParsedImage]] = {}
        rows_left = settings.IMPORT_MAX_ROWS
        for bundle, manifest in found:
            ok = parse_bundle(zf, bundle, manifest, issues, opts, used, cache, rows_left)
            rows_left -= len(bundle.items)
            if not ok:
                break
    except BundleError as e:
        issues.error(e.code, e.message, params=e.params)
        return []
    for path in sorted(zf.entries):
        if path.lower().endswith(IMAGE_EXTENSIONS) and path not in used:
            issues.warning("image_unused", f"Image '{path}' is not used by any question.", file=path)
    return [b for b, _ in found]
