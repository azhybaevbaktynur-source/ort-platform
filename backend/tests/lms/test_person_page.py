"""S4 person page (docs/ROADMAP_EXAM_PREP.md S4, docs/DISCUSSION_ADMIN_CENTER.md part B, A4, A9).

Users list: email/name substring search, filters, one query per page, test students never listed. Person page: last
login (a full sign-in and the two-step login step, never a refresh), age and consent, parent links, the pending email
change. Attempt lookup: only that person's attempts, never answers, scores, results or grades. Actions: password reset
and email change, each with a reason, audited, behind the S1 admin gate. Email change (A9): self-service with the
password and a rate limit, a 24-hour single-use link to the new address, collision checked again at confirmation, old
sessions end, a notice without a link goes to the old address."""
from __future__ import annotations

import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db import session as db_session
from app.lms.access.models import AccessPass
from app.lms.attempts.models import Attempt
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock as clock_module
from app.lms.core import ratelimit
from app.lms.email_change import service as ec
from app.lms.email_change.models import EmailChangeRequest
from app.lms.guardian.models import GuardianLink
from app.lms.privacy.anonymize import anonymize_user
from app.main import app
from app.models.user import User
from app.services import email_service
from tests.lms.attempt_support import attempt_stubs, attempt_url, make_quiz  # noqa: F401
from tests.lms.factories import auth, make_user
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401
from tests.lms.test_admin_mfa import PASSWORD, clock, code_at, enroll  # noqa: F401

V = "/api/v1"
P = f"{V}/platform"
FORBIDDEN_KEYS = {"raw_score", "result", "points_possible", "response", "score", "grade", "correctness", "answers"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example")
    monkeypatch.setattr(email_service, "send_email",
                        lambda to, subject, text, html, **kw: sent.append(dict(to=to, subject=subject, text=text,
                                                                                **kw)) or True)
    return sent


def code_of(res) -> str:
    body = res.json() or {}
    err = body.get("error") or {}
    if err:
        return err.get("code")
    detail = body.get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def tok(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.id, 'tv': user.token_version or 0})}"}


def person(db, **kw) -> User:
    user = make_user(db, **kw)
    user.password_hash = hash_password(PASSWORD)
    db.commit()
    return user


def admin(db) -> User:
    return make_user(db, platform_admin=True, display_name="Admin")


def audit_rows(db, action: str, target_id: str) -> list[AdminAuditLog]:
    db.expire_all()
    return list(db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action,
                                                       AdminAuditLog.target_id == target_id)).scalars())


def link_token(mail: dict) -> str:
    url = next(w for w in mail["text"].split() if w.startswith("https://app.example/"))
    assert "/confirm-email?" in url
    return parse_qs(urlparse(url).query)["token"][0]


def ids(res) -> list[str]:
    assert res.status_code == 200, res.text
    return [u["id"] for u in res.json()["items"]]


# ------------------------------------------------------------------ users list

def test_search_matches_email_substring_and_name_case_insensitively(client, db):
    a = admin(db)
    u1 = make_user(db, email=f"zara.{uuid.uuid4().hex[:6]}@school-kg.example", display_name="айгерим бекова")  # SQLite lower() is ASCII only
    u2 = make_user(db, email=f"bob.{uuid.uuid4().hex[:6]}@mail.example", display_name="Bob Stone")
    test_student = make_user(db, email=f"x.{uuid.uuid4().hex[:6]}@school-kg.example")
    test_student.is_test_student = True
    db.commit()
    assert ids(client.get(f"{P}/users", params={"q": "SCHOOL-KG"}, headers=auth(a))) == [u1.id]  # not at the start
    assert ids(client.get(f"{P}/users", params={"q": "бекова"}, headers=auth(a))) == [u1.id]
    assert ids(client.get(f"{P}/users", params={"q": "stone"}, headers=auth(a))) == [u2.id]
    assert ids(client.get(f"{P}/users", params={"q": "%"}, headers=auth(a))) == []  # a wildcard is a plain character


def test_filters_unconfirmed_disabled_admins_and_active_access(client, db):
    a = admin(db)
    tag = uuid.uuid4().hex[:8]
    plain = make_user(db, email=f"plain.{tag}@t.example")
    unconfirmed = make_user(db, email=f"unconf.{tag}@t.example")
    unconfirmed.email_verified = False
    disabled = make_user(db, email=f"dis.{tag}@t.example", disabled=True)
    other_admin = make_user(db, email=f"adm.{tag}@t.example", platform_admin=True)
    paid = make_user(db, email=f"paid.{tag}@t.example")
    expired = make_user(db, email=f"old.{tag}@t.example")
    revoked = make_user(db, email=f"rev.{tag}@t.example")
    now = clock_module.now()
    db.add_all([
        AccessPass(user_id=paid.id, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=9), source="admin"),
        AccessPass(user_id=expired.id, starts_at=now - timedelta(days=9), ends_at=now - timedelta(days=1),
                   source="admin"),
        AccessPass(user_id=revoked.id, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=9),
                   source="admin", revoked_at=now),
    ])
    db.commit()

    def got(**params):
        return set(ids(client.get(f"{P}/users", params={"q": tag, **params}, headers=auth(a))))

    everyone = {plain.id, unconfirmed.id, disabled.id, other_admin.id, paid.id, expired.id, revoked.id}
    assert got() == everyone
    assert got(email_unverified="true") == {unconfirmed.id}
    assert got(disabled="true") == {disabled.id}
    assert got(platform_admin="true") == {other_admin.id}
    assert got(has_access="true") == {paid.id}
    assert got(has_access="true", disabled="true") == set()


def test_list_pages_with_a_cursor_and_one_query_per_page(client, db):
    a = admin(db)
    tag = uuid.uuid4().hex[:8]
    users = [make_user(db, email=f"p{i}.{tag}@t.example") for i in range(5)]
    seen, cursor = [], None
    while True:
        params = {"q": tag, "limit": 2, **({"cursor": cursor} if cursor else {})}
        res = client.get(f"{P}/users", params=params, headers=auth(a))
        seen += ids(res)
        cursor = res.json()["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == sorted(u.id for u in users) and len(seen) == len(set(seen))

    statements: list[str] = []

    def count(conn, cursor_, statement, *args):
        statements.append(statement)

    def queries(limit: int) -> int:
        statements.clear()
        event.listen(db_session.engine, "before_cursor_execute", count)
        try:
            assert client.get(f"{P}/users", params={"has_access": "true", "limit": limit},
                              headers=auth(a)).status_code == 200
        finally:
            event.remove(db_session.engine, "before_cursor_execute", count)
        return sum(1 for s in statements if "FROM users" in s)

    make_user(db)
    queries(1)  # warm-up: first-use reads of the process
    assert queries(1) == queries(50) <= 2  # the caller's own row, then the page itself


def test_list_rows_carry_last_login(client, db):
    a = admin(db)
    u = person(db)
    assert client.post(f"{V}/auth/login", json={"email": u.email, "password": PASSWORD}).status_code == 200
    row = next(r for r in client.get(f"{P}/users", params={"q": u.email}, headers=auth(a)).json()["items"])
    assert row["last_login_at"] is not None


# ------------------------------------------------------------------ admin gate

@pytest.mark.parametrize("method,path,body", [
    ("GET", "/users", None), ("GET", "/users/{uid}", None), ("GET", "/users/{uid}/attempts", None),
    ("POST", "/users/{uid}/password-reset", {"reason": "asked"}),
    ("POST", "/users/{uid}/email-change", {"new_email": "n@t.example", "reason": "asked"}),
])
def test_every_person_route_is_platform_admin_only_and_behind_two_step_login(client, db, monkeypatch, outbox, method,
                                                                              path, body):
    target = make_user(db)
    url = P + path.format(uid=target.id)
    teacher = make_user(db, teacher_status="approved")
    assert client.request(method, url, json=body, headers=auth(teacher)).status_code == 403
    assert client.request(method, url, json=body).status_code == 401
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    res = client.request(method, url, json=body, headers=auth(admin(db)))
    assert res.status_code == 403 and code_of(res) == "mfa_enrollment_required"
    assert outbox == []


# ------------------------------------------------------------------ last login

def test_last_login_is_set_on_login_and_not_on_refresh(client, db):
    u = person(db)
    assert u.last_login_at is None
    res = client.post(f"{V}/auth/login", json={"email": u.email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    db.expire_all()
    first = db.get(User, u.id).last_login_at
    assert first is not None
    db.get(User, u.id).last_login_at = first - timedelta(days=3)
    db.commit()
    token = res.json()["access_token"]
    assert client.post(f"{V}/auth/refresh", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    db.expire_all()
    assert db.get(User, u.id).last_login_at.replace(tzinfo=None) == (first - timedelta(days=3)).replace(tzinfo=None)


def test_a_wrong_password_or_an_unconfirmed_email_sets_no_last_login(client, db, outbox):
    u = person(db)
    assert client.post(f"{V}/auth/login", json={"email": u.email, "password": "nope"}).status_code == 401
    u.email_verified = False
    db.commit()
    assert client.post(f"{V}/auth/login", json={"email": u.email, "password": PASSWORD}).status_code == 403
    db.expire_all()
    assert db.get(User, u.id).last_login_at is None


async def test_last_login_waits_for_the_two_step_login_step(db, client, clock):  # noqa: F811
    a = admin(db)
    a.password_hash = hash_password(PASSWORD)
    db.commit()
    secret, _codes, _token = await enroll(db, a)
    db.expire_all()
    db.get(User, a.id).last_login_at = None
    db.commit()
    res = client.post(f"{V}/auth/login", json={"email": a.email, "password": PASSWORD})
    assert res.status_code == 403 and code_of(res) == "mfa_required"
    db.expire_all()
    assert db.get(User, a.id).last_login_at is None  # the password alone is not a sign-in
    clock["now"] += 30
    res = client.post(f"{V}/auth/mfa", json={"challenge": res.json()["detail"]["challenge"], "code": code_at(secret)})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(User, a.id).last_login_at is not None


# ------------------------------------------------------------------ person page

def test_person_page_shows_age_consent_parent_links_and_pending_change(client, db, outbox):
    a = admin(db)
    kid = make_user(db, display_name="Kid")
    kid.age_band, kid.consent_state = "under_14", "ok"
    mom = make_user(db, display_name="Mom", email=f"mom.{uuid.uuid4().hex[:6]}@t.example")
    dad = make_user(db, display_name="Dad")
    db.add_all([GuardianLink(guardian_user_id=mom.id, student_user_id=kid.id),
                GuardianLink(guardian_user_id=dad.id, student_user_id=kid.id, revoked_at=clock_module.now())])
    db.commit()
    body = client.get(f"{P}/users/{kid.id}", headers=auth(a)).json()
    assert body["age_band"] == "under_14" and body["consent_state"] == "ok" and body["last_login_at"] is None
    links = body["parent_links"]
    assert links["parents_count"] == 1 and links["parents"] == [{"id": mom.id, "display_name": "Mom"}]
    assert links["children_count"] == 0
    assert mom.email not in str(links)  # display names only
    assert client.get(f"{P}/users/{mom.id}", headers=auth(a)).json()["parent_links"]["children"] == [
        {"id": kid.id, "display_name": "Kid"}]
    assert body["pending_email_change"] is None
    res = client.post(f"{P}/users/{kid.id}/email-change", json={"new_email": "kid.new@t.example", "reason": "typo"},
                      headers=auth(a))
    assert res.status_code == 200, res.text
    pending = res.json()["pending_email_change"]
    assert pending["new_email"] == "kid.new@t.example" and pending["by_admin"] is True


# ------------------------------------------------------------------ attempt lookup

def _attempt_with_answers(client, db, q, n_answers: int) -> str:
    h = auth(q.student)
    aid = client.post(attempt_url(q.course, q.assessment), json={}, headers=h).json()["id"]
    if n_answers:
        answers = [{"position": i + 1, "client_ts": 1000 + i, "response": {"choice_id": "B"}} for i in range(n_answers)]
        assert client.put(f"{V}/attempts/{aid}/answers", json={"answers": answers}, headers=h).status_code == 200
    return aid


def test_attempt_lookup_shows_status_and_saved_answer_count_only(client, db):
    a = admin(db)
    q = make_quiz(db, sections=[("s1", 3, None)], allowed_attempts=2)
    aid = _attempt_with_answers(client, db, q, 2)
    res = client.get(f"{P}/users/{q.student.id}/attempts", headers=auth(a))
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["id"] == aid and row["status"] == "in_progress" and row["saved_answers"] == 2
    assert row["item_count"] == 3 and row["submitted_at"] is None
    assert row["course_title"] == q.course.title and row["assessment_title"] == q.assessment.title
    assert not FORBIDDEN_KEYS & set(row)
    # submitted: still only the status, never the score
    assert client.post(f"{V}/attempts/{aid}/submit", json={}, headers=auth(q.student)).status_code == 200
    row = client.get(f"{P}/users/{q.student.id}/attempts", headers=auth(a)).json()["items"][0]
    assert row["status"] != "in_progress" and row["submitted_at"] is not None and row["submit_reason"] == "manual"
    assert not FORBIDDEN_KEYS & set(row) and '"B"' not in res.text and "choice_id" not in res.text


def test_attempt_lookup_lists_only_that_persons_attempts_and_pages(client, db):
    a = admin(db)
    q = make_quiz(db, allowed_attempts=3)
    first = _attempt_with_answers(client, db, q, 0)
    assert client.post(f"{V}/attempts/{first}/submit", json={}, headers=auth(q.student)).status_code == 200
    second = _attempt_with_answers(client, db, q, 1)
    other = make_user(db)
    from tests.lms.factories import enroll as enroll_user

    enroll_user(db, q.course, other)
    other_attempt = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(other)).json()["id"]
    # a staff preview of the teacher never shows up as the teacher's attempt
    client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.teacher))

    page1 = client.get(f"{P}/users/{q.student.id}/attempts", params={"limit": 1}, headers=auth(a)).json()
    page2 = client.get(f"{P}/users/{q.student.id}/attempts", params={"limit": 1, "cursor": page1["next_cursor"]},
                       headers=auth(a)).json()
    got = [r["id"] for r in page1["items"] + page2["items"]]
    assert sorted(got) == sorted([first, second]) and page2["next_cursor"] is None
    assert [r["id"] for r in client.get(f"{P}/users/{other.id}/attempts", headers=auth(a)).json()["items"]] == [
        other_attempt]
    assert client.get(f"{P}/users/{q.teacher.id}/attempts", headers=auth(a)).json()["items"] == []
    assert client.get(f"{P}/users/nope/attempts", headers=auth(a)).status_code == 404
    db.expire_all()
    assert db.execute(select(Attempt).where(Attempt.user_id == q.teacher.id)).first() is not None


# ------------------------------------------------------------------ password reset

def test_admin_sends_the_existing_reset_email_with_a_reason(client, db, outbox):
    a = admin(db)
    u = make_user(db)
    assert client.post(f"{P}/users/{u.id}/password-reset", json={"reason": ""}, headers=auth(a)).status_code == 422
    res = client.post(f"{P}/users/{u.id}/password-reset", json={"reason": "asked by phone"}, headers=auth(a))
    assert res.status_code == 200, res.text
    assert len(outbox) == 1 and outbox[0]["to"] == u.email and "/reset-password?token=" in outbox[0]["text"]
    db.expire_all()
    assert db.get(User, u.id).reset_token is not None
    rows = audit_rows(db, "user.password_reset_sent", u.id)
    assert len(rows) == 1 and rows[0].reason == "asked by phone" and rows[0].actor_id == a.id
    token = parse_qs(urlparse(next(w for w in outbox[0]["text"].split() if "token=" in w)).query)["token"][0]
    again = client.post(f"{P}/users/{u.id}/password-reset", json={"reason": "again"}, headers=auth(a))
    assert again.status_code == 409 and code_of(again) == "reset_cooldown"
    res = client.post(f"{V}/auth/reset-password", json={"token": token, "new_password": "brand new pass"})
    assert res.status_code == 200, res.text


def test_no_reset_email_for_a_disabled_account(client, db, outbox):
    a = admin(db)
    u = make_user(db, disabled=True)
    res = client.post(f"{P}/users/{u.id}/password-reset", json={"reason": "x"}, headers=auth(a))
    assert res.status_code == 409 and code_of(res) == "target_disabled" and outbox == []


# ------------------------------------------------------------------ email change: self-service

def _request_own(client, user, new_email, password=PASSWORD, lang="ru"):
    return client.post(f"{V}/me/email-change", json={"new_email": new_email, "password": password, "lang": lang},
                       headers=tok(user))


def test_self_service_change_happy_path(client, db, outbox):
    u = person(db, display_name="Student")
    old_email = u.email
    old_headers = tok(u)
    res = _request_own(client, u, "  New.Address@T.example ")
    assert res.status_code == 201, res.text
    assert res.json()["pending"]["new_email"] == "new.address@t.example" and res.json()["pending"]["by_admin"] is False
    assert len(outbox) == 1 and outbox[0]["to"] == "new.address@t.example" and outbox[0]["private"] is True
    assert "подтвердите" in outbox[0]["subject"]
    token = link_token(outbox[0])
    db.expire_all()
    row = db.execute(select(EmailChangeRequest).where(EmailChangeRequest.user_id == u.id)).scalar_one()
    assert token not in row.token_hash and len(row.token_hash) == 64  # only the keyed hash is stored
    assert db.get(User, u.id).email == old_email  # nothing changes before the link is opened
    assert client.get(f"{V}/me/email-change", headers=old_headers).json()["pending"]["new_email"] == \
        "new.address@t.example"

    res = client.post(f"{V}/auth/email-change/confirm", json={"token": token})
    assert res.status_code == 200, res.text
    assert res.json() == {"user_id": u.id, "email": "new.address@t.example"}
    db.expire_all()
    user = db.get(User, u.id)
    assert user.email == "new.address@t.example" and user.email_verified is True and user.token_version == 1
    assert db.execute(select(EmailChangeRequest).where(EmailChangeRequest.user_id == u.id)).first() is None
    # old sessions end
    assert client.get(f"{V}/me/email-change", headers=old_headers).status_code == 401
    # a notice to the old address, without a link and without the new address
    notice = outbox[-1]
    assert notice["to"] == old_email and notice["private"] is True
    assert "http" not in notice["text"] and "new.address" not in notice["text"]
    # sign in with the new address, not the old one
    assert client.post(f"{V}/auth/login", json={"email": old_email, "password": PASSWORD}).status_code == 401
    assert client.post(f"{V}/auth/login", json={"email": "new.address@t.example", "password": PASSWORD}
                       ).status_code == 200
    rows = audit_rows(db, "user.email_changed", u.id)
    assert len(rows) == 1 and rows[0].actor_id == u.id
    assert rows[0].details == {"old_email": old_email, "new_email": "new.address@t.example", "by": "self"}
    assert len(audit_rows(db, "user.email_change.requested", u.id)) == 1


def test_self_service_needs_the_current_password(client, db, outbox):
    u = person(db)
    res = _request_own(client, u, "n1@t.example", password="wrong password")
    assert res.status_code == 403 and code_of(res) == "password_incorrect" and outbox == []
    res = client.post(f"{V}/me/email-change", json={"new_email": "n1@t.example"}, headers=tok(u))
    assert res.status_code == 422


def test_self_service_is_rate_limited_counting_wrong_passwords(client, db, outbox):
    u = person(db)
    for i in range(ec.REQUEST_USER_1H.limit):
        assert _request_own(client, u, f"try{i}@t.example", password="wrong").status_code == 403
    res = _request_own(client, u, "late@t.example")
    assert res.status_code == 429 and code_of(res) == "rate_limited" and outbox == []


def test_same_address_and_taken_address_are_refused(client, db, outbox):
    u = person(db)
    other = make_user(db, email=f"taken.{uuid.uuid4().hex[:6]}@t.example")
    res = _request_own(client, u, u.email.upper())
    assert res.status_code == 422 and code_of(res) == "email_same"
    res = _request_own(client, u, other.email)
    assert res.status_code == 409 and code_of(res) == "email_taken" and outbox == []


def test_link_expires_after_24_hours(client, db, outbox, monkeypatch):
    u = person(db)
    assert _request_own(client, u, "late.link@t.example").status_code == 201
    token = link_token(outbox[0])
    later = clock_module.now() + timedelta(hours=24, seconds=1)
    monkeypatch.setattr(clock_module, "now", lambda: later)
    res = client.post(f"{V}/auth/email-change/confirm", json={"token": token})
    assert res.status_code == 422 and code_of(res) == "email_change_expired"
    db.expire_all()
    assert db.get(User, u.id).email != "late.link@t.example"
    assert db.execute(select(EmailChangeRequest).where(EmailChangeRequest.user_id == u.id)).first() is None


def test_link_works_once_and_a_newer_request_replaces_the_older_link(client, db, outbox):
    u = person(db)
    assert _request_own(client, u, "first@t.example").status_code == 201
    first = link_token(outbox[-1])
    assert _request_own(client, u, "second@t.example").status_code == 201
    second = link_token(outbox[-1])
    res = client.post(f"{V}/auth/email-change/confirm", json={"token": first})
    assert res.status_code == 422 and code_of(res) == "email_change_invalid"
    assert client.post(f"{V}/auth/email-change/confirm", json={"token": second}).status_code == 200
    res = client.post(f"{V}/auth/email-change/confirm", json={"token": second})  # reuse
    assert res.status_code == 422 and code_of(res) == "email_change_invalid"
    db.expire_all()
    assert db.get(User, u.id).email == "second@t.example" and db.get(User, u.id).token_version == 1


def test_collision_at_confirmation_time_is_refused(client, db, outbox):
    u = person(db)
    assert _request_own(client, u, "wanted@t.example").status_code == 201
    token = link_token(outbox[-1])
    make_user(db, email="wanted@t.example")  # someone registered the address meanwhile
    res = client.post(f"{V}/auth/email-change/confirm", json={"token": token})
    assert res.status_code == 409 and code_of(res) == "email_taken"
    db.expire_all()
    user = db.get(User, u.id)
    assert user.email != "wanted@t.example" and user.token_version == 0
    assert audit_rows(db, "user.email_changed", u.id) == []


def test_cancel_drops_the_pending_change(client, db, outbox):
    u = person(db)
    assert _request_own(client, u, "gone@t.example").status_code == 201
    token = link_token(outbox[-1])
    assert client.delete(f"{V}/me/email-change", headers=tok(u)).status_code == 204
    assert client.get(f"{V}/me/email-change", headers=tok(u)).json()["pending"] is None
    assert client.post(f"{V}/auth/email-change/confirm", json={"token": token}).status_code == 422
    rows = audit_rows(db, "user.email_change.cancelled", u.id)
    assert len(rows) == 1 and rows[0].actor_id == u.id and rows[0].details == {"by": "self"}


def test_admin_cancels_a_pending_change_with_a_reason(client, db, outbox):
    a = admin(db)
    u = person(db)
    url = f"{P}/users/{u.id}/email-change/cancel"
    res = client.post(url, json={"reason": "x"}, headers=auth(a))
    assert res.status_code == 404 and code_of(res) == "email_change_not_found"
    assert _request_own(client, u, "undo@t.example").status_code == 201
    token = link_token(outbox[-1])
    assert client.post(url, json={"reason": ""}, headers=auth(a)).status_code == 422
    assert client.post(url, json={"reason": "x"}, headers=auth(make_user(db, teacher_status="approved"))
                       ).status_code == 403
    res = client.post(url, json={"reason": "asked by phone"}, headers=auth(a))
    assert res.status_code == 200, res.text and res.json()["pending_email_change"] is None
    assert res.json()["pending_email_change"] is None
    assert client.post(f"{V}/auth/email-change/confirm", json={"token": token}).status_code == 422
    rows = audit_rows(db, "user.email_change.cancelled", u.id)
    assert len(rows) == 1 and rows[0].actor_id == a.id and rows[0].reason == "asked by phone"


def test_an_admin_started_change_dies_when_the_person_becomes_a_platform_admin(client, db, outbox):
    a = admin(db)
    u = person(db)
    assert client.post(f"{P}/users/{u.id}/email-change", json={"new_email": "later@t.example", "reason": "r"},
                       headers=auth(a)).status_code == 200
    token = link_token(next(m for m in outbox if m["to"] == "later@t.example"))
    # promoted outside the grant flow (e.g. directly in the database): the link is refused at confirmation
    db.expire_all()
    db.get(User, u.id).is_platform_admin = True
    db.commit()
    res = client.post(f"{V}/auth/email-change/confirm", json={"token": token})
    assert res.status_code == 422 and code_of(res) == "email_change_invalid"
    db.expire_all()
    assert db.get(User, u.id).email != "later@t.example"
    assert db.execute(select(EmailChangeRequest).where(EmailChangeRequest.user_id == u.id)).first() is None


def test_promoting_to_platform_admin_drops_a_pending_change(client, db, outbox):
    from app.lms.platform_admin import admins

    a = admin(db)
    u = person(db)
    assert client.post(f"{P}/users/{u.id}/email-change", json={"new_email": "gone2@t.example", "reason": "r"},
                       headers=auth(a)).status_code == 200
    db.expire_all()
    admins.grant(db, db.get(User, u.id))
    db.commit()
    assert db.execute(select(EmailChangeRequest).where(EmailChangeRequest.user_id == u.id)).first() is None


async def test_a_platform_admin_changing_their_own_address_also_gives_the_code(db, client, clock, outbox):  # noqa: F811
    a = admin(db)
    a.password_hash = hash_password(PASSWORD)
    db.commit()
    res = _request_own(client, a, "admin.new@t.example")  # no two-step login yet
    assert res.status_code == 403 and code_of(res) == "mfa_enrollment_required"
    secret, _codes, token = await enroll(db, a)
    headers = {"Authorization": f"Bearer {token}"}
    body = {"new_email": "admin.new@t.example", "password": PASSWORD, "lang": "en"}
    res = client.post(f"{V}/me/email-change", json=body, headers=headers)
    assert res.status_code == 400 and code_of(res) == "mfa_invalid_code"
    clock["now"] += 30
    res = client.post(f"{V}/me/email-change", json={**body, "code": code_at(secret)}, headers=headers)
    assert res.status_code == 201, res.text
    assert outbox[-1]["to"] == "admin.new@t.example"


def test_confirm_failures_are_rate_limited_per_address(client, db, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    headers = {"x-forwarded-for": "203.0.113.7, 10.255.255.1"}
    for _ in range(ec.CONFIRM_IP_FAIL_10M.limit):
        assert client.post(f"{V}/auth/email-change/confirm", json={"token": "guess"}, headers=headers
                           ).status_code == 422
    res = client.post(f"{V}/auth/email-change/confirm", json={"token": "guess"}, headers=headers)
    assert res.status_code == 429


def test_a_failed_send_leaves_no_pending_change(client, db, monkeypatch):
    u = person(db)
    monkeypatch.setattr(email_service, "send_email", lambda *a, **kw: False)
    res = _request_own(client, u, "never@t.example")
    assert res.status_code == 503 and code_of(res) == "email_send_failed"
    db.expire_all()
    assert db.execute(select(EmailChangeRequest).where(EmailChangeRequest.user_id == u.id)).first() is None


def test_a_test_student_cannot_change_an_email(client, db):
    u = make_user(db)
    u.is_test_student = True
    db.commit()
    assert _request_own(client, u, "ts@t.example").status_code == 403


# ------------------------------------------------------------------ email change: by the admin

def test_admin_change_sends_the_same_link_and_is_audited(client, db, outbox):
    a = admin(db)
    u = person(db)
    u.locale = "ky"
    db.commit()
    old = u.email
    res = client.post(f"{P}/users/{u.id}/email-change", json={"new_email": "fixed@t.example", "reason": ""},
                      headers=auth(a))
    assert res.status_code == 422
    res = client.post(f"{P}/users/{u.id}/email-change", json={"new_email": "fixed@t.example", "reason": "typo"},
                      headers=auth(a))
    assert res.status_code == 200, res.text
    link_mail = next(m for m in outbox if m["to"] == "fixed@t.example")
    assert "ырастаңыз" in link_mail["subject"]
    # the current address hears of it too: no link, not the new address
    notice = next(m for m in outbox if m["to"] == old)
    assert notice["private"] is True and "http" not in notice["text"] and "fixed@" not in notice["text"]
    assert "администратор" in notice["subject"]
    rows = audit_rows(db, "user.email_change.requested", u.id)
    assert len(rows) == 1 and rows[0].actor_id == a.id and rows[0].reason == "typo"
    assert client.post(f"{V}/auth/email-change/confirm", json={"token": link_token(link_mail)}).status_code == 200
    db.expire_all()
    assert db.get(User, u.id).email == "fixed@t.example"
    rows = audit_rows(db, "user.email_changed", u.id)
    assert rows[0].actor_id == a.id and rows[0].details["by"] == "admin" and rows[0].details["old_email"] == old
    assert outbox[-1]["to"] == old


def test_admin_cannot_change_an_admins_disabled_or_unknown_account(client, db, outbox):
    a = admin(db)
    body = {"new_email": "x@t.example", "reason": "r"}
    res = client.post(f"{P}/users/{make_user(db, platform_admin=True).id}/email-change", json=body, headers=auth(a))
    assert res.status_code == 409 and code_of(res) == "target_is_platform_admin"
    res = client.post(f"{P}/users/{make_user(db, disabled=True).id}/email-change", json=body, headers=auth(a))
    assert res.status_code == 409 and code_of(res) == "target_disabled"
    assert client.post(f"{P}/users/nope/email-change", json=body, headers=auth(a)).status_code == 404
    assert outbox == []


def test_a_disabled_account_cannot_confirm(client, db, outbox):
    u = person(db)
    assert _request_own(client, u, "after@t.example").status_code == 201
    token = link_token(outbox[-1])
    db.expire_all()
    db.get(User, u.id).disabled_at = clock_module.now()
    db.commit()
    res = client.post(f"{V}/auth/email-change/confirm", json={"token": token})
    assert res.status_code == 422 and code_of(res) == "email_change_invalid"


# ------------------------------------------------------------------ privacy

def test_deletion_drops_the_pending_change_and_scrubs_the_addresses_in_the_audit(client, db, outbox):
    u = person(db)
    assert _request_own(client, u, "mine@t.example").status_code == 201
    assert client.post(f"{V}/auth/email-change/confirm", json={"token": link_token(outbox[-1])}).status_code == 200
    s = db_session.SessionLocal()
    try:
        s.add(EmailChangeRequest(user_id=u.id, new_email="left@t.example", token_hash="f" * 64,
                                 expires_at=clock_module.now() + timedelta(hours=1), requested_by_id=u.id))
        s.commit()
        anonymize_user(s, u.id, actor_id=u.id)
        s.commit()
    finally:
        s.close()
    db.expire_all()
    assert db.execute(select(EmailChangeRequest).where(EmailChangeRequest.user_id == u.id)).first() is None
    assert db.get(User, u.id).last_login_at is None
    for row in audit_rows(db, "user.email_changed", u.id):
        assert "old_email" not in (row.details or {}) and "new_email" not in (row.details or {})


def test_rate_limit_rules_are_distinct():
    assert len({ec.REQUEST_USER_1H.name, ec.REQUEST_USER_24H.name, ec.CONFIRM_IP_FAIL_10M.name}) == 3
    assert isinstance(ec.CONFIRM_IP_FAIL_10M, ratelimit.Limit) and ec.CONFIRM_IP_FAIL_10M.is_ip_rule
