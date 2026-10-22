from types import SimpleNamespace

import pytest

from app.core.authz import A, ALL_ACTIONS, AuthzContext, decide

ALL = frozenset({
    "course.read", "course.update", "course.delete", "course.publish", "roster.read", "roster.manage",
    "content.read", "content.read_admin", "content.manage", "assessment.take", "attempt.read_own",
    "attempt.read_all", "grades.read_own", "grades.manage", "course.transfer", "course.leave",
})
ASSISTANT_PUBLISHED = ALL - {"course.delete", "course.publish", "roster.manage", "course.transfer"}
STUDENT_PUBLISHED = frozenset({
    "course.read", "content.read", "assessment.take", "attempt.read_own", "grades.read_own", "course.leave",
})
READ_ONLY = frozenset({
    "course.read", "roster.read", "content.read", "content.read_admin", "attempt.read_own", "attempt.read_all",
    "grades.read_own",
})

# Explicit expectation table, written independently of decide().
EXPECTED = {
    ("teacher", "draft"): ALL,
    ("teacher", "published"): ALL,
    ("teacher", "concluded"): READ_ONLY | {"course.publish", "course.delete", "course.transfer", "course.leave"},
    ("assistant", "draft"): ASSISTANT_PUBLISHED,
    ("assistant", "published"): ASSISTANT_PUBLISHED,
    ("assistant", "concluded"): READ_ONLY | {"course.leave"},
    ("student", "draft"): frozenset({"course.leave"}),
    ("student", "published"): STUDENT_PUBLISHED,
    ("student", "concluded"): frozenset({"course.read", "content.read", "attempt.read_own", "grades.read_own",
                                          "course.leave"}),
}


def test_action_set_is_pinned():
    assert ALL_ACTIONS == ALL


@pytest.mark.parametrize("platform_admin", [False, True])
@pytest.mark.parametrize("role", ["teacher", "assistant", "student", None])
@pytest.mark.parametrize("status", ["draft", "published", "concluded"])
def test_decide_table(role, status, platform_admin):
    if role is None:
        expected = {"course.read", "roster.read", "course.delete"} if platform_admin else set()
    else:
        expected = EXPECTED[(role, status)]
    for action in sorted(ALL):
        assert decide(role=role, course_status=status, action=action, is_platform_admin=platform_admin) is (
            action in expected
        ), (role, status, action, platform_admin)


def test_pinned_cases():
    assert decide(role="assistant", course_status="published", action=A.ROSTER_MANAGE) is False
    assert decide(role="teacher", course_status="concluded", action=A.COURSE_UPDATE) is False
    assert decide(role="teacher", course_status="concluded", action=A.COURSE_PUBLISH) is True
    assert decide(role="teacher", course_status="concluded", action=A.ROSTER_MANAGE) is False
    assert decide(role="student", course_status="draft", action=A.COURSE_READ) is False
    assert decide(role="student", course_status="draft", action=A.COURSE_LEAVE) is True
    assert decide(role="teacher", course_status="bogus", action=A.COURSE_LEAVE) is False


def test_admin_flag_without_opt_in_grants_nothing():
    admin = SimpleNamespace(role="student", is_platform_admin=True)
    assert AuthzContext(admin, db=None).is_platform_admin is False
    assert AuthzContext(admin, db=None, allow_platform_admin=True).is_platform_admin is True


def test_old_role_admin_grants_nothing():
    old = SimpleNamespace(role="admin")
    assert AuthzContext(old, db=None, allow_platform_admin=True).is_platform_admin is False


def test_cache_normalizes_string_course_ids():
    import uuid

    calls = []
    ctx = AuthzContext(SimpleNamespace(id="u"), None, lambda cid: calls.append(cid) or None)
    cid = uuid.uuid4()
    assert ctx.role_for(str(cid)) is None
    assert ctx.role_for(cid) is None  # None cached, same key for str and UUID
    assert len(calls) == 1
