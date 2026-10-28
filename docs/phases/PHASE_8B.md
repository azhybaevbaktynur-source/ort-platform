# Phase 8b: exam templates II (visual constructor, sample questions with preview, scrolling display mode)

**Status**: built 2026-10-28 on `phase-8b`; deploy details at the end. Design: `PHASE_8B_DESIGN.md`. Decisions: `PRODUCT_DECISIONS.md` "Phase 8b decisions" (owner questions 8b-Q1…Q6 with defaults in effect, P8B-1…P8B-11). **Owner checkpoint follows this phase.**

## What platform admins, org admins and teachers get
- **Visual constructor for exam templates** at three places: platform admin, organization admin, and the teacher's own templates in Teaching. It has five tabs.
  - **Structure**: sections with order, name, min/max question count, time limit, allowed question types, passage rule and display.
  - **Scoring**: a grading scheme with the live score table.
  - **Display**: navigation, display mode, result view, passage display, and what the lock fixes.
  - **Sample questions**: written with the 7c card editor. "Preview" opens the real player as a student would see it, with a way back to the template.
  - **Versions**: a list with a readable diff. Publish, archive, lock and unlock, promote a teacher's template to the organization, and download the import format.
- **Saving**: valid drafts autosave. Problems show next to their fields, with a "Go to" link. A conflict dialog appears when two tabs edit the same template.
- **Teachers** create exams from a template ("Create from template"). The template's locks and allowed question types apply. A new template version never changes exams created earlier.
- **Scrolling display mode** in the general player shows a whole section as a list, in windows of 30. The current question follows the scroll. The palette, keyboard shortcuts, autosave and timers work as before.
- **Display settings on general quizzes**: display mode, passage display and result view, respecting template locks.

## ORT
ORT is unchanged:
- ORT exams resolve to one question per page, numbered passages and the ORT result view.
- ORT stays on its presets (8b-Q6).
- ORT screenshots are zero-diff on every run, and the importers diff is empty.

## Schema
Migration `0013_phase8b_template_sandbox` adds `courses.sandbox_for_template_id`: a hidden sandbox course per template holds its sample questions. There are no data steps.

## Reviews
- **Security review** (architect) found no high findings. Fixed:
  - M1: stale sandbox access after a manager lost rights. Access is now rechecked on every request.
  - M2: course transfer and restore of a sandbox.
  - L1: publish and create inside a sandbox.
  - L2: diff on an old stored version.
  - L3: rate limit on opening the sandbox.
  - L4: course-structure writes inside a sandbox.
  - Later also hand-in assignments inside a sandbox.
- **UX gate** (ux-reviewer): 7 major and 9 minor findings, fixed in `phase-8b-ux`. Screens are in `PHASE_8B_screens/` (`INDEX.md`).

## Tests
- Backend:
  - `test_exam_template_sandbox.py`, `test_exam_template_sandbox_fixes.py`, `test_spec_diff.py`
  - `test_pg_concurrency_sandbox.py`, `test_sandbox_hidden_from_lists.py`
  - `test_attempt_display_resolver.py`, `test_assessment_display_settings.py`
  - `test_constructor_blocks_contract.py`, `tests/test_migration_0013.py`
- Frontend:
  - `frontend/e2e/exam-constructor.spec.ts`: design, preview, publish, diff, lock, then a teacher creates an exam, a student takes it on desktop and phone, v2 leaves v1 exams alone, and promote.
  - `frontend/e2e/scrolling-player.spec.ts`: 48 items, windowing, palette, keyboard, forward-only, 375 px, return link safety.

## Deploy
(filled in after the gates and the deploy)
