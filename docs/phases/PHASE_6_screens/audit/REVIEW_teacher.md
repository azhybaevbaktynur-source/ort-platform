# UX audit: teaching area (current app, branch `lms`, 2026-10-24)

Reviewed all 70 `teacher-*` screenshots (375 px and 1440 px, ru) against `docs/UX_GUIDELINES.md`; code opened only to confirm causes. Paths are under `frontend/src/`.

**Totals**: 1 blocker, 16 major, 13 minor.

## What works well (keep)
Stable course frame (back link, title + status badge, same six tabs everywhere); every delete/unpublish/void goes through `ConfirmDialog` and names the object; icon-only buttons carry `aria-label` (83 uses); the publish panel lists validation errors in red before publishing; the gradebook has a legend, sticky student column and per-cell accessible labels; the attempt detail puts the essay that needs review first and offers "only pending" filtering; the create-assessment dialog explains each preset in one sentence; the scheme editor has a live preview table.

## Findings: teaching (most severe first)

### Blocker
**T1. A section title set in the builder crashes the student player.** Screen: `teacher-19-builder-*` (SectionDialog) → `student-90-*`. Problem: `GET /attempts/{id}/content` returns `sections[].title` as `{ru, ky}` and `PlayerShell.sectionTitle()` renders it as a string (React #31). Why it hurts: a normal teacher action makes the exam unopenable for every student; nothing warns the teacher. Fix: pick the localized string in `components/lms/player/PlayerShell.tsx` (`pickLocalized(title, lang, defaultLanguage)`), add an error boundary around the player, add a test that publishes a titled section and opens the attempt.

### Major
**T2. Roster table unusable at 375 px.** `teacher-04-people-phone-ru.jpg` (`/courses/<C>/people`). The page renders 727 px wide; Role, Status, Date and "Удалить" are off-screen. Cause: `components/lms/RosterTable.tsx:31` keeps a 6-column table on phones. Fix: below `sm`, render stacked cards (name + role badge, email; actions row with the role `select` and "Удалить"); keep the table from `sm` up. Also show the count ("Учеников: 4").

**T3. Staff attempts table unusable at 375 px.** `teacher-23-staff-attempts-phone-ru.jpg`, `teacher-25-*-ort-phone-ru.jpg` (ORT screen, layout only). Page 772 px / 608 px wide; score, grade and "Открыть" are off-screen; the "Проверить: 1" badge is clipped. Cause: `components/lms/results/StaffAttemptList.tsx:93-94`. Fix: phone cards with student, status badge, score, one "Открыть" link; add a student search box and a total count; keep `Pager`.

**T4. Question editor overflows horizontally on phones.** `teacher-08/09/10-question-editor-*-phone-ru.jpg` (page is 511 px wide; T10 is an ORT screen, layout only). Cause: the four editor tabs are `flex gap-1` with no wrap or scroll at `app/[lang]/courses/[courseId]/bank/q/[questionId]/page.tsx:72`. Fix: `flex-wrap` or `overflow-x-auto` on the tablist (same pattern as `CourseTabs.tsx:26`).

**T5. ORT curve scheme page overflows at 375 px; preview cut on desktop.** `teacher-29-grading-scheme-ort-phone-ru.jpg` (545 px wide), desktop preview column "Золотой сертиф…" clipped. Cause: `components/lms/grading/schemes/CurveForm.tsx:53` `min-w-[34rem]` (= 544 px) escapes its wrapper; `SchemePreview.tsx:102` table has 5 columns in a 24 rem column. Fix: add `max-w-full` to the wrapper at `CurveForm.tsx:52` and stack the segment row as a card on phones; let the preview table scroll inside its box (`min-w-max` on the table). System-scheme view, no scoring change.

**T6. Draft assessment card breaks on phones.** `teacher-16-assessments-list-phone-ru.jpg`. The title "Домашнее задание: ткани" and meta are squeezed to one word per line beside the buttons. Cause: `components/lms/assessments/StaffAssessmentList.tsx` action block `flex flex-wrap gap-2` sits beside the `min-w-0 flex-1` text block. Fix: give the action block `w-full sm:w-auto` so it drops to its own row below `sm`. Also "Снять с публикации" on a test with 4 submissions goes straight through `flow.unpublish` without a confirmation: route it through `ConfirmDialog` naming the test and the attempt count.

**T7. Builder section header wraps one word per line on phones.** `teacher-19/20-builder-*-phone-ru.jpg` ("1. / Раздел / 1"). Cause: `components/lms/assessments/SectionCard.tsx:54-68` header keeps title and four buttons on one line. Fix: `flex-wrap` with the actions as a second row (`basis-full sm:basis-auto`); truncate item titles with `line-clamp-2` instead of one line.

**T8. Assessment page has six top actions and two primary buttons.** `teacher-18-assessment-detail-desktop-ru.jpg`: "Попытки", "Изменить" (primary), "Посмотреть как ученик", "Проверить", "Снять с публикации", "Опубликовать изменения" (primary). "Проверить" is also the word used for grading. Fix: one primary ("Опубликовать изменения" when there are changes, else "Изменить"); rename validate to "Проверить перед публикацией" / "Жарыялоодон мурда текшерүү" / "Check before publishing"; move "Снять с публикации" into a secondary group.

**T9. Gradebook actions are hidden.** `teacher-26-gradebook-*`. Release, hide and regrade exist only behind the "…" icon in a column header (`StaffGradebook.tsx:158`), explained by a sentence above. Guideline §4: no hidden features. Fix: a visible "Действия" button per column header with text, plus a page-level "Опубликовать оценки" bulk action and "Экспорт CSV".

**T10. Teacher course home has no actions and shows roadmap text.** `teacher-03`, `teacher-31`, `teacher-35`. "Уроки и задания появятся здесь в следующих обновлениях" (`courses.home.contentSoon`, `app/[lang]/courses/[courseId]/page.tsx:69`); the join code is only in Settings. Fix: for staff, show the join code (`JoinCodeDisplay`) with copy, "Нужна проверка: 3" linking to attempts, and shortcuts "Новое задание", "Добавить вопросы"; drop the roadmap sentence.

**T11. Import defaults to the ORT template in a general course.** `teacher-15-import-*`. `components/lms/content/import/ImportPanel.tsx:32` starts with `"full_main"`; a biology CSV then fails the ORT section check. Also the native "Choose file" is English, and "ort-digitizer", "manifest.json" are technical. Fix: default to `""` (general) unless the course is an ORT course; replace the native input with a labelled button + file name; move the zip details into a help line.

**T12. Student's answer labelled "Ваш ответ" in staff grading.** `teacher-24-staff-attempt-grading-*`. `components/lms/results/ReviewItemCard.tsx:107,117,133,142,153` reuses the student label. Fix: `viewer: "student" | "staff"` prop; staff label "Ответ ученика" / "Окуучунун жообу" / "Student's answer".

**T13. Teacher's "My courses" opens with the student catalog.** `teacher-01-my-courses-*`: two "Записаться" cards sit above "Мои курсы"; course cards show no student count or pending work. Fix: for `can_create_courses` users render `CatalogSection` after the course list, collapsed; add "Учеников: 4 · Нужна проверка: 3" to `CourseCard`.

**T14. Bank question list: filters first, hidden "new" action, no bulk actions.** `teacher-07-bank-questions-*`. Seven filters are expanded by default (the whole first phone screen); "Новый вопрос" is a `<select>` (`bank/[bankId]/page.tsx:88`); no multi-select to move/delete/tag. Fix: a search box + "Фильтры (0)" toggle; a primary "Новый вопрос" button opening a type menu; checkboxes with a bulk bar (delete, move to bank, set topic).

**T15. Question editor is twice as long as needed.** `teacher-08-*-phone-ru.jpg` is 3684 px: every field has a permanent "ПРЕДПРОСМОТР" block although a "Предпросмотр" tab exists; textareas use a monospace font. Fix: show the inline preview only when the text contains `$` or formatting, otherwise a "Показать предпросмотр" link; body font in textareas; "Сохранить" sticky at the bottom.

**T16. Times shown in UTC as if local.** `teacher-18` versions, `teacher-23` "Сдано", `teacher-24` header. Backend returns naive ISO datetimes (INDEX bug 2). Fix: serialize with timezone (`Z`) in the attempt/assessment schemas; format with `toLocaleString(lang)`.

**T17. Inconsistent glossary.** Nav "Схемы оценивания" vs page "Шкалы оценивания" (`ru.json:107` vs `:1623`); tab "Задания" vs "тест"/"контрольная" in body copy; "Проверить" for validate, file check and grading. Fix: one term per concept per language (suggest "Шкалы оценивания", "Задания", "Проверка" only for grading).

### Minor
- **T18** Create-assessment overlay leaves a white strip above the header (`assessments/Modal.tsx:24`, `items-start`+`my-8` with page scroll); use `inset-0` on a non-scrolling overlay and scroll the panel.
- **T19** Phone header takes ~250 px on every screen (5 links + languages + account, `LmsShell.tsx:78-115`); collapse the nav into a menu button below `md`.
- **T20** Join code wraps "VDMW–/YX3H" on phones (`teacher-05-settings-phone`); `whitespace-nowrap` and a smaller size in `JoinCodeDisplay`.
- **T21** Image hint says "до 5 МБ" while the limit is 2 MiB (`ImagePicker`); state the real limit.
- **T22** Review cards use a serif font (`ReviewItemCard.tsx:82,100`); guideline: one family.
- **T23** Passage card truncates mid-word without an ellipsis (`teacher-12`); `line-clamp-2`.
- **T24** Empty states lack their own button ("Заданий пока нет.", "Разделов пока нет."); use `EmptyState` with the action inside.
- **T25** People: the "add staff" form permanently occupies the top of the page and search needs a button; make it "Добавить учителя" → dialog, live search.
- **T26** Technical words visible to teachers: "Версия 1" in the editor title, codes `g5`, `golden_certificate`, `math_1`/`quantitative_comparison` (ORT bank, ORT screen); label them ("Код (для экспорта)") or hide by default.
- **T27** "Текст: Без названия" repeated in the ORT builder (ORT screen); show the first words of the passage instead.
- **T28** Course settings has three separate "Сохранить" buttons and a 2000 px page; one sticky save bar or per-section accordions.
- **T29** Course tabs wrap into two rows on phones (`CourseTabs.tsx:26`); a single scrollable row with the active tab in view.
- **T30** Scheme list cards have no visible action (whole card is the link); add "Открыть".

## Cross-cutting design-system issues
- **Tables**: three hand-made tables, each with its own phone failure (T2, T3, T5). Need one `Table` with a `cardBelow="sm"` mode and a `Pagination`/count footer.
- **Buttons**: at least four button class strings (`btnSmall`, inline classes, red outline "Удалить"/"Убрать"); two primaries on one screen (T8). Need `Button` variants primary/secondary/danger/link with one primary per page.
- **Tabs**: three tab implementations (`CourseTabs`, editor tablist, my-courses tabs) with different overflow behaviour (T4, T29). One `Tabs` that scrolls.
- **Dialogs**: `ConfirmDialog` and `Modal` are separate; the modal has the overlay gap (T18). One `Dialog` with focus trap and `max-h` scrolling.
- **Type**: Inter plus monospace textareas plus serif review text (T15, T22). One family; 16 px body on phones.
- **Empty/loading/error**: loading is a text line, empties are plain paragraphs (T24); introduce `EmptyState`, `Skeleton`, keep `ErrorMessage` with Retry.
- **Badges**: status pills are inline class strings with inconsistent colors (amber "Черновик", emerald "Опубликован", blue "Владелец"); a `Badge` with semantic variants.
- **Page header**: back link + title + actions are rebuilt per page; a `PageHeader` with title, status badge, one primary and a secondary group.

## Design-system components the teaching screens most need (priority order)
1. `Table` (sortable headers, search, count, cursor pagination, stacked-card mode under 640 px).
2. `PageHeader` (title, badge, breadcrumbs, primary + secondary actions, wraps on phones).
3. `Button` and `IconButton` (variants, loading, forced `aria-label`).
4. `Dialog` / `ConfirmDialog` (focus trap, Esc, scroll inside, danger variant naming the object).
5. `Tabs` (scrollable, `aria-selected`, used by course, editor and list pages).
6. `EmptyState`, `Skeleton`, `ErrorState` with Retry.
7. `Badge` (status, role, correctness) and `Toast` for "saved"/"published".
8. `FilterBar` (search + collapsible filters + active count) for banks, people, attempts, gradebook.
9. `BulkActionBar` (selection count + actions) for the bank and gradebook.
10. `LocalizedTextInput` and `MathTextarea` (toolbar, collapsible preview) as shared editors.

## Navigation recommendations for a "teaching area" in the 4-area app
- **Area switcher in the header**, one item per area the person has: "Учусь", "Преподаю", "Организация", "Платформа". Each area has its own landing page; the global nav shows only that area's sections. Phase 6's org admin adds the third entry without touching course pages.
- **Teaching landing** (`/teach`): list of courses taught with per-course counters (students, needs review, drafts) and the three cross-course tools as a secondary row: "Создать курс", "Шкалы оценивания", "Корзина". The catalog and "Присоединиться" belong to the student area only.
- **Inside a course**: keep the six tabs but order them by workflow: Главная (teacher dashboard, T10) · Задания · Банк вопросов · Участники · Оценки · Настройки. Breadcrumb "Преподаю › Биология 9 класс › Задания › Контрольная: клетка" replaces the stacked "Назад к…" links.
- **Depth rule**: at most three levels under a course (tab → object → sub-page such as attempts or edit); the question editor and builder are full-width "work" pages with a sticky save bar and a single back crumb.
- **ORT template courses** (locked template): same frame, with a lock badge next to the course title and disabled structure actions explained in a tooltip ("Структура ОРТ закреплена шаблоном"), so staff do not look for missing buttons.
- **Phone**: header collapses to logo + area menu + account; course tabs scroll horizontally; tables become cards.

## ORT player ideas (owner decision)
None from the teaching screens. All ORT-related findings above (T3, T4, T5, T26, T27) are readability or layout only and keep the exam unchanged.
