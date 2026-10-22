"""ORT rich text v1 normalisation (design P2-15).

Text is plain with `$...$` / `$$...$$` LaTeX and `<u>`, `<b>` tags. The client
renderer escapes first, so the server only normalises line endings, strips
control characters and enforces length caps. LaTeX is preserved byte for byte.
"""
from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

STEM_MAX = 20_000
CHOICE_MAX = 2_000
EXPLANATION_MAX = 20_000
PASSAGE_BODY_MAX = 100_000
PASSAGE_TITLE_MAX = 300

# C0 controls except \n (0x0a) and \t (0x09); also DEL.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(value: str, max_length: int) -> str:
    """Normalise `value`; raise ValueError when longer than `max_length`."""
    if not isinstance(value, str):
        raise ValueError("must be a string")
    out = value.replace("\r\n", "\n").replace("\r", "\n")
    out = _CONTROL_RE.sub("", out)
    if len(out) > max_length:
        raise ValueError(f"exceeds {max_length} characters")
    return out


def rich_text(max_length: int):
    """Annotated str type that runs `clean_text` with the given cap."""
    return Annotated[str, AfterValidator(lambda v: clean_text(v, max_length))]


Stem = rich_text(STEM_MAX)
ChoiceText = rich_text(CHOICE_MAX)
Explanation = rich_text(EXPLANATION_MAX)
