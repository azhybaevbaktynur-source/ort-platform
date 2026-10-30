"""Phase 9 S4: catalog search, filters, cards and the course landing (PHASE_9_DESIGN 4.6)."""
from tests.lms.application_support import (  # noqa: F401
    SECRET_NAME, _purge_throttle_and_mail, api, apply, catalog_course, clean_rate_limits, db, enroll, form_course,
    make_user, teacher,
)
from tests.lms.org_support import make_department, make_org


async def _ids(api, user, **params):
    r = await api.call(user, "GET", "/catalog/courses", params=params)
    assert r.status_code == 200, r.text
    return [i["id"] for i in r.json()["items"]], r.json()


async def test_search_in_three_languages(db, api):
    t, s = teacher(db), make_user(db)
    a = catalog_course(db, t, title={"en": "Algebra basics", "ru": "Основы алгебры", "ky": "Алгебранын негиздери"},
                       languages=["en", "ru", "ky"])
    b = catalog_course(db, t, title={"en": "Chemistry"}, description={"en": "Atoms and molecules"})
    for q, want in (("algebra", a), ("АЛГЕБРЫ", a), ("негиздери", a), ("molecul", b)):
        ids, _ = await _ids(api, s, q=q)
        assert ids == [str(want.id)], q
    assert (await _ids(api, s, q="100%_"))[0] == []  # LIKE wildcards are escaped


async def test_filters_language_mode_organization(db, api):
    t, s = teacher(db), make_user(db)
    school = make_org(db, "Lyceum 61")
    maths = make_department(db, school, "Maths")
    other = make_org(db, "Other school")
    ky = catalog_course(db, t, languages=["ky"], default_language="ky", title={"ky": "Курс"}, organization_id=maths.id)
    en_open = catalog_course(db, t, mode="open", organization_id=other.id)
    ids, body = await _ids(api, s, language="ky")
    assert str(ky.id) in ids and str(en_open.id) not in ids
    ids, _ = await _ids(api, s, mode="open")
    assert str(en_open.id) in ids and str(ky.id) not in ids
    ids, body = await _ids(api, s, organization_id=str(school.id))
    assert ids == [str(ky.id)]
    card = body["items"][0]
    assert card["organization_id"] == str(school.id) and card["organization_name"] == "Lyceum 61"
    assert card["has_active_form"] is False and card["my_application"] is None


async def test_suspended_root_hides_department_courses(db, api):
    t, s = teacher(db), make_user(db)
    school = make_org(db)
    dept = make_department(db, school)
    c = catalog_course(db, t, organization_id=dept.id)
    assert str(c.id) in (await _ids(api, s))[0]
    school.status = "suspended"
    db.commit()
    assert str(c.id) not in (await _ids(api, s))[0]
    assert (await api.call(s, "GET", f"/catalog/courses/{c.id}")).status_code == 404


async def test_card_shows_form_and_my_application(db, api):
    c, form, t = await form_course(db, api)
    s = make_user(db)
    _, body = await _ids(api, s)
    card = next(i for i in body["items"] if i["id"] == str(c.id))
    assert card["has_active_form"] is True and card["enrollment_mode"] == "form_review"
    app_id = (await apply(api, s, c, form)).json()["id"]
    _, body = await _ids(api, s)
    card = next(i for i in body["items"] if i["id"] == str(c.id))
    assert card["my_application"] == {"id": app_id, "status": "pending"}
    assert SECRET_NAME not in str(body)


async def test_landing(db, api):
    c, form, t = await form_course(db, api, description={"en": "About"}, enrollment_limit=30)
    s = make_user(db)
    r = await api.call(s, "GET", f"/catalog/courses/{c.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["form"]["id"] == form["id"] and [f["key"] for f in body["form"]["fields"]][0] == "full_name"
    assert body["teachers"] and t.email not in r.text and c.join_code not in r.text
    assert "enrollment_limit" not in body and body["my_enrollment"] is None
    # private, unlisted and draft courses are 404
    for field, value in (("visibility", "private"), ("unlisted_by_admin_at", __import__("datetime").datetime.now()),
                         ("status", "draft")):
        other = catalog_course(db, t, **{field: value})
        assert (await api.call(s, "GET", f"/catalog/courses/{other.id}")).status_code == 404
    # no form block outside form modes
    plain = catalog_course(db, t, mode="open")
    assert (await api.call(s, "GET", f"/catalog/courses/{plain.id}")).json()["form"] is None


async def test_home_pending_line(db, api):
    c, form, t = await form_course(db, api)
    s = make_user(db)
    app_id = (await apply(api, s, c, form)).json()["id"]
    home = (await api.call(s, "GET", "/me/home")).json()
    assert [p["application_id"] for p in home["pending_applications"]] == [app_id]
    assert SECRET_NAME not in str(home)
    await api.call(s, "POST", f"/courses/{c.id}/applications/{app_id}/withdraw")
    assert (await api.call(s, "GET", "/me/home")).json()["pending_applications"] == []
