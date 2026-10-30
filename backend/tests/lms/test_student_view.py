"""Phase 8c S1: read-only Student view (PHASE_8C_DESIGN 6.2, 7.1, invariants 2-4).

`X-View-As: student` on a `/courses/{id}[/...]` request downgrades a real teacher or assistant role to "student" for
reads (draft courses stay readable), refuses every write with 403 `student_view_read_only` (except `POST _A/preview`)
and persists nothing. Students, org admins, platform admins, outsiders and sandbox staff: the header is ignored."""
import re
import uuid
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.route_inventory import ROUTE_POLICIES
from app.lms.core.models import utcnow
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import CourseGrade, Submission
from app.lms.modules.models import CourseModule, ItemProgress, ItemRequirementStatus, ModuleItem, ModuleProgress
from app.main import app
from tests.lms.factories import auth, enroll, make_user
from tests.lms.modules_support import (
    C, I, M, add_prerequisite, make_assignment, make_course_file, make_item, make_module, make_page, published_quiz,
    structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

VIEW = {"X-View-As": "student"}
_TABLES = (ModuleProgress, ItemProgress, ItemRequirementStatus, Submission, CourseGrade, Enrollment, CourseModule,
           ModuleItem)


async def call(user, method, path, *, view=True, json=None, params=None, headers=None):
    h = dict(auth(user)) if user is not None else {}
    h["x-forwarded-for"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7, 10.255.255.1"
    if view:
        h.update(VIEW)
    h.update(headers or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, "/api/v1" + path, json=json, params=params, headers=h)


def counts(db) -> dict:
    db.expire_all()
    return {t.__tablename__: db.execute(select(func.count()).select_from(t)).scalar_one() for t in _TABLES}


def code(res) -> str:
    return (res.json().get("error") or {}).get("code")


def _world_with_structure(db, *, status="published"):
    w = structure_world(db, status=status)
    m1 = make_module(db, w.course, w.O, title={"en": "M1"})
    m2 = make_module(db, w.course, w.O, title={"en": "M2"})
    hidden = make_module(db, w.course, w.O, title={"en": "Draft module"}, published=False)
    page = make_page(db, w.course, w.O, title="Intro")
    locked_page = make_page(db, w.course, w.O, title="Later")
    text = make_assignment(db, w.course, w.O, kind="text")
    make_item(db, m1, page, requirement=("view", None))
    make_item(db, m1, text, requirement=("submit", None))
    make_item(db, m2, locked_page)
    make_item(db, hidden, make_page(db, w.course, w.O, title="Secret"))
    add_prerequisite(db, m2, m1)
    return w, m1, m2, page, locked_page, text


# ------------------------------------------------------------------ reads: student shapes for staff only

@pytest.mark.parametrize("who", ["O", "T"])
async def test_staff_get_course_and_outline_as_student(db, who):
    w, m1, m2, page, locked_page, _text = _world_with_structure(db)
    user = getattr(w, who)
    staff = (await call(user, "GET", C(w), view=False)).json()
    assert "join_code" in staff and staff["my_enrollment"]["role"] in ("teacher", "assistant")
    res = await call(user, "GET", C(w))
    assert res.status_code == 200, res.text
    body = res.json()
    assert "join_code" not in body and "active_student_count" not in body
    assert body["my_enrollment"]["role"] == "student"
    student = (await call(w.S, "GET", C(w), view=False)).json()
    assert set(body) == set(student)  # the student serializer
    out = (await call(user, "GET", f"{C(w)}/modules")).json()
    assert [m["title"]["en"] for m in out["modules"]] == ["M1", "M2"]  # no unpublished module
    assert all("rules_version" not in m and "warnings" not in m for m in out["modules"])
    states = {m["title"]["en"]: m["state"] for m in out["modules"]}
    assert states == {"M1": "unlocked", "M2": "locked"}  # a new student: nothing done yet
    assert out["modules"][1]["lock_reasons"][0]["kind"] == "prerequisite"
    # assignments list: the student shape (no counts), people: the "Teachers" list
    items = (await call(user, "GET", f"{C(w)}/assignments")).json()["items"]
    assert items and all("counts" not in a for a in items)
    people = (await call(user, "GET", f"{C(w)}/people")).json()["items"]
    assert {p["role"] for p in people} <= {"teacher", "assistant"} and all("user" not in p for p in people)
    # staff-only reads answer as for a student
    assert (await call(user, "GET", f"{C(w)}/modules/unsorted")).status_code == 403
    assert (await call(user, "GET", f"{C(w)}/todo")).status_code == 403
    assert (await call(user, "GET", f"{C(w)}/modules/progress/{w.enr.id}")).status_code == 403


async def test_gate_answers_423_in_student_view(db):
    w, _m1, _m2, page, locked_page, _text = _world_with_structure(db)
    assert (await call(w.O, "GET", f"{C(w)}/pages/{locked_page.id}", view=False)).status_code == 200
    res = await call(w.O, "GET", f"{C(w)}/pages/{locked_page.id}")
    assert res.status_code == 423 and code(res) == "module_locked"
    res = await call(w.O, "GET", f"{C(w)}/pages/{page.id}")
    assert res.status_code == 200 and "body_md" not in res.json()


async def test_draft_course_readable_in_student_view(db):
    w, *_ = _world_with_structure(db, status="draft")
    assert (await call(w.S, "GET", C(w), view=False)).status_code in (403, 404)  # students never read drafts
    res = await call(w.O, "GET", C(w))
    assert res.status_code == 200 and res.json()["status"] == "draft" and "join_code" not in res.json()
    out = (await call(w.O, "GET", f"{C(w)}/modules")).json()
    assert {m["title"]["en"]: m["state"] for m in out["modules"]} == {"M1": "unlocked", "M2": "locked"}
    assert (await call(w.O, "GET", f"{C(w)}/assignments")).status_code == 200
    assert (await call(w.O, "GET", f"{C(w)}/grades/mine")).status_code == 200


async def test_nothing_is_persisted_after_a_full_walk(db):
    w, m1, _m2, page, _locked, text = _world_with_structure(db)
    quiz = published_quiz(db, w.course, w.O)
    make_item(db, m1, quiz)
    f = make_course_file(db, w.course, w.O)
    make_item(db, m1, f)
    before = counts(db)
    paths = [C(w), f"{C(w)}/modules", f"{C(w)}/pages/{page.id}", f"{C(w)}/assignments",
             f"{C(w)}/assignments/{text.id}", f"{C(w)}/assignments/{text.id}/mine", f"{C(w)}/grades/mine",
             f"{C(w)}/people", f"{C(w)}/announcements", f"{C(w)}/files", f"{C(w)}/assessments",
             f"{C(w)}/assessments/{quiz.assessment_id}"]
    for who in (w.O, w.T):
        for p in paths:
            res = await call(who, "GET", p)
            assert res.status_code < 500, (p, res.text)
    assert counts(db) == before
    staff_enrollments = select(Enrollment.id).where(Enrollment.course_id == w.course.id,
                                                    Enrollment.role != "student")
    assert db.execute(select(func.count()).select_from(ModuleProgress)
                      .where(ModuleProgress.enrollment_id.in_(staff_enrollments))).scalar_one() == 0
    # the teacher's own home is unchanged by the header (no course path, header ignored)
    plain = (await call(w.O, "GET", "/me/home", view=False)).json()
    viewed = (await call(w.O, "GET", "/me/home")).json()
    assert plain == viewed


# ------------------------------------------------------------------ the header is ignored for everyone else

async def test_header_ignored_for_students_org_admins_platform_admins_and_outsiders(db):
    w, m1, _m2, page, _locked, _text = _world_with_structure(db)
    admin = make_user(db, platform_admin=True)
    for user in (w.S, w.OA, admin, w.X):
        for path in (C(w), f"{C(w)}/modules", f"{C(w)}/people"):
            plain = await call(user, "GET", path, view=False)
            viewed = await call(user, "GET", path)
            assert (plain.status_code, plain.json()) == (viewed.status_code, viewed.json()), (user.id, path)
    # a student's writes follow the normal rules with the header (here: a recorded view fact)
    item = db.execute(select(ModuleItem).where(ModuleItem.page_id == page.id)).scalar_one()
    res = await call(w.S, "POST", f"{I(w, m1, item)}/view")
    assert res.status_code == 200, res.text
    assert db.execute(select(func.count()).select_from(ItemProgress)
                      .where(ItemProgress.enrollment_id == w.enr.id)).scalar_one() == 1
    # an org admin's write keeps its own answer (no roster rights on content: 403 forbidden, not the view code)
    res = await call(w.OA, "POST", f"{C(w)}/modules", json={"title": {"en": "x"}})
    assert res.status_code == 403 and code(res) != "student_view_read_only"


async def test_header_ignored_for_staff_who_are_org_admins_or_platform_admins(db):
    w, *_ = _world_with_structure(db)
    enroll(db, w.course, w.OA, role="assistant", source="owner")  # org admin who is also an assistant here
    admin = make_user(db, platform_admin=True)
    enroll(db, w.course, admin, role="assistant", source="owner")
    for user in (w.OA, admin):
        res = await call(user, "GET", C(w))
        assert res.status_code == 200 and "join_code" in res.json(), res.text
        res = await call(user, "POST", f"{C(w)}/modules", json={"title": {"en": "x"}})
        assert res.status_code == 201, res.text


async def test_other_course_and_other_paths(db):
    w, *_ = _world_with_structure(db)
    other = structure_world(db)
    assert (await call(w.O, "GET", C(other))).status_code == 404
    assert (await call(w.O, "POST", f"{C(other)}/modules", json={"title": {"en": "x"}})).status_code == 404
    # every spelling of the course id in the path counts (FastAPI also accepts the 32-hex form)
    res = await call(w.O, "POST", f"/courses/{w.course.id.hex}/modules", json={"title": {"en": "x"}})
    assert res.status_code == 403 and code(res) == "student_view_read_only"
    res = await call(w.O, "GET", f"/courses/{w.course.id.hex}")
    assert res.status_code == 200 and "join_code" not in res.json()
    # header on a course list: ignored (no course id in the path)
    plain = await call(w.O, "GET", "/courses", view=False)
    viewed = await call(w.O, "GET", "/courses")
    assert plain.json() == viewed.json()


async def test_sandbox_staff_header_ignored(db, api):
    from tests.lms.test_exam_template_sandbox import draft_t, open_sb
    from tests.lms.test_exam_templates_api import tworld

    w = tworld(db)
    t = await draft_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id)
    sb = await open_sb(api, w.TA, t["id"])
    path = f"/courses/{sb['course_id']}"
    plain = await call(w.TA, "GET", path, view=False)
    viewed = await call(w.TA, "GET", path)
    assert plain.status_code == 200 and viewed.json() == plain.json() and "join_code" in viewed.json()
    # a sandbox write keeps its own answer (409 `sandbox_course`), never the Student view code
    res = await call(w.TA, "POST", f"{path}/modules", json={"title": {"en": "x"}})
    assert code(res) != "student_view_read_only"


# ------------------------------------------------------------------ writes: refused for staff, except preview

_PATH = "/api/v1/courses/{course_id}"


def _fill(path: str, cid: str) -> str:
    return re.sub(r"\{[a-z_]+\}", lambda m: cid if m.group(0) == "{course_id}" else str(uuid.uuid4()), path)


WRITE_ROUTES = sorted((m, p) for (m, p) in ROUTE_POLICIES if m != "GET" and p.startswith(_PATH)
                      and not p.endswith("/assessments/{assessment_id}/preview"))


async def test_every_course_write_refused_in_student_view(db):
    w, *_ = _world_with_structure(db)
    assert len(WRITE_ROUTES) > 60
    before = counts(db)
    for who in (w.O, w.T):
        for method, path in WRITE_ROUTES:
            url = _fill(path, w.cid)[len("/api/v1"):]
            res = await call(who, method, url, json={})
            assert res.status_code == 403 and code(res) == "student_view_read_only", (method, path, res.text)
    assert counts(db) == before


async def test_preview_allowed_with_real_role(db, api):
    from tests.lms.assessment_support import simple_published

    w, *_ = _world_with_structure(db)
    out, _qs = await simple_published(api, db, w, 1)
    before = db.execute(select(func.count()).select_from(Submission)).scalar_one()
    for who in (w.O, w.T):
        url = f"{C(w)}/assessments/{out['assessment']['id']}/preview"
        res = await call(who, "POST", url, json={})
        assert res.status_code == 201 and res.json()["is_preview"] is True, res.text
        assert (await call(w.S, "POST", url, json={})).status_code == 403  # students: as today, header or not
    db.expire_all()
    assert db.execute(select(func.count()).select_from(Submission)).scalar_one() == before


async def test_lobby_and_locked_quiz_in_student_view(db):
    w, m1, m2, *_ = _world_with_structure(db)
    quiz = published_quiz(db, w.course, w.O)
    make_item(db, m2, quiz)
    res = await call(w.O, "GET", f"{C(w)}/assessments/{quiz.assessment_id}")
    assert res.status_code == 423 and code(res) == "module_locked"
    m2.unlock_at = utcnow() - timedelta(days=1)
    db.commit()
    open_quiz = published_quiz(db, w.course, w.O)
    make_item(db, m1, open_quiz)
    res = await call(w.O, "GET", f"{C(w)}/assessments/{open_quiz.assessment_id}")
    assert res.status_code == 200 and "sections" in res.json() and "draft_rev" not in res.json(), res.text


# ------------------------------------------------------------------ serializer contract with the header on (8a 7.3)

@pytest.mark.parametrize("who", ["O", "T"])
async def test_outline_allow_list_in_student_view(db, who):
    from tests.lms.test_modules_serializers import (
        FORBIDDEN, ITEM_KEYS, LINK_KEYS, MODULE_KEYS, REQ_KEYS, _walk_keys, _world,
    )

    w = _world(db)
    r = await call(getattr(w, who), "GET", f"{C(w)}/modules")
    assert r.status_code == 200
    body = r.json()
    student = (await call(w.S, "GET", f"{C(w)}/modules", view=False)).json()
    assert body == student  # a new student and S (no facts of S) see the same outline
    assert set(body) == {"modules", "up_next"} and "HIDDEN" not in r.text
    for mod in body["modules"]:
        assert set(mod) == MODULE_KEYS
        for it in mod["items"]:
            assert set(it) == ITEM_KEYS
            if it["requirement"] is not None:
                assert set(it["requirement"]) == REQ_KEYS
            if it["link"] is not None:
                assert set(it["link"]) == LINK_KEYS
    assert not _walk_keys(body, set()) & set(FORBIDDEN)
