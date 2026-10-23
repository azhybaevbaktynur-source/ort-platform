# Implementation Plan (phase by phase)

**Status**: Phases 0–5 done and deployed (2026-10-23); H1 hotfix released 2026-10-24. Phases 6–11 rewritten 2026-10-24 to the owner's decisions (`PRODUCT_DECISIONS.md`, "Owner decisions 2026-10-24" and "second round"): organizations first (personal organizations for independents), ORT as a locked course template kept exactly as today with an **ORT review** every phase, assignments before modules, **exam templates** (owner's constructor idea) as 7b (data model) and 8b (visual builder) pending the owner's review of `docs/phases/EXAM_TEMPLATES_DESIGN.md`, UX gate every phase. Design: `LMS_ARCHITECTURE.md`. Decisions D1–D24 are at the end; "Alternatives" closes the file (A1–A12 decided; B1–B12 open).
**Sizes** are relative effort (S ≈ days, M ≈ 1–2 weeks, L ≈ 3–4 weeks of focused work with an AI pair), not promises.

---

## 0. Strategy

1. **Strangler, not big bang.** The current ORT app (with the security fixes already committed) keeps running in production while the LMS is built *beside it* in new packages (`backend/app/lms/…`, `frontend/src/app/[lang]/courses/…`) on new tables added through Alembic. We do **not** refactor old exam code that will be deleted. Old code is removed in one planned **cutover (Phase 5)**, after an ORT parity gate passes. This avoids wasted work on the in-memory Firestore, `ExamSet` and `ExamAccess`.
2. **Integration branch.** Long-lived `lms` branch off `main`. Each phase is a short-lived branch merged into `lms` by PR after its exit criteria pass. `main` only receives fixes until Phase 5.
3. **Every phase ships a vertical slice**: migration + models + service + endpoints + teacher/student UI + i18n (en/ru/ky) + tests. No phase ends with "backend only, UI later".
4. **Gates that apply to every phase** (definition of done):
   - `pytest` green on SQLite *and* Postgres 18 (matches Neon) in CI; `alembic upgrade head` + `alembic check` clean; frontend `tsc --noEmit` and `next build` clean (isolated copy, per `AGENTS.md`).
   - Every new route is in the permission matrix (route-inventory test), with table-driven action × role × status tests and cross-tenant tests (teacher A cannot see or edit teacher B's anything).
   - i18n key parity across `en.json`, `ky.json`, `ru.json` (CI check). No hard-coded user-facing strings.
   - No answer keys, PINs, join codes or other users' data in any student-facing payload (contract tests on serializers).
   - Soft delete only; attempts and submissions never cascade.
   - A short `docs/phases/PHASE_N.md` note: what changed, how to verify, what was deferred.
   - Code review pass (`/code-review`) before merge; security review (`/security-review`) at phases 1, 3, 6 (organizations/authz), 7 (assignments, student file uploads), 9 (invitations, PII), 11.
   - **ORT review (owner rule A, revised 2026-10-24 second round; every phase from 6 on)**. "ORT must not change" means ORT's **functionality and exam behaviour** stay the same; its **design and layout keep up** with the platform. Each phase: (1) **Look**: check the ORT screens (bank, CSV/zip upload, exam builder, exam player, results, student course pages) for design and arrangement against the design system, navigation and the rest of the platform, on phones too; apply visual and layout updates (colors, spacing, components, menus, page arrangement, phone layout) so ORT never looks like an old, separate app. (2) **Function**: the parity tests (the reference ORT CSV and zip bundles import identically: same banks, questions, positions, images, warnings; the ORT API/e2e tests pass unchanged; ORT scores: scaled, percentile, section breakdown, golden certificate match the parity property test) **plus a real walkthrough**: upload a CSV and a zip, build an ORT exam, take it as a student, see the result. (3) **ux-reviewer** reviews the ORT screens with the rest; design findings are fixed without asking. Anything that changes **how ORT works** (exam rules, timing, navigation, question layout during the exam, scoring, import formats) is never done in a phase: it goes into `docs/ORT_PLAYER_IDEAS.md` for the owner's decision. (4) **Report** in `docs/phases/PHASE_N.md` what changed in ORT's look, with before/after screenshots, and confirm functionality is unchanged (test names + walkthrough). (5) **Screenshot check**: the comparison runs against the **approved "after" baselines** in `docs/phases/ORT_BASELINE/` (tolerance + DOM assertions), so allowed polish is not flagged as a regression; every baseline update is reviewed in the PR with before/after images. From Phase 7b the ORT expressibility dry-run test (`EXAM_TEMPLATES_DESIGN.md` §8) is part of this review if the owner agrees (B9).
   - **UX gate (added 2026-10-24, owner rule D4)**: before merging, screenshots of every new or changed screen at 375 px and desktop (student screens in en, ky and ru), reviewed by the `ux-reviewer` agent (`.claude/agents/ux-reviewer.md`, Fable) against `docs/UX_GUIDELINES.md`; findings are fixed, not deferred; the final screenshots are saved in `docs/phases/PHASE_N_screens/`. UX reviews never wait for the owner.
   - After the cutover `lms` and `main` carry the same code: a phase branch merges into `lms` and then into `main` (deploy, `AGENTS.md` §6.7) only after every gate above passes.
5. **Models for the work** (owner decision B, 2026-10-22): the main session runs on **Fable** (Opus if Fable is unavailable) as orchestrator only: phase plans, slicing, briefs, review of every diff, full gates, commit/push/merge/deploy, minimal own reading and typing. Subagents (revised 2026-10-22): `architect` (**Fable**) designs and reviews the hard parts (authz, attempt engine, grading, gating, concurrency, security); `implementer` (**Opus** by default, **Sonnet** for simple well-specified work incl. mechanical edits) implements from precise briefs (goal, exact files, schema/API shape, tests that must pass), independent slices in parallel; escalate on failure sonnet → opus → fable; no Haiku. No subagents for single-file lookups.
6. **Git and production** (owner decision A, 2026-10-22): the agent pushes, merges into `lms`/`main` and deploys without asking, with a Neon backup branch before `main` merges that touch models/migrations/DB files and a `/health` commit check after each deploy. Owner OK only for Phase 5, Neon data deletion/wipes, spending money, and owner secrets. No load tests against production.

## Non-functional targets (added 2026-10-22)

**Scale target: about 6,000 students active at the same time** (for example, a national mock exam where everyone starts within a few minutes). This is a design constraint for every phase, not a Phase 9 afterthought.
- Peak scenarios to design and load-test for: (a) a start burst, 6,000 attempts created within ~5 minutes, each writing ~150 `attempt_items` rows; (b) steady autosave, one write per answer per student, roughly 300 writes/s at the peak; (c) a submit burst when the timer ends, with scoring done within seconds; (d) 6,000 students loading the same quiz payload.
- Initial budgets to confirm in the capacity review (`CAPACITY_REVIEW_BRIEF.md`): API error rate < 0.5 %, p95 < 500 ms for autosave and < 2 s for attempt start, no lost answers, no double submits, zero data loss on deploy during an exam.
- The current hosting (Vercel + Render + Neon) has **not** been checked against this target. The capacity review runs first (Phase 0, task 0.0) and may change infrastructure choices before schema work starts.

## Phase overview

| # | Phase | Size | Depends on | Result you can see |
|---|---|---|---|---|
| 0 | Foundations | M | – | CI, Alembic, hardened uploads, authz scaffolding |
| 1 | Courses, enrollment, authorization | L | 0 | Admin-approved teachers create courses; students join by code |
| 2 | Files and content library | L | 1 | Persistent images; teachers build banks/questions; imports work |
| 3 | Assessments and attempts | L | 2 | Teacher builds and publishes a quiz; students take it safely |
| 4 | Grading and results | L | 3 | Flexible grading schemes; ORT scoring as data; gradebook; real review |
| 5 | **ORT cutover** (done 2026-10-23) | M | 4 | ORT is just a course; old code and Firestore mock removed |
| 6a | Organizations foundation (personal orgs for independents), course templates (ORT first, locked, admin-granted), sign-up/invite flows, migration | L | 5, H1 | Schools and independents own courses and teachers; ORT is a locked, admin-granted course template owned by the owner; teachers arrive by invitation |
| 6b | Design system, app header, student home, UX audit fixes, ORT look part 1 | M | 6a | One design system; a student home that answers "what next?"; ORT screens match the platform |
| 7a | Assignments and general gradebook | L | 6a (6b for UI) | Any gradable work (offline, text, file, quiz) in one gradebook; accommodations; quiz access codes |
| 7b | **Exam templates I**: data model, versions, create-assessment-from-template, save-as-template, general import format with template validation, block catalog (proposed; owner review pending) | M | 7a | Teachers reuse exam structures; uploads validated against a template; ORT untouched |
| 8a | Course structure: modules, pages, files, announcements, gating | L | 7a | Guided course paths with locked/unlocked steps; pages, files, announcements, course home |
| 8b | **Exam templates II**: visual constructor (platform/org/teacher), scrolling display mode, result-view and passage options UI, lock/scope UI (proposed) | M–L | 7b, 6b | Exam templates designed in a builder and previewed with the real player |
| 9 | Organizations completion, enrollment forms, invitations | M | 6a | Shared org banks, org settings and departments, roster import; catalog forms, student email invitations |
| 10 | Practice, analytics, quiz statistics, student tools | M | 7, 8 | Practice by topic, mistakes notebook, course and org analytics, item statistics |
| 11 | Privacy (observer/parent with consent), hardening, launch | M | 6–10 | Parent accounts and consent, data requests, load/security checks, runbooks |

Dependencies: 6b needs 6a; 7a needs 6a (organizations, course templates) and uses 6b's design system for its screens; 7b needs 7a (creating an exam from a template creates its assignment in the same transaction) and 6a (`assert_not_locked`, `CourseOut.template`); 8a needs 7a (module items reference assignments, not raw quizzes); 8b needs 7b and 6b and may run in parallel with 8a; 9 needs only 6a and may run in parallel with 7 and 8; 10 needs 7 and 8; 11 closes. Lettered sub-phases are separate releases with their own gates (as 6a/6b); the numbers stay so that every phase reference in the other documents remains true (Alternatives B10). Each release ships the ORT review and the UX gate (§0.4).

---

## Phase 0 — Foundations (M)

**Goal**: the safety net and shared building blocks every later phase relies on. No user-visible features.

**Work**
- **0.0 Capacity review (first task, before any schema work)**: follow `docs/CAPACITY_REVIEW_BRIEF.md`; deliver `docs/CAPACITY_REVIEW.md` with measured numbers and a go/no-go on Vercel + Render + Neon, plus the cheapest upgrade path. Its findings can change D4 and the attempt-engine design (e.g. write batching, connection pooling).
- **Alembic baseline of the *current* schema** (autogenerate against an empty Postgres, review by hand, `stamp` Neon). Naming convention for constraints; batch mode for SQLite dev. From now on schema changes are Alembic revisions only; the runtime `ALTER` helpers stay until cutover, then are deleted. Migrations run as a pre-deploy step (D4).
- **CI** (GitHub Actions): backend tests on SQLite and Postgres 18, `alembic upgrade head`, `alembic check`, pytest-alembic built-ins, frontend `tsc` + build, i18n key-parity check, lint.
- **Shared building blocks** in `app/lms/core/`: UUID PK + timestamps + soft-delete mixin; `LocalizedText` JSON type with Pydantic validation and read fallback; `JSON().with_variant(JSONB, "postgresql")` helper; error shape; cursor pagination helper; structured logging without PII.
- **`app/core/authz.py` scaffolding**: `can()/require()` interfaces, `ROLE_GRANTS`, the route-inventory test (initially whitelisting all existing routes so the gate is live from day one).
- **Hardening carried over from the review**: upload content check (magic bytes via Pillow) and size cap; remove `print()` of payloads; PIN stays only in old code (removed at cutover).
- **`en.json`** next to `ky.json`/`ru.json`; the language switcher gets a third option.

**Exit criteria**: CI green on both databases; a throw-away migration upgrade/downgrade test passes; route-inventory test fails when a dummy unlisted route is added.
**Risks**: Alembic baseline drift between SQLite and Postgres → baseline is generated on Postgres only; SQLite is dev/test convenience.

---

## Phase 1 — Courses, enrollment, authorization (L) · *`architect` (Fable) for design/review*

**Goal**: a teacher signs up, creates a course, shares a code; students join. The permission layer is real.

**Schema (Alembic)**: `users` += `is_platform_admin`, `locale`, `age_band` (nullable); `courses`, `enrollments`, `enrollment_events` (see architecture §3). Old `users.role` stays (old app) but new code ignores it.
**Backend**
- `app/lms/courses/`: create/update/publish/conclude/soft-delete/restore, transfer ownership, regenerate join code. Owner's `teacher/active` enrollment inserted in the same transaction; owner invariants.
- `app/lms/enrollments/`: join by code (single transaction, `FOR UPDATE`, limit, identical failure messages, rate limiting by user and IP), leave, teacher removes student, roster, role change (teacher ↔ assistant), events log.
- `authz.py` completed: role grants, status gates, request-scoped enrollment cache, SQL scopes (`courses_visible_to`, `my_courses`).
- Registration: every sign-up is a student. Teacher access is requested by the user and approved by a platform admin (`users.teacher_status`, `teacher_requests`; endpoints: request, list pending, approve/reject, revoke). Only `approved` users can create courses. Email verification unchanged.
- Endpoints (all under `/api/v1/courses…`), each listed in the permission matrix.
**Frontend**
- "Become a teacher" request form for students.
- **Platform admin area** `/[lang]/admin` (new; the old `(admin)` pages stay until cutover): teacher requests (pending list, approve / reject with reason, revoke), users (search, paginated, teacher status, disable account), courses (search, unlist from catalog, soft-delete/restore), and an audit log of every admin action. Every endpoint checks `is_platform_admin` from the database.
- Route group `/[lang]/courses`: "My courses" (teaching / learning), create-course form (title, languages ⊆ en/ru/ky, default language, enrollment mode: closed/open/code), course shell with role-aware tabs (Home, People, Settings), join-by-code page and dialog, roster management, course settings incl. conclude/delete/restore.
- Navigation no longer depends on a global admin role; the old `(admin)`/`(student)` groups stay untouched until cutover.
**Tests**: matrix tests (action × role × course status); two teachers / three students isolation suite; join concurrency (limit never exceeded with parallel joins); code-guessing rate limit; re-join revives the row and its history; owner cannot be removed; soft-deleted course returns 404 to everyone except owner restore.
**Exit criteria**: scripted flow passes end to end (teacher creates → student joins → teacher removes → student re-joins); security review done; isolation suite green.
**Risks**: authorization gaps → merge gate + review. Teacher approval queue must not be bypassable (check `teacher_status` on the server for every course-creation call).

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

## Phase 3 — Assessments and attempts (L) · *`architect` (Fable) for design/review*

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
**Scale check**: a load test (k6 or Locust) with 6,000 virtual students meets the budgets above before merge; results saved in `docs/phases/PHASE_3.md`. A first load test runs before Phase 3 starts. Both use free resources (a Neon branch + local or free-tier backend); if a meaningful test needs a paid service, record what was tested and ask the owner only for that spending decision (decision D, 2026-10-22).
**Exit criteria**: a 150-question five-section ORT-style quiz imported in Phase 2 is built, published, taken, timed out, resumed and submitted in an automated end-to-end test; the review shows correct answers only after submit.
**Risks**: player refactor regressions → keep the old player in place until cutover and compare behavior with Playwright smoke tests; timer drift handling (client shows server time offset).

---

## Phase 4 — Grading and results (L) · *`architect` (Fable) for design/review*

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

**Status: deployed 2026-10-23 (`main` 6fc3d38). See `docs/phases/PHASE_5.md`. Next: Phase 6 (design first: `docs/phases/PHASE_6_DESIGN.md`, owner review before code).**

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

## Phase 6 — Organizations foundation, course templates (ORT first), sign-up and invite flows, design system, student home (L) · *`architect` (Fable) for design/review*

**Design**: `docs/phases/PHASE_6_DESIGN.md` (second draft after the owner's second-round answers; §10 "Decided" lists them). Architecture: `LMS_ARCHITECTURE.md` §2b, §3. Phase 6 builds only the organization *foundation*; org completion is Phase 9. Released as **6a** (foundation) and **6b** (experience); the H1 hotfix went out alone first.

**Schema (Alembic)**
- `organizations` (id, slug, name, status `active|suspended`, `parent_id` NULL for later departments, `settings` with one key for now: `teachers_can_create_courses` default **false**, timestamps, soft delete). No tree management, no roster import, no other settings in this phase.
- `organization_members` (organization_id, user_id, role `org_admin|teacher`, state, invited_by, timestamps; UNIQUE(organization_id, user_id)).
- `courses.organization_id` and `question_banks.organization_id` NOT NULL (every course and bank belongs to an organization).
- Course templates: `courses.template_key` NULL, `template_version`, `template_settings` JSON, `template_locked`; `organization_template_grants` (organization_id, template_key, granted_by, granted_at, revoked_at). Templates themselves are code (registry), not rows.
- `invitations` (id, token_hash, email, organization_id, role `org_admin|teacher`, course_id NULL for course staff invites, invited_by, expires_at, accepted_at, accepted_user_id). Hashed tokens, single use, expiry.
- `users.teacher_status` and `teacher_requests` stay, used only by independent teachers applying to the platform admin.
- **Migration (decided)**: one organization owned by the owner (platform admin = its first org admin; name/slug from the placeholders `PLATFORM_ORG_NAME`/`PLATFORM_ORG_SLUG`, renameable later) holding both ORT courses and their banks, with the owner's account as course owner (A11) and the demo teacher as a system co-teacher; **one personal organization per approved independent teacher** (the teacher is its org admin; course creation on; A1/A14), every other existing course and bank moves to its owner's personal organization (production: the tester's draft course → the tester's personal org); banks are never shared between independents. ORT template grant for the owner's organization only. Exact steps in the Phase 6 design §4.

**Backend**
- `app/lms/organizations/`: platform admin: create, edit, suspend; assign and remove org admins; list an organization's teachers, courses and usage (counts and storage bytes); grant and remove course templates. Org admin: invite and remove teachers, list courses, create a course and assign its owning teacher (A2), reassign a course's teacher; **inside courses org admins are read-only plus roster management** (A13); full teacher powers only by adding themselves as a teacher (`join-as-teacher`, visible in the roster, audited). Suspended organization: its courses are read-only for staff and hidden from the catalog.
- Authorization resolution extended (`LMS_ARCHITECTURE.md` §3): platform admin → org admin of the course's organization → enrollment role. `can_create_courses` = org member with role teacher and (org setting on or org admin) and not disabled; platform admin always. Routes in the inventory with the new `org_admin` policies.
- Sign-up: every sign-up is a student; the form has no teacher choice; "Student (ORT preparation)" and similar texts become neutral. Teachers arrive through invitations (org admin or platform admin) and land already as org members. The "become a teacher" request remains only for independent teachers; approval creates the teacher's personal organization and its `org_admin` membership.
- Invitations: create (email through the existing Resend/Brevo/SMTP path, en/ky/ru; From display name "{inviter} via {appName}"), accept with an existing account or inside sign-up, expire, revoke; same `user_not_found`-style non-enumeration rules as Phase 1.
- **Course templates** (`app/lms/templates/`): a code registry of template plugins. A template declares: key and version, default course structure and default banks, importer profile, question types and passage options, ready-made assessments with section structure, timing and navigation rules, grading scheme, result view, lock scope. The `ort` template wraps the *existing* ORT code unchanged: `assessments/rules.py` presets, `ort_main`/`ort_subject` presets and `preset_rule_locked`, the ORT CSV and bundle importers, the system ORT schemes, `OrtResultView`, numbered passages, the comparison card. A course without a template is a general course and gets the general versions (plain section names, no ORT datalists, no numbered passages unless chosen, the general result view). A locked template refuses changes to section keys, order, timers, navigation, scheme and result view (locked controls are greyed out with a short note); teachers still edit questions, banks, availability and attempt settings (exact scope: Phase 6 design §5.4). The ORT template is visible only to organizations holding a grant; grants are given by platform admins only. ORT bank screens keep today's layout (A6). A *course template* is not an *exam template*: the latter (owner's constructor idea) is data and comes in 7b/8b (`docs/phases/EXAM_TEMPLATES_DESIGN.md`); 6a only reserves `exam_template_keys` on `CourseTemplate` and exposes `result_view`/`passage_display` as explicit keys so the two nest later.
- Platform name: one i18n key (`common.appName`, placeholder "the platform" per language) replaces "ORT Preparation Platform"; the hard-coded "ОРТ" logo on auth pages becomes a component fed by i18n. Email templates use the same key.

**Frontend**
- **Design system** (from the UX audit, Task D): tokens (colors, type, spacing), shared components (buttons, inputs, tables with search and filters, cards, empty/loading/error states, dialogs), 375 px first, long ky/ru strings fit. Existing pages migrate to it in this phase where cheap; the rest is listed per phase in the UX audit.
- **Student home**: "what should I do next?" (next exam or assignment, due dates, recent results), one main action, small celebrations; nothing else above the fold.
- Four areas as navigation (not new global roles): platform admin (`/[lang]/admin/**`, now with organizations), organization admin (`/[lang]/org/**`), teaching (course manage views), student (home, courses, attempts, grades).
- Sign-up without a teacher choice; invitation accept page; org admin pages (teachers: invite/remove; courses: list, create with owner); platform admin organization pages (create/edit/suspend, org admins, teachers, courses, usage, template grants).
- ORT: teacher upload, bank, exam and result screens keep their **function**; their **look** follows the design system in 6b (ORT review §0.4) together with the fidelity-preserving player improvements from `docs/ORT_PLAYER_IDEAS.md` part 1 (readability, phone layout, accessibility, timer/palette/flag states, autosave feedback, error messages), with before/after screenshots and a baseline update.

**Tests**: org isolation suite (org admin A sees nothing of org B; two personal organizations see nothing of each other; a teacher sees only own org's courses and banks); authorization matrix extended with `org_admin` (read-only inside courses, `join-as-teacher` audited); course creation blocked when the org setting is off and allowed for org admins; template grant (an ungranted teacher gets no ORT template option and a 403 on creating one); locked template rejects structure edits and accepts question edits; invitation expiry, single use, revoke, no enumeration; sign-up API has no teacher path; migration test on a fixture database (every course and bank has an organization; ORT courses in the owner's organization; one personal org per approved teacher); **ORT review** (golden imports incl. the A10 alias fix, e2e, screenshots against approved baselines, scores, walkthrough) and **UX gate**.
**Exit criteria**: the owner's organization holds both ORT courses and only it can create ORT courses; an org admin invites a teacher who logs in and receives a course created for them; a student signs up with a join code and sees a home page with the next action; ORT review done and reported; UX gate screenshots saved.
**Risks**: scope (see Alternatives A4: split 6a/6b); template abstraction leaking into ORT code (rule: wrap, never rewrite; parity gate catches drift); migration of ownership (rehearse on a Neon branch).

## Phase 7 — 7a Assignments and general gradebook (L) · 7b Exam templates I (M) · *`architect` (Fable) for design/review*

### Phase 7a — Assignments and general gradebook (L)

**Schema**: `assignments` (id, course_id, title, description, kind `none|text|file|quiz`, assessment_id NULL UNIQUE, points_possible, due_at, available_from, available_until, category_id, grading_scheme_version_id, published, position, deleted_at); `assignment_submissions` content rows (text body or file asset id, submitted_at, late); **`submissions.assignment_id` replaces `assessment_id`** (one assignment created per existing assessment in the migration; grades and grade events move one-to-one); `assignment_overrides` (assignment_id, enrollment_id, due_at, available_until, extra_time_s, extra_attempts) = per-student accommodations (see Alternatives A5); `assessments.access_code_hash` NULL (quiz access code, checked at attempt start, never in student payloads).
**Backend**: assignment CRUD; the quiz becomes one kind of assignment (an assessment is always reachable through its assignment; ORT `ort_main` gets its assignment in the migration, nothing else changes for ORT); text and file submissions (PDF or image within the R2 limits, private bucket, owner and course staff download only); manual grade entry and teacher feedback with an optional file; simple rubrics (criteria × points, no outcomes); late policy and weighted categories reused from Phase 4; attempt start honors overrides (`extra_time_s` already exists on attempts) and access codes; availability windows generalized to assignments (quiz windows stay on the assessment and are mirrored).
**Frontend**: Assignments tab (teacher list with filters; student list ordered by due date); assignment editor; student submit (text, file) and status; grade entry and feedback; gradebook with one column per assignment; accommodations dialog per student; access code field on quiz settings. Student home shows due assignments.
**Tests**: migration one-to-one (every grade and event reachable through its assignment; totals unchanged); file submission abuse corpus; access code never leaks; overrides respected at attempt start and in due-date logic; rubric totals; ORT review (result view and scores unchanged through the assignment layer); UX gate.
**Exit criteria**: a teacher grades an uploaded homework and an oral exam without a quiz; the ORT gradebook shows exactly the Phase 4 numbers.

### Phase 7b — Exam templates I: data model, versions, import format (M) · *`architect` (Fable) for design/review* · **proposed, owner review pending**

**Design**: `docs/phases/EXAM_TEMPLATES_DESIGN.md` (§3 data model, §5 import format, §7 API, §8 ORT expressibility). An **exam template** is a reusable, versioned exam structure (sections in order with name, question count as min/max, time limit, allowed question types, passage rule and display; navigation free/forward-only; display mode; scoring = a grading scheme version; result view; importer profile; attempt-setting defaults; lock scope), owned by the platform, an organization or a teacher. It is **not** the course template of Phase 6 (code) and ORT never uses one: ORT exams stay on the `preset` path, and `preset`/`exam_template_version_id` are mutually exclusive on an assessment.
**Schema (Alembic)**: `exam_templates` (owner_scope `platform|organization|teacher`, organization_id, owner_user_id, key NULL UNIQUE, title, description, status `draft|published|archived`, locked, current_version_id, draft_spec JSON, draft_rev, timestamps, soft delete); `exam_template_versions` (template_id, version_no, spec JSON validated by `ExamTemplateSpec`, spec_hash, grading_scheme_version_id FK, published_at/by) **immutable**; `assessments` += `exam_template_version_id` NULL FK, `display_mode` (`one_per_page|scrolling`, default one_per_page), `passage_display` NULL, `result_view` NULL, `structure_locked`; `assessment_sections.rules` gains `min_items`. Existing rows keep today's behaviour through the defaults.
**Backend**: `app/lms/exam_templates/` (spec validation reusing `assessments/rules.py::normalize_rules`; drafts with optimistic `draft_rev`; publish = new immutable version; archive; lock/unlock/promote audited; visibility scope `exam_templates_visible_to`); `instantiate(version, parameters)` writes the assessment + sections (+ the Phase 7a assignment) in one transaction and copies `structure_locked`; `assert_not_locked` from 6a extended to the exam template's lock scope; "save this assessment as a template" (`POST .../assessments/{id}/save-as-template`, Alternatives B2); "upgrade to latest version" only for drafts without attempts; the publish snapshot carries `exam_template_version_id`, `display_mode`, `passage_display`, `result_view` so **running exams keep their version** (attempts read only the snapshot); block catalog `GET /exam-templates/blocks` (question types, scheme versions, result views, passage displays, display modes, navigation, importer profiles; the frontend maps must list the same keys, contract-tested). **General import format** for all 7 question types (`content/importers/general_csv.py`, manifest `format: "lms-bundle"`), moved here from Phase 9 (A12): a template version derives its accepted sections, types, columns and counts (`GET .../import-format[?download=csv]` with a header and one example row per section); uploads with `exam_template_version_id`/`assessment_id` are validated against it and may attach the questions to the matching sections. The ORT importer stays byte-for-byte as the `ort` profile. **ORT expressibility dry-run test** (B9): a spec built from the ORT constants instantiates into the same section rows as `create_assessment(preset="ort_main")` and every subject key, in a scratch course, without switching ORT.
**Frontend (minimal in 7b)**: "Create from template" and "Save as template" in the assessment builder and the Phase 7a quiz-assignment dialog; a plain form (no visual constructor yet) for platform/org admins to edit a draft spec and publish it; import-format download; i18n groups `examTemplates`.
**Tests**: spec validation table; instantiate equals hand-built rows; lock matrix; visibility matrix (platform/org/teacher × caller × course org, personal orgs isolated); version immutability; publish leaves created assessments untouched; attempts run after the template is re-published or archived; import-format derivation; general importer rejects wrong section/type/passage; `preset`/template exclusivity; ORT review green with the new columns at defaults and **no ORT fixture change**; UX gate.
**Exit criteria**: an org admin publishes an exam template; a teacher creates a quiz assignment from it, downloads the import header, uploads a matching CSV and publishes; a second template version does not touch the first exam; the ORT expressibility test is green while ORT still runs on the preset path.

## Phase 8 — 8a Course structure: modules, pages, files, announcements, gating (L) · 8b Exam templates II (M–L) · *`architect` (Fable) for design/review*

### Phase 8a — Course structure: modules, pages, files, announcements, gating (L)

**Schema**: `pages`, `course_modules`, `module_prerequisites`, `module_items` (kind `page|file|assignment|url|header`; quizzes enter through their assignment), `item_completion_requirements`, `item_progress`, `module_progress`, `item_requirement_status` (architecture §7); `course_files` (course_id, asset or private file id, folder, title, published); `announcements` (course_id, title, body, published_at, author_id); `courses.home_kind` `modules|page|assignments`.
**Backend**: page CRUD (language variants, sanitize on write), modules/items CRUD with reorder in one transaction, prerequisite validation (earlier module, same course, 422), the 7-step gating evaluator with `rules_version` cache invalidation, fact recording (view / mark done / submit / scored from Phase 7 submissions), "re-apply rules", computed visibility; course files (PDF, private bucket, R2 limits); announcements (teacher post, student list, optional email digest later). Templates may declare a default structure; the ORT template keeps today's layout (assessments list as home) unless the owner decides otherwise.
**Frontend**: Modules view (student: locked/unlocked/progress, "up next" feeding the student home; teacher: outline editor, requirement and prerequisite pickers, publish toggles), page editor/viewer with KaTeX, files area, announcements, course home choice.
**Tests**: gating matrix (all requirement types, `all`/`any`, sequential, `unlock_at` boundary, unpublished/deleted targets), cycle/forward-prerequisite rejection, regrade doesn't relock, re-apply does, concurrent facts, teacher bypass, cache invalidation; ORT review (ORT course home and screens keep their function); UX gate.
**Exit criteria**: a three-module course with a min-score checkpoint gates correctly end to end; an ORT course works as before.

### Phase 8b — Exam templates II: visual constructor, display modes (M–L) · **proposed, owner review pending**

**Design**: `docs/phases/EXAM_TEMPLATES_DESIGN.md` §4, §6, §9. Depends on 7b (data model) and 6b (design system); may run in parallel with 8a.
**Frontend**: the **constructor** (`/[lang]/org/[orgId]/exam-templates/**`, `/[lang]/admin/exam-templates/**`, and a teacher view inside Teaching): sections editor (order, name, min/max count, time limit, allowed types, passage rule and display), navigation and display mode, scoring (scheme version picker with the live preview table from Phase 4), result view, parameters (choice bound to a section key), lock scope, versions list with diff, publish, archive, lock/unlock, promote teacher → organization, import-format download, **live preview with the real player** (a preview attempt on a scratch assessment). Every pick list comes from `GET /exam-templates/blocks`; no key is hard-coded. **Scrolling display mode** in the player (`display_mode = scrolling`: all visible items of the section as a list, current item by viewport, palette and keyboard shortcuts kept, windows of 30 items / one section, autosave unchanged); result-view and passage-display choices on general assessments; ORT player untouched (one-per-page, numbered passages, `OrtResultView`).
**Backend**: nothing structural (7b did it); minor endpoints for version diff and preview-attempt creation.
**Tests**: constructor Playwright flow (design → publish → create exam → take → result); scrolling-mode player tests and baselines for the **general** player; block catalog ⇔ frontend map contract; ORT review (ORT baselines unchanged except approved look updates); UX gate in en/ky/ru.
**Exit criteria**: a teacher designs a two-section exam in the constructor, previews it, publishes a version and gives it as an assignment; an org admin locks it and teachers can no longer change its structure; the ORT exam behaves exactly as before.

## Phase 9 — Organizations completion, enrollment forms, invitations (M)

**Schema**: `question_banks.visibility` `private|organization` (shared org banks), org `settings` grows (bank sharing on/off, catalog defaults), department tree management on `parent_id`, `organization_roster_imports`; `enrollment_forms`, `enrollment_form_fields`, `enrollment_applications`; student invitations reuse `invitations` with `course_id` and role `student`.
**Backend**: shared question banks per organization (read for every org teacher, edit by owner and org admins; copy into a course; personal organizations of independents can never share with each other); org settings page; departments (create, move, org admin scope includes descendants); roster CSV import (students and teachers, dry run, no passwords in files); org usage dashboard; (the general import format moved to Phase 7b; the ORT importer stays the ORT template's profile, unchanged); catalog modes `open | invite_code | form_auto | form_review | closed`, form builder with versioning, application submit/approve/reject/withdraw, purge job (D7), student email invitations with expiry; answers visible only to the course's staff, never logged.
**Frontend**: org settings, departments, shared banks picker in the bank tab, roster import with preview; catalog browse/search, course landing, apply flow, teacher form builder and applications inbox, invite dialog.
**Tests**: cross-org bank isolation (independents in personal organizations never see each other's banks; A1 decided); department scope; roster import dry run and idempotency; PII visibility matrix, purge job, form immutability, approval transactionality, invitation expiry/reuse; ORT review; UX gate.
**Exit criteria**: two teachers of one school share a bank; a student applies through a teacher-made form and is approved; a department admin sees only their department.

## Phase 10 — Practice, analytics, quiz statistics, student tools (M)

- **Practice mode**: self-paced practice assessments (unlimited attempts, immediate feedback) built from a bank by topic/difficulty with `pick` items; ORT practice uses the ORT template's banks without changing the exam.
- **Mistakes notebook** and **progress** pages on `attempt_items` (SQL aggregates); per-course goal (D18).
- **Quiz statistics** (institutional feature): per-item accuracy, point-biserial discrimination, time per item, distractor analysis, score distribution per assessment; teacher view and org admin roll-up; previews excluded; paginated, no whole-bank loads.
- **Course and organization analytics**: completion and gating progress, assignment status, per-course score distribution; org admins see their organization only.
**Tests**: aggregates against fixture attempts, preview exclusion, org and course scoping, N+1 query budgets; ORT review; UX gate.
**Exit criteria**: a teacher sees a correct distribution and hardest-question list; an org admin sees roll-ups for their courses only; a student's notebook matches their attempts.

## Phase 11 — Privacy (observer/parent with consent), hardening, launch (M)

- **Observer (parent) role**: enrollment role `observer` linked to one student by a pairing code the student generates; sees the student's grades, due dates and announcements, never answers of others; gives guardian consent for under-14s (D5). Consent capture at sign-up by age band, `consent_records`, `policy_versions`, data export/delete requests with due dates, anonymized attempts of deleted users (D17), personal-data column registry, legal review of wording and cross-border basis.
- **Security**: full `/security-review`; dependency audit; rate limits everywhere guesses are possible (login, codes, join, invitations, access codes); JWT lifetime/revocation; HttpOnly cookie sessions evaluation; CSP; backups and restore drill; secrets rotation.
- **Performance**: indexes reviewed with `EXPLAIN` on realistic data; full-scale load test at 6,000 concurrent students on production-like infrastructure (owner decides the Render plan); cost per month documented.
- **Operations**: runbooks (deploy, rollback, restore), error tracking, uptime checks, structured logs, cost review.
- **Quality**: Playwright suite for the golden journeys (org admin invites a teacher; teacher builds/publishes; student joins/takes/reviews; ORT parity; enrollment form; parent pairing); final ORT review and UX gate over all student screens.
**Exit criteria**: launch checklist signed off by the owner; restore drill passed; load test within targets.

---

## Cross-cutting test strategy

- **Pyramid**: unit tests for pure logic (grading `apply()`, type scorers, gating evaluator, authz grants) → service tests on a real database (SQLite fast path, Postgres in CI) → API contract tests (serializers, error shapes, permission matrix) → a small Playwright suite for golden journeys.
- **Property tests** (Hypothesis) for ORT scoring parity and gating invariants.
- **Concurrency tests** on Postgres for submit, join limit, and autosave.
- **Security tests as code**: route-inventory, isolation suite (two teachers / three students, and from Phase 6 two organizations), serializer contract tests, upload abuse corpus.
- **ORT review as code and process** (from Phase 6): import fixtures with expected results, the ORT e2e test, Playwright screenshot comparison with approved baselines and tolerance, the scoring property test, the expressibility dry-run (7b); plus the real walkthrough and the look check per phase (§0.4). **UX gate as process**: screenshots + `ux-reviewer` + fixes, saved per phase.

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
| D5 | Minimum age / guardian consent | **Revised 2026-10-24**: observer (parent) accounts with pairing code and guardian consent for under-14s ship in Phase 11 together with privacy (Q9); wording after legal review. |
| D6 | ORT "raw 0 → 0" below the stated 60 minimum | Preserve exactly during parity; then decide and change deliberately with a test update. |
| D7 | Application-answer retention | 30 days after rejection/withdrawal/unenroll. |
| D8 | Server timer grace | 45 seconds (Canvas uses 1–5 minutes). |
| D9 | Editing a published quiz | Allowed; creates a draft; republish bumps the version; in-flight attempts keep the old version; teacher is warned if attempts exist. |
| D10 | Who can create courses | **Revised 2026-10-24** (replaces 2026-10-22; second round applied): teachers are organization members who arrive by invitation from an org admin or the platform admin; independent teachers apply to the platform admin (the only remaining use of `teacher_requests`) and get a **personal organization** (they are its org admin; course creation on). Course creation by teachers is an organization setting, off by default for new school organizations; org admins and platform admins create courses and assign the owner (A2). Org admins are read-only inside courses plus roster management; full teacher powers only by joining the course as a teacher, audited (A13). Course owners add co-teachers and assistants to their own course without approval (Q3). |
| D11 | Which score counts for retakes (ORT) | Highest (teacher-configurable per assessment). |
| D12 | "ORT visible to everyone" | A catalog-listed course students join with one click; no anonymous reading in v1. (2026-10-24: the two ORT courses belong to the owner's organization.) |
| D13 | Re-lock after a regrade | No (Canvas behavior) plus a teacher "re-apply rules" action. |
| D14 | Scheme edits and old results | New version; regrade only on request. |
| D15 | Translations model | Monolingual question variants linked by a translation group (decided in the architecture). |
| D16 | Language variants of a page | One module item, many language variants; "viewed" counts any variant. |
| D17 | Deleted users' attempts | Anonymize and keep for statistics. |
| D18 | Daily planner / target-score widget | Defer the planner; keep a simple per-course goal later (Phase 10). |
| D19 | Course templates (owner, 2026-10-24) | Templates are code-registered plugins; the DB stores only template key, version, settings and lock. ORT is the first template and wraps the existing ORT code unchanged (never rewritten into generic settings). Locked templates refuse structure changes (controls greyed out with a note). Grants are given by the platform admin only, to organizations (A1 decided). ORT functionality and exam behaviour must not change; its look keeps up: ORT review every phase (§0.4). |
| D20 | Platform name (owner, 2026-10-24) | Not decided. One i18n placeholder key per language (`common.appName`) so the final name is a one-line change; no "ORT" in the generic app name or logo. |
| D21 | UX gate (owner, 2026-10-24) | Every phase: screenshots at 375 px and desktop (student screens in en/ky/ru), `ux-reviewer` review against `docs/UX_GUIDELINES.md`, fixes before merge, screenshots saved in `docs/phases/PHASE_N_screens/`. Reviews never wait for the owner. |
| D22 | ORT player improvements (owner, 2026-10-24) | Fidelity-preserving changes (readability, phone layout, accessibility, timer/palette/flag states, loading/autosave feedback, error messages) are done without asking, with before/after screenshots and a baseline update. Anything changing how the exam works (navigation, timing, question layout, scoring) goes only into `docs/ORT_PLAYER_IDEAS.md` for the owner's decision. |
| D23 | ORT review (owner, 2026-10-24 second round) | ORT is one special, fixed template exactly as today (code, CSV/zip import, exam rules, scoring unchanged; owned by the owner; granted only by platform admins; not rebuilt on the constructor now). "Unchanged" = functionality and exam behaviour; design and layout keep up with the platform. Every phase runs the ORT review of §0.4 (look check and visual updates, parity tests + real walkthrough, ux-reviewer, report with before/after screenshots, approved baselines). Whether ORT later moves onto the exam template constructor is a joint decision once the constructor is proven on other exams; `EXAM_TEMPLATES_DESIGN.md` §8 records what that would need. |
| D24 | Exam templates (architect proposal, 2026-10-24; **owner review pending**) | Exam templates are data (`exam_templates` + immutable versions with a validated JSON spec), separate from code course templates; assessments store the template version id and keep it for their lifetime; `preset` and template are mutually exclusive, so ORT never touches the template path. Data model, save-as-template and the general import format with template validation in **7b**; visual constructor and scrolling display mode in **8b**. Alternatives B1–B12 in the design. |

---

## Alternatives (A1–A12 decided 2026-10-24 second round; B1–B12 open)

**Decided by the owner** (kept below for history; the decision column of `docs/phases/PHASE_6_DESIGN.md` §10 is authoritative): A1 personal organizations, grants to organizations only · A2 adopted · A3 approved "after" baselines · A4 6a/6b split · A5 stays for Phase 7a (per enrollment + per-assignment override) · A6 keep today's bank layout · A7 exact lock list, greyed-out controls with a note · A8 adopted · A9 curated set · A10 fix with identical-import proof · A11 owner's account owns ORT · A12 general import format moves to Phase 7b. **Open**: the exam template constructor alternatives **B1–B12** in `docs/phases/EXAM_TEMPLATES_DESIGN.md` §10 (presets vs templates, save-as-template first, one general import format, platform templates without grants, teacher scope, JSON spec, min/max counts, scrolling split, ORT expressibility test, lettered sub-phases, template sharing, ORT exactly as today).

| # | Topic | Owner's version | Alternative | Pros / cons | Recommendation |
|---|---|---|---|---|---|
| A1 | Default organization for independent teachers | One shared default organization; template grants "to organizations or teachers" | A **personal organization per independent teacher**, auto-created on approval (one row, the teacher is its org admin and teacher). Template grants then go to organizations only. | Pro: shared org banks (Phase 9) can never leak between unrelated independents; one grant model (org only) instead of two (org + teacher); independents get the same org admin pages as schools. Con: many small organizations (one per independent), a platform admin list to filter. The shared default org works too if bank sharing is forced off for it, but then "share with my organization" means nothing for independents and the per-teacher grant path must be built and tested as a second permission source. | A1 alternative: personal organizations, grants to organizations only. |
| A2 | "Teachers can create courses" off by default | Org setting, default off | Same, plus: **org admins (and platform admins) create courses and assign the owning teacher**, in Phase 6; the owner's organization and personal organizations (A1) default the setting to on for their single teacher. | Without this an organization with the default setting cannot get a first course. Pro: matches institutional Canvas. Con: one more org admin page in Phase 6 (small). | Adopt; it is written into Phase 6 above as required. |
| A3 | Exam-player screenshot comparison vs allowed player improvements | Screenshot comparison every phase; fidelity-preserving improvements allowed | **Versioned baselines**: the gate compares against `docs/phases/ORT_BASELINE/`; an approved player improvement updates the baseline in the same PR with before/after images; pixel diffs use a tolerance (fonts, KaTeX anti-aliasing) plus DOM/structure assertions (section order, timer, palette, flag, comparison columns). | Pro: the gate catches unintended changes without blocking approved ones; fewer flaky failures. Con: a careless baseline update could hide a regression, so the orchestrator reviews every baseline change. | Adopt as the definition of the parity gate (already written into §0.4). |
| A4 | Phase 6 size | One phase: organizations, templates, invites, design system, student home, UX fixes | **6a** (organizations, templates, invitations, migration, sign-up) then **6b** (design system, student home, UX audit fixes), each with its own gates and deploy. | Pro: 6a ships the risky data model alone and is reviewable; 6b's visual work does not block it; smaller rollbacks. Con: two gates, two UX passes; the student home arrives a little later. | Split into 6a and 6b, same design document. |
| A5 | Accommodations (extra time, extra attempts) | Per student, exam-related phases | **Per enrollment by default** (`enrollment_accommodations`: extra time factor or seconds, extra attempts) with an optional per-assignment override (`assignment_overrides`), applied at attempt start (`extra_time_s` on attempts already exists). | Pro: a student with a documented need gets it on every exam without per-quiz work; the override still allows exceptions. Con: two tables instead of one. | Per enrollment + per-assignment override, in Phase 7. |
| A6 | "Default question banks by ORT section" in the ORT template | Template provides default banks per section | Keep **today's bank layout** (one bank per imported source, section as a question field) as the ORT template default; per-section banks only if the owner asks for it. | Restructuring banks per section would change the ORT bank screens, which rule A forbids. | Keep today's layout. |
| A7 | Lock scope of a locked template | "Courses using it can't change the exam structure" | Define the lock exactly: locked = section keys and order, section timers, navigation rule, question-type rule per section, grading scheme, result view, importer profile; editable = questions and banks, availability window, allowed attempts, access code, accommodations, course title and description. Today's `preset_rule_locked` is the starting point. | Precise lock means precise tests. | Adopt the list; details in the Phase 6 design. |
| A8 | "Four areas" | Platform admin, org admin, teaching, student | Keep the areas as **navigation and layout**, not new global roles: per-course powers stay on the enrollment role; `org_admin` is an organization-membership role; `is_platform_admin` stays a flag. | Pro: no `users.role` column reintroduced (hard rule), no second permission source. | Adopt (written into Phase 6). |
| A9 | Screenshot storage in a public git repository | Save screenshots in `docs/phases/PHASE_N_screens/` | Commit a **curated, compressed set** (WebP or JPEG, changed screens only, three languages for student screens) and keep the full sets as CI artifacts; baselines for the ORT gate are the exception and are always committed. | Pro: the repo stays small. Con: the owner sees only the curated set in git (the full set is downloadable from CI). | Curated committed set + CI artifacts. |
| A10 | Importer subject-key mismatch (`math_subject` vs `advanced_math`, existing bug) | ORT code is not rewritten | Fix the key mapping inside the ORT template in Phase 6 with a parity test showing identical import results and scores. | Pro: a known bug stops shipping in the first template release. Con: touches ORT code, so it needs an explicit owner OK under rule A. | Fix it in Phase 6 with the owner's OK. |
| A11 | ORT course ownership after migration | Demo teacher (disabled) owns the ORT courses | Make the owner's account the owner of both ORT courses (the demo teacher stays as a disabled co-teacher or is removed). | Pro: no disabled owner; the owner's org admin and course owner are the same person. Con: a small change to the seed. | Phase 6 design decides; recommend transferring ownership. |
| A12 | General import format (all 7 question types) | Not placed by the owner | Phase 9 (with shared banks) as written, or earlier in Phase 7 if teachers need bulk import for general courses sooner. | Phase 9 keeps Phase 7 focused on grading. | Phase 9 unless demand appears. |
