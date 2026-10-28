"""Phase 7b S2 structure locks (PHASE_7B_DESIGN 5.4): locked field x action -> 409 `template_locked` with
`source = exam_template`, editable fields -> 200, unlock later does not propagate, lock later does not lock existing
drafts, `structure-unlock` authorization and audit. ORT preset exams are untouched (their guard is the 6a branch)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.lms.assessments.models import Assessment
from app.lms.audit.models import AdminAuditLog
from app.lms.exam_templates import ids
from app.lms.grading.seeds import ORT_MAIN_V1_ID
from app.lms.templates import base as tpl_fields
from tests.lms.assessment_support import bank_of
from tests.lms.exam_template_support import general_spec
from tests.lms.factories import enroll
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_templates_api import T, create_from, err, published_template, tworld

LOCKED_SPEC = general_spec(scoring={"grading_scheme_version_id": str(ORT_MAIN_V1_ID)},
                           lock_scope=list(ids.LOCK_SCOPE_KEYS))


async def _locked_world(api, db, *, owner="PA", scope="platform", lock_scope=None):
    w = tworld(db)
    spec = general_spec(scoring={"grading_scheme_version_id": str(ORT_MAIN_V1_ID)},
                        lock_scope=list(ids.LOCK_SCOPE_KEYS) if lock_scope is None else lock_scope)
    kw = {} if scope == "platform" else {"organization_id": w.org.id}
    t = await published_template(api, getattr(w, owner), owner_scope=scope, spec=spec, **kw)
    assert (await api.call(getattr(w, owner), "POST", f"{T}/{t['id']}/lock")).status_code == 200
    a = await create_from(api, w.TA, w.cid, t["id"])
    assert a["structure_locked"] is True
    return w, t, a


def _p(w, a, tail=""):
    return f"/courses/{w.cid}/assessments/{a['id']}{tail}"


async def test_lock_matrix(db, api):
    w, t, a = await _locked_world(api, db)
    s1, s2 = a["sections"]
    assert set(a["exam_template"]["locked_fields"]) == (  # Phase 8a: course-level locks are not exam fields
        set(tpl_fields.ALL_LOCK_FIELDS) - {tpl_fields.LOCK_PRESET} - tpl_fields.COURSE_LEVEL_LOCK_FIELDS)
    locked = [
        ("POST", _p(w, a, "/sections"), {"title": {"en": "C"}}, tpl_fields.LOCK_SECTION_ADD_REMOVE),
        ("DELETE", _p(w, a, f"/sections/{s2['id']}"), None, tpl_fields.LOCK_SECTION_ADD_REMOVE),
        ("PUT", _p(w, a, "/sections/order"), {"section_ids": [s2["id"], s1["id"]]}, tpl_fields.LOCK_SECTION_ORDER),
        ("PATCH", _p(w, a, f"/sections/{s1['id']}"), {"key": "renamed"}, tpl_fields.LOCK_SECTION_KEY),
        ("PATCH", _p(w, a, f"/sections/{s1['id']}"), {"time_limit_s": 600}, tpl_fields.LOCK_SECTION_TIME_LIMIT),
        ("PATCH", _p(w, a, f"/sections/{s1['id']}"), {"rules": {"allowed_types": ["essay"]}},
         tpl_fields.LOCK_SECTION_RULES),
        ("PATCH", _p(w, a), {"draft_rev": a["draft_rev"], "navigation": "section_forward_only"},
         tpl_fields.LOCK_NAVIGATION),
        ("PATCH", _p(w, a), {"draft_rev": a["draft_rev"], "grading_scheme_version_id": None},
         tpl_fields.LOCK_SCHEME_VERSION),
    ]
    for method, path, body, field in locked:
        res = await api.call(w.TA, method, path, json=body)
        assert res.status_code == 409 and err(res) == "template_locked", (method, path, res.text)
        assert res.json()["error"]["details"] == {"field": field, "source": "exam_template"}
    # unchanged values and editable fields pass (6a 5.4 editable list)
    same = await api.call(w.TA, "PATCH", _p(w, a, f"/sections/{s1['id']}"), json={
        "key": s1["key"], "time_limit_s": s1["time_limit_s"], "rules": s1["rules"], "title": {"en": "Renamed title"}})
    assert same.status_code == 200 and same.json()["title"] == {"en": "Renamed title"}
    assert (await api.call(w.TA, "PUT", _p(w, a, "/sections/order"),
                           json={"section_ids": [s1["id"], s2["id"]]})).status_code == 200
    rev = (await api.call(w.TA, "GET", _p(w, a))).json()["draft_rev"]
    ok = await api.call(w.TA, "PATCH", _p(w, a), json={
        "draft_rev": rev, "title": {"en": "New title"}, "allowed_attempts": 5, "score_policy": "latest",
        "results_policy": "after_submit", "show_correct_answers": True, "shuffle_items": True, "time_limit_s": 7200,
        "grading_scheme_version_id": str(ORT_MAIN_V1_ID), "grade_release": "manual", "omit_from_total": True,
        "access_code": "secret-1"})
    assert ok.status_code == 200, ok.text
    bank, qs = bank_of(db, w.course, w.TA, 2)
    add = await api.call(w.TA, "POST", _p(w, a, f"/sections/{s1['id']}/items"),
                         json={"kind": "question", "question_id": str(qs[0].id)})
    assert add.status_code == 201, add.text
    # a template exam in an ORT-template course: the ORT (6a) branch does not apply to preset 'none' exams
    assert db.get(Assessment, uuid.UUID(a["id"])).preset == "none"


async def test_partial_lock_scope(db, api):
    w, t, a = await _locked_world(api, db, lock_scope=["navigation"])
    assert a["exam_template"]["locked_fields"] == [tpl_fields.LOCK_NAVIGATION]
    res = await api.call(w.TA, "PATCH", _p(w, a), json={"draft_rev": a["draft_rev"], "navigation": "section_forward_only"})
    assert res.status_code == 409 and err(res) == "template_locked"
    assert (await api.call(w.TA, "POST", _p(w, a, "/sections"), json={"title": {"en": "C"}})).status_code == 201
    rev = (await api.call(w.TA, "GET", _p(w, a))).json()["draft_rev"]
    res = await api.call(w.TA, "PATCH", _p(w, a), json={"draft_rev": rev, "grading_scheme_version_id": None})
    assert res.status_code == 200, res.text


async def test_template_lock_changes_never_propagate(db, api):
    w, t, a = await _locked_world(api, db)
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/unlock")).status_code == 200
    res = await api.call(w.TA, "POST", _p(w, a, "/sections"), json={"title": {"en": "C"}})
    assert res.status_code == 409 and err(res) == "template_locked"                 # still locked (3.3)
    b = await create_from(api, w.TA, w.cid, t["id"])
    assert b["structure_locked"] is False and b["exam_template"]["locked_fields"] == []
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/lock")).status_code == 200
    res = await api.call(w.TA, "POST", _p(w, b, "/sections"), json={"title": {"en": "C"}})
    assert res.status_code == 201                                                     # a later lock leaves drafts


async def test_structure_unlock_authorization_and_audit(db, api):
    # platform template: only the platform admin may unlock, and the platform admin is not course staff
    w, t, a = await _locked_world(api, db)
    res = await api.call(w.TA, "POST", _p(w, a, "/structure-unlock"), json={"reason": "please"})
    assert res.status_code == 403 and err(res) == "scope_not_allowed"
    assert (await api.call(w.AS, "POST", _p(w, a, "/structure-unlock"))).status_code == 403
    assert (await api.call(w.S, "POST", _p(w, a, "/structure-unlock"))).status_code == 403
    assert (await api.call(w.PA, "POST", _p(w, a, "/structure-unlock"))).status_code == 404  # not course staff
    enroll(db, w.course, w.PA, "teacher", source="staff_add")
    res = await api.call(w.PA, "POST", _p(w, a, "/structure-unlock"), json={"reason": "exception"})
    assert res.status_code == 200 and res.json()["structure_locked"] is False, res.text
    assert res.json()["exam_template"]["locked_fields"] == []
    rows = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == ids.AUDIT_STRUCTURE_UNLOCK)).scalars().all()
    assert len(rows) == 1 and rows[0].target_type == "assessment" and rows[0].target_id == a["id"]
    assert rows[0].reason == "exception" and rows[0].details["template_id"] == t["id"]
    assert (await api.call(w.PA, "POST", _p(w, a, "/structure-unlock"))).status_code == 200      # idempotent
    assert len(db.execute(select(AdminAuditLog).where(AdminAuditLog.action == ids.AUDIT_STRUCTURE_UNLOCK))
               .scalars().all()) == 1
    assert (await api.call(w.TA, "POST", _p(w, a, "/sections"), json={"title": {"en": "C"}})).status_code == 201
    # not a template assessment
    plain = await api.call(w.TA, "POST", f"/courses/{w.cid}/assessments",
                           json={"title": {"en": "P"}, "preset": "none", "languages": ["en"]})
    res = await api.call(w.TA, "POST", _p(w, plain.json(), "/structure-unlock"))
    assert res.status_code == 422 and err(res) == "not_a_template_assessment"


async def test_structure_unlock_by_teacher_owner_and_org_admin(db, api):
    # teacher template: its owner (course teacher) unlocks; the assistant cannot
    w, t, a = await _locked_world(api, db, owner="TA", scope="teacher")
    assert (await api.call(w.AS, "POST", _p(w, a, "/structure-unlock"))).status_code == 403
    res = await api.call(w.TA, "POST", _p(w, a, "/structure-unlock"))
    assert res.status_code == 200 and res.json()["structure_locked"] is False
    # organization template: the org admin after join-as-teacher (A13); plain course staff cannot
    w2, t2, a2 = await _locked_world(api, db, owner="OA", scope="organization")
    assert err(await api.call(w2.TA, "POST", _p(w2, a2, "/structure-unlock"))) == "scope_not_allowed"
    assert (await api.call(w2.OA, "POST", _p(w2, a2, "/structure-unlock"))).status_code == 403  # no content.manage
    enroll(db, w2.course, w2.OA, "teacher", source="staff_add")
    assert (await api.call(w2.OA, "POST", _p(w2, a2, "/structure-unlock"))).status_code == 200


@pytest.mark.parametrize("field", sorted(ids.LOCK_SCOPE_MAP))
def test_lock_scope_map_covers_course_template_fields(field):
    assert ids.LOCK_SCOPE_MAP[field] <= tpl_fields.ALL_LOCK_FIELDS
