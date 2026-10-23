# Implementation Plan (phase by phase)

**Status**: Phases 0–5 done and deployed (2026-10-23). Phases 6–11 rewritten 2026-10-24 to the owner's decisions (`PRODUCT_DECISIONS.md`, "Owner decisions 2026-10-24"): organizations first, ORT as a locked course template, assignments before modules, UX gate every phase. Design: `LMS_ARCHITECTURE.md`. Decisions D1–D22 are at the end; "Alternatives to discuss" (owner decides) closes the file.
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
   - **ORT parity gate (added 2026-10-24, owner rule A, every phase from 6 on)**: the reference ORT CSV and zip bundles import with identical results (same banks, questions, positions, images, warnings); the ORT end-to-end test (join → take `ort_main` ky and ru → results) passes unchanged; screenshot comparison of the exam player (comparison card, numbered passage, timer, palette, flags) and of the ORT result view against the stored baselines, within the agreed tolerance; ORT scores (scaled, percentile, section breakdown, golden certificate) match the parity property test. A deliberate, reviewed player improvement (owner rule D5) updates the baseline in the same PR with before/after screenshots; the gate catches only unintended differences. Baselines live in `docs/phases/ORT_BASELINE/` (see Alternatives A3).
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
| 6 | Organizations foundation, course templates (ORT first), sign-up/invite flows, design system, student home | L | 5 | Schools own courses and teachers; ORT is a locked, admin-granted template; teachers arrive by invitation; one design system; a student home that answers "what next?" |
| 7 | Assignments and general gradebook | L | 6 | Any gradable work (offline, text, file, quiz) in one gradebook; accommodations; quiz access codes |
| 8 | Course structure: modules, pages, files, announcements, gating | L | 7 | Guided course paths with locked/unlocked steps; pages, files, announcements, course home |
| 9 | Organizations completion, enrollment forms, invitations | M | 6 | Shared org banks, org settings and departments, roster import; catalog forms, student email invitations |
| 10 | Practice, analytics, quiz statistics, student tools | M | 7, 8 | Practice by topic, mistakes notebook, course and org analytics, item statistics |
| 11 | Privacy (observer/parent with consent), hardening, launch | M | 6–10 | Parent accounts and consent, data requests, load/security checks, runbooks |

Dependencies: 7 needs 6 (organizations, templates and the design system are in place); 8 needs 7 (module items reference assignments, not raw quizzes); 9 needs only 6 and may run in parallel with 7 and 8; 10 needs 7 and 8; 11 closes. Each phase ships the ORT parity gate and the UX gate (§0.4).

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

**Design**: `docs/phases/PHASE_6_DESIGN.md` (written before any code; owner reviews it). Architecture: `LMS_ARCHITECTURE.md` §2b, §3. Phase 6 builds only the organization *foundation*; org completion is Phase 9.

**Schema (Alembic)**
- `organizations` (id, slug, name, status `active|suspended`, `parent_id` NULL for later departments, `settings` with one key for now: `teachers_can_create_courses` default **false**, timestamps, soft delete). No tree management, no roster import, no other settings in this phase.
- `organization_members` (organization_id, user_id, role `org_admin|teacher`, state, invited_by, timestamps; UNIQUE(organization_id, user_id)).
- `courses.organization_id` and `question_banks.organization_id` NOT NULL (every course and bank belongs to an organization).
- Course templates: `courses.template_key` NULL, `template_version`, `template_settings` JSON, `template_locked`; `organization_template_grants` (organization_id, template_key, granted_by, granted_at, revoked_at). Templates themselves are code (registry), not rows.
- `invitations` (id, token_hash, email, organization_id, role `org_admin|teacher`, course_id NULL for course staff invites, invited_by, expires_at, accepted_at, accepted_user_id). Hashed tokens, single use, expiry.
- `users.teacher_status` and `teacher_requests` stay, used only by independent teachers applying to the platform admin.
- **Migration**: one organization owned by the owner (platform admin = its first org admin) holding both ORT courses, their banks and the demo teacher; one default organization for independent teachers; every other existing course and bank moves to the default organization with its owner as a `teacher` member; approved teachers become members of the default organization. ORT template grant for the owner's organization. Exact steps in the Phase 6 design.

**Backend**
- `app/lms/organizations/`: platform admin: create, edit, suspend; assign and remove org admins; list an organization's teachers, courses and usage (counts and storage bytes); grant and remove course templates. Org admin: invite and remove teachers, list courses, create a course and assign its owning teacher (needed because course creation is off by default; see Alternatives A2). Suspended organization: its courses are read-only for staff and hidden from the catalog.
- Authorization resolution extended (`LMS_ARCHITECTURE.md` §3): platform admin → org admin of the course's organization → enrollment role. `can_create_courses` = org member with role teacher and (org setting on or org admin) and not disabled; platform admin always. Routes in the inventory with the new `org_admin` policies.
- Sign-up: every sign-up is a student; the form has no teacher choice; "Student (ORT preparation)" and similar texts become neutral. Teachers arrive through invitations (org admin or platform admin) and land already as org members. The "become a teacher" request remains only for independent teachers; approval creates membership in the default organization.
- Invitations: create (email through the existing Resend/Brevo/SMTP path, en/ky/ru), accept with an existing account or inside sign-up, expire, revoke; same `user_not_found`-style non-enumeration rules as Phase 1.
- **Course templates** (`app/lms/templates/`): a code registry of template plugins. A template declares: key and version, default course structure and default banks, importer profile, question types and passage options, ready-made assessments with section structure, timing and navigation rules, grading scheme, result view, lock scope. The `ort` template wraps the *existing* ORT code unchanged: `assessments/rules.py` presets, `ort_main`/`ort_subject` presets and `preset_rule_locked`, the ORT CSV and bundle importers, the system ORT schemes, `OrtResultView`, numbered passages, the comparison card. A course without a template is a general course and gets the general versions (plain section names, no ORT datalists, no numbered passages unless chosen, the general result view). A locked template refuses changes to section keys, order, timers, navigation, scheme and result view; teachers still edit questions, banks, availability and attempt settings (exact scope: Alternatives A7). The ORT template is visible only to organizations holding a grant.
- Platform name: one i18n key (`common.appName`, placeholder "the platform" per language) replaces "ORT Preparation Platform"; the hard-coded "ОРТ" logo on auth pages becomes a component fed by i18n. Email templates use the same key.

**Frontend**
- **Design system** (from the UX audit, Task D): tokens (colors, type, spacing), shared components (buttons, inputs, tables with search and filters, cards, empty/loading/error states, dialogs), 375 px first, long ky/ru strings fit. Existing pages migrate to it in this phase where cheap; the rest is listed per phase in the UX audit.
- **Student home**: "what should I do next?" (next exam or assignment, due dates, recent results), one main action, small celebrations; nothing else above the fold.
- Four areas as navigation (not new global roles): platform admin (`/[lang]/admin/**`, now with organizations), organization admin (`/[lang]/org/**`), teaching (course manage views), student (home, courses, attempts, grades).
- Sign-up without a teacher choice; invitation accept page; org admin pages (teachers: invite/remove; courses: list, create with owner); platform admin organization pages (create/edit/suspend, org admins, teachers, courses, usage, template grants).
- ORT: teacher upload, bank, exam and result screens unchanged. Only the fidelity-preserving player improvements from `docs/ORT_PLAYER_IDEAS.md` (readability, phone layout, accessibility, timer/palette/flag states, autosave feedback, error messages) with before/after screenshots and a baseline update.

**Tests**: org isolation suite (org admin A sees nothing of org B; a teacher sees only own org's courses and banks); authorization matrix extended with `org_admin`; course creation blocked when the org setting is off and allowed for org admins; template grant (an ungranted teacher gets no ORT template option and a 403 on creating one); locked template rejects structure edits and accepts question edits; invitation expiry, single use, revoke, no enumeration; sign-up API has no teacher path; migration test on a fixture database (every course and bank has an organization; ORT courses in the owner's organization); **ORT parity gate** (import, e2e, screenshots, scores) and **UX gate**.
**Exit criteria**: the owner's organization holds both ORT courses and only it can create ORT courses; an org admin invites a teacher who logs in and receives a course created for them; a student signs up with a join code and sees a home page with the next action; ORT parity gate green; UX gate screenshots saved.
**Risks**: scope (see Alternatives A4: split 6a/6b); template abstraction leaking into ORT code (rule: wrap, never rewrite; parity gate catches drift); migration of ownership (rehearse on a Neon branch).

## Phase 7 — Assignments and general gradebook (L) · *`architect` (Fable) for design/review*

**Schema**: `assignments` (id, course_id, title, description, kind `none|text|file|quiz`, assessment_id NULL UNIQUE, points_possible, due_at, available_from, available_until, category_id, grading_scheme_version_id, published, position, deleted_at); `assignment_submissions` content rows (text body or file asset id, submitted_at, late); **`submissions.assignment_id` replaces `assessment_id`** (one assignment created per existing assessment in the migration; grades and grade events move one-to-one); `assignment_overrides` (assignment_id, enrollment_id, due_at, available_until, extra_time_s, extra_attempts) = per-student accommodations (see Alternatives A5); `assessments.access_code_hash` NULL (quiz access code, checked at attempt start, never in student payloads).
**Backend**: assignment CRUD; the quiz becomes one kind of assignment (an assessment is always reachable through its assignment; ORT `ort_main` gets its assignment in the migration, nothing else changes for ORT); text and file submissions (PDF or image within the R2 limits, private bucket, owner and course staff download only); manual grade entry and teacher feedback with an optional file; simple rubrics (criteria × points, no outcomes); late policy and weighted categories reused from Phase 4; attempt start honors overrides (`extra_time_s` already exists on attempts) and access codes; availability windows generalized to assignments (quiz windows stay on the assessment and are mirrored).
**Frontend**: Assignments tab (teacher list with filters; student list ordered by due date); assignment editor; student submit (text, file) and status; grade entry and feedback; gradebook with one column per assignment; accommodations dialog per student; access code field on quiz settings. Student home shows due assignments.
**Tests**: migration one-to-one (every grade and event reachable through its assignment; totals unchanged); file submission abuse corpus; access code never leaks; overrides respected at attempt start and in due-date logic; rubric totals; ORT parity gate (result view and scores unchanged through the assignment layer); UX gate.
**Exit criteria**: a teacher grades an uploaded homework and an oral exam without a quiz; the ORT gradebook shows exactly the Phase 4 numbers.

## Phase 8 — Course structure: modules, pages, files, announcements, gating (L) · *`architect` (Fable) for design/review*

**Schema**: `pages`, `course_modules`, `module_prerequisites`, `module_items` (kind `page|file|assignment|url|header`; quizzes enter through their assignment), `item_completion_requirements`, `item_progress`, `module_progress`, `item_requirement_status` (architecture §7); `course_files` (course_id, asset or private file id, folder, title, published); `announcements` (course_id, title, body, published_at, author_id); `courses.home_kind` `modules|page|assignments`.
**Backend**: page CRUD (language variants, sanitize on write), modules/items CRUD with reorder in one transaction, prerequisite validation (earlier module, same course, 422), the 7-step gating evaluator with `rules_version` cache invalidation, fact recording (view / mark done / submit / scored from Phase 7 submissions), "re-apply rules", computed visibility; course files (PDF, private bucket, R2 limits); announcements (teacher post, student list, optional email digest later). Templates may declare a default structure; the ORT template keeps today's layout (assessments list as home) unless the owner decides otherwise.
**Frontend**: Modules view (student: locked/unlocked/progress, "up next" feeding the student home; teacher: outline editor, requirement and prerequisite pickers, publish toggles), page editor/viewer with KaTeX, files area, announcements, course home choice.
**Tests**: gating matrix (all requirement types, `all`/`any`, sequential, `unlock_at` boundary, unpublished/deleted targets), cycle/forward-prerequisite rejection, regrade doesn't relock, re-apply does, concurrent facts, teacher bypass, cache invalidation; ORT parity gate (ORT course home and screens unchanged); UX gate.
**Exit criteria**: a three-module course with a min-score checkpoint gates correctly end to end; an ORT course looks as before.

## Phase 9 — Organizations completion, enrollment forms, invitations (M)

**Schema**: `question_banks.visibility` `private|organization` (shared org banks), org `settings` grows (bank sharing on/off, catalog defaults), department tree management on `parent_id`, `organization_roster_imports`; `enrollment_forms`, `enrollment_form_fields`, `enrollment_applications`; student invitations reuse `invitations` with `course_id` and role `student`.
**Backend**: shared question banks per organization (read for every org teacher, edit by owner and org admins; copy into a course); org settings page; departments (create, move, org admin scope includes descendants); roster CSV import (students and teachers, dry run, no passwords in files); org usage dashboard; general import format for all 7 question types (the ORT importer stays the ORT template's profile, unchanged); catalog modes `open | invite_code | form_auto | form_review | closed`, form builder with versioning, application submit/approve/reject/withdraw, purge job (D7), student email invitations with expiry; answers visible only to the course's staff, never logged.
**Frontend**: org settings, departments, shared banks picker in the bank tab, roster import with preview; catalog browse/search, course landing, apply flow, teacher form builder and applications inbox, invite dialog.
**Tests**: cross-org bank isolation (default-organization independents never see each other's banks; see Alternatives A1); department scope; roster import dry run and idempotency; PII visibility matrix, purge job, form immutability, approval transactionality, invitation expiry/reuse; ORT parity gate; UX gate.
**Exit criteria**: two teachers of one school share a bank; a student applies through a teacher-made form and is approved; a department admin sees only their department.

## Phase 10 — Practice, analytics, quiz statistics, student tools (M)

- **Practice mode**: self-paced practice assessments (unlimited attempts, immediate feedback) built from a bank by topic/difficulty with `pick` items; ORT practice uses the ORT template's banks without changing the exam.
- **Mistakes notebook** and **progress** pages on `attempt_items` (SQL aggregates); per-course goal (D18).
- **Quiz statistics** (institutional feature): per-item accuracy, point-biserial discrimination, time per item, distractor analysis, score distribution per assessment; teacher view and org admin roll-up; previews excluded; paginated, no whole-bank loads.
- **Course and organization analytics**: completion and gating progress, assignment status, per-course score distribution; org admins see their organization only.
**Tests**: aggregates against fixture attempts, preview exclusion, org and course scoping, N+1 query budgets; ORT parity gate; UX gate.
**Exit criteria**: a teacher sees a correct distribution and hardest-question list; an org admin sees roll-ups for their courses only; a student's notebook matches their attempts.

## Phase 11 — Privacy (observer/parent with consent), hardening, launch (M)

- **Observer (parent) role**: enrollment role `observer` linked to one student by a pairing code the student generates; sees the student's grades, due dates and announcements, never answers of others; gives guardian consent for under-14s (D5). Consent capture at sign-up by age band, `consent_records`, `policy_versions`, data export/delete requests with due dates, anonymized attempts of deleted users (D17), personal-data column registry, legal review of wording and cross-border basis.
- **Security**: full `/security-review`; dependency audit; rate limits everywhere guesses are possible (login, codes, join, invitations, access codes); JWT lifetime/revocation; HttpOnly cookie sessions evaluation; CSP; backups and restore drill; secrets rotation.
- **Performance**: indexes reviewed with `EXPLAIN` on realistic data; full-scale load test at 6,000 concurrent students on production-like infrastructure (owner decides the Render plan); cost per month documented.
- **Operations**: runbooks (deploy, rollback, restore), error tracking, uptime checks, structured logs, cost review.
- **Quality**: Playwright suite for the golden journeys (org admin invites a teacher; teacher builds/publishes; student joins/takes/reviews; ORT parity; enrollment form; parent pairing); final ORT parity gate and UX gate over all student screens.
**Exit criteria**: launch checklist signed off by the owner; restore drill passed; load test within targets.

---

## Cross-cutting test strategy

- **Pyramid**: unit tests for pure logic (grading `apply()`, type scorers, gating evaluator, authz grants) → service tests on a real database (SQLite fast path, Postgres in CI) → API contract tests (serializers, error shapes, permission matrix) → a small Playwright suite for golden journeys.
- **Property tests** (Hypothesis) for ORT scoring parity and gating invariants.
- **Concurrency tests** on Postgres for submit, join limit, and autosave.
- **Security tests as code**: route-inventory, isolation suite (two teachers / three students, and from Phase 6 two organizations), serializer contract tests, upload abuse corpus.
- **ORT parity as code** (from Phase 6): import fixtures with expected results, the ORT e2e test, Playwright screenshot comparison with versioned baselines and tolerance, the scoring property test. **UX gate as process**: screenshots + `ux-reviewer` + fixes, saved per phase.

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
| D10 | Who can create courses | **Revised 2026-10-24** (replaces 2026-10-22): teachers are organization members who arrive by invitation from an org admin or the platform admin; independent teachers apply to the platform admin (the only remaining use of `teacher_requests`) and join the default organization. Course creation by teachers is an organization setting, off by default; org admins and platform admins create courses and assign the owner (Alternatives A2). Course owners add co-teachers and assistants to their own course without approval (Q3). |
| D11 | Which score counts for retakes (ORT) | Highest (teacher-configurable per assessment). |
| D12 | "ORT visible to everyone" | A catalog-listed course students join with one click; no anonymous reading in v1. (2026-10-24: the two ORT courses belong to the owner's organization.) |
| D13 | Re-lock after a regrade | No (Canvas behavior) plus a teacher "re-apply rules" action. |
| D14 | Scheme edits and old results | New version; regrade only on request. |
| D15 | Translations model | Monolingual question variants linked by a translation group (decided in the architecture). |
| D16 | Language variants of a page | One module item, many language variants; "viewed" counts any variant. |
| D17 | Deleted users' attempts | Anonymize and keep for statistics. |
| D18 | Daily planner / target-score widget | Defer the planner; keep a simple per-course goal later (Phase 10). |
| D19 | Course templates (owner, 2026-10-24) | Templates are code-registered plugins; the DB stores only template key, version, settings and lock. ORT is the first template and wraps the existing ORT code unchanged (never rewritten into generic settings). Locked templates refuse structure changes. Grants are given by the platform admin only (to organizations; per-teacher grants: Alternatives A1). The ORT experience must not change: parity gate every phase. |
| D20 | Platform name (owner, 2026-10-24) | Not decided. One i18n placeholder key per language (`common.appName`) so the final name is a one-line change; no "ORT" in the generic app name or logo. |
| D21 | UX gate (owner, 2026-10-24) | Every phase: screenshots at 375 px and desktop (student screens in en/ky/ru), `ux-reviewer` review against `docs/UX_GUIDELINES.md`, fixes before merge, screenshots saved in `docs/phases/PHASE_N_screens/`. Reviews never wait for the owner. |
| D22 | ORT player improvements (owner, 2026-10-24) | Fidelity-preserving changes (readability, phone layout, accessibility, timer/palette/flag states, loading/autosave feedback, error messages) are done without asking, with before/after screenshots and a baseline update. Anything changing how the exam works (navigation, timing, question layout, scoring) goes only into `docs/ORT_PLAYER_IDEAS.md` for the owner's decision. |

---

## Alternatives to discuss (owner decides)

The owner's decisions above stand until changed. These are points where the orchestrator or the architect sees a possibly better option. Phase-6 details are kept short here; the Phase 6 design carries the full version.

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
