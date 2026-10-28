# Phase 8a UX-gate screenshots

Written by `frontend/e2e/modules.spec.ts` (test 3, `PHASE8A_SCREENS_DIR=docs/phases/PHASE_8A_screens`; test 2 writes the
`ort-review/ort-*` images) against the scratch e2e backend (`scripts/e2e_backend.sh`) and a production build, system
Chrome on macOS, device scale factor 1, time zone UTC, light scheme. Viewports: phone 375x812, desktop 1440x900
(full page unless a dialog is shown). Student screens in en, ky and ru; teacher screens in ru and en. Content titles
written by the teacher (page, file, quiz names) stay in Russian on purpose; module titles are translated.

Course: "Курс модулей E2E" after the modules walk (test 1): M1 page + PDF (completed), M2 quiz with "score at least
80 %" (best 60 % after the teacher override and "Re-apply rules"), M3 sequential with prerequisite M2 (locked), M4 opens
15/12/2026 (locked), M5 open with a page to view (not started).

## Student

| File | What | URL | Size | Lang |
|---|---|---|---|---|
| `student-announcements-desktop-en.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 1440x900 (57 KB) | en |
| `student-announcements-desktop-ky.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 1440x900 (59 KB) | ky |
| `student-announcements-desktop-ru.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 1440x900 (58 KB) | ru |
| `student-announcements-phone-en.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 375x812 (45 KB) | en |
| `student-announcements-phone-ky.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 375x812 (48 KB) | ky |
| `student-announcements-phone-ru.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 375x812 (46 KB) | ru |
| `student-course-home-fallback-desktop-en.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 1440x900 (49 KB) | en |
| `student-course-home-fallback-desktop-ky.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 1440x900 (51 KB) | ky |
| `student-course-home-fallback-desktop-ru.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 1440x900 (48 KB) | ru |
| `student-course-home-fallback-phone-en.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 375x812 (42 KB) | en |
| `student-course-home-fallback-phone-ky.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 375x812 (42 KB) | ky |
| `student-course-home-fallback-phone-ru.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 375x812 (40 KB) | ru |
| `student-course-home-modules-desktop-en.png` | Student course home = modules view: Up next card; M1 completed, M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 1440x900 (115 KB) | en |
| `student-course-home-modules-desktop-ky.png` | Student course home = modules view: Up next card; M1 completed, M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 1440x900 (132 KB) | ky |
| `student-course-home-modules-desktop-ru.png` | Student course home = modules view: Up next card; M1 completed, M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 1440x900 (129 KB) | ru |
| `student-course-home-modules-phone-en.png` | Student course home = modules view: Up next card; M1 completed, M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 375x812 (96 KB) | en |
| `student-course-home-modules-phone-ky.png` | Student course home = modules view: Up next card; M1 completed, M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 375x812 (111 KB) | ky |
| `student-course-home-modules-phone-ru.png` | Student course home = modules view: Up next card; M1 completed, M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 375x812 (109 KB) | ru |
| `student-course-home-page-desktop-en.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 1440x900 (49 KB) | en |
| `student-course-home-page-desktop-ky.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 1440x900 (53 KB) | ky |
| `student-course-home-page-desktop-ru.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 1440x900 (51 KB) | ru |
| `student-course-home-page-phone-en.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 375x812 (38 KB) | en |
| `student-course-home-page-phone-ky.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 375x812 (41 KB) | ky |
| `student-course-home-page-phone-ru.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 375x812 (40 KB) | ru |
| `student-files-desktop-en.png` | Student course files: a PDF at the top level and a folder group | `/{lang}/courses/{courseId}/files` | 1440x900 (49 KB) | en |
| `student-files-desktop-ky.png` | Student course files: a PDF at the top level and a folder group | `/{lang}/courses/{courseId}/files` | 1440x900 (55 KB) | ky |
| `student-files-desktop-ru.png` | Student course files: a PDF at the top level and a folder group | `/{lang}/courses/{courseId}/files` | 1440x900 (51 KB) | ru |
| `student-files-phone-en.png` | Student course files: a PDF at the top level and a folder group | `/{lang}/courses/{courseId}/files` | 375x812 (39 KB) | en |
| `student-files-phone-ky.png` | Student course files: a PDF at the top level and a folder group | `/{lang}/courses/{courseId}/files` | 375x812 (43 KB) | ky |
| `student-files-phone-ru.png` | Student course files: a PDF at the top level and a folder group | `/{lang}/courses/{courseId}/files` | 375x812 (41 KB) | ru |
| `student-home-strip-desktop-en.png` | Student home: Continue in your courses (module next item) and the Announcements strip | `/{lang}/courses` | 1440x900 (93 KB) | en |
| `student-home-strip-desktop-ky.png` | Student home: Continue in your courses (module next item) and the Announcements strip | `/{lang}/courses` | 1440x900 (97 KB) | ky |
| `student-home-strip-desktop-ru.png` | Student home: Continue in your courses (module next item) and the Announcements strip | `/{lang}/courses` | 1440x900 (100 KB) | ru |
| `student-home-strip-phone-en.png` | Student home: Continue in your courses (module next item) and the Announcements strip | `/{lang}/courses` | 375x812 (81 KB) | en |
| `student-home-strip-phone-ky.png` | Student home: Continue in your courses (module next item) and the Announcements strip | `/{lang}/courses` | 375x812 (83 KB) | ky |
| `student-home-strip-phone-ru.png` | Student home: Continue in your courses (module next item) and the Announcements strip | `/{lang}/courses` | 375x812 (86 KB) | ru |
| `student-page-locked-desktop-en.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (40 KB) | en |
| `student-page-locked-desktop-ky.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (42 KB) | ky |
| `student-page-locked-desktop-ru.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (40 KB) | ru |
| `student-page-locked-phone-en.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (30 KB) | en |
| `student-page-locked-phone-ky.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (32 KB) | ky |
| `student-page-locked-phone-ru.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (30 KB) | ru |
| `student-page-math-desktop-en.png` | Student page with Markdown and KaTeX math (translated page in en / ky) | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (49 KB) | en |
| `student-page-math-desktop-ky.png` | Student page with Markdown and KaTeX math (translated page in en / ky) | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (52 KB) | ky |
| `student-page-math-desktop-ru.png` | Student page with Markdown and KaTeX math (translated page in en / ky) | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (51 KB) | ru |
| `student-page-math-phone-en.png` | Student page with Markdown and KaTeX math (translated page in en / ky) | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (38 KB) | en |
| `student-page-math-phone-ky.png` | Student page with Markdown and KaTeX math (translated page in en / ky) | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (41 KB) | ky |
| `student-page-math-phone-ru.png` | Student page with Markdown and KaTeX math (translated page in en / ky) | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (40 KB) | ru |
| `student-quiz-lobby-locked-desktop-en.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 1440x900 (43 KB) | en |
| `student-quiz-lobby-locked-desktop-ky.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 1440x900 (46 KB) | ky |
| `student-quiz-lobby-locked-desktop-ru.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 1440x900 (42 KB) | ru |
| `student-quiz-lobby-locked-phone-en.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 375x812 (33 KB) | en |
| `student-quiz-lobby-locked-phone-ky.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 375x812 (35 KB) | ky |
| `student-quiz-lobby-locked-phone-ru.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 375x812 (32 KB) | ru |

## Teacher

| File | What | URL | Size | Lang |
|---|---|---|---|---|
| `teacher-add-item-desktop-en.png` | Add item dialog (kinds, page list, requirement) | `/{lang}/courses/{courseId}/modules` | 1440x900 (115 KB) | en |
| `teacher-add-item-desktop-ru.png` | Add item dialog (kinds, page list, requirement) | `/{lang}/courses/{courseId}/modules` | 1440x900 (128 KB) | ru |
| `teacher-add-item-phone-en.png` | Add item dialog (kinds, page list, requirement) | `/{lang}/courses/{courseId}/modules` | 375x812 (39 KB) | en |
| `teacher-add-item-phone-ru.png` | Add item dialog (kinds, page list, requirement) | `/{lang}/courses/{courseId}/modules` | 375x812 (45 KB) | ru |
| `teacher-announcement-compose-desktop-en.png` | Compose announcement with Markdown preview (math) | `/{lang}/courses/{courseId}/announcements/new` | 1440x900 (77 KB) | en |
| `teacher-announcement-compose-desktop-ru.png` | Compose announcement with Markdown preview (math) | `/{lang}/courses/{courseId}/announcements/new` | 1440x900 (84 KB) | ru |
| `teacher-announcement-compose-phone-en.png` | Compose announcement with Markdown preview (math) | `/{lang}/courses/{courseId}/announcements/new` | 375x812 (55 KB) | en |
| `teacher-announcement-compose-phone-ru.png` | Compose announcement with Markdown preview (math) | `/{lang}/courses/{courseId}/announcements/new` | 375x812 (60 KB) | ru |
| `teacher-announcements-desktop-en.png` | Teacher announcements list (pinned, posted) | `/{lang}/courses/{courseId}/announcements` | 1440x900 (80 KB) | en |
| `teacher-announcements-desktop-ru.png` | Teacher announcements list (pinned, posted) | `/{lang}/courses/{courseId}/announcements` | 1440x900 (87 KB) | ru |
| `teacher-announcements-phone-en.png` | Teacher announcements list (pinned, posted) | `/{lang}/courses/{courseId}/announcements` | 375x812 (57 KB) | en |
| `teacher-announcements-phone-ru.png` | Teacher announcements list (pinned, posted) | `/{lang}/courses/{courseId}/announcements` | 375x812 (63 KB) | ru |
| `teacher-files-desktop-en.png` | Teacher course files list | `/{lang}/courses/{courseId}/files` | 1440x900 (75 KB) | en |
| `teacher-files-desktop-ru.png` | Teacher course files list | `/{lang}/courses/{courseId}/files` | 1440x900 (80 KB) | ru |
| `teacher-files-phone-en.png` | Teacher course files list | `/{lang}/courses/{courseId}/files` | 375x812 (52 KB) | en |
| `teacher-files-phone-ru.png` | Teacher course files list | `/{lang}/courses/{courseId}/files` | 375x812 (55 KB) | ru |
| `teacher-files-upload-desktop-en.png` | Upload file dialog | `/{lang}/courses/{courseId}/files` | 1440x900 (95 KB) | en |
| `teacher-files-upload-desktop-ru.png` | Upload file dialog | `/{lang}/courses/{courseId}/files` | 1440x900 (106 KB) | ru |
| `teacher-files-upload-phone-en.png` | Upload file dialog | `/{lang}/courses/{courseId}/files` | 375x812 (43 KB) | en |
| `teacher-files-upload-phone-ru.png` | Upload file dialog | `/{lang}/courses/{courseId}/files` | 375x812 (47 KB) | ru |
| `teacher-module-settings-desktop-en.png` | Module settings dialog (title, opening date, sequential) | `/{lang}/courses/{courseId}/modules` | 1440x900 (114 KB) | en |
| `teacher-module-settings-desktop-ru.png` | Module settings dialog (title, opening date, sequential) | `/{lang}/courses/{courseId}/modules` | 1440x900 (124 KB) | ru |
| `teacher-module-settings-phone-en.png` | Module settings dialog (title, opening date, sequential) | `/{lang}/courses/{courseId}/modules` | 375x812 (50 KB) | en |
| `teacher-module-settings-phone-ru.png` | Module settings dialog (title, opening date, sequential) | `/{lang}/courses/{courseId}/modules` | 375x812 (55 KB) | ru |
| `teacher-outline-desktop-en.png` | Teacher module outline: five modules, items, requirements, publish switches, reorder, actions | `/{lang}/courses/{courseId}/modules` | 1440x900 (180 KB) | en |
| `teacher-outline-desktop-ru.png` | Teacher module outline: five modules, items, requirements, publish switches, reorder, actions | `/{lang}/courses/{courseId}/modules` | 1440x900 (200 KB) | ru |
| `teacher-outline-empty-desktop-en.png` | Teacher module outline, empty course | `/{lang}/courses/{courseId}/modules` | 1440x900 (61 KB) | en |
| `teacher-outline-empty-desktop-ru.png` | Teacher module outline, empty course | `/{lang}/courses/{courseId}/modules` | 1440x900 (66 KB) | ru |
| `teacher-outline-empty-phone-en.png` | Teacher module outline, empty course | `/{lang}/courses/{courseId}/modules` | 375x812 (38 KB) | en |
| `teacher-outline-empty-phone-ru.png` | Teacher module outline, empty course | `/{lang}/courses/{courseId}/modules` | 375x812 (41 KB) | ru |
| `teacher-outline-phone-en.png` | Teacher module outline: five modules, items, requirements, publish switches, reorder, actions | `/{lang}/courses/{courseId}/modules` | 375x812 (158 KB) | en |
| `teacher-outline-phone-ru.png` | Teacher module outline: five modules, items, requirements, publish switches, reorder, actions | `/{lang}/courses/{courseId}/modules` | 375x812 (177 KB) | ru |
| `teacher-page-editor-desktop-en.png` | Page editor with server-rendered math preview | `/{lang}/courses/{courseId}/pages/{pageId}/edit` | 1440x900 (110 KB) | en |
| `teacher-page-editor-desktop-ru.png` | Page editor with server-rendered math preview | `/{lang}/courses/{courseId}/pages/{pageId}/edit` | 1440x900 (121 KB) | ru |
| `teacher-page-editor-phone-en.png` | Page editor with server-rendered math preview | `/{lang}/courses/{courseId}/pages/{pageId}/edit` | 375x812 (84 KB) | en |
| `teacher-page-editor-phone-ru.png` | Page editor with server-rendered math preview | `/{lang}/courses/{courseId}/pages/{pageId}/edit` | 375x812 (92 KB) | ru |
| `teacher-pages-desktop-en.png` | Teacher pages list | `/{lang}/courses/{courseId}/pages` | 1440x900 (108 KB) | en |
| `teacher-pages-desktop-ru.png` | Teacher pages list | `/{lang}/courses/{courseId}/pages` | 1440x900 (121 KB) | ru |
| `teacher-pages-phone-en.png` | Teacher pages list | `/{lang}/courses/{courseId}/pages` | 375x812 (116 KB) | en |
| `teacher-pages-phone-ru.png` | Teacher pages list | `/{lang}/courses/{courseId}/pages` | 375x812 (126 KB) | ru |
| `teacher-prerequisites-desktop-en.png` | Prerequisites dialog for module 3 | `/{lang}/courses/{courseId}/modules` | 1440x900 (115 KB) | en |
| `teacher-prerequisites-desktop-ru.png` | Prerequisites dialog for module 3 | `/{lang}/courses/{courseId}/modules` | 1440x900 (125 KB) | ru |
| `teacher-prerequisites-phone-en.png` | Prerequisites dialog for module 3 | `/{lang}/courses/{courseId}/modules` | 375x812 (49 KB) | en |
| `teacher-prerequisites-phone-ru.png` | Prerequisites dialog for module 3 | `/{lang}/courses/{courseId}/modules` | 375x812 (54 KB) | ru |
| `teacher-progress-desktop-en.png` | Student progress drawer for one student | `/{lang}/courses/{courseId}/modules` | 1440x900 (131 KB) | en |
| `teacher-progress-desktop-ru.png` | Student progress drawer for one student | `/{lang}/courses/{courseId}/modules` | 1440x900 (140 KB) | ru |
| `teacher-progress-phone-en.png` | Student progress drawer for one student | `/{lang}/courses/{courseId}/modules` | 375x812 (48 KB) | en |
| `teacher-progress-phone-ru.png` | Student progress drawer for one student | `/{lang}/courses/{courseId}/modules` | 375x812 (54 KB) | ru |
| `teacher-requirement-desktop-en.png` | Requirement picker for the quiz item (score at least 80 %) | `/{lang}/courses/{courseId}/modules` | 1440x900 (110 KB) | en |
| `teacher-requirement-desktop-ru.png` | Requirement picker for the quiz item (score at least 80 %) | `/{lang}/courses/{courseId}/modules` | 1440x900 (120 KB) | ru |
| `teacher-requirement-phone-en.png` | Requirement picker for the quiz item (score at least 80 %) | `/{lang}/courses/{courseId}/modules` | 375x812 (43 KB) | en |
| `teacher-requirement-phone-ru.png` | Requirement picker for the quiz item (score at least 80 %) | `/{lang}/courses/{courseId}/modules` | 375x812 (47 KB) | ru |
| `teacher-settings-home-desktop-en.png` | Course settings: Course home section (modules / page / assignments) | `/{lang}/courses/{courseId}/settings` | 1440x900 (58 KB) | en |
| `teacher-settings-home-desktop-ru.png` | Course settings: Course home section (modules / page / assignments) | `/{lang}/courses/{courseId}/settings` | 1440x900 (66 KB) | ru |
| `teacher-settings-home-phone-en.png` | Course settings: Course home section (modules / page / assignments) | `/{lang}/courses/{courseId}/settings` | 375x812 (42 KB) | en |
| `teacher-settings-home-phone-ru.png` | Course settings: Course home section (modules / page / assignments) | `/{lang}/courses/{courseId}/settings` | 375x812 (46 KB) | ru |

## ORT review (`ort-review/`)

See `ort-review/README.md` for the ORT baseline comparison (before / after / diff of the teacher baselines).

| File | What | URL | Size | Lang |
|---|---|---|---|---|
| `ort-review/ort-student-course-home-before-desktop-ru.png` | ORT (Russian) student course home before any structure: no new tabs | `/{lang}/courses/{courseId}` | 1440x900 (54 KB) | ru |
| `ort-review/ort-student-course-home-before-phone-ru.png` | ORT (Russian) student course home before any structure: no new tabs | `/{lang}/courses/{courseId}` | 375x812 (45 KB) | ru |
| `ort-review/ort-student-course-home-with-structure-desktop-ru.png` | ORT student course home with a published module and file: Modules and Files tabs appear, home unchanged | `/{lang}/courses/{courseId}` | 1440x900 (56 KB) | ru |
| `ort-review/ort-student-course-home-with-structure-phone-ru.png` | ORT student course home with a published module and file: Modules and Files tabs appear, home unchanged | `/{lang}/courses/{courseId}` | 375x812 (45 KB) | ru |
| `ort-review/ort-student-modules-desktop-ru.png` | ORT student modules view: module with the ORT exam locked by date (the exam still starts) | `/{lang}/courses/{courseId}/modules` | 1440x900 (47 KB) | ru |
| `ort-review/ort-student-modules-phone-ru.png` | ORT student modules view: module with the ORT exam locked by date (the exam still starts) | `/{lang}/courses/{courseId}/modules` | 375x812 (35 KB) | ru |
| `ort-review/ort-teacher-course-home-after-desktop-ru.png` | ORT staff course home: Modules, Pages, Files, Announcements tabs (owner Q5 default) | `/{lang}/courses/{courseId}` | 1440x900 (121 KB) | ru |
| `ort-review/ort-teacher-course-home-after-phone-ru.png` | ORT staff course home: Modules, Pages, Files, Announcements tabs (owner Q5 default) | `/{lang}/courses/{courseId}` | 375x812 (98 KB) | ru |
