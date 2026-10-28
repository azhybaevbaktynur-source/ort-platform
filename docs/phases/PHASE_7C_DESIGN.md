# Phase 7c design: quiz editor (questions written inside the quiz, quiz banks, drafts, edit scope)

**Status**: architect draft 2026-10-28 (branch `phase-7c-design` off `origin/lms` at 860810f). Implements `PHASE_7C_PROPOSAL.md` and the binding owner decisions **7c-1 … 7c-9** (`PRODUCT_DECISIONS.md`, 2026-10-28). Names in **bold code** are to be used exactly as written so parallel slices merge cleanly. Every file and line below was checked against `lms` at 860810f. Anything that could change ORT behaviour is in §13 (answer: nothing does).

---

## 1. Scope and non-goals

**In**: `question_banks.assessment_id` (quiz banks, 7c-1, 7c-3); table **`question_drafts`** (per-card server drafts, 7c-4); quiz bank created on first use and soft-deleted/restored with its quiz; create question + version + item in one transaction; draft autosave with optimistic `draft_rev`; "Done" = one `question_versions` row with edit scope `all | this` (7c-2) and the type-change rule (7c-5); usage count per question; move/copy a question to a shared bank; Bank tab "Quiz banks" group; the card-based quiz editor for non-preset assessments (template exams included, with their locks); hidden default section (7c-6, no schema); bank "New question" without the pre-menu for general courses (7c-9); i18n en/ky/ru.

**Out**: new question types (7c-7, Phase 10); "paste questions as text" (later, 7b format); type change inside the Bank-tab editor (stays locked there; the card is the place for it); any ORT screen or flow (7c-8, §13); org-shared banks (Phase 9; §6.3 names the hook).

---

## 2. Schema and migration **`0011_phase7c_quiz_editor`**

`down_revision = "0010_phase7b_exam_templates"`. Naming via `op.f(...)`, `JSONType = sa.JSON().with_variant(JSONB, "postgresql")`, SQLite through `op.batch_alter_table`, as in 0010. **No data steps**: every new column is nullable, the new table starts empty, so SQLite `create_all` needs no bootstrap and every existing row (all ORT and general content) keeps its meaning.

### 2.1 `question_banks` (content/models.py, block `# --- Phase 7c S1 ---`)

| Column / constraint | Definition |
|---|---|
| `assessment_id` | uuid NULL FK `assessments.id` ON DELETE RESTRICT, named `fk_question_banks_assessment_id_assessments`. NULL = shared bank (every existing row). NOT NULL = the quiz bank of that assessment. |
| `ix_question_banks_assessment_id` | index on `assessment_id` |
| **`uq_question_banks_assessment_live`** | partial UNIQUE (`assessment_id`) WHERE `assessment_id IS NOT NULL AND deleted_at IS NULL` (`postgresql_where` + `sqlite_where`, like `uq_question_banks_course_source`): one live quiz bank per assessment |
| CHECK `quiz_bank_has_course` | `assessment_id IS NULL OR course_id IS NOT NULL` |
| CHECK `quiz_bank_no_source` | `assessment_id IS NULL OR source_id IS NULL` (an importer bank is never a quiz bank; the ORT importer keeps creating `source_id` banks exactly as today) |

The 6a `bank_org_listener` (`organizations/defaults.py`) runs unchanged: a quiz bank copies its course's organization.

### 2.2 `question_drafts` (new; model **`QuestionDraft`** in `app/lms/quiz_editor/models.py`)

| Column | Definition |
|---|---|
| `id` | uuid PK |
| `assessment_id` | uuid NOT NULL FK assessments RESTRICT |
| `section_id` | uuid NOT NULL FK assessment_sections RESTRICT (where the card sits) |
| `item_id` | uuid NULL FK assessment_items RESTRICT. NOT NULL = draft of an existing card; NULL = **new card not yet committed** |
| `after_item_id` | uuid NULL FK assessment_items ON DELETE SET NULL. Position hint of a new card (NULL = end of section). Ignored when `item_id` is set |
| `base_version_id` | uuid NULL FK question_versions RESTRICT. The question version the draft started from (existing cards); NULL for new cards |
| `payload` | JSON NOT NULL: **`CardPayload`** = `{type, language, stem, data, explanation, default_points, image_asset_id, points, meta: {topic, difficulty, section, tags, passage_id}}` (the card's whole form; validated at commit, only size-checked at autosave) |
| `draft_rev` | int NOT NULL default 1 (same convention as `assessments.draft_rev`) |
| `created_by_id`, `updated_by_id` | varchar(64) NULL FK users SET NULL |
| `created_at`, `updated_at` | timestamptz (`TimestampMixin`) |
| **`uq_question_drafts_item`** | partial UNIQUE (`item_id`) WHERE `item_id IS NOT NULL`: one draft per card, shared by every tab and teacher (conflicts surface through `draft_rev`) |
| `ix_question_drafts_assessment_section` | (`assessment_id`, `section_id`) |
| CHECK `draft_payload_size` | none in SQL; the service caps the JSON at 256 KiB (413 `payload_too_large`) |

**Why a separate table, not columns on `assessment_items` or "draft items" with `question_id NULL`**: the builder, `build_snapshot`, `draft_totals`, `_caps`, `_tree_out` and the ORT parity fixtures all read `assessment_items`; a draft row there would need a `question_kind_valid` CHECK change and a skip in every consumer. `question_drafts` is read by the quiz editor only; snapshots, attempts and the ORT builder cannot see it by construction.

**Lifecycle hooks (S2)**: `builder.delete_item` / `delete_section` delete the drafts of the removed items first (RESTRICT would otherwise block); `soft_delete_assessment` leaves drafts in place (restorable with the quiz). No cascade FKs, as everywhere in the schema.

### 2.3 Default section (7c-6): no column

A general quiz (`preset = 'none'`) with exactly one section whose `key`, `title`, `time_limit_s` are NULL and `rules = {}` is shown without a section header. **`quiz_editor/service.py::ensure_default_section(db, a)`** creates that section lazily on the first card/draft/find-add when the quiz has none (`position = 1`, `rules = {}`); `create_assessment` is not changed (existing tests expect `sections == []` after create, and ORT/template creation already writes explicit sections). When the teacher adds a second section the first one is rendered as "Section 1" by the existing `sectionName()` fallback (`assessments.section.n`). Template exams (`exam_template_version_id` set) always show their headers.

### 2.4 Downgrade

Drop `question_drafts`; drop the two CHECKs, the index, the partial unique and `assessment_id` (batch on SQLite). Lossless when no quiz bank exists; refused with a clear error when any `question_banks.assessment_id IS NOT NULL` (quiz-bank questions would silently become shared). `tests/test_migration_0011.py`: up/down/up on SQLite and PG; an existing ORT importer bank keeps `assessment_id IS NULL`; `alembic check` clean.

---

## 3. Module layout **`app/lms/quiz_editor/`** (new) and touched modules

| File | Content (slice) |
|---|---|
| `models.py` | `QuestionDraft` (S1); registered in `app/lms/models.py` block `# --- Phase 7c S1 ---` |
| `ids.py` | error codes (§5.7), issue code **`unfinished_drafts`**, `DRAFT_PAYLOAD_MAX = 262_144`, policy names (none new: all routes use `course:*`) (S1) |
| `schemas.py` | `CardPayloadIn/Out`, `DraftCreateIn`, `DraftUpdateIn`, `DraftOut`, `CommitIn`, `CommitOut`, `QuizQuestionCreateIn`, `QuestionUsageOut`, `CopyToBankIn` (S1 shapes, S2 fills validators) |
| `quiz_banks.py` | `ensure_quiz_bank(db, ctx, course, a) -> QuestionBank`, `is_quiz_bank(bank)`, `soft_delete_with_quiz`, `restore_with_quiz` (S2) |
| `drafts.py` | create / update / delete / list drafts (S2) |
| `commit.py` | `commit_draft(...)`, `create_question_in_quiz(...)`, scope resolution, type-change rule (S2) |
| `usage.py` | `question_usage(db, course, q) -> QuestionUsageOut`, `published_pins(db, assessments, q)` (S2) |
| `bank_ops.py` | `copy_or_move_to_bank(...)` (S2) |
| `router.py`, `policies.py` | quiz routes under `/courses/{course_id}/assessments/{assessment_id}/...` and the two question routes (S2; `policies.py` stub by S1, imported by `route_inventory.py` in a `# --- Phase 7c S1 ---` block) |

Touched existing files (delimited blocks): `content/models.py` (2.1), `content/schemas.py::BankOut` (+ `assessment: {id, title} | None`), `content/repository.py::bank_rows_stmt` (outer join `assessments` for the title), `content/service.py` (`soft_delete_bank`/`restore_bank` refuse quiz banks: 409 **`quiz_bank_follows_quiz`**), `assessments/builder.py` (`soft_delete_assessment`/`restore_assessment` call `quiz_banks.*_with_quiz`; `delete_item`/`delete_section` remove drafts; `_tree_out` sets `ItemOut.has_draft`; `staff_out(db, a, *, include_drafts)`), `assessments/publish.py::validate` (+ `unfinished_drafts` warnings), `assessments/schemas.py` (`ItemOut.has_draft: bool = False`, `AssessmentStaffOut.drafts: list[DraftOut] = []`, `ItemQuestionOut.bank_kind: "quiz" | "shared"`, `ItemQuestionOut.used_elsewhere: int`), `api/v1/router.py` (mount).

---

## 4. Invariants

1. **One store (7c-1)**: a question written in a quiz is a `bank_questions` row whose bank has `assessment_id = that quiz`. No copy table. Items reference `question_id` exactly as today.
2. **Versions stay immutable and are created only by Done/commit** (7c-4). Autosave writes `question_drafts.payload` only. `test_drafts_never_version`: 50 autosaves → `count(question_versions)` unchanged.
3. **Snapshots and attempts never read drafts or quiz-bank-ness**: `build_snapshot` pins `current_version_id`s as before; `attempt_items.question_version_id` is untouched by any 7c write. Edits reach students only through republish (the scope dialog says so).
4. **Scope `this` never touches the source question**; **scope `all` never touches items**. Both run under the assessment row lock in one transaction.
5. **A quiz bank is never shared** (Phase 9 `visibility` applies to `assessment_id IS NULL` banks only; `test_quiz_bank_not_shareable` is written now against a `visibility` attribute guard in `quiz_banks.is_quiz_bank` so Phase 9 cannot forget it).
6. **ORT**: no ORT code path reaches `quiz_editor/*` (§13).

---

## 5. Services

### 5.1 Quiz bank (`quiz_banks.py`)

`ensure_quiz_bank(db, ctx, course, a)`: `SELECT ... WHERE assessment_id = a.id AND deleted_at IS NULL`; if none, insert `QuestionBank(owner_id=ctx.user.id, course_id=course.id, assessment_id=a.id, title=core.types.localized(a.title, course.default_language)[:200] or "Quiz", default_language=course.default_language)`. Always called while the caller holds `load_assessment(for_update=True)` (the builder's `_manage`), which serializes first use on PG; `uq_question_banks_assessment_live` is the backstop (a violation can only mean a caller outside the lock: it surfaces as a 500 in tests, never as a second bank; PG test §7 proves one bank). `soft_delete_with_quiz(db, a, actor_id)` / `restore_with_quiz(db, a)` flip `deleted_at` of the quiz's bank (at most one exists per quiz, live or deleted, because creation only happens on a live quiz without one). Direct `DELETE /banks/{id}` and `POST /banks/{id}/restore` on a quiz bank → 409 `quiz_bank_follows_quiz`; `PATCH` of `title` on a quiz bank → 409 `quiz_bank_follows_quiz` too (the Bank tab shows the quiz title from the join; the stored title is a fallback written at creation), `description` and `default_language` stay editable (Q3).

### 5.2 Drafts (`drafts.py`; all under `_manage` → `course:content.manage`, assessment row lock)

- `create_draft(ctx, course, aid, data: DraftCreateIn{item_id?, section_id?, after_item_id?, payload})`: exactly one mode. **Existing card** (`item_id`): item must be `kind = question` and belong to the quiz (404 `item_not_found`); if a draft exists → 409 **`draft_exists`** with `details = DraftOut` (the client loads it); `base_version_id = question.current_version_id`. **New card**: `section_id` or default section (§2.3); `after_item_id` must be a top-level item of that section or NULL. Payload size ≤ `DRAFT_PAYLOAD_MAX`, `type ∈ TYPE_NAMES`, `language ∈ a.languages` (422); content is **not** validated (half-typed cards are the point). Returns `DraftOut{id, item_id, section_id, after_item_id, base_version_id, payload, draft_rev, updated_at, updated_by_name}`.
- `update_draft(ctx, course, aid, draft_id, data: DraftUpdateIn{draft_rev, payload})`: `UPDATE question_drafts SET payload, draft_rev = draft_rev + 1, updated_by_id, updated_at WHERE id = :id AND assessment_id = :aid AND draft_rev = :rev`; rowcount 0 → re-select: missing → 404 `draft_not_found`; else 409 **`draft_conflict`** `details = {draft_rev, payload, updated_by_name}` (the other tab's state, so the client can show "take theirs"). Single-statement optimistic update: no read-modify-write between tabs. The assessment `draft_rev` is **not** bumped by autosave (drafts are not quiz structure; `has_unpublished_changes` must not flicker while typing).
- `delete_draft(ctx, course, aid, draft_id)`: discard (204; idempotent 204 when already gone).
- Drafts are listed inside `AssessmentStaffOut.drafts` when the caller has `course:content.read_admin` (`staff_out(..., include_drafts=True)` from the router); org admins reading a course (`ORG_ADMIN_ACTIONS` has `CONTENT_READ` only) get `drafts = []` and `has_draft = false`: a draft is unreviewed teacher text, like bank content, which org admins cannot read either (A13 keeps them read-only on course content).

### 5.3 Create a question in the quiz (`commit.py::create_question_in_quiz`; one transaction, no commit inside)

Signature: `create_question_in_quiz(db, ctx, course, a, *, section, after_item_id, payload: CardPayload) -> tuple[AssessmentItem, BankQuestion]`. Steps: `_check_language` (language ∈ course languages **and** ∈ `a.languages`, else 422 `item_language_mismatch`); `check_item_rules(section, a, payload.type, payload.language)` → 422 `item_type_not_allowed` (section rules, including template rules written by `instantiate`); `allow_passages`/passage: `payload.meta.passage_id` must be a passage of the quiz bank (new cards cannot join a shared-bank passage; 422 `passage_not_in_quiz_bank`); `_caps(db, a, section, 1)`; `prepare_content` + `normalize_question_content` (validate before any write, as `content/service.py::create_question` does); `bank = ensure_quiz_bank(...)` (`_lock_bank`); `BankQuestion(bank_id, type, language, meta..., position=_next_position)`; `new_question_version(origin="create")` with `default_points = payload.points`; item: `AssessmentItem(kind="question", question_id, points=payload.points, section_id, position)` where position = `after_item.position + 1` and the following top-level items are shifted (`_renumber`), or `_next_pos` when `after_item_id` is NULL; `_flush_unique`. The public endpoint wraps it with `_manage` + `_commit` (bumps the assessment `draft_rev`). Structure locks do not apply (items and points are in the 6a editable list).

### 5.4 Commit a draft ("Done"; `commit.py::commit_draft(ctx, course, aid, draft_id, data: CommitIn{draft_rev, scope?})`)

1. `_manage` (lock), load draft (404), `draft.draft_rev == data.draft_rev` else 409 `draft_conflict` (an autosave landed after the client's last known rev; the client flushes autosaves before Done and retries once with the returned rev).
2. Validate payload fully (`prepare_content` → `normalize_question_content`; 422 `invalid_question_data` with `details[].loc`, the card renders them inline; **the draft stays**).
3. **New card** (`item_id IS NULL`): `create_question_in_quiz` with `draft.section_id`, `draft.after_item_id`; delete the draft; `scope` ignored. → `CommitOut{item, question, applied: "created", version_created: true}`.
4. **Existing card**: `q = load_question(for_update=True)` (course-scoped). Compute `u = usage.question_usage(db, course, q)` (§5.5), `type_changed = payload.type != q.type`, `in_quiz_bank = q.bank.assessment_id == a.id`, `can_edit_source = permissions.can_edit_bank(ctx, course, q.bank)` (§6.3), `content_changed = question_content_hash(...) != current.content_hash`, `meta_changed`.
   - **Forced `this`** (7c-5): `type_changed and (u.other_count > 0 or u.published_anywhere or q.translation_group_id is not None)`. The translation-group case is added because `link_translation` requires equal types and a type change would break the group; it is still "a new question in this quiz only".
   - Else `u.other_count == 0` → **in place**, `scope` ignored (used only here: no question asked, 7c-2).
   - Else `scope` required: `None` → 409 **`scope_required`** `details = {assessment_count: u.other_count, can_update_all, assessments: u.assessments[:10]}` (the client opens the dialog and re-sends); `"all"` with `not can_edit_source` → 403 **`scope_not_allowed`**.
   - **Passage children** (`item.parent_item_id IS NOT NULL`): `this` is refused with 409 **`passage_child_scope`** because the copy would leave the passage block (`snapshot.py` `passage_mismatch`); a child used elsewhere is edited with `all` or not at all (the card says so, §8). Children in the quiz's own bank are "used only here" in practice and edit in place.
   - **In place / `all`**: `draft.base_version_id != q.current_version_id` → 409 **`version_conflict`** `details = {current_version_id}` (someone else published a version of this question since the card opened; client: "Reload and keep my draft" re-creates the draft with the new base (`PUT` with payload) or "Discard"). Then `new_question_version(db, q, n, origin="edit")` if `content_changed`; `_apply_meta` + `_refresh_search` if `meta_changed`; `item.points = payload.points`; `default_points` of the new version = `payload.points` when `in_quiz_bank`, else the current version's `default_points` (a shared question's default is the bank's business; the item carries the quiz's points). Translation-group type stays equal by construction (type changes were routed to `this`).
   - **`this`**: `q2 = BankQuestion(bank=ensure_quiz_bank(...), type=payload.type, language=payload.language, topic/difficulty/section/tags copied from q, passage_id=None, position=_next_position)`; `new_question_version(q2, origin="create", default_points=payload.points)`; `item.question_id = q2.id; item.points = payload.points`; `check_item_rules` for the new type (422 `item_type_not_allowed`); `_flush_unique` (`uq_assessment_items_question` cannot collide: new id). `q` and every other quiz are untouched.
5. Delete the draft, `_commit(db, a)` (assessment `draft_rev + 1`: the structure or the pinned content changed). Return `CommitOut{item: ItemOut, question: QuestionStaffOut, applied: "in_place" | "all" | "this" | "created" | "unchanged", version_created: bool}`. `unchanged` = nothing differed (draft deleted, points possibly updated).

### 5.5 Usage ("used in N quizzes"; `usage.py`)

`question_usage(db, course, q) -> QuestionUsageOut{other_count, assessments: [{id, title, status, is_this}], published_anywhere}`:
- Live uses: `SELECT DISTINCT assessments.id, title, status, published_version_id FROM assessment_items JOIN assessments ON ... WHERE question_id = q.id AND assessments.deleted_at IS NULL AND assessments.course_id = course.id`. Passage children are `kind = question` rows and are therefore counted. **Picks are not counted** (a pick references a bank + filter; its pool is re-resolved at every publish, so editing a question changes nothing until a republish, exactly like a link). The current quiz is excluded from `other_count`.
- `published_anywhere`: for every assessment in the list with `published_version_id`, load the version's `snapshot["slots"]` (the `newer_version_item_ids` pattern in `publish.py:42-67`) and test whether any slot `qv` ∈ `{id of question_versions WHERE question_id = q.id}`. Exact (an item repointed after publish pins the old question's version and does not count for the new one) and cheap (N assessments ≤ dozens, versions per question ≤ dozens). Preview versions (`kind = preview`) are ignored. `unpublish` keeps `published_version_id`, so an unpublished quiz that students took still counts as published, which is what 7c-5 intends.

Also exposed as `GET /courses/{cid}/questions/{qid}/usage` (`course:content.read_admin`) for the card chip and the bank row; the quiz `GET` already returns `used_elsewhere` per item (one grouped query in `_tree_out`: `GROUP BY question_id` over the course's live items, minus this quiz).

### 5.6 Move / copy to a shared bank (`bank_ops.py`; `POST /courses/{cid}/questions/{qid}/copy-to-bank {bank_id, mode: "move" | "copy"}`)

Target: a live bank of the same course with `assessment_id IS NULL` (else 422 **`target_not_shared_bank`**; cross-course → 404 `bank_not_found` from `load_bank`). Source question must be live (404 otherwise). **move**: `q.bank_id = target.id`, `q.position = _next_position(target)`, `passage_id` must be NULL (409 **`question_has_passage`**: move the passage with its questions in the Bank tab instead; v1 keeps it simple), `source_ref` kept (partial unique per bank; collision → 409 `source_conflict`), translation group kept (course-scoped), items untouched (they point at `q.id`). **copy**: new `BankQuestion` + `new_question_version(origin="create")` from the current version's content (`_version_content`, refs accepted as our own history, P2-16), meta copied, no translation group, items untouched. Both commit; returns `QuestionStaffOut` of the moved/created row.

### 5.7 Error codes (`ids.py`; HTTP as in `core/errors.py`)

`draft_not_found` 404, `draft_exists` 409 (details: the existing `DraftOut`), `draft_conflict` 409 (details: current `draft_rev`, `payload`, `updated_by_name`), `payload_too_large` 413, `scope_required` 409 (details §5.4), `scope_not_allowed` 403, `passage_child_scope` 409, `version_conflict` 409 (existing code, content module), `invalid_question_data` 422 (existing), `item_type_not_allowed` / `item_language_mismatch` / `too_many_items` 422 (existing builder codes), `passage_not_in_quiz_bank` 422, `quiz_bank_follows_quiz` 409, `target_not_shared_bank` 422, `question_has_passage` 409, `item_not_found` 404 (existing). Issue code (warning) `unfinished_drafts`.

### 5.8 Publish with unfinished drafts (decision)

**Ignore, with a warning.** `publish.validate` appends one `Issue("unfinished_drafts", section_pos, item_id | None, severity="warning")` per draft; `publish.publish` is unchanged (drafts are not items, so the snapshot cannot contain them; an existing card with a draft is published with its **current version**, the draft stays for later). UX: the publish bar shows "N cards have unsaved edits. They are not part of the published quiz until you click Done." (`quizEditor.publish.unfinishedDrafts`), the publish confirm lists the cards. Refusing would block a finished quiz over a stray half-card and contradict "nothing is lost"; ignoring plus a visible warning keeps publishing predictable. (Recorded as P7C-3.)

---

## 6. API surface, policies, authorization

### 6.1 Routes (`quiz_editor/policies.py` → `route_inventory.py` block `# --- Phase 7c S1 ---`; `_A = /api/v1/courses/{course_id}/assessments/{assessment_id}`)

| Method, path | Policy | Body → response |
|---|---|---|
| POST `_A/questions` | `course:content.manage` | `QuizQuestionCreateIn{section_id?, after_item_id?, payload: CardPayloadIn}` → 201 `CommitOut` (§5.3; direct create without a draft, used by tests and future "paste questions") |
| POST `_A/drafts` | `course:content.manage` | `DraftCreateIn` → 201 `DraftOut` (409 `draft_exists`) |
| PUT `_A/drafts/{draft_id}` | `course:content.manage` | `DraftUpdateIn{draft_rev, payload}` → `DraftOut` (409 `draft_conflict`) |
| DELETE `_A/drafts/{draft_id}` | `course:content.manage` | → 204 |
| POST `_A/drafts/{draft_id}/commit` | `course:content.manage` | `CommitIn{draft_rev, scope?}` → `CommitOut` (409 `scope_required` / `version_conflict` / `draft_conflict`, 403 `scope_not_allowed`, 422 content issues) |
| GET `/api/v1/courses/{course_id}/questions/{question_id}/usage` | `course:content.read_admin` | → `QuestionUsageOut` |
| POST `/api/v1/courses/{course_id}/questions/{question_id}/copy-to-bank` | `course:content.manage` | `CopyToBankIn{bank_id, mode}` → `QuestionStaffOut` |
| GET `/api/v1/courses/{course_id}/banks` (existing) | existing | query gains `kind: all \| shared \| quiz` (default `all`); `BankOut.assessment` added |

Existing routes unchanged in signature: `GET _A` (`AssessmentStaffOut` gains `drafts`, items gain `has_draft`, `question.bank_kind`, `question.used_elsewhere`), `POST _A/sections` (7c-6 is presentational), `POST _A/validate` (new warning code).

### 6.2 Authorization matrix (server-side, DB roles)

| Action | Course owner / teacher / assistant with `content.manage` | Org admin inside the course (A13, read-only) | Student | Platform admin (not staff) | Teacher of another course / other org |
|---|---|---|---|---|---|
| create question / draft / commit / copy-to-bank | yes | no (403) | no (403) | no (403; platform routes stay separate) | 404 (`load_assessment` / `load_question` course-scoped) |
| read drafts in `GET _A` | yes (`read_admin`) | `drafts = []`, `has_draft = false` | lobby only | no | 404 |
| usage | yes | no (403: `read_admin`) | no | no | 404 |
| list quiz banks in the Bank tab | yes (`read_admin`) | no (as today) | no | no | 404 |
| write in a quiz bank through the Bank tab routes (`POST /banks/{quiz_bank}/questions`, PATCH question) | yes: a quiz bank is a course bank; course staff may edit it like any other | no | no | no | 404 |
| delete / restore a quiz bank directly | 409 `quiz_bank_follows_quiz` | no | no | no | 404 |

### 6.3 Edit rights on the source bank (`content/permissions.py::can_edit_bank(ctx, course, bank) -> bool`, new, S2)

7c: `True` for every live bank of the course when the caller holds `course:content.manage` (every course bank is editable by course staff today). It is the single place Phase 9 extends for org-shared banks (owner or org admin only). The commit uses it for `can_update_all`; `GET _A` exposes nothing about it (the dialog asks the server through `scope_required.details.can_update_all`).

Isolation tests (`test_quiz_editor_isolation.py`): course B's teacher gets 404 on every `_A` route of course A and on `usage`/`copy-to-bank` of A's questions; A's quiz banks are absent from B's `GET /banks`; two independents in personal organizations never see each other's quiz banks; a student gets 403 on every write and the lobby on `GET _A`; an org admin reading the course gets `drafts = []`.

---

## 7. Concurrency

| Case | Mechanism | Test |
|---|---|---|
| Two tabs on one card | one draft per item (`uq_question_drafts_item`); `UPDATE ... WHERE draft_rev = :rev` single statement; loser gets 409 `draft_conflict` with the winner's payload | SQLite API test (two sessions) + PG `test_pg_concurrency_quiz_editor.py::test_two_tabs_autosave` (20 threads, exactly 20 revs, last payload = winner's) |
| Done racing autosave | client awaits in-flight autosaves (`useDraftAutosave.flush()`) before Done; server commit requires the exact `draft_rev`; a late PUT after commit → 404 `draft_not_found` (client ignores when the card is closed) | API test: PUT(rev 3) then commit(rev 3) then PUT(rev 4) → 404 |
| Two teachers commit `all` on one question | `load_question(for_update=True)` + `base_version_id == current_version_id` check (existing `version_conflict` pattern) + `uq_question_versions_question_version` backstop | PG: two threads → one 200, one 409, exactly one new version |
| Two tabs commit the same new-card draft | assessment row lock (`_manage`) serializes; the second finds no draft → 404 | PG: two threads → one 201, one 404, one question, one item |
| Quiz bank first use from two tabs | assessment row lock + `uq_question_banks_assessment_live` | PG: two threads create first question → one bank, two questions |
| Repoint (`this`) atomicity | one transaction: q2 + version + `item.question_id` + draft delete + `draft_rev`; validation before writes | API test: invalid payload with `scope=this` → no new question, no item change, draft kept |
| Section/item deleted while a card is open | `delete_item`/`delete_section` remove drafts; the open tab's next autosave → 404, card shows "This question was removed" and offers "Re-add as new card" (payload kept client-side) | API test |

---

## 8. Frontend

### 8.1 Routing (7c-8)

`frontend/src/app/[lang]/courses/[courseId]/assessments/[assessmentId]/edit/page.tsx` becomes `<StaffGate><EditorSwitch/></StaffGate>`: it loads the assessment once and renders **`SectionBuilder`** (today's `Builder`, moved verbatim to `components/lms/assessments/SectionBuilder.tsx` with an `initial` prop; same markup, same i18n keys) when `a.preset !== "none"`, else **`QuizEditor`**. ORT exams (`ort_main`, `ort_subject`) therefore keep today's builder pixel for pixel (`ort-visual.spec.ts` `teacher-builder-*` baselines must match); template-created exams and blank quizzes get the new editor.

### 8.2 Component tree (`frontend/src/components/lms/quiz/`)

```
QuizEditor.tsx            page shell: tabs Questions · Settings (existing SettingsPanel) · Preview (existing startPreview); state (§8.3)
├─ QuizPublishBar.tsx     sticky top: status badge, item count, total points, "unpublished changes", drafts count, Check / Publish (usePublishFlow, IssueList)
├─ QuizSectionBlock.tsx   one per section; header hidden for the single default section (§2.3); SectionDialog reuse; locks via templateLockedFields/isAssessmentLocked
│  ├─ QuestionCard.tsx    collapsed: number, type chip, points, first stem line (MathRenderer), correct answers marked, chips "Draft", "Used in N quizzes", "Shared bank"
│  │  ├─ QuestionCardForm.tsx   (components/lms/content/, shared with the Bank tab; §8.4)
│  │  ├─ useDraftAutosave.ts    debounce 800 ms, draft_rev, status idle|saving|saved|conflict|gone|error, flush()
│  │  ├─ CardToolbar            Done (primary), Discard draft, Duplicate, Move up/down (+ drag), Delete (undo toast 10 s = re-add same question/points/position)
│  │  ├─ ScopeDialog.tsx        "Update in all N quizzes" / "Change only in this quiz"; note "Published quizzes change only after they are republished"; `all` disabled with reason when !can_update_all; list of the quizzes
│  │  └─ DraftConflictDialog    reuse content/ConflictDialog.tsx (take theirs / keep mine)
│  ├─ PassageCard.tsx     header (title, body excerpt) + indented child QuestionCards; children from shared banks show the §5.4 note; "Add passage" via the Find drawer (existing passage tab)
│  ├─ PickCard.tsx        random group: PickFields reuse, pool sizes, points, count
│  └─ AddBetween.tsx      small "+" between cards and at the end → menu: Question, Passage, Random group, Find questions
├─ FindQuestionsDrawer.tsx  AddItemsDialog's body inside a side drawer (full screen at 375 px); BankSelect grouped "Shared banks" / "Quiz banks" (other quizzes, with their titles; this quiz's own bank excluded since its questions are already cards)
└─ lib/lms/quizEditor.ts + quizEditorTypes.ts  API client: createQuizQuestion, createDraft, updateDraft, deleteDraft, commitDraft, getQuestionUsage, copyToBank
```

### 8.3 State model (`QuizEditor`)

`assessment: AssessmentStaffOut` (sections, items with `has_draft`, `drafts`), `openCardId: string | null` (one open card: an item id or a draft id `draft:<id>`), per open card `{form: QuestionForm, draftId, draftRev, status, serverErrors}`; new cards appear in the list at their `after_item_id` position from `assessment.drafts` (item_id null). **Open**: existing card → `POST /drafts {item_id}` (or adopt the `draft_exists` payload); form seeded from the draft payload or `formFromStaff`. **Typing** → `useDraftAutosave` PUT. **Done** → `flush()` → `commitDraft(scope?)`: 409 `scope_required` → `ScopeDialog` → retry with scope; 409 `version_conflict` → `DraftConflictDialog`; 422 → inline field errors (`details[].loc` mapped to fields), card stays open; 200 → reload the assessment, collapse. **Close card (click outside / Esc / another card)** = Done when the form validates client-side (`validateForm`), else the card stays open as a draft with the "Draft saved · has errors" chip (7c-4: closing commits; invalid cards cannot commit so they remain drafts). **Discard** → `DELETE /drafts/{id}`. **Type dropdown** options = `QUESTION_TYPES ∩ section.rules.allowed_types` (template and preset rules are already in `section.rules`); switching the type keeps the whole `QuestionForm` (it already holds every type's fields), so text, choices and correct marks carry over where shapes match. Answers UI: Enter adds a choice, Backspace on an empty choice removes it (both also reachable with visible buttons, UX §4 "no hidden features"), radio/checkbox marks correct (green + check icon, never colour alone).

### 8.4 `QuestionEditor` refactor (no behaviour change for the Bank tab or ORT)

Extract the form body of `components/lms/content/QuestionEditor.tsx` (type select, language, points, stem, image, per-type fields, explanation, meta grid) into **`QuestionCardForm.tsx`** `({form, onChange, disabled, courseId, typeOptions, lockType, lockLanguage, passages, showMeta, idPrefix})`; `QuestionEditor` keeps its props, API calls, save button and `formModel.ts` usage and renders `QuestionCardForm` (`lockType = editing`, `typeOptions = QUESTION_TYPES`). Snapshot test of the rendered DOM before/after (Playwright `bank-editor` screenshot in the walkthrough) proves pixel parity for the ORT bank screens. `ChoiceFields`/`SimpleFields`/`formModel` are untouched except `formModel.ts` gaining `payloadFromForm(f): CardPayloadIn` and `formFromPayload(p)` (pure additions).

### 8.5 Bank tab (7c-3, 7c-9; S4)

`bank/page.tsx`: `listBanks(..., kind: "all")`, split by `b.assessment` into "Shared banks" and "Quiz banks" (group headers only when the quiz group is non-empty, so ORT courses render exactly as today); quiz bank card shows the quiz title (from `b.assessment.title`), "Open quiz" link, counts; rename, delete and restore hidden (the bank follows the quiz, Q3). `bank/[bankId]/page.tsx`: for `templateUi().key !== "ort"` the "New question" `MenuButton` becomes a `Button` → `new` route without `?type`; `new/page.tsx` defaults to `single_choice` and the type dropdown is in the form (already the case for `QuestionEditor` in create mode). ORT courses keep the `MenuButton` and `?type` flow (`templateUi().key === "ort"`). Question rows in a quiz bank get "Move or copy to a shared bank" → **`MoveToBankDialog.tsx`** (bank select of shared banks, radio move/copy, usage note "used in N quizzes; links are kept").

### 8.6 Mobile (375 px)

Cards full width; collapsed card is one row (number, chip, points, stem line); expanded card stacks fields; the publish bar is sticky at the top with status + Publish only (points/count under it); the Find drawer is full screen with a back button; `AddBetween` uses a 44 px target; drag handles hidden below `sm`, Move up/down buttons shown instead; the scope dialog is a bottom sheet (`Dialog` component). Russian/Kyrgyz labels tested at 375 px.

### 8.7 i18n groups (en/ky/ru; parity script)

**`quizEditor.*`**: `tabs.{questions,settings,preview}`, `publishBar.*` (status, items, points, unpublished, unfinishedDrafts, check, publish), `card.*` (addQuestion, addBetween, done, discard, duplicate, delete, undo, deleted, readd, draftSaved, draftSaving, draftError, draftHasErrors, usedIn, sharedBank, quizBank, typeLabel, pointsLabel, correctHint, addAnswer, removeAnswer, enterAdds), `scope.*` (title, body, republishNote, all, this, allDisabled, cancel), `conflict.*` (title, body, takeTheirs, keepMine), `passageChild.*` (note), `find.*` (title, add, groupShared, groupQuiz, close), `pick.*`, `section.{defaultHidden, firstBecomesSection1}`, `errors.{draft_conflict, draft_exists, scope_required, scope_not_allowed, passage_child_scope, payload_too_large, passage_not_in_quiz_bank}`. **`bank.quizBanks.*`** (group, sharedGroup, openQuiz, followsQuiz), **`bank.moveToBank.*`** (title, move, copy, target, usageNote, errors.{target_not_shared_bank, question_has_passage, quiz_bank_follows_quiz}), **`assessments.issues.unfinished_drafts`**, `lms.errors.{version_conflict}` reused.

---

## 9. Slices, ownership, order, models

Branches `phase-7c/<slice>` off `lms`. Delimited blocks `# --- Phase 7c S<n> begin/end ---` in shared files. The orchestrator merges and reviews every diff.

| Slice | Model | Scope | Owns (exclusive) |
|---|---|---|---|
| **S1** migration + models + shapes (alone, early push; merged before S2–S4) | opus | §2, `quiz_editor/{__init__,models,ids,schemas,policies(stub)}.py`, `BankOut.assessment` + `bank_rows_stmt` join + `kind` query param, `ItemOut.has_draft`, `ItemQuestionOut.{bank_kind, used_elsewhere}` (defaults, not yet computed), `AssessmentStaffOut.drafts = []`, models registration, inventory block, migration test | `backend/alembic/versions/0011_phase7c_quiz_editor.py`, `app/lms/quiz_editor/{__init__,models,ids,schemas,policies}.py`, blocks in `content/{models,schemas,repository,router(list_banks kind)}.py`, `assessments/schemas.py`, `app/lms/models.py`, `app/core/route_inventory.py`, `tests/test_migration_0011.py`, `tests/lms/quiz_editor_support.py` (fixtures: general course + quiz + shared bank + second quiz) |
| **S2** backend services + API + tests | opus (architect review of `commit.py` and `usage.py` before merge) | §5, §6, §7: quiz banks, drafts, commit/scope/type rule, create-in-quiz, usage, copy-to-bank, `can_edit_bank`, builder/content/publish hooks, `staff_out(include_drafts)`, `_tree_out` fields, router mount, all backend tests incl. PG | `app/lms/quiz_editor/{quiz_banks,drafts,commit,usage,bank_ops,router}.py`, `policies.py` (fills), `content/permissions.py`, blocks in `content/service.py`, `assessments/{builder,publish,router}.py`, `app/api/v1/router.py`, `tests/lms/test_quiz_editor_{drafts,commit,scope,type_change,usage,bank_ops,quiz_banks,isolation,publish_drafts}.py`, `tests/lms/test_pg_concurrency_quiz_editor.py` |
| **S3** frontend quiz editor | opus | §8.1–8.4, 8.6, `quizEditor.*` i18n, `payloadFromForm/formFromPayload` | `components/lms/quiz/**`, `components/lms/assessments/SectionBuilder.tsx` (move), `edit/page.tsx`, `components/lms/content/{QuestionEditor,QuestionCardForm}.tsx`, `components/lms/content/types/formModel.ts` (additions), `lib/lms/{quizEditor,quizEditorTypes}.ts`, `lib/lms/assessmentTypes.ts` (new fields), i18n JSON group `quizEditor` + `assessments.issues.unfinished_drafts` |
| **S4** Bank tab | sonnet | §8.5, `bank.quizBanks.*`, `bank.moveToBank.*` | `app/[lang]/courses/[courseId]/bank/page.tsx`, `bank/[bankId]/page.tsx`, `bank/[bankId]/new/page.tsx`, `components/lms/content/MoveToBankDialog.tsx`, `components/lms/content/QuestionRow.tsx` (menu item), `lib/lms/content.ts` (`listBanks kind`, `copyToBank`), `lib/lms/contentTypes.ts` (`BankOut.assessment`), i18n groups `bank.quizBanks`, `bank.moveToBank` |
| **S5** integration + gates | orchestrator + ux-reviewer (fable) + architect security review | full suites SQLite + PG, `alembic check`, ORT review §13, UX gate §12, `/security-review` (draft payload size and IDOR, scope authorization, copy-to-bank target scoping, org admin draft redaction), i18n parity, `next build` in the rsync'd copy, Playwright walkthrough §11, `docs/phases/PHASE_7C.md`, `PRODUCT_DECISIONS.md` (P7C-*), handoff + memory | docs, `docs/phases/PHASE_7C_screens/**`, `frontend/e2e/quiz-editor.spec.ts` |

**Order**: S1 alone (pushes names, shapes, migration). Then S2, S3, S4 in parallel: S3 codes against §5/§6 shapes with a mock until S2 lands; S3 and S4 share no file (`getQuestionUsage` lives in S3's `quizEditor.ts` and S4 imports it; S4's `content.ts` change is additive). S5 last.

**Gates per slice**: SQLite suite green; route-inventory test green; action × role table tests for every new route; isolation tests; serializer test (no `drafts` for org admins, no `access_code_hash` regressions); `tsc --noEmit` for S3/S4. **Phase gates (before `lms`, again before `main`)**: SQLite and PG suites, `alembic upgrade head && alembic check`, `test_migration_0011.py` both engines, PG concurrency suite, ORT review §13, UX gate §12, security review, i18n parity, `next build`, `/health` shows the commit after deploy. **Neon rule**: snapshot `pre-7c-<date>` before the `main` merge (models and migration change), id recorded in `PHASE_7C.md`.

---

## 10. Tests (backend `tests/lms/`, scratch SQLite + PG parity)

- `test_quiz_editor_drafts.py`: create new-card and existing-card drafts, `draft_exists` returns the existing one, autosave bumps `draft_rev` only, stale rev → 409 with the winner's payload, 50 autosaves → zero new versions, payload cap 413, delete idempotent, drafts not in snapshot (`build_snapshot` of a quiz with drafts equals one without), org admin sees `drafts = []`, item delete removes the draft.
- `test_quiz_editor_commit.py`: new card → question in the quiz bank + version + item at `after_item_id` position in one transaction (rollback on invalid payload leaves nothing); default section created lazily; quiz bank created once and reused; `item.points` and `default_points` as §5.4; unchanged content → `applied = unchanged`, no version; `too_many_items` and section `allowed_types` enforced (template exam created from a 7b template with `allowed_types = [comparison]` refuses `single_choice`).
- `test_quiz_editor_scope.py`: used only here → in place without `scope`; used in a second quiz → `scope_required` with count and `can_update_all`; `all` → new version, both quizzes' `GET` show `newer_version_available` after republish of neither, the second quiz's published snapshot unchanged; `this` → new question in this quiz's bank, item repointed, source question and second quiz untouched; `all` with `can_edit_bank = False` (monkeypatched) → 403; passage child + `this` → 409 `passage_child_scope`.
- `test_quiz_editor_type_change.py`: type change, used only here, never published → in place (new version with the new type, `q.type` updated); used elsewhere → forced `this`; published anywhere (including after `unpublish`) → forced `this`; translation group member → forced `this`; new type not allowed in the section → 422.
- `test_quiz_editor_usage.py`: counts distinct live assessments, excludes deleted assessments, excludes picks, counts passage children, `published_anywhere` exact after repoint (old question still published, new one not), preview versions ignored.
- `test_quiz_editor_bank_ops.py`: move keeps items and translation group, refuses passages and non-shared targets, `source_conflict`; copy leaves items; cross-course target 404.
- `test_quiz_editor_quiz_banks.py`: `assessment_id` set, org copied, soft delete/restore of the quiz flips the bank, direct bank delete/restore → 409, `kind=quiz|shared|all` listing, `BankOut.assessment.title` follows the quiz title, `is_quiz_bank` guard for Phase 9 `visibility`.
- `test_quiz_editor_publish_drafts.py`: `unfinished_drafts` warnings per draft, publish succeeds, snapshot pins current versions, a running attempt is unaffected by a later commit (`all` and `this`), republish picks the new version.
- `test_quiz_editor_isolation.py`: §6.3 matrix.
- `test_pg_concurrency_quiz_editor.py`: the five PG rows of §7.
- Existing suites unchanged and green: `test_assessment_builder.py`, `test_banks_api.py`, `test_content_*.py`, `test_ort_*.py`, `test_route_inventory.py`.
- Frontend: `tsc --noEmit`; `scripts/check_i18n_parity.py`; Playwright **`frontend/e2e/quiz-editor.spec.ts`** (general course: create quiz → write five cards of five types without opening the Bank tab → add a shared-bank question → edit it with "Change only in this quiz" → add a second section ("Section 1" appears) → publish with one unfinished draft (warning shown) → student takes it → second quiz unchanged) and the ORT suite `ort.spec.ts` + `ort-visual.spec.ts` unchanged.

---

## 11. Walkthrough (S5, dated in `PHASE_7C.md`)

Teacher in a general course: new quiz from the assignments list → editor opens with an empty default section → "+ Add question" → multiple choice card, type dropdown shows all seven types → write, Enter adds answers, mark correct → Done → card collapses with number/points/stem → repeat for true/false, numeric, short text, essay → "Find questions" adds two from a shared bank (chips "Shared bank", "Used in 2 quizzes") → open one, edit, Done → scope dialog → "Change only in this quiz" → chip becomes "Quiz bank" → add a section → first block now titled "Section 1" → close the browser mid-card, reopen → the draft is back → Publish with the warning → student takes the quiz; the second quiz shows no change; Bank tab shows the quiz bank under "Quiz banks"; "Move to shared bank" one question → it is still in the quiz. ORT course: bank, import, builder, player, result as before (§13).

---

## 12. UX gate screens (`docs/phases/PHASE_7C_screens/`, 375 px + desktop, teacher screens in ru, student screens unchanged)

Quiz editor empty state; one collapsed card list (5 types); expanded multiple-choice card with answers; expanded card with inline validation errors; draft chips ("Draft saved", "has errors"); scope dialog (both options; `all` disabled variant); version-conflict dialog; "Section 1" after a second section; passage card with children (incl. the shared-passage note); random group card; Find drawer (desktop side, 375 full screen) with the grouped bank select; publish bar with unfinished-drafts warning and the confirm list; Bank tab with "Quiz banks" group; move/copy dialog; bank "New question" in a general course (button) and in an ORT course (unchanged menu). Reviewed by `ux-reviewer` against `docs/UX_GUIDELINES.md`; findings fixed without asking.

---

## 13. ORT review plan (nothing changes; proofs)

Why: ORT exams are `preset ort_main|ort_subject`, routed to `SectionBuilder` (today's code) in §8.1; the ORT Bank tab shows no "Quiz banks" group because ORT courses never get quiz banks (no inline authoring in the ORT builder; the `MenuButton` + `?type` flow is kept for `templateUi().key === "ort"`); the importer files are untouched and `quiz_bank_no_source` keeps importer banks shared; `build_snapshot`, the engine, the player and `OrtResultView` read nothing new; `AssessmentStaffOut` gains additive fields with defaults.

| Proof | How |
|---|---|
| Imports identical | `test_ort_import_golden.py`, `test_import_csv.py`, `test_import_bundle.py`, `test_import_rules.py` green; `git diff --stat lms -- backend/app/lms/content/importers/` empty |
| Scores, flow, seed | `test_ort_parity.py`, `test_ort_e2e_api.py`, `test_ort_cutover_flow.py`, `test_ort_seed.py`, `test_ort_gradebook_golden.py` green; `test_ort_seed.py` additionally asserts no `question_banks.assessment_id` in ORT courses |
| Builder and bank screens | `frontend/e2e/ort-visual.spec.ts` against `docs/phases/ORT_BASELINE/` (`teacher-builder-*`, bank screens) with zero expected diffs; `QuestionEditor` DOM snapshot before/after the §8.4 refactor identical |
| Player | `ort.spec.ts` unchanged and green |
| Report | `PHASE_7C.md` ORT section: test names, diff check, walkthrough date |

---

## 14. Decisions taken here (to `PRODUCT_DECISIONS.md` as P7C-1 … when applied)

- **P7C-1** Drafts live in their own table `question_drafts`; a new card is a draft row with `item_id NULL` and a position hint; question, version and item are created together on the first valid Done (nothing half-made ever enters `assessment_items`).
- **P7C-2** Autosave never bumps the assessment `draft_rev`; commit does.
- **P7C-3** Publishing ignores unfinished drafts and warns (`unfinished_drafts`); an existing card with a draft publishes its current version.
- **P7C-4** The hidden default section is a presentation rule (one untitled, unkeyed, rule-less section on a `preset = none` quiz), created lazily; no schema.
- **P7C-5** Picks do not count as "uses"; passage children do. "Published anywhere" is computed exactly from published snapshots and survives `unpublish`.
- **P7C-6** A passage child used elsewhere can only be edited with `all` (`this` refused); shared-passage children without edit rights are read-only in the card.
- **P7C-7** Type change on a translation-group member takes the `this` path (keeps groups type-homogeneous).
- **P7C-8** "Find questions" offers shared banks and other quizzes' quiz banks of the same course (one store, nothing hidden); the quiz's own bank is excluded.
- **P7C-9** Move to a shared bank refuses questions attached to a passage in v1; copy never joins a translation group; quiz banks cannot be deleted or restored directly.
- **P7C-10** `can_edit_bank` returns true for every course bank in 7c and is the Phase 9 extension point.
- **P7C-11** The Bank-tab editor keeps its type lock; the card is the only place a type changes.

---

## 15. Alternatives to discuss (owner; none blocks, each has a default)

| # | Question | Options | Default |
|---|---|---|---|
| **Q1** | Find questions from **other quizzes' banks** (P7C-8). Linking across quiz banks means deleting quiz A later makes quiz B's linked card `question_deleted` at its next publish (today's deleted-bank behaviour; the delete confirm will say "N questions of this quiz are used in other quizzes"). | (a) allow, grouped "Quiz banks" in the drawer; (b) shared banks only, teachers copy to a shared bank first. | **(a)**; switching to (b) is one filter in the drawer's bank select. |
| **Q2** | Publishing with unfinished drafts (P7C-3). | (a) warn and publish; (b) refuse until every card is Done or discarded. | **(a)**. |
| **Q3** | Quiz bank title in the Bank tab follows the quiz title (join) rather than a teacher-editable bank title. | (a) follow the quiz, rename hidden for quiz banks; (b) allow rename (shown as "<quiz title> · <bank title>"). | **(a)**, simpler and never stale; `PATCH` stays available for description only. |
