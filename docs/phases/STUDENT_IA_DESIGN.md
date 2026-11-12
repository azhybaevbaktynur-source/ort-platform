# One student interface: information architecture and course page pattern (fix round 2026-11-12, step 3a)

**Status**: design only (architect on Fable, 2026-11-12). Base: `lms` 6370128. Owner brief: `FIX_ROUND_2026-11-12.md`
step 3a. Rule: AGENTS.md §6.9 (ORT exam rules fixed; ORT is a normal course). Owner decision 2026-11-12: teachers and
students are separate accounts, so this design is for people who learn (`learnsHere(me)`) and for Student view; the
teacher interface is out of scope except its links into Student view (§5).

Before-screenshots (production code against the Neon triage branch, student `azhybaevbaktynur3@…`, ru):
`docs/phases/STUDENT_IA_screens/before/01-home-1440.png` … `08-ort-lessons-1440.png`.

## 1. Problems today, and what stays

| # | Problem | Where (file:line) | Screen |
|---|---|---|---|
| P1 | **Two navigations at once.** Inside a teacher's course the global student sidebar (Главная, Тесты, Аналитика, Уроки, Сохранённые of the *ORT* course) and the old course sidebar (Курс, Задания, Оценки, Преподаватели, Файлы, Мой прогресс, Сохранённые) are both drawn | `app/[lang]/courses/[courseId]/layout.tsx:168-175` (`CourseSidebar` for general courses) + `components/lms/student/StudentShell.tsx:399-405` (global `SidebarNav`) | 05, 06, 07 |
| P2 | **The ORT switcher stays visible in unrelated courses**, and "Тесты"/"Аналитика" in the global sidebar point at the remembered ORT course while the student reads a teacher course | `StudentShell.tsx:235-296` (`ExamSwitcher`), `student/useStudentShellData.ts:143-151` (`current` = remembered exam when the path's course is not an exam) | 05 |
| P3 | **Global items are per-course.** Тесты, Уроки, Практика, Сохранённые, Аналитика carry the *current exam's* id (`lib/lms/studentNav.ts:48-64`); switching the exam silently swaps the page under the same link (`ExamSwitcher.switchTo` keeps the section) | `studentNav.ts`, `StudentShell.tsx:242-255` | 01, 03 |
| P4 | **Two course page shapes**: the exam-shell branch (own titles, no course header, no sidebar: `layout.tsx:130-146`) and the general branch (`StudentCourseHeader` + `CourseSidebar`: `layout.tsx:148-175`); four student course homes (`[courseId]/page.tsx:44-61`: `ToTests` redirect, `StudentSyllabus`, `PageView`+modules, `StudentCourseHome`) | | 03, 05, 08 |
| P5 | **The ORT course has no overview**: `/courses/{c}` redirects to `/tests` (`page.tsx:47, 121-127`); the countdown, target score and section bars live only on the global home for the "current" exam (`home/ExamPrepHome.tsx`), so a student with two ORT courses sees one exam's numbers on a page called "Главная" | | 01 |
| P6 | **Phone: per-exam tab bar + a course drawer.** The bottom bar is Главная · Тесты · Практика · Аналитика · Ещё of the current exam (`StudentShell.tsx:488-490`); inside a teacher course a second menu «Меню курса» opens a drawer (`components/lms/course/CourseSidebar.tsx:41-43`, `AreaShell phone="drawer"`) | | 06, 07 |
| P7 | **`?view=` machinery** for the home: `ViewSync` and `ViewParam`, `coursesDefault`, the `/courses?view=learning` redirect, the `#catalog` hash redirect (`courses/page.tsx:28-50`, `LmsShell.tsx:59-67, 135-137`, `lib/lms/shellKind.ts:33-36, 68-71`). Triage "Better idea 3" | | |
| P8 | **A third navigation for lesson courses**: the УРОКИ sidebar group lists lesson courses of the current exam with progress rings and «Все уроки» (`StudentShell.tsx:91-136`, `courses/[courseId]/lessons/page.tsx`) | | |
| P9 | **Exam-shell special cases in the layout**: `isExamShellCourse`, the `ownTitle` route list, `examPage` reading column (`layout.tsx:130-146`), `breadcrumbs={false}` on `StudentCourseHeader` — every new student page must be added to a list | | |

**What stays (unchanged, reused):** the palette "Sky and teal" and `.student-theme` tokens (`STUDENT_UI_DESIGN.md` §1.1);
`StudentShell` primitives (`SidebarNav`, `TabBar`, `Sheet`, `GoldPill`, `StudentPageHeader`, `Mascot`, `Countdown`,
`Meter`, `SectionTag`); the frame decision and performance work (`shellKind.ts` rules, per-page latch and neutral frame
in `LmsShell.tsx`, `meCache`, `swr.ts`, `GET /me/bootstrap?include=home`, hover prefetch in `pageData.ts`, split
dictionaries); Student view (test-student session, `StudentViewBanner`, `X-View-As` is not used: the test student is a
real user); Pro rules (`SUBSCRIPTION_DESIGN.md` §12: module-level Pro, paid tests, `ProCallout`, `ProChip`, never for
staff/test students); the full-screen player (`PLAYER_FRAME`, `isPlayerRoute`) and the fixed ORT rules (section order,
timers, forward-only, scoring, CSV/zip import); the result page (`ExamResultHero`, `SectionBreakdown`, review);
`TestsPage`/`TestLibrary`, `NextCard`, `GoalStrip`, `StreakCard`, `StudentSyllabus`, `LessonView`, `AnalyticsOverview`,
`SavedPage`, `CourseCard`, `CatalogView`, `CourseLanding`. The teacher, organization and platform frames (`AppHeader`,
`CourseSidebar` for staff) are untouched.

## 2. Information architecture

Principle: **the global navigation is about the person; the course page is about the course.** No global item carries
a course id. Every course, ORT included, opens on one course page pattern (§3). The exam switcher disappears.

### 2.1 Global navigation (people who learn; test students in Student view)

| Item | ru / ky / en | URL | Content |
|---|---|---|---|
| Главная | Главная / Башкы бет / Home | `/{lang}/home` (new) | "What next": greeting, the next step across courses (the newest exam course's `NextCard`), streak, «Продолжить» strip (`modules_next`), course cards (up to 4, «Все курсы»), «К выполнению», «От платформы» join cards, getting-started checklist |
| Мои курсы | Мои курсы / Менин курстарым / My courses | `/{lang}/courses` | Every active student course as `CourseCard` (cover, progress, next due, Pro mark): exam courses first, then lesson courses grouped under their exam («К экзамену: ОРТ (рус)»), then other courses. Quiet links: «Войти по коду», «Каталог» |
| Каталог | Каталог / Каталог / Catalog | `/{lang}/courses/catalog` | unchanged (`CatalogView`, landings) |
| Сохранённые | Сохранённые / Сакталгандар / Saved | `/{lang}/saved` (new) | course picker chips (every course with tests; default: the course last opened) + today's `SavedPage` (tabs Сохранённые · Ошибки) for that course. `?course={id}` deep link |
| Аналитика | Аналитика / Аналитика / Analytics | `/{lang}/analytics` (new) | v1: course picker + today's `AnalyticsOverview` for that course. v2 (owner decision D2): a summary card per exam course (last / target score, trend, weak sections, open mistakes) above the picker, from `GET /me/analytics` |
| Pro | Открыть все экзамены / «Pro до …» | `/{lang}/pro` | gold pill at the bottom of the sidebar and in «Ещё»; account menu row stays (`access.pro.menu`) |
| Account | — | sheet | name, language, Конфиденциальность, Установить приложение, Выйти (as today) |

`/{lang}/courses` is therefore "my courses **in the area the person is in**": the Teaching list for people who teach
(unchanged, `courses/page.tsx` `TeachingList`), the student list for learners. The student *home* gets its own URL
(triage Better idea 3), so `?view=`, `ViewSync`, `ViewParam`, `coursesDefault` and the `#catalog` redirect go.

**Redirects (frontend, in the old route's `page.tsx`, query kept):**

| Old | New |
|---|---|
| `/courses?view=learning`, `/courses?view=teaching` | `/courses` (the area is the person's; for a learner the Learning home is `/home`, so `?view=learning` → `/home`) |
| `/courses#catalog` | `/courses/catalog` (kept) |
| `/courses/{c}/tests` | `/courses/{c}/tests` (kept: it is the Тесты tab of every course now) |
| `/courses/{c}/assignments` (students) | `/courses/{c}/tests` (staff keep `/assignments`) |
| `/courses/{c}/modules` (students) | `/courses/{c}/lessons` (staff keep their redirect to the course page) |
| `/courses/{c}/lessons` («Все уроки») | `/courses/{c}/lessons` (same URL: the Lessons tab also lists the exam's lesson courses) |
| `/courses/{c}/saved`, `/courses/{c}/progress?tab=mistakes` | `/saved?course={c}` (`&tab=mistakes` kept) |
| `/courses/{c}/progress` | `/courses/{c}/progress` (kept: the Прогресс tab); the global page is `/analytics?course={c}` |
| `/courses/{c}/practice` | `/courses/{c}/tests#practice` (practice sets are a section of the Тесты tab) |
| `/courses/{c}/people` (students) | `/courses/{c}` («О курсе» card lists the teachers; the page stays reachable for observers) |
| `/courses/{c}/announcements` | kept (object page inside the course frame, reached from the Overview strip) |
| `/courses/{c}/files` (students) | kept (object page; reached from the Overview «Материалы» card when `features.files`) |
| `/courses/{c}/modules/{m}/items/{i}`, `/pages/{id}`, `/assessments/{a}`, `/attempts/{id}`, `/attempts/{id}/result` | kept (object pages, §3.5) |
| `/unlock` | kept (`/pro` links to it) |

**What disappears, with reasons.** The exam switcher and the "current course" (`ort_student_course` in
`localStorage`, `useStudentShellData.current/setCurrent/lessonCourseExam/features`): with per-course pages a global
"current exam" has no meaning; the course picker on Saved/Analytics replaces it where a choice is still needed.
Per-course global links (`studentNavLinks` tests/lessons/practice/analytics/saved): they become course tabs. The
УРОКИ group and «Все уроки»: lesson courses are rows in the exam's Lessons tab and cards in My courses. `CourseSidebar`
for students (staff keep it). `StudentCourseHeader` with breadcrumbs: the course frame header replaces it. The four
student course homes: one Overview. `ToTests`. `isExamShellCourse` and the `ownTitle` list in the layout. The
`?tab=` reading in `LmsShell` (only the switcher used it).

### 2.2 Frame rules (`shellKind.ts`)

`areaFromUrl`: `/home`, `/saved`, `/analytics` are Learning. `/courses` is `homeArea(me)` for people who teach, Learning
for learners (the `coursesDefault` parameter goes; `urlAreaFor` already maps unclaimed URLs to the person's home area,
so `/home` for a teacher opens the Teaching list through the existing redirect rule, never a student frame). `isPlayerRoute`
unchanged. `roleLinks.check.ts` gets the three URLs in its fixed table.

## 3. One course page pattern (students of every course; Student view)

### 3.1 Header
```
┌ cover strip (16:9 crop to 160 px desktop / 120 px phone; CourseCover default) ─────────────────────┐
│ ОРТ (на русском)                                 [exam courses: 30 дн · 07 ч · 59 мин  до экзамена ✎] │
│ Платформа · Русский · 1 тест · 1 урок            [Последний балл 132 · Цель 200 ✎]                   │
│ Пройдено 3 из 5 ▮▮▮▯▯ 60 %                                                                           │
├ Обзор · Уроки · Тесты · Оценки · Прогресс ──────────────────────────────────────────────── (tabs) ──┤
│ ★ Pro bar (only when this tab holds locked content)                                                 │
```
- Title `<h1>` on every tab; meta line: provider (`courses.home.providerPlatform` or owner name), language, counts
  (`tests_count`, `lessons_count` from `CourseOut`; the home card already shows them).
- Progress bar: `ModulesStudentOut.progress` when the course has modules (lessons + tests placed in modules), else
  tests passed / published tests (`exam-prep` `library_total` and done count for exam courses; assignments list for
  others). One number, the same as the My courses card.
- **Exam courses only** (`templateUi(course).studentLayout === "exam_prep"`): the countdown tiles (`Countdown`, exam
  date from the course, "Сегодня" on the day; nothing without a date) and the goal strip (`GoalStrip`: last scaled
  score, target, edit). This block is the only template-specific part of the pattern.
- The header is **full** on Overview and **compact** (title line + tabs, no cover, no bars) on the other tabs and on
  object pages, so lists start high on a phone. The compact title is a link to Overview.
- «Покинуть курс» is a quiet link at the end of Overview (as today), never in the header.

### 3.2 Tabs (`<nav aria-label="Разделы курса">` of links, `aria-current="page"`; horizontal scroll on phones)

| Key | ru / ky / en | URL | Shown when | Content |
|---|---|---|---|---|
| overview | Обзор / Жалпы маалымат / Overview | `/courses/{c}` | always | §3.3 |
| lessons | Уроки / Сабактар / Lessons | `/courses/{c}/lessons` | `features.modules` (exam courses: a lesson exists; general: a published module) **or** the exam has attached lesson courses (`lesson_courses` non-empty) | today's `StudentSyllabus` (banner block removed: the header has it; «Продолжить» stays as the first row's CTA), then «Курсы с уроками к экзамену» cards (`LessonCourses`) for exam courses |
| tests | Тесты / Тесттер / Tests, **or** Задания / Тапшырмалар / Assignments when the course has a published non-quiz assignment (`features.hand_ins`, glossary of `UX_GUIDELINES.md` §5) | `/courses/{c}/tests` | `features.tests` (a published, live assessment or assignment) | exam courses: today's `TestsPage` (`TestLibrary`, status chips, source chips); other courses: the student assignments list restyled as the same card grid (`StudentAssignmentCard` → `TestLibrary` card shape, percent instead of a scaled score; hand-ins keep their kind badge). Section «Тренировки» (`#practice`) below when `features.practice`: today's practice list |
| grades | Оценки / Баалар / Grades | `/courses/{c}/grades` | not an exam course, or the course has a non-quiz assignment (`features.hand_ins`) | today's `StudentGrades` |
| progress | Прогресс / Жетишкендик / Progress | `/courses/{c}/progress` | `features.tests` or `features.modules` | today's `AnalyticsOverview` (sections, topics, activity, heatmap) with `examPrep` for exam courses; for courses with modules a «Уроки» block (done / total, per module) above it; the mistakes link goes to `/saved?course={c}&tab=mistakes` |

Empty-tab rules: a tab is hidden until its feature flag is true (server EXISTS, `course_features`); a hidden tab opened
by URL shows `AreaUnavailable` ("Пока недоступно … Назад к курсу") inside the frame, as today for announcements/files.
A shown tab whose list is empty shows the existing empty states. Overview is never hidden. An exam course with only tests
shows Обзор · Тесты · Прогресс (three tabs). A new teacher course with nothing published shows Обзор only.

### 3.3 Overview (`/courses/{c}`)
Order (desktop two columns 1fr + 320 px; phone one column):
1. **Следующий шаг** card: exam courses: today's `NextCard` (start / resume / retake / practice, the page's one primary
   button); other courses: the next item from `modules_next` / the first open assignment (today's `StudentCourseHome`
   "next" logic). Not shown when nothing is open.
2. **Последний результат** (exam: scaled score + five section bars of the latest result, `SectionBars`; other: the
   latest released grade) with «Все результаты» → Прогресс.
3. **Объявления** strip: the latest published announcement (title, date, two lines) + «Все объявления» →
   `/announcements`; only when `features.announcements`.
4. **Уроки** teaser: «Продолжить урок» row (`modules_next` of this course) + «Все уроки» → Lessons tab; only with lessons.
5. Side column **О курсе**: description, provider, teachers (from `GET /courses/{c}/people`, names only; replaces the
   People tab for students), language, counts (modules, lessons, tests), «Материалы» link to `/files` when
   `features.files`, mascot. Exam courses add «Курсы с уроками к экзамену» (up to 3 cards + «Все» → Lessons tab).
6. Gold **unlock card** (`UnlockCard`) when `needs_pass` (exam courses) or a locked module exists (others); «Покинуть курс».

### 3.4 Object mapping

| Object today | Where it lives in the pattern |
|---|---|
| Modules and items (page / file / url / header) | Lessons tab (`StudentSyllabus`), lesson page (§3.5) |
| Quiz assignments, `ort_main` exams | Тесты tab cards → lobby; also rows inside modules on the Lessons tab (L7, never twice in the syllabus) |
| Text / file / offline assignments | Тесты tab (label becomes Задания) → assignment page `/assignments/{id}` (object page) |
| Practice sets | Тесты tab, section «Тренировки» (`#practice`) |
| Announcements | Overview strip → `/announcements` list (object page) |
| Course files outside modules | Overview «Материалы» → `/files` (object page) |
| Teachers | Overview «О курсе» |
| Grades | Оценки tab (rule above) |
| Saved questions, mistakes | global `/saved?course={c}`; link from Прогресс and from the result page |
| Exam date, target score, latest scaled score | header of exam courses |
| Lesson courses attached to an exam | Lessons tab of the exam + My courses; each is a normal course in the same pattern whose Overview says «К экзамену: ОРТ (рус)» (`exam_course_id`) |

### 3.5 Object pages inside the pattern
Lesson page `/courses/{c}/modules/{m}/items/{i}`, page `/pages/{id}`, assignment `/assignments/{id}`, lobby
`/assessments/{a}`, result and review `/attempts/{id}/result`, announcements list, files list: **compact header**
(title link + tabs with the parent tab active: Уроки for lessons and pages, Тесты for lobby/result/assignment, Обзор
for announcements/files), then the object. The lesson page keeps its outline aside (desktop) / collapsible (phone) and
sticky pager (`COURSE_LESSONS_DESIGN.md` §7.2). Lobby, result and review keep the 880 px reading column inside the
frame (today's `examPage` column moves from the layout's exam branch to the object-page rule). The **player**
`/attempts/{id}` keeps `PLAYER_FRAME`: no chrome at all; its `?return=` leads back to the lobby. Deep links (`#item-{n}`
on the review, `#m-{id}` on the syllabus, `#practice`) keep working.

Pro lock bar: `ProCallout variant="course"` directly under the tabs on Уроки (a locked module exists) and Тесты (a paid
test exists and no pass), on the lobby of a paid test, and on a locked lesson page (the `ProLockCard` replaces the
content). Never on Overview twice: the unlock card is the Overview's version.

### 3.6 ORT as a normal course
ORT (ru / ky) opens on Overview: countdown + goal in the header, Следующий шаг, latest result with section bars,
lesson courses. Tabs: Обзор · Уроки (when a lesson or a lesson course exists) · Тесты · Прогресс (section and topic
analytics, activity). No Оценки tab (scores are on the test cards and on Прогресс; D3). The exam-prep pages become:
`ExamPrepHome` → split into the global home (greeting, next step across courses, streak, courses) and the ORT Overview
(countdown, goal, sections, lesson courses, unlock card); `TestsPage` → the Тесты tab unchanged; `/progress` → the
Прогресс tab unchanged; `/saved` → global Saved with the course picker. Nothing in `attempts/`, `grading/`, `ort/`,
`content/importers/` changes; the player, section order, timers, forward-only sections and scoring are untouched. ORT
student screenshot baselines (`lobby`, `result`, `review` × phone/desktop × ru/ky) are re-approved deliberately for the
compact header; the five player screens, `review-page`, `section-end`, `submit`, `passage`, `comparison`,
`flagged-palette` and every `teacher-*` image must still match pixel-for-pixel.

## 4. Layouts (ru; 1440 and 375; 1920 = 1440 with wider gutters, content max 1200 px)

Global frame: desktop 264 px teal sidebar (unchanged look), phone 56 px top bar (brand, page title, avatar) + 64 px
bottom bar **Главная · Курсы · Аналитика · Сохранённые · Ещё** («Ещё»: Каталог, Pro pill, Начало работы, Установить,
Другие разделы, account). The bar is the same on every page, inside courses too.

### 4.1 Home `/home`
```
1440                                                            375
┌ sidebar ┬────────────────────────────────────────────────┐   ┌──────────────────────┐
│ Главная │ [🐆] Добрый вечер, Тоха         До ОРТ 30 дней │   │ ▣  Главная        (T)│
│ Мои     │ СЛЕДУЮЩИЙ ШАГ  Пробный тест 2 · ОРТ (рус)      │   │ [🐆] Добрый вечер     │
│  курсы  │                              [Начать тест →]   │   │ До ОРТ 30 дней        │
│ Каталог │ Продолжить: ▶ watch · ОРТ (рус) · 1st quarter  │   │ СЛЕДУЮЩИЙ ШАГ         │
│ Сохран. │ Серия 3 дня 🔥  пт сб вс пн вт ср чт           │   │ [Начать тест →]       │
│ Аналит. │ Мои курсы                          Все курсы → │   │ Продолжить ▶ …        │
│         │ [ОРТ рус ▮▮▯ 60 %] [ОРТ кырг] [цоомо ▮▮▮▯]     │   │ Серия 3 дня 🔥        │
│ ◔ Начало│ К выполнению        │ От платформы (join cards)│   │ Мои курсы  (1 col)    │
│ ★ Pro   │ ○ все тесты · до 23 февр.                      │   │ К выполнению          │
│ (T) Тоха│                                                │   │ От платформы          │
└─────────┴────────────────────────────────────────────────┘   │ ⌂  ▤  ▥  ⚑  ⋯        │ tab bar
                                                               └──────────────────────┘
```
Sources: `GET /me/bootstrap?include=home` (unchanged: home, exam_prep of the newest exam course, 7-day activity).

### 4.2 My courses `/courses`
```
┌ Мои курсы                         [Войти по коду] [Каталог] ┐   375: title, two quiet links, one column of cards
│ ЭКЗАМЕНЫ   [ОРТ (рус) · 1 тест · 1 урок · 60 %] [ОРТ (кырг)]│
│ К ЭКЗАМЕНУ ОРТ (РУС)  [Математика с Альбертом ◔ 3/5]        │
│ ДРУГИЕ КУРСЫ  [основной орт тест цоомо ▮▮▮▯ 60 %]           │
└──────────────────────────────────────────────────────────────┘
```
Source: `GET /me/home/courses` (paginated; `student_layout`, `exam_course_id`, counts, progress, cover already there).

### 4.3 A lesson course (teacher's or platform masterclass), Overview
```
1440                                                              375
┌ sidebar ┬ cover strip ──────────────────────────────────────┐  ┌ cover strip ─────────┐
│         │ основной орт тест цоомо                           │  │ основной орт тест …  │
│         │ Альберт · Русский · 2 теста · 3 урока             │  │ Пройдено 3 из 5 60 % │
│         │ Пройдено 3 из 5 ▮▮▮▯▯ 60 %                        │  │ Обзор Уроки Задания ›│
│         │ Обзор · Уроки · Задания · Оценки · Прогресс       │  ├──────────────────────┤
│         ├───────────────────────────────┬───────────────────┤  │ СЛЕДУЮЩИЙ ШАГ        │
│         │ СЛЕДУЮЩИЙ ШАГ  все тесты      │ О курсе           │  │ все тесты · до 23.02 │
│         │ до 23 февр.       [Начать →]  │ все тесты основ…  │  │ [Начать →]           │
│         │ Продолжить урок ▶ купить бы…  │ Преподаватели:    │  │ Продолжить урок ▶ …  │
│         │ Последний результат  7 / 10   │ Альберт           │  │ Последний результат  │
│         │ Объявления: «…»  Все →        │ Материалы (2) →   │  │ О курсе (compact)    │
│         │ Покинуть курс                 │ [mascot]          │  │ Покинуть курс        │
└─────────┴───────────────────────────────┴───────────────────┘  │ ⌂  ▤  ▥  ⚑  ⋯        │
```

### 4.4 ORT course: Overview, Тесты, Прогресс
```
Overview 1440                                                   375
┌ cover strip ──────────────────────────────────────────────┐  ┌ cover strip ─────────┐
│ ОРТ (на русском)        [30 дн][07 ч][59 мин] до экзамена ✎│  │ ОРТ (на русском)     │
│ Платформа · Русский · 1 тест · 1 урок                      │  │ 30 дн 07 ч 59 мин ✎  │
│ Последний балл 132 · Цель 200 ✎   Пройдено 0 из 1 ▯▯▯ 0 %  │  │ 132 → 200  ▯▯▯ 0 %   │
│ Обзор · Уроки · Тесты · Прогресс                           │  │ Обзор Уроки Тесты Пр›│
├────────────────────────────────┬───────────────────────────┤  ├──────────────────────┤
│ СЛЕДУЮЩИЙ ШАГ  asa  [Начать →] │ О курсе · Платформа       │  │ СЛЕДУЮЩИЙ ШАГ        │
│ Последний результат            │ Подготовка к ОРТ …        │  │ [Начать тест →]      │
│  math_1 ▮▮▮▯ 12/30 · math_2 …  │ Курсы с уроками к экзамену│  │ Разделы (5 bars)     │
│ Продолжить урок ▶ watch        │  [Математика с Альбертом] │  │ Продолжить урок      │
│ ★ Откройте все экзамены (gold) │ [mascot]                  │  │ ★ Откройте все …     │
└────────────────────────────────┴───────────────────────────┘  └──────────────────────┘
Тесты (compact header)                                          Прогресс (compact header)
┌ ОРТ (на русском) › Обзор · Уроки · [Тесты] · Прогресс ─────┐  ┌ … · [Прогресс]  [30 дней ▾] ┐
│ ★ Платные тесты открываются с Pro  [Открыть доступ]        │  │ [Вопросов 240][Точность 64 %]│
│ Тесты · 12   [Все] [Не начат] [В процессе] [Пройден]       │  │ 5 слабых тем … → Практика    │
│ [card][card][card]  (TestLibrary, unchanged)               │  │ Активность bars · по разделам│
│ Тренировки #practice  [Математика I · 20 вопросов] …       │  │ Ошибки 5 → Сохранённые       │
└────────────────────────────────────────────────────────────┘  └──────────────────────────────┘
```

### 4.5 Lesson page (object page inside the pattern)
```
1440                                                                 375
┌ sidebar ┬ ОРТ (на русском) › Обзор · [Уроки] · Тесты · Прогресс ─┐ ┌ ‹ Уроки · ОРТ (рус)     │
│         │ ‹ Программа · 1st quarter · 1/1                        │ │ watch  ▶ 6 мин          │
│         │ watch  ▶ 6 мин                 │ Программа курса       │ │ ┌ ▶ click-to-load ─────┐│
│         │ ┌ navy card ▶ click-to-load ──┐│ ▾ 1 1st quarter 0/1   │ │ └──────────────────────┘│
│         │ └─────────────────────────────┘│   ● watch             │ │ ▸ Программа курса (0/1) │
│         │ [Отметить как пройденный]      │ ▸ 2 … 🔒 Pro          │ ├─────────────────────────┤
│         │ ← Назад        Следующий урок →│ (sticky)              │ │ ← Назад  [Следующий →]  │ sticky
└─────────┴────────────────────────────────┴───────────────────────┘ └─────────────────────────┘
```

### 4.6 Saved, Analytics, catalog entry
```
Saved /saved?course=…                                  Analytics /analytics?course=… (v1)
┌ Сохранённые   [ОРТ (рус)] [ОРТ (кырг)] [цоомо]     ┐ ┌ Аналитика  [ОРТ (рус)] [ОРТ (кырг)]  [30 дней ▾] ┐
│ Сохранённые · Ошибки (tabs of SavedPage, unchanged)│ │ (v2: summary cards per exam above the picker)    │
│ math_1 · asa · 12.11 · «Сравните …»     Открыть →  │ │ AnalyticsOverview of the picked course           │
└────────────────────────────────────────────────────┘ └──────────────────────────────────────────────────┘
Catalog entry /courses/catalog/{id}: CourseLanding unchanged; «Записаться» → the course Overview (not /tests).
375: the picker chips scroll horizontally under the title; the rest stacks.
```

## 5. Staff side

- **Student view must show exactly this interface.** It already does by construction: `enterStudentView` signs the tab
  in as the course's test student (a real user with `learnsHere` true), so the student frame, `/home`, My courses (one
  course) and the course pattern render for it. Changes: Student view opens the course **Overview** (today it reloads
  "the course page", which redirected ORT to `/tests`); the test student's global nav hides Каталог, Pro and
  «Войти по коду» (the `testStudent` flag already hides the pill and install); the banner (`StudentViewBanner`) stays
  sticky above the course frame and scrolls away on object pages with their own sticky parts (unchanged rule).
- Teachers' links into Student view stay where they are: `StaffCourseBar` button on the course page
  (`layout.tsx:149`) and `CourseLanding` for a teacher opening a catalog entry. The teacher interface
  (`AppHeader`, `CourseSidebar`, `TeacherCoursePage`, settings) does not change in this step; `features.tests` and
  `features.hand_ins` appear in the staff serializer too but no staff screen reads them.
- Org admins and platform admins reading a course (`read_only` observers) keep today's app-frame read-only view.

## 6. Data, API, performance, i18n, accessibility

**Backend (small, additive, no migration):**
1. `courses/service.course_features`: two more EXISTS, `tests` (published live assessment or quiz assignment visible
   to students; same predicate as `exam_prep._visible_test` for exam courses, `assignments` list for others) and
   `hand_ins` (published non-quiz assignment). `CourseOut.features` and `HomeCourseOut.features` carry them (the
   home's `_exam_features` becomes `_features` for every course; G5 of `TEACHER_TO_STUDENT_MAP.md` is then closed for
   good). Test: `tests/lms/test_course_features.py` over every kind.
2. (v2, decision D2) `GET /me/analytics`: one row per exam course the caller studies (`course_id`, `title`,
   `latest`, `goal`, `history` (last 10), `sections`, `open_mistakes`), built from `exam_prep_svc.page()` per course;
   policy `authenticated`, enrolled courses only; listed in `route_inventory.py`. ≤ 3 courses in practice; paginate at
   20. (v2) `GET /me/saved?course=&cursor=`: the per-course saved query over the caller's enrollments.
3. Nothing in `attempts/`, `grading/`, `ort/`, `content/importers/`, `access/`, `modules/`, `exam_prep/` changes.

**Reused endpoints:** `GET /me/bootstrap?include=home`, `GET /me/home`, `GET /me/home/courses`, `GET /courses/{c}`,
`GET /courses/{c}/exam-prep` + `/library`, `GET /courses/{c}/modules` (student), `GET /courses/{c}/assignments`,
`GET /courses/{c}/grades/mine`, `GET /courses/{c}/my/progress|activity|saved|mistakes`, `PUT …/my/goal`,
`GET /courses/{c}/lesson-courses`, `GET /courses/{c}/practice`, `GET /courses/{c}/announcements`, `GET /courses/{c}/people`.

**Performance:** the course frame needs `GET /courses/{c}` (SWR, 60 s, session) and the tab's one read; Overview of an
exam course = `exam-prep` (cached by `pageData.ts`) + `modules` when lessons exist; the header's progress comes from
the same answers. Tab links prefetch on hover/focus/touch through `pageData.ts` (`prefetchExamPrep`,
`prefetchAnalytics`, new `prefetchModules`). The shell no longer asks for a "current course" (`useStudentShellData`
shrinks to `courses`, `access`, `forget`), so no page waits for the course list. Home stays one round. Phone: the compact
header on tabs keeps lists above the fold.

**Frontend pieces (names for the slices):** `components/lms/course/CourseFrame.tsx` (header, tabs, Pro bar; props
`course`, `variant: "full" | "compact"`, `activeTab`), `lib/lms/courseTabs.ts` (dependency-free: `courseTabs(course,
pathname, t)` → list + active + label rule; `courseTabs.check.ts` like `nav.check.ts`), `course/CourseOverview.tsx`,
`course/ExamHeaderBlock.tsx` (countdown + goal), `app/[lang]/home/page.tsx`, `app/[lang]/saved/page.tsx`,
`app/[lang]/analytics/page.tsx`, `components/lms/student/CoursePicker.tsx`, `lib/lms/studentNav.ts` (global links only),
`StudentShell.tsx` (no switcher, no exam sheet; «Ещё» content), `courses/page.tsx` (`MyCourses` for learners),
`courses/[courseId]/layout.tsx` (student branch = `CourseFrame`; staff branch unchanged).

**i18n plan (en, ky, ru; parity script):** new `student.nav.courses`, `course.tabs.{overview,lessons,tests,assignments,
grades,progress}`, `course.tabs.label`, `course.header.{progress,examIn,target,lastScore,provider,counts}`,
`course.overview.{nextStep,latestResult,allResults,announcements,allAnnouncements,continueLesson,allLessons,about,
teachers,materials,lessonCourses,forExam}`, `course.tests.practiceSection`, `saved.global.{title,picker,all}`,
`analytics.global.{title,picker,summaryTitle,weakSections,openMistakes}`, `courses.mine.{title,exams,forExam,other,
join,catalog}`. Removed after the last slice: `student.switcher.*`, `student.nav.{lessonsGroup,practiceGroup,allLessons,
mistakes,tests,lessons,practice}`, `home.prep.{otherCourses,addCourse,lessonCourses.subtitle}`,
`student.lessonCourses.*`, `courses.home.tab`, `courseNav.menu` stays (staff drawer).

**Accessibility:** one `<h1>` per page (course title); tabs are links in a `<nav>` with `aria-current`, 44 px targets,
visible focus, scrollable on phones without clipping the focused tab; the countdown is not `aria-live`; cover images are
decorative (`alt=""`); the Pro bar is a `role="note"`; the course picker is a `role="group"` of `aria-pressed` chips
(today's switcher markup, reused); every tab's loading, empty and error states exist (`UX_GUIDELINES.md` §5).

## 7. Migration plan (slices; each deploys alone and leaves both interfaces working)

The switch is route-by-route, no runtime flag: new pages are added first, the course frame replaces the student branch
of the layout in one slice (the old frame is not kept behind a flag: both branches cannot coexist on one URL), then the
global navigation is rewired, then the old pieces are deleted. Every slice: `tsc`, parity script, SQLite suite, the
e2e specs named, screenshots at 375 / 1440 / 1920 in ru checked by the orchestrator.

| # | Slice (model) | Content | Tests | Deployable alone because |
|---|---|---|---|---|
| S1 | Routes and features (Opus) | backend `features.tests/hand_ins` (+ home `_features` for every course); `/home`, `/saved`, `/analytics` pages (picker + existing components); `/courses` = My courses for learners; `shellKind.ts` rules; redirects for `?view=`; sidebar gains Главная/Мои курсы/Сохранённые/Аналитика as global items while the per-course links and the switcher still work | `roleLinks.check.ts` table, `shellKind.check.ts`, `role-links.spec.ts`, `student-home.spec.ts`, new `student-ia.spec.ts` (home, my courses, saved picker, analytics picker, redirects) | adds pages; nothing removed |
| S2 | Course frame for every student course (Opus) | `CourseFrame`, `courseTabs.ts`, `CourseOverview`, `ExamHeaderBlock`; the layout's student branches (exam and general) become one; `/lessons` tab, `/tests` for general courses (assignments as cards, label rule), Оценки/Прогресс rules, object-page compact header, redirects (`/modules`, `/assignments`, `/practice`, `/people`, `/courses/{c}/saved`, `/progress?tab=mistakes`); Student view opens Overview | `course-nav.spec.ts` (student parts rewritten: no `CourseSidebar`, tabs, hidden-tab page), `lessons.spec.ts`, `modules.spec.ts`, `exam-prep.spec.ts`, `teacher-to-student.spec.ts`, `student-result.spec.ts`, `practice.spec.ts`, `pro-courses.spec.ts`; **ORT**: `ort.spec.ts`, `ort-visual.spec.ts` DOM assertions green; lobby/result/review baselines re-recorded deliberately (before/after pairs in `STUDENT_IA_screens/ort/`, note in `ORT_BASELINE/README.md`); player, section-end, submit, passage, comparison, flagged-palette, review-page and `teacher-*` zero diff; backend `test_ort_parity.py`, `test_ort_e2e_api.py`, `test_ort_import_golden.py`, `test_grading_scoring.py` unchanged | the global sidebar still works (its links land on tabs); old URLs redirect |
| S3 | Global navigation rewrite (Opus) | `StudentShell` without the switcher, exam sheet, УРОКИ group and per-course links; tab bar Главная · Курсы · Аналитика · Сохранённые · Ещё; `useStudentShellData` reduced; home = global home (greeting, next step, streak, cards, К выполнению, От платформы); ORT Overview takes countdown/goal/sections/lesson courses/unlock | `student-shell.spec.ts` rewritten (one nav, no second sidebar on any course page, phone bar on every page), `mobile-sheets.spec.ts`, `student-links.spec.ts`, `header-areas.spec.ts`, `shell-stable.spec.ts`, `perf-waterfall.spec.ts` (home still one round) | S2 already made every course self-navigating |
| S4 | Cleanup (Opus; `grep -rl` before each deletion) | delete `ToTests`, `isExamShellCourse` uses in the layout, `StudentCourseHome`, `StudentCourseHeader` for students, student `CourseSidebar` path, `lessons/page.tsx` old body, `ExamSwitcher`, `ExamSheetBody`, `lessonCourseLinks`, `ViewSync`/`ViewParam`/`coursesDefault`, `?tab=` in `LmsShell`; i18n keys of §6; docs (`STUDENT_UI_DESIGN.md` §2 pointer, `HANDOFF_NEXT_AGENT.md`, `PRODUCT_DECISIONS.md`) | full SQLite suite, `tsc`, parity, `nav.check.ts`, all e2e | removals only |
| S5 | Analytics summary and global Saved (Opus; D2 yes) | `GET /me/analytics`, `GET /me/saved`; summary cards; «Все» chip on Saved | `tests/lms/test_me_analytics.py`, `test_me_saved.py`, `test_pg_concurrency` untouched, `student-analytics.spec.ts`, `student-saved.spec.ts` | additive endpoint |
| S6 | Text and polish (Sonnet) | ky/en strings, spacing at 375/1440/1920, empty states, `STUDENT_IA_screens/after/` | parity script, screenshot pass | styling only |

**Rollback:** every slice is one merge commit; S1 and S5 are additive (revert the commit; the two columns in
`features` are computed, not stored); S2/S3 revert restores the previous frame because no data changed and every old
URL still exists. No migration, so no Neon backup is needed for this step (the backup rule applies only if S5 adds
tables, which it does not).

## 8. Decisions for the owner, and better ideas

| # | Decision | Recommendation |
|---|---|---|
| D1 | Home URL: `/home` (new) with `/courses` = My courses, or keep the home on `/courses` and add `/courses/all` | **`/home`**: the home is not a list; `/courses` then means the same for teachers and students; `?view=` goes (Better idea 3) |
| D2 | Global Аналитика: picker-only (v1, no backend) or a cross-exam summary (`GET /me/analytics`, S5) | **Build v1 in S1, v2 in S5**: the summary gives the global page its own purpose (per exam: last / target, trend, weak sections) instead of duplicating the course tab |
| D3 | Оценки tab on exam courses | **Hidden**: scaled scores live on the test cards and Прогресс; a gradebook of ORT attempts adds nothing. Shown automatically if a hand-in assignment is ever added |
| D4 | Tab label Тесты vs Задания | **By content** (glossary rule): Тесты when every published assignment is a quiz/exam, Задания otherwise; URL `/tests` always |
| D5 | Lesson courses attached to an exam | **Stay separate courses** (same pattern, listed on the exam's Lessons tab and in My courses). Merging them into the exam course as modules is a data move for later, if ever |
| D6 | Practice sets | **A section of the Тесты tab** (`#practice`), not a tab: fewer tabs, and practice is "tests without a score" |
| D7 | Lobby, result and review | **Inside the course frame with the compact header** (orientation on a phone, one pattern); the player stays chrome-less. The alternative (bare reading column, as today) keeps the current baselines but leaves one more special case |
| D8 | Phone tab bar | **Главная · Курсы · Аналитика · Сохранённые · Ещё** (Каталог and Pro in «Ещё»); the alternative with Каталог in the bar fits new students better but drops Аналитика or Сохранённые |
| D9 | Countdown on the global home | **One line in the hero** («До ОРТ 30 дней») for the newest exam course; tiles only on the ORT Overview |
| D10 | Teachers (names) on the Overview instead of a People tab | **Yes** (students rarely need the page; observers keep `/people`) |

**Better ideas (beyond the brief):**
1. **Tab visibility from `course_features` only, no template branches in the layout.** The course template then adds
   just the exam header block and the scoring display; "ORT as a normal course" is true in code, not only on screen
   (`isExamShellCourse` and the `ownTitle` list go). S2 does this.
2. **One test library for every course (later).** A per-course `GET /courses/{c}/tests` for general courses built on
   `exam_prep.library` (status, best score, questions, duration) would give teacher courses the same cards and status
   chips as ORT; S2 reuses the assignments list to keep the step small.
3. **Getting started per student, not per exam course**: goal set, first test, first lesson, app installed; it lives on
   `/home` and the «Ещё» sheet, and the sidebar pill no longer depends on a "current course".
4. **The `CourseCard` progress and the course header show the same number** (one helper `courseProgress(course)`),
   so the list and the course never disagree.
5. **Catalog «Записаться» lands on the Overview** with the «Следующий шаг» card, never on a list.
6. **Not recommended**: a persistent "current exam" anywhere in the global frame (it is what made every page
   ambiguous), and tabs as client-side state (`?tab=`): tabs are URLs so deep links, prefetch and the per-role link
   check keep working.
