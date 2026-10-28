# LMS Architecture (target design)

**Status**: §3–§6 and §9–§10 are built (Phases 0–5, deployed 2026-10-23). Updated 2026-10-24 to the owner's decisions (`PRODUCT_DECISIONS.md`, "Owner decisions 2026-10-24"): organizations, course templates with ORT as the first locked template, assignments as the gradable unit, observer role, UX gate. Anything marked *Phase 6 design* is specified in `docs/phases/PHASE_6_DESIGN.md`. Supersedes the old Canvas drafts (deleted 2026-10-22).
**Inputs**: `PRODUCT_DECISIONS.md`, `PROJECT_UNDERSTANDING.md`, and four research reports in `docs/research/` that read the real `instructure/canvas-lms` source (commit `1c9f0bb`, 2026-04-30) plus platform research. Canvas facts below were verified in that source by the research agents unless marked *(unverified)*. New Quizzes' backend is not public, so anything about it is unverified.

---

## 1. Principles

1. **Copy Canvas's semantics, not its machinery.** Authority comes from the enrollment (plus organization membership for admin powers, 2026-10-24). Delete is soft. History is never cascaded away. Skip Pseudonyms, Sections, Terms, custom roles, STI, polymorphic links and JSON rule columns. Organizations are a *lightweight* version of Canvas accounts: one table, a nullable `parent_id`, two membership roles.
2. **Everything belongs to a course, and every course and question bank belongs to an organization** (`organization_id` NOT NULL, from Phase 6). Resources carry `course_id`/`owner_id`. One authorization layer decides access. No endpoint decides on its own.
3. **Real foreign keys, no JSON rule blobs, typed nullable FKs with CHECK instead of polymorphic pairs.** JSON only for validated, type-specific payloads.
4. **Numbers are truth, labels are derived.** Scores are stored as points. Scaled scores and labels come from versioned, immutable grading schemes.
5. **Attempts are sacred.** A snapshot at start, a server-owned deadline, one-shot submit, one row per answer, never deleted by cascade.
6. **Server-side everything that matters**: timer, submit lock, answer-key privacy, roles from the database.
7. **ORT is a locked course template, and ORT must not change** (owner rule A, 2026-10-24; replaces "ORT is data, not code"). ORT's scoring schemes are data; its section rules, presets, importers, result view and player behaviour are the *existing code*, registered unchanged as the `ort` template. The database stores only which template a course uses (key, version, settings, lock). ORT logic is never rewritten into generic settings. A parity gate (imports, e2e, screenshots, scores) runs every phase.
8. **Small and cheap**: Postgres, Cloudflare R2, our own policy module, synchronous gating. No queues in v1.
9. **The assignment is the gradable unit** (from Phase 7). A quiz is one kind of assignment; offline, text and file work are the others. Submissions point to assignments.
10. **Mobile-first, one design system, UX gate every phase** (`docs/UX_GUIDELINES.md`): students get one main action per screen; teachers and admins get organized tables; everything works at 375 px and in en/ky/ru.

## 2. Concept map

```
Organization (parent_id NULL) ──< OrganizationMember (org_admin | teacher)
 │   ├──< TemplateGrant (template_key, by platform admin)      CourseTemplate = code plugin (ort, …), not a row
 │   ├──< QuestionBank ──< Question ──< QuestionVersion         (owner teacher; course-scoped or org-shared from Phase 9)
 │   └──< Course (template_key NULL, template_settings, template_locked)
User ──< Enrollment >── Course ──< Module ──< ModuleItem ──> Page | File | Assignment | URL | Header
 │   (teacher|assistant|      │
 │    student|observer)       ├──< Assignment (none|text|file|quiz) ──1 Assessment(Quiz) ──< Section ──< QuizItem ──> QuestionVersion | PassageVersion | Pick(bank)
 │                            │         │                                │
 │                            │         │                                └─ GradingSchemeVersion (immutable)
 │                            │         └──< Submission (one per enrollment+assignment, kept result) ──< GradeEvent
 │                            ├──< Announcement, CourseFile, Page
 │                            ├──< EnrollmentForm ──< Application        Invitation (org role or course role, hashed token)
 │                            └──< GradeCategory (optional weights)
 └──< Attempt ──< AttemptItem
```

*Course = a teacher's live class inside an organization. There are no sections. Reuse is by copy (course copy, bank copy), not by "blueprint".*

## 2b. Organizations and course templates (owner decisions 2026-10-24; schema details: *Phase 6 design*)

**organizations**: `id, slug, name, status active|suspended, parent_id NULL, settings JSON, created_at, deleted_at`. The only setting in Phase 6 is `teachers_can_create_courses` (default **false**). `parent_id` is stored now so departments can come later (Phase 9: tree management, roster CSV import, more settings); Phase 6 builds no tree logic. **organization_members**: `organization_id, user_id, role org_admin|teacher, state, invited_by, timestamps, UNIQUE(organization_id, user_id)`. Students are *not* org members; they belong to courses through enrollments. Suspending an organization makes its courses read-only for staff and hides them from the catalog.

Bootstrap (owner decisions 2026-10-24, second round): one organization owned by the platform owner (placeholder name/slug, renameable) holds both ORT courses and their banks, with the owner's account as course owner; **every independent teacher gets a personal organization** (created on approval; the teacher is its org admin; course creation on); banks are never shared between independents. The platform admin manages organizations (create, edit, suspend, assign and remove org admins, see teachers, courses and usage, grant and remove templates). Org admins invite and remove teachers, list courses, create a course for a teacher and reassign its owner; inside courses they are **read-only plus roster management**, and they gain full teacher powers only by joining a course as a teacher (visible in the roster, audited).

**Exam templates** (`docs/phases/EXAM_TEMPLATES_DESIGN.md`, Phases 7b/8b, approved 2026-10-25) are *data*, not code: `exam_templates` + immutable `exam_template_versions` (validated JSON spec: sections with rules and timers, navigation, display mode, passage display, scheme version, result view, importer profile, defaults, parameters, lock scope), owned by the platform, an organization or a teacher; an assessment created from one stores `exam_template_version_id` for its lifetime and its publish snapshot copies the structural keys, so attempts never look back at the template. A course template may offer exam templates; the ORT course template offers today's presets only, and `preset` and `exam_template_version_id` are mutually exclusive on an assessment.

**Course templates** are *code-registered plugins* (`app/lms/templates/`), not rows. A template declares: key and version; default course structure and default banks; importer profile; question types and passage options; ready-made assessments with section structure, timing and navigation rules; grading scheme; result view; lock scope. The DB stores on `courses` only `template_key, template_version, template_settings, template_locked`. **The `ort` template wraps the existing ORT code unchanged**: `assessments/rules.py` presets and `preset_rule_locked`, the `ort_main`/`ort_subject` preset values, the ORT CSV and bundle importers, the system ORT grading schemes, `OrtResultView`, numbered passages and the comparison card. General courses (no template) get general versions of these (plain sections, general result view, no ORT datalists). New exam types reuse the general pieces and add code only for truly new formats. A locked template refuses changes to the exam structure (section keys and order, timers, navigation, type rules, scheme, result view, importer profile) and leaves questions, banks, availability, attempts, access codes and accommodations editable (Alternatives A7). **Grants**: `organization_template_grants(organization_id, template_key, granted_by, granted_at, revoked_at)`, written only by platform admins; a teacher sees a template only if their organization holds the grant. The `preset` CHECK on `assessments` stays as is; a new template that needs a new preset adds a value by migration (templates are code, so this is a normal release).

## 3. Identity, courses, enrollment, authorization

(Research: `canvas-core-domain.md`.)

**users**: no global `role` (dropped in Phase 5; never reintroduced). `is_platform_admin` (read from DB, never silent), `locale` (`en|ru|ky`), `age_band` (nullable, for consent). **Identity (owner decisions 2026-10-24)**: every sign-up is a student and the sign-up form offers no teacher choice. Teachers come in by **invitation** from an org admin or a platform admin (`invitations`: `token_hash, email, organization_id, role org_admin|teacher, course_id NULL, invited_by, expires_at, accepted_at, accepted_user_id`; hashed, single use, expiring; accept with an existing account or inside sign-up) and become organization members. **Independent teachers** apply to the platform admin: `teacher_status` (`none|pending|approved|revoked`) and `teacher_requests` stay for this case only; approval creates membership in the default organization. **Course creation**: an organization member with role `teacher` may create courses only if the organization setting `teachers_can_create_courses` is on (default off); org admins and platform admins always can and assign the owning teacher. Course owners add co-teachers and assistants to their own course without approval (Q3). Per-course powers still come from the enrollment role. Revoking membership or teacher status blocks new courses but does not delete existing ones. Bootstrap: the first platform admin is set with `make_admin.py` on an existing verified account (never an email in code; the repo is public). All platform admin and org admin actions are written to `admin_audit_log` (org admin rows carry `organization_id`).

**Four areas** (navigation, not global roles): platform admin (`/[lang]/admin/**`), organization admin (`/[lang]/org/**`), teaching (course manage views), student (home, courses, attempts, grades). The same user can appear in several areas; which ones is derived from `is_platform_admin`, organization memberships and enrollments on every request.

**courses**: `id uuid, organization_id (NOT NULL from Phase 6), owner_id, title(LocalizedText), description, languages text[] (⊆ en|ru|ky), default_language, status draft|published|concluded, visibility private|catalog, enrollment_mode closed|open|invite_code|form_auto|form_review, join_code (generated 6–8 chars, partial unique, regenerable), enrollment_limit, starts_at, ends_at, default_grading_scheme_version_id, template_key NULL, template_version, template_settings, template_locked, home_kind (Phase 8), settings, copied_from_id, created_at, updated_at, deleted_at, deleted_by_id`. Soft delete is separate from `status`; restore returns to `draft`.

**enrollments**: `course_id, user_id, role teacher|assistant|student|observer (observer from Phase 11), state requested|invited|active|declined|removed, source, content_language, invite_token_hash, invite_expires_at, activated_at, removed_at, removed_by_id, observed_enrollment_id NULL (observer → the student's enrollment)`. `UNIQUE(course_id,user_id)`, `ON DELETE RESTRICT`. Re-joining revives the same row (old attempts become visible again). *Concluded* is derived from course status, not stored per enrollment. **enrollment_events** (append-only) records every state/role change. Student email invitations (Phase 9) reuse `invitations` with `course_id` and role `student`.

**Invariants**: creating a course inserts the owner's `teacher/active` enrollment in the same transaction; it cannot be removed or downgraded until ownership is transferred. Joining runs in one transaction with `SELECT … FOR UPDATE` on the course to enforce the limit; failure messages are identical to avoid code-guessing; join is rate-limited by user and IP.

**Authorization** (`app/lms/core/deps.py` policies, route inventory): `can(user, action, resource)` / `require(...)`. Resolution with organizations (from Phase 6): resource → course (one hop through `course_id`) → 404 if deleted → **platform admin** (audited `/platform/*` routes and a small whitelist inside course routes) → **org admin** of the course's organization (staff-level read and management of its courses, teachers and banks; never student answer keys beyond what a teacher sees; cached per request) → the user's *active* **enrollment role** → status gates (draft: staff only; concluded: read-only; organization suspended: read-only) → `action ∈ ROLE_GRANTS[role]` + row rules (students read only their own attempts; observers read only their linked student's results; answer keys need `content.read_admin`). Roles and grants are defined in code (no DB overrides). List endpoints use SQL scopes (`courses_visible_to`, `catalog_courses`, `attempts_visible_to`, `organizations_administered_by`), never `can()` in a loop. **Merge gate**: a test walks `app.routes` and fails if a route is not listed in the permission matrix; table-driven action × role × status tests; a two-teachers / three-students isolation suite, extended with two organizations (org admin A sees nothing of org B).

## 4. Content library

(Research: `canvas-assessments.md`, `platform-concerns.md`.)

```
question_banks(id, organization_id, owner_id, course_id NULL, assessment_id NULL (Phase 7c: quiz bank),
               visibility private|organization (Phase 9), title, deleted_at)
assets(id, owner_id, sha256, storage_key, mime, bytes, UNIQUE(owner_id, sha256), deleted_at)   -- images/files in R2
passages(id, bank_id, current_version_id, deleted_at)
passage_versions(id, passage_id, version_no, language, title, body, created_at)               -- immutable
questions(id, bank_id, passage_id NULL, translation_group_id NULL, type, topic, difficulty, tags,
          position NULL, source_ref NULL, current_version_id, deleted_at,
          UNIQUE(owner_id, source_ref))
question_versions(id, question_id, version_no, language, type, schema_version, stem, data JSON,
                  explanation, default_points, created_at, created_by)                          -- immutable
```

- **Versioning replaces Canvas's copy-and-sync.** Every edit inserts a new version; quizzes and attempts reference *version ids*. Nothing is copied, nothing goes stale, and history is exact.
- **Languages (resolved conflict between two reports)**: a *question is monolingual* (`language` per version), with an optional `translation_group_id` linking variants. ORT ky and ru exams are different item sets, not translations; statistics and grading are per variant; editing the Russian text never rewrites Kyrgyz history. Short metadata (titles, descriptions, form labels) uses a validated `LocalizedText` JSON `{en?,ru?,ky?}` with the course default required and a read fallback (requested → default → first). A quiz item points to a translation group *or* a single question; the attempt records the exact variant id.
- **Quiz banks and authoring inside the quiz (Phase 7c, owner decisions 7c-1…7c-9)**: questions can be written directly in the quiz editor. There is still **one store**: such a question is a normal `bank_questions` row in the quiz's own **quiz bank** (`question_banks.assessment_id` set, one live quiz bank per assessment, created on first use, soft-deleted with its quiz). Shared banks (`assessment_id IS NULL`) are reused by link. Quiz banks are listed in the Bank tab under "Quiz banks" and are **never shared directly**; a question reaches a shared bank only by "move/copy to shared bank" (Phase 9 org sharing applies to shared banks only).
- **Edit-scope rule (7c-2, 7c-5)**: when a question edited inside a quiz is also used by other assessments, the teacher chooses once: **all** (new version of the linked question; every quiz using it picks it up at its next publish) or **this** (copy into this quiz's bank and repoint this item). `all` requires edit rights on the source bank; otherwise only `this` is offered. Published versions and attempts never change (snapshots); the dialog says so. A **type change** on a question used in another assessment or in any published version always takes the `this` path (new question in this quiz only).
- **Draft vs version (7c-4)**: typing in a quiz card autosaves a **draft** (per item, optimistic `draft_rev`, not visible outside the editor, never in snapshots). A `question_versions` row is created only when the card is closed or "Done" is clicked, where the scope rule is applied once. No version per autosave; versions stay immutable.
- **Answer key** lives in `data`, refers to stable choice ids, and is never serialized to students. Each type defines `student_view()` built from an allowlist (the Canvas `censor` pattern).
- **Text**: sanitized Markdown + raw LaTeX (rendered by KaTeX as today), or an allowlisted HTML subset sanitized on write (`nh3`). No `equation_images`. Inline images are `assets` ids.
- **Question types v1** (registry: Pydantic data model, response model, `student_view`, `score`): `single_choice`, `multiple_answers` (all-or-nothing or partial), `true_false`, `comparison` (ORT math_1; its 4 labels are app i18n, not stored), `numeric` (exact±margin or range), `short_text` (normalized, incl. Cyrillic look-alikes), `essay` (manual → `needs_review`). Phase 10: matching, fill-in-the-blank, ordering (they then appear in the 7c editor's type dropdown and the 7b general import format). Later: file_upload. Skipped: calculated, hot-spot, categorization.
- **Imports**: the ORT CSV and bundle importers (`content/importers/`) are the **ORT template's importer profile** and do not change (same files, same screens, same results; the parity gate checks this every phase). One bank per source per course, `source_ref` unique per bank, document order preserved as `position`, images through `assets` with sha256 dedupe. A general import format for all question types (the `general` profile) came in Phase 7b (moved from Phase 9, A12); the 7c "paste questions as text" (later) uses the same format. Section rules (math_1 = comparison only) live on the quiz section (`assessment_sections.rules`), enforced at import, item add and publish.
- **Shared banks (Phase 9)**: `visibility = organization` makes a bank readable by every teacher of the organization (edit by owner and org admins, copy into a course). Independent teachers must never see each other's banks (Alternatives A1).

## 5. Assessments and attempts

```
assessments(id, course_id, owner_id, title, description, languages, status draft|published, published_version_id,
            time_limit_s, allowed_attempts (-1 = unlimited), score_policy highest|latest|first|average,
            shuffle_items, shuffle_choices, navigation free|section_forward_only,
            results_policy never|after_submit|after_close, show_correct_answers,
            available_from, available_until, grading_scheme_version_id, points_possible, category_id,
            preset none|ort_main|ort_subject (provided by the course template), access_code_hash NULL (Phase 7), deleted_at)
assessment_sections(id, assessment_id, position, key NULL, title, time_limit_s NULL, rules JSON)
assessment_items(id, assessment_id, section_id, position, kind question|passage|pick,
                 question_id|translation_group_id NULL, passage_id NULL, points,
                 pick_bank_id NULL, pick_count NULL, pick_filter JSON NULL)
assessment_versions(id, assessment_id, version_no, snapshot JSON, published_at)
```

Sections are optional for general quizzes (7c-6): a new quiz has one hidden default section; when a second section is added the existing items visibly become "Section 1". ORT and template-created exams keep their explicit sections and locks. Publishing resolves every item to its current version id and writes an immutable `snapshot` (Canvas `generate_quiz_data`, but with ids not blobs). Students see only a published version; editing makes a draft and republishing bumps the version. A published quiz with attempts keeps serving the old version to in-flight attempts. (Edit-after-publish rule: decision D9.) From Phase 7 every assessment is reached through its **assignment** (kind `quiz`, `assessment_id` UNIQUE); the quiz tables themselves do not change. **Institutional exam features**: availability windows exist today; quiz **access codes** (hashed, checked at attempt start, never in student payloads) and **per-student accommodations** (extra time, extra attempts; `attempts.extra_time_s` already exists; stored per enrollment with a per-assignment override, Alternatives A5) come in Phase 7; **quiz statistics** in Phase 10.

```
attempts(id, assessment_id, assessment_version_id, enrollment_id, attempt_no, language, is_preview,
         status in_progress|submitted|needs_review|graded|void, started_at, deadline_at, extra_time_s,
         current_section_pos, submitted_at, submit_reason manual|timeout|sweep, raw_score, points_possible, result JSON,
         UNIQUE(assessment_id, enrollment_id, attempt_no);
         partial UNIQUE(assessment_id, enrollment_id) WHERE status='in_progress')
attempt_sections(attempt_id, section_pos, started_at, deadline_at, closed_at)
attempt_items(id, attempt_id, position, section_pos, question_version_id, points, choice_order JSON,
              response JSON, flagged, answered_at, score, correctness, manual_score, feedback)
```

**Integrity (fixes today's holes at the root)**
- *Snapshot at start*: all `attempt_items` rows (resolved picks, shuffle permutations, points) are created in one transaction; later edits never affect the attempt.
- *Server deadline*: `deadline_at = min(started + limit + extra, available_until)` plus per-section deadlines. Autosave is `UPDATE attempt_items … WHERE attempt.status='in_progress' AND now() <= LEAST(deadlines) + grace` (grace 30–60 s, D8).
- *One-shot submit*: `UPDATE attempts SET status='submitted' WHERE id=:id AND status='in_progress' RETURNING …`. Exactly one caller wins and only that caller grades. Expiry is handled lazily on any read/write, plus a periodic sweep for abandoned attempts.
- *Section navigation*: closing a section sets `closed_at`; its items reject writes (server-side forward-only).
- *Row per answer*: autosave is a single-row UPDATE (no read-modify-write race between tabs); per-item statistics are SQL (replaces the fake discrimination index); regrade and manual grading work per item.
- *No cascade-deletes* of attempts anywhere (`ON DELETE RESTRICT`); parents are soft-deleted and filtered.

## 6. Grading

(Research: `canvas-modules-grading.md`.) Canvas has no ORT-style curve; its grading standard is only a table of percentage cutoffs. Ours is a pluggable, versioned scheme.

```
grading_schemes(id, owner_user_id NULL, title, type points|percent|bands|pass_fail|piecewise_curve|lookup_table, deleted_at)
grading_scheme_versions(id, scheme_id, version, scale_min, scale_max, pass_threshold_percent,
                        percentile_mean, percentile_sd, rounding, created_at)       -- immutable once referenced
grading_scheme_bands / _curve_segments / _table_rows / _thresholds                   -- per-type child rows
assignments(id, course_id, title, description, kind none|text|file|quiz, assessment_id NULL UNIQUE, points_possible,
            due_at, available_from, available_until, category_id, grading_scheme_version_id, published, position, deleted_at)   -- Phase 7
assignment_submissions(id, submission_id, body_text NULL, file_asset_id NULL, submitted_at, late)                             -- Phase 7
assignment_overrides(assignment_id, enrollment_id, due_at, available_until, extra_time_s, extra_attempts)                     -- Phase 7
submissions(id, enrollment_id, assignment_id, UNIQUE(enrollment_id, assignment_id), state, kept_attempt_id, kept_policy_snapshot,
            raw_points, points_possible, late_deduction, override_points, scheme_version_id,
            display_value, label, percentile, released_at, version)
            -- today: assessment_id NOT NULL; Phase 7 creates one assignment per assessment and moves the FK one-to-one
grade_events(id, submission_id, actor_id, field, old, new, reason, at)               -- append-only
grade_categories(course_id, title, weight, position, deleted_at)  [optional]
course_grades(enrollment_id PK, current_percent, final_percent, display_value, label, computed_at)
```

`effective_points = coalesce(override_points, raw_points) − late_deduction`. One pure function `apply(version, raw, possible) → (display_value, label, percentile, passed, thresholds)` per type, in a registry, unit-tested. **The assignment is the gradable unit** (Phase 7): kind `quiz` takes `raw_points` from the kept attempt as today; `none` (offline, oral, participation) and `text`/`file` take a teacher-entered score, optionally through a simple rubric (criteria × points), with feedback and an optional feedback file. The gradebook shows one column per assignment; weighted categories and the late policy stay as built. ORT grades migrate one-to-one and keep the ORT result view through the template.

**ORT as data**: main = `piecewise_curve` v1 (scale 60–245, mean 150, SD 30; segments ratio [0,.5]→[60,150] exponent 1.05 and [.5,1]→[150,245] exponent 0.95; threshold `golden_certificate` = 219); subject = same shape 60/105/150, SD 20. Today's `test_scoring` numbers are reproduced exactly as the parity gate, including the "raw 0 → 0" quirk, *unless* the owner decides to fix it (D6). When the official CEATM tables are available, add a `lookup_table` version; no code change. Editing a scheme creates a new version; old results keep theirs until the teacher regrades (recommended: on request only). Recompute triggers: attempt submitted, override, scheme version swap, points change, kept-policy change; each writes `grade_events` and re-evaluates gating for those enrollments.

## 7. Modules and gating

```
course_modules(id, course_id, title, position, published, unlock_at, sequential, completion_mode all|any, rules_version, deleted_at)
module_prerequisites(module_id, prerequisite_module_id)       -- must point to an earlier module of the same course (422 otherwise)
module_items(id, module_id, position, indent, title_override, published, kind page|file|assignment|url|header,
             page_id|file_id|assignment_id|url (exactly one by CHECK), deleted_at)      -- quizzes enter through their assignment
item_completion_requirements(item_id PK, type view|mark_done|submit|min_score|min_percent, threshold)
item_progress(enrollment_id, item_id, event viewed|marked_done|submitted|scored, score_percent, submission_id, created_at)  -- append-only facts
module_progress(enrollment_id, module_id, state locked|unlocked|started|completed, evaluated_rules_version, evaluated_at, version)  -- derived cache
item_requirement_status(enrollment_id, item_id, met, best_score_percent, met_at)                                                   -- derived cache
pages(id, course_id, translation_group_id, language, title, body, published, deleted_at)
course_files(id, course_id, asset_id|file_id, folder, title, published, deleted_at)                                                -- Phase 8
announcements(id, course_id, author_id, title, body, published_at, deleted_at)                                                     -- Phase 8
```

Phase 8 (after assignments, Phase 7). A course template may declare a default module structure; the ORT template keeps today's layout (assessments list as home, `courses.home_kind`).

Visibility is computed (item ∧ module ∧ target published and none deleted), not synced (removes Canvas's `ContentTag.update_for` bug class). **Gating algorithm** (synchronous, small courses): (1) unpublished/deleted → locked, teachers bypass; (2) return cached row if rules version, facts and `unlock_at` are unchanged; (3) open iff `now ≥ unlock_at` and all prerequisites `completed` (recursion goes strictly backwards, memoized); (4) evaluate each visible item's requirement from facts, or from the *released* kept score for `min_*`; (5) state completed/started/unlocked; (6) in sequential modules items after the first unmet requirement are locked; (7) persist, and mark dependents stale for this enrollment. Teacher edits bump `rules_version` (lazy invalidation, no batch job). **Policy**: like Canvas, an unlocked module stays unlocked after a later regrade; a teacher action "re-apply rules" clears the cache.

## 8. Enrollment, invitations, catalog, privacy

- **Modes**: `open`, `invite_code`, `form_auto`, `form_review`, `closed` (`open` and `invite_code` built; forms in Phase 9). Public catalog lists `visibility=catalog` published courses of active organizations. Students always self-enroll (join code or catalog); staff and org roles come only by invitation (§3).
- **Invitations** (one table, §3): org admin and teacher invitations in Phase 6; course staff invitations by email in Phase 6 (replaces the `user_not_found` add-staff path only as an addition, the direct add stays); student invitations and roster import in Phase 9.
- **Forms**: `enrollment_forms(course_id, version, status)` immutable once answered; `enrollment_form_fields(key, type, label LocalizedText, help, options, required, position, pii_category)`; types short/long text, single/multi choice, number, date, email, phone; no files; no special-category data. `enrollment_applications(course_id, user_id, form_id, status, answers JSON, submitted_at, decided_by, decided_at, purge_after)`; approval creates the enrollment. Answers visible only to that course's teachers, never logged or exported, purged 30–90 days after rejection/withdrawal/unenroll (D7).
- **Observer (parent) role, Phase 11, with consent** (Q9): enrollment role `observer` linked to one student's enrollment by a **pairing code** the student generates (short-lived, single use). Observers read the linked student's grades, due dates and announcements; never other students, never answer keys, never attempt content beyond released results. Guardian consent for under-14s is recorded through the observer link.
- **Privacy (schema now, features in Phase 11; not legal advice)**: `age_band`, append-only `consent_records` (purpose, policy version, proof, given_by observer or self), `policy_versions`, `data_requests` (export/delete/objection with due dates), and one registry of columns holding personal data. Kyrgyzstan's Digital Code (in force 2026-02-08; per ICNL's secondary summary: under-14 need a guardian's consent, 14+ may consent, consent per purpose, answer objections in 7 working days, cross-border transfer needs a basis). A lawyer must confirm before launch to minors (D5).

## 9. Files and images

Cloudflare R2 (verified 2026-10-21: $0.015/GB-month, 10 GB free, zero egress; Neon bytea costs $0.35/GB-month). Keep `BaseStorageService`, add `R2StorageService` (boto3) and a `files`/`assets` table with sha256 dedupe and soft delete. Uploads are validated by content (not extension), size-capped, EXIF-stripped, re-encoded to WebP (Pillow); no SVG. Public content images via a CDN custom domain (requires DNS on Cloudflare, D2/D3); private files via short presigned GET after a permission check (Canvas pattern). Replaces the ephemeral `/uploads` disk.

## 10. Platform

- **Database**: wipe Neon (testers only) and adopt **Alembic** from a reviewed baseline on empty Postgres, then delete the runtime `ALTER` helpers. Naming convention, batch mode for SQLite dev, CI runs `alembic upgrade head`, `alembic check`, pytest-alembic on Postgres 18 (matches Neon); migrations run as a pre-deploy step, not at import.
- **Remove the in-memory Firestore** entirely (all reads and writes), including the sample-question seeding and `firebase.py`; tests stop depending on `mock_firestore_db.reset()`.
- **API**: stay on `/api/v1`; cursor pagination in the response body; consistent error shape.
- **Ops**: stop `print()`-ing payloads; structured logs without PII; Render paid plan for pre-deploy migrations and no spin-down (D4); confirm Vercel Hobby's non-commercial clause fits.
- **Frontend**: route groups `/[lang]/courses/...` (student view), teacher views inside the course (`/[lang]/courses/[id]/manage/...`), `/[lang]/org/**` (organization admin, Phase 6), `/[lang]/admin/**` (platform admin). Role is not a route group; the same user can teach one course and study another. UI strings in `en.json`, `ky.json`, `ru.json` with a CI key-parity check. **Platform name**: one placeholder key (`common.appName`) per language until the owner chooses a neutral name; no "ORT" in the generic name, logo or email templates (ORT appears only inside ORT courses). **Design system** (Phase 6, `docs/UX_GUIDELINES.md`): tokens and shared components, 375 px first, empty/loading/error states, layouts sized for ky/ru text; every phase passes the UX gate.

## 11. What we deliberately skip (and why)

Canvas's full account tree and account-level settings beyond `teachers_can_create_courses` (we have one `organizations` table with `parent_id`; departments and more settings only in Phase 9), Pseudonyms, Sections, Terms, custom roles/overrides, Blueprint sync, cross-listing, SpeedGrader (manual grading is a per-assignment score, simple rubric and feedback), discussions (moderation and minors; announcements only, Q8), LTI/external tools, inbox, calculated/hot-spot questions, IP filters/lockdown browser, quiz event log, bank/quiz copy-and-sync (7c's "change only in this quiz" is a one-time copy with no sync), media and link submission types (Q7). No longer skipped: organizations (Phase 6/9), observers (Phase 11), organization bank sharing (Phase 9), assignments and rubrics (Phase 7). Each remaining item can be added later without changing the core tables above.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Scope creep toward "all of Canvas" | The skip list above; each phase has an exit test and a stop point. |
| ORT regression (hard rule: ORT must not change) | Parity gate every phase: identical CSV/zip import results, ORT e2e, exam-player and result-view screenshot comparison against versioned baselines with tolerance, scoring property test. ORT code is wrapped by the template, never rewritten. |
| Template abstraction leaking into ORT code | The `ort` template only registers existing modules; any edit to ORT modules needs the parity gate and, for behaviour changes, the owner's decision (`ORT_PLAYER_IDEAS.md`). |
| Cross-organization leaks | Organization isolation suite; `organization_id` on every course and bank; org admin scope in SQL scopes. |
| Authorization mistakes leak data (today's #1 problem) | One `can()`, SQL scopes, route-inventory merge gate, two-teacher isolation suite. |
| Versioned content complicates queries | Always join through `current_version_id` via a single repository module; indexes on version ids. |
| Large rewrite stalls | Phases deliver a usable product slice each; old ORT keeps working until the parity cutover (Phase 5). |
| Legal exposure with minors | Consent schema now; decide minimum age (D5) and get legal review before public launch. |
| Cost | R2/Neon free tiers cover a modeled 5k images/500 students; Render paid plan is the one certain cost. |
