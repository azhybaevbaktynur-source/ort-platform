"""Phase 8b S4 (PHASE_8B_DESIGN invariant 6, 12): every pick list of the exam template constructor comes from
`GET /exam-templates/blocks`, so the constructor code holds no literal block key. This scans
`frontend/src/components/lms/examTemplates/**` for a quoted block key (`"one_per_page"`, `'numbered'`, `` `ort` ``,
question type names, ...). Pure file reads, no DB.

Keys come from the backend itself (`exam_templates/blocks.py` and the question type registry), so a new block is
covered without editing this test. The few keys the constructor must reason about (server defaults, the forward-only
navigation, the ORT-only type left unchecked in new sections) live in `frontend/src/lib/lms/examTemplates.ts`, typed
against `blocks.ts`. Lock-scope keys are not scanned: they are also spec field names (`"sections"`, `"navigation"`),
which the constructor legitimately uses as issue locations.

Files that are not the constructor (7b picker, badge, save-as dialog, import fields; owned elsewhere) are skipped.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.lms.content.types import TYPE_NAMES
from app.lms.exam_templates import blocks

ROOT = Path(__file__).resolve().parents[3]
CONSTRUCTOR = ROOT / "frontend" / "src" / "components" / "lms" / "examTemplates"
NOT_CONSTRUCTOR = {"TemplatePicker.tsx", "TemplateBadge.tsx", "SaveAsTemplateDialog.tsx", "ImportValidationFields.tsx"}

BLOCK_KEYS = sorted(set(blocks.RESULT_VIEWS) | set(blocks.PASSAGE_DISPLAYS) | set(blocks.DISPLAY_MODES)
                    | set(blocks.NAVIGATIONS) | set(blocks.IMPORTER_PROFILES) | set(TYPE_NAMES))

_HTML_ATTR = re.compile(r"""\binputMode=(["'])[^"']*\1""")

pytestmark = pytest.mark.skipif(not CONSTRUCTOR.exists(), reason="frontend checkout not present")


def _constructor_files() -> list[Path]:
    files = [p for p in sorted(CONSTRUCTOR.rglob("*")) if p.suffix in {".ts", ".tsx"} and p.name not in NOT_CONSTRUCTOR]
    return [p for p in files if not p.name.endswith((".test.ts", ".test.tsx", ".check.ts"))]


def test_constructor_files_exist():
    names = {p.name for p in _constructor_files()}
    assert "ExamTemplateEditor.tsx" in names
    assert len(names) >= 5


def test_block_keys_are_known():
    assert {"one_per_page", "scrolling", "numbered", "ort", "single_choice"} <= set(BLOCK_KEYS)


@pytest.mark.parametrize("key", BLOCK_KEYS)
def test_no_hard_coded_block_key_in_constructor(key):
    pattern = re.compile(r"""(["'`])""" + re.escape(key) + r"\1")
    hits = []
    for path in _constructor_files():
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            # HTML attribute values that happen to equal a type name (`inputMode="numeric"`) are not block keys
            if pattern.search(_HTML_ATTR.sub("", line)):
                hits.append(f"{path.relative_to(ROOT)}:{no}: {line.strip()}")
    assert not hits, (
        f"block key {key!r} is hard-coded in the constructor; list it from GET /exam-templates/blocks "
        f"(or name it in lib/lms/examTemplates.ts):\n" + "\n".join(hits)
    )
