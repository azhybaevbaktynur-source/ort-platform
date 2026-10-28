# Phase 8a UX-gate screenshots

Written by `frontend/e2e/modules.spec.ts` (test 3, `PHASE8A_SCREENS_DIR=docs/phases/PHASE_8A_screens`; test 2 writes the
`ort-review/ort-*` images) against the scratch e2e backend (`scripts/e2e_backend.sh`) and a production build, system
Chrome on macOS, device scale factor 1, time zone UTC, light scheme. Viewports: phone 375x812, desktop 1440x900
(full page unless a dialog is shown). Student screens in en, ky and ru; teacher screens in ru and en. Content titles
written by the teacher (page, file, quiz names) stay in Russian on purpose; module titles are translated.

Course: "Курс модулей E2E" after the modules walk (test 1): M1 page + PDF (completed), M2 quiz with "score at least
80 %" (best 60 % after the teacher override and "Re-apply rules"), M3 sequential with prerequisite M2 (locked), M4 opens
15/12/2026 (locked), M5 open with a page to view (not started) and a draft quiz with "score at least 80 %" (teacher
only: the "Quiz not published" warning).

Re-taken 2026-10-28 after the 8a UX fixes (branch `phase-8a-ux`: B1 page typography, M1-M7, minor 1-12); every
image below is from that run.

## Student

| File | What | URL | Size | Lang |
|---|---|---|---|---|
| `student-announcements-desktop-en.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 1440x900 (57 KB) | en |
| `student-announcements-desktop-ky.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 1440x900 (60 KB) | ky |
| `student-announcements-desktop-ru.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 1440x900 (58 KB) | ru |
| `student-announcements-phone-en.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 375x812 (46 KB) | en |
| `student-announcements-phone-ky.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 375x812 (48 KB) | ky |
| `student-announcements-phone-ru.png` | Student announcements: pinned announcement and a posted one with math | `/{lang}/courses/{courseId}/announcements` | 375x812 (47 KB) | ru |
| `student-course-home-fallback-desktop-en.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 1440x900 (49 KB) | en |
| `student-course-home-fallback-desktop-ky.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 1440x900 (51 KB) | ky |
| `student-course-home-fallback-desktop-ru.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 1440x900 (49 KB) | ru |
| `student-course-home-fallback-phone-en.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 375x812 (42 KB) | en |
| `student-course-home-fallback-phone-ky.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 375x812 (43 KB) | ky |
| `student-course-home-fallback-phone-ru.png` | Course home = modules without published modules: falls back to the assignments home (quiz-editor course) | `/{lang}/courses/{courseId}` | 375x812 (40 KB) | ru |
| `student-course-home-modules-desktop-en.png` | Student course home = modules view: Up next card; M1 completed (file row says Download), M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 1440x900 (116 KB) | en |
| `student-course-home-modules-desktop-ky.png` | Student course home = modules view: Up next card; M1 completed (file row says Download), M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 1440x900 (132 KB) | ky |
| `student-course-home-modules-desktop-ru.png` | Student course home = modules view: Up next card; M1 completed (file row says Download), M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 1440x900 (130 KB) | ru |
| `student-course-home-modules-phone-en.png` | Student course home = modules view: Up next card; M1 completed (file row says Download), M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 375x812 (97 KB) | en |
| `student-course-home-modules-phone-ky.png` | Student course home = modules view: Up next card; M1 completed (file row says Download), M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 375x812 (113 KB) | ky |
| `student-course-home-modules-phone-ru.png` | Student course home = modules view: Up next card; M1 completed (file row says Download), M2 in progress (best 60 % of 80 %), M3 locked until M2 is finished (prerequisite), M4 locked until 15/12/2026, M5 open and not started | `/{lang}/courses/{courseId}` | 375x812 (111 KB) | ru |
| `student-course-home-page-desktop-en.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 1440x900 (51 KB) | en |
| `student-course-home-page-desktop-ky.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 1440x900 (54 KB) | ky |
| `student-course-home-page-desktop-ru.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 1440x900 (53 KB) | ru |
| `student-course-home-page-phone-en.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 375x812 (41 KB) | en |
| `student-course-home-page-phone-ky.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 375x812 (43 KB) | ky |
| `student-course-home-page-phone-ru.png` | Course home set to a page: the student course opens on the page | `/{lang}/courses/{courseId}` | 375x812 (42 KB) | ru |
| `student-files-desktop-en.png` | Student course files: a PDF without a folder ("Without folder" group) and a folder group | `/{lang}/courses/{courseId}/files` | 1440x900 (50 KB) | en |
| `student-files-desktop-ky.png` | Student course files: a PDF without a folder ("Without folder" group) and a folder group | `/{lang}/courses/{courseId}/files` | 1440x900 (55 KB) | ky |
| `student-files-desktop-ru.png` | Student course files: a PDF without a folder ("Without folder" group) and a folder group | `/{lang}/courses/{courseId}/files` | 1440x900 (51 KB) | ru |
| `student-files-phone-en.png` | Student course files: a PDF without a folder ("Without folder" group) and a folder group | `/{lang}/courses/{courseId}/files` | 375x812 (40 KB) | en |
| `student-files-phone-ky.png` | Student course files: a PDF without a folder ("Without folder" group) and a folder group | `/{lang}/courses/{courseId}/files` | 375x812 (43 KB) | ky |
| `student-files-phone-ru.png` | Student course files: a PDF without a folder ("Without folder" group) and a folder group | `/{lang}/courses/{courseId}/files` | 375x812 (41 KB) | ru |
| `student-home-strip-desktop-en.png` | Student home: hero and Next up; a module step that is already the hero or a Next up row is not repeated (8a UX M4); Announcements below Latest results | `/{lang}/courses` | 1440x900 (79 KB) | en |
| `student-home-strip-desktop-ky.png` | Student home: hero and Next up; a module step that is already the hero or a Next up row is not repeated (8a UX M4); Announcements below Latest results | `/{lang}/courses` | 1440x900 (83 KB) | ky |
| `student-home-strip-desktop-ru.png` | Student home: hero and Next up; a module step that is already the hero or a Next up row is not repeated (8a UX M4); Announcements below Latest results | `/{lang}/courses` | 1440x900 (85 KB) | ru |
| `student-home-strip-phone-en.png` | Student home: hero and Next up; a module step that is already the hero or a Next up row is not repeated (8a UX M4); Announcements below Latest results | `/{lang}/courses` | 375x812 (68 KB) | en |
| `student-home-strip-phone-ky.png` | Student home: hero and Next up; a module step that is already the hero or a Next up row is not repeated (8a UX M4); Announcements below Latest results | `/{lang}/courses` | 375x812 (71 KB) | ky |
| `student-home-strip-phone-ru.png` | Student home: hero and Next up; a module step that is already the hero or a Next up row is not repeated (8a UX M4); Announcements below Latest results | `/{lang}/courses` | 375x812 (73 KB) | ru |
| `student-page-locked-desktop-en.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (39 KB) | en |
| `student-page-locked-desktop-ky.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (43 KB) | ky |
| `student-page-locked-desktop-ru.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (41 KB) | ru |
| `student-page-locked-phone-en.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (30 KB) | en |
| `student-page-locked-phone-ky.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (33 KB) | ky |
| `student-page-locked-phone-ru.png` | Student opens a page inside a module that opens later: locked state with the reason | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (31 KB) | ru |
| `student-page-math-desktop-en.png` | Student page opened from a module (`?from=module`): Markdown typography (headings, lists) and KaTeX math, language chips, Modules tab active, "Go to modules" as the next step | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (54 KB) | en |
| `student-page-math-desktop-ky.png` | Student page opened from a module (`?from=module`): Markdown typography (headings, lists) and KaTeX math, language chips, Modules tab active, "Go to modules" as the next step | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (58 KB) | ky |
| `student-page-math-desktop-ru.png` | Student page opened from a module (`?from=module`): Markdown typography (headings, lists) and KaTeX math, language chips, Modules tab active, "Go to modules" as the next step | `/{lang}/courses/{courseId}/pages/{pageId}` | 1440x900 (55 KB) | ru |
| `student-page-math-phone-en.png` | Student page opened from a module (`?from=module`): Markdown typography (headings, lists) and KaTeX math, language chips, Modules tab active, "Go to modules" as the next step | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (43 KB) | en |
| `student-page-math-phone-ky.png` | Student page opened from a module (`?from=module`): Markdown typography (headings, lists) and KaTeX math, language chips, Modules tab active, "Go to modules" as the next step | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (46 KB) | ky |
| `student-page-math-phone-ru.png` | Student page opened from a module (`?from=module`): Markdown typography (headings, lists) and KaTeX math, language chips, Modules tab active, "Go to modules" as the next step | `/{lang}/courses/{courseId}/pages/{pageId}` | 375x812 (44 KB) | ru |
| `student-quiz-lobby-locked-desktop-en.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 1440x900 (42 KB) | en |
| `student-quiz-lobby-locked-desktop-ky.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 1440x900 (46 KB) | ky |
| `student-quiz-lobby-locked-desktop-ru.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 1440x900 (43 KB) | ru |
| `student-quiz-lobby-locked-phone-en.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 375x812 (32 KB) | en |
| `student-quiz-lobby-locked-phone-ky.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 375x812 (36 KB) | ky |
| `student-quiz-lobby-locked-phone-ru.png` | Quiz lobby while its module is locked by an opening date (423 module_locked reason, link to modules) | `/{lang}/courses/{courseId}/assessments/{assessmentId}` | 375x812 (33 KB) | ru |

## Teacher

| File | What | URL | Size | Lang |
|---|---|---|---|---|
| `teacher-add-item-desktop-en.png` | Add item dialog (kinds, page list, requirement) | `/{lang}/courses/{courseId}/modules` | 1440x900 (114 KB) | en |
| `teacher-add-item-desktop-ru.png` | Add item dialog (kinds, page list, requirement) | `/{lang}/courses/{courseId}/modules` | 1440x900 (127 KB) | ru |
| `teacher-add-item-phone-en.png` | Add item dialog (kinds, page list, requirement) | `/{lang}/courses/{courseId}/modules` | 375x812 (41 KB) | en |
| `teacher-add-item-phone-ru.png` | Add item dialog (kinds, page list, requirement) | `/{lang}/courses/{courseId}/modules` | 375x812 (46 KB) | ru |
| `teacher-announcement-compose-desktop-en.png` | Compose announcement with Markdown preview (math) | `/{lang}/courses/{courseId}/announcements/new` | 1440x900 (78 KB) | en |
| `teacher-announcement-compose-desktop-ru.png` | Compose announcement with Markdown preview (math) | `/{lang}/courses/{courseId}/announcements/new` | 1440x900 (84 KB) | ru |
| `teacher-announcement-compose-phone-en.png` | Compose announcement with Markdown preview (math) | `/{lang}/courses/{courseId}/announcements/new` | 375x812 (55 KB) | en |
| `teacher-announcement-compose-phone-ru.png` | Compose announcement with Markdown preview (math) | `/{lang}/courses/{courseId}/announcements/new` | 375x812 (61 KB) | ru |
| `teacher-announcements-desktop-en.png` | Teacher announcements list (pinned, posted); Delete is a quiet text button | `/{lang}/courses/{courseId}/announcements` | 1440x900 (79 KB) | en |
| `teacher-announcements-desktop-ru.png` | Teacher announcements list (pinned, posted); Delete is a quiet text button | `/{lang}/courses/{courseId}/announcements` | 1440x900 (87 KB) | ru |
| `teacher-announcements-phone-en.png` | Teacher announcements list (pinned, posted); Delete is a quiet text button | `/{lang}/courses/{courseId}/announcements` | 375x812 (56 KB) | en |
| `teacher-announcements-phone-ru.png` | Teacher announcements list (pinned, posted); Delete is a quiet text button | `/{lang}/courses/{courseId}/announcements` | 375x812 (62 KB) | ru |
| `teacher-files-desktop-en.png` | Teacher course files list ("Without folder" group) | `/{lang}/courses/{courseId}/files` | 1440x900 (76 KB) | en |
| `teacher-files-desktop-ru.png` | Teacher course files list ("Without folder" group) | `/{lang}/courses/{courseId}/files` | 1440x900 (80 KB) | ru |
| `teacher-files-phone-en.png` | Teacher course files list ("Without folder" group) | `/{lang}/courses/{courseId}/files` | 375x812 (53 KB) | en |
| `teacher-files-phone-ru.png` | Teacher course files list ("Without folder" group) | `/{lang}/courses/{courseId}/files` | 375x812 (55 KB) | ru |
| `teacher-files-upload-desktop-en.png` | Upload file dialog: styled "Choose PDF" button (the chosen file name shows next to it) | `/{lang}/courses/{courseId}/files` | 1440x900 (95 KB) | en |
| `teacher-files-upload-desktop-ru.png` | Upload file dialog: styled "Choose PDF" button (the chosen file name shows next to it) | `/{lang}/courses/{courseId}/files` | 1440x900 (105 KB) | ru |
| `teacher-files-upload-phone-en.png` | Upload file dialog: styled "Choose PDF" button (the chosen file name shows next to it) | `/{lang}/courses/{courseId}/files` | 375x812 (43 KB) | en |
| `teacher-files-upload-phone-ru.png` | Upload file dialog: styled "Choose PDF" button (the chosen file name shows next to it) | `/{lang}/courses/{courseId}/files` | 375x812 (48 KB) | ru |
| `teacher-module-settings-desktop-en.png` | Module settings dialog (title, opening date with "Your local time", sequential) | `/{lang}/courses/{courseId}/modules` | 1440x900 (115 KB) | en |
| `teacher-module-settings-desktop-ru.png` | Module settings dialog (title, opening date with "Your local time", sequential) | `/{lang}/courses/{courseId}/modules` | 1440x900 (125 KB) | ru |
| `teacher-module-settings-phone-en.png` | Module settings dialog (title, opening date with "Your local time", sequential) | `/{lang}/courses/{courseId}/modules` | 375x812 (52 KB) | en |
| `teacher-module-settings-phone-ru.png` | Module settings dialog (title, opening date with "Your local time", sequential) | `/{lang}/courses/{courseId}/modules` | 375x812 (57 KB) | ru |
| `teacher-outline-desktop-en.png` | Teacher module outline: five modules, publish switches (no duplicate status text), requirement links that open the picker, M5 with the "Quiz not published" warning (draft quiz with a requirement), Re-apply rules with a warning icon | `/{lang}/courses/{courseId}/modules` | 1440x900 (208 KB) | en |
| `teacher-outline-desktop-ru.png` | Teacher module outline: five modules, publish switches (no duplicate status text), requirement links that open the picker, M5 with the "Quiz not published" warning (draft quiz with a requirement), Re-apply rules with a warning icon | `/{lang}/courses/{courseId}/modules` | 1440x900 (232 KB) | ru |
| `teacher-outline-empty-desktop-en.png` | Teacher module outline, empty course | `/{lang}/courses/{courseId}/modules` | 1440x900 (61 KB) | en |
| `teacher-outline-empty-desktop-ru.png` | Teacher module outline, empty course | `/{lang}/courses/{courseId}/modules` | 1440x900 (66 KB) | ru |
| `teacher-outline-empty-phone-en.png` | Teacher module outline, empty course | `/{lang}/courses/{courseId}/modules` | 375x812 (39 KB) | en |
| `teacher-outline-empty-phone-ru.png` | Teacher module outline, empty course | `/{lang}/courses/{courseId}/modules` | 375x812 (41 KB) | ru |
| `teacher-outline-phone-en.png` | Teacher module outline: five modules, publish switches (no duplicate status text), requirement links that open the picker, M5 with the "Quiz not published" warning (draft quiz with a requirement), Re-apply rules with a warning icon | `/{lang}/courses/{courseId}/modules` | 375x812 (188 KB) | en |
| `teacher-outline-phone-ru.png` | Teacher module outline: five modules, publish switches (no duplicate status text), requirement links that open the picker, M5 with the "Quiz not published" warning (draft quiz with a requirement), Re-apply rules with a warning icon | `/{lang}/courses/{courseId}/modules` | 375x812 (211 KB) | ru |
| `teacher-page-editor-desktop-en.png` | Page editor with server-rendered math preview and language chips (selected chip for the current version) | `/{lang}/courses/{courseId}/pages/{pageId}/edit` | 1440x900 (113 KB) | en |
| `teacher-page-editor-desktop-ru.png` | Page editor with server-rendered math preview and language chips (selected chip for the current version) | `/{lang}/courses/{courseId}/pages/{pageId}/edit` | 1440x900 (124 KB) | ru |
| `teacher-page-editor-phone-en.png` | Page editor with server-rendered math preview and language chips (selected chip for the current version) | `/{lang}/courses/{courseId}/pages/{pageId}/edit` | 375x812 (87 KB) | en |
| `teacher-page-editor-phone-ru.png` | Page editor with server-rendered math preview and language chips (selected chip for the current version) | `/{lang}/courses/{courseId}/pages/{pageId}/edit` | 375x812 (95 KB) | ru |
| `teacher-pages-desktop-en.png` | Teacher pages list (Show trash as a checkbox; phone cards without a doubled Actions label) | `/{lang}/courses/{courseId}/pages` | 1440x900 (106 KB) | en |
| `teacher-pages-desktop-ru.png` | Teacher pages list (Show trash as a checkbox; phone cards without a doubled Actions label) | `/{lang}/courses/{courseId}/pages` | 1440x900 (120 KB) | ru |
| `teacher-pages-phone-en.png` | Teacher pages list (Show trash as a checkbox; phone cards without a doubled Actions label) | `/{lang}/courses/{courseId}/pages` | 375x812 (110 KB) | en |
| `teacher-pages-phone-ru.png` | Teacher pages list (Show trash as a checkbox; phone cards without a doubled Actions label) | `/{lang}/courses/{courseId}/pages` | 375x812 (120 KB) | ru |
| `teacher-prerequisites-desktop-en.png` | Prerequisites dialog for module 3 | `/{lang}/courses/{courseId}/modules` | 1440x900 (114 KB) | en |
| `teacher-prerequisites-desktop-ru.png` | Prerequisites dialog for module 3 | `/{lang}/courses/{courseId}/modules` | 1440x900 (125 KB) | ru |
| `teacher-prerequisites-phone-en.png` | Prerequisites dialog for module 3 | `/{lang}/courses/{courseId}/modules` | 375x812 (52 KB) | en |
| `teacher-prerequisites-phone-ru.png` | Prerequisites dialog for module 3 | `/{lang}/courses/{courseId}/modules` | 375x812 (51 KB) | ru |
| `teacher-progress-desktop-en.png` | Student progress drawer for one student | `/{lang}/courses/{courseId}/modules` | 1440x900 (130 KB) | en |
| `teacher-progress-desktop-ru.png` | Student progress drawer for one student | `/{lang}/courses/{courseId}/modules` | 1440x900 (138 KB) | ru |
| `teacher-progress-phone-en.png` | Student progress drawer for one student | `/{lang}/courses/{courseId}/modules` | 375x812 (48 KB) | en |
| `teacher-progress-phone-ru.png` | Student progress drawer for one student | `/{lang}/courses/{courseId}/modules` | 375x812 (52 KB) | ru |
| `teacher-publish-warning-desktop-en.png` | Publishing a module whose requirement points at a draft quiz asks first ("Quiz not published") | `/{lang}/courses/{courseId}/modules` | 1440x900 (109 KB) | en |
| `teacher-publish-warning-desktop-ru.png` | Publishing a module whose requirement points at a draft quiz asks first ("Quiz not published") | `/{lang}/courses/{courseId}/modules` | 1440x900 (120 KB) | ru |
| `teacher-publish-warning-phone-en.png` | Publishing a module whose requirement points at a draft quiz asks first ("Quiz not published") | `/{lang}/courses/{courseId}/modules` | 375x812 (50 KB) | en |
| `teacher-publish-warning-phone-ru.png` | Publishing a module whose requirement points at a draft quiz asks first ("Quiz not published") | `/{lang}/courses/{courseId}/modules` | 375x812 (50 KB) | ru |
| `teacher-requirement-desktop-en.png` | Requirement picker for the quiz item (score at least 80 %), options in one casing | `/{lang}/courses/{courseId}/modules` | 1440x900 (109 KB) | en |
| `teacher-requirement-desktop-ru.png` | Requirement picker for the quiz item (score at least 80 %), options in one casing | `/{lang}/courses/{courseId}/modules` | 1440x900 (119 KB) | ru |
| `teacher-requirement-phone-en.png` | Requirement picker for the quiz item (score at least 80 %), options in one casing | `/{lang}/courses/{courseId}/modules` | 375x812 (46 KB) | en |
| `teacher-requirement-phone-ru.png` | Requirement picker for the quiz item (score at least 80 %), options in one casing | `/{lang}/courses/{courseId}/modules` | 375x812 (43 KB) | ru |
| `teacher-settings-home-desktop-en.png` | Course settings: Course home section (modules / page / assignments) | `/{lang}/courses/{courseId}/settings` | 1440x900 (58 KB) | en |
| `teacher-settings-home-desktop-ru.png` | Course settings: Course home section (modules / page / assignments) | `/{lang}/courses/{courseId}/settings` | 1440x900 (66 KB) | ru |
| `teacher-settings-home-phone-en.png` | Course settings: Course home section (modules / page / assignments) | `/{lang}/courses/{courseId}/settings` | 375x812 (42 KB) | en |
| `teacher-settings-home-phone-ru.png` | Course settings: Course home section (modules / page / assignments) | `/{lang}/courses/{courseId}/settings` | 375x812 (46 KB) | ru |

## ORT review (`ort-review/`)

See `ort-review/README.md` for the ORT baseline comparison (before / after / diff of the teacher baselines).

| File | What | URL | Size | Lang |
|---|---|---|---|---|
| `ort-review/ort-student-course-home-before-desktop-ru.png` | ORT (Russian) student course home before any structure: no new tabs | `/{lang}/courses/{courseId}` | 1440x900 (55 KB) | ru |
| `ort-review/ort-student-course-home-before-phone-ru.png` | ORT (Russian) student course home before any structure: no new tabs | `/{lang}/courses/{courseId}` | 375x812 (46 KB) | ru |
| `ort-review/ort-student-course-home-with-structure-desktop-ru.png` | ORT student course home with a published module and file: Modules and Files tabs appear, home unchanged | `/{lang}/courses/{courseId}` | 1440x900 (56 KB) | ru |
| `ort-review/ort-student-course-home-with-structure-phone-ru.png` | ORT student course home with a published module and file: Modules and Files tabs appear, home unchanged | `/{lang}/courses/{courseId}` | 375x812 (46 KB) | ru |
| `ort-review/ort-student-modules-desktop-ru.png` | ORT student modules view: module locked by date; the ORT exam row inside it opens and says "Available from Assignments" (gating-exempt, 8a UX M6) | `/{lang}/courses/{courseId}/modules` | 1440x900 (50 KB) | ru |
| `ort-review/ort-student-modules-phone-ru.png` | ORT student modules view: module locked by date; the ORT exam row inside it opens and says "Available from Assignments" (gating-exempt, 8a UX M6) | `/{lang}/courses/{courseId}/modules` | 375x812 (39 KB) | ru |
| `ort-review/ort-teacher-course-home-after-desktop-ru.png` | ORT staff course home: Modules, Pages, Files, Announcements tabs (owner Q5 default); no "Change the course home" link (home kind locked) | `/{lang}/courses/{courseId}` | 1440x900 (118 KB) | ru |
| `ort-review/ort-teacher-course-home-after-phone-ru.png` | ORT staff course home: Modules, Pages, Files, Announcements tabs (owner Q5 default); no "Change the course home" link (home kind locked) | `/{lang}/courses/{courseId}` | 375x812 (95 KB) | ru |
