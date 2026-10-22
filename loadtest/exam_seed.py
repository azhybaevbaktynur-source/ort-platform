"""Phase 3 exam load test: seed (design PHASE_3_DESIGN.md section 8.1). No secrets; run from <worktree>/backend.

  python exam_seed.py base <students>      # DB: approved teacher, published ru course, <students> enrolled students,
                                           #     hook-counter table; HTTP: import tests/fixtures/bundles/tsoomo19.zip
  (create_exam() is called by exam_load.py for every run: a fresh ort_main assessment, 5 sections x 30 items)

Env: DATABASE_URL (local scratch Postgres), LMS_STORAGE_DRIVER=db, LOCAL_UPLOAD_DIR, LT_STATE (state json, outside
the repo), LT_BASE (default http://127.0.0.1:8111). The API server must be running for the HTTP part. Tokens are
minted with the app's own create_access_token (same default dev key as the local server; no .env is involved).
Students get an unusable password hash: they never log in (login cost was measured in LOAD_TEST_PRE_PHASE3.md).
"""
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.getcwd())

import httpx  # noqa: E402

BASE = os.environ.get("LT_BASE", "http://127.0.0.1:8111") + "/api/v1"
SECTION_KEYS = ["math_1", "math_2", "analogies", "reading", "grammar"]


def token(uid: str) -> str:
    from app.core.security import create_access_token
    return create_access_token({"sub": uid})


def hdr(uid: str) -> dict:
    return {"Authorization": f"Bearer {token(uid)}"}


def seed_base(n: int) -> dict:
    from sqlalchemy import insert, text
    from app.db.session import SessionLocal
    from app.lms.core.models import utcnow
    from app.lms.enrollments.models import Enrollment
    from app.models.user import User
    from tests.lms.factories import make_course, make_user

    db = SessionLocal()
    db.execute(text("CREATE TABLE IF NOT EXISTS lt_hook_calls (id bigserial PRIMARY KEY, attempt_id uuid NOT NULL,"
                    " at timestamptz NOT NULL DEFAULT clock_timestamp())"))
    db.commit()
    teacher = make_user(db, teacher_status="approved")
    course = make_course(db, teacher, status="published", title={"ru": "Нагрузочный тест"}, languages=["ru"],
                         default_language="ru")
    now = utcnow()
    users, enrs = [], []
    for _ in range(n):
        uid = f"usr_{uuid.uuid4().hex[:12]}"
        users.append(dict(id=uid, email=f"lt3_{uid}@loadtest.example", password_hash="!unusable", role="student",
                          email_verified=True, teacher_status="none", is_platform_admin=False))
        enrs.append(dict(id=uuid.uuid4(), course_id=course.id, user_id=uid, role="student", state="active",
                         source="staff_add", activated_at=now, created_at=now, updated_at=now))
    for k in range(0, n, 1000):
        db.execute(insert(User), users[k:k + 1000])
        db.execute(insert(Enrollment), enrs[k:k + 1000])
    db.commit()
    cid, tid = str(course.id), teacher.id
    db.close()

    bundle = os.path.join(os.getcwd(), "tests", "fixtures", "bundles", "tsoomo19.zip")
    with open(bundle, "rb") as f:
        r = httpx.post(f"{BASE}/courses/{cid}/imports", headers=hdr(tid), timeout=300,
                       files={"file": ("tsoomo19.zip", f.read(), "application/octet-stream")},
                       data={"language": "ru", "exam_type": "full_main"})
    r.raise_for_status()
    bank_id = r.json()["banks"][0]["bank_id"]
    state = {"course_id": cid, "teacher_id": tid, "bank_id": bank_id, "students": [u["id"] for u in users]}
    json.dump(state, open(os.environ["LT_STATE"], "w"))
    print(f"seeded {n} students, course {cid}, bank {bank_id}")
    return state


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def create_exam(state: dict, *, t0: float, ramp_s: int, section_s: int, last_min_s: int, title: str) -> dict:
    """Build and publish a fresh ort_main assessment (forward-only, shuffled choices). Sections 1-4 are timed
    `section_s`; section 5 runs to `available_until` = t0 + ramp + 4*section_s + last_min_s, so every attempt has
    the same deadline (one national exam window) and the submit burst happens at that deadline."""
    cid, tid, bank = state["course_id"], state["teacher_id"], state["bank_id"]
    h = hdr(tid)
    until = t0 + ramp_s + 4 * section_s + last_min_s
    with httpx.Client(base_url=BASE, headers=h, timeout=120) as c:
        r = c.post(f"/courses/{cid}/assessments", json={"title": {"ru": title}, "preset": "ort_main",
                                                         "languages": ["ru"]})
        r.raise_for_status()
        a = r.json()
        aid = a["id"]
        base = f"/courses/{cid}/assessments/{aid}"
        assert [s["key"] for s in a["sections"]] == SECTION_KEYS, a["sections"]
        for s in a["sections"]:
            r = c.post(f"{base}/sections/{s['id']}/items/bulk",
                       json={"bank_id": bank, "filter": {"section": s["key"]}, "group_passages": True})
            r.raise_for_status()
            assert r.json()["added"] == 30, r.text
            limit = section_s if s["key"] != "grammar" else 4 * 3600
            r = c.patch(f"{base}/sections/{s['id']}", json={"time_limit_s": limit})
            r.raise_for_status()
        rev = c.get(base).json()["draft_rev"]
        r = c.patch(base, json={"draft_rev": rev, "shuffle_choices": True, "results_policy": "after_submit",
                                "available_from": _iso(t0 - 120), "available_until": _iso(until)})
        r.raise_for_status()
        r = c.post(f"{base}/validate")
        assert r.json()["errors"] == [], r.text
        r = c.post(f"{base}/publish", json={"confirm": True})
        r.raise_for_status()
        v = r.json()["version"]
        assert v["item_count"] == 150, v
    return {"assessment_id": aid, "version_id": v["id"], "t0": t0, "until": until, "ramp_s": ramp_s,
            "section_s": section_s, "last_min_s": last_min_s}


if __name__ == "__main__":
    if sys.argv[1] == "base":
        seed_base(int(sys.argv[2]))
    else:
        st = json.load(open(os.environ["LT_STATE"]))
        print(create_exam(st, t0=time.time() + 5, ramp_s=60, section_s=60, last_min_s=60, title="smoke"))
