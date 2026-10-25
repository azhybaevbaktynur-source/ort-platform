"""ORT preset (P2-20): section names/aliases and the math_1 / math_2 rule.

Copied from the frozen app.schemas.question (SectionType, math_section_rule_error) and
app.services.csv_service (SECTION_ALIASES). The preset applies only when an exam_type is given.
"""
from __future__ import annotations

from typing import Optional

# SectionType values of the old platform, plus the three subject sections named in BUNDLE_FORMAT.
ORT_SECTIONS = frozenset({
    "math_1", "analogies", "reading", "grammar", "math_2",
    "chemistry", "biology", "physics", "history", "english",
    "advanced_math", "native_language",
    "math_subject", "kyrgyz_lang_lit", "russian_lang_lit",
})

SECTION_ALIASES = {
    "math_1": "math_1", "math1": "math_1", "math-1": "math_1", "math 1": "math_1",
    "quantitative_comparison": "math_1", "quantitative comparison": "math_1", "салыштыруу": "math_1",
    "mathematics_1": "math_1", "mathematics 1": "math_1", "математика_1": "math_1", "математика 1": "math_1",
    "математика-1": "math_1", "математика i": "math_1", "математика 1-бөлүк": "math_1", "math": "math_1",
    "math_2": "math_2", "math2": "math_2", "math-2": "math_2", "math 2": "math_2",
    "mathematics_2": "math_2", "mathematics 2": "math_2", "математика_2": "math_2", "математика 2": "math_2",
    "математика-2": "math_2", "математика ii": "math_2", "математика 2-бөлүк": "math_2",
    "analogies": "analogies", "analogy": "analogies", "analogies_and_completion": "analogies",
    "аналогия": "analogies", "аналогии": "analogies", "аналогиялар": "analogies",
    "аналогии_и_дополнение_предложений": "analogies", "аналогии и дополнение предложений": "analogies",
    "reading": "reading", "reading_comprehension": "reading", "reading comprehension": "reading",
    "comprehension": "reading", "чтение": "reading", "чтение_и_понимание": "reading",
    "чтение и понимание": "reading", "окуу": "reading", "окуу_жана_түшүнүү": "reading",
    "окуу жана түшүнүү": "reading",
    "grammar": "grammar", "practical_grammar": "grammar", "practical grammar": "grammar",
    "грамматика": "grammar", "практикалык_грамматика": "grammar", "практикалык грамматика": "grammar",
    "практическая грамматика": "grammar", "практическая_грамматика": "grammar",
    "chemistry": "chemistry", "химия": "chemistry",
    "biology": "biology", "биология": "biology",
    "physics": "physics", "физика": "physics",
    "history": "history", "тарых": "history", "история": "history",
    "english": "english", "англис": "english", "англис тили": "english",
    "английский": "english", "английский язык": "english",
    # A10 (owner OK 2026-10-24): BUNDLE_FORMAT subject keys -> the ort_subject preset keys; old keys stay accepted
    "math_subject": "advanced_math", "kyrgyz_lang_lit": "native_language", "russian_lang_lit": "native_language",
}


def normalize_section(raw: str) -> str:
    """Alias lookup exactly as the old parser: lower-case, then '-'/' ' -> '_'."""
    low = (raw or "").strip().lower()
    clean = low.replace("-", "_").replace(" ", "_")
    return SECTION_ALIASES.get(low) or SECTION_ALIASES.get(clean) or clean


def math_section_rule_error(section: str, column_a: Optional[str], column_b: Optional[str]) -> Optional[tuple[str, str]]:
    """math_1 is ALWAYS quantitative comparison (both columns); columns are never used elsewhere."""
    has_a = bool((column_a or "").strip())
    has_b = bool((column_b or "").strip())
    if section == "math_1":
        if not has_a:
            return "column_a", "math_1 is quantitative comparison: column_a is required."
        if not has_b:
            return "column_b", "math_1 is quantitative comparison: column_b is required."
    elif has_a or has_b:
        return ("column_a" if has_a else "column_b"), (
            f"column_a/column_b are only used in math_1 (quantitative comparison), not in '{section}'."
        )
    return None


def ort_section_error(section: str) -> Optional[str]:
    if section not in ORT_SECTIONS:
        return f"Invalid section '{section}'. Must be one of: {sorted(ORT_SECTIONS)}"
    return None
