"""Item 3 slice C (docs/phases/AUTH_SOCIAL_DESIGN.md 10): the admin person page lists how a person signs in: the password
(only a usable one) and the linked Google / Apple accounts with the link date. Never the provider's email or subject."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.lms.oauth.models import UserIdentity
from app.lms.privacy.anonymize import UNUSABLE_PASSWORD_HASH
from app.main import app
from tests.lms.factories import auth, make_user
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401

P = "/api/v1/platform"
LINKED = datetime(2026, 11, 9, 8, 30, tzinfo=timezone.utc)


def _methods(db, target):
    admin = make_user(db, platform_admin=True)
    res = TestClient(app).get(f"{P}/users/{target.id}", headers=auth(admin))
    assert res.status_code == 200, res.text
    return res.json()["sign_in_methods"]


def test_password_only(db):
    assert _methods(db, make_user(db)) == [{"method": "password", "linked_at": None}]


def test_password_and_google_with_the_link_date_but_no_email_or_subject(db):
    user = make_user(db)
    db.add(UserIdentity(user_id=user.id, provider="google", subject="g-sub-123", email="person@gmail.test",
                        email_verified=True, linked_at=LINKED))
    db.commit()
    methods = _methods(db, user)
    assert [m["method"] for m in methods] == ["password", "google"]
    assert methods[1]["linked_at"].startswith("2026-11-09T08:30")
    assert "g-sub-123" not in str(methods) and "gmail" not in str(methods)


def test_google_only_account_has_no_password_line(db):
    user = make_user(db)
    user.password_hash = UNUSABLE_PASSWORD_HASH
    db.add(UserIdentity(user_id=user.id, provider="google", subject="g-only", email=user.email, email_verified=True,
                        linked_at=LINKED))
    db.add(UserIdentity(user_id=user.id, provider="apple", subject="a-only", email=None, email_verified=True,
                        linked_at=LINKED))
    db.commit()
    assert [m["method"] for m in _methods(db, user)] == ["google", "apple"]


def test_no_method_at_all(db):
    user = make_user(db)
    user.password_hash = UNUSABLE_PASSWORD_HASH
    db.commit()
    assert _methods(db, user) == []
