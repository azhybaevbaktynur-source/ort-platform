"""Phase 8b S1 (PHASE_8B_DESIGN 5.4, invariant 4, 13): `attempts/display.py::effective_display` resolves the snapshot's
display keys with the course template as fallback. Every ORT attempt resolves to one_per_page / numbered / ort (what
the ORT player and result page render today), through the real seed path and the student API too."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.attempts.display import EffectiveDisplay, effective_display, needs_course
from app.lms.ort.seed import course_id_for, ensure_ort_courses
from tests.lms.factories import make_user
from tests.lms.s3_support import Api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_ort_seed import insert_export

ORT_COURSE = SimpleNamespace(template_key="ort")
GENERAL_COURSE = SimpleNamespace(template_key=None)
ORT_SNAPSHOT_KEYS = {"exam_template_version_id": None, "display_mode": "one_per_page", "passage_display": None,
                     "result_view": None}


def test_ort_resolves_to_numbered_ort_one_per_page():
    assert effective_display(ORT_SNAPSHOT_KEYS, ORT_COURSE) == EffectiveDisplay("one_per_page", "numbered", "ort")
    # snapshots older than 7b carry none of the keys: same answer
    assert effective_display({"navigation": "section_forward_only"}, ORT_COURSE) == EffectiveDisplay(
        "one_per_page", "numbered", "ort")
    assert needs_course(ORT_SNAPSHOT_KEYS) is True


@pytest.mark.parametrize("snapshot, course, expected", [
    (None, None, ("one_per_page", "plain", "general")),
    ({}, GENERAL_COURSE, ("one_per_page", "plain", "general")),
    ({"display_mode": "one_per_page", "passage_display": None, "result_view": None}, GENERAL_COURSE,
     ("one_per_page", "plain", "general")),
    ({"display_mode": "scrolling", "passage_display": "numbered", "result_view": "ort"}, GENERAL_COURSE,
     ("scrolling", "numbered", "ort")),
    # explicit values win over the ORT template's (a general exam inside an ORT course)
    ({"display_mode": "scrolling", "passage_display": "plain", "result_view": "general"}, ORT_COURSE,
     ("scrolling", "plain", "general")),
    # unknown stored values fall back like NULL; an unknown template key is a general course
    ({"display_mode": "paged", "passage_display": "fancy", "result_view": "x"}, ORT_COURSE,
     ("one_per_page", "numbered", "ort")),
    ({}, SimpleNamespace(template_key="retired"), ("one_per_page", "plain", "general")),
])
def test_general_and_fallback_snapshots(snapshot, course, expected):
    assert effective_display(snapshot, course) == EffectiveDisplay(*expected)


def test_needs_course_only_when_a_value_is_inherited():
    assert needs_course({"passage_display": "plain", "result_view": "general"}) is False
    assert needs_course({"passage_display": "plain", "result_view": None}) is True
    assert needs_course(None) is True


def _seed_ort(db) -> Assessment:
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ru", language="ru", keep_images=False)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok and rep.assessments_published == 1, rep
    return db.scalars(select(Assessment).where(Assessment.course_id == course_id_for("ru"))).one()


async def test_ort_attempt_payloads_resolve_through_the_api(db):
    a = _seed_ort(db)
    snap = db.get(AssessmentVersion, a.published_version_id).snapshot
    assert (snap["display_mode"], snap["passage_display"], snap["result_view"]) == ("one_per_page", None, None)
    cid = course_id_for("ru")
    api = Api()
    student = make_user(db)
    assert (await api.call(student, "POST", f"/courses/{cid}/join")).status_code == 200
    st = await api.call(student, "POST", f"/courses/{cid}/assessments/{a.id}/attempts", json={"language": "ru"})
    assert st.status_code == 201, st.text
    assert (st.json()["display_mode"], st.json()["passage_display"]) == ("one_per_page", "numbered")
    tid = st.json()["id"]
    state = (await api.call(student, "GET", f"/attempts/{tid}")).json()
    assert (state["display_mode"], state["passage_display"]) == ("one_per_page", "numbered")
    sub = await api.call(student, "POST", f"/attempts/{tid}/submit", json={})
    assert sub.status_code == 200 and sub.json()["results_available"], sub.text
    assert sub.json()["result"]["result_view"] == "ort"
    result = (await api.call(student, "GET", f"/attempts/{tid}/result")).json()
    assert (result["result_view"], result["passage_display"]) == ("ort", "numbered")
    review = await api.call(student, "GET", f"/attempts/{tid}/review")
    assert review.status_code == 200, review.text
    assert (review.json()["result_view"], review.json()["passage_display"]) == ("ort", "numbered")
