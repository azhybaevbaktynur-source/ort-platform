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

## S5b app header, area shells, platform-admin and org-admin screens (branch `phase-6/s5b-shell`, 2026-10-25)

105 JPEG files (quality 70), playwright-core + Chrome against `next build` / `next start` from an rsync'd copy and a scratch
backend (copy of the 6a UX-gate SQLite data). Phone 375x812 (`isMobile`), desktop 1440x900, ru everywhere; header also en/ky for
student / teacher / org admin / platform admin. `scrollWidth` is `document.documentElement.scrollWidth` measured before each shot:
375 on every phone shot and 1440 on every desktop shot. `header` is the AppHeader height in px (57 on phones, 65 on desktop incl. border; 0 = signed-out page).
Keyboard checks in the same run: Tab stays inside the suspend dialog (6 presses), Esc closes it and focus returns to the opener (M6).
Browser tab title / description per language: "Платформа" / "Platform" + `landing.badge` (no more "ОРТ / ЖРТ Даярдоо Платформасы").

| File | Shows | Route | Role | Viewport | Lang | scrollWidth | header |
|---|---|---|---|---|---|---|---|
| s5b-admin-01-overview-desktop-ru.jpg | Admin overview: tiles as links, sections | `/ru/admin` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-01-overview-phone-ru.jpg | Admin overview: tiles as links, sections | `/ru/admin` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-02-organizations-desktop-ru.jpg | Organizations table | `/ru/admin/organizations` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-02-organizations-phone-ru.jpg | Organizations table | `/ru/admin/organizations` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-03-org-detail-desktop-ru.jpg | Organization detail, tab Summary | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-03-org-detail-phone-ru.jpg | Organization detail, tab Summary | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-04-org-tab-admins-desktop-ru.jpg | Organization detail, tab Администраторы | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-04-org-tab-admins-phone-ru.jpg | Organization detail, tab Администраторы | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-04-org-tab-courses-desktop-ru.jpg | Organization detail, tab Курсы | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-04-org-tab-courses-phone-ru.jpg | Organization detail, tab Курсы | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-04-org-tab-log-desktop-ru.jpg | Organization detail, tab Журнал | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-04-org-tab-log-phone-ru.jpg | Organization detail, tab Журнал | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-04-org-tab-templates-desktop-ru.jpg | Organization detail, tab Шаблоны | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-04-org-tab-templates-phone-ru.jpg | Organization detail, tab Шаблоны | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-04-org-tab-usage-desktop-ru.jpg | Organization detail, tab Использование | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-04-org-tab-usage-phone-ru.jpg | Organization detail, tab Использование | `/ru/admin/organizations/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-05-teacher-requests-all-desktop-ru.jpg | Teacher requests, tab All (request cards) | `/ru/admin/teacher-requests` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-05-teacher-requests-all-phone-ru.jpg | Teacher requests, tab All (request cards) | `/ru/admin/teacher-requests` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-05-teacher-requests-desktop-ru.jpg | Teacher requests (Tabs filter) | `/ru/admin/teacher-requests` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-05-teacher-requests-phone-ru.jpg | Teacher requests (Tabs filter) | `/ru/admin/teacher-requests` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-06-users-desktop-ru.jpg | Users table (cards on phones, M2) | `/ru/admin/users` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-06-users-phone-ru.jpg | Users table (cards on phones, M2) | `/ru/admin/users` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-07-user-detail-desktop-ru.jpg | User detail | `/ru/admin/users/usr_1451905d478d` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-07-user-detail-phone-ru.jpg | User detail | `/ru/admin/users/usr_1451905d478d` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-08-courses-desktop-ru.jpg | Courses table | `/ru/admin/courses` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-08-courses-phone-ru.jpg | Courses table | `/ru/admin/courses` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-09-course-detail-desktop-ru.jpg | Course detail | `/ru/admin/courses/a71d282e-c0fd-4841-b76b-0630880627cc` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-09-course-detail-phone-ru.jpg | Course detail | `/ru/admin/courses/a71d282e-c0fd-4841-b76b-0630880627cc` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-10-audit-log-desktop-ru.jpg | Audit log table | `/ru/admin/audit-log` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-10-audit-log-phone-ru.jpg | Audit log table | `/ru/admin/audit-log` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-11-storage-desktop-ru.jpg | Storage | `/ru/admin/storage` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-11-storage-phone-ru.jpg | Storage | `/ru/admin/storage` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-dlg-create-org-desktop-ru.jpg | Create organization dialog | `/ru/admin/organizations` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-dlg-create-org-phone-ru.jpg | Create organization dialog | `/ru/admin/organizations` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-dlg-disable-desktop-ru.jpg | Disable account dialog names the person | `/ru/admin/users/usr_1451905d478d` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-dlg-disable-phone-ru.jpg | Disable account dialog names the person | `/ru/admin/users/usr_1451905d478d` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-admin-dlg-suspend-desktop-ru.jpg | Suspend dialog names the organization and the effect | `/ru/admin/organizations/fd38eb64-dc3b-4c5f-9300-cd4bb25e8bbb` | platform admin | 1440x900 | ru | 1440 | 65 |
| s5b-admin-dlg-suspend-phone-ru.jpg | Suspend dialog names the organization and the effect | `/ru/admin/organizations/fd38eb64-dc3b-4c5f-9300-cd4bb25e8bbb` | platform admin | 375x812 | ru | 375 | 57 |
| s5b-auth-forgot-desktop-ru.jpg | Signed out: /forgot-password | `/ru/forgot-password` | anonymous | 1440x900 | ru | 1440 | — |
| s5b-auth-forgot-phone-ru.jpg | Signed out: /forgot-password | `/ru/forgot-password` | anonymous | 375x812 | ru | 375 | — |
| s5b-auth-login-desktop-ru.jpg | Signed out: /login | `/ru/login` | anonymous | 1440x900 | ru | 1440 | — |
| s5b-auth-login-phone-ru.jpg | Signed out: /login | `/ru/login` | anonymous | 375x812 | ru | 375 | — |
| s5b-auth-register-desktop-ru.jpg | Signed out: /register | `/ru/register` | anonymous | 1440x900 | ru | 1440 | — |
| s5b-auth-register-phone-ru.jpg | Signed out: /register | `/ru/register` | anonymous | 375x812 | ru | 375 | — |
| s5b-auth-reset-desktop-ru.jpg | Signed out: /reset-password?token=x | `/ru/reset-password?token=x` | anonymous | 1440x900 | ru | 1440 | — |
| s5b-auth-reset-phone-ru.jpg | Signed out: /reset-password?token=x | `/ru/reset-password?token=x` | anonymous | 375x812 | ru | 375 | — |
| s5b-header-account-admin-desktop-en.jpg | Account menu open (name, email, language, log out) | `/en/admin` | admin | 1440x900 | en | 1440 | 65 |
| s5b-header-account-admin-desktop-ky.jpg | Account menu open (name, email, language, log out) | `/ky/admin` | admin | 1440x900 | ky | 1440 | 65 |
| s5b-header-account-admin-desktop-ru.jpg | Account menu open (name, email, language, log out) | `/ru/admin` | admin | 1440x900 | ru | 1440 | 65 |
| s5b-header-account-admin-phone-en.jpg | Account menu open (name, email, language, log out) | `/en/admin` | admin | 375x812 | en | 375 | 57 |
| s5b-header-account-admin-phone-ky.jpg | Account menu open (name, email, language, log out) | `/ky/admin` | admin | 375x812 | ky | 375 | 57 |
| s5b-header-account-admin-phone-ru.jpg | Account menu open (name, email, language, log out) | `/ru/admin` | admin | 375x812 | ru | 375 | 57 |
| s5b-header-account-student-desktop-ru.jpg | Account menu of a student: 'I am a teacher' link | `/ru/courses` | student | 1440x900 | ru | 1440 | 65 |
| s5b-header-account-student-phone-ru.jpg | Account menu of a student: 'I am a teacher' link | `/ru/courses` | student | 375x812 | ru | 375 | 57 |
| s5b-header-admin-desktop-en.jpg | Header as admin on /courses | `/en/courses` | admin | 1440x900 | en | 1440 | 65 |
| s5b-header-admin-desktop-ky.jpg | Header as admin on /courses | `/ky/courses` | admin | 1440x900 | ky | 1440 | 65 |
| s5b-header-admin-desktop-ru.jpg | Header as admin on /courses | `/ru/courses` | admin | 1440x900 | ru | 1440 | 65 |
| s5b-header-admin-phone-en.jpg | Header as admin on /courses | `/en/courses` | admin | 375x812 | en | 375 | 57 |
| s5b-header-admin-phone-ky.jpg | Header as admin on /courses | `/ky/courses` | admin | 375x812 | ky | 375 | 57 |
| s5b-header-admin-phone-ru.jpg | Header as admin on /courses | `/ru/courses` | admin | 375x812 | ru | 375 | 57 |
| s5b-header-areamenu-admin-phone-en.jpg | Phone area switcher open (platform admin) | `/en/admin` | admin | 375x812 | en | 375 | 57 |
| s5b-header-areamenu-admin-phone-ky.jpg | Phone area switcher open (platform admin) | `/ky/admin` | admin | 375x812 | ky | 375 | 57 |
| s5b-header-areamenu-admin-phone-ru.jpg | Phone area switcher open (platform admin) | `/ru/admin` | admin | 375x812 | ru | 375 | 57 |
| s5b-header-areamenu-orgadmin-phone-ru.jpg | Phone area switcher open (org admin of two organizations) | `/ru/org` | orgadmin | 375x812 | ru | 375 | 57 |
| s5b-header-orgadmin-desktop-en.jpg | Header as orgadmin on /courses | `/en/courses` | orgadmin | 1440x900 | en | 1440 | 65 |
| s5b-header-orgadmin-desktop-ky.jpg | Header as orgadmin on /courses | `/ky/courses` | orgadmin | 1440x900 | ky | 1440 | 65 |
| s5b-header-orgadmin-desktop-ru.jpg | Header as orgadmin on /courses | `/ru/courses` | orgadmin | 1440x900 | ru | 1440 | 65 |
| s5b-header-orgadmin-phone-en.jpg | Header as orgadmin on /courses | `/en/courses` | orgadmin | 375x812 | en | 375 | 57 |
| s5b-header-orgadmin-phone-ky.jpg | Header as orgadmin on /courses | `/ky/courses` | orgadmin | 375x812 | ky | 375 | 57 |
| s5b-header-orgadmin-phone-ru.jpg | Header as orgadmin on /courses | `/ru/courses` | orgadmin | 375x812 | ru | 375 | 57 |
| s5b-header-orgs-dropdown-desktop-ru.jpg | Organization area: picker dropdown (two organizations) | `/ru/org` | orgadmin | 1440x900 | ru | 1440 | 65 |
| s5b-header-student-desktop-en.jpg | Header as student on /courses | `/en/courses` | student | 1440x900 | en | 1440 | 65 |
| s5b-header-student-desktop-ky.jpg | Header as student on /courses | `/ky/courses` | student | 1440x900 | ky | 1440 | 65 |
| s5b-header-student-desktop-ru.jpg | Header as student on /courses | `/ru/courses` | student | 1440x900 | ru | 1440 | 65 |
| s5b-header-student-phone-en.jpg | Header as student on /courses | `/en/courses` | student | 375x812 | en | 375 | 57 |
| s5b-header-student-phone-ky.jpg | Header as student on /courses | `/ky/courses` | student | 375x812 | ky | 375 | 57 |
| s5b-header-student-phone-ru.jpg | Header as student on /courses | `/ru/courses` | student | 375x812 | ru | 375 | 57 |
| s5b-header-teacher-desktop-en.jpg | Header as teacher on /courses | `/en/courses` | teacher | 1440x900 | en | 1440 | 65 |
| s5b-header-teacher-desktop-ky.jpg | Header as teacher on /courses | `/ky/courses` | teacher | 1440x900 | ky | 1440 | 65 |
| s5b-header-teacher-desktop-ru.jpg | Header as teacher on /courses | `/ru/courses` | teacher | 1440x900 | ru | 1440 | 65 |
| s5b-header-teacher-phone-en.jpg | Header as teacher on /courses | `/en/courses` | teacher | 375x812 | en | 375 | 57 |
| s5b-header-teacher-phone-ky.jpg | Header as teacher on /courses | `/ky/courses` | teacher | 375x812 | ky | 375 | 57 |
| s5b-header-teacher-phone-ru.jpg | Header as teacher on /courses | `/ru/courses` | teacher | 375x812 | ru | 375 | 57 |
| s5b-invite-invalid-desktop-ru.jpg | Signed out: /invite/not-a-token | `/ru/invite/not-a-token` | anonymous | 1440x900 | ru | 1440 | — |
| s5b-invite-invalid-phone-ru.jpg | Signed out: /invite/not-a-token | `/ru/invite/not-a-token` | anonymous | 375x812 | ru | 375 | — |
| s5b-org-00-picker-desktop-ru.jpg | Organization picker (two organizations) | `/ru/org` | org admin | 1440x900 | ru | 1440 | 65 |
| s5b-org-00-picker-phone-ru.jpg | Organization picker (two organizations) | `/ru/org` | org admin | 375x812 | ru | 375 | 57 |
| s5b-org-01-overview-desktop-ru.jpg | Org overview: tiles link to the lists | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | org admin | 1440x900 | ru | 1440 | 65 |
| s5b-org-01-overview-phone-ru.jpg | Org overview: tiles link to the lists | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | org admin | 375x812 | ru | 375 | 57 |
| s5b-org-02-teachers-desktop-ru.jpg | Org teachers and invitations tables | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee/teachers` | org admin | 1440x900 | ru | 1440 | 65 |
| s5b-org-02-teachers-phone-ru.jpg | Org teachers and invitations tables | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee/teachers` | org admin | 375x812 | ru | 375 | 57 |
| s5b-org-03-courses-desktop-ru.jpg | Org courses table | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee/courses` | org admin | 1440x900 | ru | 1440 | 65 |
| s5b-org-03-courses-phone-ru.jpg | Org courses table | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee/courses` | org admin | 375x812 | ru | 375 | 57 |
| s5b-org-04-course-desktop-ru.jpg | Org course summary | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee/courses/ecb1a978-ab08-4c89-ba96-12fa0c04490f` | org admin | 1440x900 | ru | 1440 | 65 |
| s5b-org-04-course-phone-ru.jpg | Org course summary | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee/courses/ecb1a978-ab08-4c89-ba96-12fa0c04490f` | org admin | 375x812 | ru | 375 | 57 |
| s5b-org-05-new-course-desktop-ru.jpg | Create course form | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee/courses/new` | org admin | 1440x900 | ru | 1440 | 65 |
| s5b-org-05-new-course-phone-ru.jpg | Create course form | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee/courses/new` | org admin | 375x812 | ru | 375 | 57 |
| s5b-org-06-suspended-desktop-ru.jpg | Suspended organization: banner, actions disabled (if suspended) | `/ru/org/fd38eb64-dc3b-4c5f-9300-cd4bb25e8bbb` | org admin | 1440x900 | ru | 1440 | 65 |
| s5b-org-06-suspended-phone-ru.jpg | Suspended organization: banner, actions disabled (if suspended) | `/ru/org/fd38eb64-dc3b-4c5f-9300-cd4bb25e8bbb` | org admin | 375x812 | ru | 375 | 57 |
| s5b-org-dlg-invite-desktop-ru.jpg | Invite teacher dialog | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | org admin | 1440x900 | ru | 1440 | 65 |
| s5b-org-dlg-invite-phone-ru.jpg | Invite teacher dialog | `/ru/org/8e4687c7-21b6-4962-9c21-d1f5f36132ee` | org admin | 375x812 | ru | 375 | 57 |
| s5b-teacher-access-desktop-ru.jpg | Teacher access page inside the new shell | `/ru/teacher-access` | student | 1440x900 | ru | 1440 | 65 |
| s5b-teacher-access-phone-ru.jpg | Teacher access page inside the new shell | `/ru/teacher-access` | student | 375x812 | ru | 375 | 57 |
| s5b-teaching-schemes-desktop-ru.jpg | Teaching area active (grading schemes) | `/ru/grading-schemes` | teacher | 1440x900 | ru | 1440 | 65 |
| s5b-teaching-schemes-phone-ru.jpg | Teaching area active (grading schemes) | `/ru/grading-schemes` | teacher | 375x812 | ru | 375 | 57 |
