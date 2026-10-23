"""Registry unit tests (Phase 2 C2): validation, scoring tables, richtext."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.lms.content.richtext import clean_text
from app.lms.content.types import REGISTRY, TYPE_NAMES, get_type, set_media_url
from app.lms.core.errors import ValidationFailed

D = Decimal
SHA = "a" * 64


def ch(i, t=None, image=None):
    c = {"id": i, "text": t if t is not None else f"opt {i}"}
    if image:
        c["image"] = image
    return c


SC = {"choices": [ch("A"), ch("B"), ch("C")], "correct": "B"}
MA = {"choices": [ch("A"), ch("B"), ch("C"), ch("D")], "correct": ["A", "B"]}
MAP = {**MA, "scoring": "partial"}


def pts(t, data, resp, mx="10"):
    r = get_type(t).score(get_type(t).validate(data), resp, D(mx))
    return r


def test_registry_names():
    assert set(TYPE_NAMES) == {
        "single_choice", "multiple_answers", "true_false", "comparison",
        "numeric", "short_text", "essay",
    }
    for t in REGISTRY.values():
        assert t.schema_version == 1


def test_unknown_type():
    with pytest.raises(ValidationFailed) as e:
        get_type("nope")
    assert e.value.code == "unsupported_type"


GOOD = {
    "single_choice": SC,
    "multiple_answers": MA,
    "true_false": {"correct": True},
    "comparison": {"column_a": "$x^2$", "column_b": "4", "correct": "C"},
    "numeric": {"answers": [{"kind": "exact", "value": "1,5"}]},
    "short_text": {"answers": ["Бишкек"]},
    "essay": {"word_limit": 100},
}


@pytest.mark.parametrize("name", list(GOOD))
def test_good_payload_roundtrip_and_unknown_keys(name):
    t = get_type(name)
    out = t.validate(GOOD[name])
    assert t.validate(out) == out  # idempotent
    with pytest.raises(ValidationFailed) as e:
        t.validate({**GOOD[name], "bogus": 1})
    assert e.value.code == "invalid_question_data"
    assert e.value.details


@pytest.mark.parametrize("name", list(GOOD))
def test_non_object_rejected(name):
    with pytest.raises(ValidationFailed):
        get_type(name).validate("x")  # type: ignore[arg-type]


BAD = [
    ("single_choice", {**SC, "correct": "Z"}),
    ("single_choice", {"choices": [ch("A"), ch("A")], "correct": "A"}),
    ("single_choice", {"choices": [ch("A")], "correct": "A"}),
    ("single_choice", {"choices": [ch(str(i)) for i in range(11)], "correct": "1"}),
    ("single_choice", {"choices": [ch("A"), ch("bad id!")], "correct": "A"}),
    ("single_choice", {"choices": [ch("A"), ch("B", "")], "correct": "A"}),
    ("single_choice", {"choices": [ch("A"), ch("B", image={"asset_id": "x", "sha256": SHA})], "correct": "A"}),
    ("multiple_answers", {**MA, "correct": []}),
    ("multiple_answers", {**MA, "correct": ["A", "A"]}),
    ("multiple_answers", {**MA, "correct": ["A", "Z"]}),
    ("multiple_answers", {**MA, "scoring": "weird"}),
    ("true_false", {}),
    ("comparison", {"column_a": "", "column_b": "1", "correct": "A"}),
    ("comparison", {"column_a": "1", "column_b": "2", "correct": "E"}),
    ("comparison", {"column_a": "1", "column_b": "2"}),
    ("numeric", {"answers": []}),
    ("numeric", {"answers": [{"kind": "exact", "value": "NaN"}]}),
    ("numeric", {"answers": [{"kind": "exact", "value": "Infinity"}]}),
    ("numeric", {"answers": [{"kind": "exact", "value": "abc"}]}),
    ("numeric", {"answers": [{"kind": "exact", "value": "1", "margin": "-1"}]}),
    ("numeric", {"answers": [{"kind": "range", "min": "5", "max": "1"}]}),
    ("numeric", {"answers": [{"kind": "other", "value": "1"}]}),
    ("numeric", {"answers": [{"kind": "exact", "value": str(i)} for i in range(11)]}),
    ("short_text", {"answers": []}),
    ("short_text", {"answers": ["   "]}),
    ("short_text", {"answers": ["x"] * 21}),
    ("essay", {"word_limit": 0}),
    ("essay", {"word_limit": 5001}),
]


@pytest.mark.parametrize("name,payload", BAD)
def test_bad_payloads(name, payload):
    with pytest.raises(ValidationFailed) as e:
        get_type(name).validate(payload)
    assert e.value.code == "invalid_question_data"


def test_image_ref_ok_and_refs_listed():
    aid = str(uuid.uuid4())
    data = {"choices": [ch("A", image={"asset_id": aid, "sha256": SHA}), ch("B")], "correct": "A"}
    t = get_type("single_choice")
    out = t.validate(data)
    assert t.image_refs(out) == [{"asset_id": aid, "sha256": SHA}]
    set_media_url(lambda s: f"/cdn/{s}")
    try:
        assert t.student_view(out)["choices"][0]["image_url"] == f"/cdn/{SHA}"
    finally:
        set_media_url(None)
    assert t.student_view(out)["choices"][0]["image_url"] == f"/api/v1/media/{SHA}.webp"
    assert "image_url" not in t.student_view(out)["choices"][1]


# --- scoring tables -------------------------------------------------------

@pytest.mark.parametrize("resp,exp,ok", [
    ({"choice_id": "B"}, "10.00", True),
    ({"choice_id": "A"}, "0.00", False),
    ({"choice_id": None}, "0.00", False),
    ({}, "0.00", False),
    (None, "0.00", False),
    ({"choice_id": "B", "x": 1}, "0.00", False),
    ({"choice_id": 5}, "0.00", False),
    ("junk", "0.00", False),
])
def test_single_choice(resp, exp, ok):
    r = pts("single_choice", SC, resp)
    assert (r.points, r.correct, r.needs_review) == (D(exp), ok, False)


@pytest.mark.parametrize("data,picked,exp,ok", [
    (MA, ["A", "B"], "10.00", True),
    (MA, ["B", "A"], "10.00", True),
    (MA, ["A"], "0.00", False),
    (MA, ["A", "B", "C"], "0.00", False),
    (MA, [], "0.00", False),
    (MAP, ["A", "B"], "10.00", True),
    (MAP, ["A"], "5.00", False),
    (MAP, ["A", "C"], "0.00", False),      # (1-1)/2
    (MAP, ["C", "D"], "0.00", False),      # floor at 0
    (MAP, ["A", "B", "C"], "5.00", False),  # (2-1)/2
    ({**MAP, "correct": ["A", "B", "C"]}, ["A"], "3.33", False),
    ({**MAP, "correct": ["A", "B", "C"]}, ["A", "B"], "6.67", False),
])
def test_multiple_answers(data, picked, exp, ok):
    r = pts("multiple_answers", data, {"choice_ids": picked})
    assert (r.points, r.correct) == (D(exp), ok)


def test_multiple_answers_empty_malformed():
    for resp in (None, {}, {"choice_ids": "A"}, {"choice_ids": [1]}):
        r = pts("multiple_answers", MAP, resp)
        assert r.points == D("0.00") and r.correct is False


@pytest.mark.parametrize("correct,resp,ok", [
    (True, {"value": True}, True), (True, {"value": False}, False),
    (False, {"value": False}, True), (False, {"value": None}, False),
    (True, None, False), (True, {"value": "yes"}, False),
])
def test_true_false(correct, resp, ok):
    r = pts("true_false", {"correct": correct}, resp)
    assert r.correct is ok and r.points == (D("10.00") if ok else D("0.00"))


@pytest.mark.parametrize("resp,ok", [
    ({"choice": "C"}, True), ({"choice": "A"}, False), ({"choice": "E"}, False),
    ({"choice": None}, False), (None, False), ({}, False),
])
def test_comparison(resp, ok):
    r = pts("comparison", GOOD["comparison"], resp)
    assert r.correct is ok


NUM = {"answers": [
    {"kind": "exact", "value": "3.14", "margin": "0.01"},
    {"kind": "range", "min": "-10", "max": "-5"},
    {"kind": "exact", "value": "100"},
]}


@pytest.mark.parametrize("val,ok", [
    ("3.14", True), ("3,14", True), (" 3 . 14 ", True), ("3.15", True), ("3.16", False),
    ("3.13", True), ("3.12", False),
    ("-5", True), ("−7", True), ("−10", True), ("-10.01", False), ("-4.99", False),
    ("100", True), ("1 00", True), ("100.0", True), ("100.1", False),
    ("", False), ("abc", False), ("NaN", False), ("Infinity", False), ("1e400", False),
])
def test_numeric(val, ok):
    assert pts("numeric", NUM, {"value": val}).correct is ok


def test_numeric_malformed():
    for resp in (None, {}, {"value": 3}, {"value": "x" * 101}):
        assert pts("numeric", NUM, resp).correct is False


def test_numeric_normalized_storage():
    out = get_type("numeric").validate({"answers": [{"kind": "exact", "value": "1,5", "margin": "0,1"}]})
    assert out["answers"][0] == {"kind": "exact", "value": "1.5", "margin": "0.1"}


@pytest.mark.parametrize("answers,cs,text,ok", [
    (["Бишкек"], False, "  бишкек ", True),
    (["Бишкек"], False, "БИШКЕК", True),
    (["Бишкек"], True, "бишкек", False),
    (["Бишкек"], True, "Бишкек", True),
    (["New  York"], False, "new york", True),
    (["cat"], False, "саt", True),            # Cyrillic а, с look-alikes
    (["cat"], False, "cat ", True),
    (["кот"], False, "kоt", False),           # т is not a look-alike mapped letter
    (["кос"], False, "koc", True),            # к о с all fold to Latin
    (["ү"], False, "y", False),               # Kyrgyz letters not folded
    (["ң"], False, "н", False),
    (["ө"], False, "o", False),
    (["Ａ"], False, "a", True),               # NFKC fullwidth
    (["a", "b"], False, "b", True),
    (["a"], False, "", False),
])
def test_short_text(answers, cs, text, ok):
    data = {"answers": answers, "case_sensitive": cs}
    assert pts("short_text", data, {"text": text}).correct is ok


def test_short_text_malformed_and_cap():
    d = {"answers": ["a"]}
    for resp in (None, {}, {"text": 1}, {"text": "a" * 501}):
        assert pts("short_text", d, resp).correct is False


def test_essay():
    d = {}
    r = pts("essay", d, {"text": "hello"})
    assert (r.points, r.correct, r.needs_review) == (None, None, True)
    for resp in ({"text": ""}, {"text": "  \n"}, None, {}, {"text": "a" * 20001}):
        r = pts("essay", d, resp)
        assert (r.points, r.correct, r.needs_review) == (D("0.00"), False, False)


def test_max_points_carried():
    r = pts("single_choice", SC, {"choice_id": "B"}, "2.5")
    assert r.max_points == D("2.5") and r.points == D("2.50")


# --- key view / search ------------------------------------------------------

def test_key_views():
    assert get_type("single_choice").key_view(SC) == {"correct": "B"}
    assert get_type("multiple_answers").key_view(MA) == {"correct": ["A", "B"]}
    assert get_type("true_false").key_view({"correct": False}) == {"correct": False}
    assert get_type("comparison").key_view(GOOD["comparison"]) == {"correct": "C"}
    assert get_type("short_text").key_view({"answers": ["x"]}) == {"answers": ["x"]}
    assert get_type("numeric").key_view(NUM)["answers"] == NUM["answers"]
    assert get_type("essay").key_view({}) == {}


def test_search_strings():
    assert "opt A" in get_type("single_choice").search_strings(SC)
    assert get_type("comparison").search_strings(GOOD["comparison"]) == ["$x^2$", "4"]


# --- richtext -----------------------------------------------------------------

@pytest.mark.parametrize("raw,out", [
    ("a\r\nb\rc", "a\nb\nc"),
    ("a\x00b\x07c\x1fd\x7f", "abcd"),
    ("keep\ttab\nnl", "keep\ttab\nnl"),
    ("$x^2 < 3$ and $$\\frac{a}{b}$$", "$x^2 < 3$ and $$\\frac{a}{b}$$"),
    ("<u>under</u> <b>bold</b>", "<u>under</u> <b>bold</b>"),
    ("<script>alert(1)</script>", "<script>alert(1)</script>"),  # stored as text; renderer escapes
    ("Кыргыз тили ү ө ң", "Кыргыз тили ү ө ң"),
])
def test_clean_text(raw, out):
    assert clean_text(raw, 100) == out


def test_clean_text_limits():
    assert clean_text("a" * 10, 10) == "a" * 10
    with pytest.raises(ValueError):
        clean_text("a" * 11, 10)
    with pytest.raises(ValueError):
        clean_text(5, 10)  # type: ignore[arg-type]


def test_text_cleaned_inside_data():
    out = get_type("comparison").validate({"column_a": "a\r\n\x00b", "column_b": "1", "correct": "A"})
    assert out["column_a"] == "a\nb"
    with pytest.raises(ValidationFailed):
        get_type("single_choice").validate({"choices": [ch("A", "x" * 2001), ch("B")], "correct": "A"})
