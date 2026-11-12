# Database storage review (fix round 2026-11-12, step 2)

Architect: Fable, 2026-11-12. Read-only on production (Neon project `noisy-sound-20763725`, branch `production`
`br-cool-firefly-b227gbuy`, Postgres 18.6): `pg_class`, `pg_stat_user_tables`, `pg_stat_user_indexes`, `pg_indexes`,
`information_schema`, `pg_column_size` averages, `SELECT count(*)` with retention predicates; Neon `describe_project`
and `list_branches`; Neon's plan pages read on 2026-11-12 (`neon.com/faqs/free-plan-limits-and-quotas`, last updated
2026-11-03; `neon.com/docs/introduction/usage-metrics`; changelog 2026-10-02 "1 GB per project"). Nothing was written
to production and no branch was created or deleted. Code references are to `main` `348b910` (= `lms` `07c1f7e`).

## 1. The limit, exactly

| fact | value | source |
|---|---|---|
| Free plan Postgres storage | **1 GB per project** (20 GB across all projects) | FAQ, changelog 2026-10-02 (was 0.5 GB) |
| What the API enforces | `branch_logical_size_limit_bytes` = **1,073,741,824** (1 GiB) per branch | `describe_project` |
| What happens above it | "inserts, updates, and deletes that would increase storage fail"; reads keep working; nothing is deleted | FAQ "What happens when you hit a limit" |
| History (instant restore) | 6 hours, "capped at 1 GB of change history"; a separate cap, not part of the 1 GB of storage | FAQ table, `history_retention_seconds` 21600 |
| Child branches | billed on the minimum of the delta since creation and the logical size; an unchanged branch "initially consumes no storage" | usage-metrics page |
| Branches | **7 of 10** used: `production`, `triage-2026-11-12`, and five backups `backup-2026-11-12-before-notice-0032`, `backup-2026-11-09-before-identities-infra-0031`, `backup-2026-11-08-before-exam-link-0027`, `backup-2026-11-07-before-covers-0026`, `backup-2026-11-07-before-pro-0025` | `list_branches` |
| Compute this month | 32,064 s = 8.9 CU-hours of 100 in 12 days (≈ 22/month) | `describe_project` |
| Network transfer | 82 MB of 5 GB/month | `describe_project` |

**Where production stands: Neon `logical_size` of `production` = 41,590,784 B = 39.7 MiB = 3.9 % of the limit.** The
five backup branches report the same ≈ 41.2–41.6 MB each because `logical_size` is the branch's full data size, not
what it adds; with zero writes since creation (`written_data_bytes` 0, `compute_time_seconds` 0) they add ≈ nothing to
project storage. `triage-2026-11-12` has writes (migration 0032, a TOTP enrolment, logins) and adds that small delta.
Branch slots are the real constraint: one backup per DB-touching merge, ten slots; keep the newest two backups and
delete older ones after the owner's OK (rule in `PRODUCT_DECISIONS.md` 10-N: a row-ID comparison first).

## 2. Table sizes now

`pg_database_size('neondb')` = 17,571,840 B (16.8 MiB). All databases on the branch: `neondb` 17.6 MB + `postgres`
8.1 MB + `template0` 7.7 MB + `template1` 7.7 MB = **41,041,920 B**, which is within 1.3 % of Neon's `logical_size`
(41,590,784 B): the logical size is the sum of every database on the branch, and the three system databases are a fixed
≈ 23.5 MB that never grows. Our schema: 77 tables, 230 indexes; `public` tables 6,791,168 B in total, of which indexes
3,948,544 B. Schema `neon_auth` (Neon's Better Auth tables `user`, `session`, `account`, `verification`, `member`,
`invitation`, `jwks`, `project_config`): 442,368 B, all empty; the app does not use Neon Auth.

Top 20 tables (bytes; `live`/`dead` from `pg_stat_user_tables`, so estimates):

| table | live | dead | total | heap | indexes | toast | growth driver |
|---|---|---|---|---|---|---|---|
| bank_questions | 455 | 0 | 712,704 | 450,560 | 221,184 | 8,192 | content: `search_text`, `source_meta`; 6 indexes |
| question_versions | 455 | 0 | 647,168 | 532,480 | 81,920 | 8,192 | content: 1,109 B avg row (stem, data, explanation, image) |
| attempt_items | 1,510 | 318 | 360,448 | 196,608 | 122,880 | 8,192 | **exams: one row per question per attempt, 86 B avg row, 239 B/row all-in** |
| assessment_items | 615 | 0 | 294,912 | 90,112 | 172,032 | 8,192 | content |
| legacy_ort_export | 1 | 3 | 245,760 | 8,192 | 16,384 | 221,184 | Phase 5 import source, consumed; 171 kB payload |
| attempts | 15 | 34 | 212,992 | 16,384 | 163,840 | 8,192 | **exams: 758 B avg row (`result` 529 B) + 10 indexes** |
| assessment_versions | 9 | 0 | 172,032 | 8,192 | 49,152 | 114,688 | one 8 kB snapshot per publish |
| courses | 13 | 16 | 163,840 | 8,192 | 147,456 | 8,192 | 9 indexes on 13 rows |
| exam_templates | 3 | 16 | 155,648 | 57,344 | 65,536 | 8,192 | |
| question_banks | 8 | 4 | 147,456 | 8,192 | 131,072 | 8,192 | |
| passage_versions | 9 | 0 | 131,072 | 8,192 | 32,768 | 90,112 | content |
| submissions | 8 | 9 | 131,072 | 8,192 | 114,688 | 8,192 | grades (one per attempt) |
| admin_audit_log | 59 | 0 | 122,880 | 24,576 | 65,536 | 8,192 | security record: 234 B avg row + 4 indexes ≈ 400 B/row |
| rate_limit_buckets | 8 | 75 | 122,880 | 32,768 | 57,344 | 0 | self-cleaning (`ratelimit._cleanup`) |
| assets | 31 | 0 | 114,688 | 16,384 | 65,536 | 8,192 | metadata only; bytes live in R2 (17.3 MB live) |
| enrollments | 42 | 10 | 106,496 | 8,192 | 98,304 | 0 | 133 B avg row + 7 indexes |
| organizations | 4 | 1 | 98,304 | 8,192 | 81,920 | 8,192 | |
| users | 22 | 21 | 98,304 | 8,192 | 81,920 | 8,192 | 221 B avg row |
| module_items | 24 | 30 | 98,304 | 8,192 | 81,920 | 8,192 | |
| enrollment_events | 54 | 0 | 98,304 | 16,384 | 49,152 | 8,192 | append-only: 152 B avg row |

Everything else is under 82 kB. At this size every table is dominated by the 8 kB page minimum per index (a table with
9 indexes costs ≥ 80 kB empty), which is why the per-row figures below come from `pg_column_size` averages and from
`attempt_items`, the only table past 1,000 rows.

## 3. Growth model

Per-row costs measured on production (row + its share of indexes and page slack):

| row | bytes | basis |
|---|---|---|
| attempt item | **≈ 240** | 360,448 / 1,510 (includes 318 dead tuples and the PK index); `pg_column_size` 86 B |
| attempt | ≈ 1,200 (fallback 1,500 in `capacity.py`) | 758 B row (`result` jsonb 529 B) + 10 indexes × ≈ 40 B |
| attempt section | ≈ 150 (fallback 400) | 72 B row + PK |
| grade rows per graded attempt | ≈ 500 | `submissions` + `attempt_grades` + `course_grades` |
| audit entry | ≈ 400 | 234 B + 3 indexes |
| enrollment + 2 events | ≈ 600 | 133 B + 7 indexes; 152 B per event |
| user | ≈ 500 | 221 B + 5 indexes; plus `consent_records` ≈ 150 each |
| question version | ≈ 1,300 | 1,109 B + index |

**One full ORT exam for 6,000 students** (150 items, 5 sections): 6,000 × (1,200 + 5 × 150 + 150 × 240 + 500) ≈
**6,000 × 38.5 kB ≈ 231 MB** (`capacity.py` says 226 MB with its fallbacks: same answer). Headroom today = 1,073.7 −
41.6 = 1,032 MB; with the panel's 10 % reserve that is **4 full exams**, then the project is full. One practice set
(30 items) per student ≈ 8.5 kB; 6,000 students doing one practice set a day ≈ 51 MB/day. Users: 6,000 sign-ups with
one enrollment ≈ 7 MB. Audit: at today's rate (59 rows in 6 weeks) irrelevant; at 1,000 admin actions a day ≈ 0.4
MB/day. Content: the whole ORT bank (455 questions) is 1.4 MB; a second language or a second exam adds the same.

So: **the only thing that can fill 1 GB is attempts (exam and practice), at about 230 MB per full exam day.** Nothing
else gets near 1 GB before launch, and cleanup of "waste" (next section) buys kilobytes, not megabytes. The Free plan
fits four exam days and must be upgraded (Neon Launch, storage $0.35/GB-month) before the fifth; that is an owner
decision for the exam calendar, recorded here, not a cleanup problem.

## 4. Waste found (real counts on production, 2026-11-12)

| what | count / size | needed? | proposal |
|---|---|---|---|
| `rate_limit_buckets` expired rows | **0** expired of 8 live (75 dead tuples: autovacuum's job) | no | nothing: `app/lms/core/ratelimit.py:217` `_cleanup` deletes expired rows on every hit |
| `users.reset_token` expired | 1 | no | null the column when expired (hygiene; the token is useless but should not linger) |
| `users.email_code_hash` expired | 2 | no | null the column when expired |
| unverified accounts | 2 (1 older than 7 days) | not after a grace period | delete rows older than **90 days** that have only a `users` row and their sign-up `consent_records` (no enrollment, attempt, submission, guardian link, teacher request, data request, audit target, identity); otherwise leave for the anonymization path. Owner question Q-S1 below |
| test-student leftovers (Student view) | 9 users, 9 enrollments (all `is_test_student`), 1 attempt | no (synthetic) | see §6 "with the owner's explicit OK": the design (`PHASE_11_DESIGN` 5.6) already sweeps their files (`POST /admin/storage/test-student-files/sweep`, dry run default) |
| preview attempts (staff "try the test") | 4 of 15 attempts | no grades (`attempts/hooks.py:17`) | delete after **90 days** with items and sections; owner OK (§6) |
| practice attempts | 3 of 15 | kept by decision 10-Q5 | `PRACTICE_RETENTION_DAYS` stays 0; the dry-run endpoint exists (`practice/retention_router.py`); turn on 365 days when practice passes 100 MB |
| soft-deleted courses / assessments | 2 / 3 | trash | no hard purge exists; propose 180 days after `deleted_at` for courses with no graded attempt of a real student (later, small) |
| `guardian_pairing_codes` expired, unconsumed | 4 (hashes only) | no | delete after **7 days** past `expires_at` |
| `email_change_requests` expired | 0 | no | delete after 7 days past `expires_at` |
| `enrollment_applications` due for purge | 0 | — | `enrollment_forms/purge.py` already runs opportunistically and from `/internal/purge-applications` |
| old question versions not current, not in any attempt, not in any snapshot | **0** of 455 (454 are in attempts and in snapshots) | — | no job now; rule for later: delete versions older than 180 days with no reference (`bank_questions.current_version_id` / `imported_version_id`, `attempt_items.question_version_id`, `assessment_versions.snapshot`) |
| `question_drafts` | 0 (deleted on commit) | — | nothing |
| orphan uploads | `assets.deleted_at` 0, `erased_at` 0; `asset_blobs` 0 rows (R2 driver) | — | `files/service.py:213` `sweep_orphan_blobs` runs hourly on db/local; on R2 nothing is ever deleted by design (content addressing); 31 live assets = 17.3 MB in R2 |
| `legacy_ort_export` consumed row | 1 row, 245 kB (the biggest single row in the database) | no: Phase 5 import source, converted (`consumed_at` set) | drop the row after the owner's OK (the ORT courses are seeded from `ort/seed.py`, the row is history only). 0.6 % of the database: optional |
| `neon_auth` schema | 8 empty tables, 442 kB | no | the owner can disable Neon Auth in the console; optional |
| dead tuples | `users` 21/22, `attempts` 34/15, `alembic_version` 29, `storage_usage` 31 | — | autovacuum thresholds (50 rows + 20 %) are not met on tiny tables; harmless; `VACUUM` is not needed |
| indexes | 230, 3.9 MB; 74 with < 50 scans | yes | keep all (PERFORMANCE_AUDIT §10.3); no bloat at this size |
| `infra_snapshots`, `storage_monthly_usage`, `storage_usage` | 5, 2, 1 rows | yes | bounded by design |

Total reclaimable today: well under 1 MB. The review's value is the rules and the warning, not the bytes.

## 5. How jobs run today, and the proposed cleanup job

**Today there is no scheduler**, and four mechanisms stand in for one:

1. Opportunistic, in-process, after a response (`BackgroundTasks`): the attempt sweep every 60 s from attempt routes
   (`attempts/sweep.py`, advisory lock `3_000_001`, own 2-connection engine), the application-answer purge and the
   teacher-phone purge once per hour per process (`enrollment_forms/purge.py`, `teachers/purge.py`,
   `PURGE_OPPORTUNISTIC_INTERVAL_S = 3600`), the orphan-blob sweep once per hour (`files/service.py:235`), the
   activation-code note purge with the teacher purge (`access/purge.py`).
2. Token routes for an external cron: `POST /internal/attempts/sweep` and `POST /internal/purge-applications`
   (`attempts/internal_router.py`; `X-Sweep-Token` = `ATTEMPT_SWEEP_TOKEN`, 404 otherwise). **Nothing calls them
   today**; the GitHub uptime workflow deliberately uses no secrets.
3. Admin-triggered, audited, dry run by default: test-student file sweep (`student_view/sweep_router.py`), practice
   retention (`practice/retention_router.py`).
4. Autovacuum.

Render Free has no cron and the process sleeps, so in-process timers never run while nobody is using the site, which
is exactly when cleanup should run. **Proposal: one maintenance route plus one scheduled GitHub workflow.**

- `POST /internal/maintenance?dry_run=1|0` (`app/lms/maintenance/`: `router.py`, `tasks.py`, `service.py`; policy
  `internal` like the sweep; same `X-Sweep-Token`/404 rule, so the owner sets one secret in two places: Render env
  `ATTEMPT_SWEEP_TOKEN` and the repository secret `SWEEP_TOKEN`). It runs, in order and each bounded to 500 rows and its
  own transaction with `FOR UPDATE SKIP LOCKED` on PostgreSQL (the pattern of `enrollment_forms/purge.py`):
  1. `run_sweep()` (expired attempts), `run_purge()` (applications), the phone and note purges: the existing functions;
  2. `expire_user_tokens`: `UPDATE users SET reset_token = NULL, reset_token_expires = NULL WHERE reset_token_expires < now`
     and the same for `email_code_*`;
  3. `delete_expired_codes`: `guardian_pairing_codes` (expired or revoked, unconsumed, > 7 days),
     `email_change_requests` (expired > 7 days), `rate_limit_buckets` (expired; a backstop for `_cleanup`);
  4. `delete_unverified_accounts` (90 days, the guard list of §4; off until the owner answers Q-S1: `MAINTENANCE_UNVERIFIED_DAYS = 0`);
  5. `delete_preview_attempts` (90 days; off until Q-S2: `MAINTENANCE_PREVIEW_DAYS = 0`);
  6. `sweep_test_students` (removed test-student enrollments older than 30 days, with their attempts, items, sections,
     submissions, progress rows, files via the existing `sweep_retired_files(apply=True)`, then the enrollment and the
     `is_test_student` user; off until Q-S3: `MAINTENANCE_TEST_STUDENT_DAYS = 0`);
  7. `measure_storage`: the §7 SQL, stored for the Services panel and the overview.
  Returns `{task: {examined, changed}}`. Writes one line per task to the JSON log (counts only) and stores
  `{"ran_at", "dry_run", "counts"}` under `platform_settings` key `maintenance.last_run` (an audit row needs an actor,
  `admin_audit_log.actor_id` is NOT NULL, so the token run cannot write one; an admin-triggered run via the Services
  page button `POST /platform/maintenance/run` is audited as `maintenance.run` with the admin as actor and the counts).
- `.github/workflows/maintenance.yml`: `schedule: "30 4 * * *"` (after Neon's Saturday 03:00–04:00 maintenance window),
  `workflow_dispatch`, `curl -fsS --max-time 120 -X POST -H "X-Sweep-Token: ${{ secrets.SWEEP_TOKEN }}" …/internal/maintenance?dry_run=0`
  with two tries (the first call may wake Render), failure opens the same "Uptime"-style issue. Secrets on a public
  repository are not exposed to fork pull requests or to scheduled runs of forks; the token only unlocks bounded
  cleanup, never reads.
- Fallback when GitHub skips: `maybe_run_maintenance()` from the admin overview request, at most once per 12 hours per
  process, dry-run-safe tasks 1–3 and 7 only.
- Safety rules: every delete has a hard upper bound per run; nothing in §6 is ever selected (asserted by tests that
  seed one row of each protected kind and run every task with `apply=True`); `dry_run=1` is the default for the manual
  button; the first production run is a dry run whose counts the owner sees on the Services page before the schedule
  is switched to `dry_run=0`.
- Tests: `tests/lms/test_maintenance.py` (each task: due rows go, not-due rows stay, bound respected, idempotent twice;
  protected kinds untouched; token 404; `platform_settings` row written; SQLite + the PG concurrency file for
  `SKIP LOCKED`); route inventory; isolation (`internal` routes 404 for every role).

## 6. Never deleted (and why), with the privacy rules that bind

| data | why it stays | rule |
|---|---|---|
| `attempts`, `attempt_items`, `attempt_sections` of real students (exam and practice) | the student's result and the proof behind the scaled score and certificate; anonymization keeps them under the tombstone (`privacy/registry.py:85-87` `keep_immutable`) | owner brief 2026-11-12; `PRODUCT_DECISIONS` 10-Q5 (practice kept); `PERSONAL_DATA.md` |
| `submissions`, `attempt_grades`, `course_grades`, `grade_events` | grades are append-only; `grade_events` is the audit of every grade change (`keep_immutable`) | AGENTS.md §4 |
| `admin_audit_log` | the security record; the actor is tombstoned, never removed (`keep_tombstone`); FK `RESTRICT` to users. **Retention proposal: 3 years**, then export month-files as JSONL to the private R2 bucket and delete rows older than 36 months, as a later maintenance task behind an owner switch (`AUDIT_RETENTION_MONTHS = 0` = keep forever). Size today ≈ 400 B/row, so a year of heavy admin use is < 10 MB: no pressure | owner brief ("keep, it's the security record") |
| `consent_records` | append-only legal record (versions accepted, by whom, when) | Phase 11 design §9; `registry.py:119` |
| `data_requests` | the privacy request log (due dates, decisions) | Phase 11 |
| `enrollment_events` | the enrolment history behind every "who had access when" question; 152 B/row | Phase 9 |
| `assessment_versions` (snapshots) | attempts reference the version they ran against; the result view renders from it | AGENTS.md §4 |
| `question_versions` referenced by an attempt or a snapshot | same reason; `attempt_items.question_version_id` | AGENTS.md §4 |
| tombstoned users (`deleted_at`) and their `guardian_links` scrubbed rows | the tombstone is what the kept rows point to | `anonymize.py` |
| `enrollment_applications` rows (answers nulled) | counts and history; answers are purged, rows stay | P9-7 |
| `teacher_requests` | the approval record (phone purged separately) | ACCOUNTS.md C |
| `infra_snapshots`, `storage_*` | the panel's history | — |

Test-student attempts (§5 task 6) and staff preview attempts (task 5) are the only attempt rows a job may delete,
both are synthetic (no real student, no grade), and both ship switched off until the owner says yes.

## 7. Services panel: what it measures today and the change

**Today** (`app/lms/infra/capacity.py`, `cards.py`, `providers/neon.py`; `frontend/.../infra/CapacityCard.tsx`):

- The Neon card is **not connected** in production (`NEON_API_KEY` unset; `infra_snapshots.neon = not_connected`), so
  there is no storage bar, no 80 %/95 % level and no branch count on the page at all.
- The capacity card falls back to `pg_database_size(current_database()) × 1.3` = **22.8 MB**, while Neon's logical size
  is **41.6 MB**: the fallback is 45 % low because the logical size counts every database on the branch and the three
  system databases are a fixed 23.5 MB. The "exams that fit" number is right anyway (the 19 MB error is 2 % of the
  headroom), but the "занято X из 1 ГБ" line is wrong by half.
- Levels are `ok < 80 %`, `warning ≥ 80 %`, `critical ≥ 95 %` for every metric (`schemas.py:1-2`). For the database
  those are too late: 80 % of 1 GiB leaves 215 MB, **less than one full exam day** (231 MB). The first warning would
  arrive when the next exam already does not fit.
- The exams-that-fit formula (`capacity.py`) is sound: 150 items, 5 sections, per-row sizes measured when a table has
  ≥ 1,000 rows (`attempt_items` qualifies: 239 B measured vs 241 fallback), the 10 % reserve covers grades and the other
  tables. Keep it; lower `FALLBACK_ATTEMPT_B` to 1,200 and `FALLBACK_SECTION_B` to 150 to match §3 (optional, it only
  moves the fourth exam's margin).

**Change (slice D1, Opus, one day; frontend strings Sonnet):**

1. **Measure without a key.** `capacity._local_used_bytes` on PostgreSQL becomes
   `SELECT sum(pg_database_size(datname)) FROM pg_database` (41.04 MB on production, 1.3 % under Neon's 41.59 MB) and
   `LOCAL_SIZE_FACTOR` goes from 1.3 to **1.02**. `pg_database_size(name)` on the other databases needs `CONNECT` on
   them (the Neon owner role has it; the MCP query ran as that role); if the app role is refused on a database, fall
   back to `pg_database_size(current_database()) + 23,500,000` (the fixed size of `postgres` + the two templates,
   measured) and mark the source `database_estimate`. The Neon figure still wins when the key is set (`used_source = neon`). The same statement feeds
   `measure_storage` (§5) and the overview.
2. **Database-specific levels**, computed server-side in `cards.py` for the metric `storage` of the `neon` card and for
   the capacity block: `ok < 50 %`, `notice ≥ 50 %` ("plan the upgrade before the next exam"), **`warning ≥ 70 %`**,
   **`critical ≥ 85 %`**; and independent of the percent, `fits < 1` → at least `warning`, `fits == 0` → `critical`.
   `Level` gains `notice` (amber-light; the R2 and compute metrics keep 80/95). Thresholds are constants in
   `capacity.py` (`DB_NOTICE = 0.5, DB_WARNING = 0.7, DB_CRITICAL = 0.85`) with a test for each boundary and for the
   `fits` override.
3. **The sentence that explains the limit**, always visible on the capacity card, three languages:
   `infra.capacity.writesStop` = "При 1 ГБ Neon останавливает запись (INSERT, UPDATE, DELETE); чтение продолжает
   работать. Лимит плана Free." / ky / en, and under `warning`/`critical` a second line `infra.capacity.upgradeHint` =
   "Перед следующим экзаменом нужен план Launch (хранилище 0,35 $/ГБ в месяц)". No price in code beyond `costs.py`'s
   rows (it already carries Launch).
4. **The overview's "Требует внимания"** gets one line when the database level is `warning` or worse or `fits < 1`:
   "База данных: занято 72 % (ещё помещается 1 экзамен)" linking to Services; read from the stored `measure_storage`
   value (`platform_settings`), refreshed by the overview itself if older than 60 minutes (one statement, cached in
   `overview.py`'s 60 s cache). No provider call.
5. **Capacity block shows the inputs**: used (source), limit, per-exam bytes, exams that fit, branches `6 из 10`
   (when the key is set), "last measured" time. The e2e `admin-services.spec.ts` gets the cases 55 % (notice), 72 %
   (warning with the writes-stop text), 90 % (critical), and `fits = 0` at 40 %.
6. Owner action once: create the project-scoped Neon key (`INFRA_PANEL_DESIGN` §2) and set `NEON_API_KEY` on Render so
   the branch count and the real logical size appear; until then the SQL path above shows the right number.

Measure before/after: the Services page on production today says "Занято 22,8 МБ из 1 ГиБ" (fallback); after D1 it
must say ≈ 41 MB (within 2 % of the Neon console) and the overview must stay quiet (3.9 % < 50 %). A test seeds
`platform_settings` with 75 % and asserts the overview line and its text.

## 8. Slices and order

| order | slice | builder | what | gate |
|---|---|---|---|---|
| 1 | **D1 panel measures and warns** (§7) | Opus; strings Sonnet | SQL-based size, DB levels 50/70/85 + fits rule, writes-stop text, overview line | backend suite, `admin-services.spec.ts`, parity, UX check 375/1440/1920 ru |
| 2 | **D2 maintenance route + workflow** (§5 tasks 1–3, 7; 4–6 behind switches set to 0) | Opus | `app/lms/maintenance/`, `/internal/maintenance`, `maintenance.yml`, Services button (dry run), `platform_settings` last run | `test_maintenance.py`, PG concurrency test, route inventory, isolation; first production run as dry run, counts recorded in `FIX_ROUND_2026-11-12.md` |
| 3 | **D3 owner switches** after the answers to Q-S1…Q-S3 | Opus (small) | set the three `MAINTENANCE_*_DAYS` on Render; nothing else changes | the dry-run counts of the previous day match what gets deleted |
| later | audit export-and-trim (3 years), question-version pruning, course trash purge, practice retention on | — | only when a table passes 50 MB; each needs an owner line in `PRODUCT_DECISIONS.md` | — |

Owner questions (answers go to `PRODUCT_DECISIONS.md`):
- **Q-S1** Delete never-verified accounts after 90 days (rows with nothing but the sign-up consent)? Default proposed: yes.
- **Q-S2** Delete staff preview attempts after 90 days? Default proposed: yes (no grades, no student).
- **Q-S3** Delete retired test students (Student view) with their synthetic attempts after 30 days? Default proposed: yes.
- **Q-S4** Audit log retention 3 years with export to the private R2 bucket, or keep forever? Default proposed: keep
  forever until the table passes 50 MB, then decide.
- **Q-S5** Drop the consumed `legacy_ort_export` row (245 kB) and disable Neon Auth (442 kB)? Cosmetic; default: leave.
- **Q-S6** Keep only the two newest Neon backup branches (slots 7 of 10 used, five are backups)? Default proposed: yes, after each deploy
  is verified.

## 9. Better ideas than the brief's

1. **Watch the exam calendar, not the waste.** Four exam days fit on Free and nothing a cleanup job can delete changes
   that by more than a few hundred kilobytes. The useful control is the panel line "ещё помещается N экзаменов" on the
   overview and a rule in `LAUNCH_CHECKLIST.md`: "N < 2 → move to Neon Launch before the next exam date".
2. **Measure in SQL first, provider second.** The panel was designed around provider APIs that are all unconnected in
   production a week after deploy; the one number that matters (database size against 1 GiB) is available from SQL to
   within 2 %. D1 makes the panel useful without any key.
3. **One scheduler for everything.** The repository already runs a free GitHub schedule; the token routes already
   exist. One daily call replaces four opportunistic timers that only fire while someone is using the site, and it gives
   the owner a "last run" time to look at.
4. **`attempt_items` is the table to shape, if any.** 240 B per row all-in, of which the PK `(attempt_id, position)`
   is a third; `choice_order` (25 B) and `client_ts` could move into `response`, and `correctness`/`score` could be
   `smallint`/`numeric(5,2)`, for maybe −20 %. Not now: the player and the ORT scoring parity depend on this shape and
   the Free plan's ceiling moves by less than one exam.

## D2. Maintenance route and daily workflow (built 2026-11-12)

What shipped (`backend/app/lms/maintenance/`: `tasks.py`, `service.py`, `router.py`; runbook
`docs/runbooks/MAINTENANCE.md`): `POST /internal/maintenance?dry_run=1|0` (token `X-Sweep-Token` = `ATTEMPT_SWEEP_TOKEN`,
404 otherwise, dry run unless `dry_run=0`), `GET /platform/maintenance` and `POST /platform/maintenance/run` (platform
admin, dry run unless `apply`, audited `maintenance.run`, 12 per hour), the "Очистка базы" block on the Services page,
`platform_settings` key `maintenance.last_run`, `.github/workflows/maintenance.yml` (daily `30 4 * * *`, two tries,
`dry_run=0`, skips with a notice while `SWEEP_TOKEN` is unset, one issue on failure), and the overview fallback (safe
tasks 1-3, production only, once per 12 h per process, only when no applied run in 24 h; task 7 is left out there
because the overview re-measures on its own).

Owner rules (PRODUCT_DECISIONS "Owner 2026-11-12: storage retention answers"; constants in `tasks.py`), all ON:
- Q-S1: never-verified accounts after 90 days, when nothing points at them but their own sign-up consent (generic guard
  over every foreign key to `users.id`, plus no audit row naming them); the sign-up consent goes with the account.
- Q-S2: staff preview attempts at any age once not in progress; in-progress ones after 24 h (never one being taken).
- Q-S3: test-student attempts by the same rule, with their synthetic grade rows (attempt grade, grade events, the quiz
  submission that kept them, the course-total cache); retired (removed by a reset, more than 1 h ago) test students go
  with enrollments, submissions, progress rows, enrollment events, exam goals and erased file rows, after
  `sweep_retired_files(apply=True)`. The course's active test student keeps its enrollment and user.
- Audit log: kept (no task).
Each task is bounded (500 rows, 100 accounts), one transaction, `FOR UPDATE SKIP LOCKED` on PostgreSQL, idempotent.

Dry run on the production copy (Neon branch `triage-2026-11-12`, alembic `0032`, read-only sessions, nothing
committed), which predicts the first production run:

| task | due | task | due |
|---|---|---|---|
| attempt_sweep | 0 | unverified_accounts | 0 |
| application_purge | 0 | preview_attempts | 4 |
| phone_purge | 0 | test_student_attempts | 1 |
| code_note_purge | 0 | test_student_files | 0 |
| user_tokens | 3 | retired_test_students | 2 (of 9 test students; 7 are active) |
| pairing_codes | 4 | measure_storage | measured |
| email_changes | 0 | rate_limits | 83 |

Apply was verified on the same copy inside one transaction that was then rolled back: the counts above were handled,
a second pass found 0, and every protected kind of §6 was unchanged (real attempts 10, their items 1,059 and sections 38,
real submissions 6, attempt grades 7, course grades 9, audit rows 58, consent records 14, data requests 2, real
enrollment events 41, assessment versions 10, question versions 480, teacher requests 2, real users 13).
