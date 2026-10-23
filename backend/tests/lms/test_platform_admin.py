import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.lms.audit.models import AdminAuditLog
from app.main import app
from app.models.user import User
from tests.lms.factories import auth, make_course, make_user

P = "/api/v1/platform"
_UID = "00000000-0000-0000-0000-000000000001"

# Every route this slice owns: (method, path, json body)
ROUTES = [
    ("GET", f"{P}/summary", None),
    ("GET", f"{P}/teacher-requests", None),
    ("POST", f"{P}/teacher-requests/{_UID}/approve", {}),
    ("POST", f"{P}/teacher-requests/{_UID}/reject", {"reason": "x"}),
    ("GET", f"{P}/users", None),
    ("GET", f"{P}/users/usr_x", None),
    ("POST", f"{P}/users/usr_x/teacher-status", {"status": "approved"}),
    ("POST", f"{P}/users/usr_x/disable", {"reason": "x"}),
    ("POST", f"{P}/users/usr_x/enable", None),
    ("GET", f"{P}/audit-log", None),
]


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def test_routes_table_matches_policies():
    from app.lms.platform_admin.policies import PLATFORM_POLICIES
    from app.lms.platform_admin.router import router
    mine = {(m, "/api/v1/platform" + r.path) for r in router.routes for m in r.methods}
    assert mine == set(PLATFORM_POLICIES)
    assert len(ROUTES) == len(PLATFORM_POLICIES)
    assert set(PLATFORM_POLICIES.values()) == {"platform_admin"}


@pytest.mark.parametrize("method,path,body", ROUTES)
async def test_non_admin_forbidden(client, db, method, path, body):
    student = make_user(db)
    teacher = make_user(db, teacher_status="approved")
    # forged token: platform-admin claims for a plain student (claims must be ignored)
    forged = {"Authorization": "Bearer " + create_access_token(
        {"sub": student.id, "role": "admin", "is_platform_admin": True})}
    legacy_admin = make_user(db, role="admin", teacher_status="approved")  # old role only
    for headers in (auth(student), auth(teacher), forged, auth(legacy_admin)):
        r = await client.request(method, path, json=body, headers=headers)
        assert r.status_code == 403, (method, path, r.text)
        assert r.json()["error"]["code"] == "platform_admin_required"
    assert (await client.request(method, path, json=body)).status_code in (401, 403)


async def test_disabled_admin_gets_401(client, db):
    admin = make_user(db, platform_admin=True, disabled=True)
    for method, path, body in ROUTES:
        r = await client.request(method, path, json=body, headers=auth(admin))
        assert r.status_code == 401, (method, path)


async def test_disable_enable_flow_and_audit(client, db):
    admin = make_user(db, platform_admin=True)
    target = make_user(db, email=f"victim.{uuid.uuid4().hex[:8]}@test.example", display_name="Victim Person")
    headers = auth(target)
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    r = await client.post(f"{P}/users/{target.id}/disable", json={"reason": "abuse"}, headers=auth(admin))
    assert r.status_code == 200 and r.json()["disabled_reason"] == "abuse" and r.json()["disabled_at"]
    # disabled everywhere: auth api and LMS api
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (await client.get("/api/v1/me/lms", headers=headers)).status_code == 401

    r = await client.post(f"{P}/users/{target.id}/enable", headers=auth(admin))
    assert r.status_code == 200 and r.json()["disabled_at"] is None
    assert (await client.get("/api/v1/me/lms", headers=headers)).status_code == 200

    rows = db.query(AdminAuditLog).filter(AdminAuditLog.target_id == target.id).all()
    assert sorted(x.action for x in rows) == ["user.disable", "user.enable"]
    for x in rows:
        assert x.actor_id == admin.id and x.target_type == "user"
        blob = str(x.details) + (x.reason or "")
        assert "victim" not in blob.lower() and "@" not in blob
    assert db.query(AdminAuditLog).filter_by(action="user.disable", target_id=target.id).one().reason == "abuse"

    assert (await client.post(f"{P}/users/{uuid.uuid4()}/disable", json={"reason": "x"},
                              headers=auth(admin))).status_code == 404


async def test_cannot_disable_self_or_admin(client, db):
    admin = make_user(db, platform_admin=True)
    other_admin = make_user(db, platform_admin=True)
    r = await client.post(f"{P}/users/{admin.id}/disable", json={"reason": "x"}, headers=auth(admin))
    assert r.status_code == 409 and r.json()["error"]["code"] == "cannot_disable_self"
    r = await client.post(f"{P}/users/{other_admin.id}/disable", json={"reason": "x"}, headers=auth(admin))
    assert r.status_code == 409 and r.json()["error"]["code"] == "cannot_disable_admin"
    db.expire_all()
    assert db.get(User, admin.id).disabled_at is None and db.get(User, other_admin.id).disabled_at is None
    assert db.query(AdminAuditLog).filter(AdminAuditLog.action == "user.disable",
                                          AdminAuditLog.target_id.in_([admin.id, other_admin.id])).count() == 0


async def test_users_list_filters_pagination_and_detail(client, db):
    admin = make_user(db, platform_admin=True)
    tag = uuid.uuid4().hex[:8]
    users = [make_user(db, email=f"{tag}.u{i}@test.example", display_name=f"Zed{tag} {i}") for i in range(5)]
    owner = users[0]
    owner.teacher_status = "approved"
    db.commit()
    make_course(db, owner)

    seen, cursor = [], None
    while True:
        url = f"{P}/users?q={tag}&limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = (await client.get(url, headers=auth(admin))).json()
        assert len(body["items"]) <= 2
        seen += [i["id"] for i in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == sorted(u.id for u in users)

    body = (await client.get(f"{P}/users?q={tag}&teacher_status=approved", headers=auth(admin))).json()
    assert [i["id"] for i in body["items"]] == [owner.id]
    body = (await client.get(f"{P}/users?q={tag}&disabled=true", headers=auth(admin))).json()
    assert body["items"] == []
    item = (await client.get(f"{P}/users?q={tag}.u0", headers=auth(admin))).json()["items"][0]
    assert set(item) == {"id", "email", "display_name", "created_at", "email_verified", "is_platform_admin",
                         "teacher_status", "disabled_at", "disabled_reason"}
    assert "password_hash" not in item

    d = (await client.get(f"{P}/users/{owner.id}", headers=auth(admin))).json()
    assert len(d["owned_courses"]) == 1 and d["active_enrollment_count"] == 1
    assert "join_code" not in str(d)
    assert (await client.get(f"{P}/users/nope", headers=auth(admin))).status_code == 404


async def test_audit_log_pagination_and_filters(client, db):
    admin = make_user(db, platform_admin=True)
    targets = [make_user(db) for _ in range(3)]
    for t in targets:
        await client.post(f"{P}/users/{t.id}/disable", json={"reason": "r"}, headers=auth(admin))
    await client.post(f"{P}/users/{targets[0].id}/enable", headers=auth(admin))

    seen, cursor = [], None
    while True:
        url = f"{P}/audit-log?actor_id={admin.id}&limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = (await client.get(url, headers=auth(admin))).json()
        assert len(body["items"]) <= 2
        seen += body["items"]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 4 and len({i["id"] for i in seen}) == 4
    assert all(i["actor"]["id"] == admin.id for i in seen)
    assert [i["action"] for i in seen][0] == "user.enable"  # newest first

    body = (await client.get(f"{P}/audit-log?actor_id={admin.id}&action=user.disable", headers=auth(admin))).json()
    assert len(body["items"]) == 3
    body = (await client.get(f"{P}/audit-log?target_type=user&target_id={targets[0].id}",
                             headers=auth(admin))).json()
    assert sorted(i["action"] for i in body["items"]) == ["user.disable", "user.enable"]
    assert set(body["items"][0]) == {"id", "created_at", "actor", "action", "target_type", "target_id",
                                     "reason", "details"}
