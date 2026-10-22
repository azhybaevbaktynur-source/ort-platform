"""Two teachers, three students: no cross-course leakage (design 7.3)."""
import uuid

from sqlalchemy import select

from app.lms.enrollments.models import Enrollment
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


async def world(db):
    ta, tb = teacher(db), teacher(db)
    s1, s2, s3 = make_user(db), make_user(db), make_user(db)
    ca, cb = make_course(db, ta, status="published"), make_course(db, tb, status="published")
    enroll(db, ca, s1)
    enroll(db, ca, s2)
    e_s2_b = enroll(db, cb, s2)
    e_s3_b = enroll(db, cb, s3)
    return ta, tb, s1, s2, s3, ca, cb, e_s2_b, e_s3_b


async def test_teacher_a_gets_404_on_every_course_b_route(db, api):
    ta, tb, s1, s2, s3, ca, cb, e_s2, e_s3 = await world(db)
    c = f"/courses/{cb.id}"
    calls = [
        ("GET", c, None), ("PATCH", c, {"title": {"en": "hacked"}}), ("GET", c + "/people", None),
        ("POST", c + "/staff", {"email": s1.email, "role": "assistant"}),
        ("PATCH", f"{c}/enrollments/{e_s3.id}", {"role": "assistant"}), ("DELETE", f"{c}/enrollments/{e_s3.id}", None),
        ("POST", c + "/publish", None), ("POST", c + "/unpublish", None), ("POST", c + "/conclude", None),
        ("POST", c + "/reopen", None), ("DELETE", c, None), ("POST", c + "/restore", None),
        ("POST", c + "/transfer-ownership", {"new_owner_user_id": ta.id}),
        ("POST", c + "/join-code/regenerate", None), ("POST", c + "/leave", None),
    ]
    for m, p, body in calls:
        r = await api.call(ta, m, p, json=body)
        assert r.status_code == 404, (m, p, r.status_code)
    db.expire_all()
    assert db.get(type(cb), cb.id).owner_id == tb.id and db.get(type(cb), cb.id).title == {"en": "Test course"}
    assert db.get(Enrollment, e_s3.id).state == "active"


async def test_lists_show_exactly_own_courses(db, api):
    ta, tb, s1, s2, s3, ca, cb, *_ = await world(db)

    async def ids(u):
        return {i["id"] for i in (await api.call(u, "GET", "/courses")).json()["items"]}

    assert await ids(ta) == {str(ca.id)}
    assert await ids(tb) == {str(cb.id)}
    assert await ids(s1) == {str(ca.id)}
    assert await ids(s2) == {str(ca.id), str(cb.id)}
    assert await ids(s3) == {str(cb.id)}
    roster = (await api.call(ta, "GET", f"/courses/{ca.id}/people")).json()["items"]
    assert {i["user"]["id"] for i in roster} == {ta.id, s1.id, s2.id}


async def test_anti_idor_and_ownership_guards(db, api):
    ta, tb, s1, s2, s3, ca, cb, e_s2, e_s3 = await world(db)
    r = await api.call(ta, "PATCH", f"/courses/{ca.id}/enrollments/{e_s3.id}", json={"role": "assistant"})
    assert r.status_code == 404
    r = await api.call(ta, "POST", f"/courses/{ca.id}/transfer-ownership", json={"new_owner_user_id": s1.id})
    assert r.status_code == 422
    r = await api.call(ta, "POST", f"/courses/{ca.id}/staff", json={"email": s3.email, "role": "teacher"})
    assert r.status_code == 422
    r = await api.call(ta, "POST", f"/courses/{ca.id}/transfer-ownership", json={"new_owner_user_id": tb.id})
    assert r.status_code == 422  # tb is approved but not a teacher in CA
    assert (await api.call(s1, "GET", f"/courses/{cb.id}")).status_code == 404
    assert (await api.call(s3, "GET", f"/courses/{ca.id}")).status_code == 404
    assert (await api.call(s1, "GET", f"/courses/{cb.id}/people")).status_code == 404


async def test_student_bodies_leak_neither_codes_nor_other_students(db, api):
    ta, tb, s1, s2, s3, ca, cb, *_ = await world(db)
    secrets_ = [ca.join_code, cb.join_code, s1.email, s2.email, s3.email, s1.id, s3.id, ta.email, tb.email]
    for who, forbidden in ((s1, [cb.join_code, s2.email, s3.email, s2.id, s3.id, ta.email, tb.email, ca.join_code]),
                           (s3, [ca.join_code, s1.email, s2.email, s1.id, s2.id, ta.email, tb.email, cb.join_code])):
        mine = ca if who is s1 else cb
        responses = [
            await api.call(who, "GET", "/courses"), await api.call(who, "GET", f"/courses/{mine.id}"),
            await api.call(who, "GET", f"/courses/{mine.id}/people"),
            await api.call(who, "GET", "/courses/trash"),
        ]
        for r in responses:
            assert r.status_code == 200
            for token in forbidden:
                assert token not in r.text, token
    # s2 sees both courses but still no other student or any join code
    for r in (await api.call(s2, "GET", "/courses"), await api.call(s2, "GET", f"/courses/{ca.id}"),
              await api.call(s2, "GET", f"/courses/{cb.id}/people")):
        for token in (ca.join_code, cb.join_code, s1.email, s3.email, s1.id, s3.id, ta.email, tb.email):
            assert token not in r.text
    assert uuid.UUID(str(ca.id))
