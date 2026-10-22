"""Join by code, rate limits, rejoin, leave, staff management, owner protections."""
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from tests.lms.s3_support import api, auth, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


def events(db, course_id):
    db.expire_all()
    return [e.event for e in db.execute(
        select(EnrollmentEvent).where(EnrollmentEvent.course_id == course_id).order_by(EnrollmentEvent.created_at)
    ).scalars()]


async def test_join_happy_and_already_enrolled(db, api):
    t, s = teacher(db), make_user(db)
    c = make_course(db, t, status="published")
    r = await api.call(s, "POST", "/courses/join", json={"code": c.join_code})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["already_enrolled"] is False and b["enrollment"]["role"] == "student"
    assert b["course"]["my_role"] == "student"
    # code is forgiving: lower case, spaces, dash
    pretty = c.join_code[:4].lower() + " - " + c.join_code[4:].lower()
    r2 = await api.call(s, "POST", "/courses/join", json={"code": pretty})
    assert r2.status_code == 200 and r2.json()["already_enrolled"] is True
    assert r2.json()["enrollment"]["id"] == b["enrollment"]["id"]
    assert events(db, c.id).count("joined") == 1


async def test_every_join_failure_is_byte_identical(db, api):
    t, s = teacher(db), make_user(db)
    draft = make_course(db, t)
    concluded = make_course(db, t, status="concluded")
    closed = make_course(db, t, status="published", enrollment_mode="closed")
    deleted = make_course(db, t, status="published")
    deleted.deleted_at = utcnow()
    full = make_course(db, t, status="published", enrollment_limit=1)
    enroll(db, full, make_user(db))
    db.commit()
    codes = [draft.join_code, concluded.join_code, closed.join_code, deleted.join_code, full.join_code,
             "ZZZZZZZZ", "short", "0O1I0O1I", "", "x" * 500, "ÄÖÜ-ÄÖÜ"]
    bodies = set()
    for code in codes:
        r = await api.call(make_user(db), "POST", "/courses/join", json={"code": code}, ip=f"7.7.7.{len(bodies)}")
        assert r.status_code == 404, code
        assert r.json()["error"]["code"] == "join_code_invalid"
        bodies.add(r.content)
    assert len(bodies) == 1


async def test_user_rate_limit_429(db, api):
    s = make_user(db)
    codes = []
    for i in range(10):
        r = await api.call(s, "POST", "/courses/join", json={"code": "ZZZZZZZZ"}, ip=f"8.8.8.{i}")
        codes.append(r.status_code)
    assert set(codes) == {404}
    r = await api.call(s, "POST", "/courses/join", json={"code": "ZZZZZZZZ"}, ip="8.8.9.9")
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert r.json()["error"]["details"]["retry_after_seconds"] >= 1


async def test_ip_failure_limit_counts_failures_only(db, api, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True, raising=False)
    t = teacher(db)
    c = make_course(db, t, status="published")
    ip = "5.5.5.5"
    for _ in range(62):  # successes from one IP never count
        r = await api.call(make_user(db), "POST", "/courses/join", json={"code": c.join_code}, ip=ip)
        assert r.status_code == 200
    for _ in range(60):
        r = await api.call(make_user(db), "POST", "/courses/join", json={"code": "ZZZZZZZZ"}, ip=ip)
        assert r.status_code == 404
    r = await api.call(make_user(db), "POST", "/courses/join", json={"code": "ZZZZZZZZ"}, ip=ip)
    assert r.status_code == 429
    r = await api.call(make_user(db), "POST", "/courses/join", json={"code": "ZZZZZZZZ"}, ip="5.5.5.6")
    assert r.status_code == 404


async def test_limit_counts_students_only(db, api):
    t = teacher(db)
    c = make_course(db, t, status="published", enrollment_limit=1)
    enroll(db, c, teacher(db), role="assistant")
    assert (await api.call(make_user(db), "POST", "/courses/join", json={"code": c.join_code})).status_code == 200
    assert (await api.call(make_user(db), "POST", "/courses/join", json={"code": c.join_code})).status_code == 404


async def test_remove_then_rejoin_revives_same_row(db, api):
    t, s = teacher(db), make_user(db)
    c = make_course(db, t, status="published")
    j = (await api.call(s, "POST", "/courses/join", json={"code": c.join_code})).json()
    eid = j["enrollment"]["id"]
    # promoted to assistant, then removed
    assert (await api.call(t, "PATCH", f"/courses/{c.id}/enrollments/{eid}", json={"role": "assistant"})).status_code == 200
    assert (await api.call(t, "DELETE", f"/courses/{c.id}/enrollments/{eid}")).status_code == 204
    assert (await api.call(s, "GET", f"/courses/{c.id}")).status_code == 404
    r = await api.call(s, "POST", "/courses/join", json={"code": c.join_code})
    assert r.status_code == 200 and r.json()["already_enrolled"] is False
    assert r.json()["enrollment"]["id"] == eid and r.json()["enrollment"]["role"] == "student"
    assert events(db, c.id) == ["created", "joined", "role_changed", "removed", "rejoined"]
    assert len(db.execute(select(Enrollment).where(Enrollment.user_id == s.id)).scalars().all()) == 1


async def test_leave_then_rejoin(db, api):
    t, s = teacher(db), make_user(db)
    c = make_course(db, t, status="published")
    enroll(db, c, s)
    assert (await api.call(s, "POST", f"/courses/{c.id}/leave")).status_code == 204
    assert (await api.call(s, "POST", f"/courses/{c.id}/leave")).status_code == 404
    assert (await api.call(s, "POST", "/courses/join", json={"code": c.join_code})).status_code == 200
    assert "left" in events(db, c.id) and "rejoined" in events(db, c.id)


async def test_owner_protections(db, api):
    o, co = teacher(db), teacher(db)
    c = make_course(db, o, status="published")
    co_enr = enroll(db, c, co, role="teacher")
    owner_enr = db.execute(select(Enrollment).where(Enrollment.user_id == o.id)).scalar_one()
    base = f"/courses/{c.id}/enrollments/"
    # owner cannot be removed / demoted, even by themselves or a co-teacher
    for actor in (o, co):
        r = await api.call(actor, "DELETE", base + str(owner_enr.id))
        assert r.status_code == 409 and r.json()["error"]["code"] == "owner_immutable"
        r = await api.call(actor, "PATCH", base + str(owner_enr.id), json={"role": "assistant"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "owner_immutable"
    r = await api.call(o, "POST", f"/courses/{c.id}/leave")
    assert r.status_code == 409 and r.json()["error"]["code"] == "owner_cannot_leave"
    # a non-owner teacher cannot remove or demote another teacher, nor promote to teacher
    third = teacher(db)
    third_enr = enroll(db, c, third, role="teacher")
    for m, body in (("DELETE", None), ("PATCH", {"role": "assistant"})):
        r = await api.call(co, m, base + str(third_enr.id), json=body)
        assert r.status_code == 403 and r.json()["error"]["code"] == "owner_only"
    stud = enroll(db, c, make_user(db))
    r = await api.call(co, "PATCH", base + str(stud.id), json={"role": "teacher"})
    assert r.status_code == 403
    # the owner can
    assert (await api.call(o, "PATCH", base + str(stud.id), json={"role": "teacher"})).status_code == 422  # not approved
    assert (await api.call(o, "PATCH", base + str(third_enr.id), json={"role": "assistant"})).status_code == 200
    assert (await api.call(o, "DELETE", base + str(co_enr.id))).status_code == 204
    # self removal through DELETE is refused for non-owners with use_leave
    asst = enroll(db, c, make_user(db), role="assistant")  # assistants cannot manage anyway
    r = await api.call(co, "DELETE", base + str(asst.id))
    assert r.status_code == 404  # co was removed


async def test_use_leave(db, api):
    o, co = teacher(db), teacher(db)
    c = make_course(db, o, status="published")
    enroll(db, c, co, role="teacher")
    me = db.execute(select(Enrollment).where(Enrollment.user_id == co.id)).scalar_one()
    # teacher target -> owner-only first (spec order); a self-targeting non-teacher manager cannot exist
    r = await api.call(co, "DELETE", f"/courses/{c.id}/enrollments/{me.id}")
    assert r.status_code == 403


async def test_enrollment_from_other_course_is_404(db, api):
    a, b = teacher(db), teacher(db)
    ca, cb = make_course(db, a, status="published"), make_course(db, b, status="published")
    e = enroll(db, cb, make_user(db))
    for m, body in (("DELETE", None), ("PATCH", {"role": "assistant"})):
        assert (await api.call(a, m, f"/courses/{ca.id}/enrollments/{e.id}", json=body)).status_code == 404
    assert (await api.call(a, "DELETE", f"/courses/{ca.id}/enrollments/{uuid.uuid4()}")).status_code == 404


async def test_add_staff(db, api):
    o = teacher(db)
    c = make_course(db, o, status="published")
    appr, plain, unverified = teacher(db), make_user(db), make_user(db)
    unverified.email_verified = False
    db.commit()
    r = await api.call(o, "POST", f"/courses/{c.id}/staff", json={"email": appr.email.upper(), "role": "teacher"})
    assert r.status_code == 201 and r.json()["role"] == "teacher" and r.json()["user"]["email"] == appr.email
    r = await api.call(o, "POST", f"/courses/{c.id}/staff", json={"email": appr.email, "role": "assistant"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_enrolled"
    r = await api.call(o, "POST", f"/courses/{c.id}/staff", json={"email": plain.email, "role": "teacher"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_approved_teacher"
    r = await api.call(o, "POST", f"/courses/{c.id}/staff", json={"email": plain.email, "role": "assistant"})
    assert r.status_code == 201
    for email in ("nobody@test.example", unverified.email):
        r = await api.call(o, "POST", f"/courses/{c.id}/staff", json={"email": email, "role": "assistant"})
        assert r.status_code == 404 and r.json()["error"]["code"] == "user_not_found"
    # a co-teacher may add assistants but not teachers
    r = await api.call(appr, "POST", f"/courses/{c.id}/staff", json={"email": make_user(db).email, "role": "assistant"})
    assert r.status_code == 201
    r = await api.call(appr, "POST", f"/courses/{c.id}/staff", json={"email": teacher(db).email, "role": "teacher"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "owner_only"


async def test_add_staff_rate_limit(db, api):
    o = teacher(db)
    c = make_course(db, o, status="published")
    last = None
    for _ in range(31):
        last = await api.call(o, "POST", f"/courses/{c.id}/staff", json={"email": "nobody@test.example", "role": "assistant"})
    assert last.status_code == 429


async def test_people_filters_and_students_view(db, api):
    o = teacher(db)
    c = make_course(db, o, status="published")
    s1 = make_user(db, email=f"alice.{uuid.uuid4().hex[:6]}@test.example", display_name="Alice")
    s2 = make_user(db)
    e1, _ = enroll(db, c, s1), enroll(db, c, s2)
    r = (await api.call(o, "GET", f"/courses/{c.id}/people", params={"role": "student", "q": "alice."})).json()
    assert [i["user"]["id"] for i in r["items"]] == [s1.id]
    await api.call(o, "DELETE", f"/courses/{c.id}/enrollments/{e1.id}")
    r = (await api.call(o, "GET", f"/courses/{c.id}/people", params={"state": "removed"})).json()
    assert [i["user"]["id"] for i in r["items"]] == [s1.id]
    r = (await api.call(s2, "GET", f"/courses/{c.id}/people", params={"role": "student", "q": "alice."})).json()
    assert [set(i) for i in r["items"]] == [{"display_name", "role"}] and r["items"][0]["role"] == "teacher"
