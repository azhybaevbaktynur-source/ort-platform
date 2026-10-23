# Phase 4 — Grading schemes, submissions, gradebook

**Status**: done 2026-10-23 on branch `phase-4/grading`, merged into `lms` (not `main`; ships at the Phase 5 cutover). Design: `PHASE_4_DESIGN.md`; decisions: `PRODUCT_DECISIONS.md` ("Phase 4" sections).

## What changed

- **Schema** (Alembic `0005_phase4_grading`): `grading_schemes` + immutable `grading_scheme_versions`, `grade_categories`, `submissions`, `attempt_grades`, append-only `grade_events`, `course_grades`; grading columns on `assessments` and `courses` (incl. `late_policy_changed_at`). Backfills submissions for already-graded attempts. On PostgreSQL, triggers refuse UPDATE/DELETE of grade events and UPDATE of scheme versions.
- **Schemes** (`app/lms/grading/{registry,params,schemes,seeds}.py`): types points, percent, bands, pass/fail, piecewise curve, lookup table; per-section values, percentile, thresholds. System schemes ORT main, ORT subject, percent, pass/fail are seeded at startup; ORT schemes reproduce the old scoring exactly (every N 1–200, every raw). Teacher-owned library with versions, preview, soft delete/restore (`/api/v1/grading-schemes`).
- **Submissions and grading** (`submissions.py`, `late.py`, `actions.py`, `regrade.py`): the attempt-scored hook (inside Phase 3's finalize transaction) keeps one submission per student and assessment (highest/latest/average/first), applies the late policy, writes attempt grades; override (with reason and version check), excuse, release/unrelease (refused on auto release), chunked regrade with one shared "stale" definition, void. Every change writes a grade event. States: pending review, graded, excused, no attempts.
- **Gradebook and totals** (`gradebook.py`, `totals.py`): cursor-paged gradebook with fixed query count per page, course totals (points or weighted categories), submission detail with history, student "my grades" (only own, only released, results policy respected).
- **Settings**: assessment scheme/category/due date/release mode/omit from total; course total mode, course scheme, late policy, categories.
- **Frontend**: scheme library and editor with live preview; grading settings in course and assessment settings; staff gradebook with submission side panel (override, excuse, release, regrade, void, history); student grade badge, ORT result view and "my grades"; Grades tab; scheme library link in the LMS nav. 1630+ i18n keys (en/ky/ru).
- **Reviews**: Fable concurrency + final security review — no deadlock or lost update across grading and Phase 3 writers (attempt rows locked `FOR NO KEY UPDATE` by grade writers so foreign-key checks pass); fixed: preview 500 on huge numbers, unrelease undone by auto release, missing backfill, voided attempts still readable, staff cache rows, DB-level append-only, duplicated models.

## How to verify

```bash
cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" venv/bin/python -m pytest -q -p no:cacheprovider -W ignore
# Postgres full suite: one UTF8 DB (TEMPLATE template0), PGTZ=UTC, BOTH URLs postgresql+psycopg2://postgres@127.0.0.1:55432/<db>
```
Exit criteria: `tests/lms/test_phase4_flow.py` (end to end over HTTP), `test_ort_parity.py`, `test_pg_concurrency_grading.py`, `test_phase4_review_fixes.py`, `test_gradebook_api.py`, `test_grading_budgets.py`, `tests/test_migrations.py` (0005 up/down, triggers).

## Deferred / owner input

- Nothing needs the owner for Phase 4. Phases 1–4 stay on `lms` until the Phase 5 cutover (owner OK needed).
- Course analytics (score distribution, per-question stats) is Phase 8; grade CSV export and grade notifications are not planned yet.
