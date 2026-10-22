"""Phase 3 exam load test (design PHASE_3_DESIGN.md section 8.1): one national ORT exam window.

  python exam_load.py <label> <students> [ramp_s section_s last_min_s procs]      # run from <worktree>/backend
  python exam_load.py calib <label> <students> <concurrency>    # CPU per request, one request kind at a time

Env: LT_STATE (from exam_seed.py base), LT_BASE (default http://127.0.0.1:8111), LT_OUT (scratch dir for raw events
and acknowledged answers; never the repo). The server PID is found by the port in LT_BASE (CPU/RSS sampling).

Per run a fresh ort_main assessment is published (exam_seed.create_exam): 5 forward-only sections x 30 items,
sections 1-4 timed `section_s`, section 5 open until available_until, so every attempt shares one deadline.
Virtual student (closed loop, own clock):
  start (ramp: student i starts at t0 + ramp*i/N) -> GET content?section=1 -> per section: one batched autosave
  (1-5 answers) every U(15,25) s -> flush + POST sections/{pos}/close -> GET content?section=pos+1 -> ... ->
  in section 5 wait for the deadline and submit with 0-3 final answers at deadline - U(0,60) s.
Variants (seeded per student): 25 % reload once in section 1 (GET state + content with If-None-Match -> 304);
2 % never close sections (server lazy-advances them; they poll GET state after deadline+grace); 2 % go offline
for 60 s in section 5 and replay the queue; 2 % abandon mid-exam (half come back after the deadline, the rest are
left to the sweep); 1 % open a second tab (GET state, content 304, autosave); 1 % double-click submit; 10 % view
their attempt after the deadline (this also triggers the sweep).
Output: loadtest/results/exam_<label>.json (per endpoint and per phase latency, codes, server CPU per request;
with LT_PROBE_DIR also the server-side latencies logged by exam_verify.Probe). LT_CONNS = connections per process.
"""
import asyncio
import json
import multiprocessing as mp
import os
import random
import re
import resource
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("LT_BASE", "http://127.0.0.1:8111")
API = BASE + "/api/v1"
GRACE = 45
OK = {200, 201, 304}


def ts_of(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


async def sleep_until(t):
    d = t - time.time()
    if d > 0:
        await asyncio.sleep(d)


class Ctx:
    def __init__(self, cl, cfg):
        self.cl, self.cfg = cl, cfg
        self.t0 = cfg["exam"]["t0"]
        self.until = cfg["exam"]["until"]
        self.ev = defaultdict(list)      # name -> [(t_rel, ms, code)]
        self.c = Counter()               # misc counters
        self.sem = asyncio.Semaphore(cfg["conns"])  # keep httpx's pool small: a stalled server must not stall us

    async def call(self, name, method, url, hdr, **kw):
        t, p = time.time(), time.perf_counter()
        try:
            async with self.sem:
                r = await self.cl.request(method, url, headers=hdr, **kw)
            code = r.status_code
        except Exception as e:  # transport errors count as errors
            r, code = None, type(e).__name__
        self.ev[name].append((round(t - self.t0, 3), round((time.perf_counter() - p) * 1000, 2), code))
        return r


class Student:
    def __init__(self, i, uid, ctx):
        from app.core.security import create_access_token
        self.i, self.ctx = i, ctx
        self.hdr = {"Authorization": f"Bearer {create_access_token({'sub': uid})}"}
        self.rng = random.Random(i)
        r = self.rng.random()
        self.abandon = r < 0.02
        self.lazy = 0.02 <= r < 0.04
        self.offline = 0.04 <= r < 0.06
        self.tab2 = self.rng.random() < 0.01
        self.dbl = self.rng.random() < 0.01
        self.reload = self.rng.random() < 0.25
        self.post = self.rng.random() < 0.10
        self.abandon_pos = self.rng.randint(2, 5)
        self.returns = self.rng.random() < 0.5
        self.last_ts = 0
        self.q, self.etag, self.acked = {}, {}, {}
        self.queue = []

    # ---------------------------------------------------------------- helpers
    def ts(self):
        self.last_ts = max(self.last_ts + 1, int(time.time() * 1000))
        return self.last_ts

    def apply_state(self, st):
        self.st = st
        self.aid = st["id"]
        self.pos = st["current_section_pos"]
        self.items = {it["position"]: it for it in st["items"]}
        self.by_sec = defaultdict(list)
        for it in st["items"]:
            self.by_sec[it["section_pos"]].append(it["position"])
        self.sec_dl = {s["pos"]: ts_of(s["deadline_at"]) for s in st["sections"]}

    def answer(self, pos):
        q = self.q.get(self.items[pos]["qv"]) or {}
        if q.get("type") == "comparison":
            resp = {"choice": self.rng.choice("ABCD")}
        else:
            ids = [c["id"] for c in (q.get("data") or {}).get("choices") or []] or list("ABCD")
            resp = {"choice_id": self.rng.choice(ids)}
        e = {"position": pos, "response": resp, "client_ts": self.ts()}
        if self.rng.random() < 0.05:
            e["flagged"] = True
        return e

    def batch(self, k):
        es = {}
        for _ in range(k):
            p = self.rng.choice(self.by_sec[self.pos])
            es[p] = self.answer(p)
        return list(es.values())

    def ack(self, e, src):
        p = e["position"]
        if p not in self.acked or self.acked[p][0] < e["client_ts"]:
            self.acked[p] = (e["client_ts"], e["response"], src)
        self.ctx.c["acked_entries"] += 1

    async def save(self, entries, name="autosave"):
        if not entries:
            return
        for attempt in range(2):
            r = await self.ctx.call(name if attempt == 0 else name + "_retry", "PUT", f"/attempts/{self.aid}/answers",
                                    self.hdr, json={"answers": entries})
            if r is not None and r.status_code == 200:
                j = r.json()
                saved = set(j["saved"])
                for e in entries:
                    if e["position"] in saved:
                        self.ack(e, name)
                self.ctx.c["stale_entries"] += len(j["stale"])
                return
            if r is not None and r.status_code == 429:
                await asyncio.sleep(float(r.headers.get("Retry-After", "2")))
            elif r is not None and r.status_code < 500:
                self.ctx.c[f"autosave_rejected_{r.status_code}"] += 1
                return
            else:
                await asyncio.sleep(2)

    async def content(self, pos, name="content", cond=False):
        h = dict(self.hdr)
        if cond and pos in self.etag:
            h["If-None-Match"] = self.etag[pos]
        r = await self.ctx.call(name, "GET", f"/attempts/{self.aid}/content?section={pos}", h)
        if r is not None and r.status_code == 200:
            self.etag[pos] = r.headers.get("etag")
            self.q.update(r.json().get("questions") or {})
        if self.st.get("extra_questions"):
            self.q.update(self.st["extra_questions"])
        return r

    async def get_state(self, name):
        r = await self.ctx.call(name, "GET", f"/attempts/{self.aid}", self.hdr)
        return r.json() if r is not None and r.status_code == 200 else None

    # ---------------------------------------------------------------- scenario
    async def run(self):
        ctx, S = self.ctx, self.ctx.cfg["exam"]["section_s"]
        n, ramp = ctx.cfg["n"], ctx.cfg["exam"]["ramp_s"]
        await sleep_until(ctx.t0 + ramp * self.i / n)
        st = None
        for k in range(3):
            r = await ctx.call("start" if k == 0 else "start_retry", "POST",
                               f"/courses/{ctx.cfg['course_id']}/assessments/{ctx.cfg['exam']['assessment_id']}/attempts",
                               self.hdr, json={"language": "ru"})
            if r is not None and r.status_code in (200, 201):
                st = r.json()
                break
            await asyncio.sleep(2 + 2 * k)
        if st is None:
            ctx.c["start_failed"] += 1
            return
        ctx.c["started_ok"] += 1
        self.apply_state(st)
        await self.content(1)
        first = True
        for pos in range(1, 6):
            if pos > 1:
                await self.content(pos)
            sec_start = time.time()
            dl = self.sec_dl.get(pos) or ctx.until
            if pos < 5:
                end = dl - 1 if self.lazy else min(sec_start + S * self.rng.uniform(0.6, 0.95), dl - 3)
            else:
                end = ctx.until - self.rng.uniform(0, 60)
            gone_at = None
            if self.abandon and pos == self.abandon_pos:
                gone_at = sec_start + self.rng.uniform(5, max(6, min(end, ctx.until - 70) - sec_start))
            off = None
            if self.offline and pos == 5 and ctx.until - 150 > sec_start + 5:
                o = self.rng.uniform(sec_start + 5, ctx.until - 150)
                off = (o, o + 60)
            tab2_at = None
            if self.tab2 and pos == 5:
                tab2_at = self.rng.uniform(sec_start + 2, max(sec_start + 3, end - 20))
            reload_at = sec_start + self.rng.uniform(5, max(6, (end - sec_start) * 0.7)) if self.reload and pos == 1 else None
            tab_task = None
            nxt = time.time() + (self.rng.uniform(3, 20) if first else self.rng.uniform(15, 25))
            first = False
            stop = gone_at or end
            while True:
                # events due before the next autosave
                if reload_at is not None and reload_at <= nxt and reload_at < stop:
                    await sleep_until(reload_at)
                    reload_at = None
                    s2 = await self.get_state("state_reload")
                    if s2:
                        self.apply_state(s2)
                    await self.content(self.pos, "content_304", cond=True)
                    continue
                if tab2_at is not None and tab2_at <= nxt and tab2_at < stop:
                    await sleep_until(tab2_at)
                    tab2_at = None
                    tab_task = asyncio.create_task(self.second_tab())
                    continue
                if nxt >= stop - 1:
                    break
                await sleep_until(nxt)
                entries = self.batch(self.rng.randint(1, 5))
                if off and off[0] <= time.time() < off[1]:
                    self.queue.extend(entries)
                else:
                    if self.queue:
                        await self.replay()
                    await self.save(entries)
                nxt += self.rng.uniform(15, 25)
            if tab_task:
                await tab_task
            if gone_at is not None:  # abandoned: never closes, never submits
                ctx.c["abandoned"] += 1
                if self.returns:
                    await sleep_until(ctx.until + GRACE + self.rng.uniform(5, 60))
                    s2 = await self.get_state("state_after_deadline")
                    ctx.c[f"abandon_return_status_{(s2 or {}).get('status')}"] += 1
                return
            if self.queue:
                await self.replay()
            if pos < 5:
                if self.lazy:
                    await sleep_until(dl + GRACE + self.rng.uniform(1, 10))
                    s2 = await self.get_state("state_lazy")
                    if s2 is None or s2["current_section_pos"] != pos + 1:
                        ctx.c["lazy_advance_unexpected"] += 1
                        return
                    self.apply_state(s2)
                else:
                    await sleep_until(end)
                    await self.save(self.batch(self.rng.randint(1, 3)))
                    r = await ctx.call("section_close", "POST", f"/attempts/{self.aid}/sections/{pos}/close", self.hdr)
                    if r is None or r.status_code != 200:
                        ctx.c["close_failed"] += 1
                        return
                    self.apply_state(r.json())
            else:
                await sleep_until(end)
                await self.submit()
        if self.post:
            await sleep_until(ctx.until + GRACE + self.rng.uniform(5, 85))
            await self.get_state("state_post")

    async def replay(self):
        q = {}
        for e in self.queue:
            q[e["position"]] = e
        self.queue = []
        es = sorted(q.values(), key=lambda e: e["client_ts"])
        for k in range(0, len(es), 20):
            await self.save(es[k:k + 20], "autosave_replay")

    async def second_tab(self):
        s2 = await self.get_state("state_tab2")
        if not s2:
            return
        await self.content(s2["current_section_pos"], "content_304", cond=True)
        await asyncio.sleep(self.rng.uniform(1, 5))
        if s2["current_section_pos"] == self.pos:
            await self.save(self.batch(self.rng.randint(1, 2)))

    async def submit(self):
        ctx = self.ctx
        entries = self.batch(self.rng.randint(0, 3))
        body = {"answers": entries}
        url = f"/attempts/{self.aid}/submit"
        for k in range(3):
            if self.dbl and k == 0:
                rs = await asyncio.gather(ctx.call("submit", "POST", url, self.hdr, json=body),
                                          ctx.call("submit_dup", "POST", url, self.hdr, json=body))
            else:
                rs = [await ctx.call("submit" if k == 0 else "submit_retry", "POST", url, self.hdr, json=body)]
            good = [r.json() for r in rs if r is not None and r.status_code == 200]
            winners = [g for g in good if not g.get("already_submitted")]
            if len(winners) > 1:
                ctx.c["double_winner"] += 1
            if winners and k == 0:
                for e in entries:
                    self.ack(e, "submit")
            if good:
                ctx.c["submitted_ok"] += 1
                ctx.c["submit_status_" + good[0]["status"]] += 1
                return
            await asyncio.sleep(2 + 2 * k)
        ctx.c["submit_failed"] += 1


async def lag_probe(ctx, stop):
    worst, lags = 0.0, []
    while not stop.is_set():
        t = time.perf_counter()
        await asyncio.sleep(0.5)
        lag = time.perf_counter() - t - 0.5
        lags.append(lag)
        worst = max(worst, lag)
    lags.sort()
    ctx.c["loop_lag_p99_ms"] = round(1000 * lags[int(len(lags) * 0.99)], 1) if lags else 0
    ctx.c["loop_lag_max_ms"] = round(1000 * worst, 1)


async def wmain(k, cfg, out_path):
    if os.environ.get("LT_PROFILE_S") and k == 0:  # debugging aid: cProfile one generator process for N seconds
        import cProfile
        prof = cProfile.Profile()
        prof.enable()
        asyncio.get_running_loop().call_later(float(os.environ["LT_PROFILE_S"]),
                                              lambda: (prof.disable(), prof.dump_stats(out_path + ".prof")))
    limits = httpx.Limits(max_connections=cfg["conns"], max_keepalive_connections=cfg["conns"])
    async with httpx.AsyncClient(base_url=API, limits=limits, timeout=httpx.Timeout(60.0)) as cl:
        ctx = Ctx(cl, cfg)
        studs = [Student(i, cfg["uids"][i], ctx) for i in range(k, cfg["n"], cfg["procs"])]
        stop = asyncio.Event()
        lp = asyncio.create_task(lag_probe(ctx, stop))
        hard = cfg["exam"]["until"] + GRACE + 150 - time.time()  # hard stop: a collapsed server ends the run
        res = await asyncio.gather(*(asyncio.wait_for(s.run(), hard) for s in studs), return_exceptions=True)
        stop.set()
        await lp
        for r in res:
            if isinstance(r, Exception):
                ctx.c["vu_exception_" + type(r).__name__] += 1
        acks = [(s.aid, p, a[0], a[1], a[2]) for s in studs if hasattr(s, "aid") for p, a in s.acked.items()]
    ru = resource.getrusage(resource.RUSAGE_SELF)
    ctx.c["gen_cpu_s"] = round(ru.ru_utime + ru.ru_stime, 1)
    json.dump({"ev": ctx.ev, "c": ctx.c, "acks": acks}, open(out_path, "w"))


def worker(k, cfg, out_path):
    asyncio.run(wmain(k, cfg, out_path))


# ------------------------------------------------------------------ coordinator: sampling and statistics

def _secs(s):
    s = s.strip()
    if not s:
        return None
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    parts = [float(x) for x in s.split(":")]
    v = 0.0
    for x in parts:
        v = v * 60 + x
    return v + days * 86400


def sample(pid):
    """Server CPU/RSS = uvicorn master + its worker children; Postgres CPU = all postgres processes (approximate:
    exited backends drop out); load = 1-min load average of the (shared) machine."""
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,time=,rss=,comm="], capture_output=True, text=True).stdout
    srv, rss, pg = 0.0, 0, 0.0
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(\d+)\s+(\S+)\s+(\d+)\s+(.*)", line)
        if not m:
            continue
        if pid in (int(m.group(1)), int(m.group(2))):
            srv += _secs(m.group(3)) or 0
            rss = max(rss, int(m.group(4)) // 1024)
        if "postgres" in m.group(5):
            pg += _secs(m.group(3)) or 0
    load = float(subprocess.run(["sysctl", "-n", "vm.loadavg"], capture_output=True, text=True).stdout.split()[1])
    return {"t": time.time(), "srv": srv, "rss_mb": rss, "pg": pg, "load1": load}


def pct(v, q):
    return v[min(len(v) - 1, int(len(v) * q))] if v else None


def summarize(evs, lo=None, hi=None):
    out = {}
    for name, rows in sorted(evs.items()):
        rows = [r for r in rows if (lo is None or r[0] >= lo) and (hi is None or r[0] < hi)]
        if not rows:
            continue
        lat = sorted(r[1] for r in rows)
        codes = Counter(str(r[2]) for r in rows if r[2] not in OK)
        t = [r[0] for r in rows]
        span = max(max(t) - min(t), 1.0)
        out[name] = {"n": len(rows), "rps": round(len(rows) / span, 1), "p50_ms": pct(lat, .5), "p95_ms": pct(lat, .95),
                     "p99_ms": pct(lat, .99), "max_ms": lat[-1], "err_pct": round(100 * sum(codes.values()) / len(rows), 3),
                     "codes": dict(codes)}
    return out


def cpu_between(samples, t0, lo, hi):
    a = [s for s in samples if s["t"] - t0 >= lo and s["srv"] is not None]
    b = [s for s in a if s["t"] - t0 <= hi]
    if len(b) < 2:
        return None, None, None
    return b[-1]["srv"] - b[0]["srv"], b[-1]["pg"] - b[0]["pg"], (b[0]["t"] - t0, b[-1]["t"] - t0)


def nnls(A, y, iters=3000):
    """Tiny projected-gradient NNLS (no scipy): per-endpoint CPU cost from bucketed counts."""
    import numpy as np
    A, y = np.asarray(A, float), np.asarray(y, float)
    x = np.maximum(np.linalg.lstsq(A, y, rcond=None)[0], 0)
    L = np.linalg.norm(A, 2) ** 2 or 1.0
    for _ in range(iters):
        x = np.maximum(x - (A.T @ (A @ x - y)) / L, 0)
    return x


def main():
    label, n = sys.argv[1], int(sys.argv[2])
    ramp, sec, last, procs = (int(x) for x in (sys.argv[3:7] + ["300", "180", "120", "6"][len(sys.argv[3:7]):]))
    from exam_seed import create_exam
    state = json.load(open(os.environ["LT_STATE"]))
    outdir = os.environ.get("LT_OUT", "/tmp/lt3_out")
    os.makedirs(outdir, exist_ok=True)
    port = int(BASE.rsplit(":", 1)[1])
    pid = int(subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
              .stdout.split()[0])
    t0 = time.time() + 20
    exam = create_exam(state, t0=t0, ramp_s=ramp, section_s=sec, last_min_s=last, title=f"LT {label}")
    cfg = {"n": n, "procs": procs, "uids": state["students"][:n], "course_id": state["course_id"], "exam": exam,
           "conns": int(os.environ.get("LT_CONNS", "48"))}
    print(f"[{label}] exam {exam['assessment_id']} t0+{ramp}s ramp, until t0+{exam['until'] - t0:.0f}s; pid {pid}",
          flush=True)
    mpc = mp.get_context("spawn")
    ps = [mpc.Process(target=worker, args=(k, cfg, f"{outdir}/w{k}.json")) for k in range(procs)]
    for p in ps:
        p.start()
    samples = []
    while any(p.is_alive() for p in ps):
        samples.append(sample(pid))
        time.sleep(2)
    samples.append(sample(pid))
    evs, c, acks = defaultdict(list), Counter(), []
    for k in range(procs):
        d = json.load(open(f"{outdir}/w{k}.json"))
        for name, rows in d["ev"].items():
            evs[name].extend(rows)
        for kk, v in d["c"].items():
            if kk.startswith("loop_lag") or kk == "gen_cpu_s":
                c[f"{kk}_w{k}"] = v
            else:
                c[kk] += v
        acks.extend(d["acks"])
    acks_file = f"{outdir}/acks_{label}.jsonl"
    with open(acks_file, "w") as f:
        for a in acks:
            f.write(json.dumps(a) + "\n")
    U = exam["until"] - t0
    windows = {"a_start_ramp": (0, ramp), "b_steady": (ramp, U - 90), "d_submit_burst": (U - 90, U + 30),
               "e_after_deadline": (U + 30, 1e9)}
    phases = {}
    for w, (lo, hi) in windows.items():
        st = summarize(evs, lo, hi)
        nreq = sum(e["n"] for e in st.values())
        cpu = cpu_between(samples, t0, lo, hi)
        ph = {"window_s": [round(lo), round(min(hi, samples[-1]["t"] - t0))], "requests": nreq, "endpoints": st}
        if cpu[0] is not None:
            srv, pg, (a, b) = cpu
            ph.update({"server_cpu_s": round(srv, 2), "server_cpu_util": round(srv / max(b - a, 1), 2),
                       "server_cpu_ms_per_req": round(1000 * srv / max(nreq, 1), 2),
                       "pg_cpu_s": round(pg, 2), "pg_cpu_ms_per_req": round(1000 * pg / max(nreq, 1), 2)})
        phases[w] = ph
    # per-endpoint CPU cost (NNLS over 10-s buckets)
    groups = {"start": ["start", "start_retry"], "content_200": ["content"], "content_304": ["content_304"],
              "autosave": ["autosave", "autosave_retry", "autosave_replay", "autosave_replay_retry"],
              "section_close": ["section_close"], "submit": ["submit", "submit_dup", "submit_retry"],
              "state_get": ["state_reload", "state_lazy", "state_tab2", "state_post", "state_after_deadline"]}
    B = 10
    nb = int((samples[-1]["t"] - t0) // B) + 1
    rows_A, rows_y = [], []
    for b in range(nb):
        cpu = cpu_between(samples, t0, b * B, (b + 1) * B)
        if cpu[0] is None:
            continue
        lo, hi = cpu[2]
        rows_A.append([sum(1 for nm in g for r in evs.get(nm, []) if lo <= r[0] < hi) for g in groups.values()])
        rows_y.append(cpu[0])
    try:
        x = nnls(rows_A, rows_y)
        cost = {g: round(1000 * v, 2) for g, v in zip(groups, x)}
    except Exception as e:  # numpy missing or singular
        cost = {"error": str(e)}
    autosave_t = sorted(r[0] for nm in groups["autosave"] for r in evs.get(nm, []))
    peak = max(Counter(int(t // B) for t in autosave_t).values()) / B if autosave_t else 0
    sub_t = sorted(r[0] for r in evs.get("submit", []))
    out = {"label": label, "students": n, "procs": procs, "exam": exam, "course_id": state["course_id"],
           "server_env": {k: os.environ.get(k) for k in ("LT_SRV_POOL", "LT_SRV_TOKENS")},
           "wall_s": round(samples[-1]["t"] - t0, 1), "started_ok": c["started_ok"], "acks_total": c["acked_entries"],
           "acks_file": acks_file, "counters": dict(c), "endpoints": summarize(evs), "phases": phases,
           "cpu_ms_per_request_nnls": cost, "autosave_peak_rps_10s": peak,
           "submit_spread_s": round(sub_t[-1] - sub_t[0], 1) if sub_t else None,
           "server_rss_mb_max": max((s["rss_mb"] or 0) for s in samples),
           "server_cpu_total_s": round(samples[-1]["srv"] - samples[0]["srv"], 1),
           "pg_cpu_total_s": round(samples[-1]["pg"] - samples[0]["pg"], 1),
           "machine_load1_max": max(s["load1"] for s in samples),
           "machine_load1_avg": round(sum(s["load1"] for s in samples) / len(samples), 1)}
    if os.environ.get("LT_PROBE_DIR"):
        out["server_side"] = probe_summary(os.environ["LT_PROBE_DIR"], t0, windows)
    json.dump(out, open(os.path.join(HERE, "results", f"exam_{label}.json"), "w"), indent=1)
    json.dump(samples, open(f"{outdir}/samples_{label}.json", "w"))
    brief = {k: out[k] for k in ("label", "students", "wall_s", "started_ok", "acks_total", "autosave_peak_rps_10s",
                                 "submit_spread_s", "server_rss_mb_max", "server_cpu_total_s", "pg_cpu_total_s",
                                 "machine_load1_avg", "machine_load1_max",
                                 "cpu_ms_per_request_nnls")}
    print(json.dumps(brief, indent=1))
    print("counters", json.dumps(dict(c)))
    for name, e in out["endpoints"].items():
        print(f"  {name:22s} n={e['n']:7d} p50={e['p50_ms']:8.1f} p95={e['p95_ms']:8.1f} p99={e['p99_ms']:8.1f} "
              f"err={e['err_pct']}% {e['codes']}")
    for w, ph in phases.items():
        print(w, {k: v for k, v in ph.items() if k != "endpoints"})
    for w, st in (out.get("server_side") or {}).items():
        print("server-side", w)
        for name, e in st.items():
            print(f"    {name:16s} n={e['n']:7d} p50={e['p50_ms']:8.1f} p95={e['p95_ms']:8.1f} p99={e['p99_ms']:8.1f} "
                  f"admit_p95={e['admit_wait_p95_ms']} {e['codes']}")


def probe_summary(d, t0, windows):
    """Server-side latency per request kind and phase from the Probe files (see exam_verify.Probe)."""
    rows = []
    for fn in os.listdir(d):
        if fn.startswith("probe_"):
            for line in open(os.path.join(d, fn)):
                t, kind, code, ms, wait = line.strip().split(",")
                code = int(code)
                if kind == "content" and code == 304:
                    kind = "content_304"
                rows.append((float(t) - t0, kind, code, float(ms), float(wait)))
    out = {}
    for w, (lo, hi) in list(windows.items()) + [("all", (-1e9, 1e9))]:
        by = defaultdict(list)
        for r in rows:
            if lo <= r[0] < hi:
                by[r[1]].append(r)
        out[w] = {}
        for k, rs in sorted(by.items()):
            lat, wt = sorted(r[3] for r in rs), sorted(r[4] for r in rs)
            codes = Counter(str(r[2]) for r in rs if r[2] not in OK)
            out[w][k] = {"n": len(rs), "p50_ms": pct(lat, .5), "p95_ms": pct(lat, .95), "p99_ms": pct(lat, .99),
                         "max_ms": lat[-1], "admit_wait_p95_ms": pct(wt, .95), "codes": dict(codes),
                         "err_pct": round(100 * sum(codes.values()) / len(rs), 3)}
    return out


# ------------------------------------------------------------------ calibration: CPU per request, one kind at a time

async def calib_async(label, n, conc, state, pid):
    from exam_seed import create_exam
    exam = create_exam(state, t0=time.time(), ramp_s=0, section_s=3600, last_min_s=3600, title=f"LT calib {label}")
    cfg = {"n": n, "procs": 1, "exam": exam, "conns": conc, "course_id": state["course_id"]}
    steps = []
    async with httpx.AsyncClient(base_url=API, limits=httpx.Limits(max_connections=conc), timeout=60) as cl:
        ctx = Ctx(cl, cfg)
        studs = [Student(i, state["students"][i], ctx) for i in range(n)]
        url_start = f"/courses/{state['course_id']}/assessments/{exam['assessment_id']}/attempts"

        async def start(s):
            r = await ctx.call("start", "POST", url_start, s.hdr, json={"language": "ru"})
            s.apply_state(r.json())

        async def content(s, name, pos, cond):
            await s.content(pos, name, cond)

        async def save(s, k, name):
            es = s.batch(k) if k <= 5 else [s.answer(p) for p in s.by_sec[s.pos][:k]]
            await ctx.call(name, "PUT", f"/attempts/{s.aid}/answers", s.hdr, json={"answers": es})

        async def close(s):
            r = await ctx.call("section_close", "POST", f"/attempts/{s.aid}/sections/1/close", s.hdr)
            s.apply_state(r.json())

        async def submit(s):
            await ctx.call("submit", "POST", f"/attempts/{s.aid}/submit", s.hdr, json={"answers": s.batch(2)})

        plan = [("start", lambda s: start(s)),
                ("content", lambda s: content(s, "content", 1, False)),
                ("content_304", lambda s: content(s, "content_304", 1, True)),
                ("state", lambda s: s.get_state("state")),
                ("autosave_1", lambda s: save(s, 1, "autosave_1")),
                ("autosave_3", lambda s: save(s, 3, "autosave_3")),
                ("autosave_5", lambda s: save(s, 5, "autosave_5")),
                ("autosave_20", lambda s: save(s, 20, "autosave_20")),
                ("section_close", lambda s: close(s)),
                ("content_s2", lambda s: content(s, "content_s2", 2, False)),
                ("submit", lambda s: submit(s))]
        for name, fn in plan:
            sem = asyncio.Semaphore(conc)

            async def one(s):
                async with sem:
                    await fn(s)
            a = sample(pid)
            t = time.time()
            await asyncio.gather(*(one(s) for s in studs))
            wall = time.time() - t
            b = sample(pid)
            lat = sorted(r[1] for r in ctx.ev[name])
            codes = Counter(str(r[2]) for r in ctx.ev[name] if r[2] not in OK)
            steps.append({"step": name, "n": len(lat), "rps": round(len(lat) / wall, 1),
                          "server_cpu_ms_per_req": round(1000 * (b["srv"] - a["srv"]) / max(len(lat), 1), 2),
                          "pg_cpu_ms_per_req": round(1000 * (b["pg"] - a["pg"]) / max(len(lat), 1), 2),
                          "p50_ms": pct(lat, .5), "p95_ms": pct(lat, .95), "codes": dict(codes)})
            print(steps[-1], flush=True)
    return {"label": label, "students": n, "concurrency": conc, "exam": exam, "steps": steps}


def calib():
    label, n, conc = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    state = json.load(open(os.environ["LT_STATE"]))
    port = int(BASE.rsplit(":", 1)[1])
    pid = int(subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
              .stdout.split()[0])
    out = asyncio.run(calib_async(label, n, conc, state, pid))
    json.dump(out, open(os.path.join(HERE, "results", f"exam_calib_{label}.json"), "w"), indent=1)


if __name__ == "__main__":
    calib() if sys.argv[1] == "calib" else main()
