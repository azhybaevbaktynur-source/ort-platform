# Canvas assessments: what the real code does, and what we should build

**Written**: 2026-10-21. **Source**: `instructure/canvas-lms` shallow clone, commit `1c9f0bb` (2026-04-30), read only, nothing run. New Quizzes facts come from Instructure's public API docs, because its backend source is **not public**: the `instructure` GitHub org has about 223 repos, and the only quiz-related ones are `qti` and `QTIMigrationTool`. Anything I could not check in code is marked **[unverified]**.

---

## 1. What Canvas Classic Quizzes actually does

### 1.1 Tables (`db/migrate/20101210192618_init_canvas_db.rb`)

| Table | Key columns |
|---|---|
| `assessment_question_banks` | `context_id/context_type` (polymorphic Account or Course), `title`, `workflow_state` (active/deleted), `deleted_at`, `migration_id` |
| `assessment_questions` | `name`, `question_data` **text (Rails `serialize`)**, `assessment_question_bank_id`, `position`, `workflow_state` (active / independently_edited / deleted), `deleted_at` |
| `quizzes` | `quiz_data` text (the **published snapshot**), `points_possible`, `quiz_type`, `time_limit` (minutes), `allowed_attempts`, `scoring_policy`, `shuffle_answers`, `access_code` string(255), `ip_filter` string, `one_question_at_a_time`, `cant_go_back`, `show_correct_answers(_at/_last_attempt)`, `hide_correct_answers_at`, `hide_results`, `due_at/lock_at/unlock_at`, `disable_timer_autosubmission`, lockdown-browser flags, `workflow_state` |
| `quiz_groups` | `quiz_id`, `name`, `pick_count`, `question_points`, `position`, `assessment_question_bank_id` (nullable) |
| `quiz_questions` | `quiz_id`, `quiz_group_id`, `assessment_question_id`, **`question_data` (a full copy)**, `assessment_question_version`, `position`, `workflow_state` (active/deleted/**generated**), `duplicate_index` |
| `quiz_submissions` | **unique `(quiz_id, user_id)`**, `attempt`, `quiz_version`, `quiz_data` (snapshot per attempt), `submission_data`, `started_at`, `end_at`, `finished_at`, `score`, `kept_score`, `fudge_points`, `extra_time`, `extra_attempts`, `validation_token`, `was_preview`, `workflow_state` |
| `quiz_submission_events` | `quiz_submission_id`, `attempt`, `event_type`, `event_data`, `created_at`, `client_timestamp` (partitioned) |
| `quiz_submission_snapshots` | `quiz_submission_id`, `attempt`, `data` |

There is no `question_type` column. The type is `question_data[:question_type]`. There is no per-question language and no translation support: question text is single-language sanitized HTML.

### 1.2 Banks and questions
- `AssessmentQuestionBank` (`app/models/assessment_question_bank.rb`): soft delete via `destroy` (sets `workflow_state = "deleted"` and `deleted_at`). Users can bookmark a bank through `assessment_question_bank_users`, which is how banks are shared. `unfiled_for_context` auto-creates an "Unfiled Questions" bank.
- `AssessmentQuestion` (`app/models/assessment_question.rb`): 13 types in `ALL_QUESTION_TYPES`: multiple_choice, true_false, multiple_answers, short_answer, fill_in_multiple_blanks, multiple_dropdowns, matching, numerical, calculated, essay, file_upload, text_only, missing_word. Versioning is `simply_versioned automatic: false`. `parse_question` allowlists the keys of `question_data`: `question_text`, `answers`, `points_possible`, `formulas`, `variables`, `answer_tolerance`, `matches`, and comment fields. HTML is sanitized in `QuestionData.generate` (`app/models/quizzes/quiz_question/question_data.rb`).
- `question_data` shape: `{question_type, question_name, question_text (HTML), points_possible, answers:[{id, text, html, weight(100=correct), comments...}], ...}`. Numerical answers carry `numerical_answer_type` (`exact_answer` + `margin`, where the margin may be a %; `range_answer` with `start/end`; `precision_answer`). Fill-in and dropdown answers carry `blank_id`.

### 1.3 Quizzes, groups, quiz questions
- **Quiz-level questions are copies, not links.** `Quiz#add_assessment_questions` copies `question_data` into a new `QuizQuestion` and records `assessment_question_version`. A question written directly in a quiz goes the other way: `QuizQuestion#create_assessment_question` creates a matching AssessmentQuestion, usually in "Unfiled Questions". Deciding which side may edit the other relies on a heuristic: `AssessmentQuestion#editable_by?` compares `created_at` within a 30-second to 5-minute window.
- `QuizGroup` (`quiz_group.rb`) has two modes. It either holds its own quiz questions (picked and shuffled per student), or it points at a bank (`assessment_question_bank_id`), and then `question_points` overrides each question's points.
- **Publishing freezes the quiz.** The `generate_quiz_data_on_publish` callback runs `generate_quiz_data`, which writes `root_entries` (questions and groups ordered by `position`) into `quizzes.quiz_data` and recomputes `points_possible`. Comment in `quiz_group.rb`: "the teacher can be futzing with questions and groups and not affect the quiz, as students see it." The quiz itself is also `simply_versioned`.

### 1.4 Attempts (`quiz.rb#generate_submission`, `quiz_submission.rb`, `quiz_question_builder.rb`)
- There is **one `quiz_submissions` row per user per quiz.** Each retake overwrites it (`attempt += 1`), and earlier attempts survive only as `versions` rows (`QuizSubmissionHistory`).
- At start: `QuizQuestionBuilder#build_submission_questions` resolves groups. For bank groups it calls `AssessmentQuestionBank#select_for_submission`: active questions minus those already picked, `ORDER BY RANDOM() LIMIT pick_count`, then it creates `generated` QuizQuestions and shuffles them. It shuffles answers too, unless the type is true_false, matching or fill_in_multiple_blanks. The full result goes into **`quiz_submissions.quiz_data`** along with `quiz_version`, which makes it a per-attempt snapshot. An event `submission_created` with the `quiz_data` is also logged.
- **Deadline is computed by the server**: `end_at = started_at + time_limit + extra_time`, capped at `lock_at` (`build_submission_end_at`). `time_left` = `end_at - now`. `overdue?` allows 5 minutes of grace (1 minute in strict mode). `QuizSubmissionService#update_question` rejects answers once the attempt is overdue or complete. `rectify_finished_at_drift` snaps `finished_at` back to `end_at` when the drift is 5 minutes or less. Expired attempts are auto-submitted by the browser JS. On the server, `OutstandingQuizSubmissionManager` grades leftovers (`needs_grading`: untaken and `end_at < now`).
- **Autosave lock**: `backup_submission_data` writes with `update_all ... WHERE workflow_state NOT IN ('complete','pending_review')`. A full snapshot is taken every 5th save. `cant_go_back` is enforced on the server through `_question_N_read` markers.
- **Finalize**: `complete!` takes a snapshot, marks the attempt complete and calls `SubmissionGrader#grade_submission`. That method raises `AlreadyGradedError` if `submission_data` is already an Array: the column holds a Hash of raw answers while the attempt is open and an Array of graded results afterwards. The service also checks `untaken?`, `validation_token` (owner) and `ensure_latest_attempt!`.
- **Kept score**: `score_to_keep` in `quiz_submission.rb` supports `keep_highest` (default), `keep_average` and `keep_latest`. `attempts_left` = `allowed_attempts - attempt + extra_attempts`, and -1 means unlimited.
- **Access gate** (`quiz_eligibility.rb`): the access code is compared in plain text against `session[:quiz_access_code][quiz.id]`. `access_code` is listed in `serialization_excludes`. `ip_filter` is a comma-separated list of IPAddr ranges, plus account-level named filters.
- **Hiding answers from students**: `lib/api/v1/quiz_question.rb#censor` uses **allowlists**: question keys, answer keys (`id`, `text`, `html`, `blank_id`, `variables`), and which types may send `answers` at all. Weights (the answer key) are never sent.

### 1.5 Auto-scoring (`app/models/quizzes/quiz_question/*.rb`)
Lookup goes through `Base.from_question_data`, with subclasses registered via `inherited` (a registry pattern). `UserAnswer#score` = `correct_parts / total_parts * points`, minus a penalty for incorrect parts (`incorrect_dock` or proportional), floored at 0. Partial credit defaults to on.
- multiple_choice / true_false / missing_word: the chosen answer must have `weight == 100`.
- multiple_answers: parts = number of correct choices, wrong ticks subtract.
- short_answer: **exact match after strip + downcase** against the accepted list. No wildcards.
- numerical: exact ± margin, range, or precision. calculated: answer sets are **pre-generated at authoring time** and one is `sample`d per attempt. Nothing is evaluated at runtime.
- matching and fill_in_multiple_blanks: scored per part. essay and file_upload: `requires_manual_scoring?`, which puts the attempt in `pending_review`. text_only: 0 parts and excluded from `question_count`.

### 1.6 Passages, images, math
- **Classic quizzes have no passage concept.** `text_only_question` is a standalone "Spacer" (`decorate_question_for_submission`) with **no link** to the questions that follow it. Inside a random group it gets shuffled like any other item.
- **Images and files**: question HTML links to course files. `AssessmentQuestion#translate_links` clones each linked attachment into the question's own context and rewrites the URL to `/assessment_questions/:id/files/:fid/download?verifier=<uuid>`. `QuizQuestion` copies the attachment associations.
- **Math**: the editor stores `<img class="equation_image" src="/equation_images/<double-URL-escaped LaTeX>" data-equation-content="...">`. `EquationImagesController` redirects to the MathMan SVG service or to codecogs. `lib/quiz_math_data_fixup.rb` exists only to repair broken math HTML. `lib/latex/math_ml.rb` converts LaTeX to MathML for accessibility.

### 1.7 Changing questions after attempts
Editing a published quiz does not touch attempts already started, because each one holds its own `quiz_data` copy. Changes reach students only on republish (`check_if_submissions_need_review`, `changed_significantly_since?`). An answer-key change can trigger regrading (`QuizRegrade`, `QuizQuestionRegrade`) with options `full_credit | current_and_previous_correct | current_correct_only | no_regrade | disabled`.

### 1.8 Signs in the code that the design was painful
- An open TODO about id collisions between AssessmentQuestion and QuizQuestion ids (`AssessmentQuestion#data`).
- `QuestionReferenceDataFixer`, which repairs submissions whose `quiz_data` points at AQ ids.
- The math fixup jobs.
- The time-window heuristic in `editable_by?`.
- Attempts stored as versions of a single row.
- YAML/JSON text blobs that cannot be queried.

### 1.9 New Quizzes (from the public API docs only; source not public)
- Separate service, embedded in Canvas over LTI (`app/models/quizzes_next/service.rb`: `type_quiz_lti` assignments).
- A quiz is a list of **QuizItems**: `position`, `points_possible`, `entry_type` ∈ {Item, Stimulus, BankEntry, Bank}, `stimulus_quiz_entry_id`, `status` (mutable/immutable).
- Items have `item_body`, `interaction_type_slug`, `interaction_data`, `scoring_data`, `scoring_algorithm`. In other words, the student-visible data and the answer key are **separate fields**.
- Types: choice, multi-answer, true-false, numeric, formula, essay, file-upload, matching, categorization, ordering, rich-fill-blank, hot-spot.
- **Stimulus** is a first-class item (`body`, `instructions`, `passage` boolean, `orientation` top/left) and questions attach to it.
- Bank draws use `sample_num`.
- Settings include `session_time_limit_in_seconds` (one timer per quiz, with no per-section timers), `shuffle_questions`, `allow_backtracking`, `one_at_a_time_type`, `student_access_code`, IP `filters`, `multiple_attempts.score_to_keep` ∈ {average, first, highest, latest}, `cooling_period_seconds`, and a detailed `result_view_settings`.
- **[unverified] Why Canvas moved**: Instructure's public messaging cites more item types, stimuli, shareable item banks and accommodations. The code evidence above (copy synchronization, blob fixups) is consistent with that. Classic Quizzes sunset: no confirmed official date. One institution announced a creation cutoff on 2026-05-11, and others say no date is set.

---

## 2. Corrections to the drafts

| Draft claim (`CANVAS_INTEGRATION_SPEC.md` §5/§8, Explainer Block 6) | Reality |
|---|---|
| "Questions do not live inside Quizzes… quizzes pull questions dynamically… or direct links" | Fixed quiz questions are **copies** (`quiz_questions.question_data`) with a version number. There are no live links. Only bank-backed groups draw at attempt start, and even those draws are materialized as `generated` QuizQuestions and snapshotted into the attempt. |
| 9 native question types | 13 types. The draft misses matching, fill_in_multiple_blanks, multiple_dropdowns and missing_word. |
| short_answer "with wildcard support" | No wildcards: exact, case-insensitive match after trimming. |
| calculated "dynamically assigns randomized numbers … and evaluates" | Variable sets are generated when the question is authored. One set is sampled per attempt. |
| text_only = "reading passage … followed by related questions" | A spacer with no link to other questions. Shared passages exist only in **New Quizzes** (Stimulus). |
| `access_code`: "4-to-6 digit PIN" | Free-text string(255), stored in plain text, kept in the session, excluded from serialization. |
| `scoring_policy` | Correct, and `keep_average` exists in code. [unverified] whether the Classic UI offers it. New Quizzes adds `first`. |
| QuizGroup runtime `order("RANDOM()").limit(n)` | Roughly right (`select_for_submission`). It also excludes questions already picked, creates `generated` rows and reshuffles. Groups can also hold their own questions without any bank. |
| Spec §8 model: `question_type` column + JSON `question_data` | Canvas has no type column, and `question_data` is a serialized text blob. A type column is still a good idea for us, just not one copied from Canvas. |
| Spec §9: "Fixed 150-Q timed exam via `Quiz`" | Neither Classic (`time_limit`) nor New Quizzes (`session_time_limit_in_seconds`) supports **per-section time limits**. ORT needs them, so we must build them ourselves. |
| Explainer: bank of "40 passages" with random draws | Classic random draws would split passages from their questions. Whether New Quizzes banks draw a stimulus together with its questions: [unverified]. |
| "Every student takes a unique, cheating-proof exam" | Only for groups. Fixed questions are shared. Answer order is shuffled only when `shuffle_answers` is set. |

The drafts also say nothing about the per-attempt snapshot, the server-side `end_at`, the autosave lock, or answer censoring. Those are the parts most worth copying.

---

## 3. Recommendation for our product (SQLAlchemy 2 / Postgres)

Rules for every table below: UUID primary keys, `created_at`, `created_by`, and **`deleted_at` for soft delete** on content tables. Never cascade-delete attempts. Use `JSON().with_variant(JSONB, "postgresql")` so the SQLite tests keep working.

### 3.1 Banks, passages, questions
```
question_banks(id, owner_id→users, course_id→courses NULL, title, deleted_at)
assets(id, owner_id, sha256 UNIQUE per owner, storage_key, mime, bytes)        -- object storage, signed URLs
passages(id, bank_id, current_version_id, deleted_at)
passage_versions(id, passage_id, version_no, title JSON{lang:text}, body JSON{lang:text}, created_at)
questions(id, bank_id, passage_id NULL, type, topic, difficulty, tags JSON,
          position NULL,                  -- document order inside the bank (imports)
          source_ref NULL,                -- e.g. "<source_id>:<section>:<q_num>", UNIQUE(owner_id, source_ref)
          current_version_id, deleted_at)
question_versions(id, question_id, version_no, type, schema_version,
                  stem JSON{lang:text}, data JSON, explanation JSON{lang:text},
                  default_points NUMERIC, created_at, created_by)   -- immutable once inserted
```
- **Versioning**: every edit inserts a new `question_versions` row and moves `current_version_id`. Quizzes and attempts point at **version ids**. This replaces Canvas's copy-and-sync machinery and its fixers: nothing is copied and nothing goes stale.
- **i18n**: each language-bearing field is a `{ "en"?, "ru"?, "ky"? }` map. The answer key lives in `data` and refers to stable choice ids, so scoring does not depend on language. The questions a quiz may use are those that have all of the quiz's `languages`; validate this at publish. ORT ky and ru exams are different item sets, so each question simply has only `ky` or only `ru`. Translations that are not equivalent should be separate questions.
- **`data` per type**: validated by a Pydantic model looked up by `type` (see 3.4). Inline images go in as `assets` ids (`image_asset_id`, or `![](asset:<id>)` inside text), never as raw `/uploads` paths. Math stays raw LaTeX inside the text and is rendered by KaTeX on the client (as today). Do **not** copy Canvas `equation_images`. Store text as sanitized Markdown+LaTeX, or as a small allowlisted HTML subset (sanitize on write with `nh3`).

### 3.2 Quizzes
```
quizzes(id, course_id, owner_id, title JSON, description JSON, languages JSON,
        status draft|published, published_version_id NULL,
        time_limit_s NULL, allowed_attempts INT (-1 = unlimited), score_policy highest|latest|first|average,
        shuffle_items BOOL, shuffle_choices BOOL, navigation free|section_forward_only,
        results_policy (never|after_submit|after_close) + show_correct_answers BOOL,
        available_from/available_until TIMESTAMPTZ, grading JSON {scheme: points|percent|ort_main|ort_subject, ...},
        deleted_at)
quiz_sections(id, quiz_id, position, key NULL (e.g. "math_1"), title JSON, time_limit_s NULL, rules JSON)
quiz_items(id, quiz_id, section_id, position,
           kind question|passage|pick,
           question_id NULL, passage_id NULL,
           points NUMERIC,
           pick_bank_id NULL, pick_count NULL, pick_filter JSON NULL)    -- optional random group
quiz_versions(id, quiz_id, version_no, snapshot JSON, published_at)    -- like Canvas quizzes.quiz_data
```
- **Publish** resolves every item to its `current_version_id` and writes `quiz_versions.snapshot` (settings, sections, items, version ids, points). Students only ever see a published version. Editing creates a draft and republishing bumps `version_no`. This is Canvas's `generate_quiz_data`, but with version ids instead of copied blobs.
- A random `pick` item draws `pick_count` questions at attempt start, excluding questions already used in the quiz (as Canvas does). If a drawn question has a passage, its passage block is drawn with it as one unit (later; v1 can forbid picks in passage sections).

### 3.3 Attempts
```
attempts(id, quiz_id, quiz_version_id, user_id, attempt_no, language, is_preview,
         status in_progress|submitted|needs_review|graded|void,
         started_at, deadline_at,                 -- server: min(started+limit+extra, available_until)
         current_section_pos, extra_time_s DEFAULT 0,
         submitted_at, submit_reason manual|timeout|sweep,
         raw_score, points_possible, result JSON (scaled score, percentile, section breakdown))
  UNIQUE(quiz_id, user_id, attempt_no); partial UNIQUE(quiz_id, user_id) WHERE status='in_progress'
attempt_sections(attempt_id, section_pos, started_at, deadline_at, closed_at)
attempt_items(id, attempt_id, position, section_pos, question_version_id, points,
              choice_order JSON NULL,           -- shuffle permutation (the snapshot)
              response JSON NULL, flagged BOOL, answered_at,
              score NUMERIC NULL, correctness correct|partial|incorrect|pending NULL,
              manual_score NULL, feedback TEXT NULL)
```
- **Snapshot at start**: create every `attempt_items` row in one transaction (resolved picks, permutations, points). The attempt then never depends on later edits. Unlike Canvas, there is one row per attempt, not one row per user plus history versions.
- **Rows per answer instead of a JSON blob.** Benefits: autosave becomes an `UPDATE` on a single row, with no race when two tabs read, modify and write the same blob. Per-item statistics and analytics become SQL, which replaces `Question.stats` and the bogus "discrimination index". Manual grading and regrading also work per item. Cost is about 150 rows per ORT attempt, which is trivial.
- **Integrity**:
  - Autosave: `UPDATE attempt_items … WHERE attempt.status='in_progress' AND now() <= LEAST(attempt.deadline_at, section.deadline_at) + grace`. Use a 30–60 s grace; Canvas uses 1–5 minutes.
  - Submit: `UPDATE attempts SET status='submitted' WHERE id=:id AND status='in_progress' RETURNING`. Exactly one caller wins; grading runs only for that caller. This closes resubmission for good.
  - Expiry is handled lazily: any read or write past the deadline auto-submits. A periodic sweep catches abandoned attempts (Canvas's `OutstandingQuizSubmissionManager`).
  - Section navigation: closing a section sets `closed_at`, and from then on writes to its items are rejected. This is the server-side equivalent of Canvas's `cant_go_back`.
- **Never leak answers.** Each type defines a `student_view(version, choice_order)` that builds the student payload from an **allowlist** (Canvas `censor`). Never serialize `data` directly. Results and review go through `results_policy`.
- **Kept score** is computed when needed from attempts (status graded, not preview) according to `score_policy`. Store nothing on `users`.

### 3.4 Question-type registry
```python
QUESTION_TYPES: dict[str, QuestionType]  # each: DataModel (pydantic), ResponseModel, student_view(), score(data, response, points) -> (score, correctness)
```
| v1 | Data (keys illustrative) | Scoring |
|---|---|---|
| `single_choice` | `choices:[{id, text{lang}, image_asset_id?}]`, `correct:id` | all or nothing |
| `multiple_answers` | `choices`, `correct:[ids]`, `mode: all_or_nothing\|partial` | Canvas parts formula, floor 0 |
| `true_false` | `correct: bool` | all or nothing |
| `comparison` (ORT math_1) | `column_a{lang}`, `column_b{lang}`, `correct: A\|B\|C\|D`. The 4 labels are fixed by the app (i18n), not stored per question | all or nothing |
| `numeric` | `answers:[{exact, margin, margin_pct?} \| {min, max}]` | any match |
| `short_text` | `accepted:[text{lang}]`, `case_sensitive=false`, normalize whitespace and Cyrillic look-alikes | exact after normalization |
| `essay` | `rubric_hint?` | manual, sets attempt `needs_review` |

Later: matching, ordering, fill_blanks (multiple blanks), file_upload (needs storage plus privacy review). Skip: calculated, multiple_dropdowns, hot-spot, categorization, missing_word. No `text_only` type: passages cover that need.

### 3.5 Mapping current ORT behavior
- **ORT main / subject exam** = a quiz with `grading.scheme = ort_main | ort_subject`. Sections `math_1, math_2, analogies, reading, grammar` each get their own `time_limit_s`, with `navigation = section_forward_only` and shuffle off. Today's `ScoringService` becomes the `ort_*` grading function. `test_scoring` numbers must be reproduced exactly (including the current raw-0 → 0 quirk, unless we decide to fix it).
- **Document order** = `quiz_items.position` (plus `questions.position` inside the imported bank). The bundle and CSV import create one bank per source and one quiz with items in source order. `source_ref` uniqueness becomes **per owner** (this fixes the global `external_id` collision).
- **math_1 rule** moves from the question to the section: `quiz_sections.rules = {"allowed_types": ["comparison"]}` for `key = math_1`, and `{"forbid_types": ["comparison"]}` for the other ORT sections. It is enforced at import, at item add, and at publish. The existing math-rule tests carry over to that validator.
- **Reading passages**: `passage_text` becomes `passages`, and its questions reference `passage_id`. A passage `quiz_item` renders above its questions, with `[N]` line markers unchanged.
- **PIN**: the product decision is enrollment instead of PINs, so drop it. If kept, store a hash, never serialize it, and rate-limit attempts.
- **Admin preview**: `attempts.is_preview`, excluded from kept score and analytics (same as today).

---

## 4. Skip, and why
- **Copying questions between banks and quizzes, and the `independently_edited` / `generated` states**: version ids make all of that unnecessary.
- **Attempts as versions of one row, and snapshot tables every 5 saves**: per-item rows already provide durability.
- **The 5-option regrade engine**: instead, offer one teacher action, "apply answer-key change to attempts of version N", which re-runs `score()` on the stored responses.
- **Partitioned event log**: add a plain append-only `attempt_events` table only if proctoring or timing analytics are requested.
- **Bank sharing / bookmarks, account-level banks, MasterCourses restrictions, outcomes alignment**: the product decided no sharing and no accounts for now.
- **IP filters, lockdown browser, anonymous submissions, surveys**: no use case yet.
- **`equation_images` and MathMan, file-link translation with verifiers**: KaTeX plus content-addressed `assets` with signed URLs is simpler and fixes the ephemeral-disk problem.
- **The `show_correct_answers_at` / `hide_at` date matrix**: a three-value `results_policy` is enough.
- **New Quizzes-style LTI separation**: we are a single app.

---

## 5. Risks and open questions
1. **One question with an i18n map vs. separate questions per language.** The map assumes the translations are equivalent, so they share one answer key and one statistics row. Is that true for teacher content? ORT ky and ru will stay separate items either way.
2. **Score policy for ORT**: should it be first attempt, highest, or latest? It drives the dashboard "current score".
3. **Grace windows**: the client clock is only for display. Agree a grace period (30–60 s) and an auto-submit UX for each section boundary.
4. **Pick groups vs. fixed order vs. passages**: v1 should allow picks only in sections without passages.
5. **JSON `data` drift**: carry `schema_version` and keep the Pydantic models as the only writers. Add migrations per type when shapes change.
6. **Editing a published quiz**: confirm the rule "attempts keep their version; changes reach new attempts only after republish; regrade is explicit".
7. **Storage and privacy**: assets need an owner, and access checks on read (minors). Signed URLs should be short-lived.
8. **[unverified]** New Quizzes internals (stimulus draw semantics, attempt storage) are not public. Any claim about them beyond the API docs is a guess.
