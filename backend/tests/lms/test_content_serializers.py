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


# ---------------------------------------------------------------------------------------------------------
# API contract tests (slice C4): students never receive keys, on any content endpoint
# ---------------------------------------------------------------------------------------------------------

import copy  # noqa: E402

from app.lms.content import repository as _repo  # noqa: E402
from app.lms.content import schemas as _sch  # noqa: E402
from tests.lms.content_support import new_bank, new_passage, world  # noqa: E402
from tests.lms.factories import make_asset  # noqa: E402
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401,E402

QUESTION_KEYS = {"id", "type", "language", "stem", "image_url", "points", "data", "passage"}
PASSAGE_KEYS = {"id", "title", "body", "image_url"}


def api_data(name, sentinel, asset_id):
    data = copy.deepcopy(build(name, sentinel))
    for ch in data.get("choices", []):
        ch.pop("image", None)
    if name == "single_choice":
        data["choices"][1]["image_asset_id"] = str(asset_id)
    return data


def test_response_models_have_exact_student_keys():
    assert set(_sch.StudentQuestionOut.model_fields) == QUESTION_KEYS - {"passage"}
    assert set(_sch.QuestionPreviewOut.model_fields) == QUESTION_KEYS
    assert set(_sch.StudentPassageOut.model_fields) == PASSAGE_KEYS


async def _seed(api, db, w, name, sentinel):
    asset = make_asset(db, w.O, w.course)
    b = await new_bank(api, w.O, w.cid)
    p = await new_passage(api, w.O, w.cid, b["id"], body="Reading body", title="Title")
    body = {"type": name, "language": "en", "stem": "A stem", "data": api_data(name, sentinel, asset.id),
            "explanation": sentinel + "_EXPLANATION", "default_points": 3, "passage_id": p["id"],
            "image_asset_id": str(asset.id), "topic": "t"}
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b['id']}/questions", json=body)
    assert res.status_code == 201, res.text
    return b, p, res.json()


@pytest.mark.parametrize("name", list(EXPECTED_KEYS))
async def test_preview_never_contains_key_material(db, api, name):
    w = world(db)
    sentinel = S(name)
    b, p, q = await _seed(api, db, w, name, sentinel)
    # not vacuous: the staff view of the same question does carry the sentinels
    staff = json.dumps((await api.call(w.AS, "GET", f"/courses/{w.cid}/questions/{q['id']}")).json(), ensure_ascii=False)
    assert sentinel in staff or name not in ("short_text", "essay")
    assert sentinel + "_EXPLANATION" in staff
    for params in ({}, {"version_id": q["current_version"]["id"]}):
        res = await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}/preview", params=params)
        assert res.status_code == 200, res.text
        body = res.json()
        dumped = json.dumps(body, ensure_ascii=False)
        assert set(body) == QUESTION_KEYS and set(body["passage"]) == PASSAGE_KEYS
        assert set(body["data"]) == EXPECTED_KEYS[name]
        assert body["id"] == q["current_version"]["id"] and body["points"] == 3.0
        assert "SENTINEL" not in dumped and "explanation" not in dumped
        assert body["passage"]["body"] == "Reading body"
        for tok in FORBIDDEN_TOKENS:
            assert tok not in json.dumps(body["data"]), tok
        assert "asset_id" not in dumped and body["image_url"].startswith("/api/v1/media/")


async def test_preview_of_an_older_version_and_unknown_version(db, api):
    w = world(db)
    b, p, q = await _seed(api, db, w, "short_text", S("old"))
    v1 = q["current_version"]["id"]
    new_data = {"answers": ["other"], "case_sensitive": False}
    ed = await api.call(w.O, "PATCH", f"/courses/{w.cid}/questions/{q['id']}", json={
        "base_version_id": v1, "content": {"type": "short_text", "stem": "New stem", "data": new_data}})
    assert ed.status_code == 200
    old = (await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}/preview", params={"version_id": v1})).json()
    cur = (await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}/preview")).json()
    assert old["stem"] == "A stem" and cur["stem"] == "New stem" and old["id"] == v1
    assert old["data"] == {} and cur["data"] == {}
    bad = await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}/preview",
                         params={"version_id": str(w.course.id)})
    assert bad.status_code == 404 and bad.json()["error"]["code"] == "version_not_found"


async def test_students_get_403_without_leaking_anything_on_every_content_endpoint(db, api):
    from tests.lms.test_content_matrix import ROUTES

    w = world(db)
    sentinel = S("student")
    b, p, q = await _seed(api, db, w, "essay", sentinel)
    ids = type("I", (), dict(c=w.cid, b=b["id"], q=q["id"], q2=q["id"], qru=q["id"], p=p["id"],
                             v=q["current_version"]["id"], pv=p["current_version"]["id"]))
    for name, (method, tpl, body, kind, _) in ROUTES.items():
        res = await api.call(w.S, method, tpl.format(**vars(ids)), json=body(ids) if body else None)
        assert res.status_code == 403, (name, res.status_code)
        assert "SENTINEL" not in res.text and "correct" not in res.text, name
        assert set(res.json()) == {"error"}


async def test_multiple_answers_and_numeric_edit_keeps_student_view_clean(db, api):
    w = world(db)
    for name in ("multiple_answers", "numeric", "comparison", "true_false"):
        b, p, q = await _seed(api, db, w, name, S(name))
        res = await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}/preview")
        assert set(res.json()["data"]) == EXPECTED_KEYS[name]


def test_repository_student_payload_helpers_are_pure_allowlists():
    import uuid
    from decimal import Decimal

    from app.lms.content.models import PassageVersion, QuestionVersion

    for name in EXPECTED_KEYS:
        s = S(name)
        data = get_type(name).validate(build(name, s))
        v = QuestionVersion(id=uuid.uuid4(), question_id=uuid.uuid4(), version_no=1, language="en", type=name,
                            stem="stem", data=data, explanation=s + "_E", default_points=Decimal("2.5"),
                            image=None, content_hash="h", origin="create")
        out = _repo.student_question(v)
        assert set(out) == QUESTION_KEYS - {"passage"} and out["points"] == 2.5 and out["id"] == v.id
        assert "SENTINEL" not in json.dumps(out, default=str)
    pv = PassageVersion(id=uuid.uuid4(), passage_id=uuid.uuid4(), version_no=1, language="en", title="t", body="b",
                        image={"asset_id": str(uuid.uuid4()), "sha256": SHA}, content_hash="h", origin="create")
    out = _repo.student_passage(pv)
    assert set(out) == PASSAGE_KEYS and out["image_url"] == f"/api/v1/media/{SHA}.webp"
