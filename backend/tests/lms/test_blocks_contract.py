"""Phase 7b (PHASE_7B_DESIGN 7): the frontend block catalog `frontend/src/lib/lms/blocks.ts` mirrors the backend
(`exam_templates/blocks.py`, the question type registry). The TS literal arrays are read with a regex (like
`scripts/check_i18n_parity.py` reads JSON), so a key added on one side only fails here. Pure file reads, no DB."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.lms.content.types import REGISTRY, TYPE_NAMES
from app.lms.exam_templates import blocks

ROOT = Path(__file__).resolve().parents[3]
BLOCKS_TS = ROOT / "frontend" / "src" / "lib" / "lms" / "blocks.ts"
I18N = ROOT / "frontend" / "src" / "lib" / "i18n"

_ARRAY = re.compile(r"export const (?P<name>[A-Z_]+) = \[(?P<body>[^\]]*)\] as const;")
_STR = re.compile(r"""["']([^"']+)["']""")


def _ts_arrays() -> dict[str, tuple[str, ...]]:
    src = BLOCKS_TS.read_text(encoding="utf-8")
    return {m.group("name"): tuple(_STR.findall(m.group("body"))) for m in _ARRAY.finditer(src)}


def _flat(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


pytestmark = pytest.mark.skipif(not BLOCKS_TS.exists(), reason="frontend checkout not present")


@pytest.mark.parametrize("name, expected", [
    ("RESULT_VIEWS", blocks.RESULT_VIEWS),
    ("PASSAGE_DISPLAYS", blocks.PASSAGE_DISPLAYS),
    ("DISPLAY_MODES", blocks.DISPLAY_MODES),
    ("NAVIGATIONS", blocks.NAVIGATIONS),
    ("IMPORTER_PROFILES", blocks.IMPORTER_PROFILES),
    ("QUESTION_TYPES", TYPE_NAMES),
])
def test_ts_arrays_equal_backend(name, expected):
    arrays = _ts_arrays()
    assert name in arrays, f"{name} missing in blocks.ts (keep it one line, `as const`)"
    assert arrays[name] == tuple(expected)


def test_available_display_modes_equal_display_modes():
    """Phase 8b S1 (PHASE_8B_DESIGN invariant 6): every display mode is available since P7B-1 was lifted."""
    src = BLOCKS_TS.read_text(encoding="utf-8")
    assert re.search(r"export const AVAILABLE_DISPLAY_MODES: readonly DisplayMode\[\] = DISPLAY_MODES;", src)


def test_ts_maps_cover_every_key():
    src = BLOCKS_TS.read_text(encoding="utf-8")
    for map_name, keys in (("resultViews", blocks.RESULT_VIEWS), ("passageRenderers", blocks.PASSAGE_DISPLAYS)):
        m = re.search(rf"export const {map_name}\b[^=]*=\s*\{{(?P<body>.*?)\n\}};", src, re.S)
        assert m, f"{map_name} map missing in blocks.ts"
        found = set(re.findall(r"^\s*([a-z_]+):", m.group("body"), re.M))
        assert found == set(keys), map_name


@pytest.mark.parametrize("lang", ["en", "ky", "ru"])
def test_every_title_key_exists(lang):
    flat = _flat(json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8")))
    for name, qt in REGISTRY.items():
        assert qt.title_key, f"{name} has no title_key"
        assert qt.title_key in flat, f"{lang}.json lacks {qt.title_key}"
    for key in blocks.RESULT_VIEWS:
        assert f"examTemplates.blocks.resultViews.{key}" in flat
    for key in blocks.PASSAGE_DISPLAYS:
        assert f"examTemplates.blocks.passageDisplays.{key}" in flat
    for key in blocks.DISPLAY_MODES:
        assert f"examTemplates.blocks.displayModes.{key}" in flat


def test_frontend_error_codes_cover_ids():
    from app.lms.exam_templates import ids
    src = (ROOT / "frontend" / "src" / "lib" / "lms" / "examTemplateTypes.ts").read_text(encoding="utf-8")
    m = re.search(r"EXAM_TEMPLATE_ERROR_CODES = \[(?P<body>.*?)\] as const;", src, re.S)
    assert m
    assert set(_STR.findall(m.group("body"))) == set(ids.ERROR_CODES)
    flat = _flat(json.loads((I18N / "en.json").read_text(encoding="utf-8")))
    for code in ids.ERROR_CODES:
        assert f"examTemplates.errors.{code}" in flat, code
