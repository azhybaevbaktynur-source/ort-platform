# Phase 7a design: assignments and the general gradebook

**Status**: architect draft 2026-10-26 (branch `phase-7a` off `lms` at 158f124). Implements `IMPLEMENTATION_PLAN.md` Phase 7a within the owner's decisions (`PRODUCT_DECISIONS.md`: rule A "ORT must not change", A5 accommodations per enrollment + per-assignment override, A13 org admins read-only inside courses, Q7 submission types none/text/file). Architecture: `LMS_ARCHITECTURE.md` §5–§6. 7b (`EXAM_TEMPLATES_DESIGN.md` §3.2/§3.4) plugs into §3.1 and §4.1 of this document. Names in **bold code** are to be used exactly as written so parallel slices merge cleanly. Anything that would change ORT's behaviour is in §8, not decided here.

---

## 1. Scope and non-goals

**In**: the assignment as the gradable unit (`none | text | file | quiz`); every assessment reachable through exactly one quiz assignment (created by migration `0009` for existing rows, by the builder for new ones); text and file submissions (PDF or image, private bucket, owner and course staff download only, R2 guard); manual grades with feedback (text + optional file) and simple rubrics (criteria × points); the gradebook with one column per assignment; weighted categories and the late policy reused from Phase 4; per-enrollment accommodations and per-assignment overrides (A5) applied at attempt start and in due-date logic; quiz access codes; grade release per assignment; student home "next up" over assignments; Assignments tab, editor, submit page, grading screen, accommodations dialog.

**Out** (later phases): modules, pages, files area, announcements, gating (8a); exam templates and "create quiz from template" (7b; §3.1 leaves the hook); rubrics with learning outcomes, rubric libraries, peer review, group assignments, media/link submissions (Q7), plagiarism, SpeedGrader-style annotation; discussions; analytics (10). ORT: nothing changes except that its exam is listed as an assignment (§6).

---

## 2. Schema and migration `0009_phase7a_assignments`

`down_revision = "0008_phase6_organizations"`. Naming through `op.f(...)` as in 0008; `JSONType = sa.JSON().with_variant(JSONB, "postgresql")`; SQLite changes through `op.batch_alter_table`. Models: **`app/lms/assignments/models.py`** (`Assignment`, `AssignmentSubmission`, `AssignmentRubricCriterion`, `SubmissionRubricScore`, `AssignmentOverride`), **`app/lms/accommodations/models.py`** (`EnrollmentAccommodation`); columns added to `Submission`, `GradeEvent`, `Assessment` live on those models. Register all in `app/lms/models.py` (block `# --- Phase 7a S1 begin/end ---`).

### 2.1 `assignments`

| Column | Type / constraint |
|---|---|
| id | uuid PK. **Quiz assignments always use `assignment_id_for(assessment_id)`** = `uuid5(ASSIGN_NS, f"assignment:assessment:{assessment_id}")`, `ASSIGN_NS = uuid5(NAMESPACE_URL, "https://ort-platform/lms/assignments")` (**`app/lms/assignments/ids.py`**; the migration copies the formula, as 0008 does for organizations). Other kinds: uuid4. |
| course_id | uuid NOT NULL FK courses RESTRICT (organization comes through the course; no `organization_id`) |
| kind | varchar(8) NOT NULL, CHECK IN (`none`,`text`,`file`,`quiz`) |
| assessment_id | uuid NULL FK assessments RESTRICT, **UNIQUE**; CHECK `(kind = 'quiz') = (assessment_id IS NOT NULL)` |
| title | JSON LocalizedText NOT NULL (quiz: mirrored from the assessment, §3.2) |
| description | JSON LocalizedText NULL (instructions; sanitized Markdown as pages/questions) |
| points_possible | numeric(10,2) NULL; CHECK `IS NULL OR BETWEEN 0 AND 10000`. Quiz: mirrored from the published version (NULL until published). `none/text/file`: required, 0 = feedback only (excluded from totals like today's `points_possible <= 0`). |
| due_at, available_from, available_until | timestamptz NULL; CHECK `window_valid` as on assessments |
| category_id | uuid NULL FK grade_categories SET NULL |
| grading_scheme_version_id | uuid NULL FK grading_scheme_versions RESTRICT |
| grade_release | varchar(8) NOT NULL, CHECK IN (`auto`,`manual`); default **`manual` for none/text/file**, mirrored for quiz (P7-3) |
| omit_from_total | bool NOT NULL default false |
| published, published_at | bool NOT NULL default false; timestamptz NULL. Quiz: mirrored = `status='published' AND published_version_id IS NOT NULL` |
| position | int NOT NULL (assignment order inside the course; independent of `assessments.position`, which keeps ordering the builder list) |
| created_by_id, deleted_by_id | varchar(64) NULL FK users SET NULL |
| created_at, updated_at, deleted_at | timestamptz |
| Indexes | `ix_assignments_course_id_deleted_at_position_id`, `ix_assignments_course_id_published_due_at` |

### 2.2 `assignment_submissions` (what the student handed in; one row per hand-in)

| Column | Type / constraint |
|---|---|
| id | uuid PK |
| submission_id | uuid NOT NULL FK submissions RESTRICT (the grade row of this enrollment × assignment, created on first hand-in) |
| assignment_id, enrollment_id, user_id | denormalized NOT NULL FKs RESTRICT (scoped queries without joins) |
| attempt_no | int NOT NULL (1, 2, …); UNIQUE(submission_id, attempt_no) |
| kind | varchar(4) NOT NULL CHECK IN (`text`,`file`) |
| body_text | text NULL (≤ 20,000 chars, enforced in the schema); CHECK `(kind='text') = (body_text IS NOT NULL)` |
| asset_id | uuid NULL FK assets RESTRICT (private asset owned by the student); CHECK `(kind='file') = (asset_id IS NOT NULL)` |
| submitted_at | timestamptz NOT NULL |
| late_seconds | int NOT NULL default 0 (seconds past the **effective** due date + grace, §3.5; 0 = on time) |
| Index | `ix_assignment_submissions_assignment_id_enrollment_id_attempt_no` |

Rows are never updated or deleted (append-only like attempts; a student "replaces" a file by handing in again). `assignments.max_submissions` is not built: hand-ins are allowed while the effective window is open and until the teacher has graded the latest one (P7-4).

### 2.3 `submissions`: `assignment_id` replaces `assessment_id` as the identity

Steps inside `upgrade()` (every step idempotent, same order in the bootstrap §2.9):

1. `ADD COLUMN assignment_id uuid NULL FK assignments RESTRICT`; `feedback_text text NULL`; `feedback_asset_id uuid NULL FK assets SET NULL`; `graded_item_id uuid NULL FK assignment_submissions SET NULL` (which hand-in the current grade belongs to); `graded_by_id varchar(64) NULL FK users SET NULL`; `graded_at timestamptz NULL`.
2. **Backfill assignments**: for every `assessments` row (soft-deleted included, so restores and old grades keep working) insert one `assignments` row with `id = assignment_id_for(assessment.id)`, `kind='quiz'`, mirrored columns per §3.2 (`points_possible` from `assessment_versions.points_possible` of `published_version_id`, `category_id = grade_category_id`, `position = assessments.position`, `deleted_at/deleted_by_id` copied), `created_by_id = created_by_id`. Skip ids that already exist (re-run safety).
3. **Move submissions**: Python loop over distinct `submissions.assessment_id` → `UPDATE submissions SET assignment_id = :aid WHERE assessment_id = :asid AND assignment_id IS NULL` (executemany; N = number of assessments, 1 in production).
4. `ALTER COLUMN assignment_id SET NOT NULL`; `ALTER COLUMN assessment_id DROP NOT NULL`; add `UNIQUE(enrollment_id, assignment_id)` **`uq_submissions_enrollment_assignment_id`**; add CHECK **`quiz_link_valid`**: `kept_attempt_id IS NULL OR assessment_id IS NOT NULL`; index `ix_submissions_assignment_id_state_released_at`.
5. `grade_events`: CHECK `event_valid` gains `manual_grade` (recreated with the same name; PG trigger `trg_grade_events_append_only` untouched: inserts only). Grade events reference `submission_id`, so they move one-to-one with no data step.

**Decision P7-1: keep `assessment_id` (nullable) as a denormalized column**, do not drop it. Reasons: (a) `attempts` reference assessments, and the scored hook's UPSERT conflict target, `_attempt_grades_stale`, `counted_attempts`, `regrade`, `results` all correlate on `S.c.assessment_id`; dropping it would rewrite every ORT grading path, which the parity rule forbids touching without need; (b) the existing `uq_submissions_enrollment_assessment` keeps working (NULLs are distinct on PG and SQLite) and the hook stays at five statements; (c) `downgrade()` is lossless (drop the new column, restore NOT NULL). "Replaces" holds semantically: `assignment_id` is NOT NULL and the unique identity, the API and the gradebook speak in assignments only, and `assessment_id` is a read-only shortcut equal to `assignments.assessment_id` (invariant test `test_submission_assessment_id_matches_assignment`).

### 2.4 `enrollment_accommodations` (A5, per student for the whole course)

| Column | Type / constraint |
|---|---|
| enrollment_id | uuid PK FK enrollments RESTRICT |
| course_id | uuid NOT NULL FK courses RESTRICT (scope) |
| extra_time_percent | int NOT NULL default 0, CHECK 0..300 |
| extra_time_s | int NOT NULL default 0, CHECK 0..86400 |
| extra_attempts | int NOT NULL default 0, CHECK 0..100 |
| note | varchar(500) NULL (staff-only; never in student payloads) |
| set_by_id, created_at, updated_at | FK users SET NULL; timestamps |

### 2.5 `assignment_overrides` (A5, exception for one student on one assignment)

`id` PK; `assignment_id` FK RESTRICT; `enrollment_id` FK RESTRICT; `course_id` (scope); `due_at`, `available_from`, `available_until` timestamptz NULL (CHECK `window_valid`); `extra_time_percent` NULL (0..300), `extra_time_s` NULL (0..86400), `extra_attempts` NULL (0..100); `note` varchar(500) NULL; `set_by_id`; timestamps; **UNIQUE(assignment_id, enrollment_id)**; index `ix_assignment_overrides_enrollment_id`. NULL = "no override for this field" (falls back to the accommodation, then the assignment).

### 2.6 Rubrics and feedback

**`assignment_rubric_criteria`**: `id`, `assignment_id` FK RESTRICT, `position` int, `title` LocalizedText NOT NULL, `description` LocalizedText NULL, `points` numeric(8,2) NOT NULL CHECK 0..1000, `deleted_at`; index `(assignment_id, deleted_at, position)`. At most 30 live criteria per assignment. Sum of criterion points ≠ `points_possible` is a warning (`rubric_total_mismatch`) in the editor, not an error.
**`submission_rubric_scores`**: PK(`submission_id`, `criterion_id`), `points` numeric(8,2) NOT NULL CHECK ≥ 0, `comment` varchar(1000) NULL. Written only by the grade endpoint (§4.3); replaced as a set on every grade write.
Feedback: `submissions.feedback_text` (≤ 10,000 chars) and `feedback_asset_id` (a private asset uploaded by staff through §4.3; PDF or image). Students see feedback only when `released_at` is set.

### 2.7 `assessments.access_code_hash`

`varchar(100) NULL`: bcrypt hash of the normalized code (trimmed, 4–32 chars, printable ASCII) through the existing `app/core/security.py` helpers. Never serialized; staff payloads carry `has_access_code: bool`, student lobby carries `requires_access_code: bool`. Set/clear through `PATCH /assessments/{id}` field `access_code` (string or null; absent = unchanged). Editable under the ORT lock (A7 editable list already names "access code").

### 2.8 Downgrade

Drop `submission_rubric_scores`, `assignment_rubric_criteria`, `assignment_overrides`, `enrollment_accommodations`; drop `assignment_submissions`; on `submissions` drop the six new columns and the new unique/check/index, restore `assessment_id NOT NULL` (refused with a clear error if any row has `assessment_id IS NULL`, i.e. a non-quiz grade exists; that is the only one-way case and is documented in the revision docstring); restore the `grade_events` CHECK (refused if a `manual_grade` row exists); drop `assignments`; drop `assessments.access_code_hash`.

### 2.9 Lifespan bootstrap and the builder

- **`app/lms/assignments/bootstrap.py::ensure_assignments(db) -> BootstrapReport`** runs in `main.py` lifespan after `_ensure_organizations()` and **before** `_seed_ort_courses()` (block `# --- Phase 7a S1 begin/end ---`). Steps 2–3 of §2.3 in ORM/Core form, idempotent, never fatal (same pattern as `ensure_organizations`). SQLite dev/test databases (create_all) get their quiz assignments this way; on PostgreSQL it is a no-op safety net after the migration. Test `test_0009_migration_and_bootstrap_paths_match_on_pg` asserts both produce identical `assignments` and `submissions.assignment_id` rows (as `test_0008_migration_and_bootstrap_paths_match_on_pg`).
- **`assessments/builder.py::create_assessment`** calls **`app.lms.assignments.sync.ensure_quiz_assignment(db, assessment, actor_id)`** before `_commit` (one delimited block); `update_assessment`, `soft_delete_assessment`, `restore_assessment` and `publish.py::publish/unpublish` call **`sync.mirror_from_assessment(db, assessment)`** (one line each, same block markers). Hence `ort/seed.py::ensure_ort_courses` is **not edited** and still produces the ORT exam with its assignment in the same transaction (`test_ort_seed` asserts one quiz assignment per seeded assessment).

### 2.10 Production data steps (rehearsal on a Neon branch before `main`)

Production today (verify on the rehearsal branch, never assume): courses = "ORT (Kyrgyz)" (published, no questions, 0 assessments), "ORT (Russian)" (one `ort_main` assessment, 150 items, `allowed_attempts` 3 from the legacy `max_attempts`, published), the owner's draft course in the platform organization (0 assessments expected). Steps: create Neon branch `rehearsal-<date>-phase7a` → run the backend against it (`alembic upgrade head` through the lifespan) → assert `SELECT count(*) FROM assignments` = `SELECT count(*) FROM assessments` (expected 1), `count(*) FROM submissions WHERE assignment_id IS NULL` = 0, every `assignments.id` for a quiz equals `assignment_id_for(assessment_id)` (script `backend/scripts/check_0009.py`, read-only) → compare `GET /courses/{ort_ru}/gradebook` and `GET /courses/{ort_ru}/grades/mine` (as a tester) before (from `lms`) and after: same cells and totals (§6) → `alembic check` clean. Then `backup-<date>-before-phase7a` branch, merge to `main`, `/health` shows the commit.

---

## 3. Domain rules

### 3.1 Kinds and where grades come from

| kind | Grade source | Student action | `submissions.state` path |
|---|---|---|---|
| `quiz` | kept attempt, exactly today's hook (`grading/submissions.py::on_attempt_scored`, unchanged) | start attempt (existing lobby) | as Phase 4 |
| `text` | teacher-entered points (optionally rubric) | hand in text (resubmit while open and ungraded) | `pending_review` on hand-in → `graded` on grade entry |
| `file` | same | hand in one PDF or image per hand-in | same |
| `none` | same (offline work, oral exam, participation) | nothing | row created by the teacher's grade entry → `graded` |

Creating a quiz assignment (`POST /assignments` with `kind: quiz` and `quiz: {preset?, languages, subject_key?}`) calls `builder.create_assessment` and `ensure_quiz_assignment` in one transaction. **7b hook**: the same body accepts `quiz.exam_template_id / exam_template_version_id / parameters` and routes to `exam_templates.service.instantiate(...)`, which must call `ensure_quiz_assignment` inside its transaction; `preset` and `exam_template_*` are mutually exclusive (422) as `EXAM_TEMPLATES_DESIGN.md` §3.2 says. 7a leaves the branch as a `NotImplemented` 422 `exam_templates_not_available`.

### 3.2 Quiz assignments: single source of truth and the mirror rule

**For `kind = quiz` the assessment row is the truth** for `title`, `description`, `due_at`, `available_from`, `available_until`, `category_id` (= `grade_category_id`), `grading_scheme_version_id`, `grade_release`, `omit_from_total`, `published`/`published_at`, `points_possible` (published version), `deleted_at`. The assignment row **mirrors** them: `sync.mirror_from_assessment` is called by every builder/publisher write (§2.9), and `PATCH /assignments/{id}` on a quiz assignment **delegates** those fields to `builder.update_assessment` (which applies the ORT lock and then mirrors). Only `position` is assignment-owned for every kind. Why: the attempt engine, timing, publish snapshot, ORT seed and the Phase 4 hook read assessment columns; moving truth to the assignment would rewrite ORT paths. Invariant test `test_quiz_assignment_mirror_property`: after every builder operation on a fixture (create, update each field, publish, unpublish, delete, restore) the mirrored columns are equal. For `none/text/file` the assignment is the only store.

### 3.3 Visibility, publishing, deletion

Students see assignments with `published AND deleted_at IS NULL` in a non-draft course (quiz: also `published_version_id IS NOT NULL`, as today). Unpublishing a non-quiz assignment with grades keeps the grades and removes the column from student totals (same as unpublished assessments today). Delete is soft; a quiz assignment's delete/restore delegates to the builder. `assignments.position` is renumbered on `PUT /assignments/order` in one transaction.

### 3.4 Effective dates, attempts and time (accommodations and overrides)

Pure function **`app/lms/accommodations/effective.py::resolve(assignment, assessment, accommodation, override) -> Effective`** with fields `due_at`, `available_from`, `available_until`, `allowed_attempts`, `extra_time_percent`, `extra_time_s`:
- dates: `override.<field>` if not NULL else the assignment (for quiz: the assessment, identical by the mirror);
- `allowed_attempts`: `-1` stays `-1`; else `base + coalesce(override.extra_attempts, accommodation.extra_attempts, 0)` (capped at 200);
- time: `(percent, seconds)` = the override's pair if either is not NULL, else the accommodation's, else `(0, 0)`; **`attempts/timing.py::extra_seconds(snapshot, percent, seconds) -> int`** = `round(total_limit_s * percent / 100) + seconds` (0 when the snapshot has no total limit and percent only), and **`timing.extended_section_limits(snapshot, extra_s) -> dict[pos, limit]`** scales every per-section limit by `(total + extra_s) / total` (floor to whole seconds, remainder on the last section) so the sum of section limits equals the extended total.

Applied in **`engine.start_attempt`** (one block `# --- Phase 7a S4 begin/end ---` replacing the window / attempts-left checks and the `extra_time_s=0` and `timing.attempt_deadline(now, snapshot, 0, …)` arguments): for non-staff, load the accommodation and override in one SELECT (enrollment already loaded), compute `eff`, check `available_from/until` and `allowed_attempts` against `eff`, pass `extra_s` to `attempt_deadline` and write `extra_time_s = extra_s`; section deadlines use `extended_section_limits`. **For assessments with `preset != 'none'` (ORT) `extra_s` is forced to 0 until the owner answers Q1 (§8)**; extra attempts and date overrides do apply to ORT exams (they are within A7's editable scope: `allowed_attempts`, `available_*`). With no accommodation, no override and no code the block computes exactly today's values, so every existing attempt test passes unchanged.

Due-date logic: the Phase 4 hook's statement 1 (`submissions.load_context(db, assessment_id, enrollment_id)`) LEFT JOINs `assignment_overrides` for that enrollment and returns `due_at = coalesce(override.due_at, assessment.due_at)`; still five statements. Writing an override or accommodation that changes `due_at` recomputes **that one submission** immediately (lock → `counted_attempts` → `recompute_submission` with event `regraded`, reason `override_changed`); nothing else goes stale. Students see their own effective dates in every student payload (`due_at` already effective; no mention of "override" in the UI text, only the date).

### 3.5 Hand-ins, late, resubmission

`POST /assignments/{a}/submissions` (student, `assignment.submit`): the assignment is published, kind text/file, `eff.available_from <= now < eff.available_until` (NULL = open), the course is published and the organization active (same gate as `assessment.take`), the latest grade (if any) is not for the latest hand-in → else 409 `submission_closed` / `already_graded`. Transaction: `lock_or_create_submission(..., assignment_id, assessment_id=None, kept_policy='latest')` → insert `assignment_submissions(attempt_no = last + 1, late_seconds = late.late_seconds(now, eff.due_at, course.late_policy))` → `UPDATE submissions SET state='pending_review'` when the row has no grade yet. Late deduction is computed on grade entry from the graded hand-in's `late_seconds` (same `late.late_deduction`). Body cap 64 KiB; rate limit `submission_submit_1h` = 60 per user. Files: `POST /assignments/{a}/submissions/files` (multipart, 1 file) → `files.service.ingest_file` (PDF, 10 MiB) or `ingest_image(visibility='private')` (2 MiB) with `owner = student`, `course_id`; `usage.check_capacity` (507 `storage_full`) and the per-user cap already apply; extra caps `SUBMISSION_FILES_PER_ASSIGNMENT_MAX = 10` hand-ins per student per assignment and rate limit `submission_upload_1h` = 30 (owner question Q2 on the global budget). The returned `asset_id` is then handed in; an asset not owned by the caller or already used by another submission is 422 `asset_not_usable`.

### 3.6 Manual grading

`PUT /assignments/{a}/grades/{enrollment_id}` (staff, `grades.manage`): body `{points: Decimal|null, rubric_scores?: [{criterion_id, points, comment?}], feedback_text?, feedback_asset_id?, version?}`. Rules: the enrollment is an active student of the course (404 otherwise); `points` ≤ `points_possible` (422 `points_out_of_range`); with `rubric_scores`, every live criterion exactly once, each ≤ its points, and `points` = their sum (sent `points` must match, 422 `rubric_sum_mismatch`); `feedback_asset_id` must be a private asset owned by the caller. **`app/lms/assignments/grading.py::grade_manual(...)`**: `lock_or_create_submission` (by enrollment × assignment) → optimistic `version` check (409 `stale_grade`) → write `raw_points`, `points_possible` (assignment's), `late_seconds` and `late_deduction` from the latest hand-in (0 for `none`), `effective_points = coalesce(override_points, raw) − deduction`, scheme values through `grading.registry.apply` (assignment scheme version), `state = 'graded'` (or `excused` stays), `graded_item_id` = latest hand-in, `graded_by_id/graded_at`, rubric score rows replaced, feedback columns; `released_at` as the release rule (§3.7); one `grade_events` row `manual_grade` with old/new `TRACKED` fields plus `rubric_scores` and `feedback` keys. Pure core **`compute_manual_values(sub, assignment_row, course_row, hand_in, now)`** mirrors `submissions.compute_values` and is unit-tested side by side. `points: null` clears the grade (state back to `pending_review` if a hand-in exists, else the row keeps `state='graded'` with NULL points and is ignored by totals; event recorded). Override and excuse (existing routes) work unchanged on these rows (they only touch `override_points` / `state`).

### 3.7 Release and totals

`grade_release` on the assignment: `auto` releases on every grade write (quiz: as today); `manual` needs `POST /assignments/{a}/grades/release` (routes move from `/assessments/{id}/grades/*` to `/assignments/{id}/grades/*`; the old three routes are removed from the inventory and the frontend). Default for non-quiz is `manual` (P7-3: teachers grade over days; releasing together is fairer). `totals.compute_totals` keys by `assignment_id` (duck-typed `.assignment_id` on submissions, `.id/.category_id/.omit_from_total/.points_possible` on assignment rows); the gradebook passes assignment rows. The student course total stays hidden when scales differ (J5).

### 3.8 Access code

Checked in the same `engine.start_attempt` block, after the window check and only for non-staff when `assessment.access_code_hash IS NOT NULL`: missing code → 403 **`access_code_required`**; wrong code → `ratelimit.enforce(user.id, access_code_fail_limit())` (`access_code_fail_10m`, 10) then 403 **`access_code_invalid`**; compare with the bcrypt verifier (constant-time). Resumes of an open attempt never ask again. The code is never logged or echoed; `StartIn.access_code: Optional[str]` (max 64). Preview attempts skip it.

### 3.9 Student home

`home/service.py::_next_up` and `_next_due` read **assignments**: published, not deleted, course published, organization active, `eff` window open (override-aware through a LEFT JOIN on `assignment_overrides` for the caller's enrollment), and either (quiz) today's `_startable` predicate on the joined assessment or (text/file) no `assignment_submissions` row of the caller, or (`none`) never listed. Ordered by effective `due_at` NULLS LAST, then `available_until`, then id. `HomeNextUpOut` gains `assignment_id: uuid`, `kind: str`; `assessment_id` becomes Optional. `latest_results` and `in_progress` keep their shape (quiz) and `latest_results` also lists released manual grades (join `assignments` instead of `assessments`, title from the assignment). Statement budget stays fixed.

---

## 4. API surface

All under `/api/v1`, errors in the `{"error":{code,message,details}}` shape, lists cursor-paginated (`limit` ≤ 50). Policies live in **`app/lms/assignments/policies.py::ASSIGNMENT_POLICIES`** and **`app/lms/accommodations/policies.py::ACCOMMODATION_POLICIES`**, imported by `route_inventory.py` (block `# --- Phase 7a S1 begin/end ---`, S1 creates both files as empty dicts; S2/S4 fill them). New actions in `authz.py` (block `# --- Phase 7a S1 begin/end ---`): **`A.ASSIGNMENT_SUBMIT = "assignment.submit"`** (student only; honours the status and suspension gates like `assessment.take`) and **`A.ACCOMMODATIONS_MANAGE = "accommodations.manage"`** (teacher only; not in `ORG_ADMIN_ACTIONS`, not for assistants).

### 4.1 Assignments

| Method, path | Policy | Notes |
|---|---|---|
| GET `/courses/{course_id}/assignments` | `course:content.read` | staff: `AssignmentStaffSummaryOut` (all, `?deleted=`, `?kind=`, `?published=`, `?category_id=`), order `position`; students and org admins: `AssignmentStudentOut` (published only; students with their own `status`: `not_started\|in_progress\|submitted\|graded\|missing\|excused`, effective dates, `attempts_left`); org admins get the student shape without status (J2) |
| POST `/courses/{course_id}/assignments` | `course:content.manage` | `AssignmentCreateIn {title, description?, kind, points_possible?, due_at?, available_from?, available_until?, category_id?, grading_scheme_version_id?, grade_release?, omit_from_total?, quiz?: QuizCreateIn}`; quiz → builder in the same transaction; 422 `quiz_body_required` / `quiz_body_forbidden`; ORT presets only in a course whose template allows them (6a guard, unchanged) |
| GET `/courses/{course_id}/assignments/{assignment_id}` | `course:content.read` | staff `AssignmentStaffOut` (+ `assessment` brief, rubric, counts: submitted/graded/released/stale); student `AssignmentStudentDetailOut` (+ own hand-ins, grade and feedback when released) |
| PATCH `/courses/{course_id}/assignments/{assignment_id}` | `course:content.manage` | `AssignmentUpdateIn` (same fields as create minus `kind`/`quiz`, plus `published`); quiz: delegates mirrored fields to `builder.update_assessment` (409 `template_locked` passes through); `published` on a quiz → 409 `quiz_publish_via_assessment` |
| DELETE / POST `.../restore` | `course:content.manage` | soft delete; quiz delegates to the builder |
| PUT `/courses/{course_id}/assignments/order` | `course:content.manage` | `{assignment_ids: [...]}` full order, one transaction |
| PUT `/courses/{course_id}/assignments/{assignment_id}/rubric` | `course:content.manage` | full replace `[{id?, title, description?, points}]`; 409 `rubric_locked` once a graded submission has rubric scores (clear grades first) |

### 4.2 Hand-ins and files

| Method, path | Policy | Notes |
|---|---|---|
| GET `/courses/{course_id}/assignments/{assignment_id}/mine` | `course:assignment.submit` | own status, hand-ins (text bodies, file names, late flags), effective dates, grade + feedback if released |
| POST `/courses/{course_id}/assignments/{assignment_id}/submissions` | `course:assignment.submit+ratelimit` | `{body_text}` or `{asset_id}`; 201 `HandInOut`; §3.5 errors |
| POST `/courses/{course_id}/assignments/{assignment_id}/submissions/files` | `course:assignment.submit+ratelimit` | multipart; returns `{asset_id, filename, bytes, mime}`; exempt from `bodycap` like the course files route |
| GET `/courses/{course_id}/submissions/{submission_id}/files/{asset_id}` | `course:attempt.read_own` | row rule: the submission's student, or anyone with `attempt.read_all`; the asset must be a hand-in of that submission or its `feedback_asset_id`; presigned GET (300 s) or streamed as `/assets/{id}/content` does; `Cache-Control: private, no-store` |
| POST `/courses/{course_id}/assignments/{assignment_id}/feedback-files` | `course:grades.manage+ratelimit` | staff upload of a feedback file (same ingest, owner = staff) |

### 4.3 Grades, gradebook

| Method, path | Policy | Notes |
|---|---|---|
| GET `/courses/{course_id}/assignments/{assignment_id}/submissions` | `course:attempt.read_all` | roster-paginated: one row per active student with `cell` (`CellOut`), hand-in count, latest `submitted_at`, late, `graded_item_id != latest` → `resubmitted: true` |
| PUT `/courses/{course_id}/assignments/{assignment_id}/grades/{enrollment_id}` | `course:grades.manage+ratelimit` (`grade_item_limit`) | §3.6; 409 `quiz_grade_via_attempts` for quiz assignments |
| GET `/courses/{course_id}/submissions/{submission_id}` | `course:attempt.read_all` | existing; `SubmissionStaffOut` gains `assignment_id`, `kind`, `hand_ins[]`, `rubric_scores[]`, `feedback_text`, `feedback_asset_id`, `graded_by_name`, `graded_at` |
| PUT `.../submissions/{id}/override`, `.../excuse` | existing | unchanged |
| POST `/courses/{course_id}/assignments/{assignment_id}/grades/release\|unrelease\|regrade` | `course:grades.manage+ratelimit` | moved from `/assessments/{id}/grades/*` (removed); regrade of non-quiz recomputes late/scheme from stored `raw_points` |
| GET `/courses/{course_id}/gradebook?assignment_ids=&cursor=&limit=` | `course:attempt.read_all` | `GradebookPageOut.assignments: [GbAssignmentOut]` (replaces `assessments`; `id` = assignment id, `kind`, `assessment_id?`, same counts/warnings), `rows[].cells` keyed by assignment id |
| GET `/courses/{course_id}/grades/mine` | `course:grades.read_own` | items per assignment (`assignment_id`, `kind`, `assessment_id?`, `submitted_at?`, `late`, `feedback_text` when released); states as today plus `submitted` (handed in, not graded) |

### 4.4 Accommodations, overrides, access code

| Method, path | Policy | Notes |
|---|---|---|
| GET `/courses/{course_id}/accommodations` | `course:accommodations.manage` | roster-paginated, students with their accommodation (or none) |
| PUT / DELETE `/courses/{course_id}/enrollments/{enrollment_id}/accommodations` | `course:accommodations.manage` | `{extra_time_percent, extra_time_s, extra_attempts, note?}`; audited in `enrollment_events` (`accommodation_set` / `accommodation_cleared`, details without the note) |
| GET `/courses/{course_id}/assignments/{assignment_id}/overrides` | `course:accommodations.manage` | list |
| PUT / DELETE `/courses/{course_id}/assignments/{assignment_id}/overrides/{enrollment_id}` | `course:accommodations.manage` | fields of §2.5; writing `due_at` recomputes that submission (§3.4) |
| PATCH `/courses/{course_id}/assessments/{assessment_id}` | existing | `access_code: str \| null` added to `AssessmentUpdateIn`; `AssessmentStaffOut.has_access_code`; `AssessmentLobbyOut.requires_access_code` |
| POST `.../assessments/{assessment_id}/attempts` | existing | `StartIn.access_code?`; 403 `access_code_required` / `access_code_invalid` (rate-limited) |

### 4.5 Authorization matrix (server-side, roles from the DB)

| Action | Owner / teacher | Assistant | Student | Org admin (A13) | Platform admin |
|---|---|---|---|---|---|
| list / read assignments | all, staff shape | all, staff shape | published, own status | published, student shape, no status, no grades | via `/platform/*` only (course read actions as today) |
| create / edit / delete / order / rubric | yes | yes (`content.manage`) | no | no | no |
| hand in, upload hand-in file | no (staff get 403 `assignment.submit`) | no | yes | no | no |
| read hand-ins, grade, feedback, release, override, excuse, regrade | yes | yes (Phase 4 rule) | own, released only | **no** (no `attempt.read_all` / `grades.manage`) | no |
| download hand-in files | yes | yes | own only | no | no |
| accommodations and overrides | **teacher only** | no | sees only effective dates / attempts | no (join-as-teacher first) | no |
| set / clear access code | yes | yes (`content.manage`) | enters it at start | no | no |

Cross-tenant tests: teacher A never sees course B's assignments, submissions, files or accommodations (404), org admin of org A nothing of org B; two students never see each other's hand-ins (`submission_id` of another student → 404 `submission_not_found`).

---

## 5. Frontend

Design system components only (`frontend/src/components/ui/**`), 375 px first, every string in `en.json`/`ky.json`/`ru.json` under new groups **`assignments`**, **`accommodations`** (and additions in `gradebook`, `assessments`, `home`). API client **`frontend/src/lib/lms/assignments.ts`** + **`assignmentTypes.ts`**, **`accommodations.ts`**.

| Screen (route) | Who | Content and states |
|---|---|---|
| **Assignments tab** `/[lang]/courses/[courseId]/assignments` (`CourseTabs`: label `assignments.tab`; for students it replaces the current "Assessments" tab entry, the `/assessments` student page stays reachable by URL) | teacher | `Table` with search, kind filter, published filter, category; columns title, kind badge, due, points, submitted/graded counts, published switch; row menu edit / order / delete; "New assignment" primary button → `AssignmentEditorDialog` (kind radios; quiz shows the existing `CreateAssessmentDialog` fields: preset radios and subject list from `templateUi`) |
| | student | cards ordered by effective due date (`StudentAssignmentCard`: title, kind icon + text, due, status badge, one primary action: "Start" (quiz → existing lobby `/assessments/{id}`), "Hand in", "Open"); empty state "No assignments yet"; ORT course: the one exam card, same Start flow |
| **Assignment editor** `.../assignments/[assignmentId]/edit` | teacher | fields of §2.1; quiz: mirrored fields editable (saved through the assignment PATCH, 409 `template_locked` shows the greyed-out note as today) plus a link "Open exam builder"; rubric editor (rows title/points, add/remove, total vs points warning); overrides list with "Add exception" (`OverrideDialog`: student picker from the roster, dates, extra time, extra attempts, note) |
| **Submit page** `.../assignments/[assignmentId]` | student | instructions (KaTeX), effective due and window, status; text: `Textarea` with character count and "Hand in" primary; file: picker (PDF/JPG/PNG/WebP, size limits shown), progress, "Hand in"; previous hand-ins list (number, time, late badge); after grading: grade, feedback text, feedback file download; states: not open yet / closed / already graded / offline retry; one confirm dialog before handing in |
| **Grading screen** `.../assignments/[assignmentId]/grade` | staff | left: roster list with status filter (`Table` → stacked at 375 px), right/below: `GradePanel` for the chosen student: hand-ins (text rendered, files download), rubric score inputs (sum shown), points input, feedback `Textarea` + file upload, save (version conflict toast), release / unrelease per student or all; keyboard next/previous student |
| **Gradebook** `/[lang]/courses/[courseId]/grades` (existing `StaffGradebook`) | staff | one column per assignment (`gradebookModel.ts` reads `assignments`), kind icon in the header, `ColumnFilterDialog` by kind/category, cell click → `SubmissionPanel` (quiz: attempts as today; others: hand-ins, rubric, feedback); release actions moved to the assignment menu; **ORT course: one column, same numbers, same cells** |
| **Accommodations dialog** (People tab, per student row menu "Accommodations", teacher only) | teacher | `AccommodationDialog`: extra time (% and/or minutes), extra attempts, note; summary badge on the roster row ("+25 % time, +1 attempt"); ORT course: the time fields show the note `accommodations.ortTimePending` (Q1) |
| **Access code** (`SettingsPanel` of the assessment) | staff | `Input` "Access code" with show/hide, "Clear"; `has_access_code` badge in the staff list; lobby: a code field appears when `requires_access_code` (`LobbyView`, below the Start button; error text for `access_code_invalid`) |
| **Student home** (`StudentHome`, `HomeRow`) | student | next-up rows link to the lobby (quiz) or the submit page (text/file); kind icon; results include manual grades |
| **My grades** (`/grades` student view) | student | rows per assignment with kind, submitted/late, feedback link |

UX states on every screen: skeleton, empty, error with retry, no-permission text. Teacher screens shot in ru, student screens in en/ky/ru at 375 and 1440 px (`docs/phases/PHASE_7A_screens/`).

---

## 6. ORT review plan for 7a

Functionality must be identical; the only visible ORT change is that the exam is listed as an assignment (student card; teacher Assignments table with one row) and the access-code field appears in the builder settings (empty for ORT).

| Proof | How |
|---|---|
| Scores unchanged | `tests/lms/test_ort_parity.py` (all), `test_ort_e2e_api.py`, `test_ort_cutover_flow.py` unchanged and green |
| ORT gradebook shows the Phase 4 numbers | **`tests/lms/test_ort_gradebook_golden.py`**: S1 first captures, on `lms` before any 7a code, `GET /gradebook` and `GET /grades/mine` of the ORT e2e fixture (deterministic answers of `test_ort_e2e_api`) into `tests/fixtures/ort_gradebook_golden.json` (cells: `raw_points`, `effective_points`, `display_value`, `label`, `percentile`, `passed`, `breakdown`; totals); after 7a the same flow must produce equal values with the quiz assignment as the only column (keys mapped `assessment_id → assignment_id_for(...)`) |
| Migration one-to-one | **`tests/test_migration_0009.py`**: fixture DB (the 0008 fixture extended with an ORT exam, two students, attempts, submissions, grade events, an override) → upgrade → every submission has `assignment_id = assignment_id_for(assessment_id)`, counts equal, every grade event reachable through its submission's assignment, totals before/after equal; `up_down_up` on SQLite and PG; migration ≡ bootstrap on PG |
| Seed | `test_ort_seed.py`: seeded assessments have exactly one quiz assignment, deterministic id, mirrored fields; running the seed twice adds nothing |
| Engine untouched for ORT | existing attempt suites (`test_attempt_ported.py`, timing, integrity, PG concurrency) unchanged; new test: ORT preset start with an accommodation writes `extra_time_s = 0` (Q1 pending) but respects `extra_attempts` |
| Browser suite | `frontend/e2e/ort.spec.ts` DOM walk unchanged (lobby → exam → result); `ort-visual.spec.ts` against `docs/phases/ORT_BASELINE/`: expected diffs **none** for player, result, review; `teacher-builder-desktop-ru.png` may change by the new access-code row in settings (look update, re-baselined with before/after in the PR); the student course list has no baseline (card markup may change) |
| Walkthrough | CSV + zip upload, build an ORT exam, take it, see the result; plus: the ORT gradebook column, the student card, start with and without a wrong access code on a **general** exam (ORT exams get no code in the walkthrough) |
| Report | `docs/phases/PHASE_7A.md` ORT section: what changed in look, test names, walkthrough date |

---

## 7. Slices, ownership, order, gates

Pattern of Phase 6 (§9 there): one branch per slice (`phase-7a/<slice>`), strict file ownership, delimited blocks `# --- Phase 7a S<n> begin/end ---` in shared files, i18n groups appended per slice, the orchestrator merges and reviews every diff. Decisions P7-1 … P7-5 of this document go into `PRODUCT_DECISIONS.md` when applied.

| Slice | Model | Scope | Owns (exclusive) |
|---|---|---|---|
| **S1** models (first, alone; "models push" merged before S2–S4 start) | opus | §2 tables and columns, migration 0009 (+ downgrade), `ids.py`, `bootstrap.py`, `sync.py` (`ensure_quiz_assignment`, `mirror_from_assessment`) and its builder/publisher hooks, `models.py` registration, `authz.py` actions, `route_inventory.py` import blocks with empty policy dicts, `main.py` lifespan line, golden capture, migration tests, seed test addition | `backend/alembic/versions/0009_phase7a_assignments.py`, `app/lms/assignments/{__init__,models,ids,bootstrap,sync,policies(stub)}.py`, `app/lms/accommodations/{__init__,models,policies(stub)}.py`, blocks in `assessments/builder.py`, `assessments/publish.py`, `grading/models.py`, `app/lms/models.py`, `app/core/authz.py`, `app/core/route_inventory.py`, `app/main.py`, `tests/test_migration_0009.py`, `tests/fixtures/ort_gradebook_golden.json`, `tests/lms/test_ort_gradebook_golden.py`, `tests/lms/test_assignment_sync.py` |
| **S2** assignments API | opus | §4.1, §4.2: service, schemas, scopes, router, hand-ins, file upload/download, rubric CRUD, student status, 7b hook stub, isolation and abuse tests (renamed executable, oversize, SVG, another student's asset) | `app/lms/assignments/{service,schemas,scopes,router,handins,files}.py`, `app/lms/assignments/policies.py` (fills the dict), `app/lms/files/submissions.py`, `app/core/config.py` block (`SUBMISSION_*`), `tests/lms/test_assignments_api.py`, `test_handins.py`, `assignment_support.py` |
| **S3** grading and gradebook | fable (grading hot path) | §3.6, §3.7, §4.3: `grading.py` manual path, gradebook over assignments, `totals.py` key change, serializers, moved release/regrade routes, `SubmissionStaffOut` extension, `grades/mine` per assignment, `load_context` enrollment join (one block) | `app/lms/assignments/grading.py`, `app/lms/grading/{gradebook,gradebook_router,gradebook_policies,router,policies,serializers,totals,regrade,actions}.py`, one block in `grading/submissions.py`, `tests/lms/test_gradebook_api.py` (update), `test_manual_grading.py`, `test_grade_totals.py` (update) |
| **S4** accommodations, overrides, access code, home | opus | §2.4–§2.5 services and routes, `effective.py`, `timing.py` additions, the engine block, `AssessmentUpdateIn.access_code`, lobby flag, `home/service.py` rewrite of `_next_up`/`_next_due`/`_latest_results` | `app/lms/accommodations/{service,schemas,router,effective}.py`, `app/lms/accommodations/policies.py` (fills), block in `attempts/engine.py`, `attempts/timing.py` additions, `attempts/schemas.py` (`StartIn`), block in `assessments/{builder,schemas}.py` for the code, `app/lms/core/ratelimit.py` (`access_code_fail_limit`), `app/lms/home/**`, `tests/lms/test_accommodations.py`, `test_access_code.py`, `test_me_home.py` (update) |
| **S5** frontend | opus (sonnet for i18n/mechanical) | §5 screens, API clients, `gradebookModel.ts`, `CourseTabs`, home links, i18n groups, `tsc` + build | `frontend/src/app/[lang]/courses/[courseId]/assignments/**`, `components/lms/assignments/**`, `components/lms/accommodations/**`, `components/lms/gradebook/**`, `components/lms/home/{StudentHome,HomeRow,StudentCourseHome}.tsx`, `components/lms/assessments/{SettingsPanel,LobbyView,StaffAssessmentList}.tsx`, `components/lms/CourseTabs.tsx`, `lib/lms/{assignments,assignmentTypes,accommodations,grading,gradingTypes,home,homeTypes}.ts`, i18n JSON (own groups + listed keys) |
| **S6** integration | orchestrator + ux-reviewer (fable) + architect security review | full suites, PG parity, rehearsal (§2.10), ORT review (§6), UX gate, `/security-review`, `docs/phases/PHASE_7A.md`, `PRODUCT_DECISIONS.md` (P7-*), memory | docs, `docs/phases/PHASE_7A_screens/**`, baseline updates if any |

**Order**: S1 alone (also captures the golden file before touching code). Then S2, S3, S4 in parallel (they share only S1's models; S3's `load_context` block and S4's engine block are in different files; S2 and S3 both touch `SubmissionStaffOut` → S3 owns `serializers.py`, S2 passes hand-in rows through a function S3 defines: `ser.hand_in_out`). S5 starts from the shapes in §4 once S1 is merged and integrates against S2–S4 as they land. S6 last.

**Gates per slice**: SQLite suite green; route-inventory test green (every new route listed; no stale routes); table-driven action × role × status tests for new routes; cross-tenant tests; serializer contract tests (no `access_code_hash`, no `note`, no other students' data, no unreleased feedback in student payloads); `tsc --noEmit` for S5.
**Gates for the phase (before `lms`, again before `main`)**: SQLite ~2650+ and PG suites green, `alembic upgrade head && alembic check`, `tests/test_migration_0009.py` on SQLite and PG, PG concurrency suites, the ORT review of §6, UX gate (screenshots in `docs/phases/PHASE_7A_screens/`, ux-reviewer findings fixed), `/security-review` (student uploads, file download authorization, access code handling, override scoping), i18n parity, `next build` in an rsync'd copy, rehearsal on a production copy (§2.10), **Neon backup branch before the `main` merge** (models and migration change), `/health` shows the commit after deploy. No owner checkpoint after 7a (the next is after 7b).

---

## 8. Alternatives to discuss (owner)

| # | Question | Options | Recommendation |
|---|---|---|---|
| **Q1** | **Extra time on ORT exams.** Applying an accommodation to an ORT exam changes that student's section timers, i.e. exam timing (rule A). How should extra time apply to a forward-only exam with five section timers? | (a) Not at all: ORT exams never get extra time (the dialog says so). (b) Proportionally per section (each section limit × (1 + percent) + its share of the seconds; total deadline extended by the same amount), only for students with an accommodation; everyone else unchanged. (c) Only on the total attempt deadline (sections unchanged): useless for ORT, where sections carry the limits. | **(b)**: it is how real exam accommodations work and touches only accommodated students; the exam stays identical for everyone else and the player needs no change (deadlines come from the server). Until decided, 7a **stores** the accommodation but applies `extra_time_s = 0` to `preset != 'none'` exams and shows a note in the dialog. Extra attempts and date exceptions apply to ORT already (within A7's editable scope). |
| **Q2** | **Storage budget for student hand-ins.** PDFs up to 10 MB in the private R2 bucket count against the 10 GB free tier (about 1,000 hand-ins of maximum size fill it; the guard then refuses every upload platform-wide at 9.5 GB). | (a) Keep the current limits (10 MB PDF, 2 MB image) plus 10 hand-ins per student per assignment. (b) Lower student files to 5 MB and add a per-course hand-in cap (e.g. 500 MB) shown to teachers. (c) Pay for R2 beyond the free tier when needed. | **(b)** for launch; the caps are config (`SUBMISSION_FILE_MAX_BYTES`, `SUBMISSION_COURSE_MAX_BYTES`) so the owner can change them without code. (c) is a spending decision only the owner can take. 7a is built with (a)'s mechanics and (b)'s defaults unless the owner says otherwise. |
| **Q3** | **Who sets accommodations.** A13 makes org admins read-only inside courses plus roster management; accommodations sit between roster and exam integrity. | (a) Teachers only (assistants and org admins excluded; org admins via "Join as teacher"). (b) Teachers and assistants. (c) Also org admins as part of roster management. | **(a)**: extra time is an integrity-relevant setting; the audited join-as-teacher path exists for org admins. Built as (a); switching to (b)/(c) is one grant line. |

Everything else is decided in this document with its justification: P7-1 keep `submissions.assessment_id` as a denormalized shortcut (§2.3); P7-2 the assessment stays the truth for quiz assignments, the assignment mirrors (§3.2); P7-3 `grade_release` defaults to `manual` for none/text/file (§3.7); P7-4 one file per hand-in, hand-ins append-only, resubmission allowed while open and ungraded (§3.5); P7-5 rubric scores must sum to the points, rubric total ≠ points is a warning (§2.6, §3.6).
