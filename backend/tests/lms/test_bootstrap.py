"""PERFORMANCE_AUDIT S2: `GET /me/bootstrap` is the app shell's one request. Its answer equals the parts' own routes
(`/me/lms`, `/me/home/courses?limit=50`, `/me/access`, `/me/privacy` without `requests`, the count of
`/me/invitations`, `/courses/{exam}/lesson-courses`) for a student, a teacher, an admin and a revoked teacher; it needs
no more statements than the parts together (Server-Timing); 401 without a token; listed `authenticated`; the import
warm-up imports without error."""
from __future__ import annotations

import re
import sys
from datetime import timedelta

from app.core.route_inventory import ROUTE_POLICIES
from app.core.warmup import WARM_MODULES, warm_up
from app.lms.core import clock
from app.lms.home.schemas import BOOTSTRAP_KEYS
from app.lms.invitations.service import hash_token, new_token
from app.lms.organizations.models import Invitation
from app.lms.student_view.allowlist import TEST_STUDENT_ROUTES
from tests.lms.factories import enroll, make_course, make_user
from tests.lms.modules_support import make_item, make_module, make_page
from tests.lms.org_support import make_org
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_course_link import link, world

TIMING = re.compile(r'desc="n=(\d+)"')


def queries(res) -> int:
    m = TIMING.search(res.headers["server-timing"])
    assert m, res.headers.get("server-timing")
    return int(m.group(1))


async def get(api, user, path, params=None):
    r = await api.call(user, "GET", path, params=params)
    assert r.status_code == 200, (path, r.text)
    return r


def invite(db, email):
    org = make_org(db)
    inviter = make_user(db)
    db.add(Invitation(token_hash=hash_token(new_token()), email=email, organization_id=org.id, role="teacher",
                      language="en", invited_by_id=inviter.id, expires_at=clock.now() + timedelta(days=14)))
    db.commit()


async def parts(api, user, *, student: bool, exams=()):
    """The parts' own answers and their summed statement counts."""
    rs = {"me": await get(api, user, "/me/lms"), "inv": await get(api, user, "/me/invitations"),
          "privacy": await get(api, user, "/me/privacy")}
    if student:
        rs["courses"] = await get(api, user, "/me/home/courses", params={"limit": 50})
        if exams:
            rs["access"] = await get(api, user, "/me/access")
        for e in exams:
            rs[f"lessons:{e}"] = await get(api, user, f"/courses/{e}/lesson-courses")
    privacy = rs["privacy"].json()
    privacy.pop("requests")
    out = {"me": rs["me"].json(), "pending_invitations": len(rs["inv"].json()["items"]), "privacy": privacy,
           "student": None}
    if student:
        out["student"] = {"courses": rs["courses"].json()["items"],
                          "access": rs["access"].json() if exams else None,
                          "lesson_courses": {str(e): rs[f"lessons:{e}"].json() for e in exams}}
    return out, sum(queries(r) for r in rs.values())


async def check(api, user, *, student: bool, exams=()):
    expected, parts_n = await parts(api, user, student=student, exams=exams)
    r = await get(api, user, "/me/bootstrap")
    body = r.json()
    assert set(body) == BOOTSTRAP_KEYS
    assert body == expected
    assert queries(r) <= parts_n, (queries(r), parts_n)
    return body


async def test_student_equals_the_parts(db, api):
    w = world(db)
    link(db, w.lc, w.exam)
    enroll(db, w.lc, w.s)
    mod = make_module(db, w.lc, w.admin)
    make_item(db, mod, make_page(db, w.lc, w.admin, language="ru"), requirement=("view",))
    other = make_lesson_free_course(db)
    enroll(db, other, w.s)
    invite(db, w.s.email)
    body = await check(api, w.s, student=True, exams=[w.exam.id])
    assert body["pending_invitations"] == 1
    assert {c["id"] for c in body["student"]["courses"]} == {str(w.exam.id), str(w.lc.id), str(other.id)}
    rows = body["student"]["lesson_courses"][str(w.exam.id)]
    assert [x["id"] for x in rows] == [str(w.lc.id)] and rows[0]["enrolled"] is True
    assert body["student"]["access"] is not None
    assert body["me"]["has_student_enrollments"] is True


def make_lesson_free_course(db):
    owner = make_user(db, teacher_status="approved")
    return make_course(db, owner, title={"en": "General"}, status="published")


async def test_student_without_exam_course_has_no_pass_and_no_lessons(db, api):
    s = make_user(db)
    enroll(db, make_lesson_free_course(db), s)
    body = await check(api, s, student=True)
    assert body["student"]["access"] is None and body["student"]["lesson_courses"] == {}
    assert len(body["student"]["courses"]) == 1


async def test_teacher_without_enrollments_gets_no_student_part(db, api):
    t = make_user(db, teacher_status="approved")
    make_course(db, t, title={"en": "Mine"})
    invite(db, t.email)
    body = await check(api, t, student=False)
    assert body["student"] is None and body["me"]["is_teacher"] is True and body["pending_invitations"] == 1


async def test_teacher_who_also_learns_gets_the_student_part(db, api):
    w = world(db)
    enroll(db, w.exam, w.teacher)
    body = await check(api, w.teacher, student=True, exams=[w.exam.id])
    assert [c["id"] for c in body["student"]["courses"]] == [str(w.exam.id)]


async def test_admin_gets_no_student_part(db, api):
    admin = make_user(db, platform_admin=True)
    body = await check(api, admin, student=False)
    assert body["student"] is None and body["me"]["is_platform_admin"] is True


async def test_revoked_teacher_is_shown_as_a_student(db, api):
    u = make_user(db, teacher_status="revoked")
    body = await check(api, u, student=True)
    assert body["me"]["teacher_status"] == "revoked" and body["student"]["courses"] == []


async def test_requires_a_token(api):
    r = await api.call(None, "GET", "/me/bootstrap")
    assert r.status_code == 401


def test_route_is_listed_and_open_to_student_view():
    assert ROUTE_POLICIES[("GET", "/api/v1/me/bootstrap")] == "authenticated"
    assert ("GET", "/api/v1/me/bootstrap") in TEST_STUDENT_ROUTES


def test_warm_up_imports_without_error():
    assert warm_up() == list(WARM_MODULES)
    assert all(name in sys.modules for name in WARM_MODULES)
