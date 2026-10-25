# Phase 6b UX-gate screenshots

## S5a design system (`frontend/src/components/ui/`, branch `phase-6/s5a-ui`, 2026-10-25)

66 JPEG files (quality 72). Showcase page `/[lang]/dev/ui` (development only, `notFound()` in production), shot with playwright-core + Chrome against `next dev` from an rsync'd copy. Section shots are element screenshots of one `<section>`; `dialog-*` and `toasts-*` are viewport shots. Viewports: phone 375x812 (`isMobile`, deviceScaleFactor 1), desktop 1440x900. Measured `document.documentElement.scrollWidth` = 375 at 375 px (ru, ky, en), also after opening dialogs, toasts, the picker and the table states. Keyboard checks in the same run: focus moves into the dialog, Esc closes it and focus returns to the opener, Tab stays inside the dialog, ConfirmDialog starts on Cancel.

| File | Shows | Route | Viewport | Lang |
|---|---|---|---|---|
| ui-badges-desktop-ru.jpg | Badge tones neutral / info / success / warning / danger / system | `/ru/dev/ui` | 1440x900 | ru |
| ui-badges-phone-ru.jpg | Badge tones neutral / info / success / warning / danger / system | `/ru/dev/ui` | 375x812 | ru |
| ui-buttons-desktop-ru.jpg | Button variants, sizes, loading (spinner + aria-busy), disabled; LinkButton; IconButton | `/ru/dev/ui` | 1440x900 | ru |
| ui-buttons-phone-ky.jpg | Button variants, sizes, loading (spinner + aria-busy), disabled; LinkButton; IconButton | `/ky/dev/ui` | 375x812 | ky |
| ui-buttons-phone-ru.jpg | Button variants, sizes, loading (spinner + aria-busy), disabled; LinkButton; IconButton | `/ru/dev/ui` | 375x812 | ru |
| ui-cards-desktop-ru.jpg | Card with actions, StatTile (plain, link, gold), DescriptionList (stacked 2-col, columns) | `/ru/dev/ui` | 1440x900 | ru |
| ui-cards-phone-ky.jpg | Card with actions, StatTile (plain, link, gold), DescriptionList (stacked 2-col, columns) | `/ky/dev/ui` | 375x812 | ky |
| ui-cards-phone-ru.jpg | Card with actions, StatTile (plain, link, gold), DescriptionList (stacked 2-col, columns) | `/ru/dev/ui` | 375x812 | ru |
| ui-dialog-confirm-desktop-ky.jpg | ConfirmDialog danger: object + effect, focus starts on Cancel (ring shown after Tab cycling) | `/ky/dev/ui` | 1440x900 | ky |
| ui-dialog-confirm-desktop-ru.jpg | ConfirmDialog danger: object + effect, focus starts on Cancel (ring shown after Tab cycling) | `/ru/dev/ui` | 1440x900 | ru |
| ui-dialog-confirm-phone-ky.jpg | ConfirmDialog danger: object + effect, focus starts on Cancel (ring shown after Tab cycling) | `/ky/dev/ui` | 375x812 | ky |
| ui-dialog-confirm-phone-ru.jpg | ConfirmDialog danger: object + effect, focus starts on Cancel (ring shown after Tab cycling) | `/ru/dev/ui` | 375x812 | ru |
| ui-dialog-form-desktop-ky.jpg | Dialog with a field (focus on the input; footer primary on top on phones) | `/ky/dev/ui` | 1440x900 | ky |
| ui-dialog-form-desktop-ru.jpg | Dialog with a field (focus on the input; footer primary on top on phones) | `/ru/dev/ui` | 1440x900 | ru |
| ui-dialog-form-phone-ky.jpg | Dialog with a field (focus on the input; footer primary on top on phones) | `/ky/dev/ui` | 375x812 | ky |
| ui-dialog-form-phone-ru.jpg | Dialog with a field (focus on the input; footer primary on top on phones) | `/ru/dev/ui` | 375x812 | ru |
| ui-dialog-reason-error-desktop-ky.jpg | ReasonDialog: confirm without a reason shows the field error | `/ky/dev/ui` | 1440x900 | ky |
| ui-dialog-reason-error-desktop-ru.jpg | ReasonDialog: confirm without a reason shows the field error | `/ru/dev/ui` | 1440x900 | ru |
| ui-dialog-reason-error-phone-ky.jpg | ReasonDialog: confirm without a reason shows the field error | `/ky/dev/ui` | 375x812 | ky |
| ui-dialog-reason-error-phone-ru.jpg | ReasonDialog: confirm without a reason shows the field error | `/ru/dev/ui` | 375x812 | ru |
| ui-dialogs-desktop-ru.jpg | Dialog launchers | `/ru/dev/ui` | 1440x900 | ru |
| ui-dialogs-phone-ru.jpg | Dialog launchers | `/ru/dev/ui` | 375x812 | ru |
| ui-fields-desktop-ky.jpg | Input / Textarea / Select / Checkbox / Switch with hint, error, optional, disabled, busy | `/ky/dev/ui` | 1440x900 | ky |
| ui-fields-desktop-ru.jpg | Input / Textarea / Select / Checkbox / Switch with hint, error, optional, disabled, busy | `/ru/dev/ui` | 1440x900 | ru |
| ui-fields-phone-ky.jpg | Input / Textarea / Select / Checkbox / Switch with hint, error, optional, disabled, busy | `/ky/dev/ui` | 375x812 | ky |
| ui-fields-phone-ru.jpg | Input / Textarea / Select / Checkbox / Switch with hint, error, optional, disabled, busy | `/ru/dev/ui` | 375x812 | ru |
| ui-header-desktop-ky.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/ky/dev/ui` | 1440x900 | ky |
| ui-header-desktop-ru.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/ru/dev/ui` | 1440x900 | ru |
| ui-header-phone-en.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/en/dev/ui` | 375x812 | en |
| ui-header-phone-ky.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/ky/dev/ui` | 375x812 | ky |
| ui-header-phone-ru.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/ru/dev/ui` | 375x812 | ru |
| ui-picker-desktop-ru.jpg | UserPicker (empty) | `/ru/dev/ui` | 1440x900 | ru |
| ui-picker-open-desktop-ky.jpg | UserPicker with results, first option active (ArrowDown) | `/ky/dev/ui` | 1440x900 | ky |
| ui-picker-open-desktop-ru.jpg | UserPicker with results, first option active (ArrowDown) | `/ru/dev/ui` | 1440x900 | ru |
| ui-picker-open-phone-ky.jpg | UserPicker with results, first option active (ArrowDown) | `/ky/dev/ui` | 375x812 | ky |
| ui-picker-open-phone-ru.jpg | UserPicker with results, first option active (ArrowDown) | `/ru/dev/ui` | 375x812 | ru |
| ui-picker-phone-ru.jpg | UserPicker (empty) | `/ru/dev/ui` | 375x812 | ru |
| ui-states-desktop-ru.jpg | EmptyState, ErrorState (page and inline, retrying), Skeleton, LoadingState | `/ru/dev/ui` | 1440x900 | ru |
| ui-states-phone-ky.jpg | EmptyState, ErrorState (page and inline, retrying), Skeleton, LoadingState | `/ky/dev/ui` | 375x812 | ky |
| ui-states-phone-ru.jpg | EmptyState, ErrorState (page and inline, retrying), Skeleton, LoadingState | `/ru/dev/ui` | 375x812 | ru |
| ui-table-desktop-ky.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/ky/dev/ui` | 1440x900 | ky |
| ui-table-desktop-ru.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/ru/dev/ui` | 1440x900 | ru |
| ui-table-empty-desktop-ky.jpg | Table empty state (EmptyState + action) | `/ky/dev/ui` | 1440x900 | ky |
| ui-table-empty-desktop-ru.jpg | Table empty state (EmptyState + action) | `/ru/dev/ui` | 1440x900 | ru |
| ui-table-empty-phone-ky.jpg | Table empty state (EmptyState + action) | `/ky/dev/ui` | 375x812 | ky |
| ui-table-empty-phone-ru.jpg | Table empty state (EmptyState + action) | `/ru/dev/ui` | 375x812 | ru |
| ui-table-error-desktop-ky.jpg | Table error state (ErrorState + Retry) | `/ky/dev/ui` | 1440x900 | ky |
| ui-table-error-desktop-ru.jpg | Table error state (ErrorState + Retry) | `/ru/dev/ui` | 1440x900 | ru |
| ui-table-error-phone-ky.jpg | Table error state (ErrorState + Retry) | `/ky/dev/ui` | 375x812 | ky |
| ui-table-error-phone-ru.jpg | Table error state (ErrorState + Retry) | `/ru/dev/ui` | 375x812 | ru |
| ui-table-loading-desktop-ky.jpg | Table loading skeleton | `/ky/dev/ui` | 1440x900 | ky |
| ui-table-loading-desktop-ru.jpg | Table loading skeleton | `/ru/dev/ui` | 1440x900 | ru |
| ui-table-loading-phone-ky.jpg | Table loading skeleton | `/ky/dev/ui` | 375x812 | ky |
| ui-table-loading-phone-ru.jpg | Table loading skeleton | `/ru/dev/ui` | 375x812 | ru |
| ui-table-phone-en.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/en/dev/ui` | 375x812 | en |
| ui-table-phone-ky.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/ky/dev/ui` | 375x812 | ky |
| ui-table-phone-ru.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/ru/dev/ui` | 375x812 | ru |
| ui-tabs-desktop-ru.jpg | Tabs (role=tablist, overflow fade, counts, disabled tab) and TabsNav (links) | `/ru/dev/ui` | 1440x900 | ru |
| ui-tabs-phone-ky.jpg | Tabs (role=tablist, overflow fade, counts, disabled tab) and TabsNav (links) | `/ky/dev/ui` | 375x812 | ky |
| ui-tabs-phone-ru.jpg | Tabs (role=tablist, overflow fade, counts, disabled tab) and TabsNav (links) | `/ru/dev/ui` | 375x812 | ru |
| ui-toasts-desktop-ky.jpg | Toasts (success + error) in the polite live region | `/ky/dev/ui` | 1440x900 | ky |
| ui-toasts-desktop-ru.jpg | Toasts (success + error) in the polite live region | `/ru/dev/ui` | 1440x900 | ru |
| ui-toasts-phone-ky.jpg | Toasts (success + error) in the polite live region | `/ky/dev/ui` | 375x812 | ky |
| ui-toasts-phone-ru.jpg | Toasts (success + error) in the polite live region | `/ru/dev/ui` | 375x812 | ru |
| ui-tokens-desktop-ru.jpg | Color tokens (brand, slate, success, warning, danger, gold) and type scale | `/ru/dev/ui` | 1440x900 | ru |
| ui-tokens-phone-ru.jpg | Color tokens (brand, slate, success, warning, danger, gold) and type scale | `/ru/dev/ui` | 375x812 | ru |


## S6b student home and student screens (branch `phase-6/s6b-home-ui`, 2026-10-25)

79 JPEG files (quality 70, full page unless noted). Built frontend (`next build` + `next start` from an rsync'd copy) against a scratch backend (SQLite copy of the 6a UX-gate DB plus `s6b_setup.js`: a new student, a student with an in-progress attempt, a due-soon assignment, three released results and a personal best, a 215-minute assessment with its only attempt used). playwright-core + Chrome, phone 375x812 (`isMobile`), desktop 1440x900, timezone Asia/Bishkek. `scrollWidth` column: `document.documentElement.scrollWidth` measured on the shot (375 on every phone shot). ORT check (desktop, ru): a fresh account joined "ОРТ (на русском)" from `/courses/catalog`, pressed Start on the course home, then Start in the lobby, and the ORT player opened (`s6b-ort-check-*`).

| File | Shows | Route | Viewport | Lang | scrollWidth |
|---|---|---|---|---|---|
| s6b-assessments-desktop-en.jpg | Student assessment list: status badges, due date, duration (h/min), questions, attempts left / No attempts left, one primary (Continue), result links | `/en/courses/{course}/assessments` | 1440x900 | en | 1440 |
| s6b-assessments-desktop-ky.jpg | Student assessment list: status badges, due date, duration (h/min), questions, attempts left / No attempts left, one primary (Continue), result links | `/ky/courses/{course}/assessments` | 1440x900 | ky | 1440 |
| s6b-assessments-desktop-ru.jpg | Student assessment list: status badges, due date, duration (h/min), questions, attempts left / No attempts left, one primary (Continue), result links | `/ru/courses/{course}/assessments` | 1440x900 | ru | 1440 |
| s6b-assessments-phone-en.jpg | Student assessment list: status badges, due date, duration (h/min), questions, attempts left / No attempts left, one primary (Continue), result links | `/en/courses/{course}/assessments` | 375x812 | en | 375 |
| s6b-assessments-phone-ky.jpg | Student assessment list: status badges, due date, duration (h/min), questions, attempts left / No attempts left, one primary (Continue), result links | `/ky/courses/{course}/assessments` | 375x812 | ky | 375 |
| s6b-assessments-phone-ru.jpg | Student assessment list: status badges, due date, duration (h/min), questions, attempts left / No attempts left, one primary (Continue), result links | `/ru/courses/{course}/assessments` | 375x812 | ru | 375 |
| s6b-catalog-desktop-en.jpg | Catalog page (moved from /courses#catalog): breadcrumbs, Join with code, language names, no student count under 10, secondary Join/Open | `/en/courses/catalog` | 1440x900 | en | 1440 |
| s6b-catalog-desktop-ky.jpg | Catalog page (moved from /courses#catalog): breadcrumbs, Join with code, language names, no student count under 10, secondary Join/Open | `/ky/courses/catalog` | 1440x900 | ky | 1440 |
| s6b-catalog-desktop-ru.jpg | Catalog page (moved from /courses#catalog): breadcrumbs, Join with code, language names, no student count under 10, secondary Join/Open | `/ru/courses/catalog` | 1440x900 | ru | 1440 |
| s6b-catalog-phone-en.jpg | Catalog page (moved from /courses#catalog): breadcrumbs, Join with code, language names, no student count under 10, secondary Join/Open | `/en/courses/catalog` | 375x812 | en | 375 |
| s6b-catalog-phone-ky.jpg | Catalog page (moved from /courses#catalog): breadcrumbs, Join with code, language names, no student count under 10, secondary Join/Open | `/ky/courses/catalog` | 375x812 | ky | 375 |
| s6b-catalog-phone-ru.jpg | Catalog page (moved from /courses#catalog): breadcrumbs, Join with code, language names, no student count under 10, secondary Join/Open | `/ru/courses/catalog` | 375x812 | ru | 375 |
| s6b-course-home-desktop-en.jpg | Student course home: breadcrumbs, scrollable tabs (Teachers), next assessment with the one primary button, latest result, about, quiet Leave course | `/en/courses/{course}` | 1440x900 | en | 1440 |
| s6b-course-home-desktop-ky.jpg | Student course home: breadcrumbs, scrollable tabs (Teachers), next assessment with the one primary button, latest result, about, quiet Leave course | `/ky/courses/{course}` | 1440x900 | ky | 1440 |
| s6b-course-home-desktop-ru.jpg | Student course home: breadcrumbs, scrollable tabs (Teachers), next assessment with the one primary button, latest result, about, quiet Leave course | `/ru/courses/{course}` | 1440x900 | ru | 1440 |
| s6b-course-home-phone-en.jpg | Student course home: breadcrumbs, scrollable tabs (Teachers), next assessment with the one primary button, latest result, about, quiet Leave course | `/en/courses/{course}` | 375x812 | en | 375 |
| s6b-course-home-phone-ky.jpg | Student course home: breadcrumbs, scrollable tabs (Teachers), next assessment with the one primary button, latest result, about, quiet Leave course | `/ky/courses/{course}` | 375x812 | ky | 375 |
| s6b-course-home-phone-ru.jpg | Student course home: breadcrumbs, scrollable tabs (Teachers), next assessment with the one primary button, latest result, about, quiet Leave course | `/ru/courses/{course}` | 375x812 | ru | 375 |
| s6b-course-ort-desktop-en.jpg | ORT course home for a student: Platform course, next exam with Start | `/en/courses/{ORT}` | 1440x900 | en | 1440 |
| s6b-course-ort-desktop-ky.jpg | ORT course home for a student: Platform course, next exam with Start | `/ky/courses/{ORT}` | 1440x900 | ky | 1440 |
| s6b-course-ort-desktop-ru.jpg | ORT course home for a student: Platform course, next exam with Start | `/ru/courses/{ORT}` | 1440x900 | ru | 1440 |
| s6b-course-ort-phone-en.jpg | ORT course home for a student: Platform course, next exam with Start | `/en/courses/{ORT}` | 375x812 | en | 375 |
| s6b-course-ort-phone-ky.jpg | ORT course home for a student: Platform course, next exam with Start | `/ky/courses/{ORT}` | 375x812 | ky | 375 |
| s6b-course-ort-phone-ru.jpg | ORT course home for a student: Platform course, next exam with Start | `/ru/courses/{ORT}` | 375x812 | ru | 375 |
| s6b-courses-teacher-learning-desktop-ru.jpg | Teacher who studies: Teaching / Learning tabs (Tabs), Learning = the student home | `/ru/courses` | 1440x900 | ru | 1440 |
| s6b-courses-teacher-learning-phone-ru.jpg | Teacher who studies: Teaching / Learning tabs (Tabs), Learning = the student home | `/ru/courses` | 375x812 | ru | 375 |
| s6b-courses-teacher-teaching-desktop-ru.jpg | Teacher: Teaching tab (PageHeader, one primary Create course) | `/ru/courses` | 1440x900 | ru | 1440 |
| s6b-courses-teacher-teaching-phone-ru.jpg | Teacher: Teaching tab (PageHeader, one primary Create course) | `/ru/courses` | 375x812 | ru | 375 |
| s6b-grades-ort-desktop-en.jpg | ORT grades: no raw 'course total %' next to the scaled ORT score (S7) | `/en/courses/{ORT}/grades` | 1440x900 | en | 1440 |
| s6b-grades-ort-desktop-ky.jpg | ORT grades: no raw 'course total %' next to the scaled ORT score (S7) | `/ky/courses/{ORT}/grades` | 1440x900 | ky | 1440 |
| s6b-grades-ort-desktop-ru.jpg | ORT grades: no raw 'course total %' next to the scaled ORT score (S7) | `/ru/courses/{ORT}/grades` | 1440x900 | ru | 1440 |
| s6b-grades-ort-phone-en.jpg | ORT grades: no raw 'course total %' next to the scaled ORT score (S7) | `/en/courses/{ORT}/grades` | 375x812 | en | 375 |
| s6b-grades-ort-phone-ky.jpg | ORT grades: no raw 'course total %' next to the scaled ORT score (S7) | `/ky/courses/{ORT}/grades` | 375x812 | ky | 375 |
| s6b-grades-ort-phone-ru.jpg | ORT grades: no raw 'course total %' next to the scaled ORT score (S7) | `/ru/courses/{ORT}/grades` | 375x812 | ru | 375 |
| s6b-home-error-desktop-en.jpg | Error: ErrorState with Retry (`/me/home` answered 500) | `/en/courses` | 1440x900 | en | 1440 |
| s6b-home-error-desktop-ky.jpg | Error: ErrorState with Retry (`/me/home` answered 500) | `/ky/courses` | 1440x900 | ky | 1440 |
| s6b-home-error-desktop-ru.jpg | Error: ErrorState with Retry (`/me/home` answered 500) | `/ru/courses` | 1440x900 | ru | 1440 |
| s6b-home-error-phone-en.jpg | Error: ErrorState with Retry (`/me/home` answered 500) | `/en/courses` | 375x812 | en | 375 |
| s6b-home-error-phone-ky.jpg | Error: ErrorState with Retry (`/me/home` answered 500) | `/ky/courses` | 375x812 | ky | 375 |
| s6b-home-error-phone-ru.jpg | Error: ErrorState with Retry (`/me/home` answered 500) | `/ru/courses` | 375x812 | ru | 375 |
| s6b-home-loading-desktop-en.jpg | Loading: header and greeting at once, Skeleton rows for the rest (`/me/home` held 8 s) | `/en/courses` | 1440x900 | en | 1440 |
| s6b-home-loading-desktop-ky.jpg | Loading: header and greeting at once, Skeleton rows for the rest (`/me/home` held 8 s) | `/ky/courses` | 1440x900 | ky | 1440 |
| s6b-home-loading-desktop-ru.jpg | Loading: header and greeting at once, Skeleton rows for the rest (`/me/home` held 8 s) | `/ru/courses` | 1440x900 | ru | 1440 |
| s6b-home-loading-phone-en.jpg | Loading: header and greeting at once, Skeleton rows for the rest (`/me/home` held 8 s) | `/en/courses` | 375x812 | en | 375 |
| s6b-home-loading-phone-ky.jpg | Loading: header and greeting at once, Skeleton rows for the rest (`/me/home` held 8 s) | `/ky/courses` | 375x812 | ky | 375 |
| s6b-home-loading-phone-ru.jpg | Loading: header and greeting at once, Skeleton rows for the rest (`/me/home` held 8 s) | `/ru/courses` | 375x812 | ru | 375 |
| s6b-home-new-desktop-en.jpg | New student: greeting, My courses empty state as the hero (Join with code primary + Open the catalog) | `/en/courses` | 1440x900 | en | 1440 |
| s6b-home-new-desktop-ky.jpg | New student: greeting, My courses empty state as the hero (Join with code primary + Open the catalog) | `/ky/courses` | 1440x900 | ky | 1440 |
| s6b-home-new-desktop-ru.jpg | New student: greeting, My courses empty state as the hero (Join with code primary + Open the catalog) | `/ru/courses` | 1440x900 | ru | 1440 |
| s6b-home-new-phone-en.jpg | New student: greeting, My courses empty state as the hero (Join with code primary + Open the catalog) | `/en/courses` | 375x812 | en | 375 |
| s6b-home-new-phone-ky.jpg | New student: greeting, My courses empty state as the hero (Join with code primary + Open the catalog) | `/ky/courses` | 375x812 | ky | 375 |
| s6b-home-new-phone-ru.jpg | New student: greeting, My courses empty state as the hero (Join with code primary + Open the catalog) | `/ru/courses` | 375x812 | ru | 375 |
| s6b-home-student-desktop-en.jpg | Student home: greeting + one primary (Continue), Continue, Next up (due soon in red with clock), Latest results with Personal best (gold), My courses rows (platform course, next due, In progress) | `/en/courses` | 1440x900 | en | 1440 |
| s6b-home-student-desktop-ky.jpg | Student home: greeting + one primary (Continue), Continue, Next up (due soon in red with clock), Latest results with Personal best (gold), My courses rows (platform course, next due, In progress) | `/ky/courses` | 1440x900 | ky | 1440 |
| s6b-home-student-desktop-ru.jpg | Student home: greeting + one primary (Continue), Continue, Next up (due soon in red with clock), Latest results with Personal best (gold), My courses rows (platform course, next due, In progress) | `/ru/courses` | 1440x900 | ru | 1440 |
| s6b-home-student-phone-en.jpg | Student home: greeting + one primary (Continue), Continue, Next up (due soon in red with clock), Latest results with Personal best (gold), My courses rows (platform course, next due, In progress) | `/en/courses` | 375x812 | en | 375 |
| s6b-home-student-phone-ky.jpg | Student home: greeting + one primary (Continue), Continue, Next up (due soon in red with clock), Latest results with Personal best (gold), My courses rows (platform course, next due, In progress) | `/ky/courses` | 375x812 | ky | 375 |
| s6b-home-student-phone-ru.jpg | Student home: greeting + one primary (Continue), Continue, Next up (due soon in red with clock), Latest results with Personal best (gold), My courses rows (platform course, next due, In progress) | `/ru/courses` | 375x812 | ru | 375 |
| s6b-join-desktop-en.jpg | Join with code page: one name for the action, catalog link for students without a code | `/en/courses/join` | 1440x900 | en | 1440 |
| s6b-join-desktop-ky.jpg | Join with code page: one name for the action, catalog link for students without a code | `/ky/courses/join` | 1440x900 | ky | 1440 |
| s6b-join-desktop-ru.jpg | Join with code page: one name for the action, catalog link for students without a code | `/ru/courses/join` | 1440x900 | ru | 1440 |
| s6b-join-phone-en.jpg | Join with code page: one name for the action, catalog link for students without a code | `/en/courses/join` | 375x812 | en | 375 |
| s6b-join-phone-ky.jpg | Join with code page: one name for the action, catalog link for students without a code | `/ky/courses/join` | 375x812 | ky | 375 |
| s6b-join-phone-ru.jpg | Join with code page: one name for the action, catalog link for students without a code | `/ru/courses/join` | 375x812 | ru | 375 |
| s6b-lobby-no-attempts-desktop-en.jpg | After the last attempt: My attempts first (No attempts left + See result primary), lobby below (S1) | `/en/courses/{course}/assessments/{a}` | 1440x900 | en | 1440 |
| s6b-lobby-no-attempts-desktop-ky.jpg | After the last attempt: My attempts first (No attempts left + See result primary), lobby below (S1) | `/ky/courses/{course}/assessments/{a}` | 1440x900 | ky | 1440 |
| s6b-lobby-no-attempts-desktop-ru.jpg | After the last attempt: My attempts first (No attempts left + See result primary), lobby below (S1) | `/ru/courses/{course}/assessments/{a}` | 1440x900 | ru | 1440 |
| s6b-lobby-no-attempts-phone-en.jpg | After the last attempt: My attempts first (No attempts left + See result primary), lobby below (S1) | `/en/courses/{course}/assessments/{a}` | 375x812 | en | 375 |
| s6b-lobby-no-attempts-phone-ky.jpg | After the last attempt: My attempts first (No attempts left + See result primary), lobby below (S1) | `/ky/courses/{course}/assessments/{a}` | 375x812 | ky | 375 |
| s6b-lobby-no-attempts-phone-ru.jpg | After the last attempt: My attempts first (No attempts left + See result primary), lobby below (S1) | `/ru/courses/{course}/assessments/{a}` | 375x812 | ru | 375 |
| s6b-ort-check-1-course-desktop-ru.jpg | ORT check: joined ORT (Russian) from the catalog, lands on the course home | `/ru/courses/{ORT}` | 1440x900 | ru |  |
| s6b-ort-check-2-lobby-desktop-ru.jpg | ORT check: Start on the course home opens the ORT lobby | `/ru/courses/{ORT}/assessments/{exam}` | 1440x900 | ru |  |
| s6b-ort-check-3-player-desktop-ru.jpg | ORT check: lobby Start opens the ORT player (viewport shot) | `/ru/courses/{ORT}/attempts/{attempt}` | 1440x900 | ru |  |
| s6b-teacher-access-desktop-en.jpg | I am a teacher, no request yet: no status line (6a carry-over), design-system textarea and button | `/en/teacher-access` | 1440x900 | en | 1440 |
| s6b-teacher-access-desktop-ky.jpg | I am a teacher, no request yet: no status line (6a carry-over), design-system textarea and button | `/ky/teacher-access` | 1440x900 | ky | 1440 |
| s6b-teacher-access-desktop-ru.jpg | I am a teacher, no request yet: no status line (6a carry-over), design-system textarea and button | `/ru/teacher-access` | 1440x900 | ru | 1440 |
| s6b-teacher-access-phone-en.jpg | I am a teacher, no request yet: no status line (6a carry-over), design-system textarea and button | `/en/teacher-access` | 375x812 | en | 375 |
| s6b-teacher-access-phone-ky.jpg | I am a teacher, no request yet: no status line (6a carry-over), design-system textarea and button | `/ky/teacher-access` | 375x812 | ky | 375 |
| s6b-teacher-access-phone-ru.jpg | I am a teacher, no request yet: no status line (6a carry-over), design-system textarea and button | `/ru/teacher-access` | 375x812 | ru | 375 |
