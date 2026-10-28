# Phase 8a design: course structure (modules, pages, course files, announcements, gating)

**Status**: architect draft 2026-10-28 (Fable), base `origin/phase-7c`. Owner questions in §15 have safe defaults; nothing blocks (next checkpoint after 8b). Precedents: `PHASE_7A_DESIGN.md`, `PHASE_7C_DESIGN.md`; ground truth: `LMS_ARCHITECTURE.md` §7/§9, `IMPLEMENTATION_PLAN.md` Phase 8a, `research/canvas-modules-grading.md` §1.1–1.3, §3.1–3.3.

---

## 1. Scope and non-goals

In: `pages` (language variants, sanitized Markdown), `course_modules` + `module_prerequisites` + `module_items` (`page|file|assignment|url|header`), one optional completion requirement per item, append-only student facts, a derived per-enrollment progress cache, the gating evaluator with `rules_version` invalidation and "re-apply rules", gate enforcement on the targets themselves (a locked quiz cannot be started by URL), `course_files` (PDF, private bucket, folders), `announcements` (post, list, student home strip), `courses.home_kind`, template default structure (ORT: today's layout). Quizzes enter modules through their 7a assignment, whichever editor made them; "New quiz" from a module creates the quiz assignment and opens the 7c editor.

Out (unchanged or later): discussions, read receipts, email digest for announcements (Phase 9/11; no column reserved), module copy between courses, teacher "student view" toggle, file kinds other than PDF, Canvas "requirement_count" (we have `all|any`), per-student module overrides, observer role (Phase 11). ORT player, bank, import, scoring, result view: untouched (§13).

---

## 2. Schema and migration **`0012_phase8a_course_structure`**

`down_revision = "0011_phase7c_quiz_editor"`; `op.f(...)` names, `JSONType = sa.JSON().with_variant(JSONB, "postgresql")`, SQLite via `op.batch_alter_table`, as 0011. **No data steps**: the two new course columns have server defaults that reproduce today's behaviour; eight new tables start empty. LocalizedText (`Title` type, `{lang: str}`) for module and item titles as `courses.title`; plain strings for page/file/announcement titles (one language per row).

### 2.1 `courses` (block `# --- Phase 8a S1 ---` in `courses/models.py`)

| Column | Definition |
|---|---|
| `home_kind` | varchar(16) NOT NULL, server_default `'assignments'`, CHECK `home_kind IN ('modules','page','assignments')`. `assignments` = today's `StudentCourseHome` / `StaffCourseHome`. |
| `home_page_id` | uuid NULL FK `pages.id` ON DELETE SET NULL, `use_alter=True` (`fk_courses_home_page_id_pages`). Service rule: NOT NULL iff `home_kind = 'page'`, and the page belongs to this course. |

### 2.2 `pages` (model `Page`, `app/lms/pages/models.py`)

| Column | Definition |
|---|---|
| `id`, `course_id` | uuid PK; FK courses RESTRICT, NOT NULL |
| `translation_group_id` | uuid NOT NULL (defaults to own `id`; variants share it) |
| `language` | varchar(2) NOT NULL, must be in `course.languages` (422 `language_not_in_course`) |
| `title` | varchar(300) NOT NULL (`clean_text`) |
| `body_md` | TEXT NOT NULL, ≤ 100,000 chars (`PAGE_BODY_MAX`, 413 `payload_too_large` above) |
| `body_html` | TEXT NOT NULL: sanitized render of `body_md` written by the service (§5.1); never accepted from the client |
| `published` | bool NOT NULL default false |
| `created_by_id`, `updated_by_id` | varchar(64) NULL FK users SET NULL |
| mixins | `TimestampMixin`, `SoftDeleteMixin` |
| `uq_pages_group_language_live` | partial UNIQUE (`translation_group_id`, `language`) WHERE `deleted_at IS NULL` |
| `ix_pages_course_id_deleted_at` | (`course_id`, `deleted_at`) |

### 2.3 `course_modules` (`app/lms/modules/models.py`, model `CourseModule`)

| Column | Definition |
|---|---|
| `id`, `course_id` | uuid PK; FK courses RESTRICT |
| `title` | JSON LocalizedText NOT NULL |
| `position` | int NOT NULL (1..n, dense; no DB unique: `reorder` rewrites under the course row lock, as `assignments.reorder`) |
| `published` | bool default false |
| `unlock_at` | timestamptz NULL |
| `sequential` | bool default false |
| `completion_mode` | varchar(3) default `'all'`, CHECK `IN ('all','any')` |
| `rules_version` | int NOT NULL default 1 (cache key, §6) |
| `created_by_id`, `deleted_by_id`, mixins | as pages |
| `ix_course_modules_course_id_position` | (`course_id`, `position`) |

Caps (service, 422 `limit_reached`): 100 live modules per course, 200 live items per module. The outline is one document, not a cursor list (§8.1).

### 2.4 `module_prerequisites`

`module_id` FK course_modules RESTRICT, `prerequisite_module_id` FK course_modules RESTRICT, PK (`module_id`, `prerequisite_module_id`), CHECK `module_id <> prerequisite_module_id`. Service invariant (422 `prerequisite_invalid`, details `{module_id, prerequisite_module_id, reason: not_same_course|not_earlier|deleted}`): same course, `prerequisite.position < module.position`, prerequisite live. Earlier-only makes cycles impossible; `reorder` re-validates every pair and refuses an order that would break one (422 `prerequisite_order`, listing pairs) instead of dropping silently like Canvas.

### 2.5 `module_items` (model `ModuleItem`)

| Column | Definition |
|---|---|
| `id`, `module_id` | uuid PK; FK course_modules RESTRICT |
| `position` | int NOT NULL (dense per module, service-owned) |
| `indent` | smallint default 0, CHECK `0..3` |
| `title_override` | JSON LocalizedText NULL (shown instead of the target's title) |
| `published` | bool default false |
| `kind` | varchar(10) CHECK `IN ('page','file','assignment','url','header')` |
| `page_id` | uuid NULL FK pages RESTRICT |
| `file_id` | uuid NULL FK course_files RESTRICT |
| `assignment_id` | uuid NULL FK assignments RESTRICT (quizzes via `assignment_id_for(assessment_id)`) |
| `url` | varchar(2000) NULL; `http(s)` only (422 `url_invalid`) |
| CHECK `item_target_matches_kind` | `(kind='page' AND page_id IS NOT NULL AND file_id IS NULL AND assignment_id IS NULL AND url IS NULL) OR (kind='file' AND ...) OR (kind='assignment' AND ...) OR (kind='url' AND url IS NOT NULL AND the three ids NULL) OR (kind='header' AND all four NULL)` |
| mixins | `TimestampMixin`, `SoftDeleteMixin`; `ix_module_items_module_id_position`, `ix_module_items_assignment_id`, `ix_module_items_page_id`, `ix_module_items_file_id` (gate lookups, §6.5) |

Service: the target must belong to the same course (404 as elsewhere); the same target may appear in several modules (the gate uses "any unlocked", §6.5); a `header` has no requirement.

### 2.6 `item_completion_requirements`

`item_id` PK FK module_items RESTRICT; `type` varchar(12) CHECK `IN ('view','mark_done','submit','min_score','min_percent')`; `threshold` NUMERIC(8,2) NULL; CHECK `(type IN ('min_score','min_percent')) = (threshold IS NOT NULL)`; CHECK `threshold IS NULL OR threshold >= 0`. Service: `submit`/`min_*` only on `kind='assignment'` (422 `requirement_kind_mismatch`); `min_percent ≤ 100`; `header` none; `min_score` compares `submissions.effective_points` (points after late deduction and override, never display values), `min_percent` compares `effective_points / points_possible × 100`.

### 2.7 `item_progress` (append-only student facts)

`id` uuid PK, `enrollment_id` FK enrollments RESTRICT, `item_id` FK module_items RESTRICT, `event` varchar(14) CHECK `IN ('viewed','marked_done','unmarked_done')`, `created_at`. `uq_item_progress_viewed` partial UNIQUE (`enrollment_id`, `item_id`) WHERE `event = 'viewed'` (one row per view-requirement, inserted `ON CONFLICT DO NOTHING` on PG / `INSERT OR IGNORE` on SQLite). `ix_item_progress_enrollment_id_created_at`. **Deviation from `LMS_ARCHITECTURE.md` §7 (`submitted|scored` events)**: submit and score facts are **read from Phase 7 `submissions` rows** at evaluation time (§6.2); duplicating them as facts would need hooks in every grading path (hand-in, finalize, manual grade, release, regrade, override, excuse) and any missed hook would be a gating bug. `submissions.updated_at` (TimestampMixin) is the change signal.

### 2.8 `module_progress` (derived cache; rebuildable)

PK (`enrollment_id`, `module_id`), both FK RESTRICT; `state` varchar(10) CHECK `IN ('locked','unlocked','started','completed')`; `unlocked_at`, `completed_at` NULL; `current_position` int NULL (sequential: first item with an unmet requirement); `evaluated_rules_version` int; `evaluated_at` timestamptz; `facts_seen_at`, `grades_seen_at` timestamptz NULL (max fact / submission timestamps folded in); `version` int default 1 (optimistic lock). `ix_module_progress_enrollment_id`.

### 2.9 `item_requirement_status` (derived; only items with a requirement)

PK (`enrollment_id`, `item_id`); `met` bool; `best_score_percent` NUMERIC(6,2) NULL; `met_at` NULL; `updated_at`. Kept as a table (not JSON on `module_progress`): it is the **monotone memory** behind "a regrade never relocks" (§6.3) and the per-item check marks of the student view.

### 2.10 `course_files` (`app/lms/course_files/models.py`, model `CourseFile`)

`id`, `course_id` FK RESTRICT, `asset_id` FK assets RESTRICT (an `assets` row with `kind='file'`, `visibility='private'`, i.e. the Phase 5 PDF path), `folder` varchar(200) NOT NULL default `''` (path-like `Lectures/Week 1`, segments ≤ 60 chars, no `..`, `/` separated; no folder table), `title` varchar(300) NOT NULL, `published` bool default false, `created_by_id`, mixins. `ix_course_files_course_id_folder`.

### 2.11 `announcements` (`app/lms/announcements/models.py`)

`id`, `course_id` FK RESTRICT, `author_id` varchar(64) FK users RESTRICT, `title` varchar(300), `body_md` TEXT ≤ 20,000, `body_html` TEXT (same pipeline as pages), `pinned` bool default false, `published_at` timestamptz NULL (NULL = draft), mixins. `ix_announcements_course_id_published_at`.

### 2.12 Downgrade

Drop the eight tables (progress, status, requirements, items, prerequisites, modules, announcements, course_files, pages in dependency order), drop `courses.home_page_id` FK then both columns (batch on SQLite). Lossless only while no module/page/file/announcement exists; otherwise refused with a clear error. `tests/test_migration_0012.py`: up/down/up on SQLite and PG, `alembic check` clean, existing ORT and general courses read `home_kind = 'assignments'`.

---

## 3. Module layout and touched files

New packages: `app/lms/modules/` (`models, ids, schemas, policies, service, evaluator, facts, gate, router`), `app/lms/pages/` (`models, schemas, policies, render, service, router`), `app/lms/course_files/` (`models, schemas, policies, service, router`), `app/lms/announcements/` (`models, schemas, policies, service, router`). Touched: `courses/{models,schemas,service}.py` (home kind, `features` counts), `templates/base.py` (`LOCK_HOME_KIND`, `LOCK_GATING`, `default_home_kind`), `templates/{ort,general}.py`, `core/authz.py` (`A.PROGRESS_RECORD`), `core/route_inventory.py`, `core/config.py` (`COURSE_FILES_MAX_BYTES = 500 MiB`, `PAGE_PREVIEW_RATE_PER_HOUR = 600`), `app/lms/models.py`, `api/v1/router.py`, one block each in `assignments/service.py` (publish/delete/restore → `gate.touch_assignment`), `attempts/engine.py::start` and `assignments/handins.py::hand_in` and `assignments/service.py::mine/student_detail` (gate check, §6.5), `home/{service,schemas}.py`. Backend deps: `markdown` and `nh3` (§5.1).

---

## 4. Invariants

1. Visibility is computed, never synced: a student sees an item iff item ∧ module ∧ target are published and none is deleted and the course is published. Headers and urls have no target.
2. Prerequisites point to a live earlier module of the same course; reorder preserves this or fails atomically.
3. `item_progress` is append-only; `module_progress` and `item_requirement_status` are caches rebuildable from facts + `submissions` + rules.
4. Evaluation never lowers a module state or clears `met` (monotone), except "re-apply rules", which deletes the caches.
5. Staff are never evaluated and never gated; no progress row is written for a teacher or assistant.
6. Every teacher change to rules bumps `rules_version` of the affected modules (`lock_course` first) inside the same transaction.
7. `home_kind = 'page'` ⇒ `home_page_id` is a live page of the course; deleting that page resets `home_kind` to `assignments` (service, same transaction).
8. ORT template courses: `home_kind` fixed (`LOCK_HOME_KIND`) and preset exams never gated (`LOCK_GATING`, §13).
9. No student payload carries another student's progress, unpublished content, `body_md` of unpublished pages, staff notes, or `rules_version`.

---

## 5. Services

### 5.1 Pages (`pages/render.py`, `pages/service.py`)

`render(body_md) -> body_html`: `markdown` with extensions `extra, sane_lists, nl2br`, then `nh3.clean` with allowlist tags `p h2 h3 h4 ul ol li strong em u s a img br hr blockquote code pre table thead tbody tr th td sup sub`; attributes `a[href,title,rel,target] img[src,alt,title] code[class]`; `href` schemes `http https mailto` plus relative `/` and same-page fragments `#[A-Za-z0-9_:.-]+` (footnotes, fix1; `sup[id]`/`li[id]` keep only Markdown footnote ids `fn:…`/`fnref:…`); `img.src` only `/api/v1/media/` or `R2_PUBLIC_BASE_URL` (external and `data:` sources are dropped); every `a` gets `rel="noopener noreferrer"` and external links `target="_blank"`. KaTeX is not rendered on the server: `$…$` / `$$…$$` stay text and the client runs katex `auto-render` (`ignoredTags: pre code a`). No raw HTML survives: `nh3` strips unknown tags and attributes, so the sanitizer, not the Markdown library, is the trust boundary. Render runs on create/update and `POST /pages/preview` (rate-limited; never stored). Deterministic: a golden test fixes the output of a sample document.

CRUD: `create_page(ctx, course, PageCreateIn{title, language, body_md, published=false, translation_group_id=None})` (group must be in the course, language free in the group); `update_page`, `soft_delete_page` (also `module_items.page_id` rows stay; they become invisible by invariant 1; `gate.touch_pages([id])` bumps containing modules; home reset by invariant 7), `restore_page`, `resolve_variant(page, lang) -> Page` (exact language in the group, else the course default language, else the item's own page). Student `GET` resolves the variant for `enrollment.content_language or course.default_language` and runs `gate.require_access(ctx, course, page=page)`.

### 5.2 Modules and items (`modules/service.py`; every write under `lock_course`, one transaction, `rules_version += 1` on affected modules)

`create_module`, `update_module` (title, published, unlock_at, sequential, completion_mode), `delete_module` (soft; items stay; prerequisites that point to it are **kept** and ignored by the evaluator with warning `prerequisite_deleted` in the staff outline; restore revives them), `restore_module`, `reorder_modules(ids)` (dense 1..n, must list every live module, 422 otherwise; re-validates §2.4), `set_prerequisites(mid, ids)` (replace set), `add_item`, `update_item` (title_override, indent, published, url), `move_item(iid, module_id, position)` (within or across modules; both modules bumped), `reorder_items(mid, ids)`, `delete_item` (requirement row deleted first; facts and status rows stay), `set_requirement(iid, type, threshold)`, `clear_requirement(iid)`, `reapply(course | module)` (§6.4), `create_quiz_item(mid, AssignmentCreateIn)` = 7a `create_assignment(kind=quiz)` + `add_item` in one transaction, returns `{item, assignment, assessment_id}` so the UI opens `/assessments/{id}/edit`.

Staff outline warnings (computed, not stored): `target_unpublished`, `target_deleted`, `prerequisite_unpublished`, `prerequisite_deleted`, `requirement_on_unpublished_target`, `unlock_in_past_with_locked_students` (none in 8a; placeholder list is a schema so the UI needs no change later).

### 5.3 Course files (`course_files/service.py`)

`upload(ctx, course, raw, filename, folder, title, published)` → `files.service.ingest_file(course_scoped=False)` (PDF magic, `FILE_MAX_UPLOAD_BYTES` 10 MiB, `usage.store_blob` → 507 `storage_full` at `STORAGE_HARD_BYTES`; sha256 dedup shares blobs), plus a per-course cap `COURSE_FILES_MAX_BYTES` (sum of `assets.bytes` over live course files; 413 `course_files_quota`, details `{used, max}`), then the `course_files` row. `update` (title, folder, published; `gate.touch_files` when `published` changes), `soft_delete` (row only; `delete_unreferenced_blobs` runs through the existing sweep when the asset has no other live reference), `download_url(ctx, course, file)` → after `require_access` returns `{url, expires_at}`: presigned GET (`storage.presigned_get`, 120 s, `Content-Disposition: attachment; filename=<safe>`) on R2, or the existing authenticated content route on `db`/`local` (7a hand-in pattern). Never lists R2 objects (rule 5).

### 5.4 Announcements (`announcements/service.py`)

`create` (draft unless `publish=true` → `published_at = now`), `update` (title/body/pinned; editing a published one keeps `published_at`), `publish` (sets `published_at` once; 409 `already_published`), `soft_delete`. Student list: `published_at <= now`, pinned first, then `published_at desc, id`, cursor paginated. `/me/home` gains `announcements` (latest 3 across active student courses, one query; schema allow-list: `id, course_id, course_title, title, published_at`, never `body`).

### 5.5 Course home (`courses/service.py::update_course` block)

`CourseUpdateIn.home_kind`, `.home_page_id`: `templates.service.assert_not_locked(course, LOCK_HOME_KIND)` (409 `template_locked` on ORT courses), `page` requires a live page of this course (422 `home_page_invalid`). `CourseStudentOut/CourseStaffOut` gain `home_kind`, `home_page_id`, and `features: {modules: bool, files: bool, announcements: bool}` (three EXISTS over published rows; the tabs rule in §8.2). `create_course` applies `template.default_home_kind` (`general`: `modules`; `ort`: `assignments`; existing rows keep `assignments` by server default). A template's `default_structure: Optional[Callable[[Session, Course], None]]` may seed modules on creation; both templates ship `None` in 8a (the hook exists so 8b/9 can add one without touching the course service).

### 5.6 Error codes (`modules/ids.py` etc.)

422: `prerequisite_invalid`, `prerequisite_order`, `requirement_kind_mismatch`, `url_invalid`, `language_not_in_course`, `home_page_invalid`, `limit_reached`, `order_incomplete`. 409: `template_locked`, `already_published`, `page_conflict` (pages and announcements carry an integer `rev`; `PATCH` sends the `rev` it edited, stale → 409). Modules and items have no `rev`: structure writes are serialized by the course row lock and last write wins. 413: `payload_too_large`, `course_files_quota`. 423 **`module_locked`** (details `{module_id, reasons: [...]}`, §6.5). 404 for cross-course targets (`course_scoped` loaders). 507 `storage_full`.

---

## 6. Gating

### 6.1 Terms

A **student view** of a course computes the state of every module for one enrollment in one pass, in position order. Inputs: live modules + prerequisites + items + requirements (3 queries, course-wide), the enrollment's `module_progress` and `item_requirement_status` rows (2 queries), `last_fact_at` per module (`max(item_progress.created_at)` joined through items, grouped; 1 query), and the `submissions` rows of the enrollment for every assignment referenced by a requirement (1 query: `assignment_id, state, effective_points, points_possible, released_at, updated_at`). About seven queries per evaluation regardless of module count; writes only for rows whose state, `current_position`, `met` or seen-timestamps changed.

### 6.2 Algorithm `evaluate_course(db, enrollment, course, now) -> {module_id: ModuleState}` (`modules/evaluator.py`; pure function over loaded rows + a small writer)

1. **Scope**: staff (`teacher|assistant`) are never evaluated: the router returns the outline with `state = null` and lock badges only. Course not published, module unpublished or deleted → the module is `locked` for students, not stored. Items whose target is unpublished/deleted are **invisible** and their requirements are **ignored** (a module whose only requirement sits on an unpublished quiz completes once open; the staff outline warns).
2. **Cache check** per module (*as built: not used*; the evaluator always recomputes from the loaded rows, and `evaluated_rules_version`, `facts_seen_at`, `grades_seen_at` are stored for information and diagnostics only, no code path decides on them; see §6.7): reuse the stored row iff `evaluated_rules_version == module.rules_version` ∧ `facts_seen_at >= last_fact_at` ∧ `grades_seen_at >= max(submissions.updated_at)` for the module's assignments ∧ not (`unlock_at IS NOT NULL` ∧ `evaluated_at < unlock_at <= now`) ∧ no prerequisite's state changed earlier in this pass. Otherwise recompute.
3. **Unlock**: open iff `now >= unlock_at` (inclusive; NULL = always) ∧ every prerequisite that is live and published is `completed` in this pass (prerequisites are earlier, so already computed; unpublished/deleted prerequisites are skipped). Not open → `locked` (unless already `unlocked|started|completed` in the stored row: monotone, invariant 4). `unlocked_at` set on the first open.
4. **Requirements** (visible items only): `view` met if a `viewed` fact exists; `mark_done` met if the latest `marked_done|unmarked_done` fact is `marked_done` (the student's own undo may clear this one; it is the one non-monotone flag, by design); `submit` met if a `submissions` row exists with `state IN ('pending_review','graded','excused')`; `min_score`/`min_percent` met if `state = 'excused'`, or `state = 'graded'` ∧ `released_at IS NOT NULL` ∧ value ≥ threshold (`best_score_percent` keeps the best released percent). A requirement once `met` stays met (status row), so a later regrade below the threshold does not unmeet it (Canvas policy, `research` §1.3).
5. **State**: `completed` if open ∧ (no requirements, or all met in `all` mode, or ≥1 met in `any` mode); `started` if open ∧ ≥1 met or ≥1 `viewed` fact in the module; else `unlocked`. `completed_at` on the first completion.
6. **Sequential**: `current_position` = position of the first visible item with an unmet requirement (NULL when none); items with `position > current_position` are `locked` (header and requirement-less items before it never block; items after it are locked even without a requirement).
7. **Persist**: upsert changed `module_progress` rows (`version += 1`, `WHERE version = :seen`; 0 rows → re-read and keep the newer row; stale writers can only be equal or lower by monotonicity) and `item_requirement_status` rows; set `facts_seen_at = last_fact_at`, `grades_seen_at = max updated_at`, `evaluated_at = now`. Dependents need no stale flag: they come later in the same pass and re-evaluate when a prerequisite's state changed (step 2).

### 6.3 Edge cases (each is a test in §10)

`all`/`any`; empty module completes on unlock; `unlock_at` exactly `now` → open; cache row evaluated 1 s before `unlock_at` is refreshed after it passes; prerequisite chain A→B→C unlocks in one pass after A completes; a module listing an unpublished prerequisite ignores it (warning); unpublishing an assignment hides its item and drops its requirement from the formula (`touch_assignment` bumps the module); a deleted item's facts stay but count for nothing; `min_score` unmet while the grade is unreleased, met after release, **still met** after a regrade to a lower score, unmet after "re-apply rules"; excused counts as met; `mark_done` then undo → `started`, not `completed` (only when the undone box was ticked no later than the stored `completed_at`; a box ticked and unticked after the completion keeps `completed`, fix1); `sequential` with a header first; the same quiz in two modules (gate = any unlocked); concurrent `view` + `done` for one student converge (PG test, two sessions); staff get `state = null` and 403 on facts; removed enrollment keeps its rows (re-activation resumes); concluded course: facts refused (403, `progress.record` not in `CONCLUDED_ACTIONS`), view read-only.

### 6.4 Teacher edits, re-apply

Every §5.2 write bumps `rules_version` of the touched modules (and of the dependents of a module whose publish state changed, so their cache rows re-check prerequisites). Lazy invalidation: no batch job; each student's next view recomputes. **Re-apply rules** (`POST .../reapply`): under `lock_course`, delete `module_progress` and `item_requirement_status` for the course (or the module and its transitive dependents), bump their `rules_version`, audit `module.reapply`. This is the only path that can relock (a regraded `min_score`, a tightened threshold, a new prerequisite). **Requirement change** (`PUT .../requirement`, fix1): when the type changes (or a requirement is set on an item without one) or the threshold becomes stricter (higher `min_score`/`min_percent`), that item's `item_requirement_status` rows are deleted in the same transaction, so the new requirement never inherits the old `met`. Facts stay, so `view`/`mark_done`/`submit` are re-met from them on the next read; a lower or equal threshold keeps the rows. `module_progress` is untouched: a module already `completed` stays completed (monotone, invariant 4), a module not yet completed must meet the new requirement; re-apply is still the way to relock. The UI warns: "N students may lose access to later modules". `touch_assignment/pages/files(ids)` = `UPDATE course_modules SET rules_version = rules_version + 1 WHERE id IN (SELECT module_id FROM module_items WHERE assignment_id IN (...) AND deleted_at IS NULL)`.

### 6.5 Gate enforcement (`modules/gate.py::require_access(db, ctx, course, *, page=None, file=None, assignment=None)`)

Students only (staff return immediately). If no live, published module item references the target → allowed (content outside modules is ungated, as today). Else evaluate the course (§6.2, cached) and allow iff at least one referencing item is visible and not locked (module `state != locked` ∧ not sequentially locked). Otherwise 423 `module_locked` with `details.module_id`, `details.module_title`, `details.reasons: [{kind: unlock_at, at} | {kind: prerequisite, module_id, title} | {kind: sequential, item_id, title}]` (titles of published modules/items only). Call sites: `pages` student GET, `course_files` download, `assignments.mine/student_detail` (card shows the lock), `handins.hand_in`, the hand-in file upload (fix1), the student quiz lobby `GET .../assessments/{id}` (fix1, same ORT exemption as start), `attempts/engine.py::start` (before the access-code and window checks; `templates.service.is_locked(course, LOCK_GATING, preset=assessment.preset)` → skip, §13). The student assignments list and `/me/home` are **not** gated (cards show `locked: true` from one `GET /modules` call on the client); only the target routes are.

### 6.6 Facts (`modules/facts.py`)

`record_view(ctx, course, item)` (idempotent insert), `set_done(ctx, course, item, done: bool)` (appends `marked_done|unmarked_done`; accepted on any non-header item as a personal checkbox, it only affects a `mark_done` requirement). Both require an active student enrollment (`A.PROGRESS_RECORD`), a visible item that is **not locked** (423 otherwise), then evaluate the course and return the module state so the UI updates without a second call. Rate limit: 600/h per user (shared `progress_limit`).

### 6.7 Scale

Per student view: ≤ 7 reads, writes only on change. Start burst (6,000 attempt starts): one `EXISTS module_items WHERE assignment_id = :a` each; the evaluation runs only for gated quizzes and only when the cache is stale. `/me/home` reads `module_progress` only (never evaluates) for the "up next" strip (§7.4). No per-request loops over students; teacher progress table (§7.1 `progress/{enrollment_id}`) evaluates one student per request. Course-wide re-apply deletes with one statement per table. **As built** (fix1): there is no cache decision; every evaluation recomputes all modules from the ≤ 7 loaded reads, and `rules_version` / `evaluated_rules_version` are informational (nothing relies on them to skip work; a future cache would have to add and test that rule). `/me/home` scans at most `MODULES_SCAN_MAX = 100` open `module_progress` rows (ordered by course, then position) for the "up next" strip; a student with more open modules than that may see no strip entry for the courses past the bound (accepted; each course's Modules page is complete).

---

## 7. API surface, policies, authorization

`_C = /api/v1/courses/{course_id}`. Policies in each package's `policies.py`, merged in `route_inventory.py` block `# --- Phase 8a S1 ---`. New action `A.PROGRESS_RECORD = "progress.record"` (students only, like `assignment.submit`; not in `CONCLUDED_ACTIONS`).

### 7.1 Modules

| Method, path | Policy | Body → result |
|---|---|---|
| `GET _C/modules` | `course:content.read` | Staff: `ModulesStaffOut{modules: [ModuleStaffOut{…, items: [ItemStaffOut{…, requirement, target: {title, published, deleted, kind detail}, warnings}], prerequisites, warnings, rules_version}]}`. Student: `ModulesStudentOut{modules: [ModuleStudentOut{id, title, state, unlock_at, sequential, completion_mode, current_position, items: [ItemStudentOut{id, kind, title, indent, locked, requirement: {type, threshold, met, best_score_percent}, link: {page_id | file_id | assignment_id+assessment_id+assignment_kind | url}}]}], up_next: ItemRef | null}` (visible items only; evaluates). Org admin: student shape with `state = null`. |
| `POST _C/modules`, `PATCH _C/modules/{mid}`, `DELETE`, `POST …/restore` | `course:content.manage` | `ModuleIn{title, published, unlock_at, sequential, completion_mode}` |
| `PUT _C/modules/order` | manage | `{ids}` (422 `order_incomplete`, `prerequisite_order`) |
| `PUT _C/modules/{mid}/prerequisites` | manage | `{module_ids}` |
| `POST _C/modules/{mid}/items`, `PATCH _C/modules/{mid}/items/{iid}`, `DELETE` | manage | `ItemIn{kind, page_id?, file_id?, assignment_id?, url?, title_override?, indent, published, position?, requirement?: {type, threshold}}` |
| `PUT _C/modules/{mid}/items/order` | manage | `{ids}` |
| `PUT _C/modules/{mid}/items/{iid}/move` | manage | `{module_id, position}` |
| `PUT _C/modules/{mid}/items/{iid}/requirement`, `DELETE` | manage | `{type, threshold?}` |
| `POST _C/modules/{mid}/quiz` | manage (+ `template_locked` rules of 7a) | `AssignmentCreateIn` (kind quiz) → `{item, assignment, assessment_id}` |
| `POST _C/modules/reapply`, `POST _C/modules/{mid}/reapply` | manage + ratelimit (10/h) | → `{cleared_students}` |
| `POST _C/modules/{mid}/items/{iid}/view`, `POST …/done` | `course:progress.record+ratelimit` | `{}` / `{done}` → `ModuleStudentOut` |
| `GET _C/modules/progress/{enrollment_id}` | `course:attempt.read_all` | one student's `ModulesStudentOut` (teacher progress drawer) |

### 7.2 Pages, files, announcements

| Method, path | Policy |
|---|---|
| `GET _C/pages` (cursor; staff: all + `?deleted`, student: published, grouped by `translation_group_id`) | `course:content.read` |
| `POST _C/pages`, `PATCH _C/pages/{pid}`, `DELETE`, `POST …/restore` | `course:content.manage` |
| `GET _C/pages/{pid}` (student: variant + gate; `body_html` only; staff: also `body_md`, `rev`) | `course:content.read` |
| `POST _C/pages/preview` `{body_md}` → `{body_html}` | `course:content.manage+ratelimit` |
| `GET _C/course-files?folder=&cursor=` (student: published) | `course:content.read` |
| `POST _C/course-files` (multipart `file, folder, title, published`) | `course:content.manage+ratelimit` |
| `PATCH _C/course-files/{fid}`, `DELETE` | `course:content.manage` |
| `GET _C/course-files/{fid}/download` → `{url, expires_at}` (gate) | `course:content.read` |
| `GET _C/announcements` (cursor; student: published) | `course:content.read` |
| `POST _C/announcements`, `PATCH _C/announcements/{aid}`, `POST …/publish`, `DELETE` | `course:content.manage` |
| `PATCH _C` gains `home_kind`, `home_page_id` | `course:course.update` (existing) |
| `GET /me/home` gains `modules_next`, `announcements` | `authenticated` (existing) |

### 7.3 Authorization matrix (server-side, roles from the DB)

| Action | Teacher / assistant | Student | Org admin in course (A13) | Platform admin (not staff) | Other course / org |
|---|---|---|---|---|---|
| read outline, pages, files list, announcements | all, staff shape, unpublished included, `body_md` | published + unlocked only; `body_html`; own progress | student shape, everything published, `state = null`, no progress of anyone | no (platform routes only) | 404 |
| create/edit/delete/order modules, items, requirements, prerequisites; pages; files; announcements; home kind; re-apply | yes (`content.manage`; home kind `course.update`) | no (403) | no (403) | no | 404 |
| record view / mark done | no (403: `progress.record` is student-only) | yes, unlocked items, active enrollment, course published | no | no | 404 |
| download a course file | yes | published + unlocked | yes (published) | no | 404 |
| start a gated quiz / hand in a gated assignment | n/a | 423 while locked | n/a | no | 404 |
| one student's progress (`progress/{enrollment_id}`) | yes (`attempt.read_all`) | own only via `GET /modules` | no | no | 404 |
| upload page images | yes (existing `POST /assets`) | no | no | no | 404 |

Serializer contract tests: student payloads never include `rules_version`, `body_md`, warnings, unpublished items/modules/pages/files/announcements, `created_by_id`, other enrollments' rows; `module_locked` details name only published modules/items.

---

## 8. Frontend

### 8.1 Routes and components

| Route | Who | Content |
|---|---|---|
| `/[lang]/courses/[courseId]` (`page.tsx`) | both | switch on `course.home_kind`: `modules` → `StudentModulesView` (students; falls back to today's `StudentCourseHome` when no published module exists) / `StaffCourseHome` + outline link (staff); `page` → `PageView(home_page_id)`; `assignments` → today's components unchanged |
| `/courses/[courseId]/modules` | student | `StudentModulesView`: "Up next" card on top (one primary action), modules as cards (state badge locked/unlocked/started/completed, lock reasons in plain words: "Opens 12 Nov", "Finish *Module 1* first"), items as rows (kind icon + text, check mark when met, requirement text "Score at least 80 %", locked rows greyed with a lock icon and text); tapping a `page|file|assignment` item records the view (`POST view`) then navigates; `mark_done` items have a `Checkbox`; small celebration line when a module completes |
| `/courses/[courseId]/modules` | staff | `ModuleOutlineEditor`: `PageHeader` + "New module" primary; per module: title (LocalizedTextInput), publish `Switch`, menu (edit settings, prerequisites, re-apply, delete), `ModuleSettingsDialog` (unlock_at, sequential, completion_mode), `PrerequisitePicker` (earlier modules only, disabled others with hint), items list with move up/down buttons (375 px) and drag on desktop, `AddItemMenu` (Page: new or existing picker; File: upload or pick; Assignment: picker of published and draft assignments; **New quiz** → `POST …/quiz` → router push to `/assessments/{id}/edit` (7c editor); URL; Header), `RequirementPicker` per item (types allowed by kind), warnings as `Badge`s, "Student progress" drawer (`progress/{enrollment_id}` with roster `UserPicker`) |
| `/courses/[courseId]/pages`, `/pages/new`, `/pages/[pageId]`, `/pages/[pageId]/edit` | staff / student (view only) | list (table: title, language, published, used in N modules); `PageEditor`: `Textarea` Markdown + toolbar (bold, heading, list, link, image via existing asset upload, math `$`), side/below preview via `POST preview` (debounced 600 ms), language select, variants chips ("Add Russian version"), publish switch, `rev` conflict toast; `PageView`: `body_html` in a `.prose` container + katex `auto-render`, variant switcher when several exist |
| `/courses/[courseId]/files` | both | folders as collapsible groups, rows title/size/date, student: "Download" (fetches `{url}` then opens), staff: upload dialog (PDF, 10 MB, quota bar `used/max`), rename/move/publish/delete menu |
| `/courses/[courseId]/announcements`, `/announcements/new`, `/announcements/[id]/edit` | both | list newest first, pinned on top, body rendered like pages; staff: compose (Markdown, preview, "Post now" / "Save draft"), drafts section |
| Settings → "Course home" | staff | `Select` modules / page / assignments (+ page picker); ORT courses: disabled with `templates.lockedHint` as other locked fields |
| Student home (`StudentHome`) | student | `modules_next` strip ("Continue in *Course*: *Item*") above assignments; `announcements` list (title, course, date) |

### 8.2 Tabs (`CourseTabs`)

Staff: `Modules`, `Pages`, `Files`, `Announcements` always (general courses) and in ORT courses too (additive; nothing ORT-specific moves). Students: `Modules` when `features.modules`, `Files` when `features.files`, `Announcements` when `features.announcements`; `Pages` never (pages are reached from modules or home). So an ORT student's tab bar is unchanged until a teacher publishes structure.

### 8.3 i18n groups (en/ky/ru, parity script)

`modules.*` (states, reasons, requirement texts with `{threshold}`, warnings, editor labels, confirm texts incl. re-apply), `pages.*`, `courseFiles.*`, `announcements.*`, `courses.homeKind.*`, `home.modulesNext.*`, `home.announcements.*`, `errors.module_locked`, `errors.course_files_quota`, `errors.prerequisite_order`. Glossary: "module" = ky "модуль", ru "модуль"; "page" = ky "барак", ru "страница"; "mark as done" = ky "аткарылды деп белгилөө", ru "отметить как выполненное".

### 8.4 Mobile

375 px: outline editor uses buttons, not drag; item rows are one line + meta line; lock reasons wrap; file rows stack; preview below the editor; dialogs full-height. Long ru/ky labels tested per UX §5.

---

## 9. Slices, ownership, order, models

Branches `phase-8a-s<n>-<name>` off the phase branch `phase-8a` (from `phase-7c`/`lms` once 7c is deployed). Delimited blocks `# --- Phase 8a S<n> begin/end ---` in shared files. The orchestrator merges and reviews every diff.

| Slice | Model | Scope | Owns (exclusive) |
|---|---|---|---|
| **S1** migration + models + shapes (alone; early push) | opus | §2, `ids.py` of each package, `schemas.py` of each package (full shapes of §7 so S2–S4 code against them), empty `*_POLICIES` dicts + inventory block, `A.PROGRESS_RECORD`, `LOCK_HOME_KIND`/`LOCK_GATING`/`default_home_kind`/`default_structure` on `CourseTemplate` (ORT: `ALL_LOCK_FIELDS` grows, so both new locks apply), `CourseStudentOut.home_kind/home_page_id/features` (features computed `False` until S3), models registration, config keys, `test_migration_0012.py`, support fixtures | `alembic/versions/0012_phase8a_course_structure.py`, `app/lms/{modules,pages,course_files,announcements}/{__init__,models,ids,schemas,policies}.py`, blocks in `courses/{models,schemas}.py`, `templates/{base,ort,general}.py`, `core/{authz,config,route_inventory}.py`, `app/lms/models.py`, `tests/test_migration_0012.py`, `tests/lms/modules_support.py` |
| **S2** modules + gating backend | opus; **architect (fable) reviews `evaluator.py`, `gate.py`, `facts.py` before merge** | §5.2, §6, §7.1: service, evaluator, facts, gate, router mount, `touch_*` hooks in `assignments/service.py`, gate calls in `attempts/engine.py::start`, `handins.hand_in`, `assignments.service.mine/student_detail`, `progress_limit`, all §10 gating tests incl. PG | `app/lms/modules/{service,evaluator,facts,gate,router}.py`, `modules/policies.py` (fills), blocks in `assignments/{service,handins}.py`, `attempts/engine.py`, `core/ratelimit.py`, `api/v1/router.py` (one line), `tests/lms/test_modules_{api,gating,gate_enforcement,prerequisites,reorder,isolation,serializers}.py`, `tests/lms/test_pg_concurrency_modules.py` |
| **S3** pages, files, announcements, home backend | opus | §5.1, §5.3–5.5, §7.2: render pipeline + golden, pages CRUD and variants, course files (quota, download URL, sweep), announcements, `update_course` home block, `features`, `/me/home` additions, `touch_pages/files` calls (functions defined by S2 in `gate.py`; S3 imports them, stub returns until S2 lands) | `app/lms/pages/{render,service,router}.py`, `course_files/{service,router}.py`, `announcements/{service,router}.py`, their `policies.py` (fill), block in `courses/service.py`, `home/{service,schemas}.py`, `api/v1/router.py` (own block), `requirements.txt` (markdown, nh3), `tests/lms/test_pages_{api,render,variants}.py`, `test_course_files.py`, `test_announcements.py`, `test_course_home_kind.py`, `test_me_home.py` (update), `tests/fixtures/page_render_golden.json` |
| **S4** frontend | opus (sonnet for i18n and the files/announcements lists) | §8: all routes, components, API clients, tabs, home switch, student home strip, i18n; `tsc` + build | `app/[lang]/courses/[courseId]/{modules,pages,files,announcements}/**`, `app/[lang]/courses/[courseId]/page.tsx`, `components/lms/{modules,pages,courseFiles,announcements}/**`, `components/lms/{CourseTabs}.tsx`, `components/lms/home/{StudentHome,StudentCourseHome}.tsx` (blocks), `components/lms/course/StaffCourseHome.tsx` (link block), settings page block, `lib/lms/{modules,modulesTypes,pages,pagesTypes,courseFiles,announcements}.ts`, `lib/lms/types.ts` (additive), `lib/lms/home*.ts` (additive), i18n groups §8.3 |
| **S5** integration + gates | orchestrator + ux-reviewer (fable) + architect security review (fable) | contracts frontend ⇔ backend, walkthrough §11, full suites SQLite + PG, `alembic check`, ORT review §13, UX gate §12, `/security-review` (sanitizer bypass attempts, gate bypass by URL, IDOR on progress/files, presigned URL scope, quota), i18n parity, `next build` (rsync copy), `docs/phases/PHASE_8A.md`, `PRODUCT_DECISIONS.md` (P8A-*), handoff + memory | docs, `docs/phases/PHASE_8A_screens/**`, `frontend/e2e/modules.spec.ts` |

**Order**: S1 alone. Then S2 ∥ S3 ∥ S4: S4 codes against S1's schemas with mocks until S2/S3 land; S2 and S3 share no file because **S1 creates `modules/gate.py` with the three `touch_*` functions as no-op stubs and `require_access` raising `NotImplementedError`**, S3 imports them, S2 fills them. S5 last. If capacity allows, S4 splits into S4a (modules, home, tabs) and S4b (pages, files, announcements) with the ownership lines above.

**Gates per slice**: SQLite suite green; route-inventory test; action × role × status table tests for every new route; isolation tests; serializer contracts; `tsc --noEmit` (S4). **Phase gates (before `lms`, again before `main`)**: SQLite and PG suites, `alembic upgrade head && alembic check`, `test_migration_0012.py` both engines, PG concurrency, ORT review §13, UX gate §12, security review, i18n parity, `next build`, migration rehearsal on a production copy, **Neon backup branch before the `main` merge** (models and migration change), `/health` shows the commit.

---

## 10. Tests (`backend/tests/lms/`, scratch SQLite + PG parity)

- `test_migration_0012.py`: up/down/up both engines; existing courses `home_kind = 'assignments'`; downgrade refused with data.
- `test_modules_api.py`: CRUD, caps, dense positions after delete/restore, `order_incomplete`, cross-course targets 404, header without requirement, `requirement_kind_mismatch`, `url_invalid`, `create_quiz_item` returns an editable 7c quiz (and 409 `template_locked` for ORT presets).
- `test_modules_prerequisites.py`: same course, earlier only, self, deleted; `reorder` that would invert a pair → 422 and nothing changes; chain completion.
- `test_modules_gating.py` (table-driven over §6.3): every requirement type × `all|any`, sequential positions, `unlock_at` boundary and crossing, unpublished/deleted targets and prerequisites, released vs unreleased grades, excused, regrade does not relock, re-apply relocks (course and module scope), `mark_done` undo, empty module, cache hit (query count asserted with a counter: second view issues no writes), `rules_version` bump on each write path, staff bypass.
- `test_modules_gate_enforcement.py`: locked quiz start → 423 with published-only details; hand-in 423; page GET 423; file download 423; same quiz in two modules; content outside modules ungated; **ORT preset exam never 423 even inside a locked module** (`LOCK_GATING`).
- `test_pg_concurrency_modules.py`: two sessions record `view`+`done` for one student (converges, no lost `met`); concurrent teacher edit + student view (student's cache is invalid next time); `reapply` under load.
- `test_modules_isolation.py`, `test_modules_serializers.py`: cross-course/org 404s, student payload allow-list, org admin shape.
- `test_pages_render.py`: golden output; `<script>`, `javascript:` href, `onerror=`, `data:` img, external img, raw HTML, 100 KB+ body, KaTeX source survives as text; `test_pages_api.py`, `test_pages_variants.py` (resolution order, group language unique, cross-course group 404).
- `test_course_files.py`: PDF magic, 10 MB, `course_files_quota`, `storage_full` 507 via guard, dedup shares blob and delete keeps it while referenced, download URL shape and gate, folder validation.
- `test_announcements.py`: draft/publish/pinned ordering, student list, `/me/home` strip allow-list.
- `test_course_home_kind.py`: transitions, `home_page_invalid`, page delete resets, ORT 409 `template_locked`, new general course defaults to `modules`, ORT seed courses stay `assignments`.
- Updates: `test_me_home.py`, `test_serializer_contracts.py`, `test_ort_seed.py` (ORT courses have no modules/pages and `home_kind = 'assignments'`).

---

## 11. Walkthrough (S5; dated in `PHASE_8A.md`)

Teacher: create a general course → three modules (M1 page + PDF, M2 quiz made with "New quiz" in the 7c editor with `min_percent 80`, M3 prerequisite M2, sequential) → publish → student: M1 open, M2 open, M3 locked with the reason; start the quiz by URL while M2 is locked by `unlock_at` → 423 message; score 70 % released → M3 still locked; retake 90 % → M3 opens; teacher regrades to 60 % → M3 stays open; "Re-apply rules" → M3 locks; announcement posted → appears on the student home; course home switched to `page`. Then the ORT walkthrough of §13.

---

## 12. UX gate screens (`docs/phases/PHASE_8A_screens/`, 375 px + 1440 px; student screens en/ky/ru, teacher ru)

Student: course home `modules` (with and without content), modules list (locked/unlocked/started/completed, lock reasons, celebration), page view (KaTeX, variant switcher), files list, announcements list, student home with `modules_next` + announcements, 423 state on a quiz lobby card. Teacher: outline editor (empty, filled, warnings), module settings dialog, prerequisite picker, requirement picker, add-item menu, progress drawer, page list + editor + preview, files upload dialog + quota, announcement compose, settings "Course home". ORT: teacher course tabs and student course home before/after (expected identical for students).

---

## 13. ORT review plan (nothing changes in ORT behaviour; proofs)

Why nothing changes: `home_kind` is locked to `assignments` on ORT courses (`LOCK_HOME_KIND` in `ALL_LOCK_FIELDS`, 409 on change; the seed writes `assignments`); ORT preset exams are never gated (`is_locked(course, LOCK_GATING, preset)` → `require_access` returns; a teacher may still list the exam in a module as a link; the player, lobby, timing, scoring never see 8a code); student tabs appear only with content; importers, `build_snapshot`, engine, `OrtResultView` untouched; `CourseStudentOut` gains additive fields with defaults.

| Proof | How |
|---|---|
| Imports identical | `test_ort_import_golden.py`, `test_import_*` green; `git diff --stat <base> -- backend/app/lms/content/importers/` empty |
| Scores, flow, seed | `test_ort_parity.py`, `test_ort_e2e_api.py`, `test_ort_cutover_flow.py`, `test_ort_gradebook_golden.py`, `test_ort_seed.py` (+ home kind and no structure assertions) green |
| Gate never touches ORT | `test_modules_gate_enforcement.py::test_ort_preset_never_locked`; `test_course_home_kind.py::test_ort_home_locked` |
| Player, builder, bank | `frontend/e2e/ort.spec.ts` unchanged and green; `ort-visual.spec.ts` against `docs/phases/ORT_BASELINE/` with zero expected diffs (staff tab bar gains tabs: if a baseline includes the course tab bar, re-baseline with before/after in the PR as a look update) |
| Walkthrough | CSV + zip upload, build an ORT exam, take it, see the result, in an ORT course that also has one published module with a PDF; the exam card and Start flow identical |
| Report | `PHASE_8A.md` ORT section: test names, diff check, walkthrough date, screenshots |

---

## 14. Decisions taken here (to `PRODUCT_DECISIONS.md` as P8A-1 … when applied)

| # | Decision |
|---|---|
| P8A-1 | Submit/score facts are read from `submissions`, not duplicated in `item_progress` (§2.7); `submissions.updated_at` invalidates the cache. |
| P8A-2 | Pages and announcements are **Markdown** (`body_md`) rendered and sanitized **on the server** (`markdown` + `nh3`, allowlist §5.1) into `body_html`; KaTeX runs client-side on text; images only from our media/R2 host. No block editor, no client-side sanitizer. |
| P8A-3 | The gate is enforced on the target routes (page, file download, assignment detail, hand-in, attempt start) with 423 `module_locked`; content not in any module is ungated; the same target in several modules is open if any one is. |
| P8A-4 | Course-wide evaluation per enrollment in position order (≤ 7 queries), monotone states, lazy `rules_version` invalidation, no jobs; "re-apply rules" is the only relock. |
| P8A-5 | Prerequisite/order violations are 422, never silently dropped; unpublished or deleted prerequisites are skipped with a staff warning. |
| P8A-6 | `course_files` are PDF-only `assets` (private, 10 MiB) with a per-course `COURSE_FILES_MAX_BYTES` 500 MiB default and the platform free-tier guard; folders are path strings. |
| P8A-7 | New general courses default to `home_kind = 'modules'` (student view falls back to today's layout while no module is published); existing courses and ORT courses stay `assignments`; ORT locked. |
| P8A-8 | Student tabs `Modules/Files/Announcements` appear only when published content exists; staff always see them. |
| P8A-9 | No email for announcements in 8a; `/me/home` shows the latest three. |

---

## 15. Alternatives to discuss (owner; none blocks, each has a default in effect)

| # | Question | Options | Default |
|---|---|---|---|
| **Q1** | **Gating the ORT exam.** A teacher could want "finish the rules page before the ORT exam". Enforcing it changes how students reach the exam (rule A: exam behaviour), so 8a never locks ORT preset exams; the exam may still be listed in a module. | (a) never gated (built); (b) allow module locks on ORT exams (one lock-scope line: remove `LOCK_GATING` from the ORT template). | **(a)** |
| **Q2** | **Default home for new general courses.** | (a) `modules` with fallback to today's layout while empty (built); (b) `assignments` as today, teachers switch in Settings. | **(a)** |
| **Q3** | **Page format.** Markdown with server-side sanitizing (built) vs a block editor (richer UI, more frontend work, no new deps) vs HTML WYSIWYG (needs a client editor and a second sanitizer). | (a) Markdown; (b) blocks; (c) WYSIWYG. | **(a)**; (b)/(c) could replace the editor later since `body_html` stays the rendered contract. |
| **Q4** | **Course files budget.** 500 MiB per course of PDFs inside the 10 GB free tier (about 20 full courses before the platform guard refuses). | (a) 500 MiB (built, config); (b) lower; (c) pay for R2 beyond the free tier (owner's spending call). | **(a)** |
| **Q5** | **Homework-style modules in ORT courses** (pages, PDFs, announcements are additive and allowed; 7a Q5 keeps non-quiz assignments out of ORT courses). | (a) allow pages/files/announcements/modules in ORT courses, exam untouched (built); (b) hide the whole structure feature in ORT courses. | **(a)** |
