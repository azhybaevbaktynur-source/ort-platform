"""Phase 5 exit criterion (PHASE_5_DESIGN section 8), SQLite and (PG suite) PostgreSQL: the old ORT exam sets, exported
by revision 0006, become course content and a real student takes them.

legacy_ort_export rows (ky and ru, built from tsoomo19; the ru row keeps old image refs, P5-3) -> ensure_ort_courses()
twice (second run: nothing new) -> a student registers over HTTP -> both ORT courses in the catalog -> one-click
join -> the ky and the ru exam (start, autosave, forward-only sections, submit) -> result with the ORT scaled score
and percentile of the frozen oracle table -> review with correctness and keys (allowed after submit) -> the platform
admin is a teacher of both courses and reads the staff attempt list. Also: the demo teacher cannot log in, /auth/me
has no `role`, no route policy is `legacy`."""
from __future__ import annotations

import json
import uuid
from decimal import Decimal as D
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.lms.assessments.models import Assessment
from app.lms.content.models import QuestionVersion
from app.lms.enrollments.models import Enrollment
from app.lms.ort.seed import DEMO_TEACHER_EMAIL, DEMO_TEACHER_ID, course_id_for, ensure_ort_courses
from app.main import app
from app.models.user import User
from tests.auth_helpers import register_and_verify
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_ort_seed import counts, insert_export

FIXTURES = Path(__file__).parent / "fixtures"
N = 150
WRONG = {"ky": 23, "ru": 61}  # raw scores 127 and 89


def oracle(raw: int) -> tuple[D, D]:
    t = json.loads((FIXTURES / "ort_parity_main.json").read_text(encoding="utf-8"))
    return D(str(t["scaled"][str(N)][raw])), D(str(t["percentile"][str(N)][raw]))


async def call(token: str, method: str, path: str, json=None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, "/api/v1" + path, json=json,
                               headers={"Authorization": f"Bearer {token}", "x-forwarded-for": "10.9.8.7"})


def response_for(qv: QuestionVersion, correct: bool) -> dict:
    d = qv.data
    if qv.type == "comparison":
        return {"choice": d["correct"] if correct else next(c for c in "ABCD" if c != d["correct"])}
    assert qv.type == "single_choice", qv.type
    if correct:
        return {"choice_id": d["correct"]}
    return {"choice_id": next(c["id"] for c in d["choices"] if c["id"] != d["correct"])}


async def take_exam(db, token: str, cid: uuid.UUID, aid: uuid.UUID, lang: str, wrong: int) -> str:
    base = f"/courses/{cid}/assessments/{aid}"
    lobby = await call(token, "GET", base)
    assert lobby.status_code == 200 and lobby.json()["can_start"] is True, lobby.text
    st = await call(token, "POST", f"{base}/attempts", json={"language": lang})
    assert st.status_code == 201, st.text
    state = st.json()
    tid = state["id"]
    assert state["navigation"] == "section_forward_only" and len(state["items"]) == N
    assert len(state["sections"]) == 5 and state["current_section_pos"] == 1
    # forward-only: later sections are not served
    ahead = await call(token, "GET", f"/attempts/{tid}/content?section=2")
    assert ahead.status_code == 409 and ahead.json()["error"]["code"] == "section_not_current"
    # no result / review before submit
    early = await call(token, "GET", f"/attempts/{tid}/review")
    assert early.status_code == 403 and early.json()["error"]["code"] == "results_not_available"
    items = sorted(state["items"], key=lambda i: i["position"])
    qvs = {str(v.id): v for v in db.scalars(select(QuestionVersion).where(
        QuestionVersion.id.in_([uuid.UUID(i["qv"]) for i in items])))}
    wrong_positions = {i["position"] for i in items[:wrong]}
    ts = 1000
    for pos in range(1, 6):
        content = await call(token, "GET", f"/attempts/{tid}/content?section={pos}")
        assert content.status_code == 200, content.text
        sec = [i for i in items if i["section_pos"] == pos]
        assert len(sec) == 30
        for k in range(0, len(sec), 20):
            batch = []
            for i in sec[k:k + 20]:
                ts += 1
                batch.append({"position": i["position"], "client_ts": ts,
                              "response": response_for(qvs[i["qv"]], i["position"] not in wrong_positions)})
            r = await call(token, "PUT", f"/attempts/{tid}/answers", json={"answers": batch})
            assert r.status_code == 200, r.text
        if pos < 5:
            r = await call(token, "POST", f"/attempts/{tid}/sections/{pos}/close")
            assert r.status_code == 200 and r.json()["current_section_pos"] == pos + 1, r.text
            back = await call(token, "PUT", f"/attempts/{tid}/answers", json={"answers": [
                {"position": sec[0]["position"], "client_ts": ts + 1, "response": {"choice": "A"}}]})
            assert back.status_code == 409 and back.json()["error"]["code"] == "section_closed"
    sub = await call(token, "POST", f"/attempts/{tid}/submit", json={})
    assert sub.status_code == 200 and sub.json()["status"] == "graded", sub.text
    return tid


async def test_ort_cutover_exit_flow(db, api):
    # ---- 1. export rows (what 0006 writes) -> conversion, twice
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ru", language="ru", keep_images=True)
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ky", language="ky", keep_images=False)
    first = ensure_ort_courses(db, samples=False)
    assert first.ok and first.exports_converted == 2 and first.assessments_published == 2, first
    assert first.images_dropped == 14
    before = counts(db)
    second = ensure_ort_courses(db, samples=False)
    assert second.ok and second.exports_converted == 0 and second.questions_created == 0
    assert counts(db) == before

    # ---- 2. a real student registers over HTTP
    email = f"ort_student_{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        tok = await register_and_verify(c, {"email": email, "password": "Student-pass-123", "displayName": "Айбек",
                                            "lang": "ky"})
    token = tok["access_token"]
    me = await call(token, "GET", "/auth/me")
    assert me.status_code == 200 and "role" not in me.json() and "target_score" not in me.json(), me.text
    student = db.scalar(select(User).where(User.email == email))

    # ---- 3. catalog lists both ORT courses; one-click join
    cat = await call(token, "GET", "/catalog/courses")
    assert cat.status_code == 200, cat.text
    listed = {i["id"]: i for i in cat.json()["items"]}
    cids = {lang: course_id_for(lang) for lang in ("ky", "ru")}
    for lang, cid in cids.items():
        assert str(cid) in listed, (lang, listed)
        assert listed[str(cid)]["enrollment_mode"] == "open" and listed[str(cid)]["my_enrollment"] is None
        r = await call(token, "POST", f"/courses/{cid}/join")
        assert r.status_code == 200, r.text
        assert r.json()["enrollment"]["role"] == "student" and r.json()["already_enrolled"] is False
    cat = await call(token, "GET", "/catalog/courses")
    assert all(i["my_enrollment"]["role"] == "student" for i in cat.json()["items"] if i["id"] in map(str, cids.values()))

    # ---- 4. take both exams; ORT scaled score + percentile; review
    for lang, cid in cids.items():
        aid = db.scalar(select(Assessment.id).where(Assessment.course_id == cid))
        tid = await take_exam(db, token, cid, aid, lang, WRONG[lang])
        raw = N - WRONG[lang]
        res = await call(token, "GET", f"/attempts/{tid}/result")
        assert res.status_code == 200, res.text
        rj = res.json()
        assert D(str(rj["raw_score"])) == raw and D(str(rj["points_possible"])) == N
        g = rj["grade"]
        assert g is not None and g["scheme_type"] == "piecewise_curve", rj
        scaled, pct = oracle(raw)
        assert (D(str(g["display_value"])), D(str(g["percentile"]))) == (scaled, pct)
        assert g["thresholds"] == {"golden_certificate": scaled >= 219}
        rev = await call(token, "GET", f"/attempts/{tid}/review")
        assert rev.status_code == 200, rev.text
        ritems = rev.json()["items"]
        assert len(ritems) == N and all(i["correctness"] in ("correct", "incorrect") for i in ritems)
        assert sum(1 for i in ritems if i["correctness"] == "correct") == raw
        assert all(i.get("key") for i in ritems)  # keys allowed after submit (ORT preset)

        # ---- 5. the platform admin is a teacher here and reads the staff attempt list
        admin = db.get(User, "usr_admin_01")
        enr = db.scalar(select(Enrollment).where(Enrollment.course_id == cid, Enrollment.user_id == admin.id))
        assert (enr.role, enr.state) == ("teacher", "active")
        staff = await api.call(admin, "GET", f"/courses/{cid}/assessments/{aid}/attempts")
        assert staff.status_code == 200, staff.text
        assert tid in staff.text and student.id in staff.text
        # a student cannot read the staff list
        assert (await call(token, "GET", f"/courses/{cid}/assessments/{aid}/attempts")).status_code in (403, 404)

    # ---- 6. demo teacher cannot log in (service and token level), no legacy policy left
    from fastapi import HTTPException
    import pytest

    from app.api.v1.endpoints import auth as auth_ep
    from app.core.route_inventory import ROUTE_POLICIES
    from app.schemas.user import UserLoginRequest

    for pw in ("!", "password"):
        with pytest.raises(HTTPException) as ei:
            auth_ep.login_user(UserLoginRequest.model_construct(email=DEMO_TEACHER_EMAIL, password=pw, lang="ky"), db)
        assert ei.value.status_code in (401, 403)
    demo = db.get(User, DEMO_TEACHER_ID)
    assert (await api.call(demo, "GET", "/courses")).status_code == 401
    assert "legacy" not in set(ROUTE_POLICIES.values())
    assert db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.user_id == student.id)) == 2
