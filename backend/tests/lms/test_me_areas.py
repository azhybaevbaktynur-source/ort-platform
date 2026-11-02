"""UX rework 2: one answer (`GET /me/lms`) carries what the header's menu needs, and one answer the admin overview's cards."""
from app.lms.core.models import utcnow
from app.lms.guardian.models import GuardianLink
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, make_user  # noqa: F401


async def test_me_lists_only_the_organizations_the_person_administers(db, api):
    u = make_user(db)
    runs, teaches, gone, left = make_org(db, "Runs"), make_org(db, "Teaches"), make_org(db, "Gone"), make_org(db, "Left")
    add_member(db, runs, u, "org_admin")
    add_member(db, teaches, u, "teacher")
    add_member(db, gone, u, "org_admin")
    member = add_member(db, left, u, "org_admin")
    member.state = "removed"
    gone.deleted_at = utcnow()
    db.commit()
    me = (await api.call(u, "GET", "/me/lms")).json()
    assert me["admin_organizations"] == [{"id": str(runs.id), "name": "Runs"}]


async def test_me_says_whether_the_person_is_a_parent(db, api):
    parent, child, former = make_user(db), make_user(db), make_user(db)
    assert (await api.call(parent, "GET", "/me/lms")).json()["is_guardian"] is False
    db.add_all([GuardianLink(guardian_user_id=parent.id, student_user_id=child.id),
                GuardianLink(guardian_user_id=former.id, student_user_id=child.id, revoked_at=utcnow())])
    db.commit()
    assert (await api.call(parent, "GET", "/me/lms")).json()["is_guardian"] is True
    assert (await api.call(former, "GET", "/me/lms")).json()["is_guardian"] is False  # a revoked link is not a parent


async def test_a_student_has_no_extra_areas(db, api):
    me = (await api.call(make_user(db), "GET", "/me/lms")).json()
    assert me["admin_organizations"] == [] and me["is_guardian"] is False
