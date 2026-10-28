"""Phase 8b S1 (PHASE_8B_DESIGN 4 invariant 1, 5.1): a template's sandbox course (`sandbox_for_template_id` set) is
absent from every course list (owner, student, catalog, organization admin, platform admin, user detail, trash), is
not counted in organization usage, never makes anyone "staff in the organization", and every course-level write
refuses it with 409 `sandbox_course` (joins fail like an unknown code). Assessment routes still reach it.

The fixture inserts the sandbox row directly (S2 owns `sandbox.ensure`) and makes it published, catalog-visible and
open with an enrolled student, so the tests prove the new predicate rather than the status filters."""
from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

from app.lms.core.models import utcnow
from app.lms.enrollments.models import Enrollment
from app.lms.exam_templates import scopes as et_scopes
from tests.lms.exam_template_support import make_template
from tests.lms.factories import enroll, make_assessment, make_course, make_user
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _err(res):
    return res.json()["error"]["code"]


def sandbox_world(db):
    org = make_org(db, "Sandbox school")
    OA, TA = make_user(db), make_user(db, teacher_status="approved")
    add_member(db, org, OA, "org_admin")
    add_member(db, org, TA, "teacher")
    PA = make_user(db, platform_admin=True)
    S, X = make_user(db), make_user(db)
    t = make_template(db, owner_scope="organization", organization_id=org.id, created_by_id=TA.id)
    regular = make_course(db, TA, organization_id=org.id, status="published", visibility="catalog",
                          enrollment_mode="open", published_at=utcnow())
    enroll(db, regular, S, "student")
    sandbox = make_course(db, TA, organization_id=org.id, status="published", visibility="catalog",
                          enrollment_mode="open", published_at=utcnow(), sandbox_for_template_id=t.id,
                          title={"en": "Sandbox of the template"})
    enroll(db, sandbox, S, "student")
    assert sandbox.is_sandbox and not regular.is_sandbox
    return SimpleNamespace(org=org, OA=OA, TA=TA, PA=PA, S=S, X=X, t=t, regular=regular, sandbox=sandbox,
                           rid=str(regular.id), sid=str(sandbox.id))


def _ids(res) -> set:
    assert res.status_code == 200, res.text
    return {x["id"] for x in res.json()["items"]}


async def test_sandbox_absent_from_every_course_list(db, api):
    w = sandbox_world(db)
    for user, params in ((w.TA, {}), (w.TA, {"as": "teaching"}), (w.S, {"as": "learning"}), (w.S, {})):
        ids = _ids(await api.call(user, "GET", "/courses", params=params))
        assert w.sid not in ids and w.rid in ids, (user.id, params)
    for user in (w.S, w.X):
        ids = _ids(await api.call(user, "GET", "/catalog/courses"))
        assert w.sid not in ids and w.rid in ids
    ids = _ids(await api.call(w.OA, "GET", f"/org/{w.org.id}/courses"))
    assert w.sid not in ids and w.rid in ids
    ids = _ids(await api.call(w.PA, "GET", "/platform/courses"))
    assert w.sid not in ids and w.rid in ids
    ids = _ids(await api.call(w.PA, "GET", "/platform/courses", params={"q": "sandbox"}))
    assert w.sid not in ids
    detail = await api.call(w.PA, "GET", f"/platform/users/{w.TA.id}")
    assert detail.status_code == 200, detail.text
    owned = {c["id"] for c in detail.json()["owned_courses"]}
    assert w.sid not in owned and w.rid in owned


async def test_sandbox_not_counted_in_organization_usage(db, api):
    w = sandbox_world(db)
    overview = await api.call(w.OA, "GET", f"/org/{w.org.id}")
    assert overview.status_code == 200, overview.text
    assert overview.json()["usage"]["courses"] == 1 and overview.json()["usage"]["students"] == 1
    usage = await api.call(w.PA, "GET", f"/platform/organizations/{w.org.id}/usage")
    assert usage.status_code == 200 and usage.json()["courses"] == 1, usage.text


async def test_deleted_sandbox_absent_from_trash(db, api):
    w = sandbox_world(db)
    w.sandbox.deleted_at, w.sandbox.deleted_by_id = utcnow(), w.TA.id
    w.regular.deleted_at, w.regular.deleted_by_id = utcnow(), w.TA.id
    db.commit()
    ids = _ids(await api.call(w.TA, "GET", "/courses/trash"))
    assert w.sid not in ids and w.rid in ids


def test_sandbox_staff_is_not_staff_in_the_organization(db):
    w = sandbox_world(db)
    U = make_user(db, teacher_status="approved")
    enroll(db, w.sandbox, U, "teacher", source="staff_add")
    assert et_scopes._staff_in_org(db, U.id, w.org.id) is False
    enroll(db, w.regular, U, "assistant", source="staff_add")
    assert et_scopes._staff_in_org(db, U.id, w.org.id) is True


async def test_course_writes_refuse_the_sandbox(db, api):
    w = sandbox_world(db)
    c = f"/courses/{w.sid}"
    writes = [
        ("PATCH", c, {"title": {"en": "Renamed"}}),
        ("POST", f"{c}/publish", None),
        ("POST", f"{c}/unpublish", None),
        ("POST", f"{c}/conclude", None),
        ("DELETE", c, None),
        ("POST", f"{c}/join-code/regenerate", None),
        ("POST", f"{c}/staff", {"email": w.OA.email, "role": "assistant"}),
        ("POST", f"{c}/staff/invitations", {"email": "new.person@example.org", "role": "assistant"}),
    ]
    for method, path, body in writes:
        res = await api.call(w.TA, method, path, json=body)
        assert res.status_code == 409 and _err(res) == "sandbox_course", (method, path, res.text)
    res = await api.call(w.PA, "POST", f"/platform/courses/{w.sid}/delete", json={"reason": "cleanup of a sandbox"})
    assert res.status_code == 409 and _err(res) == "sandbox_course", res.text
    db.expire_all()
    assert w.sandbox.deleted_at is None and w.sandbox.status == "published"
    # the regular course of the same owner is unaffected
    ok = await api.call(w.TA, "PATCH", f"/courses/{w.rid}", json={"title": {"en": "Renamed"}})
    assert ok.status_code == 200, ok.text


async def test_joins_fail_like_an_unknown_course(db, api):
    w = sandbox_world(db)
    for path, body in (("/courses/join", {"code": w.sandbox.join_code}), (f"/courses/{w.sid}/join", None)):
        res = await api.call(w.X, "POST", path, json=body)
        assert res.status_code == 404, (path, res.text)
    assert db.execute(select(Enrollment).where(Enrollment.course_id == w.sandbox.id,
                                               Enrollment.user_id == w.X.id)).first() is None


async def test_sample_assessment_reachable_but_not_deletable(db, api):
    w = sandbox_world(db)
    a = make_assessment(db, w.sandbox, w.TA)
    p = f"/courses/{w.sid}/assessments/{a.id}"
    assert (await api.call(w.TA, "GET", p)).status_code == 200
    res = await api.call(w.TA, "DELETE", p)
    assert res.status_code == 409 and _err(res) == "sandbox_course", res.text
    db.refresh(a)
    assert a.deleted_at is None
    # a regular course's assessment is still deletable
    b = make_assessment(db, w.regular, w.TA)
    assert (await api.call(w.TA, "DELETE", f"/courses/{w.rid}/assessments/{b.id}")).status_code == 204


def test_ort_courses_are_not_sandboxes(db):
    from app.lms.courses.models import Course
    from app.lms.ort.seed import ensure_ort_courses

    ensure_ort_courses(db, samples=False)
    rows = db.execute(select(Course)).scalars().all()
    assert len(rows) == 2 and all(c.sandbox_for_template_id is None and not c.is_sandbox for c in rows)
