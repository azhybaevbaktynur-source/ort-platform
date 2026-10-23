"""Permission matrix for every content route: route x actor x course status (design 7.5).

Expected values are written out here independently of authz.decide:
  reads  -> staff 200 (draft, published, concluded), student 403
  writes -> staff success (draft, published), 403 when concluded (read-only), student 403
  removed student, outsider, platform admin (no enrollment) -> 404; deleted course -> 404 for everyone.
"""
from types import SimpleNamespace

import pytest

from app.core.route_inventory import ROUTE_POLICIES
from app.lms.content.policies import CONTENT_POLICIES
from app.lms.core.models import utcnow
from app.lms.enrollments.models import Enrollment
from tests.lms.factories import make_bank, make_course, make_passage, make_question, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

ACTORS = ["O", "T", "AS", "S", "R", "X", "P"]
STATUSES = ["draft", "published", "concluded", "deleted"]
_USERS: dict = {}

QUESTION_CONTENT = {"type": "true_false", "stem": "changed", "data": {"correct": False}, "default_points": 1}
NEW_QUESTION = {"type": "true_false", "language": "en", "stem": "new", "data": {"correct": True}}

# name -> (method, path template, body factory(ids) or None, kind, staff success status for a write)
ROUTES = {
    "banks_list": ("GET", "/courses/{c}/banks", None, "r", 200),
    "bank_get": ("GET", "/courses/{c}/banks/{b}", None, "r", 200),
    "questions_list": ("GET", "/courses/{c}/banks/{b}/questions", None, "r", 200),
    "question_get": ("GET", "/courses/{c}/questions/{q}", None, "r", 200),
    "versions_list": ("GET", "/courses/{c}/questions/{q}/versions", None, "r", 200),
    "version_get": ("GET", "/courses/{c}/questions/{q}/versions/{v}", None, "r", 200),
    "preview": ("GET", "/courses/{c}/questions/{q}/preview", None, "r", 200),
    "translations_list": ("GET", "/courses/{c}/questions/{q}/translations", None, "r", 200),
    "passages_list": ("GET", "/courses/{c}/banks/{b}/passages", None, "r", 200),
    "passage_get": ("GET", "/courses/{c}/passages/{p}", None, "r", 200),
    "passage_versions_list": ("GET", "/courses/{c}/passages/{p}/versions", None, "r", 200),
    "passage_version_get": ("GET", "/courses/{c}/passages/{p}/versions/{pv}", None, "r", 200),
    "bank_create": ("POST", "/courses/{c}/banks", lambda i: {"title": "n"}, "w", 201),
    "bank_update": ("PATCH", "/courses/{c}/banks/{b}", lambda i: {"title": "renamed"}, "w", 200),
    "bank_delete": ("DELETE", "/courses/{c}/banks/{b}", None, "w", 204),
    "bank_restore": ("POST", "/courses/{c}/banks/{b}/restore", None, "w", 409),  # live bank: not_deleted
    "question_create": ("POST", "/courses/{c}/banks/{b}/questions", lambda i: NEW_QUESTION, "w", 201),
    "question_update": ("PATCH", "/courses/{c}/questions/{q}",
                        lambda i: {"base_version_id": i.v, "content": QUESTION_CONTENT}, "w", 200),
    "question_delete": ("DELETE", "/courses/{c}/questions/{q}", None, "w", 204),
    "question_restore": ("POST", "/courses/{c}/questions/{q}/restore", None, "w", 409),
    "question_move": ("POST", "/courses/{c}/questions/{q2}/move", lambda i: {"direction": "up"}, "w", 200),
    "question_revert": ("POST", "/courses/{c}/questions/{q}/versions/{v}/revert",
                        lambda i: {"base_version_id": i.v}, "w", 200),
    "translation_add": ("POST", "/courses/{c}/questions/{q}/translations", lambda i: {"language": "ru"}, "w", 201),
    "translation_link": ("POST", "/courses/{c}/questions/{q}/translation-link",
                         lambda i: {"question_id": i.qru}, "w", 204),
    "translation_unlink": ("DELETE", "/courses/{c}/questions/{q}/translation-link", None, "w", 204),
    "passage_create": ("POST", "/courses/{c}/banks/{b}/passages",
                       lambda i: {"language": "en", "body": "text"}, "w", 201),
    "passage_update": ("PATCH", "/courses/{c}/passages/{p}",
                       lambda i: {"base_version_id": i.pv, "body": "changed"}, "w", 200),
    "passage_delete": ("DELETE", "/courses/{c}/passages/{p}", None, "w", 204),
    "passage_restore": ("POST", "/courses/{c}/passages/{p}/restore", None, "w", 409),
    "passage_revert": ("POST", "/courses/{c}/passages/{p}/versions/{pv}/revert",
                       lambda i: {"base_version_id": i.pv}, "w", 200),
}

CASES = [pytest.param(n, st, a, id=f"{n}-{st}-{a}") for n in ROUTES for st in STATUSES for a in ACTORS]


@pytest.fixture(autouse=True)
def _reset_users():
    _USERS.clear()
    yield
    _USERS.clear()


def users(db):
    if not _USERS:
        _USERS["O"] = make_user(db, teacher_status="approved")
        _USERS["T"] = make_user(db, teacher_status="approved")
        for k in ("AS", "S", "R", "X"):
            _USERS[k] = make_user(db)
        _USERS["P"] = make_user(db, platform_admin=True, teacher_status="approved")
        for k, v in list(_USERS.items()):
            _USERS[k] = SimpleNamespace(id=v.id, email=v.email)
    return _USERS


def build(db, status):
    u = users(db)
    course = make_course(db, _owner(db, u), status="published" if status == "deleted" else status,
                         languages=["en", "ru", "ky"], default_language="en")
    db.add_all([
        Enrollment(course_id=course.id, user_id=u["T"].id, role="teacher", state="active", source="staff_add"),
        Enrollment(course_id=course.id, user_id=u["AS"].id, role="assistant", state="active", source="staff_add"),
        Enrollment(course_id=course.id, user_id=u["S"].id, role="student", state="active", source="join_code"),
        Enrollment(course_id=course.id, user_id=u["R"].id, role="student", state="removed", source="join_code"),
    ])
    db.commit()
    owner = _owner(db, u)
    bank = make_bank(db, course, owner)
    q = make_question(db, bank, owner, type="true_false", data={"correct": True}, stem="one")
    q2 = make_question(db, bank, owner, type="true_false", data={"correct": True}, stem="two")
    qru = make_question(db, bank, owner, type="true_false", data={"correct": True}, stem="ru", language="ru")
    p = make_passage(db, bank, owner)
    if status == "deleted":
        course.deleted_at = utcnow()
        course.deleted_by_id = owner.id
        db.commit()
    return course, SimpleNamespace(
        c=str(course.id), b=str(bank.id), q=str(q.id), q2=str(q2.id), qru=str(qru.id), p=str(p.id),
        v=str(q.current_version_id), pv=str(p.current_version_id),
    )


def _owner(db, u):
    from app.models.user import User

    return db.get(User, u["O"].id)


def expected(kind, ok, status, actor):
    if status == "deleted" or actor in ("R", "X", "P"):
        return 404
    if actor == "S":
        return 403
    if kind == "w" and status == "concluded":
        return 403
    return ok


def test_every_content_route_is_in_the_matrix():
    covered = {(m, "/api/v1" + t.replace("{c}", "{course_id}").replace("{b}", "{bank_id}").replace("{q2}", "{question_id}")
                .replace("{q}", "{question_id}").replace("{pv}", "{version_id}").replace("{v}", "{version_id}")
                .replace("{p}", "{passage_id}")) for m, t, *_ in ROUTES.values()}
    assert covered == set(CONTENT_POLICIES), covered ^ set(CONTENT_POLICIES)
    assert set(CONTENT_POLICIES) <= set(ROUTE_POLICIES)
    for (m, _), pol in CONTENT_POLICIES.items():
        assert pol == ("course:content.read_admin" if m == "GET" else "course:content.manage")


@pytest.mark.parametrize("name,status,actor", CASES)
async def test_matrix(db, api, name, status, actor):
    u = users(db)
    _, ids = build(db, status)
    method, tpl, body, kind, ok = ROUTES[name]
    path = tpl.format(**vars(ids))
    res = await api.call(u[actor], method, path, json=body(ids) if body else None)
    assert res.status_code == expected(kind, ok, status, actor), (res.status_code, res.text)
