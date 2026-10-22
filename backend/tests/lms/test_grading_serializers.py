"""7.3 Serializer contracts of the student-facing grade payloads (result, review, attempts/mine, grades/mine,
lobby, course grading GET) and the staff attempt extension: exact key sets per state, release gating (P4-11),
results policy x show_correct_answers, previews inline, void rendering, sentinels never present."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.lms.attempts import grading
from app.lms.attempts.models import Attempt
from app.lms.core import clock
from app.lms.core.models import utcnow
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import AttemptGrade, Submission
from app.lms.grading.seeds import ORT_MAIN_V1_ID, PERCENT_V1_ID
from tests.lms.factories import enroll, make_submission, make_user
from tests.lms.gradebook_support import SENTINEL_EVENT, SENTINEL_REASON, add_event, no_scored_hooks  # noqa: F401
from tests.lms.grading_support import CORRECT, grading_plan, make_world, new_attempt  # noqa: F401
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("grading_plan", "no_scored_hooks")

T0 = clock.now()
NAMES = ["sc", "tf"]  # 3 points, auto-graded only -> status graded
RESULT_KEYS = {"raw_score", "points_possible", "sections", "pending_review", "submitted_at", "grade"}
GRADE_KEYS = {"scheme_type", "scale_min", "scale_max", "display_value", "label", "percentile", "passed", "thresholds",
              "sections", "is_kept", "released", "labels"}
GRADED_KEYS = {"assessment_id", "title", "state", "display_value", "label", "percentile", "passed", "thresholds",
               "effective_points", "points_possible", "late_deduction", "released_at", "kept_attempt_id", "due_at"}
NO_NUMBER_KEYS = {"assessment_id", "title", "state", "due_at"}
FORBIDDEN = ("override_reason", "submission_id", "user_id", "params", "events", "enrollment_id", SENTINEL_REASON,
             SENTINEL_EVENT, "segments")


def world(db, *, scheme=PERCENT_V1_ID, release="auto", **kw):
    w = make_world(db, names=NAMES, **kw)
    w.assessment.grading_scheme_version_id = scheme
    w.assessment.grade_release = release
    db.commit()
    return w


def submit(db, att):
    grading.finalize(db, att.id, reason="manual", now=clock.now())
    db.commit()
    db.expire_all()
    return db.get(Attempt, att.id)


def store(db, w, att, *, released=True, state="graded", display=Decimal("66.67"), sections=None, sub=None):
    """What slice G2 would write for this attempt (factories only)."""
    db.add(AttemptGrade(attempt_id=att.id, scheme_version_id=w.assessment.grading_scheme_version_id,
                        display_value=display, label=None, percentile=None, passed=None, thresholds={},
                        sections=sections, computed_at=utcnow()))
    db.commit()
    if sub is None:
        enr = db.execute(select(Enrollment).where(Enrollment.id == att.enrollment_id)).scalar_one()
        sub = make_submission(db, w.assessment, enr, state=state, kept_attempt_id=att.id, attempts_counted=1,
                              raw_points=att.raw_score, points_possible=att.points_possible,
                              effective_points=att.raw_score, scheme_version_id=PERCENT_V1_ID, display_value=display,
                              thresholds={}, released_at=utcnow() if released else None,
                              override_reason=SENTINEL_REASON)
        add_event(db, sub, w.teacher)
    return sub


async def get(api, user, path):
    return await api.call(user, "GET", path)


def assert_clean(text):
    for f in FORBIDDEN:
        assert f not in text, f


# ------------------------------------------------------------------ result / mine / review

async def test_result_grade_when_released(db, api):
    w = world(db)
    att = submit(db, new_attempt(db, w, responses={"sc": CORRECT["sc"]}))
    store(db, w, att)
    r = await get(api, w.student, f"/attempts/{att.id}/result")
    assert r.status_code == 200, r.text
    res = r.json()
    assert set(res) == RESULT_KEYS and set(res["grade"]) == GRADE_KEYS
    g = res["grade"]
    assert g["scheme_type"] == "percent" and Decimal(g["display_value"]) == Decimal("66.67")
    assert g["is_kept"] is True and g["released"] is True and g["sections"] is None
    assert_clean(r.text)
    mine = await get(api, w.student, f"/courses/{w.course.id}/assessments/{w.assessment.id}/attempts/mine")
    assert mine.json()[0]["result"]["grade"]["display_value"] == g["display_value"]
    assert_clean(mine.text)
    rev = await get(api, w.student, f"/attempts/{att.id}/review")
    assert rev.status_code == 200 and "grade" not in rev.json()
    assert_clean(rev.text)


async def test_result_grade_hidden_until_manual_release(db, api):
    w = world(db, release="manual")
    att = submit(db, new_attempt(db, w, responses=CORRECT))
    sub = store(db, w, att, released=False)
    res = (await get(api, w.student, f"/attempts/{att.id}/result")).json()
    assert set(res) == RESULT_KEYS and res["grade"] is None
    mine = await get(api, w.student, f"/courses/{w.course.id}/assessments/{w.assessment.id}/attempts/mine")
    assert mine.json()[0]["result"]["grade"] is None
    item = (await get(api, w.student, f"/courses/{w.course.id}/grades/mine")).json()["items"][0]
    assert item["state"] == "pending" and set(item) == NO_NUMBER_KEYS
    sub = db.get(Submission, sub.id)
    sub.released_at = utcnow()
    db.commit()
    res = (await get(api, w.student, f"/attempts/{att.id}/result")).json()
    assert res["grade"]["released"] is True
    item = (await get(api, w.student, f"/courses/{w.course.id}/grades/mine")).json()["items"][0]
    assert item["state"] == "graded" and set(item) == GRADED_KEYS


async def test_ort_sections_and_thresholds_shape(db, api):
    w = world(db, scheme=ORT_MAIN_V1_ID)
    att = submit(db, new_attempt(db, w, responses=CORRECT))
    store(db, w, att, display=Decimal("245"), sections=[{"pos": 1, "display_value": "245.00"}])
    db.execute(AttemptGrade.__table__.update().where(AttemptGrade.attempt_id == att.id).values(
        thresholds={"golden_certificate": True}, percentile=Decimal("99.9")))
    db.commit()
    g = (await get(api, w.student, f"/attempts/{att.id}/result")).json()["grade"]
    assert g["scheme_type"] == "piecewise_curve" and Decimal(g["scale_max"]) == 245
    assert g["thresholds"] == {"golden_certificate": True} and Decimal(g["percentile"]) == Decimal("99.9")
    assert g["sections"] == [{"pos": 1, "display_value": "245.00"}]


@pytest.mark.parametrize("policy,until_delta,state", [
    ("never", None, "hidden"), ("after_submit", None, "graded"),
    ("after_close", 3600, "pending"), ("after_close", -3600, "graded"),
])
@pytest.mark.parametrize("show", [False, True])
async def test_policy_matrix(db, api, policy, until_delta, state, show):
    until = None if until_delta is None else T0 + timedelta(seconds=until_delta)
    w = world(db, results_policy=policy, show_correct=show, available_until=until)
    att = submit(db, new_attempt(db, w, responses=CORRECT))
    store(db, w, att)
    r = await get(api, w.student, f"/attempts/{att.id}/result")
    assert (r.status_code == 200) == (state == "graded")
    if r.status_code == 200:
        assert r.json()["grade"] is not None
    else:
        assert "display_value" not in r.text
    mine = await get(api, w.student, f"/courses/{w.course.id}/grades/mine")
    item = mine.json()["items"][0]
    assert item["state"] == state
    assert set(item) == (GRADED_KEYS if state == "graded" else NO_NUMBER_KEYS)
    if state != "graded":
        assert mine.json()["total"] is None
    assert_clean(mine.text)


async def test_after_close_with_open_attempt_stays_pending(db, api, monkeypatch):
    until = T0 + timedelta(hours=1)
    w = world(db, results_policy="after_close", available_until=until)
    att = submit(db, new_attempt(db, w, responses=CORRECT))
    store(db, w, att)
    other = make_user(db)
    enroll(db, w.course, other)
    new_attempt(db, w, other)  # still in progress
    monkeypatch.setattr("app.lms.core.clock.now",
                        lambda: until + timedelta(seconds=settings.ATTEMPT_GRACE_S + 1))
    item = (await get(api, w.student, f"/courses/{w.course.id}/grades/mine")).json()["items"][0]
    assert item["state"] == "pending"


async def test_my_grades_states_and_total(db, api):
    w = world(db)
    from tests.lms.factories import make_assessment
    from tests.lms.gradebook_support import publish

    graded = w.assessment
    att = submit(db, new_attempt(db, w, responses=CORRECT))
    store(db, w, att, display=Decimal("100.00"))
    enr = db.execute(select(Enrollment).where(Enrollment.id == att.enrollment_id)).scalar_one()
    excused = make_assessment(db, w.course, w.teacher, title={"en": "Excused"})
    publish(db, excused, w.teacher, 5)
    make_submission(db, excused, enr, state="excused", raw_points=Decimal("1"), points_possible=Decimal("5"),
                    effective_points=Decimal("1"), display_value=Decimal("20"), released_at=utcnow())
    review = make_assessment(db, w.course, w.teacher, title={"en": "Review"})
    publish(db, review, w.teacher, 5)
    make_submission(db, review, enr, state="pending_review", released_at=utcnow(), display_value=Decimal("1"))
    missing = make_assessment(db, w.course, w.teacher, title={"en": "Missing"}, due_at=T0)
    publish(db, missing, w.teacher, 5)
    r = await get(api, w.student, f"/courses/{w.course.id}/grades/mine")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"total", "scheme", "items"}
    states = {i["assessment_id"]: i for i in body["items"]}
    assert states[str(graded.id)]["state"] == "graded" and set(states[str(graded.id)]) == GRADED_KEYS
    for a, st in ((excused, "excused"), (review, "pending"), (missing, "missing")):
        assert states[str(a.id)]["state"] == st and set(states[str(a.id)]) == NO_NUMBER_KEYS
    assert states[str(missing.id)]["due_at"] is not None
    assert set(body["total"]) == {"percent", "display_value", "label", "passed"}
    assert Decimal(body["total"]["percent"]) == Decimal("100.00") and body["scheme"] is None
    assert_clean(r.text)


async def test_course_scheme_student_ref_has_no_params(db, api):
    w = world(db)
    w.course.grading_scheme_version_id = ORT_MAIN_V1_ID
    db.commit()
    r = await get(api, w.student, f"/courses/{w.course.id}/grades/mine")
    assert set(r.json()["scheme"]) == {"type", "scale_min", "scale_max", "title", "labels"}
    assert_clean(r.text)
    g = await get(api, w.student, f"/courses/{w.course.id}/grading")
    assert g.status_code == 200 and set(g.json()) <= {"total_mode", "scheme"}
    assert_clean(g.text)
    lobby = await get(api, w.student, f"/courses/{w.course.id}/assessments/{w.assessment.id}")
    assert lobby.status_code == 200
    assert_clean(lobby.text)


# ------------------------------------------------------------------ previews and void

async def test_preview_grade_inline(db, api):
    w = world(db)
    att = submit(db, new_attempt(db, w, w.teacher, responses={"sc": CORRECT["sc"]}, preview=True, attempt_no=None))
    r = await get(api, w.teacher, f"/attempts/{att.id}/result")
    assert r.status_code == 200, r.text
    g = r.json()["grade"]
    assert set(g) == GRADE_KEYS and Decimal(g["display_value"]) == Decimal("66.67")  # 2 / 3 with the percent scheme
    assert g["is_kept"] is False and g["released"] is True
    assert db.execute(select(AttemptGrade).where(AttemptGrade.attempt_id == att.id)).first() is None
    w.assessment = db.get(type(w.assessment), w.assessment.id)
    w.assessment.grading_scheme_version_id = None
    db.commit()
    assert (await get(api, w.teacher, f"/attempts/{att.id}/result")).json()["grade"] is None


async def test_void_attempt_renders_status_only(db, api):
    w = world(db)
    att = submit(db, new_attempt(db, w, responses=CORRECT))
    store(db, w, att)
    db.get(Attempt, att.id).status = "void"
    db.commit()
    r = await get(api, w.student, f"/attempts/{att.id}/result")
    assert r.status_code == 200 and r.json() == {"status": "void"}
    # every other student read hides a voided attempt like any attempt the caller cannot see (S4)
    for path in ("review", "content", ""):
        rev = await get(api, w.student, f"/attempts/{att.id}/{path}".rstrip("/"))
        assert rev.status_code == 404 and rev.json()["error"]["code"] == "attempt_not_found", (path, rev.text)
    # another user's void attempt stays a 404
    other = make_user(db)
    enroll(db, w.course, other)
    r = await get(api, other, f"/attempts/{att.id}/result")
    assert r.status_code == 404


# ------------------------------------------------------------------ staff extension

async def test_staff_attempt_detail_grade_always_and_submission_id(db, api):
    w = world(db, release="manual")
    att = submit(db, new_attempt(db, w, responses=CORRECT))
    sub = store(db, w, att, released=False)
    r = await get(api, w.teacher, f"/courses/{w.course.id}/attempts/{att.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["submission_id"] == str(sub.id)
    assert set(body["grade"]) == GRADE_KEYS and body["grade"]["released"] is False and body["grade"]["is_kept"] is True
    lst = await get(api, w.teacher, f"/courses/{w.course.id}/assessments/{w.assessment.id}/attempts")
    assert "grade" in lst.json()["items"][0]
