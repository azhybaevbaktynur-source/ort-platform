"""Phase 6b S6a: `GET /me/home` (PHASE_6_DESIGN 8.4): shape, server limits (3/3/3/10), ordering, released-only
results, suspended organizations, pending invitations, isolation and a fixed statement count."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.core.route_inventory import ROUTE_POLICIES
from app.db import session as db_session
from app.lms.core import clock
from app.lms.home.schemas import COURSE_KEYS, HOME_KEYS, IN_PROGRESS_KEYS, NEXT_UP_KEYS, RESULT_KEYS
from app.lms.invitations.service import hash_token, new_token
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import platform_org_id
from app.lms.organizations.models import Invitation
from tests.lms.factories import enroll, make_attempt, make_course, make_user
from tests.lms.gradebook_support import grade_row, graded_assessment, no_scored_hooks  # noqa: F401
from tests.lms.org_support import make_org
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_scored_hooks")

FORBIDDEN = {"join_code", "email", "user_id", "raw_score", "raw_points", "effective_points", "points_possible",
             "correct", "answer_key", "key", "enrollment_id", "override_reason", "settings"}


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


def now():
    return clock.now()


def teacher(db, name="Teacher"):
    return make_user(db, teacher_status="approved", display_name=name)


def course(db, owner, title="Course", status="published", **kw):
    return make_course(db, owner, title={"en": title, "ru": title + " ru"}, status=status, **kw)


def assessment(db, c, owner, **kw):
    kw.setdefault("allowed_attempts", 1)
    return graded_assessment(db, c, owner, **kw)


async def home(api, user):
    r = await api.call(user, "GET", "/me/home")
    assert r.status_code == 200, r.text
    return r.json()


class Counter:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        event.listen(db_session.engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *a):
        event.remove(db_session.engine, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, params, context, executemany):
        if "rate_limit_buckets" in statement or statement.strip().upper().startswith(("PRAGMA", "SELECT 1")):
            return
        self.statements.append(statement)


# ------------------------------------------------------------------ policy, auth, shape

def test_route_policy_declared():
    assert ROUTE_POLICIES[("GET", "/api/v1/me/home")] == "authenticated"


async def test_needs_login(db, api):
    assert (await api.call(None, "GET", "/me/home")).status_code == 401


async def test_empty_home(db, api):
    body = await home(api, make_user(db))
    assert set(body) == HOME_KEYS
    assert body == {"in_progress": [], "next_up": [], "latest_results": [], "courses": [], "courses_total": 0,
                    "pending_invitations": 0}


async def test_full_shape_and_no_private_fields(db, api):
    t = teacher(db)
    s = make_user(db, display_name="Student")
    c = course(db, t)
    enr = enroll(db, c, s)
    a1, v1 = assessment(db, c, t, due_at=now() + timedelta(days=1))
    a2, v2 = assessment(db, c, t)
    a3, v3 = assessment(db, c, t, allowed_attempts=-1)
    make_attempt(db, a2, v2, s, enrollment=enr)
    grade_row(db, a3, v3, enr, s, 7)
    body = await home(api, s)
    assert set(body) == HOME_KEYS
    assert [set(x) for x in body["in_progress"]] == [IN_PROGRESS_KEYS]
    assert {frozenset(x) for x in body["next_up"]} == {NEXT_UP_KEYS}
    assert [set(x) for x in body["latest_results"]] == [RESULT_KEYS]
    assert [set(x) for x in body["courses"]] == [COURSE_KEYS]
    assert not (set(walk_keys(body)) & FORBIDDEN), set(walk_keys(body)) & FORBIDDEN
    assert body["in_progress"][0]["assessment_id"] == str(a2.id)
    assert body["in_progress"][0]["course_title"] == {"en": "Course", "ru": "Course ru"}  # localized dicts
    # a1 (due) first, then a3 (unlimited, one attempt used); a2 has an open attempt -> only under in_progress
    assert [x["assessment_id"] for x in body["next_up"]] == [str(a1.id), str(a3.id)]
    assert body["next_up"][0]["attempts_left"] == 1 and body["next_up"][1]["attempts_left"] is None
    res = body["latest_results"][0]
    assert res["assessment_id"] == str(a3.id) and Decimal(res["display_value"]) == Decimal("70.00")
    assert res["scheme_type"] == "percent" and res["is_personal_best"] is False
    crs = body["courses"][0]
    assert crs["id"] == str(c.id) and crs["owner_display_name"] == "Teacher" and crs["in_progress"] is True
    assert crs["is_platform_course"] is False and crs["next_due_at"] is not None
    assert body["courses_total"] == 1


# ------------------------------------------------------------------ limits and ordering

async def test_server_limits(db, api):
    t = teacher(db)
    s = make_user(db)
    courses = [course(db, t, title=f"C{i}") for i in range(12)]
    for c in courses:
        enroll(db, c, s)
    for i, c in enumerate(courses[:5]):
        a, v = assessment(db, c, t, allowed_attempts=3)
        make_attempt(db, a, v, s)
        a, v = assessment(db, c, t)
        grade_row(db, a, v, s_enr(db, c, s), s, 5)
        assessment(db, c, t)
    body = await home(api, s)
    assert len(body["in_progress"]) == 3 and len(body["next_up"]) == 3 and len(body["latest_results"]) == 3
    assert len(body["courses"]) == 10 and body["courses_total"] == 12
    # courses newest first
    assert [x["id"] for x in body["courses"]] == [str(c.id) for c in reversed(courses)][:10]


def s_enr(db, c, s):
    from sqlalchemy import select

    from app.lms.enrollments.models import Enrollment
    return db.execute(select(Enrollment).where(Enrollment.course_id == c.id, Enrollment.user_id == s.id)).scalar_one()


async def test_in_progress_newest_first_and_previews_hidden(db, api):
    t = teacher(db)
    s = make_user(db)
    c = course(db, t)
    enr = enroll(db, c, s)
    ids = []
    for i in range(4):
        a, v = assessment(db, c, t)
        ids.append(make_attempt(db, a, v, s, enrollment=enr, started_at=now() - timedelta(hours=10 - i)).id)
    a, v = assessment(db, c, t)
    make_attempt(db, a, v, s, enrollment=enr, is_preview=True, started_at=now())
    body = await home(api, s)
    assert [x["attempt_id"] for x in body["in_progress"]] == [str(i) for i in reversed(ids)][:3]


async def test_next_up_order_and_filters(db, api):
    t = teacher(db)
    s = make_user(db)
    c = course(db, t)
    enr = enroll(db, c, s)
    n = now()
    late, _ = assessment(db, c, t, due_at=n + timedelta(days=5))
    soon, _ = assessment(db, c, t, due_at=n + timedelta(days=1))
    nodue_until, _ = assessment(db, c, t, available_until=n + timedelta(days=2))
    nodue, _ = assessment(db, c, t)
    later, _ = assessment(db, c, t, available_from=n + timedelta(days=3), due_at=n + timedelta(days=9))
    # excluded: closed, exhausted, draft, deleted, concluded course
    assessment(db, c, t, available_until=n - timedelta(minutes=1))
    ex, exv = assessment(db, c, t, allowed_attempts=1)
    make_attempt(db, ex, exv, s, enrollment=enr, status="graded", submitted_at=n)
    from tests.lms.factories import make_assessment
    make_assessment(db, c, t)  # draft
    gone, _ = assessment(db, c, t)
    gone.deleted_at = n
    db.commit()
    concluded = course(db, t, status="concluded")
    enroll(db, concluded, s)
    assessment(db, concluded, t, due_at=n + timedelta(hours=1))

    body = await home(api, s)
    assert [x["assessment_id"] for x in body["next_up"]] == [str(soon.id), str(late.id), str(later.id)]
    # with the due ones done, undated ones follow: available_until first, then neither
    for a in (soon, late, later):
        a.deleted_at = n
    db.commit()
    body = await home(api, s)
    assert [x["assessment_id"] for x in body["next_up"]] == [str(nodue_until.id), str(nodue.id)]
    concluded_row = next(x for x in body["courses"] if x["id"] == str(concluded.id))
    assert concluded_row["next_due_at"] is None


async def test_voided_attempts_do_not_count(db, api):
    t = teacher(db)
    s = make_user(db)
    c = course(db, t)
    enr = enroll(db, c, s)
    a, v = assessment(db, c, t, allowed_attempts=2)
    make_attempt(db, a, v, s, enrollment=enr, status="void", submitted_at=now())
    make_attempt(db, a, v, s, enrollment=enr, status="graded", attempt_no=2, submitted_at=now())
    body = await home(api, s)
    assert body["next_up"][0]["attempts_left"] == 1


# ------------------------------------------------------------------ latest results

async def test_latest_results_released_and_visible_only(db, api):
    t = teacher(db)
    s = make_user(db)
    c = course(db, t)
    enr = enroll(db, c, s)
    n = now()
    shown = []
    for i in range(2):
        a, v = assessment(db, c, t)
        grade_row(db, a, v, enr, s, 5 + i, released_at=n - timedelta(hours=5 - i))
        shown.append(a)
    a, v = assessment(db, c, t)
    grade_row(db, a, v, enr, s, 9, released=False)  # manual release pending
    a, v = assessment(db, c, t, results_policy="never")
    grade_row(db, a, v, enr, s, 9)
    a, v = assessment(db, c, t, results_policy="after_close", available_until=n + timedelta(days=1))
    grade_row(db, a, v, enr, s, 9)  # window still open
    a, v = assessment(db, c, t)
    grade_row(db, a, v, enr, s, 9, state="pending_review")
    closed, cv = assessment(db, c, t, results_policy="after_close", available_until=n - timedelta(hours=1))
    grade_row(db, closed, cv, enr, s, 4, released_at=n - timedelta(hours=1))
    body = await home(api, s)
    assert [x["assessment_id"] for x in body["latest_results"]] == [str(closed.id), str(shown[1].id), str(shown[0].id)]
    # after_close with another student still in progress: hidden again (same rule as /grades/mine)
    other = make_user(db)
    make_attempt(db, closed, cv, other, enrollment=enroll(db, c, other))
    body = await home(api, s)
    assert [x["assessment_id"] for x in body["latest_results"]] == [str(shown[1].id), str(shown[0].id)]


async def test_personal_best(db, api):
    t = teacher(db)
    s = make_user(db)
    c = course(db, t)
    enr = enroll(db, c, s)
    n = now()

    def two(kept_raw, other_raw, i, kept_second=True):
        a, v = assessment(db, c, t, allowed_attempts=3)
        first, sub = grade_row(db, a, v, enr, s, other_raw if kept_second else kept_raw, attempt_no=1,
                               released_at=n - timedelta(minutes=i))
        second, _ = grade_row(db, a, v, enr, s, kept_raw if kept_second else other_raw, attempt_no=2, sub=sub)
        sub.kept_attempt_id = second.id if kept_second else first.id
        db.commit()
        return a

    best = two(8, 5, 1)
    tie = two(5, 5, 2)
    worse = two(3, 6, 3)  # policy "latest": kept is lower than another attempt
    single, sv = assessment(db, c, t)
    grade_row(db, single, sv, enr, s, 10, released_at=n - timedelta(minutes=4))
    body = await home(api, s)
    got = {x["assessment_id"]: x["is_personal_best"] for x in body["latest_results"]}
    assert got == {str(best.id): True, str(tie.id): False, str(worse.id): False}
    best.deleted_at = n
    db.commit()
    got = {x["assessment_id"]: x["is_personal_best"] for x in (await home(api, s))["latest_results"]}
    assert got == {str(tie.id): False, str(worse.id): False, str(single.id): False}


# ------------------------------------------------------------------ organizations, courses

async def test_suspended_org_lists_course_but_nothing_to_start(db, api):
    t = teacher(db)
    s = make_user(db)
    org = make_org(db, "Paused", status="suspended")
    c = course(db, t, organization_id=org.id)
    enr = enroll(db, c, s)
    a, v = assessment(db, c, t, due_at=now() + timedelta(days=1))
    done, dv = assessment(db, c, t)
    grade_row(db, done, dv, enr, s, 6)
    body = await home(api, s)
    assert body["next_up"] == []
    assert [x["id"] for x in body["courses"]] == [str(c.id)] and body["courses"][0]["next_due_at"] is None
    assert [x["assessment_id"] for x in body["latest_results"]] == [str(done.id)]  # results stay readable
    org.status = "active"
    db.commit()
    body = await home(api, s)
    assert [x["assessment_id"] for x in body["next_up"]] == [str(a.id)] and body["courses"][0]["next_due_at"]


async def test_platform_course_flag_and_owner_name(db, api):
    ensure_platform_org(db.connection())
    db.commit()
    t = teacher(db, name=None)
    s = make_user(db)
    plat = course(db, t, organization_id=platform_org_id())
    own = course(db, t)
    enroll(db, plat, s)
    enroll(db, own, s)
    rows = {x["id"]: x for x in (await home(api, s))["courses"]}
    assert rows[str(plat.id)]["is_platform_course"] is True and rows[str(own.id)]["is_platform_course"] is False
    assert rows[str(own.id)]["owner_display_name"] == "—"  # never the owner's email


async def test_only_active_student_enrollments(db, api):
    t = teacher(db)
    s = make_user(db, teacher_status="approved")
    mine = course(db, t, title="Mine")
    enroll(db, mine, s)
    teaching = course(db, s, title="Teaching")  # s owns it (teacher enrollment)
    assessment(db, teaching, s)
    removed = course(db, t, title="Removed")
    enroll(db, removed, s, state="removed")
    assessment(db, removed, t)
    draft = course(db, t, title="Draft", status="draft")
    enroll(db, draft, s)
    deleted = course(db, t, title="Deleted")
    enroll(db, deleted, s)
    deleted.deleted_at = now()
    db.commit()
    body = await home(api, s)
    assert [x["id"] for x in body["courses"]] == [str(mine.id)] and body["courses_total"] == 1
    assert body["next_up"] == []


# ------------------------------------------------------------------ invitations

def _invite(db, org, inviter, email, **kw):
    fields = dict(token_hash=hash_token(new_token()), email=email, organization_id=org.id, role="teacher",
                  language="en", invited_by_id=inviter.id, expires_at=now() + timedelta(days=14))
    fields.update(kw)
    inv = Invitation(**fields)
    db.add(inv)
    db.commit()
    return inv


async def test_pending_invitations_count(db, api):
    admin = make_user(db)
    s = make_user(db, email=f"Mixed.{uuid.uuid4().hex[:6]}@Test.example")
    org = make_org(db)
    org2 = make_org(db)
    email = s.email.lower()
    _invite(db, org, admin, email)
    _invite(db, org2, admin, email, role="org_admin")
    _invite(db, org, admin, email, revoked_at=now())
    _invite(db, org, admin, email, expires_at=now() - timedelta(minutes=1))
    _invite(db, org, admin, email, accepted_at=now(), accepted_user_id=s.id)
    _invite(db, org, admin, "someone.else@test.example")
    gone = make_org(db)
    _invite(db, gone, admin, email)
    gone.deleted_at = now()
    db.commit()
    assert (await home(api, s))["pending_invitations"] == 2


# ------------------------------------------------------------------ isolation

async def test_other_students_data_never_appears(db, api):
    t = teacher(db)
    s, other = make_user(db), make_user(db)
    c = course(db, t)
    enr = enroll(db, c, s)
    oenr = enroll(db, c, other)
    theirs = course(db, t, title="Theirs")
    tenr = enroll(db, theirs, other)
    a, v = assessment(db, c, t, allowed_attempts=2)
    make_attempt(db, a, v, other, enrollment=oenr)
    b, bv = assessment(db, c, t)
    grade_row(db, b, bv, oenr, other, 9)
    ta, tv = assessment(db, theirs, t)
    grade_row(db, ta, tv, tenr, other, 9)
    body = await home(api, s)
    assert body["in_progress"] == [] and body["latest_results"] == []
    assert [x["id"] for x in body["courses"]] == [str(c.id)] and body["courses"][0]["in_progress"] is False
    # the other student's attempts do not use up the caller's attempts
    assert {x["assessment_id"]: x["attempts_left"] for x in body["next_up"]} == {str(a.id): 2, str(b.id): 1}
    assert enr.id != oenr.id


# ------------------------------------------------------------------ statement budget

def _fill(db, n_courses, n_assessments):
    t = teacher(db)
    s = make_user(db)
    for i in range(n_courses):
        c = course(db, t, title=f"C{i}")
        enr = enroll(db, c, s)
        for j in range(n_assessments):
            a, v = assessment(db, c, t, allowed_attempts=3, due_at=now() + timedelta(days=j + 1))
            if j % 3 == 0:
                make_attempt(db, a, v, s, enrollment=enr)
            elif j % 3 == 1:
                grade_row(db, a, v, enr, s, j % 10, attempt_no=1)
    return s


async def test_statement_count_is_fixed(db, api):
    small = _fill(db, 1, 3)
    big = _fill(db, 14, 6)
    counts = {}
    for name, user in (("small", small), ("big", big)):
        await home(api, user)
        with Counter() as c:
            body = await home(api, user)
        if name == "big":
            assert len(body["courses"]) == 10 and body["courses_total"] == 14
            assert len(body["in_progress"]) == 3 and len(body["next_up"]) == 3 and len(body["latest_results"]) == 3
        counts[name] = len(c.statements)
        # user, courses (+total, in_progress), next_due, in_progress, next_up, results, attempts, invitations
        assert counts[name] <= 8, "\n".join(st[:120] for st in c.statements)
    assert counts["small"] == counts["big"], counts
