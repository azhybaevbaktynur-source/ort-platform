# Phase 3 — Assessments, attempt engine, grading, player

**Status**: done 2026-10-23 on branch `phase-3/assessments`, merged into `lms` (not `main`; ships at the Phase 5 cutover). Design: `PHASE_3_DESIGN.md`; load test: `PHASE_3_LOADTEST.md`; decisions: `PRODUCT_DECISIONS.md` ("Phase 3").

## What changed

- **Schema** (Alembic `0004_phase3_assessments`): `assessments`, `assessment_sections`, `assessment_items`, immutable `assessment_versions` (publish snapshot), `attempts`, `attempt_sections`, `attempt_items`.
- **Builder and publish** (`app/lms/assessments/`): sections, items (questions, passages with children, random picks from banks), ORT rules (math_1 comparison, section order), publish = immutable snapshot; per-process plan and student-payload caches with byte caps; `after_close` results need an end date.
- **Attempt engine** (`app/lms/attempts/`): start = one multi-row insert from the snapshot; server deadlines with 45 s grace; forward-only sections served one at a time (no reading ahead); autosave = one conditional UPDATE per answer (<= 20 per request, `client_ts` ordering); one-shot submit (lock order attempts -> sections -> items, all item locks up front); lazy expiry plus a session-locked sweep; `SubmitOut.saved`/`rejected` tell the client which final answers were stored (B2).
- **Grading and results**: grading through the type registry (`score()`), finalize exactly once (hook per attempt), results policies `never` / `after_submit` / `after_close`, review with keys only when allowed, staff attempt list and manual scoring.
- **Platform**: `get_lms_user` single pool checkout; DB-backed rate limits; global API body cap (1 MiB, attempts lower); per-process admission gate (B1: N = min(thread tokens, pool + overflow), 503 `server_busy` + Retry-After after 20 s, capped bodies read before a slot is taken); `Cache-Control: private, no-cache` on attempt content.
- **Frontend**: assessment builder, publish flow, student list and lobby; player with server clock, offline autosave queue (localStorage per user, cleared on logout), last-minute continuous flush that respects server Retry-After, forward-only section flow, unsaved-answers notice; results and review; staff attempts and manual grading. 1211 i18n keys (en/ky/ru).
- **Reviews**: architect review and final security review (submit/autosave deadlock, numeric overflow poisoning the sweep, body caps, early `after_close`, start limit counting resumes, submit after enrollment removal, reading later sections early, browser-cache replay, queue left after logout, sweep lock lifetime, plan cache size) — all fixed with tests.
- **Load test** (merge gate, local M1 + PG 18, 6,000 virtual students): first run NO-GO (pool/threadpool livelock under overload, submit-body answers dropped silently after grace); after B1/B2 re-runs R9/R10: 0 pool timeouts, 0 5xx, 0 lost answers, 0 double grades, all 6,000 attempts finalized. Capacity per Render plan in `PHASE_3_LOADTEST.md` §7; re-run in §11.

## How to verify

```bash
cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" venv/bin/python -m pytest -q -p no:cacheprovider -W ignore
# Postgres full suite: one UTF8 DB (TEMPLATE template0), PGTZ=UTC, and BOTH URLs with the psycopg2 driver
#   DATABASE_URL=LMS_PG_TEST_DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:55432/<db>
```
Exit criteria: `tests/lms/test_phase3_flow.py` (end-to-end ORT quiz), `test_attempt_integrity.py`, `test_pg_concurrency_attempts.py`, `test_grading_pg_concurrency.py`, `test_admission.py`, `test_submit_b2.py`; load test `loadtest/exam_{seed,load,verify}.py`.

## Deferred / owner input

- **Exam-window capacity (spending, owner decision)**: a 6,000-student exam needs about 4 Render CPUs (Pro Plus, billed per second) — Free/Starter cannot carry it. Estimates from a local M1; confirm on Render before the first real exam.
- **Storage**: `attempt_items` is about 230 B/row (about 0.2 GB per 6,000 x 150 exam); Neon Free holds about two such exams.
- Client retry on 503 `server_busy` was not exercised by the load test (no request waited 20 s).
- On a fresh DB, several workers race in `init_db` at first start (harmless warnings).
