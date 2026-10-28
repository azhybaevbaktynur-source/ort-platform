"""Phase 8b S1 (PHASE_8B_DESIGN 5.3, 5.4, 6.2, P8B-4): `display_mode`, `passage_display`, `result_view` are editable on
general assessments through `PATCH /courses/{c}/assessments/{a}`; null passage display / result view = inherit; a
change bumps `draft_rev`; the exam-template lock scope (`display_mode`, `result_view` which also governs the passage
display) and the ORT course template (preset exams) answer 409 `template_locked`; the values reach the student's
attempt state, result and review after a publish."""
from __future__ import annotations

import uuid

import pytest

from app.lms.assessments.models import Assessment
from app.lms.grading.seeds import ORT_MAIN_V1_ID
from app.lms.templates import base as tpl_fields
from tests.lms.assessment_support import add_q, bank_of, get, mk, publish, section, world
from tests.lms.exam_template_support import general_spec
from tests.lms.factories import make_assessment, make_course, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_templates_api import T, create_from, err, published_template, tworld


def _p(cid, aid):
    return f"/courses/{cid}/assessments/{aid}"


async def _patch(api, user, cid, aid, **body):
    rev = (await api.call(user, "GET", _p(cid, aid))).json().get("draft_rev")
    return await api.call(user, "PATCH", _p(cid, aid), json={"draft_rev": rev, **body})


async def test_general_quiz_display_fields_roundtrip(db, api):
    w = world(db)
    a = await mk(api, w.O, w.cid)
    assert (a["display_mode"], a["passage_display"], a["result_view"]) == ("one_per_page", None, None)
    rev = a["draft_rev"]
    res = await api.call(w.O, "PATCH", _p(w.cid, a["id"]), json={
        "draft_rev": rev, "display_mode": "scrolling", "passage_display": "numbered", "result_view": "ort"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert (out["display_mode"], out["passage_display"], out["result_view"]) == ("scrolling", "numbered", "ort")
    assert out["draft_rev"] == rev + 1
    row = db.get(Assessment, uuid.UUID(a["id"]))
    db.refresh(row)
    assert (row.display_mode, row.passage_display, row.result_view) == ("scrolling", "numbered", "ort")
    # explicit null = inherit the course template's value; display_mode is never null
    res = await _patch(api, w.O, w.cid, a["id"], passage_display=None, result_view=None)
    assert res.status_code == 200 and (res.json()["passage_display"], res.json()["result_view"]) == (None, None)
    for bad in ({"display_mode": None}, {"display_mode": "paged"}, {"passage_display": "fancy"},
                {"result_view": "scaled"}):
        res = await _patch(api, w.O, w.cid, a["id"], **bad)
        assert res.status_code == 422, (bad, res.text)
    # an assistant manages content; a student and an outsider cannot
    assert (await _patch(api, w.AS, w.cid, a["id"], display_mode="one_per_page")).status_code == 200
    assert (await api.call(w.S, "PATCH", _p(w.cid, a["id"]),
                           json={"draft_rev": 1, "display_mode": "scrolling"})).status_code in (403, 404)
    assert (await api.call(w.X, "PATCH", _p(w.cid, a["id"]),
                           json={"draft_rev": 1, "display_mode": "scrolling"})).status_code == 404


async def test_display_fields_reach_attempt_state_result_and_review(db, api):
    w = world(db)
    bank, qs = bank_of(db, w.course, w.O, 2)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    for q in qs:
        await add_q(api, w.O, w.cid, a["id"], s["id"], q.id)
    res = await _patch(api, w.O, w.cid, a["id"], display_mode="scrolling", passage_display="numbered",
                       result_view="ort", results_policy="after_submit")
    assert res.status_code == 200, res.text
    assert (await publish(api, w.O, w.cid, a["id"])).status_code == 200
    st = await api.call(w.S, "POST", f"{_p(w.cid, a['id'])}/attempts", json={"language": "en"})
    assert st.status_code == 201, st.text
    assert (st.json()["display_mode"], st.json()["passage_display"]) == ("scrolling", "numbered")
    tid = st.json()["id"]
    state = (await api.call(w.S, "GET", f"/attempts/{tid}")).json()
    assert (state["display_mode"], state["passage_display"]) == ("scrolling", "numbered")
    assert "result_view" not in state                                    # the state never carries the result view
    sub = await api.call(w.S, "POST", f"/attempts/{tid}/submit", json={})
    assert sub.status_code == 200 and sub.json()["result"]["result_view"] == "ort", sub.text
    result = (await api.call(w.S, "GET", f"/attempts/{tid}/result")).json()
    assert (result["result_view"], result["passage_display"]) == ("ort", "numbered")
    review = await api.call(w.S, "GET", f"/attempts/{tid}/review")
    assert review.status_code == 200, review.text
    assert (review.json()["result_view"], review.json()["passage_display"]) == ("ort", "numbered")


async def test_inherit_resolves_to_general_defaults(db, api):
    w = world(db)
    bank, qs = bank_of(db, w.course, w.O, 1)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    await add_q(api, w.O, w.cid, a["id"], s["id"], qs[0].id)
    assert (await _patch(api, w.O, w.cid, a["id"], results_policy="after_submit")).status_code == 200
    assert (await publish(api, w.O, w.cid, a["id"])).status_code == 200
    st = (await api.call(w.S, "POST", f"{_p(w.cid, a['id'])}/attempts", json={"language": "en"})).json()
    assert (st["display_mode"], st["passage_display"]) == ("one_per_page", "plain")
    await api.call(w.S, "POST", f"/attempts/{st['id']}/submit", json={})
    result = (await api.call(w.S, "GET", f"/attempts/{st['id']}/result")).json()
    assert (result["result_view"], result["passage_display"]) == ("general", "plain")


@pytest.mark.parametrize("lock_scope, locked, free", [
    (["display_mode"], {"display_mode": "scrolling"}, {"passage_display": "numbered", "result_view": "ort"}),
    (["result_view"], {"passage_display": "numbered", "result_view": "ort"}, {"display_mode": "scrolling"}),
])
async def test_exam_template_lock_scope_guards_display_fields(db, api, lock_scope, locked, free):
    w = tworld(db)
    spec = general_spec(scoring={"grading_scheme_version_id": str(ORT_MAIN_V1_ID)}, lock_scope=lock_scope)
    t = await published_template(api, w.PA, spec=spec)
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/lock")).status_code == 200
    a = await create_from(api, w.TA, w.cid, t["id"])
    assert a["structure_locked"] is True
    want_field = tpl_fields.LOCK_DISPLAY_MODE if lock_scope == ["display_mode"] else tpl_fields.LOCK_RESULT_VIEW
    for field, value in locked.items():
        res = await _patch(api, w.TA, w.cid, a["id"], **{field: value})
        assert res.status_code == 409 and err(res) == "template_locked", (field, res.text)
        assert res.json()["error"]["details"] == {"field": want_field, "source": "exam_template"}
    # the unchanged value passes; the fields outside the lock scope stay editable
    same = await _patch(api, w.TA, w.cid, a["id"], display_mode=a["display_mode"],
                        passage_display=a["passage_display"], result_view=a["result_view"])
    assert same.status_code == 200, same.text
    res = await _patch(api, w.TA, w.cid, a["id"], **free)
    assert res.status_code == 200, res.text


async def test_ort_preset_exam_refuses_display_changes(db, api):
    owner = make_user(db, teacher_status="approved")
    ort = make_course(db, owner, status="published", languages=["ru"], default_language="ru", template_key="ort",
                      template_version=1, template_locked=True)
    a = make_assessment(db, ort, owner, preset="ort_main", languages=["ru"], navigation="section_forward_only")
    cid, aid = str(ort.id), str(a.id)
    out = await get(api, owner, cid, aid)
    assert (out["display_mode"], out["passage_display"], out["result_view"]) == ("one_per_page", None, None)
    for field, value, lock in (("display_mode", "scrolling", tpl_fields.LOCK_DISPLAY_MODE),
                               ("passage_display", "plain", tpl_fields.LOCK_RESULT_VIEW),
                               ("result_view", "general", tpl_fields.LOCK_RESULT_VIEW)):
        res = await _patch(api, owner, cid, aid, **{field: value})
        assert res.status_code == 409 and err(res) == "template_locked", (field, res.text)
        assert res.json()["error"]["details"] == {"field": lock}
    db.refresh(a)
    assert (a.display_mode, a.passage_display, a.result_view) == ("one_per_page", None, None)
