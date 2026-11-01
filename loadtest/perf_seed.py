"""Phase 11 perf seed (PHASE_11_DESIGN 6.1). LOCAL SCRATCH POSTGRES ONLY; refuses any other host. No secrets.

  cd backend && DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:<port>/<db> LMS_STORAGE_DRIVER=db \
      LOCAL_UPLOAD_DIR=<scratch>/up LT_STATE=<scratch>/perf_state.json python ../loadtest/perf_seed.py

Run `alembic upgrade head` first. Data, deterministic (seed 11):
  6,000 students (+ one heavy one), 200 courses in a school with 5 departments, 5 real `ort_main` exams of 150 items
  published through the API from tests/fixtures/bundles/tsoomo19.zip (one holding 4,000 attempts, a national exam), 20
  real practice sets, 6,000 exam attempts = 900k attempt_items, 50k practice attempts of 10 items (500k more),
  200k grade events, modules with progress, a test student in every course plus retired ones with attempts on the
  biggest exam. Everything except the published content is bulk loaded with COPY, then VACUUM ANALYZE.

Rows are shaped like real rows but not produced by the engine: the numbers measure queries, not grading.
"""
import csv
import io
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STUDENTS = int(os.environ.get("PERF_STUDENTS", 6000))
COURSES = int(os.environ.get("PERF_COURSES", 200))
PRACTICE_ATTEMPTS = int(os.environ.get("PERF_PRACTICE", 50000))
GRADE_EVENTS = int(os.environ.get("PERF_GRADE_EVENTS", 200000))
EXAM_SIZES = [round(STUDENTS * f) for f in (2 / 3, 1 / 12, 1 / 12, 1 / 12, 1 / 12)]  # 4000 + 4 * 500
PRACTICE_SETS = 20
HEAVY_PRACTICE = 300
ASSIGNMENTS_PER_COURSE = 8
MODULES_PER_COURSE = 6
ITEMS_PER_MODULE = 3

rng = random.Random(11)
NOW = datetime.now(timezone.utc)


def guard() -> str:
    from sqlalchemy.engine import make_url

    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() != "postgresql" or url.host not in ("127.0.0.1", "localhost"):
        sys.exit("perf_seed: local scratch Postgres only")
    return str(url.database)


def ago(**kw) -> str:
    return (NOW - timedelta(**kw)).isoformat()


def j(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


class Copier:
    """COPY rows into a table, flushing every 100k rows."""

    def __init__(self, conn, table: str, cols: list):
        self.conn, self.table, self.cols = conn, table, cols
        self.buf = io.StringIO()
        self.w = csv.writer(self.buf)
        self.n = self.total = 0

    def add(self, *row):
        self.w.writerow(row)
        self.n += 1
        if self.n >= 100_000:
            self.flush()

    def flush(self):
        if self.n:
            self.buf.seek(0)
            with self.conn.cursor() as cur:
                cur.copy_expert(f"COPY {self.table} ({','.join(self.cols)}) FROM STDIN WITH (FORMAT csv)", self.buf)
            self.total += self.n
            self.buf, self.n = io.StringIO(), 0
            self.w = csv.writer(self.buf)
        return self.total


def real_content(app, teacher_token_user: str, course_id: str, db) -> dict:
    """Bundle import, 5 exams and the practice sets through the real API."""
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    import exam_seed

    class Client(TestClient):
        def __init__(self, base_url=None, headers=None, timeout=None):
            super().__init__(app, base_url=base_url, headers=headers)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

    api = "http://perf.local/api/v1"
    exam_seed.BASE = api
    exam_seed.httpx = SimpleNamespace(Client=Client)
    h = exam_seed.hdr(teacher_token_user)
    c = Client(base_url=api, headers=h)
    bundle = os.path.join(os.getcwd(), "tests", "fixtures", "bundles", "tsoomo19.zip")
    with open(bundle, "rb") as f:
        r = c.post(f"/courses/{course_id}/imports", files={"file": ("tsoomo19.zip", f.read(), "application/octet-stream")},
                   data={"language": "ru", "exam_type": "full_main"})
    assert r.status_code == 200, r.text[:2000]
    bank_id = r.json()["banks"][0]["bank_id"]
    state = {"course_id": course_id, "teacher_id": teacher_token_user, "bank_id": bank_id}
    exams = []
    for i in range(5):
        # stays open a year: seeded attempts are already final; the window only matters to `home`
        e = exam_seed.create_exam(state, t0=time.time(), ramp_s=365 * 86400, section_s=1500, last_min_s=1500,
                                  title=f"ОРТ {i + 1}")
        exams.append(e)
    sets = []
    sections = ["math_2", "analogies", "grammar"]
    for i in range(PRACTICE_SETS):
        r = c.post(f"/courses/{course_id}/practice", json={
            "title": {"ru": f"Практика {i + 1}"}, "languages": ["ru"],
            "blocks": [{"bank_id": bank_id, "count": 10, "section": sections[i % 3]}]})
        r.raise_for_status()
        sets.append(r.json()["id"])

    from app.lms.assessments.models import Assessment, AssessmentVersion
    from app.lms.assignments.models import Assignment
    from app.lms.content.models import QuestionVersion

    def plan(aid):
        a = db.get(Assessment, uuid.UUID(str(aid)))
        v = db.get(AssessmentVersion, a.published_version_id)
        asg = db.execute(select(Assignment.id).where(Assignment.assessment_id == a.id)).scalar()
        return dict(id=str(a.id), version_id=str(v.id), slots=v.snapshot["slots"]["ru"], assignment_id=asg,
                    points=float(v.points_possible),
                    sections=sorted({int(s["section_pos"]) for s in v.snapshot["slots"]["ru"]}))

    exam_plans = [plan(e["assessment_id"]) for e in exams]
    set_plans = [plan(s) for s in sets]
    qvs = {}
    for qid, typ, data in db.execute(select(QuestionVersion.id, QuestionVersion.type, QuestionVersion.data)):
        qvs[str(qid)] = (typ, [str(ch["id"]) for ch in (data.get("choices") or [])])
    return dict(bank_id=bank_id, exams=exam_plans, sets=set_plans, qvs=qvs)


def response_for(qv, ok: bool) -> dict:
    typ, ids = qv
    if typ == "comparison":
        return {"choice": "A" if ok else rng.choice("BCD")}
    if typ == "true_false":
        return {"value": ok}
    return {"choice_id": (ids[0] if ok else rng.choice(ids[1:] or ids)) if ids else "A"}


def attempt_rows(att, item, sec, plan: dict, *, course_id, enrollment_id, user_id, attempt_no, submitted, practice,
                 skill):
    """One graded attempt with all its items and sections. Returns (attempt id, raw score)."""
    aid = uuid.uuid4()
    started = submitted - timedelta(minutes=rng.randint(10, 170))
    score = 0.0
    drawn = []
    for s in plan["slots"]:  # a pick slot draws `count` questions from its pool, every one with the same slot number
        qvs = [e["qv"] for e in rng.sample(s["pool"], s["count"])] if s.get("kind") == "pick" else [s["qv"]]
        drawn += [(s, q) for q in qvs]
    n = len(drawn)
    step = (submitted - started) / max(n, 1)
    for pos, (s, qv_id) in enumerate(drawn, start=1):
        roll = rng.random()
        unanswered = roll > 0.93
        ok = not unanswered and roll < skill
        pts = float(s.get("points") or 1)
        if ok:
            score += pts
        at = started + step * pos
        item.add(aid, pos, s["section_pos"], s["slot"], qv_id,
                 None if unanswered else j(response_for(QV[qv_id], ok)), "false",
                 None if unanswered else at.isoformat(),
                 "unanswered" if unanswered else ("correct" if ok else "incorrect"), pts if ok else 0)
    for p in plan["sections"]:
        sec.add(aid, p, started.isoformat(), submitted.isoformat())
    att.add(aid, plan["id"], plan["version_id"], course_id, enrollment_id, user_id, attempt_no, "ru", "false",
            "true" if practice else "false", "graded", started.isoformat(), n, submitted.isoformat(), "manual",
            round(score, 2), plan["points"], submitted.isoformat(), started.isoformat(), submitted.isoformat())
    return aid, score


QV: dict = {}
ATT = ["id", "assessment_id", "assessment_version_id", "course_id", "enrollment_id", "user_id", "attempt_no",
       "language", "is_preview", "is_practice", "status", "started_at", "item_count", "submitted_at", "submit_reason",
       "raw_score", "points_possible", "graded_at", "created_at", "updated_at"]
ITEM = ["attempt_id", "position", "section_pos", "slot", "question_version_id", "response", "flagged", "answered_at",
        "correctness", "score"]
SEC = ["attempt_id", "section_pos", "started_at", "closed_at"]


def main():
    dbname = guard()
    t00 = time.time()
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.db.session import SessionLocal, engine
    from app.lms.organizations.models import Organization, OrganizationMember, path_segment
    from app.main import app
    from tests.lms.factories import make_course, make_user

    with TestClient(app):  # lifespan: seeds system schemes and the ORT courses, as in production
        db = SessionLocal()
        teacher = make_user(db, teacher_status="approved", display_name="Perf teacher")
        org_admin = make_user(db, teacher_status="approved", display_name="Perf org admin")
        root_id, dept_ids = uuid.uuid4(), [uuid.uuid4() for _ in range(5)]
        root_path = path_segment(root_id)
        db.add(Organization(id=root_id, slug=f"perf-{root_id.hex[:8]}", name="Perf school", path=root_path,
                            kind="school", status="active"))
        db.flush()
        for i, d in enumerate(dept_ids):
            db.add(Organization(id=d, slug=f"perf-d{i}-{d.hex[:8]}", name=f"Department {i + 1}", parent_id=root_id,
                                path=f"{root_path}/{path_segment(d)}", kind="department", status="active", depth=1))
        db.flush()
        db.add(OrganizationMember(organization_id=root_id, user_id=org_admin.id, role="org_admin", state="active"))
        db.add(OrganizationMember(organization_id=root_id, user_id=teacher.id, role="teacher", state="active"))
        db.commit()
        ort = make_course(db, teacher, status="published", title={"ru": "ОРТ нагрузка"}, languages=["ru"],
                          default_language="ru", organization_id=root_id, template_key="ort", template_version=1)
        ort_id, teacher_id, org_admin_id = str(ort.id), teacher.id, org_admin.id
        content = real_content(app, teacher_id, ort_id, db)
        QV.update(content["qvs"])
        db.commit()
        db.close()
    print(f"content ready {time.time() - t00:.0f}s", flush=True)

    raw = engine.raw_connection()
    conn = raw.driver_connection
    conn.autocommit = False

    # ---- users
    students = [f"usr_{uuid.uuid4().hex[:12]}" for _ in range(STUDENTS + 1)]
    heavy, typical = students[-1], students[STUDENTS // 2]
    testers = [f"usr_{uuid.uuid4().hex[:12]}" for _ in range(COURSES + 30)]
    teachers = [f"usr_{uuid.uuid4().hex[:12]}" for _ in range(20)]
    u = Copier(conn, "users", ["id", "email", "password_hash", "display_name", "email_verified", "email_code_attempts",
                               "teacher_status", "is_platform_admin", "consent_state", "created_at"])
    now_naive = NOW.replace(tzinfo=None).isoformat()
    for s in students:
        u.add(s, f"{s}@perf.example", "!unusable", f"Студент {s[-5:]}", "true", 0, "none", "false",
              "ok" if rng.random() < 0.3 else "legacy", now_naive)
    for t in testers:
        u.add(t, f"{t}@test-student.invalid", "!unusable", "Test student", "true", 0, "none", "false", "exempt", now_naive)
    for t in teachers:
        u.add(t, f"{t}@perf.example", "!unusable", f"Учитель {t[-5:]}", "true", 0, "approved", "false", "legacy", now_naive)
    u.flush()

    # ---- courses, modules, assignments
    course_ids = [ort_id] + [str(uuid.uuid4()) for _ in range(COURSES - 1)]
    TS = NOW.isoformat()
    cc = Copier(conn, "courses", ["id", "created_at", "updated_at", "owner_id", "title", "languages", "default_language",
                                  "status", "visibility", "enrollment_mode", "join_code", "settings", "organization_id"])
    for i, cid in enumerate(course_ids[1:], start=1):
        cc.add(cid, ago(days=i % 300), TS, rng.choice(teachers), j({"ru": f"Курс {i}"}), j(["ru"]), "ru",
               "draft" if i % 40 == 0 else "published", "private", "invite_code", f"P{uuid.uuid4().hex[:7].upper()}", "{}",
               dept_ids[i % 5])
    cc.flush()

    asm = Copier(conn, "assessments", ["id", "created_at", "updated_at", "course_id", "title", "languages", "position",
                                       "status", "published_version_id", "last_version_no", "results_policy", "due_at",
                                       "allowed_attempts", "published_at", "created_by_id"])
    ver = Copier(conn, "assessment_versions", ["id", "assessment_id", "kind", "version_no", "snapshot", "content_hash",
                                               "draft_rev", "item_count", "points_possible", "created_at"])
    asg = Copier(conn, "assignments", ["id", "created_at", "updated_at", "course_id", "kind", "assessment_id", "title",
                                       "position", "published", "due_at", "points_possible"])
    mods = Copier(conn, "course_modules", ["id", "created_at", "updated_at", "course_id", "title", "position", "published"])
    mit = Copier(conn, "module_items", ["id", "created_at", "updated_at", "module_id", "position", "kind", "url", "published",
                                        "title_override"])
    req = Copier(conn, "item_completion_requirements", ["item_id", "type"])
    course_assignments, course_modules = {}, {}
    empty = j({"schema": 1, "languages": ["ru"], "sections": [], "slots": {"ru": []}})
    # ver.assessment_id <-> assessments.published_version_id reference each other: versions go in first, FK deferred below
    with conn.cursor() as cur:
        cur.execute("SET session_replication_role = replica")  # scratch bulk load: no FK checks, no triggers
    for ci, cid in enumerate(course_ids):
        rows = []
        if cid != ort_id:
            for k in range(ASSIGNMENTS_PER_COURSE):
                aid = uuid.uuid4()
                past = k < ASSIGNMENTS_PER_COURSE - 2
                due = ago(days=rng.randint(1, 200)) if past else (NOW + timedelta(days=rng.randint(1, 60))).isoformat()
                if k % 4 == 0:
                    q, v = uuid.uuid4(), uuid.uuid4()
                    asm.add(q, TS, TS, cid, j({"ru": f"Тест {k}"}), j(["ru"]), k + 1, "published", v, 1, "after_submit",
                            due, 3, TS, teachers[0])
                    ver.add(v, q, "published", 1, empty, uuid.uuid4().hex, 1, 0, 0, TS)
                    asg.add(aid, TS, TS, cid, "quiz", q, j({"ru": f"Тест {k}"}), k + 1, "true", None, 10)
                    rows.append((aid, q))
                else:
                    asg.add(aid, TS, TS, cid, "text" if k % 2 else "none", None, j({"ru": f"Задание {k}"}), k + 1, "true",
                            due, 10)
                    rows.append((aid, None))
            course_assignments[cid] = rows
        ms = []
        for m in range(MODULES_PER_COURSE):
            mid = uuid.uuid4()
            mods.add(mid, TS, TS, cid, j({"ru": f"Модуль {m + 1}"}), m + 1, "true")
            ms.append(mid)
            for p in range(ITEMS_PER_MODULE):
                item_id = uuid.uuid4()
                mit.add(item_id, TS, TS, mid, p + 1, "url", "https://example.org/x", "true", j({"ru": f"Ссылка {p + 1}"}))
                req.add(item_id, "view")
        course_modules[cid] = ms
    for x in (asm, ver, asg, mods, mit, req):
        x.flush()

    # ---- enrollments
    enr = Copier(conn, "enrollments", ["id", "created_at", "updated_at", "course_id", "user_id", "role", "state", "source",
                                       "activated_at", "is_test_student"])
    enrollment_of = {}

    def add_enr(cid, uid, role="student", state="active", source="staff_add", test=False):
        eid = uuid.uuid4()
        enr.add(eid, TS, TS, cid, uid, role, state, source, TS, "true" if test else "false")
        enrollment_of[(cid, uid)] = eid
        return eid

    small = course_ids[1:]
    members = {cid: [] for cid in course_ids}
    for s in students:
        add_enr(ort_id, s)
        members[ort_id].append(s)
        picks = small if s == heavy else rng.sample(small, rng.randint(1, 4))
        if s == heavy:
            picks = rng.sample(small, min(12, len(small)))
        for cid in picks:
            add_enr(cid, s)
            members[cid].append(s)
    for i, cid in enumerate(course_ids):
        add_enr(cid, testers[i], test=True)
    retired = testers[COURSES:]
    for t in retired:
        add_enr(ort_id, t, state="removed", test=True)
    for cid in small:
        add_enr(cid, rng.choice(teachers), role="teacher", source="owner")
    enr.flush()

    # ---- module progress
    mp = Copier(conn, "module_progress", ["enrollment_id", "module_id", "state", "evaluated_rules_version", "evaluated_at"])
    for cid, ids in members.items():
        for uid in ids + [testers[course_ids.index(cid)]]:
            eid = enrollment_of[(cid, uid)]
            done = rng.randint(0, MODULES_PER_COURSE)
            for k, mid in enumerate(course_modules[cid]):
                st = "completed" if k < done else ("started" if k == done else "locked")
                mp.add(eid, mid, st, 1, TS)
    mp.flush()
    print(f"structure ready {time.time() - t00:.0f}s", flush=True)

    # ---- exam attempts
    att, item, sec = Copier(conn, "attempts", ATT), Copier(conn, "attempt_items", ITEM), Copier(conn, "attempt_sections", SEC)
    sub = Copier(conn, "submissions", ["id", "created_at", "updated_at", "course_id", "assessment_id", "assignment_id",
                                       "enrollment_id", "user_id", "state", "kept_attempt_id", "kept_policy",
                                       "attempts_counted", "raw_points", "points_possible", "effective_points",
                                       "display_value", "released_at", "computed_at", "late_seconds"])
    gev = Copier(conn, "grade_events", ["id", "submission_id", "course_id", "actor_id", "event", "attempt_id", "created_at"])
    sub_ids = []

    pool = list(students[:-1])
    rng.shuffle(pool)
    offset = 0
    for e, size in zip(content["exams"], EXAM_SIZES):
        takers = pool[offset:offset + size] if offset + size <= len(pool) else rng.sample(pool, size)
        offset += size
        takers = takers[:-1] + [heavy]  # the heavy student sits every exam; total stays EXAM_SIZES
        day = rng.randint(30, 300)
        for uid in takers:
            eid = enrollment_of[(ort_id, uid)]
            submitted = NOW - timedelta(days=day, minutes=rng.randint(0, 600))
            aid, score = attempt_rows(att, item, sec, e, course_id=ort_id, enrollment_id=eid, user_id=uid, attempt_no=1,
                                      submitted=submitted, practice=False, skill=rng.uniform(0.3, 0.9))
            sid = uuid.uuid4()
            sub.add(sid, TS, TS, ort_id, e["id"], e["assignment_id"], eid, uid, "graded", aid, "highest", 1,
                    score, e["points"], score, score, submitted.isoformat(), TS, 0)
            sub_ids.append((sid, ort_id, aid))
    # test students mixed in: retired ones plus the active one have final attempts on the biggest exam
    big = content["exams"][0]
    for uid in retired + [testers[0]]:
        attempt_rows(att, item, sec, big, course_id=ort_id, enrollment_id=enrollment_of[(ort_id, uid)], user_id=uid,
                     attempt_no=1, submitted=NOW - timedelta(days=5), practice=False, skill=0.99)
    print(f"exam attempts ready {time.time() - t00:.0f}s", flush=True)

    # ---- practice attempts: mostly a few per student, a long tail; 30 % older than a year
    sets = content["sets"]
    made, counters = 0, {}

    def practice(uid, s):
        nonlocal made
        key = (s["id"], uid)
        counters[key] = counters.get(key, 0) + 1
        days = rng.randint(366, 700) if rng.random() < 0.3 else rng.randint(1, 365)
        attempt_rows(att, item, sec, s, course_id=ort_id, enrollment_id=enrollment_of[(ort_id, uid)], user_id=uid,
                     attempt_no=counters[key], submitted=NOW - timedelta(days=days, minutes=rng.randint(0, 1000)),
                     practice=True, skill=rng.uniform(0.4, 0.9))
        made += 1

    for _ in range(HEAVY_PRACTICE):
        practice(heavy, rng.choice(sets))
    weights = [1 / (i + 1) ** 0.5 for i in range(len(students))]  # the busiest around 320, the median around 6
    drawn = rng.choices(students, weights=weights, k=PRACTICE_ATTEMPTS - HEAVY_PRACTICE)
    for uid in drawn:
        practice(uid, rng.choice(sets))
    for x in (att, item, sec):
        x.flush()
    print(f"practice attempts ready {time.time() - t00:.0f}s", flush=True)

    # ---- submissions of the small courses
    for cid in small:
        for aid, quiz in course_assignments[cid]:
            for uid in members[cid]:
                r = rng.random()
                if r > 0.78:
                    continue
                st = "graded" if r < 0.70 else ("pending_review" if r < 0.75 else "excused")
                pts = round(rng.uniform(0, 10), 2) if st == "graded" else None
                sid = uuid.uuid4()
                sub.add(sid, TS, TS, cid, quiz, aid, enrollment_of[(cid, uid)], uid, st, None, "highest", 1, pts, 10, pts,
                        pts, TS if st == "graded" else None, TS, rng.choice((0, 0, 0, 3600)))
                sub_ids.append((sid, cid, None))
    sub.flush()

    # ---- grade events, append-only: released for all, then regraded until the target
    k = 0
    events = ("released", "regraded")
    while k < GRADE_EVENTS:
        sid, cid, aid = sub_ids[k % len(sub_ids)]
        gev.add(uuid.uuid4(), sid, cid, teacher_id, events[min(k // len(sub_ids), 1)], aid, ago(days=k % 300))
        k += 1
    gev.flush()
    with conn.cursor() as cur:
        cur.execute("SET session_replication_role = DEFAULT")
    conn.commit()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("VACUUM ANALYZE")
        counts = {}
        for t in ("users", "courses", "enrollments", "assessments", "attempts", "attempt_items", "attempt_sections",
                  "submissions", "grade_events", "module_progress"):
            cur.execute(f"SELECT count(*) FROM {t}")
            counts[t] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM attempts WHERE is_practice")
        counts["practice_attempts"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM enrollments WHERE is_test_student")
        counts["test_enrollments"] = cur.fetchone()[0]
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        counts["database_size"] = cur.fetchone()[0]
    raw.close()
    state = dict(database=dbname, ort_course_id=ort_id, teacher_id=teacher_id, org_admin_id=org_admin_id,
                 org_id=str(root_id), department_id=str(dept_ids[0]), bank_id=content["bank_id"],
                 exams=[dict(id=e["id"], version_id=e["version_id"]) for e in content["exams"]],
                 practice_sets=[dict(id=s["id"], version_id=s["version_id"]) for s in sets],
                 heavy_student=heavy, typical_student=typical, small_course_id=small[1], students=students[:-1],
                 counts=counts, seeded_at=NOW.isoformat(), seconds=round(time.time() - t00))
    json.dump(state, open(os.environ["LT_STATE"], "w"))
    print(json.dumps(counts), f"{time.time() - t00:.0f}s", flush=True)


if __name__ == "__main__":
    main()
