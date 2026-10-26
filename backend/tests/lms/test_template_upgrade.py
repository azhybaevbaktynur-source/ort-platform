"""Phase 7b S2 upgrade to the latest template version (PHASE_7B_DESIGN 5.5, P7B-7): drafts without attempts only,
sections mapped by position, items kept, violations reported as issues, parameters re-applied."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection
from app.lms.assignments.sync import mirror_mismatches
from app.lms.grading.seeds import ORT_MAIN_V1_ID, ORT_SUBJECT_V1_ID
from tests.lms.assessment_support import add_q, bank_of
from tests.lms.exam_template_support import general_spec, ort_subject_spec
from tests.lms.factories import make_assessment_version, make_attempt
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_templates_api import T, create_from, err, publish_t, published_template, tworld

V1 = general_spec(sections=[
    {"key": "a", "title": {"en": "A"}, "allowed_types": ["single_choice", "essay"], "allow_passages": True},
    {"key": "b", "title": {"en": "B"}, "allowed_types": ["single_choice"], "allow_passages": True},
])
V2 = general_spec(navigation="section_forward_only", result_view="ort",
                  scoring={"grading_scheme_version_id": str(ORT_MAIN_V1_ID)}, sections=[
    {"key": "a2", "title": {"en": "A2"}, "time_limit_s": 600, "allowed_types": ["single_choice"],
     "allow_passages": True},
    {"key": "b2", "title": {"en": "B2"}, "time_limit_s": 600, "allowed_types": ["essay"], "allow_passages": False},
    {"key": "c2", "title": {"en": "C2"}, "time_limit_s": 600, "allowed_types": ["numeric"], "allow_passages": False,
     "min_items": 1},
])
V3 = general_spec(sections=[{"key": "only", "allowed_types": ["single_choice"], "allow_passages": True}])


async def _bump(api, w, t, spec):
    cur = (await api.call(w.PA, "GET", f"{T}/{t['id']}")).json()
    res = await api.call(w.PA, "PATCH", f"{T}/{t['id']}", json={"draft_rev": cur["draft_rev"], "draft_spec": spec})
    assert res.status_code == 200, res.text
    pub = await publish_t(api, w.PA, t["id"])
    assert pub.status_code == 200, pub.text
    return pub.json()["version"]


def _items(db, aid):
    return db.execute(select(AssessmentItem).where(AssessmentItem.assessment_id == uuid.UUID(aid))
                      .order_by(AssessmentItem.section_id, AssessmentItem.position)).scalars().all()


async def test_upgrade_keeps_items_by_position_and_reports_violations(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=V1)
    a = await create_from(api, w.TA, w.cid, t["id"])
    p = f"/courses/{w.cid}/assessments/{a['id']}"
    _, qs = bank_of(db, w.course, w.TA, 3)
    sa, sb = a["sections"]
    await add_q(api, w.TA, w.cid, a["id"], sa["id"], qs[0].id)
    await add_q(api, w.TA, w.cid, a["id"], sb["id"], qs[1].id)         # single_choice: forbidden in b2 (essay only)
    await add_q(api, w.TA, w.cid, a["id"], sb["id"], qs[2].id)
    res = await api.call(w.TA, "POST", f"{p}/template-upgrade")
    assert res.status_code == 409 and err(res) == "template_upgrade_not_allowed"   # already on the latest
    v2 = await _bump(api, w, t, V2)
    staff = (await api.call(w.TA, "GET", p)).json()
    assert (staff["exam_template"]["version_no"], staff["exam_template"]["latest_version_no"]) == (1, 2)
    res = await api.call(w.TA, "POST", f"{p}/template-upgrade")
    assert res.status_code == 200, res.text
    body = res.json()
    out = body["assessment"]
    assert out["exam_template"]["version_id"] == v2["id"] and out["exam_template"]["version_no"] == 2
    assert out["navigation"] == "section_forward_only" and out["result_view"] == "ort"
    assert out["grading_scheme_version_id"] == str(ORT_MAIN_V1_ID) and out["draft_rev"] == staff["draft_rev"] + 1
    assert [(s["position"], s["key"], s["time_limit_s"]) for s in out["sections"]] == [
        (1, "a2", 600), (2, "b2", 600), (3, "c2", 600)]
    assert out["sections"][1]["rules"] == {"allowed_types": ["essay"], "allow_passages": False}
    assert [s["id"] for s in out["sections"][:2]] == [sa["id"], sb["id"]]           # rows kept, not recreated
    assert len(out["sections"][0]["items"]) == 1 and len(out["sections"][1]["items"]) == 2
    assert sorted((i["code"], i["section_pos"]) for i in body["issues"]) == [("type_not_allowed", 2)] * 2
    assert {i["item_id"] for i in body["issues"]} == {i["id"] for i in out["sections"][1]["items"]}
    row = db.get(Assessment, uuid.UUID(a["id"]))
    assert row.grading_changed_at is not None and mirror_mismatches(db, row) == {}
    # v3 drops to one section: the items of removed sections go, the first section's stay
    await _bump(api, w, t, V3)
    res = await api.call(w.TA, "POST", f"{p}/template-upgrade")
    assert res.status_code == 200, res.text
    out = res.json()["assessment"]
    assert [s["key"] for s in out["sections"]] == ["only"] and res.json()["issues"] == []
    assert len(_items(db, a["id"])) == 1 and _items(db, a["id"])[0].question_id == qs[0].id
    assert len(db.execute(select(AssessmentSection).where(
        AssessmentSection.assessment_id == uuid.UUID(a["id"]))).scalars().all()) == 1
    assert out["grading_scheme_version_id"] is None


async def test_upgrade_refusals(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=V1)
    a = await create_from(api, w.TA, w.cid, t["id"])
    b = await create_from(api, w.TA, w.cid, t["id"])
    await _bump(api, w, t, V3)
    p = f"/courses/{w.cid}/assessments"
    # published assessments never move
    row = db.get(Assessment, uuid.UUID(a["id"]))
    make_assessment_version(db, row, w.TA)
    res = await api.call(w.TA, "POST", f"{p}/{a['id']}/template-upgrade")
    assert res.status_code == 409 and err(res) == "template_upgrade_not_allowed"
    # a draft with attempts (a preview version with a student attempt) never moves either
    rb = db.get(Assessment, uuid.UUID(b["id"]))
    v = make_assessment_version(db, rb, w.TA, kind="preview", publish=False)
    make_attempt(db, rb, v, w.S, items=0)
    res = await api.call(w.TA, "POST", f"{p}/{b['id']}/template-upgrade")
    assert res.status_code == 409 and err(res) == "template_upgrade_not_allowed"
    # not a template assessment; wrong roles
    plain = (await api.call(w.TA, "POST", p, json={"title": {"en": "P"}, "preset": "none", "languages": ["en"]})).json()
    res = await api.call(w.TA, "POST", f"{p}/{plain['id']}/template-upgrade")
    assert res.status_code == 422 and err(res) == "not_a_template_assessment"
    assert (await api.call(w.S, "POST", f"{p}/{b['id']}/template-upgrade")).status_code == 403
    assert (await api.call(w.X, "POST", f"{p}/{b['id']}/template-upgrade")).status_code == 404
    assert (await api.call(w.OA, "POST", f"{p}/{b['id']}/template-upgrade")).status_code == 403
    assert rb.exam_template_version_id == uuid.UUID(t["current_version"]["id"])
    # a template re-published with the scrolling mode cannot be upgraded to until 8b
    await _bump(api, w, t, general_spec(display_mode="scrolling"))
    c = await create_from(api, w.TA, w.cid, t["id"], version_id=t["current_version"]["id"])
    res = await api.call(w.TA, "POST", f"{p}/{c['id']}/template-upgrade")
    assert res.status_code == 422 and err(res) == "display_mode_not_available"


async def test_upgrade_reapplies_parameters(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=ort_subject_spec())
    a = await create_from(api, w.TA, w.cid, t["id"], parameters={"subject": "biology"})
    spec2 = ort_subject_spec()
    spec2["sections"][0]["time_limit_s"] = 4800
    await _bump(api, w, t, spec2)
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assessments/{a['id']}/template-upgrade")
    assert res.status_code == 200, res.text
    s = res.json()["assessment"]["sections"]
    assert [(x["key"], x["time_limit_s"]) for x in s] == [("biology", 4800)]
    assert res.json()["assessment"]["grading_scheme_version_id"] == str(ORT_SUBJECT_V1_ID)
    # the stored key is no longer an option: 422 parameter_missing, nothing changed
    spec3 = ort_subject_spec()
    spec3["parameters"][0]["options"] = ["chemistry", "physics"]
    await _bump(api, w, t, spec3)
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assessments/{a['id']}/template-upgrade")
    assert res.status_code == 422 and err(res) == "parameter_missing"
    row = db.get(Assessment, uuid.UUID(a["id"]))
    db.refresh(row)
    assert db.execute(select(AssessmentSection.time_limit_s).where(
        AssessmentSection.assessment_id == row.id)).scalar() == 4800
