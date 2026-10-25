"""Course template guards (PHASE_6_DESIGN 5, 6 "Template guard tests"): registry, ORT wrap, presets, importer
profiles, the locked ORT template (5.4), the platform-admin unlock and GET /courses/templates (5.5)."""
from __future__ import annotations

import uuid
from typing import get_args

import pytest
from sqlalchemy import select

from app.lms.assessments.rules import ORT_MAIN_SECTIONS, ORT_PRESETS, ORT_SUBJECT_KEYS
from app.lms.assessments.schemas import Preset
from app.lms.audit.models import AdminAuditLog
from app.lms.content.importers.schemas import EXAM_TYPES
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.courses.models import Course
from app.lms.grading import seeds
from app.lms.organizations.ids import platform_org_id
from app.lms.organizations.models import Organization, OrganizationMember, OrganizationTemplateGrant
from app.lms.ort.seed import DEMO_TEACHER_ID, course_id_for, ensure_ort_courses
from app.lms.templates import base, registry
from app.lms.templates import service as tpl
from app.lms.templates.general import GENERAL
from app.lms.templates.ort import ORT
from tests.lms.assessment_support import cmp_q, mk, sc, section
from tests.lms.content_support import world
from tests.lms.factories import enroll, make_bank, make_course, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_import_api import imp, zbytes

MAIN_KEYS = [k for k, _ in ORT_MAIN_SECTIONS]
TEMPLATE_OUT_KEYS = {"key", "version", "locked", "result_view", "passage_display", "section_keys",
                     "assessment_presets", "importer_profiles", "title_key"}


def err(res):
    return res.json()["error"]["code"]


def ort_course(db, owner, *, locked=True, languages=("en",)):
    return make_course(db, owner, languages=list(languages), default_language=languages[0], status="published",
                       template_key="ort", template_version=1, template_locked=locked,
                       template_settings={"language": languages[0]})


# =========================================================================== registry

def test_ort_template_wraps_todays_constants():
    assert registry.TEMPLATES == {"ort": ORT} and registry.get("ort") is ORT and registry.all() == [ORT]
    assert (ORT.key, ORT.version, ORT.title_key) == ("ort", 1, "templates.ort.title")
    assert ORT.assessment_presets == tuple(get_args(Preset)) == ("none", "ort_main", "ort_subject")
    assert set(ORT_PRESETS) <= set(ORT.assessment_presets)
    assert ORT.importer_profiles == EXAM_TYPES == ("full_main", "subject", "practice_bank")
    assert list(ORT.section_keys) == MAIN_KEYS + list(ORT_SUBJECT_KEYS)
    assert ORT.scheme_version_by_preset == seeds.PRESET_SCHEME_VERSIONS
    assert (ORT.result_view, ORT.passage_display, ORT.exam_template_keys) == ("ort", "numbered", ())
    assert ORT.lock_scope == base.ALL_LOCK_FIELDS and ORT.locks("navigation") and ORT.seed is not None
    assert ORT.allows_preset("ort_main") and ORT.allows_preset("none") and not ORT.allows_preset("x")


def test_general_template_and_lookup():
    assert registry.GENERAL is GENERAL
    assert (GENERAL.assessment_presets, GENERAL.importer_profiles, GENERAL.section_keys) == (("none",), (), ())
    assert (GENERAL.result_view, GENERAL.passage_display, GENERAL.lock_scope) == ("general", "plain", frozenset())
    assert GENERAL.exam_template_keys == () and not GENERAL.locks("navigation")
    with pytest.raises(ValidationFailed) as e:
        registry.get("nope")
    assert e.value.code == "unknown_template" and e.value.status_code == 422

    class C:
        template_key = None
        template_version = None
        template_locked = False

    assert registry.for_course(C()) is None and tpl.course_template_out(C()) is None
    C.template_key, C.template_version = "ort", 1
    assert registry.for_course(C()) is ORT
    C.template_key = "retired"  # an unknown stored key behaves as a general course
    assert registry.for_course(C()) is None


def test_service_guards_unit():
    class C:
        template_key, template_version, template_locked = "ort", 1, True

    gen = type("G", (), {"template_key": None, "template_version": None, "template_locked": False})()
    for p in ("ort_main", "ort_subject", "none"):
        tpl.assert_preset_allowed(C(), p)
    tpl.assert_preset_allowed(gen, "none")
    for p in ORT_PRESETS:
        with pytest.raises(ValidationFailed) as e:
            tpl.assert_preset_allowed(gen, p)
        assert e.value.code == "preset_not_available"
    for x in (None, *EXAM_TYPES):
        tpl.assert_import_profile_allowed(C(), x)
    tpl.assert_import_profile_allowed(gen, None)
    for x in EXAM_TYPES:
        with pytest.raises(ValidationFailed) as e:
            tpl.assert_import_profile_allowed(gen, x)
        assert e.value.code == "import_profile_not_available"
    for f in base.ALL_LOCK_FIELDS:
        with pytest.raises(Conflict) as e:
            tpl.assert_not_locked(C(), f, preset="ort_main", actor_id="usr_x")
        assert e.value.code == "template_locked" and e.value.status_code == 409
        tpl.assert_not_locked(C(), f, preset="none", actor_id="usr_x")      # free assessment
        tpl.assert_not_locked(C(), f, preset="ort_main", actor_id=DEMO_TEACHER_ID)  # the ORT seed
        tpl.assert_not_locked(gen, f, preset="ort_main", actor_id="usr_x")
    C.template_locked = False
    tpl.assert_not_locked(C(), "navigation", preset="ort_main", actor_id="usr_x")


# =========================================================================== ORT course (seeded)

async def test_seeded_ort_course_has_todays_options(db, api):
    ensure_ort_courses(db, samples=False)
    db.expire_all()
    for lang in ("ky", "ru"):
        c = db.get(Course, course_id_for(lang))
        assert (c.template_key, c.template_version, c.template_locked) == ("ort", 1, True)
        assert c.organization_id == platform_org_id() and c.template_settings == {"language": lang}
    course = db.get(Course, course_id_for("ky"))
    t = make_user(db, teacher_status="approved")
    s = make_user(db)
    enroll(db, course, t, "teacher", source="staff_add")
    enroll(db, course, s, "student")
    for user in (t, s):
        res = await api.call(user, "GET", f"/courses/{course.id}")
        assert res.status_code == 200, res.text
        out = res.json()["template"]
        assert set(out) == TEMPLATE_OUT_KEYS
        assert out == {
            "key": "ort", "version": 1, "locked": True, "result_view": "ort", "passage_display": "numbered",
            "section_keys": MAIN_KEYS + list(ORT_SUBJECT_KEYS), "assessment_presets": ["none", "ort_main",
                                                                                     "ort_subject"],
            "importer_profiles": ["full_main", "subject", "practice_bank"], "title_key": "templates.ort.title",
        }
    # every preset of today is still available in the ORT course
    cid = str(course.id)
    main = await mk(api, t, cid, preset="ort_main", languages=["ky"])
    assert [x["key"] for x in main["sections"]] == MAIN_KEYS
    assert main["grading_scheme_version_id"] == str(seeds.ORT_MAIN_V1_ID)
    subj = await mk(api, t, cid, preset="ort_subject", subject_key="chemistry", languages=["ky"])
    assert [x["key"] for x in subj["sections"]] == ["chemistry"]
    assert (await mk(api, t, cid, languages=["ky"]))["preset"] == "none"
    # locked: structure edits of the ORT exam are refused
    res = await api.call(t, "POST", f"/courses/{cid}/assessments/{main['id']}/sections", json={"key": "extra"})
    assert res.status_code == 409 and err(res) == "template_locked", res.text


async def test_ort_course_import_profiles_accepted(db, api):
    w = world(db, languages=("ru", "ky", "en"))
    w.course.template_key, w.course.template_version, w.course.template_locked = "ort", 1, True
    db.commit()
    for exam_type in EXAM_TYPES:
        res = await imp(w.O, w.cid, zbytes(), commit=False, exam_type=exam_type)
        assert res.status_code == 200, (exam_type, res.text)
    assert (await imp(w.O, w.cid, zbytes(), commit=False)).status_code == 200  # plain import stays


# =========================================================================== general course

async def test_general_course_has_no_ort_options(db, api):
    w = world(db, languages=("ru", "ky", "en"))
    res = await api.call(w.O, "GET", f"/courses/{w.cid}")
    assert res.status_code == 200 and res.json()["template"] is None
    res = await api.call(w.S, "GET", f"/courses/{w.cid}")
    assert res.status_code == 200 and res.json()["template"] is None
    for body in ({"preset": "ort_main"}, {"preset": "ort_subject", "subject_key": "chemistry"}):
        res = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments",
                             json={"title": {"en": "x"}, "languages": ["en"], **body})
        assert res.status_code == 422 and err(res) == "preset_not_available", res.text
    a = await mk(api, w.O, w.cid)
    assert a["preset"] == "none" and a["sections"] == []
    # free structure: sections, navigation and scheme stay editable in a general course
    s = await section(api, w.O, w.cid, a["id"], key="anything", time_limit_s=600)
    res = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}",
                         json={"time_limit_s": 900})
    assert res.status_code == 200, res.text
    # importer: no ORT format, plain import only
    for exam_type in EXAM_TYPES:
        for commit in (False, True):
            res = await imp(w.O, w.cid, zbytes(), commit=commit, exam_type=exam_type)
            assert res.status_code == 422 and err(res) == "import_profile_not_available", res.text
    res = await imp(w.O, w.cid, zbytes(), commit=False)
    assert res.status_code == 200 and res.json()["ok"], res.text


async def test_existing_ort_assessment_in_general_course_untouched(db, api):
    """A15: the guard only applies to new assessments; an old ORT exam in a plain course keeps working."""
    w = world(db)
    w.course.template_key, w.course.template_version = "ort", 1
    db.commit()
    a = await mk(api, w.O, w.cid, preset="ort_main")
    w.course.template_key = w.course.template_version = None
    db.commit()
    res = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}",
                         json={"draft_rev": a["draft_rev"], "navigation": "free"})
    assert res.status_code == 200 and res.json()["preset"] == "ort_main", res.text


# =========================================================================== locked ORT course (5.4)

async def _locked_exam(db, api):
    owner = make_user(db, teacher_status="approved")
    course = ort_course(db, owner)
    cid = str(course.id)
    a = await mk(api, owner, cid, preset="ort_main")
    return owner, course, cid, a


async def test_locked_fields_refused(db, api):
    owner, course, cid, a = await _locked_exam(db, api)
    aid = a["id"]
    secs = a["sections"]
    base_url = f"/courses/{cid}/assessments/{aid}"

    def locked(res):
        assert res.status_code == 409 and err(res) == "template_locked", res.text

    locked(await api.call(owner, "POST", f"{base_url}/sections", json={"key": "extra", "time_limit_s": 600}))
    locked(await api.call(owner, "DELETE", f"{base_url}/sections/{secs[-1]['id']}"))
    locked(await api.call(owner, "PUT", f"{base_url}/sections/order",
                          json={"section_ids": [x["id"] for x in reversed(secs)]}))
    locked(await api.call(owner, "PATCH", f"{base_url}/sections/{secs[0]['id']}", json={"time_limit_s": 600}))
    locked(await api.call(owner, "PATCH", f"{base_url}/sections/{secs[0]['id']}", json={"time_limit_s": None}))
    locked(await api.call(owner, "PATCH", f"{base_url}/sections/{secs[0]['id']}",
                          json={"rules": {"max_items": 5}}))
    locked(await api.call(owner, "PATCH", f"{base_url}/sections/{secs[3]['id']}",
                          json={"rules": {"allow_passages": False}}))
    # the ORT rule lock that existed before still answers first for keys and question types (unchanged)
    res = await api.call(owner, "PATCH", f"{base_url}/sections/{secs[0]['id']}", json={"key": "grammar"})
    assert res.status_code == 422 and err(res) == "preset_rule_locked"
    rev = a["draft_rev"]
    locked(await api.call(owner, "PATCH", base_url, json={"draft_rev": rev, "navigation": "free"}))
    locked(await api.call(owner, "PATCH", base_url, json={"draft_rev": rev, "grading_scheme_version_id": None}))
    locked(await api.call(owner, "PATCH", base_url,
                          json={"draft_rev": rev, "grading_scheme_version_id": str(seeds.ORT_SUBJECT_V1_ID)}))
    # the preset is not an update field at all (schema forbids it)
    res = await api.call(owner, "PATCH", base_url, json={"draft_rev": rev, "preset": "none"})
    assert res.status_code == 422
    after = (await api.call(owner, "GET", base_url)).json()
    assert after["preset"] == "ort_main" and after["navigation"] == "section_forward_only"
    assert after["draft_rev"] == rev and after["grading_scheme_version_id"] == str(seeds.ORT_MAIN_V1_ID)
    assert [(x["key"], x["time_limit_s"], x["rules"]) for x in after["sections"]] == \
        [(x["key"], x["time_limit_s"], x["rules"]) for x in secs]


async def test_editable_fields_still_work(db, api):
    owner, course, cid, a = await _locked_exam(db, api)
    aid = a["id"]
    secs = a["sections"]
    base_url = f"/courses/{cid}/assessments/{aid}"
    res = await api.call(owner, "PATCH", base_url, json={
        "draft_rev": a["draft_rev"], "title": {"en": "Renamed"}, "description": {"en": "d"},
        "available_from": "2030-01-01T08:00:00Z", "available_until": "2030-01-02T08:00:00Z",
        "due_at": "2030-01-02T08:00:00Z", "allowed_attempts": 3, "score_policy": "latest",
        "results_policy": "never", "show_correct_answers": False, "shuffle_items": True, "shuffle_choices": True,
        "grade_release": "manual", "omit_from_total": True,
        # unchanged locked values are fine (a form may send them back)
        "navigation": "section_forward_only", "grading_scheme_version_id": str(seeds.ORT_MAIN_V1_ID),
    })
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["title"] == {"en": "Renamed"} and out["allowed_attempts"] == 3 and out["score_policy"] == "latest"
    # section title / instructions, with the unchanged time limit and rules sent back
    res = await api.call(owner, "PATCH", f"{base_url}/sections/{secs[0]['id']}", json={
        "title": {"en": "Math"}, "instructions": {"en": "Compare"}, "time_limit_s": secs[0]["time_limit_s"],
        "key": secs[0]["key"], "rules": secs[0]["rules"]})
    assert res.status_code == 200, res.text
    assert res.json()["title"] == {"en": "Math"}
    # same order is not a reorder
    res = await api.call(owner, "PUT", f"{base_url}/sections/order", json={"section_ids": [x["id"] for x in secs]})
    assert res.status_code == 200, res.text
    # questions, pick items and their points
    bank = make_bank(db, course, owner)
    q_cmp, q_sc = cmp_q(db, bank, owner), sc(db, bank, owner)
    sc(db, bank, owner, stem="pool 2")
    res = await api.call(owner, "POST", f"{base_url}/sections/{secs[0]['id']}/items",
                         json={"kind": "question", "question_id": str(q_cmp.id)})
    assert res.status_code == 201, res.text
    item = res.json()[0]
    res = await api.call(owner, "PATCH", f"{base_url}/items/{item['id']}", json={"points": "2"})
    assert res.status_code == 200, res.text
    res = await api.call(owner, "POST", f"{base_url}/sections/{secs[1]['id']}/items",
                         json={"kind": "pick", "points": "1", "pick": {"bank_id": str(bank.id), "count": 1}})
    assert res.status_code == 201, res.text
    pick = res.json()[0]
    res = await api.call(owner, "PATCH", f"{base_url}/items/{pick['id']}", json={"points": "3"})
    assert res.status_code == 200, res.text
    res = await api.call(owner, "POST", f"{base_url}/sections/{secs[1]['id']}/items",
                         json={"kind": "question", "question_id": str(q_sc.id)})
    assert res.status_code == 201, res.text
    res = await api.call(owner, "DELETE", f"{base_url}/items/{res.json()[0]['id']}")
    assert res.status_code == 204, res.text
    # course settings stay editable
    res = await api.call(owner, "PATCH", f"/courses/{cid}", json={"title": {"en": "ORT group"}})
    assert res.status_code == 200, res.text


async def test_free_assessment_in_locked_course_not_locked(db, api):
    owner = make_user(db, teacher_status="approved")
    cid = str(ort_course(db, owner).id)
    a = await mk(api, owner, cid)
    s = await section(api, owner, cid, a["id"], key="part", time_limit_s=600)
    res = await api.call(owner, "PATCH", f"/courses/{cid}/assessments/{a['id']}/sections/{s['id']}",
                         json={"time_limit_s": 1200})
    assert res.status_code == 200, res.text


async def test_unlocked_ort_course_allows_structure_edits(db, api):
    owner = make_user(db, teacher_status="approved")
    cid = str(ort_course(db, owner, locked=False).id)
    a = await mk(api, owner, cid, preset="ort_main")
    res = await api.call(owner, "PATCH", f"/courses/{cid}/assessments/{a['id']}/sections/{a['sections'][0]['id']}",
                         json={"time_limit_s": 600})
    assert res.status_code == 200, res.text


# =========================================================================== platform admin unlock

async def test_platform_admin_unlocks_and_relocks_audited(db, api):
    owner, course, cid, a = await _locked_exam(db, api)
    admin = make_user(db, platform_admin=True)
    url = f"/platform/courses/{cid}"
    res = await api.call(owner, "PATCH", url, json={"template_locked": False})
    assert res.status_code == 403
    res = await api.call(admin, "PATCH", url, json={"template_locked": False, "reason": "custom ORT group"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert (out["template_key"], out["template_version"], out["template_locked"]) == ("ort", 1, False)
    assert out["template"]["locked"] is False and set(out["template"]) == TEMPLATE_OUT_KEYS
    db.expire_all()
    assert db.get(Course, course.id).template_locked is False
    # structure edits now work
    res = await api.call(owner, "PATCH", f"/courses/{cid}/assessments/{a['id']}/sections/{a['sections'][0]['id']}",
                         json={"time_limit_s": 600})
    assert res.status_code == 200, res.text
    # unchanged value: no-op, no audit row
    assert (await api.call(admin, "PATCH", url, json={"template_locked": False})).status_code == 200
    res = await api.call(admin, "PATCH", url, json={"template_locked": True})
    assert res.status_code == 200 and res.json()["template_locked"] is True
    rows = db.scalars(select(AdminAuditLog).where(AdminAuditLog.target_type == "course",
                                                  AdminAuditLog.target_id == cid)
                      .order_by(AdminAuditLog.created_at, AdminAuditLog.id)).all()
    assert [(r.action, r.actor_id) for r in rows] == [("course.template_unlock", admin.id),
                                                      ("course.template_lock", admin.id)]
    assert rows[0].reason == "custom ORT group"
    assert rows[0].details == {"template_key": "ort", "from": True, "to": False}
    # extra fields refused; a general course has nothing to lock; unknown course 404
    assert (await api.call(admin, "PATCH", url, json={"template_locked": True, "title": "x"})).status_code == 422
    general = make_course(db, owner)
    res = await api.call(admin, "PATCH", f"/platform/courses/{general.id}", json={"template_locked": True})
    assert res.status_code == 422 and err(res) == "no_template"
    res = await api.call(admin, "PATCH", f"/platform/courses/{uuid.uuid4()}", json={"template_locked": True})
    assert res.status_code == 404


async def test_course_cannot_unlock_itself(db, api):
    owner, course, cid, a = await _locked_exam(db, api)
    res = await api.call(owner, "PATCH", f"/courses/{cid}", json={"template_locked": False})
    assert res.status_code == 422
    db.expire_all()
    assert db.get(Course, course.id).template_locked is True


# =========================================================================== GET /courses/templates

def _org(db, *, teachers_can_create=True, status="active"):
    org = Organization(slug=f"org-{uuid.uuid4().hex[:10]}", name="School", status=status,
                       settings={"teachers_can_create_courses": teachers_can_create})
    db.add(org)
    db.commit()
    return org


def _member(db, org, user, role):
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=role, state="active"))
    db.commit()


async def test_course_templates_grant_rules(db, api):
    org = _org(db)
    oa, t, x = make_user(db), make_user(db, teacher_status="approved"), make_user(db, teacher_status="approved")
    admin = make_user(db, platform_admin=True)
    _member(db, org, oa, "org_admin")
    _member(db, org, t, "teacher")

    async def listing(user, oid=None):
        return await api.call(user, "GET", "/courses/templates", params={"organization_id": str(oid or org.id)})

    for user in (oa, t, admin):  # no grant -> empty
        res = await listing(user)
        assert res.status_code == 200 and res.json() == [], res.text
    grant = OrganizationTemplateGrant(organization_id=org.id, template_key="ort", granted_by_id=admin.id)
    db.add(grant)
    db.add(OrganizationTemplateGrant(organization_id=org.id, template_key="retired_kind", granted_by_id=admin.id))
    db.commit()
    for user in (oa, t, admin):
        res = await listing(user)
        assert res.status_code == 200 and res.json() == [{"key": "ort", "title_key": "templates.ort.title"}]
    assert [g.key for g in tpl.granted_templates(db, org.id)] == ["ort"]
    # outsiders, anonymous and a missing organization
    res = await listing(x)
    assert res.status_code == 403
    assert (await listing(None)).status_code == 401
    assert (await listing(x, uuid.uuid4())).status_code == 403
    assert (await listing(admin, uuid.uuid4())).status_code == 404
    assert (await api.call(t, "GET", "/courses/templates")).status_code == 422
    # revoked grant -> empty again
    from app.lms.core.models import utcnow

    grant.revoked_at, grant.revoked_by_id = utcnow(), admin.id
    db.commit()
    for user in (oa, t, admin):
        res = await listing(user)
        assert res.status_code == 200 and res.json() == []


async def test_course_templates_creator_rules(db, api):
    org = _org(db, teachers_can_create=False)
    oa, t = make_user(db), make_user(db, teacher_status="approved")
    _member(db, org, oa, "org_admin")
    _member(db, org, t, "teacher")
    db.add(OrganizationTemplateGrant(organization_id=org.id, template_key="ort"))
    db.commit()
    params = {"organization_id": str(org.id)}
    assert (await api.call(oa, "GET", "/courses/templates", params=params)).status_code == 200
    assert (await api.call(t, "GET", "/courses/templates", params=params)).status_code == 403
    # removed membership and suspended organization
    m = db.scalars(select(OrganizationMember).where(OrganizationMember.user_id == oa.id)).one()
    m.state = "removed"
    db.commit()
    assert (await api.call(oa, "GET", "/courses/templates", params=params)).status_code == 403
    org2 = _org(db, status="suspended")
    _member(db, org2, t, "org_admin")
    res = await api.call(t, "GET", "/courses/templates", params={"organization_id": str(org2.id)})
    assert res.status_code == 403
