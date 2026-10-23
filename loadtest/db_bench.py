"""DB micro-benchmark for the Phase 3 attempt engine (free resources only).

Usage: BENCH_DATABASE_URL=<pooled postgresql:// url> python db_bench.py [phase ...]
Phases: setup start autosave submit read conns cleanup
The URL is read from the environment only. Objects live in schema "loadtest".
"""
import json, os, queue, random, statistics, sys, threading, time
import psycopg2

URL = os.environ["BENCH_DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
OUT = os.path.join(os.path.dirname(__file__), "results")
N_ITEMS = 150
LOCK = threading.Lock()


def connect(autocommit=True):
    c = psycopg2.connect(URL, connect_timeout=30, options="")
    c.autocommit = autocommit
    return c


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * p / 100))] * 1000, 1)


def summarize(lat, errs, wall, extra=None):
    d = {"ok": len(lat), "errors": len(errs), "wall_s": round(wall, 2),
         "rate_per_s": round(len(lat) / wall, 1) if wall else None,
         "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "p99_ms": pct(lat, 99),
         "max_ms": round(max(lat) * 1000, 1) if lat else None}
    if errs:
        d["error_samples"] = sorted(set(str(e)[:120] for e in errs))[:5]
    d.update(extra or {})
    return d


def save(name, data):
    with open(os.path.join(OUT, f"db_{name}.json"), "w") as f:
        json.dump(data, f, indent=1)
    print(name, json.dumps(data))


def setup():
    c = connect()
    cur = c.cursor()
    cur.execute("""
    DROP SCHEMA IF EXISTS loadtest CASCADE; CREATE SCHEMA loadtest;
    CREATE TABLE loadtest.quiz_items(quiz_id int, item_id int, key text, points int, body text,
        PRIMARY KEY(quiz_id,item_id));
    CREATE TABLE loadtest.attempts(id bigserial PRIMARY KEY, user_id int, quiz_id int, status text,
        started_at timestamptz, deadline timestamptz, submitted_at timestamptz, score int);
    CREATE TABLE loadtest.attempt_items(attempt_id bigint, item_id int, response jsonb,
        updated_at timestamptz, PRIMARY KEY(attempt_id,item_id));
    INSERT INTO loadtest.quiz_items SELECT 1, g, (ARRAY['A','B','C','D'])[1+g%4], 1, repeat('x',1000)
        FROM generate_series(1,150) g;
    """)
    print("setup ok")


START_SQL_A = ("INSERT INTO loadtest.attempts(user_id,quiz_id,status,started_at,deadline) "
               "VALUES(%s,1,'in_progress',now(),now()+interval '3 hours') RETURNING id")
START_SQL_B = ("INSERT INTO loadtest.attempt_items(attempt_id,item_id,response,updated_at) "
               "SELECT %s,item_id,NULL,now() FROM loadtest.quiz_items WHERE quiz_id=1")


def run_closed(n_conns, n_jobs, job, autocommit=False):
    """n_conns workers drain n_jobs jobs; job(conn, i) does the work."""
    q = queue.Queue()
    for i in range(n_jobs):
        q.put(i)
    lat, errs = [], []

    def worker():
        try:
            c = connect(autocommit)
        except Exception as e:
            with LOCK: errs.append(e)
            return
        while True:
            try:
                i = q.get_nowait()
            except queue.Empty:
                break
            t = time.perf_counter()
            try:
                job(c, i)
                dt = time.perf_counter() - t
                with LOCK: lat.append(dt)
            except Exception as e:
                with LOCK: errs.append(e)
                try: c.rollback()
                except Exception:
                    try: c = connect(autocommit)
                    except Exception: pass
        c.close()
    ths = [threading.Thread(target=worker) for _ in range(n_conns)]
    t0 = time.perf_counter()
    [t.start() for t in ths]; [t.join() for t in ths]
    return lat, errs, time.perf_counter() - t0


def start_job(c, i):
    cur = c.cursor()
    cur.execute(START_SQL_A, (i,))
    aid = cur.fetchone()[0]
    cur.execute(START_SQL_B, (aid,))
    c.commit()


START_CTE = ("WITH a AS (INSERT INTO loadtest.attempts(user_id,quiz_id,status,started_at,deadline) "
             "VALUES(%s,1,'in_progress',now(),now()+interval '3 hours') RETURNING id) "
             "INSERT INTO loadtest.attempt_items(attempt_id,item_id,response,updated_at) "
             "SELECT a.id,q.item_id,NULL,now() FROM a, loadtest.quiz_items q WHERE q.quiz_id=1")


def start_cte_job(c, i):
    c.cursor().execute(START_CTE, (i,))  # autocommit: 1 round trip, 1 transaction


def start_cte():
    res = {}
    for conns, jobs in ((50, 1500), (100, 2000), (200, 3000)):
        lat, errs, wall = run_closed(conns, jobs, start_cte_job, autocommit=True)
        r = summarize(lat, errs, wall)
        r["est_6000_attempts_s"] = round(6000 / r["rate_per_s"], 1) if r["rate_per_s"] else None
        res[f"conns_{conns}"] = r
        print("cte", conns, r)
    save("start_cte_sweep", res)


def start():
    res = {}
    for conns, jobs in ((100, 2000), (200, 3000)):
        lat, errs, wall = run_closed(conns, jobs, start_job)
        r = summarize(lat, errs, wall)
        r["est_6000_attempts_s"] = round(6000 / r["rate_per_s"], 1) if r["rate_per_s"] else None
        res[f"conns_{conns}"] = r
        print(conns, r)
    save("start_sweep_hi", res)


def start_full():
    c = connect(); cur = c.cursor()
    cur.execute("SELECT count(*) FROM loadtest.attempts"); have = cur.fetchone()[0]
    need = max(0, 6000 - have)
    lat, errs, wall = run_closed(200, need, start_cte_job, autocommit=True)
    r = summarize(lat, errs, wall, {"attempts_inserted": len(lat), "pre_existing": have})
    save("start_full6000", r)


def run_open(rate, duration, workers, job, autocommit=True):
    """Open-loop: jobs scheduled at fixed rate; latency measured from scheduled time."""
    q = queue.Queue()
    lat, errs, svc = [], [], []
    stop = threading.Event()

    def worker():
        try: c = connect(autocommit)
        except Exception as e:
            with LOCK: errs.append(e)
            return
        while True:
            try: sched = q.get(timeout=0.5)
            except queue.Empty:
                if stop.is_set(): break
                continue
            t = time.perf_counter()
            try:
                job(c)
                now = time.perf_counter()
                with LOCK: lat.append(now - sched); svc.append(now - t)
            except Exception as e:
                with LOCK: errs.append(e)
                try: c.rollback()
                except Exception:
                    try: c = connect(autocommit)
                    except Exception: pass
        c.close()
    ths = [threading.Thread(target=worker) for _ in range(workers)]
    [t.start() for t in ths]
    time.sleep(3)  # let connections open
    t0 = time.perf_counter(); n = 0
    while True:
        due = t0 + n / rate
        if due - t0 >= duration: break
        d = due - time.perf_counter()
        if d > 0: time.sleep(d)
        q.put(due); n += 1
    done_at = time.perf_counter()
    stop.set(); [t.join(timeout=30) for t in ths]
    completed_in_window = len(lat)
    r = summarize(lat, errs, duration)
    r.update({"target_rate": rate, "scheduled": n, "workers": workers,
              "service_p50_ms": pct(svc, 50), "service_p95_ms": pct(svc, 95),
              "drain_s": round(time.perf_counter() - done_at, 1)})
    return r


AUTOSAVE_SQL = ("UPDATE loadtest.attempt_items ai SET response=%s::jsonb, updated_at=now() "
                "FROM loadtest.attempts a WHERE ai.attempt_id=%s AND ai.item_id=%s "
                "AND a.id=ai.attempt_id AND a.status='in_progress' AND a.deadline>now()")
# variant without join (deadline pre-checked in app memory / denormalised): pure single row
AUTOSAVE_SIMPLE = ("UPDATE loadtest.attempt_items SET response=%s::jsonb, updated_at=now() "
                   "WHERE attempt_id=%s AND item_id=%s")


def autosave(duration=60, rates=(100, 200, 300, 500)):
    c = connect(); cur = c.cursor()
    cur.execute("SELECT min(id), max(id) FROM loadtest.attempts"); lo, hi = cur.fetchone(); c.close()
    res = {}
    for variant, sql in (("join_conditional", AUTOSAVE_SQL),):
        for rate in rates:
            def job(c):
                cur = c.cursor()
                cur.execute(sql, ('{"o":"%s"}' % random.choice("ABCD"),
                                  random.randint(lo, hi), random.randint(1, N_ITEMS)))
                if cur.rowcount != 1: raise RuntimeError("0 rows")
            r = run_open(rate, duration, int(rate * 0.6) + 30, job)
            res[f"{variant}_{rate}"] = r
            print(variant, rate, r)
            save("autosave", res)
    return res


def autosave_variants(rate=300, duration=30):
    c = connect(); cur = c.cursor()
    cur.execute("SELECT min(id), max(id) FROM loadtest.attempts"); lo, hi = cur.fetchone(); c.close()
    res = {}
    def mk(sql):
        def job(c):
            cur = c.cursor()
            cur.execute(sql, ('{"o":"%s"}' % random.choice("ABCD"), random.randint(lo, hi), random.randint(1, N_ITEMS)))
        return job
    res["pk_only_autocommit"] = run_open(rate, duration, 300, mk(AUTOSAVE_SIMPLE))
    def txn_job(c):  # ORM-style: statement + separate COMMIT round trip
        cur = c.cursor()
        cur.execute(AUTOSAVE_SQL, ('{"o":"A"}', random.randint(lo, hi), random.randint(1, N_ITEMS)))
        c.commit()
    res["join_conditional_explicit_txn"] = run_open(rate, duration, 300, txn_job, autocommit=False)
    save("autosave_variants", res)


def submit():
    c = connect(); cur = c.cursor()
    cur.execute("SELECT id FROM loadtest.attempts WHERE status='in_progress' ORDER BY id LIMIT 6000")
    ids = [r[0] for r in cur.fetchall()]; c.close()
    def job(c, i):
        cur = c.cursor()
        cur.execute("UPDATE loadtest.attempts SET status='submitted', submitted_at=now() "
                    "WHERE id=%s AND status='in_progress' AND deadline>now() RETURNING id", (ids[i],))
        if cur.fetchone() is None: raise RuntimeError("not updated")
        cur.execute("SELECT coalesce(sum(CASE WHEN ai.response->>'o'=qi.key THEN qi.points ELSE 0 END),0) "
                    "FROM loadtest.attempt_items ai JOIN loadtest.quiz_items qi "
                    "ON qi.quiz_id=1 AND qi.item_id=ai.item_id WHERE ai.attempt_id=%s", (ids[i],))
        s = cur.fetchone()[0]
        cur.execute("UPDATE loadtest.attempts SET score=%s WHERE id=%s", (s, ids[i]))
        c.commit()
    res = {}
    lat, errs, wall = run_closed(50, len(ids), job)
    res["submit_6000_conc50"] = summarize(lat, errs, wall, {"n": len(ids)})
    save("submit", res)


def read():
    res = {}
    def job(c, i):
        cur = c.cursor()
        cur.execute("SELECT item_id,key,body FROM loadtest.quiz_items WHERE quiz_id=1 ORDER BY item_id")
        cur.fetchall()
    for conns in (25, 50, 100):
        lat, errs, wall = run_closed(conns, 3000, job, autocommit=True)
        res[f"conns_{conns}"] = summarize(lat, errs, wall, {"payload_kb_each": 150})
        print(conns, res[f"conns_{conns}"])
    save("read", res)


def conns(levels=(100, 200, 400, 800)):
    res = {}
    for n in levels:
        errs, ok = [], []
        barrier = threading.Barrier(n)
        def w():
            try:
                c = connect(); cur = c.cursor(); barrier.wait(timeout=120)
                for _ in range(5):
                    cur.execute("SELECT pg_sleep(0.05)")
                ok.append(1); c.close()
            except Exception as e:
                with LOCK: errs.append(e)
        ths = [threading.Thread(target=w) for _ in range(n)]
        t = time.perf_counter(); [x.start() for x in ths]; [x.join() for x in ths]
        res[f"simultaneous_{n}"] = {"ok": len(ok), "errors": len(errs), "wall_s": round(time.perf_counter() - t, 1),
                                    "error_samples": sorted(set(str(e)[:120] for e in errs))[:3]}
        print(n, res[f"simultaneous_{n}"])
    save("conns", res)


def cleanup():
    c = connect(); c.cursor().execute("DROP SCHEMA IF EXISTS loadtest CASCADE"); print("dropped")


def read_server():
    """Server-side cost of the 150-row payload query: result stays in the DB (aggregate), so the client link is not the limit."""
    def job(c, i):
        cur = c.cursor()
        cur.execute("SELECT count(*), sum(length(body)) FROM (SELECT item_id,key,body FROM loadtest.quiz_items "
                    "WHERE quiz_id=1 ORDER BY item_id) s")
        cur.fetchone()
    res = {}
    for conns in (100, 300):
        lat, errs, wall = run_closed(conns, 6000, job, autocommit=True)
        res[f"conns_{conns}"] = summarize(lat, errs, wall)
        print(conns, res[f"conns_{conns}"])
    c = connect(); cur = c.cursor()
    cur.execute("EXPLAIN (ANALYZE, BUFFERS) SELECT item_id,key,body FROM loadtest.quiz_items WHERE quiz_id=1 ORDER BY item_id")
    res["explain_analyze"] = [r[0] for r in cur.fetchall()][-3:]
    cur.execute("SELECT pg_size_pretty(pg_total_relation_size('loadtest.attempt_items')), (SELECT count(*) FROM loadtest.attempt_items)")
    res["attempt_items_size_rows"] = list(cur.fetchone())
    save("read_server", res)


if __name__ == "__main__":
    ph = sys.argv[1:] or ["setup", "start", "start_full", "autosave", "autosave_variants", "submit", "read", "conns"]
    for p in ph:
        globals()[p]()
