# Phase 11: EXPLAIN review (S5)

Local scratch PostgreSQL 18 only (8-core Mac, 8 GB, `shared_buffers=512MB`, default planner settings). Nothing ran against Neon, Render or Vercel. Rerun: `loadtest/perf_seed.py`, then `loadtest/explain_review.py run <label>` (usage in each file). Output: `loadtest/results/explain_phase11/<label>/`: `summary.json` plus the plans of statements >= 20 ms or failing.

**Data**: 6,000 students + one heavy one, 202 courses (200 seeded, 2 ORT courses from startup), 5 real `ort_main` exams of 150 items published through the API (one with 4,000 attempts), 20 real practice sets, 56,031 attempts (50,000 practice), 1,404,650 `attempt_items`, 99,768 submissions, 200,000 grade events, 21,457 enrollments, 230 test-student enrollments, 448 MB. Rows are bulk loaded in the shape of real ones, not produced by the engine.

**Method**: the real service functions run twice to warm up, then a third time with a cursor listener. Every SELECT sent is replayed three times with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` and its parameters; the median is kept. A statement fails above 200 ms, or when a Seq Scan on `attempts`, `attempt_items`, `enrollments` or `submissions` reads more than 1 % of the table.

## Result
Before: 19 of 23 cases failed the rule. After: 0 open failures of 25; 21 pass outright, 4 are reviewed exceptions (below). On the data with six times the practice attempts, one open failure remains (`analytics.practice_page`).

| Case | Before: worst statement ms | Before: verdict | After: service ms | After: worst statement ms | After: verdict | x6 practice: worst statement ms |
|---|---|---|---|---|---|---|
| `statistics.summary_fresh` | 2.38 | FAIL | 6.6 | 1.0 | ok | 1.41 (ok) |
| `statistics.item_page` | 2.09 | FAIL | 5.0 | 0.92 | ok | 1.24 (ok) |
| `statistics.refresh_compute_4000` | 1087.1 | FAIL | 2368.1 | 1079.15 | accepted | 1478.4 (accepted) |
| `statistics.refresh_compute_500` | 100.18 | FAIL | 316.9 | 124.89 | ok | 158.6 (ok) |
| `analytics.overview_6000` | 18.4 | FAIL | 48.2 | 26.54 | ok | 32.73 (ok) |
| `analytics.overview_small` | 3.69 | FAIL | 8.1 | 0.91 | ok | 1.0 (ok) |
| `analytics.modules_page` | 11.27 | FAIL | 12.5 | 11.77 | ok | 14.6 (ok) |
| `analytics.assignments_page` | 7.26 | FAIL | 9.3 | 6.12 | ok | 7.76 (ok) |
| `analytics.quizzes_page` | 5.59 | FAIL | 7.8 | 5.58 | ok | 7.02 (ok) |
| `analytics.practice_page` | 57.72 | FAIL | 57.3 | 61.08 | accepted | 465.09 (FAIL) |
| `org.overview` | 113.56 | FAIL | 182.4 | 140.31 | accepted | 186.19 (accepted) |
| `org.courses_page` | 23.08 | FAIL | 62.2 | 21.13 | ok | 35.9 (ok) |
| `org.courses_page_department` | 14.39 | FAIL | 42.9 | 14.69 | ok | 21.24 (ok) |
| `org.quizzes_page` | 6.55 | FAIL | 7.3 | 5.12 | ok | 6.63 (ok) |
| `progress.mistakes_open_heavy` | 12.41 | FAIL | 11.8 | 5.26 | ok | 7.62 (ok) |
| `progress.mistakes_fixed_heavy` | 11.26 | FAIL | 10.7 | 5.49 | ok | 7.7 (ok) |
| `progress.mistakes_page2_heavy` | 16.73 | FAIL | 21.3 | 6.43 | ok | 7.78 (ok) |
| `progress.mistakes_open_typical` | 0.56 | ok | 7.3 | 0.49 | ok | 1.29 (ok) |
| `progress.progress_heavy` | 7.72 | FAIL | 12.0 | 2.96 | ok | 5.13 (ok) |
| `progress.progress_typical` | 0.34 | ok | 5.9 | 0.29 | ok | 0.62 (ok) |
| `progress.mistakes_open_busiest` | - | - | 11.9 | 5.57 | ok | 42.48 (ok) |
| `progress.progress_busiest` | - | - | 11.6 | 2.96 | ok | 23.26 (ok) |
| `home.home_heavy` | 3.39 | ok | 22.2 | 0.52 | ok | 0.62 (ok) |
| `home.home_typical` | 0.31 | ok | 22.0 | 0.29 | ok | 0.4 (ok) |
| `retention.dry_run` | 32.0 | FAIL | 27.1 | 42.27 | accepted | 204.28 (accepted) |

Timings are from a machine shared with other work (load about 4 for "after", up to 15 in other runs, where the same statements took up to 8 s); treat them as ratios. The plan shapes do not depend on load. Busiest student: about 320 attempts in the seed, 1,896 in the x6 data.

## What changed
1. **`ix_enrollments_test_student`** on `enrollments (id) WHERE is_test_student IS TRUE` (migration `0018`). `not_test_enrollment` is in every staff aggregate over attempts and planned as an anti join over a full scan of `enrollments`. The predicate has to be written `IS TRUE`: a first try with `WHERE is_test_student` was ignored, because PostgreSQL does not prove `x IS TRUE` implies `x`.
2. **`ix_grade_events_attempt_id`** (`0018`). Deleting a practice attempt runs the RESTRICT foreign key check, which scanned `grade_events` once per deleted row. Three batches of 500: 22.1 s without the index, 3.8 s with it, both at load 9; 0.35 s with it at load 5.
3. **Course named on the enrollments side** of the analytics joins (`analytics/service.py`, `org_service.py`). `real_student(_E)` alone made the planner build a hash over 98 % of `enrollments` even for a small course.
4. **Notebook and progress** (`progress/service.py`). Two changes, both needed:
   - The student's final attempts come first through a materialized CTE; otherwise the planner chose a parallel Seq Scan of `attempts` for one student.
   - `SET LOCAL random_page_cost = 1.1` for that transaction. With the default of 4 a student near 300 attempts tips the plan into a Seq Scan of all of `attempt_items`: 209 to 461 ms instead of about 6 ms. Whether it tips varied between two seeds with the same code, so without the setting the plan is not stable. It costs one extra round trip per notebook or progress read.
5. **`by_topic` ties** now also sort by section. Before, two rows tied on accuracy, total and topic came back in whatever order the plan produced.

**Same output**: `explain_review.py compare` on the answers of the old code (`phase-11`) and the new code, same database: 22 of 23 identical; `progress_typical` differed only in the order of two tied rows (item 5) and is identical once sorted. The existing analytics and progress test files pass unchanged.

## Reviewed exceptions
Marked `accepted` in the tool, by case and failure text, so a new failure elsewhere stays a FAIL.

| Case | Why | Limit |
|---|---|---|
| `statistics.refresh_compute_*` over 200 ms | Reads every item of every first attempt (600,000 rows at 4,000 attempts), three statements. Single flight, cached, 20 s statement timeout. | Runs inside the teacher's request. See "Risks". |
| `analytics.practice_page`, Seq Scan `attempts` | Rollup of every practice attempt in a course that holds 89 % of the table: the rows are the answer. | **Grows with attempts**: 61 ms at 56k attempts, 465 ms at 306k (open failure there). |
| `org.overview`, Seq Scans and time | This organization holds 98 % of `enrollments` and `submissions`. | Linear in the organization's size. |
| `retention.dry_run` | Admin only, reads the practice rows. | 204 ms at 306k attempts. |

## Risks these numbers do not remove
- **Statistics timeout.** The first refresh on the x6 database, cold, at load 16, hit the 20 s statement timeout once: logged, claim released, state `computing`, and the next call succeeded. Neon at 0.25 to 2 CU with a cold cache is slower than this Mac; the timeout may fire there more often. The failure mode is safe (no bad data, the teacher sees "computing"), but a very large exam might not get statistics until the cache warms.
- **`random_page_cost` for the whole database.** With 1.1 on replay (`after_rpc11`), the accepted Seq Scans of `analytics.practice_page` and `org.overview` disappear too; only `retention.dry_run` keeps one. The production value was not read (no production access in this slice). Setting it on the Neon database is free and could replace item 4's `SET LOCAL`, but it changes every plan, so it needs a production check by whoever does the Neon work.
- **Practice growth.** `analytics.practice_page` is the first read to break 200 ms as practice grows. Retention (below) or a rollup table are the levers. Neither is applied.

## Practice retention
`practice/retention.py`, `POST /api/v1/admin/storage/practice-retention/sweep` (platform admin). **Off** (`PRACTICE_RETENTION_DAYS=0`): apply gives 409 `retention_off`; a dry run answers with the suggested 365 days. On the seed, 365 days selects 5,948 attempts, 59,480 items, about 16 MB. No production run has happened; the window and first apply need the owner's OK.

Deviations from the design, all narrower or additive: previews, test students, an attempt with a grade row and open attempts are never selected; one call deletes at most 20 batches (the dry run shows what is left); the answer adds `days`; a dry run accepts `days` and an apply refuses it (422).

A mistake recorded only in a deleted attempt leaves the notebook, and a mistake already fixed stops appearing under "fixed" when its wrong attempt is deleted. Tested.

## Migration
`0018_phase11_indexes` chains after `0017_phase11_privacy` and is the new head. **Plain `CREATE INDEX`, not `CONCURRENTLY` as the design said**: `app/db/migrate.py` runs every migration at startup in one transaction holding the advisory lock, where `CONCURRENTLY` cannot run (the first version failed in `tests/test_migrations.py` for this reason). The build blocks writes to `enrollments` and `grade_events` only: 8 ms and 61 ms on the seed at load 5, 0.5 s and 1.9 s at load 13.
