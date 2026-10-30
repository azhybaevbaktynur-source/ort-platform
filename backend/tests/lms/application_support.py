"""Phase 9 S4 helpers: a catalog course with an active enrollment form, applications through the API."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.lms.core.models import utcnow
from app.lms.enrollment_forms import emails, purge
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

FIELDS = [
    {"key": "full_name", "type": "short_text", "label": {"en": "Full name"}, "required": True,
     "pii_category": "personal"},
    {"key": "phone", "type": "phone", "label": {"en": "Phone"}, "required": False, "pii_category": "contact"},
    {"key": "grade", "type": "single_choice", "label": {"en": "Grade"}, "required": True, "pii_category": "none",
     "options": [{"key": "g10", "label": {"en": "10"}}, {"key": "g11", "label": {"en": "11"}}]},
    {"key": "about", "type": "long_text", "label": {"en": "About you"}, "pii_category": "personal"},
]
REAL_SEND = emails.send_application_email  # captured before the autouse stub replaces it
SECRET_NAME = "Zarina Secretova"
SECRET_PHONE = "+996 555 123 456"
SECRET_ABOUT = "I live at 12 Hidden Street"


def answers(**over):
    a = {"full_name": SECRET_NAME, "phone": SECRET_PHONE, "grade": "g10", "about": SECRET_ABOUT}
    a.update(over)
    return a


@pytest.fixture(autouse=True)
def _purge_throttle_and_mail(monkeypatch):
    """Every test starts with a fresh opportunistic-purge slot and an email stub (`sent` list on the module)."""
    purge.reset_throttle()
    sent: list = []
    monkeypatch.setattr(emails, "send_application_email", lambda mail: sent.append(mail) or True)
    emails._test_sent = sent  # type: ignore[attr-defined]
    yield
    purge.reset_throttle()


def sent_mails():
    return emails._test_sent  # type: ignore[attr-defined]


_N = [0]


def catalog_course(db, owner, *, mode="invite_code", **kw):
    _N[0] += 1
    fields = dict(status="published", visibility="catalog", enrollment_mode=mode,
                  published_at=utcnow() - timedelta(minutes=10_000 - _N[0]))
    fields.update(kw)
    return make_course(db, owner, **fields)


async def make_form(api, owner, course, fields=None, *, activate=True):
    r = await api.call(owner, "POST", f"/courses/{course.id}/enrollment-forms",
                       json={"fields": FIELDS if fields is None else fields})
    assert r.status_code == 201, r.text
    form = r.json()
    if activate:
        r = await api.call(owner, "POST", f"/courses/{course.id}/enrollment-forms/{form['id']}/activate")
        assert r.status_code == 200, r.text
        form = r.json()
    return form


async def form_course(db, api, owner=None, *, mode="form_review", fields=None, **kw):
    """Published catalog course in `mode` with an active form. Returns (course, form, owner)."""
    owner = owner or teacher(db)
    course = catalog_course(db, owner, **kw)
    form = await make_form(api, owner, course, fields)
    r = await api.call(owner, "PATCH", f"/courses/{course.id}", json={"enrollment_mode": mode})
    assert r.status_code == 200, r.text
    db.expire_all()
    return course, form, owner


async def apply(api, user, course, form, ans=None):
    return await api.call(user, "POST", f"/courses/{course.id}/applications",
                          json={"form_id": form["id"], "answers": answers() if ans is None else ans})
