"""Content serializer contracts. Registry-level tests (C2); API tests are appended by C4."""
from __future__ import annotations

import json
import uuid

import pytest

from app.lms.content.types import REGISTRY, get_type

SHA = "b" * 64


def S(name):
    return f"SENTINEL_{name}_{uuid.uuid4().hex}"


def img():
    return {"asset_id": str(uuid.uuid4()), "sha256": SHA}


def build(name, s):
    """Raw data per type with sentinels in every key-only field."""
    if name == "single_choice":
        return {"choices": [{"id": "A", "text": "one"}, {"id": "B", "text": "two", "image": img()}],
                "correct": "B", "shuffle": True}
    if name == "multiple_answers":
        return {"choices": [{"id": "A", "text": "one"}, {"id": "B", "text": "two"}],
                "correct": ["A"], "scoring": "partial", "shuffle": False}
    if name == "true_false":
        return {"correct": True}
    if name == "comparison":
        return {"column_a": "colA", "column_b": "colB", "correct": "D"}
    if name == "numeric":
        return {"answers": [{"kind": "exact", "value": "77777.123", "margin": "0.4242"},
                            {"kind": "range", "min": "31337", "max": "41414"}]}
    if name == "short_text":
        return {"answers": [s], "case_sensitive": True}
    if name == "essay":
        return {"word_limit": 321, "rubric_note": s}
    raise AssertionError(name)


EXPECTED_KEYS = {
    "single_choice": {"choices", "shuffle"},
    "multiple_answers": {"choices", "shuffle"},
    "true_false": set(),
    "comparison": {"column_a", "column_b"},
    "numeric": set(),
    "short_text": set(),
    "essay": {"word_limit"},
}

FORBIDDEN_TOKENS = ["77777.123", "0.4242", "31337", "41414", "range", "exact", "margin",
                    "correct", "scoring", "partial", "case_sensitive", "rubric", "answers",
                    "explanation"]


def test_every_type_covered():
    assert set(EXPECTED_KEYS) == set(REGISTRY)


@pytest.mark.parametrize("name", list(EXPECTED_KEYS))
def test_student_view_has_no_key_material(name):
    s = S(name)
    t = get_type(name)
    data = t.validate(build(name, s))
    # sentinel really is in the stored data (test is not vacuous)
    stored = json.dumps(data, ensure_ascii=False)
    if name in ("short_text", "essay"):
        assert s in stored
    view = t.student_view(data)
    dumped = json.dumps(view, ensure_ascii=False)
    assert s not in dumped
    assert set(view) == EXPECTED_KEYS[name]
    for tok in FORBIDDEN_TOKENS:
        assert tok not in dumped, tok
    assert "SENTINEL" not in dumped


def test_student_choice_item_keys_exact():
    t = get_type("single_choice")
    view = t.student_view(t.validate(build("single_choice", "x")))
    assert [set(c) for c in view["choices"]] == [{"id", "text"}, {"id", "text", "image_url"}]
    assert view["choices"][1]["image_url"] == f"/api/v1/media/{SHA}.webp"
    assert "asset_id" not in json.dumps(view)


def test_multiple_answers_view_hides_scoring_and_correct():
    t = get_type("multiple_answers")
    view = t.student_view(t.validate(build("multiple_answers", "x")))
    assert set(view) == {"choices", "shuffle"}
    assert all(set(c) == {"id", "text"} for c in view["choices"])


def test_explanation_never_reaches_student_view():
    # explanation is a version column, not part of Data; Data forbids it.
    from app.lms.core.errors import ValidationFailed
    for name in REGISTRY:
        with pytest.raises(ValidationFailed):
            get_type(name).validate({**build(name, "x"), "explanation": "SENTINEL_EXPL"})
