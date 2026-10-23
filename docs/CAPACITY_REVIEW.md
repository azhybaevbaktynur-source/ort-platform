# Capacity review (interim, 2026-10-22)

**Question**: can Vercel + Render + Neon run the LMS for ~6,000 concurrent students on about $30/month?
**Status**: interim. Inventory and database CPU costs are measured; HTTP-level load tests (free resources, decision D) are NOT done yet. Prices are from memory and unverified.

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
| 2 | All API traffic proxied through Vercel | Fix: set `NEXT_PUBLIC_API_URL` to the Render URL (CORS already configurable). Removes a hop and Vercel request/bandwidth load. Postponed by the owner (2026-10-22); when resumed, no approval needed (decision A in `PRODUCT_DECISIONS.md`). |
| 3 | Vercel in US, backend in Frankfurt | Fixed on branch `perf/capacity-prep` (`frontend/vercel.json`, `fra1`); merged to `main` 2026-10-22. |
| 4 | Default DB pool, no timeouts | Configurable on the branch (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`, `DB_POOL_TIMEOUT`). Statement timeout is opt-in because pooled (PgBouncer) URLs reject startup options. |
| 5 | Large question payloads | gzip added on the branch. Design rule: exam content is identical for all students, so cache it at the CDN instead of rebuilding per start. |
| 6 | Neon free (max 2 CU) | Unverified for bursts; likely needs Launch for exam periods. Use the pooled connection string. |
| 7 | Vercel Hobby is non-commercial | Re-check before charging anyone (Pro is $20/seat). |

## 4. Cost model (unverified prices)

- Normal days: Neon free-Launch ($0-15) + Render Starter ($7) + Vercel Hobby ($0) + R2 (~$1) = about **$8-25/month**.
- Exam window: Render Standard (~$25/mo rate) or Pro (~$85/mo rate) billed per second, so a 3-hour exam costs cents to under a dollar.
- Fallback if the daily load is heavy: a single 4 vCPU VPS (~EUR 15) for the API, Neon for the database.

## 5. Next steps

1. ~~Merge `perf/capacity-prep`~~ (done). `NEXT_PUBLIC_API_URL` postponed by the owner. Upgrading Render to Starter costs money: owner OK required (decision A).
2. Before Phase 3, on free resources (a Neon branch + local or free-tier backend; decision D), run `k6` against the **old** endpoints for connection and CPU limits; then re-run against LMS endpoints as they appear (Phase 3 attempt engine).
3. Reduce load by design: cached exam payload, client-side autosave batching, in-memory scoring from the snapshot.
4. Decide D4 with the measured numbers, and delete scratch branch `scratch-loadtest-2026-10-22`.

## 6. R2 free tier (Phase 5)

Owner requirement 8: Cloudflare R2 has no spending cap, so the app keeps itself inside the free tier (10 GB-month stored, 1,000,000 Class A and 10,000,000 Class B operations per month, Standard class only; no Infrequent Access, no lifecycle rules). Design: `docs/phases/PHASE_5_DESIGN.md` §6 (P5-11, P5-12).

**What the app enforces**
- `storage_usage` counts every byte and object ever written (`app/lms/files/usage.py`, updated on its own connection right after a NEW blob is stored; dedup hits write nothing). On r2 nothing is deleted or listed, so the counter only grows: it is an upper bound of what R2 bills.
- Warn at `STORAGE_WARN_BYTES` = 8 GB (8,000,000,000 bytes, decimal like Cloudflare's free tier) (amber banner in `/[lang]/admin` and `/[lang]/admin/storage`), refuse new blobs at `STORAGE_HARD_BYTES` = 9.5 GB (9,500,000,000 bytes) (HTTP 507 `storage_full`, trilingual message). Both are settings (env vars), no code change needed to lower them.
  - Decimal units on purpose: 9.5 GiB would be 10.2 decimal GB, above the 10 GB free tier.
- Upload caps: images 2 MiB (re-encoded to WebP, usually far smaller), PDF files 10 MiB (private bucket, owner-only download by presigned URL). Images are content-addressed (`img/{sha256}.webp`) and stored with `Cache-Control: public, max-age=31536000, immutable`, served from `R2_PUBLIC_BASE_URL`, never through the backend.
- No list call in any request path. Class B reads are **estimated at read time** in the admin summary (`attempts started this month × distinct images in that exam version`), so the attempt hot path writes nothing.

**Arithmetic for a 6,000-student ORT exam**
- One digitized 150-question ORT exam has about 16 images (production: 16 image refs in 150 questions). Stored WebP is 3-30 KB each (tsoomo19 sample: 2.8 KB), so 16 × 30 KB = 480 KB < **1 MB per exam**.
- Storage: rounding up to 1 MiB per exam, 9.5 GB / 1 MiB ≈ 9,060 exams; at the real worst case of 480 KiB (16 × 30 KiB), 9.5 × 10⁹ / (16 × 30 × 1024) ≈ 19,330 exams. **Storage holds thousands of exams**; it is not the limit.
- Class A (writes): ≤ 1 PUT per new image (the HEAD before it is Class B) → 16 per new exam. 1,000,000 / 16 = 62,500 new exams per month. Irrelevant.
- **Class B (reads) is the limit**: one sitting = 6,000 students × 16 images = **96,000 public reads** (the browser cache keeps repeats within one attempt out). 10,000,000 / 96,000 ≈ **104 full 6,000-student exam sittings per month** (about 100). A 30-question subject test with 5 images: 6,000 × 5 = 30,000 reads → about 333 sittings per month.
- The admin page shows this month's Class A (counted), Class B by the backend (counted) and Class B estimated (computed); compare with 1,000,000 / 10,000,000.
- Neon side unchanged: `attempt_items` ≈ 0.2 GB per 6,000 × 150 exam (PHASE_3.md).

**Real risk: r2.dev.** `R2_PUBLIC_BASE_URL` is the r2.dev address until the owner buys a domain. r2.dev is rate-limited (Cloudflare publishes no number) and not meant for production; a 6,000-student burst (96,000 image GETs in minutes) can hit it. Before the first large exam, move public images to a custom domain on the bucket (owner purchase, owner item 4); the admin storage page shows `public_base_is_r2dev` as a standing reminder.

**Verification without secrets**: `/[lang]/admin/storage` → "Run R2 check" (`POST /platform/storage/smoke`, platform admin, 5/hour, audited `storage.smoke`) or `python -m app.lms.files.smoke` on the server: puts a fixed 1-px WebP, HEADs it, reads it from `R2_PUBLIC_BASE_URL` over HTTPS, deletes it. Each run costs 1 Class A + 2 Class B operations.
