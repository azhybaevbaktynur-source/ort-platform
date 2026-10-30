"""Field types: builder validation and answer validation (PHASE_9_DESIGN 4.10). Pure functions: no DB, no logging.

PII rule (invariant 5): an answer error names the field key and a code (`required`, `too_long`, `bad_option`,
`bad_format`), **never the submitted value**; messages are constant strings. Nothing here logs."""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from app.lms.core.errors import ValidationFailed
from app.lms.enrollment_forms import ids

_KEY_RE = re.compile(ids.FIELD_KEY_RE)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # = invitations.service._EMAIL_RE (normalize_email)
_PHONE_STRIP_RE = re.compile(r"[\s\-().]")
_PHONE_RE = re.compile(r"^\+?\d+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEXT_TYPES = ("short_text", "long_text")
TEXT_LIMITS = {"short_text": (ids.SHORT_TEXT_DEFAULT_MAX, ids.SHORT_TEXT_MAX),
               "long_text": (ids.LONG_TEXT_DEFAULT_MAX, ids.LONG_TEXT_MAX)}
EMAIL_MAX = 255


# ------------------------------------------------------------------ builder (teacher input; no PII involved)

def _builder_error(loc: list, code: str) -> dict:
    return {"loc": loc, "msg": code, "type": code}


def validate_builder_fields(fields: list, default_language: str) -> list[dict]:
    """`FieldIn` list -> rows for `enrollment_form_fields` (key, type, label, help, options, required, position,
    pii_category, max_len). Refusals: 422 `too_many_fields`, or 422 `validation_failed` with one detail per
    problem (`duplicate_key`, `label_default_language`, `options_required`, `options_not_allowed`,
    `duplicate_option`, `max_len_not_allowed`, `max_len_too_large`, `bounds_not_allowed`, `bounds_invalid`)."""
    if len(fields) > ids.FIELDS_PER_FORM_MAX:
        raise ValidationFailed("Too many fields", code=ids.E_TOO_MANY_FIELDS,
                               details=[_builder_error(["fields"], ids.E_TOO_MANY_FIELDS)])
    errors: list[dict] = []
    rows: list[dict] = []
    seen: set[str] = set()
    for i, f in enumerate(fields):
        loc = ["fields", i]
        if f.key in seen:
            errors.append(_builder_error(loc + ["key"], "duplicate_key"))
        seen.add(f.key)
        if not (f.label.get(default_language) or "").strip():
            errors.append(_builder_error(loc + ["label"], "label_default_language"))
        options = None
        if f.type in ids.CHOICE_TYPES:
            if not f.options:
                errors.append(_builder_error(loc + ["options"], "options_required"))
            else:
                keys = [o.key for o in f.options]
                if len(set(keys)) != len(keys):
                    errors.append(_builder_error(loc + ["options"], "duplicate_option"))
                for j, o in enumerate(f.options):
                    if not (o.label.get(default_language) or "").strip():
                        errors.append(_builder_error(loc + ["options", j, "label"], "label_default_language"))
                options = [{"key": o.key, "label": o.label} for o in f.options]
        elif f.options:
            errors.append(_builder_error(loc + ["options"], "options_not_allowed"))
        if f.type == "number":
            if f.bounds is not None:
                lo, hi = f.bounds.min, f.bounds.max
                bad = any(v is not None and not math.isfinite(v) for v in (lo, hi))
                if bad or (lo is not None and hi is not None and lo > hi):
                    errors.append(_builder_error(loc + ["bounds"], "bounds_invalid"))
                elif lo is not None or hi is not None:
                    options = {"min": lo, "max": hi}
        elif f.bounds is not None:
            errors.append(_builder_error(loc + ["bounds"], "bounds_not_allowed"))
        max_len = f.max_len
        if max_len is not None:
            if f.type not in TEXT_TYPES:
                errors.append(_builder_error(loc + ["max_len"], "max_len_not_allowed"))
            elif max_len > TEXT_LIMITS[f.type][1]:
                errors.append(_builder_error(loc + ["max_len"], "max_len_too_large"))
        rows.append(dict(key=f.key, type=f.type, label=f.label, help=f.help or None, options=options,
                         required=bool(f.required), position=i, pii_category=f.pii_category, max_len=max_len))
    if errors:
        raise ValidationFailed("Invalid form fields", details=errors)
    return rows


def field_out_dict(row) -> dict:
    """Builder row (ORM or dict-like) -> `FieldOut` kwargs: number bounds move from `options` to `bounds`."""
    get = (lambda k: row[k]) if isinstance(row, dict) else (lambda k: getattr(row, k))
    options = get("options")
    bounds = None
    if get("type") == "number":
        bounds, options = (options if isinstance(options, dict) else None), None
    return dict(id=get("id"), key=get("key"), type=get("type"), label=get("label"), help=get("help"),
                options=options, bounds=bounds, required=get("required"), position=get("position"),
                pii_category=get("pii_category"), max_len=get("max_len"))


# ------------------------------------------------------------------ answers (applicant input; PII)

class _Bad(Exception):
    def __init__(self, code: str):
        self.code = code


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, list) and not value)


def _text(value: Any, ftype: str, max_len: Optional[int]) -> str:
    if not isinstance(value, str):
        raise _Bad(ids.A_BAD_FORMAT)
    text = value.replace("\x00", "").strip()
    default, cap = TEXT_LIMITS[ftype]
    if len(text) > min(max_len or default, cap):
        raise _Bad(ids.A_TOO_LONG)
    return text


def _option_keys(options: Any) -> set:
    return {o.get("key") for o in (options or []) if isinstance(o, dict)}


def _number(value: Any, bounds: Any) -> float | int:
    if isinstance(value, bool):
        raise _Bad(ids.A_BAD_FORMAT)
    if isinstance(value, str):
        try:
            value = float(value.strip().replace(",", "."))
        except ValueError:
            raise _Bad(ids.A_BAD_FORMAT) from None
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _Bad(ids.A_BAD_FORMAT)
    if isinstance(bounds, dict):
        lo, hi = bounds.get("min"), bounds.get("max")
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            raise _Bad(ids.A_BAD_FORMAT)
    if isinstance(value, float) and value.is_integer() and abs(value) < 2 ** 53:
        return int(value)
    return value


def _date(value: Any, today: date) -> str:
    if not isinstance(value, str) or not _DATE_RE.match(value.strip()):
        raise _Bad(ids.A_BAD_FORMAT)
    try:
        d = date.fromisoformat(value.strip())
    except ValueError:
        raise _Bad(ids.A_BAD_FORMAT) from None
    if not (ids.DATE_YEAR_MIN <= d.year <= today.year + 1):
        raise _Bad(ids.A_BAD_FORMAT)
    return d.isoformat()


def _email(value: Any) -> str:
    if not isinstance(value, str):
        raise _Bad(ids.A_BAD_FORMAT)
    email = value.strip().lower()
    if len(email) > EMAIL_MAX:
        raise _Bad(ids.A_TOO_LONG)
    if not _EMAIL_RE.match(email):
        raise _Bad(ids.A_BAD_FORMAT)
    return email


def _phone(value: Any) -> str:
    if not isinstance(value, str):
        raise _Bad(ids.A_BAD_FORMAT)
    phone = _PHONE_STRIP_RE.sub("", value.strip())
    digits = phone.lstrip("+")
    if not _PHONE_RE.match(phone) or not (ids.PHONE_DIGITS_MIN <= len(digits) <= ids.PHONE_DIGITS_MAX):
        raise _Bad(ids.A_BAD_FORMAT)
    return phone


def _one(field, value: Any, today: date) -> Any:
    ftype = field.type
    if ftype in TEXT_TYPES:
        return _text(value, ftype, field.max_len)
    if ftype == "single_choice":
        if not isinstance(value, str) or value not in _option_keys(field.options):
            raise _Bad(ids.A_BAD_OPTION)
        return value
    if ftype == "multi_choice":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise _Bad(ids.A_BAD_FORMAT)
        if len(value) > ids.MULTI_CHOICE_MAX or len(set(value)) != len(value):
            raise _Bad(ids.A_BAD_FORMAT)
        keys = _option_keys(field.options)
        if any(v not in keys for v in value):
            raise _Bad(ids.A_BAD_OPTION)
        return list(value)
    if ftype == "number":
        return _number(value, field.options)
    if ftype == "date":
        return _date(value, today)
    if ftype == "email":
        return _email(value)
    if ftype == "phone":
        return _phone(value)
    raise _Bad(ids.A_BAD_FORMAT)  # pragma: no cover - CHECK constraint on type


def validate_answers(fields: Iterable, answers: Any, *, today: Optional[date] = None) -> dict:
    """Answers checked against the form's fields -> the cleaned answers to store (optional empty answers dropped).

    Refusal: 422 `validation_failed` whose details are `[{"field_key", "type"}]` only. Unknown keys are reported
    as `bad_format` under their key when it looks like a field key (else `_unknown`); the value is never echoed."""
    today = today or datetime.now(timezone.utc).date()
    if not isinstance(answers, dict):
        raise ValidationFailed("Invalid answers", details=[{"field_key": "_answers", "type": ids.A_BAD_FORMAT}])
    fields = list(fields)
    known = {f.key for f in fields}
    errors: list[dict] = []
    for key in answers:
        if key not in known:
            safe = key if isinstance(key, str) and _KEY_RE.match(key) else "_unknown"
            errors.append({"field_key": safe, "type": ids.A_BAD_FORMAT})
    clean: dict = {}
    for f in sorted(fields, key=lambda x: x.position):
        value = answers.get(f.key)
        if _empty(value):
            if f.required:
                errors.append({"field_key": f.key, "type": ids.A_REQUIRED})
            continue
        try:
            clean[f.key] = _one(f, value, today)
        except _Bad as bad:
            errors.append({"field_key": f.key, "type": bad.code})
    if errors:
        raise ValidationFailed("Some answers are not valid", details=errors[:ids.FIELDS_PER_FORM_MAX + 5])
    return clean
