"""Course CRUD, lifecycle, delete/restore, transfer, regenerate, teacher gating (design 7.5)."""
import uuid

import pytest
from sqlalchemy import func, select

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.core.route_inventory import ROUTE_POLICIES
from app.lms.courses import service as svc
from app.lms.courses.models import Course
from app.lms.courses.schemas import CourseCreateIn
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from app.lms.platform_admin.courses_policies import PLATFORM_COURSE_POLICIES
from app.lms.courses.policies import COURSE_POLICIES
from tests.lms.s3_support import api, auth, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

BODY = {"title": {"en": "Algebra", "ru": "Алгебра"}, "languages": ["en", "ru"], "default_language": "en"}


async def test_create_course_makes_owner_enrollment_and_event(db, api):
    t = teacher(db)
    r = await api.call(t, "POST", "/courses", json=BODY)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_owner"] and body["status"] == "draft" and body["my_enrollment"]["role"] == "teacher"
    assert len(body["join_code"]) == 8 and body["enrollment_mode"] == "invite_code"
    db.expire_all()
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == uuid.UUID(body["id"]))).scalar_one()
    assert (enr.user_id, enr.role, enr.state, enr.source) == (t.id, "teacher", "active", "owner")
    ev = db.execute(select(EnrollmentEvent).where(EnrollmentEvent.course_id == uuid.UUID(body["id"]))).scalar_one()
    assert ev.event == "created"


def test_create_course_is_atomic(db, monkeypatch):
    t = teacher(db)
    before = db.scalar(select(func.count()).select_from(Course))

    def boom(*a, **k):
        raise RuntimeError("injected")

    monkeypatch.setattr(svc, "add_event", boom)
    with pytest.raises(RuntimeError):
        svc.create_course(db, t, CourseCreateIn(**BODY))
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Course)) == before
    assert db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.user_id == t.id)) == 0


@pytest.mark.parametrize("kind", ["none", "pending", "revoked", "disabled", "old_admin"])
async def test_teacher_status_bypass_attempts(db, api, kind):
    if kind == "disabled":
        u = make_user(db, teacher_status="approved", disabled=True)
    elif kind == "old_admin":
        u = make_user(db)  # the old users.role column is gone (0006): nothing grants teacher rights
    else:
        u = make_user(db, teacher_status=kind)
    r = await api.call(u, "POST", "/courses", json=BODY)
    assert r.status_code == (401 if kind == "disabled" else 403)
    if kind != "disabled":
        assert r.json()["error"]["code"] == "teacher_not_approved"


@pytest.mark.parametrize("patch,ok", [
    ({"languages": []}, False),
    ({"languages": ["en", "en"]}, False),
    ({"languages": ["de"]}, False),
    ({"default_language": "ky"}, False),
    ({"title": {"ky": "x"}}, False),
    ({"title": {"en": ""}}, False),
    ({"title": {"en": "x" * 201}}, False),
    ({"enrollment_mode": "open"}, True),           # Phase 9 S1: CreateMode widened to the five modes
    ({"enrollment_mode": "form_review"}, False),   # Phase 9 S1: a new course has no form (form_needs_catalog)
    ({"enrollment_mode": "form_auto"}, False),
    ({"enrollment_mode": "waitlist"}, False),
    ({"enrollment_limit": 0}, False),
    ({"enrollment_limit": 10001}, False),
    ({"join_code": "AAAAAAAA"}, False),
    ({"status": "published"}, False),
    ({"enrollment_mode": "closed", "enrollment_limit": 3}, True),
])
async def test_create_validation(db, api, patch, ok):
    t = teacher(db)
    r = await api.call(t, "POST", "/courses", json={**BODY, **patch})
    assert (r.status_code == 201) == ok, r.text


async def test_update_rules(db, api):
    t = teacher(db)
    c = (await api.call(t, "POST", "/courses", json=BODY)).json()
    cid = c["id"]
    r = await api.call(t, "PATCH", f"/courses/{cid}", json={"status": "published"})
    assert r.status_code == 422
    assert (await api.call(t, "PATCH", f"/courses/{cid}", json={"languages": ["ru"]})).status_code == 422
    c2 = (await api.call(t, "POST", "/courses", json={**BODY, "title": {"en": "Only EN"}})).json()
    r = await api.call(t, "PATCH", f"/courses/{c2['id']}", json={"languages": ["ru"], "default_language": "ru"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "title_required"
    r = await api.call(t, "PATCH", f"/courses/{cid}", json={"languages": ["ru"], "default_language": "ru"})
    assert r.status_code == 200 and r.json()["title"] == {"ru": "Алгебра"}
    r = await api.call(t, "PATCH", f"/courses/{cid}", json={"starts_at": "2026-02-01T00:00:00Z",
                                                            "ends_at": "2026-01-01T00:00:00Z"})
    assert r.status_code == 422
    r = await api.call(t, "PATCH", f"/courses/{cid}", json={"visibility": "catalog"})
    assert r.status_code == 200 and r.json()["visibility"] == "catalog"


async def test_limit_below_current_and_unlisted(db, api):
    t = teacher(db)
    c = make_course_pub(db, t)
    for _ in range(3):
        enroll(db, c, make_user(db))
    r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"enrollment_limit": 2})
    assert r.status_code == 409 and r.json()["error"]["code"] == "limit_below_current"
    assert (await api.call(t, "PATCH", f"/courses/{c.id}", json={"enrollment_limit": 3})).status_code == 200
    from app.lms.core.models import utcnow
    c.unlisted_by_admin_at = utcnow()
    db.commit()
    r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"visibility": "catalog"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "unlisted_by_admin"


def make_course_pub(db, owner, **kw):
    return make_course(db, owner, status="published", **kw)


async def test_lifecycle(db, api):
    t = teacher(db)
    cid = (await api.call(t, "POST", "/courses", json=BODY)).json()["id"]

    async def go(action):
        return await api.call(t, "POST", f"/courses/{cid}/{action}")

    for bad in ("unpublish", "conclude", "reopen"):
        r = await go(bad)
        assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    r = await go("publish")
    assert r.status_code == 200 and r.json()["status"] == "published" and r.json()["published_at"]
    assert (await go("publish")).status_code == 409
    assert (await go("unpublish")).json()["status"] == "draft"
    await go("publish")
    s = make_user(db)
    enroll(db, db.get(Course, uuid.UUID(cid)), s)
    r = await go("unpublish")
    assert r.status_code == 409 and r.json()["error"]["code"] == "has_students"
    r = await go("conclude")
    assert r.status_code == 200 and r.json()["status"] == "concluded"
    assert (await go("reopen")).json()["status"] == "published"


async def test_delete_restore_trash(db, api):
    t = teacher(db)
    c = make_course(db, t)
    assert (await api.call(t, "DELETE", f"/courses/{c.id}")).status_code == 204
    assert (await api.call(t, "GET", f"/courses/{c.id}")).status_code == 404
    lst = (await api.call(t, "GET", "/courses")).json()["items"]
    assert str(c.id) not in [i["id"] for i in lst]
    trash = (await api.call(t, "GET", "/courses/trash")).json()["items"]
    assert [i["id"] for i in trash] == [str(c.id)] and trash[0]["deleted_at"]
    assert (await api.call(t, "DELETE", f"/courses/{c.id}")).status_code == 404
    r = await api.call(t, "POST", f"/courses/{c.id}/restore")
    assert r.status_code == 200 and r.json()["status"] == "draft"
    assert (await api.call(t, "GET", "/courses/trash")).json()["items"] == []


def _add_org_member(db, organization_id, user, role: str = "teacher") -> None:
    """S5: ownership transfers require the new owner to be an active member of the course's organization."""
    from app.lms.organizations.models import OrganizationMember

    db.add(OrganizationMember(id=uuid.uuid4(), organization_id=organization_id, user_id=user.id, role=role,
                              state="active"))
    db.commit()


async def test_transfer(db, api):
    o, co, other, stud = teacher(db), teacher(db), teacher(db), make_user(db)
    c = make_course(db, o, status="published")
    enroll(db, c, co, role="teacher")
    enroll(db, c, stud)
    for target in (stud.id, other.id, o.id, "usr_nope"):
        r = await api.call(o, "POST", f"/courses/{c.id}/transfer-ownership", json={"new_owner_user_id": target})
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_new_owner", target
    # S5: an approved co-teacher outside the course's organization cannot become the owner ...
    r = await api.call(o, "POST", f"/courses/{c.id}/transfer-ownership", json={"new_owner_user_id": co.id})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_new_owner"
    _add_org_member(db, c.organization_id, co)  # ... an active member can
    r = await api.call(o, "POST", f"/courses/{c.id}/transfer-ownership", json={"new_owner_user_id": co.id})
    assert r.status_code == 200 and r.json()["is_owner"] is False and r.json()["owner"]["id"] == co.id
    db.expire_all()
    evs = {e.event for e in db.execute(select(EnrollmentEvent).where(EnrollmentEvent.course_id == c.id)).scalars()}
    assert {"owner_transferred_in", "owner_transferred_out"} <= evs
    # old owner is still a teacher and may now leave; new owner cannot
    assert (await api.call(o, "POST", f"/courses/{c.id}/leave")).status_code == 204
    assert (await api.call(co, "POST", f"/courses/{c.id}/leave")).status_code == 409


async def test_regenerate_invalidates_old_code(db, api):
    t, s = teacher(db), make_user(db)
    c = make_course(db, t, status="published")
    old = c.join_code
    r = await api.call(t, "POST", f"/courses/{c.id}/join-code/regenerate")
    assert r.status_code == 200 and r.json()["join_code"] != old
    assert (await api.call(s, "POST", "/courses/join", json={"code": old})).status_code == 404
    assert (await api.call(s, "POST", "/courses/join", json={"code": r.json()["join_code"]})).status_code == 200


async def test_list_pagination_and_as_filter(db, api):
    t, s = teacher(db), make_user(db)
    cs = [make_course(db, t, status="published") for _ in range(3)]
    other = make_course(db, teacher(db), status="published")
    enroll(db, cs[0], s)
    enroll(db, other, t)  # t is a student elsewhere
    ids = set()
    cur = None
    while True:
        r = (await api.call(t, "GET", "/courses", params={"limit": 2, "as": "teaching", **({"cursor": cur} if cur else {})})).json()
        ids |= {i["id"] for i in r["items"]}
        cur = r["next_cursor"]
        if not cur:
            break
    assert ids == {str(c.id) for c in cs}
    learn = (await api.call(t, "GET", "/courses", params={"as": "learning"})).json()["items"]
    assert [i["id"] for i in learn] == [str(other.id)] and learn[0]["my_role"] == "student"
    # students do not see drafts
    draft = make_course(db, t)
    enroll(db, draft, s)
    assert str(draft.id) not in [i["id"] for i in (await api.call(s, "GET", "/courses")).json()["items"]]


def test_policies_are_declared_and_known():
    import re
    ok = re.compile(r"^(authenticated(\+ratelimit)?|course_creator|platform_admin|legacy|course:[a-z_.]+(\+owner)?)$")
    for key, pol in {**COURSE_POLICIES, **PLATFORM_COURSE_POLICIES}.items():
        assert ok.match(pol), (key, pol)
        assert ROUTE_POLICIES[key] == pol


async def test_platform_routes_need_db_flag_not_old_role(db, api):
    old_admin = make_user(db)  # users.role dropped in 0006; only the DB flag counts
    t = teacher(db)
    c = make_course(db, t)
    for m, p, body in [("GET", "/platform/courses", None), ("GET", f"/platform/courses/{c.id}", None),
                       ("GET", f"/platform/courses/{c.id}/people", None),
                       ("POST", f"/platform/courses/{c.id}/delete", {"reason": "x"})]:
        for u in (old_admin, t):
            r = await api.call(u, m, p, json=body)
            assert r.status_code == 403 and r.json()["error"]["code"] == "platform_admin_required"


async def test_admin_moderation_is_audited(db, api):
    from app.lms.audit.models import AdminAuditLog
    admin = make_user(db, platform_admin=True, teacher_status="approved")
    o, new = teacher(db), teacher(db)
    c = make_course(db, o, status="published")
    stud = make_user(db)
    enroll(db, c, stud)

    async def post(path, body):
        return await api.call(admin, "POST", f"/platform/courses/{c.id}/{path}", json=body)

    assert (await api.call(admin, "GET", "/platform/courses", params={"q": o.email[:8]})).status_code == 200
    r = await api.call(admin, "GET", f"/platform/courses/{c.id}")
    assert r.json()["active_student_count"] == 1 and "join_code" not in r.json()
    assert (await api.call(admin, "GET", f"/platform/courses/{c.id}/people")).status_code == 200
    r = await post("unlist", {"reason": "spam"})
    assert r.json()["unlisted_by_admin_at"]
    assert (await post("relist", {})).json()["unlisted_by_admin_at"] is None
    r = await post("transfer-ownership", {"new_owner_user_id": new.id, "reason": "handover"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_new_owner"  # S5: not a member
    _add_org_member(db, c.organization_id, new)
    r = await post("transfer-ownership", {"new_owner_user_id": new.id, "reason": "handover"})
    assert r.status_code == 200 and r.json()["owner"]["id"] == new.id
    assert (await post("transfer-ownership", {"new_owner_user_id": stud.id, "reason": "x"})).status_code == 422
    assert (await post("restore", {"reason": "x"})).status_code == 409
    assert (await post("delete", {"reason": "abuse"})).json()["deleted_at"]
    assert (await post("delete", {"reason": "abuse"})).status_code == 409
    # no bypass: the owner's own view is gone, admin sees it
    assert (await api.call(admin, "GET", f"/platform/courses/{c.id}")).status_code == 200
    assert (await post("restore", {"reason": "ok"})).json()["deleted_at"] is None
    assert (await post("delete", {})).status_code == 422
    db.expire_all()
    rows = db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == str(c.id))).scalars().all()
    actions = sorted(r.action for r in rows)
    assert actions == sorted(["course.roster.view", "course.unlist", "course.relist", "course.transfer_ownership",
                              "course.delete", "course.restore"])
    assert all(r.actor_id == admin.id for r in rows)
    assert not any("@" in str(r.details) for r in rows)
