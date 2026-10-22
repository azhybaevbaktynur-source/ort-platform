# Project Understanding: ORT Platform → Canvas-style LMS

**Written**: 2026-10-21, branch `fix/question-order` (`94e8124`)
**Basis**: AGENTS.md, the four docs, and the real code (backend models, schemas, services, endpoints, core, db, all 12 test modules; frontend middleware, API client, auth context, layouts, route inventory).
**Not done**: no file was changed except this one. Four suspected defects were reproduced against a throw-away SQLite DB in `/tmp` (since deleted); `backend/test.db` and `backend/data/` were not touched. I did not read `backend/.env`. I did not read every frontend page line by line (about 15k lines); frontend claims below come from the layouts, middleware, auth context, API client and the audit doc, and are marked where unverified. I do not have the Canvas source, so statements about Canvas's real design are from memory and marked as such.

---

## 0. Findings that need your attention first

These are bugs and exposures in the **current** system, independent of the Canvas redesign. The first four were reproduced by running the code.

| # | Finding | Evidence | Severity |
|---|---|---|---|
| 1 | **Any logged-in student can read the answer key and explanation of every question**, including exams they have no access to. `GET /questions` and `GET /questions/{id}` use `get_current_user` and return `QuestionInDB` (with `correct_option`, `explanation`). The docstring says students get projections; the code does not do it. | Probe: student token → `correct_option: "A"`, explanation present, both endpoints 200. | High |
| 2 | **The exam PIN is sent to students.** `ExamSet` responses include `access_code`; `GET /exam-sets/student` and `GET /exam-sets/{id}` return it to the student. The PIN gate is decorative. | Probe: student sees `access_code: 4321`. (Probe used a practice-bank set; the serializer is shared, so full/subject exams behave the same.) | High |
| 3 | **A submitted attempt can be submitted again.** `submit_and_score_test` has no "already completed" guard, and the first submit returns the full review with correct answers. Probe: first submit 0/25, resubmit with the correct answers → 25/25, HTTP 200. It also increments `exams_taken` again. Only `save_session_progress` has the lock. | Probe. | High (cheating, score integrity) |
| 4 | **Updating an exam fails after a backend restart.** `update_exam_set` requires the exam to exist in the in-memory Firestore mock, which is wiped on restart. A SQL-only exam then returns 404 on `PUT` (publish/unpublish, PIN, schedule). | Probe: create → reset store → `PUT` → 404. On Render, restarts and cold starts happen. | High (admin tooling silently broken) |
| 5 | Any admin can edit/delete/publish **any** exam and question; `created_by` is stored but never checked. | `exam_sets.py`, `questions.py`, `question_service.py`. | Blocker for multi-teacher |
| 6 | The max-attempts check, completion counts, in-progress detection and **both analytics endpoints read the in-memory mock**, not SQL. After a restart, instructor analytics and student `/analytics/student` start from zero while SQL still has the data. | `mock_test_service.py:421-428`, `analytics.py`. Contradicts AGENTS.md ("SQL is the primary source of truth"). | High (data appears lost; attempt limits reset on restart) |
| 7 | Hard-coded email `azhybaev.baktynur@gmail.com` is auto-promoted to admin on every startup (`init_db.py:82`). | The repo is public. Email verification is the only protection. | Medium |
| 8 | `/uploads` is public and unauthenticated; `.svg` uploads are allowed and served from the API origin. | `main.py`, `upload.py`. | Medium |
| 9 | 4-digit PIN: stored in plain text, no rate limit (10,000 guesses). Tokens: 7-day JWT in `localStorage` plus a non-HttpOnly cookie, no revocation. | `security.py`, `auth-context.tsx`. | Medium |
| 10 | Deleting an `ExamSet` cascades to **all students' attempts** for it (`cascade="all, delete-orphan"` on `attempts`). | `models/exam_set.py`. | High once teachers own content |

Not verified, worth a look: `exam_sets.py` uses `Dict`, `Any` and `logger` without importing them (a `NameError` would only trigger inside an existing `except` block); the bundle format lists subject sections `math_subject`, `kyrgyz_lang_lit`, `russian_lang_lit`, which `question_order.py` knows but the `SectionType` enum does not.

---

## 1. How the system works end to end

### 1.1 Stack and storage (reality)
- **Backend**: FastAPI, SQLAlchemy 2 (`declarative_base`, legacy `Column` style), SQLite locally, Neon Postgres in production. No Alembic: `init_db()` runs `create_all` plus hand-written `ALTER TABLE ADD COLUMN` helpers on every boot.
- **"Firestore"**: `PersistentLocalFirestore` is a pure in-memory dict (the "File-backed persistent" comment in `firebase.py` is wrong). It is seeded at import (canonical exam sets + sample CSV questions) and wiped on restart. It is dual-written by many services and still **read** by several (see §0 #4, #6, and §5).
- **Frontend**: Next.js 15, React 19, hooks/context only, `fetch` wrapper `lib/api.ts`, `localStorage` token. Route groups `(auth)`, `(student)`, `(admin)` under `[lang]` (ky/ru).
- **Files**: `LocalStorageService` writes to disk and serves `/uploads`; `CloudStorageService` is a stub. If production uses local disk on Render, uploaded images vanish on redeploy (open question Q9).

### 1.2 Auth and roles
- Register (always `role="student"`) → 6-digit code, HMAC-hashed, 10-min TTL, 5 attempts, 60-s resend cooldown → verify → JWT (HS256, 7 days). Login blocks unverified accounts. Password reset by emailed token (SHA-256 stored).
- `get_current_user` decodes the JWT, loads the user from SQL on **every request** and takes the role from the DB (token `role` claim ignored). Good, and tested.
- Roles: exactly `student | admin`. `require_instructor` is an alias of `require_admin`. `require_student` accepts both. There is no `teacher`.
- Mock tokens (`mock_admin_token`, plus "any token containing `admin`" fallback) work only when `ALLOW_MOCK_TOKENS=true`; the app logs CRITICAL if that is on in production. Default `SECRET_KEY` is public in the repo; production only logs a warning.
- Admins are made via `make_admin.py` or the hard-coded email.
- Frontend guards: `(admin)/layout.tsx` redirects non-admins client-side; `middleware.ts` checks the `ort_role` cookie, which the browser sets and the user can edit. This is UX only; the real guard is the backend.

### 1.3 Content model (what a "question bank" is today)
- A `Question` belongs to **at most one** `ExamSet` (`exam_set_id` FK, cascade delete). Order is `Question.position` (1-based across sections) and `q_num`. `ExamSet.question_ids` (JSON) is a second, partly redundant reference list; queries OR the two.
- Exam types: `full_main`, `subject`, `practice_bank`. Sections are an ORT-specific enum; `math_1` must have `column_a/b`, others must not (enforced in API, CSV, and bundle paths; tested).
- `practice_bank` sets are the "free" pools: one per language, always visible. Practice sessions (`is_fast_practice`) load questions by language across the table, not from the set's own list.
- Imports: 15-column CSV (`csv_service`, `csv_image_rule`) and ort-digitizer `.zip` bundles (`bundle_service`, 832 lines: safe zip, manifest/fallback discovery, SHA-256 image keys, preview then single-transaction upsert by `external_id`, one exam set per source with id `exam_bundle_<source_id>`, created `published`). `QuestionSource.external_id` is a global primary key.

### 1.4 Exam flow
1. Student lists exams: `GET /exam-sets/student` returns published `practice_bank` sets plus `full_main`/`subject` sets with an `ExamAccess` row. Admins see all published sets and are flagged preview.
2. `POST /mock-tests/start`: checks (non-practice only) access row → published → availability window (ISO strings compared lexically) → PIN → max attempts (read from the mock store). Practice is exempt from all of these. Detection of "practice" is by `exam_type` **or `"practice" in template_id.lower()`** (a fragile string match).
3. Questions are loaded from SQL in document order, grouped by section, answer keys stripped; sections define time limits. An attempt row is written to the mock store **and** SQL (SQL write wrapped in `except: pass`). The attempt stores its own `question_ids`, which is what makes the test stable if the bank changes.
4. Autosave `POST /{id}/save` (answers, remaining time, section index). Time is client-reported: the server never enforces the timer.
5. Submit (`/submit` or `/save` with `final`): grades via `ScoringService`, writes score, section breakdown, and per-question review to both stores, updates `User.exams_taken/current_score/starting_score` (not for previews, not for subject tests' `current_score`), supersedes other in-progress attempts of that template.
6. Review/mistakes read completed attempts (mock store first, SQL fallback).

### 1.5 Scoring
- `ScoringService`: raw = 1 point per correct, unanswered = 0. Scaled via a piecewise power curve around ratio 0.5 (main 60–245 mean 150; subject 60–150 mean 105); percentile from a normal CDF; golden certificate ≥ 219 (main only). Note `raw_to_scaled` returns **0** for raw 0 (below the stated 60 minimum) and 245/150 for a perfect score. The curve is a **model**, not the official CEATM conversion table; the code comments say "calibrated" but nothing in the repo shows calibration data. Section-level "scaled scores" apply the same curve to each section.
- `exam_type` selects the scale. Everything ORT-specific (219, 150 questions, section weights table that is unused) is global config.

### 1.6 Analytics
- Student (`/analytics/student`): reads the mock store's `test_attempts`; static per-section time defaults.
- Instructor (`/analytics/instructor`): loads **all** users, **all** completed attempts and **all** questions from the mock store; excludes previews and admin accounts; buckets scores; "discrimination index" is `1 − accuracy` clamped to 0.1–0.9, which is not a discrimination index. When there are no attempts it fabricates a "hardest questions" list from the bank. This also breaks AGENTS.md rule 6 (no unbounded reads).

### 1.7 Admin surface
Single global admin portal: exam sets, question bank (12k, paginated), student roster (every `student` user in the system), per-student/per-exam access toggles, bulk upload, analytics. Student mode lets an admin take any published exam as a preview.

---

## 2. Models and relationships

```
User 1─* ExamAccess *─1 ExamSet 1─* Question 1─1 QuestionSource
User 1─* TestAttempt ··(template_id, no FK)·· ExamSet
ExamSet.question_ids (JSON list of Question ids)   ExamSet.attempts (cascade via primaryjoin on template_id)
```

| Model | Notes that matter for the redesign |
|---|---|
| `User` | `role` string; global scores (`current_score`, `starting_score`, `exams_taken`, `target_score`) assume one ORT track per user. Verification and reset fields. No tenant, no owner. |
| `ExamSet` | The "exam" and the "container" at once. Sections/time/PIN/availability/attempts/status all live here. `created_by` is a plain string (no FK, never checked). |
| `Question` | ORT-shaped: `column_a/b`, options A–E only, single correct option, `section` from an enum. Monolingual (`language`). `created_by` unchecked. `stats` JSON is stored but analytics don't use it. |
| `ExamAccess` | The only "enrollment" concept: user ↔ exam, granted by a global admin, no course/teacher/cohort. |
| `TestAttempt` | `template_id` has no FK; `answers`, `scores`, `review` are JSON blobs; `is_preview` flag. Doubles as the "submission". |
| `QuestionSource` | Import provenance; global key. |

### Where "one admin / one exam bank" is hard-coded
1. `UserRole` enum and `require_instructor = require_admin`; every write endpoint uses it.
2. `init_db.py`: hard-coded admin email; fixed canonical exam ids re-seeded on **every boot** (overwrites title, description, sections, type of those rows, so a rename by an admin is reverted).
3. `admin.py`: roster = all users with `role == "student"`; any admin can grant any student any exam.
4. `exam_sets.py` / `mock_test_service.py`: update, delete, publish with no owner check. `/exam-sets` (non-student) lists drafts of every admin.
5. `questions.py` / `question_service.py`: global list and CRUD; students can read all (§0 #1).
6. `ExamAccess` is per exam, granted by a single role.
7. Practice bank: per-language global pool; a start with practice loads questions by language. If teachers' private questions share the table, they would leak into it. (`test_two_pool_practice_isolation` covers the current two pools only.)
8. Analytics: global cohort, no filter by teacher or class.
9. Bundle/CSV: `exam_bundle_<source_id>` and `QuestionSource.external_id` are global. Teacher B uploading a bundle with the same `source_id` would update Teacher A's questions.
10. Uploads: one global namespace, public, no owner.
11. Scoring/config: ORT scales, 219 threshold, `SectionType`, `math_1` rule, `preferredLanguage="ky"` hard-coded in `get_current_user`.
12. Frontend: `(admin)` route group = global admin; flat URLs (`/exams`, `/questions`) with no course context; nav links fixed.

---

## 3. What the tests protect (106 tests; must not break)

| Area | Protected behavior |
|---|---|
| **Auth** (`test_auth_flow`) | email code required before login; wrong-code lockout then resend with cooldown; expiry; unknown email reveals nothing; email failure reported honestly; verified-flag migration; cost-12 hash upgraded at login; mock tokens rejected when disabled; deleted user's token rejected; reset flow and expiry. |
| **Scoring** (`test_scoring`) | boundary and median scaled scores, percentile, golden certificate threshold, subject scale, review generation. Any new "grading scheme" must reproduce these numbers for ORT exams. |
| **Question order** (`test_question_order`) | import keeps document order; admin list, results review, mistakes follow document order; move up/down within section; new question appended; backfill. This invariant (`position`) must survive any move to a join table. |
| **Bundle import** (`test_bundle_import`, 20 tests) | the 12 acceptance cases of `BUNDLE_FORMAT.md` plus zip-slip, version refusal, sha mismatch, partial-import refusal, re-upload upsert, leftover warning. |
| **CSV / math rule** | 15-column parsing, Cyrillic normalization, math_1 comparison rule, images. |
| **Student mode** (`test_student_mode`) | admin sees all published; role from DB not token claims; previews excluded from stats; previews ignore attempt limits. |
| **Mock test service / API** | start/save/resume/submit, PIN and practice exemption, access gating, exam CRUD and cascade deletion, student practice projection, analytics split. |
| **Practice** | strict bank selection, topic filter, submit/mastery. |

**Not protected (gaps):** answer-key privacy on `/questions` (§0 #1); PIN not exposed (#2); resubmission (#3); persistence across restart (every test resets the mock store and starts fresh, so the mock-vs-SQL divergence cannot show up); anything about ownership or multiple admins; timer enforcement; attempt isolation between two real students (mock tokens map to fixed users). Tests lean on `mock_firestore_db.reset()`, so they would need rework when the mock is removed.

---

## 4. Current code vs AGENTS.md

AGENTS.md (v2.0.0, already rewritten) is far closer to reality than the old one the audit doc describes. Remaining differences:

| AGENTS.md says | Code does |
|---|---|
| "SQL is the primary source of truth; Firebase a secondary mirror" | Several reads and writes depend on the mock (exam update/delete lookup, attempt-limit check, completion counts, in-progress state, both analytics). |
| `PersistentLocalFirestore` "persistent" (in comments) | Pure in-memory. |
| Rule 6: no unbounded reads; paginate | `get_exam_sets`, analytics, `get_exam_set_by_id` (Firestore branch) scan all questions/attempts. |
| Rule 2: no hard-coded accounts | Hard-coded admin **email** promotion (no password, but still a fixed privileged identity). |
| §5.3: admins preview as students | True; but other endpoints (`/exam-sets`, `/admin/exams`) show every admin's drafts. |
| §4 schemas | Missing `created_by` on `ExamSet`/`Question`, `User.reset_requested_at`, `ExamSet.updated_at`; `TestAttempt.template_id` has no FK; `ExamSet.attempts` cascades. |
| §2.1 "Roles are verified on every request" | True for JWT; plus mock-token branches (flagged and test-only). |
| Test count 106 | Matches the audit; I did not re-run the suite for this document. |
| Roadmap #2 (result page static review) | Taken from the audit; not re-verified by me. |

The old `CURRENT_STATE_AUDIT.md` (deleted 2026-10-22) was mostly accurate but too generous: it labels analytics and `exam_sets` "100% complete / SQL" and misses all of §0.

---

## 5. Mocked, stubbed, fragile

- **Mock Firestore store**: described above; the single biggest source of drift. Silent `except Exception: pass` around nearly every SQL sync means a failed SQL write is invisible and the two copies diverge.
- **Planner** (`planner.py`): in-memory dict with static tasks.
- **`CloudStorageService`**: log-only stub.
- **Analytics**: fake discrimination index, fabricated fallback list, `total_students = max(n, 1)`.
- **Timer**: client-trusted; no server cut-off; `remainingTimeSeconds` accepted as sent.
- **Endpoint `print()`** of whole submission payloads (`mock_tests.py`) writes answers to logs.
- **Availability window** compared as strings (`now_iso < available_from`): wrong if offsets differ.
- **Runtime migrations**: fine for `ADD COLUMN`; cannot express new FKs, unique constraints, data backfills, or reversible steps. Two parallel mechanisms (`init_db.py` inline plus helper modules).
- **Dual id sources**: `Question.exam_set_id` and `ExamSet.question_ids` both define membership.
- **Duplicate routers**: `/exam-sets` and `/exams` both mounted; exam-set routes also duplicated under `/mock-tests`, with different permissions (the `/mock-tests/exam-sets/{id}` GET has no draft check).
- **Frontend**: three admin/student pages above 1,000 lines (`mock-tests/[testId]` 1,778; `questions` 1,124; `exams/[examId]` 1,117); role cookie is client-writable; `ky.json`/`ru.json` have equal line counts (229) but I did not diff the keys.
- Also worth noting: attempt/user history is the only durable record of learning; `TestAttempt.review` embeds full question text and answers (a snapshot, which is good for history, heavy for storage).

---

## 6. Critical review of the two Canvas documents

> The reviewed drafts were deleted on 2026-10-22; the current design is `docs/LMS_ARCHITECTURE.md`. Kept as history.

### 6.1 `CANVAS_INTEGRATION_SPEC.md`

**Good**
- The core ideas fit your goal: courses owned by a teacher, cohorts, modules with gating, question banks decoupled from quizzes. `Account → Course → Section → Enrollment` and "roles live on the enrollment" are the right mental model for "teachers connected with their own students".
- The decoupling of questions from exams (bank + quiz) removes today's biggest limitation (one question, one exam).
- Self-enrollment codes and `AssignmentOverride`-style per-section dates are a good, small, valuable subset.

**Wrong, risky, or missing**
1. **The blueprint stops where the product starts.** Section 8 defines Account, Course, Section, Enrollment, Module, ContentTag, Bank, Question, but **no Quiz, QuizGroup/QuizItem, Assignment, Submission/Attempt, Grade, or Page** model, although §9's table says ORT is "a fixed 150-Q timed exam via `Quiz`". The thing this platform actually does (timed attempts, scoring, review) has no home in the schema.
2. **Scoring is not modeled.** ORT scaled scoring (60–245, 60–150, percentile, golden certificate) needs a per-quiz *grading scheme* (`ort_main`, `ort_subject`, `percent`, `points`). The spec mentions "Standard ORT Scaled Curve" in a UI sketch only.
3. **Question model is too loose and too wide at once.** `question_data` as one JSON blob throws away what the current typed columns give (validation, `math_1` rule, indexed `section/topic/difficulty`, order). It then lists 9 Canvas question types (calculated, file upload, multi-answer, essay…), none of which the exam player or scorer supports. Reading passages (shared across rows today) and the Column A/B type have no representation.
4. **Question order is lost.** Document order (`position`) is a tested invariant; in a bank+quiz design it must live on the quiz-item join (`quiz_id, question_id, position, points`), and the spec has no such table.
5. **Sections are not optional in practice.** Real Canvas always creates a default section per course; a "Section" you must pick is friction for a tutor with one class. The spec makes `Enrollment.course_section_id` non-null but never says how a default section is created.
6. **Not tenant-safe by itself.** `Account` is introduced but nothing says every query is scoped by it. Without a single authorization layer (see §7), the same "any admin does anything" bug reappears as "any teacher edits any course".
7. **`Enrollment.user_id` has no FK**, `ContentTag.content_id` is an untyped string, and `context_type/context_id` is polymorphic with no integrity. Canvas (Rails) tolerates this through its own code; with SQLAlchemy and Postgres you should prefer real foreign keys (nullable typed columns with a CHECK, or one table per item kind).
8. **`prerequisites` and `completion_requirements` as JSON lists** mirror Canvas's serialized columns, which are a legacy of Rails. They can't be queried or constrained and are painful to migrate. Use rows (`module_prerequisites`, `completion_requirements`).
9. **Code mismatches with this repo**: the sample defines a new `DeclarativeBase` in `canvas_core.py`; the repo uses `declarative_base()` from `app.db.session`, so two metadata registries would diverge. String PKs without the project's `prefix_uuid` convention. `user_id`, status words (`workflow_state`) differ from the existing `status` columns.
10. **Not addressed at all**: migration of the existing 12k questions and ORT exams, soft delete (today deleting an exam deletes students' history), question versioning (editing a question after attempts exist), copy/sharing between teachers, platform-owned content vs teacher-owned content, data-privacy for minors, enrollment-code abuse and rate limiting, teacher onboarding/approval, notifications, translation of teacher-authored content, rollout order.
11. **Scope.** SpeedGrader, discussions, observers, cross-listing, terms, pseudonyms, sub-account hierarchies, calculated questions and Blueprint courses are each months of work. Presented as one "definitive blueprint" they will stall the part that matters.
12. **Accuracy of the Canvas claims (from memory, not verified against the repo)**: Canvas is moving from Classic Quizzes (`Quizzes::Quiz`, which the spec describes) to New Quizzes (a separate service), so copying the classic model copies the legacy side. The spec's claim that SpeedGrader lives in `submissions_api_controller` looks wrong (the page is rendered by the gradebooks controller; the API is separate). The "document verified against official source" framing should not be taken at face value: I could not confirm it and some details are simplified (e.g. random draw is not literally `ORDER BY RANDOM()`).
13. **Invariants it breaks if applied literally**: random `QuizGroup` draws conflict with fixed document order and with comparability of ORT scores; fine as an option for practice, wrong default for mocks.

**What I would reconsider**
- Keep the spec as a vocabulary and a menu, not a schema to copy. Build the thin core first (§7).
- Replace "Account" with a nullable `owner`/`account_id` on Course and Bank now, and add the Account table when a second organization exists.

### 6.2 `CANVAS_EXPLAINER_FOR_FOUNDER.md`

**Good**: readable, makes the vision concrete (course cards, join code, gating), and the join-by-code flow is the right first enrollment path.

**Wrong or unsupported**
1. **"Navigation paralysis" does not describe the current product.** Students do not see 12,000 questions or 15 exams: they see practice banks plus exams an admin explicitly granted (`/exam-sets/student`). The churn flowchart ("student churns after 3 days") is invented, not measured; it should not be used to justify the work without real retention data.
2. **A Course is not "a blueprint with no students attached" in Canvas.** In Canvas the course is where students are enrolled (through sections). The reusable-template idea is a separate feature (Blueprint courses/templates). The doc's mapping would give teachers a template they cannot actually teach from. For this product: a Course is a teacher's live class; "templates" are copy/import.
3. **"Nothing is hardcoded to a specific exam"** is the goal, but ORT is highly specialized (comparison questions, normative scaling, ordered sections). The doc understates that ORT must become a *configuration* of the generic engine (a quiz type + grading scheme), which is real work.
4. **"Teachers do the work instead of engineers"** assumes a teacher studio, import tooling and moderation that don't exist; today even exam publishing needs an admin.
5. **B2B licensing as "the primary growth engine"** is a strategy claim with no data. Fine as a hypothesis; it should be a question for you, not a premise (it drives the Account-hierarchy priority).
6. Features sold as simple (SpeedGrader, discussions, audio feedback, observers) are large and not needed for the stated goal.
7. Lists "Quantitative Comparison" as a Canvas question format; it is not one in Canvas. It is ORT-specific and must be a custom type here.

---

## 7. What I would propose (for discussion, not a decision)

1. **Fix the §0 items first** (answer-key leak, PIN exposure, resubmission, restart-dependent updates). They are small, independent, and block any multi-teacher launch.
2. **Remove the mock store from the read path** (and ideally entirely), then adopt **Alembic** before adding tables.
3. **One authorization module** (`can(user, action, resource)`): platform role (`user | platform_admin`) plus enrollment role (`teacher | student | ta`) per course. Every endpoint goes through it; add cross-tenant tests first.
4. **Minimal LMS core (Phase 1)**: `Course` (owner, language, join code, soft-delete state), `Enrollment` (role, state; default section created implicitly), `QuestionBank` (owner, optional course), `Question` keeps its typed columns and moves under a bank, `Quiz` + `QuizItem` (ordered join with points, section label, time), `Attempt` keeps the JSON review snapshot. ORT exams are migrated into one platform-owned course and bank. Grading scheme as a quiz setting with `ort_main`, `ort_subject`, `percent`.
5. **Phase 2**: modules and gating (rows, not JSON), sections/cohorts with date overrides, teacher analytics scoped to a course, copy-from-platform-bank.
6. **Later**: accounts/schools, SpeedGrader/manual grading, new question types, observers.

---

## 8. Open questions for you

1. **Who is a teacher?** Self-service sign-up, admin approval, or invite only? Can a user be teacher in one course and student in another?
2. **Who owns the existing 12k questions?** Platform-owned and read-only for teachers (copy to edit), or visible/editable by everyone with the teacher role?
3. **Can a teacher share their questions** with other teachers, with a school, or never?
4. **Do you want Sections in v1**, or one class per course (a default section hidden from the UI)?
5. **B2B schools**: is that a real near-term target (then Account and bulk roster import move up), or a hypothesis?
6. **ORT scoring**: is the current curve acceptable as is, or do you have the official conversion tables? Should teachers be able to choose a grading scheme for their own tests?
7. **Student access today**: should the existing `ExamAccess` list be converted into enrollments in an "ORT" course, and what happens to the open practice banks (a free public course)?
8. **Deleting content**: soft delete with history kept (my recommendation) versus the current cascade?
9. **Production storage and runtime**: where do uploaded images live on Render (ephemeral disk or something else), and is the Render instance restarted/spun down regularly? This determines how urgent §0 #4/#6 are in practice.
10. **Existing students' data**: is anything in the production DB you must migrate exactly (attempts, scores), and may I run read-only queries through the Render/Neon tools to measure it?
11. **Privacy**: are users under 18? Any legal requirements on storing their data (consent, location)?
12. **Languages**: should a course have a single language, or can a course mix ky and ru content?
13. **PIN-gated exams**: keep the PIN (and hash it, rate-limit it) or replace it with enrollment-based access?
14. **The hard-coded admin email** in `init_db.py`: can I remove it in favour of `make_admin.py` only?
15. **Priority**: should the §0 fixes ship before design work starts, as a separate branch?

lets fristly answer to rpovided 15 questions 
1. probalby here teacher can sign up by themselves and they can only ne teachers. 
2. of addressing 12k question. formulating when we started that project we just think that we will have 12k question in our platform. currently we rethinking it. we want to make different thin. 12k question is not important now. when we can build like canvas lms we can just open course as ort make it visible to everyone. for exmaple by teacher account open course and upload that question regarding ort. currentl it is not a problem. 
3. if we will have exact architecture as school and etc under teacher yes they can share. but again currently it is not a problem. because we want to reach that level of where teacher can create their courses. 
4. for one course we dont need sections. one course and that is it we dont need to divide into classes inside that course. (kinda adapting to ourselve)
5. not near term. as I mentioned we need to put a real goals. current documents are not perfect we are very flexible to cahnge them. 
6. yes again we want to make it flxible grading criteria. we are not fixed only to ort now. 
7. again we do not have users for now they are just testers we can remove them totally. 
8. yes lets make sofisticated system 
9. I dont know regarding that where images are saved. probably they are not saved because after one session images are jsut disaapearing. we need to build that also. 
10. yes you ahve all access to read all required documents and access any required tools 
11. maybe we need to add that 
12. probalby it would be great if we can integrate into system to have three language by defaul where teacher can regulate their courses. (english/ russian/ kyrgyz)
13. for that one I am thinking of system where firstly students can get into portal to system and enroll to courses (maybe by filling out form which can be created by teacher)
14. yes 
15. lets fix thats. 

