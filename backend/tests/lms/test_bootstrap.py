"""PERFORMANCE_AUDIT S2: `GET /me/bootstrap` is the app shell's one request. Its answer equals the parts' own routes
(`/me/lms`, `/me/home/courses?limit=50`, `/me/access`, `/me/privacy` without `requests`, the count of
`/me/invitations`, `/courses/{exam}/lesson-courses`) for a student, a teacher, an admin and a revoked teacher; it needs
no more statements than the parts together (Server-Timing); 401 without a token; listed `authenticated`; the import
warm-up imports without error.

PERFORMANCE_AUDIT P2: `?include=home` adds `home` (= `/me/home`), `exam_prep` and `activity` (= `/courses/{id}/exam-prep`
and `/courses/{id}/my/activity?days=7` of the home's exam course: `course` when it is one of the student's exam courses,
else the first) with fewer statements than the four requests it replaces; the default answer has none of the three
keys; people who teach, admins and the two-step gate get none of them; a test student gets them."""
from __future__ import annotations

import re
import sys
from datetime import timedelta

from app.core.route_inventory import ROUTE_POLICIES
from app.lms.core.models import utcnow
from app.core.warmup import WARM_MODULES, warm_up
from app.lms.core import clock
from app.lms.home.schemas import BOOTSTRAP_HOME_KEYS, BOOTSTRAP_KEYS
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


async def test_teacher_with_a_student_enrollment_gets_no_student_part(db, api):
    """Owner decision 2026-11-12 (fix round 1e): student and teacher are separate accounts; the enrolment stays but the
    person who teaches has no Learning area, so the bootstrap reads no student data for them."""
    w = world(db)
    enroll(db, w.exam, w.teacher)
    body = await check(api, w.teacher, student=False)
    assert body["student"] is None and body["me"]["has_student_enrollments"] is True


async def test_admin_gets_no_student_part(db, api):
    admin = make_user(db, platform_admin=True)
    body = await check(api, admin, student=False)
    assert body["student"] is None and body["me"]["is_platform_admin"] is True


async def test_admin_without_two_step_login_gets_only_me_under_the_requirement(db, api, monkeypatch):
    """Integration fix: with ADMIN_MFA_REQUIRED an unenrolled admin's bootstrap answers like the parts it replaced (only
    `/me/lms` is open; every other part is refused), so the shell can draw /admin/security instead of a load error."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    w = world(db)
    admin = make_user(db, platform_admin=True)
    enroll(db, w.exam, admin)  # a student enrolment (ignored for people who teach: fix round 1e)
    invite(db, admin.email)
    me = (await get(api, admin, "/me/lms")).json()
    for path in ("/me/invitations", "/me/privacy", "/me/home/courses", "/me/access", f"/courses/{w.exam.id}/lesson-courses"):
        r = await api.call(admin, "GET", path)
        assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_enrollment_required", path
    body = (await get(api, admin, "/me/bootstrap")).json()
    assert body == {"me": me, "pending_invitations": 0, "privacy": None, "student": None}
    admin.mfa_enabled_at = clock.now()  # set up: the full answer, as without the requirement
    db.commit()
    body = (await get(api, admin, "/me/bootstrap")).json()
    assert body["pending_invitations"] == 1 and body["privacy"] is not None and body["student"] is None


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


# --- PERFORMANCE_AUDIT P2 begin --- (`?include=home`)
HOME = {"include": "home"}


def exam_course(db, owner, title="ОРТ (кырг)"):
    from app.lms.organizations.ids import platform_org_id

    return make_course(
        db, owner, title={"ru": title}, languages=["ru"], default_language="ru", status="published",
        visibility="catalog", enrollment_mode="open", organization_id=platform_org_id(), template_key="ort",
        template_version=1, template_locked=True, published_at=utcnow())


async def home_parts(api, user, exam):
    """`/me/bootstrap` + the home's own reads, as the cold home asked them before P2, and their statements."""
    rs = {"boot": await get(api, user, "/me/bootstrap"), "home": await get(api, user, "/me/home"),
          "prep": await get(api, user, f"/courses/{exam}/exam-prep"),
          "activity": await get(api, user, f"/courses/{exam}/my/activity", params={"days": 7})}
    out = {**rs["boot"].json(), "home": rs["home"].json(), "exam_prep": {str(exam): rs["prep"].json()},
           "activity": {str(exam): rs["activity"].json()}}
    return out, sum(queries(r) for r in rs.values())


async def test_include_home_equals_the_parts_in_fewer_statements(db, api):
    w = world(db)
    link(db, w.lc, w.exam)
    enroll(db, w.lc, w.s)
    invite(db, w.s.email)
    expected, parts_n = await home_parts(api, w.s, w.exam.id)
    r = await get(api, w.s, "/me/bootstrap", params=HOME)
    body = r.json()
    assert set(body) == BOOTSTRAP_KEYS | BOOTSTRAP_HOME_KEYS
    assert body == expected
    # statement budget: one request instead of four, fewer statements than they needed together (here 50 against 57:
    # the user, profile and enrolment reads once), and no more than today's 50 for this world
    assert queries(r) < parts_n, (queries(r), parts_n)
    assert queries(r) <= 50, queries(r)
    default = (await get(api, w.s, "/me/bootstrap")).json()
    assert set(default) == BOOTSTRAP_KEYS and {k: body[k] for k in BOOTSTRAP_KEYS} == default


async def test_include_home_follows_the_remembered_exam_course(db, api):
    w = world(db)
    second = exam_course(db, w.admin)
    enroll(db, second, w.s)
    first = (await get(api, w.s, "/me/bootstrap", params=HOME)).json()
    exams = [c["id"] for c in first["student"]["courses"] if c["student_layout"] == "exam_prep"]
    assert len(exams) == 2 and list(first["exam_prep"]) == [exams[0]] and list(first["activity"]) == [exams[0]]
    picked = (await get(api, w.s, "/me/bootstrap", params={**HOME, "course": exams[1]})).json()
    assert list(picked["exam_prep"]) == [exams[1]] and list(picked["activity"]) == [exams[1]]
    assert picked["exam_prep"][exams[1]] == (await get(api, w.s, f"/courses/{exams[1]}/exam-prep")).json()
    # a course that is not one of the student's exam courses, or no id at all: the first, never an error
    for bad in (str(w.lc.id), "not-an-id", ""):
        body = (await get(api, w.s, "/me/bootstrap", params={**HOME, "course": bad})).json()
        assert list(body["exam_prep"]) == [exams[0]], bad


async def test_include_home_without_an_exam_course_has_the_home_only(db, api):
    s = make_user(db)
    enroll(db, make_lesson_free_course(db), s)
    body = (await get(api, s, "/me/bootstrap", params=HOME)).json()
    assert body["home"] == (await get(api, s, "/me/home")).json()
    assert body["exam_prep"] == {} and body["activity"] == {}


async def test_include_home_for_a_test_student(db, api):
    w = world(db)
    tester = make_user(db)
    tester.is_test_student = True
    enroll(db, w.exam, tester).is_test_student = True  # Student view: the test student's own course
    db.commit()
    body = (await get(api, tester, "/me/bootstrap", params=HOME)).json()
    assert body["home"] == (await get(api, tester, "/me/home")).json()
    assert body["exam_prep"] == {str(w.exam.id): (await get(api, tester, f"/courses/{w.exam.id}/exam-prep")).json()}
    assert body["pending_invitations"] == 0 and body["privacy"] is None


async def test_include_home_gives_people_who_teach_nothing_more(db, api):
    w = world(db)
    enroll(db, w.exam, w.teacher)  # a student enrolment of a teacher: still no Learning area (fix round 1e)
    admin = make_user(db, platform_admin=True)
    for user in (w.teacher, admin):
        body = (await get(api, user, "/me/bootstrap", params=HOME)).json()
        assert set(body) == BOOTSTRAP_KEYS and body["student"] is None
        assert body == (await get(api, user, "/me/bootstrap")).json()


async def test_include_home_under_the_two_step_gate_answers_only_me(db, api, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    w = world(db)
    admin = make_user(db, platform_admin=True)
    enroll(db, w.exam, admin)
    me = (await get(api, admin, "/me/lms")).json()
    body = (await get(api, admin, "/me/bootstrap", params={**HOME, "course": str(w.exam.id)})).json()
    assert body == {"me": me, "pending_invitations": 0, "privacy": None, "student": None}
# --- PERFORMANCE_AUDIT P2 end ---
