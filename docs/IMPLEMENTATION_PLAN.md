# Implementation Plan (phase by phase)

**Status**: proposal for owner review, 2026-10-21. Design: `LMS_ARCHITECTURE.md`. Decisions: `PRODUCT_DECISIONS.md`. Open decisions D1–D18 are at the end, each with a recommended default; reply only to the ones you want to change.
**Sizes** are relative effort (S ≈ days, M ≈ 1–2 weeks, L ≈ 3–4 weeks of focused work with an AI pair), not promises.

---

## 0. Strategy

1. **Strangler, not big bang.** The current ORT app (with the security fixes already committed) keeps running in production while the LMS is built *beside it* in new packages (`backend/app/lms/…`, `frontend/src/app/[lang]/courses/…`) on new tables added through Alembic. We do **not** refactor old exam code that will be deleted. Old code is removed in one planned **cutover (Phase 5)**, after an ORT parity gate passes. This avoids wasted work on the in-memory Firestore, `ExamSet` and `ExamAccess`.
2. **Integration branch.** Long-lived `lms` branch off `main`. Each phase is a short-lived branch merged into `lms` by PR after its exit criteria pass. `main` only receives fixes until Phase 5.
3. **Every phase ships a vertical slice**: migration + models + service + endpoints + teacher/student UI + i18n (en/ru/ky) + tests. No phase ends with "backend only, UI later".
4. **Gates that apply to every phase** (definition of done):
   - `pytest` green on SQLite *and* Postgres 16 in CI; `alembic upgrade head` + `alembic check` clean; frontend `tsc --noEmit` and `next build` clean (isolated copy, per `AGENTS.md`).
   - Every new route is in the permission matrix (route-inventory test), with table-driven action × role × status tests and cross-tenant tests (teacher A cannot see or edit teacher B's anything).
   - i18n key parity across `en.json`, `ky.json`, `ru.json` (CI check). No hard-coded user-facing strings.
   - No answer keys, PINs, join codes or other users' data in any student-facing payload (contract tests on serializers).
   - Soft delete only; attempts and submissions never cascade.
   - A short `docs/phases/PHASE_N.md` note: what changed, how to verify, what was deferred.
   - Code review pass (`/code-review`) before merge; security review (`/security-review`) at phases 1, 3, 7, 9.
5. **Models for the work** (cost control): design-heavy phases (1, 3, 4, 6) and reviews run on **Opus**; CRUD/UI-heavy work on **Sonnet**. Subagents are used for independent, parallelizable slices (e.g., UI page vs. API) and always get this plan and the architecture doc as context. Nothing is run against production without your say-so.

## Non-functional targets (added 2026-10-22)

**Scale target: about 6,000 students active at the same time** (for example, a national mock exam where everyone starts within a few minutes). This is a design constraint for every phase, not a Phase 9 afterthought.
- Peak scenarios to design and load-test for: (a) a start burst, 6,000 attempts created within ~5 minutes, each writing ~150 `attempt_items` rows; (b) steady autosave, one write per answer per student, roughly 300 writes/s at the peak; (c) a submit burst when the timer ends, with scoring done within seconds; (d) 6,000 students loading the same quiz payload.
- Initial budgets to confirm in the capacity review (`CAPACITY_REVIEW_BRIEF.md`): API error rate < 0.5 %, p95 < 500 ms for autosave and < 2 s for attempt start, no lost answers, no double submits, zero data loss on deploy during an exam.
- The current hosting (Vercel + Render + Neon) has **not** been checked against this target. The capacity review runs first (Phase 0, task 0.0) and may change infrastructure choices before schema work starts.

## Phase overview

| # | Phase | Size | Depends on | Result you can see |
|---|---|---|---|---|
| 0 | Foundations | M | – | CI, Alembic, hardened uploads, authz scaffolding |
| 1 | Courses, enrollment, authorization | L | 0 | Teachers create courses; students join by code |
| 2 | Files and content library | L | 1 | Persistent images; teachers build banks/questions; imports work |
| 3 | Assessments and attempts | L | 2 | Teacher builds and publishes a quiz; students take it safely |
| 4 | Grading and results | L | 3 | Flexible grading schemes; ORT scoring as data; gradebook; real review |
| 5 | **ORT cutover** | M | 4 | ORT is just a course; old code and Firestore mock removed |
| 6 | Pages, modules, gating | L | 5 | Guided course paths with locked/unlocked steps |
| 7 | Enrollment forms, catalog, invites | M | 5 | Browse, apply (teacher-made form), approve |
| 8 | Practice, analytics, student tools | M | 5 | Practice by topic, mistakes notebook, course analytics |
| 9 | Privacy, hardening, launch | M | 6–8 | Consent, data requests, load/security checks, runbooks |

Phases 6, 7, 8 are independent of each other after the cutover and may run in any order or in parallel.

---

## Phase 0 — Foundations (M)

**Goal**: the safety net and shared building blocks every later phase relies on. No user-visible features.

**Work**
- **0.0 Capacity review (first task, before any schema work)**: follow `docs/CAPACITY_REVIEW_BRIEF.md`; deliver `docs/CAPACITY_REVIEW.md` with measured numbers and a go/no-go on Vercel + Render + Neon, plus the cheapest upgrade path. Its findings can change D4 and the attempt-engine design (e.g. write batching, connection pooling).
- **Alembic baseline of the *current* schema** (autogenerate against an empty Postgres, review by hand, `stamp` Neon). Naming convention for constraints; batch mode for SQLite dev. From now on schema changes are Alembic revisions only; the runtime `ALTER` helpers stay until cutover, then are deleted. Migrations run as a pre-deploy step (D4).
- **CI** (GitHub Actions): backend tests on SQLite and Postgres 16, `alembic upgrade head`, `alembic check`, pytest-alembic built-ins, frontend `tsc` + build, i18n key-parity check, lint.
- **Shared building blocks** in `app/lms/core/`: UUID PK + timestamps + soft-delete mixin; `LocalizedText` JSON type with Pydantic validation and read fallback; `JSON().with_variant(JSONB, "postgresql")` helper; error shape; cursor pagination helper; structured logging without PII.
- **`app/core/authz.py` scaffolding**: `can()/require()` interfaces, `ROLE_GRANTS`, the route-inventory test (initially whitelisting all existing routes so the gate is live from day one).
- **Hardening carried over from the review**: upload content check (magic bytes via Pillow) and size cap; remove `print()` of payloads; PIN stays only in old code (removed at cutover).
- **`en.json`** next to `ky.json`/`ru.json`; the language switcher gets a third option.

**Exit criteria**: CI green on both databases; a throw-away migration upgrade/downgrade test passes; route-inventory test fails when a dummy unlisted route is added.
**Risks**: Alembic baseline drift between SQLite and Postgres → baseline is generated on Postgres only; SQLite is dev/test convenience.

---

## Phase 1 — Courses, enrollment, authorization (L) · *Opus for design/review*

**Goal**: a teacher signs up, creates a course, shares a code; students join. The permission layer is real.

**Schema (Alembic)**: `users` += `is_platform_admin`, `locale`, `age_band` (nullable); `courses`, `enrollments`, `enrollment_events` (see architecture §3). Old `users.role` stays (old app) but new code ignores it.
**Backend**
- `app/lms/courses/`: create/update/publish/conclude/soft-delete/restore, transfer ownership, regenerate join code. Owner's `teacher/active` enrollment inserted in the same transaction; owner invariants.
- `app/lms/enrollments/`: join by code (single transaction, `FOR UPDATE`, limit, identical failure messages, rate limiting by user and IP), leave, teacher removes student, roster, role change (teacher ↔ assistant), events log.
- `authz.py` completed: role grants, status gates, request-scoped enrollment cache, SQL scopes (`courses_visible_to`, `my_courses`).
- Registration: every sign-up can create courses (D10). Email verification unchanged.
- Endpoints (all under `/api/v1/courses…`), each listed in the permission matrix.
**Frontend**
- Route group `/[lang]/courses`: "My courses" (teaching / learning), create-course form (title, languages ⊆ en/ru/ky, default language, enrollment mode: closed/open/code), course shell with role-aware tabs (Home, People, Settings), join-by-code page and dialog, roster management, course settings incl. conclude/delete/restore.
- Navigation no longer depends on a global admin role; the old `(admin)`/`(student)` groups stay untouched until cutover.
**Tests**: matrix tests (action × role × course status); two teachers / three students isolation suite; join concurrency (limit never exceeded with parallel joins); code-guessing rate limit; re-join revives the row and its history; owner cannot be removed; soft-deleted course returns 404 to everyone except owner restore.
**Exit criteria**: scripted flow passes end to end (teacher creates → student joins → teacher removes → student re-joins); security review done; isolation suite green.
**Risks**: authorization gaps → merge gate + review. Minors creating courses (D10).

---

## Phase 2 — Files and content library (L)

**Goal**: images persist; teachers own banks and questions with full history; existing import tools work against the new model.

**Schema**: `assets`; `question_banks`, `passages`, `passage_versions`, `questions`, `question_versions` (architecture §4).
**Backend**
- **Storage**: `R2StorageService` (boto3) behind the existing `BaseStorageService`; `assets` with sha256 dedupe per owner and soft delete; content validation, size cap, EXIF strip, WebP re-encode, no SVG; public images via CDN domain or presigned/backend URLs (D2/D3); local-disk driver kept for tests.
- **Question type registry** (`app/lms/questions/types/`): data model, response model, `student_view` allowlist, `score()` for `single_choice`, `multiple_answers`, `true_false`, `comparison`, `numeric`, `short_text`, `essay`.
- Banks/questions/passages CRUD with versioning (every edit inserts a version; `current_version_id` moves); translation groups; permissions: only course teachers/assistants (or the bank owner) edit; students never see keys.
- **Import port**: CSV (15 columns) and ort-digitizer bundle import write into banks (one bank per source), `source_ref` unique **per owner**, `position` preserved, images through `assets`; dry-run preview kept; `math_1` ⇒ comparison and the other sections ⇒ no columns, enforced by the section-rules validator (rules are attached to quiz sections in Phase 3; in this phase the importer applies the ORT preset when `exam_type` is given).
**Frontend**: teacher "Question bank" tab inside a course (list with search/filter/pagination, editor per type with KaTeX preview and image upload, passage editor, version history view, bulk import UI migrated from `bulk-upload`/`BundleImportPanel`), translation variants UI.
**Tests**: versioning (old attempt/quiz versions unaffected by edits); port `test_csv_ingestion`, `test_bundle_import` (all 12 acceptance cases + zip-slip, sha mismatch), `test_math_section_rule`, `test_question_order` against the new importer; image dedupe and persistence across a process restart; upload abuse cases (renamed executable, oversize, SVG); serializer contract test (no `data.correct*` in student views).
**Exit criteria**: tsoomo19 bundle imports into a teacher's bank with images served from R2; images survive a redeploy; parity tests green.
**Risks**: R2/domain setup (D2/D3) → plan a driver fallback (backend-served from storage) so the phase is not blocked on DNS.

---

## Phase 3 — Assessments and attempts (L) · *Opus*

**Goal**: a teacher assembles and publishes a quiz; students take it with server-enforced integrity. ORT-style multi-section timed exams work.

**Schema**: `assessments`, `assessment_sections`, `assessment_items`, `assessment_versions`, `attempts`, `attempt_sections`, `attempt_items` (architecture §5). Partial unique index for one in-progress attempt.
**Backend**
- Builder service: sections with time limits and rules, ordered items (question / passage / translation group / pick), points; **publish** resolves items to version ids and writes the immutable snapshot; section-rules validation at item add and publish (ORT presets for `math_1` etc.); edit-after-publish rule (D9).
- **Attempt engine**: start (access checks: enrolled, course published, availability window, allowed attempts counted from SQL, language choice), snapshot rows in one transaction, shuffle permutations, server `deadline_at` and per-section deadlines; autosave as single-row conditional UPDATE with grace (D8); section close; **one-shot submit** (conditional UPDATE … RETURNING, one winner grades); lazy expiry on any access plus a sweep job; preview attempts for teachers (`is_preview`).
- Scoring through the type registry; essay items set `needs_review`; manual scoring endpoint per item.
- Student payloads via `student_view` only; results policy (`never | after_submit | after_close`).
**Frontend**
- Teacher: quiz builder (sections, drag-reorder items, points, time limits, settings, publish/unpublish, preview as student).
- Student: **adapt the existing 1,778-line exam player** to the new API instead of rewriting it: split it into components (palette, timer, question card, passage, comparison card are already separate); timer driven by server `deadline_at`; section-forward-only navigation; offline-tolerant autosave queue with clear errors.
**Tests**: table-driven integrity suite — resubmit (two parallel submits: exactly one wins), answer after deadline (rejected beyond grace), answer after section close, tab race on autosave, attempt limit under concurrency, edits after publish don't change in-flight attempts, key never in any student payload, student cannot read another's attempt; question-type scoring unit tests; ported `test_mock_test_service` behaviors that still apply (resume, save/exit).
**Scale check**: a load test (k6 or Locust) with 6,000 virtual students on a staging copy meets the budgets above before merge; results saved in `docs/phases/PHASE_3.md`.
**Exit criteria**: a 150-question five-section ORT-style quiz imported in Phase 2 is built, published, taken, timed out, resumed and submitted in an automated end-to-end test; the review shows correct answers only after submit.
**Risks**: player refactor regressions → keep the old player in place until cutover and compare behavior with Playwright smoke tests; timer drift handling (client shows server time offset).

---

## Phase 4 — Grading and results (L) · *Opus*

**Goal**: flexible grading per assessment/course; ORT scoring reproduced as *data*; teachers see a gradebook; students see real reviews.

**Schema**: `grading_schemes`, `grading_scheme_versions` and per-type child tables, `submissions`, `grade_events`, optional `grade_categories` and `course_grades` (architecture §6).
**Backend**
- Scheme registry with pure `apply()` per type: `points`, `percent`, `bands`, `pass_fail`, `piecewise_curve`, `lookup_table`; thresholds (e.g. `golden_certificate`); percentile via normal CDF when mean/SD given; immutable versions; rounding rule.
- **ORT parity**: seed system schemes `ort_main` and `ort_subject` as `piecewise_curve` versions; the old `ScoringService` stays in the repo only as an oracle in tests until cutover. Raw-0 handling per D6.
- Submissions: kept-attempt policy (highest/latest/first/average, D11), teacher override, late deduction (single course-level policy, optional), recompute triggers, `grade_events` audit, `released_at`.
- Gradebook service: per-assessment and course totals (points or weighted categories) cached in `course_grades`; per-section breakdown for ORT results.
**Frontend**: grading-scheme editor (type-specific forms with a live preview table), assessment settings picker, teacher gradebook (students × assessments, override with reason, regrade on request), student results page showing **real** review data (replaces the static stub), ORT result view (scaled score, percentile, golden-certificate flag, section breakdown).
**Tests**: **parity gate**: for every case in `test_scoring` the new schemes return identical numbers (property test over all raw scores 0…N for both exam types against the old oracle); scheme edit creates a new version and leaves old results untouched; regrade on request; override audit; recompute after attempt submit is atomic with the submission row; weighted course total edge cases (weights < 100).
**Exit criteria**: parity property test green for both scales; a teacher can create a pass/fail course and a percent course without code changes.
**Risks**: official CEATM tables unknown → ship the curve now and a `lookup_table` path ready.

---

## Phase 5 — ORT cutover (M)

**Goal**: ORT becomes ordinary course content; the old system is deleted. This is the only destructive phase and needs your explicit go-ahead.

**Work**
- Create the platform's own demo teacher and an "ORT" course per language from the existing bundles/CSVs (ky and ru), public catalog or code per D12.
- **Delete**: `ExamSet`, `ExamAccess`, `TestAttempt`, `QuestionSource` and old question tables and endpoints; the in-memory Firestore (`firebase.py`) and all call sites; `ALLOW_MOCK_TOKENS` mock-token paths (tests use real tokens/fixtures); the runtime `ALTER` helpers; `users.role`, PINs, `exam_access`; old `(admin)`/`(student)` route groups and the middleware cookie check.
- **Wipe Neon** and re-create from the Alembic baseline + new revisions (D1; testers only), keeping a backup branch first. Re-seed system grading schemes.
- Update `AGENTS.md`/`CLAUDE.md`, `docs/BUNDLE_FORMAT.md` (target model), memory notes.
**Retired tests (explicit list in the PR)**: tests of removed behavior (ExamAccess toggles, PIN gating, admin student-mode flags, Firestore fallbacks) are replaced by their new-model equivalents; nothing is deleted without a mapped replacement.
**Exit criteria**: parity gate (Phase 2–4) green; the full old ORT journey (join → take ky and ru exams → results → mistakes notebook data) passes in an automated test on the new stack; production smoke test after deploy.
**Rollback**: the pre-cutover Neon branch and the last `main` commit are kept; cutover is a single deploy.

---

## Phase 6 — Pages, modules, gating (L) · *Opus*

**Schema**: `pages`, `course_modules`, `module_prerequisites`, `module_items`, `item_completion_requirements`, `item_progress`, `module_progress`, `item_requirement_status` (architecture §7).
**Backend**: page CRUD (language variants, sanitize on write), modules/items CRUD with reorder in one transaction (deferrable unique positions), prerequisite validation (earlier module, same course, 422 on violation — never silently dropped), the 7-step gating evaluator with `rules_version` cache invalidation, fact recording (view / mark done / submit / scored from Phase 4), "re-apply rules" teacher action, computed visibility.
**Frontend**: course Modules view (student: locked/unlocked/progress, "up next"; teacher: drag-drop outline editor, requirement and prerequisite pickers, publish toggles), page editor/viewer with KaTeX, course home "continue where you left off".
**Tests**: gating matrix (all requirement types, `all`/`any`, sequential, `unlock_at` boundary, unpublished/deleted targets), cycle/forward-prerequisite rejection, regrade doesn't relock, re-apply rules does, concurrent facts, teacher bypass, cache invalidation on edits.
**Exit criteria**: a three-module course with a min-score checkpoint gates correctly end to end.

## Phase 7 — Enrollment forms, catalog, invitations (M)

**Schema**: `enrollment_forms`, `enrollment_form_fields`, `enrollment_applications`; invitations on `enrollments` (hashed tokens).
**Backend**: catalog listing (published + `visibility=catalog`, search, pagination, language filter), modes `open | invite_code | form_auto | form_review | closed`, form builder with versioning (immutable once answered), application submit/approve/reject/withdraw (approval creates the enrollment), invitation by email (Resend/Brevo path exists) with expiry, purge job for answers (D7), per-user rate limits, answers visible only to that course's teachers and never logged.
**Frontend**: catalog browse/search page, course landing page (description, languages, teacher), apply flow with purpose text, teacher form builder and applications inbox, invite dialog.
**Tests**: PII visibility matrix (other teachers/students cannot read answers), purge job, form version immutability, approval transactionality, invitation expiry/reuse.
**Exit criteria**: student applies via a teacher-made form, teacher approves, student appears in the roster; answers purge on schedule.

## Phase 8 — Practice, analytics, student tools (M)

**Backend/Frontend**
- **Practice mode**: self-paced practice assessments (unlimited attempts, immediate feedback) built from a bank by topic/difficulty using `pick` items; replaces the old practice feed with course-scoped practice.
- **Mistakes notebook** and **progress** pages rebuilt on `attempt_items` (SQL aggregates, no Firestore); target-score widget generalized to "goal" per course/scheme (optional).
- **Course analytics** for teachers: score distribution, per-question accuracy and *real* discrimination index (point-biserial from `attempt_items`), time per question, completion/gating progress; previews excluded.
- Daily planner stays deferred (it is a stub today) — D18.
**Tests**: aggregates against fixture attempts, preview exclusion, teacher can see only own course analytics, N+1 query budget tests.
**Exit criteria**: a teacher sees a correct distribution and hardest-question list from real attempts; a student's mistakes notebook matches their attempts.

## Phase 9 — Privacy, hardening, launch (M)

- **Privacy**: consent capture at sign-up by age band, `consent_records`, `policy_versions`, data export/delete requests with due dates, attempts of deleted users anonymized (D17), personal-data column registry, minimum-age flow per D5, legal review of consent wording and cross-border basis.
- **Security**: full `/security-review`; dependency audit; rate limits everywhere that guesses are possible (login, codes, join); JWT lifetime/revocation decision; HttpOnly cookie sessions evaluation; CSP headers; backups and restore drill (Neon branches); secrets rotation (default `SECRET_KEY`).
- **Performance**: indexes reviewed with `EXPLAIN` on realistic data (10k attempts, 150-item attempts, 500-student course); full-scale load test at 6,000 concurrent students (start burst, autosave, submit burst) on production-like infrastructure; capacity plan and cost per month documented.
- **Operations**: runbooks (deploy, rollback, restore), error tracking, uptime checks, structured logs, cost review, Render plan (D4).
- **Quality**: Playwright end-to-end suite for the golden journeys (teacher builds/publishes; student joins/takes/reviews; ORT parity; enrollment form).
**Exit criteria**: launch checklist signed off by you; restore drill passed; load test within targets agreed with you.

---

## Cross-cutting test strategy

- **Pyramid**: unit tests for pure logic (grading `apply()`, type scorers, gating evaluator, authz grants) → service tests on a real database (SQLite fast path, Postgres in CI) → API contract tests (serializers, error shapes, permission matrix) → a small Playwright suite for golden journeys.
- **Property tests** (Hypothesis) for ORT scoring parity and gating invariants.
- **Concurrency tests** on Postgres for submit, join limit, and autosave.
- **Security tests as code**: route-inventory, isolation suite, serializer contract tests, upload abuse corpus.

## Progress tracking

`task-progress.md` (memory) and `docs/phases/PHASE_N.md` are updated at each phase boundary so any session — or any model — can resume.

---

## Decisions (reply only to change a default)

| ID | Question | Recommended default |
|---|---|---|
| D1 | Wipe Neon and start from Alembic? | Baseline the current schema now; wipe Neon at the Phase 5 cutover (testers only), with a backup branch. |
| D2 | Storage vendor and domain | Cloudflare R2; use a domain with DNS on Cloudflare for a public image CDN; until then serve via the backend. |
| D3 | Content images of private courses | Unguessable hashed URLs for course content images; signed URLs for private files and student uploads. |
| D4 | Render plan; Vercel Hobby clause | Render paid plan (pre-deploy migrations, no spin-down); check Vercel Hobby's non-commercial clause before real launch. |
| D5 | Minimum age / guardian consent | Require 14+ at launch; guardian flow later after legal review. |
| D6 | ORT "raw 0 → 0" below the stated 60 minimum | Preserve exactly during parity; then decide and change deliberately with a test update. |
| D7 | Application-answer retention | 30 days after rejection/withdrawal/unenroll. |
| D8 | Server timer grace | 45 seconds (Canvas uses 1–5 minutes). |
| D9 | Editing a published quiz | Allowed; creates a draft; republish bumps the version; in-flight attempts keep the old version; teacher is warned if attempts exist. |
| D10 | Who can create courses | Any verified user 14+ (aligned with D5). |
| D11 | Which score counts for retakes (ORT) | Highest (teacher-configurable per assessment). |
| D12 | "ORT visible to everyone" | A catalog-listed course students join with one click; no anonymous reading in v1. |
| D13 | Re-lock after a regrade | No (Canvas behavior) plus a teacher "re-apply rules" action. |
| D14 | Scheme edits and old results | New version; regrade only on request. |
| D15 | Translations model | Monolingual question variants linked by a translation group (decided in the architecture). |
| D16 | Language variants of a page | One module item, many language variants; "viewed" counts any variant. |
| D17 | Deleted users' attempts | Anonymize and keep for statistics. |
| D18 | Daily planner / target-score widget | Defer the planner; keep a simple per-course goal later. |
