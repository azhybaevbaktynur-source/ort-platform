# Phase 6 design: organizations, course templates (ORT first), invitations, design system, student home

**Status**: **approved by the owner 2026-10-25** (third round; implementation of 6a started). Second draft of 2026-10-24. The owner's answers to the first draft are applied throughout and recorded in §10 "Decided"; `docs/PRODUCT_DECISIONS.md` "Owner decisions 2026-10-24 (second round)" is the source of truth. H1 (the hotfix) is the only code released before this review. The exam template constructor the owner proposed is evaluated in `docs/phases/EXAM_TEMPLATES_DESIGN.md` (summary in §12); it is **not** part of Phase 6. Plan: `docs/IMPLEMENTATION_PLAN.md` Phase 6; architecture: `docs/LMS_ARCHITECTURE.md` §2b, §3.

Conventions: tables are PostgreSQL + SQLite (no runtime ALTERs); ids are uuid unless noted; `users.id` is a string. All names below are proposals the implementers must use as written so slices merge cleanly.

---

## 1. Scope and non-goals

**In Phase 6**

| Part | What ships |
|---|---|
| H1 hotfix (first) | General-assessment player crash when a section has a teacher-set title (React #31). Fix: `attemptTypes.ts` types `title`/`instructions` as `string \| Localized \| null`; `PlayerShell.sectionTitle()` and `Palette.tsx:38` resolve with `pickLocalized(...)`; add `app/[lang]/courses/[courseId]/attempts/[attemptId]/error.tsx` (friendly message, Retry, back to course); test that publishes a titled section and opens the attempt. ORT is unaffected (titles `null`). Released alone, before everything else (owner decision H1; done). |
| 6a Foundation | Organizations, memberships, org admins, template registry with the ORT template wrapping existing ORT code, template grants, locked templates, invitations, sign-up without a teacher choice, migration 0008 (personal organizations), platform admin and org admin pages (on the current UI components), authorization extension, ORT review (§6). |
| 6b Experience | Design system (`frontend/src/components/ui/`), app header with area switcher, student home + `GET /me/home`, UX audit fixes marked "6b" in §8, ORT player part-1 improvements with baselines, UX gate. |

**Decided**: 6a and 6b are released separately, each with its own gates and deploy (owner, A4).

**Non-goals (later phases)**: departments/tree logic (9), roster CSV import (9), org settings beyond `teachers_can_create_courses` (9), shared org banks (9), student invitations and enrollment forms (9), assignments/accommodations/access codes (7a), **exam templates and the constructor (7b data model, 8b builder; `EXAM_TEMPLATES_DESIGN.md`)**, general import format (7b), modules and pages (8a), quiz statistics and org analytics (10), observer accounts and privacy (11). No `users.role` column, ever.

---

## 2. Organizations and permissions

### 2.1 Tables (migration `0008_phase6_organizations`, down_revision `0007_phase5_storage`)

**organizations**

| Column | Type / constraint |
|---|---|
| id | uuid PK (bootstrap rows use fixed uuid5 ids, see §4) |
| slug | varchar(64) NOT NULL UNIQUE, `^[a-z0-9-]{2,64}$` |
| name | varchar(200) NOT NULL (plain string; organization names are proper nouns, not translated) |
| status | varchar(16) NOT NULL default `active`, CHECK IN (`active`,`suspended`) |
| parent_id | uuid NULL FK organizations.id ON DELETE RESTRICT (stored only; no tree logic) |
| settings | JSON NOT NULL default `{}`; Phase 6 key: `teachers_can_create_courses` bool (absent = false) |
| created_by_id | varchar(64) NULL FK users.id SET NULL |
| created_at, updated_at | timestamptz NOT NULL |
| suspended_at, suspended_reason | timestamptz NULL, varchar(500) NULL |
| deleted_at | timestamptz NULL (soft delete; Phase 6 UI has no delete, only suspend) |
| Indexes | `ix_organizations_status`, `ix_organizations_parent_id` |

**organization_members**

| Column | Type / constraint |
|---|---|
| id | uuid PK |
| organization_id | uuid NOT NULL FK organizations.id RESTRICT |
| user_id | varchar(64) NOT NULL FK users.id RESTRICT |
| role | varchar(16) NOT NULL CHECK IN (`org_admin`,`teacher`); one row per user per org. An org admin manages the organization (members, courses, owners) and has **read-only** access inside its courses plus roster management; full teacher powers in a course only through a `teacher` enrollment they add themselves to (§2.2, owner decision A13) |
| state | varchar(16) NOT NULL CHECK IN (`active`,`removed`) |
| invited_by_id, invitation_id | FK users.id SET NULL; FK invitations.id SET NULL |
| created_at, updated_at, removed_at, removed_by_id | timestamps; FK users.id SET NULL |
| Constraints | UNIQUE(organization_id, user_id); `ix_organization_members_user_id_state` |

Students are never members; they reach courses through enrollments only. Re-adding a removed member revives the row.

**courses** (new columns)

| Column | Type / constraint |
|---|---|
| organization_id | uuid NOT NULL FK organizations.id RESTRICT (nullable during migration, NOT NULL at the end); `ix_courses_organization_id_status_deleted_at` |
| template_key | varchar(32) NULL (`ort`; NULL = general course) |
| template_version | int NULL; CHECK ((template_key IS NULL) = (template_version IS NULL)) |
| template_settings | JSON NOT NULL default `{}` (ORT v1: `{"language": "ky"\|"ru"}`) |
| template_locked | bool NOT NULL default false |

**question_banks**: `organization_id uuid NOT NULL FK organizations.id RESTRICT`, index. Rule: a bank with `course_id` copies the course's organization; a bank without a course takes the creator's organization (the request names it when the creator is in several). **assets** get no organization column in Phase 6 (they are owner-scoped and deduplicated by hash); org storage usage is computed as the bytes of assets owned by the org's active members (approximation, documented on the usage tab; exact attribution in Phase 9).

**organization_template_grants**

| Column | Type / constraint |
|---|---|
| id | uuid PK |
| organization_id | uuid NOT NULL FK organizations.id RESTRICT |
| template_key | varchar(32) NOT NULL |
| granted_by_id, granted_at | FK users.id SET NULL; timestamptz NOT NULL |
| revoked_by_id, revoked_at | FK users.id SET NULL; timestamptz NULL (NULL = active grant) |
| Constraints | UNIQUE(organization_id, template_key): one row per pair; a re-grant clears `revoked_at` (no partial indexes, same on SQLite and PG) |

Templates themselves are code (§5), so there is no `course_templates` table. The admin "Templates" tab lists `registry.all()`.

**invitations**

| Column | Type / constraint |
|---|---|
| id | uuid PK |
| token_hash | varchar(64) NOT NULL UNIQUE (sha256 of a 32-byte urlsafe token; the token is only in the email) |
| email | varchar(255) NOT NULL, lowercased; `ix_invitations_email` |
| organization_id | uuid NOT NULL FK organizations.id RESTRICT |
| role | varchar(16) NOT NULL CHECK IN (`org_admin`,`teacher`,`assistant`) |
| course_id | uuid NULL FK courses.id RESTRICT; CHECK (role <> 'org_admin' OR course_id IS NULL); CHECK (role <> 'assistant' OR course_id IS NOT NULL) |
| message | varchar(500) NULL (shown in the email) |
| language | varchar(2) NOT NULL (email language) |
| invited_by_id | varchar(64) NOT NULL FK users.id RESTRICT |
| expires_at | timestamptz NOT NULL (created + 14 days) |
| accepted_at, accepted_user_id | timestamptz NULL; FK users.id SET NULL |
| revoked_at, revoked_by_id | timestamptz NULL; FK users.id SET NULL |
| created_at | timestamptz NOT NULL; `ix_invitations_organization_id_created_at` |

State is derived: `pending` (no accepted/revoked, not expired) → `accepted` / `revoked` / `expired`. An invitation with `course_id` creates a course staff enrollment (`teacher` or `assistant`) on accept and **no** organization membership (per-course powers come from the enrollment; membership is about creating courses and being listed as the org's teacher). An invitation without `course_id` creates the membership.

Unchanged: `users.teacher_status`, `teacher_requests` (independent teachers only), `enrollments`, `admin_audit_log` (org admin actions are written with `details.organization_id`).

### 2.2 Authorization resolution

Order, evaluated per request (`app/core/authz.py`, extended; roles always from the database):

1. Resource → course (one hop) → 404 if deleted.
2. **Platform admin** (`users.is_platform_admin`): `/platform/*` routes and today's `PLATFORM_ADMIN_ACTIONS` inside course routes. Unchanged.
3. **Org admin** of `course.organization_id` (active membership, role `org_admin`, organization not deleted): course actions `course.read`, `roster.read`, `roster.manage`, `course.transfer`, `content.read` (no answer keys, no attempts, no grades; owner decision A13). Cached per request like the enrollment role (`AuthzContext.org_admin_for(organization_id)`). **Full teacher powers** only by adding themselves as a teacher: `POST /org/{organization_id}/courses/{course_id}/join-as-teacher` writes a `teacher/active` enrollment with `source = org_admin_self` and an `enrollment_events` row, plus an `admin_audit_log` row (`org_admin_joined_course`, `details.organization_id`, `course_id`); the roster and the People tab show the badge "Joined as organization admin" on that row, and the course owner sees it in the course's activity. Leaving the course again is the normal teacher removal (also logged). An org admin who is already staff of the course simply has that enrollment's powers. Roster management without that enrollment stays student-level: adding staff, changing a role to `assistant`/`teacher` and staff invitations answer 403 `org_admin_join_required` (S5); every ownership transfer needs a new owner who is an active member of the course's organization.
4. **Enrollment role** (`teacher`/`assistant`/`student`) → `ROLE_GRANTS`, unchanged.
5. **Status gates**: draft (staff only), concluded (read-only) as today; **suspended organization** → read-only for everyone except the platform admin (`READ_ONLY_ACTIONS` only: no attempt start, no edits, no joins); the course disappears from `catalog_courses` and join by code answers with the same generic error as a wrong code.

Derived helpers (one SQL each, no loops): `organizations_administered_by(user_id)`, `organizations_of(user_id)`, `can_create_courses(user)` = platform admin, or an active membership whose org is active and (role `org_admin`, or role `teacher` and `settings.teachers_can_create_courses` is true), and the user is not disabled. `teacher_status` no longer feeds `can_create_courses`; approval of an independent creates a membership instead (§7).

Course creation (`POST /courses`): body gains `organization_id` (required when the caller has several eligible organizations), optional `owner_id` (org admin or platform admin only; must be an active member of that organization; the owner's `teacher/active` enrollment is written in the same transaction as today) and optional `template_key` (must be granted to that organization, else 403 `template_not_granted`). Assessments with preset `ort_main`/`ort_subject` are accepted only in a course whose template declares them (422 `preset_not_available`); existing assessments are untouched (A15).

### 2.3 New policies and routes

Route inventory (`app/core/route_inventory.py`): new `POLICY_NAMES` `org_admin` (active org admin of `{organization_id}` or platform admin), `course_creator` (replaces `teacher_approved` on `POST /courses`; the old name is removed from the inventory), `public+ratelimit` (invitation lookup). New policy files `app/lms/organizations/policies.py`, `app/lms/invitations/policies.py`, `app/lms/platform_admin/organizations_policies.py`.

| Method, path | Policy |
|---|---|
| GET/POST `/platform/organizations`; GET/PATCH `/platform/organizations/{id}`; POST `.../suspend`, `.../resume` | platform_admin (suspend/resume audited with reason) |
| GET `/platform/organizations/{id}/members`; POST `.../members` (assign org admin or teacher by user id); DELETE `.../members/{user_id}` | platform_admin |
| GET `/platform/organizations/{id}/courses`, `.../usage`, `.../templates`; PUT/DELETE `.../templates/{template_key}` | platform_admin (grant/revoke audited) |
| GET `/platform/templates` (registry listing) | platform_admin |
| GET `/org/{organization_id}`; GET `/org/{organization_id}/members`; POST `.../invitations`; DELETE `.../members/{user_id}` | org_admin |
| GET `/org/{organization_id}/courses`; POST `/org/{organization_id}/courses` (create + assign owner; same service as `POST /courses`) | org_admin |
| POST `/org/{organization_id}/courses/{course_id}/join-as-teacher` (A13; audited, visible in the roster) | org_admin |
| GET `/org/{organization_id}/invitations`; POST `.../invitations/{id}/revoke`, `.../resend` | org_admin |
| GET `/invitations/{token}` (org name, role, masked email, expiry; 404 for unknown/expired/revoked) | public+ratelimit |
| POST `/invitations/{token}/accept` | authenticated+ratelimit (email must match the account's email) |
| GET `/me/organizations`, GET `/me/invitations` (pending for my email), GET `/me/home` (6b) | authenticated |
| GET `/courses/templates?organization_id=` (granted templates + general) | authenticated |
| POST `/courses/{course_id}/staff/invitations` (owner invites a co-teacher/assistant without an account) | course:roster.manage |

---

## 3. Pages and navigation

Four **areas** are navigation only (A8). The header shows an area switcher with only the areas the person has: *Learning* (every user), *Teaching* (`can_create_courses` or staff in any course), *Organization* (`organizations_administered_by` non-empty; a switcher if several), *Platform* (`is_platform_admin`). 6a builds the pages with today's components; 6b moves them onto the design system (`AreaShell`, `Table`, `Dialog`, ...).

**Platform admin `/[lang]/admin/**`** (admin reviewer's proposal, adopted)

| Page | Content |
|---|---|
| Organizations (new) | Table: name, status badge, org admins, teachers, courses, created; search; primary "Create organization" → dialog (name, slug auto, contact email optional). |
| Organization detail (new) | Header: name, status, "Edit", "Suspend/Resume" (reason dialog naming the effect: "courses become read-only and leave the catalog"). Tabs: **Summary** (counts, storage bytes, created) · **Admins** (table + "Assign admin" via `UserPicker`; row "Remove" with reason) · **Teachers** (members, read-only, link to user; "Add teacher" via picker) · **Courses** (courses table filtered by org) · **Usage** (teachers, courses, students, banks, questions, storage bytes) · **Templates** (one row per registry template, switch "Granted" + confirm; ORT shows "visible only to granted organizations") · **Log** (audit filtered by org). |
| Teacher requests, Users, User detail, Courses, Course detail, Audit log, Storage | As today + organization column/filter; user detail gets "Organizations and roles" + "Add to organization"; course detail transfer uses `UserPicker` (admin B1) and dialogs name the course (M4); system account badge (M5). |

**Org admin `/[lang]/org/[orgId]/**`** (new)

| Page | Content |
|---|---|
| Overview | Org name; tiles teachers / courses / students; pending invitations list; primary "Invite teacher". Suspended org: amber banner, write actions disabled. |
| Teachers | Table: name, email, status badge (active / invited / blocked), courses count. "Invite teacher" → dialog (email, optional message). Row actions: "Revoke invitation", "Remove from organization" (reason dialog: "{name} keeps their courses; assign another owner if needed"). |
| Courses | Table: title, owner, status, students. Primary "Create course" → page (title ky/ru/en, languages, template from the org's granted templates or general, owner = picker of org teachers). |
| Course summary | Description list, staff list, "Assign owner" (picker, confirm), "Open course" (read-only staff view per §2.2), secondary "Join as teacher" (confirm dialog naming the effect: "You will appear in the course roster as a teacher; this is recorded in the organization log"). |

**Teaching** and **Student** areas: unchanged in 6a except the removed teacher sign-up texts and the "Become a teacher" link (§7). 6b: student home (§8.4), header, design-system migration of touched screens.

---

## 4. Migration of existing data (0008)

Schema first, then data in the same revision (raw SQL, deterministic), then NOT NULL. The same steps live in `app/lms/organizations/bootstrap.py::ensure_organizations(db)`, idempotent, run in the lifespan **after** grading schemes and **before** `ensure_ort_courses` (SQLite dev/tests have no Alembic; production gets the migration, then the lifespan finds nothing to do). A test asserts both paths yield the same rows.

Decided variant: **personal organizations** (owner, A1). There is no shared "independent" organization.

| Step | What happens |
|---|---|
| 1 | Insert `organizations` **platform**: id `uuid5(NS, "org:platform")`, slug from `PLATFORM_ORG_SLUG` (default `platform`), name from `PLATFORM_ORG_NAME` (default "Platform"), settings `{"teachers_can_create_courses": true}`. Both are **placeholders**: the owner renames them later with `PATCH /platform/organizations/{id}` (name and slug editable; slug uniqueness checked); nothing references the slug except URLs. |
| 2 | For every user with `teacher_status = approved` (not the demo teacher): insert the **personal organization** `uuid5(NS, f"org:personal:{user_id}")`, slug `t-{first 12 hex chars of a sha256 of the user id}`, name = the user's display name, settings `{"teachers_can_create_courses": true}` (A14: independents keep creating courses, inside their personal org), membership `org_admin` (the teacher administers their own org). A disabled user's personal org is created `suspended`. Platform admins get no personal org (they create courses in `platform` or in any org they administer). |
| 3 | All `is_platform_admin` users → `organization_members(platform, org_admin)`. |
| 4 | Both ORT courses (`course_id_for("ky")`, `course_id_for("ru")`) and their banks (`question_banks.course_id` in those) → `platform`; `template_key = 'ort'`, `template_version = 1`, `template_settings = {"language": <lang>}`, `template_locked = true`. Grant `(platform, 'ort')`. The ORT template is granted only by platform admins (never automatically to other orgs). |
| 5 | **ORT ownership (A11, decided)**: `courses.owner_id` → the owner's account = the earliest-created active platform admin; its enrollment becomes the owner (`teacher/active`, source `admin_restored` event); the demo teacher `usr_ort_demo_teacher` keeps a `teacher/active` enrollment but is shown as "System account" (admin M5) and `ensure_ort_courses` stops re-adding it when `owner_id != DEMO_TEACHER_ID` (one guard line in `_ensure_course`; the seed's content logic is untouched). If no platform admin exists (fresh dev DB), nothing changes. |
| 6 | Every other course → its owner's personal organization (created in step 2; an owner without `approved` status gets one here too, created `suspended` like a revoked teacher's, and so does a disabled user). In production this is exactly one row: the tester's private draft course moves to **that tester's personal organization** (owner decision). |
| 7 | Banks: `course_id` set → the course's org; else the owner's personal org (created if missing). |
| 8 | `courses.organization_id`, `question_banks.organization_id` → NOT NULL. Courses outside the two ORT courses that contain `ort_*` preset assessments: counted in the migration log, left as general courses (A15). |

Idempotency: fixed uuid5 ids and "insert where missing"; re-running `ensure_organizations` changes nothing. `make_admin.py` also inserts the `platform` org admin membership. New platform admins promoted later get it from `make_admin.py`, not from the seed. New independents approved later get their personal org from `teachers/service.approve` (§7). Isolation invariant (tested): no bank, course or template grant is ever visible across two personal organizations; Phase 9 bank sharing is per organization, so independents can never share banks (owner rule).

**Rehearsal (before merging to `main`)**: Neon branch from production → `create_postgres_role` on that branch only → `pg_dump -Fc` → local PG 18 (`/tmp/agy_pg`, port 55432) → `alembic upgrade head` + `alembic check` → run the lifespan via `TestClient` with `env -i`, cwd outside `backend/`, `ENVIRONMENT=production`, `LMS_STORAGE_DRIVER=db` → verification SQL: 0 courses and 0 banks without org; ORT courses in `platform` with `template_key='ort'`; grants = 1; one personal org per approved teacher (production: 2, the owner's account excluded as platform admin → 1 personal org for the tester holding the draft course); `ensure_ort_courses` report unchanged (0 new conversions). Then a Neon backup branch and the deploy.

**Downgrade**: `downgrade()` drops the new columns and tables (memberships and invitations are lost). Policy: never downgrade production; rollback = redeploy the previous commit on the Neon backup branch.

---

## 5. Course templates

A **course template** (this section) describes a course kind and is code; an **exam template** (owner's constructor idea, `EXAM_TEMPLATES_DESIGN.md` §2) describes one exam's structure and will be data (Phase 7b). ORT is a course template whose exams are today's `ort_main`/`ort_subject` presets; it never references an exam template. Design choice made now so that the two nest later: `CourseTemplate` gets a reserved field `exam_template_keys: tuple[str, ...] = ()` (empty for `ort` and `GENERAL` in 6a), and `CourseOut.template` exposes `result_view` and `passage_display` as explicit keys, which the exam template spec reuses verbatim.

### 5.1 Registry (`backend/app/lms/templates/`)

| File | Content |
|---|---|
| `base.py` | `@dataclass(frozen=True) class CourseTemplate`: `key`, `version`, `title_key` (i18n), `assessment_presets: tuple[str, ...]` (values of the existing `preset` column), `importer_profiles: tuple[str, ...]` (values of `ImportOptions.exam_type`), `section_keys: tuple[str, ...]`, `scheme_version_by_preset: dict`, `result_view: "general" \| "ort"`, `passage_display: "plain" \| "numbered"`, `lock_scope: frozenset[str]`, `default_settings: dict`, `seed: Callable \| None`. Pure data plus two helpers: `locks(field)`, `allows_preset(preset)`. |
| `registry.py` | `TEMPLATES = {"ort": ORT}`; `get(key) -> CourseTemplate` (KeyError → 422 `unknown_template`), `all()`, `for_course(course) -> CourseTemplate \| None`, `GENERAL` sentinel for `template_key IS NULL`. |
| `general.py` | `GENERAL`: presets `("none",)`, profiles `()` (plain CSV only), section keys `()`, result view `general`, passages `plain`, lock scope empty. |
| `ort.py` | `ORT` built only from imports (below). No logic of its own beyond the dataclass literal. |
| `service.py` | `assert_preset_allowed(course, preset)`, `assert_import_profile_allowed(course, exam_type)`, `assert_not_locked(course, field)`, `granted_templates(db, organization_id)`, `course_template_out(course)` (the `template` object in `CourseOut`). |

### 5.2 Exactly what becomes the ORT template (rule A: wrap, never rewrite)

| Existing file | What happens |
|---|---|
| `app/lms/assessments/rules.py` (`ORT_MAIN_SECTIONS`, `ORT_SUBJECT_KEYS`, `ORT_SECTION_RULES`, `ORT_PRESETS`, `locked_rules`, `check_item_rules`) | **Stays**; `templates/ort.py` imports `ORT_PRESETS` as `assessment_presets` and `ORT_MAIN_SECTIONS` + `ORT_SUBJECT_KEYS` as `section_keys`. `locked_rules`/`preset_rule_locked` keep working as today (they are the start of the lock scope). |
| `app/lms/assessments/builder.py` | One added guard at `create_assessment`: `templates.service.assert_preset_allowed(course, body.preset)`. Section/assessment update paths get `assert_not_locked` for the fields in §5.4. Nothing else changes. |
| `app/lms/content/importers/*` (`ort_csv.py`, `bundle.py`, `rules.py` with `ORT_SECTIONS`/`SECTION_ALIASES`, `schemas.py` `EXAM_TYPES`, `service.py`) | **Stays byte-for-byte** except A10 (below). `templates/ort.py` imports `EXAM_TYPES` as `importer_profiles`. `service.preview/commit` get one guard: `assert_import_profile_allowed(course, opts.exam_type)` (general courses: `exam_type` must be None). |
| `app/lms/grading/seeds.py` (`PRESET_SCHEME_VERSIONS`, ORT scheme ids and params) | **Stays**; imported as `scheme_version_by_preset`. |
| `app/lms/grading/*` scoring (`piecewise_curve`, sections, golden certificate) | Untouched. |
| `app/lms/ort/seed.py` (`ensure_ort_courses`, `course_id_for`, `build_bundle`, legacy conversion) | **Stays** as the ORT template's `seed`; two additions only: new ORT courses are created with `organization_id = platform org`, `template_key='ort'`, `template_locked=true`; the demo-teacher guard from §4 step 5. |
| `app/lms/ort/models.py` (`legacy_ort_export`) | Untouched. |
| `app/lms/attempts/*` (timing, forward-only sections, autosave, sweep) | Untouched. |
| Frontend `OrtResultView.tsx`, `NumberedPassage.tsx`, `ItemView.tsx` comparison card, `DeadlineTimer.tsx`, `Palette.tsx`, `PlayerShell.tsx` | Untouched in 6a. 6b applies only ORT_PLAYER_IDEAS part 1 (§8) with baseline updates. |

**A10** (owner OK needed): `importers/rules.py` `ORT_SECTIONS` accepts `math_subject`, `kyrgyz_lang_lit`, `russian_lang_lit`, which `rules.py` `ORT_SUBJECT_KEYS` does not know (`advanced_math`, `native_language`), so a subject bundle with those keys imports but cannot become an `ort_subject` assessment (`seed.py:462`). Proposed one-line fix inside the ORT importer: `SECTION_ALIASES` maps `math_subject → advanced_math`, `kyrgyz_lang_lit → native_language`, `russian_lang_lit → native_language`; the three old keys stay accepted as aliases. Parity test: the golden fixtures (§6) import identically, plus one subject fixture that now yields the right preset.

### 5.3 How the frontend chooses template pieces

`CourseOut.template` (null for general courses): `{ key, version, locked, result_view, passage_display, section_keys, assessment_presets, importer_profiles, title }`. One helper `frontend/src/lib/lms/templates.ts::templateUi(course)` returns the general defaults when `template` is null. Every current ORT check is replaced by a read of this object (no `ort` string in components):

| Component | Today | Phase 6 |
|---|---|---|
| `results/ResultSummary.tsx:13,31` | `OrtResultView` whenever `grade.sections` is non-empty | `OrtResultView` when `ui.resultView === "ort"` and `grade.sections` non-empty; otherwise `GradeBadge` + the general sections table (unchanged markup). |
| `player/PassagePane.tsx:15`, `results/ReviewItemCard.tsx:78`, `content/StudentPreview.tsx:22`, `content/PassageEditor.tsx:93` | `NumberedPassage` always | `ui.passageDisplay === "numbered"` → `NumberedPassage` (unchanged); else new `PlainPassage` (same card, no line numbers). |
| `assessments/CreateAssessmentDialog.tsx:26,67,82` | all `ASSESSMENT_PRESETS`, `ORT_SUBJECT_KEYS` | radios from `ui.assessmentPresets` (general: only `none`, radios hidden); subject list from `ui.sectionKeys` filtered to subjects. |
| `assessments/SectionDialog.tsx:47`, `AddItemsDialog.tsx:168`, `PickFields.tsx:68` | `ORT_SECTIONS` datalist and lock | `ui.sectionKeys` (general: no datalist; section stays a free label). Lock condition identical for ORT. |
| `content/import/ImportPanel.tsx:18-32` | `FORMATS` with default `full_main` (T11) | formats from `ui.importerProfiles`; general courses show no format select and send `exam_type = null`. ORT courses see exactly today's three options with `full_main` default. |
| `lib/lms/contentTypes.ts` `ORT_SECTIONS`, `assessmentTypes.ts` `ORT_SUBJECT_KEYS` | constants used directly | kept and re-exported; consumed only through `templateUi`. |

Teacher screens in an ORT course are unchanged: the same options appear because the ORT template declares exactly today's values. The ORT bank screens keep today's layout (one bank per imported source, section as a field; no split by section; owner decision A6).

### 5.4 Locked template (A7)

| Locked (409 `template_locked`; UI shows the control **greyed out with a short note** "Fixed by the ORT template", owner decision A7) | Editable |
|---|---|
| section keys, section order, add/remove sections, section `time_limit_s`, assessment `navigation`, `preset`, section `rules`, `grading_scheme_version_id`, result view, importer profile | questions, passages, pick items and their points; banks; title, description; `available_from/until`, `due_at`; `allowed_attempts`, `score_policy`, `results_policy`, `show_correct_answers`, `shuffle_*`; `grade_release`, `omit_from_total`; course title, description, join code, visibility, enrollment limit; roster |

Enforced in `builder.py` and the section endpoints through `templates.service.assert_not_locked`. Only the platform admin can change `template_locked` (`PATCH /platform/courses/{id}`), audited.

### 5.5 Grants and visibility

The ORT template is listed in create-course forms only for organizations with an active grant (`GET /courses/templates?organization_id=`). Teachers without a grant never see "ORT" anywhere: no preset radios, no import formats, no ORT datalists. The platform admin grants/revokes per organization; revoking leaves existing ORT courses working (locked, unchanged) and only blocks new ORT courses. Per-teacher grants are not built (A1).

### 5.6 General template defaults

No template: plain section labels, no ORT suggestions, no line numbers, general result view (`GradeBadge` + per-section table), plain CSV import only, every grading scheme selectable, `preset = none` only.

---

## 6. ORT review (gate, every phase from now): functionality unchanged, look keeps up

Owner rule (second round): "unchanged" means ORT's **functionality and exam behaviour** stay the same; ORT's **design and layout keep up** with the platform so it never looks like an old, separate app. Every phase therefore runs the **ORT review**:

1. **Look**: check the ORT screens (bank, CSV/zip upload, exam builder, exam player, results, student course pages) against the design system, navigation and the rest of the platform, on phones too. Apply visual and layout updates (colors, spacing, components, menus, page arrangement, phone layout) without asking.
2. **Function**: the parity tests below (same imports, same scores, same exam rules) plus a **real walkthrough**: upload a CSV and a zip, build an ORT exam, take it as a student, see the result.
3. **ux-reviewer** reviews the ORT screens with the rest; design findings are fixed without asking. Anything that changes **how ORT works** (exam rules, timing, navigation, question layout during the exam, scoring, import formats) is not done: it goes into `docs/ORT_PLAYER_IDEAS.md` part 2 for the owner's decision.
4. **Report** in `docs/phases/PHASE_N.md`: what changed in ORT's look, with before/after screenshots, and the confirmation (test names + walkthrough) that functionality is unchanged.
5. **Screenshot check**: the comparison runs against the **approved "after" baselines** in `docs/phases/ORT_BASELINE/`, so allowed polish is never flagged as a regression; every baseline update is reviewed by the orchestrator in the PR (before/after side by side) and the DOM assertions (section order, timer, palette, comparison columns, numbered lines, result cards) must still pass.

| Test | What it proves | Where |
|---|---|---|
| Golden import fixtures | The current ORT CSV (`sample_ort_questions*.csv` with the `\\frac` fix applied to the dev files only) and the bundle zip (`tests/fixtures/bundles/tsoomo19.zip`) import to the same questions, versions, `content_hash`es, sections, passages and `source_ref`s as a frozen JSON table `tests/lms/fixtures/ort_import_golden_{csv,zip}.json` (generated once from the pre-Phase-6 code, like `ort_parity_*.json`). Run in a general course with the ORT template and assert identical results. | `tests/lms/test_ort_import_golden.py` (new) |
| Score parity | Existing `test_ort_parity.py` (frozen tables, live oracle, Hypothesis), `test_ort_seed.py`, `test_ort_cutover_flow.py` unchanged and green. | existing |
| ORT API e2e | Start `ort_main` → answer with the comparison card → autosave → finish section (forward-only refuses return) → timer boundary → submit → result has scaled score, percentile, five section rows, golden certificate rule. API-level in pytest (exists in part in `test_ort_cutover_flow.py`; extend). | `tests/lms/test_ort_e2e_api.py` |
| ORT browser e2e | Playwright (new, `frontend/e2e/ort.spec.ts`, scratch backend via `env -i`, built frontend): lobby → start → comparison question → flag → palette states → section-end dialog → passage question with line numbers → submit dialog → result page. DOM assertions: section order and count, timer present, palette count, comparison columns A/B, numbered lines, result cards. | `frontend/e2e/` |
| Screenshot baselines (A3, decided) | `docs/phases/ORT_BASELINE/<screen>-<viewport>-<lang>.png` for: lobby, comparison, flagged palette, section-end dialog, passage, submit dialog, result, review (phone 375 and desktop 1440, ru + ky). Compared with `pixelmatch` at a 0.5 % pixel tolerance and anti-aliasing ignored, after the DOM assertions. The baselines are the **approved "after" images**: an allowed visual update replaces them in the same PR with before/after images; the orchestrator reviews every baseline diff. | `frontend/e2e/ort-visual.spec.ts` |
| ORT teacher screens | Screenshots of the ORT bank list, question editor (comparison), passage editor, import page, ORT builder, publish panel, staff attempts, before and after 6a, in the same baseline folder (`teacher-*`); same comparison. | same |
| Template guard tests | ORT course: all today's options present; general course: no ORT presets/profiles/datalists; ungranted org: 403 on `template_key='ort'`; locked course: 409 on structure edits, 200 on question edits. | `tests/lms/test_templates.py` |

The gate is a CI job (`ort-parity`) that must be green to merge into `lms` or `main`.

---

## 7. Sign-up and invitation flows

| Flow | Steps |
|---|---|
| Student self sign-up (unchanged API) | `POST /auth/register` → email code → account. UI: no teacher choice; texts become neutral ("Create an account", no "ORT preparation"); auth pages use the shared `LanguagePicker` (student P2) and the platform-name key. Join by code or catalog as today. |
| Teacher invited by an org admin or the platform admin | Org admin: "Invite teacher" (email, message) → `invitations` row (role `teacher`, 14 days) → email in the inviter's UI language via `email_service.send_email` (new templates en/ky/ru: "{inviter} invites you to {org} on {appName}", button with `/{lang}/invite/{token}`). **Sender (owner decision)**: the From display name is "{inviter display name} via {appName}" (`appName` from the i18n placeholder `common.appName` in the email's language), the From address is the configured sender of the existing Resend/Brevo/SMTP path (nothing new to configure or pay); **Reply-To = the inviter's email** (owner decision 2026-10-25), so a reply reaches the inviter; the address is not in the message body. Accept page shows org, role, masked email. Existing account: log in → `POST /invitations/{token}/accept` (email must match, else `invitation_email_mismatch`) → membership → redirect to Teaching (or the course if the org admin created one). New account: "Create account" with the email prefilled → verify → the page retries accept automatically. Platform admin uses the same flow for `org_admin` invitations. Expired: 404 and "ask your administrator for a new invitation"; resend issues a new token and revokes the old. Revoke by the inviter (only while they can still manage it: `roster.manage` on the course of a course invitation), any org admin of that org, or the platform admin; resending a `teacher` course invitation is owner-only, like creating it. Pending invitations for an email are shown to that user after login (`GET /me/invitations`) so a lost email is not a dead end. |
| Independent teacher | `POST /me/teacher-requests` stays (only path left for teachers without an organization). Approval (`teachers/service.approve`) creates the teacher's **personal organization** (same ids and settings as migration step 2) and the `org_admin` membership in the same transaction (A1, decided). Rejection/revoke unchanged (revoke suspends the personal org: its courses become read-only). |
| Course owner adds staff | Existing `POST /courses/{id}/staff` by email for accounts that exist; new `POST /courses/{id}/staff/invitations` for emails without an account (role `teacher` or `assistant`, `course_id` set) → on accept, the enrollment is created; no org membership. |
| "Become a teacher" link | Removed from the student navigation. Account menu gets "I am a teacher" → page `/[lang]/teacher-access`: "At a school or center? Ask your administrator for an invitation." + "Independent teacher? Apply" (today's request form). Pending request state shown as today. |

Non-enumeration: creating an invitation for an existing member returns 409 `already_member` (the org admin sees the list anyway); the public token lookup returns one 404 shape for unknown, expired and revoked; accept and lookup are rate-limited per IP and user.

---

## 8. UX: audit results and Phase 6 plan

### 8.1 Audit summary (`docs/phases/PHASE_6_screens/audit/`, 204 screenshots)

| Area | Blockers | Major | Minor | Top findings |
|---|---|---|---|---|
| Public + student | 0 | 11 | 10 | My courses is a catalog, not a home (S3, S5); no status or next action on lists (S6); assessment page dead end after the last attempt (S1); "Не сдано" for not started (S2); 250 px phone header (S4); students see the scheme library (S8). |
| ORT player, lobby, results | 1 (B1 = H1) | 3 bugs + 7 | 9 | Dates shown as local time (B3/H2), result page sideways scroll on phones (B4), palette states hide each other (P2), touch targets under 44 px (P3), timer unlabeled (P4), dialog wording and focus (P5), passage scroll on phones (P6), result table cut on phones (R1). |
| Teaching | 1 (T1 = H1) | 16 | 13 | Tables unusable at 375 px (T2, T3, T5), question editor overflow (T4), two primaries per page (T8), hidden gradebook actions (T9), roadmap text on course home (T10), import defaults to ORT in general courses (T11), glossary (T17). |
| Platform admin | 1 | 8 | 10 | Ownership transfer needs a raw id (B1), phone nav takes half the screen (M1), users table on phones (M2), audit log in ids/JSON (M3), dialogs without object/effect (M4), system account editable (M5), dialogs without focus trap (M6). |

### 8.2 Fixed in Phase 6

| Part | Findings |
|---|---|
| H1 | B1/T1 player crash + error boundary. |
| 6a | Admin B1 (`UserPicker` for transfer), M4, M5, M7, M8 on admin screens 6a touches; T11 (import default from the template); S8 (scheme library gated); sign-up/auth texts (P2, P3); platform name key; H2 check (datetime serialization: columns typed `DateTime(timezone=True)` serialize with `+00:00`; `users.created_at` and the auth `DateTime` columns are naive → add a response serializer that emits `Z` for naive UTC datetimes, plus the frontend guard in `format.ts`). |
| 6b | Design system components (§8.3); `AppHeader` with account menu and area switcher (S4, T19, M1); student home (§8.4; S3, S5, S13); S1, S2 (`not_started` state), S6 (status badges, due dates, duration), S7, S9–S12, S14–S16; teacher T2, T3, T6, T7, T8, T12, T13, T18, T20–T24, T29 (component swaps on screens the design system touches); admin M1, M2, M6, m5–m8; ORT part 1: B3, B4, P1–P12, L1–L3, R1–R4 and the cross-cutting items, each with before/after screenshots and a baseline update. |

Scheduled later: T9 gradebook actions, T14/T15 bank list and editor, T25, T28, M3 audit log labels, m1–m4, m9 → **Phase 7** (gradebook and assignment screens are rebuilt there); T10 teacher course home, T26, T27 → **Phase 8** (course home/modules); S14 people tab → Phase 9; ORT_PLAYER_IDEAS part 2 (O1–O9) → owner decision, no phase.

### 8.3 Design system (`frontend/src/components/ui/`)

`Button` (primary / secondary / danger / link, loading), `IconButton` (required `aria-label`), `Input`, `Textarea`, `Select`, `Checkbox`, `Switch`, `Card`, `Table` (sort, count, search slot, cursor `Pagination`, stacked-card mode under 640 px), `Tabs` (scrollable, `aria-selected`), `Dialog` (native `<dialog>`, focus trap, Esc, return focus) + `ConfirmDialog`/`ReasonDialog` on top, `Badge` (neutral / info / success / warning / danger / system), `EmptyState` (text + action), `ErrorState` (Retry), `Skeleton`, `Toast`, `PageHeader` (title, badge, breadcrumbs, one primary + secondary group), `DescriptionList`, `StatTile`, `UserPicker` (async combobox), `FilterBar`, `AppHeader` (brand from `common.appName`, area switcher, account menu with language and logout), `AreaShell` (side nav on desktop, section select on phones), `LanguagePicker` (existing, reused on auth pages). Tokens in `tailwind.config` (`brand-*`, slate, success/warning/danger, gold for achievements), one font family, 16 px body on phones.

Platform name: `common.appName` already exists ("ORT Preparation Platform"); its value becomes the placeholder "Platform" / "Платформа" / "Платформа" in the three files, the hard-coded "ОРТ" logo and "ЖРТ / ОРТ 2026" on auth pages become `AppHeader`'s brand mark fed by `common.appName` and `landing.badge`, and emails use the same key. Final name = one line per language.

### 8.4 Student home

Route `/[lang]/courses` for users without a Teaching area; users with one see it under the *Learning* area. Data from one call `GET /me/home` (server-limited, no N+1):

```
{ in_progress: [{attempt_id, assessment_id, assessment_title, course_id, course_title, started_at}],           // max 3
  next_up:     [{assessment_id, course_id, course_title, title, due_at, available_until, attempts_left}],      // max 3, by due_at
  latest_results: [{assessment_id, course_id, course_title, title, display_value, label, scheme_type,
                    released_at, kept_attempt_id, is_personal_best}],                                           // max 3
  courses:     [{id, title, owner_display_name, is_platform_course, next_due_at, in_progress}],                 // max 10 + total
  pending_invitations: n }
```

Sections in order (phone: one column, 16 px gutters; desktop: 720 px column): greeting + **one primary button** (Continue > Start next due > Join with code); *Continue*; *Next up* (empty: "No new assignments. Check back later."); *Latest results* (empty: "Results appear after your first assignment."; "Personal best" badge as the small celebration); *My courses* (rows, 44 px tap height; empty state is the hero for a new student: "You are not in any course yet." + Join with code + Catalog link); the catalog moves to `/courses/catalog`. Loading: header and greeting instantly, skeleton rows for the rest. Screenshots in en/ky/ru at 375 and 1440 for the UX gate.

---

## 9. Slices and gates

Pattern of `docs/phases/PHASE_5_SLICE_RULES.md`: one worktree and branch per slice (`phase-6/<slice>`), strict file ownership, delimited blocks in shared files (`# --- Phase 6 S<n> begin/end ---`), i18n groups per slice added at the end of the JSON files, orchestrator merges.

| Slice | Scope | Owns |
|---|---|---|
| S0 (first, alone; **released**) | H1 hotfix + error boundary + test | `frontend/src/lib/lms/attemptTypes.ts`, `components/lms/player/PlayerShell.tsx`, `Palette.tsx`, `app/[lang]/courses/[courseId]/attempts/[attemptId]/error.tsx`, one test |
| S1 | Schema + migration 0008 (personal organizations) + bootstrap + `organizations` service/routers (incl. `join-as-teacher`) + authz extension + `can_create_courses` + `POST /courses` changes + `make_admin.py` + isolation tests + rehearsal script | `backend/alembic/versions/0008_*`, `app/lms/organizations/**`, `app/core/authz.py`, `app/lms/courses/{service,schemas,router,scopes}.py`, `app/lms/teachers/service.py`, `app/core/route_inventory.py` (S1 owns the file), `app/lms/platform_admin/organizations_*` |
| S2 | Templates registry + ORT wrap + guards in builder/importers + `CourseOut.template` + A10 + golden import fixtures + template tests + ORT API e2e | `app/lms/templates/**`, guard blocks in `assessments/builder.py`, `content/importers/service.py`, `content/importers/rules.py` (A10 only), `ort/seed.py` (two additions), `tests/lms/test_templates.py`, `test_ort_import_golden.py`, `test_ort_e2e_api.py` |
| S3 | Invitations (model is in S1's migration; S3 owns service/router/email templates), accept flow API, course staff invitations, `GET /me/invitations`, `/me/organizations`, teacher request → membership | `app/lms/invitations/**`, `app/services/email_service.py` (one block), `app/lms/teachers/router.py` |
| S4 | Frontend 6a: admin organization pages, org admin area, invite accept page, teacher-access page, sign-up texts, `templateUi` and the component switches of §5.3, import panel default, scheme library gate, i18n groups `organizations`, `invitations`, `templates` | `frontend/src/app/[lang]/admin/organizations/**`, `app/[lang]/org/**`, `app/[lang]/invite/**`, `app/[lang]/teacher-access/**`, `lib/lms/{organizations,invitations,templates}.ts`, the six components in §5.3 |
| S5 (6b) | Design system + `AppHeader`/`AreaShell` + migration of admin/org/teacher screens listed in §8.2 | `frontend/src/components/ui/**`, `LmsShell.tsx`, `AdminShell.tsx`, the touched screens |
| S6 (6b) | `GET /me/home` + student home + student findings + `not_started` grade state + datetime serializer (H2) | `app/lms/home/**`, `frontend/src/app/[lang]/courses/page.tsx`, `courses/catalog/**`, `components/lms/home/**`, `grading` state addition |
| S7 (6b) | ORT player part 1 + Playwright suite + baselines + visual comparison | `frontend/e2e/**`, `docs/phases/ORT_BASELINE/**`, `components/lms/player/**`, `components/lms/results/**`, `LobbyView.tsx` |

**Gates** (all before merging into `lms`; again before `main`): SQLite suite and PG suite (`alembic upgrade head && alembic check`, migrations test, concurrency tests) green; route-inventory test green; org isolation suite (org admin A sees nothing of org B; two personal organizations see nothing of each other; teacher sees only own org's courses and banks; students unaffected); authorization matrix with `org_admin` (read-only inside courses; `join-as-teacher` audited) and suspended orgs; template tests; invitation tests (expiry, single use, revoke, email mismatch, no enumeration, rate limit, sender name "{inviter} via {appName}"); sign-up API has no teacher path; migration test on a fixture DB; **ORT review** (§6: parity tests, walkthrough, look, report); **UX gate** (§8, screenshots saved in `docs/phases/PHASE_6_screens/`); `/security-review` on 6a (new authz paths, token handling, org scoping of every list) and on 6b (home endpoint scoping); i18n parity; `tsc --noEmit` and `next build` in an rsync'd copy; Neon backup branch + rehearsal (§4) before `main`; `/health` shows the new commit after deploy.

---

## 10. Decided (owner answers 2026-10-24, second round)

The alternatives of the first draft are closed. Source: `docs/PRODUCT_DECISIONS.md` "Owner decisions 2026-10-24 (second round)". Nothing here is open any more; the remaining alternatives concern the exam template constructor only (`EXAM_TEMPLATES_DESIGN.md` §10).

| # | Topic | Decision | Where applied |
|---|---|---|---|
| H1 | Player crash hotfix | Fixed and released alone first; then the rest. | §1, §9 S0 |
| A1 | Independent teachers | **Personal organization per independent teacher** (auto-created on approval; the teacher is its org admin). Banks are never shared between independent teachers. Grants go to organizations only. | §2.1, §4, §7 |
| A2 | Course creation off by default | Org admins and platform admins create courses and assign the owner. | §2.3, §3 |
| A3 | Screenshot comparison | Versioned baselines = the **approved "after" images**; allowed polish is never a regression; DOM assertions stay. | §6 |
| A4 | Phase size | 6a and 6b released separately. | §1, §9 |
| A6 | ORT banks | Keep today's bank screens and layout (no split by section). | §5.3 |
| A7 | Lock scope and UI | The exact list of §5.4; locked settings **greyed out with a short note**. | §5.4 |
| A8 | Four areas | Navigation only; powers stay on enrollment roles, membership and the admin flag. | §3 |
| A9 | Screenshots in git | Curated compressed set + CI artifacts; ORT baselines always committed. | §8 |
| A10 | Importer subject keys | Fix the alias bug inside the ORT importer; **prove ORT imports come out identical** (golden fixtures). | §5.2, §6 |
| A11 | ORT course owner | The owner's account owns both ORT courses; demo teacher = system co-teacher; seed guarded. | §4 step 5 |
| A12 | General import format | Moves to **Phase 7b** with the exam templates (`EXAM_TEMPLATES_DESIGN.md` §5); shared banks stay in Phase 9. | plan |
| A13 | Org admin inside courses | **Read-only** + roster management + reassigning the teacher. Full teacher powers only by adding themselves as a teacher (visible in the roster, audited). | §2.1, §2.2, §2.3, §3 |
| A14 | Course creation for independents | Stays **on**, inside the personal organization. Off by default for new school organizations. | §4 step 2 |
| A15 | ORT presets outside ORT courses | Refuse new ones; existing ones grandfathered and counted. | §2.2 |
| A16 | Course staff invitation | Enrollment only, no org membership. | §2.1 |
| A17 | Invitation acceptance | Logged-in email must match the invitation. | §7 |
| A18 | H2 datetime serialization | Fix in 6a. | §8.2 |
| Org name | Owner's organization | Placeholders `PLATFORM_ORG_NAME` / `PLATFORM_ORG_SLUG` (defaults "Platform" / `platform`), renameable later by the owner in the admin UI. | §4 step 1 |
| Tester course | The one private draft course in production | Moves to that tester's personal organization. | §4 step 6 |
| Emails | Invitation sender | "{Inviter's name} via {appName}" as the From display name; address = the configured sender; `appName` from the i18n placeholder. | §7 |
| ORT | Stance | One special, fixed template exactly as today: code, CSV/zip import, exam rules and scoring unchanged; owned by the owner; granted only by platform admins; **not rebuilt on the constructor now**. | §5, §6, `EXAM_TEMPLATES_DESIGN.md` §8 |
| ORT review | Every phase | Functionality and exam behaviour unchanged (parity tests + real walkthrough); design and layout keep up with the platform (visual updates applied without asking); ux-reviewer covers ORT screens; behaviour ideas only in `docs/ORT_PLAYER_IDEAS.md`; report with before/after screenshots in `PHASE_N.md`. | §6, plan §0.4 |

---

## 11. Owner answers (third round, 2026-10-25)

All open questions are answered (`PRODUCT_DECISIONS.md` "Owner decisions 2026-10-25 (third round)"): 7b/8b lettering; save-as-template in 7b; one general import format validated against the template (ORT CSV/zip unchanged); platform exam templates visible to all without grants (ORT course template grant-only); locking by the template's owner; ORT dry-run test from 7b; **invitation Reply-To = the inviter's email** (applied in §7).

---

## 12. Exam template constructor: evaluation (summary)

Full text: `docs/phases/EXAM_TEMPLATES_DESIGN.md`. In short:

- **Verdict**: the idea holds up. Sections with rules and timers, navigation, type restrictions, passage rules, scoring scheme versions and immutable snapshots already exist on assessments; the constructor adds a **reusable, versioned exam structure** (`exam_templates` + immutable `exam_template_versions` holding a validated JSON spec), **assessment creation from a template version** (`assessments.exam_template_version_id`; running exams keep their version because attempts read only the assessment snapshot), a **general import format validated against a template version**, a **block catalog** (question types, scheme versions, result views, passage renderers, display modes, importer profiles; backend registry + frontend map), and two new player features (**scrolling display mode**, explicit **result view** key).
- **Terms**: a *course template* (Phase 6a, code) describes a course kind; an *exam template* (7b, data) describes one exam. A course template may offer exam templates; ORT offers today's presets and no exam template. `preset` and `exam_template_version_id` are mutually exclusive on an assessment, so the ORT path and the template path never mix.
- **ORT**: stays on the preset path, unchanged. §8 of the design lists every ORT fact and how the spec could express it later (comparison-only sections, order and timings, forward-only per-section timers, numbered passages in reading only, the `piecewise_curve` version with the `zero_raw` quirk and section scoring, golden certificate threshold, the ORT result view, the subject exam through a template parameter). The one thing a generated format cannot do is accept today's CSV/zip files byte-compatibly; therefore the ORT importer stays a code **building block** (`importer_profile = "ort"`) that a template references. A dry-run parity test (B9) can prove expressibility without switching.
- **Cost**: M (data model, API, save-as-template, general import format) + M (scrolling mode, result-view registry) + L (visual constructor).
- **Placement**: 7b (after assignments, so "create from template" creates the assignment too) and 8b (after the design system). Not 6a.
- **Alternatives** (B1–B12 in the design): evolve presets into data (not now), save-as-template first (yes), one general format with template validation (yes), platform templates without grants (yes), teacher scope from day one (yes), JSON spec not rows (yes), min/max counts (yes), scrolling split 7b column / 8b UI (yes), ORT expressibility test (yes), lettered sub-phases (yes), templates shareable while banks are not (yes), ORT exactly as today (keep).
