# Phase 11: mixed load test (S5)

**This does not prove 6,000 students.** At 6,000 on this machine the server was saturated: saves took a median of 14 s. It was a local test on a laptop, free, against scratch data; nothing ran against Render, Vercel or Neon.

## Size reached on this machine
**3,000 students saving (150 saves per second) plus 60 readers**, in the better of two runs: save p50 17 ms, p95 249 ms, p99 1.2 s, no errors. The second run at the same size had a stall of about 90 s; the machine was slightly busier (load 7.6 against 6.2), and the cause was not identified. During the ramps of the two larger runs the server fell behind at about 3,750 students (about 190 saves per second) and did not recover during the run.

| Run | Students saving | Readers | Workers | Saves/s | Save p50 ms | p95 | p99 | Home p95 | Notebook p95 | Statistics p95 | Org overview p95 | Errors | Lost saves | Load avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `n1000` | 1000 | 40 | 2 | 49.9 | 10 | 38 | 139 | 102 | 73 | 130 | 386 | 0/11007 | 0/18801 | 3.1 |
| `n3000b` | 3000 | 60 | 2 | 149.3 | 17 | 249 | 1181 | 501 | 295 | 1197 | 904 | 0/29896 | 0/62512 | 6.2 |
| `n3000` | 3000 | 60 | 2 | 141.8 | 41 | 6197 | 12035 | 3677 | 4507 | 4182 | 4137 | 14/28035 | 0/61181 | 7.6 |
| `n4500` | 4500 | 60 | 2 | 166.5 | 6632 | 14923 | 20318 | 13710 | 14184 | 14310 | 13035 | 36/31077 | 0/89400 | 7.6 |
| `w4_n6000` | 6000 | 60 | 4 | 170.0 | 14330 | 25743 | 32938 | 28920 | 25471 | 25712 | 33060 | 3/26433 | 0/104593 | 12.4 |

Times in ms, steady window only (after the ramp). Raw results: `loadtest/results/mixed_<run>.json`. All errors are client-side `ReadError` (connection reset), no 5xx in those five runs. "Lost saves" compares every acknowledged answer with the database afterwards.

**Setup**: `loadtest/perf_seed.py` data, reseeded before each run; `uvicorn` with 10+10 pool and 20 thread tokens per worker; admission gate on, as in the Phase 3 runs. Students start during a ramp of n/25 seconds, then save 1 to 5 answers every 15 to 25 s. Readers wait 2 to 5 s between requests: 60 % students (home, notebook, progress), 25 % teachers (statistics, course analytics), 15 % org admins. The statistics cache of the 4,000-attempt exam is invalidated every 60 s, so real refreshes run during the test. Load generators ran on the same machine.

## What we learned
- **Nothing acknowledged was lost**, even saturated: 0 of about 336,000 acknowledged answers.
- **The saturation point stayed near 170 to 200 requests per second**, with 2 workers or 4. Phase 3's 6,000-student exam run also saturated (autosave p50 7.1 s at 233 per second). More workers did not help here, probably because server, Postgres and generators share 8 cores; this is inferred, not measured.
- **The database is not what was waiting.** During stalls Postgres connections were mostly `idle in transaction`, waiting on Python. This is sampled, not profiled: the exact cause inside the server was not measured. The CPU columns in the JSON are approximate, because backends that exit drop out of the sampling.
- **Statistics refresh under load is visible but short**: at 1,000 students the statistics route had p99 2.7 s and max 4 s, while saves stayed at p95 38 ms.
- **The test is sensitive to other work on the machine.** An early run at 1,000 students (not in the table), at load 8 with other test suites running, stalled for 20 s; the stall went away on a quieter machine. Runs at 2,000 at load 11 to 16 were saturated. An autosave-only control at 2,000 under that load was worse than the mixed run, which points away from the reads, although that database also still held the open attempts of earlier runs.

## What local measurements cannot tell us about 6,000 students
- **The real limit.** Render CPU, Neon compute (0.25 to 2 CU), remote storage and the connection pooler are all different from a local Mac with a local SSD and no network between server and database. Neither direction can be read from these numbers.
- **Network and TLS.** No client round trip, no TLS, no Vercel in the path.
- **A whole exam.** This is steady autosave plus reads. It has no section closes, no submit burst at the deadline and no start burst within a minute. Phase 3's `exam_load.py` covers those, also only locally. No full exam ran in this slice.
- **Login.** Tokens are minted directly, so no bcrypt.
- **Real browsers.** Page loads, images from R2 and asset traffic are not included.
- **Real data.** Seeded rows are shaped like real ones but not produced by the engine. Real distributions of practice use and courses per student will differ.
- **Cold caches.** The numbers come from a warm local cache. Neon can scale to zero and start cold.

Proving 6,000 needs the same scripts on paid infrastructure near Frankfurt: an owner decision (`PHASE_11_DESIGN.md` §8).

## Rerun
```bash
cd backend
export DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:<port>/<db> LMS_STORAGE_DRIVER=db LOCAL_UPLOAD_DIR=<scratch>/up \
       LT_STATE=<scratch>/perf_state.json LT_BASE=http://127.0.0.1:8177 LT_OUT=<scratch>/mixed
alembic upgrade head && python ../loadtest/perf_seed.py
DB_POOL_SIZE=10 DB_MAX_OVERFLOW=10 LMS_THREADPOOL_TOKENS=20 uvicorn app.main:app --port 8177 --workers 2 --log-level warning &
python ../loadtest/mixed_load.py <label> <students> <readers> <steady seconds>
```
Run it in a worktree (no `backend/.env`). Both scripts refuse any non-local host. Reseed between runs: each leaves its attempts open. `exam_seed.py base` is out of date since Phase 6 (the course needs `template_key="ort"` for the bundle import); `perf_seed.py` sets it, and `exam_seed.create_exam` still works.
