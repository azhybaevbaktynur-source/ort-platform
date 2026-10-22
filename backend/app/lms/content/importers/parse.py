"""Pure entry point: raw upload bytes -> ParsedUpload (no DB, no storage, no writes)."""
from __future__ import annotations

import posixpath
from typing import Optional

from app.core.config import settings

from .bundle import image_base_name, is_external_image, parse_zip
from .ort_csv import decode_bytes, parse_row, read_plain_csv
from .parsed import Issues, ParsedBundle, ParsedPassage, ParsedUpload
from .schemas import ImportOptions


def _parse_plain_csv(raw: bytes, filename: str, opts: ImportOptions, issues: Issues) -> list[ParsedBundle]:
    if len(raw) > settings.IMPORT_MAX_CSV_BYTES:
        mb = settings.IMPORT_MAX_CSV_BYTES // (1024 * 1024)
        issues.error("csv_too_large", f"The CSV is larger than {mb} MB.", file=filename, params={"limit_mb": mb})
        return []
    text = decode_bytes(raw, lenient=True)
    try:
        rows, header, truncated = read_plain_csv(text or "", settings.IMPORT_MAX_ROWS)
    except Exception as e:  # csv.Error and friends
        issues.error("csv_unreadable", f"CSV file parsing failed: {e}", file=filename)
        return []
    del text
    if truncated:
        issues.too_many_rows()
        return []
    if opts.allowed_languages is not None and opts.language not in opts.allowed_languages:
        issues.error("language_not_in_course", f"Language '{opts.language}' is not enabled for this course.",
                     params={"language": opts.language})
        return []
    stem = posixpath.splitext(posixpath.basename(filename or "questions.csv"))[0] or "questions"
    bundle = ParsedBundle(root="", has_manifest=False, source_id=None, language=opts.language,
                          questions_path=filename or "questions.csv", title=stem)
    passages: dict[str, ParsedPassage] = {}
    for n, rec in enumerate(rows, start=1):
        item, errs, image_value = parse_row(rec, n, opts.language, opts.ort)
        for e in errs:
            issues.add_error(e.model_copy(update={"file": bundle.questions_path}))
        if image_value:
            if is_external_image(image_value):
                issues.error("image_external_url",
                             f"image_url '{image_value}' is an external link; external images are not imported.",
                             row=n, column="image_url", file=bundle.questions_path, params={"image": image_value})
            else:
                issues.error("image_not_included",
                             f"Image not included - upload the zip bundle: '{image_base_name(image_value)}'.",
                             row=n, column="image_url", file=bundle.questions_path,
                             params={"image": image_value})
            continue
        if item is None:
            continue
        if item.passage_key and item.passage_key not in passages:
            p = ParsedPassage(key=item.passage_key, text=item.passage_key, first_row=n)
            passages[item.passage_key] = p
            bundle.passages.append(p)
        bundle.items.append(item)
    return [bundle]


def parse_upload(raw: bytes, filename: str, opts: Optional[ImportOptions] = None) -> ParsedUpload:
    """Parse and validate a .zip bundle upload or a plain .csv. Never raises for bad content."""
    opts = opts or ImportOptions()
    issues = Issues()
    is_csv = (filename or "").lower().endswith(".csv")
    kind = "csv" if is_csv else "zip"
    if len(raw) > settings.IMPORT_MAX_UPLOAD_BYTES:
        mb = settings.IMPORT_MAX_UPLOAD_BYTES // (1024 * 1024)
        issues.error("zip_too_large", f"The file is larger than {mb} MB.", params={"limit_mb": mb})
        return ParsedUpload(kind, [], issues)
    bundles = _parse_plain_csv(raw, filename, opts, issues) if is_csv else parse_zip(raw, opts, issues)

    rows = sum(len(b.items) for b in bundles)
    if rows > settings.IMPORT_MAX_ROWS:
        issues.error("too_many_rows", f"The upload has {rows} rows; the limit is {settings.IMPORT_MAX_ROWS}.",
                     params={"limit": settings.IMPORT_MAX_ROWS, "got": rows})
    up = ParsedUpload(kind, bundles, issues)
    n_img = len(up.distinct_images)
    if n_img > settings.IMPORT_MAX_IMAGES:
        issues.error("too_many_images", f"The upload has {n_img} distinct images; the limit is {settings.IMPORT_MAX_IMAGES}.",
                     params={"limit": settings.IMPORT_MAX_IMAGES, "got": n_img})
    if opts.target_bank_id and not (len(bundles) == 1 and not bundles[0].has_manifest):
        issues.error("target_bank_not_allowed",
                     "target_bank_id is allowed only for a plain CSV or a zip with exactly one manifest-less bundle.")
    issues.finalize()
    return up
