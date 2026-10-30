"""Phase 9 S1: the organization tree in authorization (PHASE_9_DESIGN 2.1, 4.1, invariant 4, P9-1).

Tree used below:  school R ── department D ── sub-department S
                           └─ department D2
                  school X (another tree); personal organizations P1, P2 (independent teachers).

An org admin of a node administers that node and every descendant, never an ancestor or a sibling; personal
organizations stay isolated; suspension and deletion apply through the root."""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.authz import A, AuthzContext, can, enrollment_role_resolver
from app.lms.core.models import utcnow
from app.lms.organizations import tree
from app.lms.organizations.ids import personal_org_id, platform_org_id
from app.lms.organizations.models import Organization
from app.lms.organizations.service import organizations_administered_by
from app.lms.organizations.settings import effective_settings, settings_of, validate_settings_write
from app.lms.organizations.schemas import OrganizationSettingsIn, organization_out
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


def ctx_for(db, user) -> AuthzContext:
    return AuthzContext(user, db, enrollment_role_resolver(db, user.id))


class W:
    pass


def world(db) -> W:
    w = W()
    w.R, w.X = make_org(db, "R"), make_org(db, "X")
    w.D = make_department(db, w.R, "D")
    w.S = make_department(db, w.D, "S")
    w.D2 = make_department(db, w.R, "D2")
    w.admin_R, w.admin_D, w.admin_S, w.admin_D2, w.admin_X = (make_user(db) for _ in range(5))
    for org, user in ((w.R, w.admin_R), (w.D, w.admin_D), (w.S, w.admin_S), (w.D2, w.admin_D2), (w.X, w.admin_X)):
        add_member(db, org, user, "org_admin")
    w.i1, w.i2 = teacher(db), teacher(db)  # approved independents: personal organizations (kind personal)
    w.P1, w.P2 = db.get(Organization, personal_org_id(w.i1.id)), db.get(Organization, personal_org_id(w.i2.id))
    return w


# ------------------------------------------------------------------ pure helpers

def test_path_helpers():
    r, d, s = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    p = tree.child_path(tree.child_path(r.hex, d), s)
    assert p == f"{r.hex}/{d.hex}/{s.hex}"
    assert tree.ancestor_ids(p) == [r, d, s] and tree.root_id(p) == r and tree.depth_of(p) == 2
    assert tree.is_within(p, r.hex) and tree.is_within(p, p) and not tree.is_within(r.hex, p)
    other = uuid.uuid4()
    assert tree.rebase(p, f"{r.hex}/{d.hex}", f"{other.hex}/{d.hex}") == f"{other.hex}/{d.hex}/{s.hex}"
    with pytest.raises(ValueError):
        tree.rebase(other.hex, r.hex, d.hex)
    assert tree.fits_depth(1, 1) and not tree.fits_depth(2, 1)


def test_kinds_paths_and_checks(db):
    w = world(db)
    assert (w.R.kind, w.R.depth, w.R.path) == ("school", 0, w.R.id.hex)
    assert (w.D.kind, w.D.depth, w.D.path) == ("department", 1, f"{w.R.id.hex}/{w.D.id.hex}")
    assert (w.S.depth, tree.ancestor_ids(w.S.path)) == (2, [w.R.id, w.D.id, w.S.id])
    assert w.P1.kind == "personal" and w.P1.path == w.P1.id.hex and w.P1.depth == 0
    assert db.get(Organization, platform_org_id()) is None or db.get(Organization, platform_org_id()).kind == "platform"
    out = organization_out(w.D)
    assert (out.kind, out.depth, out.path, out.parent_id) == ("department", 1, w.D.path, w.R.id)
    bad = [
        dict(kind="department", parent_id=None, depth=0),            # a department needs a parent
        dict(kind="school", parent_id=w.R.id, depth=1),              # a root kind cannot have a parent
        dict(kind="personal", parent_id=w.R.id, depth=1),            # personal is always a root
        dict(kind="department", parent_id=w.S.id, depth=3),          # depth <= 2
        dict(kind="department", parent_id=w.R.id, depth=0),          # depth matches the parent
        dict(kind="club", parent_id=None, depth=0),                  # kind CHECK
    ]
    for fields in bad:
        db.add(Organization(slug=f"b-{uuid.uuid4().hex[:10]}", name="bad", status="active", settings={}, **fields))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


# ------------------------------------------------------------------ authz: org_admin_for / organizations_administered_by

def test_parent_admin_has_scope_over_departments(db):
    w = world(db)
    c = ctx_for(db, w.admin_R)
    assert all(c.org_admin_for(o.id) for o in (w.R, w.D, w.S, w.D2))
    assert not c.org_admin_for(w.X.id) and not c.org_admin_for(w.P1.id)
    assert set(organizations_administered_by(db, w.admin_R.id)) == {w.R.id, w.D.id, w.S.id, w.D2.id}


def test_department_admin_has_no_scope_over_parent_or_siblings(db):
    w = world(db)
    c = ctx_for(db, w.admin_D)
    assert c.org_admin_for(w.D.id) and c.org_admin_for(w.S.id)
    assert not c.org_admin_for(w.R.id) and not c.org_admin_for(w.D2.id) and not c.org_admin_for(w.X.id)
    assert set(organizations_administered_by(db, w.admin_D.id)) == {w.D.id, w.S.id}
    cs = ctx_for(db, w.admin_S)
    assert cs.org_admin_for(w.S.id) and not any(cs.org_admin_for(o.id) for o in (w.R, w.D, w.D2))
    assert organizations_administered_by(db, w.admin_S.id) == [w.S.id]
    assert set(organizations_administered_by(db, w.admin_D2.id)) == {w.D2.id}


def test_personal_organizations_are_isolated(db):
    w = world(db)
    c1 = ctx_for(db, w.i1)
    assert c1.org_admin_for(w.P1.id)
    assert not any(c1.org_admin_for(o.id) for o in (w.P2, w.R, w.D, w.X))
    assert organizations_administered_by(db, w.i1.id) == [w.P1.id]
    assert not ctx_for(db, w.admin_R).org_admin_for(w.P1.id)
    assert tree.member_tree_roots(db, w.i1.id) == [w.P1.id]


def test_removed_membership_and_deleted_ancestor_grant_nothing(db):
    w = world(db)
    from app.lms.organizations.models import OrganizationMember
    from sqlalchemy import select

    m = db.execute(select(OrganizationMember).where(OrganizationMember.user_id == w.admin_R.id)).scalar_one()
    m.state = "removed"
    db.commit()
    assert not ctx_for(db, w.admin_R).org_admin_for(w.D.id)
    assert organizations_administered_by(db, w.admin_R.id) == []
    m.state = "active"
    w.R.deleted_at = utcnow()
    db.commit()
    c = ctx_for(db, w.admin_R)
    assert not c.org_admin_for(w.R.id) and not c.org_admin_for(w.D.id)
    # a deleted root takes its departments with it, also for their own admins
    assert not ctx_for(db, w.admin_D).org_admin_for(w.D.id)
    assert organizations_administered_by(db, w.admin_R.id) == []


def test_suspension_applies_through_the_root(db):
    w = world(db)
    owner, student = make_user(db), make_user(db)
    add_member(db, w.D, owner, "teacher")
    course = make_course(db, owner, organization_id=w.D.id, status="published")
    enroll(db, course, student)
    assert can(ctx_for(db, owner), A.CONTENT_MANAGE, course)
    assert can(ctx_for(db, student), A.ASSESSMENT_TAKE, course)
    w.R.status, w.R.suspended_at = "suspended", utcnow()
    db.commit()
    assert w.D.status == "active"  # the department row itself is untouched
    for user, action in ((owner, A.CONTENT_MANAGE), (student, A.ASSESSMENT_TAKE)):
        c = ctx_for(db, user)
        assert c.org_suspended(w.D.id, course.id)
        assert not can(c, action, course)
        assert can(c, A.COURSE_READ, course)  # read-only, like a suspended root


def test_tree_scopes(db):
    w = world(db)
    from sqlalchemy import select

    sub = set(db.execute(tree.subtree_scope(w.D.path)).scalars())
    assert sub == {w.D.id, w.S.id}
    both = set(db.execute(tree.trees_scope([w.R.id, w.P1.id])).scalars())
    assert both == {w.R.id, w.D.id, w.S.id, w.D2.id, w.P1.id}
    assert set(db.execute(select(Organization.id).where(Organization.id.in_(tree.administered_scope(
        w.admin_D.id)))).scalars()) == {w.D.id, w.S.id}
    assert tree.is_org_admin_in_tree(db, w.admin_R.id, w.S) and not tree.is_org_admin_in_tree(db, w.admin_D2.id, w.S)
    t = make_user(db)
    add_member(db, w.S, t, "teacher")
    assert tree.member_tree_roots(db, t.id) == [w.R.id]
    assert tree.load_root(db, w.S).id == w.R.id and tree.load_root(db, w.R) is w.R


async def test_course_reach_through_the_tree(db, api):
    """Org-admin course actions (A13: read, roster) reach a department's course from the root and the department
    itself, not from a sibling, a sub-department or another school."""
    w = world(db)
    owner = make_user(db)
    add_member(db, w.D, owner, "teacher")
    course = make_course(db, owner, organization_id=w.D.id, status="published")
    for user, code in ((w.admin_R, 200), (w.admin_D, 200), (w.admin_S, 404), (w.admin_D2, 404), (w.admin_X, 404),
                       (w.i1, 404)):
        r = await api.call(user, "GET", f"/courses/{course.id}")
        assert r.status_code == code, (user.id, r.status_code)
        r = await api.call(user, "GET", f"/courses/{course.id}/people")
        assert r.status_code == code, (user.id, r.status_code)


# ------------------------------------------------------------------ settings (root only)

def test_settings_live_on_the_root(db):
    w = world(db)
    from app.lms.core.errors import Conflict, ValidationFailed

    eff = effective_settings({})
    assert (eff.bank_sharing_enabled, eff.application_retention_days, eff.student_invitations_enabled,
            eff.catalog_defaults.visibility, eff.catalog_defaults.enrollment_mode) == (
        False, 30, True, "private", "invite_code")
    w.R.settings = validate_settings_write(w.R, OrganizationSettingsIn(bank_sharing_enabled=True,
                                                                         application_retention_days=60))
    db.commit()
    assert settings_of(db, w.S).bank_sharing_enabled and settings_of(db, w.D).application_retention_days == 60
    with pytest.raises(Conflict) as e:
        validate_settings_write(w.D, OrganizationSettingsIn(bank_sharing_enabled=False))
    assert e.value.code == "settings_on_root"
    with pytest.raises(ValidationFailed) as e:
        validate_settings_write(w.P1, OrganizationSettingsIn(bank_sharing_enabled=True))
    assert e.value.code == "sharing_disabled"
    assert not effective_settings({"bank_sharing_enabled": True}, "personal").bank_sharing_enabled
    with pytest.raises(ValueError):
        OrganizationSettingsIn(application_retention_days=10)
    with pytest.raises(ValueError):
        OrganizationSettingsIn.model_validate({"unknown": 1})
    # one invalid stored value does not reset the others
    eff = effective_settings({"application_retention_days": 7, "bank_sharing_enabled": True})
    assert eff.application_retention_days == 30 and eff.bank_sharing_enabled
