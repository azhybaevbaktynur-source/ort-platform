# Phase 3 merge-gate load test (local, free resources), 2026-10-23

Design: `PHASE_3_DESIGN.md` §8. Earlier results: `docs/LOAD_TEST_PRE_PHASE3.md`. Raw data: `loadtest/results/exam_*.json`
(per run: client and server-side latency per endpoint and phase, CPU summary) and `exam_*_verify.json` (integrity).
Scripts: `loadtest/exam_seed.py`, `exam_load.py`, `exam_verify.py`. No secrets.

## 1. Setup

- **Code and services**: worktree at `e06d63f`; no app file was edited; Neon and Render were not touched.
- **DB**: local Postgres 18.6 (port 55432, `fsync=on`, `shared_buffers=128MB`, `max_connections=100`; cluster shared with other agents' test DBs), DB `lt3`, `alembic upgrade head`.
- **API**: `uvicorn --factory --app-dir loadtest exam_verify:hooked_app --port 8111` from the worktree with the briefed env. The factory is `app.main:app` plus harness-only additions: a scored hook that counts calls in `lt_hook_calls` (inside the grading transaction), `Probe` (server-side log of ASGI time and status), and optional `LT_ADMIT=n` (§3).
- **Machine**: Apple M1 (4 performance + 4 efficiency cores, 8 GB), shared with Chrome and other agents (load average recorded per run). The generator runs on the same machine (httpx asyncio, 4–6 processes, 48 connections each).
- **Data**: 1 approved teacher; 1 published `ru` course; `tsoomo19.zip` imported through the Phase 2 importer (150 questions); 6,000 enrolled students inserted directly, JWTs from `create_access_token`. Each run publishes a fresh `ort_main` assessment: 5 sections × 30 items (comparison in math_1, single_choice elsewhere), forward-only, shuffled choices.
- **Timeline**: starts ramp over 300 s (20/s); sections 1–4 timed S = 180 s (60 s in R1, R2, R5); section 5 runs to `available_until`, so all attempts share one deadline, as in a national window. Compressed: closes and content fetches run about 10× more often than in a real 3-hour ORT.
- **Per VU**: start, content for section 1; every U(15,25) s one autosave with 1–5 answers (about 300 req/s, about 900 item writes/s at 6,000 VUs); at section end flush, close, next section's content (ETag); submit at deadline − U(0,60) s with 0–3 final answers.
- **Variants**: 25 % reload (state + content 304); 2 % never close (lazy advance); 2 % offline 60 s then replay; 2 % abandon (half return after the deadline, half left to the sweep); 1 % second tab; 1 % double-click submit; 10 % view state after the deadline (also triggers the sweep).

## 2. Runs

| Run | VUs | Workers | Pool / tokens | `LT_ADMIT` | Outcome | 5xx + transport errors |
|---|---|---|---|---|---|---|
| R1 | 6,000 | 1 | 10+10 / 20 | – | collapses in the first minute: 149 of 6,000 starts succeed | 98.4 % |
| R2 | 6,000 | 1 | 20+20 / 40 | – | collapses after about 1,320 starts | 77.6 % |
| R5 | 6,000 | 4 | 10+10 / 20 | – | deadlock at peak: 860 QueuePool timeouts | **0.71 %** |
| R4 | 6,000 | 4 | 10+10 / 20 | 20 | no pool errors; machine oversubscribed (load average 10.9, client p50 22 s) | 0.07 % |
| R8 | 6,000 | 2 | 10+10 / 20 | 20 | no pool errors; API CPU saturated (2.02 cores) | 0.004 % |
| R6 | 3,000 | 2 | 10+10 / 20 | 20 | healthy, all budgets met | 0.001 % |
| R7 | 3,000 | 2 | 10+10 / 20 | – | healthy, all budgets met (no overload, so no deadlock) | 0 % |

R3 (6,000 VUs, 4 workers, gate on) is discarded: the generator was the bottleneck (500 connections per process). The 409s and few 422s in overloaded runs are side effects (late autosaves after the section expired; a VU whose content fetch timed out sent the wrong answer shape).

## 3. Blocker B1: pool and threadpool deadlock under overload (P3-27 + L5)

**Evidence** (R1, R2, R5): every pool connection `idle in transaction` (ClientRead) for 40–76 s after `SELECT users…`; server CPU 0 %; log: `QueuePool limit of size 10 overflow 10 reached, connection timed out, timeout 10.00`. This is `LOAD_TEST_PRE_PHASE3.md` §3.1, still unfixed.

**Mechanism**: P3-27 gives one checkout per request, but FastAPI runs the sync auth dependency, the endpoint and the `get_db` teardown as separate threadpool hops, holding the connection between them. When more than P requests have passed auth (holding connections, waiting for a token) and all T tokens belong to new requests blocked in checkout, nothing moves until `pool_timeout` (10 s), then 500s. New arrivals keep refilling the FIFO limiter, so the server livelocks instead of recovering.

**Why the settings don't prevent it**: L5 ("tokens = pool + overflow") is no safeguard; any T and P lock up once arrivals outrun service for about P / rate seconds. A larger pool (R2) or more workers (R5) only delay it. Nominal load doesn't trigger it (R7), but a national start burst is exactly the overload case.

**Fix options** (architect decision, app code):
1. ASGI admission gate: `asyncio.Semaphore(min(tokens, pool + overflow))` per process; excess requests wait in the event loop holding nothing. Emulated by `LT_ADMIT` in R4/R6/R8: 0 pool errors, no measurable overhead (R6 vs R7).
2. One threadpool hop per request, or release the connection after the auth read.
3. `DB_POOL_TIMEOUT` of 2–3 s, so a stall becomes fast 503s.

Add a regression test: more than P concurrent requests through `get_lms_user` with a slow handler.

## 4. API CPU per request (calibration: 1 worker, concurrency 8, idle machine, M1 P-core)

| Request | CPU ms | Req/s per worker | p50 / p95 ms |
|---|---|---|---|
| start (150 rows, shuffled choices) | **20.9** | 63 | 120 / 176 |
| content (cached) / content 304 | 1.9 / 1.9 | 570 / 590 | 13 / 20 |
| state | 3.7 | 311 | 24 / 31 |
| autosave, 1 / 3 / 5 / 20 answers | 2.1 / **3.2** / 4.3 / 12.8 | 520 / 336 / 245 / 83 | p50 15 / 23 / 31 / 93 |
| section close | 4.4 | 250 | 28 / 71 |
| submit (2 answers, grade 150, hook) | **10.6** | 100 | 75 / 121 |

In-run cost matches the calibration below about 70 % CPU (R6: 3.8 ms/request) and doubles at saturation (R8: 6.7 ms; GIL contention, efficiency cores). Postgres CPU: about 0.15 ms/request (R8: 36 s for 286k requests). API RSS ≤ 175 MB per worker (budget 300 MB).

## 5. Latency (ms, client p50 / p95 / p99; server-side ASGI p95 in brackets)

**R6** (3,000 VUs, 2 workers): autosave peak 163/s; 2,942 submits within 60 s; API CPU 0.53 cores in the ramp, 0.68 steady, 0.57 in the burst.

| Phase | Start | Autosave | Content | Close | Submit |
|---|---|---|---|---|---|
| ramp 0–300 s | 22 / 37 / 104 [37] | 7 / 16 / 47 [16] | 3 / 8 / 17 [8] | 7 / 19 / 43 [19] | – |
| steady | – | 7 / 18 / 62 [18] | 4 / 10 / 23 [10] | 8 / 20 / 53 [20] | – |
| submit burst | – | 8 / 31 / 104 [31] | – | – | 20 / 77 / 183 [77] |
| whole run | 23 / 40 / 114 | 9 / 22 / 97 | 5 / 13 / 28 | 10 / 23 / 65 | 23 / 94 / 217 |

R7 (same as R6 without the gate) is within noise: autosave 9 / 22 / 83, start 24 / 40 / 108, submit 23 / 111 / 281.

**R8** (6,000 VUs, 2 workers; CPU saturated): autosave peak 294/s; 5,883 submits spread over 112 s.

| | Start | Autosave | Content | Close | Submit |
|---|---|---|---|---|---|
| client p50 / p95 | 30 / 7,093 | 14,130 / 21,932 | 10,779 / 17,502 | 13,152 / 17,577 | 26,659 / 30,888 |
| server p95 (all) | 1,317 | 1,286 | 1,116 | 1,209 | 2,610 |

In R4, R5 and R8, client latency is 10–20 s above the server-side figure. Those requests waited before reaching ASGI (uvicorn's loop starved of CPU and the GIL). In-app metrics hide this; watch the proxy's response times.

## 6. Integrity (`exam_verify.py`)

| Run | Attempts | Finalized: manual / timeout / sweep | Hooks (double) | Acked positions exact / superseded | Lost | Submit answers rejected late |
|---|---|---|---|---|---|---|
| R4 | 6,000 | 2,213 / 3,646 / 141 | 6,000 (0) | 383,608 / 2 | **0** | 2,062 |
| R5 | 6,000 | 5,601 / 50 / 349 | 6,000 (0) | 187,999 / 5 | **0** | 1 |
| R6 | 3,000 | 2,942 / 1 / 57 | 3,000 (0) | 258,573 / 0 | **0** | 0 |
| R7 | 3,000 | 2,942 / 1 / 57 | 3,000 (0) | 258,559 / 0 | **0** | 0 |
| R8 | 6,000 | 4,977 / 919 / 104 | 6,000 (0) | 477,966 / 0 | **0** | 1,265 |
| R1 / R2 | 170 / 1,336 | server dead; finalized later by `run_sweep` | 1 / 1 (0) | 38 / 5,813 | **0** | – |

Every run: one attempt per user; every item graded and `raw_score` = sum of item scores; `correctness` matches the key on all 3.8 M rows; no answer after `graded_at`; no open section on a finalized attempt; one winner per double-click submit; 0 `stale` entries.

**Finding B2** (not a loss): final answers in a submit body are judged at processing time. A submit queued past deadline + 45 s is finalized as `timeout` and its body answers are dropped, and `SubmitOut` doesn't say so; every autosaved answer was graded. Recommend `saved`/`rejected` positions in `SubmitOut` and a continuous client flush in the last 60 s (design §8.2).

## 7. Capacity per Render plan (estimate; no purchases; prices from memory, unverified)

**Real exam** (6,000 students; sections 30–60 min, so closes and content are negligible):

| Load | M1 P-core cost |
|---|---|
| Steady: 300 autosaves/s × 3.2 ms × 1.15 | about 1.1 core |
| Start ramp: + 20/s × 21 ms | about +0.4 core |
| Deadline minute: 6,000 × 10.6 ms = 64 CPU-s, plus autosave | about 2.1 cores for 60 s |

**Assumptions**: 1 Render CPU ≈ 0.5–0.7 of an M1 P-core (Render cost ≈ 1.4–2× the M1 figures); size for ≤ 60 % CPU, since per-request cost doubles at saturation.

| Plan (CPU) | Students in steady autosave at 60 % | 6,000-student exam window | Price |
|---|---|---|---|
| Free (0.1, sleeps) | about 150–250 | no (development only) | $0 |
| Starter (0.5) | about 800–1,150 | no | about $7/mo |
| Standard (1) | about 1,600–2,300 | no | about $25/mo |
| Pro (2) | about 3,200–4,600 | marginal: about 100 % at peak, deadline burst drains in 1.5–3 min, so B2 drops (R8 is the local analogue) | about $85/mo |
| Pro Plus (4) | about 6,500–9,200 | **yes**, with burst headroom | about $175/mo |

Cost notes: Render bills per second, so a 3-hour window on Pro Plus costs about $0.7 (plan switch needs a redeploy). Alternative: 2–3 instances behind Render's load balancer; each worker opens up to pool 20 + rate-limit 5 + sweep 1 connections, so use Neon's pooled URL. Neon compute is not the limit (about 0.05 CU at 6,000). Neon storage is: `attempt_items` measured 230 B/row with indexes and update churn (3.8 M rows = 837 MB), i.e. **about 0.2 GB per 6,000 × 150 exam** (design §2.9 assumed 110–150 MB). Free (0.5 GB) holds about 2 exams; plan Launch or archive rows after grading.

## 8. Bottlenecks

1. **B1** (above).
2. **API CPU (Python, GIL)**: autosave 1.6 + 0.55 ms per answer, start 21 ms, submit 10.6 ms; workers ≈ cores; keep CPU ≤ 60 %.
3. **Pre-ASGI queueing hidden from app metrics**: at saturation, client latency is 10–20 s while ASGI p95 stays near 1 s.
4. **Deadline submit burst**: about 1 core-minute per 6,000 submits; queueing past grace triggers B2.
5. **Uneven uvicorn worker shares** (R4: 30 / 27 / 25 / 18 %).
6. **Not bottlenecks**: content and 304s (1.9 ms; both authenticate and load the attempt), Postgres CPU, caches, RSS, lock contention (no ungranted locks in spot checks).

## 9. Verdict: **NO-GO at `e06d63f`**

**Integrity gates pass in every run, including the collapses**: zero lost answers, zero double grades, every attempt finalized (lazy expiry and sweep), grading matches keys.

**Error budget (< 0.5 %)**: **fails** without a gate once the API is overloaded (R1 98 %, R2 78 %, R5 0.71 %; B1). Passes with the emulated fix (R4 0.07 %, R8 0.004 %, R6 0.001 %) and at nominal load without it (R7 0 %).

**Latency (p95 autosave < 500 ms, start < 2 s)**: passes at 3,000 VUs on 2 workers (autosave 22 ms, start 40 ms, submit 94 ms). At 6,000 VUs the local stack is CPU-bound: R8 on 2 workers gives 21.9 s and 7.1 s, and 4 workers plus the generator oversubscribe this shared M1 (R4). A clean 6,000-VU latency gate needs about 3–4 dedicated cores.

**Before merge**: (1) fix B1 in app code with a regression test; (2) re-run R5 (4 workers) and R8 without `LT_ADMIT` and expect 0 QueuePool errors; (3) fix B2 (`SubmitOut` saved/rejected) and the client last-minute flush; (4) owner decision on the exam-window plan, Pro Plus or 2+ instances (§7).

## 10. Reproduce

```
git worktree add <wt> e06d63f; createdb lt3 (UTF8, template0); cd <wt>/backend; DATABASE_URL=… alembic upgrade head
LT_STATE=<scratch>/state.json DATABASE_URL=… LMS_STORAGE_DRIVER=db python <repo>/loadtest/exam_seed.py base 6000   # with the server up
LT_PROBE_DIR=<dir> [LT_ADMIT=20] DB_POOL_SIZE=10 DB_MAX_OVERFLOW=10 LMS_THREADPOOL_TOKENS=20 … uvicorn --factory \
  --app-dir <repo>/loadtest exam_verify:hooked_app --workers 2 --port 8111
LT_STATE=… LT_OUT=<scratch>/out LT_PROBE_DIR=<dir> python <repo>/loadtest/exam_load.py r6 3000 300 180 120 4
python <repo>/loadtest/exam_load.py calib w1 1000 8; DATABASE_URL=… python <repo>/loadtest/exam_verify.py r6
```

Kill uvicorn by PID: `pkill` does not stop stuck workers. After a collapsed run, run the app's `run_sweep` to clear leftovers before the next run.

## 11. B1 fix (admission gate in app code), re-run 2026-10-23

**Fix**: `backend/app/lms/core/admission.py`, registered innermost in `main.py` (inside CORS, GZip and BodyCap). Each process admits at most N requests; the rest wait in the event loop. N = `LMS_ADMISSION_LIMIT`, or auto = min(thread tokens, `DB_POOL_SIZE` + `DB_MAX_OVERFLOW`) − sweep reserve (0 on Postgres: the sweep has its own engine), at least 1. A request waiting more than `LMS_ADMISSION_WAIT_SECONDS` (20) gets 503 `server_busy` with `Retry-After: 2`. `/health`, `/uploads`, `OPTIONS` are not gated. The startup log shows N. Regression test: `backend/tests/lms/test_admission.py` (Postgres, pool 2, threads 2, 8 slow requests: pool timeouts without the gate, none with it).

**Re-run** (same harness and settings as R5 and R8, `LT_ADMIT` unset, the app's own gate: N = 20 per worker; fresh DB `lt3b`):

| Run | As | VUs | Workers | QueuePool errors | 503 `server_busy` | 5xx + transport errors | Client p95 autosave / start / submit | Server p95 (incl. gate wait) | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| R9 | R5 | 6,000 | 4 | **0** (R5: 860) | 0 | 48 client `ReadError` of 165k = **0.03 %** (R5: 0.71 %; R4 with `LT_ADMIT`: 180) | 24.2 / 15.3 / 26.2 s | 349 / 217 / 1,785 ms | 0 lost, 0 double grades, all 6,000 finalized |
| R10 | R8 | 6,000 | 2 | **0** | 0 | **0** of 334k | 12.7 / 4.6 / 17.0 s (R8: 21.9 / 7.1 / 30.9 s) | 1,198 / 1,284 / 2,557 ms | `ok`: 0 lost, 0 double grades, 0 late-rejected submit answers |

No request waited 20 s for a slot, so the 503 path did not fire. The high client latencies come from the CPU-bound local stack (pre-ASGI queueing, §5 and §8.3): R9 oversubscribes this M1 (load average 8.6, max 13.5) like R4. The `ReadError`s are the same client-side connection drops seen in R4, R6 and R8. Raw data: `loadtest/results/exam_r9_w4_p10_t20_gate*.json`, `exam_r10_w2_p10_t20_gate*.json`. **B1 is closed**; B2 and the plan decision (§9) remain.
