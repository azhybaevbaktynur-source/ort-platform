# Phase 7a: assignments and the general gradebook

**Status**: **deployed 2026-10-26** (`main` 95b040f; Render /health OK; Neon at `0009_phase7a_assignments`, verified: 3 assessments with 3 quiz assignments, the one real submission on its assignment with unchanged values, 299 question versions, 4 attempts). Backup: Neon branch `backup-2026-10-26-before-phase7a` (after deleting `rehearsal-2026-10-23-phase5`, owner OK). No owner checkpoint for 7a; the next one is after 7b. Design: `docs/phases/PHASE_7A_DESIGN.md`. Open owner questions with the defaults in effect: `docs/PRODUCT_DECISIONS.md` "Phase 7a: open owner questions" (Q1–Q6).

## What changed

| Area | Change |
|---|---|
| Assignments | The assignment is the gradable unit. Kinds: **quiz** (an assessment; graded from attempts exactly as before), **text** and **file** hand-ins, **none** (graded without a hand-in, e.g. an oral exam). Points, due date, availability window, category, grading scheme version, grade release, published, order, soft delete. Every existing assessment got its quiz assignment in migration `0009_phase7a_assignments` (deterministic ids; the assessment stays the source of truth and the assignment mirrors it). |
| Hand-ins | Text (up to 20,000 characters) or one file (PDF, JPEG, PNG, WebP; 5 MB per file; 500 MB per course; private bucket; file type checked by content). Resubmission keeps every hand-in (append-only); a resubmission after an unreleased grade goes back to "needs grading". Late hand-ins are marked and the late policy applies. |
| Grading | Grading screen per assignment: roster with status, previous/next (Alt+↑/↓), rubric (criteria × points), feedback text and an optional feedback file, grade release (publish / hide). Manual grades write append-only `manual_grade` events. The gradebook has one column per assignment with categories, weights and totals. |
| Accommodations | Per student for the whole course (extra time, extra attempts) and per-assignment exceptions (due date, window, attempts), applied when an attempt starts and in lateness. Only course teachers set them; every change is audited. **ORT**: extra time is stored but not applied to ORT exams until the owner decides (Q1). |
| Access codes | A quiz may require an access code (at least 6 characters, stored as a hash only, never shown again; rate-limited per student and exam and per IP). Not available on ORT exams (Q4). |
| Student side | "Assignments" tab with status, due date and one next action; hand-in page with a late warning; grade and feedback after release; the student home lists assignments. |
| Naming | "Задания / Тапшырмалар / Assignments" (all gradable work) vs "Тесты / Тесттер / Quizzes" (assessments); grade release "опубликовать / скрыть" (glossary in `UX_GUIDELINES.md` §5). |

## ORT review

**Function unchanged** — proven by:
- `tests/lms/test_ort_gradebook_golden.py`: the ORT gradebook (raw, scaled, percentile, sections, totals, release) captured **before any 7a code** equals the 7a result.
- The ORT tests (`test_ort_import_golden.py`, `test_ort_e2e_api.py`, `test_ort_parity.py`, `test_ort_seed.py`, `test_ort_cutover_flow.py`) unchanged and green.
- ORT browser suite (`frontend/e2e/`): both specs green twice, zero screenshot differences (the access-code field is hidden for ORT exams, so no baseline changed).
- Walkthrough (`docs/phases/PHASE_7_screens/7a/WALKTHROUGH.md`, 40/40 steps): the ORT exam appears in the ORT course as its assignment ("Экзамен ОРТ"), the lobby, player and result are as before, and the result and gradebook numbers match the reference attempt.

**Visible in ORT courses**: the ORT exam is listed under "Задания"; staff cannot add homework assignments there (Q5); the staff gradebook is unchanged (Q6).

## How to verify

```bash
# Backend (AGENTS.md §5): SQLite ~2811 passed, 27 skipped; PG ~2868 passed; alembic head 0009_phase7a_assignments, `alembic check` clean.
# ORT browser suite: docs/phases/ORT_BASELINE/README.md
```
Rehearsal on a copy of production (the 2026-10-25 dump, 0007 → 0008 → 0009, plus production's one real submission replayed): `backend/scripts/check_0009.py` passes (every assessment has its quiz assignment, no submission or grade event without an assignment, mirrored columns equal, the replayed submission keeps its numbers).

UX gate: `docs/phases/PHASE_7_screens/7a/` (INDEX.md), ux-reviewer findings fixed. Security review: one high (quiz results policy bypass on the student assignment views) and six lower findings, all fixed with tests.

## Deferred

- Inline PDF preview while grading; one Save for the assignment form and its rubric; one student list (the `/assessments` page will redirect to assignments); "next due" label on course cards; access-code hint wording.
- Linux screenshot baselines for CI (unchanged policy).

## Owner items

- Q1 (extra time on ORT exams), Q2 (upload storage), Q3 (who sets accommodations), Q4 (access codes on ORT), Q5 (homework in ORT courses), Q6 (ORT gradebook total column) — defaults in `PRODUCT_DECISIONS.md`.
- Neon branch limit (10) reached; the pre-deploy backup is a snapshot.
