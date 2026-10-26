"""Import format derived from an exam template version (PHASE_7B_DESIGN 8, EXAM_TEMPLATES_DESIGN 5).

A template version does not define a new file format: it gives the one general format (`content/importers/
general_csv.py`, manifest `format: "lms-bundle"`) a validation profile and a downloadable header + example rows.

- `format_for(db, version) -> ImportFormatOut`: sections (key, parameter options, titles, allowed types, passages,
  counts), per section the columns it uses, the full header.
- `csv_for(fmt, lang) -> bytes`: UTF-8 CSV with BOM, the header row and one example row per section, commented out
  with `#` (the parser skips comment rows; remove the `#` and the row imports as is).
- `profile_from_format(fmt, keys)`: the `TemplateProfile` the parser validates against.
- `resolve_import_target(db, ctx, course, opts)`: the profile and attach target of one import request
  (`exam_template_version_id` / `assessment_id` / `attach_to_assessment_id`), 404/422 before anything is parsed.
- `attach_imported(...)`: the commit-only attach step through `builder.attach_questions` (flush only; the
  importer's transaction commits or rolls back everything)."""
from __future__ import annotations

import csv
import io
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from pydantic import BaseModel, Field
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.content.importers.general_csv import (
    COMMON_COLUMNS, GENERAL_FORMAT, GENERAL_FORMAT_VERSION, PASSAGE_COLUMNS, ProfileSection, TemplateProfile,
    type_columns,
)
from app.lms.content.importers.schemas import ImportAttachSummary, ImportOptions
from app.lms.content.types import REGISTRY
from app.lms.core.errors import NotFound, ValidationFailed
from app.lms.exam_templates import ids
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion
from app.lms.exam_templates.spec import ExamTemplateSpec


# ------------------------------------------------------------------------------------------------ format

class ImportFormatSection(BaseModel):
    position: int                                   # 0-based, the order of the template's sections
    key: Optional[str] = None
    options: list[str] = Field(default_factory=list)  # parameter options when the key is chosen at instantiate
    title: Optional[dict] = None
    allowed_types: list[str]
    allow_passages: bool
    min_items: Optional[int] = None
    max_items: Optional[int] = None
    columns: list[str]


class ImportFormatOut(BaseModel):
    template_id: uuid.UUID
    version_id: uuid.UUID
    version_no: int
    format: str = GENERAL_FORMAT
    format_version: int = GENERAL_FORMAT_VERSION
    header: list[str]
    passage_columns: list[str] = Field(default_factory=list)
    sections: list[ImportFormatSection]


# Header order: identification, the question text, type columns, then metadata and passages.
_LEAD = ("section", "type", "stem")
_TAIL = tuple(c for c in COMMON_COLUMNS if c not in _LEAD)


def _columns(types: list[str], passages: bool) -> list[str]:
    tcols = {c for t in types for c in REGISTRY[t].import_columns}
    out = list(_LEAD) + [c for c in type_columns() if c in tcols] + list(_TAIL)
    return out + (list(PASSAGE_COLUMNS) if passages else [])


def format_for(db: Session, version: ExamTemplateVersion) -> ImportFormatOut:
    """The import format of one (immutable) template version. `db` is unused today (the version row carries the
    whole spec); it stays in the signature for parity with the other derivations."""
    spec = ExamTemplateSpec.model_validate(version.spec)
    options: dict[int, list[str]] = {p.section_index: list(p.options) for p in spec.parameters}
    sections: list[ImportFormatSection] = []
    all_types: list[str] = []
    any_passages = False
    for i, s in enumerate(spec.sections):
        types = [t for t in s.allowed_types if t in REGISTRY]
        passages = bool(s.allow_passages) and any(REGISTRY[t].supports_passages for t in types)
        any_passages = any_passages or passages
        all_types += [t for t in types if t not in all_types]
        sections.append(ImportFormatSection(
            position=i, key=s.key, options=options.get(i, []), title=dict(s.title) if s.title else None,
            allowed_types=types, allow_passages=passages, min_items=s.min_items, max_items=s.max_items,
            columns=_columns(types, passages)))
    return ImportFormatOut(template_id=version.template_id, version_id=version.id, version_no=version.version_no,
                           header=_columns(all_types, any_passages),
                           passage_columns=list(PASSAGE_COLUMNS) if any_passages else [], sections=sections)


def profile_from_format(fmt: ImportFormatOut, keys: Optional[dict[int, str]] = None) -> TemplateProfile:
    """`keys`: the section keys of the assessment the import targets, by position (they win over the template's
    keys and parameter options, which stay accepted as aliases)."""
    keys = keys or {}
    out = []
    for s in fmt.sections:
        key = keys.get(s.position) or s.key
        alts = [o for o in ([s.key] if s.key else []) + list(s.options) if o and o != key]
        out.append(ProfileSection(
            index=s.position, key=key, options=tuple(alts) if key else tuple(s.options),
            titles=tuple(str(v) for v in (s.title or {}).values() if v), allowed_types=tuple(s.allowed_types),
            allow_passages=s.allow_passages, min_items=s.min_items, max_items=s.max_items))
    return TemplateProfile(version_id=str(fmt.version_id), sections=tuple(out))


# ------------------------------------------------------------------------------------------------ CSV download

# Fixed ASCII placeholders (no translated prose: the UI shows the translated help, PHASE_7B_DESIGN 8).
_OPTIONS = {"option_a": "Option A", "option_b": "Option B", "option_c": "Option C", "option_d": "Option D"}
EXAMPLE_VALUES: dict[str, dict[str, str]] = {
    "single_choice": {"stem": "Question text", **_OPTIONS, "correct_option": "A"},
    "multiple_answers": {"stem": "Question text", **_OPTIONS, "correct_option": "A,C"},
    "true_false": {"stem": "Statement", "correct_option": "A"},
    "comparison": {"stem": "", "column_a": "2+2", "column_b": "5", "correct_option": "B"},
    "numeric": {"stem": "Question text", "answer": "42", "tolerance": "0"},
    "short_text": {"stem": "Question text", "answers": "answer|other answer", "case_sensitive": "false"},
    "essay": {"stem": "Question text", "rubric": "Rubric note", "max_points": "5"},
}
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: str) -> str:
    """Spreadsheet formula injection guard for exported cells (a leading ' makes the cell text)."""
    return "'" + value if value and value.startswith(_FORMULA_START) else value


def _title(title: Optional[dict], lang: str) -> Optional[str]:
    if not title:
        return None
    v = title.get(lang) or next((x for x in title.values() if x), None)
    return str(v).strip() if v else None


def section_label(fmt: ImportFormatOut, s: ImportFormatSection, lang: str) -> str:
    """What the example row writes in `section`: the title in `lang` when it names this section unambiguously,
    else the key / first parameter option / `section_<n>`."""
    t = _title(s.title, lang)
    if t:
        low = t.casefold()
        clash = any(o is not s and ((o.key and o.key.casefold() == low) or any(
            str(v).strip().casefold() == low for v in (o.title or {}).values() if v)) for o in fmt.sections)
        if not clash:
            return t
    return s.key or (s.options[0] if s.options else f"section_{s.position + 1}")


def csv_for(fmt: ImportFormatOut, lang: str) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(fmt.header)
    for s in fmt.sections:
        row = {c: "" for c in fmt.header}
        t = s.allowed_types[0]
        row.update(EXAMPLE_VALUES.get(t, {"stem": "Question text"}))
        row["type"] = t
        row["difficulty"] = "medium"
        # "#" first: a comment row for the parser, and never a formula for a spreadsheet
        row["section"] = "#" + section_label(fmt, s, lang)
        w.writerow([row["section"]] + [safe_cell(row.get(c, "")) for c in fmt.header[1:]])
    return ("﻿" + buf.getvalue()).encode("utf-8")


# --- Phase 7b S7 begin --- (UX fix: Cyrillic titles (ru / ky) are transliterated into the ASCII file name slug)
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "i",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "iu",
    "я": "ia", "ң": "ng", "ө": "o", "ү": "u",
}


def transliterate(text: str) -> str:
    """Lower-case Latin rendering of a ru / ky text (other characters unchanged)."""
    return "".join(_TRANSLIT.get(ch, ch) for ch in text.lower())
# --- Phase 7b S7 end ---


def csv_filename(template: ExamTemplate, version_no: int, lang: str) -> str:
    title = _title(template.title, lang) or ""
    slug = re.sub(r"[^a-z0-9]+", "-", transliterate(title)).strip("-")[:40].strip("-") or "template"
    return f"import-format-{slug}-v{version_no}.csv"


# ------------------------------------------------------------------------------------------------ visibility

def visible_in_course(ctx: Any, course: Any, t: ExamTemplate) -> bool:
    """PHASE_7B_DESIGN 5.2 for one row: S2's `scopes.visible_in_course` (the same rule as `scopes.visible_stmt`)."""
    from app.lms.exam_templates import scopes

    return scopes.visible_in_course(ctx.user.id, course, t)


# ------------------------------------------------------------------------------------------------ import target

@dataclass
class ImportTarget:
    ctx: Any
    course: Any
    version: ExamTemplateVersion
    profile: TemplateProfile
    attach_id: Optional[uuid.UUID] = None
    labels: dict[int, str] = field(default_factory=dict)


def _uuid(value: str, loc: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise ValidationFailed(f"invalid {loc}", details=[{"loc": [loc], "msg": "invalid uuid"}]) from None


def _mismatch(msg: str) -> ValidationFailed:
    return ValidationFailed(msg, code=ids.E_ATTACH_TARGET_MISMATCH,
                            details=[{"loc": ["attach_to_assessment_id"], "msg": msg}])


def _check_attach(a: Any, version_id: Optional[uuid.UUID]) -> None:
    if a.status != "draft":
        raise _mismatch("Questions can be added only to a draft exam.")
    if a.exam_template_version_id is None or a.exam_template_version_id != version_id:
        raise _mismatch("The exam was not created from this exam template version.")


def resolve_import_target(db: Session, ctx: Any, course: Any, opts: ImportOptions) -> Optional[ImportTarget]:
    """None for a plain import. Raises 404 (`assessment_not_found`, `template_not_found`) or 422
    (`format_mismatch`, `not_a_template_assessment`, `attach_target_mismatch`)."""
    from app.lms.assessments import repository as arepo

    if not (opts.exam_template_version_id or opts.assessment_id or opts.attach_to_assessment_id):
        return None
    if opts.exam_type is not None:
        raise ValidationFailed("Exam template validation uses the general format, not the ORT format",
                               code=ids.E_FORMAT_MISMATCH, details=[{"loc": ["exam_type"], "msg": "not allowed"}])
    source = None
    version_id: Optional[uuid.UUID] = None
    if opts.assessment_id:
        source = arepo.load_assessment(db, course.id, _uuid(opts.assessment_id, "assessment_id"))
        if source.exam_template_version_id is None:
            raise ValidationFailed("This exam was not created from an exam template",
                                   code=ids.E_NOT_A_TEMPLATE_ASSESSMENT,
                                   details=[{"loc": ["assessment_id"], "msg": "not a template assessment"}])
        version_id = source.exam_template_version_id
    explicit = _uuid(opts.exam_template_version_id, "exam_template_version_id") \
        if opts.exam_template_version_id else None
    if explicit is not None and version_id is not None and explicit != version_id:
        raise ValidationFailed("exam_template_version_id does not match the exam's template version",
                               details=[{"loc": ["exam_template_version_id"], "msg": "mismatch"}])
    version_id = version_id or explicit
    attach = None
    if opts.attach_to_assessment_id:
        attach = arepo.load_assessment(db, course.id, _uuid(opts.attach_to_assessment_id, "attach_to_assessment_id"))
        version_id = version_id or attach.exam_template_version_id
        _check_attach(attach, version_id)
    version = db.get(ExamTemplateVersion, version_id) if version_id else None
    template = db.get(ExamTemplate, version.template_id) if version is not None else None
    if template is None or template.deleted_at is not None:
        raise NotFound("Exam template not found", code=ids.E_TEMPLATE_NOT_FOUND)
    if source is None and attach is None and not visible_in_course(ctx, course, template):
        # an explicit version: only templates the caller may pick in this course (never 403, 5.2)
        raise NotFound("Exam template not found", code=ids.E_TEMPLATE_NOT_FOUND)
    keys: dict[int, str] = {}
    holder = source or attach
    if holder is not None:
        for i, s in enumerate(arepo.load_sections(db, holder.id)):
            if s.key:
                keys[i] = s.key
    profile = profile_from_format(format_for(db, version), keys)
    labels = {s.index: s.label_for(s.key or "") for s in profile.sections}
    return ImportTarget(ctx=ctx, course=course, version=version, profile=profile,
                        attach_id=attach.id if attach is not None else None, labels=labels)


# ------------------------------------------------------------------------------------------------ attach

@contextmanager
def capture_new_questions(db: Session) -> Iterator[list]:
    """Collects the BankQuestion rows added to the session while the block runs (the importer creates them)."""
    from app.lms.content.models import BankQuestion

    created: list = []

    def _on_add(session, instance):
        if isinstance(instance, BankQuestion):
            created.append(instance)

    event.listen(db, "transient_to_pending", _on_add)
    try:
        yield created
    finally:
        event.remove(db, "transient_to_pending", _on_add)


def position_bases(db: Session, up: Any, opts: ImportOptions) -> dict[int, int]:
    """Per bundle (by `id`), the offset the writer adds to row positions (CSV append into `target_bank_id`).
    Read before the writer runs."""
    from app.lms.content.models import BankQuestion

    out: dict[int, int] = {}
    for b in up.bundles:
        base = 0
        if not b.has_manifest and opts.target_bank_id:
            base = db.execute(select(func.max(BankQuestion.position)).where(
                BankQuestion.bank_id == uuid.UUID(opts.target_bank_id))).scalar() or 0
        out[id(b)] = base
    return out


def attach_imported(db: Session, target: ImportTarget, up: Any, summaries: list, bases: dict[int, int],
                    created: list) -> ImportAttachSummary:
    """Adds every imported / updated / unchanged question of the upload to the target's section with the same
    position as its template section. Flush only; raises (whole import rolled back) on a target mismatch."""
    from app.lms.assessments import builder
    from app.lms.assessments import repository as arepo
    from app.lms.content.models import BankQuestion

    a = arepo.load_assessment(db, target.course.id, target.attach_id, for_update=True)
    _check_attach(a, target.version.id)
    sections = arepo.load_sections(db, a.id)
    per_index: dict[int, list[uuid.UUID]] = {}
    for b, s in zip(up.bundles, summaries):
        if not s.bank_id:
            continue
        bank_id = uuid.UUID(s.bank_id)
        refs = [it.source_ref for it in b.items if it.source_ref]
        by_ref: dict[str, uuid.UUID] = {}
        for k in range(0, len(refs), 500):
            for qid, ref in db.execute(select(BankQuestion.id, BankQuestion.source_ref).where(
                    BankQuestion.bank_id == bank_id, BankQuestion.source_ref.in_(refs[k:k + 500]),
                    BankQuestion.deleted_at.is_(None))):
                by_ref[ref] = qid
        new_by_pos = {q.position: q.id for q in created if q.bank_id == bank_id and q.source_ref is None}
        base = bases.get(id(b), 0)
        for it in b.items:
            idx = getattr(it, "profile_index", None)
            qid = by_ref.get(it.source_ref) if it.source_ref else new_by_pos.get(base + it.position)
            if qid is not None and idx is not None:
                per_index.setdefault(idx, []).append(qid)
    out = ImportAttachSummary(assessment_id=str(a.id))
    for idx in sorted(per_index):
        if idx >= len(sections):
            raise _mismatch("The exam has no section for some imported questions.")
        res = builder.attach_questions(db, target.ctx, target.course, a, sections[idx], per_index[idx])
        label = target.labels.get(idx) or f"section_{idx + 1}"
        out.added += res.added
        out.sections[label] = out.sections.get(label, 0) + res.added
        out.section_positions.setdefault(label, idx)  # Phase 7b S7
        for sk in res.skipped:
            out.skipped[sk.code] = out.skipped.get(sk.code, 0) + 1
        # --- Phase 7b S7: which cap a too_many_items skip hit (the section's max_items or the exam's limit) ---
        full = sum(1 for sk in res.skipped if sk.code == "too_many_items")
        if full:
            mx = (sections[idx].rules or {}).get("max_items")
            out.skip_details.append({"code": "too_many_items", "section": label, "position": idx,
                                     "max": mx or settings.ASSESSMENT_MAX_ITEMS,
                                     "scope": "section" if mx else "exam", "count": full})
    return out
