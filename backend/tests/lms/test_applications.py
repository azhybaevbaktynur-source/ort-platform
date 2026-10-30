"""Phase 9 S4: applications state machine, visibility matrix, emails (PHASE_9_DESIGN 4.7-4.9, 5.1)."""
from sqlalchemy import select

from app.lms.audit.models import AdminAuditLog
from app.lms.enrollment_forms.models import EnrollmentApplication
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from tests.lms.application_support import (  # noqa: F401
    SECRET_NAME, _purge_throttle_and_mail, answers, api, apply, catalog_course, clean_rate_limits, db, enroll,
    form_course, make_form, make_user, sent_mails, teacher,
)
from tests.lms.org_support import add_member, make_org


def _enr(db, course, user):
    db.expire_all()
    return db.execute(select(Enrollment).where(Enrollment.course_id == course.id,
                                               Enrollment.user_id == user.id)).scalar_one_or_none()


async def test_submit_validation_per_type(db, api):
    c, form, _ = await form_course(db, api)
    s = make_user(db)
    r = await apply(api, s, c, form, {"full_name": "", "grade": "g99", "phone": "12", "extra": "x"})
    assert r.status_code == 422
    details = r.json()["error"]["details"]
    assert {(d["field_key"], d["type"]) for d in details} == {
        ("full_name", "required"), ("grade", "bad_option"), ("phone", "bad_format"), ("extra", "bad_format")}
    r = await apply(api, s, c, form, answers(about="x" * 1001))
    assert r.status_code == 422 and r.json()["error"]["details"] == [{"field_key": "about", "type": "too_long"}]


async def test_review_submit_then_approve(db, api):
    c, form, t = await form_course(db, api)
    s = make_user(db)
    r = await apply(api, s, c, form)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending" and body["answers"]["full_name"] == SECRET_NAME
    assert body["answers"]["phone"] == "+996555123456"  # normalized
    assert [m.subject for m in sent_mails()] == ["Application received: Test course"]
    # a second pending application is refused
    r = await apply(api, s, c, form)
    assert r.status_code == 409 and r.json()["error"]["code"] == "application_pending"
    app_id = body["id"]
    assert _enr(db, c, s) is None
    r = await api.call(t, "POST", f"/courses/{c.id}/applications/{app_id}/approve", json={"note": "Welcome"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["enrollment_id"]
    enr = _enr(db, c, s)
    assert enr.state == "active" and enr.role == "student" and enr.source == "form"
    assert db.execute(select(EnrollmentEvent.event).where(EnrollmentEvent.enrollment_id == enr.id)).scalars().all() \
        == ["joined"]
    # decided once
    r = await api.call(t, "POST", f"/courses/{c.id}/applications/{app_id}/reject", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "application_decided"
    assert len(sent_mails()) == 2 and "Welcome" not in sent_mails()[1].text  # note not ticked
    audit = db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == str(c.id),
                                                   AdminAuditLog.action == "course.application_approved")).scalar_one()
    assert audit.target_type == "course" and audit.details == {"application_id": app_id, "status": "approved"}
    # enrolled: a new application is refused
    r = await apply(api, s, c, form)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_enrolled"


async def test_form_auto_enrolls_in_the_same_transaction(db, api):
    c, form, _ = await form_course(db, api, mode="form_auto")
    s = make_user(db)
    r = await apply(api, s, c, form)
    assert r.status_code == 201 and r.json()["status"] == "approved"
    assert _enr(db, c, s).state == "active"
    app = db.get(EnrollmentApplication, __import__("uuid").UUID(r.json()["id"]))
    assert app.decided_by_id is None and app.enrollment_id is not None
    assert sent_mails()[-1].subject.startswith("You are enrolled")


async def test_form_auto_on_a_full_course_stays_pending(db, api):
    c, form, t = await form_course(db, api, mode="form_auto", enrollment_limit=1)
    enroll(db, c, make_user(db))
    s = make_user(db)
    r = await apply(api, s, c, form)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    r = await api.call(t, "POST", f"/courses/{c.id}/applications/{r.json()['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "course_full"
    db.expire_all()
    assert db.execute(select(EnrollmentApplication.status).where(
        EnrollmentApplication.user_id == s.id)).scalar_one() == "pending"


async def test_reject_with_note_and_reapply(db, api):
    c, form, t = await form_course(db, api)
    s = make_user(db)
    app_id = (await apply(api, s, c, form)).json()["id"]
    r = await api.call(t, "POST", f"/courses/{c.id}/applications/{app_id}/reject",
                       json={"note": "Course is for grade 11", "send_note": True})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert "Course is for grade 11" in sent_mails()[-1].text
    db.expire_all()
    row = db.get(EnrollmentApplication, __import__("uuid").UUID(app_id))
    assert row.purge_after is not None and row.answers is not None
    mine = (await api.call(s, "GET", "/me/applications")).json()["items"]
    assert mine[0]["status"] == "rejected" and mine[0]["decision_note"] == "Course is for grade 11"
    # re-application after a rejection is a new row
    r = await apply(api, s, c, form)
    assert r.status_code == 201 and r.json()["id"] != app_id


async def test_withdraw_only_by_the_applicant(db, api):
    c, form, t = await form_course(db, api)
    s, other = make_user(db), make_user(db)
    app_id = (await apply(api, s, c, form)).json()["id"]
    n_mails = len(sent_mails())
    path = f"/courses/{c.id}/applications/{app_id}/withdraw"
    assert (await api.call(other, "POST", path)).status_code == 404
    assert (await api.call(t, "POST", path)).status_code == 404
    r = await api.call(s, "POST", path)
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    assert len(sent_mails()) == n_mails  # no email on withdraw
    r = await api.call(s, "POST", path)
    assert r.status_code == 409 and r.json()["error"]["code"] == "application_decided"
    r = await api.call(t, "POST", f"/courses/{c.id}/applications/{app_id}/approve", json={})
    assert r.status_code == 409


async def test_assistant_reads_answers_but_cannot_decide(db, api):
    c, form, t = await form_course(db, api)
    a = make_user(db)
    enroll(db, c, a, role="assistant")
    app_id = (await apply(api, make_user(db), c, form)).json()["id"]
    r = await api.call(a, "GET", f"/courses/{c.id}/applications/{app_id}")
    assert r.status_code == 200 and r.json()["answers"]["full_name"] == SECRET_NAME
    assert [f["key"] for f in r.json()["fields"]] == ["full_name", "phone", "grade", "about"]
    r = await api.call(a, "POST", f"/courses/{c.id}/applications/{app_id}/approve", json={})
    assert r.status_code == 403


async def test_visibility_matrix(db, api):
    org = make_org(db)
    c, form, t = await form_course(db, api, organization_id=org.id)
    applicant, other_student, org_admin = make_user(db), make_user(db), make_user(db)
    platform_admin = make_user(db, platform_admin=True)
    enroll(db, c, other_student)
    add_member(db, org, org_admin, role="org_admin")
    app_id = (await apply(api, applicant, c, form)).json()["id"]
    one = f"/courses/{c.id}/applications/{app_id}"
    lst = f"/courses/{c.id}/applications"
    # teacher: answers in the detail, never in the list
    r = await api.call(t, "GET", one)
    assert r.json()["answers"]["full_name"] == SECRET_NAME
    r = await api.call(t, "GET", lst)
    assert r.status_code == 200 and SECRET_NAME not in r.text and r.json()["items"][0]["has_answers"] is True
    # org admin: statuses only (no answers, no fields)
    r = await api.call(org_admin, "GET", one)
    assert r.status_code == 200 and "answers" not in r.json() and SECRET_NAME not in r.text
    r = await api.call(org_admin, "GET", lst)
    assert r.status_code == 200 and SECRET_NAME not in r.text
    # other student: 403; platform admin and outsiders: 404
    assert (await api.call(other_student, "GET", one)).status_code == 403
    assert (await api.call(platform_admin, "GET", one)).status_code == 404
    assert (await api.call(make_user(db), "GET", lst)).status_code == 404
    # applicant: own answers in /me/applications only
    mine = await api.call(applicant, "GET", "/me/applications")
    assert mine.json()["items"][0]["answers"]["full_name"] == SECRET_NAME
    assert SECRET_NAME not in (await api.call(other_student, "GET", "/me/applications")).text
    # the org admin may decide (roster management, A13), still without seeing answers
    r = await api.call(org_admin, "POST", f"{one}/approve", json={})
    assert r.status_code == 200 and SECRET_NAME not in r.text


async def test_inbox_filters_search_and_pagination(db, api):
    c, form, t = await form_course(db, api)
    users = [make_user(db, display_name=f"Student {i}") for i in range(5)]
    ids_ = [(await apply(api, u, c, form)).json()["id"] for u in users]
    await api.call(t, "POST", f"/courses/{c.id}/applications/{ids_[0]}/reject", json={})
    r = await api.call(t, "GET", f"/courses/{c.id}/applications", params={"status": "pending", "limit": 2})
    page = r.json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    r2 = await api.call(t, "GET", f"/courses/{c.id}/applications",
                        params={"status": "pending", "limit": 2, "cursor": page["next_cursor"]})
    seen = [i["id"] for i in page["items"] + r2.json()["items"]]
    assert len(set(seen)) == 4 and ids_[0] not in seen
    r = await api.call(t, "GET", f"/courses/{c.id}/applications", params={"q": "student 3"})
    assert [i["applicant"]["id"] for i in r.json()["items"]] == [users[3].id]
    # search never matches answer content
    r = await api.call(t, "GET", f"/courses/{c.id}/applications", params={"q": "Hidden Street"})
    assert r.json()["items"] == []


async def test_submit_refusals(db, api):
    t = teacher(db)
    s = make_user(db)
    # not in a form mode
    c = catalog_course(db, t, mode="open")
    form = await make_form(api, t, c)
    r = await apply(api, s, c, form)
    assert r.status_code == 409 and r.json()["error"]["code"] == "course_not_open"
    # private course: 404
    c2, form2, _ = await form_course(db, api)
    c2.visibility = "private"
    db.commit()
    assert (await apply(api, s, c2, form2)).status_code == 404
    # stale form id after a new version was activated
    c3, form3, t3 = await form_course(db, api)
    nv = (await api.call(t3, "POST", f"/courses/{c3.id}/enrollment-forms/{form3['id']}/new-version")).json()
    await api.call(t3, "POST", f"/courses/{c3.id}/enrollment-forms/{nv['id']}/activate")
    r = await apply(api, s, c3, form3)
    assert r.status_code == 409 and r.json()["error"]["code"] == "form_changed"


async def test_rate_limit_counts_sent_applications(db, api):
    from app.lms.enrollment_forms import applications as apps

    c, form, t = await form_course(db, api)
    s = make_user(db)
    for _ in range(3):  # invalid answers do not use up the budget
        assert (await apply(api, s, c, form, {"full_name": ""})).status_code == 422
    for i in range(apps.APPLY_USER_24H.limit):
        r = await apply(api, s, c, form)
        assert r.status_code == 201, (i, r.text)
        assert (await api.call(s, "POST", f"/courses/{c.id}/applications/{r.json()['id']}/withdraw")).status_code == 200
    r = await apply(api, s, c, form)
    assert r.status_code == 429


async def test_unenroll_sets_purge_after(db, api):
    c, form, t = await form_course(db, api, mode="form_auto")
    s = make_user(db)
    app_id = (await apply(api, s, c, form)).json()["id"]
    assert (await api.call(s, "POST", f"/courses/{c.id}/leave")).status_code in (200, 204)
    db.expire_all()
    assert db.get(EnrollmentApplication, __import__("uuid").UUID(app_id)).purge_after is not None


async def test_concluded_course_refuses_approve_allows_reject(db, api):
    c, form, t = await form_course(db, api)
    a1 = (await apply(api, make_user(db), c, form)).json()["id"]
    a2 = (await apply(api, make_user(db), c, form)).json()["id"]
    c.status = "concluded"
    db.commit()
    r = await api.call(t, "POST", f"/courses/{c.id}/applications/{a1}/approve", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "course_not_open"
    r = await api.call(t, "POST", f"/courses/{c.id}/applications/{a2}/reject", json={})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    a = make_user(db)
    enroll(db, c, a, role="assistant")
    r = await api.call(a, "POST", f"/courses/{c.id}/applications/{a1}/reject", json={})
    assert r.status_code == 403
