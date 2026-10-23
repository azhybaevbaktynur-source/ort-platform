# UX audit: public + student (current app, branch `lms`, screenshots 2026-10-24)

Scope: `public-*`, `student-*` except player/lobby/section-end/submit/result/review/error-player. Standard: `docs/UX_GUIDELINES.md`. Code paths are under `frontend/src/`. Totals: 0 blockers, 11 major, 10 minor.

## What works well (keep)

- Join-by-code: big monospace input, disabled button until a code is typed, error text that says what to do (`student-03`). Course-not-found and "Нет доступа" pages are friendly, with a way back (`student-04`, `student-37`).
- "Leave course" goes through `ConfirmDialog` (`courses/[courseId]/page.tsx:75`). Pending grade row explains why there is no number yet (`student-32`). Pending teacher request shows an amber badge on My courses and a clear status on the request page (`student-35/36`).
- Every page already has an `ErrorMessage` with Retry, and language switching keeps the current route (`LmsShell.tsx:43`).

## Findings: public (anonymous)

**P1. Landing header overflows on the phone.** `public-01-landing-phone-ru.jpg` is 593 px wide: the header (`app/[lang]/page.tsx:17`, `h-16 flex justify-between`, no wrap) pushes the language switcher + Login + Register past 375 px, the brand name wraps and the first word is clipped. Why: horizontal scroll on the first screen a student sees; the Register button is partly off-screen. Fix: on `<sm` hide the subtitle, show only the brand mark, keep the language switcher, and drop Login/Register from the header (they are already in the hero). Or `flex-wrap` + `h-auto`. Severity: major.

**P2. Auth pages have a different, hard-coded language switcher (no English).** `login/page.tsx:81-96` renders literal "Кыргызча"/"Русский" and no `en`; the tagline "ЖРТ / ОРТ 2026" (`:76`) is hard-coded too; register/forgot-password repeat it. Why: an English user who chose EN on the landing lands on a Russian-only switcher; breaks the trilingual rule (§5). Fix: reuse one `LanguagePicker` (exists in `components/lms/LanguagePicker.tsx`) with `en/ky/ru` and move the tagline to `landing.badge`. Also the switcher touches the right edge at 375 px (`public-02-login-phone-ru.jpg`): give the header `px-4` on both sides. Severity: major.

**P3. Auth copy is ORT-only while the product is an LMS.** "Вход в систему ОРТ", "Регистрация в ОРТ", "Создайте аккаунт для начала подготовки к экзамену" vs the landing's "Учебная платформа для учителей и учеников". Fix: "Вход" / "Регистрация" + the landing badge as subtitle (keys `auth.login.title`, `auth.register.*`). Severity: minor.

**P4. Register form gives no rules.** No password requirement hint, no show-password toggle, phone label "(WhatsApp/Telegram)" does not say whether it is required (`public-03`). Fix: helper text under Password ("Не менее 8 символов"), an eye toggle with `aria-label`, and "(необязательно)"/required mark on Phone. Severity: minor.

## Findings: student

**S1. After the last attempt the assessment page is a dead end.** `student-26`, `student-31`: the lobby shows only "Вы использовали все попытки." `LobbyView.tsx` never calls `listMyAttempts` (available in `lib/lms/attempts.ts:13`), so there is no link to the result; the student has to guess that it lives under "Оценки", and only once grades are released. Why: the most important thing after an exam (my score) is unreachable from where the student is. Fix: in `LobbyView` load `listMyAttempts(course.id, lobby.id)` and render "Мои попытки" (date, status, "Посмотреть результат" when `results_available`); when attempts are exhausted make that list the primary content and the amber notice secondary. Severity: major.

**S2. "Не сдано" shown for an assessment the student simply has not started.** `student-08`: state `missing` → ru "Не сдано" (`ru.json:1585`), which in Russian reads as "failed", before any due date and before any attempt. Why: a teenager reads a fail mark on day one. Fix: ru "Ещё не сдано", ky "Азырынча тапшырылган жок", en keeps "Not submitted"; better, the API distinguishes `not_started` (no due date passed) from `missing` (due date passed), and the row shows an "Открыть" link for `not_started`. Severity: major.

**S3. My courses is not a student home.** `student-01/11/34`: the public catalog sits above "Мои курсы"; three filled primary buttons on one screen (two "Записаться" + "Стать учителем"); a pure student sees a "Преподаю" tab (`courses/page.tsx:96` renders both tabs unconditionally); course cards show "Опубликован", "Ученик" and "RU / KY" (`CourseCard.tsx:30-37`) and nothing about what to do next. Why: §2 says the home answers "what should I do next?"; this page answers "what can you sell me". Fix: see the proposal below; short-term: render the catalog after the course list, only one primary button (Join by code), tabs only when `me.can_create_courses`, drop the status badge for students, show language names from `courses.languages.*`. Severity: major.

**S4. Phone header takes 250 px on every page.** `student-05-course-home-phone-*`: brand, language row, name + Logout, then 2-3 rows of nav links (`LmsShell.tsx:78-117`, `flex-wrap`); content starts a third of the way down an 812 px screen, before the course title and tabs. Why: every student page on a phone starts with chrome; `ky` and `ru` labels wrap to three rows. Fix: one 56 px row: brand mark, page area, an account menu (name, language, log out) on the right; the nav as a `Tabs`-style bar below only on `/courses`, and inside a course only the course tabs. Severity: major.

**S5. Course home has no next action.** `student-05/12`: "О курсе" card with "Моя роль: Ученик" (the student knows), "Опубликован" badge (teacher state), then the roadmap sentence "Уроки и задания появятся здесь в следующих обновлениях." (`courses.home.contentSoon`) and a red "Покинуть курс". Why: the student opens the course and still does not know what to do. Fix: on the student home render the next assessment (from `listAssessments`) with one primary button (Начать / Продолжить), the latest released grade, then the description; delete `contentSoon`; put "Покинуть курс" into a secondary "…" menu or the bottom of the page in a quiet link style. Severity: major.

**S6. The assessment list does not show status.** `student-06/13`: "Вопросов: 6 · 20 мин · Попытки 0 из 1", button "Открыть" (secondary only), no due date, no "done / score". "Попытки 0 из 1" reads as "0 attempts out of 1", not "none used". ORT shows "215 мин". `StudentAssessmentList.tsx:54-76`. Fix: a status `Badge` per row ("Не начато", "В процессе", "Сдано · 4/25", "Проверяется"), `due_at` when set (field exists on `AssessmentStudentSummaryOut`), attempts as "Осталось попыток: 1", a primary button for the one row that is in progress or next, and a `fmtDuration` helper ("3 ч 35 мин"). Severity: major.

**S7. ORT grades: "Итог по курсу 16 %" next to a scaled score of 87.** `student-33`: the course total uses raw percent (4/25) while the row shows the ORT curve value. Why: two numbers for one exam, the small one dominates and demotivates. Fix: for a course whose scheme is a curve, show the total as the scheme value (or hide the total when there is a single assessment); `StudentGrades.tsx` total block. Severity: major.

**S8. Students see the teacher-only grading-scheme library.** `student-38`: `/grading-schemes` renders `SchemeLibrary` for anyone signed in; only the create button is gated (`SchemeLibrary.tsx:71`). Text says "во всех ваших курсах". Fix: in `grading-schemes/page.tsx` gate on `me.can_create_courses || me.is_platform_admin` and render the same "Нет доступа" card as `/admin`. Severity: major.

**S9. Lobby details are noisy and duplicated.** `student-26/31`: label "Попытки" over value "Попытки 1 из 1"; "Доступно с: В любое время" and "Доступно до: Без даты окончания" shown even when nothing is set; "215 мин". `LobbyView.tsx:55-64`. Fix: value "1 из 1" (or "Осталось: 0"); hide the two date rows unless set; duration in hours. Severity: minor. (The rest of the lobby belongs to the player review.)

**S10. One action, four names.** Nav "Присоединиться к курсу", button "Войти по коду", catalog "Записаться", ky "Курска кошулуу" / "Код менен кирүү" / "Кошулуу"; "Стать учителем" (nav) vs "Стать преподавателем" (page title) vs "Ваш статус преподавателя". Fix: one glossary entry per language: join by code = "Войти по коду" / "Код менен кирүү" / "Join with code"; catalog join = "Записаться" / "Жазылуу" / "Join"; teacher = учитель / мугалим everywhere. Severity: minor.

**S11. Catalog cards show "Учеников: 0" and "Учитель: ORT".** `student-01`, `student-34`. An empty course looks dead; the platform course has no human owner. Fix: hide the count under 10; for platform-owned courses show "Курс платформы" instead of the owner line (`CourseCard.tsx:34`). Severity: minor.

**S12. Course tabs wrap to two rows on the phone** (`student-05-phone-*`, `CourseTabs.tsx:27` `flex-wrap`). Four tabs fit at 375 px only in en. Fix: horizontally scrollable tab row (`overflow-x-auto`, no wrap) or shorter labels. Severity: minor.

**S13. Empty "My courses" has text but no button** (`student-35`): "Используйте код от учителя." Fix: an `EmptyState` with the Join-by-code button inside it. Severity: minor.

**S14. People tab for students lists only staff under "Участники".** Fine for privacy, but the tab name promises classmates. Fix: rename the student view heading to "Учителя" or hide the tab for students until Phase 7 shows what students may see. Severity: minor.

**S15. Timestamps with seconds** ("23.10.2026, 16:55:22", `student-36`) and UTC-as-local (INDEX bug 2). Fix: `fmtDateTime` without seconds and parse server times as UTC. Severity: minor.

**S16. Loading states are plain text.** Every page shows "Загрузка…" in a paragraph; no skeleton, and `LmsShell` blanks the whole screen while `/auth/me` loads (`LmsShell.tsx:54-60`). Fix: `Skeleton` component in the page layout (§5). Severity: minor.

## Cross-cutting design-system issues

- **Colors**: ok on brand/slate; the gradebook-style state colors (indigo "Ожидает", sky "Освобождён") are not in the palette rule (green/amber/red). Status badges need one `Badge` with `neutral | info | success | warning | danger`.
- **Type**: body text on student pages is 14 px (`text-sm`) almost everywhere; §5 asks for 16 px on a phone. Section labels in all-caps (`О КУРСЕ`) are hard in Cyrillic; use a normal-case section title.
- **Spacing**: cards use `p-4`, `p-5` and `p-6` across pages; pick one `Card` padding.
- **Components** (each is currently re-styled inline): `Button` (primary/secondary/danger/link; `btnPrimary` strings in `components/lms/content/ui.ts` are the seed), `Badge`, `Card`, `Tabs` (course tabs, My courses tabs, auth language switcher are three implementations), `EmptyState` (dashed box in `courses/page.tsx:108`), `ErrorState` (`ErrorMessage` is close), `Skeleton`, `PageHeader` (title + badge + back link repeated per page), `Dialog` (`ConfirmDialog`, `Modal`), `Input` with label and help text (auth forms and join form differ), `LanguagePicker` (reuse on auth pages), `AppHeader` with account menu.
- **States**: loading is text only; empty states lack buttons; errors are good.
- **Writing**: glossary (S10); "contentSoon" roadmap text in product UI; teacher states leaking to students ("Опубликован", "Моя роль").

## Student home proposal (Phase 6)

Route: `/[lang]/courses` for a user without `can_create_courses` (teachers keep the current list as their "Teaching" area; a teacher who also studies gets a "Learning" tab that renders this home). All data comes from calls that already exist in `lib/lms/`.

Sections, in order (phone: one column, 16 px gutters, each section a `Card`; desktop: max 720 px column, same order):

1. **Greeting line + one primary action.** "Привет, Нурлан" (`getMe().display_name`). Below it the single primary button chosen by priority: Continue (any `in_progress_attempt_id`) > Start the next due assessment > Join a course (no courses). Everything else on the page is secondary.
2. **Continue** (only when present): one card per attempt in progress: assessment title, course title, "Продолжить" primary. Data: `listMyCourses("learning")` then `listAssessments(courseId)` per course, `in_progress_attempt_id` (max 24 courses, 50 assessments each, loaded after the shell with skeletons).
3. **Next up**: up to 3 assessments not yet done, sorted by `due_at` (then `available_until`, then newest), each with course name, due date ("Срок: 28 окт", red when < 24 h), attempts left, button "Открыть" (secondary). Empty: "Новых заданий нет. Загляните позже или откройте курс." + link to the course list.
4. **Latest results**: up to 3 graded rows from `getMyGrades(courseId)` (`items[].state === "graded"`, newest `released_at`), each with the scheme value (`display_value`/`label`), course name and "Посмотреть результат" → `/attempts/{kept_attempt_id}/result`. Small celebration: a one-line "Лучший результат по курсу" badge when the value is the student's max (client-side compare). Empty: "Результатов пока нет. Они появятся после первого задания."
5. **My courses**: compact rows (title, teacher, next due or "Без заданий"), tap opens the course; secondary "Войти по коду" and a link "Каталог" under the list. Empty state (`EmptyState`): "Вы пока не записаны ни на один курс." + primary "Войти по коду" + secondary "Открыть каталог".
6. **Catalog**: moved to its own page `/courses/catalog` (nav link stays); on the home only the link above. The "Become a teacher" banner moves to the account menu for students.

Empty home (new student): sections 2-4 hidden, section 5 empty state is the hero; nothing else.

Phone layout: sticky 56 px header (brand, account menu); greeting; primary button full width; cards stacked; course rows with 44 px tap height; no tables. Load order: shell and greeting from cached profile immediately, then `listMyCourses`, then per-course calls in parallel with skeleton rows; cap at the first 10 courses and show "Показать все" for more.

Existing API data that covers it: `getMe` (name, locale), `listMyCourses("learning")` (`CourseCard`: title, owner, status), `listAssessments(courseId)` (`AssessmentStudentSummaryOut`: `due_at`, `available_until`, `attempts_used`, `allowed_attempts`, `in_progress_attempt_id`, `last_result`), `getMyGrades(courseId)` (`MyGradeOut`: `state`, `display_value`, `label`, `kept_attempt_id`, `released_at`, `due_at`), `listMyAttempts` (for section 2 dates).

New API data needed (one call instead of N+1): `GET /me/home` returning `{ in_progress: [{attempt_id, assessment_title, course_id, course_title, started_at}], next_up: [{assessment_id, course_id, course_title, title, due_at, available_until, attempts_left}], latest_results: [{assessment_id, course_id, course_title, title, display_value, label, scheme_type, released_at, kept_attempt_id, is_personal_best}], courses: [{id, title, owner_display_name, next_due_at, in_progress}] }`, limited server-side (3/3/3/10). Also a `not_started` grade state (S2) and `fmtDuration` for ORT times. Nothing here touches the ORT player.

## ORT player ideas (owner decision)

None from this scope.
