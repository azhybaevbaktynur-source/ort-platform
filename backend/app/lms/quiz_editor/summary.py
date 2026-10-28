"""Phase 7c S5: the correct answer(s) of a question in one short line, for the collapsed quiz-editor card (owner's
proposal 4). Staff only: `builder.staff_out(include_answers=True)` adds it for callers holding
`course:content.read_admin`; student and lobby payloads never carry it.

Format (language-neutral; the client renders math and translates the true/false tokens):
- single_choice / multiple_answers: the text of each correct choice ("; "-joined), or its letter when it has no text;
- true_false: "true" | "false";
- comparison: the letter A-D;
- numeric: each accepted answer as "7", "7 ± 0.5" or "1 – 3";
- short_text: the accepted answers;
- essay and unknown types: None."""
from __future__ import annotations

from typing import Any, Optional

MAX_LEN = 200
SEP = "; "


def _text(v: Any) -> str:
    return " ".join(str(v or "").split())


def _choices(data: dict, ids: list[str]) -> list[str]:
    by_id = {c.get("id"): c for c in data.get("choices") or [] if isinstance(c, dict)}
    out = []
    for cid in ids:
        c = by_id.get(cid)
        if c is not None:
            out.append(_text(c.get("text")) or str(cid))
    return out


def _numeric(a: dict) -> str:
    if a.get("kind") == "range":
        return f"{_text(a.get('min'))} – {_text(a.get('max'))}"
    value, margin = _text(a.get("value")), _text(a.get("margin"))
    try:
        zero = float(margin or "0") == 0
    except ValueError:
        zero = False
    return value if zero else f"{value} ± {margin}"


def correct_summary(qtype: str, data: Optional[dict]) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    parts: list[str]
    if qtype == "single_choice":
        parts = _choices(data, [data.get("correct")])
    elif qtype == "multiple_answers":
        parts = _choices(data, list(data.get("correct") or []))
    elif qtype == "true_false":
        c = data.get("correct")
        parts = [("true" if c else "false")] if isinstance(c, bool) else []
    elif qtype == "comparison":
        parts = [_text(data.get("correct"))]
    elif qtype == "numeric":
        parts = [_numeric(a) for a in data.get("answers") or [] if isinstance(a, dict)]
    elif qtype == "short_text":
        parts = [_text(a) for a in data.get("answers") or []]
    else:
        return None
    s = SEP.join(p for p in parts if p)
    if not s:
        return None
    return s if len(s) <= MAX_LEN else s[: MAX_LEN - 1] + "…"
