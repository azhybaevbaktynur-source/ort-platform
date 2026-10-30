"""Phase 9 S4b: the exact payloads the frontend sends (FormBuilder, Settings → Enrollment, ApplyPage, ApplicationPanel)
and the response fields it reads. Guards the API shape the screens depend on."""
from tests.lms.application_support import (  # noqa: F401
    _purge_throttle_and_mail, api, catalog_course, clean_rate_limits, db, make_user, sent_mails, teacher,
)

BUILDER_FIELDS = [  # FormBuilder.payload(): every key present, nulls where the type does not use them
    {"key": "full_name", "type": "short_text", "label": {"en": "Full name"}, "help": None, "options": None,
     "bounds": None, "required": True, "pii_category": "personal", "max_len": None},
    {"key": "age", "type": "number", "label": {"en": "Age"}, "help": {"en": "Years"}, "options": None,
     "bounds": {"min": 10, "max": 20}, "required": True, "pii_category": "personal", "max_len": None},
    {"key": "level", "type": "multi_choice", "label": {"en": "Level"}, "help": None, "bounds": None,
     "options": [{"key": "o1", "label": {"en": "A"}}, {"key": "o2", "label": {"en": "B"}}],
     "required": False, "pii_category": "none", "max_len": None},
    {"key": "about", "type": "long_text", "label": {"en": "About"}, "help": None, "options": None, "bounds": None,
     "required": False, "pii_category": "personal", "max_len": 300},
]


async def test_builder_settings_apply_decide_flow(db, api):
    t = teacher(db)
    course = catalog_course(db, t, visibility="private")
    base = f"/courses/{course.id}"

    # FormBuilder "Create the form": an empty draft with null title / intro.
    r = await api.call(t, "POST", f"{base}/enrollment-forms", json={"title": None, "intro": None, "fields": []})
    assert r.status_code == 201, r.text
    form = r.json()
    assert form["status"] == "draft" and form["fields"] == [] and form["answered"] is False

    # Save: PATCH replaces title, intro and all fields.
    r = await api.call(t, "PATCH", f"{base}/enrollment-forms/{form['id']}",
                       json={"title": {"en": "Join"}, "intro": None, "fields": BUILDER_FIELDS})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert [f["key"] for f in saved["fields"]] == ["full_name", "age", "level", "about"]
    assert saved["fields"][1]["bounds"] == {"min": 10, "max": 20}

    # Settings → Enrollment before activation: form mode refused (422 form_required, after form_needs_catalog).
    r = await api.call(t, "PATCH", base, json={"enrollment_mode": "form_review", "enrollment_limit": None,
                                               "visibility": "catalog"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "form_required"

    r = await api.call(t, "POST", f"{base}/enrollment-forms/{form['id']}/activate")
    assert r.status_code == 200 and r.json()["status"] == "active"
    r = await api.call(t, "GET", f"{base}/enrollment-forms")
    assert [(v["status"], v["field_count"]) for v in r.json()] == [("active", 4)]

    # Mode and catalog switch in one PATCH (the Settings form sends them together).
    r = await api.call(t, "PATCH", base, json={"enrollment_mode": "form_review", "enrollment_limit": None,
                                               "visibility": "catalog"})
    assert r.status_code == 200, r.text
    assert r.json()["enrollment_mode"] == "form_review" and r.json()["visibility"] == "catalog"

    # Catalog card and landing (CatalogView, CourseLanding).
    s = make_user(db)
    r = await api.call(s, "GET", "/catalog/courses", params={"mode": "form_review"})
    card = next(c for c in r.json()["items"] if c["id"] == str(course.id))
    assert card["has_active_form"] is True and card["my_application"] is None and card["organization_name"] is not None
    r = await api.call(s, "GET", f"/catalog/courses/{course.id}")
    landing = r.json()
    assert landing["form"]["id"] == form["id"] and len(landing["form"]["fields"]) == 4

    # ApplyPage: answersPayload() converts numbers, drops empty optional answers.
    r = await api.call(s, "POST", f"{base}/applications",
                       json={"form_id": form["id"], "answers": {"full_name": "Aidana", "age": 15, "level": ["o2"]}})
    assert r.status_code == 201, r.text
    app = r.json()
    assert app["status"] == "pending"

    # A second submit: 409 application_pending (the apply page shows the "waiting" state).
    r = await api.call(s, "POST", f"{base}/applications", json={"form_id": form["id"], "answers": {"full_name": "A", "age": 15}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "application_pending"

    # Inbox (pending filter) and the panel (answers + fields for the teacher).
    r = await api.call(t, "GET", f"{base}/applications", params={"status": "pending", "limit": 25})
    assert [a["id"] for a in r.json()["items"]] == [app["id"]]
    r = await api.call(t, "GET", f"{base}/applications/{app['id']}")
    panel = r.json()
    assert panel["answers"]["age"] == 15 and [f["key"] for f in panel["fields"]] == ["full_name", "age", "level", "about"]

    # Reject with a note, not e-mailed: the student still sees the note (S4 decision), the email has no note.
    sent_mails().clear()
    r = await api.call(t, "POST", f"{base}/applications/{app['id']}/reject", json={"note": "Next term", "send_note": False})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert len(sent_mails()) == 1 and "Next term" not in (sent_mails()[0].text or "")
    r = await api.call(s, "GET", "/me/applications", params={"limit": 50})
    mine = next(a for a in r.json()["items"] if a["id"] == app["id"])
    assert mine["status"] == "rejected" and mine["decision_note"] == "Next term"
    r = await api.call(s, "GET", f"/catalog/courses/{course.id}")
    assert r.json()["my_application"] == {"id": app["id"], "status": "rejected"}

    # The answered form is immutable; a new version is a draft copy.
    r = await api.call(t, "PATCH", f"{base}/enrollment-forms/{form['id']}", json={"fields": BUILDER_FIELDS[:1]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "form_answered"
    r = await api.call(t, "POST", f"{base}/enrollment-forms/{form['id']}/new-version")
    assert r.status_code == 201 and r.json()["status"] == "draft" and r.json()["version"] == 2
