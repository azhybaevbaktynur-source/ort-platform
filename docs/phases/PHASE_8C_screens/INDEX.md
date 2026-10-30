# Phase 8c UX-gate screenshots (PHASE_8C_DESIGN section 15)

Recorded by `frontend/e2e/phase8c-screens.spec.ts` (`PHASE8C_SCREENS_DIR=docs/phases/PHASE_8C_screens`) against the
merged S1 + S2 + S3 branch, re-shot after the UX fix slice (`phase-8c-ux`, findings M1-M7, m1-m10) with the
same names. Name: `<screen>-<viewport>-<lang>.png`; `phone` = 375x812, `desktop` = 1440x900 (viewport
shots; `*-full` = full page). Teacher screens: ru and en. Student screens: en, ky, ru. ORT course page: ru.
ORT before/after evidence is in `ort-before-after/` (README there).

| Screen | Files (`teacher-` / `student-` prefix) |
|---|---|
| Sidebar (desktop) / phone drawer | `teacher-sidebar` (desktop), `teacher-drawer` (phone, on the empty course so the "hidden from students" marks show), `student-drawer` (phone); the sidebar is also visible in every desktop `*-course*` shot |
| Course page, empty / filled | `teacher-course-empty`, `teacher-course-filled`, `teacher-course-filled-full` |
| Grouped "+ Add" (desktop popover, phone bottom sheet) | `teacher-add-menu` |
| "..." menus (module, item) | `teacher-module-menu`, `teacher-item-menu` (Publish / Unpublish first, Delete / Remove last in red after a separator; phone sheet titled with the module name) |
| Unsorted ("Not in a module") | `teacher-unsorted` |
| To do panel (desktop, right column) and phone line | `teacher-course-filled` (desktop), `teacher-todo-collapsed`, `teacher-todo-expanded` (phone) |
| ORT Course page (exam list at full width, To do as the one-line form above it, collapsed structure) | `teacher-ort-course`, `teacher-ort-course-full` (ru) |
| Assignment page tabs | `teacher-assignment-details`, `-submissions` (`filter=to_grade`), `-settings`; quiz: `teacher-quiz-details`, `teacher-quiz-results` |
| Page object tabs | `teacher-page-edit`, `teacher-page-preview` |
| Assignments list, quiz filter | `teacher-assignments-quiz-filter` |
| Student view | `student-view-banner`, `student-view-handins-off` (owner teacher, 8c fix 2; en, ky, ru) |
| "Not available" page | `student-not-available` |
| Student course page, auto-hidden links | `student-course` (all links, content published), `student-course-hidden-links` (a course with nothing published: no Announcements / Files) |

Not shown as an image: the refused write in Student view. No screen of the app writes in that mode (forms are
hidden); the 403 `student_view_read_only` is asserted in `course-nav.spec.ts`.
