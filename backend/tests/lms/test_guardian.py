"""Phase 11 S2: parents (PHASE_11_DESIGN 4). The link, the age band and the consent state decide on every request; a
parent reads an allow-list of the student's own view and has no way into a course."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.lms.announcements.models import Announcement
from app.lms.core import clock, ratelimit
from app.lms.core.models import utcnow
from app.lms.grading.models import Submission
from app.lms.guardian import service as svc
from app.lms.guardian.models import GuardianLink, GuardianPairingCode
from app.lms.privacy.anonymize import anonymize_user
from app.lms.privacy.models import ConsentRecord, DataRequest
from app.lms.privacy.service import current_policies
from app.models.user import User
from tests.lms.assignment_support import make_assignment, published_quiz, world
from tests.lms.factories import enroll, make_course, set_status
from tests.lms.s3_support import api, clean_rate_limits, db, make_user, teacher  # noqa: F401

ME = "/me/guardians"
LINKS = "/guardian/links"


def code(res) -> str:
    return (res.json().get("error") or {}).get("code")


def person(db, band="18_plus", state="ok", name=None) -> User:
    user = make_user(db, display_name=name)
    user.age_band, user.consent_state = band, state
    db.commit()
    return user


def child(db, name="Child") -> User:
    user = person(db, "under_14", "pending_guardian", name)
    user.consent_due_at = clock.now() - timedelta(minutes=1)
    db.commit()
    return user


async def new_code(api, student) -> str:
    res = await api.call(student, "POST", f"{ME}/pairing-code")
    assert res.status_code == 201, res.text
    return res.json()["code"]


async def link(api, parent, student) -> str:
    res = await api.call(parent, "POST", LINKS, json={"code": await new_code(api, student)})
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def consent(api, db, parent, link_id):
    pid = current_policies(db)["guardian_consent"].id
    db.rollback()
    return await api.call(parent, "POST", f"{LINKS}/{link_id}/consent", json={"policy_version_id": str(pid)})


def read_routes(link_id, course_id) -> list[str]:
    return [f"{LINKS}/{link_id}/courses", f"{LINKS}/{link_id}/courses/{course_id}/grades", f"{LINKS}/{link_id}/due",
            f"{LINKS}/{link_id}/courses/{course_id}/announcements"]


def write_routes(link_id) -> list[tuple[str, str, dict | None]]:
    return [("DELETE", f"{LINKS}/{link_id}", None), ("DELETE", f"{LINKS}/{link_id}/consent", None),
            ("POST", f"{LINKS}/{link_id}/delete-request", None),
            ("POST", f"{LINKS}/{link_id}/consent", {"policy_version_id": str(uuid.uuid4())})]


def fresh(db, user_id) -> User:
    db.expire_all()
    return db.get(User, user_id)


def records(db, user_id):
    db.expire_all()
    return db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user_id)
                      .order_by(ConsentRecord.created_at)).all()


def graded(db, w, a, *, released=True, **fields):
    db.add(Submission(course_id=w.course.id, assignment_id=a.id, enrollment_id=w.enr.id, user_id=w.S.id, state="graded",
                      kept_policy="highest", computed_at=utcnow(), effective_points=Decimal("8"),
                      points_possible=Decimal("10"), released_at=utcnow() if released else None, **fields))
    db.commit()


def announcement(db, w, title, published_at):
    db.add(Announcement(course_id=w.course.id, author_id=w.O.id, title=title, body_md=title, body_html=f"<p>{title}</p>",
                        published_at=published_at))
    db.commit()


# ------------------------------------------------------------------ pairing code

async def test_a_code_is_8_crockford_chars_stored_only_as_a_hash(api, db):
    student = person(db, "14_17")
    res = await api.call(student, "POST", f"{ME}/pairing-code")
    assert res.status_code == 201 and set(res.json()) == {"code", "expires_at"}
    raw = res.json()["code"]
    assert len(raw) == 8 and set(raw) <= set(svc.CODE_ALPHABET)
    row = db.scalars(select(GuardianPairingCode)).one()
    assert raw not in row.code_hash and len(row.code_hash) == 64
    left = row.expires_at.replace(tzinfo=None) - clock.now().replace(tzinfo=None)
    assert timedelta(hours=settings.GUARDIAN_PAIRING_TTL_HOURS - 1) < left <= timedelta(
        hours=settings.GUARDIAN_PAIRING_TTL_HOURS)


async def test_a_new_code_revokes_the_old_one(api, db):
    student, parent = person(db, "14_17"), person(db)
    old = await new_code(api, student)
    new = await new_code(api, student)
    assert (await api.call(parent, "POST", LINKS, json={"code": old})).status_code == 404
    assert (await api.call(parent, "POST", LINKS, json={"code": new})).status_code == 201


@pytest.mark.parametrize("shape", [lambda c: c.lower(), lambda c: f"{c[:4]}-{c[4:]}", lambda c: f" {c[:4]} {c[4:]} "])
async def test_a_code_may_be_typed_loosely(api, db, shape):
    student, parent = person(db, "14_17", name="Aida"), person(db)
    res = await api.call(parent, "POST", LINKS, json={"code": shape(await new_code(api, student))})
    assert res.status_code == 201
    assert set(res.json()) == {"id", "student_name", "needs_consent"}
    assert res.json()["student_name"] == "Aida" and res.json()["needs_consent"] is False


async def test_every_bad_code_has_one_404_shape(api, db):
    student, parent, other = person(db, "14_17"), person(db), person(db)
    used = await new_code(api, student)
    assert (await api.call(other, "POST", LINKS, json={"code": used})).status_code == 201
    expired = await new_code(api, student)
    db.execute(update(GuardianPairingCode).where(GuardianPairingCode.consumed_at.is_(None))
               .values(expires_at=clock.now() - timedelta(seconds=1)))
    db.commit()
    revoked_student = person(db, "14_17")
    revoked = await new_code(api, revoked_student)
    await new_code(api, revoked_student)
    own = await new_code(api, parent)
    bodies = set()
    for bad in (used, expired, revoked, own, "ZZZZZZZZ", "", "short", "!" * 8, "A" * 5000):
        res = await api.call(parent, "POST", LINKS, json={"code": bad})
        assert res.status_code == 404, (bad[:10], res.text)
        bodies.add(json.dumps(res.json(), sort_keys=True))
    assert len(bodies) == 1 and code(res) == "invalid_code"


async def test_a_code_of_a_deleted_or_test_student_is_just_a_bad_code(api, db):
    gone, test_student, parent = person(db, "14_17"), person(db, "14_17"), person(db)
    raw_gone, raw_test = await new_code(api, gone), await new_code(api, test_student)
    gone.deleted_at = clock.now()
    test_student.is_test_student = True
    db.commit()
    for raw in (raw_gone, raw_test):
        res = await api.call(parent, "POST", LINKS, json={"code": raw})
        assert res.status_code == 404 and code(res) == "invalid_code"


async def test_already_linked_keeps_the_code(api, db):
    student, parent, other = person(db, "14_17"), person(db), person(db)
    await link(api, parent, student)
    raw = await new_code(api, student)
    res = await api.call(parent, "POST", LINKS, json={"code": raw})
    assert res.status_code == 409 and code(res) == "already_linked"
    assert (await api.call(other, "POST", LINKS, json={"code": raw})).status_code == 201


async def test_caps(api, db):
    student = person(db, "14_17")
    for _ in range(svc.MAX_GUARDIANS_PER_STUDENT):
        db.add(GuardianLink(guardian_user_id=person(db).id, student_user_id=student.id))
    db.commit()
    raw = await new_code(api, student)
    res = await api.call(person(db), "POST", LINKS, json={"code": raw})
    assert res.status_code == 409 and code(res) == "guardian_limit"
    assert db.scalars(select(GuardianPairingCode)).one().consumed_at is None  # a failed cap rolls the consume back

    parent = person(db)
    for _ in range(svc.MAX_STUDENTS_PER_GUARDIAN):
        db.add(GuardianLink(guardian_user_id=parent.id, student_user_id=person(db, "14_17").id))
    db.commit()
    res = await api.call(parent, "POST", LINKS, json={"code": await new_code(api, person(db, "14_17"))})
    assert res.status_code == 409 and code(res) == "guardian_limit"


# ------------------------------------------------------------------ limits

async def test_pairing_codes_are_limited(api, db):
    student = person(db, "14_17")
    for _ in range(5):
        await new_code(api, student)
    assert (await api.call(student, "POST", f"{ME}/pairing-code")).status_code == 429


async def test_failed_redeems_are_limited_and_success_is_not_counted(api, db):
    parent, students = person(db), [person(db, "14_17") for _ in range(3)]
    for s in students:
        await link(api, parent, s)
    for _ in range(10):
        assert (await api.call(parent, "POST", LINKS, json={"code": "ZZZZZZZZ"})).status_code == 404
    good = await new_code(api, person(db, "14_17"))
    assert (await api.call(parent, "POST", LINKS, json={"code": good})).status_code == 429  # also a good code


async def test_failed_redeems_per_ip_are_limited_across_accounts(api, db, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    monkeypatch.setattr(svc, "PAIR_REDEEM_IP_10M", ratelimit.Limit("pair_redeem_ip_fail_10m", 2, 600, is_ip_rule=True))
    for _ in range(2):
        assert (await api.call(person(db), "POST", LINKS, json={"code": "ZZZZZZZZ"})).status_code == 404
    assert (await api.call(person(db), "POST", LINKS, json={"code": "ZZZZZZZZ"})).status_code == 429


# ------------------------------------------------------------------ who may be a parent

@pytest.mark.parametrize("band", [None, "14_17", "under_14"])
async def test_only_an_adult_can_be_a_parent(api, db, band):
    student, not_adult = person(db, "14_17"), person(db, band)
    raw = await new_code(api, student)
    res = await api.call(not_adult, "POST", LINKS, json={"code": raw})
    assert res.status_code == 403 and code(res) == "guardian_must_be_adult"
    assert (await api.call(not_adult, "GET", LINKS)).status_code == 403
    assert db.scalars(select(GuardianPairingCode)).one().consumed_at is None


async def test_an_unverified_account_cannot_be_a_parent(api, db):
    parent = person(db)
    parent.email_verified = False
    db.commit()
    res = await api.call(parent, "GET", LINKS)
    assert res.status_code == 403 and code(res) == "guardian_must_be_adult"


async def test_the_band_is_read_on_every_request(api, db):
    w = world(db)
    w.S.age_band = "14_17"
    parent = person(db)
    db.commit()
    link_id = await link(api, parent, w.S)
    assert (await api.call(parent, "GET", f"{LINKS}/{link_id}/due")).status_code == 200
    parent.age_band = "14_17"
    db.commit()
    for path in read_routes(link_id, w.cid):
        res = await api.call(parent, "GET", path)
        assert res.status_code == 403 and code(res) == "guardian_must_be_adult"


# ------------------------------------------------------------------ the link is the only way in

async def _bad_link_404s(api, parent, link_id, course_id):
    for path in read_routes(link_id, course_id):
        res = await api.call(parent, "GET", path)
        assert res.status_code == 404 and code(res) == "guardian_link_not_found", (path, res.text)
    for method, path, body in write_routes(link_id):
        res = await api.call(parent, method, path, json=body)
        assert res.status_code == 404 and code(res) == "guardian_link_not_found", (path, res.text)


async def test_another_parent_gets_404(api, db):
    w = world(db)
    w.S.age_band = "14_17"
    parent = person(db)
    db.commit()
    link_id = await link(api, parent, w.S)
    await _bad_link_404s(api, person(db), link_id, w.cid)
    await _bad_link_404s(api, parent, uuid.uuid4(), w.cid)


@pytest.mark.parametrize("by", ["parent", "student", "direct"])
async def test_a_revoked_link_gets_404(api, db, by):
    w = world(db)
    w.S.age_band = "14_17"
    parent = person(db)
    db.commit()
    link_id = await link(api, parent, w.S)
    if by == "parent":
        assert (await api.call(parent, "DELETE", f"{LINKS}/{link_id}")).status_code == 204
    elif by == "student":
        assert (await api.call(w.S, "DELETE", f"{ME}/{link_id}")).status_code == 204
    else:
        db.execute(update(GuardianLink).values(revoked_at=clock.now()))
        db.commit()
    await _bad_link_404s(api, parent, link_id, w.cid)
    assert (await api.call(parent, "GET", LINKS)).json() == []
    assert (await api.call(parent, "GET", "/auth/me")).json()["is_guardian"] is False


async def test_a_deleted_student_gets_404_even_with_a_link_left_active(api, db):
    w = world(db)
    w.S.age_band = "14_17"
    parent = person(db)
    db.commit()
    link_id = await link(api, parent, w.S)
    w.S.deleted_at = clock.now()
    db.commit()
    await _bad_link_404s(api, parent, link_id, w.cid)
    assert (await api.call(parent, "GET", LINKS)).json() == []


async def test_an_anonymized_student_revokes_the_link(api, db):
    w = world(db)
    w.S.age_band = "14_17"
    parent = person(db)
    db.commit()
    link_id = await link(api, parent, w.S)
    anonymize_user(db, w.S.id, actor_id=person(db).id)
    db.commit()
    await _bad_link_404s(api, parent, link_id, w.cid)


async def test_a_test_student_gets_404(api, db):
    w = world(db)
    parent = person(db)
    w.S.is_test_student, w.S.consent_state = True, "exempt"
    db.add(GuardianLink(guardian_user_id=parent.id, student_user_id=w.S.id))
    db.commit()
    link_id = db.scalars(select(GuardianLink)).one().id
    await _bad_link_404s(api, parent, link_id, w.cid)


async def test_a_test_student_is_denied_every_parent_route(api, db):
    w = world(db)
    w.S.is_test_student, w.S.consent_state = True, "exempt"
    w.S.age_band = "18_plus"
    db.commit()
    lid = uuid.uuid4()
    for method, path in [("POST", f"{ME}/pairing-code"), ("GET", ME), ("DELETE", f"{ME}/{lid}"), ("GET", LINKS),
                         ("POST", LINKS), *[("GET", p) for p in read_routes(lid, w.cid)]]:
        res = await api.call(w.S, method, path, json={"code": "X"} if path == LINKS and method == "POST" else None)
        assert res.status_code == 403 and code(res) == "test_student_forbidden", (method, path)


async def test_a_gated_child_reaches_its_own_screen_and_no_parent_route(api, db):
    kid = child(db)
    assert (await api.call(kid, "POST", f"{ME}/pairing-code")).status_code == 201
    assert (await api.call(kid, "GET", ME)).status_code == 200
    res = await api.call(kid, "GET", LINKS)
    assert res.status_code == 403 and code(res) == "consent_required"


async def test_no_course_access_for_a_parent(api, db):
    w = world(db)
    w.S.age_band = "14_17"
    parent = person(db)
    a = make_assignment(db, w.course, w.O)
    db.commit()
    await link(api, parent, w.S)
    for path in (f"/courses/{w.cid}", f"/courses/{w.cid}/grades/mine", f"/courses/{w.cid}/announcements",
                 f"/courses/{w.cid}/assignments", f"/courses/{w.cid}/assignments/{a.id}", f"/courses/{w.cid}/modules",
                 f"/courses/{w.cid}/assessments", f"/courses/{w.cid}/people", f"/courses/{w.cid}/pages"):
        res = await api.call(parent, "GET", path)
        assert res.status_code in (403, 404), (path, res.status_code)
    listed = (await api.call(parent, "GET", "/courses")).json()
    assert w.cid not in json.dumps(listed)
    assert (await api.call(parent, "GET", "/me/home")).json()["courses"] == []
    assert db.scalars(select(GuardianLink)).one().guardian_user_id == parent.id


# ------------------------------------------------------------------ allow-list

GRADE_KEYS = {"title", "due_at", "state", "points", "possible", "percent", "label", "display_value", "max_value",
              "scheme_type", "labels"}
TOTAL_KEYS = {"percent", "label"}


def banned_absent(raw: str) -> None:
    for word in ("hand_in", "feedback", "rubric", "attempt", "assessment_id", "assignment_id", "submitted_at", "late",
                 "SECRET-FEEDBACK", "email", "author"):
        assert word not in raw, word


async def test_responses_are_exactly_the_allow_list(api, db):
    w = world(db)
    w.S.age_band = "14_17"
    w.S.display_name = "Aida"
    parent = person(db, name="Mother")
    db.commit()
    link_id = await link(api, parent, w.S)
    text_work = make_assignment(db, w.course, w.O, title={"en": "Essay"}, due_at=clock.now() + timedelta(days=9))
    make_assignment(db, w.course, w.O, title={"en": "Open work"}, due_at=clock.now() + timedelta(days=3))
    graded(db, w, text_work, feedback_text="SECRET-FEEDBACK", label="A")
    announcement(db, w, "Trip", clock.now() - timedelta(hours=1))

    res = await api.call(parent, "GET", f"{LINKS}/{link_id}/courses")
    assert set(res.json()) == {"items", "next_cursor"} and set(res.json()["items"][0]) == {"id", "title"}
    assert res.json()["items"][0]["id"] == w.cid

    res = await api.call(parent, "GET", f"{LINKS}/{link_id}/courses/{w.cid}/grades")
    body = res.json()
    assert res.status_code == 200 and set(body) == {"total", "items"} and set(body["total"]) == TOTAL_KEYS
    assert all(set(i) == GRADE_KEYS for i in body["items"])
    essay = next(i for i in body["items"] if i["title"] == {"en": "Essay"})
    assert essay["state"] == "graded" and Decimal(essay["points"]) == 8 and Decimal(essay["possible"]) == 10
    assert Decimal(essay["percent"]) == 80 and essay["label"] == "A"
    banned_absent(res.text)

    res = await api.call(parent, "GET", f"{LINKS}/{link_id}/due")
    assert res.status_code == 200 and [set(r) for r in res.json()] == [{"course_title", "title", "kind", "due_at"}] * 2
    assert res.json()[0]["title"] == {"en": "Open work"} and res.json()[0]["kind"] == "text"  # soonest first, as at home
    assert len((await api.call(parent, "GET", f"{LINKS}/{link_id}/due", params={"limit": 1})).json()) == 1
    banned_absent(res.text)

    res = await api.call(parent, "GET", f"{LINKS}/{link_id}/courses/{w.cid}/announcements")
    assert set(res.json()) == {"items", "next_cursor"}
    assert [set(r) for r in res.json()["items"]] == [{"title", "body_html", "published_at"}]
    assert res.json()["items"][0]["title"] == "Trip"
    banned_absent(res.text)

    res = await api.call(parent, "GET", LINKS)
    assert [set(r) for r in res.json()] == [{"id", "student_name", "created_at", "needs_consent", "holds_consent",
                                             "under_14"}]
    assert res.json()[0]["student_name"] == "Aida"
    assert "@" not in res.text

    res = await api.call(w.S, "GET", ME)
    assert [set(r) for r in res.json()] == [{"id", "guardian_name", "created_at", "holds_consent"}]
    assert res.json()[0]["guardian_name"] == "Mother" and "@" not in res.text


async def test_a_name_missing_never_shows_the_email(api, db):
    student, parent = person(db, "14_17"), person(db)
    await link(api, parent, student)
    assert "@" not in (await api.call(parent, "GET", LINKS)).text
    assert "@" not in (await api.call(student, "GET", ME)).text


async def test_what_is_hidden_from_the_student_is_hidden_from_the_parent(api, db):
    w = world(db)
    w.S.age_band = "14_17"
    parent = person(db)
    db.commit()
    link_id = await link(api, parent, w.S)
    held = make_assignment(db, w.course, w.O, title={"en": "Held back"})
    graded(db, w, held, released=False)
    make_assignment(db, w.course, w.O, title={"en": "Unpublished"}, published=False)
    published_quiz(db, w.course, w.O, title={"en": "Never shown"}, results_policy="never")
    announcement(db, w, "Draft", None)
    announcement(db, w, "Tomorrow", clock.now() + timedelta(days=1))
    announcement(db, w, "Today", clock.now() - timedelta(minutes=5))

    items = (await api.call(parent, "GET", f"{LINKS}/{link_id}/courses/{w.cid}/grades")).json()["items"]
    mine = (await api.call(w.S, "GET", f"/courses/{w.cid}/grades/mine")).json()["items"]
    assert [(i["title"], i["state"]) for i in items] == [(i["title"], i["state"]) for i in mine]
    by_title = {i["title"]["en"]: i for i in items}
    assert "Unpublished" not in by_title
    assert by_title["Held back"]["state"] == "pending" and by_title["Never shown"]["state"] == "hidden"
    for row in (by_title["Held back"], by_title["Never shown"]):
        assert row["points"] is None and row["possible"] is None and row["percent"] is None and row["label"] is None

    rows = (await api.call(parent, "GET", f"{LINKS}/{link_id}/courses/{w.cid}/announcements")).json()["items"]
    assert [r["title"] for r in rows] == ["Today"]
    due = (await api.call(parent, "GET", f"{LINKS}/{link_id}/due")).json()
    assert "Unpublished" not in json.dumps(due)


async def test_a_course_outside_the_active_student_enrollments_is_404(api, db):
    w = world(db)
    w.S.age_band = "14_17"
    parent = person(db)
    db.commit()
    link_id = await link(api, parent, w.S)
    other = make_course(db, w.O, title={"en": "Other"}, organization_id=w.course.organization_id)
    set_status(db, other, "published")
    taught = make_course(db, w.O, title={"en": "Assisted"}, organization_id=w.course.organization_id)
    set_status(db, taught, "published")
    enroll(db, taught, w.S, role="assistant", source="owner")
    left = make_course(db, w.O, title={"en": "Left"}, organization_id=w.course.organization_id)
    set_status(db, left, "published")
    gone = enroll(db, left, w.S)
    gone.state = "removed"
    draft = make_course(db, w.O, title={"en": "Draft"}, organization_id=w.course.organization_id)
    enroll(db, draft, w.S)
    db.commit()
    for course in (other, taught, left, draft):
        for tail in ("grades", "announcements"):
            res = await api.call(parent, "GET", f"{LINKS}/{link_id}/courses/{course.id}/{tail}")
            assert res.status_code == 404 and code(res) == "course_not_found", (course.title, tail)
    ids = [c["id"] for c in (await api.call(parent, "GET", f"{LINKS}/{link_id}/courses")).json()["items"]]
    assert ids == [w.cid]
    res = await api.call(parent, "GET", f"{LINKS}/{link_id}/courses/{uuid.uuid4()}/grades")
    assert res.status_code == 404


async def test_courses_are_paged(api, db):
    w = world(db)
    w.S.age_band = "14_17"
    parent = person(db)
    db.commit()
    link_id = await link(api, parent, w.S)
    second = make_course(db, w.O, title={"en": "Second"}, organization_id=w.course.organization_id)
    set_status(db, second, "published")
    enroll(db, second, w.S)
    first = (await api.call(parent, "GET", f"{LINKS}/{link_id}/courses", params={"limit": 1})).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    rest = (await api.call(parent, "GET", f"{LINKS}/{link_id}/courses",
                           params={"limit": 1, "cursor": first["next_cursor"]})).json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    assert {first["items"][0]["id"], rest["items"][0]["id"]} == {w.cid, str(second.id)}


async def test_a_parent_of_two_children_sees_each_only_through_its_link(api, db):
    w = world(db)
    w.S.age_band = w.S2.age_band = "14_17"
    parent = person(db)
    db.commit()
    first, second = await link(api, parent, w.S), await link(api, parent, w.S2)
    a = make_assignment(db, w.course, w.O)
    graded(db, w, a)
    of = {}
    for lid in (first, second):
        of[lid] = (await api.call(parent, "GET", f"{LINKS}/{lid}/courses/{w.cid}/grades")).json()["items"][0]["state"]
    assert of[first] == "graded" and of[second] != "graded"


# ------------------------------------------------------------------ under 14

async def test_consent_lifts_the_gate_and_the_reads(api, db):
    w = world(db)
    kid = w.S
    kid.age_band, kid.consent_state, kid.consent_due_at = "under_14", "pending_guardian", clock.now() - timedelta(days=1)
    parent = person(db)
    parent.locale = "ru"
    db.commit()
    res = await api.call(parent, "POST", LINKS, json={"code": await new_code(api, kid)})
    assert res.status_code == 201 and res.json()["needs_consent"] is True
    link_id = res.json()["id"]
    assert (await api.call(kid, "GET", "/me/home")).status_code == 403
    for path in read_routes(link_id, w.cid):
        res = await api.call(parent, "GET", path)
        assert res.status_code == 403 and code(res) == "consent_required", path

    res = await consent(api, db, parent, link_id)
    assert res.status_code == 201 and res.json()["needs_consent"] is False and res.json()["holds_consent"] is True
    state = fresh(db, kid.id)
    assert state.consent_state == "ok" and state.consent_due_at is None
    row = records(db, kid.id)[0]
    assert (row.kind, row.action, row.source, row.granted_by_id, row.locale) == (
        "guardian_consent", "granted", "guardian", parent.id, "ru")
    assert (await api.call(kid, "GET", "/me/home")).status_code == 200
    for path in read_routes(link_id, w.cid):
        assert (await api.call(parent, "GET", path)).status_code == 200, path
    assert (await api.call(kid, "GET", ME)).json()[0]["holds_consent"] is True


async def test_consent_twice_writes_one_record(api, db):
    kid, parent = child(db), person(db)
    link_id = await link(api, parent, kid)
    assert (await consent(api, db, parent, link_id)).status_code == 201
    assert (await consent(api, db, parent, link_id)).status_code == 201
    assert len(records(db, kid.id)) == 1


async def test_consent_needs_the_current_text_and_a_child(api, db):
    kid, parent = child(db), person(db)
    link_id = await link(api, parent, kid)
    res = await api.call(parent, "POST", f"{LINKS}/{link_id}/consent", json={"policy_version_id": str(uuid.uuid4())})
    assert res.status_code == 422 and code(res) == "policy_not_current"
    assert fresh(db, kid.id).consent_state == "pending_guardian"

    teen = person(db, "14_17")
    teen_link = await link(api, parent, teen)
    res = await consent(api, db, parent, teen_link)
    assert res.status_code == 409 and code(res) == "consent_not_needed"
    assert records(db, teen.id) == []


async def test_withdrawal_blocks_at_once_when_no_holder_is_left(api, db):
    kid, first, second = child(db), person(db), person(db)
    one, two = await link(api, first, kid), await link(api, second, kid)
    assert (await consent(api, db, first, one)).status_code == 201
    assert (await consent(api, db, second, two)).status_code == 201

    assert (await api.call(first, "DELETE", f"{LINKS}/{one}/consent")).status_code == 204
    assert fresh(db, kid.id).consent_state == "ok"  # the second parent still holds it
    links = (await api.call(first, "GET", LINKS)).json()
    assert links[0]["holds_consent"] is False and links[0]["needs_consent"] is False

    assert (await api.call(second, "DELETE", f"{LINKS}/{two}/consent")).status_code == 204
    state = fresh(db, kid.id)
    assert state.consent_state == "pending_guardian"
    assert state.consent_due_at.replace(tzinfo=None) <= clock.now().replace(tzinfo=None)
    assert (await api.call(kid, "GET", "/me/home")).status_code == 403
    res = await api.call(second, "GET", f"{LINKS}/{two}/due")
    assert res.status_code == 403 and code(res) == "consent_required"
    assert [r.action for r in records(db, kid.id)].count("withdrawn") == 2


async def test_withdrawing_nothing_changes_nothing(api, db):
    kid, holder, other = child(db), person(db), person(db)
    held, unheld = await link(api, holder, kid), await link(api, other, kid)
    assert (await consent(api, db, holder, held)).status_code == 201
    assert (await api.call(other, "DELETE", f"{LINKS}/{unheld}/consent")).status_code == 204
    assert (await api.call(other, "DELETE", f"{LINKS}/{unheld}")).status_code == 204
    assert fresh(db, kid.id).consent_state == "ok"
    assert len(records(db, kid.id)) == 1


async def test_a_parent_leaving_withdraws_and_an_old_grant_never_returns(api, db):
    kid, parent = child(db), person(db)
    link_id = await link(api, parent, kid)
    assert (await consent(api, db, parent, link_id)).status_code == 201
    assert (await api.call(parent, "DELETE", f"{LINKS}/{link_id}")).status_code == 204
    state = fresh(db, kid.id)
    assert state.consent_state == "pending_guardian"
    assert [r.action for r in records(db, kid.id)] == ["granted", "withdrawn"]
    again = await link(api, parent, kid)
    row = (await api.call(parent, "GET", LINKS)).json()[0]
    assert row["id"] == again and row["holds_consent"] is False and row["needs_consent"] is True


async def test_a_child_keeps_its_only_holder(api, db):
    kid, holder, other = child(db), person(db), person(db)
    held, unheld = await link(api, holder, kid), await link(api, other, kid)
    assert (await consent(api, db, holder, held)).status_code == 201

    res = await api.call(kid, "DELETE", f"{ME}/{held}")
    assert res.status_code == 409 and code(res) == "guardian_holds_consent"
    assert (await api.call(kid, "DELETE", f"{ME}/{unheld}")).status_code == 204  # not a holder

    third = person(db)
    both = await link(api, third, kid)
    assert (await consent(api, db, third, both)).status_code == 201
    assert (await api.call(kid, "DELETE", f"{ME}/{held}")).status_code == 204  # another holder remains
    assert fresh(db, kid.id).consent_state == "ok"
    assert [r.action for r in records(db, kid.id)].count("withdrawn") == 1


async def test_a_teen_removes_any_parent_and_only_their_own(api, db):
    teen, parent, stranger = person(db, "14_17"), person(db), person(db, "14_17")
    link_id = await link(api, parent, teen)
    res = await api.call(stranger, "DELETE", f"{ME}/{link_id}")
    assert res.status_code == 404 and code(res) == "guardian_link_not_found"
    assert (await api.call(teen, "DELETE", f"{ME}/{link_id}")).status_code == 204
    assert (await api.call(teen, "DELETE", f"{ME}/{link_id}")).status_code == 404
    assert db.scalars(select(GuardianLink)).one().revoked_by_id == teen.id


async def test_losing_the_holder_counts_holders_not_links(api, db):
    """A parent who never consented does not keep a child's consent alive when the holder's account goes."""
    kid, holder, other = child(db), person(db), person(db)
    held = await link(api, holder, kid)
    await link(api, other, kid)
    assert (await consent(api, db, holder, held)).status_code == 201
    anonymize_user(db, holder.id, actor_id=other.id)
    db.commit()
    state = fresh(db, kid.id)
    assert state.consent_state == "pending_guardian"
    due = state.consent_due_at.replace(tzinfo=None) - clock.now().replace(tzinfo=None)
    assert timedelta(days=29) < due <= timedelta(days=30)  # an account deletion gives the grace period


# ------------------------------------------------------------------ delete request

async def test_only_the_holder_of_a_child_can_ask_to_delete(api, db):
    kid, holder, other = child(db), person(db), person(db)
    held, unheld = await link(api, holder, kid), await link(api, other, kid)
    res = await api.call(holder, "POST", f"{LINKS}/{held}/delete-request")
    assert res.status_code == 403 and code(res) == "guardian_not_holder"
    assert (await consent(api, db, holder, held)).status_code == 201

    res = await api.call(other, "POST", f"{LINKS}/{unheld}/delete-request")
    assert res.status_code == 403 and code(res) == "guardian_not_holder"

    res = await api.call(holder, "POST", f"{LINKS}/{held}/delete-request")
    assert res.status_code == 201 and set(res.json()) == {"id", "status", "due_at"}
    row = db.scalars(select(DataRequest)).one()
    assert (row.user_id, row.requested_by_id, row.kind, row.status) == (kid.id, holder.id, "delete", "pending")
    res = await api.call(holder, "POST", f"{LINKS}/{held}/delete-request")
    assert res.status_code == 409 and code(res) == "request_open"


async def test_a_teen_has_no_delete_request_by_a_parent(api, db):
    teen, parent = person(db, "14_17"), person(db)
    link_id = await link(api, parent, teen)
    res = await api.call(parent, "POST", f"{LINKS}/{link_id}/delete-request")
    assert res.status_code == 403 and code(res) == "guardian_not_holder"
    assert db.scalars(select(DataRequest)).all() == []


async def test_auth_me_tells_a_parent_from_the_database(api, db):
    teen, parent = person(db, "14_17"), person(db)
    assert (await api.call(parent, "GET", "/auth/me")).json()["is_guardian"] is False
    await link(api, parent, teen)
    assert (await api.call(parent, "GET", "/auth/me")).json()["is_guardian"] is True
    assert (await api.call(teen, "GET", "/auth/me")).json()["is_guardian"] is False
