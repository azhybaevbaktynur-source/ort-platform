"""Phase 11 EXPLAIN review (PHASE_11_DESIGN 6.1). LOCAL SCRATCH POSTGRES ONLY; refuses any other host.

  cd backend && DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:<port>/<db> LMS_STORAGE_DRIVER=db \
      LOCAL_UPLOAD_DIR=<scratch>/up LT_STATE=<scratch>/perf_state.json PERF_OUTPUTS=<scratch>/outputs_<label> \
      python ../loadtest/explain_review.py run <label>
  python ../loadtest/explain_review.py compare <outputs dir a> <outputs dir b>

Runs the real service functions, so the SQL reviewed is always the SQL the service sends: each case runs twice to warm
the buffers and Python caches, then a third time with a cursor listener. Every SELECT captured is replayed with
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) and its bound parameters. A statement fails when it takes more than 200 ms or
when a Seq Scan on attempts, attempt_items, enrollments or submissions reads more than 1 % of the table's rows.
Results: loadtest/results/explain_phase11/<label>/ (summary.json, plans of statements >= 20 ms or failing).
With PERF_OUTPUTS the JSON answer of each case is written there, to compare two runs (before and after a query change).
Each statement is replayed three times and the median kept. PERF_PG_SET=random_page_cost=1.1 changes the replays only.
"""
import json
import os
import sys
import time
import uuid
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.getcwd())

HERE = os.path.dirname(os.path.abspath(__file__))
LIMIT_MS = 200
SEQ_PCT = 1.0
WATCHED = {"attempts", "attempt_items", "enrollments", "submissions"}
SLOW_PLAN_MS = 20
REPLAYS = 3
# Reviewed exceptions (docs/phases/PHASE_11_EXPLAIN.md): the design's rule still reports them; each is named by case and
# failure text, so a new failure elsewhere stays a FAIL. These queries read the rows because the answer needs the rows.
ACCEPTED = {
    "statistics.refresh_compute_4000": ("ms >",),
    "statistics.refresh_compute_500": ("ms >",),
    "analytics.practice_page": ("Seq Scan attempts",),
    "org.overview": ("Seq Scan enrollments", "Seq Scan submissions", "ms >"),
    "retention.dry_run": ("Seq Scan attempts", "ms >"),
}
# wall-clock fields that legitimately differ between two runs
VOLATILE = {"computed_at", "server_now"}


def guard():
    from sqlalchemy.engine import make_url

    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() != "postgresql" or url.host not in ("127.0.0.1", "localhost"):
        sys.exit("explain_review: local scratch Postgres only")


def plain(v):
    if hasattr(v, "model_dump"):
        return plain(v.model_dump(mode="json"))
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items() if k not in VOLATILE}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, (uuid.UUID, datetime, date, Decimal)):
        return str(v)
    return v


def walk(node):
    yield node
    for child in node.get("Plans", []) or []:
        yield from walk(child)


def cases(db, st):
    """(name, callable) in report order; every callable takes the session."""
    from sqlalchemy import select

    from app.lms.analytics import org_service, service as analytics
    from app.lms.courses.models import Course
    from app.lms.enrollments.models import Enrollment
    from app.lms.home import service as home
    from app.lms.organizations.models import Organization
    from app.lms.practice import retention
    from app.lms.progress import service as progress
    from app.lms.statistics import compute as stats_compute, service as stats
    from app.lms.core import clock
    from app.models.user import User

    def U(x):
        return uuid.UUID(str(x))

    ort = db.get(Course, U(st["ort_course_id"]))
    small = db.get(Course, U(st["small_course_id"]))
    org = db.get(Organization, U(st["org_id"]))
    big, small_exam = st["exams"][0], st["exams"][1]
    heavy, typical = st["heavy_student"], st["typical_student"]

    def eid(uid):
        return db.execute(select(Enrollment.id).where(Enrollment.course_id == ort.id, Enrollment.user_id == uid)).scalar()

    now = clock.now()
    heavy_eid, typical_eid = eid(heavy), eid(typical)

    def page2(db):
        first = progress.mistakes(db, ort, heavy, status="open", cursor=None, limit=25, now=now)
        return progress.mistakes(db, ort, heavy, status="open", cursor=first.next_cursor, limit=25, now=now)

    return [
        ("statistics.summary_fresh", lambda d: stats.summary(d, ort, U(big["id"]), None)),
        ("statistics.item_page", lambda d: stats.item_page(d, ort, U(big["id"]), None, sort="hardest", cursor=None,
                                                           limit=25)),
        ("statistics.refresh_compute_4000", lambda d: stats_compute.compute(d, U(big["version_id"]))),
        ("statistics.refresh_compute_500", lambda d: stats_compute.compute(d, U(small_exam["version_id"]))),
        ("analytics.overview_6000", lambda d: analytics.overview(d, ort)),
        ("analytics.overview_small", lambda d: analytics.overview(d, small)),
        ("analytics.modules_page", lambda d: analytics.modules_page(d, ort, None, 25)),
        ("analytics.assignments_page", lambda d: analytics.assignments_page(d, ort, None, 25)),
        ("analytics.quizzes_page", lambda d: analytics.quizzes_page(d, ort, False, None, 25)),
        ("analytics.practice_page", lambda d: analytics.quizzes_page(d, ort, True, None, 25)),
        ("org.overview", lambda d: org_service.overview(d, org)),
        ("org.courses_page", lambda d: org_service.courses_page(d, org, None, None, 25)),
        ("org.courses_page_department", lambda d: org_service.courses_page(d, org, U(st["department_id"]), None, 25)),
        ("org.quizzes_page", lambda d: org_service.quizzes_page(d, org, None, 25)),
        ("progress.mistakes_open_heavy", lambda d: progress.mistakes(d, ort, heavy, status="open", cursor=None, limit=25,
                                                                     now=now)),
        ("progress.mistakes_fixed_heavy", lambda d: progress.mistakes(d, ort, heavy, status="fixed", cursor=None,
                                                                      limit=25, now=now)),
        ("progress.mistakes_page2_heavy", page2),
        ("progress.mistakes_open_typical", lambda d: progress.mistakes(d, ort, typical, status="open", cursor=None,
                                                                       limit=25, now=now)),
        ("progress.progress_heavy", lambda d: progress.progress(d, ort, heavy, heavy_eid, now=now)),
        ("progress.progress_typical", lambda d: progress.progress(d, ort, typical, typical_eid, now=now)),
        ("home.home_heavy", lambda d: home.home(d, db.get(User, heavy))),
        ("home.home_typical", lambda d: home.home(d, db.get(User, typical))),
        ("retention.dry_run", lambda d: retention.sweep(d, days=365, apply=False)),
    ]


def review(raw_conn, statements, rows_of):
    """EXPLAIN each captured SELECT. Returns [{sql, ms, failures, plan}]."""
    out = []
    seen = set()
    applied = []
    with raw_conn.cursor() as cur:
        for sql, params, wall_ms in statements:
            if sql.startswith("SET LOCAL"):  # the service's own planner setting holds for the rest of the case
                cur.execute(sql.replace("SET LOCAL", "SET", 1), params)
                applied.append(sql.split()[2])
                continue
            head = sql.lstrip()[:6].upper()
            if head != "SELECT" and not head.startswith("WITH"):
                continue
            key = (sql, repr(params))
            if key in seen:
                continue
            seen.add(key)
            docs = []
            for _ in range(REPLAYS):
                cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
                docs.append(cur.fetchone()[0][0])
            doc = sorted(docs, key=lambda d: d["Execution Time"])[len(docs) // 2]  # median: the machine is shared
            ms = doc["Execution Time"]
            planning = doc["Planning Time"]
            failures = []
            if ms > LIMIT_MS:
                failures.append(f"{ms:.0f} ms > {LIMIT_MS} ms")
            for node in walk(doc["Plan"]):
                rel = node.get("Relation Name")
                if node["Node Type"] == "Seq Scan" and rel in WATCHED:
                    loops = max(node.get("Actual Loops", 1), 1)
                    read = (node.get("Actual Rows", 0) + node.get("Rows Removed by Filter", 0)) * loops
                    pct = 100.0 * read / max(rows_of[rel], 1)
                    if pct > SEQ_PCT:
                        failures.append(f"Seq Scan {rel}: {read:.0f} rows read, {pct:.1f} %")
            shared = doc["Plan"].get("Shared Hit Blocks", 0), doc["Plan"].get("Shared Read Blocks", 0)
            out.append(dict(sql=sql, ms=round(ms, 2), planning_ms=round(planning, 2), wall_ms=round(wall_ms, 2),
                            hit_blocks=shared[0], read_blocks=shared[1], failures=failures,
                            jit_ms=round(doc.get("JIT", {}).get("Timing", {}).get("Total", 0), 1), plan=doc))
        for name in applied:
            cur.execute(f"RESET {name}")
    return out


def run(label):
    guard()
    from sqlalchemy import event, text

    from app.db.session import SessionLocal, engine

    state = json.load(open(os.environ["LT_STATE"]))
    outdir = os.path.join(HERE, "results", "explain_phase11", label)
    os.makedirs(outdir, exist_ok=True)
    answers = os.environ.get("PERF_OUTPUTS")
    if answers:
        os.makedirs(answers, exist_ok=True)

    with engine.connect() as c:
        rows_of = {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in WATCHED}

    captured = []

    def before(conn, cursor, statement, parameters, context, executemany):
        context._perf_t0 = time.perf_counter()

    def after(conn, cursor, statement, parameters, context, executemany):
        if not executemany and captured is not None and capturing[0]:
            captured.append((statement, parameters, (time.perf_counter() - context._perf_t0) * 1000))

    capturing = [False]
    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "after_cursor_execute", after)

    raw = engine.raw_connection()
    raw.driver_connection.autocommit = True
    setting = os.environ.get("PERF_PG_SET")  # e.g. random_page_cost=1.1: replays only, to see how plans react
    if setting:
        name, value = setting.split("=")
        with raw.driver_connection.cursor() as cur:
            cur.execute(f"SET {name} = %s", (value,))

    summary = []
    db = SessionLocal()
    for name, fn in cases(db, state):
        for _ in range(2):  # warm buffers and Python caches
            fn(db)
            db.rollback()
        captured.clear()
        capturing[0] = True
        t0 = time.perf_counter()
        answer = fn(db)
        total_ms = (time.perf_counter() - t0) * 1000
        capturing[0] = False
        db.rollback()
        if answers:
            with open(os.path.join(answers, name + ".json"), "w") as f:
                json.dump(plain(answer), f, sort_keys=True, ensure_ascii=False, indent=0)
        reviewed = review(raw.driver_connection, list(captured), rows_of)
        failed = [f for r in reviewed for f in r["failures"]]
        worst = max((r["ms"] for r in reviewed), default=0)
        allowed = ACCEPTED.get(name, ())
        open_failures = [f for f in failed if not any(a in f for a in allowed)]
        verdict = "FAIL" if open_failures else ("accepted" if failed else "ok")
        summary.append(dict(case=name, statements=len(captured), explained=len(reviewed), service_ms=round(total_ms, 1),
                            sql_ms=round(sum(r["ms"] for r in reviewed), 1), worst_statement_ms=worst,
                            verdict=verdict, failures=failed))
        keep = [dict(r) for r in reviewed if r["failures"] or r["ms"] >= SLOW_PLAN_MS]
        if keep:
            with open(os.path.join(outdir, name + ".json"), "w") as f:
                json.dump(keep, f, indent=0, default=str)
        else:
            stale = os.path.join(outdir, name + ".json")
            if os.path.exists(stale):
                os.remove(stale)
        print(f"{name:36s} {verdict:8s} service {total_ms:8.1f} ms  sql {summary[-1]['sql_ms']:8.1f} ms  "
              f"worst {worst:8.1f} ms  stmts {len(captured):3d}  {'; '.join(failed)[:150]}", flush=True)
    db.close()
    raw.close()
    with open(os.path.join(outdir, "summary.json"), "w") as f:
        json.dump(dict(label=label, limits=dict(ms=LIMIT_MS, seq_pct=SEQ_PCT), counts=state["counts"], rows=rows_of,
                       load_average=[round(x, 1) for x in os.getloadavg()], setting=setting, cases=summary), f, indent=1)
    print("failed:", sum(1 for s in summary if s["verdict"] == "FAIL"), "of", len(summary))


def compare(a, b):
    bad = 0
    names = sorted(set(os.listdir(a)) | set(os.listdir(b)))
    for n in names:
        pa, pb = os.path.join(a, n), os.path.join(b, n)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            print("missing", n)
            bad += 1
            continue
        if json.load(open(pa)) != json.load(open(pb)):
            print("DIFFERENT", n)
            bad += 1
    print(f"{len(names) - bad} of {len(names)} equal")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    if sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3])
    else:
        run(sys.argv[2])
