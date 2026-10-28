# Phase 8b design: exam templates II (visual constructor, display modes, live preview)

**Status**: architect draft 2026-10-28 (Fable), branch `phase-8b-design` off `origin/phase-8a` (a2a6d3a). Implements `IMPLEMENTATION_PLAN.md` Phase 8b on top of 7b (`PHASE_7B_DESIGN.md`: spec, versions, locks, instantiate, blocks catalog), 7c (`PHASE_7C_DESIGN.md` §8: card editor) and 8a. Ground truth for the model: `EXAM_TEMPLATES_DESIGN.md` §4, §6, §9, decisions B1–B12. Names in **bold code** are to be used exactly as written. Every file and line below was checked against `phase-8a`. **Owner checkpoint right after 8b**: §16 collects the open questions; each has a default in effect so nothing blocks.

---

## 1. Scope and non-goals

**In**: the visual **constructor** for exam templates at `/[lang]/admin/exam-templates/[id]`, `/[lang]/org/[orgId]/exam-templates/[id]` and `/[lang]/exam-templates/[id]` (teacher view inside Teaching; the three 7b routes keep their paths and the shared `ExamTemplatesPage` list); sections editor, navigation, display mode, scoring with the Phase 4 live preview table, result view, parameters, lock scope, versions with a **diff**, publish/archive/lock/unlock/promote, import-format download, **live preview with the real general player** on a per-template **sandbox** (course + sample quiz written in the 7c card editor); the **scrolling display mode** in the general player; `display_mode`, `passage_display`, `result_view` editable on general assessments and honoured by the player and the result page; `scrolling` allowed at instantiate (lifts P7B-1).

**Out**: template grants (B4), un-archive/delete (P7B-5), org settings UI (Phase 9), new question types (Phase 10), quiz statistics (Phase 10), any change to the ORT player, ORT screens, ORT import or scoring (§13), a preview for people who can only *pick* a template (§16 Q2).

---

## 2. Schema and migration **`0013_phase8b_template_sandbox`**

A column **is** needed: the sample quiz must be a real assessment (the 7c card editor and the attempt engine only work on one), a real assessment needs a course (`assessments.course_id` NOT NULL), and that course must be found from the template and hidden from every course list. Nothing in `courses` (`settings` JSON aside, rejected: lists would filter on JSON) can express "sandbox of template X". One nullable column does both jobs:

| Table.column | Definition |
|---|---|
| `courses.sandbox_for_template_id` | uuid NULL FK `exam_templates.id` ON DELETE SET NULL; `uq_courses_sandbox_for_template_id` UNIQUE (one sandbox per template; PG and SQLite both allow many NULLs). |

`down_revision = "0012_phase8a_course_structure"`, `op.f(...)` names, `op.batch_alter_table` on SQLite, no data step (existing rows NULL). No FK cycle (`exam_templates` never references `courses`). Downgrade: drop the constraint and column; lossless (sandbox courses become ordinary draft courses; the design accepts that only on a rollback). `tests/test_migration_0013.py`: up/down/up both engines, ORT courses and all existing courses read NULL, `alembic check` clean. Model block `# --- Phase 8b S1 ---` in `courses/models.py` (`sandbox_for_template_id`, property **`is_sandbox`**). `assessments.display_mode`, `passage_display`, `result_view` (7b) are reused unchanged; **no `is_preview` change**: preview attempts already exist (`attempts.is_preview`, `engine.start_attempt` staff path, `publish.ensure_preview_version`) and are already excluded from the gradebook (`grading/gradebook.py:172,373,516,591` and `actions.py:333`).

---

## 3. Module layout and touched files

New in `app/lms/exam_templates/`: **`sandbox.py`** (ensure course/enrollment/sample quiz, sync, preview), **`diff.py`** (pure `spec_diff`), **`preview_schemas`** inside `schemas.py` (block `# --- Phase 8b S1 ---`). Touched: `ids.py` (codes, audit actions, `SANDBOX_*` constants), `router.py` + `policies.py` (S2 block), `instantiate.py` (remove `_assert_display_mode`, extract **`apply_spec`**), `service.py::promote` (sandbox staff re-sync), `scopes.py::_staff_in_org` (exclude sandbox), `courses/{models,scopes,service}.py` (predicate **`regular_courses()`**, `assert_not_sandbox`), `organizations/service.py:300`, `platform_admin/{courses_router.py:54,users_service.py:130}` (filter), `assessments/{schemas,builder}.py` (`AssessmentUpdateIn.display_mode/passage_display/result_view`), `attempts/{schemas,engine,serializers,results}.py` (effective display fields in state and result), `core/route_inventory.py` (S1 block), `core/config.py` (`SANDBOX_PREVIEW_KEEP = 20`). Frontend: `components/lms/examTemplates/**` (constructor), `components/lms/player/**` (scrolling branch, renderer from state), `components/lms/results/{ResultSummary,StudentResult}.tsx`, `components/lms/assessments/SettingsPanel.tsx`, `components/lms/quiz/QuizEditor.tsx` (`mode="sandbox"`), `lib/lms/{blocks,examTemplates,examTemplateTypes,attemptTypes,assessmentTypes}.ts`, i18n (§10).

---

## 4. Invariants

1. A sandbox course (`sandbox_for_template_id IS NOT NULL`) is never published, never in a catalog, never joinable, never listed in any course list, never counted in organization usage, and never makes anyone "staff in the organization" (`scopes._staff_in_org`). Its only students are none; its staff are the template's managers.
2. Preview attempts are `is_preview = true`; they never create grade events or submissions, never appear in gradebooks or (Phase 10) statistics; the existing `is_preview` filters are the single mechanism (a test asserts the sandbox course's gradebook is empty after a preview).
3. The sample quiz mirrors the **draft** spec (or the current version when there is no draft) by position: items are kept across edits, section rules carry `allowed_types`/`allow_passages` but **never `min_items`/`max_items`** (counts guide real exams; the sample needs only the type and passage rules).
4. The player chooses renderers from the **attempt state** (`display_mode`, `passage_display`) and the result page from the **result payload** (`result_view`); the server resolves `NULL` to the course template's values, so every ORT attempt resolves to `one_per_page`/`numbered`/`ort` and renders as today.
5. Scrolling mode changes presentation only: the engine, autosave, timers, section close and submit are untouched (`EXAM_TEMPLATES_DESIGN` §6).
6. Every pick list in the constructor comes from `GET /exam-templates/blocks`; `blocks.ts` mirrors it and `test_blocks_contract.py` fails on drift (`AVAILABLE_DISPLAY_MODES` now equals `DISPLAY_MODES`).
7. Versions stay immutable; the diff is computed, never stored.

---

## 5. Backend services

### 5.1 Sandbox (`sandbox.py`)

- **`ensure(ctx, t) -> Sandbox{course, assessment}`**: `scopes.can_manage(ctx, t)` else `template_not_found()` (404); `t.status == archived` → 409 `template_archived`. Under `SELECT ... FOR UPDATE` of the template row (PG; SQLite single writer): load the live course with `sandbox_for_template_id = t.id`; if none, create it directly (not through `create_course`: no grant check, no audit noise): `owner_id = ctx.user.id`, `organization_id = t.organization_id or organizations.ids.platform_org_id()`, `title = t.title`, `languages = ["en","ky","ru"]`, `default_language = "ru"`, `status = draft`, `visibility = private`, `enrollment_mode = invite_code`, `join_code = generate_join_code()`, `home_kind = assignments`, `template_key = None`, `sandbox_for_template_id = t.id`. Then **`ensure_staff`**: an active `teacher` enrollment for `ctx.user` with `source = "staff_add"` (the `source_valid` CHECK at `enrollments/models.py:38-42` lists `owner, join_code, staff_add, admin, invite, form, open, org_admin_self`; no new value, so no CHECK change; constant **`SANDBOX_ENROLLMENT_SOURCE = "staff_add"`** in `ids.py`), then `ctx.enrollment_cache.pop(course.id, None)` so `role_for` sees it in this request. Then the sample assessment: the one live assessment of the course (`preset = none`); if missing, `Assessment(title = t.title, languages = [lang], status = draft, position = 1, preset = "none")` + `assignment_sync.ensure_quiz_assignment` (7a invariant: every quiz has its assignment row; it lives in the hidden course). Returns the pair. Audited once on creation: `exam_template.sandbox_create`.
- **`sync(db, t, a, spec: ExamTemplateSpec, parameters) -> list[Issue]`**: `instantiate.apply_spec(db, a, spec, keys, version=None, counts=False)`: the by-position mapping extracted from `upgrade_to_latest` (lines 251-267) into **`apply_spec(db, a, spec, keys, *, version, counts=True)`** which sets `navigation`, `display_mode`, `passage_display`, `result_view`, `grading_scheme_version_id` (from `spec.scoring`; `exam_template_version_id` only when `version` is given), rewrites sections by position (items of kept sections stay, items of removed sections are deleted), and with `counts=False` drops `min_items`/`max_items` from the rules. `upgrade_to_latest` becomes a thin caller (behaviour unchanged; its tests prove it). Parameters: `keys = resolve_parameters(spec, parameters)` when `parameters` are given, else `_reapply_parameters(spec, old_sections)`, else the first option of each parameter (preview never fails for a missing parameter; the UI lets the author pick). Returns `_rule_issues` (items violating the new rules: shown, not deleted).
- **`preview(ctx, t, data: PreviewIn) -> PreviewOut`**: `ensure` → spec = `validate_spec(draft_spec)` if present else the current version's spec (422 `nothing_to_preview` when neither) → `sync` → `language` must be in `a.languages` (422 `language_not_in_assessment`) → `engine.start_attempt(db, ctx, course, a.id, StartIn(language=lang), now=clock.now(), fresh=True)` (staff path: `ensure_preview_version` builds the preview snapshot; its publish issues such as `empty_section` or `unresolved_language` surface as 422 **`preview_not_ready`** with `details.issues`, so the UI says "Section 2 has no questions yet") → housekeeping: hard-delete finished preview attempts of this user on `a` beyond the newest `SANDBOX_PREVIEW_KEEP` (attempt_items then attempts; previews have no grade events) → `PreviewOut{attempt_id, course_id, assessment_id, language, issues}`. Rate limit: the existing `attempt_start_limit`.
- **`sync_staff(db, t)`** (called by `service.promote`, `set_locked` is not needed): removes (`state = removed`) sandbox enrollments of users for whom `can_manage` is now false, evaluated with the same predicate as `scopes.can_manage` over the handful of enrollment rows.
- Course guard **`courses/service.py::assert_not_sandbox(course)`** → 409 **`sandbox_course`** in `update_course`, `publish_course`, `conclude`, `delete_course`, `copy_course`, `rotate_join_code`, invitations and enrollment joins (`enrollments/service.py:52` join by code checks `status == published` already; the guard is added anyway for defence in depth). Sandbox courses are reachable only through assessment, quiz-editor, attempt and bank routes, which is what the Sample tab needs.
- Filters: **`courses/scopes.py::regular_courses()`** = `Course.sandbox_for_template_id.is_(None)`, added to `_visible_predicate` (line 18), the catalog predicate (line 72), `organizations/service.py:300,316`, `platform_admin/courses_router.py:54`, `users_service.py:130`, `exam_templates/scopes.py:146`. `home/service.py` and `announcements/service.py` already require `status != draft`. Test: one sandbox exists → absent from every list endpoint for owner, org admin and platform admin.

**Failure cases** (each is a test):

| Case | Behaviour |
|---|---|
| Sandbox course soft-deleted (admin tooling, rollback) | The UNIQUE constraint covers deleted rows too, so `ensure` **restores** a soft-deleted sandbox (`deleted_at = NULL`, `deleted_by_id = NULL`) instead of creating a second one; its assessments and bank come back with it (soft-delete cascade is row-level, nothing was hard-deleted). |
| Sample assessment deleted through the quiz editor's delete action | `ensure` restores it (`deleted_at = NULL`) when it is the only assessment of the course; `DELETE /assessments/{a}` on a sandbox course answers 409 `sandbox_course` anyway (guard in `builder.delete_assessment`). |
| Draft spec references a scheme version the author can no longer use | `validate_spec` already fails the PATCH (`scheme_not_shareable`); `preview` uses the stored (valid) draft, so it cannot meet this; if the scheme was deleted later, `sync` sets `grading_scheme_version_id = NULL` and returns issue `scheme_unavailable`. |
| Template promoted while a preview is in progress | the attempt continues (it belongs to the user, not to the manager set); `sync_staff` removes the enrollment, the next `GET /attempts/{id}` is 404 for a user who lost staff rights (`can_access` reads the role); the constructor shows "You no longer manage this template". |
| Two managers preview at once | each has their own preview attempt (`_existing_open` is per user); `sync` is idempotent and runs under the template row lock; the second `sync` sees the first's sections and changes nothing. |
| Author edits the draft while the sample editor is open in another tab | the Sample tab reloads the assessment after every constructor save (`draft_rev` change → `GET /assessments/{a}`); open cards keep their drafts (7c per-card drafts survive). |
| Parameters removed from the draft | `_reapply_parameters` finds no binding; the bound section keeps its stored key (a plain section now). |
| Archived template | `POST sandbox`/`preview` 409 `template_archived`; the Sample tab is read-only with the reason. |

### 5.2 Diff (`diff.py`, pure)

`spec_diff(before: dict, after: dict) -> list[SpecChange]` over normalized specs (`ExamTemplateSpec.model_validate(...).model_dump(mode="json")`): scalar paths `navigation, display_mode, passage_display, result_view, importer_profile, scoring.grading_scheme_version_id, defaults.<field>`; `lock_scope` as a set (one change listing added/removed keys); `sections` matched by `key` when both sides have one, otherwise by position among unkeyed sections; a matched section yields one change per differing field (`sections[<key or pos>].<field>`), unmatched sections `added`/`removed` (with the whole section as `before`/`after`); `parameters` matched by `key`. `SpecChange{path, kind: added|removed|changed, before, after, section: {key, position, title} | null}`; `summary{sections_added, sections_removed, sections_changed, fields_changed}`. Deterministic order: top-level fields in spec order, then sections by `after` position, then parameters.

### 5.3 Display fields on general assessments

`AssessmentUpdateIn` gains `display_mode: Optional[Literal[*DISPLAY_MODES]]`, `passage_display: Optional[Literal[*PASSAGE_DISPLAYS]]` (explicit null allowed = inherit), `result_view: Optional[str]` (validated against `RESULT_VIEWS`, null = inherit). `builder.update_assessment` guards each with `locks.assert_structure_unlocked(..., field)` (`LOCK_DISPLAY_MODE`, `LOCK_RESULT_VIEW`; passage display under `LOCK_RESULT_VIEW` too, decision P8B-4) so ORT preset exams answer 409 `template_locked` exactly as for `navigation` today; a change bumps `draft_rev` and needs a republish like any structure field. `instantiate._assert_display_mode` is deleted together with `E_DISPLAY_MODE_NOT_AVAILABLE` (kept in `ERROR_CODES` for one phase for old clients, never raised).

### 5.4 Effective display values in attempt payloads

`engine.build_state` adds **`display_mode`**, **`passage_display`** to `AttemptStateOut`; `results.py` adds **`result_view`** and **`passage_display`** to `AttemptResultOut` and `ReviewOut`. Values: `plan.snapshot.get(key)` (7b `SNAPSHOT_TEMPLATE_KEYS`) and, when `None`, the course template's `passage_display`/`result_view` (`templates.service.course_template_out(course)`; `display_mode` defaults to `one_per_page`). Older snapshots without the keys resolve the same way. Pure helper **`attempts/display.py::effective_display(snapshot, course) -> EffectiveDisplay`**, unit-tested with ORT and general snapshots.

### 5.5 Error codes (`ids.py`, 422 unless noted)

`nothing_to_preview`, `preview_not_ready` (details `issues`), `language_not_in_assessment`, `sandbox_course` (409), `diff_target_invalid` (`to=draft` without a draft, unknown version numbers → 404 `version_not_found`). Audit: `exam_template.sandbox_create`, `exam_template.preview` (platform templates only, like `AUDIT_UPDATE`).

---

## 6. API surface, policies, authorization

### 6.1 Routes (`policies.py` S2 block; `_T = /api/v1/exam-templates/{template_id}`)

| Method, path | Policy | Body → result |
|---|---|---|
| `POST _T/sandbox` | `exam_template_manage` | `{language?}` → `SandboxOut{course_id, assessment_id, languages, draft_rev}` (ensure + sync, no attempt; the Sample tab mounts the 7c editor on it) |
| `POST _T/preview` | `exam_template_manage+ratelimit` | `PreviewIn{language?, parameters?: {key: option}}` → `PreviewOut` (§5.1) |
| `GET _T/diff?from=<no>&to=<no|draft>` | `exam_template_read` (`to=draft` additionally requires `can_manage`, else 404) | `SpecDiffOut{from: {version_no|"draft"}, to, changes, summary}` |
| `PATCH /courses/{c}/assessments/{a}` gains the three display fields | existing `course:content.manage` | 409 `template_locked` when locked |
| `GET /attempts/{t}`, `/result`, `/review` gain the effective display fields | existing | additive |

All listed in `route_inventory.py` block `# --- Phase 8b S1 ---` (the inventory test fails otherwise). `ExamTemplateOut` gains `sandbox: {course_id, assessment_id} | null` (managers only) and `unpublished_changes: int | null` (diff count draft vs current, computed in `manage_out` when both exist; `null` without a version).

### 6.2 Authorization matrix (server-side, roles from the DB; `AuthzContext.is_platform_admin`, `org_admin_for`, course roles)

| Action | Platform admin | Org admin (of the org) | Owner teacher (teacher scope) / creating teacher (P7B-3) | Other teacher who can see the template | Assistant / student |
|---|---|---|---|---|---|
| open the constructor, edit the draft, autosave | platform + all | organization + teacher templates of the org | own | read-only summary (7b picker); 404 on PATCH | no (404) |
| sandbox, write sample questions, preview | yes | yes | yes | **no** (404; §16 Q2) | no |
| diff between versions | yes | yes | yes | yes (`exam_template_read`) | no |
| diff against the draft | yes | yes | yes | no (404) | no |
| publish / archive | yes | yes | yes | no | no |
| lock / unlock | yes | organization templates | own teacher templates | no | no |
| promote teacher → organization (re-syncs sandbox staff) | yes | yes | no | no | no |
| set `display_mode`/`passage_display`/`result_view` on a course assessment | course staff only | after join-as-teacher | course staff | course staff | assistant yes (`content.manage`), student no |
| lock scope effect | – | – | `display_mode` in `lock_scope` → 409 on the created exam (`LOCK_DISPLAY_MODE`); `result_view` → `LOCK_RESULT_VIEW` covers result view and passage display | – | – |

Cross-tenant tests: org A's admin cannot `POST sandbox` on org B's template (404); a teacher cannot preview a platform template (404); the sandbox course of template X is invisible to everyone through course lists and 404 through course routes for non-staff; sandbox staff lose access after `promote` when they no longer manage.

### 6.3 Serializer contracts (`test_serializer_contracts.py` additions)

| Payload | Must contain | Must never contain |
|---|---|---|
| `AttemptStateOut` (students) | `display_mode`, `passage_display` | anything else new |
| `AttemptResultOut`, `ReviewOut` | `result_view`, `passage_display` | scheme params, template ids |
| `ExamTemplatePickerOut` | 7b fields | `sandbox`, `unpublished_changes`, `draft_spec` |
| `ExamTemplateOut` (managers) | `sandbox`, `unpublished_changes` | other users' sandbox enrollments |
| `SpecDiffOut` | paths and values of the two specs | anything outside the two specs (no ids of assessments) |

---

## 7. Preview-attempt lifecycle

1. Author opens the **Sample questions** tab → `POST _T/sandbox` (idempotent) → `QuizEditor mode="sandbox"` on `/courses/{sandbox}/assessments/{sample}` under a `CourseContext` built from `GET /courses/{sandbox}` (staff shape; the course is reachable for its staff). Cards' type dropdown = `QUESTION_TYPES ∩ section.rules.allowed_types` (7c rule, nothing new).
2. "Preview as student" → `POST _T/preview` → the real player route `/[lang]/courses/{course_id}/attempts/{attempt_id}?return=<constructor path>`; new tab at `lg:` and up, same tab below. `PlayerShell` and `StudentResult` read `return` (`useSearchParams`) for "Back" links and `goResult` forwards it; absent (every ORT and course flow) → today's links. The amber `player.previewBanner` already marks previews.
3. Finishing the preview shows the real result page with the chosen `result_view` (ORT view with scaled scores when the scheme is a scaled one) and the review.
4. A second preview voids the open one (`fresh=True`, existing); finished previews beyond `SANDBOX_PREVIEW_KEEP` per user are deleted. Archiving the template keeps the sandbox (read-only through the 7c editor's lock on archived? no: the sandbox course stays editable only by managers; preview refuses 409). Nothing is scheduled; the attempt sweep handles expired previews as today.
5. Never in gradebook/stats: invariant 2; the sandbox course has no students, and `is_preview` rows are filtered everywhere a score is aggregated. Test `test_exam_template_sandbox.py::test_preview_never_scores` runs a preview to submit and asserts no `grade_events`, no `submissions`, an empty gradebook for the sandbox course and `/me/home` unchanged for the author.

---

## 8. Scrolling display mode (general player)

### 8.1 Architecture (one branch in `PlayerShell.tsx`, state logic shared)

`const scrolling = state.display_mode === "scrolling"`. State, autosave queue, timers, dialogs, palette groups, `visibleItems`, `currentPos`, `go()`, keyboard handling stay the same code. Only the question area (lines 690-725, the `ItemView` + Prev/Next block) gets a second rendering: **`ScrollingItems.tsx`** `({items: windowItems, state, content, answers, currentPos, onAnswer, onToggleFlag, onCurrentChange, stickyTop, passageDisplay})` renders every item of the current **window** as `<section id="item-<pos>" aria-labelledby="item-<pos>-h" tabIndex={-1} style={{scrollMarginTop}}>` containing the passage pane (shown once per passage group, sticky-free; `PassagePane` with `open` always true and the toggle hidden) and the existing `ItemView` with `number`/`total`. One-per-page rendering (ORT) is byte-identical: the branch is an `if` around the existing JSX.

**Section window**: `windowItems` = items of the section that contains `currentPos` (forward-only: `visibleItems` is already one section; free navigation: `visibleItems.filter(i => i.section_pos === curItem.section_pos)`), sliced to `SCROLL_WINDOW = 30` from `windowStart` (state, section-local); a sticky footer row offers "Show next 30" / "Show previous 30" when the section is longer, and "Next section" / "Previous section" (free navigation) or the existing finish button (last window of the section). Changing section = `setCurrentPos(first position of that section)` and `windowStart = 0`; no network in free navigation (whole payload), the existing per-section fetch in forward-only.

**Current item by viewport** (`useScrollSpy(itemRefs, enabled)`):
- one `IntersectionObserver`, `rootMargin: -<header height>px 0px -40% 0px`, thresholds 0..1 step 0.25;
- the entry with the largest `intersectionRatio` whose top is below the sticky header becomes current: `onCurrentChange(pos)` → `setCurrentPos`, coalesced per animation frame;
- suppressed for 400 ms after a programmatic scroll so palette jumps do not flicker;
- palette `onSelect`, `go(±1)`, ArrowLeft/Right call **`scrollToItem(pos)`** = `scrollIntoView({block: "start", behavior: reducedMotion ? "auto" : "smooth"})` then `focus({preventScroll: true})` on the item heading; a target outside the window moves the window first;
- palette highlight, counts, progress bar and the finish dialogs read `currentPos`/`visibleItems` exactly as today.

**Keyboard and a11y**:
- shortcuts act on the current item (same handler; `curItem` is now the viewport item); F flags it, 1–5 / A–E answer it;
- each item is a landmark: heading "Question n of N" (`player.questionOf`), `aria-current="true"` on the current `<section>`, `tabIndex=-1` for programmatic focus;
- the window footer actions are visible buttons (UX §4, no hidden features); focus never moves on viewport changes, only on explicit navigation;
- `prefers-reduced-motion` → instant scrolls; touch targets ≥ 44 px (existing `ItemView` rule); the phone palette sheet is unchanged.

**Autosave and timer when a section scrolls** (unchanged by construction):
- `onAnswer` queues per item on change; an answer typed below the fold is queued like any other (the queue is per item, not per page);
- the timer lives in the sticky header; `runSectionTimeout`/`closeSection` apply the new state → `applyState` sets `currentPos` to the next section's first item → the list re-renders for that section at `windowStart = 0` and scrolls to top;
- submit, time-up and closed dialogs are the same components; `SaveStatus` pill unchanged;
- performance: at most 30 `ItemView`s mounted; KaTeX renders per item as today; a 6,000-student start burst never loads more than one window per client.

### 8.2 Renderer selection from state (ORT-safe)

`PassagePane`/`TemplatePassage` and `ReviewItemCard` take `passageDisplay` from the attempt state / result payload (`passageRenderers[passage_display]`, `blocks.ts`) instead of `useTemplateUi()`; `ResultSummary` picks `OrtResultView` when `result.result_view === "ort"` instead of `ui.resultView`. Because the server resolves `NULL` to the course template's values (§5.4), ORT renders identically (unit test on the resolver + `ort-visual.spec.ts` zero diffs). `useTemplateUi` keeps serving builder screens and preset locks.

### 8.3 Settings on general assessments

`SettingsPanel` (quiz editor Settings tab) gains a "Display" group: `display_mode` radio (one per page / scrolling, with one-line descriptions), `passage_display` select (inherit from course / plain / numbered), `result_view` select (inherit / general / ORT-style scaled) — only rendered for `preset === "none"`; locked fields grey out with `examTemplates.lockedNote` as 7b does; `AVAILABLE_DISPLAY_MODES` = all. ORT exams keep `SectionBuilder` and never see the group.

---

## 9. Constructor (frontend)

### 9.1 Component tree (`frontend/src/components/lms/examTemplates/`)

```
ExamTemplateEditor.tsx          page shell (kept file; 7b plain form replaced): header + tabs Structure · Scoring · Display · Sample questions · Versions
├─ ConstructorHeader.tsx        title (LocalizedTextInput inline), ScopeBadge, TemplateStatusBadge, LockedBadge, "v3 · N unpublished changes" (unpublished_changes),
│                               SaveStatus (saved / saving / not saved: N problems / conflict), primary "Publish", secondary "Preview", MenuButton: Archive, Lock/Unlock (ReasonDialog), Promote, Download import format (per version)
├─ IssuesBar.tsx                server `spec_invalid` details (7b `specIssuesOf`/`useSpecIssueText`) as a list with "Go to" links (scrolls to the field, switches tab)
├─ StructureTab
│  ├─ SectionList.tsx           ordered cards; desktop drag via existing `useDragReorder` (assessments/useDragReorder.ts), Move up/down buttons always visible; "Add section" at the end
│  │  └─ SectionCard.tsx        collapsed row: handle, number, title (or "Untitled section"), chips: types, "passages", "min–max", time; expanded: title/instructions (LocalizedTextInput), key (auto from title, editable, pattern hint), time limit (minutes; only when forward-only), min/max items, allowed types (checkbox group from blocks.question_types with titleKey), allow passages (+ passage display override select), parameter binding note when bound
│  ├─ NavigationCard.tsx        radio free / forward-only (descriptions); forward-only reveals the section timers and the "sum ≤ total time" hint
│  ├─ ParametersCard.tsx        choice parameters: key, options (one per line), bound section select; max 5
│  └─ DefaultsCard.tsx          time limit, attempts (+unlimited), score policy, results policy, show correct answers, shuffle items / choices
├─ ScoringTab
│  ├─ SchemePicker.tsx          Select from blocks.scheme_versions grouped System / Mine (scope label), "No scheme (points)" option; P7B-2 note for platform/org scope
│  ├─ SchemePreview (reuse grading/schemes/SchemePreview.tsx with type + params loaded via GET /grading-schemes/{id}/versions/{no}; defaultPossible = sum of max_items or 100)
│  └─ ResultViewCard.tsx        radio from blocks.result_views (resultViews titleKey) with a thumbnail description
├─ DisplayTab
│  ├─ DisplayModeCard.tsx       radio from blocks.display_modes with two small illustrations (inline SVG, no images)
│  ├─ PassageDisplayCard.tsx    default passage display (blocks.passage_displays) + list of per-section overrides
│  └─ LockScopeCard.tsx         checkbox list from blocks.lock_scope_keys with plain-language effect per key
├─ SampleTab
│  ├─ SandboxGate.tsx           lazy POST sandbox; language select (first entry); loading/empty/error states; "Sample questions are only for previewing; they are never part of exams created from this template"
│  ├─ QuizEditor mode="sandbox" (7c; hides QuizPublishBar, Settings and Preview tabs, Save-as-template; keeps cards, sections read-only header, Find drawer)
│  └─ PreviewLauncher.tsx       language select (assessment languages), one Select per parameter, "Preview as student" (opens the player, §7), last issues list
└─ VersionsTab
   ├─ VersionsTable.tsx         no, published_at, by, scheme, actions: Download import format, Compare with previous, Compare with draft
   └─ DiffView.tsx              summary chips + grouped changes (General, Sections, Parameters, Locks); two columns at lg:, stacked before/after rows at 375 px; section add/remove as whole cards
```

`ExamTemplatesPage.tsx` (list) is unchanged except the "New template" dialog adding a display-mode starter choice; `TemplatePicker`, `TemplateBadge`, `SaveAsTemplateDialog`, `ImportValidationFields` unchanged. `SpecForm.tsx` is split into the cards above (the JSON disclosure stays for platform admins only).

### 9.2 State model

`draft: SpecDraft` (7b `specDraft.ts`, extended with `sectionPassageDisplay` already present, `uid`s for stable keys) is the single source; `base: ExamTemplateSpec` for dirty diffing; `draftRev`; `saveState: idle|saving|saved|invalid|conflict|error`; `issues: SpecIssue[]`; `serverTemplate: ExamTemplateOut`. **Autosave**: 1.5 s debounce after a change → client pre-check (`specOf(draft)` builds without throwing: every section has ≥ 1 type, keys match the pattern, bound sections have no key) → `PATCH {draft_rev, draft_spec}`; 200 → `draftRev = out.draft_rev`, `issues = []`, `saved`; 422 `spec_invalid` → `issues` mapped to fields, `invalid` (the server keeps the last valid draft; the local draft stays and is mirrored into `sessionStorage[examTemplateDraft:<id>]` for crash safety, offered on reload: "Restore unsaved changes?"); 409 `draft_conflict` → `DraftConflictDialog` (7c reuse: take theirs / keep mine → re-PATCH with the new rev). Publish: flush, then `POST publish`; `unchanged: true` → toast "Nothing new to publish". Locked or archived templates render read-only (`readOnly` prop everywhere; actions hidden, reason shown). Sample tab and preview read `draftRev` to warn "Save first" when `saveState !== saved` (the server syncs the sample from the stored draft).

### 9.3 Mobile (375 px)

Tabs scroll horizontally (design-system `Tabs`); section cards full width with Move up/down buttons (drag handle hidden below `sm`); chips wrap; the scheme preview table keeps 3 columns (raw, scaled, grade) with the rest behind "Details"; diff stacks before/after; the Sample tab shows the 7c editor as on a phone (cards, bottom-sheet dialogs); preview opens in the same tab and returns via `return`. Long ru/ky labels tested per UX §5.

---

## 10. i18n groups (en/ky/ru; parity script)

**`examTemplates.constructor.*`** (tabs, header actions, saveState.*, issuesBar.*, section.* incl. `untitled`, `typesChips`, `countsChip`, `moveUp/moveDown`, `addSection`, navigation.*, parameters.*, defaults.*, scoring.* incl. `noScheme`, `previewPossible`, resultView.*, displayMode.* with `onePerPage.body`/`scrolling.body`, passageDisplay.*, lockScope.<key>.effect, restoreDraft.*), **`examTemplates.sandbox.*`** (gate body, language, note, errors.*), **`examTemplates.preview.*`** (launch, parameters, issues.*, backToTemplate), **`examTemplates.diff.*`** (compareWith, draft, summary.*, groups.*, added, removed, changed, noChanges), **`player.scrolling.*`** (showNext, showPrevious, nextSection, previousSection, windowOf), **`assessments.settings.display.*`** (group, displayMode.*, passageDisplay.* incl. `inherit`, resultView.* incl. `inherit`), **`lms.errors.{preview_not_ready, nothing_to_preview, language_not_in_assessment, sandbox_course, version_not_found}`**. Glossary: "template" = ky "шаблон", ru "шаблон"; "preview" = ky "алдын ала көрүү", ru "предпросмотр"; "sample questions" = ky "үлгү суроолор", ru "примеры вопросов".

---

## 11. Slices, ownership, order, models

Branches `phase-8b-s<n>-<name>` off **`phase-8b`** (created from `origin/phase-8a`, or from `lms` once 8a is merged). Delimited blocks `# --- Phase 8b S<n> begin/end ---` in shared files. The orchestrator merges and reviews every diff. **S1 runs alone** (a migration exists), then S2 ∥ S3 ∥ S4, then S5.

| Slice | Model | Scope | Owns (exclusive) |
|---|---|---|---|
| **S1** migration + shapes | opus | §2; `ids.py` codes/audit/constants; `schemas.py` S1 block (`SandboxOut`, `PreviewIn/Out`, `SpecDiffOut`, `SpecChange`); `ExamTemplateOut.sandbox/unpublished_changes` fields (filled by S2); `AttemptStateOut`/`AttemptResultOut`/`ReviewOut` display fields + `attempts/display.py` resolver (§5.4) wired in `engine.build_state`, `results.py`; `AssessmentUpdateIn` fields + builder guards (§5.3); delete `_assert_display_mode`; `courses/scopes.py::regular_courses()` + all §5.1 filters + `assert_not_sandbox` guards; `policies.py` stub entries + inventory block; `blocks.ts` `AVAILABLE_DISPLAY_MODES`; `attemptTypes.ts`/`assessmentTypes.ts`/`examTemplateTypes.ts` additive types; tests `test_migration_0013.py`, `test_attempt_display_resolver.py`, `test_assessment_display_settings.py`, `test_sandbox_hidden_from_lists.py` (with a fixture that inserts a sandbox row directly) | `alembic/versions/0013_phase8b_template_sandbox.py`, blocks in `courses/{models,scopes,service}.py`, `organizations/service.py`, `platform_admin/{courses_router,users_service}.py`, `exam_templates/{ids,schemas,policies,scopes(146)}.py`, `assessments/{schemas,builder}.py`, `attempts/{schemas,serializers,engine,results}.py`, `attempts/display.py`, `exam_templates/instantiate.py` (delete only), `core/{route_inventory,config}.py`, `frontend/src/lib/lms/{blocks,attemptTypes,assessmentTypes,examTemplateTypes}.ts`, the four tests |
| **S2** sandbox, preview, diff | **fable** (authorization, enrollments, transactions) | §5.1, §5.2, §6.1: `sandbox.py`, `diff.py`, `apply_spec` extraction, router + policies fill, `service.promote` hook, `manage_out` fields, audit, tests `test_exam_template_sandbox.py` (ensure idempotent; staff enrollment and cache bust; sync by position keeps items and drops counts; `preview_not_ready` on empty section; parameters default; voids previous open preview; `SANDBOX_PREVIEW_KEEP`; `test_preview_never_scores`; archived 409; non-manager 404; promote revokes), `test_spec_diff.py` (table: scalar, set, keyed/unkeyed sections, parameters, order, draft target 404 for readers), `test_pg_concurrency_sandbox.py` (two `ensure` race → one course) | `exam_templates/{sandbox,diff}.py`, `exam_templates/{router,policies,service,instantiate}.py` blocks, `tests/lms/test_exam_template_sandbox.py`, `test_spec_diff.py`, `test_pg_concurrency_sandbox.py` |
| **S3** player + display settings | opus | §8: `ScrollingItems.tsx`, `useScrollSpy.ts`, the `PlayerShell` branch, `return` param, renderer-from-state in `PassagePane`/`TemplatePassage`/`ReviewItemCard`/`ResultSummary`, `SettingsPanel` display group, Playwright `scrolling-player.spec.ts` + general-player baselines, `ort-visual.spec.ts` must stay zero-diff | `components/lms/player/**`, `components/lms/results/{ResultSummary,StudentResult,ReviewItemCard}.tsx`, `components/lms/PlainPassage.tsx`, `components/lms/assessments/SettingsPanel.tsx`, `frontend/e2e/scrolling-player.spec.ts`, `seed_backend.py::seed_scrolling` (own function), i18n `player.scrolling.*`, `assessments.settings.display.*` |
| **S4** constructor | opus (sonnet for i18n and `DiffView`) | §9, §10: all constructor components, autosave state, sandbox tab (`QuizEditor mode="sandbox"` prop, one conditional), preview launcher, versions + diff, API clients, i18n | `components/lms/examTemplates/**` (except `TemplatePicker`, `TemplateBadge`, `SaveAsTemplateDialog`, `ImportValidationFields`), `components/lms/quiz/QuizEditor.tsx` (mode block), `lib/lms/examTemplates.ts`, three route pages, i18n `examTemplates.*`, `lms.errors.*` |
| **S5** integration + gates | orchestrator + ux-reviewer (fable) + architect security review (fable) | Playwright `exam-constructor.spec.ts` (§12), full suites SQLite + PG, `alembic check`, ORT review §13, UX gate §14, `/security-review` (sandbox reachability by non-staff, IDOR on `POST sandbox/preview`, diff draft leak, `return` open-redirect: must be a same-origin path starting with `/<lang>/`), i18n parity, `next build` (rsync copy), `PHASE_8B.md`, `PRODUCT_DECISIONS.md` (P8B-*), handoff + memory, owner checkpoint list | docs, `docs/phases/PHASE_8B_screens/**`, `frontend/e2e/exam-constructor.spec.ts`, `seed_backend.py::seed_constructor` |

**Gates per slice**: SQLite suite green; route-inventory test; action × role × status tests for new routes; serializer contracts (student payloads gain only the three display fields; `ExamTemplatePickerOut` never carries `sandbox`); `tsc --noEmit` (S3, S4). **Phase gates (before `lms`, again before `main`)**: SQLite and PG suites, `alembic upgrade head && alembic check`, `test_migration_0013.py` both engines, PG concurrency, ORT review §13, UX gate §14, security review, i18n parity, `next build`, migration rehearsal on a production copy, **Neon snapshot before the `main` merge** (`pre-8b-<date>`, as 7b: branch limit), `/health` shows the commit, then the **owner checkpoint**.

---

## 12. Tests

- **Backend** (scratch SQLite + PG): the slice tests of §11 plus updates to `test_exam_template_instantiate.py` (scrolling now allowed; snapshot carries `display_mode = scrolling`), `test_exam_template_locks.py` (display fields × lock scope), `test_blocks_contract.py` (`AVAILABLE_DISPLAY_MODES` ⇔ `DISPLAY_MODES`; new i18n keys exist), `test_serializer_contracts.py`, `test_route_inventory.py`, `test_ort_seed.py` (ORT courses `sandbox_for_template_id IS NULL`).
- **Block-catalog contract**: `test_blocks_contract.py` additionally parses the constructor's pick-list sources: a regex over `components/lms/examTemplates/**` asserts no literal block key (`"one_per_page"`, `"numbered"`, `"ort"`, type names…) appears outside `blocks.ts` and test files (the "no key is hard-coded" rule as code).
- **Playwright `exam-constructor.spec.ts`** (seeded by `seed_backend.py::seed_constructor`: an org admin, a teacher, a student, a general course): org admin designs a two-section template (section 1 single choice, 10 min; section 2 passages allowed, numbered), scrolling mode, ORT-style scaled scheme, result view ORT, lock `sections`; writes two sample questions in the Sample tab (type dropdown limited); previews (player opens with the amber banner, scrolling list, palette sync); publishes; the teacher creates a quiz from it in the course (`TemplatePicker`), adds questions, publishes, student takes it (scrolling), sees the result; the org admin locks the template → the teacher's builder refuses a section rename (409 note); versions tab shows the diff after a second publish. Screenshots at 375 and 1440.
- **Playwright `scrolling-player.spec.ts`**: 45-item section renders 30, "Show next 30" reveals the rest; scrolling moves the palette highlight; palette click scrolls and focuses; ArrowRight/Left and `KeyF` act on the viewport item; answers autosave (network idle → saved pill); forward-only section close lands on the next section's first item; 375 px: no horizontal scroll, palette sheet works; reduced motion → instant scroll. Baselines for the general player saved under `docs/phases/PHASE_8B_screens/general-player/`.

### 12.1 Walkthrough (S5; dated in `PHASE_8B.md`)

1. Platform admin: new template "Entrance test" → two sections (comparison only, 20 min; single choice + passages, 40 min), forward-only, scrolling, ORT main scheme, result view `ort`, lock `sections` + `display_mode` → autosave shows "Saved" → Sample tab: three sample questions (the type dropdown offers only the section's types) → Preview: player in scrolling mode, palette follows the scroll, finish → ORT-style result with a scaled score → Publish v1.
2. Org admin of a school: sees the platform template read-only; creates an organization template from scratch, previews, publishes; a teacher of the school creates a quiz from it (`TemplatePicker`), imports a general CSV with validation, publishes, a student takes it on a phone (375 px) in scrolling mode, result page general.
3. Org admin edits the template (adds a section), publishes v2 → Versions tab shows the diff v1 → v2 and "Newer version available" in the teacher's builder; the teacher upgrades a fresh draft.
4. Org admin locks the template → the teacher's builder refuses to rename a section (409 note); `structure-unlock` by the org admin after join-as-teacher works as 7b.
5. Teacher: changes a plain quiz's display to scrolling + numbered passages in Settings → takes the preview → review shows numbered passages.
6. ORT course: CSV + zip upload, build, take, result; screens compared against `ORT_BASELINE` (zero diffs).

---

## 13. ORT review plan (nothing changes; proofs)

Why nothing changes: ORT exams are `preset` exams (`display_mode one_per_page`, `passage_display`/`result_view` NULL) → §5.4 resolves to the ORT course template's `numbered`/`ort`; `PlayerShell`'s one-per-page JSX is unchanged (the scrolling branch is an `if` ORT never enters); `SettingsPanel`'s display group is hidden for presets and the builder guards answer 409 `template_locked` for ORT; `SectionBuilder`, importers, `build_snapshot`, engine, `OrtResultView` untouched; the sandbox is a hidden general course; `return` is absent in every ORT URL.

| Proof | How |
|---|---|
| Imports identical | `test_ort_import_golden.py` and `test_import_*` green; `git diff --stat phase-8a -- backend/app/lms/content/importers/` empty |
| Scores, flow, seed | `test_ort_parity.py`, `test_ort_e2e_api.py`, `test_ort_cutover_flow.py`, `test_ort_gradebook_golden.py`, `test_ort_seed.py` green; `test_attempt_display_resolver.py::test_ort_resolves_to_numbered_ort_one_per_page` |
| Player and results pixel-identical | `frontend/e2e/ort.spec.ts` unchanged and green; `ort-visual.spec.ts` against `docs/phases/ORT_BASELINE/` with **zero** diffs (player, result, review, builder); `git diff phase-8a -- frontend/src/components/lms/player/PlayerShell.tsx` reviewed line by line: only the `scrolling` branch, the `return` link and the `passageDisplay` prop pass-through |
| Expressibility | `test_ort_expressibility.py` still green (now also instantiates with `display_mode one_per_page` explicitly) |
| Walkthrough | ORT CSV + zip upload, build, take, result in an ORT course; then a general course: template with scrolling → quiz → take → result; the ORT exam card and Start flow identical |
| Report | `PHASE_8B.md` ORT section: test names, diff check, walkthrough date, screenshots |

---

## 14. UX gate screens (`docs/phases/PHASE_8B_screens/`, 375 px + 1440 px; student screens en/ky/ru, admin/teacher ru)

Student: scrolling player (top of section, mid-scroll with palette highlight, window footer, passage group, 375 palette sheet), one-per-page general player (unchanged, regression shot), result page with `result_view = ort` on a general quiz, result page general, review with numbered passage. Teacher/admin: constructor header + Structure tab (empty, two sections, one expanded, issues bar), Navigation forward-only with timers, Parameters card, Scoring tab with the live preview table, Display tab (mode illustrations, lock scope), Sample tab (gate, editor with limited type dropdown, preview launcher with parameters), Versions tab + DiffView (desktop two-column, phone stacked), lock/promote dialogs, read-only locked state, settings "Display" group in a general quiz, ORT builder (unchanged, regression shot). Teacher area, org area and platform area variants of the header (breadcrumbs differ).

---

## 15. Decisions taken here (to `PRODUCT_DECISIONS.md` as P8B-1 … when applied)

| # | Decision |
|---|---|
| P8B-1 | One **sandbox course per template** (`courses.sandbox_for_template_id`, migration 0013) holds the sample quiz; its staff are the template's managers, enrolled lazily; it is never published, listed or joinable. |
| P8B-2 | Preview attempts reuse the existing staff preview path (`is_preview`, `ensure_preview_version`, `fresh=True`); no new attempt flag; finished previews are capped at 20 per author per template. |
| P8B-3 | The sample quiz mirrors the draft by position, keeps items, and drops `min_items`/`max_items` so a preview never demands 30 sample questions. |
| P8B-4 | `passage_display` is governed by the `result_view` lock key (`LOCK_RESULT_VIEW`); no new lock-scope key. |
| P8B-5 | Scrolling mode = one section at a time, windows of 30 items, viewport-tracked current item, Prev/Next scroll; the engine and autosave are untouched. |
| P8B-6 | Renderers are chosen from the attempt/result payloads with a server-side course-template fallback; `useTemplateUi` no longer decides passage or result rendering in the player and result pages. |
| P8B-7 | Constructor drafts autosave (1.5 s) only when the client pre-check passes; invalid drafts stay local with a visible status and a `sessionStorage` mirror; the 7b strict `PATCH` contract is unchanged. |
| P8B-8 | The diff is computed on request (`GET diff`), sections matched by key then position; nothing stored. |
| P8B-9 | Sample questions are never copied into exams created from the template (B11 stays true: templates share structure only). |

---

## 16. Alternatives to discuss (owner checkpoint after 8b; each has a default in effect)

| # | Question | Options | Default |
|---|---|---|---|
| **Q1** | **Sandbox storage.** A hidden course per template is simple and reuses every tool, but adds one course + bank per template to the database. | (a) sandbox course per template (built); (b) sandbox per author (samples of several templates in one place; managers of one template would see each other's other samples); (c) no persistent samples: auto-generated placeholder questions at preview time, no Sample tab. | **(a)** |
| **Q2** | **Who may preview.** Only managers can open the sandbox and preview. Teachers who can merely pick a template see its structure summary. | (a) managers only (built); (b) every teacher who can see the template may run a read-only preview on the manager's sample questions (needs a read-only staff role on the sandbox or a copied snapshot: S–M). | **(a)** |
| **Q3** | **Scrolling window size and section switch.** 30 items per window, one section at a time. | (a) 30 / one section (built, config constant); (b) whole section without windows (simpler; slow on long sections on phones); (c) all sections in one scroll (free navigation only). | **(a)** |
| **Q4** | **Constructor saving.** Autosave of valid drafts. | (a) autosave (built); (b) explicit Save button as in 7b. | **(a)** |
| **Q5** | **Result-view choice on general quizzes.** A teacher may give any general quiz the ORT-style scaled result page (meaningful only with a scaled scheme). | (a) allow (built; the view shows "no scaled score" copy when the scheme has none); (b) allow only when the scheme is a scaled type. | **(a)** |
| **Q6** | **Moving ORT onto the constructor.** 7b's expressibility test and 8b's constructor make it possible; B1 said not now. | (a) keep ORT on presets (built); (b) decide a later phase for the switch with the parity test as the gate. | **(a)** |
