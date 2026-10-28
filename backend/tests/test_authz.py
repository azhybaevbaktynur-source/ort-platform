from types import SimpleNamespace

import pytest

from app.core.authz import (
    A, ALL_ACTIONS, AuthzContext, can, decide, require,
)
from app.lms.core.errors import Forbidden, NotFound
from app.lms.core.models import utcnow

T, AS, S = "teacher", "assistant", "student"


@pytest.mark.parametrize("role,status,action,expected", [
    (T, "draft", A.COURSE_UPDATE, True),
    (AS, "draft", A.CONTENT_MANAGE, True),
    (AS, "draft", A.COURSE_PUBLISH, False),
    (S, "draft", A.COURSE_READ, False),
    (S, "draft", A.COURSE_LEAVE, True),
    (S, "published", A.COURSE_READ, True),
    (S, "published", A.ASSESSMENT_TAKE, True),
    (S, "published", A.CONTENT_READ_ADMIN, False),
    (S, "published", A.GRADES_MANAGE, False),
    (S, "published", A.ATTEMPT_READ_ALL, False),
    (AS, "published", A.COURSE_DELETE, False),
    (AS, "published", A.ROSTER_MANAGE, False),
    (AS, "published", A.GRADES_MANAGE, True),
    (T, "published", A.COURSE_DELETE, True),
    (T, "concluded", A.COURSE_READ, True),
    (T, "concluded", A.ATTEMPT_READ_ALL, True),
    (T, "concluded", A.CONTENT_MANAGE, False),
    (T, "concluded", A.GRADES_MANAGE, False),
    (S, "concluded", A.GRADES_READ_OWN, True),
    (S, "concluded", A.ATTEMPT_READ_OWN, True),
    (S, "concluded", A.ASSESSMENT_TAKE, False),
    (T, "published", "nope.action", False),
    (None, "published", A.COURSE_READ, False),
    (T, "weird", A.COURSE_READ, False),
])
def test_decide(role, status, action, expected):
    assert decide(role=role, course_status=status, action=action) is expected


def test_decide_platform_admin():
    for st in ("draft", "published", "concluded"):
        assert decide(role=None, course_status=st, action=A.COURSE_READ, is_platform_admin=True)
        assert decide(role=None, course_status=st, action=A.COURSE_DELETE, is_platform_admin=True)
        assert not decide(role=None, course_status=st, action=A.CONTENT_MANAGE, is_platform_admin=True)
        assert not decide(role=None, course_status=st, action=A.GRADES_READ_OWN, is_platform_admin=True)
    assert not decide(role=None, course_status="draft", action="x", is_platform_admin=True)


def test_teacher_has_all():
    # Phase 7a: staff never hand in; Phase 8a: staff never record module progress
    for a in ALL_ACTIONS - {A.ASSIGNMENT_SUBMIT, A.PROGRESS_RECORD}:
        assert decide(role=T, course_status="published", action=a)
    assert not decide(role=T, course_status="published", action=A.ASSIGNMENT_SUBMIT)
    assert not decide(role=T, course_status="published", action=A.PROGRESS_RECORD)


def _ctx(role, user=None):
    ctx = AuthzContext(user or SimpleNamespace(role="student"), db=None, allow_platform_admin=True)
    ctx.role_resolver = lambda cid: role
    return ctx


def _course(status="published", deleted=False):
    return SimpleNamespace(id="c1", status=status, deleted_at=utcnow() if deleted else None)


def test_require_outcomes():
    require(_ctx(S), A.COURSE_READ, _course())
    with pytest.raises(NotFound):
        require(_ctx(None), A.COURSE_READ, _course())
    with pytest.raises(NotFound):
        require(_ctx(None), A.COURSE_UPDATE, _course("draft"))
    with pytest.raises(Forbidden):
        require(_ctx(S), A.GRADES_MANAGE, _course())
    with pytest.raises(NotFound):
        require(_ctx(T), A.COURSE_READ, _course(deleted=True))
    assert can(_ctx(T), A.COURSE_READ, _course(deleted=True)) is False


def test_require_platform_admin():
    admin = SimpleNamespace(role="student", is_platform_admin=True)
    require(_ctx(None, admin), A.COURSE_READ, _course("draft"))
    with pytest.raises(NotFound):
        require(_ctx(None, admin), A.CONTENT_MANAGE, _course())
    assert _ctx(None, admin).is_platform_admin
    # the old role column grants nothing, and the context must opt in to admin power
    assert not _ctx(None, SimpleNamespace(role="admin")).is_platform_admin
    with pytest.raises(NotFound):
        require(_ctx(None, SimpleNamespace(role="admin")), A.COURSE_READ, _course("draft"))
    assert not AuthzContext(admin, db=None).is_platform_admin


def test_enrollment_cache():
    calls = []
    ctx = AuthzContext(SimpleNamespace(role="student"), db=None, role_resolver=lambda c: calls.append(c) or S)
    c = _course()
    can(ctx, A.COURSE_READ, c)
    can(ctx, A.CONTENT_READ, c)
    assert calls == ["c1"]


def test_default_resolver_none():
    ctx = AuthzContext(SimpleNamespace(role="student"), db=None)
    assert ctx.role_for("x") is None
