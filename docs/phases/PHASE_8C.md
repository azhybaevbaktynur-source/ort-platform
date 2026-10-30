# Phase 8c: teacher navigation redesign

**Status**: built on `phase-8c`, 2026-10-31. Deploy details are at the end.

**References**
- Proposal (owner-approved v3): `PHASE_8C_NAVIGATION_PROPOSAL.md`.
- Design: `PHASE_8C_DESIGN.md`.
- Decisions: `PRODUCT_DECISIONS.md` (8c-1 to 8c-9, P8C-1).

The owner chose no pause for the teacher test (8c-9). The test is optional after this release, and its findings will become a follow-up slice.

## What teachers get

**Short left course menu.** It replaces the 11 tabs:
- Course
- Announcements
- Assignments
- Grades
- People
- Question banks
- Settings
- Files

On phones the menu becomes a "Course menu" drawer. Students do not see links to areas with nothing published. Teachers see those links marked "hidden from students", and a direct link to a hidden area shows a friendly "not available" page. The Teaching sub-menu is gone inside courses.

**The course page is the course.** It shows the modules outline:
- each module has a grouped "+ Add" menu: Content (page, file, link, header) and Assessment (quiz, assignment);
- "+ Add" for a quiz opens the question builder directly, and Back returns to the module;
- an "Unsorted" group holds items that are in no module, with "Move to module…";
- a **To do** panel shows what to grade (linking straight to the submissions to grade), drafts, the join code and active students.

**Lighter controls.**
- A publish icon, with a toast confirming each change.
- One "⋯" menu per module and per item. It includes Publish/Unpublish, Open and Item settings, and delete entries are marked as dangerous.
- Drag to reorder on desktop. The move entries in the menu are the alternative on phones and for keyboard users.
- Modules can be duplicated.

**No separate Tests list.** Quizzes live in Assignments (filter "Type: quiz") and in Modules. Old links redirect.

**One page per object.**
- Assignment: Details · Submissions (Results for quizzes) · Settings.
- Page: Edit · Preview.
- Quiz: as in 7c.
- Close returns to where the teacher came from.

**Student view.** A read-only preview of the course exactly as a new student sees it, including module locks. Every change is refused, except starting a preview attempt. It works for every enrolled teacher and assistant, including independent teachers, who are org admins of their personal organization. Org-admin powers are switched off while in Student view.

## ORT
- **Unchanged:** the ORT exam, player, bank, builder content, import, scoring and results.
- **Changed frame only:** the left menu replaces the tabs, and the crumb is one level up. Seventeen frame-affected ORT baselines were re-recorded with owner-approved frame changes; before/after images are in `PHASE_8C_screens/ort-before-after/`.
- Player, result and review screens are pixel-identical.
- The ORT Course page keeps the exam list at full width, with To do as one line above it.

## Backend
There is no migration.

New endpoints:
- `GET _C/modules/unsorted`
- `GET _C/todo`
- `POST _C/modules/{id}/duplicate`

Student view uses the `X-View-As: student` header. `core/authz.py` matches it by route template, which covers every course-id spelling. FastAPI is pinned to `==0.141.1` (P8C-1).

## Reviews
- **Security review of Student view (architect).** It found one medium issue, fixed: some course-id spellings bypassed the header. It also found two lows, fixed: inventory labels, and the suspended-org precedence.
- **Integration (S4a).** It found that Student view did not apply to org admins, which covers every independent teacher. This was fixed in fix2.
- **UX gate (ux-reviewer).** There were no blockers, and the structure was confirmed simpler. Seven major and ten minor findings were all fixed in `phase-8c-ux`. Screens are in `PHASE_8C_screens/` (`INDEX.md`).

## Tests
**Backend:**
- `test_student_view.py` (20 tests)
- `test_course_nav_backend.py`
- `test_todo.py`
- `test_module_duplicate.py`
- PG concurrency: duplicate against reorder

**Frontend:**
- `frontend/e2e/course-nav.spec.ts` covers the sidebar and drawer, auto-hide, the "not available" page, redirects, Student view (assistant and owner teacher), the To do deep link, Unsorted, and "+ Add" quiz.
- These existing specs were updated for the new navigation: `modules`, `quiz-editor`, `exam-constructor`, `scrolling-player`, `ort` and `ort-visual`.

## Deploy
- Gates on merged `phase-8c` (a43853d + report): SQLite 3491 passed / 42 skipped; PG 3560 passed / 22 skipped; fresh PG `alembic upgrade head && alembic check` clean (head stays 0013); PG migration tests 36 passed; importers diff empty; i18n parity OK (3765 keys); `tsc` clean; `next build` OK; e2e `course-nav`, `modules`, `quiz-editor`, `exam-constructor`, `scrolling-player`, `ort`, `ort-visual` green twice (ORT zero diffs against the re-recorded frame baselines).
- No Neon backup branch: no model, migration or DB file changed (rule 7); Neon branch slots 9/10.
- `phase-8c` → `lms` (d42a41f) → `main` (ff508a8). `/health` = ff508a8 (backend reinstalled with `fastapi==0.141.1`); Neon `alembic_version` = `0013_phase8b_template_sandbox`; data intact (300 question versions, 2 ORT exams, 3 courses).
