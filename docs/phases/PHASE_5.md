# Phase 5 — ORT cutover

**Status**: built 2026-10-23 on branch `phase-5/cutover` (slices S1-S6). Deploy to `main`: pending deploy (orchestrator updates this line). Design: `PHASE_5_DESIGN.md`; decisions P5-1..P5-13 in `PRODUCT_DECISIONS.md`.

## What changed

- **Old system removed**: `ExamSet`, `ExamAccess`, `TestAttempt`, `QuestionSource`, old question tables and endpoints, Firebase mock, mock tokens, runtime ALTER helpers, `users.role` and old score columns, PINs, old `(admin)`/`(student)` routes. Alembic `0006_phase5_cutover` (one-way, downgrade raises) exports exam sets to `legacy_ort_export` and drops the old tables in one transaction; `0007_phase5_storage` adds R2 usage counters.
- **ORT as courses**: `ensure_ort_courses()` (lifespan + CLI) creates "ORT (Kyrgyz)" and "ORT (Russian)", converts exported exam sets through the Phase 2 importer and Phase 3 builder into published `ort_main`/`ort_subject` assessments, enrolls platform admins as co-teachers, and is idempotent. Dev/test DBs seed samples; production does not.
- **Auth/profile**: JWT `{sub}` only; `/auth/me` has `is_platform_admin`, `teacher_status`, `locale`, no role. Demo teacher cannot log in; disabled accounts get no reset token.
- **Catalog**: `GET /catalog/courses` (published only), `POST /courses/{id}/join` for open enrollment.
- **R2 guard**: stored-bytes tracking (warn 8,000,000,000, refuse 9,500,000,000 bytes), images 2 MiB, PDF files 10 MB (private bucket), admin usage page `/[lang]/admin/storage`, smoke check button and CLI.
- **Frontend**: catalog on `/courses`, student ORT journey (join, take, result, review); old routes deleted. Practice, mistakes, progress, planner, target score and analytics pages are gone until Phase 8.
- **Rehearsal** (Neon copy of production, local PG, `ENVIRONMENT=production`): 0001 to 0007 applied; 1 exam set (ru, 150 questions, 3 passages) became a published 5-section `ort_main` assessment in "ORT (Russian)"; 16 image refs dropped; restart idempotent.

## How to verify

```bash
cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" venv/bin/python -m pytest -q -p no:cacheprovider -W ignore
# SQLite: 2497 passed, 21 skipped. PG full suite (commands in AGENTS.md section 5): ~2552 passed.
cd frontend && npx tsc --noEmit && cd .. && python scripts/check_i18n_parity.py   # 1586 keys
```
Exit criterion: `tests/lms/test_ort_cutover_flow.py` (join, ky and ru exams, ORT parity score, review data). After deploy: `/health` shows the new commit; Render logs show `upgrade 0001 -> 0007`, grading schemes ensured, ORT seed report.

## Deferred

- Practice by topic, mistakes notebook, progress, course analytics: Phase 8 (planner and target score cancelled, D18).
- File pages referencing uploaded PDFs: Phase 6. Catalog search and enrollment forms: Phase 7.
- Join-by-code is not used for ORT.

## Owner items

1. **Kyrgyz content**: production has no Kyrgyz questions; "ORT (Kyrgyz)" is published and empty until a ky bundle is imported (owner informed).
2. After deploy, one click on **"Run R2 check"** in `/[lang]/admin/storage`.
3. Check in the Render dashboard that the start command and the R2 variables are as expected.
4. A week after a stable cutover, delete the Neon branches `rehearsal-2026-10-23-phase5` and `backup-2026-10-22-before-phase0-alembic` (agent may do it; owner approved the latter).
5. Still open from before: rotate the Brevo key; Render plan and custom R2 domain before the first large exam.
