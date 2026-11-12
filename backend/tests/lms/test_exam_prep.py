"""Exam prep S2 (docs/ROADMAP_EXAM_PREP.md S2): the exam-prep page of an ORT course, the student's target score, the
test library with its module filter, "From the platform" on the student home, the course's exam date.

Visibility (students of an exam-prep course only), isolation between students, release rules (no unreleased score
anywhere), goal validation inside the scale, the platform list's exclusions and fixed statement counts."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, select

from app.core.route_inventory import ROUTE_POLICIES
from app.db import session as db_session
from app.lms.core import clock
from app.lms.core.models import utcnow
from app.lms.enrollments.models import Enrollment
from app.lms.exam_prep.models import ExamGoal
from app.lms.exam_prep.schemas import EXAM_PREP_KEYS, LIBRARY_CARD_KEYS
from app.lms.grading.seeds import ORT_MAIN_V1_ID
from app.lms.home.schemas import PLATFORM_COURSE_KEYS
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import platform_org_id
from app.lms.student_view.allowlist import TEST_STUDENT_ROUTES
from tests.lms.factories import enroll, make_assessment, make_attempt, make_bank, make_course, make_item, make_section, \
    make_user
from tests.lms.gradebook_support import grade_row, graded_assessment, no_scored_hooks, publish  # noqa: F401
from tests.lms.modules_support import make_item as make_module_item, make_module
from tests.lms.access_support import give_pass
from tests.lms.org_support import make_org
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_scored_hooks")

SECTIONS = ("math_1", "math_2", "analogies", "reading", "grammar")
P = "/courses/{}/exam-prep"


# ------------------------------------------------------------------ world

class W:
    pass


def ort_world(db, *, students=1):
    ensure_platform_org(db.connection())
    db.commit()
    w = W()
    w.teacher = make_user(db, teacher_status="approved", display_name="Teacher")
    w.course = make_course(
        db, w.teacher, title={"ru": "ОРТ (рус)", "en": "ORT (Russian)"}, languages=["ru", "en"], default_language="ru",
        status="published", visibility="catalog", enrollment_mode="open", organization_id=platform_org_id(),
        template_key="ort", template_version=1, template_locked=True, published_at=utcnow(),
        listing="listed")  # step 3b: platform courses are listed
    w.students, w.enrs = [], []
    for i in range(students):
        s = make_user(db, display_name=f"S{i}")
        w.students.append(s)
        w.enrs.append(enroll(db, w.course, s))
    w.s, w.enr = w.students[0], w.enrs[0]
    return w


def exam(db, w, title="Exam", **kw):
    a, v = graded_assessment(db, w.course, w.teacher, points=10, scheme_version_id=ORT_MAIN_V1_ID, preset="ort_main",
                             title={"ru": title}, **kw)
    return a, v


def result(db, w, a, v, raw, value, *, user=None, enr=None, minutes=0, released=True, sub=None, attempt_no=1,
           answered=5):
    """A released (or not) graded ORT attempt; section results as `attempts.grading.result_json` stores them."""
    user, enr = user or w.s, enr or w.enr
    att, sub = grade_row(db, a, v, enr, user, raw, display_value=Decimal(value), scheme_version_id=ORT_MAIN_V1_ID,
                         released=released, sub=sub, attempt_no=attempt_no,
                         submitted_at=clock.now() - timedelta(days=10) + timedelta(minutes=minutes))
    att.result = {"sections": [{"pos": i + 1, "key": k, "raw": str(i + raw % 2), "possible": "5",
                                "answered": answered[i] if isinstance(answered, tuple) else answered,
                                "correct": i} for i, k in enumerate(SECTIONS)], "pending_review": 0}
    db.commit()
    return att, sub


async def page(api, user, w, ok=200):
    r = await api.call(user, "GET", P.format(w.course.id))
    assert r.status_code == ok, r.text
    return r.json()


async def library(api, user, w, **params):
    r = await api.call(user, "GET", P.format(w.course.id) + "/library", params=params)
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


# ------------------------------------------------------------------ policies and visibility

def test_routes_are_declared_and_open_to_the_test_student():
    base = "/api/v1/courses/{course_id}/exam-prep"
    for method, path in (("GET", base), ("GET", base + "/library"), ("PUT", base + "/goal"),
                         ("DELETE", base + "/goal")):
        assert ROUTE_POLICIES[(method, path)] == "course:attempt.read_own"
        assert (method, path) in TEST_STUDENT_ROUTES


async def test_only_students_of_an_exam_prep_course(db, api):
    w = ort_world(db)
    stranger = make_user(db)
    assert (await api.call(None, "GET", P.format(w.course.id))).status_code == 401
    for user in (stranger, w.teacher):  # staff keep today's course page: no exam-prep read
        r = await api.call(user, "GET", P.format(w.course.id))
        assert r.status_code == 404, r.text
    general = make_course(db, w.teacher, status="published")
    enroll(db, general, w.s)
    r = await api.call(w.s, "GET", P.format(general.id))
    assert r.status_code == 404 and r.json()["error"]["code"] == "exam_prep_not_available"
    r = await api.call(w.s, "PUT", P.format(general.id) + "/goal", json={"target_score": 100})
    assert r.status_code == 404
    # a removed student is a stranger again
    enr = db.get(Enrollment, w.enr.id)
    enr.state = "removed"
    db.commit()
    assert (await api.call(w.s, "GET", P.format(w.course.id))).status_code == 404


async def test_course_out_names_the_layout(db, api):
    w = ort_world(db)
    body = (await api.call(w.s, "GET", f"/courses/{w.course.id}")).json()
    assert body["template"]["student_layout"] == "exam_prep" and body["exam_date"] is None
    general = make_course(db, w.teacher, status="published")
    enroll(db, general, w.s)
    body = (await api.call(w.s, "GET", f"/courses/{general.id}")).json()
    assert body["template"] is None and body["exam_date"] is None


# ------------------------------------------------------------------ page

async def test_page_shape_history_latest_and_sections(db, api):
    w = ort_world(db)
    a1, v1 = exam(db, w, "One")
    a2, v2 = exam(db, w, "Two")
    _, sub = result(db, w, a1, v1, 4, "120", minutes=1)
    result(db, w, a2, v2, 5, "172", minutes=3)
    result(db, w, a1, v1, 6, "150", minutes=2, sub=sub, attempt_no=2)
    body = await page(api, w.s, w)
    assert set(body) == EXAM_PREP_KEYS
    assert [Decimal(p["value"]) for p in body["history"]] == [Decimal(120), Decimal(150), Decimal(172)]  # oldest first
    assert Decimal(body["latest"]["value"]) == 172 and body["latest"]["title"] == {"ru": "Two"}
    assert [s["key"] for s in body["sections"]] == list(SECTIONS)
    assert [Decimal(s["raw"]) for s in body["sections"]] == [Decimal(i + 1) for i in range(5)]  # raw 5: odd -> +1
    assert body["goal"]["target_score"] is None
    assert Decimal(body["goal"]["scale_min"]) == 60 and Decimal(body["goal"]["scale_max"]) == 245
    assert body["exam_date"] is None and body["library_total"] == 2
    assert body["sources"] == []  # no modules: no chips


async def test_section_rated_from_graded_answers_server_threshold(db, api):
    """STUDENT_UI_FIX_PLAN 4.3: a section bar is rated from its graded (non-blank) answers, at progress.service's
    SECTION_MIN_GRADED; points possible alone (blank items) never rate a section."""
    from app.lms.progress.service import SECTION_MIN_GRADED
    w = ort_world(db)
    a, v = exam(db, w, "One")
    n = SECTION_MIN_GRADED
    result(db, w, a, v, 4, "120", answered=(0, n - 1, n, n + 5, 1))
    body = await page(api, w.s, w)
    assert [s["rated"] for s in body["sections"]] == [False, False, True, True, False]
    assert all(Decimal(s["possible"]) == 5 for s in body["sections"])  # not a proxy for answers


async def test_unreleased_and_hidden_results_carry_no_score(db, api):
    w = ort_world(db)
    a1, v1 = exam(db, w, "Unreleased")
    a2, v2 = exam(db, w, "Never", results_policy="never")
    a3, v3 = exam(db, w, "After close", results_policy="after_close",
                  available_until=clock.now() + timedelta(days=1))
    for i, (a, v) in enumerate(((a1, v1), (a2, v2), (a3, v3))):
        result(db, w, a, v, 5, "200", minutes=i, released=(a is not a1))
    body = await page(api, w.s, w)
    assert body["history"] == [] and body["latest"] is None and body["sections"] == []
    cards = (await library(api, w.s, w))["items"]
    assert [c["status"] for c in cards] == ["done"] * 3
    assert all(c["best_value"] is None and c["best_percent"] is None for c in cards)
    # the window closes (plus grace): the after_close result becomes visible, exactly like the result page
    a3.available_until = clock.now() - timedelta(hours=1)
    db.commit()
    body = await page(api, w.s, w)
    assert [p["title"] for p in body["history"]] == [{"ru": "After close"}]
    cards = {c["id"]: c for c in (await library(api, w.s, w))["items"]}
    assert Decimal(cards[str(a3.id)]["best_value"]) == 200 and Decimal(cards[str(a3.id)]["scale_max"]) == 245
    assert cards[str(a1.id)]["best_value"] is None


async def test_students_see_only_their_own(db, api):
    w = ort_world(db, students=2)
    other, other_enr = w.students[1], w.enrs[1]
    a, v = exam(db, w)
    result(db, w, a, v, 5, "190", user=other, enr=other_enr)
    make_attempt(db, a, v, other, enrollment=other_enr, attempt_no=2)  # the other student's open attempt
    db.add(ExamGoal(user_id=other.id, course_id=w.course.id, target_score=200))
    db.commit()
    body = await page(api, w.s, w)
    assert body["history"] == [] and body["latest"] is None and body["goal"]["target_score"] is None
    assert body["next"]["kind"] == "start" and body["next"]["assessment_id"] == str(a.id)
    cards = (await library(api, w.s, w))["items"]
    assert cards[0]["status"] == "not_started" and cards[0]["attempts_used"] == 0 and cards[0]["best_value"] is None
    mine = await page(api, other, w)
    assert mine["goal"]["target_score"] == 200 and mine["next"]["kind"] == "resume"


# ------------------------------------------------------------------ goal

async def test_goal_crud_and_range(db, api):
    w = ort_world(db)
    url = P.format(w.course.id) + "/goal"
    for bad in (59, 246, -1):
        r = await api.call(w.s, "PUT", url, json={"target_score": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == "goal_out_of_range", r.text
    for bad in ({"target_score": "x"}, {"target_score": 150.5}, {}, {"target_score": 150, "extra": 1}):
        assert (await api.call(w.s, "PUT", url, json=bad)).status_code == 422
    r = await api.call(w.s, "PUT", url, json={"target_score": 200})
    assert r.status_code == 200 and r.json()["target_score"] == 200
    r = await api.call(w.s, "PUT", url, json={"target_score": 245})
    assert r.json()["target_score"] == 245
    assert (await page(api, w.s, w))["goal"]["target_score"] == 245
    assert db.execute(select(ExamGoal.target_score).where(ExamGoal.user_id == w.s.id)).scalars().all() == [245]
    assert (await api.call(w.teacher, "PUT", url, json={"target_score": 150})).status_code == 404
    assert (await api.call(w.s, "DELETE", url)).status_code == 204
    assert (await api.call(w.s, "DELETE", url)).status_code == 204  # idempotent
    assert (await page(api, w.s, w))["goal"]["target_score"] is None


# ------------------------------------------------------------------ next

async def test_next_resume_then_start_then_practice_then_retake(db, api):
    w = ort_world(db)
    give_pass(db, w.s)  # S3: practice of a platform course needs a pass (test_access.py covers the student without)
    a1, v1 = exam(db, w, "First")
    a2, v2 = exam(db, w, "Second", allowed_attempts=-1)
    a1.allowed_attempts = -1
    db.commit()
    open_att = make_attempt(db, a2, v2, w.s, enrollment=w.enr)
    nxt = (await page(api, w.s, w))["next"]
    assert nxt["kind"] == "resume" and nxt["attempt_id"] == str(open_att.id)
    open_att.status = "void"
    db.commit()
    nxt = (await page(api, w.s, w))["next"]
    assert nxt == {**nxt, "kind": "start", "assessment_id": str(a1.id)}  # library order
    _, s1 = result(db, w, a1, v1, 5, "150", minutes=1, attempt_no=2)
    nxt = (await page(api, w.s, w))["next"]
    assert nxt["kind"] == "start" and nxt["assessment_id"] == str(a2.id)
    result(db, w, a2, v2, 5, "160", minutes=2, attempt_no=3)
    # both taken; no section practice yet: the test taken longest ago
    nxt = (await page(api, w.s, w))["next"]
    assert nxt["kind"] == "retake" and nxt["assessment_id"] == str(a1.id) and nxt["last_at"]
    # a practice set of the weakest section (math_1: raw 1 of 5) comes before a retake
    bank = make_bank(db, w.course, w.teacher)
    for section_key in ("grammar", "math_1"):
        p = make_assessment(db, w.course, w.teacher, is_practice=True, title={"ru": f"Practice {section_key}"})
        sec = make_section(db, p)
        make_item(db, p, sec, kind="pick", pick_bank_id=bank.id, pick_count=3, pick_filter={"section": section_key})
        publish(db, p, w.teacher, 3)
    nxt = (await page(api, w.s, w))["next"]
    assert nxt["kind"] == "practice" and nxt["section"] == "math_1"
    # an exhausted test is never suggested again
    a1.allowed_attempts = a2.allowed_attempts = 1
    db.commit()
    for p in db.execute(select(type(a1)).where(type(a1).is_practice.is_(True))).scalars():
        p.status = "draft"
    db.commit()
    assert (await page(api, w.s, w))["next"] is None


# ------------------------------------------------------------------ library

async def test_library_sources_filter_status_and_pages(db, api):
    w = ort_world(db)
    tests = [exam(db, w, f"T{i}") for i in range(5)]
    from app.lms.assignments.models import Assignment

    def assignment_of(a):
        return db.execute(select(Assignment).where(Assignment.assessment_id == a.id)).scalar_one()

    sapat = make_module(db, w.course, w.teacher, title={"ru": "sapat"})
    coomo = make_module(db, w.course, w.teacher, title={"ru": "coomo_test"})
    hidden = make_module(db, w.course, w.teacher, title={"ru": "hidden"}, published=False)
    make_module_item(db, sapat, assignment_of(tests[0][0]))
    make_module_item(db, sapat, assignment_of(tests[1][0]))
    make_module_item(db, coomo, assignment_of(tests[1][0]))  # one test in two modules
    make_module_item(db, coomo, assignment_of(tests[2][0]))
    make_module_item(db, hidden, assignment_of(tests[3][0]))  # an unpublished module is no source
    make_module_item(db, coomo, assignment_of(tests[4][0]), published=False)  # nor an unpublished item
    draft, _ = exam(db, w, "Draft")
    draft.status = "draft"
    db.commit()
    make_attempt(db, tests[2][0], tests[2][1], w.s, enrollment=w.enr)
    result(db, w, tests[1][0], tests[1][1], 5, "180", attempt_no=2)

    body = await page(api, w.s, w)
    assert [(s["title"], s["count"]) for s in body["sources"]] == [({"ru": "sapat"}, 2), ({"ru": "coomo_test"}, 2),
                                                                   (None, 2)]
    assert body["library_total"] == 5
    everything = await library(api, w.s, w, limit=2)
    assert len(everything["items"]) == 2 and everything["next_cursor"]
    rest = await library(api, w.s, w, limit=50, cursor=everything["next_cursor"])
    ids = [c["id"] for c in everything["items"] + rest["items"]]
    assert ids == [str(t[0].id) for t in tests]  # library order, no draft
    assert set(everything["items"][0]) == LIBRARY_CARD_KEYS
    cards = {c["id"]: c for c in everything["items"] + rest["items"]}
    assert cards[str(tests[2][0].id)]["status"] == "in_progress" and cards[str(tests[2][0].id)]["attempt_id"]
    assert cards[str(tests[1][0].id)]["status"] == "done" and Decimal(cards[str(tests[1][0].id)]["best_value"]) == 180
    assert all(c["locked"] is False for c in cards.values())
    by = lambda **p: library(api, w.s, w, **p)  # noqa: E731
    assert [c["id"] for c in (await by(source=str(sapat.id)))["items"]] == [str(tests[0][0].id), str(tests[1][0].id)]
    assert [c["id"] for c in (await by(source=str(coomo.id)))["items"]] == [str(tests[1][0].id), str(tests[2][0].id)]
    assert [c["id"] for c in (await by(source="other"))["items"]] == [str(tests[3][0].id), str(tests[4][0].id)]
    assert (await by(source=str(hidden.id)))["items"] == []
    r = await api.call(w.s, "GET", P.format(w.course.id) + "/library", params={"source": "nope"})
    assert r.status_code == 422


async def test_statement_counts_are_fixed(db, api):
    def fill(n):
        w = ort_world(db)
        m = make_module(db, w.course, w.teacher, title={"ru": "m"})
        from app.lms.assignments.models import Assignment

        for i in range(n):
            a, v = exam(db, w, f"T{i}", allowed_attempts=-1)
            make_module_item(db, m, db.execute(select(Assignment).where(Assignment.assessment_id == a.id)).scalar_one())
            _, sub = result(db, w, a, v, 5, str(100 + i), minutes=i)
            result(db, w, a, v, 4, str(90 + i), minutes=i + 100, sub=sub, attempt_no=2)
        return w

    counts = {}
    for name, n in (("small", 1), ("big", 12)):
        w = fill(n)
        await page(api, w.s, w)
        await library(api, w.s, w)
        with Counter() as c:
            await page(api, w.s, w)
        with Counter() as c2:
            await library(api, w.s, w, limit=12)
        counts[name] = (len(c.statements), len(c2.statements))
    assert counts["small"] == counts["big"], counts
    assert counts["big"][0] <= 14 and counts["big"][1] <= 8, counts


# ------------------------------------------------------------------ exam date

async def test_exam_date_by_course_staff_only_on_exam_prep_courses(db, api):
    w = ort_world(db)
    url = f"/courses/{w.course.id}"
    r = await api.call(w.teacher, "PATCH", url, json={"exam_date": "2027-05-20"})
    assert r.status_code == 200, r.text
    assert r.json()["exam_date"] == "2027-05-20"
    assert (await page(api, w.s, w))["exam_date"] == "2027-05-20"
    assert (await api.call(w.s, "GET", url)).json()["exam_date"] == "2027-05-20"
    assert (await api.call(w.s, "PATCH", url, json={"exam_date": "2027-06-01"})).status_code in (403, 404)
    r = await api.call(w.teacher, "PATCH", url, json={"exam_date": "1999-01-01"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "exam_date_invalid"
    r = await api.call(w.teacher, "PATCH", url, json={"exam_date": None})
    assert r.status_code == 200 and r.json()["exam_date"] is None
    general = make_course(db, w.teacher, status="published")
    r = await api.call(w.teacher, "PATCH", f"/courses/{general.id}", json={"exam_date": "2027-05-20"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "exam_date_not_supported"


# ------------------------------------------------------------------ "From the platform" on the student home

async def test_home_lists_open_platform_courses_the_student_is_not_in(db, api):
    w = ort_world(db)
    ky = make_course(db, w.teacher, title={"ky": "ЖРТ"}, languages=["ky"], default_language="ky", status="published",
                     visibility="catalog", enrollment_mode="open", organization_id=platform_org_id(),
                     template_key="ort", template_version=1, published_at=utcnow(), listing="listed")
    unlisted = make_course(db, w.teacher, status="published", visibility="catalog", enrollment_mode="open",
                           organization_id=platform_org_id(), published_at=utcnow(), listing="blocked")
    not_listed = make_course(db, w.teacher, status="published", visibility="catalog", enrollment_mode="open",
                             organization_id=platform_org_id(), published_at=utcnow())  # step 3b: `listing` off
    private = make_course(db, w.teacher, status="published", visibility="private", enrollment_mode="open",
                          organization_id=platform_org_id(), published_at=utcnow())
    by_code = make_course(db, w.teacher, status="published", visibility="catalog", enrollment_mode="invite_code",
                          organization_id=platform_org_id(), published_at=utcnow(), listing="listed")
    draft = make_course(db, w.teacher, status="draft", visibility="catalog", enrollment_mode="open",
                        organization_id=platform_org_id())
    school = make_org(db)
    school_course = make_course(db, w.teacher, status="published", visibility="catalog", enrollment_mode="open",
                                organization_id=school.id, published_at=utcnow(), listing="listed")
    newcomer = make_user(db)
    r = await api.call(newcomer, "GET", "/me/home")
    listed = r.json()["platform_courses"]
    assert {c["id"] for c in listed} == {str(w.course.id), str(ky.id)}, listed
    assert all(set(c) == PLATFORM_COURSE_KEYS and c["is_platform_course"] for c in listed)
    assert not {unlisted.id, not_listed.id, private.id, by_code.id, draft.id, school_course.id} & {
        c["id"] for c in listed}
    # an enrolled student no longer sees it there (it is one of their courses); a removed one sees it again
    enrolled = (await api.call(w.s, "GET", "/me/home")).json()
    assert [c["id"] for c in enrolled["platform_courses"]] == [str(ky.id)]
    assert [c["id"] for c in enrolled["courses"]] == [str(w.course.id)]
    enr = db.get(Enrollment, w.enr.id)
    enr.state = "removed"
    db.commit()
    assert {c["id"] for c in (await api.call(w.s, "GET", "/me/home")).json()["platform_courses"]} == {
        str(w.course.id), str(ky.id)}
    # the one-tap join is the open join
    r = await api.call(newcomer, "POST", f"/courses/{ky.id}/join", json={})
    assert r.status_code in (200, 201), r.text
    assert [c["id"] for c in (await api.call(newcomer, "GET", "/me/home")).json()["platform_courses"]] == [
        str(w.course.id)]
    # a suspended platform organization takes its courses out
    from app.lms.organizations.models import Organization

    org = db.get(Organization, platform_org_id())
    org.status = "suspended"
    db.commit()
    assert (await api.call(newcomer, "GET", "/me/home")).json()["platform_courses"] == []
    org.status = "active"
    db.commit()
    # a test student (Student view) cannot join anything: nothing listed
    tester = make_user(db)
    tester.is_test_student = True
    db.commit()
    assert (await api.call(tester, "GET", "/me/home")).json()["platform_courses"] == []
