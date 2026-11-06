"""Phase 10 S6: course and organization analytics (PHASE_10_DESIGN 6): counts against fixtures, exclusions,
org isolation across trees and departments, statement budgets, pagination."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import event

from app.db import session as db_session
from app.lms.core.models import utcnow
from app.lms.grading.models import Submission
from app.lms.modules.models import ModuleProgress
from tests.lms.assignment_support import make_assignment, published_quiz
from tests.lms.factories import enroll, make_attempt, make_course, make_user
from tests.lms.modules_support import make_module
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, auth, clean_rate_limits, db, teacher  # noqa: F401
from tests.lms.attempt_support import make_quiz  # noqa: F401


def _sub(db, course, enr, assignment, state, eff=None, poss=None, late=0, assessment_id=None):
    s = Submission(course_id=course.id, assignment_id=assignment.id, assessment_id=assessment_id,
                   enrollment_id=enr.id, user_id=enr.user_id, state=state, kept_policy="highest", computed_at=utcnow(),
                   effective_points=eff, points_possible=poss, late_seconds=late)
    db.add(s)
    db.commit()
    return s


def _progress(db, enr, module, state):
    db.add(ModuleProgress(enrollment_id=enr.id, module_id=module.id, state=state, evaluated_rules_version=1,
                          evaluated_at=utcnow()))
    db.commit()


class W:
    pass


def build(db, org=None, n_students=3):
    org = org or make_org(db)
    w = W()
    w.org = org
    w.owner = teacher(db)
    add_member(db, org, w.owner, role="teacher")
    w.course = make_course(db, w.owner, organization_id=org.id, status="published")
    w.students = [make_user(db) for _ in range(n_students)]
    w.enrs = [enroll(db, w.course, u) for u in w.students]
    ts = make_user(db)
    w.ts_enr = enroll(db, w.course, ts)
    w.ts_enr.is_test_student = True
    db.commit()
    w.m1, w.m2 = make_module(db, w.course, w.owner), make_module(db, w.course, w.owner)
    s1, s2 = w.enrs[0], w.enrs[1]
    _progress(db, s1, w.m1, "completed")
    _progress(db, s1, w.m2, "completed")
    _progress(db, s2, w.m1, "completed")
    _progress(db, s2, w.m2, "started")
    _progress(db, w.ts_enr, w.m1, "completed")
    _progress(db, w.ts_enr, w.m2, "completed")
    w.past = make_assignment(db, w.course, w.owner, due_at=utcnow() - timedelta(days=1), points=Decimal("10"))
    w.future = make_assignment(db, w.course, w.owner, due_at=utcnow() + timedelta(days=5))
    _sub(db, w.course, s1, w.past, "graded", Decimal("8"), Decimal("10"), late=60)
    _sub(db, w.course, s2, w.past, "pending_review")
    _sub(db, w.course, w.ts_enr, w.past, "graded", Decimal("10"), Decimal("10"))
    return w


def _quiz(db, w):
    from tests.lms.factories import make_assessment_version

    qa = published_quiz(db, w.course, w.owner)
    from app.lms.assessments.models import Assessment
    from app.lms.assessments.models import AssessmentVersion
    from sqlalchemy import select

    q = db.get(Assessment, qa.assessment_id)
    v = db.get(AssessmentVersion, q.published_version_id)
    for enr, user_i, raw, kw in [(w.enrs[0], 0, 5, {}), (w.enrs[1], 1, 10, {}),
                                 (w.enrs[0], 0, 9, {"is_preview": True}),
                                 (w.enrs[2], 2, 7, {"status": "in_progress"}),
                                 (w.enrs[2], 2, 7, {"status": "void", "attempt_no": 2}),
                                 (w.ts_enr, None, 10, {})]:
        user = db.get(type(w.students[0]), enr.user_id)
        att = make_attempt(db, q, v, user, enrollment=enr, status=kw.pop("status", "graded"), raw_score=Decimal(raw),
                           points_possible=Decimal("10"), **kw)
    return qa, q


async def test_course_overview_counts(db, api):
    w = build(db)
    r = await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/overview")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["students"] == 3 and j["modules_total"] == 2 and j["completed_all"] == 1
    assert j["score"]["count"] == 1 and j["score"]["mean_percent"] == 80.0
    assert j["score"]["distribution"] == [0, 0, 0, 0, 0, 0, 0, 0, 1, 0]
    assert j["submissions"] == {"graded": 1, "pending_review": 1, "excused": 0, "missing": 1}


async def test_modules_and_assignments(db, api):
    w = build(db)
    r = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/modules")).json()
    rows = r["items"]
    assert [(x["completed"], x["started"], x["not_started"]) for x in rows] == [(2, 0, 1), (1, 1, 1)]
    rows = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/assignments")).json()["items"]
    past, future = rows
    assert (past["submitted"], past["graded"], past["pending_review"], past["missing"], past["late"]) == (2, 1, 1, 1, 1)
    assert past["mean_percent"] == 80.0 and past["students"] == 3
    assert future["missing"] == 0 and future["submitted"] == 0 and future["mean_percent"] is None


async def test_quizzes_exclude_preview_void_in_progress_and_test_student(db, api):
    w = build(db)
    qa, q = _quiz(db, w)
    r = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/quizzes")).json()["items"]
    assert len(r) == 1 and r[0]["assessment_id"] == str(q.id)
    assert (r[0]["attempts"], r[0]["students"], r[0]["mean_percent"]) == (2, 2, 75.0)
    # practice quizzes are absent by default
    q.is_practice = True
    db.commit()
    assert (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/quizzes")).json()["items"] == []
    pr = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/quizzes?practice=true")).json()["items"]
    assert len(pr) == 1 and pr[0]["is_practice"] is True


# ------------------------------------------------------------------ STUDENT_UI_FIX_PLAN 4.4 T1-T3

async def test_quiz_mean_is_first_attempt_and_equals_statistics_mean(db, api):
    """T1: the quizzes tab and the quiz statistics page show the same mean (first counted attempt per student)."""
    w = build(db)
    qa, q = _quiz(db, w)
    from app.lms.assessments.models import AssessmentVersion

    v = db.get(AssessmentVersion, q.published_version_id)
    # a second, better attempt of student 0 (first was 5/10): every-attempt mean would be (50+100+90)/3 = 80
    make_attempt(db, q, v, w.students[0], enrollment=w.enrs[0], status="graded", raw_score=Decimal(9),
                 points_possible=Decimal("10"), attempt_no=2)
    r = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/quizzes")).json()["items"]
    assert (r[0]["attempts"], r[0]["students"], r[0]["mean_percent"]) == (3, 2, 75.0)
    s = await api.call(w.owner, "GET", f"/courses/{w.course.id}/assessments/{q.id}/statistics")
    assert s.status_code == 200, s.text
    assert s.json()["mean_percent"] == r[0]["mean_percent"]


async def test_quiz_mean_follows_the_published_version_as_statistics(db, api):
    """T1 with two versions: the mean is the statistics page's default (published version, first attempt there)."""
    from tests.lms.factories import make_assessment_version

    w = build(db)
    qa, q = _quiz(db, w)  # v1: student 0 at 50 %, student 1 at 100 %
    v2 = make_assessment_version(db, q, w.owner)
    make_attempt(db, q, v2, w.students[0], enrollment=w.enrs[0], status="graded", raw_score=Decimal(9),
                 points_possible=Decimal("10"), attempt_no=2)
    make_attempt(db, q, v2, w.students[2], enrollment=w.enrs[2], status="graded", raw_score=Decimal(4),
                 points_possible=Decimal("10"), attempt_no=3)
    r = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/quizzes")).json()["items"]
    # v2 only: (90 + 40) / 2 = 65 (one first attempt per student across versions would give 63.3)
    assert (r[0]["attempts"], r[0]["students"], r[0]["mean_percent"]) == (4, 3, 65.0)
    s = await api.call(w.owner, "GET", f"/courses/{w.course.id}/assessments/{q.id}/statistics")
    assert s.status_code == 200, s.text
    assert s.json()["mean_percent"] == r[0]["mean_percent"]


async def test_missing_is_null_without_due_date(db, api):
    """T2: an assignment without a due date has no "missing" (null), not a confident 0."""
    w = build(db)
    make_assignment(db, w.course, w.owner, due_at=None)
    rows = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/assignments")).json()["items"]
    past, future, undated = rows
    assert past["missing"] == 1 and future["missing"] == 0 and undated["missing"] is None


async def test_module_columns_add_up(db, api):
    """T3: "not started" includes `unlocked` (open, nothing done): completed + started + not_started + locked =
    students."""
    w = build(db)
    _progress(db, w.enrs[2], w.m1, "unlocked")
    _progress(db, w.enrs[2], w.m2, "locked")
    rows = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/modules")).json()["items"]
    assert [(x["completed"], x["started"], x["not_started"], x["locked"]) for x in rows] == [(2, 0, 1, 0),
                                                                                         (1, 1, 0, 1)]
    assert all(x["completed"] + x["started"] + x["not_started"] + x["locked"] == 3 for x in rows)


async def test_course_policy_matrix(db, api):
    w = build(db)
    base = f"/courses/{w.course.id}/analytics/overview"
    assert (await api.call(w.students[0], "GET", base)).status_code == 403
    assert (await api.call(teacher(db), "GET", base)).status_code == 404
    assert (await api.call(None, "GET", base)).status_code in (401, 403)
    oa = make_user(db)
    add_member(db, w.org, oa, role="org_admin")
    assert (await api.call(oa, "GET", base)).status_code == 200


async def test_pagination(db, api):
    w = build(db)
    for _ in range(3):
        make_module(db, w.course, w.owner)
    p1 = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/modules?limit=2")).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/modules?limit=2&cursor={p1['next_cursor']}")
          ).json()
    p3 = (await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/modules?limit=2&cursor={p2['next_cursor']}")
          ).json()
    assert [len(p["items"]) for p in (p1, p2, p3)] == [2, 2, 1] and p3["next_cursor"] is None
    ids = [x["module_id"] for p in (p1, p2, p3) for x in p["items"]]
    assert len(set(ids)) == 5
    bad = await api.call(w.owner, "GET", f"/courses/{w.course.id}/analytics/modules?cursor=zzz")
    assert bad.status_code == 400 or bad.status_code == 422


# ------------------------------------------------------------------------------------------------ organizations

async def test_org_overview_counts_and_scope(db, api):
    org = make_org(db, "A")
    w = build(db, org)
    dept = make_department(db, org, "Dept")
    wd = build(db, dept)
    other = build(db, make_org(db, "B"))
    oa = make_user(db)
    add_member(db, org, oa, role="org_admin")
    j = (await api.call(oa, "GET", f"/org/{org.id}/analytics/overview")).json()
    assert j["courses"] == 2 and j["students"] == 6
    assert j["score"]["count"] == 2 and j["score"]["mean_percent"] == 80.0
    assert j["submissions"] == {"graded": 2, "pending_review": 2, "excused": 0, "missing": 2}
    rows = (await api.call(oa, "GET", f"/org/{org.id}/analytics/courses")).json()["items"]
    assert {x["course_id"] for x in rows} == {str(w.course.id), str(wd.course.id)}
    by = {x["course_id"]: x for x in rows}
    assert by[str(wd.course.id)]["department_name"] == "Dept"
    x = by[str(w.course.id)]
    assert (x["students"], x["completed_all"], x["mean_percent"], x["submitted"], x["missing"]) == (3, 1, 80.0, 2, 1)
    only = (await api.call(oa, "GET", f"/org/{org.id}/analytics/courses?department_id={dept.id}")).json()["items"]
    assert [x["course_id"] for x in only] == [str(wd.course.id)]
    # isolation: another tree and a sibling/other-tree department filter
    assert (await api.call(oa, "GET", f"/org/{other.org.id}/analytics/overview")).status_code == 404
    other_dept = make_department(db, other.org, "OD")
    r = await api.call(oa, "GET", f"/org/{org.id}/analytics/courses?department_id={other_dept.id}")
    assert r.status_code == 404
    # a child-department admin sees only its subtree and cannot read the parent
    da = make_user(db)
    add_member(db, dept, da, role="org_admin")
    assert (await api.call(da, "GET", f"/org/{dept.id}/analytics/overview")).json()["courses"] == 1
    assert (await api.call(da, "GET", f"/org/{org.id}/analytics/overview")).status_code == 404
    assert (await api.call(da, "GET", f"/org/{org.id}/analytics/courses?department_id={dept.id}")).status_code == 404
    # teachers and students of the organization are not org admins
    assert (await api.call(w.owner, "GET", f"/org/{org.id}/analytics/overview")).status_code == 404
    assert (await api.call(w.students[0], "GET", f"/org/{org.id}/analytics/overview")).status_code == 404


async def test_org_quizzes_exclude_practice_and_other_orgs(db, api):
    org = make_org(db, "A")
    w = build(db, org)
    _, q = _quiz(db, w)
    _, qp = _quiz(db, w)
    qp.is_practice = True
    other = build(db, make_org(db, "B"))
    _quiz(db, other)
    db.commit()
    oa = make_user(db)
    add_member(db, org, oa, role="org_admin")
    items = (await api.call(oa, "GET", f"/org/{org.id}/analytics/quizzes")).json()["items"]
    assert [i["assessment_id"] for i in items] == [str(q.id)]
    assert items[0]["course_id"] == str(w.course.id) and items[0]["attempts"] == 2
    assert "question" not in str(items[0]).lower()


# ------------------------------------------------------------------------------------------------ budgets

class Count:
    def __enter__(self):
        self.n = 0
        event.listen(db_session.engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *a):
        event.remove(db_session.engine, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, params, context, executemany):
        if "rate_limit_buckets" not in statement and not statement.strip().upper().startswith(("PRAGMA", "SELECT 1")):
            self.n += 1


async def _count(api, user, path):
    with Count() as c:
        r = await api.call(user, "GET", path)
    assert r.status_code == 200, r.text
    return c.n


async def test_statement_budgets_are_constant(db, api):
    org = make_org(db, "A")
    small = build(db, org, n_students=3)
    _quiz(db, small)
    oa = make_user(db)
    add_member(db, org, oa, role="org_admin")
    cp = f"/courses/{small.course.id}/analytics"
    paths = [f"{cp}/overview", f"{cp}/modules", f"{cp}/assignments", f"{cp}/quizzes",
             f"/org/{org.id}/analytics/overview", f"/org/{org.id}/analytics/courses",
             f"/org/{org.id}/analytics/quizzes"]
    users = [small.owner] * 4 + [oa] * 3
    before = [await _count(api, u, p) for u, p in zip(users, paths)]
    for _ in range(19):  # 20 courses in the org, the first course gets 20 students
        extra = build(db, org, n_students=3)
        _quiz(db, extra)
    for _ in range(18):
        enroll(db, small.course, make_user(db))
    after = [await _count(api, u, p) for u, p in zip(users, paths)]
    assert before == after, (before, after)
    assert max(after) <= 12  # includes auth lookups, after
