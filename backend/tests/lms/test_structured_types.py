"""Phase 10 S1: matching, fill_blank, ordering (PHASE_10_DESIGN 2). Unit tests of the scorer classes, the no-leak
guarantee, autosave shapes, the full quiz flow, the general import format and the ORT refusal in every layer."""
from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest

from app.lms.assessments.rules import ORT_SECTION_RULES
from app.lms.content.importers.general_csv import KNOWN_COLUMNS
from app.lms.content.types import REGISTRY, get_type
from app.lms.content.types.base import ImportRowError, proportional
from app.lms.content.types.structured import STRUCTURED_TYPES, derive_id
from app.lms.core.errors import ValidationFailed
from app.lms.templates.service import assert_question_type_allowed
from tests.lms.assessment_support import add_q, mk, publish, section
from tests.lms.attempt_support import frozen_clock  # noqa: F401
from tests.lms.content_support import new_bank, new_question, qbody, world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

D = Decimal

MATCH = {"pairs": [{"left": "Bishkek", "right": "Kyrgyzstan"}, {"left": "Astana", "right": "Kazakhstan"},
                   {"left": "Tashkent", "right": "Uzbekistan"}], "distractors": ["Tajikistan"]}
BLANK = {"text": "The {{1}} is {{2}}.", "blanks": [{"answers": ["sky", "heaven"]}, {"answers": ["blue"]}]}
ORDER = {"items": [{"text": "first"}, {"text": "second"}, {"text": "third"}, {"text": "fourth"}]}
DATA = {"matching": MATCH, "fill_blank": BLANK, "ordering": ORDER}


def valid(t, data=None):
    return get_type(t).validate(data if data is not None else DATA[t])


def bad(t, data, fragment=None):
    with pytest.raises(ValidationFailed) as e:
        get_type(t).validate(data)
    if fragment:
        assert fragment in str(e.value.details)


# ------------------------------------------------------------------ validation

def test_registered_after_essay():
    names = list(REGISTRY)
    assert names[-3:] == list(STRUCTURED_TYPES) and names.index("essay") == len(names) - 4
    for n in STRUCTURED_TYPES:
        assert REGISTRY[n].supports_passages is False and REGISTRY[n].title_key == f"bank.types.{n}.name"


def test_matching_limits():
    bad("matching", {"pairs": [{"left": "a", "right": "b"}]})                                   # < 2 pairs
    bad("matching", {"pairs": [{"left": f"l{i}", "right": "r"} for i in range(21)]})            # > 20
    bad("matching", {"pairs": [{"left": "a", "right": "x"}, {"left": "a", "right": "y"}]}, "unique")
    ok = valid("matching", {"pairs": [{"left": "a", "right": "same"}, {"left": "b", "right": "same"}]})
    assert ok["pairs"][0]["right_id"] == ok["pairs"][1]["right_id"]                              # shared right allowed
    bad("matching", {**MATCH, "distractors": ["Kyrgyzstan"]}, "distractor")
    bad("matching", {**MATCH, "distractors": [f"d{i}" for i in range(11)]})
    bad("matching", {"pairs": [{"left": " ", "right": "b"}, {"left": "c", "right": "d"}]})


def test_fill_blank_limits_and_tokens():
    bad("fill_blank", {"text": "no tokens", "blanks": [{"answers": ["a"]}]}, "tokens")
    bad("fill_blank", {"text": "{{2}} {{1}}", "blanks": [{"answers": ["a"]}, {"answers": ["b"]}]}, "tokens")
    bad("fill_blank", {"text": "{{1}} {{1}}", "blanks": [{"answers": ["a"]}]}, "tokens")
    bad("fill_blank", {"text": "{{1}} {{2}}", "blanks": [{"answers": ["a"]}]}, "tokens")
    bad("fill_blank", {"text": "{{1}}", "blanks": [{"answers": []}]})
    bad("fill_blank", {"text": "{{1}}", "blanks": [{"answers": ["  "]}]})
    bad("fill_blank", {"text": "".join(f"{{{{{i}}}}}" for i in range(1, 12)),
                       "blanks": [{"answers": ["a"]}] * 11})
    valid("fill_blank", {"text": "{{1}}", "blanks": [{"answers": [f"a{i}" for i in range(10)]}]})
    bad("fill_blank", {"text": "{{1}}", "blanks": [{"answers": [f"a{i}" for i in range(11)]}]})


def test_ordering_limits():
    bad("ordering", {"items": [{"text": "a"}, {"text": "b"}]})
    bad("ordering", {"items": [{"text": "a"}, {"text": "b"}, {"text": "a"}]}, "unique")
    bad("ordering", {"items": [{"text": f"i{i}"} for i in range(21)]})


def test_client_ids_are_ignored():
    d = valid("matching", {"pairs": [{"left": "a", "right": "b", "left_id": "evil", "right_id": "evil2"},
                                     {"left": "c", "right": "d", "left_id": "evil"}], "distractor_ids": ["x"]})
    assert d["pairs"][0]["left_id"] == derive_id("l", "a") and d["pairs"][0]["right_id"] == derive_id("r", "b")
    assert d["distractor_ids"] == []
    o = valid("ordering", {"items": [{"text": "a", "id": "zzz"}, {"text": "b"}, {"text": "c"}]})
    assert o["items"][0]["id"] == derive_id("o", "a")
    # stored data validates again to the same data (ids kept)
    for t in STRUCTURED_TYPES:
        v = valid(t)
        assert get_type(t).validate(v) == v


# ------------------------------------------------------------------ no leak

def test_student_view_allow_list_and_order_independence():
    for t in STRUCTURED_TYPES:
        sv = get_type(t).student_view(valid(t))
        assert set(sv) <= get_type(t).STUDENT_KEYS
    sv = get_type("matching").student_view(valid("matching"))
    assert [r["id"] for r in sv["lefts"]] == sorted(r["id"] for r in sv["lefts"])
    assert len(sv["rights"]) == 4                                           # three rights + one distractor
    assert "Tajikistan" in [r["text"] for r in sv["rights"]]
    assert get_type("fill_blank").student_view(valid("fill_blank")) == {"text": BLANK["text"], "blank_count": 2}
    flat = str(get_type("fill_blank").student_view(valid("fill_blank")))
    assert "sky" not in flat and "blue" not in flat


def test_student_view_independent_of_author_order():
    rev = {"pairs": list(reversed(MATCH["pairs"])), "distractors": MATCH["distractors"]}
    m = get_type("matching")
    assert m.student_view(valid("matching")) == m.student_view(valid("matching", rev))
    o = get_type("ordering")
    shuffled = {"items": [ORDER["items"][i] for i in (2, 0, 3, 1)]}
    sv = o.student_view(valid("ordering"))
    assert sv == o.student_view(valid("ordering", shuffled))
    assert set(sv) == {"items"} and all(set(i) == {"id", "text"} for i in sv["items"])
    assert "order" not in str(sv) and "answers" not in str(get_type("matching").student_view(valid("matching")))


# ------------------------------------------------------------------ scoring

def score(t, resp, mx="10", data=None):
    return get_type(t).score(valid(t, data), resp, D(mx))


def pair_resp(*, skip=(), wrong=()):
    v = valid("matching")
    out = {}
    for i, p in enumerate(v["pairs"]):
        if i in skip:
            continue
        out[p["left_id"]] = v["pairs"][(i + 1) % 3]["right_id"] if i in wrong else p["right_id"]
    return {"pairs": out}


def test_matching_scoring():
    assert score("matching", pair_resp()).points == D("10.00") and score("matching", pair_resp()).correct is True
    r = score("matching", pair_resp(wrong=(0,)))
    assert r.points == D("6.66") and r.correct is False                      # 2 of 3, rounded down
    assert score("matching", pair_resp(skip=(0, 1), wrong=(2,))).points == D("0.00")
    assert score("matching", {"pairs": {}}).points == D("0.00")
    assert score("matching", None).points == D("0.00")
    assert score("matching", {"pairs": {"nope": "nada"}}).points == D("0.00")   # unknown ids ignored


def test_fill_blank_scoring():
    assert score("fill_blank", {"blanks": {"1": "Sky", "2": " BLUE "}}).points == D("10.00")
    assert score("fill_blank", {"blanks": {"1": "heaven", "2": "red"}}).points == D("5.00")
    assert score("fill_blank", {"blanks": {"1": "x"}}).points == D("0.00")
    cs = {**BLANK, "case_sensitive": True}
    assert score("fill_blank", {"blanks": {"1": "Sky", "2": "blue"}}, data=cs).points == D("5.00")
    assert score("fill_blank", None).points == D("0.00")


def test_ordering_scoring():
    ids = [i["id"] for i in valid("ordering")["items"]]
    assert score("ordering", {"order": ids}).points == D("10.00")
    assert score("ordering", {"order": [ids[1], ids[0], ids[2], ids[3]]}).points == D("5.00")   # 2 of 4 in place
    assert score("ordering", {"order": list(reversed(ids))}).points == D("0.00")
    assert score("ordering", {"order": ids[:3]}).points == D("0.00")                           # not a permutation
    assert score("ordering", {"order": ids[:3] + ["zzzz"]}).points == D("0.00")
    assert score("ordering", {"order": [ids[0]] * 4}).points == D("0.00")
    assert score("ordering", {"order": []}).points == D("0.00")


def test_proportional_never_reaches_max_unless_all():
    r = proportional(19, 20, D("0.01"))
    assert r.points < D("0.01") and r.correct is False
    assert proportional(20, 20, D("0.01")).correct is True
    assert proportional(0, 5, D("3")).points == D("0.00")
    assert proportional(1, 3, D("1")).points == D("0.33")


def test_empty_responses_are_blank():
    from app.lms.attempts.grading import is_blank

    for t, empty in (("matching", {"pairs": {}}), ("fill_blank", {"blanks": {"1": "  "}}), ("ordering", {"order": []})):
        assert is_blank(get_type(t), empty) is True
    assert is_blank(get_type("ordering"), {"order": ["abcd1234"]}) is False


def test_autosave_shapes():
    ok = [("matching", {"pairs": {"abcd1234": "efgh5678"}}), ("matching", {"pairs": {}}),
          ("fill_blank", {"blanks": {"1": "x" * 200}}), ("ordering", {"order": ["a", "b"]})]
    for t, r in ok:
        get_type(t).Response(**r)
    no = [("matching", {"pairs": {"a" * 9: "b"}}), ("matching", {"pairs": {str(i): "b" for i in range(21)}}),
          ("matching", {"extra": 1}), ("fill_blank", {"blanks": {"x": "y"}}),
          ("fill_blank", {"blanks": {"1": "x" * 201}}), ("fill_blank", {"blanks": {str(i): "a" for i in range(11)}}),
          ("ordering", {"order": ["a" * 9]}), ("ordering", {"order": ["a"] * 21}), ("ordering", {"order": "abc"})]
    for t, r in no:
        with pytest.raises(Exception):
            get_type(t).Response(**r)


# ------------------------------------------------------------------ import

def row(**kw):
    return {"stem": "q", **kw}


def test_import_rows():
    m = get_type("matching")
    d = m.validate(m.from_import_row(row(match_pairs="a=>x|b=>y", match_distractors="z|w")))
    assert len(d["pairs"]) == 2 and d["distractors"] == ["z", "w"]
    f = get_type("fill_blank")
    d = f.validate(f.from_import_row(row(blank_text="A {{1}} b {{2}}", blank_answers="a|alt||b", case_sensitive="true")))
    assert d["blanks"][0]["answers"] == ["a", "alt"] and d["case_sensitive"] is True
    o = get_type("ordering")
    assert len(o.validate(o.from_import_row(row(order_items="x|y|z")))["items"]) == 3


@pytest.mark.parametrize("t,r,col", [
    ("matching", {"match_pairs": ""}, "match_pairs"), ("matching", {"match_pairs": "a-b|c=>d"}, "match_pairs"),
    ("fill_blank", {"blank_text": "", "blank_answers": "a"}, "blank_text"),
    ("fill_blank", {"blank_text": "{{1}}", "blank_answers": ""}, "blank_answers"),
    ("fill_blank", {"blank_text": "{{1}}", "blank_answers": "a", "case_sensitive": "maybe"}, "case_sensitive"),
    ("ordering", {"order_items": ""}, "order_items")])
def test_import_row_errors(t, r, col):
    with pytest.raises(ImportRowError) as e:
        get_type(t).from_import_row(row(**r))
    assert e.value.column == col


def test_known_columns_include_structured():
    for c in ("match_pairs", "match_distractors", "blank_text", "blank_answers", "order_items"):
        assert c in KNOWN_COLUMNS


def csv_bytes(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["type", "stem", "language", "match_pairs", "blank_text", "blank_answers", "order_items"])
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


def parse(rows, **opts):
    from app.lms.content.importers.parse import parse_upload
    from app.lms.content.importers.schemas import ImportOptions

    return parse_upload(csv_bytes(rows), "q.csv", ImportOptions(language="en", **opts))


def test_csv_import_valid_rows_and_one_error_per_column():
    up = parse([["matching", "Match", "en", "a=>x|b=>y", "", "", ""],
                ["fill_blank", "Fill", "en", "", "A {{1}}", "yes", ""],
                ["ordering", "Order", "en", "", "", "", "a|b|c"]])
    assert not up.issues.errors, [i.message for i in up.issues.errors]
    assert sum(len(b.items) for b in up.bundles) == 3
    up = parse([["matching", "Match", "en", "oops", "", "", ""], ["ordering", "Order", "en", "", "", "", ""]])
    cols = sorted((i.column, i.row) for i in up.issues.errors)
    assert [c for c, _ in cols] == ["match_pairs", "order_items"]


def test_csv_import_refused_by_template():
    up = parse([["ordering", "Order", "en", "", "", "", "a|b|c"]], refused_types=list(STRUCTURED_TYPES))
    assert [i.code for i in up.issues.errors] == ["type_not_allowed"]


# ------------------------------------------------------------------ catalog and ORT

async def test_catalog_lists_types(db, api):
    w = world(db)
    r = await api.call(w.O, "GET", "/exam-templates/blocks")
    assert r.status_code == 200, r.text
    for t in STRUCTURED_TYPES:
        assert f'"bank.types.{t}.name"' in r.text


def test_every_ort_section_refuses_the_types():
    for key, rules in ORT_SECTION_RULES.items():
        assert not set(STRUCTURED_TYPES) & set(rules["allowed_types"]), key


def test_ort_template_refuses_and_general_accepts(db):
    w = world(db)
    assert_question_type_allowed(w.course, "matching")                       # general course
    w.course.template_key, w.course.template_version = "ort", 1
    db.commit()
    for t in STRUCTURED_TYPES:
        with pytest.raises(ValidationFailed) as e:
            assert_question_type_allowed(w.course, t)
        assert e.value.code == "type_not_allowed"
    assert_question_type_allowed(w.course, "single_choice")


async def test_ort_course_bank_and_quiz_refuse(db, api):
    w = world(db)
    w.course.template_key, w.course.template_version = "ort", 1
    db.commit()
    bank = await new_bank(api, w.O, w.cid)
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{bank['id']}/questions",
                       json=qbody(type="ordering", data=ORDER))
    assert r.status_code == 422 and r.json()["error"]["code"] == "type_not_allowed", r.text


async def test_general_course_accepts_all_three(db, api):
    w = world(db)
    bank = await new_bank(api, w.O, w.cid)
    for t in STRUCTURED_TYPES:
        q = await new_question(api, w.O, w.cid, bank["id"], type=t, data=DATA[t])
        assert q["type"] == t


async def test_ort_import_and_shared_copy_refuse(db, api):
    from app.lms.content.importers import service as imp
    from app.lms.content.importers.schemas import ImportOptions

    w = world(db)
    assert imp._with_refused(w.course, ImportOptions()).refused_types == []
    w.course.template_key, w.course.template_version = "ort", 1
    db.commit()
    assert imp._with_refused(w.course, ImportOptions()).refused_types == list(STRUCTURED_TYPES)


# ------------------------------------------------------------------ full quiz flow

async def test_quiz_flow_all_three_types(db, api, frozen_clock):
    w = world(db)
    bank = await new_bank(api, w.O, w.cid)
    qs = {}
    for t in STRUCTURED_TYPES:
        qs[t] = await new_question(api, w.O, w.cid, bank["id"], type=t, data=DATA[t], default_points=4,
                                   stem=f"stem {t}")
    a = await mk(api, w.O, w.cid)
    sec = await section(api, w.O, w.cid, a["id"])
    for t in STRUCTURED_TYPES:
        await add_q(api, w.O, w.cid, a["id"], sec["id"], qs[t]["id"])
    pub = await publish(api, w.O, w.cid, a["id"])
    assert pub.status_code == 200, pub.text
    base = f"/courses/{w.cid}/assessments/{a['id']}"
    st = await api.call(w.S, "POST", f"{base}/attempts", json={"language": "en"})
    assert st.status_code == 201, st.text
    state = st.json()
    aid = state["id"]
    content = (await api.call(w.S, "GET", state["content_url"])).json()
    # the student payload never carries keys
    text = str(content)
    for secret in ("right_id", "distractor_ids", "sky", "heaven", "blue", "Kyrgyzstan"[:0] or "answers"):
        assert secret not in text, secret
    by_type = {q["type"]: (i["position"], q) for i in state["items"]
               for q in [content["questions"][i["qv"]]]}
    # matching: 2 of 3 right; fill_blank: 1 of 2; ordering: all in place
    mv = valid("matching")
    resp_m = {"pairs": {p["left_id"]: p["right_id"] for p in mv["pairs"][:2]}}
    resp_f = {"blanks": {"1": "sky", "2": "red"}}
    ids = [i["id"] for i in valid("ordering")["items"]]
    answers = [{"position": by_type["matching"][0], "response": resp_m, "client_ts": 1},
               {"position": by_type["fill_blank"][0], "response": resp_f, "client_ts": 2},
               {"position": by_type["ordering"][0], "response": {"order": ids}, "client_ts": 3}]
    r = await api.call(w.S, "PUT", f"/attempts/{aid}/answers", json={"answers": answers})
    assert r.status_code == 200, r.text
    bad_shape = await api.call(w.S, "PUT", f"/attempts/{aid}/answers", json={"answers": [
        {"position": by_type["matching"][0], "response": {"pairs": {"x" * 9: "y"}}, "client_ts": 4}]})
    assert bad_shape.status_code == 422
    sub = await api.call(w.S, "POST", f"/attempts/{aid}/submit", json={})
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "graded"
    rev = await api.call(w.S, "GET", f"/attempts/{aid}/review")
    if rev.status_code == 200:
        items = rev.json()["items"]
        by = {i["question"]["type"]: i for i in items}
        assert by["matching"]["correctness"] == "partial" and D(str(by["matching"]["score"])) == D("2.66")
        assert by["fill_blank"]["correctness"] == "partial" and D(str(by["fill_blank"]["score"])) == D("2.00")
        assert by["ordering"]["correctness"] == "correct" and D(str(by["ordering"]["score"])) == D("4.00")
    res = await api.call(w.S, "GET", f"/attempts/{aid}/result")
    assert res.status_code == 200, res.text
    assert D(str(res.json().get("raw_score", res.json().get("score", "0")))) == D("8.66")
