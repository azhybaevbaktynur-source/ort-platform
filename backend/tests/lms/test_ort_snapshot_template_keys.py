"""ORT must not change (rule 9) under the Phase 7b snapshot keys (PHASE_7B_DESIGN 6, 12).

The four `SNAPSHOT_TEMPLATE_KEYS` are purely additive: an ORT exam published through the production seed path gets
exactly the pre-7b snapshot plus `exam_template_version_id: null, display_mode: "one_per_page", passage_display: null,
result_view: null`; everything the engine reads from the plan (navigation, section limits, slots) is identical with
and without them; no student payload of an ORT attempt carries any of them; the seeded exam keeps its 0010 defaults;
a second seed run publishes no new version."""
from __future__ import annotations

import json
from types import SimpleNamespace

from sqlalchemy import func, select

from app.lms.assessments import snapshot as snapshot_module
from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.assessments.snapshot import build_snapshot
from app.lms.attempts import engine
from app.lms.exam_templates.ids import SNAPSHOT_TEMPLATE_KEYS
from app.lms.ort.seed import course_id_for, ensure_ort_courses
from tests.lms.factories import make_user
from tests.lms.s3_support import Api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_ort_seed import insert_export

ORT_VALUES = {"exam_template_version_id": None, "display_mode": "one_per_page", "passage_display": None,
              "result_view": None}


def _keys(obj) -> set:
    out: set = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            out |= _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _keys(v)
    return out


def _seed(db) -> Assessment:
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ru", language="ru", keep_images=False)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok and rep.assessments_published == 1, rep
    return db.scalars(select(Assessment).where(Assessment.course_id == course_id_for("ru"))).one()


async def test_ort_snapshot_keys_are_additive(db, monkeypatch):
    a = _seed(db)
    assert (a.preset, a.exam_template_version_id, a.display_mode, a.passage_display, a.result_view,
            a.structure_locked) == ("ort_main", None, "one_per_page", None, None, False)
    v = db.get(AssessmentVersion, a.published_version_id)
    snap = v.snapshot
    assert {k: snap[k] for k in SNAPSHOT_TEMPLATE_KEYS} == ORT_VALUES

    # the pre-7b snapshot: the same builder without the template keys
    with_keys, issues = build_snapshot(db, a)
    assert not [i for i in issues if i.severity == "error"]
    monkeypatch.setattr(snapshot_module, "template_snapshot_keys", lambda _a: {})
    without, _ = build_snapshot(db, a)
    monkeypatch.undo()
    assert set(with_keys) - set(without) == set(SNAPSHOT_TEMPLATE_KEYS)
    assert {k: v for k, v in with_keys.items() if k not in SNAPSHOT_TEMPLATE_KEYS} == without
    assert with_keys == snap                                            # the stored version is that snapshot

    # what the engine reads from a plan is identical with and without the keys
    p_with = SimpleNamespace(snapshot=with_keys, slots=with_keys["slots"])
    p_without = SimpleNamespace(snapshot=without, slots=without["slots"])
    assert engine._navigation(p_with) == engine._navigation(p_without) == "section_forward_only"
    assert engine._section_limits(p_with) == engine._section_limits(p_without)
    assert engine._section_limits(p_with, 600) == engine._section_limits(p_without, 600)
    for lang in snap["languages"]:
        assert engine._slot_maps(p_with, lang) == engine._slot_maps(p_without, lang)

    # a second seed run publishes nothing new
    again = ensure_ort_courses(db, samples=False)
    assert again.ok and again.assessments_published == 0
    n = db.execute(select(func.count()).select_from(AssessmentVersion).where(
        AssessmentVersion.assessment_id == a.id, AssessmentVersion.kind == "published")).scalar()
    assert n == 1


async def test_ort_student_payloads_carry_no_template_keys(db):
    a = _seed(db)
    cid = course_id_for("ru")
    api = Api()
    student = make_user(db)
    assert (await api.call(student, "POST", f"/courses/{cid}/join")).status_code == 200
    base = f"/courses/{cid}/assessments/{a.id}"
    lobby = await api.call(student, "GET", base)
    assert lobby.status_code == 200, lobby.text
    st = await api.call(student, "POST", f"{base}/attempts", json={"language": "ru"})
    assert st.status_code == 201, st.text
    tid = st.json()["id"]
    content = await api.call(student, "GET", f"/attempts/{tid}/content?section=1")
    assert content.status_code == 200, content.text
    state = await api.call(student, "GET", f"/attempts/{tid}")
    assert state.status_code == 200, state.text
    for res in (lobby, st, content, state):
        leaked = _keys(res.json()) & set(SNAPSHOT_TEMPLATE_KEYS)
        assert not leaked, (res.request.url, leaked)
    assert st.json()["navigation"] == "section_forward_only" and len(st.json()["items"]) == 150
    assert "exam_template_version_id" not in json.dumps(st.json())
