"""Phase 11 mixed load (PHASE_11_DESIGN 6.2): home, notebook, statistics and analytics reads during steady autosave.
LOCAL ONLY: refuses any LT_BASE or DATABASE_URL that is not on this machine. Never point it at Render, Vercel or Neon.

  cd backend && DATABASE_URL=<local scratch> LMS_STORAGE_DRIVER=db LOCAL_UPLOAD_DIR=<scratch>/up \
      LT_STATE=<scratch>/perf_state.json LT_BASE=http://127.0.0.1:8111 \
      python ../loadtest/mixed_load.py <label> <autosave students> <readers> <steady seconds> [procs]

Data comes from perf_seed.py; the exam from exam_seed.create_exam (a fresh ort_main, one section open for the whole run).
Every autosave student starts an attempt during the ramp, then saves 1-5 answers every U(15, 25) s, like exam_load.py.
Readers run a closed loop with U(2, 5) s of think time: 60 % students (home, notebook, progress), 25 % teachers
(statistics and course analytics), 15 % organization admins (organization analytics). The statistics cache of the biggest
exam is invalidated every 60 s, so a real refresh runs under load. Acknowledged answers are then checked against the
database, as exam_verify.py does for full exams. Output: loadtest/results/mixed_<label>.json.
"""
import asyncio
import json
import multiprocessing as mp
import os
import random
import resource
import subprocess
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx  # noqa: E402

import exam_load  # noqa: E402
import exam_seed  # noqa: E402
from exam_load import Ctx, sample, summarize  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("LT_BASE", "http://127.0.0.1:8111")
API = BASE + "/api/v1"
OUT = os.environ.get("LT_OUT", "/tmp/mixed_load")


def guard():
    from sqlalchemy.engine import make_url

    if urlparse(BASE).hostname not in ("127.0.0.1", "localhost"):
        sys.exit("mixed_load: local server only")
    url = make_url(os.environ["DATABASE_URL"])
    if url.host not in ("127.0.0.1", "localhost"):
        sys.exit("mixed_load: local scratch Postgres only")


def token_hdr(uid):
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token({'sub': uid})}"}


async def autosave_student(ctx, i, uid, cfg, acks):
    rng = random.Random(i)
    hdr = token_hdr(uid)
    exam = cfg["exam"]
    await exam_load.sleep_until(ctx.t0 + exam["ramp_s"] * (i / max(cfg["n"], 1)))
    st = None
    for k in range(3):
        r = await ctx.call("start", "POST", f"/courses/{cfg['course_id']}/assessments/{exam['assessment_id']}/attempts",
                           hdr, json={"language": "ru"})
        if r is not None and r.status_code in (200, 201):
            st = r.json()
            break
        await asyncio.sleep(2 + 2 * k)
    if st is None:
        ctx.c["start_failed"] += 1
        return
    ctx.c["started_ok"] += 1
    aid = st["id"]
    positions = [it["position"] for it in st["items"] if it["section_pos"] == 1]
    r = await ctx.call("content", "GET", f"/attempts/{aid}/content?section=1", hdr)
    questions = (r.json().get("questions") or {}) if r is not None and r.status_code == 200 else {}
    qv_of = {it["position"]: it["qv"] for it in st["items"]}
    last_ts = 0
    end = ctx.t0 + exam["ramp_s"] + cfg["steady_s"]
    await asyncio.sleep(rng.uniform(0, 20))
    while time.time() < end:
        entries = {}
        for _ in range(rng.randint(1, 5)):
            p = rng.choice(positions)
            q = questions.get(qv_of[p]) or {}
            last_ts = max(last_ts + 1, int(time.time() * 1000))
            if q.get("type") == "comparison":
                resp = {"choice": rng.choice("ABCD")}
            else:
                ids = [c["id"] for c in q.get("choices") or []] or ["A"]
                resp = {"choice_id": rng.choice(ids)}
            entries[p] = {"position": p, "response": resp, "client_ts": last_ts}
        batch = list(entries.values())
        r = await ctx.call("autosave", "PUT", f"/attempts/{aid}/answers", hdr, json={"answers": batch})
        if r is not None and r.status_code == 200:
            saved = set(r.json()["saved"])
            for e in batch:
                if e["position"] in saved:
                    acks[(aid, e["position"])] = (e["client_ts"], e["response"])
        elif r is not None:
            ctx.c[f"autosave_{r.status_code}"] += 1
        await asyncio.sleep(rng.uniform(15, 25))


def reader_routes(cfg, i, rng):
    """(name, url, user) for one pass. Course and exam ids come from the perf seed."""
    role = (i * 7) % 20  # spreads the roles even with few readers
    c = cfg["course_id"]
    big = cfg["big_exam"]
    if role < 12:
        uid = rng.choice(cfg["read_students"])
        return uid, [("home", "/me/home"), ("notebook", f"/courses/{c}/my/mistakes?status=open"),
                     ("progress", f"/courses/{c}/my/progress")]
    if role < 17:
        a = f"/courses/{c}/assessments/{big}/statistics"
        return cfg["teacher_id"], [("statistics", a), ("statistics_items", a + "/items?sort=hardest"),
                                   ("analytics_overview", f"/courses/{c}/analytics/overview"),
                                   ("analytics_modules", f"/courses/{c}/analytics/modules"),
                                   ("analytics_quizzes", f"/courses/{c}/analytics/quizzes")]
    o = cfg["org_id"]
    return cfg["org_admin_id"], [("org_overview", f"/org/{o}/analytics/overview"),
                                 ("org_courses", f"/org/{o}/analytics/courses"),
                                 ("org_quizzes", f"/org/{o}/analytics/quizzes")]


async def reader(ctx, i, cfg):
    rng = random.Random(10_000 + i)
    end = ctx.t0 + cfg["exam"]["ramp_s"] + cfg["steady_s"]
    await exam_load.sleep_until(ctx.t0 + cfg["exam"]["ramp_s"] + rng.uniform(0, 5))
    while time.time() < end:
        uid, routes = reader_routes(cfg, i, rng)
        hdr = token_hdr(uid)
        for name, url in routes:
            if time.time() >= end:
                break
            await ctx.call(name, "GET", url, hdr)
            await asyncio.sleep(rng.uniform(2, 5))


async def wmain(k, cfg, path):
    limits = httpx.Limits(max_connections=cfg["conns"], max_keepalive_connections=cfg["conns"])
    async with httpx.AsyncClient(base_url=API, limits=limits, timeout=httpx.Timeout(60.0)) as cl:
        ctx = Ctx(cl, cfg)
        acks: dict = {}
        tasks = [autosave_student(ctx, i, cfg["uids"][i], cfg, acks) for i in range(k, cfg["n"], cfg["procs"])]
        tasks += [reader(ctx, i, cfg) for i in range(k, cfg["readers"], cfg["procs"])]
        res = await asyncio.gather(*tasks, return_exceptions=True)
        for r in res:
            if isinstance(r, Exception):
                ctx.c["vu_exception_" + type(r).__name__] += 1
    ru = resource.getrusage(resource.RUSAGE_SELF)
    ctx.c["gen_cpu_s"] = round(ru.ru_utime + ru.ru_stime, 1)
    json.dump({"ev": ctx.ev, "c": ctx.c, "acks": [[a, p, v[0], v[1]] for (a, p), v in acks.items()]}, open(path, "w"))


def worker(k, cfg, path):
    asyncio.run(wmain(k, cfg, path))


def invalidate_statistics(version_id):
    from sqlalchemy import text

    from app.db.session import engine

    with engine.begin() as c:
        c.execute(text("UPDATE assessment_version_stats SET fingerprint = 'stale', computed_at = computed_at - interval '1 day'"
                       " WHERE assessment_version_id = :v"), {"v": version_id})


def verify(acks) -> dict:
    """Every acknowledged answer is in the database, with the acknowledged response or a newer one."""
    from sqlalchemy import text

    from app.db.session import engine

    if not acks:
        return dict(acks=0, lost=0)
    lost = 0
    with engine.connect() as c:
        for start in range(0, len(acks), 2000):
            part = acks[start:start + 2000]
            rows = c.execute(text("SELECT attempt_id::text, position, client_ts, response FROM attempt_items "
                                  "WHERE attempt_id = ANY(CAST(:ids AS uuid[]))"),
                             {"ids": list({a[0] for a in part})}).all()
            have = {(r[0], r[1]): (r[2], r[3]) for r in rows}
            for aid, pos, ts, resp in part:
                row = have.get((aid, pos))
                if row is None or row[0] is None or row[0] < ts or (row[0] == ts and row[1] != resp):
                    lost += 1
    return dict(acks=len(acks), lost=lost)


def main():
    guard()
    label, n, readers, steady = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    procs = int(sys.argv[5]) if len(sys.argv) > 5 else 4
    os.makedirs(OUT, exist_ok=True)
    st = json.load(open(os.environ["LT_STATE"]))
    if n > len(st["students"]):
        sys.exit(f"the perf seed has only {len(st['students'])} students")
    exam_seed.BASE = API
    ramp = max(30, n // 25)
    t0 = time.time() + 20
    exam = exam_seed.create_exam(dict(course_id=st["ort_course_id"], teacher_id=st["teacher_id"], bank_id=st["bank_id"]),
                                 t0=t0, ramp_s=ramp, section_s=ramp + steady + 600, last_min_s=600, title=f"Mixed {label}")
    uids = st["students"][:n]
    cfg = dict(n=n, readers=readers, procs=procs, uids=uids, steady_s=steady, exam=exam, course_id=st["ort_course_id"],
               big_exam=st["exams"][0]["id"], teacher_id=st["teacher_id"], org_id=st["org_id"],
               org_admin_id=st["org_admin_id"], read_students=st["students"][n // 2:n // 2 + 500] + [st["heavy_student"]],
               conns=int(os.environ.get("LT_CONNS", 200)))
    port = urlparse(BASE).port
    pid = int(subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()[0])
    paths = [os.path.join(OUT, f"{label}_{k}.json") for k in range(procs)]
    ps = [mp.Process(target=worker, args=(k, cfg, paths[k])) for k in range(procs)]
    for p in ps:
        p.start()
    samples, next_inval = [], t0 + ramp + 10
    while any(p.is_alive() for p in ps):
        time.sleep(2)
        samples.append(sample(pid))
        if time.time() >= next_inval and time.time() < t0 + ramp + steady - 10:
            invalidate_statistics(st["exams"][0]["version_id"])
            next_inval += 60
    for p in ps:
        p.join()
    evs, counters, acks = {}, {}, []
    for path in paths:
        d = json.load(open(path))
        for k, v in d["ev"].items():
            evs.setdefault(k, []).extend(tuple(x) for x in v)
        for k, v in d["c"].items():
            counters[k] = counters.get(k, 0) + v
        acks += d["acks"]
    steady_lo, steady_hi = ramp, ramp + steady
    stats = summarize(evs, steady_lo, steady_hi)
    total_requests = sum(s["n"] for s in stats.values())
    a = [s for s in samples if s["t"] - t0 >= steady_lo]
    cpu_s = (a[-1]["srv"] - a[0]["srv"]) if len(a) > 1 else None
    pg_s = (a[-1]["pg"] - a[0]["pg"]) if len(a) > 1 else None
    window = (a[-1]["t"] - a[0]["t"]) if len(a) > 1 else None
    out = dict(label=label, autosave_students=n, readers=readers, steady_s=steady, ramp_s=ramp, procs=procs,
               server_env=dict(workers=os.environ.get("LT_SRV_WORKERS"), pool=os.environ.get("LT_SRV_POOL"),
                               tokens=os.environ.get("LT_SRV_TOKENS")),
               counters=counters, endpoints=stats, requests_steady=total_requests,
               server_cpu_cores=round(cpu_s / window, 2) if window else None,
               postgres_cpu_cores=round(pg_s / window, 2) if window else None,
               server_rss_mb_max=max((s["rss_mb"] for s in samples), default=None),
               machine_load1_max=max((s["load1"] for s in samples), default=None),
               machine_load1_mean=round(sum(s["load1"] for s in a) / max(len(a), 1), 1), verify=verify(acks))
    path = os.path.join(HERE, "results", f"mixed_{label}.json")
    json.dump(out, open(path, "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("label", "counters", "server_cpu_cores", "postgres_cpu_cores", "machine_load1_mean",
                                          "verify")}))
    for name, s in stats.items():
        print(f"{name:22s} n {s['n']:7d} rps {s['rps']:7.1f} p50 {s['p50_ms']:9.1f} p95 {s['p95_ms']:9.1f} "
              f"p99 {s['p99_ms']:9.1f} max {s['max_ms']:9.1f} err% {s['err_pct']} {s['codes'] or ''}")


if __name__ == "__main__":
    main()
