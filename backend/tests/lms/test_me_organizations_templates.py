"""FB8-5 S3 (STAFF_UX_AUDIT 4): GET /me/organizations rows carry `template_keys`, the templates granted to the
organization (active grants the registry knows), only where the caller may create courses."""
from __future__ import annotations

import uuid

from app.lms.core.models import utcnow
from app.lms.organizations.ids import personal_org_id
from app.lms.organizations.models import Organization, OrganizationMember, OrganizationTemplateGrant
from tests.lms.factories import make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _org(db, *, teachers_can_create=True, name="School"):
    org = Organization(slug=f"org-{uuid.uuid4().hex[:10]}", name=name, status="active",
                       settings={"teachers_can_create_courses": teachers_can_create})
    db.add(org)
    db.commit()
    return org


def _member(db, org, user, role):
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=role, state="active"))
    db.commit()


async def _rows(api, user):
    res = await api.call(user, "GET", "/me/organizations", params={"limit": 100})
    assert res.status_code == 200, res.text
    return {r["id"]: r for r in res.json()["items"]}


async def test_granted_key_listed_ungranted_not(db, api):
    admin = make_user(db, platform_admin=True)
    granted, plain = _org(db, name="Granted"), _org(db, name="Plain")
    t = make_user(db, teacher_status="approved")
    _member(db, granted, t, "teacher")
    _member(db, plain, t, "teacher")
    db.add(OrganizationTemplateGrant(organization_id=granted.id, template_key="ort", granted_by_id=admin.id))
    db.add(OrganizationTemplateGrant(organization_id=granted.id, template_key="retired_kind", granted_by_id=admin.id))
    db.commit()
    rows = await _rows(api, t)
    assert rows[str(granted.id)]["template_keys"] == ["ort"]  # keys the registry does not know are left out
    assert rows[str(plain.id)]["template_keys"] == []
    # the personal organization of an approved teacher has no grant
    personal = rows[str(personal_org_id(t.id))]
    assert personal["kind"] == "personal" and personal["template_keys"] == []


async def test_revoked_grant_and_non_creator_rows_are_empty(db, api):
    admin = make_user(db, platform_admin=True)
    org = _org(db, teachers_can_create=False)
    oa, t = make_user(db), make_user(db, teacher_status="approved")
    _member(db, org, oa, "org_admin")
    _member(db, org, t, "teacher")
    grant = OrganizationTemplateGrant(organization_id=org.id, template_key="ort", granted_by_id=admin.id)
    db.add(grant)
    db.commit()
    assert (await _rows(api, oa))[str(org.id)]["template_keys"] == ["ort"]
    row = (await _rows(api, t))[str(org.id)]  # a teacher who may not create courses here sees no templates
    assert row["can_create_courses"] is False and row["template_keys"] == []
    grant.revoked_at, grant.revoked_by_id = utcnow(), admin.id
    db.commit()
    assert (await _rows(api, oa))[str(org.id)]["template_keys"] == []
