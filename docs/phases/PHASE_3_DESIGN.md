# Phase 3 design: assessments and attempts

**Status**: design for implementation, 2026-10-22 (architect). Builds on `phase-3/assessments` (Phases 0–2: `app/core/authz.py`, `app/lms/core/*`, `app/lms/courses/*`, `app/lms/content/*`, `app/lms/files/*`, Alembic `0003_phase2_content`).
**Sources**: `IMPLEMENTATION_PLAN.md` Phase 3 + §0 gates + non-functional targets + D8/D9/D11; `LMS_ARCHITECTURE.md` §5; `PRODUCT_DECISIONS.md` (Phase 1/2); `PHASE_2_DESIGN.md` §1–§3; `CAPACITY_REVIEW.md`; raw pre-Phase-3 DB load-test results in `loadtest/results/*.json` (`docs/LOAD_TEST_PRE_PHASE3.md` did not exist when this was written; if its numbers differ, §0 is the only section to update).
**Rule for implementers**: anything not stated here is out of scope. If a brief and this doc disagree, ask the orchestrator. Old code (`app/services/*`, `app/models/*`, old endpoints, old pages, `components/exam/*`) is **frozen**: read it, import it read-only, never edit it.

---

## 0. Load-test findings and what they decide

Measured on a Neon branch (free, 0.25–2 CU, Frankfurt) from a remote load generator whose round trip (RTT) to Neon is ≈ 225 ms.

| Measurement | Result | Reading |
|---|---|---|
| Autosave: single conditional `UPDATE … WHERE EXISTS(join)` autocommit, open loop 100–500/s, 60 s | 0 errors; p50 226 ms, p95 311–321 ms at 200–500/s | Server time per statement ≈ 1–5 ms; **500/s sustained on free compute**. Join predicate costs nothing measurable vs PK-only (`pk_only` p50 227 ms). |
| Same UPDATE with ORM-style explicit transaction (BEGIN, UPDATE, COMMIT) | p50 696 ms = 3 RTT | **Round trips are the currency**, not SQL CPU. |
| Start: attempt + 150 items as one CTE statement | 421 starts/s at 200 conns (6,000 in ≈ 14 s) | Fits the 5-minute burst 20× over. |
| Start: separate statements (≈ 4 RTT) | 157 starts/s at 200 conns (6,000 in ≈ 38 s) | Also fits; multi-statement start is acceptable when API and DB are co-located. |
| Submit: one-shot UPDATE + grade + write, 50 conns | 41/s, p50 1.17 s (≈ 5 RTT) | RTT-bound; same-region it becomes CPU-bound in the API. |
| Reading a 150 KB quiz payload from the DB per request | 6–13/s remote, 340–705/s server-side | **Never rebuild the payload per request**: in-process cache. |
| Simultaneous pooled connections | 800 opened, 0 errors | Neon pooler (PgBouncer) is not the limit; use the pooled URL. |
| `attempt_items` storage | 2.13 M rows = 195 MB (lean bench table) | Real rows are wider: plan ≈ 120–170 B/row, **≈ 110–150 MB per 6,000 × 150 exam** (§2.9). |

Decisions derived (referenced below as L1–L6):
- **L1** Every hot request has a fixed statement budget: autosave = 1 auth query + N item UPDATEs (N ≤ 20, usually 1) + COMMIT; start ≤ 9 statements with items as one multi-row INSERT; submit ≤ 7 statements; state read ≤ 4.
- **L2** Render (Frankfurt) and Neon (eu-central-1) are co-located (RTT ≈ 1–3 ms), so L1 budgets cost ≈ 5–25 ms of DB time per request; API CPU is the bottleneck (§8.3).
- **L3** Content is served from an immutable in-process cache keyed `(assessment_version_id, language, PAYLOAD_SCHEMA)` with pre-gzipped bytes.
- **L4** Client autosave may batch up to 20 answers per request (debounce 1.5 s); each answer is still a single-row conditional UPDATE.
- **L5** Pool per worker: `DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=10`, `DB_POOL_TIMEOUT=10`, pooled Neon URL; thread limiter = pool size + overflow (`LMS_THREADPOOL_TOKENS=20`) so threads never queue on the pool longer than a request.
- **L6** HTTP load tests must run API and DB co-located (local Postgres 18 + local API under CPU limits); remote-to-Neon runs only measure RTT (§8.1).

## 1. Decisions (defaults taken; record them in `PRODUCT_DECISIONS.md` at merge)

| # | Decision | Reason |
|---|---|---|
| P3-1 | Packages: `app/lms/assessments/` (builder, publish, snapshot, cache) and `app/lms/attempts/` (engine, autosave, grading, results, sweep). Tables use the architecture names. | Two owners, clean file ownership (§9). |
| P3-2 | Builder rows (`assessment_sections`, `assessment_items`) are the **draft** and are hard-deleted when removed; history lives only in immutable `assessment_versions`. Assessments themselves are soft-deleted. Attempts are never deleted (FK `RESTRICT`, no API). | Snapshots reference question/passage **version ids**, never builder rows. |
| P3-3 | Titles, descriptions, section titles and instructions are localized JSON (`LocalizedText`, like courses). | Same editor component as courses; three languages. |
| P3-4 | Item kinds: `question` (one bank question; resolved per language through its translation group at publish), `passage` (header row; its questions are child `question` rows with `parent_item_id`), `pick` (N random questions from a bank by filter; pool frozen at publish). | Architecture §5; passages stay together. |
| P3-5 | Multi-language: `assessments.languages ⊆ course.languages`. Publish requires every slot to resolve in **every** listed language (strict). ORT ky and ru exams are normally two single-language assessments (P2-14). Student picks the language at start (default `enrollment.content_language` if offered, else first). | D15; no half-translated exams. |
| P3-6 | Passage version pinned at publish for every resolved question that has a `passage_id`; a passage item's children must share one passage per language. | P2-11: passage link is mutable metadata; the snapshot freezes it. |
| P3-7 | Section rules JSON: `{allowed_types?: [type], max_items?: int, allow_passages?: bool}`. ORT presets fill them: `math_1` → `[comparison]`; `math_2, analogies, grammar` and subjects → `[single_choice]`; `reading` → `[single_choice]` + passages. Under `preset ∈ {ort_main, ort_subject}` the `allowed_types` of a keyed section cannot be changed (422 `preset_rule_locked`). Checked at item add **and** publish. | Ports the math_1 rule without hard-coding ORT for general courses. |
| P3-8 | ORT presets: `ort_main` creates 5 sections `math_1 45 min, math_2 45, analogies 30, reading 60, grammar 35` (old `DEFAULT_SECTIONS`), `navigation=section_forward_only`, `results_policy=after_submit`, `show_correct_answers=true`, `allowed_attempts=1`; `ort_subject` creates one section with a chosen subject key and 60 min. Teacher may edit times. | Same defaults as today's simulator. |
| P3-9 | **D9**: editing a published assessment edits the draft rows and bumps `draft_rev`; students keep getting `published_version_id`. Republish writes `version_no + 1` only if the new snapshot hash differs; new starts use it; in-flight attempts keep their version. If non-preview attempts exist on the current version, publish needs `confirm: true`, else 409 `confirm_required` with `details: {in_progress, submitted}` (the server-side "teacher warned"). | D9. |
| P3-10 | Snapshot = structure and scoring (sections, time limits, rules, slots with version ids and points, navigation, shuffle). **Live** (not versioned) settings: title/description, availability window, allowed attempts, results policy, show_correct_answers, score_policy. | Canvas behavior; teacher can extend a window or release results without a new version. |
| P3-11 | Unpublish blocks new starts and hides the assessment from students without attempts; **in-progress attempts continue** to their deadline; results stay visible per policy. Delete is refused while non-preview attempts are in progress (409 `attempts_in_progress`). | Integrity over control. |
| P3-12 | Navigation: `free` (all sections open, no section time limits allowed) or `section_forward_only` (one current section; closing it is final). | ORT is forward-only. |
| P3-13 | Deadlines: `deadline_at = min(started_at + total_limit + extra_time_s, available_until)`; `total_limit = time_limit_s` if set, else the sum of section limits if all sections are timed, else none. Section k: `deadline = min(start_k + limit_k, attempt.deadline_at)`; untimed section → attempt deadline. NULL = no limit. | Architecture §5; sweepable. |
| P3-14 | **Grace D8 = 45 s** (`ATTEMPT_GRACE_S`). Writes are accepted while `now ≤ deadline + grace` for both the attempt and the item's section. Finalize-on-expiry happens after `deadline + grace`. | D8. |
| P3-15 | Section transitions: client closes the section at its timer zero (`close_reason=timeout`) or by button (`manual`); server **lazily** closes a section only after `deadline + grace`, and the next section then starts at the previous section's `deadline_at` (time kept running while away). If the attempt deadline passed too, finalize. | Strict exam timing, no work lost inside grace. |
| P3-16 | Server clock only: all time comparisons use `clock.now()` (UTC, app side, injectable in tests) passed as SQL parameters (portable SQLite/PG). Every attempt response carries `server_now`. | Testable timeouts; client offset. |
| P3-17 | One in-progress attempt per (assessment, user): two partial unique indexes, one for non-preview, one for preview. `attempt_no` is NULL for previews; `UNIQUE(assessment_id, user_id, attempt_no)`. Concurrent starts: the loser gets IntegrityError, rolls back and returns the winner's attempt (200 resume). Limit: `count(non-void, non-preview) < allowed_attempts` (−1 = unlimited) evaluated in SQL inside the start transaction; next number = `max(attempt_no)+1`. | Limit holds under concurrency without locks. |
| P3-18 | Staff never create real attempts: `start` by teacher/assistant always creates a **preview** (`is_preview=true`). Preview of a draft uses a preview snapshot (`assessment_versions.kind='preview'`, `version_no NULL`, reused while its hash matches). Starting a new preview voids the user's in-progress preview of that assessment. Previews are excluded from limits, lists (default), stats and grade hooks. | "Preview as student" works before publishing. |
| P3-19 | Shuffle: `shuffle_items` permutes top-level blocks within each section (a passage block moves as one, children keep order). Choice shuffle for `single_choice`/`multiple_answers` when `assessment.shuffle_choices OR data.shuffle`; `comparison`/`true_false` never. Permutations stored per item (`choice_order`, list of choice ids; NULL when not shuffled). RNG `secrets.SystemRandom()`. Responses carry choice **ids**, so scoring ignores permutations. | Architecture §5. |
| P3-20 | Autosave is `PUT /attempts/{id}/answers` with ≤ 20 entries `{position, response?, flagged?, client_ts}`; each entry is one conditional single-row UPDATE (§3.6); out-of-order replays are ignored via `client_ts` (ms, monotonic per device; equal value = idempotent retry). Response validation against the item type happens in the same transaction; any invalid entry → rollback whole request, 422 `invalid_response` with positions. | Tab races and offline replays never overwrite newer answers. |
| P3-21 | One-shot submit: `UPDATE attempts SET status='submitted' … WHERE id AND status='in_progress' RETURNING`; the winner locks the item rows, grades and writes all item results in the **same** transaction; losers return the stored outcome (`already_submitted: true`). If grading raises, the whole transaction rolls back and the attempt stays `in_progress` (answers safe; client retries; sweep retries). | Exactly one grader, no half-graded attempts. |
| P3-22 | Grading door: grading sets `correctness` on **every** item (`unanswered` for blanks, `pending` for essays). Autosave requires `correctness IS NULL` on the item row itself, so Postgres re-checks it after waiting on the grader's row lock (EvalPlanQual). | Closes the submit-vs-autosave race; a join-only check would not (§3.8). |
| P3-23 | Statuses: `in_progress → graded | needs_review → graded`; `void` (previews replaced; teacher void is Phase 4). `submitted` is the transient value set by the one-shot UPDATE inside the grading transaction and never committed on its own. `submit_reason ∈ manual|timeout|sweep|closed` (`closed` = course concluded/unpublished-for-student or enrollment ended, found lazily). | Architecture §5 + robust grading. |
| P3-24 | Results policy (live): `never` (student sees "submitted" only), `after_submit`, `after_close` (requires `available_until`; visible when `now ≥ available_until`). `show_correct_answers` adds `key_view` + explanation to the review when results are visible. Staff always see everything. | Plan. |
| P3-25 | Scores: per item `score` (auto) and `manual_score` (override); effective = `coalesce(manual_score, score)`. Attempt keeps `raw_score`, `points_possible` and `result = {sections:[{pos,key,raw,possible,answered,correct}], pending_review:int}`. No scaling in Phase 3. Hook `ATTEMPT_SCORED_HOOKS` (list of callables `(db, attempt) -> None`, called inside the grading/manual-score transaction for non-preview attempts) is where Phase 4 attaches submissions/gradebook. | Phase 4 owns schemes (D11 lives in `score_policy`, stored now, used then). |
| P3-26 | Sweep without workers (Render Free): (a) lazy finalize on **every** access (student routes, start, teacher lists); (b) opportunistic sweep: each process, at most every `ATTEMPT_SWEEP_INTERVAL_S=60`, after the response (`BackgroundTasks`), on its own 1-connection engine, guarded on PG by `pg_try_advisory_xact_lock(3_000_001)`, finalizes ≤ `ATTEMPT_SWEEP_BATCH=100` expired attempts; (c) `POST /api/v1/internal/attempts/sweep` with header `X-Sweep-Token` (`ATTEMPT_SWEEP_TOKEN`, route returns 404 when empty) for an optional free external cron (GitHub Actions, every 15 min). | Render Free sleeps; when it sleeps, nobody is taking an exam; (b) runs as soon as anyone comes back. |
| P3-27 | Authentication on LMS routes uses **one** session: `get_lms_user` decodes the JWT itself (same rules as `security.get_current_user`, incl. test mock tokens) and loads the user through the request session. Today it calls `get_current_user`, which opens a second `SessionLocal()` (two pool checkouts per request). | Phase 1/2 lesson "one connection per request"; halves pool pressure (L5). |
| P3-28 | Rate limits: start `attempt_start_10m` 20/user/10 min and manual scoring `grade_item_1h` 600/user/h are DB-backed (`ratelimit.enforce`, before any session write). Autosave uses an in-process per-(worker,user) token bucket (30 requests / 30 s, LRU 20k users) → 429 `rate_limited` + `Retry-After`; a DB hit per autosave would double its cost. | Lesson "rate limits DB-backed" applied where correctness across workers matters. |
| P3-29 | Caps (settings): items per assessment ≤ 500, sections ≤ 20, pick pool ≤ 1,000 per language, pick count ≤ 200, autosave body ≤ 256 KiB, payload cache 48 MiB per process (32 MiB recommended on Free), points per item 0–1000. | Bounded memory on 512 MB. |
| P3-30 | Error shape: all new routes use `{"error":{code,message,details}}`; `LMS_PATH_PREFIXES` gains `/api/v1/attempts` and `/api/v1/internal`. Every miss on attempts (other user's, missing, wrong course) is the same 404 `attempt_not_found`. | No existence oracles. |

## 2. Schema and migration

Conventions as Phases 1–2: SQLAlchemy 2.0 `Mapped`, `UUIDPKMixin`, `TimestampMixin`, `SoftDeleteMixin`, `JSONType`, `Numeric(8,2)` points; user FKs `String(64)`; constraint names are short suffixes; partial indexes carry both `postgresql_where=` and `sqlite_where=`; booleans in predicates: PG `NOT is_preview` / SQLite `is_preview = 0`. Models: `app/lms/assessments/models.py` (2.1–2.4), `app/lms/attempts/models.py` (2.5–2.7); `app/lms/models.py` imports both.

### 2.1 `assessments`
`id`, `course_id` FK courses RESTRICT not null, `created_by_id` FK users SET NULL null, `title JSONType` not null, `description JSONType` null, `preset String(16)` CHECK `IN ('none','ort_main','ort_subject')` default `none`, `languages JSONType` not null, `status String(12)` CHECK `IN ('draft','published')` default `draft`, `published_version_id` FK assessment_versions (**use_alter**, `fk_assessments_published_version_id`) null, `last_version_no Integer` not null default 0, `draft_rev Integer` not null default 1, `published_draft_rev Integer` null, `time_limit_s Integer` null CHECK `NULL OR 60..86400`, `allowed_attempts Integer` not null default 1 CHECK `= -1 OR 1..100`, `score_policy String(8)` CHECK `IN ('highest','latest','first','average')` default `highest`, `shuffle_items Boolean` default false, `shuffle_choices Boolean` default false, `navigation String(24)` CHECK `IN ('free','section_forward_only')`, `results_policy String(16)` CHECK `IN ('never','after_submit','after_close')`, `show_correct_answers Boolean` default false, `available_from`/`available_until DateTime(tz)` null CHECK `until > from`, `position Integer` not null (course list order), `published_at` null, timestamps, soft delete (`deleted_by_id` FK users SET NULL).
Indexes: `(course_id, deleted_at, position, id)`; `(course_id, status)`.

### 2.2 `assessment_sections`
`id`, `assessment_id` FK assessments RESTRICT not null, `position Integer` not null, `key String(40)` null (ORT code or free label), `title JSONType` null, `instructions JSONType` null, `time_limit_s Integer` null CHECK `NULL OR 60..86400`, `rules JSONType` not null default `{}`, timestamps.
`UNIQUE(assessment_id, position)` is **not** used (renumbering would conflict mid-statement); index `(assessment_id, position)`; service renumbers 1..n in one transaction.

### 2.3 `assessment_items`
`id`, `assessment_id` FK RESTRICT not null, `section_id` FK assessment_sections RESTRICT not null, `parent_item_id` FK assessment_items RESTRICT null (child of a passage item), `position Integer` not null (within section for top-level; within parent for children), `kind String(8)` CHECK `IN ('question','passage','pick')`, `question_id` FK bank_questions RESTRICT null, `passage_id` FK passages RESTRICT null, `points Numeric(8,2)` null (NULL for passage headers) CHECK `NULL OR 0..1000`, `pick_bank_id` FK question_banks RESTRICT null, `pick_count Integer` null CHECK `NULL OR 1..200`, `pick_filter JSONType` null (`{section?, topic?, difficulty?, type?, tags?: [≤5]}`), timestamps.
CHECKs: `kind='question'` ⇒ `question_id IS NOT NULL`; `kind='passage'` ⇒ `passage_id IS NOT NULL AND parent_item_id IS NULL`; `kind='pick'` ⇒ `pick_bank_id, pick_count NOT NULL AND parent_item_id IS NULL`.
Indexes: `(assessment_id, section_id, position)`; `(parent_item_id)`; partial unique `(assessment_id, question_id) WHERE question_id IS NOT NULL` (`uq_assessment_items_question`: a question appears once per assessment).

### 2.4 `assessment_versions` (immutable)
`id`, `assessment_id` FK RESTRICT not null, `kind String(10)` CHECK `IN ('published','preview')`, `version_no Integer` null (NULL for preview), `snapshot JSONType` not null, `content_hash String(64)` not null, `draft_rev Integer` not null, `item_count Integer` not null, `points_possible Numeric(10,2)` not null, `created_at`, `created_by_id` FK users SET NULL null.
`UNIQUE(assessment_id, version_no)` (NULLs distinct); index `(assessment_id, kind, created_at)`. ORM `before_update`/`before_delete` listeners raise (as `question_versions`).
**Snapshot JSON** (ids, not blobs; Decimal as strings; `schema` bumps on format change):
```json
{"schema": 1, "languages": ["ru"], "navigation": "section_forward_only", "time_limit_s": null,
 "shuffle_items": false, "shuffle_choices": false, "item_count": 150, "points_possible": "150.00",
 "sections": [{"pos": 1, "key": "math_1", "title": {"ru": "…"}, "instructions": null, "time_limit_s": 2700,
               "rules": {"allowed_types": ["comparison"]}}],
 "slots": {"ru": [
   {"slot": 1, "section_pos": 1, "item_id": "…", "kind": "question", "qv": "<question_version_id>", "pv": null, "points": "1.00", "block": 1},
   {"slot": 91, "section_pos": 4, "item_id": "…", "kind": "question", "qv": "…", "pv": "<passage_version_id>", "points": "1.00", "block": 64},
   {"slot": 7, "section_pos": 2, "item_id": "…", "kind": "pick", "count": 5, "points": "1.00", "block": 7,
    "pool": [{"qv": "…", "pv": null}]}]}}
```
`block` groups slots that shuffle together (a passage block shares one value). `item_count`/`points_possible` count a pick slot as `count` items. Every language has the same slot list shape (same sections, kinds, counts, points). `content_hash` = sha256 of canonical JSON of the snapshot.

### 2.5 `attempts`
`id`, `assessment_id` FK RESTRICT, `assessment_version_id` FK assessment_versions RESTRICT, `course_id` FK courses RESTRICT, `enrollment_id` FK enrollments RESTRICT, `user_id` FK users RESTRICT, `attempt_no Integer` null, `language String(2)` CHECK, `is_preview Boolean` not null default false, `status String(16)` CHECK `IN ('in_progress','submitted','needs_review','graded','void')`, `started_at` not null, `deadline_at` null, `extra_time_s Integer` not null default 0, `current_section_pos SmallInteger` not null default 1, `item_count Integer` not null, `submitted_at` null, `submit_reason String(8)` null CHECK `IN ('manual','timeout','sweep','closed')`, `raw_score Numeric(10,2)` null, `points_possible Numeric(10,2)` not null, `result JSONType` null, `graded_at` null, timestamps.
Indexes: partial unique `(assessment_id, user_id) WHERE status='in_progress' AND NOT is_preview` (`uq_attempts_open`); partial unique same columns `WHERE status='in_progress' AND is_preview` (`uq_attempts_open_preview`); `UNIQUE(assessment_id, user_id, attempt_no)` (`uq_attempts_number`); `(assessment_id, is_preview, status, submitted_at)`; `(user_id, created_at)`; partial `(deadline_at) WHERE status='in_progress'` (`ix_attempts_open_deadline`, sweep).

### 2.6 `attempt_sections`
PK `(attempt_id, section_pos)`; `attempt_id` FK attempts RESTRICT; `section_pos SmallInteger`; `started_at` null; `deadline_at` null; `closed_at` null; `close_reason String(8)` null CHECK `IN ('manual','timeout','submit')`.

### 2.7 `attempt_items`
PK `(attempt_id, position)` (composite: one index, narrow rows; autosave addresses items by position); `attempt_id` FK RESTRICT; `position SmallInteger` (1..n display order after shuffle); `section_pos SmallInteger`; `slot SmallInteger` (snapshot slot); `question_version_id` FK question_versions RESTRICT; `choice_order JSONType` null; `response JSONType` null; `flagged Boolean` default false; `client_ts BigInteger` null; `answered_at` null; `correctness String(10)` null CHECK `NULL OR IN ('correct','incorrect','partial','unanswered','pending')`; `score Numeric(8,2)` null; `manual_score Numeric(8,2)` null; `feedback Text` null; `graded_by_id` FK users SET NULL null; `graded_at` null.
Points and passage versions are **not** stored per row: they come from the cached snapshot by `slot` (pick slots carry `pv` in the pool). No secondary index (per-question stats in Phase 8 add one). PG only, in the migration: `ALTER TABLE attempt_items SET (fillfactor = 85)` so autosave updates stay HOT.

### 2.8 Alembic `0004_phase3_assessments` (down_revision `0003_phase2_content`)
Upgrade: create `assessments` (without the version FK), `assessment_sections`, `assessment_items`, `assessment_versions`, then `batch_alter_table("assessments")` → `create_foreign_key("fk_assessments_published_version_id", …)`; then `attempts`, `attempt_sections`, `attempt_items`; PG-only fillfactor. Downgrade: reverse, FK first. `alembic check` clean on PG. `tests/lms/conftest.py` cleanup (prepend, FK-safe): delete `attempt_items, attempt_sections, attempts`, `UPDATE assessments SET published_version_id=NULL`, delete `assessment_versions, assessment_items` (children first: `parent_item_id IS NOT NULL` then rest), `assessment_sections, assessments`; reset the payload/grading caches and the autosave bucket.

### 2.9 Size budget
`attempt_items` ≈ 120–170 B/row incl. PK entry and fillfactor → **≈ 110–150 MB per 6,000 students × 150 items**; `attempts` + `attempt_sections` ≈ 2 MB per exam; snapshot ≈ 25 KB per language per version. Neon free (0.5 GB, shared with content and blobs) holds two or three national-size exams; real use needs Neon Launch (§8.3). Phase 9 candidate: archive graded attempts older than N months into one JSON per attempt.

## 3. Services

Conventions as Phase 2: services take `db` + `AuthzContext`, own the transaction, raise `LMSError` before commit. Bulk reads chunked by 500. Hot paths use SQLAlchemy **Core** statements, not ORM unit-of-work (CPU, L2).

### 3.1 Core additions (`app/lms/core/`)
```python
# clock.py
def now() -> datetime                      # UTC aware; tests monkeypatch app.lms.core.clock.now
# deps.py (P3-27) – replaces the body of get_lms_user; same signature for all existing routes
def get_lms_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User
    # missing/invalid header -> UnauthorizedException (401, as today); mock tokens only when security._mock_tokens_allowed()
    # jwt.decode(SECRET_KEY, ALGORITHM) -> sub -> db.get(User, sub); None or disabled -> 401. No SessionLocal().
```

### 3.2 Builder (`app/lms/assessments/builder.py`, `rules.py`)
```python
def create_assessment(db, ctx, course, data: AssessmentCreateIn) -> Assessment     # applies preset (P3-8); position = max+1
def update_assessment(db, ctx, course, aid, data: AssessmentUpdateIn) -> Assessment # requires data.draft_rev == row.draft_rev else 409 draft_conflict
def soft_delete_assessment / restore_assessment(...)                               # P3-11
def add_section / update_section / delete_section(...)   # delete only if empty (409 section_not_empty)
def reorder_sections(db, ctx, course, aid, section_ids: list[UUID])                 # must be exactly the current set -> 422 order_mismatch
def add_item(db, ctx, course, aid, section_id, data: ItemCreateIn) -> list[AssessmentItem]
def add_items_bulk(db, ctx, course, aid, section_id, data: BulkAddIn) -> BulkAddOut  # question_ids[≤500] or {bank_id, filter}; group_passages=True
def update_item(db, ctx, course, aid, item_id, data: ItemUpdateIn)                   # points, pick fields, section_id (move block to another section, appended)
def delete_item(...)                                                                 # passage header deletes its children
def reorder_items(db, ctx, course, aid, section_id, item_ids)                        # top-level ids of that section; children: parent_item_id variant
def check_item_rules(section, assessment, qtype, language) -> list[Issue]            # pure; used by add and publish
# repository.py (shared with the attempts package; signature fixed)
def load_assessment(db, course_id, aid, *, for_update=False, published_only=False, include_deleted=False) -> Assessment  # 404 assessment_not_found
```
Every mutating call: `load_course` → `require(CONTENT_MANAGE)` → `load_assessment(db, course.id, aid, for_update=True)` (404 `assessment_not_found` when another course/deleted) → change → `draft_rev += 1` → commit. Add-time validation: question live, its bank live and in this course (404 `question_not_found` otherwise — anti-IDOR through `content.repository.load_question(db, course.id, qid)`), type allowed by section rules (422 `item_type_not_allowed`), language ∈ assessment languages or has a group member in one (422 `item_language_mismatch`), not already present (409 `item_duplicate`), passage children: same passage (422 `passage_mismatch`), caps (422 `too_many_items`). Bulk add with `group_passages` turns consecutive questions sharing a `passage_id` into one passage block. Returned `warnings` (not errors): missing translations, newer question versions than published.

### 3.3 Publish and snapshot (`app/lms/assessments/publish.py`, `snapshot.py`)
```python
def build_snapshot(db, assessment, *, now) -> tuple[dict, list[Issue]]   # pure over loaded rows; no writes
def validate(db, ctx, course, aid) -> ValidationOut                      # dry run: {errors, warnings}
def publish(db, ctx, course, aid, *, confirm: bool) -> PublishOut         # {assessment, version, unchanged}
def unpublish(db, ctx, course, aid) -> Assessment
def ensure_preview_version(db, ctx, course, aid) -> AssessmentVersion     # P3-18
```
Resolution (≤ 6 queries for 500 items): load sections + items; load `bank_questions` by id (IN); load translation-group members for the target languages (IN on `translation_group_id`, live only); load pick pools (`question_list_stmt`-style filter per pick, live, `LIMIT PICK_POOL_MAX+1`); load passages' `current_version_id` (IN). For language L, a question item resolves to the question itself if `language == L`, else to the live member of its group in L. Errors (422 `publish_invalid`, `details=[{code, section_pos, item_id, language}]`): `no_sections`, `empty_section`, `unresolved_language`, `question_deleted`, `type_not_allowed`, `passage_mismatch`, `pick_pool_too_small`, `section_limit_in_free_navigation`, `section_limits_exceed_total`, `after_close_needs_until`, `too_many_items`, `languages_not_in_course`. Publish transaction: lock course? **No**; lock the assessment row (`FOR UPDATE`) → build → if `content_hash` equals the current published version's → `unchanged: true` (still sets `status=published`) → else if non-preview attempts exist on the current version and not `confirm` → 409 `confirm_required` → insert version (`version_no = last_version_no + 1`), set `published_version_id`, `status`, `published_draft_rev = draft_rev`, `published_at` → commit. Publishing requires the course not concluded (CONTENT_MANAGE gate); course draft is allowed (students see nothing until the course is published).

### 3.4 Caches (`app/lms/assessments/cache.py`)
```python
PAYLOAD_SCHEMA = 1
@dataclass(frozen=True)
class VersionPlan:            # everything the engine needs, built once per version per process
    version_id: UUID; snapshot: dict; languages: tuple[str, ...]
    slots: dict[str, list[dict]]                 # per language, snapshot order
    qmeta: dict[UUID, tuple[str, dict, Decimal]] # qv_id -> (type, data incl. key, default_points)  [server-side only]
def get_plan(db, version_id) -> VersionPlan                   # LRU 64 entries; per-key build lock (no stampede)
def get_student_payload(db, version_id, lang) -> CachedPayload  # (etag, raw_bytes, gzip_bytes); LRU by bytes ASSESSMENT_CACHE_BYTES
def question_fragment(db, plan, qv_id) -> dict                # student_question() for pick items (not in the shared payload)
def qtype(db, qv_id) -> str                                   # LRU 50k ids -> type, for autosave response validation (immutable)
```
Shared student payload per `(version, lang)`: `{"version_id", "language", "sections": [{pos,key,title,instructions,time_limit_s,item_count}], "questions": {qv_id: student_question(v)}, "passages": {pv_id: student_passage(pv)}, "image_urls": [...]}` built **only** from `content.repository.student_question/student_passage` (no keys, no explanation), for fixed slots only; ETag `"{version_id}.{lang}.{PAYLOAD_SCHEMA}"`; gzip level 6 once. Keys are immutable, so there is no invalidation. Memory: 150-question payload ≈ 150 KB raw + 30 KB gzip; plan ≈ 0.5 MB; caps keep the total < 64 MB per process.

### 3.5 Attempt engine: start, state, timing (`app/lms/attempts/engine.py`, `timing.py`)
```python
def start_attempt(db, ctx, course, aid, data: StartIn, *, now) -> tuple[AttemptState, bool]  # (state, created)
def get_state(db, user, attempt_id, *, now) -> AttemptState
def close_section(db, user, attempt_id, pos, *, now) -> AttemptState
def load_own_attempt(db, user, attempt_id, *, for_update=False) -> Attempt   # WHERE id AND user_id -> else 404 attempt_not_found
def apply_lazy(db, attempt, sections, plan, *, now) -> LazyResult             # pure decision + Core updates: section advances, finalize
# timing.py (pure, unit-tested)
def attempt_deadline(started_at, snapshot, extra_s, available_until) -> datetime | None   # P3-13
def section_deadline(start, limit_s, attempt_deadline) -> datetime | None
def advance(sections, attempt, now, grace) -> list[Transition]                             # P3-15
```
**Start** (statement budget L1; `require(ASSESSMENT_TAKE)` first):
1. `load_course` (404) → `require_course(ctx, ASSESSMENT_TAKE, course)`; staff → preview path (P3-18); `ratelimit.enforce(user, ATTEMPT_START_10M)` before any write.
2. Load assessment by `(course.id, aid)` live; students also need `status='published'` (else 404 `assessment_not_found`).
3. Existing in-progress attempt for (assessment, user, is_preview) → `apply_lazy`; still open → return it (200, `created=false`; language argument ignored).
4. Window: `available_from ≤ now < available_until` else 409 `assessment_not_available` (`details.reason ∈ not_open_yet|closed`).
5. One query: `SELECT max(attempt_no), count(*) FILTER-equivalent (SUM(CASE WHEN status <> 'void' THEN 1 ELSE 0 END)) … WHERE assessment_id, user_id, NOT is_preview` → limit check → 409 `attempts_exhausted`.
6. `plan = get_plan(version)`; language ∈ plan.languages else 422 `language_not_available`.
7. Build rows in Python: expand pick slots (sample `count` from the pool), order blocks (shuffle per section if set), number positions 1..n, choice permutations; compute deadlines; section 1 started now (forward-only) or all sections started (free).
8. `INSERT attempts … RETURNING id` (Core); `INSERT attempt_sections` (one multi-row statement); `INSERT attempt_items` (one multi-row statement; SQLAlchemy insertmanyvalues batches ≤ 1000 rows per statement); commit. IntegrityError on `uq_attempts_open*`/`uq_attempts_number` → rollback → re-select the open attempt → return it (200) or, if none, 409 `attempts_exhausted`.
**State** (`AttemptState`, also the start response): `{id, assessment_id, version_id, status, language, is_preview, server_now, grace_s, started_at, deadline_at, current_section_pos, navigation, sections:[{pos, started_at, deadline_at, closed_at}], items:[{position, section_pos, qv, pv, points, choice_order, response, flagged}], content_url, content_etag, extra_questions:{qv: fragment} (pick items only), results_available}`. Reads: attempt (owned) → sections + items (2 queries) → `apply_lazy` (writes + commit only if something changed) → plan from cache. ≈ 18–25 KB JSON for 150 items.
**Lazy rules** (`apply_lazy`, under `SELECT … FOR UPDATE` of the attempt row when it must write): non-preview attempt and (course not `published` or enrollment not active or assessment deleted) → finalize `closed`; attempt deadline + grace passed → finalize `timeout`; forward-only current section deadline + grace passed → close it (`timeout`), start next at the old `deadline_at`, repeat; last section closed → finalize `timeout`.

### 3.6 Autosave (`app/lms/attempts/autosave.py`)
```python
def save_answers(db, user, attempt_id, entries: list[AnswerIn], *, now) -> SaveOut
    # SaveOut{saved:[pos], stale:[pos], server_now, status, current_section_pos}; whole-request errors raise
```
Fast path, per entry, one statement (Core; `SET` lists only the fields present; `cutoff = now - grace`):
```sql
UPDATE attempt_items AS ai SET response = :resp, flagged = :flag, client_ts = :ts, answered_at = :now
WHERE ai.attempt_id = :aid AND ai.position = :pos AND ai.correctness IS NULL
  AND (ai.client_ts IS NULL OR ai.client_ts <= :ts)
  AND EXISTS (SELECT 1 FROM attempts a
      JOIN attempt_sections s ON s.attempt_id = a.id AND s.section_pos = ai.section_pos
      JOIN enrollments e ON e.id = a.enrollment_id
      JOIN courses c ON c.id = a.course_id
      JOIN assessments x ON x.id = a.assessment_id
    WHERE a.id = :aid AND a.user_id = :uid AND a.status = 'in_progress'
      AND (a.deadline_at IS NULL OR a.deadline_at >= :cutoff)
      AND s.started_at IS NOT NULL AND s.closed_at IS NULL
      AND (s.deadline_at IS NULL OR s.deadline_at >= :cutoff)
      AND e.state = 'active' AND c.deleted_at IS NULL AND x.deleted_at IS NULL
      AND ((a.is_preview AND e.role IN ('teacher','assistant') AND c.status IN ('draft','published'))
        OR (NOT a.is_preview AND e.role = 'student' AND c.status = 'published')))
RETURNING ai.position, ai.question_version_id
```
Then: validate each returned `(qv, response)` with `get_type(cache.qtype(qv)).Response(**response)` (strict; `null` response = clear) → any failure → rollback → 422 `invalid_response` (`details.positions`); commit. Slow path only when some entry updated 0 rows: one classification query (attempt owned? status, deadlines, item exists, section state, `client_ts` newer) → `stale` entries are reported (not an error); otherwise `apply_lazy` (commit) and retry those entries **once** (covers lazy section advance); still failing → 404 `attempt_not_found` (not owned / no enrollment), 409 `attempt_closed` (status/deadline), 409 `section_closed`, 422 `item_not_found`. Before the DB: Content-Length > 256 KiB → 413; > 20 entries → 422; in-process bucket (P3-28). Budget: auth SELECT + N UPDATEs + COMMIT.

### 3.7 Section close and submit (`engine.py`, `app/lms/attempts/grading.py`)
```python
def close_section(...)    # SELECT attempt FOR UPDATE (owned, in_progress) -> pos must == current_section_pos and not last (409 section_not_current / use_submit)
                          # UPDATE attempt_sections SET closed_at, close_reason WHERE … AND closed_at IS NULL; start next (started_at=now, deadline);
                          # UPDATE attempts SET current_section_pos = pos+1 WHERE current_section_pos = pos; commit. Re-close of an already closed pos -> 200 current state.
def submit(db, user, attempt_id, data: SubmitIn, *, now) -> SubmitOut
def finalize(db, attempt_id, *, reason, now) -> FinalizeOutcome   # shared by submit, lazy expiry, sweep; caller commits
def grade_items(plan, lang, rows) -> GradeOutcome                 # pure: ScoreResult per item via REGISTRY, section totals
def write_item_results(db, attempt_id, results)                   # PG: one UPDATE … FROM (VALUES …) per 500 rows; SQLite: executemany
def manual_score(db, ctx, course, attempt_id, position, data: ScoreIn) -> AttemptStaffOut
ATTEMPT_SCORED_HOOKS: list[Callable[[Session, Attempt], None]]    # app/lms/attempts/hooks.py; empty in Phase 3
```
**Submit**: apply `data.answers` (≤ 20) through `save_answers` logic inside the same transaction (rejected ones reported, not fatal) → `finalize(reason = manual if now ≤ deadline+grace else timeout)`:
1. `UPDATE attempts SET status='submitted', submitted_at=:now, submit_reason=:r WHERE id=:aid AND status='in_progress' RETURNING …` → no row → loser: return stored outcome (`already_submitted: true`, 200).
2. `SELECT position, slot, question_version_id, response FROM attempt_items WHERE attempt_id=:aid ORDER BY position FOR UPDATE` (waits for in-flight autosaves; reads their committed values).
3. `grade_items` from `get_plan` (no DB): per item `score()`; blank → `unanswered`, 0; essay non-blank → `pending`, score NULL; `partial` when 0 < points < max.
4. `write_item_results` (sets `correctness` on all rows → closes the door, P3-22); sections: `UPDATE attempt_sections SET closed_at=:now, close_reason='submit' WHERE closed_at IS NULL`.
5. `UPDATE attempts SET status = needs_review|graded, raw_score, result, graded_at`; run hooks (non-preview); commit.
Statement budget: 2 (answers) + 1 + 1 + 1 + 1 + 1 + commit. Response `SubmitOut{status, submitted_at, results_available, result?}` (result only when visible, §3.9).
**Manual score** (`GRADES_MANAGE`): course → require → attempt by `(course.id, attempt_id)` `FOR UPDATE` (404) → status ∈ (`needs_review`,`graded`) else 409 `attempt_not_submitted` → `0 ≤ points ≤ slot points` (422) → set `manual_score, feedback, graded_by_id, graded_at` → recompute `raw_score`, `result`, status (`graded` when no `pending` item lacks `manual_score`) → hooks → commit.

### 3.8 Lock order and race analysis (binding)
Order: `courses → assessments → (assessment_sections, assessment_items) → assessment_versions(insert)`; `attempts → attempt_sections → attempt_items`. Builder never touches attempt tables; the engine never locks course/assessment/content rows (reads only). Autosave locks only its item row and reads `attempts` without a lock, so it never waits on an attempt lock while holding an item lock → no cycle. Close/lazy/submit/manual-score take the attempt row first.
Races: (a) two submits → step 1 serializes; the loser's re-check finds `status <> 'in_progress'`. (b) autosave committed before step 2 → graded. (c) autosave blocked on an item row locked in step 2/4 → after commit PG re-evaluates the target row's quals: `correctness IS NULL` is false → 0 rows → `attempt_closed`; the `EXISTS` join alone would **not** be re-evaluated against new snapshots, which is why P3-22 puts the guard on the item row. (d) autosave vs close section: a save already in flight may land just after a manual close (answer given before the click; accepted, documented). (e) concurrent starts → unique indexes (P3-17). (f) two tabs → per-item rows + `client_ts` ordering; a closed section in tab A makes tab B's next save return `section_closed`, B reloads state. (g) publish vs start → start reads `published_version_id` once; either version is valid.
SQLite (tests, dev) serializes writers; races are proven only on PG (§7.9).

### 3.9 Results and serializers (`app/lms/attempts/results.py`, `serializers.py`)
```python
def results_visible(assessment, attempt, now, *, staff: bool) -> bool   # P3-24; previews visible to their staff owner
def result_out(attempt, plan) -> AttemptResultOut                       # {raw_score, points_possible, sections, pending_review, submitted_at}
def review_out(attempt, items, plan, payload, *, with_keys: bool) -> ReviewOut
    # per item: position, section_pos, question (student_question), passage?, response, flagged, correctness, score (effective), feedback,
    #           key? = type.key_view(data) and explanation? only when with_keys
```
`serializers.py` is the **only** module that turns attempt/plan data into student JSON; every student response model is built there and covered by the contract tests (§7.3). Staff variants (`AttemptStaffOut`) live in the same module with explicit names.

### 3.10 Sweep (`app/lms/attempts/sweep.py`)
```python
def maybe_schedule_sweep(background: BackgroundTasks) -> None   # per-process monotonic timer, ATTEMPT_SWEEP_INTERVAL_S
def run_sweep(limit: int = settings.ATTEMPT_SWEEP_BATCH) -> int # own engine (pool_size=1, max_overflow=0, like ratelimit._engine); PG advisory xact try-lock;
    # SELECT id FROM attempts WHERE status='in_progress' AND deadline_at < :cutoff ORDER BY deadline_at LIMIT :n
    # each: own transaction, finalize(reason='sweep') (one-shot, so concurrent lazy finalizers are harmless); errors logged, never raised
```
Called from student attempt routes and start (after the request committed; the request session holds no connection then). Teacher attempt lists call `finalize_expired_for(assessment_id, limit=200)` synchronously before listing.

## 4. Authorization

- No new actions. Mapping: builder reads `CONTENT_READ_ADMIN`, builder writes/publish/preview `CONTENT_MANAGE`; student list/lobby `CONTENT_READ`; start `ASSESSMENT_TAKE` (students only real attempts; staff → preview); own attempt reads `ATTEMPT_READ_OWN`; teacher attempt views `ATTEMPT_READ_ALL`; manual scoring `GRADES_MANAGE`. Status gates come from `decide()`: draft course → staff only; concluded → read-only (no starts, no autosave via the predicate, results readable); deleted → 404.
- Pattern: authenticate (dependency) → `load_course` → `require_course` → child loaders scoped by `course.id` (`load_assessment(db, course_id, aid)`, `load_course_attempt(db, course_id, attempt_id)`). Never load the child first.
- `/attempts/{id}/*` (student): `load_own_attempt` (`WHERE id AND user_id = me`) → 404 for anything else → then `load_course(attempt.course_id)` + `require(ATTEMPT_READ_OWN)` (reads) or the autosave predicate (writes). Course deleted/removed enrollment → same 404.
- `GET /courses/{c}/assessments` and `/{a}` choose the serializer by role (`ctx.role_for`): staff → `*StaffOut`, student → `*StudentOut`; students never see drafts, unpublished assessments without own attempts, or deleted ones (404).
- Platform admins: no bypass. Route inventory: new policy names `attempt_owner`, `internal_token`; merge `ASSESSMENT_POLICIES`, `ATTEMPT_POLICIES`, `ATTEMPT_STAFF_POLICIES`, `INTERNAL_POLICIES`. Strings: `course:content.read`, `course:content.read_admin`, `course:content.manage`, `course:assessment.take+ratelimit`, `course:attempt.read_own`, `course:attempt.read_all`, `course:grades.manage+ratelimit`, `attempt_owner`, `internal_token`.

## 5. API (all under `/api/v1`; LMS error shape; snake_case; `{c}` course, `{a}` assessment, `{s}` section, `{i}` item, `{t}` attempt)

Builder — `app/lms/assessments/router.py`:

| method | path | in → out | policy | errors |
|---|---|---|---|---|
| GET | `/courses/{c}/assessments?cursor&limit&deleted` | staff: `PageOut[AssessmentStaffSummaryOut{id,title,preset,status,languages,item_count,points_possible,has_unpublished_changes,current_version_no,attempt_counts{in_progress,submitted},available_from,available_until,deleted_at}]`; student: `PageOut[AssessmentStudentSummaryOut{id,title,languages,time_limit_s,item_count,available_from,available_until,allowed_attempts,attempts_used,in_progress_attempt_id,last_result?{raw_score,points_possible}}]` | course:content.read | course_not_found |
| POST | `/courses/{c}/assessments` | `AssessmentCreateIn{title, description?, preset, languages, subject_key? (ort_subject)}` → `AssessmentStaffOut` 201 | course:content.manage | validation_failed, languages_not_in_course |
| GET | `/courses/{c}/assessments/{a}` | staff: `AssessmentStaffOut{…summary, settings, draft_rev, sections:[{id,position,key,title,instructions,time_limit_s,rules,items:[ItemOut{id,kind,position,points,question?{id,type,language,stem_excerpt,deleted,newer_version_available},passage?{id,title},children?,pick?{bank_id,count,filter,pool_size{lang:n}}}]}], warnings}`; student: `AssessmentLobbyOut{id,title,description,languages,sections:[{pos,key,title,time_limit_s,item_count}],time_limit_s,navigation,allowed_attempts,attempts_used,available_from,available_until,in_progress_attempt_id,can_start,reason?}` | course:content.read | assessment_not_found |
| PATCH | `/courses/{c}/assessments/{a}` | `AssessmentUpdateIn{draft_rev, title?, description?, languages?, time_limit_s?, allowed_attempts?, score_policy?, shuffle_items?, shuffle_choices?, navigation?, results_policy?, show_correct_answers?, available_from?, available_until?}` → `AssessmentStaffOut` | course:content.manage | draft_conflict, validation_failed |
| DELETE / POST | `/courses/{c}/assessments/{a}` / `…/restore` | → 204 / `AssessmentStaffOut` | course:content.manage | attempts_in_progress, not_deleted |
| POST | `/courses/{c}/assessments/{a}/sections` | `{title?, key?, instructions?, time_limit_s?, rules?}` → `SectionOut` 201 | course:content.manage | too_many_sections, preset_rule_locked |
| PATCH / DELETE | `/courses/{c}/assessments/{a}/sections/{s}` | same fields → `SectionOut` / 204 | course:content.manage | section_not_found, section_not_empty |
| PUT | `/courses/{c}/assessments/{a}/sections/order` | `{section_ids}` → `AssessmentStaffOut` | course:content.manage | order_mismatch |
| POST | `/courses/{c}/assessments/{a}/sections/{s}/items` | `ItemCreateIn{kind, question_id? , passage_id?, question_ids? (passage children), points?, pick?{bank_id,count,filter}}` → `[ItemOut]` 201 | course:content.manage | question_not_found, item_type_not_allowed, item_language_mismatch, item_duplicate, passage_mismatch, too_many_items |
| POST | `/courses/{c}/assessments/{a}/sections/{s}/items/bulk` | `BulkAddIn{question_ids? ≤500 \| {bank_id, filter}, points?, group_passages=true}` → `BulkAddOut{added, skipped:[{question_id, code}]}` | course:content.manage | bank_not_found, too_many_items |
| PATCH / DELETE | `/courses/{c}/assessments/{a}/items/{i}` | `{points?, section_id?, pick?}` → `ItemOut` / 204 | course:content.manage | item_not_found |
| PUT | `/courses/{c}/assessments/{a}/sections/{s}/items/order` | `{item_ids, parent_item_id?}` → `SectionOut` | course:content.manage | order_mismatch |
| POST | `/courses/{c}/assessments/{a}/validate` | → `{errors:[Issue], warnings:[Issue]}` | course:content.read_admin | — |
| POST | `/courses/{c}/assessments/{a}/publish` | `{confirm=false}` → `PublishOut{assessment, version{id,version_no,item_count,points_possible,created_at}, unchanged}` | course:content.manage | publish_invalid, confirm_required |
| POST | `/courses/{c}/assessments/{a}/unpublish` | → `AssessmentStaffOut` | course:content.manage | not_published |
| GET | `/courses/{c}/assessments/{a}/versions` | → `PageOut[VersionOut{id,version_no,item_count,points_possible,created_at,created_by_name,attempt_counts}]` | course:content.read_admin | — |
| POST | `/courses/{c}/assessments/{a}/preview` | `{language?}` → `AttemptStateOut` 201 | course:content.manage | publish_invalid (preview snapshot invalid) |

Attempts (student) — `app/lms/attempts/router.py`:

| method | path | in → out | policy | errors |
|---|---|---|---|---|
| POST | `/courses/{c}/assessments/{a}/attempts` | `StartIn{language?}` → `AttemptStateOut` 201 (new) / 200 (resume) | course:assessment.take+ratelimit | assessment_not_found, assessment_not_available, attempts_exhausted, language_not_available, rate_limited |
| GET | `/courses/{c}/assessments/{a}/attempts/mine` | → `[MyAttemptOut{id,attempt_no,status,started_at,submitted_at,results_available,result?}]` | course:attempt.read_own | assessment_not_found |
| GET | `/attempts/{t}` | → `AttemptStateOut` | attempt_owner | attempt_not_found |
| GET | `/attempts/{t}/content` | → shared payload (pre-gzipped when accepted), `ETag`, `Cache-Control: private, max-age=86400, immutable`, 304 on `If-None-Match` | attempt_owner | attempt_not_found |
| PUT | `/attempts/{t}/answers` | `{answers:[AnswerIn{position, response?: object\|null, flagged?: bool, client_ts: int}] ≤20}` → `SaveOut` | attempt_owner | attempt_not_found, attempt_closed, section_closed, item_not_found, invalid_response, payload_too_large (413), rate_limited |
| POST | `/attempts/{t}/sections/{pos}/close` | → `AttemptStateOut` | attempt_owner | section_not_current, use_submit, attempt_closed |
| POST | `/attempts/{t}/submit` | `SubmitIn{answers?: [AnswerIn] ≤20}` → `SubmitOut` | attempt_owner | attempt_not_found |
| GET | `/attempts/{t}/result` | → `AttemptResultOut` | attempt_owner | results_not_available (403) |
| GET | `/attempts/{t}/review` | → `ReviewOut` (keys only with `show_correct_answers`) | attempt_owner | results_not_available (403) |

Attempts (staff) — `app/lms/attempts/staff_router.py`; internal — `app/lms/attempts/internal_router.py`:

| method | path | in → out | policy | errors |
|---|---|---|---|---|
| GET | `/courses/{c}/assessments/{a}/attempts?status&preview=false&cursor&limit` | → `PageOut[AttemptStaffSummaryOut{id,user_id,student_name,attempt_no,status,language,started_at,submitted_at,submit_reason,raw_score,points_possible,pending_review}]` (finalizes expired first) | course:attempt.read_all | assessment_not_found |
| GET | `/courses/{c}/attempts/{t}` | → `AttemptStaffOut` (review with keys, responses, scores, feedback) | course:attempt.read_all | attempt_not_found |
| PUT | `/courses/{c}/attempts/{t}/items/{pos}/score` | `ScoreIn{points, feedback? ≤5000}` → `AttemptStaffOut` | course:grades.manage+ratelimit | attempt_not_submitted, points_out_of_range |
| POST | `/internal/attempts/sweep` | header `X-Sweep-Token` → `{finalized}` | internal_token | not_found (token unset/wrong) |

New `lms.errors.*` codes: `assessment_not_found, section_not_found, item_not_found, attempt_not_found, draft_conflict, languages_not_in_course, too_many_sections, too_many_items, section_not_empty, order_mismatch, preset_rule_locked, item_type_not_allowed, item_language_mismatch, item_duplicate, passage_mismatch, publish_invalid, confirm_required, not_published, attempts_in_progress, assessment_not_available, attempts_exhausted, language_not_available, attempt_closed, section_closed, section_not_current, use_submit, invalid_response, payload_too_large, results_not_available, attempt_not_submitted, points_out_of_range` + issue codes of §3.3 under `assessments.issues.*`.

## 6. Frontend

Routes (inside the Phase 1 course layout; client components; server decides; trilingual):

| path | content |
|---|---|
| `courses/[courseId]/assessments/page.tsx` | staff: list (status/version badges, "unpublished changes", attempt counts), create dialog (title, preset ORT main / ORT subject / blank, languages); student: available assessments with window, attempts used, Resume/Start/Results |
| `courses/[courseId]/assessments/[assessmentId]/page.tsx` | staff: overview (settings summary, versions, attempts link, Edit, Preview); student: **lobby** (rules, sections + times, language select, attempts left, availability reason, Start/Resume, image preloading from `image_urls`) |
| `courses/[courseId]/assessments/[assessmentId]/edit/page.tsx` | builder: section list (add/edit/delete, time limit, rules, drag-reorder + up/down buttons), items per section (drag-reorder, points inline, passage blocks collapsible, pick editor with live pool size), "Add questions" dialog (bank picker on `listQuestions` filters, multi-select, "add all filtered" → bulk), settings panel, validate panel (issues mapped by code), Publish/Unpublish with the `confirm_required` dialog ("N students are taking version k; they keep it"), Preview button |
| `courses/[courseId]/assessments/[assessmentId]/attempts/page.tsx` | staff attempt list (filters, pending-review badge) |
| `courses/[courseId]/assessments/[assessmentId]/attempts/[attemptId]/page.tsx` | staff review + manual score/feedback per item (essays first) |
| `courses/[courseId]/attempts/[attemptId]/page.tsx` | **player** (full-screen, preview banner for staff) |
| `courses/[courseId]/attempts/[attemptId]/result/page.tsx` | result + review per policy ("results not available yet" / "submitted" states) |

Player (`components/lms/player/`), adapted from the old 1,778-line page by **copying its UX into small components** (the old page and `components/exam/*` stay untouched): `PlayerShell` (loads state + content, keyboard shortcuts from the old page, section header, progress bar), `DeadlineTimer` (remaining = `min(section.deadline_at, attempt.deadline_at) − (Date.now() + offset)`, recomputed each tick, never decremented; warnings at 5 min/1 min), `ItemView` (dispatch by type: `comparison` → `ComparisonQuestionCard`, `single_choice` → `QuestionCard` via an adapter mapping `choices` in `choice_order` to `options`; if their labels lack English or props do not fit, copy into `player/` — no edits to old files; new small renderers for `multiple_answers, true_false, numeric, short_text, essay`), `PassagePane` (`NumberedPassage`), `Palette` (adapter over `QuestionPalette`, current section only in forward-only mode), `SaveStatus` chip (Saved / Saving… / Offline – N pending / Error), `SectionEndDialog` (forward-only warning: "you cannot return"), `SubmitDialog` (unanswered and flagged counts), `TimeUpDialog`.
Client engine (`lib/lms/attemptClient.ts`): **server clock** offset from every response (`server_now` vs request midpoint; keep the lowest-RTT sample); **autosave queue** coalescing per position (latest `{response, flagged, client_ts}`), mirrored to `localStorage["lms_attempt_q_{attemptId}"]` (try/catch), flush after 1.5 s idle, at most every 5 s while dirty, immediately on section close/submit/`visibilitychange:hidden` (`fetch keepalive`), ≤ 20 entries per request; retry with backoff 1, 2, 4, 8, 16, 30 s ± 20 % jitter; `online` event flushes; 409 `attempt_closed`/`section_closed` → stop, reload state, show the dialog; 422 → drop the entries and show which questions failed; 401 → keep the queue, ask to sign in; `stale` entries are dropped silently. At section timer zero: flush, then `close` (server may already have advanced). At attempt zero: flush, then `submit` with all pending answers after a random 0–15 s delay (spreads the burst inside the 45 s grace). `BroadcastChannel` warns when the attempt is open in another tab.
Lib/types: `lib/lms/assessments.ts` + `assessmentTypes.ts` (builder + lobby), `lib/lms/attempts.ts` + `attemptTypes.ts` (player, results, staff attempts). `CourseTabs.tsx`: "Assessments" tab for everyone (`assessments.tab`).
i18n (en/ky/ru, parity): `assessments.*` (list, builder, settings, presets, publish, issues), `player.*`, `results.*`, `grading.*`, new `lms.errors.*`. Section names reuse existing `sections.*` labels; comparison labels reuse `bank.types.comparison.labels.*`.

## 7. Test plan

Location `backend/tests/lms/`, scratch DB per `AGENTS.md` 6.1, `clock.now` monkeypatched via fixture `frozen_clock` (advance by seconds). Factories (append): `make_assessment(db, course, actor, preset=…, items=…)`, `publish(db, …)`, `make_ort_quiz(db, course, actor, n_per_section=30)` (comparison math_1, single_choice others, one passage block in reading), `start(client, student, assessment)`.

1. **Timing unit** `test_attempt_timing.py`: table of (limits, available_until, extra, now) → deadlines; `advance()` for forward-only chains (multiple passed sections, start = previous deadline, last → finalize), free navigation, grace edges (deadline+45 s accepted, +46 s rejected).
2. **Builder/publish** `test_assessment_builder.py`, `test_assessment_publish.py`: preset creation; add rules (math_1 rejects single_choice; preset lock); duplicates; cross-course question id → 404; passage block grouping in bulk add; reorder exact-set check; `draft_conflict`; validate issue codes table-driven (one case per code); publish → version 1 snapshot exact shape; republish with no change → `unchanged`; edit then republish → version 2; question edited in bank → republish picks new version; translation resolution (ky+ru group; missing ky → `unresolved_language`); pick pool frozen (bank additions after publish not in pool); version rows immutable (ORM update/delete raise); `confirm_required` when attempts exist.
3. **Serializer contracts** `test_attempt_serializers.py`: seed every question type with sentinels in key-only fields (`correct`, `answers`, `margin`, `scoring`, `case_sensitive`, `rubric_note`, `explanation`); call **every** student-facing route (list, lobby, start, state, content, answers, close, submit, result, review, mine) across policies `never`, `after_submit`, `after_close` (before/after `available_until`) and `show_correct_answers` on/off; assert sentinels absent unless allowed; exact key sets per response model (explicit table in the test).
4. **Integrity suite** `test_attempt_integrity.py` (table-driven, SQLite; PG versions in 9): two submits (sequential + threaded) → exactly one grade (`graded_at` set once, hook called once); answer at deadline+44 s accepted, +46 s → 409 `attempt_closed`; answer in a closed section → 409 `section_closed`; answer in a future section → 409; tab race: two clients alternate saves on the same item with interleaved `client_ts` → final response = highest `client_ts`, older replays reported `stale`; different items from two tabs both kept; attempt limit (1 allowed: second start after submit → `attempts_exhausted`; start twice while open → same id, `created=false`); edits after publish don't change in-flight attempts (start → teacher edits + republishes → state/content/grading still use v1, new start gets v2); autosave after course concluded / enrollment removed → rejected and lazy finalize `closed`; student cannot read/write/submit another's attempt (404 on every `/attempts/{t}` route, identical body to a random uuid); staff routes cross-course → 404.
5. **Engine behavior** `test_attempt_engine.py`: shuffle permutations stored and stable across reloads; passage block contiguous after shuffle; pick sampling count and no duplicates; language choice + default from enrollment; preview: staff start → `is_preview`, not counted, new preview voids old, excluded from staff list by default; lazy expiry on GET; untimed attempt never expires; statement budget assertions with `before_cursor_execute` counters (autosave 1 entry ≤ 3 statements incl. auth; start ≤ 9; submit ≤ 8; state ≤ 5; content cache hit ≤ 2).
6. **Ported old behaviors** `test_attempt_ported.py` (from `tests/test_mock_test_service.py`): start and submit computes per-section raw scores (`test_start_and_submit_mock_test`); save, leave and resume keeps `in_progress`, answers and current section (`test_save_progress_keeps_in_progress_state_and_resumes`); only published, in-window assessments are listed to students (`test_exam_sets_available`). PIN/access-code tests do not apply (no PINs).
7. **Scoring/results** `test_attempt_grading.py`: every type through `grade_items` (correct, wrong, blank, malformed response → 0); essay → `needs_review`, manual score → `graded`, raw_score recomputed; manual override of an auto item; points range 422; results visibility per policy; review keys only with `show_correct_answers`; `write_item_results` equal results on SQLite and PG.
8. **Matrix/isolation** `test_assessment_matrix.py`, `test_attempt_isolation.py`: actors O, T, AS, S, R, X, P × course statuses over every new route (Phase 2 §7.5 pattern); TA/TB isolation for assessments, items, versions, attempts; student of CA cannot start CB's assessment (404).
9. **PG concurrency** `test_pg_concurrency_attempts.py` (`LMS_PG_TEST_DATABASE_URL`): 10 threads submit → 1 winner, 9 `already_submitted`; 10 threads start (allowed 1) → one attempt row; 10 threads start (allowed 2, one graded) → one new attempt no=2; autosave threads racing a submit → every save either graded or rejected, never saved-after-grade (assert no row with `answered_at > submitted_at` and `correctness` computed from an older response); 2 publishes concurrently → versions 1 and 2 or `unchanged`, never duplicate numbers; sweep from two processes → each attempt finalized once.
10. **Sweep/internal** `test_attempt_sweep.py`: expired attempts finalized `sweep`; batch limit; token unset → 404; wrong token → 404; once per interval per process.
11. **Cache/content** `test_assessment_cache.py`: payload built once per (version, lang) (query counter), ETag/304, gzip served once-encoded, cache byte cap evicts, pick fragments only in `extra_questions`.
12. **One connection per request** `test_single_checkout.py`: pool `checkout` event count = 1 for state, autosave, submit (rate-limited routes: plus the limiter's own engine).
13. **Migration** append to `tests/test_migrations.py`: `0003 → 0004 → 0003 → 0004`; `alembic check` clean. **Route inventory**: all routes listed with valid policies.
14. **E2E exit test** `test_phase3_flow.py` (plan exit criterion): teacher imports `tests/fixtures/bundles/tsoomo19.zip` through the Phase 2 import API → creates an `ort_main` assessment → bulk-adds each bank section into the matching section (`group_passages`) → validate (no errors) → publish (150 items, 150 points, v1). Student S1 (ru): lobby → start → content has no key sentinels → answers 10 math_1 items → clock passes math_1 deadline + grace (**timed out**) → `GET /attempts/{t}` (**resumed**: same id, same answers and `choice_order`, section 1 closed `timeout`, section 2 current, started at the old deadline) → answers in sections 2–5 using `close` between sections → `GET /review` = 403 `results_not_available` → **submit** → review shows `key` per item and per-section raw totals equal a hand-computed count. Student S2 starts and abandons; clock passes the whole deadline + grace; `run_sweep()` finalizes it `sweep` with the answers it had. Teacher list shows S1 `graded`, S2 `graded`, no preview rows.
Frontend: `tsc --noEmit`, isolated `next build`, i18n parity; scripted manual check (builder drag/publish/preview; player offline: devtools offline 30 s, answer, reconnect → queue flushes; timer offset with a skewed system clock; time-up auto-submit).

## 8. Load test (merge gate) and capacity

### 8.1 Plan (free resources, decision D)
- Tool: extend `loadtest/` (Locust could not be installed; reuse the asyncio `httpx` closed/open-loop runner of `http_load.py`): `loadtest/exam_seed.py` (one course, one published 150-item 5-section quiz, 6,000 students; tokens minted via `create_access_token`, no `.env`), `loadtest/exam_load.py` (scenario `exam`), `loadtest/exam_verify.py` (post-run DB checks).
- Environment (L6): local Postgres 18 (Docker) + API `uvicorn --workers 4` in Docker `--cpus=2 --memory=2g` (≈ Render Pro) and a second run at `--cpus=1 --memory=2g` (≈ Standard); load generator on the same machine but separate container/cores; one 500-VU smoke against a Neon branch only to confirm pooler behavior (RTT-bound; not a gate). Never production.
- Scenario per VU: ramp 6,000 starts over 300 s → `GET content` (ETag) → per question think time so that the fleet produces ≈ 300 answer changes/s at steady state, client batching as §6 → section closes on schedule (compressed: section limits 4–6 min, total ≈ 25 min) → at deadline submit with 0–15 s jitter; 2 % of VUs drop offline for 60 s and replay; 1 % open a second tab.
- Budgets (gate): error rate < 0.5 %; p95 autosave < 500 ms; p95 start < 2 s; p95 submit < 2 s; content p95 < 500 ms; **zero lost answers** (`exam_verify`: every acknowledged `(attempt, position, client_ts)` equals the stored row or a newer one); **zero double grading** (one `graded_at` per attempt, hook counter); no attempt left `in_progress` after deadline + grace + one sweep; API RSS per worker < 300 MB. Results table in `docs/phases/PHASE_3.md`.

### 8.2 Expected cost per hot request (to verify)
Autosave ≈ 3–5 ms API CPU, 3 statements; start ≈ 20–40 ms CPU (row building + 20 KB JSON), ≤ 9 statements; content hit ≈ 1 ms (cached gzip); submit ≈ 15–30 ms CPU (150 scores + JSON), ≤ 8 statements. Peak: 300 autosaves/s ≈ 1.2 CPU; start burst 20/s ≈ 0.6 CPU; submit burst: 6,000 submits spread by the 0–15 s client jitter ≈ 400/s × 20 ms ≈ 8 CPU-s per second, so on 4 CPU the queue drains in ≈ 30 s. Final answers in a submit body are judged at processing time, so queueing beyond deadline + 45 s would reject them (already-autosaved answers are always graded). Mitigations if the gate shows queueing > 25 s: client flushes the queue continuously in the last 60 s (submit body nearly empty), more CPU for the window, then post-commit grading (§10).

### 8.3 What the 6,000 target needs (cost notes; no purchases — owner decides)
| Component | Normal days | Exam window (6,000 concurrent) |
|---|---|---|
| Render API | Free works for development only (0.1 CPU, sleeps). Starter ($7/mo, unverified) for real courses. | **Pro (2 CPU, 4 GB) minimum, Pro Plus (4 CPU, 8 GB) recommended**, 4 workers, `LMS_THREADPOOL_TOKENS=20`, `DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=10`; billed per second (≈ $0.5–1 per 3-hour exam, unverified). Confirm with §8.1 at `--cpus=2` and `--cpus=4`. |
| Neon | Free (0.5 GB) fills after 2–3 national exams (§2.9). | Launch plan with autoscaling 1–4 CU; pooled URL; storage ≈ 0.15 GB per national exam. |
| Vercel | Hobby. | Set `NEXT_PUBLIC_API_URL` to Render (CAPACITY_REVIEW finding 2) before any national exam: 300 req/s through the Vercel rewrite is an unnecessary hop and quota risk. |
| Images | `db` driver + `/media` LRU. | R2 + domain (Phase 2 Q1/Q2) strongly preferred; lobby preloads `image_urls`. |

## 9. Slices

| slice | owns (only these files) | depends on | must pass |
|---|---|---|---|
| **A1 Schema + scaffolding** (Sonnet; architect reviews) | `app/lms/assessments/{__init__,models}.py`, `app/lms/attempts/{__init__,models}.py`, `app/lms/models.py`, `alembic/versions/0004_phase3_assessments.py`, `app/core/config.py` (all Phase 3 settings), `backend/.env.example` (names only), `app/lms/core/{clock,deps,errors}.py` (P3-27, P3-30), `app/lms/core/ratelimit.py` (two `Limit`s), `app/main.py` (thread limiter from `LMS_THREADPOOL_TOKENS` at startup), `app/core/route_inventory.py`, `app/api/v1/router.py`, stub routers and empty policy dicts: `assessments/{router,policies}.py`, `attempts/{router,policies,staff_router,staff_policies,internal_router}.py`, `tests/lms/{conftest,factories}.py`, `tests/test_migrations.py`, `tests/lms/test_phase3_constraints.py`, `tests/lms/test_single_checkout.py` | Phase 2 on branch | full suite SQLite; migration + `alembic check` on PG |
| **A2 Builder + publish + cache** (Sonnet; architect reviews publish) | `app/lms/assessments/{repository,rules,builder,snapshot,publish,cache,schemas,router,policies}.py`, tests 7.2, 7.8 (assessment part), 7.11 | A1 | its tests, route inventory, full suite |
| **A3 Attempt engine** (Sonnet; **architect reviews** engine + autosave SQL) | `app/lms/attempts/{timing,engine,autosave,sweep,router,internal_router,policies}.py`, `app/lms/attempts/schemas.py`, tests 7.1, 7.4, 7.5, 7.6, 7.9 (except grading parts), 7.10 | A1; A2 `get_plan`/`get_student_payload` (signatures fixed in §3.4; stub until A2 lands); A4 `finalize`/`grade_items` (stub returns ungraded) | its tests, full suite |
| **A4 Grading + results + staff** (Sonnet) | `app/lms/attempts/{grading,results,serializers,hooks,staff_router,staff_policies}.py`, tests 7.3, 7.7, 7.8 (attempt part), grading part of 7.9 | A1; A3 models/loaders; A2 plan | its tests, full suite |
| **F1 Builder UI** | `frontend/src/lib/lms/{assessments,assessmentTypes}.ts` (types committed first), `components/lms/assessments/**`, `app/[lang]/courses/[courseId]/assessments/**` except `[assessmentId]/attempts/**`, `components/lms/CourseTabs.tsx`, i18n `assessments.*` and all new `lms.errors.*` | this contract; live after A2 | `tsc`, isolated `next build`, i18n parity |
| **F2 Player + lobby client** | `frontend/src/lib/lms/{attempts,attemptTypes,attemptClient}.ts` (types first), `components/lms/player/**`, `app/[lang]/courses/[courseId]/attempts/[attemptId]/page.tsx`, i18n `player.*` | F1 types for lobby links; live after A3 | same + scripted offline/timer check |
| **F3 Results + staff grading UI** | `components/lms/results/**`, `app/[lang]/courses/[courseId]/attempts/[attemptId]/result/page.tsx`, `app/[lang]/courses/[courseId]/assessments/[assessmentId]/attempts/**`, i18n `results.*`, `grading.*` | F2 `attemptTypes.ts`; live after A4 | same |
| **Integration** (orchestrator + implementer) | `tests/lms/test_phase3_flow.py`, `loadtest/exam_{seed,load,verify}.py`, `docs/phases/PHASE_3.md`, `PRODUCT_DECISIONS.md` (P3 decisions), i18n merge | all | §0 gates, §8.1 gate, `/code-review`, `/security-review` (phase 3 is a security-review phase) |

Parallelism: A1 first (≈ half a day); then A2, A3, A4 in parallel against the fixed signatures (A3/A4 stub each other's functions; the orchestrator merges A2 → A4 → A3). F1/F2/F3 start at once against §5; the lobby (`[assessmentId]/page.tsx` student branch) belongs to F1 and links to F2's player route.

## 10. Risks and open questions

- **Submit burst CPU** (§8.2): if the gate fails at 4 CPU, widen the client jitter to the full grace first; then move grading to a post-commit step (status `submitted` committed alone, graded by the next access/sweep) — a design change requiring review of P3-21/P3-22.
- **Lazy-only expiry on Render Free**: attempts abandoned while the service sleeps stay `in_progress` until anyone hits it; harmless for students (deadline enforced on every write), visible to teachers only as stale rows, fixed on their next list.
- **Clock**: single trusted server clock; multi-instance Render scaling relies on NTP (milliseconds); grace absorbs it.
- **Storage** (§2.9): Neon free is not enough for repeated national exams; owner decision on Neon Launch before the first large exam.
- **Old components' languages**: `QuestionCard`/`ComparisonQuestionCard` take `{ky, ru}` text; if English labels are missing, F2 copies them into `player/` (old files frozen).
- **Playwright**: no Playwright suite exists; the plan's "compare old vs new player" becomes the scripted manual check in §7 plus the E2E API test; adding Playwright is a Phase 9 item.
- **Q1**: confirm the GZip middleware in Starlette 1.6 leaves pre-encoded responses alone (test 7.11 decides; otherwise exclude the content path).
- **Q2**: whether teachers need per-student extra time/attempts now (`extra_time_s` column exists; no API in Phase 3; Phase 4 or 6 adds overrides).
- **Deferred**: teacher void/regrade, per-student overrides, item statistics, question-level time tracking, lockdown/IP filters (skip list), Playwright suite, archival of old attempts.
