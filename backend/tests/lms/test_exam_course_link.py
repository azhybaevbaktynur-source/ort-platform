"""Lesson courses linked to an exam course (docs/phases/TEACHER_TO_STUDENT_MAP.md 2.2-2.3, slice S1).

`courses.exam_course_id`: set by platform admins only, a platform lesson course without a template -> a live platform
exam-prep course; null clears. `GET /courses/{exam}/lesson-courses`: enrolled or staff of the exam course, published
live lesson courses only, an allow-listed shape (no join code), a fixed statement count. ORT courses get no link."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.core.route_inventory import ROUTE_POLICIES
from app.db import session as db_session
from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.modules.models import ItemRequirementStatus, ModuleProgress
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import platform_org_id
from app.lms.student_view.allowlist import TEST_STUDENT_ROUTES
from tests.lms.factories import enroll, make_course, make_user
from tests.lms.modules_support import make_item, make_module, make_page
from tests.lms.org_support import make_org
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

LESSON_KEYS = {"id", "title", "cover_url", "is_platform_course", "lessons_count", "duration_s", "enrolled",
               "progress", "has_paid_modules", "next_item"}


class W:
    pass


def world(db):
    ensure_platform_org(db.connection())
    db.commit()
    w = W()
    w.admin = make_user(db, platform_admin=True, teacher_status="approved", display_name="Admin")
    w.teacher = make_user(db, teacher_status="approved", display_name="Teacher")
    w.s = make_user(db, display_name="Student")
    w.exam = make_course(
        db, w.admin, title={"ru": "ОРТ (рус)"}, languages=["ru"], default_language="ru", status="published",
        visibility="catalog", enrollment_mode="open", organization_id=platform_org_id(), template_key="ort",
        template_version=1, template_locked=True, published_at=utcnow())
    w.enr_exam = enroll(db, w.exam, w.s)
    w.lc = lesson_course(db, w.admin, "Masterclass")
    return w


def lesson_course(db, owner, title, **kw):
    fields = dict(title={"ru": title}, languages=["ru"], default_language="ru", status="published",
                  visibility="private", enrollment_mode="open", organization_id=platform_org_id(),
                  published_at=utcnow())
    fields.update(kw)
    return make_course(db, owner, **fields)


async def patch(api, user, course, value):
    return await api.call(user, "PATCH", f"/courses/{course.id}",
                          json={"exam_course_id": str(value) if value is not None else None})


def link(db, lc, exam):
    lc.exam_course_id = exam.id
    db.commit()


# ------------------------------------------------------------------ the link (PATCH /courses/{id})

async def test_admin_links_and_clears(db, api):
    w = world(db)
    r = await patch(api, w.admin, w.lc, w.exam.id)
    assert r.status_code == 200, r.text
    assert r.json()["exam_course_id"] == str(w.exam.id)
    db.refresh(w.lc)
    assert w.lc.exam_course_id == w.exam.id
    # every course shape carries it (staff here; a student of the lesson course too)
    enroll(db, w.lc, w.s)
    assert (await api.call(w.admin, "GET", f"/courses/{w.lc.id}")).json()["exam_course_id"] == str(w.exam.id)
    assert (await api.call(w.s, "GET", f"/courses/{w.lc.id}")).json()["exam_course_id"] == str(w.exam.id)
    r = await patch(api, w.admin, w.lc, None)
    assert r.status_code == 200 and r.json()["exam_course_id"] is None
    db.refresh(w.lc)
    assert w.lc.exam_course_id is None


async def test_teacher_cannot_link(db, api):
    w = world(db)
    mine = lesson_course(db, w.teacher, "Teacher masterclass")
    r = await patch(api, w.teacher, mine, w.exam.id)
    assert r.status_code == 422 and r.json()["error"]["code"] == "exam_link_forbidden", r.text
    # resending the current value is a no-op for anyone with course.update
    r = await patch(api, w.teacher, mine, None)
    assert r.status_code == 200, r.text
    link(db, mine, w.exam)
    r = await patch(api, w.teacher, mine, None)
    assert r.status_code == 422 and r.json()["error"]["code"] == "exam_link_forbidden"


async def test_only_platform_courses_without_template(db, api):
    w = world(db)
    school = make_org(db)
    elsewhere = lesson_course(db, w.admin, "School course", organization_id=school.id)
    r = await patch(api, w.admin, elsewhere, w.exam.id)
    assert r.status_code == 422 and r.json()["error"]["code"] == "exam_link_not_allowed", r.text
    other_exam = make_course(
        db, w.admin, title={"ru": "ОРТ 2"}, languages=["ru"], default_language="ru", status="published",
        organization_id=platform_org_id(), template_key="ort", template_version=1, template_locked=False)
    r = await patch(api, w.admin, other_exam, w.exam.id)
    assert r.status_code == 422 and r.json()["error"]["code"] == "exam_link_not_allowed", r.text


async def test_target_must_be_a_live_platform_exam_course(db, api):
    w = world(db)
    plain = lesson_course(db, w.admin, "Plain")
    school_exam = make_course(db, w.admin, title={"ru": "Школа ОРТ"}, languages=["ru"], default_language="ru",
                              organization_id=make_org(db).id, template_key="ort", template_version=1)
    gone = make_course(db, w.admin, title={"ru": "Удалён"}, languages=["ru"], default_language="ru",
                       organization_id=platform_org_id(), template_key="ort", template_version=1,
                       deleted_at=utcnow())
    for target in (plain.id, school_exam.id, gone.id, uuid.uuid4(), w.lc.id):
        r = await patch(api, w.admin, w.lc, target)
        assert r.status_code == 422 and r.json()["error"]["code"] == "exam_link_target_invalid", (target, r.text)
    db.refresh(w.lc)
    assert w.lc.exam_course_id is None


def test_database_refuses_a_self_link(db):
    w = world(db)
    w.lc.exam_course_id = w.lc.id
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ------------------------------------------------------------------ the list

async def test_list_visibility(db, api):
    w = world(db)
    link(db, w.lc, w.exam)
    stranger = make_user(db)
    r = await api.call(stranger, "GET", f"/courses/{w.exam.id}/lesson-courses")
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_enrolled", r.text
    # a course without the exam-prep page: 404
    r = await api.call(w.admin, "GET", f"/courses/{w.lc.id}/lesson-courses")
    assert r.status_code == 404, r.text
    # staff of the exam course and its students read it
    for user in (w.admin, w.s):
        r = await api.call(user, "GET", f"/courses/{w.exam.id}/lesson-courses")
        assert r.status_code == 200, r.text
        assert [x["id"] for x in r.json()] == [str(w.lc.id)]


async def test_list_rows_and_shape(db, api):
    w = world(db)
    link(db, w.lc, w.exam)
    draft = lesson_course(db, w.admin, "Draft", status="draft", published_at=None)
    deleted = lesson_course(db, w.admin, "Deleted", deleted_at=utcnow())
    other_exam = make_course(db, w.admin, title={"ru": "ОРТ (кыр)"}, languages=["ru"], default_language="ru",
                             status="published", organization_id=platform_org_id(), template_key="ort",
                             template_version=1)
    elsewhere = lesson_course(db, w.admin, "Other exam")
    for c in (draft, deleted):
        link(db, c, w.exam)
    link(db, elsewhere, other_exam)
    second = lesson_course(db, w.admin, "Second", visibility="catalog")
    link(db, second, w.exam)
    # lessons: two pages with a length, a Pro module
    m1 = make_module(db, w.lc, w.admin, title={"ru": "Математика"})
    make_item(db, m1, make_page(db, w.lc, w.admin, language="ru"), duration_s=360)
    make_item(db, m1, make_page(db, w.lc, w.admin, language="ru"), duration_s=120)
    m2 = make_module(db, w.lc, w.admin, title={"ru": "Аналогии"}, access_tier="paid")
    make_item(db, m2, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    r = await api.call(w.s, "GET", f"/courses/{w.exam.id}/lesson-courses")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [x["id"] for x in rows] == [str(w.lc.id), str(second.id)]  # published_at order; private listed too
    assert all(set(x) == LESSON_KEYS for x in rows)
    assert "join_code" not in r.text and w.lc.join_code not in r.text
    first = rows[0]
    assert first["title"] == {"ru": "Masterclass"} and first["is_platform_course"] is True
    assert (first["lessons_count"], first["duration_s"], first["has_paid_modules"]) == (3, 480, True)
    assert (first["enrolled"], first["progress"], first["next_item"]) == (False, None, None)
    assert rows[1]["has_paid_modules"] is False and rows[1]["lessons_count"] == 0


async def test_list_progress_and_next_item_for_enrolled(db, api):
    w = world(db)
    link(db, w.lc, w.exam)
    enr = enroll(db, w.lc, w.s)
    m = make_module(db, w.lc, w.admin, title={"ru": "Неделя 1"})
    p1, p2 = make_page(db, w.lc, w.admin, language="ru"), make_page(db, w.lc, w.admin, language="ru")
    met = make_item(db, m, p1, requirement=("view",))
    make_item(db, m, p2, requirement=("view",))
    now = utcnow()
    db.add(ModuleProgress(enrollment_id=enr.id, module_id=m.id, state="started", evaluated_rules_version=1,
                          evaluated_at=now))
    db.add(ItemRequirementStatus(enrollment_id=enr.id, item_id=met.id, met=True, met_at=now))
    db.commit()
    rows = (await api.call(w.s, "GET", f"/courses/{w.exam.id}/lesson-courses")).json()
    assert rows[0]["enrolled"] is True
    assert rows[0]["progress"] == {"done": 1, "total": 2}
    assert rows[0]["next_item"]["page_id"] == str(p2.id)
    # the exam's staff are not enrolled in the lesson course: no progress of anyone else
    other = make_user(db)
    enroll(db, w.exam, other)
    rows = (await api.call(other, "GET", f"/courses/{w.exam.id}/lesson-courses")).json()
    assert (rows[0]["enrolled"], rows[0]["progress"], rows[0]["next_item"]) == (False, None, None)


class _Count:
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


async def test_statement_count_does_not_grow_with_rows(db, api):
    w = world(db)

    def attach(c):
        link(db, c, w.exam)
        enr = enroll(db, c, w.s)
        m = make_module(db, c, w.admin)
        make_item(db, m, make_page(db, c, w.admin, language="ru"), requirement=("view",))
        db.add(ModuleProgress(enrollment_id=enr.id, module_id=m.id, state="unlocked", evaluated_rules_version=1,
                              evaluated_at=utcnow()))
        db.commit()

    attach(w.lc)
    url = f"/courses/{w.exam.id}/lesson-courses"
    await api.call(w.s, "GET", url)
    with _Count() as one:
        assert (await api.call(w.s, "GET", url)).status_code == 200
    for i in range(4):
        attach(lesson_course(db, w.admin, f"More {i}"))
    db.refresh(w.s)  # the test's own session: no lazy reload inside the count
    with _Count() as five:
        r = await api.call(w.s, "GET", url)
    assert r.status_code == 200 and len(r.json()) == 5
    assert all(x["next_item"] is not None and x["progress"] == {"done": 0, "total": 1} for x in r.json())
    assert len(five.statements) == len(one.statements), five.statements


# ------------------------------------------------------------------ home card, policies, ORT

async def test_home_card_carries_the_exam(db, api):
    w = world(db)
    link(db, w.lc, w.exam)
    enroll(db, w.lc, w.s)
    r = await api.call(w.s, "GET", "/me/home/courses")
    assert r.status_code == 200, r.text
    by_id = {c["id"]: c for c in r.json()["items"]}
    assert by_id[str(w.lc.id)]["exam_course_id"] == str(w.exam.id)
    assert by_id[str(w.exam.id)]["exam_course_id"] is None


def test_route_policy_and_test_student_allowlist():
    path = "/api/v1/courses/{course_id}/lesson-courses"
    assert ROUTE_POLICIES[("GET", path)] == "course:course.read"
    assert ("GET", path) in TEST_STUDENT_ROUTES


def test_ort_seed_writes_no_link(db):
    from app.lms.ort.seed import ensure_ort_courses

    ensure_platform_org(db.connection())
    db.commit()
    ensure_ort_courses(db, samples=False)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Course).where(Course.template_key == "ort")) >= 1
    assert db.scalar(select(func.count()).select_from(Course).where(Course.exam_course_id.isnot(None))) == 0
