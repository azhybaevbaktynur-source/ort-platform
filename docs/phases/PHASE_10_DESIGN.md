# Phase 10: design (practice, student tools, new question types, statistics, analytics)

Scope: `IMPLEMENTATION_PLAN.md` "Phase 10". Rules: `AGENTS.md` §6, UR-1…8. UX check per UR-6 (orchestrator, 375 / 1440 / 1920 px, ru; no `ux-reviewer`). Style: `UX_REWORK_DESIGN.md` (short labels, no explanatory paragraphs, full main width; `AreaShell`, course sidebar).

## 0. Invariants

1. **ORT does not change.** `_expand_rows`, `grade_items`, `finalize`, autosave predicates and the ORT screens keep their behaviour. A non-practice attempt runs exactly today's code; snapshot gains a key only when `is_practice` is true, so ORT content hashes stay equal.
2. **Practice writes no grades.** No `submissions`, `attempt_grades` or grade events; no `assignments` row.
3. **One exclusion predicate.** Every staff aggregate over attempts uses `analytics.scope.counted_attempt` (previews, void, in-progress, test students out). A test student still sees their *own* notebook and progress (Student view must work).
4. **Students see only what the review page would show.** Notebook and progress read only assessments passing `results.assessment_results_visible`; keys only with `results.keys_allowed`.
5. **Org admins get aggregates only.** No question text, no keys, no per-student rows; subtree scope (`organizations.tree.subtree_scope`).
6. **No new index on `attempt_items`.** Autosave stays cheap. Aggregates reach items through `attempts` and the PK `(attempt_id, position)`.

## 1. Migration `0016_phase10_practice_analytics` (down_revision `0015_test_student`)

Additive; on PG `ADD COLUMN ... DEFAULT false` is instant.

| Table | Change |
|---|---|
| `assessments` | `is_practice BOOLEAN NOT NULL DEFAULT false`; CHECK `practice_preset_none`: `NOT is_practice OR preset = 'none'` |
| `attempts` | `is_practice BOOLEAN NOT NULL DEFAULT false` (copied from the snapshot at start, like `is_preview`) |
| `attempts` indexes | Partial, predicate `_FINAL`: PG `status IN ('graded','needs_review') AND NOT is_preview`, SQLite `... AND is_preview = 0`: `ix_attempts_version_final (assessment_version_id, user_id, attempt_no)`, `ix_attempts_user_course_final (user_id, course_id, submitted_at)`, `ix_attempts_course_final (course_id, assessment_id)` |
| `module_progress` | `ix_module_progress_module_id_state (module_id, state)` |
| `course_goals` (new) | `enrollment_id` PK FK `enrollments.id` RESTRICT; `target_percent SMALLINT NOT NULL` CHECK 1..100; `created_at`, `updated_at` (`TimestampMixin`) |
| `assessment_version_stats` (new) | `assessment_version_id` PK FK RESTRICT; `assessment_id` FK, `course_id` FK; `computed_at`, `refreshing_since` timestamptz NULL; `fingerprint VARCHAR(64)` NULL; `attempts_counted INT NOT NULL DEFAULT 0`; `mean_percent`, `median_percent`, `stddev_percent`, `min_percent`, `max_percent NUMERIC(6,2)` NULL; `distribution` JSON NULL (10 ints); index `ix_assessment_version_stats_assessment_id` |
| `assessment_item_stats` (new) | `id` UUID PK; `assessment_version_id` FK RESTRICT; `slot SMALLINT`; `question_version_id` FK RESTRICT; `n INT`; `points NUMERIC(8,2)`; `accuracy NUMERIC(6,2)` (percent of points); `point_biserial NUMERIC(5,3)` NULL; `avg_seconds INT` NULL; `correct`, `partial`, `incorrect`, `unanswered INT`; `distractors` JSON NULL (`{key: count}`); UNIQUE `uq_assessment_item_stats_slot (assessment_version_id, slot, question_version_id)`; index `ix_assessment_item_stats_hardest (assessment_version_id, accuracy, id)` |

Models: `assessments/models.py`, `attempts/models.py`, `modules/models.py`, new `progress/models.py` (`CourseGoal`), `statistics/models.py` (`AssessmentVersionStats`, `AssessmentItemStat`).

Shared helper `backend/app/lms/analytics/scope.py` (S0, exact):

```python
COUNTED_STATUSES = ("graded", "needs_review")

def final_attempt(a):            # matches the partial indexes: not_(col) renders NOT col on PG, col = 0 on SQLite
    return and_(a.c.status.in_(COUNTED_STATUSES), not_(a.c.is_preview))

def counted_attempt(a):
    return and_(final_attempt(a), not_test_enrollment(a.c.enrollment_id))

def real_student(e):
    return and_(e.c.role == "student", e.c.state == "active", e.c.is_test_student.is_(False))

def percent_bucket(points, possible):   # 0..9 by CASE; 100% goes in bucket 9. Portable (no FLOOR, no cast rounding)
    ...
```

Authz: `A.ANALYTICS_READ = "analytics.read"` in `core/authz.py`, for teacher and assistant roles, `READ_ONLY_ACTIONS` and `ORG_ADMIN_ACTIONS`; not students. Item statistics require `A.CONTENT_READ_ADMIN`, which org admins lack.

## 2. New question types

New file `backend/app/lms/content/types/structured.py`: `Matching`, `FillBlank`, `Ordering`; registered in `REGISTRY` after `Essay`. `STRUCTURED_TYPES = ("matching", "fill_blank", "ordering")`. Text only, no images (`image_refs` stays `[]`). `supports_passages = False`.

**Ids never leak.** Ids are server-derived from text: `sha256(prefix + ":" + text).hexdigest()[:8]` with prefix `l`, `r`, `o`. Each type overrides `validate()` to strip any client id, then derive. The student view lists rows sorted by id, so display order depends only on the text, never on author order or pairing. Loading stored data (`Data(**data)`) keeps the ids. No per-attempt shuffle, so `_expand_rows` stays as is.

| | `matching` | `fill_blank` | `ordering` |
|---|---|---|---|
| Authoring `data` | `{pairs: [{left, right}], distractors: [str]}` | `{text: "A {{1}} b {{2}}", blanks: [{answers: [str]}], case_sensitive: false}` | `{items: [{text}]}` in correct order |
| Stored adds | `left_id`, `right_id` per pair; `distractor_ids` | nothing | `id` per item |
| Limits | 2..20 pairs; lefts unique; two lefts may share a right; 0..10 distractors, not equal to a right | 1..10 blanks; `{{n}}` tokens exactly `1..n`, in order, once each; 1..10 answers per blank, non-empty after `normalize_short`; `text` `rich_text(2000)` | 3..20 items, unique text |
| `student_view` (`STUDENT_KEYS`) | `lefts: [{id, text}]`, `rights: [{id, text}]` (deduplicated) | `text`, `blank_count` | `items: [{id, text}]` |
| `key_view` | `pairs: [{left_id, right_id, left, right}]` | `blanks: [{answers}]` | `order: [ids]`, `items: [{id, text}]` |
| `Response` (`StrictModel`) | `{pairs: {left_id: right_id}}`, ≤20 keys, each ≤8 chars | `{blanks: {"1": "text"}}`, ≤10 keys `^\d{1,2}$`, values ≤200 | `{order: [ids]}`, ≤20, each ≤8 chars |
| Empty handling | validator drops empty values, so `is_blank` is true on `{pairs: {}}` | validator drops whitespace-only values | `order: []` is blank; untouched stays `null` (unanswered) |
| `score` | k correct lefts of n pairs | k correct blanks of n (`normalize_short`, any accepted answer) | k items in their correct position of n; a non-permutation scores 0 |
| `import_columns` | `match_pairs` (`left=>right\|left=>right`), `match_distractors` (`a\|b`) | `blank_text`, `blank_answers` (`a\|alt\|\|b`: `\|\|` between blanks), `case_sensitive` | `order_items` (`first\|second\|third`) |

`Response` checks shape only: unknown ids pass autosave (`_response_ok`) and `score` ignores them.

**Partial credit** (`content/types/base.py`, new):

```python
def proportional(k: int, n: int, max_points: Decimal) -> ScoreResult:
    if n > 0 and k == n: return ScoreResult(quantize2(max_points), max_points, True, False)
    if k <= 0 or n <= 0: return zero_result(max_points)
    pts = (max_points * k / n).quantize(_TWO_DP, rounding=ROUND_DOWN)   # never reaches max when k < n
    return ScoreResult(pts, max_points, False, False)
```

`grade_items`, `_correctness` (`correct` / `partial` / `incorrect`), `is_blank` and `recompute_attempt` work unchanged.

**ORT refuses the types, three layers:**
1. Section rules: `ORT_SECTION_RULES.allowed_types` is already a whitelist (`check_item_rules`); a test proves it for all three types on every ORT section key.
2. `CourseTemplate.refused_question_types: tuple[str, ...] = ()`; `ORT` sets `STRUCTURED_TYPES`. New `templates.service.assert_question_type_allowed(course, type)` (422 `type_not_allowed`) is called from `content/service.create_question`, `quiz_editor/commit._prepared`, row validation in `importers/general_csv.py` and `organizations/shared_banks` copy (422 when the source bank holds such a question).
3. UI: `QUESTION_TYPES` in `contentTypes.ts` stays the seven existing names, so ORT forms are byte-identical. New `ALL_QUESTION_TYPES`. `QuestionEditor` and `cardTypeOptions` use `ALL_QUESTION_TYPES` unless `course.template_key === "ort"`.

**Catalog and import**: `GET /exam-templates/blocks` reads `REGISTRY`, so the types appear by themselves; set `title_key = "bank.types.<name>.name"`. `lib/lms/blocks.ts` `QUESTION_TYPES` adds the three (contract tests `test_blocks_contract.py`, `test_constructor_blocks_contract.py`). `KNOWN_COLUMNS` and `format_for` derive from `import_columns`; implement `from_import_row` (raises `ImportRowError(column, msg)`). `quiz_editor/summary.correct_summary` adds three cases. `search_strings` returns all texts.

**Frontend**:
- `lib/lms/contentTypes.ts`: union, `ALL_QUESTION_TYPES`, data and student view types. `content/types/formModel.ts`: fields `matchPairs: {left, right}[]`, `matchDistractors: string[]`, `blankText: string`, `blankAnswers: string[]` (one `a|alt` string per blank), `orderItems: string[]`; update from-version, to-payload, validate and type-switch carry-over. Blank count follows the `{{n}}` tokens in `blankText`.
- New `components/lms/content/types/StructuredFields.tsx`: `MatchingFields`, `FillBlankFields`, `OrderingFields` (rows with add, remove, up, down; "Add blank" inserts the next token). Mounted in `QuestionCardForm.tsx`. `QuestionCard.isBlank` covers the new fields.
- New `components/lms/player/StructuredAnswers.tsx`: `MatchingAnswer` (each left with a `<select>` of rights), `FillBlankAnswer` (split `text` on `{{n}}`, inline inputs ≤200 chars), `OrderingAnswer` (rows with up and down buttons, min 44 px; no drag; first move or "Keep this order" sets the response). Works at 375 px and by keyboard.
- `ItemView.tsx`: three branches plus new optional prop `hideFlag`. No DOM change for existing types. `playerUtils.isAnswered`: three cases.
- `ReviewItemCard.tsx`, `VersionView.tsx`, `StudentPreview.tsx`: three cases each. i18n: `bank.types.{matching,fill_blank,ordering}.{name,hint}`, `bank.editor.structured.*`, `player.structured.*`, `results.structured.*`.

## 3. Practice mode

A practice set is an `Assessment` with `is_practice = true`, one section (`key = NULL`, `rules.allowed_types` = all types except `essay`), one `pick` item per block.

**Forced at creation; not editable through the builder** (409 `practice_fixed` on `AssessmentUpdateIn` for any of them): `allowed_attempts = -1`, `time_limit_s = NULL`, `results_policy = 'after_submit'`, `show_correct_answers = true`, `score_policy = 'latest'`, `shuffle_items = true`, `navigation = 'free'`, `display_mode = 'one_per_page'`, `result_view = 'general'`, no scheme, no category, no due date, no access code.

**Exclusion by construction**: `create_assessment(..., practice=True)` skips `assignment_sync.ensure_quiz_assignment`. With no `assignments` row, the gradebook, to-do lists, assignments page, "Не в модулях", module pickers and gating never see it (the gate finds no module item and passes). A practice set is reached from its own page; it is not a module item.

**Engine changes (S2, the whole list)**:
- `assessments/snapshot.py`: after `template_snapshot_keys`, `if assessment.is_practice: snapshot["is_practice"] = True`.
- `attempts/engine.start_attempt`: `is_practice = bool(snapshot.get("is_practice"))` in `attempt_row` and `view`; `AttemptStateOut.is_practice: bool = False`, set in `build_state` via `getattr`.
- `attempts/hooks.run_scored_hooks`: `if attempt.is_preview or attempt.is_practice: return`.
- `grading/actions.py:337` and `grading/submissions.on_attempt_scored`: same guard.
- `assessments/builder.list_staff`, `list_student`: `Assessment.is_practice.is_(False)`, so existing lists (ORT staff and student included) do not change.
- `home/service.py` in-progress queries: `Attempt.is_practice.is_(False)`.
- `student_view/allowlist.py` `TEST_STUDENT_ROUTES` (exact method and template): `POST` item check, `GET` practice-feedback, `GET _C/practice`, `GET _C/my/progress`, `GET _C/my/mistakes`, `PUT` and `DELETE _C/my/goal`.

**Item check**, new `attempts/practice.py`:

```python
def check_item(db, user, attempt_id, position, *, now) -> PracticeFeedbackOut:
    attempt, env = engine.load_attempt_bundle(db, user, attempt_id)      # 404 when not the owner
    if not attempt.is_practice: raise Conflict(code="not_practice")
    row = SELECT item WHERE attempt_id, position FOR UPDATE              # 404 item_not_found
    if row.correctness is not None: return feedback(row)                 # idempotent
    if attempt.status != "in_progress": raise engine.attempt_closed()
    plan = engine.plan_for(db, attempt)
    g = grading.grade_items(plan, attempt.language, [row]).items[0]      # the same scorer as finalize
    if g.correctness == "unanswered": raise ValidationFailed(code="empty_response")
    UPDATE attempt_items SET correctness, score      -- item graded_at stays NULL: it marks manual grading
      WHERE attempt_id, position, correctness IS NULL AND <attempt in_progress, same user>
    # 0 rows: re-read; correctness set -> feedback, else attempt_closed
    db.commit(); return feedback(row)
```

- It scores the **stored** response. The client calls `queue.flushNow()` first; a failed flush shows the save error and does not check. Setting `correctness` closes the autosave door for that item (P3-22), so the answer is locked.
- **Race with `finalize`**: finalize holds the attempt row, then `SELECT items FOR UPDATE`; check holds only the item row and reads the attempt without a lock, so there is no cycle. Finalize re-scores every row with the same pure scorer on the same response. Either order gives the same scores. Proven by a PG concurrency test.
- `finalize` needs no change. No deadline, so the sweep ignores practice attempts; an abandoned one resumes on the next start (`uq_attempts_open`).

Routes (`attempts/router.py`, `ATTEMPT_POLICIES` `attempt_owner`):
- `POST /attempts/{attempt_id}/items/{position}/check` → `PracticeFeedbackOut {position, correctness, score: str, points: str, key: dict, explanation: str|null}` (`key` through `content_repo.expand_images(key_view)`).
- `GET /attempts/{attempt_id}/practice-feedback` → `{items: [PracticeFeedbackOut]}`: all checked items, for reload. 409 `not_practice` on other attempts.

Practice API, new package `backend/app/lms/practice/` (`schemas.py`, `service.py`, `router.py`, `policies.py`; `_C = /courses/{course_id}`):

| Route | Policy | Shape |
|---|---|---|
| `GET _C/practice?cursor&limit=25` | `course:content.read` | `PageOut[PracticeSetOut]`: `{id, title, status, languages, item_count, blocks: [PracticeBlockOut], my_attempts, my_best_percent, my_last_at, open_attempt_id}`. Students: published only. Staff: all live, `my_*` null |
| `POST _C/practice` | `course:content.manage` | `PracticeCreateIn {title, languages, blocks: [PracticeBlockIn {bank_id, count, section?, topic?, difficulty?}] 1..5}` → 201 `PracticeSetOut`, published. 422 `pick_pool_too_small` (details per block and language) before any write |
| `PATCH _C/practice/{aid}` | `course:content.manage` | `{title?, blocks?}`, replaces blocks and republishes. Empty body = refresh the pool from the bank |
| `DELETE _C/practice/{aid}` | `course:content.manage` | soft delete through the builder's delete; 404 when not practice |
| `GET _C/practice/facets?bank_id=` | `course:content.manage` | `{sections: [..], topics: [..], difficulties: [..]}`: `SELECT DISTINCT ... LIMIT 200` per field, for the dialog |

Starting uses the existing `POST _C/assessments/{aid}/attempts`; results and review use the existing routes. `my_*` come from one grouped query over `ix_attempts_user_course_final` for the page's assessment ids.

**ORT practice**: same endpoints in an ORT course (`preset = 'none'` is allowed, `assert_preset_allowed` passes). Pools come from `pick_pool` on the course's own ORT banks by `section` / `topic` / `difficulty`. The exam is untouched: other preset, other snapshot, no change to `locked_rules`. Passages come through the snapshot's `pv`. No new ORT content is seeded; a teacher creates the sets.

**UI** (S3): sidebar "Практика". `app/[lang]/courses/[courseId]/practice/page.tsx`:
- Student: rows with title, N questions, best %, attempts, button "Начать" or "Продолжить".
- Staff: same rows plus "…" (Rename, Refresh questions, Delete) and primary "Новый набор", opening `PracticeDialog.tsx` (title, 1..5 blocks of bank, section, topic, difficulty, count). Empty state: one line.
- Player: in `PlayerShell.tsx`, under `ItemView`, only when `state.is_practice`, `<PracticeCheck>` ("Проверить" → correct / partial / wrong, key, explanation). `ItemView` gets `disabled` and `hideFlag` only on practice attempts. Feedback loads once from `practice-feedback` on mount. Non-practice attempts render the same DOM.

## 4. Mistakes notebook, progress, goal

New package `backend/app/lms/progress/` (`models.py`, `schemas.py`, `service.py`, `router.py`, `policies.py`). Enrolled students only (404 otherwise; staff have no attempts here).

| Route | Policy | Shape |
|---|---|---|
| `GET _C/my/progress` | `course:attempt.read_own` | `ProgressOut {goal_percent, current_percent, attempts_total, assessments_done, open_mistakes, trend: [{attempt_id, at, title, percent, practice}] (last 20, oldest first), by_section: [{section, correct, total, accuracy}], by_topic: [{topic, section, correct, total, accuracy}] (30 worst)}` |
| `GET _C/my/mistakes?status=open\|fixed&cursor&limit=25` | `course:attempt.read_own` | `PageOut[MistakeOut {attempt_id, submitted_at, assessment_title, topic, section, item: ReviewItemOut\|ReviewItemKeyedOut}]` |
| `PUT _C/my/goal` | `course:attempt.read_own` | `{percent: 1..100}` → `{goal_percent}` |
| `DELETE _C/my/goal` | `course:attempt.read_own` | 204 |

Every read starts with **visible assessments**: distinct `assessment_id` of the student's final attempts in this course, keep those passing `results.assessment_results_visible`. All later SQL has `assessment_id IN (:visible)`.

Mistakes query (window functions run on PG and SQLite):

```sql
WITH r AS (
  SELECT i.attempt_id, i.position, i.correctness, a.submitted_at, qv.question_id,
    ROW_NUMBER() OVER (PARTITION BY qv.question_id ORDER BY a.submitted_at DESC, i.attempt_id, i.position) AS rn,
    MAX(CASE WHEN i.correctness IN ('incorrect','partial') THEN 1 ELSE 0 END)
      OVER (PARTITION BY qv.question_id) AS ever_wrong
  FROM attempts a JOIN attempt_items i ON i.attempt_id = a.id
  JOIN question_versions qv ON qv.id = i.question_version_id
  WHERE a.user_id = :u AND a.course_id = :c AND <final_attempt(a)> AND a.assessment_id IN (:visible))
SELECT * FROM r WHERE rn = 1 AND <open: correctness IN ('incorrect','partial') | fixed: correctness = 'correct' AND ever_wrong = 1>
ORDER BY submitted_at DESC, attempt_id DESC, position   -- keyset cursor on these three
```

- "Open": the student's latest answer to that bank question was wrong. Answering it right later moves it to "fixed". `unanswered` and `pending` are not mistakes.
- Rows render through `serializers.review_item(..., with_keys=results.keys_allowed(assessment))`; `pv` via `results._pv_for`; points from the plan.
- Accuracy: `(correct + 0.5 * partial) / total`; `total` counts `unanswered`, not `pending`. Grouped on `bank_questions.section`, `topic`.
- `current_percent`: average over assessments of the best `raw_score / points_possible` (practice counts; scaled ORT scores unused). Goal: `course_goals` upsert by the caller's active enrollment.

**UI** (S4): sidebar "Прогресс", `app/[lang]/courses/[courseId]/progress/page.tsx`, tabs "Обзор" and "Ошибки" (`?tab=mistakes`). Overview: tiles (current %, goal, attempts, open mistakes), goal inline input, trend as small CSS bars, worst topics table. Mistakes: filter open or fixed, cards through `ReviewItemCard`, link to the attempt review, `Pager`. Files: `components/lms/progress/{ProgressOverview,GoalInput,MistakesList}.tsx`, `lib/lms/progress.ts`.

## 5. Quiz statistics

New package `backend/app/lms/statistics/` (`models.py`, `math.py` pure, `compute.py`, `service.py`, `schemas.py`, `router.py`, `policies.py`).

**Unit is one published `assessment_version`** (a stable form). Default: the published version; a selector lists versions with attempts. **Sample: first counted attempt per student on that version**, standard for item analysis and not skewed by practice retakes.

**Cached, computed on request.** Attempt items are the largest table; one ORT exam is 6,000 × 150 = 900,000 rows.

```
fingerprint = sha256(f"{count}:{max(updated_at)}") over counted attempts of the version   -- catches regrades and manual scores
no row, or fingerprint differs and age >= ttl    -> try compute
fingerprint differs and age < ttl                -> serve cached, state "stale"
same fingerprint                                 -> serve cached, state "fresh"
ttl = 0 when attempts_counted < 500, else 600 s
```

**Single flight**: `INSERT ... ON CONFLICT DO NOTHING`, then `UPDATE ... SET refreshing_since = now WHERE pk AND (refreshing_since IS NULL OR refreshing_since < now - 5 min)`; rowcount 0 → someone else is computing. Plus a per-process `BoundedSemaphore(2)` (non-blocking), so many teachers opening after a large exam cannot take the pool. Losers get the cached row with `state: "computing"`; the UI refetches after 5 s, at most 3 times. On PG `SET LOCAL statement_timeout = '20s'`; on timeout clear `refreshing_since` and serve cached. The compute transaction replaces `assessment_item_stats` for the version (DELETE + bulk INSERT) and updates the stats row together.

Compute SQL (`compute.py`). CTE, always the same:

```sql
first AS (SELECT id, raw_score, points_possible FROM (
  SELECT a.id, a.raw_score, a.points_possible,
    ROW_NUMBER() OVER (PARTITION BY a.user_id ORDER BY a.attempt_no) rn
  FROM attempts a WHERE a.assessment_version_id = :v AND <counted_attempt(a)>) WHERE rn = 1)
```

1. Scores: `SELECT raw_score, points_possible, COUNT(*) FROM first GROUP BY 1, 2`. Python (`math.score_summary`) gives mean, median, stddev, min, max and 10 buckets. Portable, exact, and bounded by the number of distinct scores.
2. Items, with `x = COALESCE(i.manual_score, i.score, 0)`, `y = f.raw_score - x` (the rest score):
   `SELECT i.slot, i.question_version_id, COUNT(*), SUM(x), SUM(x*x), SUM(y), SUM(y*y), SUM(x*y), <count per correctness> FROM first f JOIN attempt_items i ON i.attempt_id = f.id WHERE i.correctness <> 'pending' GROUP BY 1, 2`.
   `math.point_biserial(n, sx, sxx, sy, syy, sxy)` is Pearson over the sums; `None` when `n < 10` or the variance is 0. `accuracy = 100 * sx / (n * points)`; `points` by slot from `cache_api().get_plan` (`plan.slots`, first language holding the slot).
3. Time: `seconds_between(i.answered_at, COALESCE(LAG(i.answered_at) OVER (PARTITION BY i.attempt_id ORDER BY i.answered_at), a.started_at))`, dropped when ≤ 0 or > 1800 s, averaged per `(slot, qv)`. Helper `statistics/sql.py seconds_between`: PG `EXTRACT(EPOCH FROM a - b)`, SQLite `(julianday(a) - julianday(b)) * 86400`. **Approximate by design**: the time between saved answers, with no player or autosave change. The UI shows "≈".
4. Distractors: `SELECT i.slot, i.question_version_id, i.response, COUNT(*) ... JOIN question_versions qv ... WHERE qv.type IN ('single_choice','multiple_answers','true_false','comparison') AND i.response IS NOT NULL GROUP BY 1, 2, 3` (JSONB and SQLite JSON text both group). `statistics/distractors.py` maps a response to keys by type (`choice_id`, each `choice_ids[]`, `value`, `choice`) and stores `{key: count}`. Other types: `NULL`.

API:

| Route | Policy | Shape |
|---|---|---|
| `GET _C/assessments/{aid}/statistics?version_id=` | `course:analytics.read` | `QuizStatsOut {assessment_id, version_id, version_no, versions: [{version_id, version_no, attempts}], state: fresh\|stale\|computing\|empty, computed_at, attempts_counted, mean_percent, median_percent, stddev_percent, min_percent, max_percent, distribution: [10 ints]}` |
| `GET _C/assessments/{aid}/statistics/items?version_id=&sort=hardest\|slot&cursor&limit=25` | `course:content.read_admin` | `PageOut[QuizItemStatOut {id, slot, question_version_id, type, stem_excerpt, section, topic, n, points, accuracy, point_biserial, avg_seconds, correct, partial, incorrect, unanswered, options: [{key, label, count, is_correct}]\|null}]` |

Reads never compute items; the items route returns an empty page until the first compute. A version not `published` kind or not of this assessment → 404. Text and `options` are joined for the **page only** (`question_versions` + `bank_questions`, one statement); `is_correct` from `key_view`. No whole-bank load: rows exist only for questions actually served.

**UI** (S5): `app/[lang]/courses/[courseId]/analytics/quizzes/[assessmentId]/page.tsx`. Tiles (attempts, mean, median, spread), `Histogram` (CSS bars with a table for screen readers, no chart library; new `components/lms/analytics/Histogram.tsx` owned by S5), version selector, item table sorted hardest first: stem excerpt, accuracy, discrimination (below 0.2 marked with a tooltip), ≈time. Row expands to options with counts and the correct one marked. At 375 px, rows become cards. Org admins see only tiles and histogram (their items request gets 403; hide the section by `read_only`).

## 6. Course and organization analytics

New package `backend/app/lms/analytics/` (`scope.py` from S0, `service.py`, `org_service.py`, `schemas.py`, `router.py`, `policies.py`). **Computed on request, no cache**: these touch `submissions`, `module_progress` and `attempts`, not `attempt_items`, with pages of ≤ 25 rows.

| Route | Policy | Shape |
|---|---|---|
| `GET _C/analytics/overview` | `course:analytics.read` | `CourseAnalyticsOut {students, modules_total, completed_all, score: {count, mean_percent, distribution}, submissions: {graded, pending_review, excused, missing}}` |
| `GET _C/analytics/modules?cursor&limit=25` | same | `PageOut[{module_id, title, position, locked, unlocked, started, completed, not_started}]` |
| `GET _C/analytics/assignments?cursor&limit=25` | same | `PageOut[{assignment_id, assessment_id, kind, title, due_at, students, submitted, graded, pending_review, excused, missing, late, mean_percent}]` |
| `GET _C/analytics/quizzes?practice=false&cursor&limit=25` | same | `PageOut[QuizRollupRow {assessment_id, title, preset, is_practice, attempts, students, mean_percent}]` |
| `GET /org/{oid}/analytics/overview` | `org_admin` | `OrgAnalyticsOut {courses, students, score: {...}, submissions: {...}}` (subtree) |
| `GET /org/{oid}/analytics/courses?department_id&cursor&limit=25` | `org_admin` | `PageOut[{course_id, title, department_name, students, completed_all, mean_percent, submitted, missing}]`; `department_id` outside the subtree → 404 |
| `GET /org/{oid}/analytics/quizzes?cursor&limit=25` | `org_admin` | `PageOut[QuizRollupRow + {course_id, course_title}]` |

Definitions:
- `students`: `enrollments` with `real_student(e)`.
- `score`: per student `SUM(effective_points) / SUM(points_possible)` over `submissions` with `state = 'graded'`, `points_possible > 0`, joined to `real_student`; outer query counts per `percent_bucket`. Staff see unreleased scores; org admins see only the aggregate.
- `module_progress` holds the state from each student's last evaluation (evaluated on their read; rule changes delete it). Counts group by `(module_id, state)` for published, live modules; `not_started = students - rows`. `completed_all`: enrollments with `completed` on all published modules (`GROUP BY enrollment_id HAVING COUNT(*) = :n`). Never run the evaluator per student here.
- Assignments: live published (`gradebook._live_published`), page first, then `submissions` grouped by `(assignment_id, state)` for the page ids via `ix_submissions_assignment_id_state_released_at`, joined to `real_student`. `submitted = graded + pending_review`. `late`: `late_seconds > 0`. `missing = max(0, students - submitted - excused)` when the due date has passed, else 0.
- Quiz roll-up: `attempts` grouped by `assessment_id` with `counted_attempt(a)` for the page ids, over all attempts. Reads no items. Practice rows excluded by default in the course route, always excluded in the org route.
- Org scope: courses through `tree.subtree_scope(org.path)` and `regular_courses()`, page first, then grouped queries with `course_id IN (:page)`. Sandbox, deleted and other orgs' courses never appear. An admin of a child department sees only that subtree.

**UI** (S6): sidebar "Аналитика" for staff and org admins (read-only observer). `analytics/page.tsx`, tabs "Обзор" and "Тесты": tiles, `Histogram`, modules table, assignments table, quizzes table with links to the statistics page. `app/[lang]/org/[orgId]/analytics/page.tsx`, nav "Аналитика" in `OrgShell`: tiles, histogram, courses table with department filter, quizzes table. Phone: tables become cards. ORT exams appear only inside these new pages; no ORT screen gets a link.

## 7. Scale and budgets

| Path | Statements (max, independent of N) | Target p95 on PG at 6,000 students | Mode |
|---|---|---|---|
| Item check | 5 | 40 ms | write, one row |
| Practice list | 3 | 50 ms | on request |
| Notebook page | 4, + 1 per distinct version on a cold plan cache (≤ 25) | 100 ms | on request, one student |
| Progress | 6 | 100 ms | on request, one student |
| Statistics read | 4 | 50 ms | cached |
| Statistics compute | 8 (+ bulk insert chunks) | ≤ 3 s at 900,000 items, hard stop 20 s | single flight, TTL |
| Statistics items page | 2 | 50 ms | cached |
| Course analytics, each route | 4 | 200 ms | on request |
| Org analytics, each route | 5 | 500 ms | on request |

Tests use the pattern of `test_grading_budgets.py` (statement count at 2 and 20 attempts must match). Row-count targets are verified with `EXPLAIN` in a PG-only test (`ix_attempts_version_final`, `ix_attempts_user_course_final`) and in Phase 11's load test.
**Growth**: unlimited practice adds ~20 `attempt_items` per attempt. 6,000 students at one set a day is about 44 M rows a year. Starts are already limited by `ratelimit.attempt_start_limit`. Phase 11 reviews retention; no action now (see Q5).

## 8. Slices

Order: **S0 first**. Then S1, S2, S4, S5, S6 in parallel. S3 after S2. All on branches from `lms`. Each slice runs the backend suite on a scratch DB (`AGENTS.md` §5), plus `tsc` and `check_i18n_parity.py` when it touches the frontend. i18n: S0 creates empty top-level sections `practice`, `progress`, `quizStats`, `analytics`; each slice adds keys only inside its own, in en, ky and ru. Delete nothing shared. Never touch a file outside your list; if you must, stop and report.

### S0 Foundation: **Sonnet**. Small; runs alone first.
Files: `alembic/versions/0016_phase10_practice_analytics.py`; column and index additions in `assessments/models.py`, `attempts/models.py`, `modules/models.py`; new `progress/models.py`, `statistics/models.py`, `analytics/scope.py`; model registration wherever `modules.models` is imported (`grep`); `core/authz.py` (`ANALYTICS_READ`); empty routers and policy dicts for `practice`, `progress`, `statistics`, `analytics` in `api/v1/router.py` and `core/route_inventory.py`; `courses/schemas.py` `CourseFeaturesOut.practice`, `courses/service.course_features` (one more EXISTS: live, published `is_practice`).
Frontend: `lib/lms/nav.ts`, `nav.check.ts`, `lib/lms/types.ts`, `CourseSidebar.tsx` icons, `OrgShell.tsx`; i18n sections and nav labels. Nav: `practice` (staff always, students when `f.practice`), `progress` (students), `analytics` (staff and observer).
Tests: `alembic upgrade head && alembic check` on PG; `tests/lms/test_analytics_scope.py` (`counted_attempt` drops preview, void, in-progress, test student, including a retired one); authz matrix for `analytics.read`; `nav.check.ts`.

### S1 Question types, full stack: **Sonnet**. Pure scorer classes; no engine change.
Backend: `content/types/structured.py` (new), `types/__init__.py`, `types/base.py` (`proportional`), `templates/base.py`, `templates/ort.py`, `templates/service.py`, `content/service.py`, `content/importers/general_csv.py` (guard only), `quiz_editor/commit.py`, `quiz_editor/summary.py`, `organizations/shared_banks.py` (guard only).
Frontend: `lib/lms/contentTypes.ts`, `lib/lms/blocks.ts`, `content/types/formModel.ts`, `content/types/StructuredFields.tsx` (new), `content/QuestionCardForm.tsx`, `content/QuestionEditor.tsx`, `content/VersionView.tsx`, `content/StudentPreview.tsx`, `quiz/QuestionCard.tsx`, `player/ItemView.tsx`, `player/playerUtils.ts`, `player/StructuredAnswers.tsx` (new), `results/ReviewItemCard.tsx`.
Tests, `tests/lms/test_structured_types.py`:
- validate: limits, duplicates, tokens; client ids are ignored.
- **No leak**: `student_view` has only the allow-listed keys; output identical when pairs or items are given in another order; no `answers`, no mapping.
- scoring table: full, partial, zero; `proportional(19, 20, 0.01)` is below max; a non-permutation scores 0; empty responses give `unanswered`.
- autosave accepts and rejects shapes.
- quiz flow through publish, start, autosave, submit, review for all three types, partial credit in totals.
- import: valid rows and one error per column; catalog lists the types; every ORT section key refuses them (`type_not_allowed`); ORT course bank, quiz commit, import and shared copy refuse; a general course accepts.
Frontend: quiz editor type dropdown and player by hand at 375 px. ORT Playwright specs unchanged.

### S2 Practice backend: **Opus**. Changes the attempt engine, hook path and item-level grading inside an open attempt; a mistake breaks exams or grades.
Files: everything under "Engine changes" in §3; `attempts/practice.py` (new), `attempts/router.py`, `attempts/schemas.py`, `attempts/policies.py`, `assessments/builder.py` (`practice` flag, `practice_fixed` guard), `assessments/snapshot.py`, `practice/*` (new), `home/service.py`, `student_view/allowlist.py`.
Tests, `tests/lms/test_practice.py`:
- create on general and ORT courses; forced settings; `practice_fixed`.
- unlimited attempts, new draw each attempt, no `assignments` row.
- after submit: zero rows in `submissions`, `attempt_grades`, grade events; absent from gradebook, to-do and `list_staff` / `list_student`.
- check: owner only, idempotent, locks autosave, `empty_response`, `not_practice`, 409 after close; `practice-feedback` after reload; final score equals the sum of checked scores.
- preview and test-student flows work; essays refused at publish; ORT exam snapshot hash, golden and parity tests unchanged.
- `tests/lms/test_pg_concurrency.py`: check racing submit, final state consistent, no deadlock.

### S3 Practice UI: **Sonnet**. After S2. API as in §3.
Files: `app/[lang]/courses/[courseId]/practice/page.tsx`, `components/lms/practice/{PracticeList,PracticeDialog,PracticeCheck}.tsx`, `lib/lms/practice.ts`, `lib/lms/attemptTypes.ts`, `player/PlayerShell.tsx` (mount only, behind `state.is_practice`), i18n `practice.*`.
Tests: `tsc`, parity; one Playwright spec `frontend/e2e/practice.spec.ts` (create, start, check, wrong answer shows key, finish, retake). All ORT specs and screenshots pass with no baseline change.

### S4 Notebook, progress, goal, full stack: **Sonnet**.
Files: `progress/{schemas,service,router,policies}.py`, the pages and components in §4, i18n `progress.*`.
Tests, `tests/lms/test_progress.py`:
- notebook equals a hand-computed fixture of attempts; fixed moves; versions of one question group together.
- `results_policy='never'` and closed `after_close` assessments are hidden; keys hidden when `show_correct_answers` is false.
- other students' rows never appear; goal CRUD and validation; test student works; statement budget constant at 2 vs 20 attempts; keyset pages without gaps.

### S5 Quiz statistics, full stack: **Sonnet**.
Files: `statistics/{math,sql,compute,distractors,service,schemas,router,policies}.py`, the page and components in §5 (`components/lms/analytics/{Histogram,QuizStatsView,ItemStatsTable}.tsx`), `lib/lms/statistics.ts`, i18n `quizStats.*`.
Tests, `tests/lms/test_quiz_statistics.py`:
- `math` against hand values (point-biserial on a small table, `None` when `n < 10` or no variance; median; buckets, 100% in the last).
- fixtures: first attempt only; preview, void, in-progress, test student excluded; manual score changes the fingerprint; pending items skipped.
- states fresh, stale, computing; a second caller does not compute; a stale `refreshing_since` is taken over.
- policy matrix: student 403 or 404; other teacher 404; org admin of the course reads the summary but gets 403 on items; other org 404.
- pagination; statement budget of compute constant at 2 vs 20 attempts; PG `EXPLAIN` uses `ix_attempts_version_final`.

### S6 Course and org analytics, full stack: **Sonnet**. Imports `Histogram` from S5; if S5 has not landed, S6 merges second and adjusts the import.
Files: `analytics/{service,org_service,schemas,router,policies}.py`, `courses/[courseId]/analytics/page.tsx`, `org/[orgId]/analytics/page.tsx`, `components/lms/analytics/{CourseAnalytics,OrgAnalytics}.tsx`, `lib/lms/analytics.ts`, i18n `analytics.*`.
Tests, `tests/lms/test_analytics.py` and additions to `test_org_isolation.py`:
- counts against fixtures for each definition in §6; test students and previews excluded; practice absent. Org admin sees own subtree only: sibling org and other tree 404, department filter outside 404, child admin cannot read the parent.
- statement budget constant at 2 vs 20 courses and students; pagination.

### Integration (orchestrator)
Full PG suite; `alembic check`; `frontend/e2e` ORT specs with no baseline change; UR-6 screen check; Neon backup branch before merging to `main`. **Exit**: a teacher sees a correct distribution and hardest-question list; an org admin sees roll-ups for their courses only; a student's notebook matches their attempts; ORT parity holds.

## 9. Owner questions (nothing blocks; safe defaults are built)

| # | Question | Default |
|---|---|---|
| Q1 | Ordering partial credit: exact positions or neighbours? | Exact positions: what the student sees matches the points. One item moved far scores low. |
| Q2 | Shuffle matching and ordering per student? | Same fixed, answer-independent order for everyone; needs no engine change. |
| Q3 | Practice sets inside modules? | No: own page, so grades and gating stay clean. A module link item can point to it. |
| Q4 | Goal unit for ORT: percent or scaled score? | Percent of raw points everywhere. |
| Q5 | Retention of old practice attempts? | Keep all; Phase 11 reviews growth, and any Neon cost goes to the owner first. |
| Q6 | Students build their own practice by topic? Statistics across quiz versions? | No: teachers build sets, as in the plan. Per version with a selector; republishing starts a new series. |
