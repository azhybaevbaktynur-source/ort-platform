"""Results policy matrix, key hiding (sentinels) and exact key sets of the student result/review routes."""
import uuid
from datetime import timedelta

import pytest

from app.lms.attempts import grading
from app.lms.core import clock
from tests.lms.factories import enroll, make_course, make_user
from tests.lms.grading_support import KEY_TOKENS, RUBRIC, grading_plan, make_world, new_attempt  # noqa: F401
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("grading_plan")

WRONG = {"sc": {"choice_id": "A"}, "num": {"value": "1"}, "st": {"text": "x"}, "es": {"text": "essay words"}}
T0 = clock.now()

RESULT_KEYS = {"raw_score", "points_possible", "sections", "pending_review", "submitted_at"}
SECTION_KEYS = {"pos", "key", "raw", "possible", "answered", "correct"}
ITEM_KEYS = {"position", "section_pos", "question", "passage", "response", "flagged", "correctness", "score",
             "points", "feedback"}
QUESTION_KEYS = {"id", "type", "language", "stem", "image_url", "points", "data"}


def _submit(db, att, now=None):
    grading.finalize(db, att.id, reason="manual", now=now or clock.now())
    db.commit()


async def _get(api, user, att, what):
    return await api.call(user, "GET", f"/attempts/{att.id}/{what}")


def _texts(*responses):
    return " ".join(r.text for r in responses)


async def test_never_hides_everything_even_after_submit(db, api):
    w = make_world(db, results_policy="never", show_correct=True)
    att = new_attempt(db, w, responses=WRONG)
    _submit(db, att)
    for what in ("result", "review"):
        r = await _get(api, w.student, att, what)
        assert r.status_code == 403 and r.json()["error"]["code"] == "results_not_available"
        assert not any(t in r.text for t in KEY_TOKENS)


async def test_after_submit_before_and_after(db, api):
    w = make_world(db, results_policy="after_submit")
    att = new_attempt(db, w, responses=WRONG)
    for what in ("result", "review"):
        r = await _get(api, w.student, att, what)
        assert r.status_code == 403 and r.json()["error"]["code"] == "results_not_available"
    _submit(db, att)
    res = await _get(api, w.student, att, "result")
    assert res.status_code == 200
    assert (await _get(api, w.student, att, "review")).status_code == 200


async def test_after_close_requires_window_end(db, api, monkeypatch):
    until = T0 + timedelta(hours=1)
    w = make_world(db, results_policy="after_close", available_until=until)
    att = new_attempt(db, w, responses=WRONG)
    _submit(db, att)
    for what in ("result", "review"):
        assert (await _get(api, w.student, att, what)).status_code == 403
    monkeypatch.setattr("app.lms.core.clock.now", lambda: until + timedelta(seconds=1))
    for what in ("result", "review"):
        assert (await _get(api, w.student, att, what)).status_code == 200
    # exactly at the close instant is visible, one second before is not
    monkeypatch.setattr("app.lms.core.clock.now", lambda: until - timedelta(seconds=1))
    assert (await _get(api, w.student, att, "result")).status_code == 403
    monkeypatch.setattr("app.lms.core.clock.now", lambda: until)
    assert (await _get(api, w.student, att, "result")).status_code == 200


@pytest.mark.parametrize("policy,until_delta,visible", [
    ("never", None, False), ("after_submit", None, True),
    ("after_close", 3600, False), ("after_close", -3600, True),
])
@pytest.mark.parametrize("show", [False, True])
async def test_policy_matrix_and_sentinels(db, api, policy, until_delta, visible, show):
    until = None if until_delta is None else T0 + timedelta(seconds=until_delta)
    w = make_world(db, results_policy=policy, show_correct=show, available_until=until)
    att = new_attempt(db, w, responses=WRONG)
    _submit(db, att)
    res = await _get(api, w.student, att, "result")
    rev = await _get(api, w.student, att, "review")
    assert (res.status_code == 200) == visible and (rev.status_code == 200) == visible
    text = _texts(res, rev)
    assert RUBRIC not in text  # never, in any case
    if not (visible and show):
        assert not any(t in text for t in KEY_TOKENS), text
        if visible:
            for item in rev.json()["items"]:
                assert "key" not in item and "explanation" not in item
    if visible and show:
        items = rev.json()["items"]
        assert all("key" in i and "explanation" in i for i in items)
        assert "SENTINEL_EXPLANATION" in text and "987654" in text


async def test_exact_key_sets(db, api):
    w = make_world(db, show_correct=False)
    att = new_attempt(db, w, responses=WRONG)
    _submit(db, att)
    res = (await _get(api, w.student, att, "result")).json()
    assert set(res) == RESULT_KEYS and all(set(s) == SECTION_KEYS for s in res["sections"])
    items = (await _get(api, w.student, att, "review")).json()["items"]
    assert set(items[0]) == ITEM_KEYS and set(items[0]["question"]) == QUESTION_KEYS
    assert [i["position"] for i in items] == list(range(1, 8))
    w2 = make_world(db, show_correct=True)
    att2 = new_attempt(db, w2, responses=WRONG)
    _submit(db, att2)
    items = (await _get(api, w2.student, att2, "review")).json()["items"]
    assert set(items[0]) == ITEM_KEYS | {"key", "explanation"}
    assert items[0]["key"] == {"correct": "B"}


async def test_result_values_and_review_scores(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses={"sc": {"choice_id": "B"}, "es": {"text": "t"}})
    _submit(db, att)
    res = (await _get(api, w.student, att, "result")).json()
    assert res["raw_score"] == "2.00" and res["points_possible"] == "22.00" and res["pending_review"] == 1
    assert [s["key"] for s in res["sections"]] == ["math", "free"]
    items = {i["position"]: i for i in (await _get(api, w.student, att, "review")).json()["items"]}
    assert items[1]["correctness"] == "correct" and items[1]["score"] == "2.00"
    assert items[7]["correctness"] == "pending" and items[7]["score"] is None


async def test_choice_order_applied_in_review(db, api):
    from sqlalchemy import update

    from app.lms.attempts.models import AttemptItem

    w = make_world(db)
    att = new_attempt(db, w, responses=WRONG)
    db.execute(update(AttemptItem).where(AttemptItem.attempt_id == att.id, AttemptItem.position == 1)
               .values(choice_order=["C", "A", "B"]))
    db.commit()
    _submit(db, att)
    items = (await _get(api, w.student, att, "review")).json()["items"]
    assert [c["id"] for c in items[0]["question"]["data"]["choices"]] == ["C", "A", "B"]


async def test_in_progress_is_403_not_leaky(db, api):
    w = make_world(db, show_correct=True)
    att = new_attempt(db, w, responses=WRONG)
    for what in ("result", "review"):
        r = await _get(api, w.student, att, what)
        assert r.status_code == 403 and not any(t in r.text for t in KEY_TOKENS)


async def test_expired_attempt_is_finalized_lazily_on_read(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=WRONG, deadline_at=clock.now() - timedelta(minutes=5))
    r = await _get(api, w.student, att, "result")
    assert r.status_code == 200
    from tests.lms.grading_support import reload

    a = reload(db, att)
    assert a.status == "needs_review" and a.submit_reason == "timeout"


async def test_preview_visible_to_staff_owner_after_submit(db, api):
    w = make_world(db, results_policy="never")
    att = new_attempt(db, w, w.teacher, responses=WRONG, preview=True, attempt_no=None)
    _submit(db, att)
    assert (await _get(api, w.teacher, att, "result")).status_code == 200
    rev = await _get(api, w.teacher, att, "review")
    # a staff preview sees keys even with show_correct_answers off (attempts router: keys for previews)
    assert rev.status_code == 200 and "SENTINEL_EXPLANATION" in rev.text


# ------------------------------------------------------------------ isolation: every miss is the same 404

async def test_other_users_and_missing_attempts_are_identical_404(db, api):
    w = make_world(db, show_correct=True)
    att = new_attempt(db, w, responses=WRONG)
    _submit(db, att)
    other = make_user(db)
    enroll(db, w.course, other)
    outsider = make_user(db)
    unknown = uuid.uuid4()
    for what in ("result", "review"):
        miss = await api.call(w.student, "GET", f"/attempts/{unknown}/{what}")
        assert miss.status_code == 404 and miss.json()["error"]["code"] == "attempt_not_found"
        for who in (other, outsider, w.teacher):  # teachers use the staff routes, not the student ones
            r = await _get(api, who, att, what)
            assert r.status_code == 404 and r.json() == miss.json(), (what, r.text)
            assert not any(t in r.text for t in KEY_TOKENS)


async def test_removed_enrollment_cannot_read(db, api):
    from app.lms.enrollments.models import Enrollment

    w = make_world(db)
    att = new_attempt(db, w, responses=WRONG)
    _submit(db, att)
    enr = db.query(Enrollment).filter_by(course_id=w.course.id, user_id=w.student.id).one()
    enr.state = "removed"
    db.commit()
    assert (await _get(api, w.student, att, "result")).status_code == 404


async def test_concluded_course_results_still_readable(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=WRONG)
    _submit(db, att)
    w.course.status = "concluded"
    db.commit()
    assert (await _get(api, w.student, att, "result")).status_code == 200


async def test_unauthenticated(db, api):
    assert (await api.call(None, "GET", f"/attempts/{uuid.uuid4()}/result")).status_code == 401
