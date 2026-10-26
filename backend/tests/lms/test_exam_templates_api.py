"""Phase 7b S2: exam template CRUD, drafts, publish (immutable versions), archive, lock / unlock / promote (audited),
list modes and the serializer contract (PHASE_7B_DESIGN 5.1, 7, 9.1, 11). The world helpers here are shared by the
other S2 test files."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.lms.assessments.models import Assessment
from app.lms.audit.models import AdminAuditLog
from app.lms.content.types import TYPE_NAMES
from app.lms.exam_templates import ids
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion, ImmutableExamTemplateVersionError
from app.lms.exam_templates.schemas import MANAGE_ONLY_KEYS, PICKER_KEYS
from app.lms.grading.seeds import ORT_MAIN_V1_ID
from tests.lms.exam_template_support import general_spec, make_template, publish_version
from tests.lms.factories import enroll, make_course, make_scheme, make_user
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

T = "/exam-templates"


def err(res):
    return res.json()["error"]["code"]


def tworld(db, *, teachers_can_publish: bool = False):
    """Organization `org` (admin OA; teachers TA, TB), course C in org owned by TA with assistant AS and student S;
    platform admin PA; outsider X; a second organization `org2` with teacher TC and course C2."""
    org = make_org(db, "Lyceum")
    if teachers_can_publish:
        org.settings = {**(org.settings or {}), "teachers_can_publish_org_templates": True}
        db.commit()
    OA, TA, TB = make_user(db), make_user(db, teacher_status="approved"), make_user(db, teacher_status="approved")
    add_member(db, org, OA, "org_admin")
    add_member(db, org, TA, "teacher")
    add_member(db, org, TB, "teacher")
    course = make_course(db, TA, organization_id=org.id, status="published", languages=["en", "ru"])
    AS, S, X = make_user(db), make_user(db), make_user(db)
    enroll(db, course, AS, "assistant", source="staff_add")
    enroll(db, course, S, "student")
    PA = make_user(db, platform_admin=True)
    org2 = make_org(db, "Gymnasium")
    TC = make_user(db, teacher_status="approved")
    add_member(db, org2, TC, "teacher")
    course2 = make_course(db, TC, organization_id=org2.id, status="published", languages=["en"])
    return SimpleNamespace(org=org, OA=OA, TA=TA, TB=TB, AS=AS, S=S, X=X, PA=PA, course=course, cid=str(course.id),
                           org2=org2, TC=TC, course2=course2, cid2=str(course2.id))


async def create_t(api, user, *, owner_scope="platform", organization_id=None, title=None, spec=None, **extra):
    body = {"owner_scope": owner_scope, "title": title or {"en": "Template"}, **extra}
    if organization_id is not None:
        body["organization_id"] = str(organization_id)
    if spec is not None:
        body["draft_spec"] = spec
    return await api.call(user, "POST", T, json=body)


async def publish_t(api, user, tid):
    return await api.call(user, "POST", f"{T}/{tid}/publish")


async def published_template(api, user, *, owner_scope="platform", organization_id=None, spec=None, title=None,
                             **extra) -> dict:
    res = await create_t(api, user, owner_scope=owner_scope, organization_id=organization_id, title=title,
                         spec=spec or general_spec(), **extra)
    assert res.status_code == 201, res.text
    pub = await publish_t(api, user, res.json()["id"])
    assert pub.status_code == 200, pub.text
    return pub.json()["template"]


async def create_from(api, user, cid, tid=None, *, version_id=None, parameters=None, status=201, **body):
    body.setdefault("title", {"en": "From template"})
    body.setdefault("languages", ["en"])
    if tid is not None:
        body["exam_template_id"] = str(tid)
    if version_id is not None:
        body["exam_template_version_id"] = str(version_id)
    if parameters is not None:
        body["parameters"] = parameters
    res = await api.call(user, "POST", f"/courses/{cid}/assessments", json=body)
    assert res.status_code == status, res.text
    return res.json()


def audit_rows(db, action, target_id=None):
    stmt = select(AdminAuditLog).where(AdminAuditLog.action == action)
    if target_id is not None:
        stmt = stmt.where(AdminAuditLog.target_id == str(target_id))
    return list(db.execute(stmt.order_by(AdminAuditLog.created_at)).scalars())


# =========================================================================== drafts, publish, versions

async def test_create_patch_publish_versions(db, api):
    w = tworld(db)
    res = await create_t(api, w.PA, spec=general_spec())
    assert res.status_code == 201, res.text
    t = res.json()
    assert (t["status"], t["draft_rev"], t["owner_scope"], t["locked"]) == ("draft", 1, "platform", False)
    assert t["draft_spec"]["sections"][0]["key"] == "part_a" and t["current_version_id"] is None
    tid = t["id"]

    conflict = await api.call(w.PA, "PATCH", f"{T}/{tid}", json={"draft_rev": 7, "title": {"en": "X"}})
    assert conflict.status_code == 409 and err(conflict) == "draft_conflict"
    assert conflict.json()["error"]["details"] == {"draft_rev": 1}
    bad = await api.call(w.PA, "PATCH", f"{T}/{tid}", json={"draft_rev": 1, "draft_spec": general_spec(sections=[])})
    assert bad.status_code == 422 and err(bad) == "spec_invalid"
    bad = await api.call(w.PA, "PATCH", f"{T}/{tid}", json={"draft_rev": 1, "draft_spec": general_spec(
        importer_profile="ort")})
    assert bad.status_code == 422 and err(bad) == "importer_profile_reserved"
    ok = await api.call(w.PA, "PATCH", f"{T}/{tid}", json={"draft_rev": 1, "title": {"en": "Midterm"},
                                                           "description": {"en": "Two parts"}})
    assert ok.status_code == 200 and ok.json()["draft_rev"] == 2 and ok.json()["title"] == {"en": "Midterm"}

    pub = await publish_t(api, w.PA, tid)
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert body["unchanged"] is False and body["version"]["version_no"] == 1
    assert body["version"]["spec"]["sections"][1]["key"] == "part_b" and body["version"]["spec"]["schema"] == 1
    assert body["template"]["status"] == "published" and body["template"]["draft_spec"] is None
    assert body["template"]["current_version_id"] == body["version"]["id"] and body["template"]["draft_rev"] == 3
    rows = audit_rows(db, ids.AUDIT_PUBLISH, tid)
    assert len(rows) == 1 and rows[0].actor_id == w.PA.id and rows[0].target_type == "exam_template"
    assert rows[0].details == {"version_no": 1, "version_id": body["version"]["id"]}

    nothing = await publish_t(api, w.PA, tid)
    assert nothing.status_code == 422 and err(nothing) == "nothing_to_publish"

    # an identical draft publishes nothing (D9)
    same = await api.call(w.PA, "PATCH", f"{T}/{tid}", json={"draft_rev": 3, "draft_spec": general_spec()})
    assert same.status_code == 200
    pub2 = await publish_t(api, w.PA, tid)
    assert pub2.status_code == 200 and pub2.json()["unchanged"] is True
    assert pub2.json()["version"]["version_no"] == 1 and pub2.json()["template"]["draft_spec"] is None
    assert len(audit_rows(db, ids.AUDIT_PUBLISH, tid)) == 1

    changed = await api.call(w.PA, "PATCH", f"{T}/{tid}", json={
        "draft_rev": pub2.json()["template"]["draft_rev"], "draft_spec": general_spec(navigation="section_forward_only")})
    assert changed.status_code == 200
    pub3 = await publish_t(api, w.PA, tid)
    assert pub3.status_code == 200 and pub3.json()["version"]["version_no"] == 2
    versions = await api.call(w.PA, "GET", f"{T}/{tid}/versions")
    assert versions.status_code == 200 and [v["version_no"] for v in versions.json()] == [2, 1]
    v1 = await api.call(w.PA, "GET", f"{T}/{tid}/versions/1")
    assert v1.status_code == 200 and v1.json()["spec"]["navigation"] == "free"
    assert (await api.call(w.PA, "GET", f"{T}/{tid}/versions/9")).status_code == 404
    assert len(audit_rows(db, ids.AUDIT_PUBLISH, tid)) == 2


def test_versions_are_immutable(db):
    t = make_template(db)
    v = publish_version(db, t, general_spec())
    v.spec = {**v.spec, "navigation": "section_forward_only"}
    with pytest.raises(ImmutableExamTemplateVersionError):
        db.flush()
    db.rollback()
    v = db.get(ExamTemplateVersion, v.id)
    db.delete(v)
    with pytest.raises(ImmutableExamTemplateVersionError):
        db.flush()
    db.rollback()


async def test_publish_leaves_created_assessments_untouched(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA)
    a = await create_from(api, w.TA, w.cid, t["id"])
    v1 = t["current_version_id"]
    assert a["exam_template"]["version_id"] == v1 and a["exam_template"]["version_no"] == 1
    p = await api.call(w.PA, "PATCH", f"{T}/{t['id']}", json={"draft_rev": t["draft_rev"],
                                                              "draft_spec": general_spec(result_view="ort")})
    assert p.status_code == 200
    assert (await publish_t(api, w.PA, t["id"])).json()["version"]["version_no"] == 2
    row = db.get(Assessment, uuid.UUID(a["id"]))
    assert str(row.exam_template_version_id) == v1 and row.result_view == "general"
    got = (await api.call(w.TA, "GET", f"/courses/{w.cid}/assessments/{a['id']}")).json()
    assert (got["exam_template"]["version_no"], got["exam_template"]["latest_version_no"]) == (1, 2)


async def test_archive_hides_from_pickers_and_refuses_writes(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA)
    a = await create_from(api, w.TA, w.cid, t["id"])
    picker = await api.call(w.TA, "GET", T, params={"course_id": w.cid})
    assert [x["id"] for x in picker.json()["items"]] == [t["id"]]
    arch = await api.call(w.PA, "POST", f"{T}/{t['id']}/archive", json={"reason": "superseded"})
    assert arch.status_code == 200 and arch.json()["status"] == "archived"
    rows = audit_rows(db, ids.AUDIT_ARCHIVE, t["id"])
    assert len(rows) == 1 and rows[0].reason == "superseded"
    assert (await api.call(w.TA, "GET", T, params={"course_id": w.cid})).json()["items"] == []
    await create_from(api, w.TA, w.cid, t["id"], status=409)
    for path, body in ((f"{T}/{t['id']}", {"draft_rev": arch.json()["draft_rev"], "title": {"en": "X"}}),):
        res = await api.call(w.PA, "PATCH", path, json=body)
        assert res.status_code == 409 and err(res) == "template_archived"
    assert err(await publish_t(api, w.PA, t["id"])) == "template_archived"
    assert err(await api.call(w.PA, "POST", f"{T}/{t['id']}/archive")) == "template_archived"
    # the staff member who holds an assessment from it still reads it and its versions (9.2)
    got = await api.call(w.TA, "GET", f"{T}/{t['id']}")
    assert got.status_code == 200 and got.json()["status"] == "archived" and "draft_spec" not in got.json()
    assert (await api.call(w.TA, "GET", f"{T}/{t['id']}/versions/1")).status_code == 200
    assert (await api.call(w.TC, "GET", f"{T}/{t['id']}")).status_code == 404
    assert db.get(Assessment, uuid.UUID(a["id"])).exam_template_version_id is not None


# =========================================================================== lock / unlock / promote

async def test_lock_unlock_promote_are_owner_actions_and_audited(db, api):
    w = tworld(db)
    t = await published_template(api, w.TA, owner_scope="teacher", organization_id=w.org.id)
    tid = t["id"]
    assert t["owner_user_id"] == w.TA.id and t["can_lock"] is True and t["can_promote"] is False
    # the org admin manages (patch/publish/archive) but does not lock a teacher's template (owner answer 5)
    res = await api.call(w.OA, "POST", f"{T}/{tid}/lock", json={"reason": "no"})
    assert res.status_code == 403 and err(res) == "scope_not_allowed"
    assert (await api.call(w.TB, "POST", f"{T}/{tid}/lock")).status_code == 404        # not visible to TB
    assert (await api.call(w.X, "POST", f"{T}/{tid}/lock")).status_code == 404
    res = await api.call(w.TA, "POST", f"{T}/{tid}/lock", json={"reason": "keep the structure"})
    assert res.status_code == 200 and res.json()["locked"] is True
    rows = audit_rows(db, ids.AUDIT_LOCK, tid)
    assert len(rows) == 1 and rows[0].reason == "keep the structure" and rows[0].details == {"from": False, "to": True}
    assert (await api.call(w.TA, "POST", f"{T}/{tid}/lock")).status_code == 200           # idempotent, no new row
    assert len(audit_rows(db, ids.AUDIT_LOCK, tid)) == 1
    res = await api.call(w.TA, "POST", f"{T}/{tid}/unlock")
    assert res.status_code == 200 and res.json()["locked"] is False
    assert len(audit_rows(db, ids.AUDIT_UNLOCK, tid)) == 1

    # promote: teacher -> organization by the org admin; the teacher cannot
    res = await api.call(w.TA, "POST", f"{T}/{tid}/promote")
    assert res.status_code == 403 and err(res) == "scope_not_allowed"
    got = await api.call(w.OA, "GET", f"{T}/{tid}")
    assert got.status_code == 200 and got.json()["can_promote"] is True
    res = await api.call(w.OA, "POST", f"{T}/{tid}/promote", json={"reason": "school-wide"})
    assert res.status_code == 200, res.text
    assert (res.json()["owner_scope"], res.json()["owner_user_id"]) == ("organization", None)
    assert res.json()["organization_id"] == str(w.org.id) and res.json()["current_version_no"] == 1
    rows = audit_rows(db, ids.AUDIT_PROMOTE, tid)
    assert len(rows) == 1 and rows[0].details["former_owner_user_id"] == w.TA.id and rows[0].reason == "school-wide"
    assert err(await api.call(w.OA, "POST", f"{T}/{tid}/promote")) == "scope_not_allowed"  # already organization
    # now the org admin owns it: locks it, and the former owner no longer manages it (but still uses it)
    assert (await api.call(w.OA, "POST", f"{T}/{tid}/lock")).status_code == 200
    res = await api.call(w.TA, "PATCH", f"{T}/{tid}", json={"draft_rev": 1, "title": {"en": "X"}})
    assert res.status_code == 403 and err(res) == "scope_not_allowed"
    assert (await api.call(w.TA, "GET", T, params={"course_id": w.cid})).json()["items"][0]["id"] == tid
    assert (await api.call(w.TB, "GET", f"{T}/{tid}")).status_code == 200  # org member reads it now


async def test_promote_refuses_private_scheme(db, api):
    w = tworld(db)
    own = make_scheme(db, w.TA)
    spec = general_spec(scoring={"grading_scheme_version_id": str(own.current_version_id)})
    t = await published_template(api, w.TA, owner_scope="teacher", organization_id=w.org.id, spec=spec)
    res = await api.call(w.OA, "POST", f"{T}/{t['id']}/promote")
    assert res.status_code == 422 and err(res) == "scheme_not_shareable"
    assert db.get(ExamTemplate, uuid.UUID(t["id"])).owner_scope == "teacher"
    # the same spec is refused outright for organization and platform templates (P7B-2)
    res = await create_t(api, w.OA, owner_scope="organization", organization_id=w.org.id, spec=spec)
    assert res.status_code == 422 and err(res) == "scheme_not_shareable"
    res = await create_t(api, w.PA, spec=general_spec(scoring={"grading_scheme_version_id": str(ORT_MAIN_V1_ID)}))
    assert res.status_code == 201


# =========================================================================== lists, serializer contract, blocks

async def test_list_modes_and_payload_contract(db, api):
    w = tworld(db)
    plat = await published_template(api, w.PA, title={"en": "Platform"})
    org_t = await published_template(api, w.OA, owner_scope="organization", organization_id=w.org.id,
                                     title={"en": "Org"})
    mine = await published_template(api, w.TA, owner_scope="teacher", organization_id=w.org.id, title={"en": "Mine"})
    draft = (await create_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id, title={"en": "Draft"})).json()
    # picker mode: published only, visible in the course; payload = structure only
    pick = await api.call(w.TA, "GET", T, params={"course_id": w.cid})
    assert pick.status_code == 200
    items = pick.json()["items"]
    assert {x["id"] for x in items} == {plat["id"], org_t["id"], mine["id"]}
    for x in items:
        assert set(x) == set(PICKER_KEYS) and not (set(x) & MANAGE_ONLY_KEYS)
        assert x["current_spec"]["sections"]
    pick = await api.call(w.TA, "GET", T, params={"course_id": w.cid, "scope": "teacher"})
    assert [x["id"] for x in pick.json()["items"]] == [mine["id"]]
    # management mode
    mine_list = await api.call(w.TA, "GET", T)
    assert {x["id"] for x in mine_list.json()["items"]} == {mine["id"], draft["id"]}
    assert all("draft_rev" in x and x["owner_user_id"] == w.TA.id for x in mine_list.json()["items"])
    oa_list = await api.call(w.OA, "GET", T)
    assert {x["id"] for x in oa_list.json()["items"]} == {org_t["id"], mine["id"], draft["id"]}
    assert {x["id"] for x in (await api.call(w.OA, "GET", T, params={"status": "draft"})).json()["items"]} == {draft["id"]}
    pa_list = await api.call(w.PA, "GET", T)
    assert {x["id"] for x in pa_list.json()["items"]} >= {plat["id"], org_t["id"], mine["id"], draft["id"]}
    assert (await api.call(w.X, "GET", T)).json()["items"] == []
    assert (await api.call(w.TC, "GET", T)).json()["items"] == []
    # pagination
    first = await api.call(w.PA, "GET", T, params={"limit": 2})
    assert len(first.json()["items"]) == 2 and first.json()["next_cursor"]
    second = await api.call(w.PA, "GET", T, params={"limit": 2, "cursor": first.json()["next_cursor"]})
    assert second.status_code == 200 and not ({x["id"] for x in first.json()["items"]}
                                              & {x["id"] for x in second.json()["items"]})
    # read shapes: manager gets the draft, a user who only sees it gets the picker shape
    assert "draft_spec" in (await api.call(w.OA, "GET", f"{T}/{mine['id']}")).json()
    body = (await api.call(w.TB, "GET", f"{T}/{org_t['id']}")).json()
    assert set(body) == set(PICKER_KEYS)
    assert (await api.call(w.TB, "GET", f"{T}/{mine['id']}")).status_code == 404
    assert (await api.call(w.S, "GET", f"{T}/{org_t['id']}")).status_code == 404
    assert (await api.call(None, "GET", T)).status_code == 401


async def test_blocks_catalog(db, api):
    w = tworld(db)
    own = make_scheme(db, w.TA, title={"en": "Mine"})
    make_scheme(db, w.TB, title={"en": "Other"})
    res = await api.call(w.TA, "GET", f"{T}/blocks")
    assert res.status_code == 200, res.text
    b = res.json()
    assert [q["key"] for q in b["question_types"]] == list(TYPE_NAMES)
    assert all(q["title_key"] and isinstance(q["import_columns"], list) for q in b["question_types"])
    assert b["result_views"] == ["general", "ort"] and b["display_modes"] == ["one_per_page", "scrolling"]
    assert b["passage_displays"] == ["plain", "numbered"] and b["navigations"] == ["free", "section_forward_only"]
    assert b["importer_profiles"] == ["general", "ort"] and set(b["lock_scope_keys"]) == set(ids.LOCK_SCOPE_KEYS)
    scopes = {s["id"]: s["scope"] for s in b["scheme_versions"]}
    assert scopes[str(ORT_MAIN_V1_ID)] == "system" and scopes[str(own.current_version_id)] == "mine"
    assert all(s["scope"] in ("system", "mine") for s in b["scheme_versions"])
    assert {s["title"]["en"] for s in b["scheme_versions"] if s["scope"] == "mine"} == {"Mine"}
    assert (await api.call(None, "GET", f"{T}/blocks")).status_code == 401
