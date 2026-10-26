"""Phase 7b S2 (PHASE_7B_DESIGN 6, 3.3): a template exam's snapshot carries the four `SNAPSHOT_TEMPLATE_KEYS` with
the assessment's values; attempts keep running after the template is re-published and archived (running exams never
look back at the template)."""
from __future__ import annotations

import uuid

from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.exam_templates.ids import SNAPSHOT_TEMPLATE_KEYS
from tests.lms.assessment_support import add_q, bank_of, publish
from tests.lms.exam_template_support import general_spec
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_templates_api import T, create_from, publish_t, published_template, tworld

SPEC = general_spec(result_view="general", passage_display="plain",
                    defaults={"time_limit_s": None, "allowed_attempts": 3, "score_policy": "highest",
                              "results_policy": "after_submit", "show_correct_answers": False,
                              "shuffle_items": False, "shuffle_choices": False},
                    sections=[{"key": "s1", "allowed_types": ["single_choice"], "allow_passages": True}])


async def test_snapshot_keys_and_attempts_survive_template_changes(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=SPEC)
    a = await create_from(api, w.TA, w.cid, t["id"], languages=["en"])
    _, qs = bank_of(db, w.course, w.TA, 2)
    for q in qs:
        await add_q(api, w.TA, w.cid, a["id"], a["sections"][0]["id"], q.id)
    res = await publish(api, w.TA, w.cid, a["id"])
    assert res.status_code == 200, res.text
    row = db.get(Assessment, uuid.UUID(a["id"]))
    snap = db.get(AssessmentVersion, row.published_version_id).snapshot
    assert {k: snap[k] for k in SNAPSHOT_TEMPLATE_KEYS} == {
        "exam_template_version_id": t["current_version"]["id"], "display_mode": "one_per_page",
        "passage_display": "plain", "result_view": "general"}
    # a student takes it
    start = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{a['id']}/attempts", json={})
    assert start.status_code in (200, 201), start.text
    att1 = start.json()["id"]
    content = await api.call(w.S, "GET", f"/attempts/{att1}/content")
    assert content.status_code == 200
    # the template is re-published and archived while the attempt is in flight
    p = await api.call(w.PA, "PATCH", f"{T}/{t['id']}", json={"draft_rev": t["draft_rev"], "draft_spec": general_spec()})
    assert p.status_code == 200
    assert (await publish_t(api, w.PA, t["id"])).json()["version"]["version_no"] == 2
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/archive")).status_code == 200
    saved = await api.call(w.S, "PUT", f"/attempts/{att1}/answers", json={
        "answers": [{"position": 1, "response": {"choice": "B"}, "client_ts": 1}]})
    assert saved.status_code in (200, 207), saved.text
    submit = await api.call(w.S, "POST", f"/attempts/{att1}/submit", json={})
    assert submit.status_code == 200, submit.text
    assert (await api.call(w.S, "GET", f"/attempts/{att1}")).status_code == 200
    # a new attempt still starts on the published version (allowed_attempts 3)
    again = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{a['id']}/attempts", json={})
    assert again.status_code in (200, 201), again.text
    assert again.json()["id"] != att1
    assert (await api.call(w.S, "GET", f"/attempts/{again.json()['id']}/content")).status_code == 200
    # the assessment row and its snapshot still point to version 1
    db.refresh(row)
    assert str(row.exam_template_version_id) == t["current_version"]["id"]
    assert db.get(AssessmentVersion, row.published_version_id).snapshot["exam_template_version_id"] == t["current_version"]["id"]
    # staff still read the archived template through the assessment
    assert (await api.call(w.TA, "GET", f"{T}/{t['id']}/versions/1")).status_code == 200
