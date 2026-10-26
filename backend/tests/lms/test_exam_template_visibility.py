"""Phase 7b S2 visibility and creation matrix (PHASE_7B_DESIGN 5.2, 9.2): platform / organization / teacher
templates x caller x course organization, personal-organization isolation, cross-tenant 404s."""
from __future__ import annotations

import uuid

import pytest

from app.lms.exam_templates.models import ExamTemplate
from app.lms.organizations.ids import personal_org_id
from tests.lms.exam_template_support import general_spec
from tests.lms.factories import make_course, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_templates_api import T, create_from, create_t, err, published_template, tworld


async def _ids(api, user, cid):
    res = await api.call(user, "GET", T, params={"course_id": cid})
    assert res.status_code == 200, res.text
    return {x["id"] for x in res.json()["items"]}


async def test_picker_matrix_and_cross_tenant_404s(db, api):
    w = tworld(db)
    plat = await published_template(api, w.PA, title={"en": "P"})
    org_t = await published_template(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    ta_t = await published_template(api, w.TA, owner_scope="teacher", organization_id=w.org.id)
    draft = (await create_t(api, w.PA)).json()                       # never published: not in any picker
    tb_course = make_course(db, w.TB, organization_id=w.org.id, status="published")
    # independent teacher I: course in the personal organization, organization template there
    I = make_user(db, teacher_status="approved")
    porg = personal_org_id(I.id)
    i_course = make_course(db, I, organization_id=porg, status="published")
    i_t = await published_template(api, I, owner_scope="organization", organization_id=porg)

    assert await _ids(api, w.TA, w.cid) == {plat["id"], org_t["id"], ta_t["id"]}
    assert await _ids(api, w.AS, w.cid) == {plat["id"], org_t["id"]}           # TA's teacher template is TA's
    assert await _ids(api, w.TB, str(tb_course.id)) == {plat["id"], org_t["id"]}
    assert await _ids(api, w.TC, w.cid2) == {plat["id"]}                       # org B: platform only
    assert await _ids(api, I, str(i_course.id)) == {plat["id"], i_t["id"]}     # personal org: own + platform
    assert draft["id"] not in await _ids(api, w.TA, w.cid)
    # students, outsiders and an org admin without an enrollment get no picker
    for u, code in ((w.S, 403), (w.X, 404), (w.OA, 403)):
        res = await api.call(u, "GET", T, params={"course_id": w.cid})
        assert res.status_code == code, (u.id, res.text)
    assert (await api.call(w.TA, "GET", T, params={"course_id": str(uuid.uuid4())})).status_code == 404

    # reads outside both scopes are 404s, never 403s
    for u, tid in ((w.TC, org_t["id"]), (w.TC, ta_t["id"]), (w.TB, ta_t["id"]), (w.TA, i_t["id"]), (w.X, org_t["id"]),
                   (w.TA, draft["id"]), (w.X, ta_t["id"])):
        res = await api.call(u, "GET", f"{T}/{tid}")
        assert res.status_code == 404, (u.id, tid, res.text)
        assert err(res) == "template_not_found"
    assert (await api.call(w.S, "GET", f"{T}/{plat['id']}")).status_code == 200   # platform: everyone (B4)
    assert (await api.call(w.TB, "GET", f"{T}/{org_t['id']}")).status_code == 200
    assert (await api.call(w.TA, "GET", f"{T}/{ta_t['id']}/versions")).status_code == 200
    assert (await api.call(w.TB, "GET", f"{T}/{ta_t['id']}/versions")).status_code == 404

    # creating from a template outside the course's scope: 404 template_not_found, nothing created
    for u, cid, tid in ((w.TC, w.cid2, org_t["id"]), (w.TC, w.cid2, ta_t["id"]), (w.TB, str(tb_course.id), ta_t["id"]),
                        (w.TA, w.cid, i_t["id"]), (w.TA, w.cid, str(uuid.uuid4()))):
        body = await create_from(api, u, cid, tid, status=404)
        assert body["error"]["code"] == "template_not_found"
    vid = org_t["current_version_id"]
    body = await create_from(api, w.TC, w.cid2, version_id=vid, status=404)
    assert body["error"]["code"] == "template_not_found"
    body = await create_from(api, w.TA, w.cid, draft["id"], status=422)
    assert body["error"]["code"] == "template_not_published"
    # a student / outsider cannot create at all
    body = await create_from(api, w.S, w.cid, plat["id"], status=403)
    body = await create_from(api, w.X, w.cid, plat["id"], status=404)
    # the same templates work where they belong
    await create_from(api, w.TB, str(tb_course.id), org_t["id"])
    await create_from(api, w.TC, w.cid2, plat["id"])
    await create_from(api, I, str(i_course.id), i_t["id"])
    await create_from(api, w.AS, w.cid, org_t["id"])                   # assistants have content.manage


@pytest.mark.parametrize("who,scope,org,status", [
    ("PA", "platform", None, 201),
    ("OA", "platform", None, 403),
    ("TA", "platform", None, 403),
    ("OA", "organization", "org", 201),
    ("TA", "organization", "org", 403),           # teachers_can_publish_org_templates is off (P7B-3)
    ("PA", "organization", "org", 201),
    ("TC", "organization", "org", 403),           # admin of nothing, member of another org
    ("TA", "teacher", "org", 201),
    ("OA", "teacher", "org", 201),                # an org admin is a member too
    ("TC", "teacher", "org", 403),                # not a member
    ("S", "teacher", "org", 403),
    ("X", "teacher", "org", 403),
    ("PA", "teacher", "org", 201),
    ("TA", "teacher", "org2", 403),
    ("TA", "teacher", None, 422),                 # organization_id required
    ("PA", "platform", "org", 422),               # platform templates carry no organization
])
async def test_create_matrix(db, api, who, scope, org, status):
    w = tworld(db)
    user = getattr(w, who)
    org_id = getattr(w, org).id if org else None
    res = await create_t(api, user, owner_scope=scope, organization_id=org_id, spec=general_spec())
    assert res.status_code == status, (who, scope, org, res.text)
    if status == 403:
        assert err(res) == "scope_not_allowed"
    if status == 201:
        b = res.json()
        assert b["owner_scope"] == scope
        assert b["owner_user_id"] == (user.id if scope == "teacher" else None)
        assert b["organization_id"] == (str(org_id) if org_id else None)


async def test_teachers_can_publish_org_templates_setting(db, api):
    w = tworld(db, teachers_can_publish=True)
    res = await create_t(api, w.TA, owner_scope="organization", organization_id=w.org.id)
    assert res.status_code == 201 and res.json()["owner_scope"] == "organization"
    assert (await create_t(api, w.TC, owner_scope="organization", organization_id=w.org.id)).status_code == 403
    # the creator keeps editing it while the setting is on (P7B-3); another teacher of the org does not; locking
    # stays the org admin's (owner answer 5)
    tid = res.json()["id"]
    assert (await api.call(w.TA, "PATCH", f"{T}/{tid}", json={"draft_rev": 1, "title": {"en": "X"}})).status_code == 200
    assert (await api.call(w.TB, "PATCH", f"{T}/{tid}", json={"draft_rev": 2, "title": {"en": "Y"}})).status_code == 404
    assert (await api.call(w.OA, "PATCH", f"{T}/{tid}", json={"draft_rev": 2, "title": {"en": "Z"}})).status_code == 200
    assert err(await api.call(w.TA, "POST", f"{T}/{tid}/lock")) == "scope_not_allowed"
    assert (await api.call(w.OA, "POST", f"{T}/{tid}/lock")).status_code == 200
    w.org.settings = {}
    db.commit()
    assert (await api.call(w.TA, "PATCH", f"{T}/{tid}", json={"draft_rev": 3, "title": {"en": "W"}})).status_code == 404


async def test_unknown_or_deleted_organization(db, api):
    w = tworld(db)
    res = await create_t(api, w.PA, owner_scope="organization", organization_id=uuid.uuid4())
    assert res.status_code == 404 and err(res) == "organization_not_found"
    res = await create_t(api, w.TA, owner_scope="teacher", organization_id=uuid.uuid4())
    assert res.status_code == 403 and err(res) == "scope_not_allowed"
    w.org.status = "suspended"
    db.commit()
    res = await create_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id)
    assert res.status_code == 403 and err(res) == "organization_suspended"
    assert db.query(ExamTemplate).count() == 0
