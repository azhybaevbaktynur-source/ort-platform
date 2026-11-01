"""Map a stored response to the option keys it picks (PHASE_10_DESIGN 5, distractors)."""
from __future__ import annotations

import json
from typing import Optional

CHOICE_TYPES = ("single_choice", "multiple_answers", "true_false", "comparison")


def keys_of(qtype: str, response) -> list[str]:
    if not isinstance(response, dict):
        return []
    if qtype == "single_choice":
        v = response.get("choice_id")
        return [str(v)] if v is not None else []
    if qtype == "multiple_answers":
        ids = response.get("choice_ids")
        return [str(x) for x in ids] if isinstance(ids, list) else []
    if qtype == "true_false":
        v = response.get("value")
        return [str(v).lower()] if isinstance(v, bool) else []
    if qtype == "comparison":
        v = response.get("choice")
        return [str(v)] if v is not None else []
    return []


def tally(qtype: str, grouped: list) -> Optional[dict]:
    """`grouped` = (response JSON text, count). `None` for types without options."""
    if qtype not in CHOICE_TYPES:
        return None
    out: dict[str, int] = {}
    for raw, count in grouped:
        try:
            resp = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            continue
        for k in keys_of(qtype, resp):
            out[k] = out.get(k, 0) + int(count)
    return out
