"""Section rules, ORT presets and issue type (design P3-7, P3-8, section 3.2). Pure code: no DB."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.lms.content.types import TYPE_NAMES
from app.lms.core.errors import ValidationFailed

# P3-8: ort_main sections (key, minutes), same defaults as the old simulator.
ORT_MAIN_SECTIONS: list[tuple[str, int]] = [
    ("math_1", 45), ("math_2", 45), ("analogies", 30), ("reading", 60), ("grammar", 35),
]
ORT_SUBJECT_KEYS = ("chemistry", "biology", "physics", "history", "english", "advanced_math", "native_language")
ORT_SUBJECT_MINUTES = 60

# P3-7: rules of keyed ORT sections. Passages only in reading.
ORT_SECTION_RULES: dict[str, dict] = {
    "math_1": {"allowed_types": ["comparison"], "allow_passages": False},
    "math_2": {"allowed_types": ["single_choice"], "allow_passages": False},
    "analogies": {"allowed_types": ["single_choice"], "allow_passages": False},
    "reading": {"allowed_types": ["single_choice"], "allow_passages": True},
    "grammar": {"allowed_types": ["single_choice"], "allow_passages": False},
    **{k: {"allowed_types": ["single_choice"], "allow_passages": False} for k in ORT_SUBJECT_KEYS},
}
RULE_KEYS = frozenset({"allowed_types", "max_items", "allow_passages"})
RULE_KEYS = RULE_KEYS | {"min_items"}  # --- Phase 7b S1 --- (PHASE_7B_DESIGN 2.4; ORT rules never set counts)
ORT_PRESETS = ("ort_main", "ort_subject")


@dataclass
class Issue:
    code: str
    section_pos: Optional[int] = None
    item_id: Optional[str] = None
    language: Optional[str] = None
    severity: str = "error"

    def as_dict(self) -> dict:
        return {"code": self.code, "section_pos": self.section_pos, "item_id": self.item_id,
                "language": self.language}


def ort_rules(key: Optional[str]) -> Optional[dict]:
    rules = ORT_SECTION_RULES.get(key or "")
    return {"allowed_types": list(rules["allowed_types"]), "allow_passages": rules["allow_passages"]} if rules else None


def normalize_rules(rules: Optional[dict]) -> dict:
    """Validated copy of a rules object; unknown keys or bad values are a 422."""
    if rules is None:
        return {}
    if not isinstance(rules, dict) or set(rules) - RULE_KEYS:
        raise ValidationFailed("Invalid section rules", details=[{"loc": ["rules"], "msg": "unknown rule key"}])
    out: dict = {}
    types = rules.get("allowed_types")
    if types is not None:
        if (not isinstance(types, list) or not types or len(set(types)) != len(types)
                or any(t not in TYPE_NAMES for t in types)):
            raise ValidationFailed("Invalid section rules",
                                   details=[{"loc": ["rules", "allowed_types"], "msg": "invalid type list"}])
        out["allowed_types"] = list(types)
    mx = rules.get("max_items")
    if mx is not None:
        if isinstance(mx, bool) or not isinstance(mx, int) or mx < 1:
            raise ValidationFailed("Invalid section rules",
                                   details=[{"loc": ["rules", "max_items"], "msg": "must be a positive integer"}])
        out["max_items"] = mx
    # --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 2.4: min_items like max_items, and min <= max when both are set)
    mn = rules.get("min_items")
    if mn is not None:
        if isinstance(mn, bool) or not isinstance(mn, int) or mn < 1:
            raise ValidationFailed("Invalid section rules",
                                   details=[{"loc": ["rules", "min_items"], "msg": "must be a positive integer"}])
        if mx is not None and mn > mx:
            raise ValidationFailed("Invalid section rules",
                                   details=[{"loc": ["rules", "min_items"], "msg": "must not exceed max_items"}])
        out["min_items"] = mn
    # --- Phase 7b S1 end ---
    ap = rules.get("allow_passages")
    if ap is not None:
        if not isinstance(ap, bool):
            raise ValidationFailed("Invalid section rules",
                                   details=[{"loc": ["rules", "allow_passages"], "msg": "must be a boolean"}])
        out["allow_passages"] = ap
    return out


def locked_rules(preset: str, key: Optional[str]) -> Optional[dict]:
    """Rules a section is locked to under an ORT preset (None when the section is free)."""
    return ort_rules(key) if preset in ORT_PRESETS else None


def check_item_rules(section, assessment, qtype: str, language: Optional[str]) -> list[Issue]:
    """Pure: issues for putting one question of `qtype`/`language` into `section` (add time and publish)."""
    issues: list[Issue] = []
    rules = section.rules or {}
    allowed = rules.get("allowed_types")
    if allowed and qtype not in allowed:
        issues.append(Issue("type_not_allowed", section.position, None, language))
    if language is not None and language not in (assessment.languages or []):
        issues.append(Issue("item_language_mismatch", section.position, None, language))
    return issues
