"""Phase 1 end-to-end flow over HTTP: signup -> teacher approval -> course lifecycle -> join/roster -> delete/restore."""
import uuid

from sqlalchemy import select

from app.lms.enrollments.models import EnrollmentEvent
from tests.auth_helpers import register_and_verify
from tests.lms.s3_support import api, auth, clean_rate_limits, db, make_user  # noqa: F401
from httpx import ASGITransport, AsyncClient
from app.main import app


def _has_key(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(_has_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_key(v, key) for v in obj)
    return False


def _fmt(code):
    return code[:4] + "-" + code[4:]


async def test_phase1_flow(db, api):
    # 1. sign up two users through the real registration flow
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t_reg = await register_and_verify(c, {"email": f"teach.{uuid.uuid4().hex[:8]}@test.example",
                                              "password": "securepassword123", "displayName": "Teach Er"})
        s_reg = await register_and_verify(c, {"email": f"stud.{uuid.uuid4().hex[:8]}@test.example",
                                              "password": "securepassword123", "displayName": "Stu Dent"})
    from app.models.user import User
    teacher = db.query(User).filter(User.display_name == "Teach Er").order_by(User.created_at.desc()).first()
    student = db.query(User).filter(User.display_name == "Stu Dent").order_by(User.created_at.desc()).first()
    admin = make_user(db, platform_admin=True)
    other_admin = make_user(db, platform_admin=True)

    # 2. teacher request -> approval
    r = await api.call(teacher, "POST", "/courses", json={"title": {"en": "X"}, "languages": ["en"], "default_language": "en"})
    assert r.status_code == 403
    r = await api.call(teacher, "POST", "/me/teacher-requests", json={"message": "I teach"})
    assert r.status_code == 201
    rid = r.json()["id"]
    r = await api.call(admin, "POST", f"/platform/teacher-requests/{rid}/approve", json={})
    assert r.status_code == 200

    # 3. create (two languages) and publish
    r = await api.call(teacher, "POST", "/courses", json={
        "title": {"en": "Algebra", "ru": "Алгебра"}, "languages": ["en", "ru"], "default_language": "en"})
    assert r.status_code == 201, r.text
    course = r.json()
    cid, code = course["id"], course["join_code"]
    assert course["status"] == "draft"
    assert (await api.call(student, "POST", "/courses/join", json={"code": code})).status_code == 404  # draft
    r = await api.call(teacher, "POST", f"/courses/{cid}/publish")
    assert r.status_code == 200 and r.json()["status"] == "published"

    # 4. join: formatted code and lowercase both work
    r = await api.call(student, "POST", "/courses/join", json={"code": _fmt(code)})
    assert r.status_code == 200 and r.json()["already_enrolled"] is False
    eid = r.json()["enrollment"]["id"]
    r2 = await api.call(student, "POST", "/courses/join", json={"code": code.lower()})
    assert r2.status_code == 200 and r2.json()["already_enrolled"] is True and r2.json()["enrollment"]["id"] == eid
    student_bodies = [r.json(), r2.json()]

    # 5. roster
    r = await api.call(teacher, "GET", f"/courses/{cid}/people")
    assert r.status_code == 200
    assert eid in [i["enrollment_id"] for i in r.json()["items"]]

    # student view never exposes join_code or email
    r = await api.call(student, "GET", f"/courses/{cid}")
    assert r.status_code == 200
    student_bodies.append(r.json())
    student_bodies.append((await api.call(student, "GET", "/courses")).json())
    student_bodies.append((await api.call(student, "GET", f"/courses/{cid}/people")).json())

    # 6. remove -> rejoin revives the same enrollment
    assert (await api.call(teacher, "DELETE", f"/courses/{cid}/enrollments/{eid}")).status_code == 204
    assert (await api.call(student, "GET", f"/courses/{cid}")).status_code == 404
    r = await api.call(student, "POST", "/courses/join", json={"code": code})
    assert r.status_code == 200 and r.json()["enrollment"]["id"] == eid and r.json()["already_enrolled"] is False
    student_bodies.append(r.json())
    db.expire_all()
    evs = [e.event for e in db.execute(select(EnrollmentEvent).where(EnrollmentEvent.enrollment_id == uuid.UUID(eid))
                                       .order_by(EnrollmentEvent.created_at)).scalars()]
    assert evs == ["joined", "removed", "rejoined"]

    # 7. regenerate: old code fails
    r = await api.call(teacher, "POST", f"/courses/{cid}/join-code/regenerate")
    assert r.status_code == 200 and r.json()["join_code"] != code
    other = make_user(db)
    r = await api.call(other, "POST", "/courses/join", json={"code": code})
    assert r.status_code == 404 and r.json()["error"]["code"] == "join_code_invalid"

    # 8. conclude: student can still read; leave is allowed (design 7.4: concluded grants COURSE_LEAVE)
    r = await api.call(teacher, "POST", f"/courses/{cid}/conclude")
    assert r.status_code == 200 and r.json()["status"] == "concluded"
    r = await api.call(student, "GET", f"/courses/{cid}")
    assert r.status_code == 200 and r.json()["status"] == "concluded"
    student_bodies.append(r.json())
    r = await api.call(other, "POST", "/courses/join", json={"code": r.json().get("join_code") or "ZZZZZZZZ"})
    assert r.status_code == 404  # concluded courses cannot be joined
    assert (await api.call(student, "POST", f"/courses/{cid}/leave")).status_code == 204
    assert (await api.call(student, "GET", f"/courses/{cid}")).status_code == 404

    # 9. owner soft-deletes: 404 for student and non-owner admin; restore -> draft
    assert (await api.call(teacher, "DELETE", f"/courses/{cid}")).status_code == 204
    for who in (student, other_admin):
        assert (await api.call(who, "GET", f"/courses/{cid}")).status_code == 404
    r = await api.call(teacher, "POST", f"/courses/{cid}/restore")
    assert r.status_code == 200 and r.json()["status"] == "draft"

    for body in student_bodies:
        assert not _has_key(body, "join_code"), body
        assert not _has_key(body, "email"), body
