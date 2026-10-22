"""CSV reading and row validation (copy of the frozen csv_service logic, no pandas / QuestionCreate / Firestore).

`parse_row` turns one raw CSV record into a `ParsedItem` or a list of issues. Image resolution is the
caller's job (bundle.py / parse.py); `image_url` is returned in `raw_image` for it.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Optional

from app.lms.content.richtext import EXPLANATION_MAX, STEM_MAX, PASSAGE_BODY_MAX, clean_text
from app.lms.content.types import get_type
from app.lms.core.errors import ValidationFailed

from .parsed import ParsedItem
from .rules import math_section_rule_error, normalize_section, ort_section_error
from .schemas import ImportIssue

BUNDLE_COLUMNS = [
    "section", "topic", "difficulty", "stem", "column_a", "column_b",
    "option_a", "option_b", "option_c", "option_d", "option_e",
    "correct_option", "passage_text", "image_url", "explanation",
]

DIFFICULTY_ALIASES = {
    "easy": "easy", "жеңил": "easy", "женил": "easy", "простой": "easy", "легкий": "easy", "лёгкий": "easy", "1": "easy",
    "medium": "medium", "орто": "medium", "средний": "medium", "2": "medium",
    "hard": "hard", "оор": "hard", "кыйын": "hard", "сложный": "hard", "трудный": "hard", "3": "hard",
}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}

CYRILLIC_TO_LATIN_OPTION = {
    "А": "A", "В": "B", "С": "C", "D": "D", "Д": "D",
    "1": "A", "2": "B", "3": "C", "4": "D", "5": "E", "Е": "E",
}
VALID_OPTIONS = {"A", "B", "C", "D", "E"}
LETTERS = "ABCDE"

COLUMN_ALIASES = {
    "correct_answer": "correct_option", "answer": "correct_option", "correct": "correct_option",
    "correct_choice": "correct_option", "key": "correct_option",
    "passage": "passage_text", "reading_passage": "passage_text", "text": "passage_text", "context": "passage_text",
    "image": "image_url", "img": "image_url", "image_link": "image_url", "diagram": "image_url", "figure": "image_url",
    "feedback": "explanation", "solution": "explanation", "exp": "explanation",
    "section_type": "section", "subject": "section", "sec": "section",
    "diff": "difficulty", "level": "difficulty",
    "subtopic": "topic", "category": "topic",
    "column_a": "column_a", "column a": "column_a", "col_a": "column_a", "cola": "column_a",
    "колонка_а": "column_a", "колонка а": "column_a", "колонка_a": "column_a", "колонка a": "column_a",
    "column_b": "column_b", "column b": "column_b", "col_b": "column_b", "colb": "column_b",
    "колонка_б": "column_b", "колонка б": "column_b", "колонка_b": "column_b", "колонка b": "column_b",
}

SECTION_LABEL_MAX = 40


def safe_str(val: Any) -> str:
    return "" if val is None else str(val).strip()


def get_field_value(raw: dict, field: str, language: str = "ky") -> str:
    """Direct key, legacy `_ky`/`_ru` suffixes, then known aliases (as the old parser)."""
    val = safe_str(raw.get(field))
    if val:
        return val
    primary = f"_{language}"
    secondary = "_ru" if language == "ky" else "_ky"
    for suffix in (primary, secondary):
        val = safe_str(raw.get(f"{field}{suffix}"))
        if val:
            return val
    for alt in (k for k, v in COLUMN_ALIASES.items() if v == field):
        val = safe_str(raw.get(alt))
        if val:
            return val
        for suffix in (primary, secondary):
            val = safe_str(raw.get(f"{alt}{suffix}"))
            if val:
                return val
    return ""


def decode_bytes(data: bytes, *, lenient: bool) -> Optional[str]:
    """Strict utf-8 (BOM allowed) for bundles; plain CSV also falls back to latin-1 like the old parser."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1") if lenient else None


def read_records(text: str, cap: int, *, plain: bool) -> tuple[list[list[str]], list[str], bool]:
    """Lazily read CSV records. Returns (header, data records without blank ones, truncated).

    Stops (truncated=True) at cap+1 non-blank data rows or when more than 2*cap+1 records were scanned, so a
    file of millions of blank lines or junk rows never gets materialised. `plain` treats whitespace-only
    records as blank too."""
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None:
        return [], [], False
    out: list[list[str]] = []
    scanned = 0
    for rec in reader:
        scanned += 1
        if scanned > 2 * cap + 1:
            return header, out, True
        if not rec or (plain and all(not c.strip() for c in rec)):
            continue
        out.append(rec)
        if len(out) > cap:
            return header, out, True
    return header, out, False


def read_plain_csv(text: str, cap: int) -> tuple[list[dict], list[str], bool]:
    """Header-normalised dict rows. Returns (rows, normalised header, truncated). Blank lines skipped,
    ragged rows padded/truncated; stops after cap+1 rows."""
    raw_header, records, truncated = read_records(text, cap, plain=True)
    if not raw_header:
        return [], [], False
    header = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in raw_header]
    drop = {"id", "question_id", "questionid", "question_no", "no", "language", "lang", "usage_type", "usagetype"}
    rows: list[dict] = []
    for rec in records:
        rec = (rec + [""] * len(header))[: len(header)]
        rows.append({h: v for h, v in zip(header, rec) if h not in drop})
    return rows, header, truncated


def _clean_import_tags(value: str) -> list[str]:
    """Same cleaning as the content service (40 chars each, at most 20); extra tags are dropped, never an error."""
    from app.lms.content.service import _clean_tags

    parts = [t.strip() for t in value.split(",") if t.strip()][:200]
    try:
        cleaned = _clean_tags(parts[:20])
    except Exception:
        cleaned = []
    return cleaned


def _issue(code: str, message: str, row: int, column: Optional[str] = None, **kw: Any) -> ImportIssue:
    return ImportIssue(severity="error", code=code, message=message, row=row, column=column, **kw)


def parse_row(raw: dict, row: int, language: str, ort: bool) -> tuple[Optional[ParsedItem], list[ImportIssue], str]:
    """Returns (item | None, errors, raw image_url). `raw` keys are the (normalised) CSV columns."""
    errors: list[ImportIssue] = []
    g = lambda f: get_field_value(raw, f, language)  # noqa: E731
    image_value = g("image_url")

    col_a, col_b = g("column_a"), g("column_b")
    if ort:
        section = normalize_section(g("section"))
    else:
        section = g("section")
    is_comparison = bool(col_a or col_b) or (ort and section == "math_1")
    if is_comparison and not section and ort:
        section = "math_1"

    correct_val = g("correct_option")
    if is_comparison:
        if not correct_val:
            errors.append(_issue("row_invalid", "Required field 'correct_option' is missing or empty for quantitative comparison.",
                                 row, "correct_option"))
    else:
        required = ["stem", "option_a", "option_b", "option_c", "option_d", "correct_option"]
        if ort:
            required.insert(0, "section")
        for f in required:
            if not g(f):
                errors.append(_issue("row_invalid", f"Required field '{f}' is missing or empty.", row, f))
    if errors:
        return None, errors, image_value

    if ort:
        msg = ort_section_error(section)
        if msg:
            errors.append(_issue("row_invalid", msg, row, "section"))
    elif len(section) > SECTION_LABEL_MAX:
        errors.append(_issue("row_invalid", f"section must be at most {SECTION_LABEL_MAX} characters.", row, "section"))

    diff_raw = g("difficulty").lower()
    difficulty = DIFFICULTY_ALIASES.get(diff_raw, diff_raw)
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = "medium"

    correct_raw = correct_val.replace(")", "").replace(".", "").replace("(", "").strip().upper()
    correct = CYRILLIC_TO_LATIN_OPTION.get(correct_raw, correct_raw)
    if correct not in VALID_OPTIONS:
        errors.append(_issue("row_invalid", f"Invalid correct_option '{correct_raw}'. Must be one of: A, B, C, D, E.",
                             row, "correct_option"))

    if ort and not errors:
        rule = math_section_rule_error(section, col_a, col_b)
        if rule:
            errors.append(_issue("row_invalid", rule[1], row, rule[0]))
    elif not ort and is_comparison:
        for name, val in (("column_a", col_a), ("column_b", col_b)):
            if not val:
                errors.append(_issue("row_invalid", f"Quantitative comparison needs both columns: {name} is empty.", row, name))
    if is_comparison and correct in VALID_OPTIONS and correct == "E" and not errors:
        errors.append(_issue("correct_option_not_allowed",
                             "Quantitative comparison answers must be A, B, C or D.", row, "correct_option"))
    if errors:
        return None, errors, image_value

    stem = g("stem")
    options = {L: g(f"option_{L.lower()}") for L in LETTERS}
    if is_comparison:
        options = {}
    elif correct == "E" and not options["E"]:
        errors.append(_issue("correct_option_not_allowed",
                             "correct_option is E but the question has only 4 options (A-D).", row, "correct_option"))
        return None, errors, image_value

    passage = g("passage_text") or None
    explanation = g("explanation") or None
    topic = g("topic") or ("Салыштыруу" if is_comparison else "General")
    tags = _clean_import_tags(g("tags"))

    try:
        stem = clean_text(stem, STEM_MAX)
        explanation = clean_text(explanation, EXPLANATION_MAX) if explanation else None
        passage = clean_text(passage, PASSAGE_BODY_MAX) if passage else None
    except ValueError as e:
        errors.append(_issue("row_invalid", str(e), row, "stem"))
        return None, errors, image_value

    if is_comparison:
        qtype = "comparison"
        payload: dict = {"column_a": col_a, "column_b": col_b, "correct": correct}
    else:
        qtype = "single_choice"
        payload = {
            "choices": [{"id": L, "text": options[L]} for L in LETTERS if options[L]],
            "correct": correct,
        }
    try:
        payload = get_type(qtype).validate(payload)
    except ValidationFailed as exc:
        for d in exc.details or [{"loc": [], "msg": exc.message}]:
            loc = [str(p) for p in d.get("loc", [])]
            col = {"column_a": "column_a", "column_b": "column_b", "correct": "correct_option"}.get(loc[0] if loc else "", None)
            errors.append(_issue("row_invalid", f"{'.'.join(loc)}: {d.get('msg')}".strip(": "), row, col,
                                 params={"loc": loc}))
        return None, errors, image_value

    item = ParsedItem(
        row=row, position=row, source_ref=None, section=section, topic=topic, difficulty=difficulty,
        q_num=None, type=qtype, payload=payload, stem=stem, explanation=explanation, correct=correct,
        tags=tags, passage_key=passage, options=options, column_a=col_a, column_b=col_b,
    )
    return item, [], image_value
