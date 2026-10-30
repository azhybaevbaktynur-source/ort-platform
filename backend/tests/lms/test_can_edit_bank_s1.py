"""Phase 9 S1: `content.permissions.can_edit_bank` and the `_manage_bank` route gate (PHASE_9_DESIGN 4.2, 5.1 row
"Shared bank: share/unshare/edit", P7C-10, P9-2, alternative 15-1 default).

Matrix on a course C in department D of school R (bank B shared with the organization, bank PB private):

| caller                                   | B (organization) | PB (private) |
|------------------------------------------|------------------|--------------|
| C's teacher / assistant                  | yes              | yes          |
| org admin of R (root) / of D (bank org)  | yes              | no           |
| org admin of D2 (sibling) / S (below D)  | no               | no           |
| org admin of school X / an independent   | no               | no           |
| student of C / teacher of R not on C     | no               | no           |
| platform admin (flag only)               | no               | no           |

and every staff gate holds for the org-admin branch: deleted bank, bank of another course, concluded / deleted
course, suspended root, ORT template course, Student view."""
import pytest

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.lms.content.permissions import can_edit_bank
from app.lms.core.models import utcnow
from tests.lms.content_support import qbody
from tests.lms.factories import make_bank, make_question
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


def ctx_for(db, user) -> AuthzContext:
    return AuthzContext(user, db, enrollment_role_resolver(db, user.id))


class W:
    pass


def world(db) -> W:
    w = W()
    w.R, w.X = make_org(db, "R"), make_org(db, "X")
    w.D, w.D2 = make_department(db, w.R, "D"), make_department(db, w.R, "D2")
    w.S = make_department(db, w.D, "S")
    w.T, w.asst, w.stud, w.T2 = (make_user(db) for _ in range(4))
    add_member(db, w.D, w.T, "teacher")
    add_member(db, w.R, w.T2, "teacher")
    w.C = make_course(db, w.T, organization_id=w.D.id, status="published")
    enroll(db, w.C, w.asst, role="assistant", source="staff_add")
    enroll(db, w.C, w.stud)
    w.B = make_bank(db, w.C, w.T, title="Shared", visibility="organization", shared_at=utcnow(), shared_by_id=w.T.id)
    w.PB = make_bank(db, w.C, w.T, title="Private")
    assert w.B.organization_id == w.D.id and w.PB.visibility == "private"
    w.admins = {}
    for key, org in (("R", w.R), ("D", w.D), ("D2", w.D2), ("S", w.S), ("X", w.X)):
        u = make_user(db)
        add_member(db, org, u, "org_admin")
        w.admins[key] = u
    w.indep = teacher(db)
    w.pa = make_user(db, platform_admin=True)
    return w


def test_matrix(db):
    w = world(db)
    yes_both = [w.T, w.asst]
    shared_only = [w.admins["R"], w.admins["D"]]
    none = [w.admins["D2"], w.admins["S"], w.admins["X"], w.indep, w.stud, w.T2, w.pa]
    for u in yes_both:
        c = ctx_for(db, u)
        assert can_edit_bank(c, w.C, w.B) and can_edit_bank(c, w.C, w.PB), u.id
    for u in shared_only:
        c = ctx_for(db, u)
        assert can_edit_bank(c, w.C, w.B) and not can_edit_bank(c, w.C, w.PB), u.id
    for u in none:
        c = ctx_for(db, u)
        assert not can_edit_bank(c, w.C, w.B) and not can_edit_bank(c, w.C, w.PB), u.id


def test_gates_of_the_org_admin_branch(db):
    w = world(db)
    admin = w.admins["R"]
    other = make_course(db, w.T, organization_id=w.D.id, status="published")
    assert not can_edit_bank(ctx_for(db, admin), other, w.B)          # bank of another course
    assert not can_edit_bank(ctx_for(db, admin), w.C, None)
    w.C.status = "concluded"
    db.commit()
    assert not can_edit_bank(ctx_for(db, admin), w.C, w.B)
    assert not can_edit_bank(ctx_for(db, w.T), w.C, w.B)              # staff cannot either (content.manage)
    w.C.status = "published"
    w.R.status, w.R.suspended_at = "suspended", utcnow()               # suspension through the root
    db.commit()
    assert not can_edit_bank(ctx_for(db, admin), w.C, w.B)
    assert not can_edit_bank(ctx_for(db, w.admins["D"]), w.C, w.B)
    w.R.status, w.R.suspended_at = "active", None
    w.B.deleted_at = utcnow()
    db.commit()
    assert not can_edit_bank(ctx_for(db, admin), w.C, w.B)
    w.B.deleted_at = None
    w.C.deleted_at = utcnow()
    db.commit()
    assert not can_edit_bank(ctx_for(db, admin), w.C, w.B)
    w.C.deleted_at = None
    db.commit()
    assert can_edit_bank(ctx_for(db, admin), w.C, w.B)
    # Student view: the org admin power is switched off for that course's organization
    c = ctx_for(db, w.T)
    c.view_as_course = w.C.id
    assert not can_edit_bank(c, w.C, w.B)


def test_ort_course_bank_never_editable_by_org_admin(db):
    w = world(db)
    ort = make_course(db, w.T, organization_id=w.D.id, status="published", template_key="ort", template_version=1,
                      template_locked=True)
    bank = make_bank(db, ort, w.T, visibility="organization")  # not reachable through the share service (S2)
    assert not can_edit_bank(ctx_for(db, w.admins["R"]), ort, bank)
    assert can_edit_bank(ctx_for(db, w.T), ort, bank)  # staff keep content.manage as today


async def test_routes_use_manage_bank(db, api):
    w = world(db)
    q_shared = make_question(db, w.B, w.T)
    q_private = make_question(db, w.PB, w.T)
    C = f"/courses/{w.C.id}"
    admin = w.admins["R"]
    # writes on the shared bank: the org admin of the tree may edit it like the course staff
    r = await api.call(admin, "PATCH", f"{C}/banks/{w.B.id}", json={"title": "Shared v2"})
    assert r.status_code == 200, r.text
    r = await api.call(admin, "POST", f"{C}/banks/{w.B.id}/questions", json=qbody())
    assert r.status_code == 201, r.text
    r = await api.call(admin, "POST", f"{C}/banks/{w.B.id}/passages", json={"language": "en", "body": "Text"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = await api.call(admin, "POST", f"{C}/questions/{q_shared.id}/move", json={"direction": "down"})
    assert r.status_code == 200, r.text
    r = await api.call(admin, "DELETE", f"{C}/passages/{pid}")
    assert r.status_code == 204, r.text
    # the private bank of the same course stays staff-only (the org admin reads the course: 403, not 404)
    for m, p, body in (("PATCH", f"{C}/banks/{w.PB.id}", {"title": "x"}),
                       ("POST", f"{C}/banks/{w.PB.id}/questions", qbody()),
                       ("DELETE", f"{C}/questions/{q_private.id}", None),
                       ("POST", f"{C}/banks", {"title": "new"}),
                       ("POST", f"{C}/questions/{q_shared.id}/translation-link", {"question_id": str(q_private.id)}),
                       ("POST", f"{C}/questions/{q_shared.id}/translations",
                        {"language": "ru", "bank_id": str(w.PB.id)})):
        r = await api.call(admin, m, p, json=body)
        assert r.status_code == 403, (m, p, r.status_code, r.text)
    # outsiders and students: unchanged refusals
    for user, code in ((w.admins["X"], 404), (w.admins["D2"], 404), (w.indep, 404), (w.stud, 403)):
        r = await api.call(user, "PATCH", f"{C}/banks/{w.B.id}", json={"title": "nope"})
        assert r.status_code == code, (user.id, r.status_code)
    # an unknown question id falls through to the usual refusal (the org admin reads the course: 403)
    r = await api.call(admin, "DELETE", f"{C}/questions/{w.B.id}")
    assert r.status_code == 403
    # BankOut: sharing state and the edit right of the caller
    r = await api.call(w.T, "GET", f"{C}/banks/{w.B.id}")
    body = r.json()
    assert (body["visibility"], body["can_edit"], body["copied_from_bank_id"]) == ("organization", True, None)
    assert body["shared_at"] is not None
    listed = {b["id"]: b for b in (await api.call(w.asst, "GET", f"{C}/banks")).json()["items"]}
    assert listed[str(w.PB.id)]["visibility"] == "private" and listed[str(w.PB.id)]["can_edit"] is True


@pytest.mark.parametrize("field", ["visibility"])
def test_existing_banks_default_private(db, field):
    w = world(db)
    assert getattr(make_bank(db, w.C, w.T), field) == "private"
