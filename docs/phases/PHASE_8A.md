# Phase 8a: course structure (modules, pages, course files, announcements, gating)

**Status**: built 2026-10-28 on `phase-8a`; deploy details at the end. Design: `PHASE_8A_DESIGN.md`. Decisions: `PRODUCT_DECISIONS.md` "Phase 8a decisions" (owner questions 8a-Q1…Q5 with defaults in effect, P8A-1…P8A-9).

## What teachers and students get
- **Modules**: teachers build an outline of modules with items (page, PDF file, assignment or quiz, link, header). Each item can carry a requirement (view, mark done, submit, minimum score or percent). Modules can have prerequisites, an unlock date and a sequential order. "New quiz" inside a module opens the Phase 7c quiz editor. Warnings cover hidden items and requirements on a draft quiz, including a confirm before publishing such a module. "Re-apply rules" relocks after a rule change.
- **Students** see each module as completed, in progress, not started, or locked with plain reasons ("Finish “Module 2” first", "Opens 15/12/2026, 09:00"). Locked pages, files, assignments and quiz lobbies show a friendly locked screen with a way back to Modules. A course home can be Modules, a page or the assignments list. The student home shows "up next" (deduplicated) and the latest announcements.
- **Pages**: Markdown with formulas (KaTeX), images and footnotes, in the course's languages (variants), sanitized on the server.
- **Course files**: PDFs with folders and publish switches (10 MiB each, 500 MiB per course, inside the R2 free-tier guard).
- **Announcements**: draft, publish, pin; a student list and the home strip.

## ORT
- ORT exam, player, import and scoring are unchanged. ORT exams are never gated by modules: they stay startable and show "Available from Assignments" inside a locked module.
- The ORT course home is locked to today's layout. Staff see the new tabs in ORT courses (owner question 8a-Q5, default "allowed"); students see them only once something is published.
- ORT student screenshots are identical to production. ORT teacher baselines were re-recorded for the new tabs (before/after in `PHASE_8A_screens/ort-review/`; dated note in `ORT_BASELINE/README.md`). The importers diff is empty.

## Schema
Migration `0012_phase8a_course_structure`:
- `courses.home_kind`, `home_page_id`;
- `pages`, `course_modules`, `module_prerequisites`, `module_items`, `item_completion_requirements`, `item_progress`, `module_progress`, `item_requirement_status`, `course_files`, `announcements`.

No data steps. New backend dependencies: `Markdown==3.11.1`, `nh3==0.3.7`.

## Reviews
- **Security and gating review** (architect): no high findings. Fixed: M1 (requirement change inherited "met"), M2 (locked quiz lobby readable), L1 (locked link destinations), L2 (undo of mark-done), L3 (hand-in upload gate), L5 (footnote links). L4 and L6 were documented.
- **UX gate** (ux-reviewer): B1 (Markdown headings and lists unstyled), M1–M7 and 12 minor findings, all fixed. Screens: `PHASE_8A_screens/` (`INDEX.md`).

## Tests
- Backend:
  - `tests/lms/test_modules_*.py`, `test_pg_concurrency_modules.py`, `test_modules_fix1.py`;
  - `test_pages_*.py` (with the render golden file of XSS vectors), `test_course_files.py`, `test_announcements.py`, `test_course_home_kind.py`;
  - `tests/test_migration_0012.py`.
- Frontend: `frontend/e2e/modules.spec.ts`:
  - the full teacher → student walkthrough;
  - the ORT proof;
  - the screenshot run.

## Deploy
(filled in after the gates and the deploy)
