"""Phase 7b S2 save-as-template (PHASE_7B_DESIGN 5.5, P7B-6): round trip save -> publish -> instantiate equals the
source structure; refused for preset exams (`preset_not_templatable`, 7b-Q1); `scheme_not_shareable`; nothing is
written to the source assessment."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.lms.assessments.models import Assessment, AssessmentSection
from app.lms.exam_templates.models import ExamTemplate
from app.lms.grading.seeds import ORT_MAIN_V1_ID
from tests.lms.assessment_support import mk, section
from tests.lms.factories import make_course, make_scheme
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_template_instantiate import A_COLS, S_COLS, rows
from tests.lms.test_exam_templates_api import T, create_from, err, publish_t, tworld


async def _source(api, w, **settings):
    a = await mk(api, w.TA, w.cid, title={"en": "Source"}, languages=["en", "ru"])
    body = {"draft_rev": a["draft_rev"], "navigation": "section_forward_only", "time_limit_s": 3600,
            "allowed_attempts": 2, "score_policy": "latest", "show_correct_answers": True, "shuffle_choices": True,
            "grading_scheme_version_id": str(ORT_MAIN_V1_ID), **settings}
    res = await api.call(w.TA, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}", json=body)
    assert res.status_code == 200, res.text
    await section(api, w.TA, w.cid, a["id"], key="part_a", title={"en": "A"}, instructions={"en": "i"},
                  time_limit_s=1200, rules={"allowed_types": ["single_choice"], "allow_passages": False})
    await section(api, w.TA, w.cid, a["id"], key="part_b", title={"en": "B"}, time_limit_s=2400,
                  rules={"allowed_types": ["essay", "short_text"], "allow_passages": True, "max_items": 5})
    return (await api.call(w.TA, "GET", f"/courses/{w.cid}/assessments/{a['id']}")).json()


async def test_round_trip(db, api):
    w = tworld(db)
    a = await _source(api, w)
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assessments/{a['id']}/save-as-template", json={
        "owner_scope": "teacher", "title": {"en": "Saved"}, "lock_scope": ["sections"],
        "sections_counts": [{"position": 1, "min_items": 3, "max_items": 3}]})
    assert res.status_code == 201, res.text
    t = res.json()
    assert (t["owner_scope"], t["organization_id"], t["owner_user_id"], t["status"]) == (
        "teacher", str(w.org.id), w.TA.id, "draft")
    spec = t["draft_spec"]
    assert spec["navigation"] == "section_forward_only" and spec["lock_scope"] == ["sections"]
    assert spec["importer_profile"] == "general" and spec["parameters"] == [] and spec["display_mode"] == "one_per_page"
    assert spec["sections"][0]["min_items"] == 3 and spec["sections"][0]["max_items"] == 3
    assert spec["sections"][1]["allowed_types"] == ["essay", "short_text"] and spec["sections"][1]["max_items"] == 5
    assert spec["scoring"] == {"grading_scheme_version_id": str(ORT_MAIN_V1_ID)}
    assert spec["passage_display"] is None and spec["result_view"] is None     # NULL stays NULL
    # nothing written to the source
    src = db.get(Assessment, uuid.UUID(a["id"]))
    assert src.draft_rev == a["draft_rev"] and src.exam_template_version_id is None
    # publish, instantiate in another course of the teacher: same structure
    assert (await publish_t(api, w.TA, t["id"])).status_code == 200
    other = make_course(db, w.TA, organization_id=w.org.id, status="published", languages=["en", "ru"])
    b = await create_from(api, w.TA, str(other.id), t["id"], languages=["en", "ru"])
    want_a, want_s = rows(db, a["id"])
    got_a, got_s = rows(db, b["id"])
    assert got_a == want_a
    # sections equal except the counts the body added to section 1
    want_s[0] = (*want_s[0][:5], {**want_s[0][5], "min_items": 3, "max_items": 3})
    assert got_s == want_s
    assert b["exam_template"]["template_id"] == t["id"]


async def test_scopes_and_refusals(db, api):
    w = tworld(db)
    a = await _source(api, w)
    p = f"/courses/{w.cid}/assessments/{a['id']}/save-as-template"
    # organization scope needs the org admin right (or the setting); platform scope the platform admin
    res = await api.call(w.TA, "POST", p, json={"owner_scope": "organization", "title": {"en": "O"}})
    assert res.status_code == 403 and err(res) == "scope_not_allowed"
    res = await api.call(w.TA, "POST", p, json={"owner_scope": "platform", "title": {"en": "P"}})
    assert res.status_code == 403 and err(res) == "scope_not_allowed"
    # the assistant has content.manage but is no member of the organization: teacher scope refused
    res = await api.call(w.AS, "POST", p, json={"owner_scope": "teacher", "title": {"en": "T"}})
    assert res.status_code == 403 and err(res) == "scope_not_allowed"
    assert (await api.call(w.S, "POST", p, json={"owner_scope": "teacher", "title": {"en": "T"}})).status_code == 403
    assert (await api.call(w.TC, "POST", p, json={"owner_scope": "teacher", "title": {"en": "T"}})).status_code == 404
    # bad body values go through the spec validator
    res = await api.call(w.TA, "POST", p, json={"owner_scope": "teacher", "title": {"en": "T"},
                                                "sections_counts": [{"position": 9, "min_items": 1}]})
    assert res.status_code == 422 and err(res) == "spec_invalid"
    res = await api.call(w.TA, "POST", p, json={"owner_scope": "teacher", "title": {"en": "T"}, "lock_scope": ["nope"]})
    assert res.status_code == 422 and err(res) == "spec_invalid"
    res = await api.call(w.TA, "POST", p, json={"owner_scope": "teacher", "title": {"en": "T"},
                                                "display_mode": "scrolling"})
    assert res.status_code == 201 and res.json()["draft_spec"]["display_mode"] == "scrolling"  # accepted (P7B-1)
    # an assessment without sections cannot become a template
    empty = await mk(api, w.TA, w.cid)
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assessments/{empty['id']}/save-as-template",
                         json={"owner_scope": "teacher", "title": {"en": "E"}})
    assert res.status_code == 422 and err(res) == "spec_invalid"
    assert db.execute(select(ExamTemplate)).scalars().all().__len__() == 1


async def test_scheme_not_shareable(db, api):
    w = tworld(db)
    own = make_scheme(db, w.TA)
    a = await _source(api, w, grading_scheme_version_id=str(own.current_version_id))
    p = f"/courses/{w.cid}/assessments/{a['id']}/save-as-template"
    res = await api.call(w.OA, "POST", p, json={"owner_scope": "organization", "title": {"en": "O"}})
    assert res.status_code == 403                                        # the org admin is not course staff (A13)
    ok = await api.call(w.TA, "POST", p, json={"owner_scope": "teacher", "title": {"en": "Mine"}})
    assert ok.status_code == 201, ok.text
    w.org.settings = {"teachers_can_publish_org_templates": True}
    db.commit()
    res = await api.call(w.TA, "POST", p, json={"owner_scope": "organization", "title": {"en": "O"}})
    assert res.status_code == 422 and err(res) == "scheme_not_shareable"
    assert len(db.execute(select(ExamTemplate)).scalars().all()) == 1


async def test_preset_not_templatable(db, api):
    w = tworld(db)
    ort = make_course(db, w.TA, organization_id=w.org.id, status="published", languages=["ru"], default_language="ru",
                      template_key="ort", template_version=1, template_locked=False,
                      template_settings={"language": "ru"})
    res = await api.call(w.TA, "POST", f"/courses/{ort.id}/assessments",
                         json={"title": {"ru": "ОРТ"}, "preset": "ort_main", "languages": ["ru"]})
    assert res.status_code == 201, res.text
    a = res.json()
    res = await api.call(w.TA, "POST", f"/courses/{ort.id}/assessments/{a['id']}/save-as-template",
                         json={"owner_scope": "teacher", "title": {"ru": "Шаблон"}})
    assert res.status_code == 409 and err(res) == "preset_not_templatable"
    assert db.execute(select(ExamTemplate)).first() is None
    row = db.get(Assessment, uuid.UUID(a["id"]))
    assert row.preset == "ort_main" and row.exam_template_version_id is None and row.draft_rev == a["draft_rev"]
    # a plain quiz in the ORT course may be saved (ORT teachers can give plain quizzes, design 2)
    plain = await mk(api, w.TA, str(ort.id), languages=["ru"])
    await section(api, w.TA, str(ort.id), plain["id"], rules={"allowed_types": ["single_choice"]})
    res = await api.call(w.TA, "POST", f"/courses/{ort.id}/assessments/{plain['id']}/save-as-template",
                         json={"owner_scope": "teacher", "title": {"ru": "Шаблон"}})
    assert res.status_code == 201, res.text
    assert len(db.execute(select(AssessmentSection)).scalars().all()) == 6   # 5 ORT + 1 plain, nothing added
