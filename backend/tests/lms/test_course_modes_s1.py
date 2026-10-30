"""Phase 9 S1: widened `CreateMode`, the form-mode rules of `update_course` and `courses.catalog_search`
(PHASE_9_DESIGN 2.6, 4.6, invariant 9)."""
import uuid

from app.lms.courses.models import Course, catalog_search_text
from app.lms.enrollment_forms.models import EnrollmentForm
from tests.lms.s3_support import api, clean_rate_limits, db, make_course, teacher  # noqa: F401

BODY = {"title": {"en": "Algebra", "ru": "Алгебра"}, "languages": ["en", "ru"], "default_language": "en"}


def _code(r):
    return r.json()["error"]["code"]


async def test_form_mode_rules(db, api):
    t = teacher(db)
    cid = (await api.call(t, "POST", "/courses", json=BODY)).json()["id"]
    url = f"/courses/{cid}"
    r = await api.call(t, "PATCH", url, json={"enrollment_mode": "form_review"})
    assert r.status_code == 422 and _code(r) == "form_needs_catalog"
    r = await api.call(t, "PATCH", url, json={"enrollment_mode": "form_auto", "visibility": "catalog"})
    assert r.status_code == 422 and _code(r) == "form_required"
    for mode in ("open", "closed", "invite_code"):
        r = await api.call(t, "PATCH", url, json={"enrollment_mode": mode})
        assert r.status_code == 200 and r.json()["enrollment_mode"] == mode
    db.add(EnrollmentForm(course_id=uuid.UUID(cid), version=1, status="active"))
    db.commit()
    r = await api.call(t, "PATCH", url, json={"enrollment_mode": "form_review", "visibility": "catalog"})
    assert r.status_code == 200 and r.json()["enrollment_mode"] == "form_review"
    r = await api.call(t, "PATCH", url, json={"visibility": "private"})  # no dead end: a form course stays listed
    assert r.status_code == 422 and _code(r) == "form_needs_catalog"
    r = await api.call(t, "PATCH", url, json={"enrollment_mode": "invite_code", "visibility": "private"})
    assert r.status_code == 200


async def test_ort_course_refuses_form_modes(db, api):
    t = teacher(db)
    ort = make_course(db, t, template_key="ort", template_version=1, template_locked=True, visibility="catalog",
                      enrollment_mode="open")
    db.add(EnrollmentForm(course_id=ort.id, version=1, status="active"))
    db.commit()
    for mode in ("form_review", "form_auto"):
        r = await api.call(t, "PATCH", f"/courses/{ort.id}", json={"enrollment_mode": mode})
        assert r.status_code == 422 and _code(r) == "template_locked"
    r = await api.call(t, "PATCH", f"/courses/{ort.id}", json={"enrollment_mode": "invite_code"})
    assert r.status_code == 200


async def test_catalog_search_follows_title_and_description(db, api):
    t = teacher(db)
    cid = (await api.call(t, "POST", "/courses", json={**BODY, "description": {"en": "  Linear EQUATIONS "}})).json()["id"]
    db.expire_all()
    c = db.get(Course, uuid.UUID(cid))
    assert c.catalog_search == "algebra алгебра linear equations"
    r = await api.call(t, "PATCH", f"/courses/{cid}", json={"title": {"en": "Geometry", "ru": "Геометрия"}})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Course, c.id).catalog_search == "geometry геометрия linear equations"
    assert catalog_search_text({"ky": "Алгебра", "en": "  "}, None) == "алгебра"
    assert catalog_search_text(None, None) == ""
