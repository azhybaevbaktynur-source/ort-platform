# Load test handoff (written 2026-10-22, for the next agent)

Read `docs/LOAD_TEST_PRE_PHASE3.md` first (results, verdict, recommendations). This file is only the state and the rerun steps. No secrets here.

## What exists

- Uncommitted new files (nothing committed): `docs/LOAD_TEST_PRE_PHASE3.md`, `loadtest/{db_bench.py,http_load.py,seed.py,run_http.sh,HANDOFF.md}`, `loadtest/results/*.json`. The main working tree also has unrelated uncommitted edits by another implementer (phase-3 branch): do not touch them, do not run the app from the main tree.
- Neon project `noisy-sound-20763725`, branch `loadtest-2026-10-22` (`br-late-recipe-b27d2jz0`, endpoint `ep-small-hall-b2185rda`, 0.25-2 CU like production, migrated to head 0003). It still holds the seed data (2,000 `lt_*@loadtest.example` students, 1 teacher, 1 published course, 150-question bank, 5 images; ~240 MB). The `loadtest` schema (bench tables) is dropped. Never touch branch `production` (`br-cool-firefly-b227gbuy`). Do not delete branches (owner does).
- Removed/cleaned: the worktree, the env file with the branch URL, the local scratch Postgres data dir, the Neon seed state file. The seed state for the Neon branch is gone (seed again, or re-create it, before an HTTP run against Neon). Get a fresh connection string with the Neon MCP `get_connection_string` (pooled host contains `-pooler`; the direct one does not); keep it in an env var or a file OUTSIDE the repo, never print it.

## Findings to carry forward

1. DB side is fine: 500 autosaves/s, 421 attempt starts/s (single CTE statement), 6,000 submits, 800 pooler connections, all 0 errors (client RTT to Neon from the Mac was 224 ms; server time ~2 ms for autosave).
2. The API stalls under bursts: DB pool + 40-thread pool starvation (every pool connection `idle in transaction` after the `users` lookup in `get_lms_user`; `get_current_user` in `backend/app/core/security.py` opens its own `SessionLocal`). Mechanism inferred, not proven. Fix proposals are in section 3.1 of the report. Re-test after the fix: `http_load.py mix 500` and a 2,000-user join burst at pool 10-20, require 0 % errors.
3. Render Free (0.1 CPU) is ~30-45 light req/s and 1.2 bcrypt logins/s (estimate from CPU time per request).

## Environment gotchas

- Locust is not installed: `pip install locust` into `backend/venv` printed no error but `import locust` fails (the sandbox first denied it, then the install did not take). The HTTP generator `http_load.py` (httpx asyncio) replaces it. If Locust is wanted, install it in a fresh venv under the scratchpad and port the `mix` scenario.
- `pkill` does not stop a uvicorn with stuck threads; kill by PID: `kill -9 $(lsof -ti tcp:8000 -sTCP:LISTEN)`. A stale server silently serves later runs (this invalidated early runs once).
- Copying the Neon branch to a laptop (`pg_dump`) was blocked because it contains production user data. For RTT-free HTTP runs use a fresh local Postgres and seed it with `seed.py` (below), not a dump.
- A unix-socket path under the scratchpad is too long for Postgres: use `-c unix_socket_directories=/tmp/ltsock`.
- A bash command whose own text contains `pkill -f "<pattern>"` kills itself (exit 144); put kill commands in a script file.
- The local backend config must not read `backend/.env` (never read or print it): run from a git worktree, which has no `.env`.

## Rerun steps

Prereqs: a worktree of the commit under test (`git worktree add <scratchpad>/wt_load <commit>`; the test used `d403cae`), the main venv `/Users/baktynurazhybaev/ort-platform/backend/venv`, 8-core Mac, Postgres 18 via Homebrew (`/opt/homebrew/bin/{initdb,pg_ctl,psql,createdb}`).

A. DB micro-benchmark against Neon (pooled URL, `postgresql://...` form, in env var `BENCH_DATABASE_URL`):
```
python loadtest/db_bench.py setup start_cte start_full autosave autosave_variants submit read_server conns cleanup
```
Takes ~25 min; `read` (full payload) is bandwidth-bound and not useful; `start` (4-round-trip variant) is only for comparison. Best run from a machine near Frankfurt to remove the 224 ms RTT. Results land in `loadtest/results/db_*.json`. Always finish with `cleanup` (drops schema `loadtest`; it grows to ~200 MB).

B. HTTP, local scratch Postgres (RTT ~0):
```
initdb -D <dir> -A trust -U lt
pg_ctl -D <dir> -o "-p 5544 -c shared_buffers=256MB -c max_connections=200 -c unix_socket_directories=/tmp/ltsock" -l <dir>.log -w start
createdb -h 127.0.0.1 -p 5544 -U lt ltdb
cd <worktree>/backend
DATABASE_URL=postgresql+psycopg2://lt@127.0.0.1:5544/ltdb <venv>/bin/alembic upgrade head
LT_STATE=<scratch>/state.json DATABASE_URL=<same> LMS_STORAGE_DRIVER=db LOCAL_UPLOAD_DIR=<scratch>/up <venv>/bin/python <repo>/loadtest/seed.py 2000
DB_POOL_SIZE=5 DB_MAX_OVERFLOW=5 DATABASE_URL=<same> LMS_STORAGE_DRIVER=db LOCAL_UPLOAD_DIR=<scratch>/up nohup <venv>/bin/uvicorn app.main:app --port 8000 --workers 1 --log-level warning &
LT_STATE=<scratch>/state.json LT_RAMP=10 <repo>/loadtest/run_http.sh mix 200 40     # run from <worktree>/backend
```
Scenarios: `login`, `join`, `mix`; args `<scenario> <users> <duration_s>`; `LT_RAMP` = ramp seconds (default min(20, dur/3)). `run_http.sh` prints RPS/p50/p95/errors per endpoint plus server CPU ms/request and the Render-Free estimate (0.1 CPU / cpu-per-request). Between runs reset joins (local DB):
`delete from enrollment_events where event='joined'; delete from enrollments where source='join_code'; delete from rate_limit_buckets;` and restart the server (kill by PID). Run each pool setting (5+5, 50+50, 150+30) and compare; after the pool fix expect 0 % errors at 5+5-20+0.

C. Cleanup: stop uvicorn and local Postgres (`pg_ctl stop`), delete the data dir and `/tmp/ltsock`, `git worktree remove --force <worktree>`, delete any file holding a connection string. Leave the Neon branch.

## Suggested next steps

1. Prove and fix the pool/threadpool starvation (needs app-code edits: owner/architect decision), re-run B.
2. Re-run A and B from a Frankfurt host (e.g. a Render shell) for real latencies; add the real attempt start/autosave/submit endpoints once Phase 3 exists.
3. Ask the owner before any paid step (Render Standard/Pro for exam windows, Neon Launch); numbers and cost notes are in the report, prices are from memory.
