# LMS Architecture (target design)

**Status**: proposal for owner review, 2026-10-21. Supersedes `CANVAS_INTEGRATION_SPEC.md` and `CANVAS_EXPLAINER_FOR_FOUNDER.md` (drafts, not binding).
**Inputs**: `PRODUCT_DECISIONS.md`, `PROJECT_UNDERSTANDING.md`, and four research reports in `docs/research/` that read the real `instructure/canvas-lms` source (commit `1c9f0bb`, 2026-04-30) plus platform research. Canvas facts below were verified in that source by the research agents unless marked *(unverified)*. New Quizzes' backend is not public, so anything about it is unverified.

---

## 1. Principles

1. **Copy Canvas's semantics, not its machinery.** Authority comes from the enrollment. Delete is soft. History is never cascaded away. Skip Accounts, Pseudonyms, Sections, Terms, custom roles, STI, polymorphic links and JSON rule columns.
2. **Everything belongs to a course** (or to a teacher's library) and carries `course_id`/`owner_id`. One authorization layer decides access. No endpoint decides on its own.
3. **Real foreign keys, no JSON rule blobs, typed nullable FKs with CHECK instead of polymorphic pairs.** JSON only for validated, type-specific payloads.
4. **Numbers are truth, labels are derived.** Scores are stored as points. Scaled scores and labels come from versioned, immutable grading schemes.
5. **Attempts are sacred.** A snapshot at start, a server-owned deadline, one-shot submit, one row per answer, never deleted by cascade.
6. **Server-side everything that matters**: timer, submit lock, answer-key privacy, roles from the database.
7. **ORT is data, not code**: a course, a quiz with sections, and a grading scheme.
8. **Small and cheap**: Postgres, Cloudflare R2, our own policy module, synchronous gating. No queues in v1.

## 2. Concept map

```
User ──< Enrollment >── Course ──< Module ──< ModuleItem ──> Page | File | Assessment | URL | Header
 │         (role, state)    │                       │
 │                          ├──< Assessment(Quiz) ──< Section ──< QuizItem ──> QuestionVersion | PassageVersion | Pick(bank)
 │                          │         │
 │                          │         └─ GradingSchemeVersion (immutable)
 │                          ├──< QuestionBank ──< Question ──< QuestionVersion   (owned by a teacher; may be course-scoped)
 │                          ├──< EnrollmentForm ──< Application
 │                          └──< GradeCategory (optional weights)
 └──< Attempt ──< AttemptItem        Submission (one per enrollment+assessment, kept result)
```

*Course = a teacher's live class. There are no sections. Reuse is by copy (course copy, bank copy), not by "blueprint".*

## 3. Identity, courses, enrollment, authorization

(Research: `canvas-core-domain.md`.)

**users**: drop global `role`. Add `is_platform_admin` (support/moderation only, read from DB, never silent), `locale` (`en|ru|ky`), `birth_year`/`age_band` (nullable, for consent). Add `teacher_status` (`none|pending|approved|revoked`, default `none`) plus a `teacher_requests` table (user, message, status, decided_by, decided_at, reason). Every sign-up is a student; only `approved` users may create courses, and a platform admin decides requests (owner decision 2026-10-22, replaces D10). Per-course powers still come from the enrollment role. Revoking teacher status blocks new courses but does not delete existing ones.

**courses**: `id uuid, owner_id, title(LocalizedText), description, languages text[] (⊆ en|ru|ky), default_language, status draft|published|concluded, visibility private|catalog, enrollment_mode closed|open|invite_code|form_auto|form_review, join_code (generated 6–8 chars, partial unique, regenerable), enrollment_limit, starts_at, ends_at, default_grading_scheme_version_id, settings, copied_from_id, created_at, updated_at, deleted_at, deleted_by_id`. Soft delete is separate from `status`; restore returns to `draft`.

**enrollments**: `course_id, user_id, role teacher|assistant|student, state requested|invited|active|declined|removed, source, content_language, invite_token_hash, invite_expires_at, activated_at, removed_at, removed_by_id`. `UNIQUE(course_id,user_id)`, `ON DELETE RESTRICT`. Re-joining revives the same row (old attempts become visible again). *Concluded* is derived from course status, not stored per enrollment. **enrollment_events** (append-only) records every state/role change.

**Invariants**: creating a course inserts the owner's `teacher/active` enrollment in the same transaction; it cannot be removed or downgraded until ownership is transferred. Joining runs in one transaction with `SELECT … FOR UPDATE` on the course to enforce the limit; failure messages are identical to avoid code-guessing; join is rate-limited by user and IP.

**Authorization** (`app/core/authz.py`): `can(user, action, resource)` / `require(...)`. Resolution: resource → course (one hop through `course_id`) → 404 if deleted → the user's *active* enrollment (cached per request) → status gates (draft: staff only; concluded: read-only) → `action ∈ ROLE_GRANTS[role]` + row rules (students read only their own attempts; answer keys need `content.read_admin`) → `is_platform_admin` only for a whitelist. Roles and grants are defined in code (no DB overrides). List endpoints use SQL scopes (`courses_visible_to`, `catalog_courses`, `attempts_visible_to`), never `can()` in a loop. **Merge gate**: a test walks `app.routes` and fails if a route is not listed in the permission matrix; table-driven action × role × status tests; a two-teachers / three-students isolation suite.

## 4. Content library

(Research: `canvas-assessments.md`, `platform-concerns.md`.)

```
question_banks(id, owner_id, course_id NULL, title, deleted_at)
assets(id, owner_id, sha256, storage_key, mime, bytes, UNIQUE(owner_id, sha256), deleted_at)   -- images/files in R2
passages(id, bank_id, current_version_id, deleted_at)
passage_versions(id, passage_id, version_no, language, title, body, created_at)               -- immutable
questions(id, bank_id, passage_id NULL, translation_group_id NULL, type, topic, difficulty, tags,
          position NULL, source_ref NULL, current_version_id, deleted_at,
          UNIQUE(owner_id, source_ref))
question_versions(id, question_id, version_no, language, type, schema_version, stem, data JSON,
                  explanation, default_points, created_at, created_by)                          -- immutable
```

- **Versioning replaces Canvas's copy-and-sync.** Every edit inserts a new version; quizzes and attempts reference *version ids*. Nothing is copied, nothing goes stale, and history is exact.
- **Languages (resolved conflict between two reports)**: a *question is monolingual* (`language` per version), with an optional `translation_group_id` linking variants. ORT ky and ru exams are different item sets, not translations; statistics and grading are per variant; editing the Russian text never rewrites Kyrgyz history. Short metadata (titles, descriptions, form labels) uses a validated `LocalizedText` JSON `{en?,ru?,ky?}` with the course default required and a read fallback (requested → default → first). A quiz item points to a translation group *or* a single question; the attempt records the exact variant id.
- **Answer key** lives in `data`, refers to stable choice ids, and is never serialized to students. Each type defines `student_view()` built from an allowlist (the Canvas `censor` pattern).
- **Text**: sanitized Markdown + raw LaTeX (rendered by KaTeX as today), or an allowlisted HTML subset sanitized on write (`nh3`). No `equation_images`. Inline images are `assets` ids.
- **Question types v1** (registry: Pydantic data model, response model, `student_view`, `score`): `single_choice`, `multiple_answers` (all-or-nothing or partial), `true_false`, `comparison` (ORT math_1; its 4 labels are app i18n, not stored), `numeric` (exact±margin or range), `short_text` (normalized, incl. Cyrillic look-alikes), `essay` (manual → `needs_review`). Later: matching, ordering, fill_blanks, file_upload. Skipped: calculated, hot-spot, categorization.
- **Imports** (CSV and ort-digitizer bundles) are ported: one bank per source, `source_ref` unique *per owner* (fixes today's global-collision), document order preserved as `position`, images through `assets` with sha256 dedupe. Section rules (math_1 = comparison only) move from the question to the quiz section (`quiz_sections.rules`), enforced at import, item add and publish.

## 5. Assessments and attempts

```
assessments(id, course_id, owner_id, title, description, languages, status draft|published, published_version_id,
            time_limit_s, allowed_attempts (-1 = unlimited), score_policy highest|latest|first|average,
            shuffle_items, shuffle_choices, navigation free|section_forward_only,
            results_policy never|after_submit|after_close, show_correct_answers,
            available_from, available_until, grading_scheme_version_id, points_possible, category_id, deleted_at)
assessment_sections(id, assessment_id, position, key NULL, title, time_limit_s NULL, rules JSON)
assessment_items(id, assessment_id, section_id, position, kind question|passage|pick,
                 question_id|translation_group_id NULL, passage_id NULL, points,
                 pick_bank_id NULL, pick_count NULL, pick_filter JSON NULL)
assessment_versions(id, assessment_id, version_no, snapshot JSON, published_at)
```

Publishing resolves every item to its current version id and writes an immutable `snapshot` (Canvas `generate_quiz_data`, but with ids not blobs). Students see only a published version; editing makes a draft and republishing bumps the version. A published quiz with attempts keeps serving the old version to in-flight attempts. (Edit-after-publish rule: decision D9.)

```
attempts(id, assessment_id, assessment_version_id, enrollment_id, attempt_no, language, is_preview,
         status in_progress|submitted|needs_review|graded|void, started_at, deadline_at, extra_time_s,
         current_section_pos, submitted_at, submit_reason manual|timeout|sweep, raw_score, points_possible, result JSON,
         UNIQUE(assessment_id, enrollment_id, attempt_no);
         partial UNIQUE(assessment_id, enrollment_id) WHERE status='in_progress')
attempt_sections(attempt_id, section_pos, started_at, deadline_at, closed_at)
attempt_items(id, attempt_id, position, section_pos, question_version_id, points, choice_order JSON,
              response JSON, flagged, answered_at, score, correctness, manual_score, feedback)
```

**Integrity (fixes today's holes at the root)**
- *Snapshot at start*: all `attempt_items` rows (resolved picks, shuffle permutations, points) are created in one transaction; later edits never affect the attempt.
- *Server deadline*: `deadline_at = min(started + limit + extra, available_until)` plus per-section deadlines. Autosave is `UPDATE attempt_items … WHERE attempt.status='in_progress' AND now() <= LEAST(deadlines) + grace` (grace 30–60 s, D8).
- *One-shot submit*: `UPDATE attempts SET status='submitted' WHERE id=:id AND status='in_progress' RETURNING …`. Exactly one caller wins and only that caller grades. Expiry is handled lazily on any read/write, plus a periodic sweep for abandoned attempts.
- *Section navigation*: closing a section sets `closed_at`; its items reject writes (server-side forward-only).
- *Row per answer*: autosave is a single-row UPDATE (no read-modify-write race between tabs); per-item statistics are SQL (replaces the fake discrimination index); regrade and manual grading work per item.
- *No cascade-deletes* of attempts anywhere (`ON DELETE RESTRICT`); parents are soft-deleted and filtered.

## 6. Grading

(Research: `canvas-modules-grading.md`.) Canvas has no ORT-style curve; its grading standard is only a table of percentage cutoffs. Ours is a pluggable, versioned scheme.

```
grading_schemes(id, owner_user_id NULL, title, type points|percent|bands|pass_fail|piecewise_curve|lookup_table, deleted_at)
grading_scheme_versions(id, scheme_id, version, scale_min, scale_max, pass_threshold_percent,
                        percentile_mean, percentile_sd, rounding, created_at)       -- immutable once referenced
grading_scheme_bands / _curve_segments / _table_rows / _thresholds                   -- per-type child rows
submissions(id, enrollment_id, assessment_id, UNIQUE(enrollment_id, assessment_id), state, kept_attempt_id, kept_policy_snapshot,
            raw_points, points_possible, late_deduction, override_points, scheme_version_id,
            display_value, label, percentile, released_at, version)
grade_events(id, submission_id, actor_id, field, old, new, reason, at)               -- append-only
grade_categories(course_id, title, weight, position, deleted_at)  [optional]
course_grades(enrollment_id PK, current_percent, final_percent, display_value, label, computed_at)
```

`effective_points = coalesce(override_points, raw_points) − late_deduction`. One pure function `apply(version, raw, possible) → (display_value, label, percentile, passed, thresholds)` per type, in a registry, unit-tested.

**ORT as data**: main = `piecewise_curve` v1 (scale 60–245, mean 150, SD 30; segments ratio [0,.5]→[60,150] exponent 1.05 and [.5,1]→[150,245] exponent 0.95; threshold `golden_certificate` = 219); subject = same shape 60/105/150, SD 20. Today's `test_scoring` numbers are reproduced exactly as the parity gate, including the "raw 0 → 0" quirk, *unless* the owner decides to fix it (D6). When the official CEATM tables are available, add a `lookup_table` version; no code change. Editing a scheme creates a new version; old results keep theirs until the teacher regrades (recommended: on request only). Recompute triggers: attempt submitted, override, scheme version swap, points change, kept-policy change; each writes `grade_events` and re-evaluates gating for those enrollments.

## 7. Modules and gating

```
course_modules(id, course_id, title, position, published, unlock_at, sequential, completion_mode all|any, rules_version, deleted_at)
module_prerequisites(module_id, prerequisite_module_id)       -- must point to an earlier module of the same course (422 otherwise)
module_items(id, module_id, position, indent, title_override, published, kind page|file|assessment|url|header,
             page_id|file_id|assessment_id|url (exactly one by CHECK), deleted_at)
item_completion_requirements(item_id PK, type view|mark_done|submit|min_score|min_percent, threshold)
item_progress(enrollment_id, item_id, event viewed|marked_done|submitted|scored, score_percent, submission_id, created_at)  -- append-only facts
module_progress(enrollment_id, module_id, state locked|unlocked|started|completed, evaluated_rules_version, evaluated_at, version)  -- derived cache
item_requirement_status(enrollment_id, item_id, met, best_score_percent, met_at)                                                   -- derived cache
pages(id, course_id, translation_group_id, language, title, body, published, deleted_at)
```

Visibility is computed (item ∧ module ∧ target published and none deleted), not synced (removes Canvas's `ContentTag.update_for` bug class). **Gating algorithm** (synchronous, small courses): (1) unpublished/deleted → locked, teachers bypass; (2) return cached row if rules version, facts and `unlock_at` are unchanged; (3) open iff `now ≥ unlock_at` and all prerequisites `completed` (recursion goes strictly backwards, memoized); (4) evaluate each visible item's requirement from facts, or from the *released* kept score for `min_*`; (5) state completed/started/unlocked; (6) in sequential modules items after the first unmet requirement are locked; (7) persist, and mark dependents stale for this enrollment. Teacher edits bump `rules_version` (lazy invalidation, no batch job). **Policy**: like Canvas, an unlocked module stays unlocked after a later regrade; a teacher action "re-apply rules" clears the cache.

## 8. Enrollment forms, catalog, privacy

- **Modes**: `open`, `invite_code`, `form_auto`, `form_review`, `closed`. Public catalog lists `visibility=catalog` published courses.
- **Forms**: `enrollment_forms(course_id, version, status)` immutable once answered; `enrollment_form_fields(key, type, label LocalizedText, help, options, required, position, pii_category)`; types short/long text, single/multi choice, number, date, email, phone; no files; no special-category data. `enrollment_applications(course_id, user_id, form_id, status, answers JSON, submitted_at, decided_by, decided_at, purge_after)`; approval creates the enrollment. Answers visible only to that course's teachers, never logged or exported, purged 30–90 days after rejection/withdrawal/unenroll (D7).
- **Privacy (schema now, features later; not legal advice)**: `age_band`, append-only `consent_records` (purpose, policy version, proof), `policy_versions`, `data_requests` (export/delete/objection with due dates), and one registry of columns holding personal data. Kyrgyzstan's Digital Code (in force 2026-02-08; per ICNL's secondary summary: under-14 need a guardian's consent, 14+ may consent, consent per purpose, answer objections in 7 working days, cross-border transfer needs a basis). A lawyer must confirm before launch to minors (D5).

## 9. Files and images

Cloudflare R2 (verified 2026-10-21: $0.015/GB-month, 10 GB free, zero egress; Neon bytea costs $0.35/GB-month). Keep `BaseStorageService`, add `R2StorageService` (boto3) and a `files`/`assets` table with sha256 dedupe and soft delete. Uploads are validated by content (not extension), size-capped, EXIF-stripped, re-encoded to WebP (Pillow); no SVG. Public content images via a CDN custom domain (requires DNS on Cloudflare, D2/D3); private files via short presigned GET after a permission check (Canvas pattern). Replaces the ephemeral `/uploads` disk.

## 10. Platform

- **Database**: wipe Neon (testers only) and adopt **Alembic** from a reviewed baseline on empty Postgres, then delete the runtime `ALTER` helpers. Naming convention, batch mode for SQLite dev, CI runs `alembic upgrade head`, `alembic check`, pytest-alembic on Postgres 16; migrations run as a pre-deploy step, not at import.
- **Remove the in-memory Firestore** entirely (all reads and writes), including the sample-question seeding and `firebase.py`; tests stop depending on `mock_firestore_db.reset()`.
- **API**: stay on `/api/v1`; cursor pagination in the response body; consistent error shape.
- **Ops**: stop `print()`-ing payloads; structured logs without PII; Render paid plan for pre-deploy migrations and no spin-down (D4); confirm Vercel Hobby's non-commercial clause fits.
- **Frontend**: new route groups `/[lang]/courses/...` (student view) and teacher studio inside the course (`/[lang]/courses/[id]/manage/...`). Role is no longer a route group; the same user can teach one course and study another. UI strings in `en.json`, `ky.json`, `ru.json` with a CI key-parity check.

## 11. What we deliberately skip (and why)

Accounts/sub-accounts, Pseudonyms, Sections, Terms, custom roles/overrides, Blueprint sync, cross-listing, SpeedGrader and rubrics (essay manual grading is a simple per-item score + feedback in v1), discussions, observers (role reserved), calculated/hot-spot questions, IP filters/lockdown browser, quiz event log, bank sharing, bank/quiz copy-and-sync. Each can be added later without changing the core tables above.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Scope creep toward "all of Canvas" | The skip list above; each phase has an exit test and a stop point. |
| ORT regression | Parity gate: `test_scoring`, `test_math_section_rule`, `test_question_order`, bundle acceptance tests ported before the old code is removed. |
| Authorization mistakes leak data (today's #1 problem) | One `can()`, SQL scopes, route-inventory merge gate, two-teacher isolation suite. |
| Versioned content complicates queries | Always join through `current_version_id` via a single repository module; indexes on version ids. |
| Large rewrite stalls | Phases deliver a usable product slice each; old ORT keeps working until the parity cutover (Phase 5). |
| Legal exposure with minors | Consent schema now; decide minimum age (D5) and get legal review before public launch. |
| Cost | R2/Neon free tiers cover a modeled 5k images/500 students; Render paid plan is the one certain cost. |
