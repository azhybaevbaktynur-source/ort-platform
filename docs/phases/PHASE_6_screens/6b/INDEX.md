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

## S5c teaching screens inside courses (branch `phase-6/s5c-teaching`, 2026-10-25)

62 JPEG files (full page, quality 70). Built frontend (`next build` + `next start` from an rsync'd copy) against a scratch backend (`env -i`, SQLite, `LMS_STORAGE_DRIVER=db`, data of the 6a UX run copied to `/tmp/agy_p6b_s5c/`), playwright-core + Chrome, viewports phone 375x812 (`isMobile`) and desktop 1440x900, ru, timezone Asia/Bishkek. `ort-teacher-*-before-*` = build of `83fc40a` (before S5c), `ort-teacher-*-after-*` and `s5c-teacher-*` = this branch. Teacher of the general course: `existing@example.com`; ORT course staff: the platform admin (owner of the ORT courses).

Measured `document.documentElement.scrollWidth` on every screen: 375 at 375 px and 1440 at 1440 px on all after screens (before: ORT staff attempts was 608 at 375 px, T3).

| File | Shows | Route | Viewport | Lang |
|---|---|---|---|---|
| ort-teacher-bank-list-after-desktop-ru.jpg | after: ORT bank list (layout kept, A6): PageHeader, one primary 'Создать банк' | `/ru/courses/{ORU}/bank` | 1440x900 | ru |
| ort-teacher-bank-list-after-phone-ru.jpg | after: ORT bank list (layout kept, A6): PageHeader, one primary 'Создать банк' | `/ru/courses/{ORU}/bank` | 375x812 | ru |
| ort-teacher-bank-list-before-desktop-ru.jpg | before: ORT bank list (layout kept, A6): PageHeader, one primary 'Создать банк' | `/ru/courses/{ORU}/bank` | 1440x900 | ru |
| ort-teacher-bank-list-before-phone-ru.jpg | before: ORT bank list (layout kept, A6): PageHeader, one primary 'Создать банк' | `/ru/courses/{ORU}/bank` | 375x812 | ru |
| ort-teacher-bank-questions-after-desktop-ru.jpg | after: ORT bank questions (layout kept, A6): PageHeader + bank TabsNav | `/ru/courses/{ORU}/bank/{bank}` | 1440x900 | ru |
| ort-teacher-bank-questions-after-phone-ru.jpg | after: ORT bank questions (layout kept, A6): PageHeader + bank TabsNav | `/ru/courses/{ORU}/bank/{bank}` | 375x812 | ru |
| ort-teacher-bank-questions-before-desktop-ru.jpg | before: ORT bank questions (layout kept, A6): PageHeader + bank TabsNav | `/ru/courses/{ORU}/bank/{bank}` | 1440x900 | ru |
| ort-teacher-bank-questions-before-phone-ru.jpg | before: ORT bank questions (layout kept, A6): PageHeader + bank TabsNav | `/ru/courses/{ORU}/bank/{bank}` | 375x812 | ru |
| ort-teacher-builder-after-desktop-ru.jpg | after: ORT builder: locked controls greyed with 'Задано шаблоном ОРТ', section header wraps (T7), item controls in one row on phones | `/ru/courses/{ORU}/assessments/{exam}/edit` | 1440x900 | ru |
| ort-teacher-builder-after-phone-ru.jpg | after: ORT builder: locked controls greyed with 'Задано шаблоном ОРТ', section header wraps (T7), item controls in one row on phones | `/ru/courses/{ORU}/assessments/{exam}/edit` | 375x812 | ru |
| ort-teacher-builder-before-desktop-ru.jpg | before: ORT builder: locked controls greyed with 'Задано шаблоном ОРТ', section header wraps (T7), item controls in one row on phones | `/ru/courses/{ORU}/assessments/{exam}/edit` | 1440x900 | ru |
| ort-teacher-builder-before-phone-ru.jpg | before: ORT builder: locked controls greyed with 'Задано шаблоном ОРТ', section header wraps (T7), item controls in one row on phones | `/ru/courses/{ORU}/assessments/{exam}/edit` | 375x812 | ru |
| ort-teacher-import-after-desktop-ru.jpg | after: ORT import page: default full_main kept, translated 'Выбрать файл' button + file name | `/ru/courses/{ORU}/bank/import` | 1440x900 | ru |
| ort-teacher-import-after-phone-ru.jpg | after: ORT import page: default full_main kept, translated 'Выбрать файл' button + file name | `/ru/courses/{ORU}/bank/import` | 375x812 | ru |
| ort-teacher-import-before-desktop-ru.jpg | before: ORT import page: default full_main kept, translated 'Выбрать файл' button + file name | `/ru/courses/{ORU}/bank/import` | 1440x900 | ru |
| ort-teacher-import-before-phone-ru.jpg | before: ORT import page: default full_main kept, translated 'Выбрать файл' button + file name | `/ru/courses/{ORU}/bank/import` | 375x812 | ru |
| ort-teacher-passage-editor-after-desktop-ru.jpg | after: ORT passage editor: PageHeader breadcrumbs, Tabs | `/ru/courses/{ORU}/bank/p/{passage}` | 1440x900 | ru |
| ort-teacher-passage-editor-after-phone-ru.jpg | after: ORT passage editor: PageHeader breadcrumbs, Tabs | `/ru/courses/{ORU}/bank/p/{passage}` | 375x812 | ru |
| ort-teacher-passage-editor-before-desktop-ru.jpg | before: ORT passage editor: PageHeader breadcrumbs, Tabs | `/ru/courses/{ORU}/bank/p/{passage}` | 1440x900 | ru |
| ort-teacher-passage-editor-before-phone-ru.jpg | before: ORT passage editor: PageHeader breadcrumbs, Tabs | `/ru/courses/{ORU}/bank/p/{passage}` | 375x812 | ru |
| ort-teacher-publish-panel-after-desktop-ru.jpg | after: ORT assessment page + publish panel: one primary (T8), 'Проверить перед публикацией' | `/ru/courses/{ORU}/assessments/{exam}` | 1440x900 | ru |
| ort-teacher-publish-panel-after-phone-ru.jpg | after: ORT assessment page + publish panel: one primary (T8), 'Проверить перед публикацией' | `/ru/courses/{ORU}/assessments/{exam}` | 375x812 | ru |
| ort-teacher-publish-panel-before-desktop-ru.jpg | before: ORT assessment page + publish panel: one primary (T8), 'Проверить перед публикацией' | `/ru/courses/{ORU}/assessments/{exam}` | 1440x900 | ru |
| ort-teacher-publish-panel-before-phone-ru.jpg | before: ORT assessment page + publish panel: one primary (T8), 'Проверить перед публикацией' | `/ru/courses/{ORU}/assessments/{exam}` | 375x812 | ru |
| ort-teacher-question-comparison-after-desktop-ru.jpg | after: ORT question editor, comparison: PageHeader breadcrumbs, design-system Tabs, 2x2 formatting toolbar, 2 MB image hint | `/ru/courses/{ORU}/bank/q/{q}` | 1440x900 | ru |
| ort-teacher-question-comparison-after-phone-ru.jpg | after: ORT question editor, comparison: PageHeader breadcrumbs, design-system Tabs, 2x2 formatting toolbar, 2 MB image hint | `/ru/courses/{ORU}/bank/q/{q}` | 375x812 | ru |
| ort-teacher-question-comparison-before-desktop-ru.jpg | before: ORT question editor, comparison: PageHeader breadcrumbs, design-system Tabs, 2x2 formatting toolbar, 2 MB image hint | `/ru/courses/{ORU}/bank/q/{q}` | 1440x900 | ru |
| ort-teacher-question-comparison-before-phone-ru.jpg | before: ORT question editor, comparison: PageHeader breadcrumbs, design-system Tabs, 2x2 formatting toolbar, 2 MB image hint | `/ru/courses/{ORU}/bank/q/{q}` | 375x812 | ru |
| ort-teacher-staff-attempts-after-desktop-ru.jpg | after: ORT staff attempts: Table with phone cards, student search, count (T3) | `/ru/courses/{ORU}/assessments/{exam}/attempts` | 1440x900 | ru |
| ort-teacher-staff-attempts-after-phone-ru.jpg | after: ORT staff attempts: Table with phone cards, student search, count (T3) | `/ru/courses/{ORU}/assessments/{exam}/attempts` | 375x812 | ru |
| ort-teacher-staff-attempts-before-desktop-ru.jpg | before: ORT staff attempts: Table with phone cards, student search, count (T3) | `/ru/courses/{ORU}/assessments/{exam}/attempts` | 1440x900 | ru |
| ort-teacher-staff-attempts-before-phone-ru.jpg | before: ORT staff attempts: Table with phone cards, student search, count (T3) | `/ru/courses/{ORU}/assessments/{exam}/attempts` | 375x812 | ru |
| s5c-teacher-assessment-detail-desktop-ru.jpg | Assessment page: one primary (T8), DescriptionList, sections, versions | `/ru/courses/{course}/assessments/{a}` | 1440x900 | ru |
| s5c-teacher-assessment-detail-phone-ru.jpg | Assessment page: one primary (T8), DescriptionList, sections, versions | `/ru/courses/{course}/assessments/{a}` | 375x812 | ru |
| s5c-teacher-assessments-list-desktop-ru.jpg | Assessments list: PageHeader one primary, Badges, action row under the text on phones (T6) | `/ru/courses/{course}/assessments` | 1440x900 | ru |
| s5c-teacher-assessments-list-phone-ru.jpg | Assessments list: PageHeader one primary, Badges, action row under the text on phones (T6) | `/ru/courses/{course}/assessments` | 375x812 | ru |
| s5c-teacher-bank-list-desktop-ru.jpg | Bank list: PageHeader, EmptyState with actions | `/ru/courses/{course}/bank` | 1440x900 | ru |
| s5c-teacher-bank-list-phone-ru.jpg | Bank list: PageHeader, EmptyState with actions | `/ru/courses/{course}/bank` | 375x812 | ru |
| s5c-teacher-bank-passages-desktop-ru.jpg | Passages: PageHeader primary 'Новый текст', excerpt cut at a word with an ellipsis (T23) | `/ru/courses/{course}/bank/{bank}/passages` | 1440x900 | ru |
| s5c-teacher-bank-passages-phone-ru.jpg | Passages: PageHeader primary 'Новый текст', excerpt cut at a word with an ellipsis (T23) | `/ru/courses/{course}/bank/{bank}/passages` | 375x812 | ru |
| s5c-teacher-bank-questions-desktop-ru.jpg | Bank questions: PageHeader + TabsNav | `/ru/courses/{course}/bank/{bank}` | 1440x900 | ru |
| s5c-teacher-bank-questions-phone-ru.jpg | Bank questions: PageHeader + TabsNav | `/ru/courses/{course}/bank/{bank}` | 375x812 | ru |
| s5c-teacher-builder-desktop-ru.jpg | Builder (general course): PageHeader breadcrumbs, section header wraps (T7) | `/ru/courses/{course}/assessments/{a}/edit` | 1440x900 | ru |
| s5c-teacher-builder-phone-ru.jpg | Builder (general course): PageHeader breadcrumbs, section header wraps (T7) | `/ru/courses/{course}/assessments/{a}/edit` | 375x812 | ru |
| s5c-teacher-course-home-desktop-ru.jpg | Staff course home: next step 'Создать задание' / 'Добавить вопросы' instead of the roadmap sentence, join code | `/ru/courses/{course}` | 1440x900 | ru |
| s5c-teacher-course-home-phone-ru.jpg | Staff course home: next step 'Создать задание' / 'Добавить вопросы' instead of the roadmap sentence, join code | `/ru/courses/{course}` | 375x812 | ru |
| s5c-teacher-gradebook-desktop-ru.jpg | Gradebook: PageHeader (actions rebuilt in Phase 7, T9) | `/ru/courses/{course}/grades` | 1440x900 | ru |
| s5c-teacher-gradebook-phone-ru.jpg | Gradebook: PageHeader (actions rebuilt in Phase 7, T9) | `/ru/courses/{course}/grades` | 375x812 | ru |
| s5c-teacher-import-desktop-ru.jpg | Import (general course, no format select) | `/ru/courses/{course}/bank/import` | 1440x900 | ru |
| s5c-teacher-import-phone-ru.jpg | Import (general course, no format select) | `/ru/courses/{course}/bank/import` | 375x812 | ru |
| s5c-teacher-my-courses-desktop-ru.jpg | After merging S6b: Teaching tab of a course creator (platform admin), "Каталог курсов" link after the list (T13), scrollWidth 1440 | `/ru/courses` | 1440x900 | ru |
| s5c-teacher-my-courses-phone-ru.jpg | After merging S6b: Teaching tab of a course creator, "Каталог курсов" link after the list (T13), scrollWidth 375 | `/ru/courses` | 375x812 | ru |
| s5c-teacher-passage-editor-desktop-ru.jpg | Passage editor (plain passage) | `/ru/courses/{course}/bank/p/{passage}` | 1440x900 | ru |
| s5c-teacher-passage-editor-phone-ru.jpg | Passage editor (plain passage) | `/ru/courses/{course}/bank/p/{passage}` | 375x812 | ru |
| s5c-teacher-people-desktop-ru.jpg | People tab: roster Table with phone cards and count (T2), add-staff card | `/ru/courses/{course}/people` | 1440x900 | ru |
| s5c-teacher-people-phone-ru.jpg | People tab: roster Table with phone cards and count (T2), add-staff card | `/ru/courses/{course}/people` | 375x812 | ru |
| s5c-teacher-question-editor-desktop-ru.jpg | Question editor: Tabs, toolbar | `/ru/courses/{course}/bank/q/{q}` | 1440x900 | ru |
| s5c-teacher-question-editor-phone-ru.jpg | Question editor: Tabs, toolbar | `/ru/courses/{course}/bank/q/{q}` | 375x812 | ru |
| s5c-teacher-settings-desktop-ru.jpg | Course settings: PageHeader, join code on one line (T20), design-system buttons and dialogs | `/ru/courses/{course}/settings` | 1440x900 | ru |
| s5c-teacher-settings-phone-ru.jpg | Course settings: PageHeader, join code on one line (T20), design-system buttons and dialogs | `/ru/courses/{course}/settings` | 375x812 | ru |
| s5c-teacher-staff-attempt-detail-desktop-ru.jpg | Staff attempt grading: breadcrumbs, 'Ответ ученика' and body font in review cards (T12, T22) | `/ru/courses/{course}/assessments/{a}/attempts/{attempt}` | 1440x900 | ru |
| s5c-teacher-staff-attempt-detail-phone-ru.jpg | Staff attempt grading: breadcrumbs, 'Ответ ученика' and body font in review cards (T12, T22) | `/ru/courses/{course}/assessments/{a}/attempts/{attempt}` | 375x812 | ru |
| s5c-teacher-staff-attempts-desktop-ru.jpg | Staff attempts: Table, search, count (T3) | `/ru/courses/{course}/assessments/{a}/attempts` | 1440x900 | ru |
| s5c-teacher-staff-attempts-phone-ru.jpg | Staff attempts: Table, search, count (T3) | `/ru/courses/{course}/assessments/{a}/attempts` | 375x812 | ru |

### S5c ORT teacher walkthrough (built frontend, desktop ru, `s5c_ort_flow.js`)

Import CSV + zip with the default `full_main`, create an `ort_main` exam through the dialog, add items to the five sections, locked controls, check before publishing, publish:

- PASS | Import CSV sample_ort_questions_ru.csv: default format is full_main | #imp-format = full_main
- PASS | Import CSV sample_ort_questions_ru.csv: chosen file name shown next to "Выбрать файл"
- PASS | Import CSV sample_ort_questions_ru.csv: preview passes | Импортировать 25 вопросов
- PASS | Import CSV sample_ort_questions_ru.csv: commit | Импорт завершён Источник: без manifest.json (RU) Папка в архиве: / Банк: sample_ort_questions_ru Раздел Всего Новые Обновлены Без изменений Правили вручную Удалены, пропущены Математика II 6 6 0 0 0 0
- PASS | Import bundle zip tsoomo19.zip: default format is full_main | #imp-format = full_main
- PASS | Import bundle zip tsoomo19.zip: chosen file name shown next to "Выбрать файл"
- PASS | Import bundle zip tsoomo19.zip: preview passes | Импортировать 150 вопросов
- PASS | Import bundle zip tsoomo19.zip: commit | Импорт завершён Источник: tsoomo19 (RU) Папка в архиве: / Банк: tsoomo19 Раздел Всего Новые Обновлены Без изменений Правили вручную Удалены, пропущены Математика I (Сравнение) 30 0 0 30 0 0 Математика
- PASS | Create dialog: ORT presets offered
- PASS | Create ORT exam with the 'ОРТ, основной тест' preset (UI) | /ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/assessments/71641192-1d79-4eb2-9aad-ef9707b17eda/edit
- PASS | New ORT exam has the five preset sections in order | Математика I (Сравнение) > Математика II > Аналогии и дополнения > Чтение и понимание > Практическая грамматика
- PASS | Builder: add 3 math_1 questions to section 1 | section counts [3,0,0,0,0]
- PASS | Builder: add 2 math_2 questions to section 2 | section counts [3,2,0,0,0]
- PASS | Builder: add 2 analogies questions to section 3 | section counts [3,2,2,0,0]
- PASS | Builder: add 2 reading questions to section 4 | section counts [3,2,2,1,2,0]: the reading section holds 1 passage item with its 2 questions ("Вопросов: 1" for the section, "Вопросов: 2" on the passage row, as in 6a); the script's first-pass regex read the item count
- PASS | Builder: add 2 grammar questions to section 5 | section counts [3,2,2,1,2,2]
- PASS | Locked: 'Добавить раздел' disabled
- PASS | Locked: section move up/down disabled
- PASS | Locked: section delete disabled | 5 disabled 'Удалить'
- PASS | Locked: disabled buttons are greyed (opacity < 1) | opacities 0.6
- PASS | Locked: note 'Задано шаблоном ОРТ' shown | 3 notes
- PASS | Check before publishing runs | Проблем не найдено.
- PASS | Draft: 'Опубликовать' is the one primary button
- PASS | Publish the ORT exam (UI) | Опубликовано Версия 1 Посмотреть как ученик Проверит
- PASS | API: published exam keeps preset ort_main, 5 sections, forward-only navigation | preset ort_main, sections 5, navigation section_forward_only, status published, items 11


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

## S7b

ORT player part 1 (`docs/ORT_PLAYER_IDEAS.md` Bugs + Part 1). Every changed ORT baseline as a pair: `before` = the S7a
baseline, `after` = the new approved baseline in `docs/phases/ORT_BASELINE/` (macOS, system Chrome; phone 375x812,
desktop 1440x900; ru + ky). Exam behaviour unchanged: the DOM walk (`frontend/e2e/ort.spec.ts`) passes with the same
assertions (section order, timer, palette count and states, comparison columns A/B with answers A-D, numbered
passage lines, result card with five section rows).

| Files (`ort-<screen>-<viewport>-<lang>-{before,after}.jpg`) | What changed | Part 1 IDs |
|---|---|---|
| `ort-lobby-{phone,desktop}-{ru,ky}` | "Start test" button with the hint "the section 1 timer starts at once" under it; on phones the start row is sticky at the bottom of the screen (in the full-page shot it floats over the middle, where the 812 px viewport ends); attempts value "0 из 1" without the repeated word; section rows as a two-column grid with the meta on one line; empty "available from / until" rows hidden and the total time as "3 h 35 min" (S9, left to S7b by S6b); not from S7b: the new `AppHeader` (S5b) and the student course frame with breadcrumbs (S6b) | L1, L2, L3, S9 |
| `ort-comparison-{phone,desktop}-{ru,ky}` | Sans-serif stem and choices (one family); 44 px answer rows and flag button on phones; timer label "Left in section" on desktop; phones: "Questions 1/3" button in the header opens the palette sheet, the palette and the outline finish button are no longer below the question; design-system Prev/Next buttons | P1, P3, P4, P7 |
| `ort-flagged-palette-{phone,desktop}-{ru,ky}` | Additive palette states: green fill = answered, grey = not, ring = current, amber dot = flagged (also on the current question); legend shows the dot, 12 px text; phones: the palette is the bottom sheet (focus trap, Esc, finish action inside), 44 px buttons; amber dot on the header button when something is flagged | P1, P2, P3, cross-cutting (legend size) |
| `ort-section-end-{phone,desktop}-{ru,ky}` | Phase 6 `Dialog` (focus trap, Esc, focus return); confirm says "Finish section" like the button that opened it; red only for the no-return sentence, counts neutral; full-width stacked buttons on phones | P5, cross-cutting (colors, components) |
| `ort-passage-{phone,desktop}-{ru,ky}` | Phones / tablets: sticky "Text" bar above the passage folds the text away and back (open by default, remembered per passage); line numbers unchanged; desktop side by side as before | P6 |
| `ort-submit-{phone,desktop}-{ru,ky}` | Same `Dialog` treatment as the section-end dialog; the "cannot change answers" sentence in red | P5, cross-cutting |
| `ort-result-{phone,desktop}-{ru,ky}` | "Test finished. Your result:" line; scaled grade card first, raw points as a small line under it; "Counts toward your grade" / "Points" instead of jargon; `Badge` components; section table without a minimum width (nothing cut at 375 px), short "Scale" header on phones, percentile on its own line in the total row | R1, R2, R3, B4 |
| `ort-review-{phone,desktop}-{ru,ky}` | Review grouped by section (folding groups, all open, "1 of 3 correct" per section) and an "Only mistakes and unanswered" filter (off by default); every card unchanged in content; sans-serif text; correctness `Badge` with an icon | R4, P7, cross-cutting |
| `ort-teacher-{bank,question-comparison,passage,import,builder,publish,attempts}-{phone,desktop}-ru` | **No S7b change.** The teacher baselines were re-recorded on top of phase-6b: new `AppHeader` and area shell (S5b) and the teaching screens on the design system (S5c: breadcrumbs, `PageHeader`, publish panel as a labelled region, `Table` with stacked cards). Two S7a locators followed S5c's markup (publish panel by its region name; the visible copy of the student name in the attempts `Table`); the assertions are the same | (S5b, S5c) |

Not in a baseline: the loading skeleton of the player and of a section (P11), the save pill texts (P10), keyboard
shortcuts with `e.code` (P9), the timer's warning icon and bold digits under five minutes (P4). The phone result
page is checked to be no wider than the viewport (B4) in `ort-visual.spec.ts`.
