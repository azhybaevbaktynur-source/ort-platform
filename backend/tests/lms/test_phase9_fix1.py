"""Phase 9 fix 1: review findings on S1 (authz tree, `can_edit_bank`, the content router's bank gates).

- M1: `can_edit_bank` decides from the course's organization, not the bank's denormalized `organization_id`.
- M2: a department's own suspension counts (row or root suspended), in `_org` and in the resolver hint.
- L2: a translation link checks every bank of both questions' translation groups.
- L3: the org-admin branch never deletes or restores a whole bank (staff keep both).
- L4: the resolver sets the suspension hint for department courses in the same statement (no extra statements)."""
from sqlalchemy import event, update

from app.core.authz import A, AuthzContext, can, enrollment_role_resolver
from app.db.session import engine
from app.lms.content.models import QuestionBank
from app.lms.content.permissions import can_edit_bank
from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from tests.lms.factories import make_bank, make_question
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user  # noqa: F401


def ctx_for(db, user) -> AuthzContext:
    return AuthzContext(user, db, enrollment_role_resolver(db, user.id))


def err(r):
    return r.json()["error"]["code"]


class W:
    pass


def world(db) -> W:
    w = W()
    w.R = make_org(db, "R")
    w.D, w.D2 = make_department(db, w.R, "D"), make_department(db, w.R, "D2")
    w.T = make_user(db)
    add_member(db, w.D, w.T, "teacher")
    w.C = make_course(db, w.T, organization_id=w.D.id, status="published")
    w.B = make_bank(db, w.C, w.T, title="Shared", visibility="organization", shared_at=utcnow(), shared_by_id=w.T.id)
    w.PB = make_bank(db, w.C, w.T, title="Private")
    w.admins = {}
    for key, org in (("R", w.R), ("D", w.D), ("D2", w.D2)):
        u = make_user(db)
        add_member(db, org, u, "org_admin")
        w.admins[key] = u
    return w


# ------------------------------------------------------------------ M1

def test_m1_course_moved_between_departments_follows_the_course(db):
    w = world(db)
    assert can_edit_bank(ctx_for(db, w.admins["D"]), w.C, w.B)
    assert not can_edit_bank(ctx_for(db, w.admins["D2"]), w.C, w.B)
    # the course moves from D to D2; the bank keeps its denormalized organization id (S2 rewrites it, not here)
    db.execute(update(Course).where(Course.id == w.C.id).values(organization_id=w.D2.id))
    db.commit()
    db.expire_all()
    course, bank = db.get(Course, w.C.id), db.get(QuestionBank, w.B.id)
    assert course.organization_id == w.D2.id and bank.organization_id == w.D.id
    assert not can_edit_bank(ctx_for(db, w.admins["D"]), course, bank)
    assert can_edit_bank(ctx_for(db, w.admins["D2"]), course, bank)
    assert can_edit_bank(ctx_for(db, w.admins["R"]), course, bank)


# ------------------------------------------------------------------ M2

async def test_m2_department_own_suspension_counts(db, api):
    w = world(db)
    student = make_user(db)
    enroll(db, w.C, student)
    w.D.status, w.D.suspended_at = "suspended", utcnow()
    db.commit()
    assert w.R.status == "active"
    # enrolled users: the resolver hint says suspended (department row), writes refused, reads kept
    for user, action in ((w.T, A.CONTENT_MANAGE), (student, A.ASSESSMENT_TAKE)):
        c = ctx_for(db, user)
        assert c.role_for(w.C.id) is not None
        assert c.role_resolver.org_status[w.C.id] == "suspended"
        assert c.org_suspended(w.D.id, w.C.id)
        assert not can(c, action, w.C)
        assert can(c, A.COURSE_READ, w.C)
    # org admins (no enrollment, `_org` through the path): no bank edit right while the department is suspended
    for key in ("R", "D"):
        c = ctx_for(db, w.admins[key])
        assert c.org_suspended(w.D.id)
        assert not can_edit_bank(c, w.C, w.B)
    # the routes say why
    C = f"/courses/{w.C.id}"
    for user in (w.T, w.admins["R"], w.admins["D"]):
        r = await api.call(user, "PATCH", f"{C}/banks/{w.B.id}", json={"title": "nope"})
        assert r.status_code == 403 and err(r) == "organization_suspended", (user.id, r.status_code, r.text)
    # a suspended sibling does not reach this department
    w.D.status, w.D.suspended_at = "active", None
    w.D2.status, w.D2.suspended_at = "suspended", utcnow()
    db.commit()
    assert can_edit_bank(ctx_for(db, w.admins["R"]), w.C, w.B)
    assert can(ctx_for(db, w.T), A.CONTENT_MANAGE, w.C)


# ------------------------------------------------------------------ L2

async def test_l2_link_checks_every_bank_of_both_groups(db, api):
    w = world(db)
    C = f"/courses/{w.C.id}"
    admin = w.admins["R"]
    q_en = make_question(db, w.B, w.T, language="en")
    q_ru_private = make_question(db, w.PB, w.T, language="ru")
    q_ky = make_question(db, w.B, w.T, language="ky")
    q_ru = make_question(db, w.B, w.T, language="ru")
    # staff put q_en (shared bank) and q_ru_private (private bank) into one group
    r = await api.call(w.T, "POST", f"{C}/questions/{q_en.id}/translation-link",
                       json={"question_id": str(q_ru_private.id)})
    assert r.status_code == 204, r.text
    # both questions are in the shared bank, but q_en's group spans the private bank: refused both ways
    for a, b in ((q_ky, q_en), (q_en, q_ky)):
        r = await api.call(admin, "POST", f"{C}/questions/{a.id}/translation-link", json={"question_id": str(b.id)})
        assert r.status_code == 403, r.text
    db.expire_all()
    assert db.get(type(q_ky), q_ky.id).translation_group_id is None
    # two shared-bank questions without groups: allowed
    r = await api.call(admin, "POST", f"{C}/questions/{q_ky.id}/translation-link", json={"question_id": str(q_ru.id)})
    assert r.status_code == 204, r.text
    # staff may still join the private-spanning group
    r = await api.call(w.T, "POST", f"{C}/questions/{q_en.id}/translation-link",
                       json={"question_id": str(make_question(db, w.B, w.T, language="ky").id)})
    assert r.status_code == 204, r.text


# ------------------------------------------------------------------ L3

async def test_l3_org_admin_cannot_delete_or_restore_a_shared_bank(db, api):
    w = world(db)
    C = f"/courses/{w.C.id}"
    admin = w.admins["R"]
    assert can_edit_bank(ctx_for(db, admin), w.C, w.B)  # content editing stays allowed
    r = await api.call(admin, "DELETE", f"{C}/banks/{w.B.id}")
    assert r.status_code == 403, r.text
    db.expire_all()
    assert db.get(QuestionBank, w.B.id).deleted_at is None
    # staff delete and restore as before; the org admin cannot restore either
    r = await api.call(w.T, "DELETE", f"{C}/banks/{w.B.id}")
    assert r.status_code == 204, r.text
    r = await api.call(admin, "POST", f"{C}/banks/{w.B.id}/restore")
    assert r.status_code == 403, r.text
    db.expire_all()
    assert db.get(QuestionBank, w.B.id).deleted_at is not None
    r = await api.call(w.T, "POST", f"{C}/banks/{w.B.id}/restore")
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(QuestionBank, w.B.id).deleted_at is None


# ------------------------------------------------------------------ L4

class _Counter:
    def __init__(self):
        self.n = 0

    def __call__(self, conn, cursor, statement, *a):
        self.n += 1


def _write_statements(db, user, course) -> int:
    db.expire_all()
    course = db.get(Course, course.id)
    _ = (user.id, user.is_platform_admin, course.status)  # loaded before counting
    counter = _Counter()
    event.listen(engine, "before_cursor_execute", counter)
    try:
        ctx = ctx_for(db, user)
        assert can(ctx, A.CONTENT_MANAGE, course)
        assert can(ctx, A.CONTENT_MANAGE, course)  # cached: no further statements
    finally:
        event.remove(engine, "before_cursor_execute", counter)
    return counter.n


def test_l4_department_course_write_costs_what_a_root_course_write_costs(db):
    w = world(db)
    root_course = make_course(db, w.T, organization_id=w.R.id, status="published")
    sub = make_department(db, w.D, "S")
    sub_course = make_course(db, w.T, organization_id=sub.id, status="published")
    n_root = _write_statements(db, w.T, root_course)
    assert n_root == 1  # the resolver statement only (role, statuses, sandbox)
    assert _write_statements(db, w.T, w.C) == n_root
    assert _write_statements(db, w.T, sub_course) == n_root
    # the hint follows the root for a department two levels down
    w.R.status, w.R.suspended_at = "suspended", utcnow()
    db.commit()
    c = ctx_for(db, w.T)
    assert not can(c, A.CONTENT_MANAGE, sub_course)
    assert c.role_resolver.org_status[sub_course.id] == "suspended"
