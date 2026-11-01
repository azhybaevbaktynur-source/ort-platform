# UX rework: design (owner decisions UR-1…8, `docs/PRODUCT_DECISIONS.md`)

Reference: institutional Canvas. ORT exam behaviour, import and scoring do not change. All strings in en/ky/ru; delete keys that become unused (parity script must pass). Short labels; explanation only in empty states or a `title` tooltip. Reuse `components/ui`. Mobile first: nothing scrolls sideways at 375 px.

## A. Width (UR-1)
- One shell width in `LmsShell.tsx` (`<main>`, skeleton) and `AppHeader.tsx` (both bars): `mx-auto w-full max-w-[1600px] px-4 sm:px-6 lg:px-8`, as one exported constant.
- `AreaShell` side nav: `md:w-52 lg:w-60`, gap `md:gap-6 lg:gap-8`. Used by course, org and admin areas, so they all gain width.
- Page roots lose `mx-auto max-w-*`: lists, tables, dashboards and outlines fill the main area. Forms and reading text keep a readable max (`max-w-3xl`) but **left-aligned**, never centered. A dialog-like single-purpose page (join code, invite accept) may stay centered.
- Multi-field forms may use two columns from `lg`.
- **Exception (PUR-6)**: `/courses/[id]/attempts/**` (player, result, review) and the assessment lobby keep today's width: an inner `mx-auto max-w-6xl`. ORT frames only move with the header.

## B. Student course home (UR-2, PUR-4)
`courses/[courseId]/page.tsx`, student branch:
- `features.modules` true → `StudentModulesView` (any `home_kind`, ORT included).
- `home_kind = page` → that page, then the modules below it when `features.modules`.
- Otherwise today's `StudentCourseHome`. On production, ORT (Kyrgyz) has no modules and keeps today's home. ORT (Russian) has 3 published modules the owner built (both published exams and a file), so it gets the modules view; exam rows must open the same lobby and player as today, and the gating-exempt rule for ORT presets stays.

`StudentModulesView`: remove the "Up next" block and its one primary action. Modules as Canvas-style groups, full main width: module header (title, state, `done / total`), items as compact rows in order (kind icon, title, kind + due date in small text, done check, lock with reason). Pages, files, assignments, quizzes, links, headers all shown. On `xl` and wider a right column (`xl:grid-cols-[minmax(0,1fr)_300px]`) with this course's to-do (section C data filtered by course); fetch it only at that width; nothing rendered when empty.

## C. Student dashboard (UR-3, PUR-5)
Backend `GET /me/home` (`app/lms/home`): add `todo: list[HomeTodoOut]`, built like `_next_up` with `TODO_MAX = 20`, in-progress attempts first, then soonest due, no-date last. Each row: kind, course id and title, title, `due_at`, `available_until`, `attempt_id` when in progress, `overdue` bool, ids for the link. Keep the existing fields until the frontend no longer uses them, then remove `next_up`/`modules_next`/`in_progress` only if no test or screen depends on them; otherwise leave them.

Frontend `StudentHome.tsx`, rewritten:
- Title "Панель" (`home.dashboard`) in a row with two secondary actions: enter code, catalog.
- Banners only when needed: pending invitations, pending applications.
- `lg:grid-cols-[minmax(0,1fr)_340px]`. Left: course cards, `sm:grid-cols-2 xl:grid-cols-3 min-[1700px]:grid-cols-4`. Right: "К выполнению" list, then "Недавние оценки" (max 3) and announcements (max 3), each only when non-empty.
- Phone: to-do first when non-empty, then cards.
- Course card (`components/lms/home/DashboardCourseCard.tsx`): a colored band (about 96 px) from a fixed palette keyed on a hash of the course id (`lib/lms/courseColor.ts`, 8 colors, white text passes AA), course name, teacher name, small "next due" line when set. The whole card is the link. All courses reachable (use the existing paging when `courses_total > courses.length`).
- To-do row: kind icon, title, course name, date ("до 12 нояб., 23:59"; "Просрочено" for overdue; "Идёт попытка" for in progress). Empty: one friendly line.
- No greeting hero, no "Что дальше", no "Продолжить в курсе" strip.
- New student with no courses: an inviting empty state with enter code + catalog as primary actions.
- A teacher's "Учёба" area uses the same screen.

## D. Teacher course page (UR-4)
- `TodoPanel` goes. Replace it with a small "На проверку" list: from `xl` a right column shown only when something waits; below `xl` one line link "На проверку: N" above the modules, only when N > 0. Drafts, unpublished modules and student count are removed (they duplicate the outline). Join code moves to the top of People (keep copy button + link to enrollment settings), for staff only.
- "Вне модулей": one collapsed row at the end of the list, "Не в модулях · N", hidden when N = 0, no explanation paragraph, no totals line (a `title` tooltip carries the one sentence). Expanded: a flat list of one-line rows (kind icon, title, small kind text, "…" with Move to module / Edit / Delete). No nested group cards. "Все страницы"/"Все файлы" links go.
- Sidebar: `navFooter` legend removed; the crossed-eye marker keeps its tooltip.
- Outline:
  - Header row: "Модули" + primary "Новый модуль" + "…"; expand/collapse all moves into "…".
  - **Inline new module**: the button opens a title input in place at the end of the list (Enter creates, Esc cancels); settings stay in the module's "…".
  - **Inline rename** of a module and of an item ("Переименовать" in "…"; input in place, Enter saves, Esc cancels). Use the existing endpoints.
  - **Inline add**: module header has a `+` icon button (accessible name "Добавить в «…»"); the menu picks a kind; header/link/page/quiz/assignment open a title input (link: + URL) inline at the end of that module and create on Enter; page/quiz/assignment then stay in the list with a link to edit. File keeps its picker. "Добавить существующие" stays in the same menu. Reuse the calls in `AddItemDialog`; if a kind needs more than these fields, keep its dialog.
  - Rows are one line at `sm`+ (`min-h-11`): drag handle, icon, title, small muted kind/due text, publish toggle, "…". Metadata that isn't essential (language chip, sequential hint) moves to a tooltip or the menu. Empty module: one small `+ Добавить` ghost button, no sentence.
  - Page header and empty state: one short line at most.
- ORT course page: keeps the exam list and every function; only the "Структура курса" hint line goes and "На проверку" follows the rule above.

## E. Other teacher, org admin and platform admin pages (UR-4)
Sweep `app/[lang]/admin/**`, `app/[lang]/org/**`, `components/lms/org`, `components/lms/admin`, and the course's assignments, people, files, pages, announcements and settings pages:
- Remove or shorten `PageHeader` descriptions and helper paragraphs (a sentence stays only for a safety or legal consequence, or in an empty state).
- Rarely used or dangerous actions go inside a "…" menu (suspend, archive, export, delete). At most one primary button plus one secondary per header.
- Org and admin summaries: stat tiles for counts; settings as a compact list, moved under a "Настройки" tab or a disclosure, not eight long label/value rows.
- Tab rows must not cut off silently on desktop: fewer tabs (group rarely used ones into "…") when they overflow at 1280 px.
- Keep every function reachable. Don't touch ORT bank, import and exam screens beyond shell width.

## F. Student view (UR-5, PUR-1…3)
A real student session, Canvas style.

Backend:
- Migration `0015_test_student`: `users.is_test_student` (bool, false) and `enrollments.is_test_student` (bool, false); partial unique index: one active test enrollment per course.
- `app/lms/student_view/` (service, router; add to `route_inventory`):
  - `POST /courses/{course_id}/student-view`: real teacher or assistant enrollment only (not org-admin-only, not read-only, not platform-admin-only, never sandbox or deleted). Get or create the course's test user (unusable password hash, `email_verified` true, reserved address that can never be delivered, display name "Test student") with an active student enrollment `is_test_student = true`. Returns `{access_token, expires_in, course_id}`: normal JWT, `sub` = test user id, 4 hours. Race-safe. Audited.
  - `POST /courses/{course_id}/student-view/reset`: same authorization. Retires the current test user (`disabled_at` set, enrollment `removed`) and returns a fresh token for a new one. Nothing is deleted. Audited.
- `get_lms_user` and `get_current_user`: test users pass a **deny-by-default** allow-list by matched route template (`route_template` in `authz.py`): `GET /auth/me`, `GET /me/home`, `GET` of the my-courses list, `/courses/{id}/**` only for their own course, plus any attempt, media or file routes the student screens use. Never: leave, join, catalog apply, invitations, teacher requests, org, admin, exam templates, password or profile changes. Refusal: 403 `test_student_forbidden`. `POST /auth/login` can't succeed (unusable hash), and reset or code flows never apply.
- A draft course is readable and usable by its test student: in `can()` treat draft as published for a test user, and find any other direct `course.status` student check.
- **Exclusions** (`enrollments.is_test_student = false` / `users.is_test_student = false`): `roster_query`, `active_student_counts`, enrollment limit, every student count (`courses/service.py`, `organizations/service.py`, `organizations/usage.py`), gradebook and exports, hand-in and grading queues, staff attempt lists, "waiting for grading", accommodations pickers, module progress drawer, announcement recipients, platform admin users list and user pickers, catalog counts, any "this quiz has attempts" lock or warning. Also every future aggregate. Grep all `role == "student"`, `Attempt`, `Submission` staff queries.
- No email to a test user: guard in `email_service` for the reserved domain.
- `UserProfile` gains `is_test_student`. Check the response schema accepts the reserved address.
- **Remove the 8c mechanism**: `X-View-As`, `view_as_*`, `STUDENT_VIEW_READ_ONLY` and its tests in `authz.py`. The staff preview attempt stays, as a normal staff route.
- Tests (`tests/lms/test_student_view.py`, rewritten): issue/reset authorization matrix (student, other teacher, org admin without enrollment, platform admin, sandbox, deleted); full flow as test student (modules, start and submit a quiz, hand in, grade appears for them); excluded from roster, counts, gradebook, queues, admin lists; old token dead after reset; allow-list denies each forbidden group; draft course works; ORT course works and its golden and parity tests stay unchanged.

Frontend:
- `lib/api.ts`: remove `viewAsHeader`. Per-tab `sessionStorage["studentView"] = {courseId, token, expiresAt}`; `getAuthHeader` prefers it. Helpers `enterStudentView`, `leaveStudentView`, `resetStudentView` (enter and reset explicitly send the real `ort_token`). A 401 while in student view clears it and returns to the course as the teacher, never logging the teacher out. Check `auth-context.tsx` and raw `fetch` users.
- Banner in `LmsShell` on every page while active, sticky, warning color: "Вы смотрите курс как ученик" + "Сбросить тестового ученика" (with confirm) + "Выйти из режима ученика" (back to the course as teacher). Phone: compact, no overflow.
- Button stays in `StaffCourseBar`; starts the mode and goes to the course home. In the mode the app simply renders as the test student; remove `isStudentView` branches, read-only notices and `student_view_read_only`.
- The header shows the name "Тестовый ученик" (i18n) when `is_test_student`.

Fallback (UR-5): if it can't be made to work, remove the button and note it in the plan. Say so; don't ship half.

## G. Slices
- **S1** Student view, full stack (section F).
- **S2** Width, student course home, dashboard (A, B, C).
- **S3** Teacher, org and admin simplification (D, E).

Shared-file notes: S2 owns `LmsShell` and `AppHeader` widths; S1 adds only the banner line in `LmsShell`, and owns `api.ts`. S3 owns `components/lms/course/*`, `components/lms/modules/ModuleOutlineEditor*`, `OutlineDialogs`, `AddItemDialog`, `UnsortedGroup`. S2 owns `StudentModulesView`, `components/lms/home/*`, and root-width fixes outside S3's area; on `app/[lang]/admin/**` and `app/[lang]/org/**`, S3 does the width fixes too. i18n JSON: append keys only inside your own section to keep merges simple.

## H. Checks
Backend suite on scratch DB; `alembic upgrade head && alembic check` on PG; `tsc`; i18n parity; `frontend/e2e` specs that touch the screen (update them if the UI changed on purpose; ORT specs' DOM assertions must keep passing unchanged). Agents: no `ux-reviewer`, no screenshot sets.
