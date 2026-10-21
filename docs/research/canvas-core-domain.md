# Canvas core domain: courses, enrollments, roles, soft delete, copy

**Source read**: `instructure/canvas-lms`, shallow clone of commit `1c9f0bb` (2026-04-30). I only read the code; I did not run it. "Verified" means I read the code at the path given. Anything I did not read is marked *(unverified)*.
**Scope**: Course, Enrollment, self-enrollment, invitations, Role/RoleOverride/policies, soft delete and history, course copy. Modules and grading are covered in `canvas-modules-grading.md`.

---

## 1. What Canvas actually does

### 1.1 Course (`app/models/course.rb`)
- **Columns** (from `db/migrate/20101210192618_init_canvas_db.rb`, `create_table :courses`): `name`, `course_code`, `account_id`, `root_account_id`, `enrollment_term_id`, `workflow_state`, `uuid`, `start_at`, `conclude_at`, `restrict_enrollments_to_course_dates`, `is_public`, `indexed`, `open_enrollment`, `self_enrollment`, `self_enrollment_code` (a **unique partial index** `WHERE self_enrollment_code IS NOT NULL`), `self_enrollment_limit`, `locale` (one locale per course), `settings` (serialized), `template`, `deleted_at`, `archived_at`, and others.
- **There is no owner column.** Teacher rights come only from a `TeacherEnrollment` row. When a course is created, `CoursesController#create` sets `workflow_state = "claimed"` and enrolls the creator only if `enroll_me` is true (`courses_controller.rb` ~L992, L1026). `Course#claim_with_teacher` does the same for the `created` state.
- **Workflow** (`workflow do`, L1898): `created`, `claimed`, `available`, `completed`, `deleted`. Events: `claim`, `offer` (publish), `complete` (conclude), `unconclude`, `delete`, and `undelete`, which goes to **`claimed`** (unpublished), not back to the state the course had before. `api_state` reports `created`/`claimed` as `"unpublished"`. `published?` is `available? || completed?`.
- **Two kinds of "concluded"**: a hard conclude is `workflow_state = completed`. A soft conclude (`soft_concluded?`, L2389) means the course or term end date has passed. `concluded?` is either one.
- **Delete is soft**: `alias_method :destroy_permanently!, :destroy`. Then `destroy` sets `deleted_at` and `process_event(:delete)` and saves (L1945). It returns `false` for template courses. `archive!` sets `deleted` plus `archived_at`. The single-course `destroy` does **not** touch enrollments. Only the bulk `Course.destroy_batch` marks enrollments `deleted`. Enrollments of a deleted course still lose all power, because `active_enrollment_allows` returns false when `deleted?`.
- **The default section always exists**: `Course#default_section` (L3064) finds or creates a `course_sections` row with `default_section: true`, retrying on a unique-constraint race. `enroll_user` does `section ||= default_section`. An enrollment cannot exist without a section (`enrollments.course_section_id NOT NULL`).
- **Catalog**: `SearchController#all_courses` lists courses with `indexed: true` and `available`. Anonymous read uses `unenrolled_user_can_read?`.

### 1.2 Enrollment (`app/models/enrollment.rb`)
- **Types**: single-table inheritance on `type`: `StudentEnrollment`, `TeacherEnrollment`, `TaEnrollment`, `DesignerEnrollment`, `ObserverEnrollment`, and also `StudentViewEnrollment` (the teacher's "fake student" used for preview). Every enrollment also has a **`role_id` (NOT NULL)**. `type` is the base role and `role_id` can point to a custom role built on that base.
- **Columns**: `user_id`, `course_id`, `course_section_id`, `type`, `role_id`, `workflow_state`, `uuid` (invitation token), `associated_user_id`, `start_at`/`end_at`, `completed_at`, `self_enrolled`, `archived_at`, and others.
- **Uniqueness**: a unique partial index on `(user_id, type, role_id, course_section_id)` where `associated_user_id IS NULL`. So one user can hold **several roles in one course**, but only once per section.
- **Workflow** (L811): `invited`, `creation_pending`, `active`, `completed`, `rejected`, `deleted`, `inactive`. This is **not a linear chain**. The events are `invited → reject|complete`, `creation_pending → invite`, `active → reject|complete`, `rejected → unreject → invited`. The states `deleted` and `inactive` are set directly by `destroy`, `deactivate` and `restore`. `inactive` is commented as a "hard" state ("tuition not paid").
- **Methods**: `conclude` (→ `completed` + `completed_at`), `unconclude`, `deactivate`, `reactivate`, `accept(force:)` (`invited → active`), and `destroy` (soft: `deleted`, also marks `scores` deleted and recomputes grades). `restore` sets the state back to `active`.
- **`EnrollmentState`** (`enrollment_state.rb`) is a cache with one row per enrollment. It holds the *date-based* effective state (`pending_active`, `pending_invited`, `active`, `completed`, …), which is computed from enrollment, section, course and term dates, with `state_is_current` and `state_valid_until`. It exists because dates can come from four levels.
- **`Course#enroll_user`** (L2896) is the single path that creates enrollments. The default state is `invited` if the course is published, else `creation_pending`. Admin types (teacher, TA, designer) are always at least `invited`. It **reuses an existing row** for the same user, type and role (in the section, or anywhere in the course) and revives a `deleted`, `completed` or `rejected` row instead of inserting a new one. So history in the enrollment row itself is overwritten. An enrollment of an admin type also calls `claim` on a `created` course.

### 1.3 Self-enrollment and join codes
- **The code is generated, not chosen by the teacher**: `set_self_enrollment_code` (L1633) makes 6 characters from the unambiguous alphabet `ABCDEFGHJKLMNPRTWXY346789` (about 244M codes), with 10 tries to avoid collisions. It is created only when `self_enrollment_enabled?`, which also needs the account setting `settings[:self_enrollment]` to be `"any"` or `"manually_created"` (`Account#self_enrollment_allowed?`). That setting is off by default. A legacy long code, `MD5("#{uuid}_for_#{id}")`, is still accepted. On a course copy or reset the code is cleared (L4340).
- **The `/enroll/:self_enrollment_code` flow** (`config/routes.rb` L1011 → `SelfEnrollmentsController#new`): it finds the course with `Account#self_enrollment_course_for(code)` and renders a page. **That page does not enroll anyone.** The enrollment happens when the user is saved, either at sign-up or through `POST .../enrollments` with `enrollment[self_enrollment_code]` (`EnrollmentsApiController#create_self_enrollment`, L785). The steps:
  - `User` validates `self_enrollment_code` (`user.rb` L538). It rejects the code if it is invalid, if the course is `full` (`self_enrollment_limit_met?`), if the course is `concluded` for students, or if the user is `already_enrolled`.
  - `User#self_enroll_if_necessary` then calls `Course#self_enroll_student`, which runs `enroll_student(self_enrolled: true)` and then `accept(force: true)`. The result is an **active** `StudentEnrollment`.
  - Blueprint (master) courses refuse self-enrollment.
  - If the default section is concluded, another open section is chosen.
- **Invitations**: a teacher enrolls a user by email. The user can be `pre_registered` and the enrollment starts `invited` with a `uuid`. `Enrollment.course_user_state(course, uuid)` gives the invitee read access through `session[:enrollment_uuid]` before they accept. `CoursesController#enrollment_invitation` handles accept and reject.

### 1.4 Roles and permissions
- **`Role`** (`role.rb`): columns `name`, `base_role_type`, `account_id`, `root_account_id`, `workflow_state` (`active|inactive|built_in|deleted`), `deleted_at`. `ENROLLMENT_TYPES` = the 5 course types; `ACCOUNT_TYPES` = `AccountAdmin`, `AccountMembership`. Custom roles belong to an **account**.
- **`RoleOverride`** (`role_override.rb`): columns `permission`, `enabled`, `locked`, `applies_to_self`, `applies_to_descendants`, `role_id`, `context` (polymorphic, **account only**). So permission customization is per account and per role, inherited down the account chain (`account_chain`) and heavily cached. A course or teacher cannot override permissions.
- **Permission registry** (`config/initializers/permissions_registry.rb`): about 160 permissions. Each has `available_to` and `true_for` (the defaults per base role), and some have `applies_to_concluded` and `account_only`. Example: `manage_courses_delete` is `available_to` Admin, Membership, Teacher and Designer, but `true_for` only `AccountAdmin`. Course delete by teachers is therefore **off by default** and has to be enabled per account.
- **The policy DSL** (`gems/adheres_to_policy`): `set_policy do given { |user, session| … }; can :right … end`. `grants_right?(user, session, :right)` evaluates the `given` blocks that grant that right, caches the result per user and object, and can return justifications. Controllers call `authorized_action(@context, @current_user, rights)` (`application_controller.rb` L1331), which uses `grants_any_right?` and renders 401 on failure.
- **How a teacher is limited to their own courses** (`Course` `set_policy`, L2101): every registry permission is granted when `active_enrollment_allows(user, permission) || account_membership_allows(user, permission)`. `active_enrollment_allows` (L2316) loads **this user's enrollments in this course** that are active or pending by date. In an unpublished course only teacher, TA, designer and student-view enrollments count. It then asks `Enrollment#has_permission_to?`, which is `RoleOverride.enabled_for?(course, action, role_id)`. Teacher scope is therefore **a property of the enrollment row**. There is no global "teacher" flag.
- **Further `given` blocks**:
  - Active admin-type enrollment → `read_as_admin`, `manage`, `update`, `view_unpublished_items`, `use_student_view`.
  - Active student in an `available` course → `participate_as_student`, `read_grades`.
  - **Completed** enrollments → read-only access (students keep `read`, `read_grades`; teachers keep `read_as_admin` but lose `manage`).
  - Plus the account-admin blocks.
- **Who can create courses**: `User#create_courses_right` (`user.rb` L4007) returns `:admin` with the account permission `manage_courses_add`, `:teacher` if the root setting `teachers_can_create_courses` is on (default `false`), and similar settings for students and users with no enrollments.

### 1.5 Soft delete and history
- **Convention**: `workflow_state` with a `deleted` value, plus `alias_method :destroy_permanently!, :destroy`. `lib/canvas/soft_deletable.rb` (`Canvas::SoftDeletable`, included by 54 models) adds the `active|deleted` workflow, an `active` scope, a soft `destroy`, `destroy_permanently!`, and `undestroy`. Assignments use `published|unpublished|deleted` and `restore` goes back to `published` if there are student submissions, otherwise `unpublished` (`abstract_assignment.rb` L1715).
- **Assignment delete** (`abstract_assignment.rb` L1665): sets `deleted`, removes module tags (`ContentTag.delete_for`), soft-deletes the linked quiz or discussion, and deletes conditional-release rules. **It does not delete `Submission` rows.** Whether those rows get marked deleted afterwards was *(unverified)*.
- **Submissions follow enrollment**: `lib/submission_lifecycle_manager.rb` (L258-L295) bulk-sets `submissions.workflow_state = 'deleted'` for students whose enrollment was deleted or rejected, or who are no longer assigned. Prior (completed) students are kept. On re-enrollment the upsert uses `COALESCE(NULLIF(workflow_state,'deleted'), inferred_state)`, so **soft-deleted submissions come back to life**. Grades and history are never hard-deleted by these flows.
- **Versioning and audit**: `Submission` is `simply_versioned`. `app/models/auditors/course.rb` records course events (created, updated, concluded, deleted, restored, published, copied, reset). There is a separate `grade_change` auditor.
- **Conclude ≠ delete**: concluding freezes participation (the `participate_as_student` grant needs `available?`) but keeps read access for prior students and teachers.

### 1.6 Course copy / import
- **`ContentMigration`** (`content_migration.rb`): `context` (polymorphic Course, Account, Group or User), `user`, `source_course`, `migration_type`, `migration_settings` (serialized YAML), attachments. Workflow: `created → queued → (pre_processing/pre_processed) → exporting → exported → importing → imported | failed`. The job runs in the background.
- **Course copy** is the plugin `course_copy_importer` (`lib/canvas/plugins/default_plugins.rb` L188, worker `CourseCopyWorker`). `Canvas::Migration::Validators::CourseCopyValidator` requires `source.grants_right?(user, :read_as_admin)` and `:read`. The controller requires `manage_course_content_add` on the target.
- **Identity across copies**: every imported object gets `migration_id = "i" + MD5(asset_string)` (`CC::CCHelper.create_key`). Importers (`app/models/importers/*_importer.rb`) **upsert by `(context, migration_id)`**, so copying the same source again updates instead of duplicating. Copies can shift or remove dates (`set_date_shift_options`) and can copy only selected items (`migration_ids_to_import`).
- **Blueprint courses** are a separate system, `MasterCourses::MasterTemplate`, which keeps one course in sync with associated courses *(only seen through references in `create_self_enrollment`; I did not read it)*.

### 1.7 Things we can drop
- **Account**: tenant tree; owns settings, roles, overrides, terms and SIS.
- **Pseudonym**: the login credential (`unique_id`, password, `account`, workflow `active|suspended|deleted`), separate from `User` (workflow `pre_registered|pending_approval|creation_pending|registered|deleted`). Its purpose is to let one person have several logins or SSO identities across accounts.
- **EnrollmentTerm**, **CourseSection** (workflow `active|deleted`), **EnrollmentState**.

None of these are needed for teacher-owned courses with no schools and no sections.

---

## 2. Corrections to the draft documents

### `CANVAS_INTEGRATION_SPEC.md`
1. **§3.1 "`claimed` (teacher assigned)"**: `claimed` means unpublished. Undelete also lands there. Created courses usually start as `claimed`.
2. **§3.1 / §7.1 code examples (`"OLYMP-2027"`, `"OLYMP10"`)**: Canvas **generates** a 6-character code from a restricted alphabet. Teachers cannot choose it. It also only exists when the account allows self-enrollment, which is off by default.
3. **§3.3 lifecycle `invited → active → completed → inactive → rejected → deleted`**: this is wrong. The states are a set, with `creation_pending`. `rejected` is only reachable from `invited` or `active`. `deleted` and `inactive` are set directly. Re-enrollment revives the old row.
4. **§3.3 "navigates to `/enroll/:code` … creates a StudentEnrollment … redirects"**: the route only renders a sign-up or confirm page. The enrollment is created when the user is saved, or by `POST enrollments` with `self_enrollment_code`. It validates full, concluded and already enrolled. The final state is `active` because `accept(force: true)` is called.
5. **§3.3 "binding a User to a CourseSection and Course"** with STI only: this leaves out `role_id`, which is NOT NULL and is how custom roles work, and the unique key per user, type, role and section.
6. **§8 SQLAlchemy blueprint**:
   - `Enrollment.user_id` has no FK. In Canvas it is a real FK.
   - There is no `role_id` and no uniqueness constraint.
   - `Course.course_code` is NOT NULL. In Canvas it is optional.
   - `self_enrollment_code unique=True` should be a **partial** unique index.
   - Nothing says that a default section has to be created automatically.
7. **§3.2 "`crosslist_course_id`"**: there is no such column. Cross-listing uses `nonxlist_course_id` (seen in `default_section`).
8. The spec has **no** information on roles, permissions or authorization. That is the most important part for us: an enrollment-scoped policy, `RoleOverride` per account, and teacher course-delete off by default.

### `CANVAS_EXPLAINER_FOR_FOUNDER.md`
1. **"A Course … does not have a specific calendar or group of students attached to it directly"**: this is false. Every enrollment has `course_id`. Courses have `start_at`/`conclude_at`. Every course has at least an auto-created default section.
2. **"each section has its own … teacher, and gradebook"**: the gradebook is per course and can only be *filtered* by section. A teacher is limited to a section only through `limit_privileges_to_course_section`.
3. **Calling the course a "Blueprint"**: in Canvas, "Blueprint" is a specific feature (`MasterCourses`) that syncs content into child courses, and those courses cannot be self-enrolled.
4. **"Account controls … teacher permissions"**: this is correct (RoleOverride context is only an account). But it means Canvas teachers cannot tune permissions per course. Course creation by teachers is also off by default (`teachers_can_create_courses`), which is the opposite of our "a sign-up is a teacher".

---

## 3. Recommendation for our product

Principle: copy Canvas's *semantics* (authority comes from the enrollment, soft delete with a `deleted` state, history is never cascaded away, re-enroll restores data). Skip its *machinery* (STI, account chain, overrides, date-state cache, sections).

### 3.1 Tables (Postgres; SQLAlchemy 2 `Mapped[...]`; UUID PKs; `timestamptz`)

**`users`** (existing): drop the global `role` and replace it with `is_platform_admin boolean not null default false`, used only for support and moderation and always read from the DB. Add `locale` (`en|ru|ky`). Add `birth_year` or `is_minor` nullable, to prepare for consent.

**`courses`**
| column | notes |
|---|---|
| `id` uuid PK | |
| `owner_id` FK users, NOT NULL | accountable creator. Canvas has no owner column; we add one so we can block removing the last teacher and so ownership can be transferred. |
| `title`, `description` | |
| `languages` text[] NOT NULL, `default_language` | check that `default_language = ANY(languages)` and that each value is in `('en','ru','ky')` |
| `status` text | `draft | published | concluded`, with a CHECK constraint |
| `visibility` text | `private | catalog` (`public` for anonymous read can come later) |
| `enrollment_mode` text | `closed | code | open | approval` |
| `join_code` text NULL | 6–8 characters from the Canvas alphabet; partial unique index `WHERE join_code IS NOT NULL`; teacher can regenerate it |
| `enrollment_limit` int NULL | |
| `starts_at`, `ends_at` NULL | informational, plus a "soft conclude" when `ends_at` has passed |
| `grading_scheme` jsonb / FK | see the grading report |
| `settings` jsonb | |
| `copied_from_id` FK courses NULL | |
| `created_at`, `updated_at`, `deleted_at`, `deleted_by_id` | soft delete is a separate column from `status`, so restoring brings back the previous status. Canvas always restores to unpublished; we can restore to `draft` to be safe. |

**`enrollments`**
| column | notes |
|---|---|
| `id` uuid PK, `course_id` FK, `user_id` FK | `ON DELETE RESTRICT` on both |
| `role` text | `teacher | assistant | student` (`observer` reserved for parents/consent) |
| `state` text | `requested | invited | active | completed | declined | removed` |
| `source` text | `owner | code | catalog | invite | form` |
| `invited_by_id`, `invite_token_hash`, `invite_expires_at` | invitations, hashed like the reset token |
| `activated_at`, `completed_at`, `removed_at`, `removed_by_id` | |
| `created_at`, `updated_at` | |
| UNIQUE `(course_id, user_id)` | one role per user per course. This is simpler than Canvas, and re-enrolling revives the row the same way `enroll_user` does. |
| index `(user_id, state)` | for "my courses" |

**`enrollment_events`** (append-only): `enrollment_id`, `from_state`, `to_state`, `from_role`, `to_role`, `actor_id`, `reason`, `at`. Canvas overwrites the enrollment row. Our "history kept" requirement needs this log. A general `audit_events(entity_type, entity_id, action, actor_id, diff jsonb, at)` could cover courses as well (the equivalent of `Auditors::Course`).

**Content tables** (modules, assessments, questions): each has `deleted_at`/`deleted_by_id` and a `status` where needed. **Attempts and submissions never cascade**: replace the current `cascade="all, delete-orphan"` on `ExamSet.attempts` with `ON DELETE RESTRICT`, and filter deleted parents in queries. `QuestionSource.external_id` and `exam_bundle_<source_id>` must be made unique **per course**, e.g. `UNIQUE(course_id, external_id)`.

### 3.2 State rules
- **Course**: `draft → published → concluded → published` (unconclude). Delete sets `deleted_at` from any status; restore clears it and sets `status = draft`. Students can see only `published` courses (and `concluded` ones read-only). Students cannot attempt in `concluded`.
- **Enrollment**:
  - Joining by code or catalog in `open` mode creates `active`. `approval` mode creates `requested`, and the teacher approves (`active`) or declines (`declined`). An invite creates `invited`, and the student accepts (`active`) or declines.
  - Teacher removal sets `removed` and keeps attempts. Concluding the course sets enrollments to `completed` (or compute this from course status and keep the enrollment `active`; computing is simpler, so I recommend it).
  - Re-joining after `removed` or `declined` revives the same row to `active`, adds an event, and the old attempts become visible again (the Canvas `COALESCE(NULLIF('deleted'))` behavior).
- **Join** (all in one transaction, `SELECT … FOR UPDATE` on the course to enforce the limit): look up the course by `upper(trim(code))` → check it is not deleted, is `published`, `enrollment_mode` is `code|open`, it is not concluded, and the limit is not reached → upsert the enrollment. Rate-limit by user and IP. The same error message for every failure gives an attacker no hint.
- **Owner invariants**: on course create, insert the `owner_id` and a `teacher`/`active` enrollment in the same transaction. The owner's enrollment cannot be removed or downgraded until ownership is transferred.

### 3.3 Authorization: a single `can(user, action, resource)`
```
# app/core/authz.py
ROLE_GRANTS = {            # code-defined, like permissions_registry true_for; no DB overrides
  "teacher":   {...all course actions..., "course.delete", "course.transfer"*, "enrollment.manage"},
  "assistant": {"course.read_admin", "content.edit", "attempt.grade", "roster.read"},
  "student":   {"course.read", "content.read_published", "attempt.create", "attempt.read_own"},
}                          # *transfer/delete additionally require user.id == course.owner_id
def can(user, action, resource, *, db) -> bool
def require(user, action, resource, *, db) -> None   # raises 403/404
```
1. Resolve `resource → course` (every content row has `course_id`, so this is one hop). Do not use polymorphic context.
2. Load the course (404 if `deleted_at` is set, unless the action is `course.restore` and the user is the owner).
3. Load the user's enrollment in that course once per request (cache it in `request.state`). Use it only if `state == 'active'`. Canvas makes the same check in `active_enrollment_allows`.
4. Status gates, the equivalent of Canvas's `given` blocks: `draft` → only teacher and assistant; `concluded` → read-only for everyone, except the teacher can unconclude.
5. `action in ROLE_GRANTS[enrollment.role]`, plus row-level rules (a student can read *own* attempts only; answer keys need `content.read_admin`).
6. `user.is_platform_admin` → allow only actions on the support whitelist, never silently.

**List endpoints must not call `can()` in a loop.** Use scoped query builders that encode the same rules in SQL: `courses_visible_to(user)`, `catalog_courses()`, `attempts_visible_to(user, course)`. Canvas does the same, with scopes such as `enrollments.for_user(user).active_by_date`. Add one test per action × role × status (a table-driven matrix) and one test per scoped query.

---

## 4. What to skip and why

| Canvas feature | Skip because |
|---|---|
| Account, sub-accounts, root account, `AccountUser` | no B2B (owner decision). Add `organizations` later as an optional FK on courses. |
| Pseudonym | one email+password login per user. Add an `auth_identities` table only if SSO or phone login arrives. |
| CourseSection, default section, cross-listing, `limit_privileges_to_course_section` | "one course = one group" (owner decision). The forced default section is pure overhead for us. |
| EnrollmentTerm, `EnrollmentState` date cache, `EnrollmentDatesOverride` | we have only course-level dates, which can be computed in the query. |
| STI enrollment types plus custom `Role` rows | a `role` text column with a CHECK constraint is enough. Custom roles only make sense with institutions. |
| RoleOverride, the 160-permission registry, `locked`/`applies_to_descendants` | no account tree to inherit along. A code-defined matrix of about 20 actions can be reviewed and tested. |
| Several roles per user per course | rare and complicates "what am I in this course?". UNIQUE `(course_id, user_id)`. |
| `creation_pending`, `pre_registered` users | no SIS or batch imports. Invite only users who already exist, or keep a pending invite by email hash. |
| ContentMigration with a Common Cartridge export/import pipeline | copy within the database. Keep the existing zip-bundle importer as the only file import. |
| Blueprint / MasterCourses sync | sharing between teachers is "later" (owner decision). |
| Student View fake user | keep our `is_preview` attempt flag. It is simpler and already tested. |

**Course copy for us**: a `course_copies` job row (`source_course_id`, `target_course_id`, `requested_by`, `state queued|running|done|failed`, `options jsonb`, `error`) that runs synchronously or in a background task. It requires `course.read_admin` on the source (as `CourseCopyValidator` does) and creates a new course owned by the requester. Every copied row gets `copied_from_id` (our version of `migration_id`), which makes a re-copy or "update from source" possible later. Never copy enrollments, attempts or the join code (Canvas clears the code too).

---

## 5. Risks and open questions

1. **"A sign-up is a teacher" versus students signing up through the portal.** With per-enrollment roles, every user is just a user. Can any user (including minors) create courses? Canvas makes this an account setting (`teachers_can_create_courses`, `no_enrollments_can_create_courses`, both off by default). Options: allow anyone, or add a `can_create_courses` flag set at "teacher sign-up". This needs an owner decision.
2. **ORT "visible to everyone"**: is this `visibility=catalog` + `enrollment_mode=open` (students still enroll, so attempts have an enrollment), or anonymous read? I recommend catalog + open so that every attempt is tied to an enrollment.
3. **Join code brute force**: 25⁶ codes is plenty only with rate limits. The code is stored in plain text because the teacher must see it. That is acceptable because it only grants a student enrollment, not a credential. Treat it like the old PIN fix: never show it to students.
4. **One role per course**: a teacher who wants to "take" their own course as a student uses preview. This needs confirmation.
5. **Enrollment form ("possibly an enrollment form")**: the `approval` mode plus `requested` state covers the gate. Form answers would need a `enrollment_requests(answers jsonb)` table. The scope is not yet clear.
6. **Concluded-course data visibility for minors**: should prior students keep read access to results forever (Canvas: yes)? Consent and data retention may require hard-delete or anonymization later, which conflicts with "history kept". Design `audit_events` and attempts so they can be pseudonymized per user.
7. **Owner leaves or account deleted**: we need a transfer flow and a rule for what happens to their courses (soft-delete them, or block account deletion while they own courses with students).
8. *Unverified*: whether Canvas marks submissions `deleted` when an assignment is deleted. I also did not read the MasterCourses internals, the full `courses_controller#create` rules for teacher creators, or the Quizzes/QuizSubmission delete paths.
