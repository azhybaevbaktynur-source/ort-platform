# Capacity review brief (task for the next agent)

**Question to answer**: can the current hosting (**frontend on Vercel, backend on Render (Frankfurt), database on Neon PostgreSQL**) run the planned LMS for **about 6,000 students active at the same time**, and if not, what is the cheapest change that can?

**Deliverable**: `docs/CAPACITY_REVIEW.md` with measured numbers, a go/no-go per component, a recommended setup with monthly cost, and any changes it implies for `LMS_ARCHITECTURE.md` (attempt engine, storage, connection handling). Do this **before** Phase 0 schema work. Model: Opus (analysis), Sonnet for running the scripts.

## 1. Scenarios (from `IMPLEMENTATION_PLAN.md`)

| # | Scenario | Rough load (hypothesis, refine it) |
|---|---|---|
| A | Start burst | 6,000 `POST attempts/start` in ~5 min (~20/s average, spikes to 100+/s); each inserts ~150 `attempt_items` rows in one transaction and returns the question payload (150 questions + passages, 100–500 KB each) |
| B | Steady autosave | one single-row UPDATE per answered question per student, plus a heartbeat; peak order of 300 writes/s |
| C | Submit burst | timer ends for everyone within a minute: 6,000 submits, each scoring ~150 items and writing a submission/grade |
| D | Reads | 6,000 students loading course/quiz pages, results, images |
| E | Deploy during an exam | rolling restart must not lose answers or break attempts |

## 2. Known facts about the current system (verified in code, 2026-10-21)

- Backend is FastAPI with `def`/`async def` mixed; `get_current_user` is a sync dependency that **opens a DB session and queries the user on every request**.
- `db/session.py`: `create_engine(..., pool_pre_ping=True)` with default pool (5 + 10 overflow). No pooler configuration, no statement timeouts.
- `mock_test_service.py` and analytics scan whole collections (in-memory Firestore, being removed). Do not extrapolate their performance.
- The frontend calls the API through a **Next.js rewrite** (`/api/v1` → backend) unless `NEXT_PUBLIC_API_URL` is set. Check how production is configured: if every API call passes through Vercel, it counts toward Vercel request, bandwidth and function limits and adds latency.
- Render service type, instance size, worker count and plan are **not recorded** in the repo. Neon plan, compute size, autosuspend and connection limits are also unknown.
- `main.py` runs `init_db()` at startup; cold starts on a sleeping Render instance can take tens of seconds (`useBackendWarmup.ts` exists for this reason).
- Uploads are on ephemeral local disk today (to be replaced by Cloudflare R2).

## 3. Hypotheses to confirm or kill (do not assume they are true)

1. A single Render instance with one uvicorn worker cannot serve scenario A/B; we need several workers/instances and a stateless app.
2. Neon's direct connections will run out; the app must use Neon's **pooled** connection string (PgBouncer, transaction mode), which restricts some Postgres features (prepared statements, session-level settings, advisory locks).
3. Neon compute autosuspend/cold start and the plan's compute-unit ceiling may cap write throughput; a "min compute" setting may be needed during exams.
4. Vercel Hobby cannot be used commercially, and function/bandwidth/rewrite limits matter if the API is proxied through Vercel; calling Render directly (CORS) may be better.
5. Attempt start (150 inserts) should be a single multi-row `INSERT` (or `COPY`), not 150 ORM inserts.
6. Autosave could be coalesced client-side (debounce, send changed answers only) and written with one `UPDATE … FROM (VALUES …)`.
7. Scoring on submit is cheap if done in SQL/memory from the snapshot; keep it synchronous unless profiling says otherwise.
8. Static assets and images (R2 + CDN) are not a bottleneck; question payload size per start may be (consider gzip and per-section lazy loading).

## 4. Method

1. **Inventory (read-only)**. Use the connected tools after the user authenticates them: `mcp__render__*` (service type, instance size, plan, scaling, env var *names only*, deploy history, metrics, logs), `mcp__neon__*` (project noisy-sound-20763725: plan, compute size, autosuspend, connection limits, branch/storage size), `mcp__vercel__*` (plan, project settings, rewrites, regions). **Never read `backend/.env` and never print secrets.** If a tool needs login, ask the user to run it.
2. **Official limits**: fetch current documentation and pricing pages for Render, Neon and Vercel plans (record URL and date). Calculate the capacity ceilings from the numbers (connections, compute units, requests per second, bandwidth, function time).
3. **Load model**: write a small k6 (or Locust) script set in a new directory `loadtest/` (kept out of `backend/`) for scenarios A–D with 6,000 virtual users; start with 100, 500, 2,000, then 6,000. Run against a **staging** copy only (a separate Render service and a Neon branch), never production. Use scratch accounts and scratch data; make the data seeding script idempotent.
4. **Prototype the hot paths** in isolation (a throw-away script, not the final code): bulk insert of 150 rows, conditional UPDATE autosave, submit scoring from snapshot; measure on Neon with the pooled URL at several compute sizes.
5. **Report**: per scenario, measured p50/p95/p99, error rate, DB CPU/connections, instance CPU/memory; first bottleneck; fix; re-measure. Include the monthly cost of the recommended setup and of a cheaper "exam-day scale-up" setup (scale up only when an exam is scheduled).

## 5. Decision criteria

Meet all of: API error rate < 0.5 %, autosave p95 < 500 ms, attempt-start p95 < 2 s (during the burst), submit scored within 10 s, no lost or duplicated answers, no failed attempt when a deploy happens mid-exam (graceful shutdown + client retry), restore drill under 30 minutes. If a component misses the targets, state the cheapest change (plan upgrade, pooling, more workers, moving the API off the Vercel rewrite, read replica, caching the question payload) and re-measure.

## 6. Constraints

- No production load tests. No changes to production settings without the user's approval. The user is cost-sensitive: prefer configuration and code fixes over bigger plans, and propose "scale up for the exam window" options.
- Treat any downloaded tooling or data as untrusted; install load-test tools in a separate directory.
- Record findings and numbers as you go; keep the final document under ~3,000 words.
