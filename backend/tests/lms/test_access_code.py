"""Phase 7a S4: quiz access codes (PHASE_7A_DESIGN 2.7, 3.8, 4.4). Set/clear through PATCH (bcrypt hash only),
`has_access_code` / `requires_access_code` flags, the start gate (required / invalid / correct / resume), the failure
rate limit (429 before any comparison once exhausted), staff previews skip it, and the code or its hash never appear
in any payload."""
from sqlalchemy import select

from app.lms.assessments.models import Assessment
from app.lms.attempts.models import Attempt
from tests.lms.attempt_support import frozen_clock, make_quiz  # noqa: F401
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

CODE = "Sesame-42"


def a_url(q):
    return f"/courses/{q.course.id}/assessments/{q.assessment.id}"


async def set_code(api, db, q, code):
    db.refresh(q.assessment)
    return await api.call(q.teacher, "PATCH", a_url(q), json={"draft_rev": q.assessment.draft_rev, "access_code": code})


def no_leak(text: str, *extra: str) -> None:
    for needle in (CODE, "access_code_hash", "$2b$", *extra):
        assert needle not in text, needle


async def test_set_and_clear_through_patch(db, api):
    q = make_quiz(db)
    r = await set_code(api, db, q, f"  {CODE}  ")  # trimmed
    assert r.status_code == 200, r.text
    assert r.json()["has_access_code"] is True
    no_leak(r.text)
    db.expire_all()
    stored = db.get(Assessment, q.assessment.id).access_code_hash
    assert stored.startswith("$2") and CODE not in stored
    staff = await api.call(q.teacher, "GET", a_url(q))
    lst = await api.call(q.teacher, "GET", f"/courses/{q.course.id}/assessments")
    assert staff.json()["has_access_code"] is True and lst.json()["items"][0]["has_access_code"] is True
    no_leak(staff.text)
    no_leak(lst.text)
    # absent = unchanged
    db.refresh(q.assessment)
    r = await api.call(q.teacher, "PATCH", a_url(q), json={"draft_rev": q.assessment.draft_rev, "shuffle_items": True})
    assert r.json()["has_access_code"] is True
    # null clears
    r = await set_code(api, db, q, None)
    assert r.status_code == 200 and r.json()["has_access_code"] is False
    db.expire_all()
    assert db.get(Assessment, q.assessment.id).access_code_hash is None


async def test_invalid_codes_rejected_without_echo(db, api):
    q = make_quiz(db)
    for bad in ("abc", "x" * 33, "кодкод", "tab\tcode", "   ", "y" * 65):
        r = await set_code(api, db, q, bad)
        assert r.status_code == 422, bad
        assert bad.strip() not in r.text or len(bad.strip()) == 0


async def test_editable_on_ort_preset(db, api):
    q = make_quiz(db)
    q.assessment.preset = "ort_main"
    db.commit()
    r = await set_code(api, db, q, CODE)
    assert r.status_code == 200 and r.json()["has_access_code"] is True


async def test_start_gate(db, api, frozen_clock):
    q = make_quiz(db)
    await set_code(api, db, q, CODE)
    lobby = await api.call(q.student, "GET", a_url(q))
    assert lobby.json()["requires_access_code"] is True
    no_leak(lobby.text)
    assert (await api.call(q.teacher, "GET", a_url(q))).json()["has_access_code"] is True
    start = f"{a_url(q)}/attempts"
    r = await api.call(q.student, "POST", start, json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "access_code_required"
    r = await api.call(q.student, "POST", start, json={"access_code": "   "})
    assert r.json()["error"]["code"] == "access_code_required"
    r = await api.call(q.student, "POST", start, json={"access_code": "wrong-code"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "access_code_invalid"
    no_leak(r.text, "wrong-code")
    r = await api.call(q.student, "POST", start, json={"access_code": f" {CODE} "})
    assert r.status_code == 201, r.text
    no_leak(r.text)
    # a resume never asks again
    r = await api.call(q.student, "POST", start, json={})
    assert r.status_code == 200
    assert db.scalar(select(Attempt).where(Attempt.is_preview.is_(False))) is not None


async def test_staff_preview_skips_code(db, api):
    from app.lms.accommodations.service import hash_access_code

    q = make_quiz(db)
    q.assessment.access_code_hash = hash_access_code(CODE)  # direct: keeps the published draft (no preview build)
    db.commit()
    r = await api.call(q.teacher, "POST", f"{a_url(q)}/attempts", json={})
    assert r.status_code == 201 and r.json()["is_preview"] is True


async def test_failure_rate_limit_blocks_even_the_right_code(db, api):
    q = make_quiz(db)
    await set_code(api, db, q, CODE)
    start = f"{a_url(q)}/attempts"
    for i in range(10):
        r = await api.call(q.student, "POST", start, json={"access_code": f"wrong-{i:02d}"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "access_code_invalid", (i, r.text)
    r = await api.call(q.student, "POST", start, json={"access_code": "wrong-xx"})
    assert r.status_code == 429
    r = await api.call(q.student, "POST", start, json={"access_code": CODE})
    assert r.status_code == 429  # no comparison once the failures are used up
    assert db.scalar(select(Attempt)) is None


async def test_without_code_nothing_changes(db, api):
    q = make_quiz(db)
    lobby = (await api.call(q.student, "GET", a_url(q))).json()
    assert lobby["requires_access_code"] is False
    r = await api.call(q.student, "POST", f"{a_url(q)}/attempts", json={"access_code": "ignored"})
    assert r.status_code == 201
