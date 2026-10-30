# Phase 9 design: organizations completion, enrollment forms, invitations

**Status**: architect draft 2026-10-31 (Fable), base `origin/lms` fd36d15 (8c deployed). Binding: `IMPLEMENTATION_PLAN.md` Phase 9 (incl. "Built inside the 8c shell"); `LMS_ARCHITECTURE.md` §2b, §3, §4 (shared banks, 7c quiz-bank rules), §8; `PRODUCT_DECISIONS.md` owner rounds 2026-10-24/25 (A1 personal organizations, banks never shared between independents, A13 org admins read-only inside courses, Q4 organizations, Q7 Reply-To), D7 retention, 7c (P7C-8 quiz banks never shared, P7C-10 `can_edit_bank`), 8c (shell, sidebar, auto-hide, one page per object); `UX_GUIDELINES.md`. Precedents: `PHASE_8A_DESIGN.md`, `PHASE_8C_DESIGN.md`.

---

## 1. Scope and non-goals

In: org-shared question banks (`visibility`), org settings page, department tree on `parent_id` with org-admin scope over descendants, roster CSV import (students and teachers, dry run, idempotent), org usage for org admins, catalog modes `form_auto | form_review` with a versioned form builder, applications (submit / approve / reject / withdraw), the D7 purge job, student email invitations, catalog browse + search + course landing, invite dialog. All new screens inside the 8c shell (§9).

Out: cross-course *linking* of shared-bank questions into quizzes (Phase 9 ships **copy into a course** only; linking stays within a course as in 7c), observer/parent role and consent (Phase 11), analytics (Phase 10), SSO or school directory sync, file fields or special-category data on forms (§8 architecture), any change to ORT player, bank screens, import, scoring, result view (§12), a per-course sidebar hide/reorder page (added only if the sidebar grows; it does not here).

### 1.1 Invariants

1. A quiz bank (`assessment_id IS NOT NULL`) is never `visibility = 'organization'` (CHECK + `quiz_banks.shareable`).
2. A bank of a **personal** organization is never shared; two independents never see each other's banks (`organizations.kind = 'personal'` refuses sharing in SQL-visible scopes and at write time).
3. Every list a teacher sees of other people's banks is produced by one SQL scope (`shared_banks_visible_to`), never `can()` in a loop.
4. Org-admin authority over a course, bank or member is decided from the **ancestor path** of its organization (`organizations.path`), computed in the DB on every request; no cached role.
5. Form answers are read only by the course's staff (teacher, assistant) and the applicant; they never appear in logs, audit rows, error details, exports or org/platform admin payloads; they are NULLed by the purge.
6. Approval and `form_auto` submission create the enrollment in the same transaction as the decision, under the same limit check as `join` (course `FOR SHARE`, enrollment row `FOR UPDATE`).
7. Roster import is idempotent per `(organization_id, kind, course_id, file_sha256)`: re-applying the same file returns the stored report and sends nothing.
8. Students are never force-enrolled by staff: roster rows and invitations create **invitations** the student accepts (§3 architecture: "students always self-enroll").
9. ORT courses: enrollment modes stay `invite_code | open | closed`; ORT banks stay private; no ORT screen gains a control.

---

## 2. Schema and migration **`0014_phase9_organizations_forms`** (SQLite batch mode + PG; data steps bounded)

### 2.1 `organizations` (block `# --- Phase 9 S1 ---` in `organizations/models.py`)

- `kind VARCHAR(16) NOT NULL DEFAULT 'school'` CHECK `IN ('platform','school','personal','department')`. Backfill in Python inside the migration (orgs are few): `id == platform_org_id()` → `platform`; `slug == personal_org_slug(user_id)` for an active `org_admin` member → `personal`; `parent_id IS NOT NULL` → `department`; else `school`.
- `path VARCHAR(400) NOT NULL` materialized ancestor chain `"<root>/<dept>/<self>"` (uuid hex, `/`-joined); backfill = own id for every existing row (no trees exist yet; `parent_id` is NULL everywhere in production). `depth SMALLINT NOT NULL DEFAULT 0` CHECK `depth <= 2` (root, department, sub-department). Index `ix_organizations_path` (prefix scans `path LIKE '<root>%'`).
- CHECKs: `kind <> 'department' OR parent_id IS NOT NULL`; `kind = 'department' OR parent_id IS NULL`; `kind <> 'personal' OR depth = 0`.
- `settings` JSON keys (validated by `OrganizationSettingsIn`, unknown keys rejected): `teachers_can_create_courses` (exists), `bank_sharing_enabled` (default false; personal: always false, write refused `sharing_disabled`), `catalog_defaults {visibility: private|catalog, enrollment_mode: invite_code|open|closed|form_review}` (applied to new courses of the tree; ORT template courses ignore it), `application_retention_days` 30–90 (default 30, D7), `student_invitations_enabled` (default true). **Settings live on the root only**; departments store `{}` and read the root's.

### 2.2 `question_banks`

- `visibility VARCHAR(16) NOT NULL DEFAULT 'private'` CHECK `IN ('private','organization')`; CHECK `assessment_id IS NULL OR visibility = 'private'` (invariant 1); `shared_at`, `shared_by_id` nullable; `copied_from_bank_id` nullable FK (SET NULL). Index `ix_question_banks_org_visibility (organization_id, visibility)` for the shared scope. `bank_questions.copied_from_question_id` nullable (SET NULL), informational only.

### 2.3 `organization_roster_imports` (model `RosterImport`, `organizations/roster_models.py`)

`id, organization_id FK RESTRICT, kind student|teacher, course_id FK NULL (NOT NULL when kind = student), department_id FK NULL (teachers; must be in the tree), status dry_run|applied|partial|failed, file_sha256 CHAR(64), file_name VARCHAR(200), row_count INT, counts JSON {valid, invalid, existing_member, invited, skipped_open_invitation, failed}, report JSON (first 500 rows: line, email_masked, result, error_code), created_by_id, created_at, applied_at NULL`. Partial unique `uq_roster_imports_applied (organization_id, kind, course_id, file_sha256) WHERE status IN ('applied','partial')` (invariant 7; SQLite `sqlite_where`). Emails in the report are **masked** (`mask_email`); the raw file is never stored.

### 2.4 `enrollment_forms`, `enrollment_form_fields` (`app/lms/enrollment_forms/models.py`)

- `enrollment_forms`: `id, course_id FK RESTRICT, version INT, status draft|active|retired, title JSON (LocalizedText, nullable → course title), intro JSON (LocalizedText, ≤ 2,000 chars/lang), created_by_id, created_at, activated_at, retired_at, answered BOOLEAN NOT NULL DEFAULT false`. UNIQUE `(course_id, version)`; partial unique `(course_id) WHERE status = 'active'`; partial unique `(course_id) WHERE status = 'draft'` (one draft at a time).
- `enrollment_form_fields`: `id, form_id FK CASCADE, key VARCHAR(40) (slug, unique per form), type short_text|long_text|single_choice|multi_choice|number|date|email|phone, label JSON (LocalizedText, course default language required), help JSON NULL, options JSON NULL (choice types: list of {key,label}; ≤ 20), required BOOL, position INT, pii_category none|contact|personal, max_len INT NULL`. ≤ 25 fields per form. CHECK `type NOT IN ('single_choice','multi_choice') OR options IS NOT NULL`.
- **Immutability**: once `answered = true` (set in the submit transaction), every write to the form or its fields is refused (409 `form_answered`); "Edit" creates the next `draft` version by copying fields; "Activate" retires the current active form in the same transaction. Applications keep `form_id` → their answers always render against the fields they were asked.

### 2.5 `enrollment_applications`

`id, course_id FK RESTRICT, user_id FK RESTRICT, form_id FK RESTRICT, status pending|approved|rejected|withdrawn, answers JSON NULL (NULL after purge), submitted_at, decided_by_id NULL, decided_at NULL, decision_note VARCHAR(500) NULL, enrollment_id FK NULL (SET NULL), purge_after TIMESTAMPTZ NULL, purged_at NULL`. Partial unique `(course_id, user_id) WHERE status = 'pending'`; indexes `(course_id, status, submitted_at)`, `(user_id, status)`, `(purge_after) WHERE purged_at IS NULL`. `enrollments.source` already allows `'form'`; `enrollment_events.event` gains no value (approval writes `joined`/`rejoined`).

### 2.6 `invitations`

CHECK `role IN ('org_admin','teacher','assistant','student')` (replaces `role_valid`); new CHECK `role <> 'student' OR course_id IS NOT NULL`; `roster_import_id FK NULL (SET NULL)`. `courses` gains `catalog_search TEXT NOT NULL DEFAULT ''` (lowercased titles + description in all languages, rebuilt in `update_course`; backfill in the migration over all courses in batches of 500). `CreateMode` in `courses/schemas.py` widens to the five modes.

### 2.7 Downgrade

Drops the new tables and columns; restores the three-value `role_valid`. Lossy only for rows that used the new values (applications, student invitations, department rows), which a rollback accepts; `alembic check` clean on PG; SQLite `create_all` matches.

---

## 3. Module layout

New packages: `app/lms/enrollment_forms/` (`models, schemas, service, applications, purge, policies, router, ids`), `app/lms/organizations/{tree.py, settings.py, roster.py, roster_models.py, shared_banks.py, usage.py}`, `app/lms/content/shared_banks_router.py` (copy), `app/lms/invitations/students.py`. Touched: `core/authz.py` (`_org` reads the path), `content/permissions.py`, `content/repository.py` (scope), `content/router.py` (`_manage_bank`), `quiz_editor/quiz_banks.py` (`shareable` enforced), `courses/{schemas,service,scopes,catalog_router}.py`, `invitations/{service,emails,policies,router}.py`, `organizations/{models,schemas,service,policies,router}.py`, `platform_admin/organizations_router.py` (departments read, settings), `attempts/internal_router.py` → a shared `internal_router` entry for the purge. Error ids in each package's `ids.py`.

---

## 4. Services and rules

### 4.1 Departments (`organizations/tree.py`)

- `create_department(root_or_parent, name, slug)`: parent must be `platform|school|department` (never personal), `depth+1 <= 2`, ≤ 200 organizations per root; `path = parent.path + '/' + id`; the new row has `status` of its parent and `settings = {}`; audited `org.department_created`.
- `move_department(dept, new_parent)`: `SELECT … FOR UPDATE` on the **root** row (serializes tree writes per root), refuse cycles (`new_parent.path` starts with `dept.path`), depth of the deepest descendant after the move ≤ 2, rewrite `path`/`depth` of the subtree (one `UPDATE … WHERE path LIKE dept.path || '%'`, bounded by the 200 cap); audited.
- Courses and banks keep `organization_id` = the department they were created in; a course may be moved between departments of one root by an org admin of both (`PATCH /org/{id}/courses/{course_id} {organization_id}`), audited, roster untouched.
- `ancestor_ids(path)` is a pure split; `AuthzContext._org()` changes to one query: `SELECT status, deleted_at, path` of the org, then `EXISTS org_admin membership WHERE organization_id IN (<path ids>)` (two statements, cached per request as today). `organizations_administered_by(user)` returns the admin orgs **plus descendants** (`path LIKE any admin path || '%'`), so every existing list scope (courses, members, exam templates, invitations) gains department scope without rewrite. Members of a department are `organization_members` rows on the department; a teacher's "my organizations" shows the department with its root name.
- Suspension applies to the root (`org_suspended` resolves the root's status via the path); departments cannot be suspended alone.

### 4.2 Shared banks (`organizations/shared_banks.py`, `content/permissions.py`, `content/shared_banks_router.py`)

- `share_bank(ctx, course, bank)`: requires `can_edit_bank`, `shareable(bank)` (not a quiz bank), the root setting `bank_sharing_enabled`, `kind <> 'personal'` (invariant 2), course not an ORT-template course (§12); sets `visibility = organization`, `shared_at/by`. `unshare_bank` reverses; copies already made are untouched.
- Scope `shared_banks_visible_to(user)`: banks with `visibility = 'organization'`, `deleted_at IS NULL`, whose `organization_id` is in the user's **trees** (roots of every active membership, `path LIKE root || '%'`), joined to the home course for its title; teachers of a department see the whole school's shared banks (default; Alternatives §15-5). Personal orgs never match another user's tree.
- Read: `GET /org/{org}/shared-banks` (paginated, `q` on title), `GET /org/{org}/shared-banks/{bank_id}` and `/questions` (read-only, staff-safe `QuestionOut` with answer keys: the reader is a teacher of the tree, `content.read_admin` equivalent), `/passages`.
- **Copy** `POST /courses/{course_id}/banks/copy-from {bank_id}` (`course:content.manage`; source visible through the scope, else 404): one transaction, new bank (`copied_from_bank_id`, title "<title> (copy)"), passages and questions copied in `position` order with one new version each (content as is; `assets` are referenced by id, public images, no re-upload; `source_ref` dropped so the copy never collides with an importer upsert; translation groups re-created inside the copy only). Bounded: ≤ 2,000 questions per copy (422 `bank_too_large`), chunks of 200 flushes; rate `bank_copy_1h` 20 per actor.
- **`can_edit_bank(ctx, course, bank)`** (P7C-10 extension): `bank.course_id == course.id` and (`can(ctx, CONTENT_MANAGE, course)` **or** (`bank.visibility == 'organization'` and `ctx.org_admin_for(bank.organization_id)`)). Content write routes on banks/questions/passages replace `_manage(ctx, course_id)` by `_manage_bank(ctx, course_id, bank)` = `require(CONTENT_MANAGE)` unless `can_edit_bank` says yes (policy strings unchanged, comment "+ org admin on shared banks"). Org admins reach the editor at `/courses/{home}/bank/{bankId}` (they already read courses); `BankOut.can_edit` and `BankOut.visibility` drive the controls. The 7c edit-scope dialog needs no change: `commit.py` already reads `can_edit_bank`.
- 7c rule restated: a quiz bank reaches a shared bank only through the existing "Move/copy to a shared bank"; `shareable()` is now enforced by the CHECK and `test_quiz_bank_not_shareable` is rewritten to assert the refusal (`quiz_bank_not_shareable`).

### 4.3 Org settings and usage (`organizations/settings.py`, `usage.py`)

`PATCH /org/{org}/settings` (root only; departments 409 `settings_on_root`), audited with before/after (no PII). `GET /org/{org}/usage` for org admins reuses `service.usage()` and adds `by_department: [{id, name, courses, teachers, students}]` (one grouped query over the subtree) and `course_files_bytes` (sum of `course_files.bytes` of the tree's courses; the asset attribution stays owner-based as noted in 6a).

### 4.4 Roster import (`organizations/roster.py`)

- `POST /org/{org}/roster-imports` multipart `file` (CSV, UTF-8 with or without BOM, `;` or `,`, ≤ 256 KiB, ≤ 500 data rows; 413/422 otherwise) + `kind`, `course_id` (students; a course of the tree), `department_id` (teachers; default the org itself), `dry_run=true` default. Columns: `email` (required), `display_name` (optional, ≤ 100), teachers: `role teacher|org_admin` (optional, default teacher). **No password column is accepted** (422 `forbidden_column` if any header matches `password|pass|pwd`).
- Dry run: validates every row (email syntax, duplicates in file, existing member/enrollment, open invitation), writes the import row with `status = dry_run` and the masked report, sends nothing. Apply: `POST /org/{org}/roster-imports/{id}/apply` re-reads the stored hash against the re-uploaded file (422 `file_changed`), then per row: teacher with an account → `add_member` (direct, as today's `POST /members`); teacher without account → `teacher` invitation; **student** (account or not) → `student` invitation on the course (invariant 8; existing active enrollment → `existing_member`); open invitation for the same email + target → `skipped_open_invitation`. Rows commit in chunks of 50 (a failed chunk marks those rows `failed`, status `partial`); emails go through `BackgroundTasks` after the response, ≤ 500 per import. Limits: `roster_import_1d` 5 per org, `roster_rows_1d` 1,000 per org (counts applied rows; refuses before any write). Audited `org.roster_import_applied {kind, course_id, counts}`.

### 4.5 Student invitations (`invitations/students.py`)

`POST /courses/{course_id}/students/invitations {emails: [≤ 50], message?, language?}` (teacher `roster.manage`; org admins of the tree too, audited). Each email: normalize, refuse if an active student enrollment exists (reported as `already_enrolled` **only to staff**, who already see the roster); reuse `_create_and_send` with `role = student`; 14-day TTL (`INVITATION_TTL`), `invite_send_1h` 50 per actor shared with staff invitations (bulk counts per email). Lookup and accept reuse the public endpoints; `accept` for `role = student` runs `_join(..., source='invite')` under the course lock: full course → 409 `course_full` (the token proves legitimacy, so no disguise), concluded/draft/unpublished → 409 `course_not_open`; the invitation is consumed only on success. List `GET /courses/{course_id}/students/invitations?state=` (paginated), `POST .../{id}/revoke`, `/resend` (same rules as org invitations). Expiry sweep: none needed (state is derived from `expires_at`, as today). ORT courses allowed (roster management is not exam behaviour).

### 4.6 Catalog, landing, modes (`courses/catalog_router.py`, `courses/scopes.py`)

- `GET /catalog/courses?q=&language=&mode=&organization_id=&cursor=&limit=` (≤ 50): `q` → `catalog_search LIKE %q%` (lowercased, ≤ 80 chars; PG `ILIKE`-free because the column is lowercased), `mode` filters joinable modes, `organization_id` = a root (its tree). Response adds `organization_name`, `enrollment_mode`, `has_active_form`, `my_application {id, status}`.
- `GET /catalog/courses/{course_id}` (landing; same scope, so private/unlisted → 404): description, staff display names (`public_display_name`), student count, languages, dates, `enrollment_mode`, the **active form** (fields, no answers), `my_enrollment`, `my_application`.
- Mode rules in `update_course`: `form_auto|form_review` require an active form (422 `form_required`); leaving a form mode keeps pending applications decidable; `open|form_*` require `visibility = catalog`? **No**: a private `form_review` course is reachable only by direct link (landing is 404 for private courses) → `visibility = private` with a form mode is refused (422 `form_needs_catalog`) to avoid dead ends. ORT template courses refuse form modes (422 `template_locked`, §12).

### 4.7 Applications (`enrollment_forms/applications.py`)

- `POST /courses/{course_id}/applications {form_id, answers: {key: value}}` (student; `apply_user_24h` 10, `apply_ip_fail_10m` 60): course published, in the catalog scope, mode `form_*`, `form_id` is the active form; validate answers against the fields (required, type, options, `max_len` ≤ 2,000, email/phone syntax, `date` ISO; unknown keys 422); refuse if an active enrollment exists (409 `already_enrolled`) or a pending application (409 `application_pending`). Transaction: `form.answered = true`, insert application; `form_auto` → continue as approve (below) with `decided_by_id = NULL`. Response returns the application without echoing answers of other users (own answers yes).
- `POST .../applications/{id}/approve {note?}` / `/reject {note?}` (staff `roster.manage`; assistants read only): `SELECT application FOR UPDATE`, status must be `pending` (409 `application_decided`), course `FOR SHARE` + enrollment row `FOR UPDATE` + limit check exactly as `_join` (`course_full` 409 leaves the application pending), create or revive the enrollment (`source = 'form'`, event `joined|rejoined`), set `approved`, `enrollment_id`, `decided_*`; audit `course.application_approved {application_id}` (no answers). Reject: status, note, `purge_after = now + retention_days` (root setting). `POST .../applications/{id}/withdraw` (applicant, pending only) → `withdrawn`, `purge_after` set. Unenroll (`remove`/`leave`) of a student with an approved application sets its `purge_after` (hook in `enrollments/service.py`). Re-application after reject/withdraw is allowed (new row; the old one keeps its history until purged).
- Lists: staff `GET /courses/{course_id}/applications?status=&q=&cursor=` (paginated; `q` on applicant name/email only, never on answers), `GET .../applications/{id}` (answers rendered with the form's fields), student `GET /me/applications`.
- **Purge** (`enrollment_forms/purge.py::run_purge(limit=500)`): `UPDATE … SET answers = NULL, purged_at = now WHERE purge_after <= now AND purged_at IS NULL LIMIT 500` (PG: `WHERE id IN (SELECT … LIMIT 500 FOR UPDATE SKIP LOCKED)`); also applications of soft-deleted courses after `retention_days`. Trigger: `POST /internal/purge-applications` (`internal_token`, same cron as the attempt sweep) **and** a once-per-process-hour opportunistic call from the staff inbox endpoint (bounded, so a missing cron still purges). Result counted in `/health`-style `PurgeOut`.

### 4.8 Emails (reuse `services/email_service.py`, `invitations/emails.py`)

Student invitation template (en/ky/ru inline, like the staff one): From "{inviter} via {appName}", Reply-To = inviter (Q7), course title in the invitation language, expiry line. Application emails to the student: `application_received`, `application_approved`, `application_rejected` (note included only if the teacher ticked "send the note"), sent via `BackgroundTasks`, ≤ 1 per status change. No email on withdraw. No enumeration: `POST .../students/invitations` returns the same row shape whether the email has an account or not; the public lookup already masks. Logging: the email service logs recipient + subject only (as today, never body) and the application endpoints log ids only.

### 4.9 Application state machine

| From → to | Actor | Preconditions | Side effects |
|---|---|---|---|
| (none) → `pending` | applicant | mode `form_review`, active form, no active enrollment, no pending application | `form.answered = true`; email `application_received` |
| (none) → `approved` | applicant (`form_auto`) | as above + seat available | enrollment `student/active`, `source = form`; email `application_approved` |
| `pending` → `approved` | teacher | application locked, still pending, seat available, course published | enrollment created/revived, `enrollment_id`, audit `course.application_approved` |
| `pending` → `rejected` | teacher | pending | `purge_after = now + retention`; email with the note if ticked; audit `course.application_rejected` |
| `pending` → `withdrawn` | applicant | pending | `purge_after` set; no email |
| `approved` (enrollment removed/left) | staff / student | — | `purge_after` set on the application |
| any → purged (`answers = NULL`) | job | `purge_after <= now` | row kept for counts; `purged_at` |

`course_full` on approve leaves the row `pending` and tells the teacher to raise the limit or reject. A concluded course refuses approve (409 `course_not_open`) but allows reject and withdraw.

### 4.10 Field types and answer validation (`enrollment_forms/fields.py`, pure functions, unit-tested)

| Type | Answer | Rules |
|---|---|---|
| `short_text` | string | trimmed, 1–`max_len` (default 200, max 500) |
| `long_text` | string | 1–`max_len` (default 1,000, max 2,000); sanitized as plain text (no HTML) |
| `single_choice` | option key | key ∈ `options` |
| `multi_choice` | list of keys | 1–20 distinct keys ∈ `options` |
| `number` | number | finite, optional `min`/`max` in `options` |
| `date` | `YYYY-MM-DD` | valid calendar date, 1900 ≤ year ≤ current + 1 |
| `email` | string | same normalizer as invitations (`normalize_email`) |
| `phone` | string | `+` and 7–15 digits after stripping spaces, dashes, parentheses |

Required fields must be present and non-empty; optional ones may be omitted. Errors name `field_key` and a code (`required`, `too_long`, `bad_option`, `bad_format`), never the submitted value.

### 4.11 Roster CSV format (`rosterImport.help` shows the same table; a template file is downloadable)

```
email;display_name;role          # teachers (role optional: teacher | org_admin)
email;display_name               # students (course chosen in the wizard)
```
Header required, order free, case-insensitive; BOM tolerated; `,` accepted as delimiter when no `;` is present; extra columns are reported as `ignored_column` in the dry run; `password`-like headers refuse the file. Row result codes: `invited`, `added`, `existing_member`, `already_enrolled`, `skipped_open_invitation`, `invalid_email`, `duplicate_in_file`, `failed`.

### 4.12 Error codes (per package `ids.py`; all 4xx with the standard error shape)

`sharing_disabled`, `quiz_bank_not_shareable`, `bank_too_large`, `settings_on_root`, `department_depth`, `department_cycle`, `department_cap`, `forbidden_column`, `file_changed`, `already_applied`, `roster_too_large`, `form_required`, `form_needs_catalog`, `form_answered`, `form_draft_exists`, `too_many_fields`, `application_pending`, `application_decided`, `already_enrolled`, `course_full`, `course_not_open`, `template_locked` (reused), `organization_suspended` (reused), `rate_limited` (reused).

---

## 5. API (policies in each package's `policies.py`; inventory block `# --- Phase 9 S1 ---`; new policy name `org_admin` reused, `course:roster.manage` reused)

| Method | Path | Policy | Notes |
|---|---|---|---|
| GET/PATCH | `/org/{org}/settings` | org_admin | root only; audited |
| GET | `/org/{org}/usage` | org_admin | tree roll-up |
| GET/POST | `/org/{org}/departments` | org_admin | tree (≤ 200), create |
| PATCH | `/org/{org}/departments/{dept}` | org_admin | rename, `parent_id` (move) |
| PATCH | `/org/{org}/courses/{course_id}` | org_admin | `organization_id` within the tree |
| GET | `/org/{org}/shared-banks[/{bank_id}[/questions|/passages]]` | authenticated | member of the tree (teacher or org admin), else 404 |
| POST/DELETE | `/courses/{course_id}/banks/{bank_id}/share` | course:content.manage | + `can_edit_bank`; refusals §4.2 |
| POST | `/courses/{course_id}/banks/copy-from` | course:content.manage+ratelimit | |
| POST | `/org/{org}/roster-imports`; GET list; GET `/{id}`; POST `/{id}/apply` | org_admin+ratelimit | multipart; masked report |
| POST/GET | `/courses/{course_id}/students/invitations`; POST `/{id}/revoke`, `/resend` | course:roster.manage+ratelimit | org admins via ORG_ADMIN_ACTIONS |
| GET | `/catalog/courses` (filters), `/catalog/courses/{course_id}` | authenticated | scope `catalog_courses` |
| GET/POST | `/courses/{course_id}/enrollment-forms`; GET/PATCH/DELETE `/{form_id}`; POST `/{form_id}/activate`, `/{form_id}/new-version` | course:course.update (teacher) | fields nested in the form payload (`fields: [...]`, replace-all on PATCH) |
| POST | `/courses/{course_id}/applications` | authenticated+ratelimit | applicant |
| GET | `/courses/{course_id}/applications[/{id}]` | course:roster.read | answers: staff only |
| POST | `.../applications/{id}/approve`, `/reject` | course:roster.manage | |
| POST | `.../applications/{id}/withdraw` | authenticated | applicant only (404 otherwise) |
| GET | `/me/applications` | authenticated | |
| POST | `/internal/purge-applications` | internal_token | cron |
| GET | `/platform/organizations/{org}/departments` | platform_admin | read; settings PATCH reuses `PATCH /platform/organizations/{org}` |

### 5.1 Authorization matrix (server-side; roles from the DB on every request)

| Action | Platform admin | Org admin (tree) | Dept admin (own subtree) | Teacher (course staff) | Student | Outsider |
|---|---|---|---|---|---|---|
| Org settings read/write | read + write (`/platform`) | yes (root) | read only, write 409 | no | no | 404 |
| Departments create/move | read | yes | create/move inside own subtree | no | no | 404 |
| Shared banks: list/read | no (not a member; `/platform` shows counts) | yes | own subtree + root's shared banks (whole tree, §4.2) | yes, whole tree | no | 404 |
| Shared bank: share/unshare/edit | no | yes (`can_edit_bank`) | yes for banks in own subtree | owner course staff | no | 404 |
| Copy shared bank into a course | no | no (not course staff; Join as teacher) | same | yes (`content.manage`) | no | 404 |
| Roster import | no | yes | yes (own subtree courses) | no | no | 404 |
| Student invitations | no | yes (audited) | yes | teacher yes; assistant no | no | 404 |
| Form builder | no | read (A13) | read | teacher yes; assistant read | no | 404 |
| Applications list / decide | count only | status + counts, **no answers** | same | teacher: all; assistant: read incl. answers (course staff) | own only | 404 |
| Answers visible | never | never | never | yes | own | never |
| Catalog / landing / apply | as a user | as a user | as a user | as a user | yes | 401 |
| Usage dashboard | yes | yes | own subtree | no | no | 404 |

Org admin inside a course remains read-only (A13); the two additions (student invitations, applications status) are roster management, which A13 grants. Suspended root → every write above is 403 `organization_suspended`.

---

## 6. PII (minors)

- **Who sees answers**: course teachers and assistants, and the applicant. Org admins, platform admins and any list payload get `has_answers`, `status`, counts. `AdminAuditLog.details` for application actions holds ids and statuses only (a unit test greps serialized details for every field key).
- **Logs**: the application router and service never pass `answers` into exceptions (`ValidationFailed.details` names the field key and the error code, not the value); the request-body logger exclusion list (`core/admission`/logging) adds `/applications`. The console email provider prints subject and recipient only for application emails (the dev-only code print path is not reused).
- **Retention and purge**: D7 default 30 days (org setting 30–90) after rejection, withdrawal or unenroll; course soft-delete → `retention_days` later; purge NULLs `answers` and keeps the row for counts. Approved + active stays as long as the enrollment is active (the teacher may need contact data); the Phase 11 data-request flow will reuse `run_purge` per user.
- **Export**: no CSV/export endpoint includes answers (gradebook, roster, audit exports unchanged); the inbox has no "export" button. Field types exclude files and special categories (§8 architecture); the builder shows a notice that forms must not ask for health, religion, ethnicity or ID numbers, and `pii_category` is required per field so Phase 11's registry can list them.
- **Student side**: the apply screen states who will read the answers and for how long (i18n `applications.privacyNote`); the student sees and can withdraw a pending application; `age_band` is untouched (Phase 11).

---

## 7. Concurrency and scale

- Approval, `form_auto` submit and invitation accept share `_join`'s lock order (course `FOR SHARE` → enrollment `FOR UPDATE`) so limits hold against concurrent joins; two approvals racing for the last seat: one `approved`, one `course_full` with the application still pending (PG test).
- Tree writes serialize on the root row; department caps keep subtree updates to ≤ 200 rows.
- Roster import: unique applied-hash index makes a double "Apply" idempotent even across two workers (the loser gets 409 `already_applied` and the stored report); chunks of 50 rows; limits before any write; emails after commit.
- Form activation: `SELECT course FOR UPDATE`, retire the active form, activate the draft (the partial unique index on `active` is the backstop).
- Scale: every list is keyset-paginated (`paginate_rows`); `catalog_search` is a plain indexed-less `LIKE` on ≤ a few thousand published courses (acceptable at this size; a trigram index is a Phase 11 note); bank copy ≤ 2,000 questions in chunks; purge ≤ 500 rows per run; `shared_banks_visible_to` uses `(organization_id, visibility)`.

---

## 8. Frontend (inside the 8c shell)

### 8.1 Placement

| Screen | Where | Pattern |
|---|---|---|
| Org settings, Departments, Shared banks, Roster import, Usage | `OrgShell` nav: Overview (usage tiles) · Teachers · Courses · **Departments** · **Shared banks** · **Roster import** · Exam templates · **Settings**; department admins see the same shell scoped to their department | org area, `AreaShell` |
| Shared-banks picker | Course → **Question banks** page: a "From my organization" section (list + "Copy into this course"); on a bank page, a "Share with organization" toggle in the "⋯" menu (hidden when sharing is off, personal org or ORT course) | existing bank tab |
| Invite students | Course → **People**: tabs **Roster · Invitations · Applications** (Applications tab appears for staff only in form modes or when any application exists; students never see tabs); "Invite students" button on Roster opens the invite dialog (emails textarea, message, language) | one page with tabs |
| Form builder | Course → **Settings** → Enrollment section: mode select gains `form_auto|form_review`; "Enrollment form" link opens `/courses/{id}/settings/enrollment-form` with tabs **Edit · Preview** (versions listed, immutable notice) | one page per object |
| Applications inbox | People → Applications tab: list with status filter, row opens a side panel (answers, approve/reject with note) | not a sidebar link (8c-1: the sidebar stays at 7–8 links) |
| Catalog browse/search | `/courses/catalog` (existing app-level page) gains search box, filters (language, organization, mode) and cards with the mode badge | app header area "Courses" |
| Course landing | `/courses/catalog/{id}`: title, organization, teachers, description, mode explanation, one primary action (Join / Apply / Enter code / "Enrollment closed") | student screen |
| Apply flow | landing → `/courses/catalog/{id}/apply`: the form, privacy note, submit → "Application sent" with withdraw; `/me/home` shows a "Pending applications" line | student screen |
| Platform admin | `/admin/organizations/{id}`: new **Departments** tab (read) and settings fields in Summary | existing tabs |

### 8.2 Components and files

`components/lms/org/{OrgSettingsForm,DepartmentTree,DepartmentDialog,SharedBankList,RosterImportWizard,UsageTiles}.tsx`; `components/lms/content/{SharedBankPicker,ShareBankToggle}.tsx`; `components/lms/people/{PeopleTabs,InviteStudentsDialog,InvitationList,ApplicationsInbox,ApplicationPanel}.tsx`; `components/lms/enrollmentForm/{FormBuilder,FieldEditor,FormPreview,FormRenderer}.tsx` (`FormRenderer` is shared by Preview and the student apply page); `components/lms/catalog/{CatalogSearch,CatalogFilters,CourseLanding,ApplyPage,ApplicationStatus}.tsx`; `lib/lms/{organizations,catalog,enrollmentForms,applications,invitations}.ts` (API functions + types); routes `app/[lang]/org/[orgId]/{settings,departments,shared-banks,roster-import}/page.tsx`, `app/[lang]/courses/[courseId]/settings/enrollment-form/page.tsx`, `app/[lang]/courses/catalog/[courseId]/{page,apply/page}.tsx`. `lib/lms/nav.ts` is unchanged (no new sidebar key); `people/page.tsx` gets tabs.

### 8.3 i18n groups (en, ky, ru; parity script)

`orgSettings.*`, `departments.*`, `sharedBanks.*`, `rosterImport.*` (steps, column help, result codes), `studentInvite.*`, `catalog.*` (extend: search, filters, mode badges, landing), `enrollmentForm.*` (builder, field types, immutability, versions), `applications.*` (statuses, inbox, panel, privacy note, student statuses), `emails.*` keys stay inline in the Python email module as today (three languages, parity by test). Email templates: `invitations/emails.py` (student) and `enrollment_forms/emails.py`.

### 8.4 Mobile (375 px)

Catalog cards full width, filters in a sheet; landing with one primary button; the form renders one field per row, choice fields as stacked radios; the inbox is a card list with a full-screen panel; the builder's field list uses the 8c row pattern (one "⋯" menu, move up/down in the menu); the roster wizard is three steps (upload → preview table as cards → result); department tree indents by one level and offers "Move" in the row menu. Long ky/ru labels: badges wrap, no fixed widths.

---

## 9. ORT (unchanged; proofs in §13)

ORT template courses: form modes refused, bank sharing refused, catalog defaults ignored, student invitations allowed (roster only). ORT bank, builder, import, player, scoring and result screens get no new control (the share toggle and copy section are hidden by `template_key = 'ort'` and refused by the server). The `ort` e2e baselines are compared as in 8c (`ort-visual`); the People page in ORT courses gains the Roster/Invitations tabs like any course (frame change recorded before/after, like 8c-7).

---

## 10. Slices, ownership, models

Branch `phase-9` off `lms`; slice branches `phase-9-s<n>-<name>`; delimited blocks `# --- Phase 9 S<n> begin/end ---` in shared files; the orchestrator merges and reviews every diff. **S1 alone first; S2, S3, S4 in parallel; S5 integrates.**

| Slice | Model | Scope | Owns (exclusive) |
|---|---|---|---|
| **S1** migration + authz tree + bank permission (alone, 1–2 days) | opus; architect (fable) reviews `authz._org`, `can_edit_bank`, the CHECKs | §2 all (migration 0014 + models + backfills), `tree.py` (paths, `ancestor_ids`, `organizations_administered_by` with descendants), `authz._org` path lookup, `can_edit_bank` + `_manage_bank`, `shareable` enforcement, `CreateMode` widening + mode validation stubs (`form_required`, `template_locked`), `catalog_search` maintenance, inventory block, `OrganizationSettingsIn` validation, TypeScript types in `lib/lms/types.ts` | `alembic/versions/0014_*`, `organizations/{models,tree,settings,schemas}.py`, `content/{models,permissions,router(_manage_bank only)}.py`, `quiz_editor/quiz_banks.py`, `core/authz.py`, `core/route_inventory.py`, `courses/{models,schemas,service(mode rules)}.py`, `enrollment_forms/models.py`, `organizations/roster_models.py`, `invitations/{models in organizations/models.py}`, `frontend/src/lib/lms/types.ts` |
| **S2** organizations completion | opus | §4.1 routes, §4.2 share/unshare/scope/read/copy, §4.3 settings + usage, org area screens (§8.1 rows 1–2), platform admin departments tab, i18n `orgSettings/departments/sharedBanks` | `organizations/{service,router,policies,usage,shared_banks}.py`, `content/{repository,shared_banks_router}.py`, `platform_admin/organizations_router.py`, `frontend .../org/**`, `components/lms/org/**` (except `InviteDialog`), `components/lms/content/{SharedBankPicker,ShareBankToggle}.tsx`, bank page menu entry, `lib/lms/organizations.ts` |
| **S3** roster import + student invitations | opus (sonnet for the wizard UI) | §4.4, §4.5, §4.8 student template, People tabs Roster · Invitations, invite dialog, roster wizard, i18n `rosterImport/studentInvite` | `organizations/roster.py`, `invitations/{students,service(student branch),emails,policies,router}.py`, `enrollments/service.py` (accept hook only), `frontend .../people/page.tsx`, `components/lms/people/{PeopleTabs,InviteStudentsDialog,InvitationList}.tsx`, `components/lms/org/RosterImportWizard.tsx`, `lib/lms/invitations.ts` |
| **S4** enrollment forms, applications, catalog, purge | opus; architect (fable) reviews `applications.py` transaction and the PII filter before merge | §4.6, §4.7, §4.8 application emails, §6, People → Applications tab (component only; S3 owns the tabs shell and leaves a slot), form builder, catalog search/landing/apply, `/me/home` line, i18n `catalog/enrollmentForm/applications` | `enrollment_forms/**`, `courses/{catalog_router,scopes}.py`, `attempts/internal_router.py` (purge entry), `home/` (pending line), `frontend .../courses/catalog/**`, `.../settings/enrollment-form/**`, `components/lms/{enrollmentForm,catalog}/**`, `components/lms/people/{ApplicationsInbox,ApplicationPanel}.tsx`, `lib/lms/{catalog,enrollmentForms,applications}.ts` |
| **S5** integration and gates | orchestrator + ux-reviewer (fable) + architect security review (fable) | contracts, full suites SQLite + PG, inventory, ORT review §13, UX gate §12, `/security-review` (tree authz, shared-bank isolation, PII in logs/audit/exports, enumeration, rate limits, purge), i18n parity, `next build` in the rsync copy, `PHASE_9.md`, `PRODUCT_DECISIONS.md` (§14), `HANDOFF_NEXT_AGENT.md`, Neon backup branch, merge `lms` → `main`, `/health` check | docs, CI |

Interfaces fixed by S1: `OrganizationOut {kind, path, depth, parent_id, settings}`, `BankOut {visibility, can_edit, copied_from_bank_id}`, `CourseOut.enrollment_mode` (five values), `RosterImportOut`, `EnrollmentFormOut/FieldOut`, `ApplicationOut` TypeScript types; error ids listed in each `ids.py`; the `PeopleTabs` slot name `applications` (S3 renders S4's component when present). S2/S3/S4 share no file; the only cross-touch is `people/page.tsx` (S3) importing S4's `ApplicationsInbox` (S4 ships it behind a stub export until merged).

**Walkthrough (S5, dated in `PHASE_9.md`)**: platform admin creates school "Lyceum 61" → org admin creates departments "Maths" and "Languages" → roster import of 3 teachers (dry run, apply; two invited, one existing added) → a Maths teacher shares a bank; a Languages teacher copies it into her course; an independent teacher in a personal org sees nothing → the Languages teacher builds a 4-field form, sets `form_review`, catalog-visible → a student searches the catalog, opens the landing, applies → inbox shows the application, teacher approves → enrollment active, student sees the course → another student withdraws → purge (internal endpoint) NULLs answers after the clock is moved → the teacher invites 3 students by email; one accepts → 375 px pass over catalog, landing, apply, inbox. ORT course: People tabs present, settings show no form option, bank menu has no share entry.

**Release**: one release after S5 (`phase-9` → `lms` → `main`), Neon backup branch first (migration 0014).

---

## 11. Tests (`backend/tests/lms/`, scratch SQLite + PG parity; frontend `tsc`, unit, e2e)

- `test_org_tree.py`: create/move/cycle/depth/cap; `organizations_administered_by` includes descendants; dept admin 404 on sibling; suspension through the root; PG: two moves on one root serialize.
- `test_shared_banks.py`: isolation matrix (school A teacher / school B teacher / two independents / dept teacher / org admin / student / platform admin) on list, read, copy, share; personal org `sharing_disabled`; quiz bank refusal (rewritten `test_quiz_bank_not_shareable`); copy content equality, `source_ref` dropped, 2,000 cap, translation groups inside the copy; `can_edit_bank` for org admin on shared vs private bank; 7c scope dialog offers `all` to the org admin; ORT course share 422.
- `test_org_settings_usage.py`: validation, root-only, catalog defaults applied to new courses (not ORT), usage by department.
- `test_roster_import.py`: parsing (BOM, `;`), forbidden password column, 500-row cap, dry run writes nothing but the import row, apply results per row, idempotent re-apply (same report, no emails: provider stub counts), `file_changed`, partial chunk failure, masked report, limits.
- `test_student_invitations.py`: bulk ≤ 50, same shape for known/unknown emails, accept creates `source=invite` student enrollment, full course 409 and token not consumed, expired token 404, revoke/resend, assistant 403, org admin audited, ORT course allowed.
- `test_enrollment_forms.py`: builder validation (types, options, 25 fields, LocalizedText default language), activation retires the old form, `form_answered` immutability, new-version copy, mode rules (`form_required`, `form_needs_catalog`, `template_locked`).
- `test_applications.py`: submit validation per type, pending uniqueness, `form_auto` enrolls in one transaction, approve/reject/withdraw state machine, limit race on PG (one `approved`, one `course_full`, application still pending), answers visibility matrix (teacher, assistant, applicant, other student, org admin, platform admin), audit rows without answers, email stub counts, `/me/applications`.
- `test_pii_guard.py`: serialized logs captured during a failing submit contain no answer value; audit details never contain field keys' values; no export endpoint returns `answers`.
- `test_purge.py`: `purge_after` set on reject/withdraw/unenroll/course delete; run NULLs answers, keeps rows, respects limit, opportunistic call bounded; retention per org setting.
- `test_catalog_search.py`: `q` on titles in three languages, filters, landing 404 for private/unlisted/suspended, `my_application`.
- Updates: `test_route_inventory` (new entries), `test_pg_concurrency*.py` (approval race, tree move), serializer contracts (`CourseOut.enrollment_mode`, `BankOut`), `tests/test_migrations.py` (0014 upgrade/downgrade, backfill of `kind`/`path`).
- Frontend: `FormRenderer` unit tests (required, choice, number), `tsc`, `check_i18n_parity.py`, e2e `catalog-apply.spec.ts`, `people-tabs.spec.ts`, ORT suite unchanged.

---

## 12. UX gate screens (`docs/phases/PHASE_9_screens/`, 375 px + 1440 px; student screens en/ky/ru, staff ru)

Org: Settings, Departments (tree + move dialog), Shared banks list, Roster import (upload, preview, result), Overview with usage tiles. Course staff: Question banks with "From my organization" section and the share toggle menu, People → Roster with Invite students dialog, People → Invitations, People → Applications inbox + panel (approve with note), Settings → Enrollment (mode select with form modes), Enrollment form Edit and Preview. Student: catalog with search and filters, course landing (open / invite code / form / closed variants), apply form with privacy note, "Application sent" and "Rejected with note" states, home with pending application line, invitation accept page for a student invitation. Platform admin: organization Departments tab. Reviewed by `ux-reviewer` against `UX_GUIDELINES.md`; findings fixed before merge.

---

## 13. ORT review plan

Proofs: (1) golden import fixtures unchanged (`tests/lms/test_ort_import_golden*`); (2) `frontend/e2e/` ORT suite green with `ort-visual` content regions byte-identical to `docs/phases/ORT_BASELINE/` (the People tabs and the unchanged sidebar are frame, recorded before/after as in 8c-7); (3) `test_ort_phase9_locks.py`: ORT course `PATCH enrollment_mode=form_review` → 422, `POST .../banks/{id}/share` → 422, catalog defaults not applied to ORT courses, ORT bank list `visibility = private` for every row after migration; (4) attempt engine, scoring and result-view tests untouched and green; (5) the ORT exam template dry-run (B9) still passes.

---

## 14. Decisions taken here (to `PRODUCT_DECISIONS.md` as P9-1 … when applied)

| # | Decision |
|---|---|
| P9-1 | Departments are `organizations` rows (`kind = department`) under a root, depth ≤ 2, ≤ 200 per root, with a materialized `path`; org-admin scope is decided from the path on every request. Settings live on the root. |
| P9-2 | Shared banks are read by every teacher of the **whole tree** of a root; edited by the home course's staff and org admins (`can_edit_bank`); reused across courses by **copy** only (no cross-course linking). |
| P9-3 | Personal organizations can never enable bank sharing (`sharing_disabled`); the platform organization's sharing stays off until the owner turns it on. |
| P9-4 | Roster rows for students become **invitations** (no forced enrollment); teachers with accounts are added directly, others invited. Imports: ≤ 500 rows, ≤ 256 KiB, idempotent per file hash, no password column. |
| P9-5 | Student invitations reuse `invitations` with `role = student`, 14-day TTL, ≤ 50 emails per request, shared `invite_send_1h` limit; accept uses the join lock and returns `course_full` honestly. |
| P9-6 | Form modes require an active form and `visibility = catalog`; forms are immutable once answered (new versions instead); ≤ 25 fields, 8 types, no files. |
| P9-7 | Answers are visible to course staff and the applicant only; org and platform admins see statuses and counts; purge after 30 days (org setting 30–90) following rejection, withdrawal, unenroll or course deletion; cron endpoint plus a bounded opportunistic purge. |
| P9-8 | No new sidebar link: applications and invitations live under **People** as tabs (Applications tab shown to staff only in form modes or when non-empty); the form builder hangs off Settings → Enrollment; catalog, landing and apply are app-level student pages. |
| P9-9 | ORT courses refuse form modes and bank sharing; student invitations are allowed there (roster, not exam behaviour). |

---

## 15. Alternatives to discuss (owner; none blocks; the default is in effect)

1. **Org admins editing shared-bank questions** (default: yes through `can_edit_bank`, from the home course's bank page). Alternative: management only (share/unshare/delete) and content edits only after "Join as teacher" (stricter A13 reading).
2. **Enrollment forms on the ORT courses** (default: refused; ORT stays `invite_code | open | closed` as today). Alternative: allow `form_review` on the ORT courses for registration data; the player is untouched either way.
3. **Student roster rows** (default: invitation the student accepts). Alternative: direct enrollment of existing accounts by the school, which contradicts "students always self-enroll" and the consent direction of Phase 11.
4. **Email volume**: roster imports and bulk invitations send up to 500 emails per import. The free tier of the configured provider may cap daily sends; default caps are 500 rows per import, 1,000 rows per org per day, 50 emails per bulk request. Raising them or choosing a paid email plan is the owner's call (costs money).
5. **Sharing scope inside a school** (default: whole tree — a department's shared bank is visible to the whole school). Alternative: department-only sharing with an explicit "share with the whole school" step; a `visibility = 'department'` value can be added later without migration churn.
6. **Retention** (default 30 days, org setting up to 90). Alternative: fixed 30 days platform-wide (less configuration, simpler audit story).
7. **Rejection note to the student** (default: optional, sent only if the teacher ticks "send the note"). Alternative: never shown to the student.
8. **Catalog search** (default: plain `LIKE` on a lowercased search column). Alternative: PG trigram index now; deferred to Phase 11 performance work unless the catalog grows past a few thousand courses.
