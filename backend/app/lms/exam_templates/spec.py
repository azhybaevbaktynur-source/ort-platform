"""`ExamTemplateSpec`: the JSON shape of a template version (EXAM_TEMPLATES_DESIGN 3.1, PHASE_7B_DESIGN 4).

Two layers:
- the Pydantic models check shapes, ranges and block keys (`extra="forbid"` everywhere);
- `validate_spec(db, spec_dict, owner)` adds the cross-field rules (section rules through
  `assessments/rules.py::normalize_rules`, timers, unique keys, parameters) and the grading scheme visibility, and
  raises one 422 with every problem as `details=[{loc, msg}]`.

Always go through `validate_spec` for user input; `ExamTemplateSpec.model_validate` alone is for specs that were
validated before (stored versions). `spec_json(spec)` is the stored form, `spec_hash(spec)` its canonical hash."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.assessments.rules import normalize_rules
from app.lms.assessments.schemas import Navigation, ResultsPolicy, ScorePolicy
from app.lms.content.types import TYPE_NAMES
from app.lms.content.types.base import VALIDATION_DETAILS_MAX
from app.lms.core.errors import ValidationFailed
from app.lms.core.types import localized_text
from app.lms.exam_templates import ids
from app.lms.exam_templates.blocks import DISPLAY_MODES, PASSAGE_DISPLAYS, RESULT_VIEWS, SPEC_IMPORTER_PROFILES

SECTION_KEY_PATTERN = r"^[a-z0-9_]{1,40}$"
_KEY_RE = re.compile(SECTION_KEY_PATTERN)
_BINDS_RE = re.compile(r"^sections\[(\d+)\]\.key$")
MAX_SECTIONS = settings.ASSESSMENT_MAX_SECTIONS  # security review 7b: never more than an assessment may hold
MAX_PARAMETERS = 5
MAX_PARAMETER_OPTIONS = 50


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _one_of(value: Optional[str], allowed: tuple, what: str) -> Optional[str]:
    if value is not None and value not in allowed:
        raise ValueError(f"{what} must be one of " + ", ".join(allowed))
    return value


class SpecDefaults(_M):
    """Assessment settings copied at instantiate; all stay editable on the assessment (6a 5.4 editable list)."""
    time_limit_s: Optional[StrictInt] = Field(default=None, ge=60, le=86400)
    allowed_attempts: StrictInt = 1
    score_policy: ScorePolicy = "highest"
    results_policy: ResultsPolicy = "after_submit"
    show_correct_answers: StrictBool = False
    shuffle_items: StrictBool = False
    shuffle_choices: StrictBool = False

    @field_validator("allowed_attempts")
    @classmethod
    def _attempts(cls, v: int) -> int:
        if v != -1 and not 1 <= v <= 100:
            raise ValueError("allowed_attempts must be -1 (unlimited) or 1..100")
        return v


class SpecSection(_M):
    key: Optional[str] = Field(default=None, pattern=SECTION_KEY_PATTERN)
    title: Optional[localized_text(200)] = None
    instructions: Optional[localized_text(5000)] = None
    time_limit_s: Optional[StrictInt] = Field(default=None, ge=60, le=86400)
    min_items: Optional[StrictInt] = Field(default=None, ge=1, le=10_000)
    max_items: Optional[StrictInt] = Field(default=None, ge=1, le=10_000)
    allowed_types: list[str] = Field(min_length=1, max_length=len(TYPE_NAMES))
    allow_passages: StrictBool = False
    passage_display: Optional[str] = None

    @field_validator("passage_display")
    @classmethod
    def _pd(cls, v):
        return _one_of(v, PASSAGE_DISPLAYS, "passage_display")

    def rules_input(self) -> dict:
        """The section rules as `normalize_rules` input, `None` values dropped (what the builder stores)."""
        raw = {"allowed_types": list(self.allowed_types), "allow_passages": self.allow_passages,
               "max_items": self.max_items, "min_items": self.min_items}
        return {k: v for k, v in raw.items() if v is not None}

    def rules(self) -> dict:
        """Normalized section rules for `assessment_sections.rules` (raises 422 like the builder)."""
        return normalize_rules(self.rules_input())


class SpecScoring(_M):
    grading_scheme_version_id: uuid.UUID


class SpecParameter(_M):
    key: str = Field(pattern=SECTION_KEY_PATTERN)
    kind: Literal["choice"]
    options: list[str] = Field(min_length=1, max_length=MAX_PARAMETER_OPTIONS)
    binds: str = Field(pattern=_BINDS_RE.pattern)

    @field_validator("options")
    @classmethod
    def _options(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("options must be unique")
        if any(not _KEY_RE.match(o) for o in v):
            raise ValueError("every option must match " + SECTION_KEY_PATTERN)
        return v

    @property
    def section_index(self) -> int:
        """Index into `sections` of the section whose key this parameter supplies."""
        return int(_BINDS_RE.match(self.binds).group(1))


class ExamTemplateSpec(_M):
    model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True, serialize_by_alias=True)

    schema_: Literal[1] = Field(default=ids.SPEC_SCHEMA, alias="schema")
    navigation: Navigation = "free"
    display_mode: str = "one_per_page"
    passage_display: Optional[str] = None
    result_view: Optional[str] = None
    importer_profile: Optional[str] = None
    defaults: SpecDefaults = Field(default_factory=SpecDefaults)
    sections: list[SpecSection] = Field(min_length=1, max_length=MAX_SECTIONS)
    scoring: Optional[SpecScoring] = None
    parameters: list[SpecParameter] = Field(default_factory=list, max_length=MAX_PARAMETERS)
    lock_scope: list[str] = Field(default_factory=list)

    @field_validator("display_mode")
    @classmethod
    def _dm(cls, v):
        return _one_of(v, DISPLAY_MODES, "display_mode")

    @field_validator("passage_display")
    @classmethod
    def _pd(cls, v):
        return _one_of(v, PASSAGE_DISPLAYS, "passage_display")

    @field_validator("result_view")
    @classmethod
    def _rv(cls, v):
        return _one_of(v, RESULT_VIEWS, "result_view")

    @field_validator("importer_profile")
    @classmethod
    def _ip(cls, v):
        return _one_of(v, SPEC_IMPORTER_PROFILES, "importer_profile")

    @field_validator("lock_scope")
    @classmethod
    def _ls(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("lock_scope entries must be unique")
        bad = [x for x in v if x not in ids.LOCK_SCOPE_KEYS]
        if bad:
            raise ValueError("unknown lock_scope keys: " + ", ".join(bad))
        return v

    @property
    def scheme_version_id(self) -> Optional[uuid.UUID]:
        return self.scoring.grading_scheme_version_id if self.scoring else None

    def locked_fields(self) -> frozenset:
        """The course-template lock field names this spec's `lock_scope` covers (5.4)."""
        return ids.expand_lock_scope(self.lock_scope)


# ------------------------------------------------------------------------------------------- owner and validation

class SpecOwnerLike(Protocol):
    owner_scope: str
    owner_user_id: Optional[str]


@dataclass(frozen=True)
class SpecOwner:
    """Who a spec is validated for (an `ExamTemplate` row works the same way)."""
    owner_scope: str
    owner_user_id: Optional[str] = None


def spec_invalid(details: list[dict]) -> ValidationFailed:
    return ValidationFailed("Invalid exam template", code=ids.E_SPEC_INVALID, details=details)


# --- Phase 7b S7 begin --- (UX fix: every `spec_invalid` detail carries a machine `type` (pydantic error types plus
# the cross-check types below) and, for range / length errors, the numeric `limit`, so the UI translates it.)
_LIMIT_CTX = ("ge", "gt", "le", "lt", "max_length", "min_length")


def _spec_details(exc: ValidationError) -> list[dict]:
    """`{loc, msg, type[, limit]}` per pydantic error (bounded like `validation_details`)."""
    errors = exc.errors(include_url=False, include_context=True, include_input=False)
    out = []
    for e in errors[:VALIDATION_DETAILS_MAX]:
        d = {"loc": [str(p) for p in e.get("loc", ())], "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))}
        ctx = e.get("ctx") or {}
        for k in _LIMIT_CTX:
            v = ctx.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                d["limit"] = v
                break
        out.append(d)
    if len(errors) > VALIDATION_DETAILS_MAX:
        left = len(errors) - VALIDATION_DETAILS_MAX
        out.append({"loc": [], "msg": f"{left} more errors are not shown", "truncated": left, "type": "truncated"})
    return out


_RULE_TYPES = {"must not exceed max_items": "min_exceeds_max", "must be a positive integer": "positive_int",
               "invalid type list": "invalid_types", "must be a boolean": "bool_type"}
# --- Phase 7b S7 end ---


def _cross_checks(spec: ExamTemplateSpec) -> list[dict]:
    """Rules across fields (4.1, 4.2, 4.6); every problem with its `loc`."""
    out: list[dict] = []
    seen: dict[str, int] = {}
    for i, sec in enumerate(spec.sections):
        try:
            sec.rules()
        except ValidationFailed as exc:
            for d in exc.details or [{"loc": ["rules"], "msg": exc.message}]:
                loc = [x for x in d.get("loc", []) if x != "rules"]
                msg = d.get("msg", "invalid")
                out.append({"loc": ["sections", i, *loc], "msg": msg, "type": _RULE_TYPES.get(msg, "invalid_rule")})
        if sec.key is not None:
            if sec.key in seen:
                out.append({"loc": ["sections", i, "key"], "msg": f"duplicate section key {sec.key!r}",
                            "type": "duplicate_key"})
            seen.setdefault(sec.key, i)
        if sec.time_limit_s and spec.navigation != "section_forward_only":
            out.append({"loc": ["sections", i, "time_limit_s"],
                        "msg": "section timers require navigation section_forward_only",
                        "type": "timer_needs_forward_only"})
    total = spec.defaults.time_limit_s
    if spec.navigation == "section_forward_only" and total:
        secs = sum(s.time_limit_s for s in spec.sections if s.time_limit_s)
        if secs > total:
            out.append({"loc": ["defaults", "time_limit_s"],
                        "msg": "section time limits exceed the total time limit",
                        "type": "section_times_exceed_total"})
    pkeys: set[str] = set()
    bound: set[int] = set()
    for j, p in enumerate(spec.parameters):
        if p.key in pkeys:
            out.append({"loc": ["parameters", j, "key"], "msg": f"duplicate parameter key {p.key!r}",
                        "type": "duplicate_key"})
        pkeys.add(p.key)
        idx = p.section_index
        if idx >= len(spec.sections):
            out.append({"loc": ["parameters", j, "binds"], "msg": "binds a section that does not exist",
                        "type": "binds_missing_section"})
            continue
        if idx in bound:
            out.append({"loc": ["parameters", j, "binds"], "msg": "another parameter binds this section",
                        "type": "binds_taken"})
        bound.add(idx)
        if spec.sections[idx].key is not None:
            out.append({"loc": ["sections", idx, "key"], "msg": "a parameter-bound section key must be null",
                        "type": "bound_key_must_be_empty"})
        clash = [o for o in p.options if o in seen]
        if clash:
            out.append({"loc": ["parameters", j, "options"],
                        "msg": "options collide with fixed section keys: " + ", ".join(clash),
                        "type": "options_collide"})
    return out


def _scheme_row(db: Session, version_id: uuid.UUID):
    """(version id, scheme owner_user_id) of a live scheme's version, or None."""
    from app.lms.grading.models import GradingScheme, GradingSchemeVersion

    return db.execute(
        select(GradingSchemeVersion.id, GradingScheme.owner_user_id)
        .join(GradingScheme, GradingScheme.id == GradingSchemeVersion.scheme_id)
        .where(GradingSchemeVersion.id == version_id, GradingScheme.deleted_at.is_(None))
    ).first()


def _scheme_visible(db: Session, version_id: uuid.UUID, owner_user_id: Optional[str]) -> bool:
    """4.5: the version exists, its scheme is live and is a system scheme or owned by `owner_user_id`."""
    from app.lms.grading.models import GradingScheme, GradingSchemeVersion

    cond = GradingScheme.owner_user_id.is_(None)
    if owner_user_id is not None:
        cond = or_(cond, GradingScheme.owner_user_id == owner_user_id)
    return db.execute(
        select(GradingSchemeVersion.id)
        .join(GradingScheme, GradingScheme.id == GradingSchemeVersion.scheme_id)
        .where(GradingSchemeVersion.id == version_id, GradingScheme.deleted_at.is_(None), cond)
    ).first() is not None


def _check_scheme(db: Session, spec: ExamTemplateSpec, owner: SpecOwnerLike) -> None:
    vid = spec.scheme_version_id
    if vid is None:
        return
    loc = ["scoring", "grading_scheme_version_id"]
    teacher = owner.owner_scope == "teacher"
    if not _scheme_visible(db, vid, owner.owner_user_id if teacher else None):
        row = _scheme_row(db, vid)
        if row is not None and not teacher:
            # a teacher's private scheme in a template others can see (P7B-2; shared schemes are Phase 9)
            raise ValidationFailed("Only system grading schemes can be used in shared templates",
                                   code=ids.E_SCHEME_NOT_SHAREABLE, details=[{"loc": loc, "msg": "not shareable", "type": "not_shareable"}])
        raise spec_invalid([{"loc": loc, "msg": "unknown grading scheme version", "type": "unknown_scheme"}])


def parse_spec(spec_dict: Any) -> ExamTemplateSpec:
    """Shape validation and cross-field rules, no DB (422 `spec_invalid` / `importer_profile_reserved`)."""
    if not isinstance(spec_dict, dict):
        raise spec_invalid([{"loc": [], "msg": "must be an object", "type": "dict_type"}])
    if spec_dict.get("importer_profile") == "ort":
        raise ValidationFailed("The ORT importer profile belongs to the ORT course template",
                               code=ids.E_IMPORTER_PROFILE_RESERVED,
                               details=[{"loc": ["importer_profile"], "msg": "reserved", "type": "reserved"}])
    try:
        spec = ExamTemplateSpec.model_validate(spec_dict)
    except ValidationError as exc:
        raise spec_invalid(_spec_details(exc)) from None
    problems = _cross_checks(spec)
    if problems:
        raise spec_invalid(problems)
    return spec


def validate_spec(db: Session, spec_dict: Any, owner: SpecOwnerLike) -> ExamTemplateSpec:
    """The normalized spec, or 422 (`spec_invalid` with `details=[{loc, msg}]`, `importer_profile_reserved`,
    `scheme_not_shareable`). `owner`: an `ExamTemplate` row or a `SpecOwner`."""
    spec = parse_spec(spec_dict)
    _check_scheme(db, spec, owner)
    return spec


def spec_json(spec: ExamTemplateSpec) -> dict:
    """The stored JSON form (`exam_template_versions.spec`, `exam_templates.draft_spec`)."""
    return spec.model_dump(mode="json")


def spec_hash(spec: ExamTemplateSpec) -> str:
    """`exam_template_versions.spec_hash`: the canonical hash of `spec_json` (same function as snapshots)."""
    from app.lms.assessments.snapshot import canonical_hash

    return canonical_hash(spec_json(spec))


# ------------------------------------------------------------------------------------------- from an assessment

def spec_from_assessment(db: Session, a) -> dict:
    """A draft spec reproducing an assessment's structure (5.5 save-as-template): navigation, display fields (NULL
    stays NULL), defaults from its settings, one section per row (rules as stored; no type list = every type,
    passages allowed unless forbidden), scoring from its scheme version, importer profile "general", no parameters,
    no locks. Unvalidated: the caller adds counts / lock scope and passes it through `validate_spec`."""
    from app.lms.assessments import repository as repo

    sections = []
    for s in repo.load_sections(db, a.id):
        rules = dict(s.rules or {})
        sections.append({
            "key": s.key, "title": s.title, "instructions": s.instructions, "time_limit_s": s.time_limit_s,
            "min_items": rules.get("min_items"), "max_items": rules.get("max_items"),
            "allowed_types": list(rules.get("allowed_types") or TYPE_NAMES),
            "allow_passages": rules.get("allow_passages") is not False,
            "passage_display": None,
        })
    return {
        "schema": ids.SPEC_SCHEMA,
        "navigation": a.navigation,
        "display_mode": a.display_mode or "one_per_page",
        "passage_display": a.passage_display,
        "result_view": a.result_view,
        "importer_profile": "general",
        "defaults": {
            "time_limit_s": a.time_limit_s, "allowed_attempts": a.allowed_attempts, "score_policy": a.score_policy,
            "results_policy": a.results_policy, "show_correct_answers": bool(a.show_correct_answers),
            "shuffle_items": bool(a.shuffle_items), "shuffle_choices": bool(a.shuffle_choices),
        },
        "sections": sections,
        "scoring": ({"grading_scheme_version_id": str(a.grading_scheme_version_id)}
                    if a.grading_scheme_version_id else None),
        "parameters": [],
        "lock_scope": [],
    }
