"""Phase 9 S4: answer validation per field type (PHASE_9_DESIGN 4.10), pure functions."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.lms.core.errors import ValidationFailed
from app.lms.enrollment_forms.fields import validate_answers

TODAY = date(2026, 10, 31)


def F(key, type_, required=False, options=None, max_len=None, position=0):
    return SimpleNamespace(key=key, type=type_, required=required, options=options, max_len=max_len,
                           position=position)


def errors(fields, answers):
    with pytest.raises(ValidationFailed) as ei:
        validate_answers(fields, answers, today=TODAY)
    return {(d["field_key"], d["type"]) for d in ei.value.details}


CH = [{"key": "a", "label": {"en": "A"}}, {"key": "b", "label": {"en": "B"}}]


def test_text_types():
    assert validate_answers([F("n", "short_text")], {"n": "  Aida  "}, today=TODAY) == {"n": "Aida"}
    assert errors([F("n", "short_text")], {"n": "x" * 201}) == {("n", "too_long")}
    assert validate_answers([F("n", "short_text", max_len=500)], {"n": "x" * 500}, today=TODAY)
    assert errors([F("n", "long_text")], {"n": "x" * 1001}) == {("n", "too_long")}
    assert errors([F("n", "long_text", max_len=5000)], {"n": "x" * 2001}) == {("n", "too_long")}
    assert errors([F("n", "short_text")], {"n": 5}) == {("n", "bad_format")}


def test_required_and_optional():
    fields = [F("a", "short_text", required=True), F("b", "short_text")]
    assert errors(fields, {"a": "   "}) == {("a", "required")}
    assert validate_answers(fields, {"a": "x", "b": ""}, today=TODAY) == {"a": "x"}


def test_choices():
    assert validate_answers([F("c", "single_choice", options=CH)], {"c": "a"}, today=TODAY) == {"c": "a"}
    assert errors([F("c", "single_choice", options=CH)], {"c": "z"}) == {("c", "bad_option")}
    m = F("m", "multi_choice", options=CH)
    assert validate_answers([m], {"m": ["a", "b"]}, today=TODAY) == {"m": ["a", "b"]}
    assert errors([m], {"m": ["a", "a"]}) == {("m", "bad_format")}
    assert errors([m], {"m": ["z"]}) == {("m", "bad_option")}
    assert errors([m], {"m": "a"}) == {("m", "bad_format")}


def test_number_date_email_phone():
    n = F("n", "number", options={"min": 5, "max": 25})
    assert validate_answers([n], {"n": 7}, today=TODAY) == {"n": 7}
    assert validate_answers([n], {"n": "7,5"}, today=TODAY) == {"n": 7.5}
    assert errors([n], {"n": 30}) == {("n", "bad_format")}
    assert errors([n], {"n": True}) == {("n", "bad_format")}
    assert errors([n], {"n": float("nan")}) == {("n", "bad_format")}
    d = F("d", "date")
    assert validate_answers([d], {"d": "2010-02-28"}, today=TODAY) == {"d": "2010-02-28"}
    for bad in ("2010-02-30", "1899-12-31", "2028-01-01", "10.02.2010"):
        assert errors([d], {"d": bad}) == {("d", "bad_format")}, bad
    e = F("e", "email")
    assert validate_answers([e], {"e": " A@B.kg "}, today=TODAY) == {"e": "a@b.kg"}
    assert errors([e], {"e": "nope"}) == {("e", "bad_format")}
    p = F("p", "phone")
    assert validate_answers([p], {"p": "+996 (555) 12-34-56"}, today=TODAY) == {"p": "+996555123456"}
    assert errors([p], {"p": "12345"}) == {("p", "bad_format")}
    assert errors([p], {"p": "+1234567890123456"}) == {("p", "bad_format")}


def test_unknown_keys_and_no_value_echo():
    fields = [F("a", "short_text")]
    secret = "my secret value"
    with pytest.raises(ValidationFailed) as ei:
        validate_answers(fields, {"a": 1, "zz": secret, "Not A Key!": secret}, today=TODAY)
    assert secret not in repr(ei.value.details) and secret not in ei.value.message
    assert {(d["field_key"], d["type"]) for d in ei.value.details} == {
        ("a", "bad_format"), ("zz", "bad_format"), ("_unknown", "bad_format")}
