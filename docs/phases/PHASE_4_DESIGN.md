# Phase 4 design: grading and results

**Status**: design for implementation, 2026-10-22 (architect). Builds on `phase-3/assessments` (Phases 0–3: `app/core/authz.py`, `app/lms/{core,courses,enrollments,content,files,assessments,attempts}/*`, Alembic `0004_phase3_assessments`).
**Sources**: `IMPLEMENTATION_PLAN.md` Phase 4 + §0 gates + D6/D11/D14; `LMS_ARCHITECTURE.md` §6; `PRODUCT_DECISIONS.md` ("grading flexible per course/test; ORT scaling is one scheme among others"); `PHASE_3_DESIGN.md` §1–§3 (P3-21/22/25 hook, lock order §3.8, results policy P3-24); oracle `app/services/scoring_service.py` + `tests/test_scoring.py`.
**Rule for implementers**: anything not stated here is out of scope. If a brief and this doc disagree, ask the orchestrator. Old code (`app/services/*`, `app/models/*`, old endpoints/pages) stays **frozen**: `ScoringService` is imported read-only by tests as the parity oracle and deleted in Phase 5.

---

## 0. The parity oracle (exact math to reproduce as data)

`ScoringService.raw_to_scaled(raw, possible, exam_type)` (old code, binding until Phase 5):
1. `possible <= 0 or raw <= 0 → 0` (D6 quirk: below the stated minimum 60; preserved exactly).
2. `raw >= possible → scale_max` (245 main, 150 subject).
3. `ratio = raw / possible` (float64). `ratio < 0.5`: `min + (mean − min) · (ratio/0.5)^1.05`; else `mean + (max − mean) · ((ratio − 0.5)/0.5)^0.95`. Main: 60/150/245; subject: 60/105/150.
4. `int(round(scaled))` (Python built-in `round` on the float: half-to-even).

`calculate_percentile(scaled, exam_type)`: `scaled <= 0 → 0.0`; `scaled <= min → 1.0`; `scaled >= max → 99.9`; else `round(clamp(Φ((scaled − mean)/sd) · 100, 1.0, 99.9), 1)` with `Φ` via `math.erf`; sd 30 (main) / 20 (subject). Golden certificate: `exam_type != subject and scaled >= 219` (`settings.GOLDEN_CERTIFICATE_MIN_SCORE`). Per-section scaled scores use the same curve with the section's own `(raw, possible)`; `calculate_score` returns `{scaled 0, percentile 0.0}` for raw 0.

Facts that shape the design: the curve depends on the **ratio**, so one `piecewise_curve` reproduces the oracle for any `possible` (teachers edit ORT section sizes); `lookup_table` (future official CEATM tables, keyed by raw points for a fixed N) is a second type with no code change later; the D6 quirk and the percentile clamps must be **data** on the version, not code paths named "ORT".

## 1. Decisions (defaults taken; record them in `PRODUCT_DECISIONS.md` at merge)

| # | Decision | Reason |
|---|---|---|
| P4-1 | One package `app/lms/grading/` (schemes, registry, submissions, gradebook, totals). Hook registration in `app/lms/grading/__init__.py` → `attempts.hooks.ATTEMPT_SCORED_HOOKS.append(on_attempt_scored)`, imported from `app/main.py` at startup and from `tests/lms/conftest.py`. | One owner per concern; Phase 3's extension point used as designed. |
| P4-2 | Per-type data lives in **one** immutable `grading_scheme_versions.params` JSON column validated by a per-type Pydantic model (not four child tables as sketched in the architecture). | Params are only ever read as a unit with the version (cached), immutability is one listener, no joins; the sketch's child tables add 4 tables for no query. |
| P4-3 | Types and `apply()` are pure (`registry.py`): `points`, `percent`, `bands`, `pass_fail`, `piecewise_curve`, `lookup_table`. Common optional blocks on every type: `rounding{mode, decimals}`, `percentile{mean, sd, min, max, decimals}`, `thresholds[{key, min_value}]`, `zero_raw{value, percentile}`, `apply_to_sections`. | Plan; ORT quirks become data (§3.1). |
| P4-4 | Scheme ownership: `owner_user_id NULL` = **system** (seeded, immutable, not editable through the API); otherwise a teacher's personal library. A version is **usable in course C** iff its scheme is live and (system, or owned by the actor, or owned by an active teacher/assistant of C). Every miss is 404 `scheme_version_not_found`. | Teachers own their stuff; reuse across their courses; no cross-tenant visibility, no oracle. |
| P4-5 | Editing a scheme = `POST …/versions` with full `params` → `version_no + 1` (immutable rows, ORM listeners raise like `AssessmentVersion`). Title is the only mutable scheme field. Soft delete hides from pickers; existing references keep working. | D14; same pattern as assessment versions. |
| P4-6 | System schemes seeded idempotently at startup and in the test fixture (`seeds.ensure_system_schemes(db)`, fixed UUIDs): `ort_main` v1 and `ort_subject` v1 as `piecewise_curve` reproducing §0 exactly (`zero_raw = {value: 0, percentile: 0.0}`), plus `percent` v1, `pass_fail` v1 (60 %). Presets `ort_main`/`ort_subject` set the assessment's scheme to the matching system version at creation. | Parity gate; "a teacher can create a pass/fail course and a percent course without code changes". |
| P4-7 | `attempt_grades` (one row per graded non-preview attempt) stores the scaled result of **that** attempt; `submissions` (one per enrollment + assessment) stores the **kept** result. Preview attempts get no rows; their result is computed inline for the staff owner. | Students need the grade of each attempt on its result page; old results stay untouched until regrade (D14); previews excluded everywhere. |
| P4-8 | Kept policy = `assessments.score_policy` (`highest` default, D11). Counted attempts: non-preview, status ∈ `graded, needs_review`. `highest` = max `raw/possible`, tie → latest; `latest`/`first` by `attempt_no`; `average` = mean of `raw/possible` × `points_possible` of the latest counted attempt, `kept_attempt_id` = latest. `needs_review` kept → submission `state = pending_review` (pending items count 0, as Phase 3). | Versions may differ in `points_possible` after a republish; ratios compare fairly. |
| P4-9 | `effective_points = max(0, coalesce(override_points, raw_points) − late_deduction)`; `display_value/label/percentile/passed/thresholds = apply(version, effective_points, points_possible)`; all stored on the submission (`computed_at`). No scheme → display fields NULL (points only). | Architecture §6. |
| P4-10 | Late policy: one optional course-level `courses.late_policy = {percent_per_day 0..100, max_percent 0..100, grace_minutes 0..1440}`; an assessment is late-able only with `due_at` set. `late_seconds = max(0, kept.submitted_at − due_at − grace)`; `late_deduction = round_half_up(coalesce(override, raw) × min(max_percent, percent_per_day × ceil(late_seconds/86400)) / 100, 2)`. | Plan ("single optional course-level policy"); explicit and testable. |
| P4-11 | Release: `assessments.grade_release ∈ auto \| manual` (live setting, default `auto`). `auto`: the hook sets `released_at = now` when it computes. `manual`: only `POST …/grades/release`. A student sees a grade iff `results_visible(assessment, attempt)` (P3-24) **and** `released_at IS NOT NULL`; otherwise `grade: null` with `grade_status ∈ pending \| hidden`. | One extra switch over the Phase 3 policy, not a second policy. |
| P4-12 | Recompute triggers (all run `recompute_submission` under the submission row lock): attempt scored (hook), manual item score (hook), attempt voided (new, Phase 4), override/excuse, regrade request. **Not** triggers (D14): changing the assessment's scheme version, `score_policy`, `due_at` or the course late policy; the gradebook shows `stale_count` and offers **Regrade**. Category/weight/omit changes need no regrade (totals are computed on read). | D14; teachers decide when old results change. |
| P4-13 | The hook runs **inside** the Phase 3 grading transaction (P3-25) with a fixed budget of **5 statements** (§3.4) and takes the submission lock **by upsert** before reading sibling attempts. No `course_grades` write in the hook. Submit budget rises from ≤ 8 to **≤ 13** statements; manual score from ≤ 6 to ≤ 11 (test 7.5 updated). | Atomic with the attempt (plan); the lock-then-read order is what makes concurrent manual scores and finalizes converge (§3.5). |
| P4-14 | **Lock order (binding, extends P3 §3.8)**: `courses → assessments → (assessment_sections, assessment_items) → assessment_versions`; `attempts → attempt_sections → attempt_items → submissions → attempt_grades → grade_events(insert) → course_grades`. Grade-side writers (override, excuse, release, regrade, totals) start at `submissions` and **never lock attempts, assessments or courses** (reads only, no `FOR UPDATE`). Multi-row lockers (regrade, release) lock in `submissions.id` order, ≤ 200 per transaction. | No cycle: finalize/manual-score/void hold an attempt then wait on a submission; nothing holds a submission and waits on an attempt. |
| P4-15 | Regrade is synchronous, chunked (200 submissions per transaction, each chunk commits), **resumable** (targets `scheme_version_id IS DISTINCT FROM assessment.grading_scheme_version_id OR computed_at < assessment.grading_changed_at`), capped at `GRADES_REGRADE_MAX=2000` per request (`pending` returned; UI calls again). Rate limit `grades_regrade_1h` 30/user/h (DB-backed). | No workers on Render; a crash mid-way leaves a consistent, re-runnable state. |
| P4-16 | `grade_events` is append-only and records **human and regrade actions only**: `override, override_cleared, excused, unexcused, released, unreleased, regraded, attempt_voided`. Automatic computations are reconstructible from `attempts.graded_at` + `submissions.computed_at/kept_attempt_id`; writing an event per submit would add 6,000 inserts to the burst. | Audit without hot-path cost. |
| P4-17 | Course totals: `courses.grading_total_mode ∈ points \| weighted`. Points: Σ effective / Σ possible over counted submissions. Weighted: `Σ_c w_c · p_c / Σ_c w_c` over categories **with ≥ 1 counted submission** (so weights summing to 70 or 130 both normalize; all-zero → `null`); `p_c` = points-weighted percent inside the category; assessments without a category are **excluded** from a weighted total (gradebook warning `uncategorized_excluded`). `current_percent` counts graded, non-excused, non-omitted submissions; `final_percent` additionally counts every published non-omitted assessment with `points_possible > 0` and no submission as 0; `released_percent` (student view) = current over released only. The course-level scheme (`courses.grading_scheme_version_id`, optional) maps the percent to `display_value/label/passed`. | Plan's "weights < 100 edge cases" and Canvas semantics. |
| P4-18 | `course_grades` is a cache **written whenever totals are computed** (gradebook page chunk, student "my grades", roster totals) and read by Phase 6/8 with `computed_at` exposed. Never written by the hook. | Bounded hot path; correct for every reader that needs exact totals (they compute). |
| P4-19 | Gradebook: student axis = the Phase 1 roster statement and cursor (active students, same ordering, `limit ≤ 50`); column axis = live published assessments (`limit 100`, filter `assessment_ids`); cells from **one** query `WHERE course_id AND enrollment_id IN (page)`; totals in the same pass. ≤ 6 statements per page, no N+1. | 500-student course = 10 pages, each < 50 ms server time. |
| P4-20 | Teacher void: `POST /courses/{c}/attempts/{t}/void {reason}` on `graded/needs_review` (in-progress → 409 `attempt_in_progress`): `status = void`, attempt_grades row deleted, submission recomputed (kept changes), event `attempt_voided`. Voided attempts stay readable by staff; the student's result page says "voided". | Phase 3 deferred it to Phase 4; the kept policy needs it. |
| P4-21 | Rate limits (DB-backed `ratelimit.Limit`s): override/excuse reuse `grade_item_1h` (600/user/h); `grades_release_1h` 60; `grades_regrade_1h` 30; `scheme_write_1h` 100; `scheme_preview_1m` 60. Body cap 64 KiB on `/api/v1/grading-schemes` and `/courses/*/grade*` (reuse `attempts/bodycap.py` prefixes). | Lessons: DB-backed limits, bounded bodies. |
| P4-22 | Caps (settings): bands ≤ 50, curve segments ≤ 20, table rows ≤ 1,000, thresholds ≤ 10, label ≤ 60 chars per language, preview ≤ 1,001 points, categories ≤ 30 per course, `GRADES_REGRADE_MAX` 2,000, release ≤ 5,000 ids per call. Numbers: `Numeric(10,2)` for points/display, `Numeric(4,1)` percentile, percent `Numeric(6,2)`. | Bounded memory; Phase 3 "numeric overflow" lesson: every stored number is quantized and range-checked before write (422 `value_out_of_range`). |
| P4-23 | Error shape `{"error":{code,message,details}}`; prefix `/api/v1/grading-schemes` added to `LMS_PATH_PREFIXES`. All new routes in the route inventory. Platform admins: no bypass. | Phase 1–3 gates. |

## 2. Schema and migration (`app/lms/grading/models.py`; `app/lms/models.py` imports it)

Conventions as Phase 3 (`UUIDPKMixin`, `TimestampMixin`, `SoftDeleteMixin`, `JSONType`, user FKs `String(64)`, partial indexes with both `postgresql_where` and `sqlite_where`).

### 2.1 `grading_schemes`
`id`, `owner_user_id` FK users RESTRICT **null** (NULL = system), `key String(32)` null (system only: `ort_main`, `ort_subject`, `percent`, `pass_fail`; `UNIQUE` partial `WHERE key IS NOT NULL`), `title JSONType` (LocalizedText) not null, `type String(16)` CHECK `IN ('points','percent','bands','pass_fail','piecewise_curve','lookup_table')`, `current_version_id` FK grading_scheme_versions (**use_alter**, `fk_grading_schemes_current_version_id`) null, `last_version_no Integer` default 0, timestamps, soft delete (`deleted_by_id`). Index `(owner_user_id, deleted_at)`.

### 2.2 `grading_scheme_versions` (immutable)
`id`, `scheme_id` FK RESTRICT, `version_no Integer` not null, `type String(16)` (copied; CHECK as above), `scale_min Numeric(10,2)` null, `scale_max Numeric(10,2)` null, `params JSONType` not null (§3.1 shapes; `schema: 1`), `params_hash String(64)`, `created_at`, `created_by_id` FK users SET NULL null. `UNIQUE(scheme_id, version_no)`; ORM `before_update`/`before_delete` raise `ImmutableGradingSchemeVersionError`.

### 2.3 Columns added to existing tables
`assessments`: `grading_scheme_version_id` FK grading_scheme_versions RESTRICT null; `grade_category_id` FK grade_categories SET NULL null; `due_at DateTime(tz)` null; `grade_release String(8)` CHECK `IN ('auto','manual')` default `auto`; `omit_from_total Boolean` default false; `grading_changed_at DateTime(tz)` null (set by PATCH when scheme/`score_policy`/`due_at` change; drives `stale_count`, P4-15).
`courses`: `grading_total_mode String(8)` CHECK `IN ('points','weighted')` default `points`; `grading_scheme_version_id` FK RESTRICT null; `late_policy JSONType` null; `grading_changed_at` null.

### 2.4 `submissions`
`id`, `course_id` FK RESTRICT, `assessment_id` FK RESTRICT, `enrollment_id` FK RESTRICT, `user_id` FK users RESTRICT (denormalized for the gradebook), `state String(16)` CHECK `IN ('pending_review','graded','excused')`, `kept_attempt_id` FK attempts RESTRICT null, `kept_policy String(8)` not null (policy used at compute), `attempts_counted Integer` default 0, `raw_points Numeric(10,2)` null, `points_possible Numeric(10,2)` null, `late_seconds Integer` default 0, `late_deduction Numeric(10,2)` default 0, `override_points Numeric(10,2)` null, `override_reason Text` null, `override_by_id` FK users SET NULL null, `override_at` null, `effective_points Numeric(10,2)` null, `scheme_version_id` FK RESTRICT null, `display_value Numeric(10,2)` null, `label String(40)` null (band key / `pass` / `fail`), `percentile Numeric(4,1)` null, `passed Boolean` null, `thresholds JSONType` null (`{"golden_certificate": true}`), `breakdown JSONType` null (`{sections:[{pos,key,raw,possible,display_value?}]}`), `released_at` null, `computed_at` not null, `version Integer` default 1 (optimistic token for override/excuse), timestamps.
`UNIQUE(enrollment_id, assessment_id)` (`uq_submissions_enrollment_assessment`); indexes `(assessment_id, state, released_at)`, `(course_id, enrollment_id)`, `(kept_attempt_id)`. Never deleted (no API; FK RESTRICT).

### 2.5 `attempt_grades`
PK `attempt_id` FK attempts RESTRICT; `scheme_version_id` FK RESTRICT null; `display_value`, `label`, `percentile`, `passed`, `thresholds`, `sections JSONType` (`[{pos, display_value}]`), `computed_at`. Deleted only by void (P4-20) and never cascaded.

### 2.6 `grade_events` (append-only; ORM listeners raise on update/delete)
`id`, `submission_id` FK RESTRICT, `course_id`, `actor_id` FK users SET NULL null, `event String(24)` CHECK (P4-16 list), `attempt_id` null, `old JSONType` null, `new JSONType` null, `reason Text` null, `created_at`. Index `(submission_id, created_at)`.

### 2.7 `grade_categories`, `course_grades`
`grade_categories`: `id`, `course_id` FK RESTRICT, `title JSONType`, `weight Numeric(5,2)` CHECK `0..100`, `position Integer`, timestamps, soft delete. Index `(course_id, deleted_at, position)`.
`course_grades`: PK `enrollment_id` FK RESTRICT; `course_id`; `current_percent`, `final_percent`, `released_percent Numeric(6,2)` null; `display_value`, `label`, `passed` null; `warnings JSONType` (`["uncategorized_excluded"]`); `computed_at`. Index `(course_id)`.

### 2.8 Alembic `0005_phase4_grading` (down_revision `0004_phase3_assessments`)
Upgrade: `grading_schemes` (without `current_version_id` FK) → `grading_scheme_versions` → `batch_alter_table("grading_schemes")` add the use_alter FK → `grade_categories` → add columns to `courses` and `assessments` (batch mode for SQLite) → `submissions`, `attempt_grades`, `grade_events`, `course_grades`. Downgrade reverses (FK first). `alembic check` clean on PG. `tests/lms/conftest.py` cleanup (prepend, FK-safe): `grade_events, course_grades, attempt_grades, submissions`; `UPDATE assessments SET grading_scheme_version_id=NULL, grade_category_id=NULL`; `UPDATE courses SET grading_scheme_version_id=NULL`; `grade_categories`; `UPDATE grading_schemes SET current_version_id=NULL`; `grading_scheme_versions, grading_schemes`; then re-seed system schemes; reset the version cache.

## 3. Services (`db` + `AuthzContext`, own the transaction, raise `LMSError` before commit; Core statements on hot paths)

### 3.1 Registry (`app/lms/grading/registry.py`, `params.py`) — pure, no DB
```python
@dataclass(frozen=True)
class GradeValue:  display_value: Decimal|None; label: str|None; percentile: Decimal|None; passed: bool|None; thresholds: dict[str,bool]
@dataclass(frozen=True)
class SchemeVersionData: id; scheme_id; type: str; scale_min; scale_max; params: dict      # built once per version (LRU 256, immutable)
def validate_params(type: str, params: dict) -> dict        # Pydantic per type; 422 scheme_params_invalid with details.errors
def apply(v: SchemeVersionData, raw: Decimal, possible: Decimal) -> GradeValue
def apply_sections(v, sections: list[dict]) -> list[dict]   # when params.apply_to_sections: [{pos, display_value}] via apply() per section
def preview(type, params, possible, raws: list[Decimal]) -> list[GradeValue]
```
Evaluation order inside `apply()` (every type): (1) `zero_raw` block set and (`possible <= 0 or raw <= 0`) → `display_value = zero_raw.value`, `percentile = zero_raw.percentile`, `label = None`, `passed = False`, thresholds all false, **return**; (2) `possible <= 0` → all `None`; (3) `raw >= possible` → `base = scale_max` (curve/lookup) or 100 % (percent-like); (4) type rule → `base`; (5) rounding; (6) `percentile` block → `clamp(round(Φ((value − mean)/sd) · 100, decimals), min, max)` computed as the oracle (clamp **then** round, `math.erf`); (7) `thresholds`: `key → value >= min_value`; (8) `pass_threshold_percent` → `passed`.
Type rules (`percent = raw / possible · 100`):
- `points`: `display_value = raw` (rounded); `label None`; optional `pass_threshold_percent`.
- `percent`: `display_value = percent`; optional `pass_threshold_percent`.
- `bands`: `bands: [{key ≤32, min_percent, label: LocalizedText, passed: bool}]` (keys unique, `min_percent` strictly descending validated, last must be 0); `display_value = percent`, `label = band.key`, `passed = band.passed`. The client renders the localized label from the version it fetched (`labels` map in `SchemeVersionOut`).
- `pass_fail`: `pass_threshold_percent` (required); `label ∈ pass|fail` (i18n `grading.labels.*`); `display_value = percent`.
- `piecewise_curve`: `scale_min, scale_max, segments: [{from_ratio, to_ratio, from_value, to_value, exponent}]` contiguous from 0 to 1 (validated); segment = first with `from_ratio ≤ ratio < to_ratio` (last inclusive); `sub = (ratio − from)/(to − from)`; `value = from_value + (to_value − from_value) · sub ** exponent`. **Float64 in exactly this expression order**; `ratio = float(raw) / float(possible)`.
- `lookup_table`: `rows: [{raw_from, raw_to, value, label?}]` sorted, non-overlapping, covering `0..expected_possible`; `expected_possible` optional (mismatch with the attempt's possible → value still looked up by raw, gradebook warning `points_possible_mismatch`); raw above the last row → last row.
Rounding `{mode: half_even|half_up|floor|ceil, decimals: 0..2}` (default `half_up`, 2). For `half_even` with float input the implementation calls Python `round(x, decimals)` (identical to the oracle); other modes go through `Decimal(repr(x)).quantize`. Output is always a quantized `Decimal`.
**Seeded ORT main v1** (`ort_subject` analog: 60/105/150, sd 20, no thresholds):
```json
{"schema": 1, "scale_min": 60, "scale_max": 245,
 "segments": [{"from_ratio": 0, "to_ratio": 0.5, "from_value": 60, "to_value": 150, "exponent": 1.05},
              {"from_ratio": 0.5, "to_ratio": 1, "from_value": 150, "to_value": 245, "exponent": 0.95}],
 "zero_raw": {"value": 0, "percentile": 0.0}, "rounding": {"mode": "half_even", "decimals": 0},
 "percentile": {"mean": 150, "sd": 30, "min": 1.0, "max": 99.9, "decimals": 1},
 "thresholds": [{"key": "golden_certificate", "min_value": 219}], "apply_to_sections": true}
```

### 3.2 Schemes (`schemes.py`, `repository.py`, `seeds.py`)
```python
def list_schemes(db, ctx, *, cursor, limit, include_system=True) -> Page[GradingScheme]   # system ∪ mine, live
def create_scheme(db, ctx, data: SchemeCreateIn) -> GradingScheme                      # teacher_approved; version 1
def load_scheme(db, ctx, scheme_id, *, for_update=False) -> GradingScheme              # system or mine, else 404 grading_scheme_not_found
def add_version(db, ctx, scheme_id, params) -> GradingSchemeVersion                    # owner only (system → 404); version_no+1; sets current_version_id
def update_title / soft_delete / restore(...)                                          # owner only
def load_usable_version(db, ctx, course, version_id) -> GradingSchemeVersion           # P4-4; 404 scheme_version_not_found
def get_version_data(db, version_id) -> SchemeVersionData                              # LRU 256; immutable rows → no invalidation
def ensure_system_schemes(db) -> None                                                   # idempotent by fixed UUIDs; startup + test fixture
```
Fixed ids: `ORT_MAIN_SCHEME_ID/ORT_MAIN_V1_ID`, `ORT_SUBJECT_*`, `PERCENT_*`, `PASS_FAIL_*` (`00000000-0000-4000-8000-0000000004NN`). `add_version` rejects identical `params_hash` with 409 `version_unchanged`.

### 3.3 Assessment/course grading settings (edits to Phase 3/1 files, owned by slice G1)
`AssessmentUpdateIn` gains `grading_scheme_version_id?, grade_category_id?, due_at?, grade_release?, omit_from_total?`; `builder.update_assessment` validates through `load_usable_version` and `load_category(db, course.id, id)` (404 `category_not_found`), sets `grading_changed_at` when scheme/`score_policy`/`due_at` change. `create_assessment` with an ORT preset sets the system version (P4-6). `AssessmentStaffOut` exposes the five fields plus `scheme{ id, scheme_id, title, type, version_no, scale_min, scale_max }|null`; the lobby/student summary exposes `scheme{type, scale_min, scale_max, title}|null` and `due_at` only.
`PUT /courses/{c}/grading` (`grading.py`): `{total_mode, grading_scheme_version_id?, late_policy?}` → validates (P4-10 ranges), sets `courses.grading_changed_at`. Categories: CRUD + reorder (exact-set check, 422 `order_mismatch`); delete only when no live assessment references it (409 `category_in_use`); weights are free (normalization P4-17).

### 3.4 The hook and `recompute_submission` (`submissions.py`) — the hard part
```python
def on_attempt_scored(db: Session, attempt: Attempt) -> None            # registered in ATTEMPT_SCORED_HOOKS; non-preview only (hooks.py already skips previews)
def lock_or_create_submission(db, *, course_id, assessment_id, enrollment_id, user_id) -> Row   # statement 2 below
def recompute_submission(db, sub_row, assessment_row, course_row, attempts: list[Row], *, now, actor_id=None, reason=None) -> Changes  # pure decision + 3 writes max
def kept_attempt(policy, attempts) -> tuple[Row|None, Decimal|None, Decimal|None, int]       # pure (P4-8), unit-tested
```
Hook statements (budget 5, counted by test 7.5):
1. `SELECT a.score_policy, a.grading_scheme_version_id, a.due_at, a.grade_release, c.late_policy FROM assessments a JOIN courses c … WHERE a.id = :aid`.
2. `INSERT INTO submissions (id, course_id, assessment_id, enrollment_id, user_id, state, kept_policy, computed_at, …) VALUES (…) ON CONFLICT (enrollment_id, assessment_id) DO UPDATE SET version = submissions.version RETURNING *` — this **takes the row lock** (PG waits here behind a concurrent override/regrade/finalize of a sibling attempt; SQLite serializes writers).
3. `SELECT id, attempt_no, status, raw_score, points_possible, submitted_at, assessment_version_id FROM attempts WHERE assessment_id AND enrollment_id AND NOT is_preview AND status IN ('graded','needs_review') ORDER BY attempt_no` — executed **after** the lock, so it sees every committed sibling plus this transaction's own attempt update (P3 step 5 ran before the hook).
4. `INSERT INTO attempt_grades … ON CONFLICT (attempt_id) DO UPDATE` for **this** attempt (its own `apply()` on `raw_score/points_possible` with the assessment's current version; `sections` from `attempt.result.sections` when `apply_to_sections`). Skipped when the assessment has no scheme.
5. `UPDATE submissions SET state, kept_attempt_id, kept_policy, attempts_counted, raw_points, points_possible, late_seconds, late_deduction, effective_points, scheme_version_id, display_value, label, percentile, passed, thresholds, breakdown, computed_at, released_at = CASE WHEN grade_release='auto' THEN coalesce(released_at, :now) ELSE released_at END, version = version + 1 WHERE id = :sid`.
Overrides survive recompute (`override_points` is never touched by the hook). `excused` submissions keep `state = excused` but still update the kept fields. A hook exception aborts the grading transaction (P3-21: answers safe, grading retried) — the hook must therefore never raise `LMSError`; invalid stored params are impossible (validated at version creation), a missing version is impossible (FK RESTRICT); any other exception is a bug and is allowed to propagate.
Other callers of `recompute_submission` (override, excuse, void, regrade) reuse statements 2–5 with their own transaction and add the `grade_events` insert; regrade also rewrites `attempt_grades` for every counted attempt of the submission (one multi-row upsert per chunk).

### 3.5 Race analysis (binding)
(a) finalize(A2 of user U) vs manual-score(A1 of U): both hold their attempt row, both then take `submissions(U, X)` by upsert; whichever waits re-reads attempts after the other committed → the last writer computes from the complete set. (b) override vs finalize: override locks the submission first (no attempt lock), finalize waits at statement 2, then recomputes with the override intact. (c) regrade chunk vs finalize: same as (b); regrade never holds attempts. (d) two overrides: `version` token → 409 `grade_conflict` for the stale client. (e) release vs hook on `auto`: `coalesce(released_at, now)` keeps the earliest release. (f) void vs autosave: void requires a final status; in-progress attempts cannot be voided (P4-20), so the autosave door (P3-22) is unaffected. Proven on PG in test 7.10.

### 3.6 Overrides, excuse, release, void, regrade (`actions.py`, `regrade.py`)
```python
def override(db, ctx, course, submission_id, data: OverrideIn) -> SubmissionStaffOut   # GRADES_MANAGE; points None clears; reason required (≤500) when points set; 0 ≤ points ≤ points_possible (422 points_out_of_range); version match else 409 grade_conflict
def excuse(db, ctx, course, submission_id, data: ExcuseIn) -> SubmissionStaffOut
def release(db, ctx, course, assessment_id, submission_ids: list|None) -> ReleaseOut    # chunks of 200 in id order; UPDATE … WHERE released_at IS NULL; one multi-row grade_events insert per chunk; {released: n}
def unrelease(...)                                                                     # symmetric; sets released_at NULL (student view hides)
def void_attempt(db, ctx, course, attempt_id, reason) -> AttemptStaffOut               # P4-20: attempt FOR UPDATE → status void → DELETE attempt_grades → recompute → event
def regrade(db, ctx, course, assessment_id) -> RegradeOut                              # P4-15: {regraded, pending, scheme_version_id}
```
`load_submission(db, course_id, submission_id, *, for_update)` → 404 `submission_not_found` for any miss (other course, missing). Every mutation: authenticate → `load_course` → `require_course(ctx, GRADES_MANAGE)` → `ratelimit.enforce` → load child by `(course.id, id)`.

### 3.7 Gradebook and totals (`gradebook.py`, `totals.py`)
```python
def gradebook_page(db, ctx, course, *, cursor, limit, assessment_ids, now) -> GradebookPageOut   # P4-19; writes course_grades for the page
def compute_totals(course_row, categories, assessments, submissions_by_enrollment, *, released_only) -> dict[enrollment_id, Totals]   # pure (P4-17), unit-tested
def my_grades(db, ctx, course, *, now) -> MyGradesOut                                              # student; released + results_visible filter; writes own course_grades row
def submission_detail(db, ctx, course, submission_id) -> SubmissionStaffOut                       # cell + counted attempts (with attempt_grades) + events (last 100)
def attempt_grade_out(db, attempt, assessment, *, staff) -> AttemptGradeOut|None                   # student result page (§5); previews computed inline via apply()
```
`my_grades` state per assessment: `graded` (visible), `pending` (submission exists, not released or results not visible yet, or `pending_review`), `missing` (no submission), `excused`, `hidden` (never per policy). Hidden/pending rows carry **no numbers**. Serializer contract test 7.3 asserts the field set per state.

## 4. Authorization
- No new actions. Mapping: scheme library routes `authenticated` (read/list), `teacher_approved+ratelimit` (create/version/title/delete), preview `authenticated+ratelimit`; course grading settings and categories `course:grades.manage`; gradebook/submission reads `course:attempt.read_all`; override/excuse/release/regrade/void `course:grades.manage+ratelimit`; student `grades/mine` `course:grades.read_own`; attempt result extensions keep `attempt_owner`. Concluded course → read-only (writes 403 via `decide()`); draft course → staff only.
- Pattern: authenticate → `load_course` → `require_course` → child loaders scoped by `course.id`. Scheme routes: `load_scheme` scopes by `owner_user_id = me OR owner_user_id IS NULL` in the `WHERE`; never load then compare.
- Students: never a route that takes another user's or submission id; `my_grades` derives the enrollment from `ctx`; the result payloads never include `user_id`, `submission_id` of others, `override_reason`, events or scheme `params` (only `type/scale/labels`).
- Route inventory: policy strings `authenticated`, `authenticated+ratelimit`, `teacher_approved+ratelimit`, `course:grades.manage`, `course:grades.manage+ratelimit`, `course:attempt.read_all`, `course:grades.read_own`, `attempt_owner`; dicts `SCHEME_POLICIES`, `GRADING_POLICIES`, `GRADEBOOK_POLICIES` merged in `route_inventory`.

## 5. API (all under `/api/v1`; LMS error shape; `{c}` course, `{a}` assessment, `{g}` scheme, `{s}` submission, `{k}` category, `{t}` attempt)

Schemes — `app/lms/grading/schemes_router.py`:

| method | path | in → out | policy | errors |
|---|---|---|---|---|
| GET | `/grading-schemes?cursor&limit&include_system` | `PageOut[SchemeSummaryOut{id,key,title,type,is_system,is_mine,current_version{id,version_no,scale_min,scale_max,created_at},deleted_at}]` | authenticated | — |
| POST | `/grading-schemes` | `SchemeCreateIn{title, type, params}` → `SchemeOut{…summary, versions:[SchemeVersionOut{id,version_no,type,scale_min,scale_max,params,labels,created_at,in_use_count}]}` 201 | teacher_approved+ratelimit | scheme_params_invalid, validation_failed |
| GET | `/grading-schemes/{g}` | → `SchemeOut` | authenticated | grading_scheme_not_found |
| PATCH / DELETE / POST | `/grading-schemes/{g}` / `…` / `…/restore` | `{title}` → `SchemeOut` / 204 / `SchemeOut` | teacher_approved+ratelimit | grading_scheme_not_found (system and others' schemes alike) |
| POST | `/grading-schemes/{g}/versions` | `{params}` → `SchemeVersionOut` 201 | teacher_approved+ratelimit | scheme_params_invalid, version_unchanged |
| POST | `/grading-schemes/preview` | `{type, params, possible, raws?: [Decimal] ≤1001 \| step?}` → `{rows:[{raw, display_value, label, percentile, passed, thresholds}]}` | authenticated+ratelimit | scheme_params_invalid |

Course grading — `app/lms/grading/router.py` (mutations, settings) and `gradebook_router.py` (reads, student):

| method | path | in → out | policy | errors |
|---|---|---|---|---|
| GET / PUT | `/courses/{c}/grading` | → `CourseGradingOut{total_mode, scheme?, late_policy?, categories:[CategoryOut{id,title,weight,position,assessment_count}], warnings}` (student: `total_mode, scheme{type,scale_min,scale_max,title}?` only) / `CourseGradingIn{total_mode, grading_scheme_version_id?, late_policy?}` → same | course:content.read / course:grades.manage | scheme_version_not_found, validation_failed |
| POST / PATCH / DELETE / PUT | `/courses/{c}/grade-categories`, `…/{k}`, `…/order` | `{title, weight}` → `CategoryOut` 201 / same / 204 / `{category_ids}` → `[CategoryOut]` | course:grades.manage | category_not_found, category_in_use, order_mismatch, too_many_categories |
| GET | `/courses/{c}/gradebook?cursor&limit≤50&assessment_ids` | → `GradebookPageOut{assessments:[GbAssessmentOut{id,title,points_possible,category_id,omit_from_total,grade_release,due_at,scheme?,score_policy,submission_count,released_count,stale_count,warnings}], rows:[GbRowOut{enrollment_id,user_id,student_name,cells:{assessment_id: CellOut{submission_id,state,kept_attempt_id,attempts_counted,raw_points,points_possible,late_deduction,override_points,has_override,effective_points,display_value,label,percentile,passed,thresholds,released_at,version}}, total:TotalsOut{current_percent,final_percent,display_value,label,passed,warnings}}], next_cursor}` | course:attempt.read_all | course_not_found |
| GET | `/courses/{c}/submissions/{s}` | → `SubmissionStaffOut{cell…, override_reason, override_by_name, override_at, attempts:[{id,attempt_no,status,raw_score,points_possible,submitted_at,late_seconds,grade:AttemptGradeOut?}], events:[GradeEventOut{id,event,actor_name,attempt_id,old,new,reason,created_at}]}` | course:attempt.read_all | submission_not_found |
| PUT | `/courses/{c}/submissions/{s}/override` | `OverrideIn{points: Decimal\|null, reason?, version}` → `SubmissionStaffOut` | course:grades.manage+ratelimit | grade_conflict, override_reason_required, points_out_of_range |
| PUT | `/courses/{c}/submissions/{s}/excuse` | `ExcuseIn{excused: bool, reason?, version}` → `SubmissionStaffOut` | course:grades.manage+ratelimit | grade_conflict |
| POST | `/courses/{c}/assessments/{a}/grades/release` / `…/unrelease` | `{submission_ids?: [uuid] ≤5000}` → `{released: n}` / `{unreleased: n}` | course:grades.manage+ratelimit | assessment_not_found, too_many_rows |
| POST | `/courses/{c}/assessments/{a}/grades/regrade` | → `RegradeOut{regraded, pending, scheme_version_id}` | course:grades.manage+ratelimit | assessment_not_found, rate_limited |
| POST | `/courses/{c}/attempts/{t}/void` | `{reason ≤500}` → `AttemptStaffOut` | course:grades.manage+ratelimit | attempt_not_found, attempt_in_progress, already_void |
| GET | `/courses/{c}/grades/mine` | → `MyGradesOut{total:{percent,display_value,label,passed}\|null, scheme?, items:[MyGradeOut{assessment_id,title,state,display_value?,label?,percentile?,passed?,thresholds?,effective_points?,points_possible?,late_deduction?,released_at?,kept_attempt_id?,due_at?}]}` | course:grades.read_own | course_not_found |

Extensions to Phase 3 responses (slice G3, `attempts/serializers.py`): `AttemptResultOut.grade: AttemptGradeOut{scheme_type, scale_min, scale_max, display_value, label, percentile, passed, thresholds, sections:[{pos, display_value}]|null, is_kept, released}|null` (student: only when visible per P4-11; preview: inline); `MyAttemptOut.grade` likewise; `AttemptStaffSummaryOut/AttemptStaffOut.grade` always; `AttemptStaffOut.submission_id`. Status `void` renders as `{status: "void"}` with no result for students.
New `lms.errors.*`: `grading_scheme_not_found, scheme_version_not_found, scheme_params_invalid, version_unchanged, submission_not_found, grade_conflict, override_reason_required, category_not_found, category_in_use, too_many_categories, too_many_rows, value_out_of_range, attempt_in_progress, already_void`.

## 6. Frontend (client components inside `LmsShell`/course layout; server decides; trilingual)

| path | content |
|---|---|
| `app/[lang]/grading-schemes/page.tsx`, `…/new/page.tsx`, `…/[schemeId]/page.tsx` | Scheme library (system first, badges, type, current version); editor with **type-specific forms** (`PointsForm`, `PercentForm`, `BandsForm` (sortable rows, trilingual labels), `PassFailForm`, `CurveForm` (segment table + scale/percentile/thresholds/zero-raw), `LookupTableForm` (paste CSV `raw_from,raw_to,value,label`)) and a **live preview table** (`POST /grading-schemes/preview`, debounced 400 ms, `possible` input, 0..N or step); system schemes are read-only with "Duplicate to my library". Saving creates a new version ("Students already graded keep version k until you regrade"). |
| `courses/[courseId]/assessments/[assessmentId]/edit` settings panel (existing) | adds **Grading** group: scheme picker (`SchemePicker`: system + mine, shows type/scale), kept policy (`score_policy`), category, `due_at`, release mode, "omit from total"; warning chip when `stale_count > 0` with a **Regrade** button (calls regrade until `pending = 0`). |
| `courses/[courseId]/settings` (existing) | **Grading** section: total mode, course scheme picker, late policy form, categories editor (add/rename/weight/reorder/delete; live "weights sum to N %" note and the P4-17 normalization explanation). |
| `courses/[courseId]/grades/page.tsx` | staff: **gradebook** grid (sticky student column, assessment columns with points/scale, cells show `display_value` or points with override/late/excused/unreleased markers, pending-review badge, totals column, pager, column filter, per-assessment menu: Release all / Unrelease / Regrade); cell click → side panel (`SubmissionPanel`: kept attempt link, attempts list with per-attempt grade, override with reason + version, excuse, events timeline). Student: **My grades** (states per §3.7, total, scheme label). |
| `courses/[courseId]/attempts/[attemptId]/result` (existing) | `ResultSummary` gains `GradeBadge` (big display value, label, percentile, threshold flags such as the golden certificate, "kept attempt" marker, "not released yet"). When `grade.sections` is present → `OrtResultView`: section table with raw, scaled per section, overall scaled, percentile, golden-certificate banner. Staff attempt pages show the same badge plus a **Void** action with reason. |
`CourseTabs.tsx`: "Grades" tab for everyone (`gradebook.tab`). Lib/types: `lib/lms/{grading,gradingTypes}.ts` (schemes, settings, gradebook, submissions, my grades), `attemptTypes.ts` gains `AttemptGradeOut`, `staffAttempts.ts` gains `voidAttempt`. i18n (parity en/ky/ru): `schemes.*` (library, forms, preview, types, params field labels, validation), `grading.*` additions (settings, labels `pass/fail`, thresholds `golden_certificate`), `gradebook.*` (grid, states, panel, events, release, regrade), `results.grade.*`, new `lms.errors.*`. Number formatting via the existing `fmtPoints`; percentiles with one decimal.

## 7. Test plan (`backend/tests/lms/`, scratch DB per `AGENTS.md` 6.1; `frozen_clock`; factories append `make_scheme(db, owner, type, params)`, `make_submission(...)`, `grade_attempt(db, attempt, raw)`)

1. **Registry unit** `test_grading_registry.py`: every type × (raw 0, mid, full, > possible, possible 0, fractional raw); rounding modes; percentile clamps; thresholds; `zero_raw`; bands ordering validation errors; curve contiguity errors; lookup gaps/overlaps; params caps; `preview` 1,001 cap.
2. **ORT parity gate** `test_ort_parity.py`: exhaustive `N ∈ 1..200`, `raw ∈ 0..N` for both system versions: `apply().display_value == ScoringService.raw_to_scaled(raw, N, exam_type)` and `percentile == calculate_percentile(...)`, `golden_certificate == (main and scaled ≥ 219)`; per-section parity via `apply_sections` against `raw_to_scaled` per section on `test_scoring`'s fixtures; every assertion of `tests/test_scoring.py` re-expressed against the new path. Also writes/compares frozen tables `tests/lms/fixtures/ort_parity_{main,subject}.json` (generated once from the oracle; the test compares against **both** the live oracle and the frozen file so the gate survives Phase 5). Hypothesis (`pytest.importorskip`) adds monotonicity in `raw` and fractional raws.
3. **Serializer contracts** `test_grading_serializers.py`: for every student-facing payload (`result`, `review`, `mine`, `grades/mine`, lobby, course grading GET) across `grade_release auto/manual`, released/unreleased, `results_policy` × `show_correct_answers`, states pending/hidden/missing/excused: exact key sets; sentinels in `override_reason`, `params`, events, other students' ids never present; numbers absent for hidden/pending.
4. **Submissions service** `test_submissions.py`: kept policies table (highest with tie, latest, first, average across versions with different `points_possible`); needs_review → pending_review → manual score → graded; late deduction table (grace edge, cap, no `due_at`, no policy); override keeps through recompute, clearing restores, reason required, range; excuse/unexcuse; release/unrelease idempotent and `auto` keeps the earliest `released_at`; void changes the kept attempt and deletes its `attempt_grades`; previews create nothing; **scheme edit creates a new version and leaves `attempt_grades`/`submissions` untouched until regrade**; regrade resumable (kill after chunk 1 by raising → second call finishes; counts), cap and `pending`; D14 switch of `score_policy` sets `stale_count`.
5. **Statement budgets** (`before_cursor_execute` counters, extend Phase 3 test 7.5): submit ≤ 13, manual score ≤ 11, override ≤ 8, gradebook page (50 × 20) ≤ 6, `grades/mine` ≤ 6, release of 500 ≤ 8.
6. **Totals unit** `test_grade_totals.py`: points mode; weighted with weights 100 / 70 / 130; empty category skipped; all-zero → null; uncategorized excluded + warning; omitted assessments; excused; `final` counts missing as 0; released-only view; course scheme mapping (pass/fail on the total); `course_grades` written and `computed_at` advances.
7. **Scheme API** `test_grading_schemes_api.py`: create/version/title/delete/restore; system schemes read-only (404 on write); `version_unchanged`; preview; list = system ∪ mine; immutability listeners raise.
8. **Matrix/isolation** `test_grading_matrix.py`, `test_grading_isolation.py`: actors O, T, AS, S, R, X, P × course statuses over every new route (Phase 2 §7.5 pattern); TA cannot see/use/version TB's scheme (404 on list absence, GET, versions, and on attaching it to TA's assessment → `scheme_version_not_found`); staff of CB cannot read CA's gradebook/submissions (404); student never sees another student's grade through any route (grid, submission detail, mine, attempt result of another user → 404/absent); platform admin no bypass.
9. **E2E** `test_phase4_flow.py`: Phase 3 flow (import ORT bundle → `ort_main` → publish) continues: S1 submits → `attempt_grades` and `submissions` rows exist inside the same commit (`graded_at == computed_at` sources; hook counter 1), result shows `grade.display_value == oracle`, percentile, section scaled values, golden flag false; S2 scores ≥ 135/150 → golden true; teacher gradebook shows both, totals; teacher switches the assessment to a new `ort_main`-derived version with a different threshold → old grades unchanged → regrade → changed, events written; student with `manual` release sees `pending` until release; a `percent` course and a `pass_fail` course are created through the API alone.
10. **PG concurrency** `test_pg_concurrency_grading.py` (`LMS_PG_TEST_DATABASE_URL`): 10 threads finalize attempts of 10 users → 10 submissions, each once; manual-score(A1) ‖ finalize(A2) for one user, 50 iterations → final submission equals a serial recompute; override ‖ finalize → override preserved; regrade ‖ finalize → no deadlock, final state consistent; two overrides with the same `version` → one 409.
11. **Migration/inventory**: append `0004 → 0005 → 0004 → 0005` and `alembic check`; route inventory lists every new route with a valid policy; `test_single_checkout.py` extended to `grades/mine`, gradebook, override.
Frontend: `tsc --noEmit`, isolated `next build`, i18n parity; scripted manual check (scheme editor preview for each type; gradebook override → event visible; regrade button loop; student sees golden banner).

## 8. Slices (strict file ownership; model per slice)

| slice | model | owns (only these files) | depends on | must pass |
|---|---|---|---|---|
| **G1 Schema + registry + seeds + settings** | opus | `app/lms/grading/{__init__,models,registry,params,repository,schemes,seeds}.py`, `alembic/versions/0005_phase4_grading.py`, `app/lms/models.py`, `app/core/config.py` (caps, limits), `app/lms/core/ratelimit.py` (new `Limit`s), `app/lms/core/errors.py`/`LMS_PATH_PREFIXES`, `app/main.py` (seed + hook import), `app/lms/assessments/{schemas,builder,router}.py` (§3.3 fields, preset scheme), `app/lms/courses/{schemas,service,router}.py` (`/grading`, categories — or a new `grading/settings_router.py` if the course router is crowded), `tests/lms/{conftest,factories}.py`, `tests/test_migrations.py`, `tests/lms/fixtures/ort_parity_*.json`, tests 7.1, 7.2, 7.7 (service part), `test_phase4_constraints.py` | Phase 3 on branch | 7.1, 7.2 exhaustive parity, migration + `alembic check` on PG, full suite |
| **G2 Submissions, hook, actions, regrade** | opus; **architect (fable) reviews** `submissions.py` + lock order + 7.10 | `app/lms/grading/{submissions,late,actions,regrade,events,router,policies,schemas}.py`, hook registration body in `grading/__init__.py`, `app/lms/attempts/staff_router.py` + `staff_policies.py` (void route only), tests 7.4, 7.5, 7.10, `test_phase3_*` budget updates | G1 | its tests, full suite |
| **G3 Gradebook, totals, student grades, result extension** | opus | `app/lms/grading/{gradebook,totals,serializers,gradebook_router,gradebook_policies}.py`, `app/lms/attempts/{serializers,results,router}.py` (grade field, void rendering), tests 7.3, 7.6, 7.8 (gradebook/mine part) | G1; G2 `recompute_submission` for void (stub until G2 lands) | its tests, full suite |
| **G4 Scheme API routes** | sonnet | `app/lms/grading/{schemes_router,schemes_policies,schemes_schemas}.py`, `app/core/route_inventory.py`, `app/api/v1/router.py` (mount all three grading routers; G2/G3 provide theirs), tests 7.7 (API part), 7.8 (scheme part) | G1 | its tests, route inventory, full suite |
| **F1 Scheme library + editor UI** | opus | `frontend/src/lib/lms/{grading,gradingTypes}.ts` (types committed first), `components/lms/grading/schemes/**`, `app/[lang]/grading-schemes/**`, i18n `schemes.*`, `lms.errors.*` (all new codes) | this contract; live after G4 | `tsc`, isolated `next build`, i18n parity |
| **F2 Assessment + course grading settings UI** | sonnet | `components/lms/assessments/SettingsPanel*` grading group, `components/lms/grading/settings/**` (course grading section, categories editor, `SchemePicker`), edits to `app/[lang]/courses/[courseId]/settings/page.tsx` and the assessment edit page (grading group only), `lib/lms/assessments.ts`/`assessmentTypes.ts` (new fields), i18n `grading.settings.*` | F1 types; live after G1/G4 | same |
| **F3 Gradebook + submission panel UI** | opus | `components/lms/gradebook/**`, `app/[lang]/courses/[courseId]/grades/**` (staff branch), `components/lms/CourseTabs.tsx`, `staffAttempts.ts` (`voidAttempt`), i18n `gradebook.*` | F1 types; live after G2/G3 | same |
| **F4 Student results + my grades UI** | sonnet | `components/lms/results/{GradeBadge,OrtResultView,StudentGrades}.tsx`, edits to `ResultSummary.tsx`, `StudentResult.tsx`, `StaffAttemptDetail.tsx` (badge + void), `app/[lang]/courses/[courseId]/grades/page.tsx` (student branch), `attemptTypes.ts` (`AttemptGradeOut`), i18n `results.grade.*` | F1 types; live after G3 | same |
| **Integration** | orchestrator + implementer (opus); **fable** for the final review | `tests/lms/test_phase4_flow.py`, `docs/phases/PHASE_4.md`, `PRODUCT_DECISIONS.md` (P4 decisions), i18n merge | all | §0 gates, `/code-review`; security-style pass on §4 (grades are personal data) |

Parallelism: G1 first (its signatures in §3.1–§3.3 are fixed); then G2, G3, G4 in parallel (G3 stubs `recompute_submission`; the orchestrator merges G2 → G3 → G4). F1 starts at once against §5 (types first); F2/F3/F4 after F1's types land.

## 9. Risks and open questions

- **Submit burst budget**: the hook adds 5 statements (≈ 5–10 ms DB time co-located) and one `apply()` (< 0.1 ms). If the Phase 3 load gate (§8.1) regresses past p95 2 s, first drop statement 4 (`attempt_grades`) into a lazy compute on the result page; then move the hook post-commit (design change, review needed).
- **Oracle float parity**: `piecewise_curve` must use float64 in the oracle's expression order; a "cleaner" Decimal implementation would fail the exhaustive gate on a handful of raws (banker's rounding at `.5`). The gate is exhaustive precisely so this cannot slip.
- **D6 quirk**: shipped as data (`zero_raw`); removing it later = a new system version + regrade on request, no code change.
- **Official CEATM tables** unknown: `lookup_table` + `expected_possible` is ready; a mismatch between the table's N and a teacher-edited exam only warns.
- **Regrade of a 6,000-student exam**: 30 chunks ≈ 30 requests through the UI loop (cap 2,000 per call); acceptable without workers; document in `PHASE_4.md`.
- **Scheme ownership vs course transfer** (P1): a course transferred to a new owner keeps assessments pointing at the old owner's versions (immutable, still apply); only the picker hides them. Acceptable; noted for Phase 9 privacy review.
- **Q1**: should `average` keep `highest`'s tie rule for `kept_attempt_id` (currently latest)? Default: latest.
- **Q2**: gradebook CSV export and per-student extra time/attempt overrides are deferred to Phase 8 (`extra_time_s` exists; no API).
- **Deferred**: comments on submissions, rubric grading, peer review, grade posting policies per student, drop-lowest rules, SpeedGrader-style queue (Phase 8), Playwright.
