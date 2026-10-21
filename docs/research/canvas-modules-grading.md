# Canvas modules, sequencing and grading: what the real code does, and what we should build

**Source**: `instructure/canvas-lms`, shallow clone at commit `1c9f0bb` (2026-04-30). Read only, not executed. Paths are relative to the repo. "Verified" means I read the code. "Unverified" means I inferred it (for example controller behavior, since `app/controllers` was not checked out).
**Scope**: modules and gating, assignments, submissions, grading schemes, gradebook math, late policy, quiz to assignment, pages and files as module items.

---

## 1. What Canvas actually does

### 1.1 Modules (`app/models/context_module.rb`, table `context_modules`)
**Columns** (from `db/migrate/20101210192618_init_canvas_db.rb`): `context_id/type` (polymorphic, restricted to `:course`), `name`, `position`, `prerequisites` and `completion_requirements` (both `serialize`d text), `workflow_state` (`active`/`unpublished`/`deleted`), `deleted_at`, `unlock_at`, `require_sequential_progress` (boolean, no default, so null means false), `requirement_count`.

**Prerequisites**: an array of `{id, type:"context_module", name}`, with no FK. `validate_prerequisites` (before_save) **silently drops any prerequisite whose position is not lower than this module's**, which is how cycles are prevented. `gather_prerequisites` also drops ids that no longer exist, using a cached `module_names` map.

**Completion requirements**: an array of `{id: content_tag_id, type, min_score|min_percentage}`. The types are `must_view`, `must_mark_done`, `must_contribute`, `must_submit`, `min_score` and `min_percentage`. `validate_completion_requirements` drops requirements whose tag is missing or deleted, and drops scored types on tags that are not scoreable. `ContentTag#destroy` calls `remove_completion_requirement`. `requirement_count == 1` means "complete one" instead of "complete all" (`requirement_type`).

**Delete and restore**: `destroy` is a soft delete. It also deletes the tags with the same timestamp. `restore` revives the tags deleted within ±5 s, and the module comes back `unpublished`.

**Relocking**: `relock_warning_check` raises a warning when a teacher adds a requirement, a prerequisite or an `unlock_at`. The teacher then *chooses* to call `relock_progressions`, which bulk-sets progressions to `locked`, recurses into dependent modules and queues re-evaluation. Removing a rule never relocks anything.

### 1.2 Module items (`app/models/content_tag.rb`, table `content_tags`)
`ContentTag` is a shared polymorphic link table that also stores learning-outcome alignments. Module items are the rows with `tag_type="context_module"` (see `add_item`).

**Columns**: `content_id/content_type` (no FK), `context_module_id` (FK), `position`, `indent`, `title`, `url`, `new_tab`, `workflow_state` (`active`/`unpublished`/`deleted`). `CONTENT_TYPES` includes `Attachment`, `Assignment`, `WikiPage`, `Quizzes::Quiz`, `DiscussionTopic`, `ContextExternalTool` and others, plus the tableless types `ExternalUrl` and `ContextModuleSubHeader`. An application-level inclusion validation is the only type check.

**Publish state is mirrored**: `asset_workflow_state` derives the tag's state from the asset, and `ContentTag.update_for(asset)` pushes title and state to every tag pointing at that asset. It also works in reverse: `update_asset_workflow_state!` publishes the asset when the tag is published.

**`scoreable?`** is true for quizzes and for assignment-backed content. A `WikiPage` is never scoreable.

**Cache signal**: every tag save touches the module's `updated_at`, which is how cached progress is invalidated (§1.3).

### 1.3 Per-student progress (`app/models/context_module_progression.rb`)
**Columns**: `(user_id, context_module_id)` unique, `workflow_state` (`locked`, `unlocked`, `started`, `completed`; `locked` is the initial state), `requirements_met` and `incomplete_requirements` (serialized; the latter keeps the best score on unmet `min_score` items), `current_position`, `completed_at`, `current`, `evaluated_at`, `lock_version` (optimistic lock).

**`evaluate`** (wrapped by `evaluate!`, which retries on `StaleObjectError`):
1. Progressions are created lazily, for enrolled users only.
2. `outdated?` skips the work unless `current=false`, the module's `updated_at` is later than `evaluated_at`, or `unlock_at` has passed since the last evaluation.
3. Unpublished modules are not evaluated at all.
4. `check_prerequisites`: if `unlock_at` is still in the future, nothing changes. If the progression is `locked` and every prerequisite progression (evaluated recursively) is `completed`, it becomes `unlocked`. **Evaluation never sets `locked` again**: only the teacher-triggered relock does.
5. `evaluate_requirements_met`:
   - It starts from the stored `requirements_met`, minus the `min_*` entries, which are recomputed from submissions every time. View, done and submit stay met once met; scores do not.
   - An excused submission counts as met.
   - `must_view` is also satisfied by any other action on the item.
   - `must_submit` is met by a submission in state submitted, graded, complete or pending_review, but not by a manual grade with no attempt.
   - Scored requirements use `QuizSubmission.kept_score` or `Submission.score`, and ignore **unposted** grades.
   - The resulting state is `completed` when all requirements are met (or `requirement_count` of them), `started` when any is met or attempted, `unlocked` otherwise.
6. `evaluate_current_position` (sequential modules only): `current_position` is the position of the **first tag with unmet requirements**. Tags without requirements never block. `locked_for_tag?` locks the tags with `position > current_position`.
7. On save, if the state moved into or out of `completed`, dependent modules' progressions are set to `current=false` and re-evaluated in delayed jobs (`trigger_reevaluation_of_dependent_progressions`).

**Triggers**:
- `Submission#context_module_action` (delayed) sends `:scored` or `:submitted`.
- `WikiPage#context_module_action` and `Attachment#context_module_action` send `:read`. The call site is in a controller, so this is unverified.
- Both paths go through `ContextModule#update_for`, then `update_requirement_met!`, then a delayed `evaluate!`.
- Module edits run `invalidate_progressions`: a batched `current=false` plus a singleton job, `evaluate_all_progressions`.
- `available_for?(deep_check_if_needed:)` evaluates on access.

Admins (`read_as_admin`) bypass all locks.

### 1.4 Assignments, submissions, quizzes
**Assignment types**: `Assignment < AbstractAssignment` (STI on `type`, in `app/models/abstract_assignment.rb`). `ALLOWED_GRADING_TYPES = points percent letter_grade gpa_scale pass_fail not_graded`. Other relevant columns: `grading_standard_id` (a per-assignment scheme), `omit_from_final_grade`, and `workflow_state` (published, unpublished, deleted, and others).

**The number is canonical, the label is derived**: `Submission.score` (points) is the truth, and `Submission.grade` is a cached string built by `score_to_grade`:
- `percent`: score/possible×100;
- `pass_fail`: complete if score > 0;
- `letter_grade` and `gpa_scale`: a GradingStandard lookup on the percentage.

`grade_to_score` and `interpret_grade` parse `"85%"`, `"B+"` or `"pass"` back into points. When `points_possible`, `grading_type` or `grading_standard_id` changes, `update_student_submissions` rewrites the stored grades and queues `course.recompute_student_scores`.

**`submissions`**: unique `(user_id, assignment_id)`, so there is one row per student per assignment, with an `attempt` counter. Other columns: `workflow_state` (submitted, unsubmitted, pending_review, graded, deleted), `excused`, `posted_at` (grade visibility), `points_deducted`, `late_policy_status`, `quiz_submission_id`. History is kept by `simply_versioned` and `Auditors::GradeChange` (`grade_change_audit`).

**Quiz to assignment** (`app/models/quizzes/quiz.rb`):
- A quiz with `quiz_type` `assignment` or `graded_survey` (`graded?`) gets an Assignment through `build_assignment` (`submission_types:"online_quiz"`). `update_assignment` keeps title, points, dates, group and publish state in sync.
- `practice_quiz` and `survey` have **no** Assignment and never reach the gradebook.
- `QuizSubmission.score_to_keep` applies `scoring_policy` (`keep_highest`, `keep_latest` or `keep_average`) and writes the result into the single Submission.

### 1.5 Grading schemes (`app/models/grading_standard.rb`)
A GradingStandard is **only a cutoff table**. `data` is a serialized array of `[label, min_fraction]` (version 2 uses lower bounds), and it belongs to a course or an account.
- `score_to_grade(pct)` returns the highest band at or below the score.
- Validations: no negative or duplicate cutoffs, and the table must include 0.
- `points_based` and `scaling_factor` allow bands expressed in points.
- Lookup order (`grading_standard_or_default`): assignment, course, account, then the built-in A–F.
- It is soft-deletable, and a scheme with graded submissions cannot be deleted (behind a feature flag).
- **`data` is not versioned.**
- **There is no curve or normative scaling anywhere in Canvas.**

### 1.6 Gradebook (`lib/grade_calculator.rb`, `assignment_group.rb`, `score.rb`)
**Groups**: `AssignmentGroup` has `group_weight`, a `rules` text (`drop_lowest:N\ndrop_highest:N\nnever_drop:id`) and the states `available`/`deleted`. Weights apply only when the course has `group_weighting_scheme == "percent"`.

**Per group**, `create_group_sums` works as follows:
- It skips unposted and pending_review submissions, excused items and `omit_from_final_grade` items.
- The *current* score ignores ungraded work; the *final* score counts it as 0.
- It applies the drop rules, choosing the drops that maximize the student's grade (`drop_assignments`).
- It then sums the points.

**Course total**: weighted is Σ(score/possible × weight) over groups that have possible points, rescaled when the weights sum to less than 100. Unweighted is Σscore/Σpossible.

**Caching**: results are stored in `scores`, with one row per enrollment for the course, per group or per grading period. Each row holds `current_score`, `final_score`, the `unposted_*` variants and `override_score`. Recomputation is `recompute_student_scores`, a singleton delayed job per course.

### 1.7 Late policy and pages/files
**Late policy** (`late_policy.rb`, `lib/late_policy_applicator.rb`):
- One row per course: missing deduction %, late deduction % per hour or day, and a minimum floor.
- `Submission#apply_late_policy` stores `points_deducted` and lowers `score`. `entered_score = score + points_deducted` recovers the raw value.
- Manual `late_policy_status` values override the computed ones.

**Pages and files**: `WikiPage` (active/unpublished/post_delayed, versioned) and `Attachment` (`file_state`) become module items only through ContentTag. They only report `:read`, so only view or done requirements apply to them.

**Integrity summary**:
- No FK: `context_type/id` everywhere, `ContentTag.content_type/id`, and the prerequisite and requirement ids stored in serialized text.
- Real FKs: `content_tags.context_module_id`, `context_module_progressions` (unique pair), `submissions` (unique pair), `scores.enrollment_id`.
- Everything else relies on before_save filters (several of which **drop bad data silently**), mirror callbacks, after-commit jobs and optimistic locking.

---

## 2. Corrections to the drafts

**`CANVAS_INTEGRATION_SPEC.md`**

| Draft claim | Reality |
|---|---|
| §4.1 prerequisites `[{id,name}]` | They are `{id,type,name}` and must point to an earlier module, otherwise they are silently dropped. |
| §4.1 four requirement types | There are six (adding `min_percentage` and `must_contribute`), plus "complete one" (`requirement_count`). |
| §4.2 ContentTag is the module item table | It is a shared table (`tag_type`). The draft omits Files, ExternalUrl, SubHeader and the `deleted` state. |
| §4.3 `current_position` = index of the furthest unlocked item | It is the tag position of the first item with unmet requirements. |
| §4.4 `evaluate_progression(user)` re-checks on every event | The real methods are `evaluate_for`/`evaluate!`. Evaluation is lazy, cached, partly delayed, and never relocks. |
| §4.4 sequential = item N−1 met | It is "all earlier requirements met". Items without requirements do not block. |
| §6.1 every graded activity is an Assignment | Only graded quizzes are. Practice quizzes and surveys have no Assignment. |
| §6.1 four grading types | There are six (adding `gpa_scale` and `not_graded`). |
| §6.2 Submission | One row per user per assignment. `score` is canonical, `grade` is derived. Omitted: `excused`, `posted_at`, late fields, versions and audit. |
| §8 JSON `prerequisites`/`completion_requirements`; `require_sequential_progress` default True | This copies Canvas's weakest part. Canvas's default is null (off). |
| No GradingStandard, AssignmentGroup, Score or late policy | These are the core of grading and are missing. |

**`CANVAS_EXPLAINER_FOR_FOUNDER.md`**:
- The "5 item types" miss Files and headers.
- "Score < 80% → gated" is partly right. A failed `min_score` leaves the module `started`, a retake can pass it (the kept score follows `scoring_policy`), but a later regrade does not relock modules that have already opened.
- An "ORT scaled curve" grading option does not exist in Canvas. It has to be our own scheme type.

## 3. Recommendation for our product

Principles:
- Real FKs, with no polymorphic `content_type/id` pairs.
- No JSON rule blobs.
- Store numbers and derive labels from them.
- Make scheme versions immutable.
- Use soft delete (`deleted_at`, `deleted_by`) on everything a teacher edits.
- Make history append-only.

Everything is scoped by `course_id`. There are no sections.

### 3.1 Modules and items

```
course_modules
  id PK, course_id FK courses NOT NULL, title, position INT NOT NULL,
  published BOOL NOT NULL DEFAULT false, unlock_at TIMESTAMPTZ NULL,
  sequential BOOL NOT NULL DEFAULT false,
  completion_mode TEXT NOT NULL DEFAULT 'all' CHECK IN ('all','any'),
  rules_version INT NOT NULL DEFAULT 1,    -- bump on any gating change (cache key)
  created_at, updated_at, deleted_at, deleted_by
  UNIQUE (course_id, position) WHERE deleted_at IS NULL  (DEFERRABLE if reorder in one txn)

module_prerequisites
  module_id FK course_modules, prerequisite_module_id FK course_modules,
  PK (module_id, prerequisite_module_id), CHECK (module_id <> prerequisite_module_id)
  -- service rule: prerequisite.position < module.position and same course → no cycles
  -- (reject with 422, do not silently drop like Canvas)

module_items
  id PK, module_id FK NOT NULL, position INT NOT NULL, indent SMALLINT DEFAULT 0,
  title_override NULL, published BOOL NOT NULL DEFAULT false,
  kind TEXT NOT NULL CHECK IN ('page','file','assessment','url','header'),
  page_id FK pages NULL, file_id FK files NULL, assessment_id FK assessments NULL,
  url TEXT NULL,
  CHECK exactly-one target matches kind (num_nonnulls(...) = 1, or 0 for 'header'),
  created_at, updated_at, deleted_at, deleted_by
  UNIQUE (module_id, position) WHERE deleted_at IS NULL

item_completion_requirements
  item_id PK FK module_items  (0..1 per item; Canvas allows several per tag, needless)
  type TEXT NOT NULL CHECK IN ('view','mark_done','submit','min_score','min_percent'),
  threshold NUMERIC NULL,
  CHECK ((type IN ('min_score','min_percent')) = (threshold IS NOT NULL))
  -- service rule: submit/min_* only when item.kind = 'assessment'
```

These are typed nullable FK columns with a CHECK constraint, in place of Canvas's `content_type/content_id`. The FKs are real, deletes are prevented, and the item kinds we support form a closed set.

`published` lives on the item (unlike Canvas's mirroring). An item is visible only when the item, its module and its target are all published and none of them is deleted. Computing visibility this way, instead of syncing it, removes `ContentTag.update_for` and its whole class of bugs.

### 3.2 Per-student progress

```
item_progress            -- append-only facts, the source of truth
  id PK, enrollment_id FK, item_id FK, event TEXT CHECK IN ('viewed','marked_done','submitted','scored'),
  score_percent NUMERIC NULL, submission_id FK NULL, created_at

module_progress          -- derived cache, rebuildable from facts + rules
  enrollment_id FK, module_id FK, PK (enrollment_id, module_id),
  state TEXT CHECK IN ('locked','unlocked','started','completed'),
  unlocked_at, completed_at NULL, current_position INT NULL,
  evaluated_rules_version INT, evaluated_at, version INT (optimistic lock)

item_requirement_status  -- derived, one row per (enrollment,item with requirement)
  enrollment_id, item_id, met BOOL, best_score_percent NULL, met_at NULL, PK(enrollment_id,item_id)
```

Progress is keyed by `enrollment_id`, not by user, so that leaving and re-enrolling, and soft-deleting an enrollment, stay clean.

### 3.3 Gating algorithm (synchronous; course sizes are small)

`evaluate(enrollment, module)`:
1. If the module or course is unpublished or deleted, return `locked` without storing anything. Teachers bypass all of this.
2. If a `module_progress` row exists with `evaluated_rules_version = module.rules_version`, `evaluated_at > max(fact timestamps for this enrollment in this module)`, and no `unlock_at` crossed since `evaluated_at`, return the cached row.
3. **Unlock**: the module is open if `now ≥ unlock_at` and every prerequisite's `evaluate(...)` is `completed`. The positional prerequisite rule means the recursion goes strictly backwards. Evaluate prerequisites in position order and memoize them for the request.
4. **Requirements**: for each visible, published item with a requirement:
   - `view`, `mark_done`: a matching fact exists. A `submitted` or `scored` fact also satisfies `view`.
   - `submit`: a `submitted` fact exists.
   - `min_score`, `min_percent`: compare against the assessment's **kept** result from the submission (§3.5), using only released results. Store the best score in `best_score_percent`.
5. State:
   - `completed` if all requirements are met (or, in `any` mode, at least one is met), or if the module has no requirements and is open;
   - `started` if at least one is met or attempted;
   - `unlocked` otherwise.
6. If the module is `sequential`, set `current_position` to the position of the first item with an unmet requirement. Items with `position > current_position` are locked.
7. Save the row. If `completed` changed, mark the cached rows of modules that list this one as a prerequisite as stale, for this enrollment only.

Triggers:
- **Student facts**: a view, mark-done or submission event writes the fact and evaluates that module, then its dependents, inside the same request.
- **Teacher edits**: changing rules, publish state, items or `unlock_at` bumps `rules_version`. This invalidates every cached row lazily. There is no batch job.
- **Policy decision: relock or not.** Canvas never relocks automatically. We can recompute fully, which relocks if a regrade drops a score below the threshold, or keep Canvas's "once unlocked stays unlocked". I recommend Canvas's behavior plus an explicit teacher action, "re-apply rules", that clears the cache.

### 3.4 Pluggable grading schemes

```
grading_schemes            -- owned by a teacher (or system-provided, owner NULL)
  id PK, owner_user_id FK NULL, title, type TEXT NOT NULL CHECK IN
    ('points','percent','bands','pass_fail','piecewise_curve','lookup_table'),
  created_at, deleted_at

grading_scheme_versions    -- immutable once referenced
  id PK, scheme_id FK, version INT, UNIQUE(scheme_id, version),
  scale_min NUMERIC NULL, scale_max NUMERIC NULL,          -- e.g. 60 / 245
  pass_threshold_percent NUMERIC NULL,                     -- pass_fail
  percentile_mean NUMERIC NULL, percentile_sd NUMERIC NULL,-- optional normal-CDF percentile
  rounding TEXT NOT NULL DEFAULT 'half_up_int', created_at

grading_scheme_bands       -- for 'bands' (letters / 5-point / any labels)
  version_id FK, lower_bound_percent NUMERIC, label TEXT, gpa_value NUMERIC NULL,
  PK(version_id, lower_bound_percent); service: must include 0

grading_scheme_curve_segments  -- for 'piecewise_curve' (ORT)
  version_id FK, from_ratio NUMERIC, to_ratio NUMERIC, out_from NUMERIC, out_to NUMERIC,
  exponent NUMERIC, PK(version_id, from_ratio)

grading_scheme_table_rows  -- for 'lookup_table' (official CEATM raw→scaled tables, when we have them)
  version_id FK, raw_points INT, scaled NUMERIC, PK(version_id, raw_points)

grading_scheme_thresholds  -- named markers, e.g. golden certificate ≥ 219
  version_id FK, code TEXT, min_scaled NUMERIC, PK(version_id, code)
```

**How ORT fits.** The main test becomes a `piecewise_curve` version with:
- `scale_min=60`, `scale_max=245`, mean 150 and SD 30;
- segment 1: ratio [0, 0.5], output [60, 150], exponent 1.05;
- segment 2: ratio [0.5, 1], output [150, 245], exponent 0.95;
- a threshold `golden_certificate` at 219.

The subject test is the same shape with 60/105/150 and SD 20. Two edge cases must be reproduced exactly so that `test_scoring` passes: raw 0 gives 0 and a perfect score gives the maximum. One option is to add a `zero_raw_result` column; the better option is to decide to fix raw 0 to 60 and update the test deliberately. Section breakdowns use the same version applied to each section.

**Applying a scheme.** An assessment carries `grading_scheme_version_id` and `points_possible`. A course carries a default version and an optional `course_grading_scheme_version_id` for the course total.

**One pure function** does the conversion: `apply(version, raw_points, points_possible) -> (display_value NUMERIC, label TEXT NULL, percentile NUMERIC NULL, passed BOOL NULL, thresholds[])`. It is implemented per type in a registry (`dict[type, Strategy]`) and is unit-tested.

### 3.5 Submissions and stored results

```
submissions   -- one per (enrollment, assessment); UNIQUE(enrollment_id, assessment_id)
  id, enrollment_id FK, assessment_id FK, state CHECK IN ('unsubmitted','in_progress','submitted','graded','excused'),
  kept_attempt_id FK attempts NULL, kept_policy_snapshot TEXT ('highest','latest','average'),
  raw_points NUMERIC NULL, points_possible NUMERIC NULL, late_deduction NUMERIC DEFAULT 0,
  override_points NUMERIC NULL,           -- teacher manual grade
  scheme_version_id FK,                   -- which version produced the cache
  display_value NUMERIC NULL, label TEXT NULL, percentile NUMERIC NULL,
  released_at NULL,                        -- Canvas posted_at: hidden results never gate or show
  updated_at, version INT
attempts      -- today's TestAttempt, with an FK to assessment, answers in a child table
grade_events  -- append-only audit: submission_id, actor_id, field, old, new, reason, at
```

The number is canonical: `effective_points = coalesce(override_points, raw_points) - late_deduction`. `display_value` and `label` are caches that `apply()` can recompute at any time.

**Recompute** runs on any of these: an attempt submitted, a teacher override, a scheme version swap on the assessment, a change to `points_possible`, or a change to the kept policy. In each case it recomputes the affected submissions, writes `grade_events`, then re-evaluates the gating for those enrollments.

Editing a scheme **creates a new version**. Old results keep their version until the teacher explicitly re-grades.

**Course total.** Use optional `grade_categories` (course_id, title, weight NUMERIC, position, deleted_at) with `assessments.category_id`. The formula is Canvas's weighted formula (rescale when the weights sum to less than 100) or plain points. Cache the result in `course_grades(enrollment_id PK, current_percent, final_percent, display_value, label, computed_at)`, computed synchronously when a grade changes.

---

## 4. What to skip and why

- **Sections, AssignmentOverride, observers, grading periods and their weights**: the owner decided "no sections", and we have no terms.
- **Polymorphic ContentTag shared with outcomes, and the asset↔tag publish/title mirroring**: typed FKs plus computed visibility do the job.
- **Separate Quiz and Assignment objects**: use one `assessments` table that has `graded BOOL` and `scoring_policy`. Practice assessments simply never feed the gradebook.
- **`must_contribute`/discussions, LTI/external tools, peer review, moderated or anonymous grading, rubrics, SpeedGrader, Turnitin, mastery paths/conditional release, completion events, and the what-if grade**: none is needed for ORT or for simple teacher courses. Rubrics can come later as a child table.
- **The drop-lowest bisection algorithm**: postpone. If needed later, use a simple "drop N lowest percentages" rule.
- **The per-course late policy**: add it later as columns on `assessments` (`due_at`, `late_deduction_percent_per_day`, `late_floor_percent`). The data model above already reserves `late_deduction`.
- **Delayed-job evaluation, sharding, batch invalidation via `current`**: our courses are small, so synchronous evaluation keyed on `rules_version` is simpler and exact.

---

## 5. Risks and open questions

1. **Relock semantics** (§3.3): should a regrade below the threshold relock a downstream module? This is the owner's call.
2. **ORT edge cases**: raw 0 currently scores 0 instead of 60, and the curve is not the official CEATM table. Should we keep the current behavior, or switch to `lookup_table` once real tables are available?
3. **Scheme versioning**: when a teacher edits a scheme in use, should old results be re-graded automatically or on request? (My recommendation: on request.)
4. **Timer and integrity**: gating on `min_score` turns the assessment result into an access key. The current gaps (a timer reported by the client, now-fixed resubmission) matter more once results unlock content.
5. **Multilingual items**: does a page or assessment per language count as one item (with language variants as child rows) or as separate items? This affects requirements: "viewed the ky version" vs "viewed any".
6. **Enrollment end**: Canvas freezes progressions of concluded enrollments. We need a rule for that, and for soft-deleted enrollments, before analytics.
7. **Reordering modules** can make an existing prerequisite point forward. Should we reject the reorder or drop the prerequisite with a warning? Canvas drops it silently on the next save.
