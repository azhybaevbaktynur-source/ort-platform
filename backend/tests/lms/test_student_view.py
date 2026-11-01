"""UX rework S1 (UX_REWORK_DESIGN F): Student view is a real session of a per-course test student.

Issue and reset authorization, the whole student flow under the issued token, every staff exclusion, the deny-by-default
allow-list decided on the matched route template, draft courses, ORT, and the removal of the 8c `X-View-As` mechanism
with the staff preview attempt unchanged."""
import re
import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.authz import ROLE_GRANTS
from app.core.route_inventory import ROUTE_POLICIES, iter_routes
from app.core.security import create_access_token
from app.lms.assessments import repository as assessment_repo
from app.lms.assessments.models import Assessment
from app.lms.assignments import service as assignment_svc
from app.lms.attempts.models import Attempt
from app.lms.audit.models import AdminAuditLog
from app.lms.content.models import QuestionVersion
from app.lms.core.models import utcnow
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.enrollments.service import roster_query
from app.lms.grading.models import Submission
from app.lms.modules.models import ModuleProgress
from app.lms.organizations.models import Organization
from app.lms.ort.seed import course_id_for, ensure_ort_courses
from app.lms.student_view.allowlist import TEST_STUDENT_ROUTES
from app.main import app
from app.models.user import User
from app.services import email_service
from tests.lms.assessment_support import simple_published
from tests.lms.assignment_support import hand_in, make_assignment, pdf, upload_hand_in  # noqa: F401
from tests.lms.factories import auth, enroll, make_course, make_user
from tests.lms.modules_support import C, I, make_course_file, make_item, make_module, make_page, structure_world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_ort_seed import insert_export


# ------------------------------------------------------------------ helpers

async def as_token(token, method, path, *, json=None, params=None, headers=None):
    h = {"Authorization": f"Bearer {token}", "x-forwarded-for": f"10.{uuid.uuid4().int % 250}.3.7, 10.255.255.1"}
    h.update(headers or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, "/api/v1" + path, json=json, params=params, headers=h)


def code(res) -> str:
    return (res.json().get("error") or {}).get("code")


async def enter(api, user, cid) -> dict:
    res = await api.call(user, "POST", f"/courses/{cid}/student-view")
    assert res.status_code == 200, res.text
    return res.json()


def test_rows(db, cid):
    db.expire_all()
    return db.execute(select(Enrollment, User).join(User, User.id == Enrollment.user_id).where(
        Enrollment.course_id == uuid.UUID(str(cid)), Enrollment.is_test_student.is_(True))).all()


test_rows.__test__ = False


async def take_quiz(token, cid, assessment_id, qs, db):
    """Start, answer every question correctly and submit, as the token's user."""
    base = f"/courses/{cid}/assessments/{assessment_id}"
    st = await as_token(token, "POST", f"{base}/attempts", json={})
    assert st.status_code == 201, st.text
    state = st.json()
    aid = state["id"]
    answers = []
    for n, item in enumerate(state["items"]):
        qv = db.get(QuestionVersion, uuid.UUID(item["qv"]))
        answers.append({"position": item["position"], "client_ts": 1000 + n,
                        "response": {"choice_id": qv.data["correct"]}})
    res = await as_token(token, "PUT", f"/attempts/{aid}/answers", json={"answers": answers})
    assert res.status_code == 200, res.text
    res = await as_token(token, "POST", f"/attempts/{aid}/submit", json={})
    assert res.status_code == 200, res.text
    return aid


# ------------------------------------------------------------------ issue and reset: authorization

@pytest.mark.parametrize("route", ["student-view", "student-view/reset"])
async def test_authorization_matrix(db, api, route):
    w = structure_world(db)
    url = f"{C(w)}/{route}"
    other = make_user(db, teacher_status="approved")
    other_course = make_course(db, other, organization_id=w.course.organization_id)
    assert other_course.id != w.course.id
    admin = make_user(db, platform_admin=True)

    for staff in (w.O, w.T):
        res = await api.call(staff, "POST", url)
        assert res.status_code == 200, res.text
        body = res.json()
        assert set(body) == {"access_token", "expires_in", "course_id"}
        assert body["expires_in"] == 4 * 3600 and body["course_id"] == w.cid

    assert (await api.call(w.S, "POST", url)).status_code == 403  # a student
    assert (await api.call(w.OA, "POST", url)).status_code == 403  # an org admin without an enrollment
    assert (await api.call(other, "POST", url)).status_code == 404  # a teacher of another course
    assert (await api.call(w.X, "POST", url)).status_code == 404  # an outsider
    assert (await api.call(admin, "POST", url)).status_code == 404  # a platform admin without an enrollment
    assert (await api.call(None, "POST", url)).status_code == 401

    # a platform admin who really teaches the course may (the ORT courses are taught that way)
    enroll(db, w.course, admin, role="teacher", source="owner")
    assert (await api.call(admin, "POST", url)).status_code == 200

    # a test student cannot mint another one
    token = (await enter(api, w.O, w.cid))["access_token"]
    res = await as_token(token, "POST", url)
    assert res.status_code == 403 and code(res) == "test_student_forbidden"


@pytest.mark.parametrize("route", ["student-view", "student-view/reset"])
async def test_deleted_suspended_and_sandbox_courses(db, api, route):
    w = structure_world(db)
    url = f"{C(w)}/{route}"
    org = db.get(Organization, w.course.organization_id)
    org.status = "suspended"
    db.commit()
    res = await api.call(w.O, "POST", url)
    assert res.status_code == 403 and code(res) == "organization_suspended"
    org.status = "active"
    db.commit()

    w.course.deleted_at = utcnow()
    db.commit()
    assert (await api.call(w.O, "POST", url)).status_code == 404
    w.course.deleted_at = None
    db.commit()

    from tests.lms.test_sandbox_hidden_from_lists import sandbox_world

    sw = sandbox_world(db)
    res = await api.call(sw.TA, "POST", f"/courses/{sw.sid}/{route}")
    assert res.status_code in (404, 409), res.text
    assert not db.execute(select(Enrollment.id).where(Enrollment.course_id == sw.sandbox.id,
                                                      Enrollment.is_test_student.is_(True))).first()


async def test_enter_reuses_the_test_student_and_is_audited(db, api):
    w = structure_world(db)
    t1 = await enter(api, w.O, w.cid)
    t2 = await enter(api, w.T, w.cid)  # the assistant shares the course's one test student
    rows = test_rows(db, w.cid)
    assert len(rows) == 1
    enr, user = rows[0]
    assert (enr.role, enr.state, enr.is_test_student) == ("student", "active", True)
    assert user.is_test_student and user.email_verified and user.display_name == "Test student"
    assert user.teacher_status == "none" and not user.is_platform_admin
    assert email_service.is_reserved_address(user.email)
    for t in (t1, t2):
        me = await as_token(t["access_token"], "GET", "/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["id"] == user.id and me.json()["is_test_student"] is True
    audited = db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == w.cid,
                                                     AdminAuditLog.action == "student_view.enter")).scalars().all()
    assert {a.actor_id for a in audited} == {w.O.id, w.T.id}


async def test_real_profile_says_not_a_test_student(db, api):
    w = structure_world(db)
    me = await api.call(w.O, "GET", "/auth/me")
    assert me.status_code == 200 and me.json()["is_test_student"] is False


async def test_reset_retires_and_replaces(db, api):
    w = structure_world(db)
    old = await enter(api, w.O, w.cid)
    res = await api.call(w.O, "POST", f"{C(w)}/student-view/reset")
    assert res.status_code == 200, res.text
    new = res.json()
    rows = test_rows(db, w.cid)
    assert len(rows) == 2  # nothing is deleted
    active = [r for r in rows if r[0].state == "active"]
    retired = [r for r in rows if r[0].state == "removed"]
    assert len(active) == 1 and len(retired) == 1
    assert retired[0][1].disabled_at is not None and retired[0][1].is_test_student
    assert retired[0][0].is_test_student and retired[0][0].removed_by_id == w.O.id
    # the old token is dead, the new one works as a different user
    assert (await as_token(old["access_token"], "GET", "/auth/me")).status_code == 401
    me = await as_token(new["access_token"], "GET", "/auth/me")
    assert me.status_code == 200 and me.json()["id"] == active[0][1].id != retired[0][1].id
    assert db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == w.cid,
                                                  AdminAuditLog.action == "student_view.reset")).first()
    # entering again reuses the new one; a reset with no test student just creates one
    assert (await enter(api, w.O, w.cid))
    assert len(test_rows(db, w.cid)) == 2
    w2 = structure_world(db)
    assert (await api.call(w2.O, "POST", f"{C(w2)}/student-view/reset")).status_code == 200
    assert len(test_rows(db, w2.cid)) == 1


def test_one_active_test_enrollment_per_course_is_enforced_by_the_database(db):
    from sqlalchemy.exc import IntegrityError

    w = structure_world(db)
    for _ in range(2):
        u = make_user(db)
        db.add(Enrollment(course_id=w.course.id, user_id=u.id, role="student", state="active", source="admin",
                          is_test_student=True))
        if _ == 0:
            db.commit()
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_token_lifetime_is_four_hours(db):
    from app.lms.student_view.service import TOKEN_TTL

    assert TOKEN_TTL == timedelta(hours=4)


async def test_expired_token_is_refused(db, api):
    w = structure_world(db)
    await enter(api, w.O, w.cid)
    user = test_rows(db, w.cid)[0][1]
    token = create_access_token({"sub": user.id}, timedelta(seconds=-5))
    assert (await as_token(token, "GET", "/auth/me")).status_code == 401


# ------------------------------------------------------------------ cannot sign in, reset or receive mail

@pytest.mark.parametrize("path,body", [
    ("/auth/login", {"password": "whatever-123"}),
    ("/auth/register", {"password": "whatever-123", "displayName": "X"}),
    ("/auth/forgot-password", {}),
    ("/auth/resend-code", {}),
    ("/auth/verify-email", {"password": "whatever-123", "code": "123456"}),
])
async def test_reserved_address_never_reaches_auth_flows(db, api, path, body):
    w = structure_world(db)
    await enter(api, w.O, w.cid)
    user = test_rows(db, w.cid)[0][1]
    res = await api.call(None, "POST", path, json={**body, "email": user.email})
    assert res.status_code == 422, res.text
    db.expire_all()
    assert db.get(User, user.id).reset_token is None


async def test_login_service_refuses_the_unusable_hash(db, api):
    from fastapi import HTTPException

    from app.api.v1.endpoints import auth as auth_ep
    from app.schemas.user import UserLoginRequest

    w = structure_world(db)
    await enter(api, w.O, w.cid)
    user = test_rows(db, w.cid)[0][1]
    req = UserLoginRequest.model_construct(email=user.email, password="!", lang="ru")
    with pytest.raises(HTTPException) as e:
        auth_ep.login_user(req, db)
    assert e.value.status_code == 401


async def test_no_email_to_the_reserved_domain(db, api, monkeypatch):
    calls = []
    monkeypatch.setattr(email_service, "active_provider", lambda: calls.append(1) or "console")
    assert email_service.send_email("test-student-abc@student-view.invalid", "s", "t", "<p>t</p>") is True
    assert email_service.send_email("TEST-student-abc@Student-View.INVALID ", "s", "t", "<p>t</p>") is True
    assert calls == []
    assert email_service.send_email("real@example.com", "s", "t", "<p>t</p>") is True
    assert calls == [1]


# ------------------------------------------------------------------ the student flow

async def test_full_flow_as_test_student(db, api):
    w = structure_world(db)
    out, qs = await simple_published(api, db, w, 2)
    quiz_id = out["assessment"]["id"]
    m = make_module(db, w.course, w.O, title={"en": "Week 1"})
    page = make_page(db, w.course, w.O, title="Intro")
    page_item = make_item(db, m, page, requirement=("view", None))
    text = make_assignment(db, w.course, w.O, kind="text")
    make_item(db, m, text)
    token = (await enter(api, w.O, w.cid))["access_token"]

    # the course reads as a student's
    res = await as_token(token, "GET", C(w))
    assert res.status_code == 200, res.text
    assert res.json()["my_enrollment"]["role"] == "student" and "join_code" not in res.json()

    # modules: evaluated, and progress persists as for any student
    res = await as_token(token, "GET", f"{C(w)}/modules")
    assert res.status_code == 200, res.text
    assert [x["title"] for x in res.json()["modules"]] == [{"en": "Week 1"}]
    res = await as_token(token, "POST", f"{I(w, m, page_item)}/view")
    assert res.status_code in (200, 201, 204), res.text

    # quiz: lobby, start, autosave, submit, result
    lobby = await as_token(token, "GET", f"{C(w)}/assessments/{quiz_id}")
    assert lobby.status_code == 200 and lobby.json()["can_start"] is True, lobby.text
    attempt_id = await take_quiz(token, w.cid, quiz_id, qs, db)
    res = await as_token(token, "GET", f"/attempts/{attempt_id}/result")
    assert res.status_code == 200, res.text
    assert D(str(res.json()["raw_score"])) == D(str(res.json()["points_possible"])) > 0

    # hand-in
    res = await as_token(token, "POST", f"{C(w)}/assignments/{text.id}/submissions", json={"body_text": "My work"})
    assert res.status_code in (200, 201), res.text
    res = await as_token(token, "GET", f"{C(w)}/assignments/{text.id}/mine")
    assert res.status_code == 200, res.text

    # the grade appears for them, and on their home
    res = await as_token(token, "GET", f"{C(w)}/grades/mine")
    assert res.status_code == 200, res.text
    states = {i["assessment_id"]: i["state"] for i in res.json()["items"]}
    assert states[quiz_id] == "graded", res.text
    res = await as_token(token, "GET", "/me/home")
    assert res.status_code == 200, res.text
    assert res.json()["courses"][0]["id"] == w.cid
    res = await as_token(token, "GET", "/courses", params={"as": "learning"})
    assert res.status_code == 200 and [c["id"] for c in res.json()["items"]] == [w.cid]


async def test_draft_course_works_for_its_test_student_only(db, api):
    w = structure_world(db, status="draft")
    assert w.course.status == "draft"
    out, qs = await simple_published(api, db, w, 1)
    quiz_id = out["assessment"]["id"]
    m = make_module(db, w.course, w.O, title={"en": "Week 1"})
    page = make_page(db, w.course, w.O, title="Intro")
    item = make_item(db, m, page, requirement=("view", None))
    token = (await enter(api, w.O, w.cid))["access_token"]

    res = await as_token(token, "GET", C(w))
    assert res.status_code == 200, res.text
    res = await as_token(token, "GET", f"{C(w)}/modules")
    assert res.status_code == 200 and len(res.json()["modules"]) == 1, res.text
    res = await as_token(token, "POST", f"{I(w, m, item)}/view")
    assert res.status_code in (200, 201, 204), res.text
    res = await as_token(token, "GET", f"{C(w)}/pages/{page.id}")
    assert res.status_code == 200, res.text
    # progress persisted, even though the course is a draft
    enr = test_rows(db, w.cid)[0][0]
    res = await as_token(token, "GET", f"{C(w)}/modules")
    assert db.execute(select(func.count()).select_from(ModuleProgress).where(
        ModuleProgress.enrollment_id == enr.id)).scalar_one() == 1
    # the quiz: start, autosave (the SQL guard) and submit
    attempt_id = await take_quiz(token, w.cid, quiz_id, qs, db)
    assert (await as_token(token, "GET", f"/attempts/{attempt_id}/result")).status_code == 200
    # home and the course list show the draft course to it
    home = await as_token(token, "GET", "/me/home")
    assert [c["id"] for c in home.json()["courses"]] == [w.cid], home.text
    listed = await as_token(token, "GET", "/courses", params={"as": "learning"})
    assert [c["id"] for c in listed.json()["items"]] == [w.cid]

    # a real student of the same draft course still reads nothing
    assert (await api.call(w.S, "GET", C(w))).status_code == 403
    assert w.cid not in (await api.call(w.S, "GET", "/me/home")).text


async def test_concluded_course_reads_but_refuses_writes(db, api):
    w = structure_world(db, status="concluded")
    a = make_assignment(db, w.course, w.O, kind="text")
    token = (await enter(api, w.O, w.cid))["access_token"]
    assert (await as_token(token, "GET", C(w))).status_code == 200
    res = await as_token(token, "POST", f"{C(w)}/assignments/{a.id}/submissions", json={"body_text": "x"})
    assert res.status_code == 403


async def test_ort_course_works_and_stays_out_of_staff_lists(db, api):
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ru", language="ru", keep_images=False)
    assert ensure_ort_courses(db, samples=False).ok
    cid = course_id_for("ru")
    admin = make_user(db, platform_admin=True)
    enroll(db, db.get(Course, cid), admin, role="teacher", source="admin")
    token = (await enter(api, admin, cid))["access_token"]

    aid = db.scalar(select(Assessment.id).where(Assessment.course_id == cid))
    lobby = await as_token(token, "GET", f"/courses/{cid}/assessments/{aid}")
    assert lobby.status_code == 200 and lobby.json()["can_start"] is True, lobby.text
    st = await as_token(token, "POST", f"/courses/{cid}/assessments/{aid}/attempts", json={"language": "ru"})
    assert st.status_code == 201, st.text
    state = st.json()
    assert state["navigation"] == "section_forward_only" and len(state["sections"]) == 5
    tid = state["id"]
    assert (await as_token(token, "GET", f"/attempts/{tid}/content?section=1")).status_code == 200
    res = await as_token(token, "POST", f"/attempts/{tid}/submit", json={})
    assert res.status_code == 200 and res.json()["status"] == "graded", res.text
    res = await as_token(token, "GET", f"/attempts/{tid}/result")
    assert res.status_code == 200 and res.json()["grade"]["scheme_type"] == "piecewise_curve", res.text

    staff = await api.call(admin, "GET", f"/courses/{cid}/assessments/{aid}/attempts")
    assert staff.status_code == 200 and tid not in staff.text
    assert assessment_repo.attempt_counts(db, [aid])[aid]["submitted"] == 0


# ------------------------------------------------------------------ exclusions

async def _world_with_test_student_work(db, api):
    """A course whose only activity is the test student's: a submitted quiz, a pending hand-in and an open attempt."""
    w = structure_world(db)
    out, qs = await simple_published(api, db, w, 1)
    quiz_id = out["assessment"]["id"]
    db.get(Assessment, uuid.UUID(quiz_id)).allowed_attempts = -1
    db.commit()
    text = make_assignment(db, w.course, w.O, kind="text")
    token = (await enter(api, w.O, w.cid))["access_token"]
    attempt_id = await take_quiz(token, w.cid, quiz_id, qs, db)
    res = await as_token(token, "POST", f"{C(w)}/assignments/{text.id}/submissions", json={"body_text": "My work"})
    assert res.status_code in (200, 201), res.text
    st = await as_token(token, "POST", f"{C(w)}/assessments/{quiz_id}/attempts", json={})
    assert st.status_code == 201, st.text
    enr, user = test_rows(db, w.cid)[0]
    return w, quiz_id, text, token, attempt_id, st.json()["id"], enr, user


async def test_excluded_from_every_staff_surface(db, api):
    w, quiz_id, text, token, attempt_id, open_id, enr, user = await _world_with_test_student_work(db, api)
    secrets = (user.id, user.email, str(enr.id), "Test student", attempt_id, open_id)

    def clean(res):
        assert res.status_code == 200, res.text
        for s in secrets:
            assert s not in res.text, (s, res.text[:300])
        return res.json()

    # roster, counts
    people = clean(await api.call(w.O, "GET", f"{C(w)}/people", params={"role": "student"}))
    assert {i["user"]["id"] for i in people["items"]} == {w.S.id, w.S2.id}
    clean(await api.call(w.O, "GET", f"{C(w)}/people", params={"state": "removed"}))
    assert course_svc.active_student_count(db, w.course.id) == 2
    assert clean(await api.call(w.O, "GET", C(w)))["active_student_count"] == 2
    w.course.visibility, w.course.enrollment_mode, w.course.published_at = "catalog", "open", utcnow()
    db.commit()
    catalog = clean(await api.call(w.X, "GET", f"/catalog/courses/{w.cid}"))
    assert catalog["student_count"] == 2
    org_courses = clean(await api.call(w.OA, "GET", f"/org/{w.course.organization_id}/courses"))
    assert [c["active_student_count"] for c in org_courses["items"] if c["id"] == w.cid] == [2]
    assert clean(await api.call(w.O, "GET", f"{C(w)}/todo"))["active_students"] == 2

    # gradebook, queues
    gb = clean(await api.call(w.O, "GET", f"{C(w)}/gradebook"))
    assert {r["user_id"] for r in gb["rows"]} == {w.S.id, w.S2.id}
    assert all(c.get("submission_count", 0) == 0 and c.get("released_count", 0) == 0 for c in gb["assignments"])
    subs = clean(await api.call(w.O, "GET", f"{C(w)}/assignments/{text.id}/submissions"))
    assert {r["user_id"] for r in subs["rows"]} == {w.S.id, w.S2.id}
    assert all(r["hand_in_count"] == 0 for r in subs["rows"])
    assert clean(await api.call(w.O, "GET", f"{C(w)}/todo"))["to_grade_total"] == 0
    counts = assignment_svc.counts(db, [text.id])[text.id]
    assert (counts.submitted, counts.needs_grading) == (0, 0)
    detail = clean(await api.call(w.O, "GET", f"{C(w)}/assignments/{text.id}"))
    assert detail["counts"]["needs_grading"] == 0

    # attempts: lists, counts, locks and warnings
    assert clean(await api.call(w.O, "GET", f"{C(w)}/assessments/{quiz_id}/attempts"))["items"] == []
    aid = uuid.UUID(quiz_id)
    assert assessment_repo.attempt_counts(db, [aid])[aid] == {"in_progress": 0, "submitted": 0}
    assert assessment_repo.has_open_attempts(db, aid) is False
    v = db.get(Assessment, aid).published_version_id
    assert assessment_repo.version_attempt_counts(db, [v])[v] == {"in_progress": 0, "submitted": 0}
    built = clean(await api.call(w.O, "GET", f"{C(w)}/assessments/{quiz_id}"))
    assert built["attempt_counts"] == {"in_progress": 0, "submitted": 0}

    # per-student staff routes: 404 as for an unknown enrollment
    for method, path, body in (
            ("GET", f"{C(w)}/modules/progress/{enr.id}", None),
            ("PUT", f"{C(w)}/assignments/{text.id}/grades/{enr.id}", {"points": 5}),
            ("PUT", f"{C(w)}/enrollments/{enr.id}/accommodations", {"extra_time_percent": 50}),
            ("PATCH", f"{C(w)}/enrollments/{enr.id}", {"role": "assistant"}),
            ("DELETE", f"{C(w)}/enrollments/{enr.id}", None)):
        res = await api.call(w.O, method, path, json=body)
        assert res.status_code == 404, (method, path, res.text)

    # accommodations picker
    acc = clean(await api.call(w.O, "GET", f"{C(w)}/accommodations"))
    assert {i["enrollment_id"] for i in acc["items"]} == {str(w.enr.id), str(w.enr2.id)}

    # organization and platform numbers
    org_id = w.course.organization_id
    usage = clean(await api.call(w.OA, "GET", f"/org/{org_id}/usage"))
    assert usage["students"] == 2
    admin = make_user(db, platform_admin=True)
    found = clean(await api.call(admin, "GET", "/platform/users", params={"q": "test-student"}))
    assert found["items"] == []
    found = clean(await api.call(admin, "GET", "/platform/users", params={"q": "Test student"}))
    assert found["items"] == []
    assert (await api.call(admin, "GET", f"/platform/users/{user.id}")).status_code == 404
    listed = clean(await api.call(admin, "GET", "/platform/courses", params={"q": ""}))
    assert [c["active_student_count"] for c in listed["items"] if c["id"] == w.cid] == [2]
    clean(await api.call(admin, "GET", f"/platform/courses/{w.cid}/people"))


async def test_excluded_counts_stay_excluded_after_reset(db, api):
    w, quiz_id, text, token, attempt_id, open_id, enr, user = await _world_with_test_student_work(db, api)
    assert (await api.call(w.O, "POST", f"{C(w)}/student-view/reset")).status_code == 200
    db.expire_all()
    assert course_svc.active_student_count(db, w.course.id) == 2
    aid = uuid.UUID(quiz_id)
    assert assessment_repo.attempt_counts(db, [aid])[aid] == {"in_progress": 0, "submitted": 0}
    assert (await api.call(w.O, "GET", f"{C(w)}/people", params={"state": "removed"})).json()["items"] == []
    # the rows are still there
    assert db.get(Attempt, uuid.UUID(attempt_id)) is not None
    assert db.execute(select(func.count()).select_from(Submission).where(
        Submission.enrollment_id == enr.id)).scalar_one() >= 1


async def test_enrollment_limit_ignores_the_test_student(db, api):
    w = structure_world(db)
    w.course.enrollment_limit = 3
    w.course.enrollment_mode = "invite_code"
    w.course.join_code = "ABCD2345"
    db.commit()
    await enter(api, w.O, w.cid)  # S, S2 and the test student: 3 enrollments, 2 students
    joiner = make_user(db)
    res = await api.call(joiner, "POST", "/courses/join", json={"code": "ABCD2345"})
    assert res.status_code == 200, res.text
    too_many = make_user(db)
    assert (await api.call(too_many, "POST", "/courses/join", json={"code": "ABCD2345"})).status_code == 404


async def test_roster_query_never_returns_test_rows(db, api):
    w = structure_world(db)
    await enter(api, w.O, w.cid)
    rows = db.execute(roster_query(w.course.id, role="student")).all()
    assert {u.id for _e, u in rows} == {w.S.id, w.S2.id}


async def test_does_not_lock_or_warn_on_quiz_changes(db, api):
    """A test attempt neither asks for the publish confirmation nor stops a delete or a rubric change."""
    w, quiz_id, text, token, attempt_id, open_id, enr, user = await _world_with_test_student_work(db, api)
    res = await api.call(w.O, "POST", f"{C(w)}/assessments/{quiz_id}/unpublish")
    assert res.status_code == 200, res.text
    x = db.get(Assessment, uuid.UUID(quiz_id))
    db.refresh(x)
    a = await api.call(w.O, "PATCH", f"{C(w)}/assessments/{quiz_id}",
                       json={"draft_rev": x.draft_rev, "description": {"en": "New text"}})
    assert a.status_code == 200, a.text
    res = await api.call(w.O, "POST", f"{C(w)}/assessments/{quiz_id}/publish", json={})
    assert res.status_code == 200, res.text  # no `confirm_required`, although the test student used this version
    res = await api.call(w.O, "DELETE", f"{C(w)}/assessments/{quiz_id}")  # the open test attempt does not stop it
    assert res.status_code in (200, 204), res.text


async def test_test_attempt_does_not_hold_back_after_close_results(db, api):
    from app.lms.attempts import results

    w = structure_world(db)
    out, qs = await simple_published(api, db, w, 1)
    quiz_id = uuid.UUID(out["assessment"]["id"])
    token = (await enter(api, w.O, w.cid))["access_token"]
    res = await as_token(token, "POST", f"{C(w)}/assessments/{quiz_id}/attempts", json={})
    assert res.status_code == 201, res.text
    a = db.get(Assessment, quiz_id)
    a.results_policy = "after_close"
    a.available_until = utcnow() - timedelta(days=1)
    db.commit()
    assert results.after_close_open(db, a, utcnow()) is True


async def test_release_and_regrade_numbers_do_not_count_test_rows(db, api):
    w, quiz_id, text, token, attempt_id, open_id, enr, user = await _world_with_test_student_work(db, api)
    aid = db.execute(select(Submission.assignment_id).where(Submission.assessment_id == uuid.UUID(quiz_id),
                                                            Submission.enrollment_id == enr.id)).scalar_one()
    sub = db.execute(select(Submission).where(Submission.enrollment_id == enr.id,
                                              Submission.assignment_id == aid)).scalar_one()
    sub.released_at = None
    db.commit()
    res = await api.call(w.O, "POST", f"{C(w)}/assignments/{aid}/grades/release", json={})
    assert res.status_code == 200 and res.json()["released"] == 0, res.text
    db.expire_all()
    assert db.get(Submission, sub.id).released_at is not None  # the test student's own row still follows the class
    res = await api.call(w.O, "POST", f"{C(w)}/assignments/{aid}/grades/regrade")
    assert res.status_code == 200 and res.json()["regraded"] == 0 and res.json()["pending"] == 0, res.text


async def test_module_reapply_count_excludes_test_rows(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O, title={"en": "Week 1"})
    make_item(db, m, make_page(db, w.course, w.O), requirement=("view", None))
    token = (await enter(api, w.O, w.cid))["access_token"]
    assert (await as_token(token, "GET", f"{C(w)}/modules")).status_code == 200
    assert db.execute(select(func.count()).select_from(ModuleProgress)).scalar_one() >= 1
    res = await api.call(w.O, "POST", f"{C(w)}/modules/reapply")
    assert res.status_code == 200 and res.json()["cleared_students"] == 0, res.text


async def test_user_pickers_refuse_the_test_student(db, api):
    w = structure_world(db)
    await enter(api, w.O, w.cid)
    user = test_rows(db, w.cid)[0][1]
    other = make_course(db, w.O, organization_id=w.course.organization_id)
    res = await api.call(w.O, "POST", f"/courses/{other.id}/staff", json={"email": user.email, "role": "assistant"})
    assert res.status_code in (404, 422), res.text
    assert not db.execute(select(Enrollment.id).where(Enrollment.course_id == other.id,
                                                      Enrollment.user_id == user.id)).first()


# ------------------------------------------------------------------ the allow-list

def _fill(path: str, cid: str) -> str:
    path = path.replace("{course_id}", cid)
    return re.sub(r"\{[a-z_]+\}", lambda m: "1" if m.group(0) == "{pos}" else str(uuid.uuid4()), path)


def test_allow_list_names_real_routes_only():
    assert TEST_STUDENT_ROUTES - set(ROUTE_POLICIES) == set()


# Routes a real student may use that a test student must not, on purpose (PUR-3)
CLOSED_ON_PURPOSE = {
    ("POST", "/api/v1/courses/{course_id}/leave"),
    ("GET", "/api/v1/courses/{course_id}/bank-sharing"),  # the teachers' shared banks settings
}


def test_every_student_route_is_decided():
    """A route a student's role can pass and that is neither allowed nor closed on purpose fails here: a new student
    screen cannot silently break in Student view."""
    grants = ROLE_GRANTS["student"]
    missing = []
    for key, policy in ROUTE_POLICIES.items():
        if not policy.startswith("course:") or "+staff" in policy:
            continue
        action = policy[len("course:"):].split("+")[0]
        if action in grants and key not in TEST_STUDENT_ROUTES and key not in CLOSED_ON_PURPOSE:
            missing.append(key)
    assert missing == []


async def test_every_route_outside_the_list_is_refused(db, api):
    """Every route of the app, walked by its template: only listed ones get past the gate."""
    w = structure_world(db)
    token = (await enter(api, w.O, w.cid))["access_token"]
    public = {k for k, p in ROUTE_POLICIES.items() if p.startswith("public") or p == "internal_token"}
    routes = set(iter_routes(app))
    assert len(routes) > 200
    checked = 0
    for method, path in sorted(routes):
        if (method, path) in TEST_STUDENT_ROUTES or (method, path) in public or not path.startswith("/api/v1"):
            continue
        res = await as_token(token, method, _fill(path, w.cid)[len("/api/v1"):], json={})
        assert res.status_code == 403 and code(res) == "test_student_forbidden", (method, path, res.text[:200])
        checked += 1
    assert checked > 200


@pytest.mark.parametrize("method,path", [
    ("POST", "/courses/join"), ("POST", "/courses/{c}/join"), ("POST", "/courses/{c}/leave"),
    ("POST", "/courses/{c}/applications"), ("GET", "/catalog/courses"), ("GET", "/catalog/courses/{c}"),
    ("GET", "/me/invitations"), ("GET", "/me/applications"), ("GET", "/me/organizations"),
    ("GET", "/me/teacher-requests"), ("POST", "/me/teacher-requests"), ("PATCH", "/me/lms"),
    ("GET", "/platform/users"), ("GET", "/exam-templates"), ("GET", "/grading-schemes"),
    ("GET", "/org/{c}"), ("GET", "/org/{c}/members"), ("GET", "/courses/{c}/gradebook"),
    ("POST", "/courses"), ("GET", "/courses/trash"),
])
async def test_forbidden_groups(db, api, method, path):
    w = structure_world(db)
    token = (await enter(api, w.O, w.cid))["access_token"]
    res = await as_token(token, method, path.replace("{c}", w.cid), json={} if method != "GET" else None)
    assert res.status_code == 403 and code(res) == "test_student_forbidden", res.text


async def test_another_course_is_refused_in_any_spelling(db, api):
    w = structure_world(db)
    other = make_course(db, w.O, organization_id=w.course.organization_id, status="published")
    token = (await enter(api, w.O, w.cid))["access_token"]
    for spelled in (str(other.id), other.id.hex, f"urn:uuid:{other.id}", "{" + str(other.id) + "}"):
        res = await as_token(token, "GET", f"/courses/{spelled}")
        assert res.status_code == 403 and code(res) == "test_student_forbidden", (spelled, res.text)
    # and its own course in every spelling FastAPI accepts is the same decision
    for spelled in (w.course.id.hex, f"urn:uuid:{w.cid}", "{" + w.cid + "}"):
        res = await as_token(token, "GET", f"/courses/{spelled}")
        assert res.status_code == 200, (spelled, res.text)


async def test_raw_path_tricks_do_not_pass(db, api):
    w = structure_world(db)
    token = (await enter(api, w.O, w.cid))["access_token"]
    for path in (f"/courses/{w.cid}/../../platform/users", f"/courses/{w.cid}/%2e%2e/%2e%2e/platform/users"):
        res = await as_token(token, "GET", path)
        assert res.status_code in (403, 404), (path, res.text)
    # a query string cannot change the template
    res = await as_token(token, "GET", "/platform/users?x=/courses/" + w.cid)
    assert res.status_code == 403 and code(res) == "test_student_forbidden"


async def test_gate_runs_before_a_listed_route_of_a_retired_test_student(db, api):
    w = structure_world(db)
    token = (await enter(api, w.O, w.cid))["access_token"]
    assert (await api.call(w.O, "POST", f"{C(w)}/student-view/reset")).status_code == 200
    assert (await as_token(token, "GET", C(w))).status_code == 401


async def test_gate_costs_real_users_nothing(db, api):
    """Real users skip the gate: a real student reaches the routes closed to a test student."""
    w = structure_world(db)
    assert (await api.call(w.S, "GET", "/catalog/courses")).status_code == 200
    assert (await api.call(w.S, "GET", "/me/organizations")).status_code == 200
    assert (await api.call(w.S, "GET", "/me/invitations")).status_code == 200


async def test_get_lms_user_without_a_request_denies_a_test_student(db, api):
    from app.lms.core.deps import get_lms_user
    from app.lms.core.errors import Forbidden

    w = structure_world(db)
    token = (await enter(api, w.O, w.cid))["access_token"]
    with pytest.raises(Forbidden):
        get_lms_user(f"Bearer {token}", db)


# ------------------------------------------------------------------ 8c is gone; the staff preview stays

def test_no_view_as_left_in_authz():
    import app.core.authz as authz

    for name in ("VIEW_AS_HEADER", "VIEW_AS_STUDENT", "STUDENT_VIEW_READ_ONLY", "view_as_course_id", "is_preview_route"):
        assert not hasattr(authz, name), name
    assert not hasattr(authz.AuthzContext, "view_as_student")
    assert not hasattr(authz.AuthzContext, "real_role_for")


async def test_x_view_as_header_is_ignored(db, api):
    w = structure_world(db)
    res = await as_token(create_access_token({"sub": w.O.id}), "GET", C(w), headers={"X-View-As": "student"})
    assert res.status_code == 200, res.text
    assert res.json()["my_enrollment"]["role"] == "teacher" and "join_code" in res.json()
    res = await as_token(create_access_token({"sub": w.O.id}), "PATCH", C(w), json={"description": {"en": "x"}},
                         headers={"X-View-As": "student"})
    assert res.status_code != 403, res.text
    res = await as_token(create_access_token({"sub": w.S.id}), "GET", f"{C(w)}/gradebook",
                         headers={"X-View-As": "student"})
    assert res.status_code == 403


async def test_staff_preview_attempt_is_unchanged(db, api):
    w = structure_world(db)
    out, _qs = await simple_published(api, db, w, 1)
    quiz_id = out["assessment"]["id"]
    before = db.execute(select(func.count()).select_from(Submission)).scalar_one()
    url = f"{C(w)}/assessments/{quiz_id}/preview"
    for who in (w.O, w.T):
        res = await api.call(who, "POST", url, json={})
        assert res.status_code == 201 and res.json()["is_preview"] is True, res.text
    assert (await api.call(w.S, "POST", url, json={})).status_code == 403
    assert (await api.call(w.X, "POST", url, json={})).status_code == 404
    token = (await enter(api, w.O, w.cid))["access_token"]
    res = await as_token(token, "POST", url, json={})
    assert res.status_code == 403 and code(res) == "test_student_forbidden"
    db.expire_all()
    assert db.execute(select(func.count()).select_from(Submission)).scalar_one() == before
    # a preview stays out of the student lists and the counts, as before
    aid = uuid.UUID(quiz_id)
    assert assessment_repo.attempt_counts(db, [aid])[aid] == {"in_progress": 0, "submitted": 0}
    staff = await api.call(w.O, "GET", f"{C(w)}/assessments/{quiz_id}/attempts", params={"preview": "true"})
    assert staff.status_code == 200 and len(staff.json()["items"]) == 2, staff.text


async def test_course_serializers_follow_the_real_role(db, api):
    w = structure_world(db)
    assert "join_code" in (await api.call(w.O, "GET", C(w))).json()
    student = (await api.call(w.S, "GET", C(w))).json()
    assert student["my_enrollment"]["role"] == "student" and "join_code" not in student
    oa = (await api.call(w.OA, "GET", C(w))).json()
    assert "active_student_count" in oa  # A13: the org admin's staff view


async def test_file_routes_reachable_for_the_student_screens(db, api):
    w = structure_world(db)
    f = make_course_file(db, w.course, w.O)
    token = (await enter(api, w.O, w.cid))["access_token"]
    res = await as_token(token, "GET", f"{C(w)}/course-files")
    assert res.status_code == 200, res.text
    res = await as_token(token, "GET", f"{C(w)}/course-files/{f.id}/download")
    assert code(res) != "test_student_forbidden", res.text
    assert auth(w.O)  # the teacher's own session is untouched by any of this
    assert (await api.call(w.O, "GET", C(w))).json()["my_enrollment"]["role"] == "teacher"
