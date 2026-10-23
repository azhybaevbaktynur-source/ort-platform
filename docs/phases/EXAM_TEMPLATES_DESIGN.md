# Exam template constructor: evaluation and design (architect, 2026-10-24)

**Status**: evaluation for the owner's review; no code. Source: owner brief 2026-10-24 #2 ("New feature: an exam template constructor"). Related: `docs/phases/PHASE_6_DESIGN.md` §5 (course templates), `docs/LMS_ARCHITECTURE.md` §2b, §5, §6, `docs/IMPLEMENTATION_PLAN.md` Phases 7b and 8b (proposed placement), `docs/PRODUCT_DECISIONS.md` "Owner decisions 2026-10-24 (second round)". ORT stays one special fixed template exactly as today and is **not** rebuilt on the constructor (owner decision); §8 lists what the constructor would need to express ORT, for a later decision.

Every file and symbol named below was checked against the code on branch `lms` at the time of writing; "today" means that code.

---

## 1. Verdict in short

The idea holds up. Almost every building block the constructor needs already exists as data or as a registry; what is missing is (a) a place to **store a reusable exam structure** separately from a concrete assessment, (b) a **general import format** that is validated against such a structure, and (c) two player features that do not exist today (a scrolling display mode, a selectable result view). Nothing in the proposal conflicts with the ORT rule: ORT exams keep the `preset` path and never reference an exam template.

| Part | Exists today | New | Size |
|---|---|---|---|
| Sections in order with name, time limit, type rules, passage rule | `assessment_sections(position, key, title, time_limit_s, rules{allowed_types, max_items, allow_passages})`, validated by `assessments/rules.py::normalize_rules`, enforced at item add and publish (`builder.py:165`, `snapshot.py:145-228`) | Store them in a **template version** and copy them into a new assessment; add `min_items` | S |
| Navigation free / forward-only | `assessments.navigation` CHECK `free|section_forward_only`; engine `attempts/engine.py::_navigation`, per-section payloads (`assessments/cache.py`) | Template default only | – |
| Display mode one-per-page / scrolling | Player renders exactly one `ItemView` for the current item with Prev/Next, arrow keys and the palette (`PlayerShell.tsx:325, 471-473, 576-606`) | `display_mode` column + snapshot key + a scrolling list in the player | S backend, M frontend |
| Allowed question types per section | `rules.allowed_types` ⊆ `content/types/__init__.py::TYPE_NAMES` (7 types) | – | – |
| Passage options (line numbers) | `NumberedPassage` is used everywhere today; Phase 6a puts `passage_display plain|numbered` on the **course** template (`PHASE_6_DESIGN.md` §5.3) | Same option on the exam template (template wins over course default) | S |
| Scoring points / percent / lookup | `grading/params.py::SCHEME_TYPES = points, percent, bands, pass_fail, piecewise_curve, lookup_table`; immutable `grading_scheme_versions`; `assessments.grading_scheme_version_id` | Template stores a scheme **version** id | – |
| Result view | Chosen implicitly: `ResultSummary.tsx:14` shows `OrtResultView` whenever `grade.sections` is non-empty; 6a changes that to the course template's `result_view` | Explicit `result_view` key on the template, copied to the snapshot; registry of view keys | S |
| Import format generated from the template | ORT CSV/zip importer only (`content/importers/*`, 15 fixed columns `ort_csv.py::BUNDLE_COLUMNS`, ORT section aliases); a general format was planned for Phase 9 (Alternatives A12) | **General format** (all 7 types) whose accepted sections/types/columns are **derived from a template version**; a downloadable header and example per template | M |
| Pluggable blocks | Question types (`content/types/REGISTRY`), scheme types (`grading/params.py::PARAM_MODELS`, `grading/registry.py::apply`) are registries already | A block **catalog endpoint** and frontend maps for result views, passage renderers, display modes | S |
| Versioned templates, running exams keep their version | `assessment_versions.snapshot` is immutable and attempts reference `assessment_version_id` only | `exam_template_versions` immutable; assessments store `exam_template_version_id`; attempts need nothing new | S |
| Owners platform / organization / teacher | Organizations arrive in 6a (`organizations`, `organization_members`) | `owner_scope` + owner columns on `exam_templates`; visibility rules | S |
| Lockable | `preset_rule_locked` for ORT presets (`builder.py:168,197`); 6a adds `templates.service.assert_not_locked` for the course template lock | Same helper reads the exam template's lock scope | S |
| Visual builder for teachers | Assessment builder UI (sections, items, settings) exists | A **constructor UI** (sections, blocks, preview, versions, publish, lock, scope) | L |

Total: roughly **M (data model + API + import format) + L (visual builder) + M (scrolling display mode and result-view registry)**, in two releases as the owner suggested (data model first, builder later). Details and the phase placement in §9.

---

## 2. Terms: course template vs exam template

| | **Course template** (Phase 6a, `app/lms/templates/`, code registry) | **Exam template** (this document, database rows) |
|---|---|---|
| What it describes | The whole course kind: which assessment presets and importer profiles are available, section vocabulary (`section_keys`), passage display default, result view default, lock scope, seed, default settings | One exam's structure: ordered sections with rules and timers, navigation, display mode, passage display, scoring scheme version, result view, importer profile, attempt-setting defaults, lock scope |
| Where it lives | Code (`CourseTemplate` dataclass; `ort`, `GENERAL`) | Rows: `exam_templates` + immutable `exam_template_versions` |
| Who creates one | A release (new Python module) | Platform admin, org admin, teacher, in the constructor or by "save as template" |
| Referenced by | `courses.template_key/template_version` | `assessments.exam_template_version_id` |
| ORT | `ort` course template wraps today's ORT code (presets `ort_main`, `ort_subject`, ORT importer profiles, ORT schemes, `OrtResultView`, numbered passages) | **None.** ORT assessments are created through the `preset` path exactly as today and have `exam_template_version_id = NULL` |

**How they nest.** A course template may declare `exam_template_keys` (platform-owned exam templates it offers by default in its courses) and `assessment_presets` (today's code presets). A general course (no course template) offers: the platform exam templates, the organization's exam templates, the teacher's own, plus "blank assessment" (today's `preset = none`). A course with the `ort` template offers today's `ort_main`/`ort_subject` presets, and in addition the same general exam templates as everyone else (ORT teachers can also give a plain quiz). Nothing about the ORT presets changes.

Sanity rule for implementers: **`preset` and `exam_template_version_id` are mutually exclusive** (`CHECK (preset = 'none' OR exam_template_version_id IS NULL)`), so the ORT path and the template path can never mix on one assessment.

---

## 3. Data model (proposal; names are to be used as written)

Migration `00NN_exam_templates` (PostgreSQL + SQLite, no runtime ALTERs). Ids uuid; `users.id` is a string.

**exam_templates**

| Column | Type / constraint |
|---|---|
| id | uuid PK |
| owner_scope | varchar(16) NOT NULL CHECK IN (`platform`,`organization`,`teacher`) |
| organization_id | uuid NULL FK organizations.id RESTRICT; CHECK ((owner_scope = 'platform') = (organization_id IS NULL)) (an organization and a teacher template both carry the organization) |
| owner_user_id | varchar(64) NULL FK users.id RESTRICT; CHECK ((owner_scope = 'teacher') = (owner_user_id IS NOT NULL)) |
| key | varchar(64) NULL UNIQUE, `^[a-z0-9_]{2,64}$`; only platform templates seeded by code have one (none in v1; reserved for a possible future `ort_main` row, §8) |
| title | JSON LocalizedText NOT NULL |
| description | JSON LocalizedText NULL |
| status | varchar(16) NOT NULL CHECK IN (`draft`,`published`,`archived`) |
| locked | bool NOT NULL default false (new assessments created from a published version copy it as `structure_locked`) |
| current_version_id | uuid NULL FK exam_template_versions.id (the latest **published** version) |
| draft_spec | JSON NULL (the editable working copy; validated on every save; NULL when nothing is unpublished) |
| draft_rev | int NOT NULL default 0 (optimistic concurrency like `assessments.draft_rev`) |
| created_by_id, created_at, updated_at, deleted_at, deleted_by_id | as elsewhere |
| Indexes | `ix_exam_templates_scope_org` (owner_scope, organization_id, status), `ix_exam_templates_owner_user` (owner_user_id) |

**exam_template_versions** (immutable; a SQLAlchemy `before_update` listener raises like `ImmutableAssessmentVersionError` in `assessments/models.py:188`)

| Column | Type / constraint |
|---|---|
| id | uuid PK |
| template_id | uuid NOT NULL FK exam_templates.id RESTRICT |
| version_no | int NOT NULL; UNIQUE(template_id, version_no) |
| spec | JSON NOT NULL (the validated `ExamTemplateSpec`, §3.1) |
| spec_hash | varchar(64) NOT NULL (sha256 of the canonical JSON, like `snapshot.py::canonical_hash`) |
| grading_scheme_version_id | uuid NULL FK grading_scheme_versions.id RESTRICT (duplicated from `spec.scoring` so the FK protects the scheme version; `grading_scheme_versions` are already immutable once referenced) |
| published_at, published_by_id | timestamptz NOT NULL; FK users.id SET NULL |

**assessments** (new columns; the `preset` column and its CHECK stay)

| Column | Type / constraint |
|---|---|
| exam_template_version_id | uuid NULL FK exam_template_versions.id RESTRICT; `ix_assessments_exam_template_version_id` |
| display_mode | varchar(16) NOT NULL default `one_per_page`, CHECK IN (`one_per_page`,`scrolling`) |
| passage_display | varchar(16) NULL CHECK IN (`plain`,`numbered`) (NULL = the course template's default: `numbered` in ORT courses, `plain` otherwise) |
| result_view | varchar(32) NULL (NULL = the course template's default; `ort` in ORT courses, `general` otherwise) |
| structure_locked | bool NOT NULL default false |
| Constraint | CHECK (preset = 'none' OR exam_template_version_id IS NULL) |

Why columns and not only the spec JSON: the player and the results page read these three per assessment version, and the snapshot (`assessment_versions.snapshot`) copies them so running attempts never look back at the template (§3.3). Existing rows get the defaults; ORT rows read `NULL/NULL`, which resolve to today's behaviour through the course template.

### 3.1 `ExamTemplateSpec` (Pydantic, `app/lms/exam_templates/spec.py`, `extra="forbid"`)

```
{ "schema": 1,
  "navigation": "free" | "section_forward_only",
  "display_mode": "one_per_page" | "scrolling",
  "passage_display": "plain" | "numbered" | null,              // null = course default
  "result_view": "general" | "ort" | <registered key> | null,
  "importer_profile": "general" | null,                        // "ort" is reserved for the ORT course template (§8)
  "defaults": { "time_limit_s": null|int, "allowed_attempts": int, "score_policy": ..., "results_policy": ...,
                "show_correct_answers": bool, "shuffle_items": bool, "shuffle_choices": bool },   // editable on the assessment
  "sections": [ { "key": "^[a-z0-9_]{1,40}$" | null, "title": LocalizedText | null, "instructions": LocalizedText | null,
                  "time_limit_s": null|int (60..86400),
                  "min_items": null|int, "max_items": null|int,                                 // "question count": equal = exact
                  "allowed_types": [<TYPE_NAMES>] (non-empty, unique), "allow_passages": bool,
                  "passage_display": "plain" | "numbered" | null } ],                            // per-section override (ORT: reading only)
  "scoring": { "grading_scheme_version_id": uuid } | null,     // null = course default scheme (points)
  "parameters": [ { "key": "subject", "kind": "choice", "options": ["chemistry", ...], "binds": "sections[0].key" } ],
  "lock_scope": ["sections", "section_time_limit_s", "navigation", "display_mode", "rules", "scheme", "result_view", "importer_profile"] }
```

Validation reuses what exists: `allowed_types` through `assessments/rules.py::normalize_rules` (extended with `min_items`), `navigation`/`results_policy`/`score_policy` through the same literals as `assessments/schemas.py`, `grading_scheme_version_id` must exist and be visible to the template's owner (system schemes or the owner's), `time_limit_s` bounds identical to the `assessments` CHECKs, section limits must not exceed `defaults.time_limit_s` (same rule as `snapshot.py:107-112`: section timers only with `section_forward_only`). A `parameters` entry declares a value the teacher picks when creating the exam (ORT's "subject" is the motivating case, §8); v1 supports `kind: choice` binding to a section key only.

### 3.2 Creating an assessment from a template version

`POST /courses/{course_id}/assessments` (existing route, body extended): `{ title, languages, exam_template_id?, exam_template_version_id?, parameters?: {key: value} }`. Rules:

1. `preset` and `exam_template_*` are mutually exclusive (422). `exam_template_id` alone resolves to `current_version_id` (published; 422 `template_not_published` otherwise). A specific `exam_template_version_id` is allowed only for versions of a template the caller may use (so a teacher can pin an older version deliberately).
2. Visibility (`exam_templates/policies.py::visible_to(ctx, course)`): platform templates (status `published`) → everyone; organization templates → staff of courses in that organization; teacher templates → the owner in any course they staff. One SQL scope `exam_templates_visible_to(user_id, course)`; never `can()` in a loop.
3. The service (`exam_templates/service.py::instantiate(db, ctx, course, version, parameters)`) writes in **one transaction**: the `Assessment` row with `navigation`, `display_mode`, `passage_display`, `result_view`, `grading_scheme_version_id` (from the version's FK column), the `defaults`, `exam_template_version_id`, `structure_locked = template.locked`, `preset = 'none'`; then one `AssessmentSection` per spec section (position, key, title, instructions, time_limit_s, `rules = {allowed_types, allow_passages, max_items, min_items}`), with `parameters` applied to bound fields. This is the same shape as `builder.py::create_assessment` lines 78-84 produce for ORT presets; the preset branch is left as is.
4. Lock enforcement reuses the 6a helper `templates.service.assert_not_locked(course, field)` extended to `assert_structure_unlocked(assessment, field)`: when `structure_locked` and `field ∈ version.spec.lock_scope` → 409 `template_locked`. Editable regardless of lock: items, points, banks, title, description, availability, `allowed_attempts`, `score_policy`, `results_policy`, `show_correct_answers`, `shuffle_*`, grade release (the same editable list as `PHASE_6_DESIGN.md` §5.4).
5. `min_items`/`max_items` become publish issues (`too_few_items` new, `too_many_items` exists at `snapshot.py:249`), never hard errors at item add, so a teacher can build incrementally.
6. "Upgrade to the latest template version" is an explicit action on a **draft without attempts** only (`POST .../assessments/{id}/template-upgrade`): it rewrites the structure rows and `exam_template_version_id`; items that violate the new rules are reported as issues. Published assessments and anything with attempts never move.

### 3.3 Versioning semantics with snapshots and attempts

- Editing a template edits `draft_spec`; **publish** validates it, inserts `exam_template_versions(version_no = last + 1)`, sets `current_version_id`, clears `draft_spec`. Versions are never edited or deleted (RESTRICT everywhere; archiving a template hides it from pickers only).
- An assessment stores the **version** id. Publishing an assessment (`publish.py`) copies into `assessment_versions.snapshot` the keys `exam_template_version_id`, `display_mode`, `passage_display`, `result_view` next to the existing `navigation` and `sections`. The attempt engine and the player already read only the snapshot (`engine.py::plan_for`, `cache.py::get_plan`), so **running exams keep their version** without any new table; even deleting the template later would not reach an attempt.
- A later template version changes nothing for existing assessments; teachers see a small "a newer version of this template exists" note on drafts (no automatic change).
- Locks: `structure_locked` is copied at creation; unlocking a template later does not unlock existing assessments (an org admin unlocks a single assessment explicitly, audited), and locking a template later does not lock drafts already created from it. This keeps the rule "what an exam does never changes behind the teacher's back".

### 3.4 Scope, sharing, organizations, assignments, modules

- **Organizations (6a)**: an organization template is created by an org admin or by a teacher of the org with `settings.teachers_can_publish_org_templates` (new org setting, default false; otherwise the teacher's template stays `teacher` scope and an org admin can "promote" it to organization scope, audited). Personal organizations (A1) make this uniform: an independent teacher's "organization" templates are visible to the courses in their personal org only, and bank/template sharing between independents is impossible by construction.
- **Platform templates**: created by platform admins; visible to all. No grant table in v1 (a granted-only exam template is listed under alternatives, §10 B4).
- **Assignments (Phase 7)**: the "create quiz assignment" dialog offers "from template" and calls the same `instantiate`; the assignment row (`kind quiz`, `assessment_id`) is written in the same transaction. Due dates, points and overrides live on the assignment, never on the template.
- **Modules (Phase 8)**: module items reference assignments; a template could later declare a default module layout, but this is a course-template concern (`CourseTemplate.seed`), not an exam template's. No change.
- **Course copy**: copying a course keeps `exam_template_version_id` on the copied assessments (same version), so copies stay comparable.

---

## 4. Building-block registry and "appears in the constructor"

| Block kind | Registry today | v1 contract |
|---|---|---|
| Question types | `content/types/__init__.py::REGISTRY` (name → `QuestionType` with `validate`, `student_view`, `score`, `image_refs`); frontend editors and `ItemView` branches per type | Add to each type: `title_key` (i18n), `supports_passages: bool`, `import_columns: tuple[str, ...]` (§5). New type = new Python class + frontend editor/player branch + i18n keys. **No constructor change**: the constructor reads the catalog. |
| Scoring rules | `grading/params.py::SCHEME_TYPES` + `PARAM_MODELS`; `grading/registry.py::apply`, `apply_sections`; scheme versions are rows | Constructor offers **scheme versions** the owner may use (system schemes + own + org, Phase 9 sharing), not raw types. A new rule type = new params model + `apply` branch + editor form; it shows up in the scheme editor and thus in the constructor. |
| Result views | Implicit (`ResultSummary.tsx:14`) | `RESULT_VIEWS = {"general", "ort"}` in backend `exam_templates/blocks.py` (validation only) and a frontend map `resultViews[key] → component` (`OrtResultView`, general `GradeBadge` + sections table). A new view = one component + one key in both lists. |
| Passage renderers | `NumberedPassage`; 6a adds `PlainPassage` | `PASSAGE_DISPLAYS = {"plain", "numbered"}`; frontend map. |
| Display modes | Only one-per-page | `DISPLAY_MODES = {"one_per_page", "scrolling"}`; player switch (§6). |
| Navigation | `free`, `section_forward_only` (engine) | Unchanged list. |
| Importer profiles | `ort` (CSV + zip, `exam_type` values `full_main|subject|practice_bank`) | `IMPORTER_PROFILES = {"general", "ort"}`; `ort` selectable only through the ORT course template (§5, §8). |

`GET /exam-templates/blocks` (authenticated) returns the catalog: for each kind, the keys with their i18n title keys and capabilities (e.g. which types allow passages, which scheme versions the caller may pick). The constructor UI builds every pick list from this response and never hard-codes a key. "Appears in the constructor" therefore means: registered on the backend (validation + catalog) **and** mapped on the frontend (how to render it). A block that exists only on one side is rejected by a contract test that compares the catalog with the frontend maps (`frontend/src/lib/lms/blocks.ts` exports the same key lists; a pytest reads the TS file's literal arrays, like the i18n parity script reads JSON).

---

## 5. Import format derived from a template version

**Principle (recommendation, see §10 B3)**: one **general** CSV/zip format for all 7 question types; a template version does not create a new file format but a **validation profile** and a **downloadable header + example** over that one format. A file valid for a template is a valid general file, and the same general file can be imported into a different template if its sections and types fit.

General format v1 (`content/importers/general_csv.py`, manifest `format: "lms-bundle"`, distinct from the ORT bundle's `format` value so the two can never be confused):

| Column | Rule |
|---|---|
| `section` | required when the target has sections; must be one of the template's section keys (or the exact section title); free label without a template |
| `type` | one of `TYPE_NAMES`; may be omitted when the section allows exactly one type (then filled in) |
| `stem`, `explanation`, `topic`, `difficulty`, `tags`, `image`, `external_id` | as in the ORT format where the names coincide (`image_url` accepted as an alias of `image`) |
| `option_a..option_e`, `correct_option` | `single_choice`, `multiple_answers` (several letters), `true_false` (A/B) |
| `column_a`, `column_b`, `correct_option` A–D | `comparison` (same validation as `importers/rules.py::math_section_rule_error`, reused) |
| `answer`, `tolerance`, `answer_min`, `answer_max` | `numeric` |
| `answers` (`|`-separated accepted forms), `case_sensitive` | `short_text` |
| `rubric`, `max_points` | `essay` |
| `passage_text` or `passage_ref` (an `external_id#passage`) | only in sections with `allow_passages` |

Derivation `exam_templates/import_format.py::format_for(version) → ImportFormatOut`: the set of allowed sections (keys + titles), per section the allowed types, the **union of `import_columns`** of those types, whether `passage_text` appears, and the counts (`min_items`/`max_items`) shown as guidance. `GET /exam-templates/{id}/versions/{no}/import-format` returns it as JSON and `?download=csv` returns a UTF-8 CSV with the header row and one commented example row per section (ky/ru/en column comments come from i18n). Validation at upload: `POST /courses/{id}/import` gains `exam_template_version_id` (optional) or `assessment_id` (derives the version from the assessment); the general importer rejects `section` not in the set, `type` not allowed in that section, passages in sections that forbid them, and reports counts against min/max as warnings. The result is still a **bank** (one bank per source as today); an optional `attach_to_assessment_id` adds the imported questions into the matching sections as items in the same transaction (this is the "upload against the template" the owner describes).

**ORT importer**: `content/importers/{ort_csv,bundle,rules,schemas,service}.py` stay byte-for-byte (A10 alias fix excepted). `ImportOptions.exam_type` keeps selecting the ORT profile; the general profile is a separate code path behind one dispatch in `importers/service.py` (`profile = "ort" if opts.exam_type else "general"`). Golden fixtures (`PHASE_6_DESIGN.md` §6) prove ORT imports unchanged every phase.

---

## 6. Display mode: one question per page vs scrolling

**Today** (`PlayerShell.tsx`): state holds `currentPos`; the page renders one `ItemView` for the current item (line 576), Prev/Next buttons (596, 606), ArrowLeft/ArrowRight and `F` for flag (471-473), the `Palette` jumps by position, and in forward-only navigation the visible items are filtered to `current_section_pos` (line 79) because the content payload is per section (`cache.py`). Autosave is per item (`autosave.ts` queue). There is no scrolling mode anywhere; ORT is one-per-page and stays so.

**New** (`display_mode = scrolling`): the same `visibleItems` are rendered as a vertical list of `ItemView`s with their passage panes; "current item" becomes the item most visible in the viewport (IntersectionObserver) so the palette highlight and keyboard shortcuts keep working; Prev/Next scroll instead of switching; the section-end dialog and submit dialog are unchanged; autosave is unchanged (per item on change). Performance guard: lists longer than 60 items render in windows of one section or 30 items with "load more" (6,000 students loading a 150-item scroll page at once is the capacity case to avoid). Nothing changes on the server beyond the column and the snapshot key; the engine never cares how items are displayed. Cost: **S backend, M frontend** (player branch + palette sync + Playwright test + baselines for the general player, not the ORT baselines).

---

## 7. API surface (v1, listed in `route_inventory.py` with policies)

| Method, path | Policy |
|---|---|
| GET `/exam-templates?scope=&organization_id=&course_id=` (visible templates, paginated) | authenticated |
| POST `/exam-templates` (owner_scope, organization_id, title; creates a draft) | `exam_template_create` (platform admin for `platform`; org admin or allowed teacher for `organization`; any course-creating teacher for `teacher`) |
| GET/PATCH `/exam-templates/{id}` (draft_spec with `draft_rev`), POST `.../publish`, `.../archive`, `.../lock`, `.../unlock`, `.../promote` (teacher → organization) | `exam_template_manage` (owner, org admin of its org, platform admin); lock/unlock/promote audited |
| GET `/exam-templates/{id}/versions`, GET `.../versions/{no}`, GET `.../versions/{no}/import-format[?download=csv]` | `exam_template_read` |
| GET `/exam-templates/blocks` | authenticated |
| POST `/courses/{id}/assessments` (body gains `exam_template_id`, `exam_template_version_id`, `parameters`) | existing `course:content.manage` |
| POST `/courses/{id}/assessments/{aid}/save-as-template` (§10 B2) | `course:content.manage` |
| POST `/courses/{id}/assessments/{aid}/template-upgrade` | `course:content.manage` + draft without attempts |
| POST `/courses/{id}/import` (gains `exam_template_version_id` / `assessment_id`, `attach_to_assessment_id`) | existing |

Tests that must exist: spec validation table (every field, bounds, mutual exclusions); instantiate = exact rows (compare with a hand-built assessment); lock matrix (locked field × action → 409, editable field → 200); visibility matrix (platform/org/teacher × caller × course org); version immutability (update raises); publish bumps version and leaves created assessments untouched; snapshot carries the four keys; attempt on an assessment whose template was later re-published and archived still runs; import-format derivation per template; general importer rejects wrong section/type/passage; scrolling player Playwright; `preset`/`exam_template` exclusivity; ORT parity gate green with the new columns at defaults (**no ORT fixture changes**).

---

## 8. What the constructor would need to express ORT exactly (later decision; nothing changes now)

| ORT fact today | Expressible with the v1 spec? | Gap / design choice taken now |
|---|---|---|
| Five sections in order `math_1 45, math_2 45, analogies 30, reading 60, grammar 35` minutes (`rules.py::ORT_MAIN_SECTIONS`) | Yes: `sections[].key/time_limit_s` | Keys are free strings; the ORT section vocabulary and its i18n (`sections.*`) already exist. |
| `math_1` comparison only; other sections `single_choice` only; passages only in `reading` (`ORT_SECTION_RULES`) | Yes: `allowed_types`, `allow_passages` | Identical rule objects to those the preset writes (`ort_rules(key)`), so a dry-run comparison is exact. |
| Forward-only navigation with per-section timers; section payloads one at a time; close section server-side | Yes: `navigation = section_forward_only` + section timers (engine unchanged) | – |
| One question per page, palette, flags, LaTeX, comparison card | Yes: `display_mode = one_per_page` (default) | – |
| Line-numbered passages in reading only | Yes: `sections[reading].passage_display = numbered` | Today numbering is global in ORT courses (course template `numbered`); per-section override is included in the spec for this reason. |
| Defaults at creation: `allowed_attempts 1, score_policy highest, results_policy after_submit, show_correct_answers true` (`builder.py:71-75`) | Yes: `defaults` | These stay editable on the assessment, as today. |
| Scoring: `piecewise_curve` 60–245, mean 150 SD 30, exponents 1.05/0.95, `zero_raw {value 0, percentile 0.0}`, rounding half_even 0 decimals, `apply_to_sections true`, threshold `golden_certificate 219`; subject 60–150 mean 105 SD 20 (`grading/seeds.py::_ort`) | Yes: `scoring.grading_scheme_version_id = ORT_MAIN_V1_ID` (the same system version the preset uses) | The scheme is already data; the quirk lives in the version params, not in the template. Section scoring is a scheme param (`apply_to_sections`), so no template field is needed. |
| ORT result view (scaled, percentile, golden banner, per-section scaled values: `OrtResultView.tsx`) | Yes: `result_view = "ort"` | 6a makes the view an explicit key; the component is untouched. |
| Subject exam: one section whose key the teacher picks from `ORT_SUBJECT_KEYS` (`schemas.py:51`, `builder.py:80-81`), 60 minutes | Yes, with `parameters[kind=choice, binds=sections[0].key]` | **Gap closed by design**: without `parameters` ORT subject exams would need seven templates. |
| Question counts | ORT today enforces **no** per-section count (`max_items` unset) | `min_items`/`max_items` are optional, so "exactly as today" = both null. |
| CSV/zip format byte-compatible: 15 columns, section/option/difficulty aliases incl. Cyrillic, `math_1` column rule, bundle `manifest.json` with `format`, `source_id`, `external_id`, images | **Not** by the general format (aliases, Cyrillic option letters, `source_id` semantics are ORT-specific) | Design choice: `importer_profile = "ort"` is a **code building block** that the ORT course template (and a future ORT exam template) references. The generated-format machinery never has to accept today's ORT files; the ORT importer stays as the profile. This is why `IMPORTER_PROFILES` contains `ort`. |
| Preset lock (`preset_rule_locked`: section keys and types fixed) | Yes: `lock_scope` + `structure_locked` | 6a's `assert_not_locked` is the single enforcement point for both paths. |
| Seed: `ort/seed.py::ensure_ort_courses` creates the `ort_main` assessment through the preset | Not covered by the spec | Would need the seed to call `instantiate` with a code-seeded template row (`key = "ort_main"`): a seed change, not an exam change; part of the later decision. |
| `assessments.preset` CHECK and the `ort_*` values | – | Kept. If ORT ever moves, `preset` rows would be migrated to `exam_template_version_id` with a parity test over the resulting section rows. |

**Proof without switching (recommended for 7b, §10 B9)**: a test builds an `ExamTemplateSpec` from the ORT constants (`ORT_MAIN_SECTIONS`, `ORT_SECTION_RULES`, `ORT_MAIN_V1_ID`, the `builder.py` defaults), instantiates it in a scratch course, and asserts the resulting `assessments` + `assessment_sections` rows (minus ids and `preset`) equal those produced by `create_assessment(preset="ort_main")`, and the same for every subject key through `parameters`. It proves the constructor **can** express ORT while ORT keeps running on the preset path. The test lives beside the parity tests and is part of the ORT review from 7b on.

---

## 9. Cost and phase placement (recommendation)

| Part | Size | Proposed release |
|---|---|---|
| Tables, `ExamTemplateSpec`, instantiate, lock, visibility, versions, API (no UI beyond a JSON-form admin page), `save-as-template`, snapshot keys, ORT expressibility test | M | **Phase 7b** (after 7a assignments, because "create from template" should create the assignment too) |
| General import format + template validation + import-format descriptor and download + `attach_to_assessment` | M | **Phase 7b** (moves Alternatives A12 "general import format" from Phase 9 to here; shared banks stay in Phase 9) |
| Result view and passage display as explicit assessment columns; block catalog endpoint; frontend maps | S | 7b (backend) + 8b (UI) |
| Scrolling display mode in the player | S + M | **Phase 8b** |
| Visual constructor (sections editor, pick lists from the catalog, live preview with the real player, versions, publish, lock, scope/promote, import-format download) for platform admins, org admins and teachers | L | **Phase 8b** |
| Phase 7 "quiz assignment from template" dialog | S | 7a/7b boundary |

Why not 6a: 6a already carries the migration of ownership, authorization and the ORT wrap; the owner asked not to overload it. Why lettered sub-phases (7b, 8b) and not new numbers: Phases 9–11 are referenced by number in `PRODUCT_DECISIONS.md`, `LMS_ARCHITECTURE.md` and the handoff (shared banks 9, statistics 10, observer 11); lettering keeps those references true, mirrors 6a/6b, and each letter is still its own release with its own gates. Renumbering is listed as an alternative (§10 B10).

Dependencies: 7b needs 6a (organizations, `assert_not_locked`, `CourseOut.template`) and 7a (assignment row). 8b needs 7b and 6b (design system). The ORT review (parity + look) and the UX gate apply to both.

---

## 10. Alternatives to discuss (owner decides)

| # | Topic | Owner's version | Alternative | Pros / cons | Recommendation |
|---|---|---|---|---|---|
| B1 | Relation to today's presets | A separate constructor; ORT stays a fixed preset | Evolve `preset` into data: seed `ort_main`/`ort_subject` as platform exam-template rows and route `create_assessment` through `instantiate` | Pro: one mechanism. Con: changes the ORT creation path now, against the owner's rule; the gain is only internal. | **Not now.** Keep `preset` for ORT, templates for everything else, exclusivity CHECK; revisit at the "later decision" with the §8 test as evidence. |
| B2 | First authoring path | Visual constructor | **"Save this assessment as a template"** (one endpoint, S) in 7b: teachers design in the familiar builder, then save the structure as a draft template; the visual constructor comes in 8b | Pro: templates get used and proven months earlier at tiny cost; the constructor then edits the same spec. Con: a few template-only fields (`display_mode`, `min_items`) need a small form on save. | Adopt both: save-as-template in 7b, constructor in 8b. |
| B3 | Import format | A format **generated per template** that validates uploads | **One general format**; a template version derives a validation profile, a header and an example file (§5) | Pro: one parser to test; files move between templates; no per-template format zoo. Con: the header shows unused columns unless trimmed (we trim to the template's union). | One general format with template validation. |
| B4 | Who may use a platform template | Not specified | Platform templates visible to all (v1) versus grant per organization like the ORT course template | Grants add a table and admin UI; no known need (ORT is a course template with grants already). | Visible to all in v1; grants later if a template must be exclusive. |
| B5 | Teacher-owned templates | "maybe teacher (own courses)" | Include `teacher` scope in the model from day one (it is one column) with "promote to organization" by an org admin; the constructor UI for teachers is still 8b | Pro: save-as-template (B2) needs an owner anyway; personal orgs make independents' templates naturally private. Con: more rows to list and filter. | Include the scope in 7b. |
| B6 | Sections as rows or JSON | Not specified | JSON `spec` in the immutable version (mirrors `assessment_versions.snapshot` and scheme `params`), rows only on the concrete assessment | Pro: one validator, immutability for free, no join tables. Con: no SQL over template sections (nobody needs it). | JSON spec. |
| B7 | "Question count" | A count per section | `min_items`/`max_items` (equal = exact), checked at publish as issues | Pro: lets a teacher build incrementally; ORT stays "no count" exactly. | min/max. |
| B8 | Scrolling display mode timing | Part of the constructor | Add the column and snapshot key in 7b (so no second migration), build the player branch in 8b | Pro: 7b stays backend-only; the player change ships with its own baselines and UX gate. | Split as described. |
| B9 | ORT expressibility | "write down what the constructor would need" | Plus an automated **dry-run parity test** (§8) that instantiates ORT from a spec and compares the rows with the preset path, without switching ORT | Pro: the later decision rests on a green test instead of a document; drift is caught every phase. Con: one more test to maintain. | Adopt in 7b. |
| B10 | Phase numbering | Not specified | Lettered sub-phases 7b/8b versus renumbering to 8 and 10 and shifting 9–11 | Lettering keeps every phase-number reference in the docs true. Renumbering is cleaner on paper but touches five documents and the memory notes. | 7b/8b. |
| B11 | Template sharing between independents | Never share banks | Templates (structures only, no questions) **may** be platform-shared; organization templates of a personal org stay private like banks | A template holds no questions, so sharing one leaks nothing; the bank rule is untouched. | Platform templates shared, org/teacher templates private to their org. |
| B12 | ORT itself: keep "exactly as today" versus the smallest possible touch | Exactly as today | No alternative proposed: the §8 gaps are all closed by design choices that do not touch ORT code or files. | – | Keep. |

---

## 11. Open questions for the owner

1. Placement as 7b (data model, save-as-template, general import format) and 8b (visual constructor, scrolling mode): agreed, or renumber (B10)?
2. B2: is "save this assessment as a template" an acceptable first authoring path before the visual constructor?
3. B3: one general import format with template validation (recommended) or a generated file format per template?
4. B4/B11: platform exam templates visible to every organization without grants?
5. Should org admins be able to lock a template so that **teachers of the org** cannot change the exam structure (the same lock as ORT), or is locking a platform-admin power only? Proposal: the template's owner scope decides (org admins lock org templates; platform admins lock platform templates).
6. B9: run the ORT expressibility dry-run test from 7b on as part of the ORT review (no switch)?
