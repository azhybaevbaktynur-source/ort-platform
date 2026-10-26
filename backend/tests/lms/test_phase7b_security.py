"""Phase 7b security review fixes (S6): CSV header width (general parser and the shared import guard), upgrade
checks, no orphan assessment on a refused quiz create, MAX_SECTIONS, the preset guard on the template branch,
bounded validation details, audit rows and "save as template" refused for locked structures (decision L5)."""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.core.config import settings
from app.lms.assessments.models import Assessment
from app.lms.assignments import schemas as asg_sch
from app.lms.assignments import service as asg_svc
from app.lms.assignments.models import Assignment
from app.lms.content.importers import ImportOptions, parse_upload
from app.lms.content.importers import service as imp_svc
from app.lms.content.importers.general_csv import MAX_COLUMNS
from app.lms.content.types.base import VALIDATION_DETAILS_MAX, validation_details
from app.lms.core.errors import ValidationFailed
from app.lms.core.models import utcnow
from app.lms.exam_templates import ids
from app.lms.exam_templates.models import ExamTemplate
from app.lms.exam_templates.spec import MAX_SECTIONS, parse_spec
from app.lms.templates import service as tpl
from tests.lms.content_support import world
from tests.lms.exam_template_support import general_spec
from tests.lms.files_support import local_storage  # noqa: F401
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_templates_api import (
    T, audit_rows, create_from, create_t, err, publish_t, published_template, tworld,
)
from tests.lms.test_import_api import imp
from tests.lms.test_template_upgrade import V1, V2, _bump

EN = ImportOptions(language="en")


def _ctx(db, user) -> AuthzContext:
    return AuthzContext(user, db, enrollment_role_resolver(db, user.id))


# =========================================================================== 1. general CSV header width

def test_general_csv_wide_header_is_refused_fast():
    header = ",".join(["type", "stem", "answers"] + [f"x{i}" for i in range(10_000 - 3)])
    rows = "\n".join("short_text,Q,a" for _ in range(3000))
    raw = f"{header}\n{rows}\n".encode()
    t0 = time.perf_counter()
    up = parse_upload(raw, "q.csv", EN)
    elapsed = time.perf_counter() - t0
    assert [e.code for e in up.issues.errors] == ["csv_too_many_columns"]
    assert up.issues.errors[0].params == {"limit": MAX_COLUMNS, "got": 10_000}
    assert up.issues.warnings == [] and elapsed < 1.0, elapsed


def test_general_csv_header_at_the_limit_still_parses():
    header = ",".join(["type", "stem", "answers"] + [f"x{i}" for i in range(MAX_COLUMNS - 3)])
    up = parse_upload((f"{header}\nshort_text,Q,a\nshort_text,R,b," + "z," * 70 + "\n").encode(), "q.csv", EN)
    assert [e.code for e in up.issues.errors] == []
    items = up.bundles[0].items
    assert [it.stem for it in items] == ["Q", "R"]                    # short rows: empty cells; long rows: extras ignored
    assert {w.code for w in up.issues.warnings} == {"unknown_column"}


# =========================================================================== 2. shared guard (every plain CSV)

def test_shared_guard_counts_header_cells_only():
    ok = ",".join(f"c{i}" for i in range(imp_svc.CSV_MAX_COLUMNS)).encode()
    assert imp_svc._too_wide_csv(ok + b"\n1,2\n", "q.csv") is None
    wide = ",".join(f"c{i}" for i in range(imp_svc.CSV_MAX_COLUMNS + 1)).encode("latin-1") + b"\xe9\n"
    up = imp_svc._too_wide_csv(wide, "Q.CSV")
    assert up is not None and [e.code for e in up.issues.errors] == ["csv_too_many_columns"]
    assert up.issues.errors[0].params == {"limit": imp_svc.CSV_MAX_COLUMNS, "got": imp_svc.CSV_MAX_COLUMNS + 1}
    assert imp_svc._too_wide_csv(wide, "b.zip") is None              # zips: their parsers check the header
    quoted = b'"a,b,c",' * 300 + b"\n"                                # quoted commas are one cell each
    assert imp_svc._too_wide_csv(quoted, "q.csv") is not None
    assert imp_svc._too_wide_csv(b'"a,b,c"\n' * 2, "q.csv") is None


@pytest.mark.usefixtures("local_storage")
async def test_shared_guard_refuses_wide_ort_csv_before_parsing(db, monkeypatch):
    w = world(db)
    calls = []
    real = imp_svc.parse_upload
    monkeypatch.setattr(imp_svc, "parse_upload", lambda *a, **k: calls.append(1) or real(*a, **k))
    # the ORT / legacy plain CSV (no `type` column) with 10,000 columns
    header = ",".join(["section", "stem", "option_a", "option_b", "correct_option"]
                      + [f"x{i}" for i in range(10_000 - 5)])
    raw = (header + "\n" + "\n".join("unit,Q,1,2,A" for _ in range(500)) + "\n").encode()
    for commit in (False, True):
        t0 = time.perf_counter()
        res = await imp(w.O, w.cid, raw, filename="q.csv", commit=commit, language="en")
        assert time.perf_counter() - t0 < 1.0
        rep = res.json()
        assert res.status_code == 200 and rep["ok"] is False and rep["committed"] is False, res.text
        assert [e["code"] for e in rep["errors"]] == ["csv_too_many_columns"]
    assert calls == []                                                 # no parser ran
    # an ordinary ORT CSV still goes through the parser
    res = await imp(w.O, w.cid, b"section,stem,option_a,option_b,option_c,option_d,correct_option\n"
                    b"unit,Q,1,2,3,4,A\n", filename="q.csv", commit=False, language="en")
    assert res.json()["ok"] is True and calls == [1], res.text


# =========================================================================== 3. upgrade checks

async def test_upgrade_refuses_archived_and_deleted_templates_before_changing(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=V1)
    a = await create_from(api, w.TA, w.cid, t["id"])
    p = f"/courses/{w.cid}/assessments/{a['id']}"
    await _bump(api, w, t, V2)
    before = (await api.call(w.TA, "GET", p)).json()
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/archive")).status_code == 200
    res = await api.call(w.TA, "POST", f"{p}/template-upgrade")
    assert res.status_code == 409 and err(res) == "template_archived", res.text
    after = (await api.call(w.TA, "GET", p)).json()
    assert after["draft_rev"] == before["draft_rev"] and after["exam_template"]["version_no"] == 1
    row = db.get(ExamTemplate, uuid.UUID(t["id"]))
    db.refresh(row)
    row.status, row.deleted_at = "published", utcnow()
    db.commit()
    res = await api.call(w.TA, "POST", f"{p}/template-upgrade")
    assert res.status_code == 404 and err(res) == "template_not_found", res.text
    assert (await api.call(w.TA, "GET", p)).json()["draft_rev"] == before["draft_rev"]


async def test_upgrade_refuses_a_template_outside_the_callers_scope(db, api):
    from tests.lms.factories import enroll

    w = tworld(db)
    t = await published_template(api, w.TA, owner_scope="teacher", organization_id=w.org.id, spec=V1)
    a = await create_from(api, w.TA, w.cid, t["id"])
    await _bump(api, SimpleW(w.TA), t, V2)
    enroll(db, w.course, w.TB, "teacher", source="staff_add")      # a co-teacher: TA's template is private
    res = await api.call(w.TB, "POST", f"/courses/{w.cid}/assessments/{a['id']}/template-upgrade")
    assert res.status_code == 404 and err(res) == "template_not_found", res.text
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assessments/{a['id']}/template-upgrade")
    assert res.status_code == 200, res.text


class SimpleW:
    """`_bump` publishes as `w.PA`; here the teacher owns the template."""

    def __init__(self, user):
        self.PA = user


# =========================================================================== 4. no orphan on a refused quiz create

async def test_quiz_from_template_with_invalid_window_leaves_nothing(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=general_spec())
    now = utcnow()
    quiz = asg_sch.QuizCreateIn(languages=["en"], exam_template_id=uuid.UUID(t["id"]))
    # the schema refuses this window too; built without validation to reach the service's own check
    data = asg_sch.AssignmentCreateIn.model_construct(
        _fields_set={"title", "kind", "quiz", "available_from", "available_until"}, title={"en": "Q"},
        kind="quiz", quiz=quiz, available_from=now + timedelta(days=2), available_until=now + timedelta(days=1))
    db.expire_all()
    with pytest.raises(ValidationFailed):
        asg_svc.create_assignment(db, _ctx(db, w.TA), w.course, data)
    db.expire_all()
    assert db.execute(select(Assessment)).first() is None
    assert db.execute(select(Assignment)).first() is None
    assert audit_rows(db, ids.AUDIT_INSTANTIATE) == []


# =========================================================================== 5. MAX_SECTIONS

def test_spec_sections_capped_by_assessment_setting():
    assert MAX_SECTIONS == settings.ASSESSMENT_MAX_SECTIONS

    def secs(n):
        return [{"key": f"s{i}", "allowed_types": ["single_choice"]} for i in range(n)]

    parse_spec(general_spec(sections=secs(MAX_SECTIONS)))
    with pytest.raises(ValidationFailed) as e:
        parse_spec(general_spec(sections=secs(MAX_SECTIONS + 1)))
    assert e.value.code == "spec_invalid" and e.value.details[0]["loc"] == ["sections"]


# =========================================================================== 6. preset guard on the template branch

async def test_template_branch_checks_the_course_template_preset(db, api, monkeypatch):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=general_spec())
    seen = []

    def refuse(course, preset):
        seen.append(preset)
        raise ValidationFailed("not here", code="preset_not_available")

    monkeypatch.setattr(tpl, "assert_preset_allowed", refuse)
    res = await create_from(api, w.TA, w.cid, t["id"], status=422)
    assert res["error"]["code"] == "preset_not_available"
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assignments", json={
        "title": {"en": "Q"}, "kind": "quiz", "quiz": {"languages": ["en"], "exam_template_id": t["id"]}})
    assert res.status_code == 422 and err(res) == "preset_not_available", res.text
    assert seen == ["none", "none"] and db.execute(select(Assessment)).first() is None


# =========================================================================== 7. bounded validation details

def test_validation_details_are_capped():
    class M(BaseModel):
        xs: list[int]

    with pytest.raises(ValidationError) as e:
        M(xs=["a"] * 120)
    out = validation_details(e.value)
    assert len(out) == VALIDATION_DETAILS_MAX + 1 == 51
    assert out[-1]["truncated"] == 70 and out[-1]["loc"] == []
    assert all(set(d) == {"loc", "msg"} for d in out[:-1])
    with pytest.raises(ValidationError) as e:
        M(xs=["a"] * 3)
    assert len(validation_details(e.value)) == 3
    bad = general_spec(sections=[{"key": f"S{i}!", "allowed_types": ["nope"]} for i in range(20)])
    with pytest.raises(ValidationFailed) as f:
        parse_spec(bad)
    assert len(f.value.details) <= VALIDATION_DETAILS_MAX + 1


# =========================================================================== 8. audit rows

async def test_platform_drafts_save_as_and_instantiate_are_audited(db, api):
    w = tworld(db)
    res = await create_t(api, w.PA, spec=general_spec())
    assert res.status_code == 201, res.text
    tid = res.json()["id"]
    rows = audit_rows(db, ids.AUDIT_CREATE, tid)
    assert len(rows) == 1 and rows[0].actor_id == w.PA.id and rows[0].details["owner_scope"] == "platform"
    res = await api.call(w.PA, "PATCH", f"{T}/{tid}", json={"draft_rev": 1, "title": {"en": "Renamed"}})
    assert res.status_code == 200, res.text
    rows = audit_rows(db, ids.AUDIT_UPDATE, tid)
    assert len(rows) == 1 and rows[0].details == {"fields": ["title"], "draft_rev": 2}
    # teacher templates: no create / update rows
    res = await create_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id)
    assert res.status_code == 201 and audit_rows(db, ids.AUDIT_CREATE, res.json()["id"]) == []
    res = await api.call(w.TA, "PATCH", f"{T}/{res.json()['id']}", json={"draft_rev": 1, "title": {"en": "Y"}})
    assert res.status_code == 200 and len(audit_rows(db, ids.AUDIT_UPDATE)) == 1
    # instantiate
    assert (await publish_t(api, w.PA, tid)).status_code == 200
    a = await create_from(api, w.TA, w.cid, tid)
    rows = audit_rows(db, ids.AUDIT_INSTANTIATE, a["id"])
    assert len(rows) == 1 and rows[0].target_type == "assessment" and rows[0].details["template_id"] == tid
    assert rows[0].details["version_no"] == 1 and rows[0].details["course_id"] == w.cid
    # save as template
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assessments/{a['id']}/save-as-template",
                         json={"owner_scope": "teacher", "title": {"en": "Copy"}})
    assert res.status_code == 201, res.text
    rows = audit_rows(db, ids.AUDIT_SAVE_AS, res.json()["id"])
    assert len(rows) == 1 and rows[0].details["assessment_id"] == a["id"]
    assert rows[0].details["owner_scope"] == "teacher" and rows[0].actor_id == w.TA.id


# =========================================================================== 9. save as template: locked structures

async def test_save_as_refused_for_locked_structure_or_template(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=general_spec(lock_scope=["sections"]))
    body = {"owner_scope": "teacher", "title": {"en": "Copy"}}
    a1 = await create_from(api, w.TA, w.cid, t["id"])                     # template unlocked: structure free
    assert a1["structure_locked"] is False and a1["exam_template"]["template_locked"] is False
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/lock")).status_code == 200
    a2 = await create_from(api, w.TA, w.cid, t["id"])                     # created while locked
    assert a2["structure_locked"] is True
    for a in (a1, a2):
        p = f"/courses/{w.cid}/assessments/{a['id']}"
        assert (await api.call(w.TA, "GET", p)).json()["exam_template"]["template_locked"] is True
        res = await api.call(w.TA, "POST", f"{p}/save-as-template", json=body)
        assert res.status_code == 409 and err(res) == "template_locked", res.text
        assert res.json()["error"]["details"]["source"] == "exam_template"
    assert db.execute(select(ExamTemplate).where(ExamTemplate.owner_scope == "teacher")).first() is None
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/unlock")).status_code == 200
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assessments/{a2['id']}/save-as-template", json=body)
    assert res.status_code == 409 and err(res) == "template_locked"     # its structure stays locked
    res = await api.call(w.TA, "POST", f"/courses/{w.cid}/assessments/{a1['id']}/save-as-template", json=body)
    assert res.status_code == 201, res.text
