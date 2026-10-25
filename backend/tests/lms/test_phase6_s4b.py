"""Phase 6 S4b (integration): the lobby's can_start mirrors the start route for an org admin, and
GET /platform/users/{user_id}/organizations for the admin user detail."""
from tests.lms.factories import make_assessment, make_assessment_version
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user  # noqa: F401


async def test_lobby_can_start_false_for_org_admin(db, api):
    org = make_org(db, "School")
    oa, owner, student = make_user(db), make_user(db), make_user(db)
    add_member(db, org, oa, "org_admin")
    add_member(db, org, owner, "teacher")
    course = make_course(db, owner, organization_id=org.id, status="published")
    enroll(db, course, student)
    a = make_assessment(db, course, owner)
    make_assessment_version(db, a, owner)
    url = f"/courses/{course.id}/assessments/{a.id}"
    lobby = (await api.call(student, "GET", url)).json()
    assert lobby["can_start"] is True and lobby["reason"] is None
    r = await api.call(oa, "GET", url)
    assert r.status_code == 200
    assert r.json()["can_start"] is False and r.json()["reason"] == "not_a_student"
    # the start route agrees
    assert (await api.call(oa, "POST", f"{url}/attempts", json={})).status_code == 403
    # a student of a concluded course gets the course reason, not the org admin one
    course.status = "concluded"
    db.commit()
    r = (await api.call(student, "GET", url)).json()
    assert r["can_start"] is False and r["reason"] == "course_not_active"
    assert (await api.call(student, "POST", f"{url}/attempts", json={})).status_code == 403


async def test_platform_user_organizations(db, api):
    admin = make_user(db, platform_admin=True)
    user, other = make_user(db), make_user(db)
    org1, org2 = make_org(db, "School 1"), make_org(db, "School 2")
    add_member(db, org1, user, "org_admin")
    add_member(db, org2, user, "teacher", state="removed")
    add_member(db, org2, other, "teacher")
    url = f"/platform/users/{user.id}/organizations"
    r = await api.call(admin, "GET", url)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [(i["organization_id"], i["organization_name"], i["role"], i["state"]) for i in items] == [
        (str(org1.id), "School 1", "org_admin", "active")]
    assert items[0]["organization_slug"] == org1.slug and items[0]["organization_status"] == "active"
    assert r.json()["next_cursor"] is None
    removed = (await api.call(admin, "GET", url, params={"state": "removed"})).json()["items"]
    assert [(i["organization_name"], i["role"]) for i in removed] == [("School 2", "teacher")]
    # pagination
    p1 = (await api.call(admin, "GET", f"/platform/users/{other.id}/organizations", params={"limit": 1})).json()
    assert len(p1["items"]) == 1
    # unknown user, and non-admins (an org admin included) are refused
    r = await api.call(admin, "GET", "/platform/users/usr_missing/organizations")
    assert r.status_code == 404 and r.json()["error"]["code"] == "user_not_found"
    assert (await api.call(user, "GET", url)).status_code == 403
