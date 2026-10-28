"""Phase 7b S2 `instantiate` (PHASE_7B_DESIGN 5.3): the rows equal a hand-built assessment, the quiz assignment is
written in the same transaction, parameters, scrolling allowed since 8b (P7B-1 lifted), exclusivity with `preset`, pinned
versions, and the 7a `/assignments` path with its `later` settings."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.lms.assessments.models import Assessment, AssessmentSection
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment
from app.lms.assignments.sync import mirror_mismatches
from app.lms.core.models import utcnow
from app.lms.exam_templates.models import ExamTemplateVersion
from app.lms.grading.seeds import ORT_MAIN_V1_ID
from tests.lms.assessment_support import mk, section
from tests.lms.exam_template_support import general_spec, ort_subject_spec
from tests.lms.factories import make_category
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_templates_api import T, create_from, create_t, publish_t, published_template, tworld

A_COLS = ("preset", "status", "navigation", "time_limit_s", "allowed_attempts", "score_policy", "results_policy",
          "show_correct_answers", "shuffle_items", "shuffle_choices", "grading_scheme_version_id", "display_mode",
          "passage_display", "result_view", "languages")
S_COLS = ("position", "key", "title", "instructions", "time_limit_s", "rules")


def rows(db, aid):
    a = db.get(Assessment, uuid.UUID(aid))
    secs = db.execute(select(AssessmentSection).where(AssessmentSection.assessment_id == a.id)
                      .order_by(AssessmentSection.position)).scalars().all()
    return tuple(getattr(a, c) for c in A_COLS), [tuple(getattr(s, c) for c in S_COLS) for s in secs]


SPEC = general_spec(
    navigation="section_forward_only",
    defaults={"time_limit_s": 5400, "allowed_attempts": 3, "score_policy": "average", "results_policy": "after_close",
              "show_correct_answers": True, "shuffle_items": True, "shuffle_choices": False},
    sections=[
        {"key": "part_a", "title": {"en": "Part A", "ru": "Часть A"}, "instructions": {"en": "Choose one"},
         "time_limit_s": 1800, "allowed_types": ["single_choice", "true_false"], "allow_passages": False,
         "min_items": 2, "max_items": 10},
        {"key": None, "title": {"en": "Part B"}, "time_limit_s": 3600, "allowed_types": ["essay"],
         "allow_passages": True},
    ],
    scoring={"grading_scheme_version_id": str(ORT_MAIN_V1_ID)}, result_view="general", passage_display="numbered",
)


async def test_instantiate_equals_hand_built_rows(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=SPEC)
    a = await create_from(api, w.TA, w.cid, t["id"], title={"en": "Exam"}, languages=["en", "ru"],
                          description={"en": "d"})
    # the same structure through the builder, by hand
    h = await mk(api, w.TA, w.cid, title={"en": "Exam"}, languages=["en", "ru"])
    upd = await api.call(w.TA, "PATCH", f"/courses/{w.cid}/assessments/{h['id']}", json={
        "draft_rev": h["draft_rev"], "navigation": "section_forward_only", "time_limit_s": 5400, "allowed_attempts": 3,
        "score_policy": "average", "results_policy": "after_close", "show_correct_answers": True,
        "shuffle_items": True, "shuffle_choices": False, "grading_scheme_version_id": str(ORT_MAIN_V1_ID)})
    assert upd.status_code == 200, upd.text
    await section(api, w.TA, w.cid, h["id"], key="part_a", title={"en": "Part A", "ru": "Часть A"},
                  instructions={"en": "Choose one"}, time_limit_s=1800,
                  rules={"allowed_types": ["single_choice", "true_false"], "allow_passages": False, "min_items": 2,
                         "max_items": 10})
    await section(api, w.TA, w.cid, h["id"], title={"en": "Part B"}, time_limit_s=3600,
                  rules={"allowed_types": ["essay"], "allow_passages": True})
    hand = db.get(Assessment, uuid.UUID(h["id"]))
    hand.result_view, hand.passage_display = "general", "numbered"   # not editable through the builder in 7b
    db.commit()
    assert rows(db, a["id"]) == rows(db, h["id"])
    row = db.get(Assessment, uuid.UUID(a["id"]))
    assert row.exam_template_version_id == uuid.UUID(t["current_version_id"]) and row.preset == "none"
    assert row.structure_locked is False and row.description == {"en": "d"} and row.draft_rev == 1
    # the quiz assignment exists in the same transaction, mirrored
    asg = db.get(Assignment, assignment_id_for(row.id))
    assert asg is not None and asg.kind == "quiz" and asg.created_by_id == w.TA.id
    assert mirror_mismatches(db, row) == {}
    # staff out: template reference, display fields, scheme
    assert a["exam_template"]["template_id"] == t["id"] and a["exam_template"]["locked_fields"] == []
    assert (a["display_mode"], a["passage_display"], a["result_view"]) == ("one_per_page", "numbered", "general")
    assert a["scheme"]["id"] == str(ORT_MAIN_V1_ID) and a["sections"][0]["rules"]["min_items"] == 2
    # a locked template copies its lock
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/lock")).status_code == 200
    b = await create_from(api, w.TA, w.cid, t["id"])
    assert b["structure_locked"] is True and db.get(Assessment, uuid.UUID(b["id"])).structure_locked is True


async def test_parameters(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=ort_subject_spec())
    body = await create_from(api, w.TA, w.cid, t["id"], status=422)
    assert body["error"]["code"] == "parameter_missing" and body["error"]["details"][0]["loc"] == ["parameters", "subject"]
    body = await create_from(api, w.TA, w.cid, t["id"], parameters={"subject": "math"}, status=422)
    assert body["error"]["code"] == "parameter_invalid"
    body = await create_from(api, w.TA, w.cid, t["id"], parameters={"subject": "physics", "x": "y"}, status=422)
    assert body["error"]["code"] == "parameter_invalid"
    assert db.execute(select(Assessment)).first() is None
    a = await create_from(api, w.TA, w.cid, t["id"], parameters={"subject": "physics"})
    assert [s["key"] for s in a["sections"]] == ["physics"] and a["sections"][0]["time_limit_s"] == 3600
    assert a["navigation"] == "section_forward_only" and a["show_correct_answers"] is True


async def test_refusals(db, api):
    w = tworld(db)
    # Phase 8b S1: the scrolling display mode is built; instantiate copies it (P7B-1 lifted)
    t = await published_template(api, w.PA, spec=general_spec(display_mode="scrolling"))
    scrolling = await create_from(api, w.TA, w.cid, t["id"])
    assert scrolling["display_mode"] == "scrolling"
    assert db.get(Assessment, uuid.UUID(scrolling["id"])).display_mode == "scrolling"
    before = {r.id for r in db.execute(select(Assessment)).scalars()}
    ok = await published_template(api, w.PA)
    body = await create_from(api, w.TA, w.cid, ok["id"], preset="ort_main", status=422)
    assert body["error"]["code"] == "preset_template_exclusive"
    body = await create_from(api, w.TA, w.cid, ok["id"], languages=["ky"], status=422)
    assert body["error"]["code"] == "languages_not_in_course"
    body = await create_from(api, w.TA, w.cid, ok["id"], parameters={"subject": "physics"}, status=422)
    assert body["error"]["code"] == "parameter_invalid"                 # the template declares no parameters
    assert {r.id for r in db.execute(select(Assessment)).scalars()} == before
    assert len(db.execute(select(Assignment)).scalars().all()) == 1     # only the scrolling quiz's assignment


async def test_pinned_version_and_version_template_mismatch(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA)
    v1 = t["current_version_id"]
    assert (await api.call(w.PA, "PATCH", f"{T}/{t['id']}", json={
        "draft_rev": t["draft_rev"], "draft_spec": general_spec(navigation="section_forward_only")})).status_code == 200
    v2 = (await publish_t(api, w.PA, t["id"])).json()["version"]["id"]
    latest = await create_from(api, w.TA, w.cid, t["id"])
    pinned = await create_from(api, w.TA, w.cid, version_id=v1)
    both = await create_from(api, w.TA, w.cid, t["id"], version_id=v1)
    assert latest["exam_template"]["version_id"] == v2 and latest["navigation"] == "section_forward_only"
    assert pinned["exam_template"]["version_id"] == v1 and pinned["navigation"] == "free"
    assert both["exam_template"]["version_id"] == v1
    other = await published_template(api, w.PA)
    body = await create_from(api, w.TA, w.cid, other["id"], version_id=v1, status=404)
    assert body["error"]["code"] == "template_not_found"
    assert await create_from(api, w.TA, w.cid, version_id=uuid.uuid4(), status=404)


async def test_quiz_assignment_from_template_applies_later_fields(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=SPEC)
    cat = make_category(db, w.course)
    due = (utcnow() + timedelta(days=2)).replace(microsecond=0)
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assignments", json={
        "title": {"en": "Quiz"}, "kind": "quiz", "due_at": due.isoformat(), "category_id": str(cat.id),
        "omit_from_total": True, "quiz": {"languages": ["en"], "exam_template_id": t["id"]}})
    assert res.status_code == 201, res.text
    b = res.json()
    a = db.get(Assessment, uuid.UUID(b["assessment_id"]))
    assert uuid.UUID(b["id"]) == assignment_id_for(a.id) and b["kind"] == "quiz"
    assert a.exam_template_version_id == uuid.UUID(t["current_version_id"]) and a.preset == "none"
    assert a.grade_category_id == cat.id and a.omit_from_total is True and a.navigation == "section_forward_only"
    assert b["category_id"] == str(cat.id) and b["assessment"]["status"] == "draft"
    staff = (await api.call(w.TA, "GET", f"/courses/{w.cid}/assessments/{a.id}")).json()
    assert staff["exam_template"]["template_id"] == t["id"] and staff["grade_category_id"] == str(cat.id)
    assert mirror_mismatches(db, a) == {}
    assert db.execute(select(AssessmentSection).where(AssessmentSection.assessment_id == a.id)).scalars().all()
    # refusals: unknown template, points on a quiz, parameters alone
    for quiz, code, status in (({"languages": ["en"], "exam_template_id": str(uuid.uuid4())}, "template_not_found", 404),
                               ({"languages": ["en"], "parameters": {"a": "b"}}, "template_not_found", 422),
                               ({"languages": ["en"], "exam_template_id": t["id"], "preset": "none"},
                                "preset_template_exclusive", 422)):
        res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assignments", json={"title": {"en": "X"}, "kind": "quiz",
                                                                               "quiz": quiz})
        assert (res.status_code, res.json()["error"]["code"]) == (status, code), res.text
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assignments", json={
        "title": {"en": "X"}, "kind": "quiz", "points_possible": 5, "quiz": {"languages": ["en"], "exam_template_id": t["id"]}})
    assert res.status_code == 422 and res.json()["error"]["code"] == "quiz_field_not_editable"
    assert db.execute(select(Assessment)).scalars().all() == [a]


async def test_quiz_from_locked_template_refuses_other_scheme_before_creating(db, api):
    w = tworld(db)
    spec = general_spec(scoring={"grading_scheme_version_id": str(ORT_MAIN_V1_ID)}, lock_scope=["scheme"])
    t = await published_template(api, w.PA, spec=spec)
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/lock")).status_code == 200
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assignments", json={
        "title": {"en": "Q"}, "kind": "quiz", "grading_scheme_version_id": None,
        "quiz": {"languages": ["en"], "exam_template_id": t["id"]}})
    assert res.status_code == 409 and res.json()["error"]["code"] == "template_locked", res.text
    assert res.json()["error"]["details"]["source"] == "exam_template"
    assert db.execute(select(Assessment)).first() is None
    # the template's own scheme is fine
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assignments", json={
        "title": {"en": "Q"}, "kind": "quiz", "grading_scheme_version_id": str(ORT_MAIN_V1_ID),
        "quiz": {"languages": ["en"], "exam_template_id": t["id"]}})
    assert res.status_code == 201, res.text


def test_version_rows_reference_scheme(db):
    assert ExamTemplateVersion.__table__.c.grading_scheme_version_id.foreign_keys
