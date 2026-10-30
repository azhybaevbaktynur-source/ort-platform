"""Phase 9 S4: enrollment form builder (PHASE_9_DESIGN 2.4, 4.6, 5, 5.1)."""
from app.core.route_inventory import ROUTE_POLICIES
from tests.lms.application_support import (  # noqa: F401
    FIELDS, _purge_throttle_and_mail, api, apply, catalog_course, clean_rate_limits, db, enroll, form_course,
    make_course, make_form, make_user, teacher,
)
from tests.lms.org_support import add_member, make_org

_C = "/api/v1/courses/{course_id}"


def test_policies_registered():
    assert ROUTE_POLICIES[("POST", f"{_C}/enrollment-forms")] == "course:course.update"
    assert ROUTE_POLICIES[("GET", f"{_C}/enrollment-forms")] == "course:course.read+staff"
    assert ROUTE_POLICIES[("POST", f"{_C}/applications")] == "authenticated+ratelimit"
    assert ROUTE_POLICIES[("POST", f"{_C}/applications/{{application_id}}/approve")] == "course:roster.manage"
    assert ROUTE_POLICIES[("POST", "/api/v1/internal/purge-applications")] == "internal_token"
    assert ROUTE_POLICIES[("GET", "/api/v1/catalog/courses/{course_id}")] == "authenticated"


async def test_create_draft_and_read_back(db, api):
    t = teacher(db)
    c = catalog_course(db, t)
    form = await make_form(api, t, c, activate=False)
    assert form["status"] == "draft" and form["version"] == 1 and not form["answered"]
    assert [f["key"] for f in form["fields"]] == [f["key"] for f in FIELDS]
    grade = form["fields"][2]
    assert grade["options"][0]["key"] == "g10" and grade["bounds"] is None
    r = await api.call(t, "GET", f"/courses/{c.id}/enrollment-forms")
    assert r.status_code == 200 and r.json()[0]["field_count"] == 4
    # one draft per course
    r = await api.call(t, "POST", f"/courses/{c.id}/enrollment-forms", json={"fields": []})
    assert r.status_code == 409 and r.json()["error"]["code"] == "form_draft_exists"


async def test_builder_validation(db, api):
    t = teacher(db)
    c = catalog_course(db, t)

    async def bad(fields):
        r = await api.call(t, "POST", f"/courses/{c.id}/enrollment-forms", json={"fields": fields})
        assert r.status_code == 422, r.text
        return {d.get("msg") for d in r.json()["error"]["details"] or []}

    base = {"key": "a", "type": "short_text", "label": {"en": "A"}, "pii_category": "none"}
    assert "duplicate_key" in await bad([base, base])
    assert "options_required" in await bad([dict(base, type="single_choice")])
    assert "options_not_allowed" in await bad([dict(base, options=[{"key": "x", "label": {"en": "X"}}])])
    assert "label_default_language" in await bad([dict(base, label={"ru": "А"})])
    assert "max_len_too_large" in await bad([dict(base, max_len=900)])
    assert "max_len_not_allowed" in await bad([dict(base, type="date", max_len=10)])
    assert "bounds_invalid" in await bad([dict(base, type="number", bounds={"min": 5, "max": 1})])
    assert "duplicate_option" in await bad([dict(base, type="multi_choice", options=[
        {"key": "x", "label": {"en": "X"}}, {"key": "x", "label": {"en": "Y"}}])])
    # 26 fields: refused before anything is written
    many = [dict(base, key=f"f{i}") for i in range(26)]
    r = await api.call(t, "POST", f"/courses/{c.id}/enrollment-forms", json={"fields": many})
    assert r.status_code == 422
    # pii_category is required per field (Phase 11 registry)
    r = await api.call(t, "POST", f"/courses/{c.id}/enrollment-forms",
                       json={"fields": [{k: v for k, v in base.items() if k != "pii_category"}]})
    assert r.status_code == 422


async def test_number_bounds_round_trip(db, api):
    t = teacher(db)
    c = catalog_course(db, t)
    f = await make_form(api, t, c, [{"key": "age", "type": "number", "label": {"en": "Age"}, "pii_category": "personal",
                                     "bounds": {"min": 5, "max": 25}}], activate=False)
    assert f["fields"][0]["bounds"] == {"min": 5, "max": 25} and f["fields"][0]["options"] is None


async def test_activation_retires_the_previous_form(db, api):
    t = teacher(db)
    c = catalog_course(db, t)
    first = await make_form(api, t, c)
    assert first["status"] == "active"
    r = await api.call(t, "POST", f"/courses/{c.id}/enrollment-forms/{first['id']}/new-version")
    assert r.status_code == 201
    second = r.json()
    assert second["version"] == 2 and second["status"] == "draft" and len(second["fields"]) == 4
    r = await api.call(t, "POST", f"/courses/{c.id}/enrollment-forms/{second['id']}/activate")
    assert r.status_code == 200 and r.json()["status"] == "active"
    versions = (await api.call(t, "GET", f"/courses/{c.id}/enrollment-forms")).json()
    assert [(v["version"], v["status"]) for v in versions] == [(2, "active"), (1, "retired")]
    # a retired form is read-only; only drafts are deleted
    r = await api.call(t, "PATCH", f"/courses/{c.id}/enrollment-forms/{first['id']}", json={"intro": {"en": "x"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "form_retired"
    r = await api.call(t, "DELETE", f"/courses/{c.id}/enrollment-forms/{second['id']}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "form_not_draft"


async def test_answered_form_is_immutable(db, api):
    c, form, t = await form_course(db, api)
    r = await apply(api, make_user(db), c, form)
    assert r.status_code == 201, r.text
    r = await api.call(t, "GET", f"/courses/{c.id}/enrollment-forms/{form['id']}")
    assert r.json()["answered"] is True
    r = await api.call(t, "PATCH", f"/courses/{c.id}/enrollment-forms/{form['id']}", json={"fields": FIELDS[:1]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "form_answered"
    # "Edit" = a new version copying the fields
    r = await api.call(t, "POST", f"/courses/{c.id}/enrollment-forms/{form['id']}/new-version")
    assert r.status_code == 201 and r.json()["answered"] is False


async def test_patch_draft_replaces_fields_and_delete(db, api):
    t = teacher(db)
    c = catalog_course(db, t)
    f = await make_form(api, t, c, activate=False)
    r = await api.call(t, "PATCH", f"/courses/{c.id}/enrollment-forms/{f['id']}",
                       json={"fields": FIELDS[:2], "intro": {"en": "Hello"}})
    assert r.status_code == 200 and len(r.json()["fields"]) == 2 and r.json()["intro"] == {"en": "Hello"}
    r = await api.call(t, "DELETE", f"/courses/{c.id}/enrollment-forms/{f['id']}")
    assert r.status_code == 204
    assert (await api.call(t, "GET", f"/courses/{c.id}/enrollment-forms")).json() == []


async def test_authorization_matrix(db, api):
    org = make_org(db)
    t = teacher(db)
    c = catalog_course(db, t, organization_id=org.id)
    form = await make_form(api, t, c, activate=False)
    assistant, student, outsider, org_admin = make_user(db), make_user(db), make_user(db), make_user(db)
    enroll(db, c, assistant, role="assistant")
    enroll(db, c, student)
    add_member(db, org, org_admin, role="org_admin")
    path = f"/courses/{c.id}/enrollment-forms/{form['id']}"
    for who in (assistant, org_admin):
        assert (await api.call(who, "GET", path)).status_code == 200
        r = await api.call(who, "PATCH", path, json={"intro": {"en": "x"}})
        assert r.status_code in (403, 404), r.text
    assert (await api.call(student, "GET", path)).status_code == 403
    assert (await api.call(outsider, "GET", path)).status_code == 404
    assert (await api.call(outsider, "POST", f"/courses/{c.id}/enrollment-forms", json={})).status_code == 404


async def test_mode_rules(db, api):
    t = teacher(db)
    c = catalog_course(db, t)
    r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"enrollment_mode": "form_review"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "form_required"
    await make_form(api, t, c)
    r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"enrollment_mode": "form_review"})
    assert r.status_code == 200
    r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"visibility": "private"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "form_needs_catalog"


async def test_ort_course_refuses_forms(db, api):
    t = teacher(db)
    c = catalog_course(db, t, template_key="ort", template_version=1)
    r = await api.call(t, "POST", f"/courses/{c.id}/enrollment-forms", json={"fields": FIELDS})
    assert r.status_code == 422 and r.json()["error"]["code"] == "template_locked"
    r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"enrollment_mode": "form_review"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "template_locked"
