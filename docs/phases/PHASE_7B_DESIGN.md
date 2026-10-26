# Phase 7b design: exam templates I (data model, versions, create/save, general import format)

**Status**: architect draft 2026-10-26 (branch `phase-7b-design` off `origin/phase-7a` at bbbbc43). Implements `IMPLEMENTATION_PLAN.md` Phase 7b on top of the approved data model `EXAM_TEMPLATES_DESIGN.md` (§3 model, §3.1 spec, §3.2–3.4 semantics, §5 import format, §7 API, §8 ORT expressibility; owner answers §10–§11: B1 no, B2–B9 yes, locking by the template's owner). 7a is finished (`PHASE_7A_DESIGN.md`; `assignments/sync.py::ensure_quiz_assignment`, the "7b hook" in `assignments/service.py::_create_quiz`). Names in **bold code** are to be used exactly as written so parallel slices merge cleanly. Every file and line named below was checked against `phase-7a` at bbbbc43. Anything that would change ORT's behaviour is in §16, not decided here.

---

## 1. Scope and non-goals

**In**: tables `exam_templates` + immutable `exam_template_versions`; the four assessment columns + exclusivity CHECK; `ExamTemplateSpec` validation; drafts (`draft_spec`, `draft_rev`), publish, archive, lock/unlock/promote (audited); visibility scope; `instantiate` (assessment + sections + quiz assignment in one transaction); "save as template"; "upgrade to latest version" for drafts without attempts; snapshot keys; block catalog + frontend contract test; the **general import format** (`lms-bundle`) with validation against a template version and attach-to-sections; `GET .../import-format[?download=csv]`; the ORT expressibility dry-run test; a minimal frontend (create from template, save as template, plain JSON-form template page for platform/org admins and teachers, import-format download, import validation select); i18n group **`examTemplates`**.

**Out** (8b and later): the visual constructor, scrolling player (`display_mode` column and snapshot key only; the player ignores `scrolling` and renders one-per-page: `instantiate` refuses `display_mode = scrolling` with 422 `display_mode_not_available` until 8b so no student ever meets an unbuilt mode), version diff, preview attempts, template grants (B4), org settings UI (`teachers_can_publish_org_templates` is read, not editable, until Phase 9), shared banks. **ORT**: nothing changes (§12).

---

## 2. Schema and migration **`0010_phase7b_exam_templates`**

`down_revision = "0009_phase7a_assignments"`. Naming through `op.f(...)`, `JSONType = sa.JSON().with_variant(JSONB, "postgresql")`, SQLite through `op.batch_alter_table`, as in 0009. No data steps (every new column has a server default or is nullable), so **no bootstrap** is needed for SQLite (`create_all` reads the models). Models in **`app/lms/exam_templates/models.py`**, registered in `app/lms/models.py` (block `# --- Phase 7b S1 begin/end ---`).

### 2.1 `exam_templates` (EXAM_TEMPLATES_DESIGN §3, as written, with these fixings)

| Column | Type / constraint |
|---|---|
| id | uuid PK (uuid4; no deterministic ids in v1, no code-seeded rows) |
| owner_scope | varchar(16) NOT NULL CHECK IN (`platform`,`organization`,`teacher`) `owner_scope_valid` |
| organization_id | uuid NULL FK organizations RESTRICT; CHECK `(owner_scope = 'platform') = (organization_id IS NULL)` `org_matches_scope` |
| owner_user_id | varchar(64) NULL FK users RESTRICT; CHECK `(owner_scope = 'teacher') = (owner_user_id IS NOT NULL)` `owner_matches_scope` |
| key | varchar(64) NULL UNIQUE (`uq_exam_templates_key`); unused in v1 (reserved, §8 of the design) |
| title, description | JSON LocalizedText NOT NULL / NULL |
| status | varchar(16) NOT NULL default `draft` CHECK IN (`draft`,`published`,`archived`) |
| locked | bool NOT NULL default false |
| current_version_id | uuid NULL FK exam_template_versions SET NULL, **created with `use_alter=True`** (circular FK; Alembic: add the FK after both tables exist, as a named constraint `fk_exam_templates_current_version_id_exam_template_versions`) |
| draft_spec | JSON NULL |
| draft_rev | int NOT NULL default 1 (same convention as `assessments.draft_rev`, which starts at 1, not 0 as §3 says) |
| created_by_id, deleted_by_id | varchar(64) NULL FK users SET NULL |
| created_at, updated_at, deleted_at | timestamptz (`TimestampMixin`, `SoftDeleteMixin`) |
| Indexes | `ix_exam_templates_scope_org_status` (owner_scope, organization_id, status), `ix_exam_templates_owner_user_id` |

### 2.2 `exam_template_versions` (immutable)

Columns exactly as §3: `id`, `template_id` FK RESTRICT, `version_no` + `UNIQUE(template_id, version_no)` `uq_exam_template_versions_template_version`, `spec` JSON NOT NULL, `spec_hash` varchar(64) (`assessments/snapshot.py::canonical_hash` reused), `grading_scheme_version_id` FK `grading_scheme_versions` RESTRICT (nullable), `published_at` NOT NULL, `published_by_id` FK users SET NULL. Index `ix_exam_template_versions_template_id_version_no`. A `before_update` listener raises **`ImmutableExamTemplateVersionError`** (copy of `assessments/models.py:188-199`).

### 2.3 `assessments` (new columns; `preset` and `preset_valid` stay)

| Column | Type / constraint |
|---|---|
| exam_template_version_id | uuid NULL FK exam_template_versions RESTRICT; index `ix_assessments_exam_template_version_id` |
| display_mode | varchar(16) NOT NULL server default `one_per_page`; CHECK IN (`one_per_page`,`scrolling`) `display_mode_valid` |
| passage_display | varchar(16) NULL; CHECK `IS NULL OR IN ('plain','numbered')` `passage_display_valid` |
| result_view | varchar(32) NULL (registered keys validated in code; no CHECK, new views must not need a migration) |
| structure_locked | bool NOT NULL server default false |
| CHECK | `preset = 'none' OR exam_template_version_id IS NULL` **`preset_template_exclusive`** |

Existing rows (all ORT and general exams) get the defaults; `passage_display`/`result_view` NULL resolve to the course template's values exactly as 6a does today (`templates/service.py::course_template_out`). **No ORT row changes value.**

### 2.4 Section rules: `min_items`

`assessments/rules.py`: `RULE_KEYS` gains `"min_items"`; `normalize_rules` validates it like `max_items` (positive int, ≤ `max_items` when both set); `assessments/schemas.py::SectionRulesIn` gains `min_items: Optional[int] = Field(None, ge=1, le=10_000)` with a model validator `min ≤ max`. `ort_rules()` output is untouched (ORT never sets counts), so every ORT parity fixture compares equal. `snapshot.py`: next to `too_many_items` (line 262) add `if rules.get("min_items") and sec_count < rules["min_items"]: issues.append(Issue("too_few_items", pos))`. `too_few_items` is an error at publish like `too_many_items` (B7: incremental building is fine, publishing an incomplete template exam is not).

### 2.5 Downgrade

Drop the assessments columns and constraint (batch on SQLite), drop both tables. Lossless when no template exists; refused with a clear error when `exam_template_version_id IS NOT NULL` on any assessment (structure would be lost).

### 2.6 Production

No data steps, so no Neon rehearsal dump is needed; `alembic upgrade head && alembic check` on a local PG 18 restore of the schema (`tests/test_migrations.py` pattern) plus **`tests/test_migration_0010.py`**: `up_down_up` on SQLite and PG, an existing ORT assessment keeps `preset='ort_main'`, `exam_template_version_id IS NULL`, `display_mode='one_per_page'`, `structure_locked=false`. Neon rule in §14.

---

## 3. Module layout **`app/lms/exam_templates/`**

| File | Content (owner slice) |
|---|---|
| `models.py` | `ExamTemplate`, `ExamTemplateVersion`, immutability listener (S1) |
| `ids.py` | Stable names shared by every slice, pushed first: `SPEC_SCHEMA = 1`; error codes (§5.6); audit actions `exam_template.publish|archive|lock|unlock|promote`, `assessment.structure_unlock`; snapshot keys `SNAPSHOT_TEMPLATE_KEYS = ("exam_template_version_id", "display_mode", "passage_display", "result_view")`; `LOCK_SCOPE_KEYS` and the map to `templates/base.py` constants (§5.4); issue code `too_few_items`; policy names (S1) |
| `spec.py` | `ExamTemplateSpec` and sub-models, `validate_spec(db, spec_dict, owner) -> ExamTemplateSpec`, `spec_from_assessment(db, a) -> dict` (S1) |
| `blocks.py` | `RESULT_VIEWS = ("general", "ort")`, `PASSAGE_DISPLAYS`, `DISPLAY_MODES`, `NAVIGATIONS`, `IMPORTER_PROFILES = ("general", "ort")`, `catalog(db, ctx) -> BlocksOut` (S1 constants; S2 endpoint) |
| `scopes.py` | `visible_stmt(user_id, course)`, `manageable_stmt(ctx)`, `can_manage(ctx, template)`, `can_create(ctx, owner_scope, organization_id)` (S2) |
| `service.py` | create draft, patch draft, publish, archive, lock, unlock, promote, list/get, `latest_version_note` (S2) |
| `instantiate.py` | `instantiate(db, ctx, course, version, parameters, *, title, languages, assignment_fields=None) -> Assessment` (no commit) and `upgrade_to_latest` (S2) |
| `save_as.py` | `save_as_template(db, ctx, course, assessment, data) -> ExamTemplate` (S2) |
| `locks.py` | `assert_structure_unlocked(db, course, assessment, field, *, actor_id)` (S2; builder.py calls it, §5.4) |
| `import_format.py` | `format_for(db, version) -> ImportFormatOut`, `csv_for(fmt, lang) -> bytes` (S3) |
| `schemas.py`, `router.py`, `policies.py` | API (S2); `policies.py` is created by S1 with an empty dict and `route_inventory.py` imports it in a `# --- Phase 7b S1 ---` block |

Routers: `exam_templates/router.py` mounted at `/exam-templates` in `app/api/v1/router.py`; the assessment-bound routes (`save-as-template`, `template-upgrade`, `structure-unlock`) live in `assessments/router.py` (S2 block) and their policies in `assessments/policies.py` (S2 block).

---

## 4. `ExamTemplateSpec` validation (`spec.py`)

Pydantic, `extra="forbid"`, field shapes exactly as EXAM_TEMPLATES_DESIGN §3.1. Rules and their reuse:

1. `sections[*].allowed_types`, `allow_passages`, `min_items`, `max_items` → built into a rules dict and passed through **`assessments/rules.py::normalize_rules`** (one validator for the builder and the template). `time_limit_s` bounds 60..86400 (the `assessments` CHECK). Section keys unique when present (`^[a-z0-9_]{1,40}$`), 1..50 sections.
2. `navigation`, `defaults.score_policy`, `defaults.results_policy`, `defaults.allowed_attempts` (-1 or 1..100) use the literals of `assessments/schemas.py`. Section timers require `navigation = section_forward_only` and must sum to ≤ `defaults.time_limit_s` when both set (same rule as `snapshot.py:107-112`, reported as 422 `spec_invalid` with `loc`).
3. `display_mode = scrolling` is accepted in the spec (8b) but refused at **instantiate** (§1) until the player exists.
4. `result_view ∈ RESULT_VIEWS`, `passage_display ∈ PASSAGE_DISPLAYS` (also per section), `importer_profile ∈ {"general", None}`; **`"ort"` is rejected with `importer_profile_reserved`** (ORT's profile belongs to the ORT course template only; §8 of the design).
5. `scoring.grading_scheme_version_id`: must exist, scheme not deleted, and be a system scheme or owned by the template's owner (`grading/repository.py::load_usable_version_row` cannot be used, it is course-scoped; a new `exam_templates/spec.py::_scheme_visible(db, version_id, owner_user_id)` runs the same `or_(owner_user_id IS NULL, owner_user_id = owner)` predicate). For `platform`/`organization` templates only system schemes are allowed in v1 (`scheme_not_shareable`): a teacher's private scheme must not leak into templates others can see (shared schemes are Phase 9).
6. `parameters`: ≤ 5 entries, `kind = "choice"`, `options` 1..50 unique keys matching the section-key pattern, `binds = "sections[<i>].key"` with `i` in range; the bound section's `key` must be `null` in the spec (the parameter supplies it). Instantiate requires every parameter (`parameter_missing`) and a listed option (`parameter_invalid`).
7. `lock_scope ⊆ LOCK_SCOPE_KEYS` (§5.4).

`validate_spec` returns the normalized model; `canonical_hash(spec.model_dump(mode="json"))` is the `spec_hash`. Table-driven test **`tests/lms/test_exam_template_spec.py`** (every field × good/bad, the ORT-like spec of §12 as the big positive case).

---

## 5. Services

### 5.1 Drafts, publish, archive (`service.py`)

- `create(ctx, data)`: `owner_scope` + `organization_id` + `title` (+ optional `draft_spec`) → row `status=draft`, `draft_rev=1`. Authorization `can_create` (§9.2). Teacher scope sets `owner_user_id = ctx.user.id` and `organization_id` = the given org, which must be one the teacher is an active member of (`organizations/service.py::is_active_member`); independents pass their personal org.
- `patch(ctx, id, data)`: optimistic `draft_rev` (409 `draft_conflict` with the current rev, as `builder.update_assessment`), validates `draft_spec` fully on every save (422 `spec_invalid`), may change `title`/`description`. Archived templates refuse writes (409 `template_archived`).
- `publish(ctx, id)`: `draft_spec` required (422 `nothing_to_publish`); `version_no = max + 1` under `SELECT ... FOR UPDATE` of the template row (PG; SQLite single writer), insert the version with `grading_scheme_version_id` copied from `spec.scoring`, set `current_version_id`, `status=published`, clear `draft_spec`, bump `draft_rev`, audit `exam_template.publish`. Re-publishing an identical spec (same `spec_hash` as the current version) is a no-op returning the current version (same rule as assessments, D9).
- `archive(ctx, id)`: `status=archived` (hidden from pickers; existing assessments untouched; versions stay). Audited. No un-archive in 7b (new template instead; one line in §15).
- `lock/unlock(ctx, id)`: `locked` flag, audited with `reason` (≤ 500 chars, optional). Only the **owner** (§9.2): platform admin for platform, org admins of the org for organization, the teacher for teacher scope; platform admin everywhere.
- `promote(ctx, id)`: `teacher → organization` by an org admin of the template's org (or platform admin): sets `owner_scope=organization`, clears `owner_user_id`, audited with the former owner in `details`. The template keeps its versions and ids, so assessments created from it are unaffected.
- `list(ctx, scope?, organization_id?, course_id?, status?, cursor, limit)`: with `course_id` → picker mode (`visible_stmt`, published only, archived excluded); without → management mode (`manageable_stmt`: own teacher templates, organization templates of administered orgs, platform templates for platform admins; drafts included). `core/pagination.py::paginate` on (`updated_at`, `id`).

### 5.2 Visibility (`scopes.py::visible_stmt(user_id, course)`)

One `OR` of three predicates over `exam_templates` with `deleted_at IS NULL AND status = 'published' AND current_version_id IS NOT NULL`: `owner_scope='platform'`; `owner_scope='organization' AND organization_id = :course_org`; `owner_scope='teacher' AND owner_user_id = :user_id`. Personal organizations (6a, A1) make independents' organization templates private by construction; a teacher template is visible to its owner in every course they staff (structure only, no questions: B11). `GET /exam-templates/{id}` for a template outside both scopes → 404 `template_not_found` (never 403, as elsewhere). A specific `exam_template_version_id` on create is accepted only when its template passes `visible_stmt` (pinning an older version deliberately, §3.2 rule 1).

### 5.3 `instantiate` (`instantiate.py`; one transaction, no commit)

Signature: `instantiate(db, ctx, course, version: ExamTemplateVersion, parameters: dict, *, title, languages) -> Assessment`. Steps:

1. `require_course(ctx, A.CONTENT_MANAGE, course)`; template visible (§5.2) and not archived (409 `template_archived`); `display_mode != scrolling` (§1); languages ⊆ course languages (same check as `builder.create_assessment:72`); parameters resolved (§4.6).
2. `Assessment(course_id, created_by_id, title, languages, status="draft", position=max+1, preset="none", navigation=spec.navigation, display_mode, passage_display, result_view, time_limit_s=defaults.time_limit_s, allowed_attempts, score_policy, results_policy, show_correct_answers, shuffle_items, shuffle_choices, grading_scheme_version_id=version.grading_scheme_version_id, exam_template_version_id=version.id, structure_locked=template.locked)`. `grading_scheme_version_id` falls back to `None` (course default, points) when the spec has no `scoring`, exactly like a blank assessment. `db.flush()`.
3. One `AssessmentSection` per spec section: `position=i`, `key` (parameter-bound keys substituted), `title`, `instructions`, `time_limit_s`, `rules = normalize_rules({allowed_types, allow_passages, max_items, min_items})` with `None` values dropped (so a rules dict equals what the builder stores for the same input).
4. `assignments.sync.ensure_quiz_assignment(db, a, ctx.user.id)` (7a) → the quiz assignment row in the same transaction.
5. Callers commit: `builder.create_assessment` (template branch, §9.1) and `assignments/service.py::_create_quiz` (replaces the `exam_templates_not_available` raise at line 125: resolve the version, call `instantiate`, then apply the 7a `later` settings through `builder.update_assessment` as the preset path does; `assert_preset_allowed` is **not** called, since `preset='none'`).

The ORT preset branch of `create_assessment` (lines 76-93) is not touched; the template branch is a separate `if data.exam_template_id or data.exam_template_version_id:` block before it (block `# --- Phase 7b S2 ---`).

### 5.4 Locks (`locks.py`)

Spec `lock_scope` keys → `templates/base.py` constants: `sections` → {`LOCK_SECTION_KEY`, `LOCK_SECTION_ORDER`, `LOCK_SECTION_ADD_REMOVE`}; `section_time_limit_s` → `LOCK_SECTION_TIME_LIMIT`; `rules` → `LOCK_SECTION_RULES`; `navigation` → `LOCK_NAVIGATION`; `scheme` → `LOCK_SCHEME_VERSION`; `result_view` → `LOCK_RESULT_VIEW`; `importer_profile` → `LOCK_IMPORTER_PROFILE`; `display_mode` → new **`LOCK_DISPLAY_MODE = "display_mode"`** added to `templates/base.py::ALL_LOCK_FIELDS` (S1 block). `assert_structure_unlocked(db, course, a, field, *, actor_id)` first calls the 6a `tpl.assert_not_locked(course, field, preset=a.preset, actor_id=actor_id)` (course template path, unchanged), then: if `a.structure_locked` and `a.exam_template_version_id` and `field` ∈ the version's expanded lock set → 409 `template_locked`, `details={"field": field, "source": "exam_template"}`. The eight `tpl.assert_not_locked` call sites in `builder.py` (lines 121, 123, 209, 234, 236, 240, 260, 278) become `locks.assert_structure_unlocked(...)` (S2, one block each; `preset` exams take the first branch only, so ORT behaviour is identical). Editable regardless of the lock: the 6a §5.4 editable list (items, points, banks, title, description, dates, `allowed_attempts`, `score_policy`, `results_policy`, `show_correct_answers`, `shuffle_*`, `grade_release`, `omit_from_total`, access code).

**`POST .../assessments/{aid}/structure-unlock`** (`structure_locked=false` on one assessment, audited `assessment.structure_unlock`): caller needs `course:content.manage` **and** `can_manage(template)` (owner answer 5: locking is the template owner's call; an org admin joins as teacher first, A13). Unlocking a template later never unlocks existing assessments; locking later never locks existing drafts (§3.3 of the design).

### 5.5 Save as template (`save_as.py`), upgrade (`instantiate.py::upgrade_to_latest`)

- `save_as_template(ctx, course, a, data)`: body `{owner_scope: teacher|organization|platform, organization_id?, title, description?, lock_scope?, display_mode?, sections_counts?: [{position, min_items?, max_items?}]}`. Refused for `a.preset != 'none'` (409 `preset_not_templatable`; §16 Q1). Builds `draft_spec` with `spec_from_assessment`: navigation, display_mode, passage_display/result_view (the assessment's explicit values, NULL stays NULL), `defaults` from the assessment settings, `sections` from the rows (key, title, instructions, time_limit_s, rules + counts from the body), `scoring` from `grading_scheme_version_id` (must pass §4.5 for the chosen scope, else 422 `scheme_not_shareable`), `importer_profile = "general"`, `parameters = []`. Creates the draft through `service.create` (same authorization). Returns the template; the teacher publishes it on the templates page. Nothing is written to the assessment.
- `upgrade_to_latest(ctx, course, a)`: 409 `template_upgrade_not_allowed` unless `status='draft'`, no attempts (`attempts` count by `assessment_id` = 0, like `publish.py` confirm logic) and `current_version_id != a.exam_template_version_id`. Rewrites the assessment's structure fields and section rows **by position**: existing items of a section stay when the new version has a section at that position; items of removed sections are deleted; items violating the new rules are returned as issues (`check_item_rules`), not deleted. Parameters are re-applied from the stored section keys when possible (bound section keeps its key), else 422 `parameter_missing`. Audit not required (teacher action on own draft).

### 5.6 Error codes (`ids.py`)

`template_not_found` 404, `template_not_published` 422, `template_archived` 409, `spec_invalid` 422 (details `loc/msg`), `nothing_to_publish` 422, `draft_conflict` 409, `template_locked` 409 (existing code, new `source`), `preset_template_exclusive` 422 (7a), `preset_not_templatable` 409, `parameter_missing`/`parameter_invalid` 422, `display_mode_not_available` 422, `importer_profile_reserved` 422, `scheme_not_shareable` 422, `template_upgrade_not_allowed` 409, `not_a_template_assessment` 422, `scope_not_allowed` 403 (create/promote without the right), import: `section_not_in_template`, `type_not_allowed_in_section`, `passage_not_allowed` (errors), `count_below_min`, `count_above_max` (warnings), `attach_target_mismatch`, `format_mismatch`.

---

## 6. Snapshot and publish

`snapshot.py::build_snapshot` adds to the dict at line 276 the four keys of `SNAPSHOT_TEMPLATE_KEYS` (values from the assessment; `None` stays `None`), `SNAPSHOT_SCHEMA` unchanged (additive keys; `engine.py::plan_for` and `cache.py::get_plan` read only the keys they know). ORT snapshots therefore gain `"exam_template_version_id": null, "display_mode": "one_per_page", "passage_display": null, "result_view": null`; `content_hash` of a re-published unchanged ORT exam changes once (new version only when someone republishes; attempts in flight keep theirs). **`test_ort_parity.py` compares scores, not hashes**, so no fixture changes (§12). The result endpoint (`attempts/results.py`) serializes `result_view`/`passage_display` from the snapshot with the course-template fallback, so results of a template exam never look back at the template.

---

## 7. Block catalog and frontend contract

`GET /exam-templates/blocks` (authenticated): `{question_types: [{key, title_key, supports_passages, import_columns}], result_views, passage_displays, display_modes, navigations, importer_profiles, scheme_versions: [{id, title, type, scope: system|mine}]}`. `QuestionType` (`content/types/base.py:85`) gains class attributes `title_key: str`, `supports_passages: bool`, `import_columns: tuple[str, ...]` (S1, data only; `validate/score` untouched). Frontend **`frontend/src/lib/lms/blocks.ts`** exports `RESULT_VIEWS`, `PASSAGE_DISPLAYS`, `DISPLAY_MODES`, `NAVIGATIONS`, `IMPORTER_PROFILES`, `QUESTION_TYPES` as `as const` arrays and the maps `resultViews`, `passageRenderers`. **`tests/lms/test_blocks_contract.py`** parses the TS literal arrays with a regex (like `scripts/check_i18n_parity.py` reads JSON) and asserts equality with `blocks.py`/`TYPE_NAMES`; a second check asserts every `title_key` exists in `en.json`.

---

## 8. General import format and template validation

**Parser** **`content/importers/general_csv.py`** (new): header-driven (columns by name, any order, unknown columns are a warning `unknown_column`), columns of EXAM_TEMPLATES_DESIGN §5, producing the same **`ParsedItem`/`ParsedBundle`** dataclasses so **`service.py::_process_bundle`, image handling and bank upsert are reused unchanged**. Per-type payload builders live next to the type classes' `import_columns` (one `from_import_row(raw) -> payload` per type in `content/types/*.py`, S3; comparison reuses `importers/rules.py::math_section_rule_error`). Zip: manifest `format: "lms-bundle"`, `format_version: 1`, `questions.csv`, `images/`, same `zipsafe` limits; detection in `parse.py::parse_upload`: manifest `format` decides the profile; a plain CSV is ORT when `opts.exam_type` is set (today's rule), general otherwise. An ORT-formatted CSV in general mode fails the header check with `format_mismatch` (clear message: "this is an ORT file; choose the ORT format"), and vice versa.

**ORT path**: `ort_csv.py`, `bundle.py`, `rules.py`, `schemas.py` stay **byte-for-byte**; `service.py` changes only in `_run`/`preview`/`commit` by (a) passing the new `ImportOptions` fields and (b) the attach step. `ImportOptions` gains `exam_template_version_id`, `assessment_id`, `attach_to_assessment_id` (all optional; `ort` property unchanged). Dispatch is already implicit (`opts.exam_type`); nothing in the ORT branch reads the new fields. `templates.service.assert_import_profile_allowed` keeps gating `exam_type`.

**Validation profile** (`import_format.py::format_for(version)`): sections (key, title, position, allowed types, `allow_passages`, counts), per section the union of `import_columns` of the allowed types, the full header = `section,type` + union over all sections + passage columns when any section allows passages. `GET /exam-templates/{id}/versions/{no}/import-format` → JSON; `?download=csv&lang=` → `text/csv; charset=utf-8` with BOM, header row, then one example row per section prefixed `#` (comment rows are skipped by the parser; comment texts from `examTemplates.importFormat.*` i18n via the backend's locale loader of `frontend/src/lib/i18n/*.json`? **No**: the backend has no access to the frontend JSON; example rows use the section title in the requested language and fixed ASCII placeholders, no translated prose; the UI shows the translated help). Filename `import-format-<template-slug>-v<no>.csv`.

**Validation at upload** (`general_csv.py` with a `TemplateProfile` derived from `format_for`): `section` must match a section key or exact title in any language (`section_not_in_template`); `type` must be allowed there (`type_not_allowed_in_section`; omitted `type` is filled when exactly one type is allowed, else `type_required`); passages only where allowed; counts per section vs min/max → warnings. With `assessment_id`, the version is `assessment.exam_template_version_id` (422 `not_a_template_assessment` otherwise). **Attach** (`attach_to_assessment_id`, commit only): after `_process_bundle` the imported/updated question ids per section label are grouped and added to the assessment's section with the same key through **`builder.attach_questions(db, ctx, course, assessment, section, question_ids) -> BulkAddOut`** (flush-only; S1 extracts the inner loop of `add_items_bulk` lines 448-end into `_add_questions(...)` so the public function keeps committing and `attach_questions` does not; behaviour unchanged, existing builder tests prove it). Attaching requires the assessment to be a draft of the same course whose template version equals the validated one (`attach_target_mismatch`) and `course:content.manage`. One transaction: a failed attach rolls the whole import back (the existing `_run` try/except).

---

## 9. API surface, policies, authorization

### 9.1 Routes (listed in `route_inventory.py`; `POLICY_NAMES` gains `exam_template_create`, `exam_template_manage`, `exam_template_read` in the S1 block)

| Method, path | Policy |
|---|---|
| GET `/api/v1/exam-templates` (`scope`, `organization_id`, `course_id`, `status`, `cursor`, `limit`) | `authenticated` (scoped by §5.1/5.2) |
| GET `/api/v1/exam-templates/blocks` | `authenticated` |
| POST `/api/v1/exam-templates` | `exam_template_create` |
| GET `/api/v1/exam-templates/{template_id}` | `exam_template_read` (visible or manageable, else 404) |
| PATCH `.../{template_id}`; POST `.../publish`, `.../archive`, `.../lock`, `.../unlock`, `.../promote` | `exam_template_manage` (lock/unlock: owner only; promote: org admin / platform admin) |
| GET `.../{template_id}/versions`, GET `.../versions/{version_no}`, GET `.../versions/{version_no}/import-format` | `exam_template_read` |
| POST `/api/v1/courses/{course_id}/assessments` (body gains `exam_template_id`, `exam_template_version_id`, `parameters`) | existing `course:content.manage` |
| POST `/api/v1/courses/{course_id}/assignments` (7a; the quiz body already carries the three fields) | existing |
| POST `.../assessments/{assessment_id}/save-as-template` | `course:content.manage` (+ `can_create` for the chosen scope) |
| POST `.../assessments/{assessment_id}/template-upgrade` | `course:content.manage` |
| POST `.../assessments/{assessment_id}/structure-unlock` | `course:content.manage` (+ `can_manage(template)`), audited |
| POST `/api/v1/courses/{course_id}/imports[/preview]` (form gains `exam_template_version_id`, `assessment_id`, `attach_to_assessment_id`; `max_fields` 8 → 11) | existing `course:content.manage+ratelimit` |

`AssessmentStaffOut` gains `exam_template: {template_id, title, version_no, version_id, latest_version_no, locked_fields: [...]} | null`, `display_mode`, `passage_display`, `result_view`, `structure_locked`. `AssessmentCreateIn` gains the three fields with a validator: `preset != 'none'` together with any of them → 422 `preset_template_exclusive`; `subject_key` only with `ort_subject` (unchanged).

### 9.2 Authorization matrix (server-side, DB roles; `AuthzContext.is_platform_admin`, `org_admin_for`, course roles)

| Action | Platform admin | Org admin (of the org) | Teacher (course owner/teacher) | Assistant | Student | Org admin inside a course (A13) |
|---|---|---|---|---|---|---|
| list/read visible templates in a course picker | yes | via courses they staff only | yes | yes (`content.manage`) | no (404) | read-only course view, no picker |
| create `platform` template | yes | no | no | no | no | – |
| create `organization` template | yes | yes (own orgs) | only with `settings.teachers_can_publish_org_templates` | no | no | – |
| create `teacher` template / save-as (teacher scope) | yes | n/a | yes (`course_creator`-eligible teacher: approved or org member) | no | no | – |
| patch draft / publish / archive | yes | organization + teacher templates of the org | own templates | no | no | – |
| lock / unlock | yes | organization templates of the org | own teacher templates | no | no | – |
| promote teacher → organization | yes | yes | no | no | no | – |
| create assessment / assignment from template | yes (platform course routes as today) | no | yes | yes | no | no |
| save-as-template, template-upgrade | no (not course staff) | no | yes | yes (`content.manage`) | no | no |
| structure-unlock | yes | after join-as-teacher and only for the org's templates | own teacher templates only | no | no | no |
| import with validation / attach | as today (`content.manage`) | no | yes | yes | no | no |

Cross-tenant tests: org A's templates invisible in org B's courses (404 on read, 422 `template_not_found` on create), teacher X's templates invisible to teacher Y, a personal-org template never visible outside its courses, archived templates not in pickers but readable through their versions by staff who hold assessments from them.

---

## 10. Frontend (minimal; design system `components/ui/**`, 375 px first)

API clients **`frontend/src/lib/lms/examTemplates.ts`**, **`examTemplateTypes.ts`**, **`blocks.ts`**; i18n group **`examTemplates`** (+ keys in `assessments.create.*`, `assignments.create.*`, `bank.import.*` listed in the slice brief).

| Screen | Content |
|---|---|
| `CreateAssessmentDialog.tsx`, `AssignmentEditorDialog.tsx` (quiz kind) | Below the existing preset radios (ORT courses keep them untouched): a `Select` "Start from" with "Blank" + visible templates (`GET /exam-templates?course_id=`), grouped platform / organization / mine; choosing one hides the preset radios, shows the template's section list (read-only summary) and one `Select` per `parameters` entry. Submit sends `exam_template_id` (+ `parameters`). |
| Assessment builder page header | `TemplateBadge`: "From template <title> v<n>" with "Newer version available · Upgrade" (draft, no attempts; confirm dialog listing issues from the response) and a "Download import format (CSV)" link; locked controls already grey out on `template_locked` (6a) and now read `locked_fields` for template exams with note `examTemplates.lockedNote`. Menu item **"Save as template"** → `SaveAsTemplateDialog.tsx` (scope radios the user may use, title (LocalizedTextInput), optional min/max per section, lock toggle) → toast with link to the templates page. Hidden for `preset != 'none'` (§16 Q1). |
| **`/[lang]/exam-templates`** (mine, teachers), **`/[lang]/org/[orgId]/exam-templates`** (org admins), **`/[lang]/admin/exam-templates`** (platform) | One shared `ExamTemplatesPage` + `ExamTemplateEditor.tsx`: list (title, scope badge, status, version, locked, updated), "New template" (title + scope), editor = structured header fields (title, description, navigation, display mode (scrolling shown disabled with `examTemplates.scrollingLater`), passage display, result view, scheme select from `/blocks`) + a `Textarea` with the `sections`/`parameters`/`lock_scope` JSON validated server-side (`spec_invalid` details rendered under the field), Save (draft_rev conflict toast), Publish, Archive, Lock/Unlock (reason prompt), Promote (org admin), Versions list with "Import format" download per version. No drag-and-drop constructor (8b). |
| Import dialog (`components/lms/content/import/**`) | "Validate against exam" `Select` (draft assessments of the course with a template), checkbox "Add imported questions to this exam", report shows the new issue codes; ORT courses: the format select is unchanged; template validation is only offered when the format is "general". |
| Nav | `AdminShell` nav gains "Exam templates"; org layout nav gains it; teacher: entry under the teaching menu (`shell.*`). |

Every string in `en.json`, `ky.json`, `ru.json`; `scripts/check_i18n_parity.py` green; `tsc --noEmit`; build in the rsync'd copy.

---

## 11. Tests (backend `tests/lms/`, scratch SQLite + PG parity)

`test_exam_template_spec.py` (§4 table), `test_exam_templates_api.py` (CRUD, draft_rev conflict, publish bumps version and leaves created assessments untouched, archive hides from pickers, lock/unlock/promote audited rows, version immutability raises, identical re-publish is a no-op), `test_exam_template_visibility.py` (matrix §9.2, personal-org isolation, cross-tenant 404s), `test_exam_template_instantiate.py` (rows equal a hand-built assessment; quiz assignment exists with `assignment_id_for`; parameters; `display_mode_not_available`; via `/assignments` the 7a `later` fields apply), `test_exam_template_locks.py` (locked field × action → 409, editable field → 200; unlock later does not propagate; structure-unlock authorization), `test_save_as_template.py` (round trip: save → publish → instantiate equals the source structure; `preset_not_templatable`; `scheme_not_shareable`), `test_template_upgrade.py` (draft without attempts only; items kept by position; issues reported), `test_snapshot_template_keys.py` (four keys present; attempt runs after the template is re-published and archived), `test_import_general.py` (every type, aliases, zip manifest, `format_mismatch` both ways, ORT golden fixtures still identical), `test_import_template_validation.py` (section/type/passage errors, count warnings, attach same transaction, `attach_target_mismatch`), `test_import_format.py` (derivation per template, CSV download header = union, example rows parse back with zero errors), `test_blocks_contract.py` (§7), `test_route_inventory.py` (new routes listed), `tests/test_migration_0010.py` (§2.6), **`test_ort_expressibility.py`** (§12). PG: `test_pg_concurrency_exam_templates.py` (two publishes race → distinct version numbers, one winner per `version_no`).

---

## 12. ORT review plan for 7b (no fixture or baseline change expected)

Why nothing changes for ORT: ORT exams are created through `preset` (`builder.py:76-93`, `ort/seed.py:479,553`) which 7b does not edit; the new columns default to today's behaviour (`passage_display`/`result_view` NULL → course template `numbered`/`ort`); the `preset_template_exclusive` CHECK makes the two paths disjoint; the ORT importer files are untouched and the general parser is reached only without `exam_type`; `ort_rules()` has no `min_items`; the player and results read snapshot keys they already know. The "Create" dialog in ORT courses gains the "Start from" select (look, not function: ORT teachers may give a plain quiz, design §2); the ORT builder header gets no "Save as template" item (§16 Q1).

| Proof | How |
|---|---|
| Imports identical | `test_ort_import_golden.py`, `test_import_csv.py`, `test_import_bundle.py`, `test_import_rules.py` unchanged and green; `git diff --stat phase-7a -- backend/app/lms/content/importers/{ort_csv,bundle,rules,schemas}.py` is empty (checked in S6) |
| Scores, flow, seed | `test_ort_parity.py`, `test_ort_e2e_api.py`, `test_ort_cutover_flow.py`, `test_ort_seed.py`, `test_ort_gradebook_golden.py` unchanged; `test_ort_seed.py` additionally asserts `exam_template_version_id IS NULL`, `structure_locked = false` on seeded exams |
| **Expressibility dry-run** (B9) | **`tests/lms/test_ort_expressibility.py`**: builds `ExamTemplateSpec` from `ORT_MAIN_SECTIONS`, `ORT_SECTION_RULES`, `ORT_MAIN_V1_ID`, the `builder.py:80-82` defaults (`navigation section_forward_only`, `results_policy after_submit`, `show_correct_answers true`, `allowed_attempts 1`, `score_policy highest`), `result_view "ort"`, `passage_display` null with `reading.passage_display = numbered`; publishes it as a platform template in a scratch DB; `instantiate` in a scratch general course; asserts the `assessments` row (minus `id`, `preset`, `exam_template_version_id`, `created_*`, `position`, `title`, `display_mode`, `passage_display`, `result_view`, `structure_locked`) and the five `assessment_sections` rows (position, key, time_limit_s, rules) equal those of `create_assessment(preset="ort_main")` in a scratch ORT course; the same for all seven `ORT_SUBJECT_KEYS` through one template with `parameters=[{key: "subject", kind: choice, options: ORT_SUBJECT_KEYS, binds: "sections[0].key"}]` and `ORT_SUBJECT_V1_ID`. The test imports the constants, never copies them, so drift fails the test. |
| Browser | `frontend/e2e/ort.spec.ts` unchanged; `ort-visual.spec.ts` against `docs/phases/ORT_BASELINE/`: expected diffs none (the create dialog is not baselined; `teacher-builder-*` shows the builder, whose header for preset exams is unchanged) |
| Walkthrough | CSV + zip upload (ORT format), build an ORT exam, take it, see the result; plus in a general course: create from a platform template, download the import format, import a matching general CSV with attach, publish, take, result |
| Report | `docs/phases/PHASE_7B.md` ORT section: look changes (create dialog), test names, walkthrough date |

---

## 13. UX gate screens (`docs/phases/PHASE_7B_screens/`)

Teacher screens in ru, student screens (none new in 7b beyond the unchanged lobby) skipped: create-assessment dialog with template selected (375/1440), assignment dialog quiz-from-template, builder header with template badge + upgrade confirm, save-as-template dialog, templates page list + editor (platform and org variants, spec error state), import dialog with validation select and the report showing template issues, import-format download toast. Reviewed by `ux-reviewer` against `docs/UX_GUIDELINES.md`; findings fixed without asking.

---

## 14. Slices, ownership, order, gates, Neon

Branches `phase-7b/<slice>` off `phase-7a` (which becomes the integration base; 7a merges to `lms`/`main` first if not yet done). Delimited blocks `# --- Phase 7b S<n> begin/end ---` in shared files. The orchestrator merges and reviews every diff.

| Slice | Model | Scope | Owns (exclusive) |
|---|---|---|---|
| **S1** models + spec + ids (first, alone; merged before S2–S4) | opus | §2 migration + models + `min_items` + `too_few_items`, `ids.py`, `spec.py`, `blocks.py` constants, `QuestionType` data attributes, `LOCK_DISPLAY_MODE`, `builder._add_questions/attach_questions` extraction, snapshot keys (§6), `policies.py` stub + inventory block + `POLICY_NAMES`, models registration, `AssessmentStaffOut` new fields, migration test | `backend/alembic/versions/0010_phase7b_exam_templates.py`, `app/lms/exam_templates/{__init__,models,ids,spec,blocks,policies(stub)}.py`, blocks in `assessments/{rules,schemas,snapshot,builder,models}.py`, `templates/base.py`, `content/types/base.py` + the 7 type files (attributes only), `app/lms/models.py`, `app/core/route_inventory.py`, `tests/test_migration_0010.py`, `tests/lms/test_exam_template_spec.py`, `tests/lms/exam_template_support.py` |
| **S2** API + service | fable (authorization, locks, transactions) | §5, §7 endpoint, §9: scopes, service, instantiate, save-as, upgrade, locks swap in builder, template branch in `create_assessment`, the 7a hook in `_create_quiz`, routers, policies, audit, ORT expressibility test | `app/lms/exam_templates/{scopes,service,instantiate,save_as,locks,schemas,router}.py`, `policies.py` (fills), blocks in `assessments/{builder,router,policies,schemas(CreateIn)}.py`, block in `assignments/service.py`, `app/api/v1/router.py`, `tests/lms/test_exam_templates_api.py`, `test_exam_template_visibility.py`, `test_exam_template_instantiate.py`, `test_exam_template_locks.py`, `test_save_as_template.py`, `test_template_upgrade.py`, `test_snapshot_template_keys.py`, `test_ort_expressibility.py`, `test_blocks_contract.py`, `test_pg_concurrency_exam_templates.py` |
| **S3** general import format | opus | §8: parser, type row builders, manifest, `ImportOptions` fields, router form fields, validation profile, attach step, import-format derivation + CSV download endpoint (route added to `exam_templates/router.py` through a function S2 exposes: `router.include_router(import_format_router)`, file owned by S3) | `content/importers/general_csv.py`, `content/importers/{parse,service,schemas}.py` blocks, `content/import_router.py` block, `from_import_row` blocks in `content/types/*.py`, `app/lms/exam_templates/{import_format,import_format_router}.py`, `tests/lms/test_import_general.py`, `test_import_template_validation.py`, `test_import_format.py`, fixtures `tests/fixtures/general_import/**` |
| **S4** frontend | opus (sonnet for i18n) | §10 screens, clients, `blocks.ts`, nav entries, i18n | `frontend/src/app/[lang]/exam-templates/**`, `[lang]/org/[orgId]/exam-templates/**`, `[lang]/admin/exam-templates/**`, `components/lms/examTemplates/**`, blocks in `components/lms/assessments/{CreateAssessmentDialog,SettingsPanel,PublishPanel}.tsx`, `components/lms/assignments/AssignmentEditorDialog.tsx`, `components/lms/content/import/**`, `components/lms/admin/AdminShell.tsx`, org layout nav, `lib/lms/{examTemplates,examTemplateTypes,blocks,contentImport,assessmentTypes}.ts`, i18n JSON (group `examTemplates` + listed keys) |
| **S5** integration | orchestrator + ux-reviewer (fable) + architect security review | full suites SQLite + PG, `alembic check`, ORT review (§12) incl. importer diff check, UX gate (§13), `/security-review` (template visibility, spec injection into rules, import attach authorization, CSV download content type), i18n parity, `next build`, `docs/phases/PHASE_7B.md`, `PRODUCT_DECISIONS.md` (P7B-*), handoff + memory | docs, `docs/phases/PHASE_7B_screens/**` |

**Order**: S1 alone (pushes `ids.py`, `spec.py`, models, `AssessmentStaffOut` shape and the route list so S2–S4 code against real names). Then S2, S3, S4 in parallel: S3 depends on S1 only (`format_for` reads the version row and `spec.py`; `attach_questions` from S1); S4 codes against §9/§10 shapes and integrates as S2/S3 land; S2 and S3 share no file (S3's router file is included by one S2 line). S5 last.

**Gates per slice**: SQLite suite green; route-inventory test green; action × role × status table tests for new routes; cross-tenant tests; serializer contract test (no `draft_spec` of other owners, no `owner_user_id` of others in picker payloads); `tsc --noEmit` for S4. **Phase gates (before `lms`, again before `main`)**: SQLite and PG suites green, `alembic upgrade head && alembic check`, `tests/test_migration_0010.py` on SQLite and PG, PG concurrency suites, ORT review §12 (expressibility test green, importer files diff empty, baselines unchanged), UX gate §13, `/security-review`, i18n parity, `next build` in the rsync'd copy, `/health` shows the commit after deploy, **owner checkpoint after the 7b deploy** (plan §0).

**Neon rule**: the project's branch limit is reached, so before the `main` merge (models and migration change) take a **Neon snapshot** of the production branch (`create_snapshot`, named `pre-7b-<date>`) instead of a backup branch, record its id in `PHASE_7B.md`, and delete nothing without the owner's OK.

---

## 15. Decisions taken here (to `PRODUCT_DECISIONS.md` as P7B-1 … when applied)

- **P7B-1** `scrolling` accepted in specs, refused at instantiate until 8b (no unbuilt mode reaches students; no second migration).
- **P7B-2** Platform and organization templates may reference system schemes only; teacher templates also the owner's own (no scheme leak before Phase 9 sharing).
- **P7B-3** `teachers_can_publish_org_templates` is read from `organizations.settings` with no UI until Phase 9; teachers use teacher scope + promote.
- **P7B-4** `too_few_items` is a publish error like `too_many_items` (B7 keeps building incremental; publishing stays correct).
- **P7B-5** No un-archive and no template deletion in 7b (versions are referenced; soft-delete only through platform admin tooling later).
- **P7B-6** Save-as-template refused for preset exams (§16 Q1 default) and never writes to the source assessment.
- **P7B-7** Upgrade maps sections by position and keeps items; violations are issues, not deletions.
- **P7B-8** Import-format CSV example rows carry section titles and ASCII placeholders only; translated help lives in the UI (backend has no i18n files).
- **P7B-9** `draft_rev` starts at 1 (matches assessments), `current_version_id` FK uses `use_alter`.

---

## 16. Alternatives to discuss (owner)

| # | Question | Options | Recommendation |
|---|---|---|---|
| **Q1** | **"Save as template" on ORT preset exams.** Allowing it adds a menu item to the ORT exam builder (an ORT screen) and lets any ORT-granted teacher publish a general template that reproduces the ORT structure and scheme (structure only; the ORT CSV/zip importer and the `ort` profile stay grant-only). | (a) Refuse (`preset_not_templatable`): ORT screens unchanged, the ORT structure spreads only through the granted course template; the §12 dry-run test is the official proof of expressibility. (b) Allow: convenient for ORT teachers who want ORT-shaped practice quizzes in general courses. | **(a)** for 7b; switching to (b) is one line and one i18n key. |

Everything else is decided above with its justification (P7B-1 … P7B-9).
