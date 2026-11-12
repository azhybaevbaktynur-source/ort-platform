"""Step 3a S1 (STUDENT_IA_DESIGN 4, 6.3): `POST /catalog/choose {course_ids}` joins several listed, published, open
platform courses at once through the join service (events, enrollment limit, the teacher refusal), answers
`{joined, skipped}`; people who teach 403 `teacher_cannot_enroll`, a test student 403, a closed / private / teacher
course 422 `course_not_choosable` with nothing joined, at most 20 ids, 5 requests a minute, the consent gate applies."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.core.route_inventory import ROUTE_POLICIES
from app.lms.core import clock
from app.lms.core.models import utcnow
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import platform_org_id
from tests.lms.factories import enroll, make_course, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

PATH = "/catalog/choose"


def code(res) -> str:
    return (res.json().get("error") or {}).get("code")


def platform_course(db, owner, title="ОРТ", *, family="ort", subject=None, **kw):
    fields = dict(title={"ru": title}, languages=["ru"], default_language="ru", status="published",
                  visibility="catalog", enrollment_mode="open", organization_id=platform_org_id(),
                  published_at=utcnow(), exam_family=family, subject=subject)
    fields.update(kw)
    return make_course(db, owner, **fields)


def setup(db):
    ensure_platform_org(db.connection())
    db.commit()
    admin = make_user(db, platform_admin=True, teacher_status="approved")
    return admin, make_user(db)


async def choose(api, user, ids):
    return await api.call(user, "POST", PATH, json={"course_ids": [str(i) for i in ids]})


def active(db, course, user) -> bool:
    return db.execute(select(Enrollment.id).where(Enrollment.course_id == course.id, Enrollment.user_id == user.id,
                                                  Enrollment.state == "active", Enrollment.role == "student")
                      ).first() is not None


def test_route_policy_declared():
    assert ROUTE_POLICIES[("POST", "/api/v1/catalog/choose")] == "authenticated+ratelimit"


async def test_joins_and_is_idempotent(db, api):
    admin, s = setup(db)
    main = platform_course(db, admin, "ОРТ (рус)")
    math = platform_course(db, admin, "Математика", subject="math")
    r = await choose(api, s, [main.id, math.id, main.id])  # a repeated id counts once
    assert r.status_code == 200, r.text
    assert r.json() == {"joined": [str(main.id), str(math.id)], "skipped": []}
    assert active(db, main, s) and active(db, math, s)
    r = await choose(api, s, [math.id, main.id])
    assert r.json() == {"joined": [], "skipped": [str(math.id), str(main.id)]}
    events = db.execute(select(func.count()).select_from(EnrollmentEvent).join(
        Enrollment, Enrollment.id == EnrollmentEvent.enrollment_id).where(
        Enrollment.user_id == s.id, EnrollmentEvent.event == "joined")).scalar()
    assert events == 2  # the join service's own events, once each


async def test_a_left_course_is_joined_again(db, api):
    admin, s = setup(db)
    main = platform_course(db, admin)
    enr = enroll(db, main, s)
    enr.state = "removed"
    db.commit()
    r = await choose(api, s, [main.id])
    assert r.json() == {"joined": [str(main.id)], "skipped": []}
    db.expire_all()
    assert active(db, main, s)


async def test_only_open_listed_published_platform_courses(db, api):
    admin, s = setup(db)
    good = platform_course(db, admin, "Good")
    teacher = make_user(db, teacher_status="approved")
    refused = [
        platform_course(db, admin, "Code", enrollment_mode="invite_code"),
        platform_course(db, admin, "Closed", enrollment_mode="closed"),
        platform_course(db, admin, "Private", visibility="private"),
        platform_course(db, admin, "Draft", status="draft", published_at=None),
        platform_course(db, admin, "Unlisted", unlisted_by_admin_at=utcnow()),
        make_course(db, teacher, title={"en": "Teacher's"}, status="published", visibility="catalog",
                    enrollment_mode="open", published_at=utcnow()),
    ]
    gone = platform_course(db, admin, "Deleted")
    gone.deleted_at = utcnow()
    db.commit()
    for bad in [*refused, gone, None]:
        user = make_user(db)  # one request each (5 a minute)
        bad_id = bad.id if bad is not None else uuid.uuid4()
        r = await choose(api, user, [good.id, bad_id])
        assert r.status_code == 422 and code(r) == "course_not_choosable", (bad_id, r.text)
        assert [d["course_id"] for d in r.json()["error"]["details"]] == [str(bad_id)]
        assert not active(db, good, user)  # nothing joined by a refused request
    assert (await choose(api, s, [good.id])).status_code == 200


async def test_full_course_stops_the_request_after_the_joined_ones(db, api):
    admin, s = setup(db)
    first = platform_course(db, admin, "First")
    full = platform_course(db, admin, "Full", enrollment_limit=1)
    enroll(db, full, make_user(db))
    r = await choose(api, s, [first.id, full.id])
    assert r.status_code == 422 and code(r) == "course_not_choosable", r.text
    details = r.json()["error"]["details"]
    assert details[0]["course_id"] == str(full.id) and details[1]["joined"] == [str(first.id)]
    db.expire_all()
    assert active(db, first, s) and not active(db, full, s)


async def test_people_who_teach_are_refused(db, api):
    admin, _ = setup(db)
    main = platform_course(db, admin)
    for user in (make_user(db, teacher_status="approved"), admin):
        r = await choose(api, user, [main.id])
        assert r.status_code == 403 and code(r) == "teacher_cannot_enroll", r.text
        assert not active(db, main, user)
    # refused before any course is read: an unknown id answers the same
    r = await choose(api, make_user(db, teacher_status="approved"), [uuid.uuid4()])
    assert r.status_code == 403 and code(r) == "teacher_cannot_enroll"


async def test_test_student_is_refused(db, api):
    admin, _ = setup(db)
    main = platform_course(db, admin)
    tester = make_user(db)
    tester.is_test_student = True
    enroll(db, main, tester).is_test_student = True
    db.commit()
    other = platform_course(db, admin, "Other")
    r = await choose(api, tester, [other.id])
    assert r.status_code == 403 and code(r) == "test_student_forbidden", r.text
    assert not active(db, other, tester)


async def test_consent_gate_applies(db, api):
    admin, s = setup(db)
    main = platform_course(db, admin)
    s.consent_state, s.age_band = "pending_guardian", "under_14"
    s.consent_due_at = clock.now() - timedelta(minutes=1)
    db.commit()
    r = await choose(api, s, [main.id])
    assert r.status_code == 403 and code(r) == "consent_required", r.text
    assert not active(db, main, s)


async def test_limits(db, api):
    admin, s = setup(db)
    main = platform_course(db, admin)
    r = await api.call(s, "POST", PATH, json={"course_ids": [str(uuid.uuid4()) for _ in range(21)]})
    assert r.status_code == 422, r.text  # at most 20 ids
    r = await api.call(s, "POST", PATH, json={"course_ids": []})
    assert r.status_code == 422
    r = await api.call(s, "POST", PATH, json={"course_ids": [str(main.id)], "role": "teacher"})
    assert r.status_code == 422  # unknown fields
    other = make_user(db)
    for _ in range(5):
        assert (await choose(api, other, [main.id])).status_code == 200
    r = await choose(api, other, [main.id])
    assert r.status_code == 429, r.text  # 5 a minute per user
    assert (await choose(api, s, [main.id])).status_code == 200  # another user's window
