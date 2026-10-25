"""Assessment and course grading settings (PHASE_4_DESIGN 3.3, P4-4, P4-6, P4-10, P4-12)."""
import uuid
from datetime import datetime, timedelta, timezone

from app.lms.grading import seeds
from app.lms.grading.models import GradeCategory
from tests.lms.assessment_support import mk
from tests.lms.content_support import world
from tests.lms.factories import enroll, make_assessment, make_course, make_scheme, make_user, set_status
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def err(res):
    return res.json()["error"]["code"]


async def patch(api, user, cid, aid, **body):
    cur = (await api.call(user, "GET", f"/courses/{cid}/assessments/{aid}")).json()["draft_rev"]
    return await api.call(user, "PATCH", f"/courses/{cid}/assessments/{aid}", json={"draft_rev": cur, **body})


# ------------------------------------------------------------------ assessments

async def test_presets_attach_system_versions(db, api):
    w = world(db)
    w.course.template_key, w.course.template_version = "ort", 1; db.commit()  # Phase 6 S2b: ORT presets/import formats need the ORT course template
    main = await mk(api, w.O, w.cid, preset="ort_main")
    subj = await mk(api, w.O, w.cid, preset="ort_subject", subject_key="chemistry")
    none = await mk(api, w.O, w.cid)
    assert main["grading_scheme_version_id"] == str(seeds.ORT_MAIN_V1_ID)
    assert main["scheme"] == {"id": str(seeds.ORT_MAIN_V1_ID), "scheme_id": str(seeds.ORT_MAIN_SCHEME_ID),
                              "title": main["scheme"]["title"], "type": "piecewise_curve", "version_no": 1,
                              "scale_min": 60.0, "scale_max": 245.0, "labels": {}}
    assert subj["scheme"]["id"] == str(seeds.ORT_SUBJECT_V1_ID) and subj["scheme"]["scale_max"] == 150.0
    assert none["scheme"] is None and none["grading_scheme_version_id"] is None
    assert (none["grade_release"], none["omit_from_total"], none["due_at"], none["grade_category_id"]) == \
        ("auto", False, None, None)


async def test_patch_grading_fields_and_changed_at(db, api):
    w = world(db)
    a = await mk(api, w.O, w.cid)
    mine = make_scheme(db, w.O, "pass_fail", {"pass_threshold_percent": 50})
    cat = GradeCategory(course_id=w.course.id, title={"en": "Quizzes"}, weight=50, position=1)
    db.add(cat)
    db.commit()
    due = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    r = await patch(api, w.O, w.cid, a["id"], grading_scheme_version_id=str(mine.current_version_id),
                    grade_category_id=str(cat.id), due_at=due.isoformat(), grade_release="manual",
                    omit_from_total=True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scheme"]["type"] == "pass_fail" and body["grade_category_id"] == str(cat.id)
    assert body["grade_release"] == "manual" and body["omit_from_total"] is True
    assert datetime.fromisoformat(body["due_at"].replace("Z", "+00:00")) == due
    from app.lms.assessments.models import Assessment

    row = db.get(Assessment, uuid.UUID(a["id"]))
    db.refresh(row)
    first = row.grading_changed_at
    assert first is not None
    # release/omit/category changes do not touch grading_changed_at; clearing the scheme does
    r = await patch(api, w.O, w.cid, a["id"], grade_release="auto", omit_from_total=False, grade_category_id=None)
    assert r.status_code == 200 and r.json()["grade_category_id"] is None
    db.refresh(row)
    assert row.grading_changed_at == first
    r = await patch(api, w.O, w.cid, a["id"], score_policy="latest")
    db.refresh(row)
    assert r.status_code == 200 and row.grading_changed_at > first
    r = await patch(api, w.O, w.cid, a["id"], grading_scheme_version_id=None)
    assert r.status_code == 200 and r.json()["scheme"] is None
    for bad in ({"grade_release": None}, {"omit_from_total": None}, {"grade_release": "later"}):
        assert (await patch(api, w.O, w.cid, a["id"], **bad)).status_code == 422


async def test_patch_rejects_unusable_scheme_and_foreign_category(db, api):
    w = world(db)
    a = await mk(api, w.O, w.cid)
    stranger = make_user(db, teacher_status="approved")
    theirs = make_scheme(db, stranger, "percent", {})
    r = await patch(api, w.O, w.cid, a["id"], grading_scheme_version_id=str(theirs.current_version_id))
    assert r.status_code == 404 and err(r) == "scheme_version_not_found"
    other = make_course(db, stranger)
    cat = GradeCategory(course_id=other.id, title={"en": "x"}, weight=0, position=1)
    db.add(cat)
    db.commit()
    r = await patch(api, w.O, w.cid, a["id"], grade_category_id=str(cat.id))
    assert r.status_code == 404 and err(r) == "category_not_found"
    # a co-teacher's scheme is usable in the course
    co = make_scheme(db, w.T, "percent", {})
    r = await patch(api, w.O, w.cid, a["id"], grading_scheme_version_id=str(co.current_version_id))
    assert r.status_code == 200 and r.json()["scheme"]["id"] == str(co.current_version_id)


async def test_student_views_expose_scheme_brief_and_due_at(db, api):
    from tests.lms.assessment_support import add_q, sc
    from tests.lms.factories import make_bank

    w = world(db)
    w.course.template_key, w.course.template_version = "ort", 1; db.commit()  # Phase 6 S2b: ORT presets/import formats need the ORT course template
    a = await mk(api, w.O, w.cid, preset="ort_subject", subject_key="chemistry")
    bank = make_bank(db, w.course, w.O)
    await add_q(api, w.O, w.cid, a["id"], a["sections"][0]["id"], sc(db, bank, w.O).id)
    due = datetime.now(timezone.utc) + timedelta(days=3)
    assert (await patch(api, w.O, w.cid, a["id"], due_at=due.isoformat())).status_code == 200
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{a['id']}/publish", json={"confirm": True})
    assert r.status_code == 200, r.text
    lobby = (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments/{a['id']}")).json()
    assert lobby["scheme"] == {"type": "piecewise_curve", "scale_min": 60.0, "scale_max": 150.0,
                               "title": lobby["scheme"]["title"], "labels": {}}
    assert lobby["due_at"] is not None
    item = (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments")).json()["items"][0]
    assert item["scheme"] == lobby["scheme"] and item["due_at"] == lobby["due_at"]
    assert "params" not in str(lobby) and str(seeds.ORT_SUBJECT_V1_ID) not in str(lobby) + str(item)


# ------------------------------------------------------------------ course grading settings

async def test_course_grading_get_put(db, api):
    w = world(db)
    r = await api.call(w.O, "GET", f"/courses/{w.cid}/grading")
    assert r.status_code == 200
    assert r.json() == {"total_mode": "points", "grading_scheme_version_id": None, "scheme": None,
                        "late_policy": None, "categories": [], "warnings": [], "grading_changed_at": None}
    body = {"total_mode": "weighted", "grading_scheme_version_id": str(seeds.PASS_FAIL_V1_ID),
            "late_policy": {"percent_per_day": 10, "max_percent": 50, "grace_minutes": 15}}
    r = await api.call(w.AS, "PUT", f"/courses/{w.cid}/grading", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["total_mode"] == "weighted" and out["scheme"]["type"] == "pass_fail"
    assert out["late_policy"] == {"percent_per_day": 10.0, "max_percent": 50.0, "grace_minutes": 15}
    assert out["grading_changed_at"] is not None and out["warnings"] == ["weights_all_zero"]
    stu = await api.call(w.S, "GET", f"/courses/{w.cid}/grading")
    assert stu.status_code == 200
    assert set(stu.json()) == {"total_mode", "scheme"}
    assert set(stu.json()["scheme"]) == {"type", "scale_min", "scale_max", "title", "labels"}
    # PUT is a full replace: omitted scheme / late policy are cleared
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/grading", json={"total_mode": "points"})
    assert r.json()["scheme"] is None and r.json()["late_policy"] is None


async def test_course_grading_validation_and_authz(db, api):
    w = world(db)
    for bad in ({"total_mode": "median"},
                {"total_mode": "points", "late_policy": {"percent_per_day": 101, "max_percent": 1}},
                {"total_mode": "points", "late_policy": {"percent_per_day": 1, "max_percent": 1,
                                                         "grace_minutes": 1441}},
                {"total_mode": "points", "extra": 1}):
        r = await api.call(w.O, "PUT", f"/courses/{w.cid}/grading", json=bad)
        assert r.status_code == 422 and err(r) == "validation_failed"
    stranger = make_user(db, teacher_status="approved")
    theirs = make_scheme(db, stranger, "percent", {})
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/grading",
                       json={"total_mode": "points", "grading_scheme_version_id": str(theirs.current_version_id)})
    assert r.status_code == 404 and err(r) == "scheme_version_not_found"
    assert (await api.call(w.S, "PUT", f"/courses/{w.cid}/grading", json={"total_mode": "points"})).status_code == 403
    for user in (w.X, stranger):
        r = await api.call(user, "GET", f"/courses/{w.cid}/grading")
        assert r.status_code == 404 and err(r) == "course_not_found"
    set_status(db, w.course, "concluded")
    assert (await api.call(w.O, "PUT", f"/courses/{w.cid}/grading",
                           json={"total_mode": "points"})).status_code == 403
    assert (await api.call(w.O, "GET", f"/courses/{w.cid}/grading")).status_code == 200


# ------------------------------------------------------------------ categories

async def test_categories_crud_order_and_in_use(db, api):
    w = world(db)
    base = f"/courses/{w.cid}/grade-categories"
    made = []
    for title, weight in (("Quizzes", 30), ("Exams", 70)):
        r = await api.call(w.O, "POST", base, json={"title": {"en": title}, "weight": weight})
        assert r.status_code == 201, r.text
        made.append(r.json())
    assert [c["position"] for c in made] == [1, 2] and made[0]["assessment_count"] == 0
    r = await api.call(w.AS, "PATCH", f"{base}/{made[0]['id']}", json={"weight": 25.5})
    assert r.status_code == 200 and r.json()["weight"] == 25.5
    assert (await api.call(w.O, "PATCH", f"{base}/{made[0]['id']}", json={"title": None})).status_code == 422
    r = await api.call(w.O, "PUT", f"{base}/order", json={"category_ids": [made[1]["id"], made[0]["id"]]})
    assert r.status_code == 200 and [c["id"] for c in r.json()] == [made[1]["id"], made[0]["id"]]
    r = await api.call(w.O, "PUT", f"{base}/order", json={"category_ids": [made[1]["id"]]})
    assert r.status_code == 422 and err(r) == "order_mismatch"
    a = make_assessment(db, w.course, w.O, grade_category_id=uuid.UUID(made[0]["id"]))
    g = (await api.call(w.O, "GET", f"/courses/{w.cid}/grading")).json()
    assert {c["id"]: c["assessment_count"] for c in g["categories"]} == {made[0]["id"]: 1, made[1]["id"]: 0}
    r = await api.call(w.O, "DELETE", f"{base}/{made[0]['id']}")
    assert r.status_code == 409 and err(r) == "category_in_use"
    a.deleted_at = datetime.now(timezone.utc)
    db.commit()
    assert (await api.call(w.O, "DELETE", f"{base}/{made[0]['id']}")).status_code == 204
    r = await api.call(w.O, "PATCH", f"{base}/{made[0]['id']}", json={"weight": 1})
    assert r.status_code == 404 and err(r) == "category_not_found"
    assert (await api.call(w.S, "POST", base, json={"title": {"en": "x"}, "weight": 1})).status_code == 403
    assert (await api.call(w.O, "POST", base, json={"title": {"en": "x"}, "weight": 101})).status_code == 422


async def test_category_cap_and_isolation(db, api, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GRADE_CATEGORIES_MAX", 1)
    w = world(db)
    base = f"/courses/{w.cid}/grade-categories"
    first = (await api.call(w.O, "POST", base, json={"title": {"en": "a"}, "weight": 1})).json()
    r = await api.call(w.O, "POST", base, json={"title": {"en": "b"}, "weight": 1})
    assert r.status_code == 422 and err(r) == "too_many_categories"
    # another course's staff cannot touch it through their own course id
    other_owner = make_user(db, teacher_status="approved")
    other = make_course(db, other_owner, status="published")
    r = await api.call(other_owner, "PATCH", f"/courses/{other.id}/grade-categories/{first['id']}",
                       json={"weight": 2})
    assert r.status_code == 404 and err(r) == "category_not_found"
    enroll(db, other, w.S)
    r = await api.call(w.X, "DELETE", f"{base}/{first['id']}")
    assert r.status_code == 404 and err(r) == "course_not_found"
