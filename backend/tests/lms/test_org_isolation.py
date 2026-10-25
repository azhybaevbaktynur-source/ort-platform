"""Phase 6 isolation suite (PHASE_6_DESIGN 4 and 9 gates): org admin A sees nothing of org B; two personal
organizations see nothing of each other's courses and banks; a teacher sees only their own organization's courses;
students are unaffected."""
import uuid

from sqlalchemy import select

from app.lms.content.models import QuestionBank
from app.lms.organizations.ids import personal_org_id
from tests.lms.factories import make_bank
from tests.lms.org_support import add_member, grant, make_org
from tests.lms.s3_support import api, auth, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

BODY = {"title": {"en": "Mine"}, "languages": ["en"], "default_language": "en"}


async def test_org_admin_a_sees_nothing_of_org_b(db, api):
    a, b = make_org(db, "A"), make_org(db, "B")
    grant(db, b)
    oa_a, oa_b, tb = make_user(db), make_user(db), make_user(db)
    add_member(db, a, oa_a, "org_admin")
    add_member(db, b, oa_b, "org_admin")
    add_member(db, b, tb, "teacher")
    cb = make_course(db, tb, organization_id=b.id, status="published")
    bank = make_bank(db, cb, tb)
    for m, p in [("GET", f"/org/{b.id}"), ("GET", f"/org/{b.id}/members"), ("GET", f"/org/{b.id}/courses"),
                 ("POST", f"/org/{b.id}/courses/{cb.id}/join-as-teacher"),
                 ("DELETE", f"/org/{b.id}/members/{tb.id}"),
                 ("GET", f"/courses/{cb.id}"), ("GET", f"/courses/{cb.id}/people"),
                 ("GET", f"/courses/{cb.id}/banks/{bank.id}")]:
        r = await api.call(oa_a, m, p)
        assert r.status_code == 404, (m, p, r.status_code)
    r = await api.call(oa_a, "POST", f"/org/{b.id}/courses", json=BODY)
    assert r.status_code == 404
    r = await api.call(oa_a, "POST", "/courses", json={**BODY, "organization_id": str(b.id)})
    assert r.status_code == 404
    # org admin A's own join-as-teacher cannot reach B's course through A's route
    r = await api.call(oa_a, "POST", f"/org/{a.id}/courses/{cb.id}/join-as-teacher")
    assert r.status_code == 404
    # B's template grant is not usable from A
    r = await api.call(oa_a, "POST", "/courses", json={**BODY, "organization_id": str(a.id), "template_key": "ort"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "template_not_granted"
    mine = (await api.call(oa_a, "GET", "/me/organizations")).json()["items"]
    assert [o["id"] for o in mine] == [str(a.id)]


async def test_two_personal_orgs_isolated(db, api):
    t1, t2 = teacher(db), teacher(db)
    c1 = (await api.call(t1, "POST", "/courses", json=BODY)).json()
    c2 = (await api.call(t2, "POST", "/courses", json=BODY)).json()
    assert c1["organization_id"] == str(personal_org_id(t1.id))
    assert c2["organization_id"] == str(personal_org_id(t2.id)) != c1["organization_id"]
    b1 = (await api.call(t1, "POST", f"/courses/{c1['id']}/banks", json={"title": "B1"}))
    assert b1.status_code == 201, b1.text
    db.expire_all()
    bank1 = db.get(QuestionBank, uuid.UUID(b1.json()["id"]))
    assert bank1.organization_id == personal_org_id(t1.id)
    loose = make_bank(db, None, t2)
    assert loose.organization_id == personal_org_id(t2.id)
    for m, p in [("GET", f"/courses/{c1['id']}"), ("GET", f"/courses/{c1['id']}/banks"),
                 ("GET", f"/courses/{c1['id']}/banks/{bank1.id}"), ("GET", f"/org/{personal_org_id(t1.id)}"),
                 ("GET", f"/org/{personal_org_id(t1.id)}/courses")]:
        assert (await api.call(t2, m, p)).status_code == 404, (m, p)
    r = await api.call(t2, "POST", "/courses", json={**BODY, "organization_id": str(personal_org_id(t1.id))})
    assert r.status_code == 404
    # no bank of one personal organization carries the other's id
    rows = db.execute(select(QuestionBank.owner_id, QuestionBank.organization_id)).all()
    assert all(org == personal_org_id(owner) for owner, org in rows)


async def test_teacher_sees_only_own_org_courses_students_unaffected(db, api):
    a, b = make_org(db, "A"), make_org(db, "B")
    ta, tb, s = make_user(db), make_user(db), make_user(db)
    add_member(db, a, ta, "teacher")
    add_member(db, b, tb, "teacher")
    ca = make_course(db, ta, organization_id=a.id, status="published")
    cb = make_course(db, tb, organization_id=b.id, status="published")
    enroll(db, ca, s)
    enroll(db, cb, s)
    teaching = (await api.call(ta, "GET", "/courses", params={"as": "teaching"})).json()["items"]
    assert [c["id"] for c in teaching] == [str(ca.id)]
    org_courses = (await api.call(ta, "GET", f"/org/{a.id}/courses")).status_code
    assert org_courses == 404  # plain teachers have no org admin area
    learning = (await api.call(s, "GET", "/courses", params={"as": "learning"})).json()["items"]
    assert {c["id"] for c in learning} == {str(ca.id), str(cb.id)}
    for c in (ca, cb):
        r = await api.call(s, "GET", f"/courses/{c.id}")
        assert r.status_code == 200 and r.json()["my_enrollment"]["role"] == "student"
        assert "join_code" not in r.json()
    assert (await api.call(s, "GET", "/me/organizations")).json()["items"] == []
