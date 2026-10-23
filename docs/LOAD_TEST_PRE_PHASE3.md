# Pre-Phase-3 load test (free resources only), 2026-10-22

Scope: can the planned attempt engine (start snapshot of ~150 `attempt_items` rows in one transaction, single-row conditional autosave UPDATE, submit with scoring) hold ~6,000 concurrent students on Neon free + Render Free? Raw numbers: `loadtest/results/*.json`. Scripts: `loadtest/` (no secrets; URLs come from env vars).

## 1. Setup

- Code: worktree at `d403cae` (Phase 2 head). Neon branch `loadtest-2026-10-22` (`br-late-recipe-b27d2jz0`, endpoint `ep-small-hall-b2185rda`), child of `production`, compute 0.25-2 CU (mirrors production), Postgres 18, migrated to head (0002, 0003). Production and Render were not touched. Branch is left for the owner to delete (it also holds 2,000 `lt_*@loadtest.example` students, 1 course, 150 questions, 5 images, ~240 MB logical).
- **Where the client ran**: a Mac in Asia. Round trip to Neon (Frankfurt) was **224 ms** (`SELECT 1`, p50). Every DB latency below is therefore `server time + k x 224 ms` (k = round trips). Render is in Frankfurt, so the real k x RTT cost is ~1-3 ms. Read "p50 ~ 226 ms" as "server time ~ 2 ms". Throughput was limited by connection count / RTT unless stated; target rates were driven open-loop (scheduled arrivals, latency measured from the scheduled time).
- Part A: `loadtest/db_bench.py`, psycopg2 + threads, against the **pooled** URL (PgBouncer transaction mode), schema `loadtest` (dropped afterwards).
- Part B: Locust could not be installed (`pip install` was denied by the sandbox), so `loadtest/http_load.py` (httpx asyncio, closed-loop virtual users with 1-3 s think time) was used instead. Tokens are minted with `create_access_token` (bcrypt login measured separately).
- Part B ran against two databases: (1) Neon pooled from the Mac - useless for latency (RTT x ~15 queries per request), kept only for the pool finding; (2) a **local scratch Postgres 18** (RTT ~0) seeded with the same fixtures, because copying the Neon branch (it contains production user data) to a laptop was blocked, correctly. Local results show API CPU and in-process behaviour, not Neon behaviour.
- Server: uvicorn, 1 worker, `LMS_STORAGE_DRIVER=db`, `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` as stated per run. Load generator and server shared one 8-core Mac, so absolute RPS is optimistic vs Render Free by ~two orders of magnitude.

## 2. Part A: database results (Neon pooled, 0.25-2 CU)

Table: 150-row `attempt_items` per attempt; 14,200 attempts / 2.13 M item rows by the end (195 MB).

### 2.1 Attempt start (150 inserts per attempt)

| Variant | Conns | Attempts/s | p50 / p95 (ms) | Errors | 6,000 attempts take |
|---|---|---|---|---|---|
| 2 statements + COMMIT (4 round trips) | 10 | 9.7 | 923 / 1351 | 0 | 619 s |
| same | 25 | 24.5 | 928 / 1035 | 0 | 245 s |
| same | 50 | 46.4 | 933 / 1407 | 0 | 129 s |
| same | 100 | 77.1 | 980 / 1800 | 0 | 78 s |
| same | 200 | 157.5 | 953 / 1431 | 0 | 38 s |
| **one CTE statement, autocommit (1 round trip)** | 50 | 148.7 | 242 / 362 | 0 | 40 s |
| same | 100 | 249.8 | 253 / 392 | 0 | 24 s |
| same | 200 | **421.2** | 259 / 729 | 0 | **14 s** |

Server time per start is ~30-40 ms (p50 minus RTT), i.e. the DB is nowhere near saturated at 421/s: throughput scales linearly with connections in all rows. 6,000 starts in 5 minutes needs only 20/s. Budget "< 2 s attempt start" holds even at 1 s measured from Asia.

### 2.2 Autosave (single-row conditional UPDATE, 60 s each, open loop)

Statement: `UPDATE attempt_items ai SET response=…, updated_at=now() FROM attempts a WHERE ai.attempt_id=… AND ai.item_id=… AND a.id=ai.attempt_id AND a.status='in_progress' AND a.deadline>now()`, autocommit, rowcount must be 1.

| Target/s | Achieved/s | p50 / p95 / p99 (ms) | Errors | Workers |
|---|---|---|---|---|
| 100 | 100.0 | 230 / 713 / 1144 | 0 | 90 |
| 200 | 200.0 | 226 / 313 / 687 | 0 | 150 |
| **300** | **300.0** | 227 / 311 / 688 | 0 | 210 |
| 500 | 500.0 | 226 / 321 / 682 | 0 | 330 |

Server time ~2 ms (p50 - RTT). Variants at 300/s, 30 s: PK-only update 227/319 ms (same as the join variant, so the `attempts` check costs nothing measurable); the same statement inside an explicit transaction (separate COMMIT round trip, what SQLAlchemy does by default) 697/1129 ms - purely one extra RTT here, but it doubles pool hold time on Render too. **Budget p95 < 500 ms holds** (client-measured, including a 224 ms RTT). The p99 tail (~690 ms, max 1-3.6 s) is thread/GIL jitter in my client plus TLS reconnects, not the server.

### 2.3 Submit (6,000 attempts, 50 conns)

Per submit: `UPDATE attempts … WHERE id=… AND status='in_progress' AND deadline>now() RETURNING id`, scoring aggregate over 150 items joined to the key table, `UPDATE … score`, one transaction (5 round trips). 6,000 ok, **0 errors**, 41 submits/s, p50 1171 ms / p95 1560 ms (RTT bound: 5 x 224 ms). Server cost ~0.1 ms of CPU for the aggregate (consistent with `CAPACITY_REVIEW.md`: 0.08 ms). Writing this as one statement (CTE) or running it inside the app with 1-2 round trips makes 6,000 submits take seconds at 200 conns.

### 2.4 Quiz payload read (150 rows, 150 KB)

- Server-side only (aggregate returned): 340/s at 100 conns, **705/s** at 300 conns, p50 232-266 ms, 0 errors; `EXPLAIN ANALYZE` 0.235 ms, 3 buffers. Postgres is not the limit.
- Full payload to the Mac: only 6-13 requests/s (about 2 MB/s of my downlink): client-bandwidth-bound, not representative. Design consequence stands: 6,000 x 150 KB = 900 MB; serve it from CDN/HTTP cache, not per student from the API.

### 2.5 Connection limits

800 simultaneous pooler connections (each running 5 x `pg_sleep(0.05)`): 800/800 ok, 0 errors, 11 s wall (TLS setup bound). No pooler errors up to 800 client connections; the PgBouncer side is not the limit at this scale. Neon CPU is not exposed by the MCP (`cpu_used_sec` stayed 0); `compute_time_seconds` 732 s over 1,460 s active implies ~0.5 CU average during the runs, i.e. autoscaling did not need to reach the 2 CU cap.

## 3. Part B: HTTP results (local Postgres, RTT ~0; one uvicorn worker)

Fixtures: 1 teacher, 2,000 students, published invite-code course, 150-question bank, 5 public images (400x300 noise WebP, db driver). Mix = join once, then loop: `/courses?limit=25`, `/courses/{id}`, `/me/lms`, 1-3 s think, media GET (same few images); 5 % of users are the teacher hitting the question-list page.

| Run | Users | Pool (size+overflow) | RPS | p50 (ms) | Errors | Notes |
|---|---|---|---|---|---|---|
| mix | 50 | 5+5 | 83 | 3-10 | 0 % | healthy (join 10 ms, question list p95 600 ms cold) |
| mix | 200 | 5+5 | 36 | 27-50 | **9.5 %** | p95 30-60 s, 500s and read timeouts |
| mix | 200 | 50+50 | **300** | 3-11 | 0 % | p95 150-540 ms, p99 ~1 s, server CPU 64 % of a core |
| mix | 500 | 50+50 | 17 | 114-690 | **32 %** | stalls, 60 s timeouts |
| mix | 500 | 150+30 | 86 | 197-374 | 3.5 % | p95 20-50 s on the stalled requests |
| join burst | 2,000 in 5 s | 5+5 | 12 | - | 99 % | collapse |
| join burst | 2,000 in 5 s | 50+50 | 12 | - | 99 % | collapse |

(`results/http_mix_200.json` = the 50+50 run, `http_mix_500.json` = the 150+30 run, `http_join_2000.json` = the last join burst; the 5+5 and 500 runs are in this table only.)

### 3.1 Bottleneck found: DB pool / threadpool starvation (real, not a test artefact)

Symptom: with the default 5+5 pool the API stops serving around 10-20 simultaneously in-flight requests; `QueuePool limit … timeout 10` errors, 500s, then 60 s client timeouts. `pg_stat_activity` showed every pool connection `idle in transaction` with last statement `SELECT … FROM users` (the `get_lms_user` lookup) and nothing running.
Mechanism (from the code and the evidence): sync dependencies run on Starlette's 40-thread pool. Per request, `get_current_user` (`app/core/security.py`) opens its own `SessionLocal()`, and `get_lms_user` then reads the user on the request session (`get_db`), which keeps its connection until teardown. Requests that have finished the dependency stage hold a connection while waiting for a thread; the 40 threads are all blocked checking out a second connection for newly arrived requests. Nobody can finish, so the pool only recovers when the 10 s `pool_timeout` fires. The in-flight count is unbounded (every arriving request holds a connection), so no pool size is safe once arrivals exceed it (50+50 fine at 200 users, broken at 500; 150+30 still broken).
Fix options (not done, no app edits allowed): (1) authenticate on the request session only (one connection per request) and release it early (`db.close()`/commit after the auth read) so waiting requests hold nothing; (2) cap in-flight requests below pool size (middleware semaphore returning 503 "retry" for excess, set threadpool tokens = pool size); (3) make hot read/auth paths cheap enough that the DB is not touched twice (JWT user claims cached for a few seconds); (4) `pool_timeout` ~2-3 s so a stall becomes fast 503s instead of 60 s hangs.
This must be fixed before Phase 3: attempt start/autosave arrive in the same bursts that triggered it.

### 3.2 API CPU per request (basis for the Render Free estimate)

CPU time of the uvicorn process (`ps` delta / requests):

| Request mix | CPU per request | Render Free capacity at 0.1 CPU |
|---|---|---|
| join + `/me/lms` | 1.5-2.8 ms | 35-110 req/s |
| mix (list, get, `/me/lms`, media) | 2.1-3.1 ms | **32-47 req/s** |
| login (bcrypt) | **83 ms** | **1.2 logins/s** |

Render Free is not a 1:1 comparison (the local M-series core is faster than a shared 0.1 vCPU slice, and the local run also paid generator contention); treat these as upper bounds, i.e. **at most ~30-45 light requests/s** on Render Free. 300 autosaves/s would need ~0.3 CPU-seconds per second if an autosave costs ~1 ms of Python (JSON parse, auth lookup, ORM, response); realistically 2-3 ms each (as measured above), i.e. 0.6-0.9 of a full core. Not measured: the real autosave endpoint (does not exist yet).

## 4. Representative vs not

| Representative | Not representative |
|---|---|
| SQL cost of start/autosave/submit/read on a 0.25-2 CU Neon through the pooler, incl. table growth to 2 M rows | Client-observed latencies (224 ms RTT inflates everything; in Frankfurt subtract ~k x 224 ms) |
| 800 pooler connections accepted | Real Render Free CPU (estimated, not run) |
| Pool/threadpool starvation (a code property) | Absolute HTTP RPS (generator on the same machine, local PG) |
| API CPU ms per request (relative) | Real autosave/start endpoints (Phase 3 not built); no Vercel rewrite hop; no TLS at the API |
| | Neon autoscaling CPU (not visible via MCP); lock contention with real data distribution (all attempts here are distinct rows, as in production) |

## 5. Go / no-go for the Phase 3 design

- **GO: single-row conditional autosave UPDATE.** 500/s sustained for 60 s, 0 errors, ~2 ms server time, no measurable cost for the `attempts` status/deadline check.
- **GO: one-transaction start snapshot with ~150 inserted rows**, provided it is a single set-based statement/transaction (CTE or `INSERT … SELECT`), not 150 ORM inserts: 421 starts/s at 200 connections, 0 errors; 6,000 in 14 s.
- **GO: submit with in-DB scoring aggregate** (0.1 ms). Do not score in Python from 150 loaded rows.
- **NO-GO as the stack is configured today** for the API tier: (a) pool/threadpool starvation (section 3.1) collapses the service under bursts; (b) Render Free (0.1 CPU) tops out at ~30-45 light requests/s and 1.2 logins/s: 6,000 students logging in at once would take over an hour of CPU; 300 autosaves/s is ~10x over its capacity. The design is sound; the runtime must change.

## 6. Recommendations

1. **Fix the pool starvation first** (section 3.1, options 1+2+4). Test: re-run `loadtest/http_load.py mix 500` and a 2,000-user join burst against the fix; require 0 % errors at pool 10-20.
2. **Autosave write path**: client-side batching (debounce 2-5 s, flush on navigation/submit) cuts 300 writes/s to ~60-100/s without changing the server design; use one HTTP request carrying several answers and one `UPDATE … FROM (VALUES …)`, still one round trip. Use autocommit single statements (no separate COMMIT round trip) and keep it a single transaction.
3. **Pool sizes**: after the fix, `DB_POOL_SIZE` ~ number of busy threads (10-20), `DB_MAX_OVERFLOW` 0-5, `DB_POOL_TIMEOUT` 2-3 s. Neon pooled URL only (PgBouncer; the direct endpoint caps at ~100 at 0.25 CU). Keep the 2+3 rate-limit pool but note every join/login costs 2-3 extra rate-limit writes.
4. **Render plan for exam windows (needs the owner's OK, costs money)**: Free is not viable. Starter ($7/mo, 0.5 CPU, no sleep) is ~5x Free CPU - still short. Plan for Standard (1 CPU, ~$25/mo rate) or Pro (2 CPU, ~$85/mo rate), billed per second during a 3-hour window, with several instances behind Render's load balancer so that total capacity = N x cores x ~(1/2.5 ms) = ~400 light req/s per core. Need for 6,000 students with batched autosave (~100 req/s) plus bursts (starts 20-40/s, logins spread out): 2-4 cores total. Login bcrypt: 83 ms/login means 6,000 logins = 500 core-seconds - stagger or pre-authenticate (long-lived tokens issued before the exam).
5. **Neon compute**: free 0.25-2 CU (as production) was enough for every DB test (avg ~0.5 CU); the pooled endpoint accepted 800 connections. Autosave at 500/s needs well under one core of DB CPU. Paid step only for storage/history: 2 M item rows = 195 MB, so 6,000 attempts x 150 rows = 900 k rows ~ 85 MB per exam; the free 0.5 GB limit allows ~5 exams of data - budget Launch ($19/mo class) or prune/archive `attempt_items` after grading. Prices are from memory, verify before buying.
6. **Quiz payload**: serve the (identical) quiz JSON and images from CDN with `Cache-Control`/ETag; per-student API reads of 150 KB are 900 MB of egress per exam. `GET /media/{sha}.webp` works and is immutable-cached already.
7. Re-run this suite (`db_bench.py`, `http_load.py`) from a machine in Frankfurt (e.g. Render shell/CI runner) for client-latency numbers without the 224 ms RTT, and again once the real Phase 3 endpoints exist.

## 7. Reproduce

```
BENCH_DATABASE_URL=<pooled url> python loadtest/db_bench.py setup start_cte start_full autosave autosave_variants submit read_server conns cleanup
LT_STATE=<state.json from seed.py> LT_RAMP=10 loadtest/run_http.sh mix 200 40   # run from <worktree>/backend
```
Gotcha: `pkill` does not stop a uvicorn with stuck threads - kill by PID (`kill -9 $(lsof -ti tcp:8000)`) between runs, or results come from a stale server.
