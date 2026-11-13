# One student interface: hub + course spaces (fix round 2026-11-12, step 3a)

**Status**: design **v3** (architect on Fable, 2026-11-13 evening): v2 plus the owner's review of the built 3a
(`FIX_ROUND_2026-11-12.md`, "Owner round 2026-11-13 (after 3a/3b, verbatim)", items 2–4): no learner «Мои курсы» page,
the catalog as the one way to add a course, «Сохранённые» → «Повторение», subject icons. §0 holds the v3 decisions and
slices S7–S10; the sections below are corrected in place where v2 is now wrong (marked "v3"). v2 (same day) replaced
the v1 design of 2026-11-12 after the owner's final direction ("Owner final direction on the step 3 designs
(2026-11-13, verbatim)"). Base of v3: `lms` 1209fc6, alembic head `0034_course_listing`, 3a S1–S6 and 3b S1–S4
deployed. Rules: AGENTS.md §6.9 (ORT exam rules fixed; ORT is a normal course); owner 2026-11-12: teachers and students
are separate accounts, so this design is for people who learn (`learnsHere(me)`) and for Student view; the teacher
interface changes only where §5 says.

Before-screenshots (production code, student account, ru): `docs/phases/STUDENT_IA_screens/before/01-home-1440.png` …
`08-ort-lessons-1440.png`.

**Owner direction in one paragraph.** One student interface like an institutional LMS home plus separate course
spaces: `/home` is a hub only (continue card, course cards grouped by exam with a next-step button and a countdown, a
to-do list across courses); each course is a complete space with tabs Обзор · Уроки · Тесты · Аналитика · Сохранённые,
a tab shown only when the course has published content for it; no global Тесты/Аналитика/Сохранённые pages, no exam
switcher, no automatic landing in ORT; global menu Главная · Мои курсы · Каталог · Pro; the student's courses listed in
the sidebar; the last course and tab remembered; phone bar Главная · Курсы · Продолжить · Каталог · Ещё; catalog
grouped by exam and subject; a skippable "choose your courses" step after sign-up; exam family and subject on platform
courses with the smallest data change; a student sees only what the teacher published and Режим ученика shows exactly
that. **v3 corrections to this paragraph:** the global menu is Главная · Каталог (no «Мои курсы» item or page: the
hub shows the courses, the sidebar lists them); the catalog is the only way to add a course (no choose step); the phone
bar is Главная · Продолжить · Каталог · Ещё; the fifth tab is «Повторение».

## 0. v3 changes (owner 2026-11-13, items 2–4 of "Owner round 2026-11-13 (after 3a/3b, verbatim)")

Owner's words, condensed: (2) home already shows my courses and the sidebar lists them again → remove the «Мои курсы»
menu item and page (redirect to `/home`); sidebar Главная, Каталог, then my courses; one way to add a course = the
catalog (remove `/courses/choose` and «Подобрать курсы»; «Добавить курс» opens the catalog; a new student lands in the
catalog with a short welcome line); «Войти по коду» only in the catalog, one button; phone bar to the same structure
(architect decides); update the per-role link check and the "nothing lost" table. (3) Rename the course tab
«Сохранённые» → «Повторение» (ky «Кайталоо», en «Review»), inner tabs «Отмеченные» and «Ошибки», new empty state text.
(4) Every course uses the same graduation cap in the sidebar and on default covers → a subject icon from
`courses.subject` (math, language, chemistry, biology, physics, history, general) or a small cover thumbnail; review
other student icons for the same sameness.

**No migration.** Everything is frontend plus the removal of one dead backend endpoint (V9). Verified against the code
on 2026-11-13 (`StudentShell.tsx`, `studentNav.ts`, `StudentHub.tsx`, `MyCourses.tsx`, `courses/page.tsx`,
`CatalogView.tsx`, `ChooseCourses.tsx`, `chooseCourses.ts`, `lastPlace.ts`, `courseTabs.ts`, `CourseCardCover.tsx`,
`CourseFrame.tsx`, `CourseGroups.tsx`, `SavedPage.tsx`, `register/page.tsx`, `oauth-callback/page.tsx`,
`roleLinks.check.ts`, `e2e/role-links.spec.ts`, `backend/app/lms/courses/exam_families.py`, `catalog_router.py`).

### 0.1 Decisions V1–V16 (recommendations in effect; the orchestrator continues with them)

| # | Decision | Choice and why |
|---|---|---|
| V1 | Learner «Мои курсы» page and menu item | **Removed.** `/courses` for a person who learns redirects to `/home` (`router.replace`; the hash is mapped: `/courses#ort`, `#nct`, `#other` → `/home#courses`; every query is dropped, including the old `?view=learning`). Sidebar menu: **Главная · Каталог**; then the **«Мои курсы» list** (the group label `student.nav.myCourses` stays as the list's heading, not as a link). `MyCourses.tsx` is deleted; the hub shows the same cards |
| V2 | Teacher side and "both" | **Unchanged.** `/courses` stays the Teaching list for everyone who teaches (`teaches(me)`; owner 2026-11-12: people who teach never get Learning, with a leftover student enrolment or not), so there is no "both" case: `hidesLearning = teaches(me)` decides. The test student (Student view) is a learner → `/home`. `courses/page.tsx` keeps its role branch: `hasTeaching` → `TeachingList` as today, else the redirect; until `me` (fresh or cached) is known the page shows the neutral loading state, exactly as `/home` does for teachers today. `lms.nav.myCourses` (teacher breadcrumbs) stays |
| V3 | One way to add a course | **The catalog** `/courses/catalog`. `/courses/choose` → `/courses/catalog` (`?first=1` → `?welcome=1`, other queries dropped; the route's `page.tsx` stays as a redirect stub so old links work). Deleted: `ChooseCourses.tsx`, `choose.*` keys, `chooseCoursesHref`, `defaultChecked`, `idsToJoin`, `joinedOfRefusal`, `mainLanguageFor` (+ their checks); kept: `defaultFamily`, `subjectSections` (the catalog's chips and sections use them; the file may keep its name). «Подобрать курсы» (`catalog.groups.pick`, `CatalogView.tsx:229-232`) goes. «Добавить курс» on the hub (`StudentHub.tsx:226`) → `/courses/catalog` |
| V4 | New student after sign-up | `register/page.tsx:58` and `oauth-callback/page.tsx:66` (`created`) push **`/courses/catalog?welcome=1`** instead of the choose step; `?redirect=` (invites, teacher code, catalog landing), under-14 (→ `/privacy`) and parent (→ `/parent`) keep precedence (N7). **"New" = the query parameter, nothing stored**: `CatalogView` (it already reads `useSearchParams`) shows the welcome line (`catalog.welcome`, one sentence under the title in a soft brand-tinted strip, `role="status"`) while `?welcome=1` is in the URL, with a quiet «×» (`catalog.welcomeClose`) that `router.replace`s the URL without the parameter; every chip and card link drops it, so the line goes away on the first navigation. A reload keeps it, which is harmless. No DB column, no `localStorage`. The default chip for a student with 0 courses is ОРТ (N9), so the new student sees the ORT main courses first |
| V5 | «Войти по коду» | **One button**: the catalog header's secondary action (`CatalogView.tsx:208`, `home.primary.join`, on every width; hidden for the test student and for people who teach, as today). Removed: the «Ещё» sheet row (`StudentShell.tsx:386-391`), the hub empty state button (`StudentHub.tsx:161`), `MyCourses.tsx:67,85` and `ChooseCourses.tsx:189,208` (go with their files), the catalog's own empty-state duplicate (`CatalogView.tsx:255`: the header button is on the same page), the course not-found link (`courses/[courseId]/layout.tsx:78` → «В каталог», `/courses/catalog`). Kept, contextual and inside the catalog: the landing's «Ввести код» for a by-code course (`CourseLanding.tsx:160`). `/courses/join` stays (teacher-code sign-up links `?redirect=/courses/join?code=…` land there). Help text `landing.help.joinCode.a` names the catalog («Откройте «Каталог», нажмите «Войти по коду»…») instead of «Мои курсы» |
| V6 | Phone bottom bar | **Главная · Продолжить · Каталог · Ещё** (four items; «Курсы» went with its page, the relative order stays). «Ещё» sheet, top to bottom: the «Мои курсы» rows (6 + «Все курсы (N)»), «Начало работы», the Pro pill, «Установить приложение», other areas, the account panel; «Выйти» in the footer. No «Войти по коду» (V5). Test student: Главная · Продолжить · Ещё (no Каталог, as today). D8 (five items) is superseded by the owner's item 2 |
| V7 | «Все курсы (N)» and the group caps | The sidebar's 7th row «Все курсы (N)» → **`/home#courses`** (the hub's «Мои курсы» section gets `id="courses"`, `scroll-mt`). A hub group with more than 4 cards keeps the cap (N10), but «Все курсы ОРТ (N)» becomes an **in-place expand** (`<button aria-expanded>`, client state only, label unchanged, «Свернуть» collapses); when `courses_total` exceeds the courses known (the bootstrap holds up to 50) the first expand loads the rest once through `GET /me/home/courses` (`listHomeCourses`, kept). No `/courses#family` anchors any more. The hub stays the one list |
| V8 | Home with 0 courses | Greeting, then the empty state: mascot «hello», «У вас пока нет курсов», «Откройте каталог, выберите экзамен и запишитесь на курс.», **one** primary button «Открыть каталог» → `/courses/catalog`; no «Войти по коду» (the catalog has it); the to-do block hidden. Test student: title and body, no button. Sidebar with 0 courses: the «Мои курсы» group is **hidden** (Каталог is the item right above; no «Выбрать курсы» row). «Продолжить» in the bar with 0 courses → `/courses/catalog` (`continueTarget` kind `catalog`; test student: `/home`, as today) |
| V9 | Dead backend parts | `POST /catalog/choose` (router `catalog_router.py:201`, `enrollments/service.py:157-…` `choose_courses`, `ratelimit.CATALOG_CHOOSE_1M`, the `route_inventory.py:241` row, `tests/lms/test_catalog_choose.py`, frontend `catalog.ts chooseCourses`) is **removed in S10**, after S7 has deployed a frontend that no longer calls it (an old tab's bundle could otherwise hit a 404 mid-step). `GET /catalog/exams` **stays**: the catalog's family chips read it (`CatalogView.tsx:72`); `GET /catalog/courses?exam=` stays; `tests/lms/test_catalog_exams.py` stays. Nothing in the bootstrap is dead: `student.courses` feeds the sidebar, the hub and «Продолжить» |
| V10 | «Сохранённые» → «Повторение» | **Labels only.** The URL `/courses/{c}/saved`, the tab key `saved`, `PlaceKind` `saved`, `?tab=mistakes` and the inner tab ids `saved`/`mistakes` stay (a URL rename needs a redirect, `tabOfPath`, `lastPlace`, e2e and ORT baseline work for no user gain; the segment is a technical name, as `/analytics` is for Аналитика). Exact strings in §0.3 |
| V11 | Course icon | One helper `courseMark({exam_family, subject})` in `lib/lms/courseIcon.tsx` (lucide, as the whole app): a **subject icon** when `subject` is set, else by family (ORT main → `Award`, НЦТ main → `ClipboardCheck`, no family → `BookOpen`). The registry's ten subjects map onto the owner's seven classes in the frontend only (§0.4); **no migration, no registry change**: `kyrgyz`/`russian`/`english` are the owner's "language", `literature` and `geography` get their own marks, `null` subject is the owner's "general" (the exam's main course, or a teacher course). The brand mark (`GraduationCap`: student sidebar brand, phone top bar, `AppHeader`, `PublicFooter`) stays the brand's: **no course uses the cap any more** |
| V12 | Cover thumbnail | A course with `cover_url` shows a **24 × 24 px thumbnail** (`h-6 w-6 rounded-md object-cover`, `alt=""`, `loading="lazy"`, `draggable={false}`) in place of the icon in the sidebar rows and the «Ещё» rows; `onError` falls back to the icon. Same URL as the card's cover (1280 × 720 WebP on R2), so the browser cache serves it; no new size on the server (an R2 variant would mean more objects and a resize step, rule 6.5). The default cover (`CourseCardCover` without an image) keeps its tinted gradient and replaces the cap/book mark with `courseMark`, so hub cards, catalog cards, the Обзор header strip and the settings preview all show the subject |
| V13 | Other repeated student icons | Reviewed (§0.4): brand cap = ORT rows (fixed by V11); `FlaskConical` stood for НЦТ and is now chemistry's (НЦТ main → `ClipboardCheck`); the Аналитика tile «Сохранено» (`progress.analytics.tiles.saved`, `Bookmark`) → «Отмечено» with a `Flag` icon, matching Повторение; kept as states, not identities: hub cards' `CalendarClock` (countdown) and `Trophy` (last result), test cards' `ListChecks`/`Clock`/`Lock`, syllabus `PlayCircle`/`CheckCircle2`/`Circle`/`Lock`, practice `Dumbbell`; empty states keep their mascot poses (`hello`, `thinking`, `celebrating`, `reading`) |
| V14 | Per-role link check | `roleLinks.check.ts`: the rows `/ru/courses` and `/ru/courses/choose` stay for every role (the pages must redirect inside the right frame), new rows `/ru/courses/catalog?welcome=1` (student `student/learning`; staff `app/teaching`) and `/ru/home#courses`; `role-links.spec.ts`: `ENTRY.student` gains `/ru/courses/catalog?welcome=1`, the case "every role opens the choose step" becomes "… lands in the catalog (learner, with the welcome line) / on Teaching (people who teach)", and the walk adds two assertions for the student: no link to `/ru/courses` on any student page (the entry itself redirects) and «Войти по коду» found only on `/ru/courses/catalog`; `studentNav.check.ts`, `lastPlace.check.ts`, `shellKind.check.ts` updated (no `choose` kind, two menu links, four bar items) |
| V15 | Old links | `/courses` (learner) → `/home`; `/courses?view=learning` → `/home`; `/courses#ort|#nct|#other` → `/home#courses`; `/courses/choose[?first=1]` → `/courses/catalog[?welcome=1]`; §3.7 otherwise unchanged |
| V16 | Models | S7 Opus (navigation, redirects, bar, hub expand, link check), S8 Sonnet (Повторение strings and empty states), S9 Opus (icon helper, cover mark, sidebar thumbnail), S10 Sonnet (removals) — §0.5 |

### 0.2 Frame after v3 (replaces the sidebar table, the phone bar and the empty states of §2.1–§2.3)

- **Sidebar**: brand → `/home` · **Главная** `/home` · **Каталог** `/courses/catalog` · group **Мои курсы** (up to 6
  recent rows, each a thumbnail or `courseMark` + title + progress ring; then «Все курсы (N)» → `/home#courses`; the group
  is hidden with 0 courses) · bottom unchanged («Начало работы», Pro pill, install, other areas, account). The test
  student: Главная and the course row only.
- **Phone**: top bar title «Главная» on `/home`, «Каталог» on the catalog, the course title inside a course, else the app
  name; bottom bar **Главная · Продолжить · Каталог · Ещё**; «Ещё» as in V6.
- **Hub**: unchanged except «Добавить курс» → the catalog, the in-place group expand (V7), the empty state (V8) and the
  `id="courses"` anchor.
- **Catalog**: the chips and sections of §2.4, the one «Войти по коду» button in the header, the welcome line when
  `?welcome=1` (V4); no «Подобрать курсы».

### 0.3 Повторение: exact strings (S8; parity script)

| Key | ru | ky | en | Note |
|---|---|---|---|---|
| `course.tabs.saved` | Повторение | Кайталоо | Review | tab label |
| `student.saved.title` | Повторение | Кайталоо | Review | page `<h1>` of the tab |
| `home.hub.place.saved` | Повторение | Кайталоо | Review | continue card place |
| `student.saved.tabsLabel` | Разделы повторения | Кайталоонун бөлүмдөрү | Review sections | inner `Tabs` label |
| `student.saved.tabs.saved` | Отмеченные | Белгиленгендер | Flagged | inner tab (id `saved` stays) |
| `student.saved.tabs.mistakes` | Ошибки | Каталар | Mistakes | unchanged |
| `student.saved.empty` | Пока нет отмеченных вопросов | Белгиленген суроолор азырынча жок | No flagged questions yet | empty title |
| `student.saved.emptyHint` | Отмечайте вопросы флажком во время теста — они появятся здесь, и вы сможете повторить их после. | Тест учурунда суроолорду желекче менен белгилеңиз — алар ушул жерде чыгат, кийин кайталап аласыз. | Flag questions during a test and they will appear here for you to review afterwards. | empty body |
| `progress.mistakes.emptyOpen` | Открытых ошибок нет. Неверные ответы из тестов появятся здесь — их можно будет повторить. | Ачык каталар жок. Тесттердеги туура эмес жооптор ушул жерде чыгат — аларды кайталай аласыз. | No open mistakes. Wrong answers from tests will appear here for you to review. | Ошибки, filter «Открытые» |
| `progress.mistakes.emptyFixed` | unchanged | | | |
| `progress.analytics.tiles.saved` | Отмечено | Белгиленген | Flagged | Аналитика tile (V13); its hint stays unless it says «сохранённых» |

New keys of S7: `catalog.welcome` «Добро пожаловать! Выберите экзамен и запишитесь на курс.» / «Кош келиңиз! Сынакты
тандап, курска жазылыңыз.» / «Welcome! Pick your exam and join a course.»; `catalog.welcomeClose` «Скрыть» / «Жашыруу» /
«Hide»; `home.hub.openCatalog` «Открыть каталог» / «Каталогду ачуу» / «Open the catalog»; `home.hub.emptyBody` (new
text) «Откройте каталог, выберите экзамен и запишитесь на курс.» / «Каталогду ачып, сынакты тандап, курска жазылыңыз.»
/ «Open the catalog, pick your exam and join a course.»; `home.hub.collapseGroup` «Свернуть» / «Жыйноо» / «Show fewer»;
`courses.notFound.catalog` «В каталог» / «Каталогго» / «To the catalog»; `landing.help.joinCode.a` reworded to the
catalog. Removed in S10: `choose.*`, `courses.mine.*`, `home.hub.{choose,join}`, `catalog.groups.pick`,
`student.nav.{chooseCourses,courses,joinByCode}`, plus the S5 leftovers still present in the dictionaries
(`student.nav.{saved,tests,lessons,practice,analytics,mistakes,allLessons,lessonsGroup,practiceGroup}`) when `grep`
finds no use.

### 0.4 Icons (S9; lucide-react, already the app's icon set)

| `subject` (registry) | Owner's class | Icon | Note |
|---|---|---|---|
| `math` | math | `Sigma` | |
| `physics` | physics | `Atom` | |
| `chemistry` | chemistry | `FlaskConical` | was the НЦТ family icon in the sidebar |
| `biology` | biology | `Dna` | |
| `history` | history | `Landmark` | |
| `geography` | (not in the owner's list) | `Globe` | |
| `kyrgyz`, `russian`, `english` | language | `Languages` | |
| `literature` | language | `BookText` | a book, not a tongue |
| `null`, `exam_family = ort` | general (main course) | `Award` | the golden certificate; never the brand cap |
| `null`, `exam_family = nct` | general (main course) | `ClipboardCheck` | |
| `null`, no family | general (teacher course) | `BookOpen` | as today's default cover mark |

Where the mark appears: sidebar rows and «Ещё» rows (20 px icon, or the 24 px thumbnail when `cover_url`); the default
cover of `CourseCardCover` (hub cards, catalog cards, the Teaching list's cards, the Обзор header strip, the settings
preview: the one quiet 48 px mark bottom right, tint unchanged); nowhere on the compact header or the tabs. Data: every
card DTO already carries `exam_family` and `subject` (`HomeCourseOut`, `CatalogCardOut`, `CourseOut`, S1); the
teacher's `CourseCard` DTO is checked in S9 and falls back to `BookOpen` when a field is missing. `courseIcon.check.ts`
asserts the table and the fallbacks. The brand mark `GraduationCap` stays in `StudentShell.tsx:298,330`, `AppHeader.tsx:67`,
`PublicFooter.tsx:33`; `CourseSidebar.tsx:24` (staff «Оценки» icon) and the admin stat tiles are staff screens, out of scope.

### 0.5 Slices S7–S10 (each deploys alone; order S7 → S8 → S9 → S10; S8 and S9 are independent of each other)

Every slice: `tsc`, parity script, SQLite suite, the e2e specs named, screens at 375 / 1440 / 1920 in ru checked by the
orchestrator (§6.9 UX check), `role-links.spec.ts` + `roleLinks.check.ts` green, ORT parity/exam-rule tests unchanged,
ORT pixel baselines zero diff (no slice touches the player, lobby, result or review).

| # | Slice (model) | Content | Tests | Deployable alone because |
|---|---|---|---|---|
| S7 | Navigation without redundancy (Opus) | `/courses` learner redirect with the hash map (V1), `MyCourses.tsx` deleted, `/courses/choose` redirect stub and `ChooseCourses.tsx` deleted (V3), sign-up and Google new-account → `/courses/catalog?welcome=1` + the welcome line and its «×» (V4), `studentNav.ts` (two menu links, no `choose`, `all` → `/home#courses`), `StudentShell` (menu, four-item bar, «Ещё» without the code row, titles), `lastPlace.continueTarget` 0 courses → catalog (V8), hub «Добавить курс» → catalog, empty hub with one button, `id="courses"`, group expand + `listHomeCourses` when incomplete (V7), catalog without «Подобрать курсы» and without the empty-state code button (V5), not-found page → catalog, help text, `roleLinks.check.ts` + `role-links.spec.ts` (V14), new keys of §0.3 | `student-home.spec.ts` (0 courses → one button to the catalog; «Добавить курс» → catalog; expand/collapse; `/courses#ort` → `/home#courses`), `student-shell.spec.ts` (two menu items, four bar items, «Ещё» rows without «Войти по коду», group hidden with 0 courses), `choose-courses.spec.ts` rewritten as `catalog-welcome.spec.ts` (sign-up → catalog with the line; «×» removes it; a chip removes it; `?redirect=` precedence; under-14 → privacy; Google `created` → catalog; teacher → Teaching), `student-links.spec.ts`, `mobile-sheets.spec.ts`, `header-areas.spec.ts`, `role-links.spec.ts`, `pwa.spec.ts`, `perf-waterfall.spec.ts` (home still one round); checks `studentNav.check.ts`, `lastPlace.check.ts`, `roleLinks.check.ts`, `shellKind.check.ts` | every old URL redirects; the backend is untouched |
| S8 | Повторение (Sonnet) | the strings of §0.3 in en/ky/ru, `SavedPage` and `MistakesList` empty states (texts only), the Аналитика tile label + `Flag` icon, `TEACHER_TO_STUDENT_MAP.md` §0 wording | parity script, `student-saved.spec.ts`, `student-analytics.spec.ts`, `course-nav.spec.ts` (tab label assertions), screens 375/1440 | text only |
| S9 | Icons (Opus) | `lib/lms/courseIcon.tsx` (`courseMark`) + `courseIcon.check.ts`, `CourseCardCover` takes `exam_family`/`subject` (callers pass them; `platform` prop goes), sidebar and «Ещё» rows: thumbnail or `courseMark` (V12), `FAMILY_ICON` removed from `StudentShell.tsx` | `student-shell.spec.ts` (a row shows the thumbnail when the seed course has a cover; subject icon `data-icon` attribute per seeded subject), `course-cards.spec.ts`, `catalog-apply.spec.ts`; ORT baselines: lobby/result/review compact headers have no cover → zero diff; the Обзор full header has no baseline | visual only; `courseMark` falls back to today's `BookOpen` |
| S10 | Cleanup (Sonnet; `grep -rl` before each deletion) | backend `POST /catalog/choose` + `choose_courses` + `CATALOG_CHOOSE_1M` + the inventory row + `test_catalog_choose.py`; frontend `catalog.ts chooseCourses`, the dead functions of `chooseCourses.ts` and their checks, the removed keys of §0.3; docs (`HANDOFF_NEXT_AGENT.md`, `PRODUCT_DECISIONS.md` as-built note, `FIX_ROUND_2026-11-12.md` results rows) | SQLite suite (route inventory test), `tsc`, parity, `nav.check.ts`, all e2e | removals only |

**Rollback**: every slice is a revert (no data changed, every old URL still exists); S10 re-adds code.

## 1. Problems today, and what stays

| # | Problem | Where (file:line) | Screen |
|---|---|---|---|
| P1 | **Two navigations at once.** Inside a teacher's course the global student sidebar (Главная, Тесты, Аналитика, Уроки, Сохранённые of the *ORT* course) and the old course sidebar (Курс, Задания, Оценки, Преподаватели, Файлы, Мой прогресс, Сохранённые) are both drawn | `app/[lang]/courses/[courseId]/layout.tsx:163-170` (`CourseSidebar` for general courses) + `components/lms/student/StudentShell.tsx:398-401` (global `SidebarNav`) | 05, 06, 07 |
| P2 | **The ORT switcher stays visible in unrelated courses**, and "Тесты"/"Аналитика" in the global sidebar point at the remembered ORT course while the student reads a teacher course | `StudentShell.tsx:235-296` (`ExamSwitcher`), `student/useStudentShellData.ts:143-151` (`current` = remembered exam when the path's course is not an exam) | 05 |
| P3 | **Global items are per-course.** Тесты, Уроки, Практика, Сохранённые, Аналитика carry the *current exam's* id (`lib/lms/studentNav.ts:48-64`); switching the exam silently swaps the page under the same link | `studentNav.ts`, `StudentShell.tsx:242-255` | 01, 03 |
| P4 | **Two course page shapes**: the exam-shell branch (own titles, no course header, no sidebar: `layout.tsx:130-146`) and the general branch (`StudentCourseHeader` + `CourseSidebar`: `layout.tsx:148-175`); four student course homes (`[courseId]/page.tsx:51-66`: `ToTests` redirect, `StudentSyllabus`, `PageView`+modules, `StudentCourseHome`) | | 03, 05, 08 |
| P5 | **The ORT course has no overview**: `/courses/{c}` redirects to `/tests` (`page.tsx:54, 121-127`); the countdown, target score and section bars live only on the global home for the "current" exam (`home/ExamPrepHome.tsx`), so a student with two ORT courses sees one exam's numbers on a page called "Главная" | | 01 |
| P6 | **Phone: per-exam tab bar + a course drawer.** The bottom bar is Главная · Тесты · Практика · Аналитика · Ещё of the current exam (`StudentShell.tsx:488-490`); inside a teacher course a second menu «Меню курса» opens a drawer (`components/lms/course/CourseSidebar.tsx:41-43`) | | 06, 07 |
| P7 | **`?view=` machinery** for the home: `ViewSync`, the `#catalog` hash redirect, `coursesDefault` (`courses/page.tsx:28-50`, `lib/lms/shellKind.ts:34-36, 68-71`) | | |
| P8 | **A third navigation for lesson courses**: the УРОКИ sidebar group lists lesson courses of the current exam with progress rings and «Все уроки» (`StudentShell.tsx:113-136`, `courses/[courseId]/lessons/page.tsx`) | | |
| P9 | **Exam-shell special cases in the layout**: `isExamShellCourse`, the `ownTitle` route list, `examPage` reading column (`layout.tsx:130-146`); every new student page must be added to a list | | |

**What stays (unchanged, reused):** the palette "Sky and teal" and `.student-theme` tokens (`STUDENT_UI_DESIGN.md`
§1.1); `StudentShell` primitives (`SidebarNav`, `TabBar`, `Sheet`, `GoldPill`, `StudentPageHeader`, `Mascot`,
`Countdown`, `Meter`, `SectionTag`); the frame decision and performance work (`shellKind.ts` rules, per-page latch and
neutral frame in `LmsShell.tsx`, `meCache`, `swr.ts`, `GET /me/bootstrap?include=home`, hover prefetch in `pageData.ts`,
split dictionaries); Student view (test-student session, `StudentViewBanner`; the test student is a real user); Pro
rules (`SUBSCRIPTION_DESIGN.md` §12: module-level Pro, paid tests, `ProCallout`, `ProChip`, `ProLockCard`, never for
staff/test students); the full-screen player (`PLAYER_FRAME`, `isPlayerRoute`) and the fixed ORT rules (section order,
timers, forward-only, scoring, CSV/zip import); the result page (`ExamResultHero`, `SectionBreakdown`, review);
`TestsPage`/`TestLibrary`, `NextCard`, `GoalStrip`, `StreakCard`, `StudentSyllabus`, `LessonView`, `AnalyticsOverview`,
`SavedPage`, `StudentGrades`, `CourseCard`, `CatalogView`, `CourseLanding`, `TodoList`, `gettingStarted.tsx`. The teacher,
organization and platform frames (`AppHeader`, `CourseSidebar` for staff, `TeacherCoursePage`, settings) are untouched
except the settings fields of §6.1.

## 2. Structure

Principle: **the global frame is about the person; a course space is about one course.** No global link carries a
course id. Every course, ORT included, opens on the same course pattern (§3). The exam switcher and the "current exam"
disappear.

### 2.1 Global frame (people who learn; test students in Student view)

Desktop (≥ 1024 px): the 264 px teal sidebar. Phone: a 56 px top bar (brand, page title, avatar) and the 64 px bottom
bar. The frame is the same on every page, inside courses too; only the player has no frame.

**Sidebar, top to bottom**

| Block | Content | Rule |
|---|---|---|
| Brand | app name → `/home` | |
| Menu | **Главная** `/home` · **Каталог** `/courses/catalog` (v3: the «Мои курсы» item is gone, V1) | the two global items; `aria-current` from the path |
| **Мои курсы** list | up to **6** course rows, **recent first** (§2.5), each: v3: the cover thumbnail or the subject/family mark `courseMark` (§0.4, V11–V12), title, right side the progress ring (`done/total`) when the course has one; the row of the course being viewed is `aria-current`; a row opens the course's **last opened tab** (§2.5), else Обзор | with more than 6 courses the 7th row is «Все курсы (N)» → v3: `/home#courses` (V7); with 0 courses the group is hidden (v3, V8; was a «Выбрать курсы» row) |
| Bottom | «Начало работы» pill (getting-started, per student), **Pro** gold pill (`AccessPill`: «Открыть все экзамены» / «Pro до …»), «Установить приложение», other areas (parent), account button (sheet: name, language, Конфиденциальность, Выйти) | unchanged components; the test student has no Pro, install, Каталог or «Выбрать курсы» |

Pinned vs recent (owner: "pinned or recent first"): **recent first, no pin control in v1** (decision N3, §8): recent
order already puts the courses a student works in at the top; a pin needs one more control and a server field.

**Phone bottom bar** (v3, V6): **Главная** `/home` · **Продолжить** (→ the last place, §2.5) · **Каталог**
`/courses/catalog` · **Ещё** (sheet); the v2 «Курсы» item went with its page. «Продолжить» is a link whose target is
computed on the client: the remembered last place, else the server fallback of §2.5, else `/courses/catalog` (0 courses;
v3). «Ещё» sheet, top to bottom: the «Мои курсы» rows (same 6 + «Все курсы»), «Начало работы», Pro pill, «Установить
приложение», other areas, the account panel (name, language, Конфиденциальность), «Выйти» in the footer; v3: no «Войти
по коду» row (V5). The test student's «Ещё» has only the course rows, «Начало работы» and the account panel.

**Frame rules (`shellKind.ts`)**: `areaFromUrl`: `/home`, `/courses/choose` are Learning; `/courses` is `homeArea(me)` for
people who teach and Learning for learners (`coursesDefault` goes; `urlAreaFor` already sends a URL no staff area claims
to the person's home area, so `/home` for a teacher opens the Teaching list through the existing redirect rule, never a
student frame). `isPlayerRoute` unchanged. The fixed table in `lib/lms/roleLinks.check.ts` gains `/home`,
`/courses/choose`, `/courses/c1/lessons`, `/courses/c1/analytics`, `/courses/c1/saved` for `student` (learning) and for
`teacher`/`org_admin`/`platform_admin` (app/teaching); `e2e/role-links.spec.ts` `ENTRY.student` gains `/ru/home` and
`/ru/courses/choose`. v3: `/courses` (learner) and `/courses/choose` are redirect-only pages, kept in both tables; new
rows `/ru/courses/catalog?welcome=1` and `/ru/home#courses` (V14).

### 2.2 Главная `/home` (hub only)

Order (desktop two columns 1fr + 320 px; phone one column):

1. **Greeting** line (`useGreeting`, mascot) — no numbers.
2. **Продолжить** card (one): course title, the place («Урок 3 · Проценты», «Пробный тест 2 · раздел 2 из 5», «Задание
   · до 23 февр.»), one primary button whose label matches the place (Продолжить тест / Продолжить урок / Открыть).
   Source: the remembered last place (§2.5) when it still resolves to a course the student is in; else the server
   fallback: the in-progress attempt (`HomeOut.in_progress[0]`), else the first `modules_next` row, else the newest
   exam course's Overview. Below the button one quiet line **«Серия N дней»** when the cross-course streak is ≥ 2
   (§2.5 data; OPEN Q2).
3. **Мои курсы**, grouped: **ОРТ**, **НЦТ**, **Другие курсы** (group order fixed; empty groups hidden; a lesson course
   attached to an exam sits in its exam's group). Each card (`CourseCard`, extended): cover, title, provider line,
   progress bar + «3 из 5», exam courses a **small countdown** («до экзамена 30 дн.»; «Сегодня»; nothing without a
   date) and the last result line («Последний балл 132 / 245»), and one **next-step button** (`next_step`, §6.2: Продолжить
   тест / Продолжить урок / Начать тест / Открыть курс). A group shows up to 4 cards, then «Все курсы ОРТ (N)», v3: an
   in-place expand (V7; was a link to `/courses#ort`). The groups header has a quiet «Добавить курс» → v3:
   `/courses/catalog` (V3; was the choose step). The section carries `id="courses"` (the sidebar's «Все курсы (N)» target).
4. **К выполнению** (side column; phone: after the courses): today's `TodoList` from `HomeOut.todo` across courses
   (in-progress attempts first, then due dates, overdue flagged), each row named with its course; plus announcement
   rows (OPEN Q1). Empty: «Пока ничего». «Все задания» is not needed: the list is complete (TODO_MAX rows, newest first).
5. Notices that exist today and stay on the home: pending invitations banner, pending catalog applications line,
   teacher-application notice, privacy banner (unchanged components).

With **0 courses** (v3, V8): the greeting, then the empty state (mascot «hello», «У вас пока нет курсов», «Откройте
каталог, выберите экзамен и запишитесь на курс.», one button «Открыть каталог» → `/courses/catalog`; v2 had «Выбрать
курсы» and «Войти по коду»), and the to-do block hidden. With **1 course**: the continue card
and one card in one group; the page is short and reads as "here is your course". With **10 courses**: three groups of up
to 4 cards (+ «Все курсы …»), the to-do list aside. No test list, no results list, no statistics on this page.

Data: `GET /me/bootstrap?include=home` (one round, as today) with the `HomeCourseOut` additions of §6.2; the 7-day
activity in the bootstrap becomes cross-course (§6.2).

### 2.3 Мои курсы `/courses` (v3: removed for learners, V1–V2)

v2 built a grouped «Мои курсы» page here (S3); the owner found it a copy of the hub and the sidebar. **v3**: for a person
who learns `/courses` redirects to `/home` (`#ort`/`#nct`/`#other` → `/home#courses`, queries dropped); `MyCourses.tsx`
is deleted; `GET /me/home/courses` stays for the hub's group expand (V7). `/courses` stays the **Teaching list** for
people who teach (unchanged `TeachingList`); the `?view=` machinery, `ViewSync` and the `#catalog` redirect went in S3/S5
(P7), and `?view=learning` now simply joins the general learner redirect.

### 2.4 Каталог `/courses/catalog` (grouping; 3b adds the listing rule)

Chips under the title: **ОРТ · НЦТ · Курсы преподавателей** (only families with at least one listed course; the default
chip is the family of the student's newest exam course, else ОРТ). A family view shows its platform courses grouped by
**subject** (section headers «Основной курс», «Математика», «Физика», …; the main course first; both languages side by
side with a language tag). «Курсы преподавателей» is today's paginated list (teacher courses have no family). v3: no
«Подобрать курсы» link (the choose step is gone, V3); the header keeps the **one** «Войти по коду» button of the whole
student area (V5); with `?welcome=1` (a new account, V4) a one-sentence welcome line with a quiet «×» sits under the
title. Query: `GET /catalog/courses?exam=ort` (§6.3), the scope of 3b (`listing = 'listed'`) applies on top. Landing
`/courses/catalog/{id}` unchanged; «Записаться» lands on the course Overview (never on a list).

### 2.5 Fast access: recent courses, last place, «Продолжить»

Stored **on the device, per user** (no server field; decision N2, §8): `localStorage["ort_last_place:{userId}"]` =
`{courseId, path, kind, at}` written by the course layout on every student navigation inside a course (`kind`: tab or
object: `overview|lessons|tests|analytics|saved|lesson|lobby|assignment`); the player and the result page write the
**lobby** path (an attempt is resumed through the server's `in_progress`, never through a stored attempt URL).
`localStorage["ort_recent_courses:{userId}"]` = up to 10 course ids, most recent first, updated by the same hook. Both
reads are wrapped in try/catch (private mode → server fallback). The per-user key keeps a teacher's Student view
session (another user id on the same device) separate. Why not a server field: the home's continue card already has a
server fallback that is right on a new device (in-progress attempt → next lesson → newest exam course), a server
"last opened" would cost one write per course open at 6,000 concurrent students, and a migration. The old key
`ort_student_course` is deleted in S5.

The sidebar list order: the ids of `ort_recent_courses` first (those still in the course list), then the rest in the
home's order (newest enrolment first). A course row opens `/courses/{c}` + the remembered tab for that course when
`ort_last_place` names it, else Обзор.

## 3. One course space (students of every course; Student view)

### 3.1 Header
```
┌ cover strip (160 px desktop / 120 px phone; CourseCover default when none) ─────────────────────────┐
│ ОРТ (на русском)                                   [exam courses: 30 дн · 07 ч · 59 мин до экзамена] │
│ Платформа · Русский · 12 тестов · 4 урока          [Последний балл 132 · Цель 200 ✎]                 │
│ Пройдено 3 из 5 ▮▮▮▯▯ 60 %                                                                            │
├ Обзор · Уроки · Тесты · Аналитика · Сохранённые ───────────────────────────────────────── (tabs) ───┤
│ ★ Pro bar (only on a tab that holds locked content)                                                   │
```
- `<h1>` = course title on every tab; meta line: provider (`courses.home.providerPlatform` or the owner's display
  name), language, counts (`tests_count`, `lessons_count`). Lesson courses add «К экзамену: ОРТ (на русском)» (link).
- Progress bar: `ModulesStudentOut.progress` when the course has modules, else tests done / published tests (exam
  courses: `library_total` and the done count), else nothing. One helper `courseProgress(course)` feeds the card, the
  header and the sidebar ring, so they never disagree.
- **Exam courses only** (`is_exam_prep`, i.e. the template's `student_layout === "exam_prep"`): the countdown tiles
  (`Countdown`, exam date from `courses.settings.exam_date`; «Сегодня» on the day; nothing without a date) and the goal
  strip (`GoalStrip`: last scaled score, target, edit). The only template-specific part of the pattern.
- The header is **full** on Обзор and **compact** (title line + tabs, no cover, no bars) on the other tabs and on object
  pages, so lists start high on a phone. The compact title links to Обзор.
- «Покинуть курс» is a quiet link at the end of Обзор (as today), never in the header.

### 3.2 Tabs (`<nav aria-label="Разделы курса">` of links, `aria-current="page"`; horizontal scroll on phones)

| Key | ru / ky / en | URL | Shown when (`CourseOut.features`, server EXISTS) | Content |
|---|---|---|---|---|
| overview | Обзор / Жалпы маалымат / Overview | `/courses/{c}` | always | §3.3 |
| lessons | Уроки / Сабактар / Lessons | `/courses/{c}/lessons` | `features.modules` (exam course: a lesson exists; general: a published module) **or** attached lesson courses exist (`lesson_courses` non-empty) | today's `StudentSyllabus` (its banner removed: the header has it; «Продолжить» stays as the first row's CTA), then the section «Курсы с уроками к экзамену» (`LessonCourses` cards) for exam courses (D5) |
| tests | Тесты / Тесттер / Tests, **or** Задания / Тапшырмалар / Assignments when `features.hand_ins` (a published non-quiz assignment; glossary `UX_GUIDELINES.md` §5) (D4) | `/courses/{c}/tests` | `features.tests` (a published, live assessment or assignment visible to students) | exam courses: today's `TestsPage` (`TestLibrary`, status chips, source chips); other courses: the assignments list in the same card grid (`StudentAssignmentCard` → `TestLibrary` card shape, percent instead of a scaled score; hand-ins keep their kind badge). Section **«Тренировки»** (`#practice`) at the end when `features.practice` (D6): today's practice list |
| analytics | Аналитика / Аналитика / Analytics | `/courses/{c}/analytics` | `features.tests` or `features.hand_ins` | block **«Оценки»** (`#grades`, today's `StudentGrades`: released grades, feedback, course total) when `features.hand_ins` or the course is not an exam course and has graded work; then today's `AnalyticsOverview` (sections, weak topics, activity, heatmap, streak; `examPrep` for exam courses; score history) when `features.tests`. The mistakes link goes to the Сохранённые tab `?tab=mistakes` (D3: no Оценки tab) |
| saved | v3: **Повторение / Кайталоо / Review** (owner item 3; was Сохранённые) | `/courses/{c}/saved` (URL and key unchanged, V10) | `features.tests` | today's `SavedPage` (inner tabs v3 **Отмеченные · Ошибки**; `?tab=mistakes`; strings §0.3), this course only |

Empty-tab rules: a tab is hidden until its flag is true; a hidden tab opened by URL shows `AreaUnavailable` («Пока
недоступно … Назад к курсу») inside the frame, as today for announcements/files. A shown tab whose list is empty shows
the existing empty states. Обзор is never hidden. Examples: only tests → Обзор · Тесты · Аналитика · Сохранённые; only
lessons → Обзор · Уроки (lesson progress is in the header and the Уроки tab; nothing to analyse); both → all five; a new
teacher course with nothing published → Обзор only. Tabs are URLs, never client state (deep links, prefetch and the
per-role link check keep working).

`/courses/{c}/analytics` is today the staff quiz-statistics page (`analytics/page.tsx`); the page branches by role (staff
→ statistics as today; students → the Аналитика tab), the same pattern as `[courseId]/page.tsx`.

### 3.3 Обзор `/courses/{c}`
Order (desktop two columns 1fr + 320 px; phone one column):
1. **Следующий шаг** card: exam courses: today's `NextCard` (start / resume / retake / practice / unlock; the page's one
   primary button); other courses: the next item from `modules_next` / the first open assignment (today's
   `StudentCourseHome` "next" logic). Hidden when nothing is open.
2. **Последний результат**: exam courses: scaled score + the five section bars of the latest released result
   (`SectionBars`), «Все результаты» → Аналитика; other courses: the latest released grade with its feedback line,
   «Все оценки» → Аналитика `#grades`. Hidden without a result.
3. **Объявления** strip: the latest published announcement (title, date, two lines) + «Все объявления» →
   `/announcements`; only when `features.announcements`.
4. **Уроки** teaser: «Продолжить урок» row (`modules_next` of this course) + «Все уроки» → Уроки tab; only with lessons.
5. Side column **О курсе**: description, provider, **teachers** (`GET /courses/{c}/people`, display names only; D10),
   language, counts (modules, lessons, tests), «Материалы» → `/files` when `features.files`, mascot. Exam courses add
   «Курсы с уроками к экзамену» (up to 3 cards + «Все» → Уроки tab). Lesson courses add «К экзамену: …».
6. Gold **unlock card** (`UnlockCard`) when `needs_pass` (exam courses) or a locked Pro module exists (others);
   «Покинуть курс».

Exam course Обзор = countdown + target + last result (owner point 2) in the header and blocks 1–2. ORT ru/ky open here;
`ToTests` goes.

### 3.4 Object mapping

| Object today | Where it lives |
|---|---|
| Modules and items (page / file / url / header) | Уроки tab (`StudentSyllabus`), lesson page (§3.5) |
| Quiz assignments, `ort_main` exams | Тесты tab cards → lobby; also rows inside modules on Уроки (L7, never twice in the syllabus) |
| Text / file / offline assignments | Тесты tab (label Задания) → assignment page `/assignments/{id}` (object page) |
| Practice sets | Тесты tab, section «Тренировки» (`#practice`) |
| Announcements | Обзор strip → `/announcements` list (object page) |
| Course files outside modules | Обзор «Материалы» → `/files` (object page; now reachable in exam courses too) |
| Teachers | Обзор «О курсе» (D10; observers keep `/people`) |
| Grades and feedback | Аналитика tab, «Оценки» block (D3) |
| Saved questions, mistakes | Сохранённые tab (per course, never mixed) |
| Exam date, target score, latest scaled score | header of exam courses (D9) |
| Lesson courses attached to an exam | Уроки tab of the exam (D5) + the exam's group on `/home` and `/courses`; each is a normal course in the same pattern |

### 3.5 Object pages inside the space
Lesson page `/courses/{c}/modules/{m}/items/{i}`, page `/pages/{id}`, assignment `/assignments/{id}`, lobby
`/assessments/{a}`, result and review `/attempts/{id}/result`, announcements list, files list: **compact header** (title
link + tabs with the parent tab active: Уроки for lessons and pages, Тесты for lobby/result/assignment, Обзор for
announcements/files), then the object (D7). The lesson page keeps its outline aside (desktop) / collapsible (phone) and
sticky pager (`COURSE_LESSONS_DESIGN.md` §7.2). Lobby, result and review keep the 880 px reading column inside the
frame. The **player** `/attempts/{id}` keeps `PLAYER_FRAME`: no chrome at all; `?return=` leads back to the lobby. Deep
links (`#item-{n}` on the review, `#m-{id}` on the syllabus, `#practice`, `#grades`) keep working.

Pro lock bar: `ProCallout variant="course"` directly under the tabs on Уроки (a locked module exists) and Тесты (a paid
test exists and no pass), on the lobby of a paid test, and on a locked lesson page (`ProLockCard` replaces the content).
Never on Обзор twice: the unlock card is the Обзор's version.

### 3.6 ORT as a normal course (fixed rules untouched)
ORT (ru / ky) opens on Обзор: countdown + goal in the header, Следующий шаг, latest result with section bars, lesson
courses. Tabs: Обзор · Уроки (when a lesson or a lesson course exists) · Тесты · Аналитика · Сохранённые. `ExamPrepHome`
splits into the hub (`/home`) and the ORT Обзор; `TestsPage` → the Тесты tab unchanged; `/progress` → the Аналитика tab;
`/saved` → the Сохранённые tab (same URL). Nothing in `attempts/`, `grading/`, `ort/`, `content/importers/` changes; the
player, section order, timers, forward-only sections and scoring are untouched. ORT student screenshot baselines
(`lobby`, `result`, `review` × phone/desktop × ru/ky) are re-approved deliberately for the compact header (before/after
pairs in `STUDENT_IA_screens/ort/`, note in `ORT_BASELINE/README.md`); the five player screens, `review-page`,
`section-end`, `submit`, `passage`, `comparison`, `flagged-palette`, `player-loading` and every `teacher-*` image must
still match pixel-for-pixel. Backend `test_ort_parity.py`, `test_ort_e2e_api.py`, `test_ort_import_golden.py`,
`test_grading_scoring.py` unchanged.

### 3.7 Redirects (frontend, in the old route's `page.tsx`, query kept)

| Old | New |
|---|---|
| `/courses` (v3, V1) | `/home` for learners (`#ort`/`#nct`/`#other` → `/home#courses`, queries dropped); the Teaching list for people who teach, as today |
| `/courses?view=learning` | `/home` (learners); `/courses` (people who teach, as today) |
| `/courses?view=teaching`, `/courses#catalog` | `/courses`, `/courses/catalog` |
| `/courses/choose`, `/courses/choose?first=1` (v3, V3) | `/courses/catalog`, `/courses/catalog?welcome=1` |
| `/courses/{c}` (exam course, was `ToTests` → `/tests`) | stays: it is Обзор now |
| `/courses/{c}/tests` | kept (the Тесты tab of every course) |
| `/courses/{c}/assignments` (students) | `/courses/{c}/tests` (staff keep `/assignments`) |
| `/courses/{c}/modules` (students) | `/courses/{c}/lessons` (staff keep their redirect to the course page); `#m-{id}` kept |
| `/courses/{c}/lessons` («Все уроки» page) | same URL: the Уроки tab, lesson courses at its end |
| `/courses/{c}/progress`, `?tab=mistakes` | `/courses/{c}/analytics`; `?tab=mistakes` → `/courses/{c}/saved?tab=mistakes` |
| `/courses/{c}/grades` (students) | `/courses/{c}/analytics#grades` (staff keep `/grades`) |
| `/courses/{c}/saved` | kept (the Сохранённые tab) |
| `/courses/{c}/practice` | `/courses/{c}/tests#practice` |
| `/courses/{c}/people` (students) | `/courses/{c}` (observers keep the page) |
| `/courses/{c}/announcements`, `/files` | kept (object pages) |
| `/courses/{c}/modules/{m}/items/{i}`, `/pages/{id}`, `/assessments/{a}`, `/attempts/{id}`, `/attempts/{id}/result`, `/assignments/{id}` | kept |
| `/pro`, `/unlock`, `/privacy`, `/courses/join`, `/invitations` | kept |
| the v1 design's `/saved`, `/analytics` (global) | never built; nothing to redirect |

**What disappears, with reasons.** The exam switcher and the "current course" (`ort_student_course`,
`useStudentShellData.current/setCurrent/lessonCourseExam/features`): with per-course spaces a global "current exam"
has no meaning. Per-course global links (`studentNavLinks` tests/lessons/practice/analytics/saved): they are course
tabs. The УРОКИ group and «Все уроки»: lesson courses are rows at the end of the exam's Уроки tab and cards in the
exam's group. `CourseSidebar` for students (staff keep it). `StudentCourseHeader` with breadcrumbs: the course header
replaces it. The four student course homes: one Обзор. `ToTests`. `isExamShellCourse` and the `ownTitle` list. The
`?tab=` reading in `LmsShell` (only the switcher used it). The home's «От платформы» join cards: «Добавить курс» → the
choose step. The global Тесты/Аналитика/Сохранённые pages of the v1 design: not built (owner point 3).

## 4. Choose your courses `/courses/choose` (v3: removed, V3–V4; kept below as the record of what S4 built)

**v3**: the owner wants one way to add a course, the catalog. After sign-up (and a new Google account) the student lands
on `/courses/catalog?welcome=1` with the welcome line; `?redirect=`, under-14 and parent keep their precedence exactly as
described below; `/courses/choose` redirects to the catalog; nothing is auto-enrolled (3c D2 still holds: no enrolment
without a tap, now the catalog's «Записаться»). The rest of this section is v2 history.

Where it sat: `register/page.tsx` pushed `/courses/choose?first=1` instead of `/courses` on success, **after** the
existing branches keep their precedence: `?redirect=` (invite links, teacher-code sign-up `/courses/join?code=…`, a
catalog landing) wins; under-14 → `/privacy` (nothing works until a parent consents; afterwards the student reaches the
step from the home's «Выбрать курсы»); parent accounts → `/parent`. Google sign-in (`oauth-callback`) follows the same
rule for a **new** account. People who teach never see it (`urlAreaFor` → Teaching, redirect to `/courses`); test
students neither.

Screen (two steps on one page, no wizard state in the URL):
1. **Экзамен**: one card per family with at least one listed platform course (ОРТ, НЦТ), each with its one-line
   description and course count; a quiet line «У меня есть код от преподавателя» → `/courses/join`. With one family only,
   step 1 is pre-selected and the page opens on step 2.
2. **Курсы**: the family's courses as checkboxes grouped by subject: the **main course of the UI language pre-checked**
   (ОРТ (на русском) for ru, ОРТ (кыргызча) for ky; en → ru), the other language's main course unchecked, subject courses
   unchecked, each with the one-line description, lessons/tests counts and a quiet Pro mark (`has_paid_tests`). Courses
   the student is already in are checked and disabled («Вы уже записаны»).
3. Buttons: **«Записаться (N)»** → `POST /catalog/choose {course_ids}` (§6.3) → `/home` (the continue card shows the
   first chosen course's next step); **«Пропустить»** (`?first=1` only) → `/home`; otherwise «Назад».

Re-open later: `/home` groups header «Добавить курс», the `/home` empty state «Выбрать курсы», `/courses` header
«Добавить курс», the catalog's «Подобрать курсы». No nagging: nothing is stored about a skip; the empty home is the
reminder. This step **replaces** the auto-enrolment of the 3c design (owner 3c D2): no account is enrolled without a
tap.

Data: `GET /catalog/exams` (§6.3): families → subjects → courses (platform, listed, published), with `enrolled`.

## 5. Teacher control and roles

- **A student sees only what the teacher published.** Every tab, card and list reads the existing server rules
  (`course_features` EXISTS over published, live content; `_visible_test`; module/item `published`; announcement
  `published_at <= now`; assignment availability windows, attempt limits, accommodations; module locks and requirements;
  result-release settings of the grading scheme). Nothing in this design adds a client-side visibility decision. The
  teacher keeps every switch it has today: publish/unpublish course, module, lesson, test, announcement; availability
  dates and attempts; module locks; release settings. New in settings (platform admin only): the «Экзамен» section gets
  **family** and **subject** selects (§6.1).
- **Режим ученика shows exactly this interface** by construction: `enterStudentView` signs the tab in as the course's
  test student (a real user with `learnsHere` true), so the student frame, `/home` (one course), the course space and
  every tab render for it. Change: Student view opens the course **Обзор** (`coursePage(courseId)` already points at
  `/courses/{c}`, which no longer redirects). The test student's global nav hides Каталог, Pro, «Войти по коду», install
  and the choose step (the `testStudent` flag already hides the pill and install). `StudentViewBanner` stays sticky
  above the course header and scrolls away on object pages with their own sticky parts (unchanged rule).
- **People who teach** never get the Learning frame (`hidesLearning = teaches(me)`, backend `learns_here`); their links
  into Student view stay: `StaffCourseBar` on the course page and `CourseLanding` for a teacher opening a catalog entry.
  Org admins and platform admins reading a course (`read_only`) keep today's app-frame read-only view; `/people` stays
  for them.
- `TEACHER_TO_STUDENT_MAP.md` §0 maps every teacher action to its place in this structure.

## 6. Data, API, performance, i18n, accessibility

### 6.1 Exam family and subject (migration `0033_course_exam_family`; 3b's listing migration becomes `0034`)

Options weighed: (a) derive family from `template_key` (`ort`) / the parent's template through `exam_course_id` and
subject from `template_settings.subject` — no migration, but every grouping query (home, My courses, catalog, choose
step) needs a self-join or JSON extraction, НЦТ needs a template before it has a single course, and subject courses with
their own tests would have no family unless they are templated; (b) two nullable columns. **(b) is the smallest total
change**: two columns, one index, one backfill, and every reader filters or orders by plain columns on both databases.

- `courses.exam_family VARCHAR(16) NULL`, `courses.subject VARCHAR(32) NULL`, index
  `ix_courses_exam_family_subject (exam_family, subject)`. No CHECK on values: the registry
  `backend/app/lms/courses/exam_families.py` holds `FAMILIES = ("ort", "nct")` and `SUBJECTS = ("math", "physics",
  "chemistry", "biology", "history", "geography", "kyrgyz", "russian", "english", "literature")` with label keys
  `exam.family.{key}` / `exam.subject.{key}` (en/ky/ru); the service validates against the registry (422
  `exam_family_invalid`, `subject_invalid`), like `template_key`. Adding a family or subject is one line plus three
  dictionary keys, no migration.
- Backfill (bounded UPDATEs in the migration): `template_key = 'ort'` → `exam_family = 'ort'` (the 2 ORT courses on
  production; `subject` stays NULL = the main course); `exam_course_id IS NOT NULL` → the parent's `exam_family` (the
  attached lesson courses). Teacher courses stay NULL (= «Другие курсы»). `alembic check` clean; SQLite via `create_all`;
  `tests/test_migrations.py` covers the backfill on PG with a fixture of the three cases. Neon backup branch before
  the merge to `main` (rule 7; delete the oldest after).
- Rules (`courses/service.update_course`): both fields only on platform courses (`is_platform_course`), caller
  `is_platform_admin` (422 `exam_family_forbidden` otherwise, the `exam_course_id` pattern); `subject` requires
  `exam_family`; linking `exam_course_id` copies the target's `exam_family` when the course has none; new ORT courses
  get `exam_family = 'ort'` in `ort_course_fields`. `CourseOut`, `HomeCourseOut`, `CatalogCardOut`, `AdminCourseOut`
  carry `exam_family` and `subject`. Settings UI: the existing «Экзамен» section (`ExamDateSection` block) gains the two
  selects, platform admin only.
- `is_exam_prep` (template) still decides the countdown/goal header; `exam_family` only groups. Later improvement, not
  now: a family-level exam date (today each course has its own `settings.exam_date`).

### 6.2 Backend additions (additive)
1. `courses/service.course_features`: `tests` (published live assessment or quiz assignment visible to students; the
   `_visible_test` predicate for exam courses, the assignments list predicate for others) and `hand_ins` (published
   non-quiz assignment). `CourseOut.features` and `HomeCourseOut.features` carry all six flags for **every** course (the
   home's `_exam_features` becomes `_features`; G5 of the map closed for good). Test `tests/lms/test_course_features.py`.
2. `HomeCourseOut` + `exam_family`, `subject`, `exam_date` (from the loaded row's `settings`, free), `next_step:
   {kind: resume_test|continue_lesson|start|open, assessment_id?, attempt_id?, item link?, title}` derived from the
   home's existing statements (in-progress attempt of the course → `modules_next` of the course → first `next_up`
   assignment → `open`; **no per-course `exam_prep.page()`**), `last_result: {value, max_value, label, at} | null` from one
   window-function statement over released results (newest per course). `GET /me/home/courses` and the bootstrap's
   `student.courses` carry the same shape. Statement ceiling test (`test_pg_concurrency` bound) unchanged: +1 statement.
3. Bootstrap `activity` (7-day activity, `progress` module) computed over **all** the caller's enrollments instead of
   the newest exam course (one statement, same shape); the continue card's streak reads it (OPEN Q2).
4. Nothing in `attempts/`, `grading/`, `ort/`, `content/importers/`, `access/`, `modules/`, `exam_prep/` changes.

### 6.3 Catalog and choose step
- `GET /catalog/courses?exam=ort|nct|other` (optional; `other` = `exam_family IS NULL`), ordered `subject NULLS FIRST,
  published_at DESC` within a family (the keyset stays `published_at, id`); the 3b scope applies on top. Whichever of
  3a S4 and 3b S1 lands first, the other adapts `courses/scopes.py:_catalog_select` (one WHERE each).
- `GET /catalog/exams` (policy `authenticated`; teachers get it too, read-only): `[{family, courses: [{id, title,
  description, default_language, subject, lessons_count, tests_count, has_paid_tests, enrolled}]}]` over listed platform
  courses, ≤ 50 rows, two statements. Listed in `route_inventory.py`.
- `POST /catalog/choose {course_ids: [≤ 20]}` (policy `authenticated`; 403 `teacher_cannot_enroll` for people who teach,
  as join): each id must be a listed, published platform course with `enrollment_mode = open`; joins through the
  existing join service (same enrollment events, limits, consent gate); already enrolled → `skipped`; answer `{joined:
  [ids], skipped: [ids]}`; rate limit 5/min per user (`core/ratelimit.py`). Tests: `tests/lms/test_catalog_choose.py`
  (teacher 403, closed course 422, limit, idempotent, test student 403, consent gate). **v3: dead once the choose step is
  gone; removed in S10 (V9).** `GET /catalog/exams` stays (the catalog's chips).

**Reused endpoints:** `GET /me/bootstrap?include=home`, `GET /me/home`, `GET /me/home/courses`, `GET /courses/{c}`,
`GET /courses/{c}/exam-prep` + `/library`, `GET /courses/{c}/modules` (student), `GET /courses/{c}/assignments`,
`GET /courses/{c}/grades/mine`, `GET /courses/{c}/my/progress|activity|saved|mistakes`, `PUT …/my/goal`,
`GET /courses/{c}/lesson-courses`, `GET /courses/{c}/practice`, `GET /courses/{c}/announcements`, `GET /courses/{c}/people`,
`POST /courses/{c}/join`, `POST /courses/{c}/student-view`.

### 6.4 Performance
The course space needs `GET /courses/{c}` (SWR, 60 s, session) and the tab's one read; Обзор of an exam course =
`exam-prep` (cached by `pageData.ts`) + `modules` when lessons exist; the header's progress comes from the same answers.
Tab links prefetch on hover/focus/touch through `pageData.ts` (`prefetchExamPrep`, `prefetchAnalytics`, new
`prefetchModules`). The shell no longer asks for a "current course" (`useStudentShellData` shrinks to `courses`,
`access`, `forget`), so no page waits for the course list. `/home` stays one round (`perf-waterfall.spec.ts`). The
«Продолжить» target and the sidebar order come from `localStorage`, no request. Phone: the compact header keeps lists
above the fold.

### 6.5 Frontend pieces (names for the slices)
`components/lms/course/CourseFrame.tsx` (header, tabs, Pro bar; props `course`, `variant: "full" | "compact"`,
`activeTab`), `lib/lms/courseTabs.ts` (dependency-free: `courseTabs(course, pathname, t)` → list + active + label rule;
`courseTabs.check.ts` like `nav.check.ts`), `course/CourseOverview.tsx`, `course/ExamHeaderBlock.tsx` (countdown + goal),
`lib/lms/courseProgress.ts`, `lib/lms/lastPlace.ts` (dependency-free read/write of the two keys + `continueTarget(place,
home)`; `lastPlace.check.ts`), `app/[lang]/home/page.tsx` (`StudentHub.tsx`: `ContinueCard`, `CourseGroups`,
`TodoList`), `app/[lang]/courses/choose/page.tsx` (`ChooseCourses.tsx`; v3: a redirect stub, the component deleted),
`home/CourseCard.tsx` (countdown, last result, next-step button), `lib/lms/studentNav.ts` (global links + «Мои курсы»
rows; v3: two links, no `choose`), `StudentShell.tsx` (no switcher, no exam sheet; course rows; «Ещё» content;
«Продолжить» slot; v3: four-item bar), `courses/page.tsx` (v3: learner redirect; `MyCourses` deleted),
`courses/catalog/page.tsx` (family chips, subject sections; v3: welcome line), `courses/[courseId]/layout.tsx` (student
branch = `CourseFrame` + last-place hook; staff branch unchanged), `lib/lms/examFamilies.ts` (labels, group order;
mirrors the backend registry keys), v3: `lib/lms/courseIcon.tsx` (`courseMark`, §0.4).

### 6.6 i18n (en, ky, ru; parity script)
New: `student.nav.{home,myCourses,catalog,continue,courses,allCourses,chooseCourses,addCourse}`,
`course.tabs.{overview,lessons,tests,assignments,analytics,saved}`, `course.tabs.label`,
`course.header.{progress,examIn,examToday,target,lastScore,provider,counts,forExam}`,
`course.overview.{nextStep,latestResult,allResults,allGrades,announcements,allAnnouncements,continueLesson,allLessons,
about,teachers,materials,lessonCourses}`, `course.tests.practiceSection`, `course.analytics.gradesSection`,
`home.hub.{continue,continueTest,continueLesson,open,streak,groups.ort,groups.nct,groups.other,allInGroup,addCourse,
emptyTitle,emptyBody,choose}`, `courses.mine.{title,join,addCourse}`, `catalog.groups.{ort,nct,teachers,pick,mainCourse}`,
`choose.{title,step1,step2,enrol,skip,back,haveCode,alreadyIn,done}`, `exam.family.{ort,nct}`,
`exam.subject.{math,physics,chemistry,biology,history,geography,kyrgyz,russian,english,literature}`,
`courses.settings.examFamily.{label,subject,hint}`, errors `exam_family_invalid`, `subject_invalid`,
`exam_family_forbidden`. Removed after S5: `student.switcher.*`, `student.nav.{lessonsGroup,practiceGroup,allLessons,
mistakes,tests,lessons,practice,analytics,saved}`, `home.prep.{otherCourses,addCourse,lessonCourses.subtitle}`,
`student.lessonCourses.*`, `courses.home.tab`, `home.platform.*` (join cards); `courseNav.menu` stays (staff drawer).
v3 (§0.3): new `catalog.welcome`, `catalog.welcomeClose`, `home.hub.openCatalog`, `home.hub.collapseGroup`,
`courses.notFound.catalog`; changed `course.tabs.saved`, `student.saved.*`, `home.hub.place.saved`, `home.hub.emptyBody`,
`progress.mistakes.emptyOpen`, `progress.analytics.tiles.saved`, `landing.help.joinCode.a`; removed in S10 `choose.*`,
`courses.mine.*`, `home.hub.{choose,join}`, `catalog.groups.pick`, `student.nav.{chooseCourses,courses,joinByCode}` (and
the S5 leftovers above, still present in the dictionaries on 2026-11-13).

### 6.7 Accessibility
One `<h1>` per page; tabs are links in a `<nav>` with `aria-current`, 44 px targets, visible focus, scrollable on
phones without clipping the focused tab; the countdown is not `aria-live`; cover images are decorative (`alt=""`); the
Pro bar is a `role="note"`; the sidebar course list is a `SidebarNav` group («Мои курсы») so screen readers get one
landmark; the choose step's checkboxes are a `fieldset` per subject with a `legend`; every tab's loading, empty and
error states exist (`UX_GUIDELINES.md` §5).

## 7. Layouts (ru; 1440 and 375; 1920 = 1440 with wider gutters, content max 1200 px)

v3 reading note for every sketch: the sidebar menu has no «Мои курсы» line (Главная, Каталог, then the МОИ КУРСЫ rows
with a thumbnail or subject mark); the phone bar is ⌂ ▶ ▦ ⋯ (Главная · Продолжить · Каталог · Ещё); the fifth tab reads
«Повторение»; «Все курсы ОРТ (5) →» expands in place; §7.3 and §7.6 are superseded as noted there.

### 7.1 Home with 1 course
```
1440                                                              375
┌ sidebar ─┬────────────────────────────────────────────────────┐ ┌──────────────────────┐
│ Главная  │ [🐆] Добрый вечер, Айда                             │ │ ▣  Главная        (T)│
│ Мои курсы│ ПРОДОЛЖИТЬ                                          │ │ [🐆] Добрый вечер     │
│ Каталог  │ ОРТ (на русском) · Пробный тест 2 · раздел 2 из 5   │ │ ПРОДОЛЖИТЬ            │
│          │                               [Продолжить тест →]   │ │ ОРТ (рус) · Пробный…  │
│ МОИ КУРСЫ│ Серия 3 дня                                         │ │ [Продолжить тест →]   │
│ ● ОРТ рус│ МОИ КУРСЫ                           + Добавить курс │ │ Серия 3 дня           │
│          │ ОРТ                              │ К ВЫПОЛНЕНИЮ     │ │ МОИ КУРСЫ  + Добавить │
│          │ ┌ cover ───────────────────────┐ │ ○ Пробный тест 2 │ │ ОРТ                   │
│ ◔ Начало │ │ ОРТ (на русском)             │ │   в процессе     │ │ ┌ cover ────────────┐ │
│ ★ Pro    │ │ до экзамена 30 дн. · 132/245 │ │ ○ Эссе · до 23.02│ │ │ ОРТ (на русском)  │ │
│ ⤓ Устан. │ │ ▮▮▮▯▯ 3 из 5  [Продолжить →] │ │                  │ │ │ 30 дн. · 132/245  │ │
│ (A) Айдар│ └──────────────────────────────┘ │                  │ │ │ ▮▮▮▯▯ [Продолж.→] │ │
└──────────┴──────────────────────────────────┴──────────────────┘ │ └───────────────────┘ │
                                                                   │ К ВЫПОЛНЕНИЮ          │
                                                                   │ ○ Пробный тест 2 …    │
                                                                   │ ⌂   ▤   ▶   ▦   ⋯     │ bar
                                                                   └──────────────────────┘
```

### 7.2 Home with 8 courses (ORT main + 4 ORT subjects + 2 НЦТ subjects + 1 teacher course)
```
1440                                                              375
┌ sidebar ─┬────────────────────────────────────────────────────┐ ┌──────────────────────┐
│ Главная  │ [🐆] Добрый вечер, Айда                             │ │ ▣  Главная        (T)│
│ Мои курсы│ ПРОДОЛЖИТЬ  ОРТ: Математика · Урок 3 · Проценты     │ │ ПРОДОЛЖИТЬ            │
│ Каталог  │                                [Продолжить урок →]  │ │ ОРТ: Математика ·     │
│          │ Серия 5 дней                                        │ │ Урок 3 · Проценты     │
│ МОИ КУРСЫ│ МОИ КУРСЫ                           + Добавить курс │ │ [Продолжить урок →]   │
│ ● ОРТ Мат│ ОРТ                              │ К ВЫПОЛНЕНИЮ     │ │ Серия 5 дней          │
│   ОРТ рус│ [ОРТ (рус)   ][ОРТ: Матем. ]     │ ○ Эссе · ИИ-курс │ │ МОИ КУРСЫ  + Добавить │
│   НЦТ Физ│ [30 дн·132/245][▮▮▯ 3/8     ]     │   до 23 февр.    │ │ ОРТ (5)       Все →   │
│   Курс уч│ [ОРТ: Физика ][ОРТ: Химия  ]     │ ○ Тест 4 · НЦТ   │ │ [ОРТ (рус) 30 дн.]    │
│   НЦТ Хим│ [▮▯▯ 1/6     ][▯▯▯ 0/5     ]     │   Физика, в проц.│ │ [ОРТ: Математика 3/8] │
│   ОРТ Физ│ Все курсы ОРТ (5) →              │ ○ ОРТ: Химия     │ │ [ОРТ: Физика 1/6]     │
│ Все (8)  │ НЦТ                              │   Тест 1 · до 1.03│ │ [ОРТ: Химия 0/5]      │
│          │ [НЦТ: Физика ][НЦТ: Химия  ]     │                  │ │ Все курсы ОРТ (5) →   │
│ ◔ Начало │ [45 дн · 38/50][45 дн · —   ]     │                  │ │ НЦТ (2)               │
│ ★ Pro    │ ДРУГИЕ КУРСЫ                     │                  │ │ [НЦТ: Физика 45 дн.]  │
│ ⤓ Устан. │ [Курс учителя  ▮▮▮▯ 60 % ]       │                  │ │ [НЦТ: Химия 45 дн.]   │
│ (A) Айдар│                                  │                  │ │ ДРУГИЕ КУРСЫ (1)      │
└──────────┴──────────────────────────────────┴──────────────────┘ │ [Курс учителя  60 %]  │
  sidebar: 6 most recent rows, then «Все (8)»                      │ К ВЫПОЛНЕНИЮ (3)      │
                                                                   │ ⌂   ▤   ▶   ▦   ⋯     │
                                                                   └──────────────────────┘
```

### 7.3 Home with 0 courses (v3, V8: body «Откройте каталог, выберите экзамен и запишитесь на курс.», one button
«Открыть каталог»; no «Войти по коду», no sidebar «Выбрать курсы» row (the group is hidden); bar ▶ → the catalog)
```
1440                                                              375
┌ sidebar ─┬────────────────────────────────────────────────────┐ ┌──────────────────────┐
│ Главная  │ [🐆] Добрый вечер, Айда                             │ │ ▣  Главная        (T)│
│ Мои курсы│                                                     │ │ [🐆 hello]            │
│ Каталог  │              [🐆 hello]                             │ │ У вас пока нет курсов │
│          │        У вас пока нет курсов                        │ │ Выберите экзамен и    │
│ МОИ КУРСЫ│  Выберите экзамен и предметы, и мы подберём курсы   │ │ предметы …            │
│ + Выбрать│    [Выбрать курсы]   [Войти по коду]                │ │ [Выбрать курсы]       │
│   курсы  │                                                     │ │ [Войти по коду]       │
│ ◔ Начало │                                                     │ │                       │
│ ★ Pro    │                                                     │ │                       │
│ (A) Айдар│                                                     │ │ ⌂   ▤   ▶   ▦   ⋯     │ ▶ → choose
└──────────┴─────────────────────────────────────────────────────┘ └──────────────────────┘
```

### 7.4 Exam course Обзор (ОРТ на русском)
```
1440                                                              375
┌ sidebar ─┬ cover strip ───────────────────────────────────────┐ ┌ cover strip ─────────┐
│ …        │ ОРТ (на русском)        [30 дн][07 ч][59 мин] до экз.│ │ ОРТ (на русском)     │
│ МОИ КУРСЫ│ Платформа · Русский · 12 тестов · 4 урока           │ │ 30 дн 07 ч 59 мин    │
│ ● ОРТ рус│ Последний балл 132 · Цель 200 ✎   Пройдено 3 из 12  │ │ 132 → 200 ✎ · 3 из 12│
│   ОРТ Мат│ Обзор · Уроки · Тесты · Аналитика · Сохранённые     │ │ Обзор Уроки Тесты Ан›│
│          ├──────────────────────────────────┬──────────────────┤ ├──────────────────────┤
│          │ СЛЕДУЮЩИЙ ШАГ  Пробный тест 2    │ О КУРСЕ          │ │ СЛЕДУЮЩИЙ ШАГ        │
│          │ раздел 2 из 5   [Продолжить →]   │ Платформа        │ │ [Продолжить тест →]  │
│          │ ПОСЛЕДНИЙ РЕЗУЛЬТАТ  132 / 245   │ Подготовка к ОРТ:│ │ ПОСЛЕДНИЙ РЕЗУЛЬТАТ  │
│          │ math_1 ▮▮▮▯ 12/30 · math_2 ▮▮▯▯ …│ 5 разделов …     │ │ 132 / 245            │
│          │ Все результаты →                 │ Преподаватели:   │ │ 5 section bars       │
│          │ ОБЪЯВЛЕНИЯ «Расписание …» Все →  │ Платформа ОРТ    │ │ ОБЪЯВЛЕНИЯ «…» Все → │
│          │ УРОКИ  Продолжить урок ▶ Проценты│ Курсы с уроками: │ │ УРОКИ ▶ Проценты     │
│          │ Все уроки →                      │ [Математика с А.]│ │ ★ Откройте все …     │
│          │ ★ Откройте все экзамены (gold)   │ [mascot]         │ │ О курсе (compact)    │
│          │ Покинуть курс                    │                  │ │ Покинуть курс        │
└──────────┴──────────────────────────────────┴──────────────────┘ │ ⌂   ▤   ▶   ▦   ⋯    │
                                                                   └──────────────────────┘
Тесты (compact header)                       Аналитика (compact header)
┌ ОРТ (на русском) › Обзор · Уроки · [Тесты] …┐ ┌ … · [Аналитика] · Сохранённые   [30 дней ▾] ┐
│ ★ Платные тесты открываются с Pro [Открыть] │ │ [Вопросов 240][Точность 64 %]  история баллов│
│ Тесты · 12  [Все][Не начат][В процессе][…]  │ │ 5 слабых тем … → Тренировки                  │
│ [card][card][card]  (TestLibrary unchanged) │ │ Активность · heatmap · серия                 │
│ ТРЕНИРОВКИ #practice  [Математика I · 20] … │ │ Ошибки 5 → Сохранённые                       │
└─────────────────────────────────────────────┘ └──────────────────────────────────────────────┘
```

### 7.5 Lesson course Обзор (platform masterclass or a teacher course)
```
1440                                                              375
┌ sidebar ─┬ cover strip ───────────────────────────────────────┐ ┌ cover strip ─────────┐
│ …        │ Математика с учителем                               │ │ Математика с учител… │
│ МОИ КУРСЫ│ Платформа · Русский · 2 теста · 8 уроков            │ │ К экзамену: ОРТ (рус)│
│   ОРТ рус│ К экзамену: ОРТ (на русском)                        │ │ Пройдено 3 из 10 30 %│
│ ● Матем. │ Пройдено 3 из 10 ▮▮▮▯▯▯▯▯▯▯ 30 %                    │ │ Обзор Уроки Задания ›│
│          │ Обзор · Уроки · Задания · Аналитика · Сохранённые   │ ├──────────────────────┤
│          ├──────────────────────────────────┬──────────────────┤ │ СЛЕДУЮЩИЙ ШАГ        │
│          │ СЛЕДУЮЩИЙ ШАГ  Урок 4 · Дроби    │ О КУРСЕ          │ │ Урок 4 · Дроби       │
│          │                [Продолжить урок →]│ Платформа        │ │ [Продолжить урок →]  │
│          │ ПОСЛЕДНИЙ РЕЗУЛЬТАТ  Эссе 7 / 10 │ Описание …       │ │ ПОСЛЕДНИЙ РЕЗУЛЬТАТ  │
│          │ «Хорошо, но …»      Все оценки → │ Преподаватели:   │ │ Эссе 7 / 10          │
│          │ ОБЪЯВЛЕНИЯ «Вебинар …»    Все → │ Учитель          │ │ ОБЪЯВЛЕНИЯ «…» Все → │
│          │ УРОКИ  Продолжить ▶ Дроби · 6 мин│ Материалы (2) →  │ │ УРОКИ ▶ Дроби        │
│          │ Все уроки →                      │ [mascot]         │ │ О курсе (compact)    │
│          │ Покинуть курс                    │                  │ │ Покинуть курс        │
└──────────┴──────────────────────────────────┴──────────────────┘ │ ⌂   ▤   ▶   ▦   ⋯    │
                                                                   └──────────────────────┘
A teacher course without an exam link: the same, without the «К экзамену» line; in the «Другие курсы» group.
```

### 7.6 Choose your courses `/courses/choose?first=1` (v3: removed; the new account lands on the catalog of §2.4 with
the welcome line «Добро пожаловать! Выберите экзамен и запишитесь на курс.» [×] under the title; kept as v2 history)
```
1440                                                              375
┌ sidebar ─┬────────────────────────────────────────────────────┐ ┌──────────────────────┐
│ …        │ Выберите курсы                        [Пропустить] │ │ Выберите курсы  Проп.│
│          │ 1 · ЭКЗАМЕН                                         │ │ 1 · ЭКЗАМЕН           │
│          │ [● ОРТ  Общереспубликанское тестирование · 5 курсов]│ │ [● ОРТ · 5 курсов]    │
│          │ [○ НЦТ  Предметные тесты · 2 курса]                 │ │ [○ НЦТ · 2 курса]     │
│          │ У меня есть код от преподавателя →                  │ │ Есть код от препод. → │
│          │ 2 · КУРСЫ ОРТ                                       │ │ 2 · КУРСЫ ОРТ         │
│          │ ОСНОВНОЙ КУРС                                       │ │ ОСНОВНОЙ КУРС         │
│          │ [☑ ОРТ (на русском) · 12 тестов · 4 урока]          │ │ ☑ ОРТ (на русском)    │
│          │ [☐ ОРТ (кыргызча) · 12 тестов]                      │ │ ☐ ОРТ (кыргызча)      │
│          │ МАТЕМАТИКА          ФИЗИКА          ХИМИЯ           │ │ МАТЕМАТИКА            │
│          │ [☐ ОРТ: Математика] [☐ ОРТ: Физика] [☐ ОРТ: Химия ★]│ │ ☐ ОРТ: Математика     │
│          │                                                     │ │ ФИЗИКА …              │
│          │                               [Записаться (1) →]   │ │ [Записаться (1) →]    │
└──────────┴─────────────────────────────────────────────────────┘ │ (sticky button)       │
                                                                   └──────────────────────┘
```

## 8. Decisions

### 8.1 Owner's answers (2026-11-13, binding)

| # | Decision | Owner |
|---|---|---|
| D1 | Home URL | **`/home`**; `/courses` = My courses (learners) / Teaching list (people who teach) |
| D2 | Global Аналитика | **Per course only**, no global page |
| D3 | Оценки tab | **No separate tab**: scores and grades are in the course's Аналитика tab |
| D4 | Tab label | **By content**: Тесты, or Задания when the course has a hand-in assignment |
| D5 | Lesson courses attached to an exam | **Stay separate courses**, listed in the related exam's Уроки tab |
| D6 | Practice sets | **Inside the Тесты tab** |
| D7 | Lobby, result and review | **Inside the course layout**; the player full-screen |
| D8 | Phone bar | **Главная · Курсы · Продолжить · Каталог · Ещё** (point 4); v3: the owner's item 2 removes «Курсы» → Главная · Продолжить · Каталог · Ещё (V6) |
| D9 | Countdown | **On the course card and on the course's Обзор tab** |
| D10 | Teachers | **Names on Обзор** (no People tab for students) |
| 1–7 | Hub-only home; course spaces with content-driven tabs; no global pages or switcher; sidebar course list, remembered last course/tab, phone bar; catalog grouped by exam/subject and the choose step; exam family + subject with the smallest change; teacher control and Режим ученика | as in the verbatim brief |

### 8.2 New decisions made here (owner silent; recommendation in effect)

| # | Decision | Choice and why |
|---|---|---|
| N1 | Exam family / subject storage | Two nullable columns + registry in code (§6.1); every grouping query filters by plain columns, НЦТ needs no template to get its first course |
| N2 | Remember last course and tab | `localStorage` per user + the server fallback on the home (§2.5); no write per page view, no migration, Student view separated by the user id in the key |
| N3 | Sidebar order | Recent first, no pin control in v1; «Все курсы» after 6 rows (v3: → `/home#courses`, V7) |
| N4 | Аналитика tab URL | `/courses/{c}/analytics`, shared with the staff statistics page by role branch; `/progress` and `/grades` redirect (bookmarks keep working, label = URL) |
| N5 | Аналитика visibility | Shown when the course has tests or hand-ins; a lessons-only course shows its progress in the header and Уроки tab, no Аналитика |
| N6 | Course card next step | Derived from the home's existing statements (in-progress attempt → next lesson → next assignment → open), never a per-course `exam_prep.page()`: ten cards stay one round |
| N7 | Choose step after sign-up | `?redirect=` (invites, teacher code, catalog landing) and the under-14 consent branch keep precedence; the step is not stored as "seen": the empty home is the reminder. v3: the step is gone; the same precedence leads a new account to `/courses/catalog?welcome=1` (V4) |
| N8 | Installed app start page | `manifest.start_url` → `/ru/home` (signed-out → login with `?redirect=`; a teacher → Teaching by `urlAreaFor`); `pwa.spec.ts` updated |
| N9 | Catalog default chip | The family of the student's newest exam course, else ОРТ; teacher courses under «Курсы преподавателей» (no family) |
| N10 | Home group caps | 4 cards per group + «Все курсы … (N)» → `/courses#family`; keeps the hub short on a phone with 10 courses. v3: the link becomes an in-place expand (V7), the cap stays |

**OPEN Q** (recommended answers in effect; the orchestrator continues with them):

| # | Question | Recommendation |
|---|---|---|
| OPEN Q1 | Announcements across courses: today the home's side list shows the newest three of all courses; the hub has no announcements block. Where do students notice a new announcement? | **Rows in «К выполнению»** of kind `announcement` (newest three unread-by-time, as today's list, each named with its course) + the course Обзор strip. No separate list on the hub |
| OPEN Q2 | Overall streak: today's `StreakCard` is the newest exam course's 7-day activity on the home; the hub "has no statistics of its own" | **One quiet line «Серия N дней» in the continue card**, cross-course (bootstrap activity over all enrollments), shown only when N ≥ 2; heatmaps and per-course streaks stay in each course's Аналитика |
| OPEN Q3 | All recent results across courses: today the home side list «Результаты» (`latest_results`); the owner removed statistics from the hub | **Removed on purpose**: each exam course card shows its last result line («132 / 245»), general cards the last grade; full lists live in each course's Аналитика. If the owner wants the cross-course list back it is one block on `/courses` (data already in `HomeOut.latest_results`) |
| OPEN Q4 | ORT subject courses: built from the ORT template (exam-prep header: countdown and target per course) or as general platform courses with `exam_family='ort'` + `subject` | **From the ORT template** (`ort_subject` presets exist; countdown/target/section bars come free); the owner sets family and subject in settings. The design works either way |

## 9. Slices (each deploys alone; safest first; Opus unless noted)

S1–S6 are deployed (`FIX_ROUND_2026-11-12.md` results); the v3 slices S7–S10 are in §0.5.

Every slice: `tsc`, parity script, SQLite suite, the e2e specs named, screenshots at 375 / 1440 / 1920 in ru checked by
the orchestrator, `role-links.spec.ts` + `roleLinks.check.ts` green, ORT parity/exam-rule tests unchanged.

| # | Slice (model) | Content | Tests | Deployable alone because |
|---|---|---|---|---|
| S1 | Data and backend (Opus) | migration `0033_course_exam_family` + backfill + registry + settings rules + `ort_course_fields`; `features.tests/hand_ins` for every course; `HomeCourseOut` additions (`exam_family`, `subject`, `exam_date`, `next_step`, `last_result`); cross-course bootstrap activity; `GET /catalog/exams`, `POST /catalog/choose`, `GET /catalog/courses?exam=`; inventory rows; settings UI selects (platform admin) | `test_migrations.py` (backfill fixture), `test_course_features.py`, `test_home.py` (next_step, last_result, groups, statement bound), `test_catalog_choose.py`, `test_catalog_exams.py`, `alembic check`, PG concurrency suite untouched; Neon backup before the `main` merge | additive columns and fields; no screen changes except two admin selects |
| S2 | Course space (Opus) | `CourseFrame`, `courseTabs.ts` + check, `CourseOverview`, `ExamHeaderBlock`, `courseProgress.ts`; the layout's student branches become one; Уроки tab (`/lessons`), Тесты for general courses (cards, label rule, `#practice`), Аналитика by role branch (`#grades`), Сохранённые tab; object-page compact header; redirects (`/modules`, `/assignments`, `/progress`, `/grades`, `/practice`, `/people`); Student view opens Обзор; `lastPlace.ts` write hook | `course-nav.spec.ts` (student parts rewritten), `lessons.spec.ts`, `modules.spec.ts`, `exam-prep.spec.ts`, `teacher-to-student.spec.ts`, `student-result.spec.ts`, `student-analytics.spec.ts`, `student-saved.spec.ts`, `practice.spec.ts`, `pro-courses.spec.ts`, `access.spec.ts`; **ORT**: `ort.spec.ts`, `ort-visual.spec.ts` DOM assertions green; lobby/result/review baselines re-recorded deliberately (pairs in `STUDENT_IA_screens/ort/`); player, section-end, submit, passage, comparison, flagged-palette, review-page, player-loading and `teacher-*` zero diff; `courseTabs.check.ts`, `lastPlace.check.ts` | the old global sidebar still works (its links land on tabs); every old URL redirects |
| S3 | Global frame and hub (Opus) | `/home` hub (`StudentHub`: continue card, grouped cards with countdown / last result / next step, to-do with announcement rows, notices, empty state); `/courses` = grouped My courses for learners; `StudentShell` without switcher, exam sheet, УРОКИ group and per-course links; sidebar «Мои курсы» rows (recent first, 6 + «Все курсы»); phone bar Главная · Курсы · Продолжить · Каталог · Ещё and the «Ещё» sheet; `useStudentShellData` reduced; `shellKind.ts` (`/home`, `/courses/choose`; `coursesDefault` gone); `?view=`/`#catalog` redirects; `roleLinks.check.ts` table + `role-links.spec.ts` entries; `manifest.start_url` `/ru/home`; getting-started per student | `student-home.spec.ts` rewritten (0 / 1 / 8 courses, continue fallback order, groups, to-do), `student-shell.spec.ts` rewritten (one nav, no second sidebar on any course page, the bar on every page, «Продолжить» target), `mobile-sheets.spec.ts`, `student-links.spec.ts`, `header-areas.spec.ts`, `shell-stable.spec.ts`, `perf-waterfall.spec.ts` (home one round), `pwa.spec.ts`, `shellKind.check.ts`, `studentNav.check.ts` | S2 already made every course self-navigating |
| S4 | Choose step and catalog grouping (Opus) | `/courses/choose` (`ChooseCourses`), sign-up and Google new-account redirect, «Добавить курс» / «Выбрать курсы» / «Подобрать курсы» entries, catalog family chips + subject sections (`?exam=`), «Записаться» → Обзор | new `choose-courses.spec.ts` (sign-up → step → skip; pick 2 → home continue card; teacher → Teaching redirect; test student none; `?redirect=` precedence), `catalog-apply.spec.ts`, `course-cards.spec.ts`, `landing.spec.ts`, `auth-screens.spec.ts`, `oauth-google.spec.ts`; `role-links` | additive pages; coordinates with 3b S1 on `_catalog_select` |
| S5 | Cleanup (Opus; `grep -rl` before each deletion) | delete `ToTests`, `isExamShellCourse`, `StudentCourseHome`, `StudentCourseHeader` for students, student `CourseSidebar` path, `lessons/page.tsx` old body, `ExamSwitcher`, `ExamSheetBody`, `lessonCourseLinks`, `ViewSync`, `coursesDefault`, `?tab=` in `LmsShell`, `ExamPrepHome`, `PlatformCourses`, `ort_student_course` key; i18n keys of §6.6; docs (`STUDENT_UI_DESIGN.md` §2 pointer, `HANDOFF_NEXT_AGENT.md`, `AGENTS.md` head `0033`/`0034`, `PRODUCT_DECISIONS.md`, `TEACHER_TO_STUDENT_MAP.md` §1 note) | full SQLite suite, `tsc`, parity, `nav.check.ts`, all e2e | removals only |
| S6 | Text and polish (Sonnet) | ky/en strings (incl. group and subject labels), spacing at 375/1440/1920, empty states, `STUDENT_IA_screens/after/` | parity script, screenshot pass | styling only |

Order S1 → S2 → S3 → S4 → S5 → S6; each is one merge commit (`lms`, then `main` with CI green and `/health` showing
the commit). **Rollback:** S1's downgrade drops the two columns (no reader depends on them before S3); S2/S3/S4 revert
restores the previous frame because no data changed and every old URL still exists; S5 is removals (revert = restore).

## 10. "Nothing lost" table (owner's check; verified against the code on 2026-11-13; v3 rows marked)

Legend: **kept** = same place or same URL; **moved** = new place, old link redirects; **removed on purpose** = with the
reason. OPEN Q rows carry the recommended answer, in effect. v3 (owner item 2) removes three things built by S3/S4 and
the table says where each went: the learner «Мои курсы» page → the hub (same cards, `/courses` redirects); the choose
step → the catalog (same courses, grouped by subject; `/courses/choose` redirects); the extra «Войти по коду» copies →
the catalog header's one button.

### 10.1 Today's student pages and features

| Item | Today (where) | New place | Note |
|---|---|---|---|
| Home: next step | `/courses` → `home/StudentHome.tsx` → `ExamPrepHome.tsx` `NextCard` of the *current* exam (`exam_prep.next`) | `/home` continue card (one button; last place → server fallback) + a next-step button on every course card | moved: the hub names the course; the exam's own `NextCard` stays on its Обзор |
| Home: to-do | `/courses` side list «К выполнению» (`StudentHome.tsx:101-104`, `HomeOut.todo`, in-progress first, overdue flag) | `/home` «К выполнению» across courses (same `TodoList`) | kept |
| Home: «Продолжить урок» strip | `ExamPrepHome.tsx:56, 65` `ContinueLessons` (`modules_next`) | folded into the continue card and the card buttons; the course Обзор «Уроки» teaser | moved |
| Home: score tiles, section bars, score history | `ExamPrepHome.tsx:70-83` `ScoreTiles`/`ScoreLine`/`SectionRows` of the current exam | exam course Обзор (goal strip, «Последний результат» + bars) and Аналитика (history) | moved (owner: no statistics on the hub; countdown and last result on the card, D9) |
| Home: countdown | `ExamPrepHome.tsx:65-100` `Hero` of the current exam | every exam course card (small) + the course header tiles | kept (D9) |
| Home: streak | `ExamPrepHome.tsx:58-76` `StreakCard` (newest exam course's 7-day activity) | continue card line «Серия N дней» (cross-course) | moved; **OPEN Q2** |
| Home: latest results side list | `StudentHome.tsx:108` «Результаты» (`HomeOut.latest_results`) | course cards: last result line; course Аналитика: full list | **removed on purpose** (owner point 1); **OPEN Q3** |
| Home: announcements side list | `StudentHome.tsx:129-145` (newest three across courses) | to-do rows of kind announcement + course Обзор strip | moved; **OPEN Q1** |
| Home: «От платформы» join cards | `ExamPrepHome.tsx:92` `PlatformCourses` (`HomeOut.platform_courses`) | «Добавить курс» → v3: `/courses/catalog` (ОРТ chip: the platform courses by subject) | moved (owner 2026-11-13: the catalog is the one place to add a course) |
| v3: «Мои курсы» page `/courses` (S3) | grouped cards, «Добавить курс», «Войти по коду», anchors `#ort`… | `/home` (the same `CourseGroups`, expand in place), `/courses` → `/home`, `#family` → `/home#courses` | **removed on purpose** (owner item 2: a copy of the hub and the sidebar) |
| v3: choose step `/courses/choose` (S4) | exam cards → courses by subject with checkboxes, «Записаться (N)», «Пропустить» | the catalog's family chips and subject sections (`/courses/catalog?exam=ort`), one «Записаться» per card; new accounts land there with a welcome line | **removed on purpose** (owner item 2: one way to add a course); `/courses/choose` redirects |
| Home: lesson courses cards | `ExamPrepHome.tsx:91` `LessonCourses`, sidebar УРОКИ group (`StudentShell.tsx:113-136`) | the exam's Уроки tab (end section) + the exam's group on `/home` and `/courses` | moved (D5) |
| Home: «Другие курсы» | `ExamPrepHome.tsx:281-296` | `/home` and `/courses` group «Другие курсы» | kept |
| Home: course cards (non-exam student) | `StudentHome.tsx:41-82` `CourseCards` + «Показать все» | `/home` grouped cards, `/courses` full list | kept |
| Home: pending invitations, pending applications, teacher-application notice, privacy banner | `courses/page.tsx` (`TeacherApplicationNotice`), `StudentHome.tsx` (`pending_invitations`, `pending_applications`), `LmsShell` (`PrivacyBanner`) | `/home` (same components) and the shell | kept |
| Tests library | `/courses/{c}/tests` (`examPrep/TestsPage.tsx`, `TestLibrary`) | Тесты tab, same URL | kept |
| Lobby | `/courses/{c}/assessments/{a}` in the exam branch's 880 px column without a header (`layout.tsx:131-146`) | same URL, inside the course space with the compact header (Тесты active) | kept (D7); baseline re-recorded |
| Exam player | `/courses/{c}/attempts/{id}` `PLAYER_FRAME` (`shellKind.isPlayerRoute`, `layout.tsx:98`) | unchanged, full-screen | kept |
| Result and review | `/courses/{c}/attempts/{id}/result` (exam branch column; general: `StudentCourseHeader` + no sidebar) | same URL inside the course space, compact header | kept (D7); baselines re-recorded |
| Analytics: weak topics, activity, heatmap, streak | `/courses/{c}/progress` (`progress/AnalyticsOverview.tsx`, `PeriodPicker`) | Аналитика tab `/courses/{c}/analytics`; `/progress` redirects | moved (D2: per course) |
| Saved questions and mistakes | `/courses/{c}/saved` (`progress/SavedPage.tsx`, tabs; `?tab=mistakes`) | v3: **Повторение** tab (inner tabs Отмеченные · Ошибки), same URL | kept (renamed, owner item 3) |
| Practice | `/courses/{c}/practice` (sidebar «Практика», phone bar slot) | Тесты tab section «Тренировки» `#practice`; redirect | moved (D6) |
| Lessons: syllabus | `/courses/{c}/modules` (`modules/StudentSyllabus.tsx`; sidebar «Уроки») | Уроки tab `/courses/{c}/lessons`; redirect, `#m-{id}` kept | moved |
| Lessons: lesson / video page | `/courses/{c}/modules/{m}/items/{i}` (`LessonView`, outline aside, pager) | same URL, compact header (Уроки active) | kept |
| Lessons: «Все уроки» lesson-course list | `/courses/{c}/lessons` (`lessons/page.tsx`) | the same URL is the Уроки tab; the list is its last section | kept (URL), moved (content) |
| Pages outside modules | no student entry (map G3, decision D3 there) | unchanged: reachable through lessons only | kept as decided |
| Announcements | `/courses/{c}/announcements` (`AnnouncementsView`; exam course: reached from the home side list only, G2) | Обзор strip «Объявления» + «Все объявления» → same URL (compact header) | kept; the strip fixes G2 for good |
| Files | `/courses/{c}/files` (general: `CourseSidebar` link; exam course: URL only, G3) | Обзор «О курсе» → «Материалы» when `features.files` | kept; now linked in exam courses too |
| Assignments with text / file hand-in | `/courses/{c}/assignments` list (`CourseSidebar` «Задания»), `/assignments/{id}` page | Задания tab (`/tests`, label by content) → same assignment page | moved (D4) |
| Grades and feedback | `/courses/{c}/grades` (`StudentGrades`; `CourseSidebar` «Оценки») | Аналитика tab block «Оценки» (`#grades`); redirect | moved (D3) |
| Course overview (general) | `/courses/{c}` → `StudentSyllabus` / `PageView` + modules / `StudentCourseHome` (`page.tsx:51-66`) | Обзор (one component); a `home_kind = page` course shows its page as the first Обзор block | kept |
| ORT course page | `/courses/{c}` → `ToTests` → `/tests` (`page.tsx:54`) | Обзор with countdown, target, last result, section bars | moved (P5 fixed) |
| Teachers (People) | `/courses/{c}/people` (students, `CourseSidebar`) | Обзор «О курсе» names | moved (D10); observers keep the page |
| Catalog | `/courses/catalog` (`CatalogView`), landing `/courses/catalog/{id}`, apply `/apply` | same URLs; family chips + subject sections (§2.4); «Записаться» → Обзор | kept + grouping |
| Join by code | `/courses/join` (`JoinCodeForm`; links on the home, exam sheet, not-found page) | same page; v3: **one** link, the catalog header's «Войти по коду» (plus the by-code landing's «Ввести код»); the «Ещё», hub, `/courses`, choose-step and not-found copies are gone; teacher-code sign-up links (`?redirect=/courses/join?code=…`) still land on the page | kept (one entry, owner item 2) |
| Pro page | `/pro` (`pro/page.tsx`: plans, comparison, how to pay); sidebar `AccessPill`, «Ещё», account row | same page; sidebar pill, «Ещё», global menu item | kept |
| Pro locks | `ProChip`/lock on test cards, `UnlockCard` on the home, `ProCallout`, `ProLockCard` on lessons, module gold chip | the same components per course: Тесты/Уроки Pro bar, lobby, lesson lock card, Обзор unlock card | kept |
| Gift codes | `/unlock` (`redeemCode`, linked from `/pro`) | unchanged | kept |
| Getting-started checklist | sidebar pill + sheet (`gettingStarted.tsx`: goal, first test, practice, install), per user **and exam course** | sidebar pill / «Ещё»; per student: goal → newest exam course Обзор `#goal`, first test → its Тесты tab, practice → `#practice`, install | kept, scope per student |
| Install app | `InstallItem` sidebar / «Ещё» (`pwa`) | same | kept |
| Account, language, privacy, logout | account sheet (`AccountPanel`: name, language, `/privacy` link, «Выйти»); «Ещё» footer | same sheet from the sidebar button and «Ещё» | kept |
| Leave course | exam sheet «Покинуть» (`ExamSheetBody`), general `LeaveCourseLink` on the course home | Обзор quiet link «Покинуть курс» (`LeaveCourseDialog`) | kept |
| Course cover | card cover, syllabus banner | card + Обзор full header; v3: a 24 px thumbnail in the sidebar/«Ещё» rows; the default cover's mark is the subject icon (§0.4) | kept (+ icons, owner item 4) |
| Target score edit | `ScoreTiles` goal dialog on the home | Обзор goal strip ✎ (same `PUT /my/goal`) | moved |
| Exam switcher | `StudentShell.tsx:235-296` | — | **removed on purpose** (owner point 3) |
| Global Тесты / Аналитика / Сохранённые | v1 design only (never built); today's per-exam sidebar links | course tabs | **removed on purpose** (owner points 2–3) |

### 10.2 States

| State | Today | New | Note |
|---|---|---|---|
| No courses yet | `/courses` empty state (`StudentHome.tsx:180-186`: «Войти по коду», «Каталог»); sidebar Главная · Каталог | v3: `/home` empty state with one button «Открыть каталог» (the catalog holds «Войти по коду»); sidebar Главная · Каталог, no course group; phone «Продолжить» → the catalog | kept (the catalog is the entry, as before 3a) |
| One course | exam switcher without chips, exam sidebar | continue card + one card; sidebar one row; the course's own tabs | kept |
| Many courses | chips for exam courses; others at the bottom of the home | groups ОРТ / НЦТ / Другие (4 cards + «Все …» v3: expands in place), sidebar 6 recent + «Все курсы (N)» → `/home#courses` | kept (owner point 1) |
| Course with only tests | ORT: Тесты, Аналитика, Сохранённые links; general: Задания, Оценки | Обзор · Тесты · Аналитика · Сохранённые | kept |
| Course with only lessons | sidebar «Уроки» (exam) / `CourseSidebar` «Уроки» | Обзор · Уроки | kept (N5) |
| Both | all links | all five tabs | kept |
| Locked Pro module | syllabus gold chip, `ProLockCard` on the lesson, sidebar gold pill | Уроки Pro bar + chip, lesson lock card, Обзор unlock card, sidebar pill | kept |
| Expired Pro pass | `access.active = false`: pill «Открыть все экзамены», paid tests locked, `/pro` shows the plans | the same (pill in sidebar/«Ещё», Pro bar on Тесты, unlock card on Обзор) | kept |
| Test in progress | home `NextCard` resume, to-do first row, Тесты card «В процессе», lobby «Продолжить» | continue card «Продолжить тест» (top of the fallback order), to-do first row, course Обзор next step, Тесты card chip; «Продолжить» bar slot | kept |
| Offline phone | service worker: network first, `/{lang}/offline` page on failure; attempt autosave queue in `attemptClient` | unchanged; the «Продолжить» target resolves from `localStorage` and then shows the offline page; the hub is served from cache only as the offline page (no offline data) | kept |

### 10.3 Roles

| Role | Today | New | Note |
|---|---|---|---|
| Student | student frame (`shellKindFor` = `student`) | the frame of §2 | kept |
| Teacher in Режим ученика | test student = real user with `learnsHere`; the student frame; `enterStudentView` → `/courses/{c}` (ORT → `/tests`); no Pro, install | the same frame; Student view opens Обзор; no Каталог, Pro, «Войти по коду», install; `/home` shows the one course; v3: bar Главная · Продолжить · Ещё, `/courses` → `/home` | kept (owner point 7) |
| Teacher who is not a student | never the Learning frame (`hidesLearning`), `/pro` and the catalog in the app frame, Student view button on the course page, leftover enrolment → «Этот курс открывается только в аккаунте ученика» | unchanged; `/home` and `/courses/choose` resolve to Teaching through `urlAreaFor` | kept |
| Org / platform admin reading a course | read-only course view in the app frame, `/people` | unchanged | kept |
| Parent / guardian | `/parent` area, other-areas links | unchanged (other areas in the sidebar and «Ещё») | kept |

### 10.4 Cross-course needs

| Need | Today | New home | Note |
|---|---|---|---|
| All upcoming deadlines | home side list «К выполнению» (`HomeOut.todo`, overdue flag) | `/home` «К выполнению» (same data, every course, each row named with its course) | kept |
| All recent results | home side list «Результаты» | per-course card last-result line; full lists per course in Аналитика | **OPEN Q3**: removed on purpose, recommended as is |
| Overall streak | `StreakCard` of the newest exam course only (not cross-course today) | continue card line, cross-course | **OPEN Q2** |
| New announcements anywhere | home side list | to-do announcement rows + course Обзор strip | **OPEN Q1** |
| "Where was I?" | `localStorage` current exam only | continue card + «Продолжить» bar slot + sidebar recent rows (§2.5) | new |

### 10.5 Links, app start, link check

| Item | Today | New | Note |
|---|---|---|---|
| Old links and bookmarks | `/courses?view=…`, `/courses/{c}/modules`, `/progress`, `/grades`, `/practice`, `/people`, `/assignments` | the redirect table §3.7 (query and hash kept); v3 adds `/courses` (learner) → `/home`, `/courses#family` → `/home#courses`, `/courses/choose[?first=1]` → `/courses/catalog[?welcome=1]` | kept |
| Installed app start page | `manifest.ts` `start_url: "/ru/"` → the landing (`[lang]/page.tsx`, CTA → `/courses`) | `start_url: "/ru/home"`: signed-in learner → hub; signed-out → login with redirect; teacher → Teaching | moved (N8); `pwa.spec.ts:83` updated |
| Per-role link check | `lib/lms/roleLinks.check.ts` fixed table + `e2e/role-links.spec.ts` `ENTRY` per role (desktop + 375) | table gains `/home`, `/courses/choose`, `/courses/c1/{lessons,analytics,saved}` per role; `ENTRY.student` gains `/ru/home`, `/ru/courses/choose`; the walk also opens the «Мои курсы» rows and the «Продолжить» slot. v3 (V14): rows `/ru/courses/catalog?welcome=1` and `/ru/home#courses`; `/ru/courses` and `/ru/courses/choose` stay as redirect entries; the student walk asserts no link to `/ru/courses` and «Войти по коду» only on the catalog | kept, extended |
| Student view entry links | `StaffCourseBar` button, `CourseLanding` for a teacher | unchanged | kept |
