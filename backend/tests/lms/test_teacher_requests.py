import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import SessionLocal
from app.lms.audit.models import AdminAuditLog
from app.lms.teachers.models import TeacherRequest
from app.main import app
from app.models.user import User
from tests.lms.factories import auth, make_course, make_user

P = "/api/v1"


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _submit(client, user, message="please"):
    return await client.post(f"{P}/me/teacher-requests", json={"message": message}, headers=auth(user))


async def test_me_and_locale(client, db):
    u = make_user(db)
    r = await client.get(f"{P}/me/lms", headers=auth(u))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"id", "email", "display_name", "locale", "is_platform_admin", "teacher_status",
                         "can_create_courses"}
    assert body["can_create_courses"] is False
    r = await client.patch(f"{P}/me/lms", json={"locale": "ky"}, headers=auth(u))
    assert r.status_code == 200 and r.json()["locale"] == "ky"
    r = await client.patch(f"{P}/me/lms", json={"locale": "xx"}, headers=auth(u))
    assert r.status_code == 422


async def test_request_approve_flow(client, db):
    user = make_user(db)
    admin = make_user(db, platform_admin=True, teacher_status="approved")
    r = await _submit(client, user)
    assert r.status_code == 201
    mine = r.json()
    assert mine["status"] == "pending"
    assert "decided_by" not in mine and "decided_by_id" not in mine
    me = (await client.get(f"{P}/me/lms", headers=auth(user))).json()
    assert me["teacher_status"] == "pending" and me["can_create_courses"] is False

    r = await client.post(f"{P}/platform/teacher-requests/{mine['id']}/approve", json={"note": "ok"},
                          headers=auth(admin))
    assert r.status_code == 200
    assert r.json()["status"] == "approved" and r.json()["decided_by"]["id"] == admin.id
    me = (await client.get(f"{P}/me/lms", headers=auth(user))).json()
    assert me["teacher_status"] == "approved" and me["can_create_courses"] is True

    # approving again: not pending
    r = await client.post(f"{P}/platform/teacher-requests/{mine['id']}/approve", json={}, headers=auth(admin))
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_pending"
    # already a teacher
    r = await _submit(client, user)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_teacher"

    rows = db.query(AdminAuditLog).filter_by(action="teacher_request.approve", target_id=mine["id"]).all()
    assert len(rows) == 1 and rows[0].actor_id == admin.id
    assert user.email not in str(rows[0].details)

    # approved user can use the courses API when it exists (S3); skip the check otherwise
    r = await client.post(f"{P}/courses", json={"title": {"en": "T"}, "languages": ["en"],
                                                 "default_language": "en"}, headers=auth(user))
    if r.status_code not in (404, 405):
        assert r.status_code in (200, 201), r.text


async def test_reject_flow(client, db):
    user = make_user(db)
    admin = make_user(db, platform_admin=True)
    rid = (await _submit(client, user)).json()["id"]
    r = await client.post(f"{P}/platform/teacher-requests/{rid}/reject", json={"reason": ""},
                          headers=auth(admin))
    assert r.status_code == 422
    r = await client.post(f"{P}/platform/teacher-requests/{rid}/reject", json={"reason": "need more info"},
                          headers=auth(admin))
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    db.expire_all()
    assert db.get(User, user.id).teacher_status == "none"
    mine = (await client.get(f"{P}/me/teacher-requests", headers=auth(user))).json()
    assert mine[0]["status"] == "rejected" and mine[0]["reason"] == "need more info"
    # may ask again
    assert (await _submit(client, user)).status_code == 201
    a = db.query(AdminAuditLog).filter_by(action="teacher_request.reject", target_id=rid).all()
    assert len(a) == 1 and a[0].reason == "need more info"


async def test_unknown_request_404(client, db):
    admin = make_user(db, platform_admin=True)
    r = await client.post(f"{P}/platform/teacher-requests/{uuid.uuid4()}/approve", json={}, headers=auth(admin))
    assert r.status_code == 404


async def test_one_pending_per_user(client, db):
    user = make_user(db)
    assert (await _submit(client, user)).status_code == 201
    r = await _submit(client, user)
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_pending"
    assert db.query(TeacherRequest).filter_by(user_id=user.id).count() == 1


async def test_rate_limit_three_per_24h(client, db):
    user = make_user(db)
    admin = make_user(db, platform_admin=True)
    for _ in range(3):
        r = await _submit(client, user)
        assert r.status_code == 201
        await client.post(f"{P}/platform/teacher-requests/{r.json()['id']}/reject", json={"reason": "no"},
                          headers=auth(admin))
    r = await _submit(client, user)
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["code"] == "rate_limited" and err["details"]["retry_after_seconds"] > 0


async def test_revoke_and_direct_grant(client, db):
    admin = make_user(db, platform_admin=True)
    user = make_user(db)
    rid = (await _submit(client, user)).json()["id"]
    # direct grant approves the pending request with this admin as decider
    r = await client.post(f"{P}/platform/users/{user.id}/teacher-status", json={"status": "approved"},
                          headers=auth(admin))
    assert r.status_code == 200 and r.json()["teacher_status"] == "approved"
    db.expire_all()
    req = db.get(TeacherRequest, uuid.UUID(rid))
    assert req.status == "approved" and req.decided_by_id == admin.id

    # existing course stays editable; new course creation is blocked after revoke
    course = make_course(db, user)
    r = await client.post(f"{P}/platform/users/{user.id}/teacher-status",
                          json={"status": "revoked", "reason": "policy"}, headers=auth(admin))
    assert r.status_code == 200 and r.json()["teacher_status"] == "revoked"
    me = (await client.get(f"{P}/me/lms", headers=auth(user))).json()
    assert me["can_create_courses"] is False
    r = await client.post(f"{P}/courses", json={"title": {"en": "T"}, "languages": ["en"],
                                                 "default_language": "en"}, headers=auth(user))
    if r.status_code not in (404, 405):
        assert r.status_code == 403
        r = await client.patch(f"{P}/courses/{course.id}", json={"title": {"en": "New"}}, headers=auth(user))
        assert r.status_code == 200, r.text

    # invalid transitions
    r = await client.post(f"{P}/platform/users/{user.id}/teacher-status", json={"status": "revoked"},
                          headers=auth(admin))
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    other = make_user(db)
    r = await client.post(f"{P}/platform/users/{other.id}/teacher-status", json={"status": "revoked"},
                          headers=auth(admin))
    assert r.status_code == 409
    # a revoked user may be granted again
    r = await client.post(f"{P}/platform/users/{user.id}/teacher-status", json={"status": "approved"},
                          headers=auth(admin))
    assert r.status_code == 200

    rows = db.query(AdminAuditLog).filter_by(action="user.teacher_status.set", target_id=user.id).all()
    assert len(rows) == 3
    assert {(x.details["from"], x.details["to"]) for x in rows} == {
        ("pending", "approved"), ("approved", "revoked"), ("revoked", "approved")}


async def test_queue_pagination_and_summary(client, db):
    admin = make_user(db, platform_admin=True)
    users = [make_user(db) for _ in range(3)]
    for u in users:
        assert (await _submit(client, u)).status_code == 201
    s = (await client.get(f"{P}/platform/summary", headers=auth(admin))).json()
    assert s["pending_teacher_requests"] >= 3
    seen, cursor = [], None
    while True:
        url = f"{P}/platform/teacher-requests?status=pending&limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = (await client.get(url, headers=auth(admin))).json()
        assert len(body["items"]) <= 2
        seen += [i["id"] for i in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) and len(seen) >= 3
    r = await client.get(f"{P}/platform/teacher-requests?cursor=garbage", headers=auth(admin))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_cursor"
