"""Endpoint matrix: action x actor x course status (design 7.2). The expected table is written out here,
independently of authz.decide.

Actors: O owner, T co-teacher, AS assistant, S student, R removed student, X outsider,
P platform admin (also old role='admin') with no enrollment.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from tests.lms.s3_support import api, clean_rate_limits, db, make_course, make_user  # noqa: F401

ACTORS = ["O", "T", "AS", "S", "R", "X", "P"]
MEMBERS = ["O", "T", "AS", "S"]
STATUSES = ["draft", "published", "concluded", "deleted"]
_USERS: dict = {}


@pytest.fixture(autouse=True)
def _reset_users():
    # the LMS conftest wipes users before each test, so the actor cache must not outlive a test
    _USERS.clear()
    yield
    _USERS.clear()


def users(db):
    if not _USERS:
        _USERS["O"] = make_user(db, teacher_status="approved")
        _USERS["T"] = make_user(db, teacher_status="approved")
        for k in ("AS", "S", "R", "X", "V", "NEW"):
            _USERS[k] = make_user(db)
        _USERS["P"] = make_user(db, platform_admin=True, role="admin", teacher_status="approved")
        for k, v in list(_USERS.items()):
            _USERS[k] = SimpleNamespace(id=v.id, email=v.email)
    return _USERS


def build(db, status):
    u = users(db)
    course = make_course(db, u["O"], status="published" if status == "deleted" else status)
    rows = [
        Enrollment(course_id=course.id, user_id=u["T"].id, role="teacher", state="active", source="staff_add"),
        Enrollment(course_id=course.id, user_id=u["AS"].id, role="assistant", state="active", source="staff_add"),
        Enrollment(course_id=course.id, user_id=u["S"].id, role="student", state="active", source="join_code"),
        Enrollment(course_id=course.id, user_id=u["R"].id, role="student", state="removed", source="join_code"),
        Enrollment(course_id=course.id, user_id=u["V"].id, role="student", state="active", source="join_code"),
    ]
    db.add_all(rows)
    if status == "deleted":
        course.deleted_at = utcnow()
    db.commit()
    return course, {r.user_id: r for r in rows}


def codes(spec):
    """'O,T:200 S:403' -> {actor: code}; unlisted actors default to 404."""
    out = {a: 404 for a in ACTORS}
    for part in spec.split():
        who, code = part.split(":")
        for a in who.split(","):
            out[a] = int(code)
    return out


def members(code, only=None):
    return " ".join(f"{a}:{code}" for a in (only or MEMBERS))


# route name -> (method, path template, body factory, success status, expectation fn(status) -> spec)
def _exp_get(st):
    return "O,T,AS:200 S:403" if st == "draft" else "O,T,AS,S:200"


def _exp_title(st):
    if st in ("draft", "published"):
        return "O,T,AS:200 S:403"
    return members(403)


def _exp_limit(st):
    return "O,T:200 AS,S:403" if st in ("draft", "published") else members(403)


def _exp_transition(valid_at):
    return lambda st: f"O,T:{200 if st == valid_at else 409} AS,S:403"


def _exp_people(st):
    return "O,T,AS:200 S:403" if st == "draft" else "O,T,AS,S:200"


def _exp_manage(ok):
    return lambda st: f"O,T:{ok} AS,S:403" if st in ("draft", "published") else members(403)


ROUTES = {
    "get": ("GET", "/courses/{c}", None, _exp_get),
    "patch_title": ("PATCH", "/courses/{c}", {"title": {"en": "New"}}, _exp_title),
    "patch_limit": ("PATCH", "/courses/{c}", {"enrollment_limit": 50}, _exp_limit),
    "publish": ("POST", "/courses/{c}/publish", None, _exp_transition("draft")),
    "unpublish": ("POST", "/courses/{c}/unpublish", None, lambda st: "O,T:409 AS,S:403"),  # students exist in the matrix course: has_students (200 is in test_courses_api)
    "conclude": ("POST", "/courses/{c}/conclude", None, _exp_transition("published")),
    "reopen": ("POST", "/courses/{c}/reopen", None, _exp_transition("concluded")),
    "delete": ("DELETE", "/courses/{c}", None, lambda st: "O:204 T,AS,S:403"),
    "transfer": ("POST", "/courses/{c}/transfer-ownership", "TRANSFER", lambda st: "O:200 T,AS,S:403"),
    "regenerate": ("POST", "/courses/{c}/join-code/regenerate", None, _exp_manage(200)),
    "people": ("GET", "/courses/{c}/people", None, _exp_people),
    "add_staff": ("POST", "/courses/{c}/staff", "ADD", _exp_manage(201)),
    "change_role": ("PATCH", "/courses/{c}/enrollments/{e}", {"role": "assistant"}, _exp_manage(200)),
    "remove": ("DELETE", "/courses/{c}/enrollments/{e}", None, _exp_manage(204)),
    "leave": ("POST", "/courses/{c}/leave", None, lambda st: "O:409 T,AS,S:204"),
    "restore": ("POST", "/courses/{c}/restore", None, lambda st: "O:409"),
}

CASES = []
for name in ROUTES:
    for st in STATUSES:
        for actor in ACTORS:
            CASES.append(pytest.param(name, st, actor, id=f"{name}-{st}-{actor}"))


def expected(name, st, actor):
    if st == "deleted":
        return 200 if (name == "restore" and actor == "O") else 404
    return codes(ROUTES[name][3](st))[actor]


@pytest.mark.parametrize("name,status,actor", CASES)
async def test_matrix(db, api, name, status, actor):
    u = users(db)
    course, enr = build(db, status)
    method, tpl, body, _ = ROUTES[name]
    if body == "TRANSFER":
        body = {"new_owner_user_id": u["T"].id}
    elif body == "ADD":
        body = {"email": u["NEW"].email, "role": "assistant"}
    path = tpl.format(c=course.id, e=enr[u["V"].id].id)
    res = await api.call(u[actor], method, path, json=body)
    assert res.status_code == expected(name, status, actor), (res.status_code, res.text)
    if name == "people" and res.status_code == 200:
        item = res.json()["items"][0]
        if actor == "S":
            assert set(item) == {"display_name", "role"}
        else:
            assert "user" in item and "email" in item["user"]
    if name == "get" and res.status_code == 200:
        assert ("join_code" in res.json()) == (actor in ("O", "T", "AS"))


async def test_removed_student_cannot_use_rejoin_without_code(db, api):
    u = users(db)
    course, _ = build(db, "published")
    assert (await api.call(u["R"], "GET", f"/courses/{course.id}")).status_code == 404
