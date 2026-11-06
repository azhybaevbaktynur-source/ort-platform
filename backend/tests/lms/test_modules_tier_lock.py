"""F5a Pro modules (COURSE_LESSONS_DESIGN 3, 5, 9): a `paid` module of a platform course locks for a student without a
pass. Locked rows keep title, kind and duration and reveal no destination (raw JSON: no stored URL, video id, page id,
file id or assignment id); the facts routes, the page, the file download and the quiz start answer 403
`access_required`, the quiz lobby shows the existing S3 lock; a target also referenced by a free module stays open; ORT
preset exams keep their own tier; a pass opens everything, an expired one locks again; test students, staff and
platform admins are never tier-locked; non-platform courses ignore the column; a module rule wins the reason (423).
Teacher side: the Pro switch is refused outside platform courses (422)."""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.lms.assignments.sync import mirror_from_assessment
from app.lms.enrollments.models import Enrollment
from app.lms.modules.models import CourseModule, ItemProgress
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import platform_org_id
from tests.lms.access_support import give_pass
from tests.lms.attempt_support import T0, frozen_clock, make_quiz  # noqa: F401
from tests.lms.factories import enroll, make_user
from tests.lms.gradebook_support import no_scored_hooks  # noqa: F401
from tests.lms.modules_support import make_course_file, make_item, make_module, make_page
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

VIDEO_ID = "dQw4w9WgXcQ"
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


def tier_world(db, *, platform: bool = True, preset: str = "none", ort: bool = False, **paid_kw):
    """A quiz course (teacher, enrolled student) with a free module (page lesson) and a `paid` module holding a page,
    a file, a video, the quiz and a header."""
    ensure_platform_org(db.connection())
    db.commit()
    q = make_quiz(db)
    c = q.course
    if platform:
        c.organization_id = platform_org_id()
    if ort:
        c.template_key, c.template_version, c.template_locked = "ort", 1, True
        c.template_settings = {"language": "en"}
    q.assessment.preset = preset
    db.commit()
    w = SimpleNamespace(q=q, course=c, O=q.teacher, S=q.student, cid=str(c.id))
    w.assignment = mirror_from_assessment(db, q.assessment)
    db.commit()
    w.enr = db.scalars(select(Enrollment).where(Enrollment.course_id == c.id, Enrollment.user_id == q.student.id)).one()
    w.free = make_module(db, c, q.teacher, title={"en": "Free"})
    w.free_page = make_page(db, c, q.teacher, title="Intro")
    w.free_item = make_item(db, w.free, w.free_page, duration_s=300)
    w.paid = make_module(db, c, q.teacher, title={"en": "Pro"}, access_tier="paid", **paid_kw)
    w.page = make_page(db, c, q.teacher, title="Secret lesson")
    w.file = make_course_file(db, c, q.teacher, title="Secret.pdf")
    w.p_item = make_item(db, w.paid, w.page, duration_s=600)
    w.f_item = make_item(db, w.paid, w.file)
    w.u_item = make_item(db, w.paid, VIDEO_URL, duration_s=480)
    w.q_item = make_item(db, w.paid, w.assignment)
    w.h_item = make_item(db, w.paid)
    return w


def code(r) -> str:
    return ((r.json() or {}).get("error") or {}).get("code")


async def outline(api, w, who=None):
    r = await api.call(who or w.S, "GET", f"/courses/{w.cid}/modules")
    assert r.status_code == 200, r.text
    return r


def module_of(body, m):
    return next(x for x in body["modules"] if x["id"] == str(m.id))


def item_path(w, m, it) -> str:
    return f"/courses/{w.cid}/modules/{m.id}/items/{it.id}"


async def assert_all_open(api, w, who=None):
    who = who or w.S
    r = await outline(api, w, who)
    pm = module_of(r.json(), w.paid)
    assert pm["access_locked"] is False
    assert all(not i["locked"] and i["locked_reason"] is None for i in pm["items"])


# ------------------------------------------------------------------ outline

async def test_locked_rows_reveal_no_destination(db, api):
    w = tier_world(db)
    r = await outline(api, w)
    body = r.json()
    pm = module_of(body, w.paid)
    assert pm["access_tier"] == "paid" and pm["access_locked"] is True
    rows = {i["id"]: i for i in pm["items"]}
    for it in (w.p_item, w.f_item, w.u_item, w.q_item):
        row = rows[str(it.id)]
        assert row["locked"] is True and row["locked_reason"] == "access_required", row
        assert row["video"] is None and row["due_at"] is None
        assert row["link"] is None or set(k for k, v in row["link"].items() if v is not None) == {"assignment_kind"}
    assert rows[str(w.p_item.id)]["title"] == {"en": "Secret lesson"} and rows[str(w.p_item.id)]["kind"] == "page"
    assert rows[str(w.p_item.id)]["duration_s"] == 600 and rows[str(w.u_item.id)]["duration_s"] == 480
    assert rows[str(w.h_item.id)]["locked_reason"] is None  # a header is no lesson
    # the raw JSON never names the destinations
    text = r.text
    for secret in (VIDEO_URL, VIDEO_ID, "youtube", str(w.page.id), str(w.file.id), str(w.assignment.id),
                   str(w.q.assessment.id)):
        assert secret not in text, secret
    # the free module stays open; up_next skips the Pro rows; progress counts them
    fm = module_of(body, w.free)
    assert fm["access_locked"] is False and fm["items"][0]["link"]["page_id"] == str(w.free_page.id)
    assert body["up_next"]["item_id"] == str(w.free_item.id)
    assert body["progress"] == {"done": 0, "total": 5, "duration_s": 300 + 600 + 480}


async def test_facts_page_file_quiz_refused(db, api):
    w = tier_world(db)
    for path, body in ((item_path(w, w.paid, w.p_item) + "/view", None),
                       (item_path(w, w.paid, w.u_item) + "/done", {"done": True})):
        r = await api.call(w.S, "POST", path, json=body)
        assert r.status_code == 403 and code(r) == "access_required", r.text
    assert db.scalars(select(ItemProgress).where(ItemProgress.enrollment_id == w.enr.id)).all() == []
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/pages/{w.page.id}")
    assert r.status_code == 403 and code(r) == "access_required", r.text
    assert "Hello" not in r.text
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/course-files/{w.file.id}/download")
    assert r.status_code == 403 and code(r) == "access_required", r.text
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/assessments/{w.q.assessment.id}")
    assert r.status_code == 200, r.text
    lobby = r.json()
    assert lobby["locked"] is True and lobby["can_start"] is False and lobby["reason"] == "access_required"
    r = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{w.q.assessment.id}/attempts", json={})
    assert r.status_code == 403 and code(r) == "access_required", r.text
    # the free module's lesson is open
    assert (await api.call(w.S, "POST", item_path(w, w.free, w.free_item) + "/view")).status_code == 200
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/pages/{w.free_page.id}")).status_code == 200


async def test_target_also_in_a_free_module_stays_open(db, api):
    w = tier_world(db)
    make_item(db, w.free, w.page)
    make_item(db, w.free, w.assignment)
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/pages/{w.page.id}")).status_code == 200
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/assessments/{w.q.assessment.id}")
    assert r.status_code == 200 and r.json()["can_start"] is True, r.text
    # the Pro row itself stays locked in the outline (its module is Pro)
    pm = module_of((await outline(api, w)).json(), w.paid)
    assert {i["locked_reason"] for i in pm["items"] if i["kind"] != "header"} == {"access_required"}


async def test_ort_preset_exam_in_a_pro_module_starts(db, api):
    w = tier_world(db, preset="ort_main", ort=True)
    r = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{w.q.assessment.id}/attempts", json={})
    assert r.status_code == 201, r.text
    pm = module_of((await outline(api, w)).json(), w.paid)
    q_row = next(i for i in pm["items"] if i["id"] == str(w.q_item.id))
    assert q_row["locked"] is False and q_row["locked_reason"] is None
    # the lessons of the same module stay locked
    p_row = next(i for i in pm["items"] if i["id"] == str(w.p_item.id))
    assert p_row["locked_reason"] == "access_required"


async def test_pass_opens_and_expired_pass_locks_again(db, api):
    w = tier_world(db)
    p = give_pass(db, w.S)
    await assert_all_open(api, w)
    r = (await outline(api, w)).json()
    assert module_of(r, w.paid)["items"][2]["video"] == {"provider": "youtube", "id": VIDEO_ID}
    assert (await api.call(w.S, "POST", item_path(w, w.paid, w.p_item) + "/view")).status_code == 200
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/pages/{w.page.id}")).status_code == 200
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/course-files/{w.file.id}/download")).status_code == 200
    lobby = (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments/{w.q.assessment.id}")).json()
    assert lobby["can_start"] is True and lobby["locked"] is False
    # the pass ends: locked again, the view done before stays counted
    from app.lms.core import clock

    p.ends_at = clock.now() - timedelta(minutes=1)
    db.commit()
    body = (await outline(api, w)).json()
    pm = module_of(body, w.paid)
    assert pm["access_locked"] is True
    p_row = next(i for i in pm["items"] if i["id"] == str(w.p_item.id))
    assert p_row["locked"] is True and p_row["done"] is True and pm["done"] == 1
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/pages/{w.page.id}")
    assert r.status_code == 403 and code(r) == "access_required"


async def test_test_student_staff_and_platform_admin_are_never_tier_locked(db, api):
    w = tier_world(db)
    ts = make_user(db)
    ts.is_test_student = True
    enr = enroll(db, w.course, ts)
    enr.is_test_student = True
    db.commit()
    await assert_all_open(api, w, ts)
    assert (await api.call(ts, "GET", f"/courses/{w.cid}/pages/{w.page.id}")).status_code == 200
    assert (await api.call(ts, "POST", item_path(w, w.paid, w.p_item) + "/view")).status_code == 200
    ta = make_user(db)
    enroll(db, w.course, ta, role="assistant", source="owner")
    for who in (w.O, ta):
        r = await outline(api, w, who)
        assert "items" in r.json()["modules"][0] and "rules_version" in r.json()["modules"][0]  # staff shape
        assert (await api.call(who, "GET", f"/courses/{w.cid}/pages/{w.page.id}")).status_code == 200
    from app.lms.organizations.models import Organization
    from tests.lms.org_support import add_member

    admin = make_user(db, platform_admin=True)  # reads platform courses as an org admin of the platform organization
    add_member(db, db.get(Organization, platform_org_id()), admin, role="org_admin")
    r = await api.call(admin, "GET", f"/courses/{w.cid}/modules")
    assert r.status_code == 200, r.text
    pm = module_of(r.json(), w.paid)
    assert pm["access_locked"] is False and not any(i["locked"] for i in pm["items"])


async def test_non_platform_course_ignores_the_tier(db, api):
    w = tier_world(db, platform=False)
    await assert_all_open(api, w)
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/pages/{w.page.id}")).status_code == 200
    r = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{w.q.assessment.id}/attempts", json={})
    assert r.status_code == 201, r.text


async def test_module_rule_wins_the_reason(db, api, frozen_clock):
    w = tier_world(db, unlock_at=T0 + timedelta(days=3))
    pm = module_of((await outline(api, w)).json(), w.paid)
    assert pm["state"] == "locked" and pm["access_locked"] is True
    assert {i["locked_reason"] for i in pm["items"] if i["kind"] != "header"} == {"module"}
    r = await api.call(w.S, "POST", item_path(w, w.paid, w.p_item) + "/view")
    assert r.status_code == 423 and code(r) == "module_locked", r.text


# ------------------------------------------------------------------ teacher: the Pro switch

async def test_pro_switch_only_on_platform_courses(db, api):
    own = tier_world(db, platform=False)
    base = f"/courses/{own.cid}/modules"
    r = await api.call(own.O, "POST", base, json={"title": {"en": "X"}, "access_tier": "paid"})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["loc"] == ["access_tier"], r.text
    r = await api.call(own.O, "POST", base, json={"title": {"en": "X"}, "access_tier": "free"})
    assert r.status_code == 201 and r.json()["access_tier"] == "free", r.text
    r = await api.call(own.O, "PATCH", f"{base}/{own.free.id}", json={"access_tier": "paid"})
    assert r.status_code == 422, r.text
    plat = tier_world(db)
    base = f"/courses/{plat.cid}/modules"
    r = await api.call(plat.O, "POST", base, json={"title": {"en": "Y"}, "access_tier": "paid"})
    assert r.status_code == 201 and r.json()["access_tier"] == "paid", r.text
    r = await api.call(plat.O, "POST", base, json={"title": {"en": "Z"}})
    assert r.status_code == 201 and r.json()["access_tier"] == "free"
    r = await api.call(plat.O, "PATCH", f"{base}/{plat.free.id}", json={"access_tier": "paid"})
    assert r.status_code == 200 and r.json()["access_tier"] == "paid", r.text
    r = await api.call(plat.O, "PATCH", f"{base}/{plat.free.id}", json={"access_tier": None})
    assert r.status_code == 422
    r = await api.call(plat.O, "PATCH", f"{base}/{plat.free.id}", json={"access_tier": "gold"})
    assert r.status_code == 422
    db.expire_all()
    assert db.get(CourseModule, plat.free.id).access_tier == "paid"
    # the student cannot set it
    r = await api.call(plat.S, "PATCH", f"{base}/{plat.paid.id}", json={"access_tier": "free"})
    assert r.status_code in (403, 404)


# ------------------------------------------------------------------ F5a review: mixed references and next-test lists

async def test_pro_and_rules_locked_free_reference_stays_locked(db, api, frozen_clock):
    """A target held by an open Pro module and by a free module locked by its rules is open through neither for a
    gated student: page, file and quiz answer `access_required` (a pass would open the Pro reference)."""
    w = tier_world(db)
    later = make_module(db, w.course, w.O, title={"en": "Later"}, unlock_at=T0 + timedelta(days=3))
    for target in (w.page, w.file, w.assignment):
        make_item(db, later, target)
    pages, files = f"/courses/{w.cid}/pages/{w.page.id}", f"/courses/{w.cid}/course-files/{w.file.id}/download"
    for path in (pages, files):
        r = await api.call(w.S, "GET", path)
        assert r.status_code == 403 and code(r) == "access_required", (path, r.text)
        assert "Hello" not in r.text
    lobby = (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments/{w.q.assessment.id}")).json()
    assert lobby["locked"] is True and lobby["can_start"] is False and lobby["reason"] == "access_required"
    r = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{w.q.assessment.id}/attempts", json={})
    assert r.status_code == 403 and code(r) == "access_required", r.text
    # the Pro module rules-locked too: nothing a pass would open -> 423
    w.paid.unlock_at = T0 + timedelta(days=3)
    db.commit()
    r = await api.call(w.S, "GET", pages)
    assert r.status_code == 423 and code(r) == "module_locked", r.text
    w.paid.unlock_at = None
    db.commit()
    # with a pass the Pro reference opens them
    give_pass(db, w.S)
    assert (await api.call(w.S, "GET", pages)).status_code == 200
    assert (await api.call(w.S, "GET", files)).status_code == 200
    r = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{w.q.assessment.id}/attempts", json={})
    assert r.status_code == 201, r.text


def test_pro_only_assessment_correlates_with_the_callers_assessment():
    """F5a review MUST: the quiz's assignment is matched inside the EXISTS, so `assessments` correlates with the
    caller's query (a scalar subquery nested in the EXISTS did not: `FROM assignments, assessments`, a constant)."""
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.orm import aliased

    from app.lms.assessments.models import Assessment
    from app.lms.modules.service import pro_only_assessment

    alias = aliased(Assessment)
    for model in (Assessment, alias):
        for dialect in (sqlite.dialect(), postgresql.dialect()):
            sql = " ".join(str(select(model.id).where(pro_only_assessment(model)).compile(dialect=dialect)).split())
            assert "FROM assignments, assessments" not in sql and "assessments, assignments" not in sql, sql
            assert sql.count("FROM assessments") == 1, sql  # only the outer query names the table
            assert sql.count("EXISTS") == 2, sql


async def test_next_test_and_todo_skip_tests_only_pro_modules_hold(db, api, no_scored_hooks):
    """The exam-prep "next" step and the home to-do / next up skip a test that only Pro modules hold for a gated
    student; an ORT preset exam in the same Pro module keeps its own (free) tier; a pass brings the test back.
    Deterministic for the F5a correlation bug: the Pro-only quiz comes FIRST (lowest position and row order) and the
    free quiz outside modules after it, so a constant subquery would lock every test (`next` = unlock)."""
    from app.lms.assignments.models import Assignment
    from app.lms.core.models import utcnow
    from app.lms.grading.seeds import ORT_MAIN_V1_ID
    from tests.lms.factories import make_course
    from tests.lms.gradebook_support import graded_assessment

    ensure_platform_org(db.connection())
    db.commit()
    t = make_user(db, teacher_status="approved")
    course = make_course(db, t, languages=["ru"], default_language="ru", status="published",
                         organization_id=platform_org_id(), template_key="ort", template_version=1,
                         template_locked=True, published_at=utcnow())
    s = make_user(db)
    enroll(db, course, s)

    def quiz(title, preset):
        a, _v = graded_assessment(db, course, t, points=10, scheme_version_id=ORT_MAIN_V1_ID, preset=preset,
                                  title={"ru": title}, allowed_attempts=-1)
        return a, db.execute(select(Assignment).where(Assignment.assessment_id == a.id)).scalar_one()

    pro_a, pro_asg = quiz("Pro", "none")        # first: only in the Pro module
    free_a, free_asg = quiz("Free", "none")     # after: in no module
    assert pro_a.position < free_a.position
    pro = make_module(db, course, t, title={"ru": "Pro"}, access_tier="paid")
    make_item(db, pro, pro_asg)

    async def state():
        page = await api.call(s, "GET", f"/courses/{course.id}/exam-prep")
        assert page.status_code == 200, page.text
        home = await api.call(s, "GET", "/me/home")
        assert home.status_code == 200, home.text
        nxt = page.json()["next"]
        return (nxt.get("assessment_id") or nxt["kind"], {r["assignment_id"] for r in home.json()["todo"]},
                {r["assignment_id"] for r in home.json()["next_up"]})

    nxt, todo, next_up = await state()
    assert nxt == str(free_a.id)  # the Pro-only test is skipped, the free one is next (not "unlock")
    assert str(pro_asg.id) not in todo | next_up and str(free_asg.id) in todo
    # an ORT preset exam in the same Pro module keeps its own (free) tier
    ort_a, ort_asg = quiz("Ort", "ort_main")
    make_item(db, pro, ort_asg)
    nxt, todo, next_up = await state()
    assert nxt == str(free_a.id) and {str(ort_asg.id), str(free_asg.id)} <= todo
    assert str(pro_asg.id) not in todo | next_up
    give_pass(db, s)
    nxt, todo, next_up = await state()
    assert nxt == str(pro_a.id) and str(pro_asg.id) in todo
