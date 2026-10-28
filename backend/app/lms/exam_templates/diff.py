"""Pure diff of two exam template specs (PHASE_8B_DESIGN 5.2, P8B-8). Computed on request, never stored.

`spec_diff(before, after)` works on normalized specs (`ExamTemplateSpec.model_validate(...).model_dump(mode="json")`),
so stored versions and drafts compare field by field regardless of key order or omitted defaults:

- scalar paths `navigation, display_mode, passage_display, result_view, importer_profile, defaults.<field>,
  scoring.grading_scheme_version_id` → one `changed` entry each;
- `lock_scope` as a set → one `changed` entry (sorted lists on both sides);
- `sections` matched by `key` when the section has one, otherwise by ordinal among the unkeyed sections; a matched
  section yields one entry per differing field (`sections[<key or position>].<field>`), unmatched sections one
  `added` / `removed` entry carrying the whole section; `parameters` matched by `key`.

Order: top-level fields in spec order, then sections by `after` position (removed ones last, by `before` position),
then parameters. Section positions are 0-based indexes into `sections`, like the spec's own `binds`
(`sections[0].key`) and the constructor's paths; publish issues' `section_pos` stay 1-based."""
from __future__ import annotations

from typing import Any, Optional

from app.lms.exam_templates import schemas as sch
from app.lms.exam_templates.spec import ExamTemplateSpec, SpecDefaults, SpecParameter, SpecSection

SCALAR_PATHS = ("navigation", "display_mode", "passage_display", "result_view", "importer_profile")
DEFAULT_FIELDS = tuple(SpecDefaults.model_fields)
SCORING_PATH = "scoring.grading_scheme_version_id"
SECTION_FIELDS = tuple(SpecSection.model_fields)
PARAMETER_FIELDS = tuple(k for k in SpecParameter.model_fields if k != "key")


def normalize(spec: Any) -> dict:
    """The canonical JSON form of a stored spec (already validated) or a draft."""
    if isinstance(spec, ExamTemplateSpec):
        return spec.model_dump(mode="json")
    return ExamTemplateSpec.model_validate(spec).model_dump(mode="json")


def _get(d: dict, path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _section_ref(sec: Optional[dict], position: int) -> sch.SpecChangeSectionOut:
    sec = sec or {}
    return sch.SpecChangeSectionOut(key=sec.get("key"), position=position, title=sec.get("title"))


def _match_sections(before: list[dict], after: list[dict]) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """(pairs of (before_index, after_index), removed before indexes, added after indexes)."""
    b_keyed = {s["key"]: i for i, s in enumerate(before) if s.get("key")}
    a_keyed = {s["key"]: i for i, s in enumerate(after) if s.get("key")}
    pairs: list[tuple[int, int]] = []
    matched_b: set[int] = set()
    matched_a: set[int] = set()
    for key, ai in a_keyed.items():
        bi = b_keyed.get(key)
        if bi is not None:
            pairs.append((bi, ai))
            matched_b.add(bi)
            matched_a.add(ai)
    b_unkeyed = [i for i, s in enumerate(before) if not s.get("key")]
    a_unkeyed = [i for i, s in enumerate(after) if not s.get("key")]
    for bi, ai in zip(b_unkeyed, a_unkeyed):
        pairs.append((bi, ai))
        matched_b.add(bi)
        matched_a.add(ai)
    removed = [i for i in range(len(before)) if i not in matched_b]
    added = [i for i in range(len(after)) if i not in matched_a]
    pairs.sort(key=lambda p: p[1])
    return pairs, removed, added


def spec_diff(before: Any, after: Any) -> list[sch.SpecChange]:
    b, a = normalize(before), normalize(after)
    out: list[sch.SpecChange] = []

    def changed(path: str, bv: Any, av: Any, section: Optional[sch.SpecChangeSectionOut] = None) -> None:
        if bv != av:
            out.append(sch.SpecChange(path=path, kind="changed", before=bv, after=av, section=section))

    for p in SCALAR_PATHS:
        changed(p, b.get(p), a.get(p))
    for f in DEFAULT_FIELDS:
        changed(f"defaults.{f}", _get(b, f"defaults.{f}"), _get(a, f"defaults.{f}"))
    changed(SCORING_PATH, _get(b, SCORING_PATH), _get(a, SCORING_PATH))
    b_lock, a_lock = set(b.get("lock_scope") or []), set(a.get("lock_scope") or [])
    if b_lock != a_lock:
        out.append(sch.SpecChange(path="lock_scope", kind="changed", before=sorted(b_lock), after=sorted(a_lock)))

    b_secs, a_secs = list(b.get("sections") or []), list(a.get("sections") or [])
    pairs, removed, added = _match_sections(b_secs, a_secs)
    # by `after` position: matched and added sections interleaved in after order, then the removed ones
    events: list[tuple[int, str, int, Optional[int]]] = [(ai, "pair", bi, ai) for bi, ai in pairs]
    events += [(ai, "added", -1, ai) for ai in added]
    events.sort(key=lambda e: (e[0], e[1] != "pair"))
    for _, kind, bi, ai in events:
        sec_a = a_secs[ai]
        ref = _section_ref(sec_a, ai)
        label = sec_a.get("key") or str(ai)
        if kind == "added":
            out.append(sch.SpecChange(path=f"sections[{label}]", kind="added", before=None, after=sec_a, section=ref))
            continue
        sec_b = b_secs[bi]
        for f in SECTION_FIELDS:
            changed(f"sections[{label}].{f}", sec_b.get(f), sec_a.get(f), ref)
    for bi in removed:
        sec_b = b_secs[bi]
        label = sec_b.get("key") or str(bi)
        out.append(sch.SpecChange(path=f"sections[{label}]", kind="removed", before=sec_b, after=None,
                                  section=_section_ref(sec_b, bi)))

    b_params = {p["key"]: p for p in (b.get("parameters") or [])}
    a_params = {p["key"]: p for p in (a.get("parameters") or [])}
    for key, pa in a_params.items():
        pb = b_params.get(key)
        if pb is None:
            out.append(sch.SpecChange(path=f"parameters[{key}]", kind="added", before=None, after=pa))
            continue
        for f in PARAMETER_FIELDS:
            changed(f"parameters[{key}].{f}", pb.get(f), pa.get(f))
    for key, pb in b_params.items():
        if key not in a_params:
            out.append(sch.SpecChange(path=f"parameters[{key}]", kind="removed", before=pb, after=None))
    return out


def summary(changes: list[sch.SpecChange]) -> sch.SpecDiffSummaryOut:
    sec_changed = {c.path.split(".", 1)[0] for c in changes
                   if c.kind == "changed" and c.path.startswith("sections[")}
    return sch.SpecDiffSummaryOut(
        sections_added=sum(1 for c in changes if c.kind == "added" and c.path.startswith("sections[")),
        sections_removed=sum(1 for c in changes if c.kind == "removed" and c.path.startswith("sections[")),
        sections_changed=len(sec_changed),
        fields_changed=sum(1 for c in changes if c.kind == "changed"),
    )


def count_changes(before: Any, after: Any) -> int:
    return len(spec_diff(before, after))
