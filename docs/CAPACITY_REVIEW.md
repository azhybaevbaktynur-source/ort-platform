# Capacity review (interim, 2026-10-22)

**Question**: can Vercel + Render + Neon run the LMS for ~6,000 concurrent students on about $30/month?
**Status**: interim. Inventory and database CPU costs are measured; HTTP-level load tests against a staging copy are NOT done yet. Prices are from memory and unverified.

## 1. Inventory (measured / reported)

| Component | Today | Source |
|---|---|---|
| Render API | **Free** plan, Frankfurt, `uvicorn app.main:app` (1 worker), auto-deploy from `main`. About 0.1 CPU, 512 MB, sleeps when idle. | owner, from dashboard (Render MCP stayed "unauthorized") |
| Neon | project `noisy-sound-20763725`, plan `free_v3`, eu-central-1, autoscaling 0.25-2 CU, Postgres 18, 10-branch limit, suspend setting locked by plan | Neon API |
| Vercel | Next.js project, region was `iad1` (US East), SSO protection on previews only (production URL is public: HTTP 200) | Vercel API, curl |
| API path | Frontend calls `/api/v1` and Vercel **rewrites** it to Render (and `/uploads`) unless `NEXT_PUBLIC_API_URL` is set | `frontend/next.config.ts`, `src/lib/api.ts` |
| DB pool | SQLAlchemy defaults (5+10), no timeouts, one user query per request | `backend/app/db/session.py`, `core/security.py` |

## 2. Measured database cost (scratch Neon branch, copy of production, 0.25-2 CU)

One backend session, loops inside a single transaction, so **CPU cost only, no commit or network latency**:

| Hot path | Measured |
|---|---|
| Attempt start: 150-row `INSERT ... SELECT generate_series` | 0.32 ms per attempt |
| Autosave: single-row `UPDATE` by primary key | 0.023 ms per op |
| Submit scoring: join 150 items with the key table | 0.08 ms per attempt |

Reading: statement CPU is not the bottleneck. 300 autosaves/s and 20 starts/s need well under 1% of one core. **The real costs will be commits (each autosave is its own transaction; a commit waits for WAL durability), connection handling, and API-side CPU (JSON, auth, ORM).** These can only be measured with concurrent HTTP clients.

## 3. Findings and verdicts (before load tests)

| # | Finding | Verdict |
|---|---|---|
| 1 | Render Free: sleeps, ~0.1 CPU, 1 worker | **No-go.** Must be a paid plan before any real use. Starter ($7) removes sleeping; exam windows need Standard/Pro, billed per second. |
| 2 | All API traffic proxied through Vercel | Fix: set `NEXT_PUBLIC_API_URL` to the Render URL (CORS already configurable). Removes a hop and Vercel request/bandwidth load. Needs owner approval (env var change). |
| 3 | Vercel in US, backend in Frankfurt | Fixed on branch `perf/capacity-prep` (`frontend/vercel.json`, `fra1`). Not merged. |
| 4 | Default DB pool, no timeouts | Configurable on the branch (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`, `DB_POOL_TIMEOUT`). Statement timeout is opt-in because pooled (PgBouncer) URLs reject startup options. |
| 5 | Large question payloads | gzip added on the branch. Design rule: exam content is identical for all students, so cache it at the CDN instead of rebuilding per start. |
| 6 | Neon free (max 2 CU) | Unverified for bursts; likely needs Launch for exam periods. Use the pooled connection string. |
| 7 | Vercel Hobby is non-commercial | Re-check before charging anyone (Pro is $20/seat). |

## 4. Cost model (unverified prices)

- Normal days: Neon free-Launch ($0-15) + Render Starter ($7) + Vercel Hobby ($0) + R2 (~$1) = about **$8-25/month**.
- Exam window: Render Standard (~$25/mo rate) or Pro (~$85/mo rate) billed per second, so a 3-hour exam costs cents to under a dollar.
- Fallback if the daily load is heavy: a single 4 vCPU VPS (~EUR 15) for the API, Neon for the database.

## 5. Next steps

1. Merge `perf/capacity-prep` (owner OK), set `NEXT_PUBLIC_API_URL` (owner OK), upgrade Render to Starter (owner action).
2. Build a staging copy (second Render service + a Neon branch) and run `k6` against the **old** endpoints for connection and CPU limits; then re-run against LMS endpoints as they appear (Phase 3 attempt engine).
3. Reduce load by design: cached exam payload, client-side autosave batching, in-memory scoring from the snapshot.
4. Decide D4 with the measured numbers, and delete scratch branch `scratch-loadtest-2026-10-22`.
