# Teacher course → student view: map, structure design, e2e, slices (owner item 3, 2026-11-08)

**Status**: design (architect on Fable), 2026-11-08. Source: `STAFF_FEEDBACK_2026-11-08.md` item 3. Base: `lms`
2a85616, alembic head `0026_course_cover`. Builds on `STUDENT_UI_DESIGN.md` §2–3, `STUDENT_UI_FIX_PLAN.md` §2.1 and
§11, `COURSE_LESSONS_DESIGN.md` L1–L10. The reference product is "the reference app" (never named; repo is public).
**Rules**: improve the existing architecture; ORT behaviour, player, scoring, imports untouched (`AGENTS.md` §6.9);
every string in `en.json`, `ky.json`, `ru.json`; authorization from the DB.

Vocabulary: **exam course** = a course whose template has `student_layout = "exam_prep"` (`templates/ort.py`: ORT ru,
ORT ky; later olympiads, НЦТ). **Lesson course** ("masterclass") = a general course (`template_key IS NULL`) of the
platform organization attached to one exam course (§2). **Exam shell** = `StudentShell` with the exam sidebar.

## 1. Map: where each teacher action lands for the student

Student entry points today: sidebar `StudentShell.tsx` (links from `lib/lms/studentNav.ts`; items from
`HomeCourseOut.features`), home `/courses` (`home/StudentHome.tsx` → `home/ExamPrepHome.tsx` + `SideLists`), Тесты
`/courses/{c}/tests` (`examPrep/TestsPage.tsx`, data `GET /courses/{c}/exam-prep` + `/library`,
`exam_prep/service.py`), overview + syllabus `/courses/{c}/modules` (`modules/StudentSyllabus.tsx`, data
`GET /courses/{c}/modules`), lesson page `/courses/{c}/modules/{m}/items/{i}` (`modules/LessonView.tsx`), saved
`/courses/{c}/saved`, analytics `/courses/{c}/progress`, practice `/courses/{c}/practice`. The frame per route is
decided in `app/[lang]/courses/[courseId]/layout.tsx` (exam-prep branch: no `CourseSidebar`; general course:
`CourseSidebar` inside the student shell).

Screenshot pairs: `docs/phases/STAFF_FEEDBACK_screens/item3/<nn>-<slug>-teacher-1440-ru.png` and
`<nn>-<slug>-student-1440-ru.png` (+ `-student-375-ru.png`), produced by the e2e spec of §3 with `ITEM3_SHOTS=<dir>`.
S5 (2026-11-08): pairs committed for every ✓ row below, plus student-only `g1-home-continue` (home strip) and
`d6-exam-tests` (the exam's Тесты page without the lesson course's test). Run from `frontend/`:
`ITEM3_SHOTS=../docs/phases/STAFF_FEEDBACK_screens/item3 npx playwright test e2e/teacher-to-student.spec.ts`.

| nn | Teacher action | Teacher screen (route · file · API) | Server rule that makes it visible | Student: where it appears (page → element · file) | Shots `<nn>-<slug>` |
|---|---|---|---|---|---|
| 01 | Create course (general) | `/courses/new` · `courses/new/page.tsx` · `POST /courses` | status `published`; student enrolled (code or catalog) | **Sidebar**: nowhere (only exam courses are listed; `useStudentShellData.ts` filters `student_layout === "exam_prep"`). **Home**: card in "Другие курсы" at the bottom of `ExamPrepHome.tsx:259-275` (exam student) or the course grid of `StudentHome.tsx` (no exam course). **Course page** `/courses/{c}`: `StudentSyllabus` when it has a lesson, else `StudentCourseHome`, inside `CourseSidebar` (`layout.tsx:132-151`) | ✓ `01-create-course` (teacher: empty outline; student: home without it, a draft) |
| 02 | Publish / unpublish course; visibility `catalog` | course settings `/courses/{c}/settings` · `POST /courses/{c}/publish`, `PATCH /courses/{c}` | `status`, `visibility`, platform org → `home/service.py:_platform_courses` | **Catalog** `/courses/catalog` card (`catalog/`); **Home**: "From the platform" cards (`PlatformCourses.tsx`) for platform courses the student is not in; draft → `courses.home.draftNotice` on the course page; a draft course is not listed | ✓ `02-publish-course` (teacher: Settings → Доступ и Pro, published + exam link; student: УРОКИ row and «Уроки» card) |
| 03 | Create ORT exam (`preset = ort_main`) and publish | `/courses/{c}/assessments/{a}/edit` · `assessments/router.py` publish | `exam_prep/service.py:_visible_test` (published, live, `is_practice = false`) | **Тесты**: library card (`TestLibrary.tsx`), filter chips = published modules holding tests (`SourceOut`); **Home**: `NextCard` (start / resume / retake), score tiles and history after a released result (`ExamPrepHome.tsx:120-160`, `ScoreHistory.tsx`), section bars (`SectionBars.tsx`); **Analytics** `/progress` (sections, topics); **Syllabus**: a row linking to the lobby when placed in a module (L7; ORT exams exempt from module locks, `_ort_exempt`); **Saved**: flagged questions of its attempts | `03-ort-exam`: not in the S5 walk (ORT and other specs cover it) |
| 04 | Create general test (quiz) and publish | same as 03, `preset = none` | same `_visible_test` | **Тесты** card (percent instead of a scaled score); **Home** `NextCard` only as "start" of a not-taken test; **Syllabus** row when in a module | `04-quiz`: not in the S5 walk (ORT and other specs cover it) |
| 05 | Unpublish test | assessments list "Unpublish" | `status = draft` | Disappears from Тесты and syllabus; an open attempt still finishes (attempt engine, unchanged) | `05-unpublish-test`: not in the S5 walk (ORT and other specs cover it) |
| 06 | Create module (+ publish) | course page outline `ModuleOutlineEditor.tsx` · `POST /courses/{c}/modules`, `PATCH …` | `published = true`; `course_features.modules` = exam course: at least one lesson (`modules/service.py:lesson_exists`); general: a published module | **Sidebar**: "Уроки" row appears (`studentNav.ts:57-59`, exam course only). **Overview/Syllabus**: module group with "N из M" and duration (`StudentSyllabus.tsx:199-245`). **Тесты**: a filter chip when the module holds a test | ✓ `06-module` (teacher: both modules; student: overview + syllabus) |
| 07 | Add video (url item, YouTube/Vimeo) | outline "+ Видео" (`ModuleOutlineEditor.tsx:525`) · `POST /courses/{c}/modules/{m}/items` kind `url` | `modules/video.py:parse_video`; item and module published | **Syllabus** row "Видео · 6 мин" (`StudentSyllabus.tsx:71`); **Lesson page** click-to-load player (`LessonView.tsx`, `VideoPlayer.tsx`), outline aside, "Следующий урок"; **Overview** CTA when it is `up_next`; **Home**: nothing (see gap G1) | ✓ `07-video` (teacher: video dialog; student: lesson page before the tap) |
| 08 | Add page (Markdown) | `/courses/{c}/pages/new` then outline "+ Страница" (`AddItemDialog.tsx`) · `POST /courses/{c}/pages`, item kind `page` | page published and placed in a published module | **Syllabus** row "Страница"; **Lesson page** renders the page inline (L3). A page **not** in a module: no student entry point (gap G3) | ✓ `08-page` (teacher: page editor; student: page lesson inline) |
| 09 | Upload file (PDF) | `/courses/{c}/files` (`CourseFilesView.tsx`) then outline "+ Файл" · `POST /courses/{c}/files`, item kind `file` | file published; `course_features.files` | **Syllabus** row "Файл"; **Lesson page** file card with download. General course: `CourseSidebar` "Файлы" (`nav.ts:82`). Exam course: `/courses/{c}/files` only by URL, no link (gap G3) | ✓ `09-file` (teacher: upload dialog from «+ Добавить → Файл»; student: file lesson, download card) |
| 10 | Add link (url item, other host) | outline "+ Ссылка" (`ModuleOutlineEditor.tsx:528`) | published | **Syllabus** row opens the address in a new tab (`StudentSyllabus.tsx:155`), view recorded on click; **Lesson page** small link card | `10-link`: not in the S5 walk (ORT and other specs cover it) |
| 11 | Add test to module | outline "+ Тест" (`AddItemDialog.tsx` assignment tab) | published; quiz assignment | **Syllabus** row → lobby `/courses/{c}/assessments/{a}` (exam shell, SF-1); counted in module progress; also in **Тесты** (by design, L7: path vs library) | ✓ `11-module-test` (teacher: quiz editor, published; student: module 1 with the test row) |
| 12 | Publish / unpublish module or item | outline toggles | `published` flags | Row/group appears or disappears; progress totals recount (`ModulesStudentOut.progress`) | ✓ `12-unpublish-module` (teacher: a lesson's switch off; student: row gone, «Пройдено 2 из 5») |
| 13 | Announcement (publish) | `/courses/{c}/announcements/new` (`AnnouncementEditor.tsx`) · `POST …/publish` | `published_at <= now`; `course_features.announcements` | **Home**: right column "Объявления" (`StudentHome.tsx:127-135`, all courses, newest 3) → `/courses/{c}/announcements` (`AnnouncementsView.tsx`). Exam course: no sidebar or Тесты link to the list (gap G2). General course: `CourseSidebar` "Объявления" | ✓ `13-announcement` (teacher: editor; student: list with the student page header) |
| 14 | Practice set | `/courses/{c}/practice` (teacher) · `POST /courses/{c}/practice` (`practice/router.py:27`) | `is_practice = true`, published; `course_features.practice` | **Sidebar** "Практика" (exam course, `StudentShell.tsx:100`); **Practice** `/courses/{c}/practice`; **Home** `NextCard` kind `practice` (weakest section). Never in Тесты (`_visible_test` excludes practice) | `14-practice`: not in the S5 walk (ORT and other specs cover it) |
| 15 | Pro toggle on a test | **platform admin only**: `/admin/access` (`AdminAccessUi.tsx`) · `PATCH /platform/access/exams/{id}` (`access/router.py:190`) | `assessments.access_tier = paid`, platform course, `access/service.py:Gate` | **Тесты** card gold "Pro" + lock (`TestLibrary.tsx:42-46`); **Home** `UnlockCard` while no result (`ExamPrepHome.tsx:200-206`), `needs_pass`; **Catalog/Home card** quiet Pro mark (`has_paid_tests`); lobby `can_start = false, reason access_required` | ✓ `15-pro-test` (teacher: Admin → Pro → Тесты, the new test made free; student: its lobby, «Начать тест») |
| 16 | Pro toggle on a module | outline Pro switch, platform courses only (`ModuleOutlineEditor.tsx:467`) · `PATCH …/modules/{m}` `access_tier` | `course_modules.access_tier`, L5 | **Syllabus** gold chip + "Открыть доступ" (`StudentSyllabus.tsx:237-238`), rows without address; **Lesson page** `ProLockCard.tsx`; **Sidebar** gold pill (always) | ✓ `16-pro-module` (teacher: module card with the gold lock; student: Pro lesson by URL, lock card) |
| 17 | Exam date | course settings `ExamDateSection.tsx` · `PATCH /courses/{c}` `exam_date` | exam course only | **Home** hero countdown (`ExamPrepHome.tsx:81-90`) | `17-exam-date`: not in the S5 walk (ORT and other specs cover it) |
| 18 | Cover image | settings cover section · `POST /courses/{c}/cover` | F7 | **Catalog/Home card** cover; **Overview** banner (`StudentSyllabus.tsx:303`) | ✓ `18-cover` (teacher: Settings → Обложка saved; student: catalog landing before the join) |

### 1.1 Gaps: missing, wrong place, twice

| # | Finding | Evidence | Fix (slice) | Status (S5) |
|---|---|---|---|---|
| G1 | **"Continue in course" is computed but never shown.** `HomeOut.modules_next` (`home/service.py:451-556`) has no consumer in the frontend (`grep modules_next frontend/src` → only the type). An exam student with lessons sees no "Продолжить урок" on the home; only the overview CTA shows it | `home/schemas.py:HomeModuleNextOut`, `ExamPrepHome.tsx` | S3: home strip from `modules_next` for the current exam and its lesson courses | **fixed** (S3; S5 spec: `g1-home-continue`) |
| G2 | **Announcements of an exam course are reachable only from the home side list**, no sidebar or Тесты entry; the list page gets the generic `StudentCourseHeader` (`layout.tsx:123`, `ownTitle` false), a different header than every other exam-shell page | `StudentHome.tsx:127-135`, `layout.tsx:117-130` | S3: `/announcements` joins `ownTitle` with `StudentPageHeader`; link "Все объявления" from the home side list; no new sidebar item | **fixed** for the list (S3; S5 spec: `13-announcement`). There is no student page for one announcement (`/announcements/[id]` has only the staff `edit`); students read them on the list, so nothing to add |
| G3 | **Files and pages outside modules are invisible to exam students.** `/courses/{c}/files` and `GET /courses/{c}/pages` (student shape exists, `pages/router.py:24-32`) have no entry point in the exam shell (`studentNav.ts` has no `files`/`pages`) | `nav.ts:82` (general only) | Decision D3: lessons are the only student path to pages and files in the exam shell; the teacher editor's empty-module hint says so (text only, S4). No new page | **fixed by decision D3**; the empty-module hint says it (seen in `01`/`06` teacher shots) |
| G4 | **Teacher-made lesson courses sit outside the exam shell.** For an exam student a general course is a card under "Другие курсы" (bottom of the home) and opens with `CourseSidebar` (Курс, Задания, Оценки, Преподаватели …), a different frame than the exam pages | `ExamPrepHome.tsx:259-275`, `layout.tsx:132-151` | §2: attach lesson courses to the exam; they get the exam shell | **fixed** (S1, S2; S5 spec: lobby, lesson pages and overview in the exam shell, no `CourseSidebar`) |
| G5 | **The sidebar cannot describe a general course**: `HomeCourseOut.features` is null for non-exam courses (`home/service.py:249, 265-266`) | `_exam_features` only for exam courses | S1: lesson-course list endpoint carries what the sidebar needs | **fixed** (S1 `GET /courses/{id}/lesson-courses`) |
| G6 | **Dead duplicate**: `examPrep/ExamPrepPage.tsx` is imported nowhere (`TestsPage.tsx` + `ExamPrepHome.tsx` replaced it) | `grep -rn ExamPrepPage frontend/src` → the file only | S3: delete (confirm with grep first) | **fixed** (S3, file deleted) |
| G7 | **Pro for tests is admin-only** (`/admin/access`), Pro for modules is on the teacher's outline; the teacher sees one switch and not the other | `access/router.py:190`, `ModuleOutlineEditor.tsx:467` | Record as decision D4 (platform admin prices tests; no change now). Item 5 (staff UX) may add a read-only "Pro" badge on the assessments table | **decided D4**, no change (S5 uses Admin → Pro → Тесты: `15-pro-test`) |
| G8 | **Twice, by design**: a test placed in a module is in Тесты and in the syllabus (L7); the Тесты filter chips repeat module titles. Keep; the design calls them path vs library | `exam_prep/service.py:98-108` | none | by design |
| G9 | **Practice sets appear only on Практика**; not in Тесты (by design) and not placeable in a module (no assignment row). A teacher placing "practice" in a syllabus must use a quiz | `_visible_test`, `AddItemDialog.tsx:33` | Decision D5: keep; hint text in the practice editor (S4) | **decided D5**; practice-editor hint **open** (S4 not in `lms` 69c59f9) |
| G10 | **Exam course description shows nowhere in the exam shell** (only on the catalog card and the general `StudentCourseHome`) | `ExamPrepHome.tsx` hero has title + countdown only | later (item 5 or a home "О курсе" line); not in this item | **open** (later) |
| G11 | **Lobby back link of a lesson-course test says «Назад к заданиям»** (the general course's Assignments list), in the exam shell where the student came from the syllabus | S5 `15-pro-test-student-*` (lobby of `/courses/{lc}/assessments/{a}`) | open: in the exam shell, back to the syllabus (`/courses/{lc}/modules`) | **open** |
| G12 | **The home «Продолжить урок» strip shows a link icon for a video lesson** (the syllabus and lesson page show the video icon) | S5 `g1-home-continue-student-*` | open: `HomeModuleNextOut` carries no video flag; use the kind + `parse_video` like the syllabus | **open** |
| G13 | **A lesson-course test is listed in the exam home's «К выполнению»** (D6 keeps it out of Тесты and analytics, the to-do list still shows it) | S5 `g1-home-continue-student-1440` | owner decision: keep (it is a to-do of a joined course) or filter lesson courses out of the exam home's to-do | **open** |

## 2. Structure: how lesson courses attach to an exam

### 2.1 Options

| | (a) Separate lesson courses linked to the exam course | (b) Modules inside the exam course | (c) New "masterclass" entity |
|---|---|---|---|
| Data | one nullable FK on `courses` | none, but a module needs cover, description, own progress banner → 3 new columns + a "module group" level | new table + items table + progress |
| Reuses | everything of F5 (overview, syllabus, lesson page, Pro modules, `up_next`, covers, catalog, enrollment, teacher editor) | syllabus only; overview per masterclass does not exist | nothing |
| ORT | untouched: ORT courses get no rows; the link lives on the lesson course | adds many modules to the ORT courses: the Тесты filter chips, `course_features`, `up_next` and the ORT course page change | untouched |
| Teacher | today's course editor, one course per masterclass | one giant outline per exam | new editor |
| Sidebar | one list per exam (`exam_course_id = current`) | module list (already dropped as sub-links in U9) | new list |

**Decision D1: (a).** It changes least (one column, one list endpoint, one sidebar group), reuses every course feature
built on 2026-11-07, and never writes into the ORT courses. A lesson course is an ordinary platform course; nothing
in the attempt engine, grading, modules or access changes.

### 2.2 Data (migration `0027_exam_course_link`, additive)

- `courses.exam_course_id` UUID NULL, FK `courses.id` ON DELETE SET NULL, index `ix_courses_exam_course_id`,
  CHECK `exam_course_id IS NULL OR exam_course_id <> id` (name `exam_course_not_self`). `down_revision =
  "0026_course_cover"`; downgrade drops index and column. Model `courses/models.py` mirrors it (`alembic check`
  clean; SQLite `create_all`). No data step. Neon backup branch before the deploy (`STUDENT_UI_FIX_PLAN.md` §0).
- Service rules (`courses/service.py:update_course`), 422 unless all hold: caller `is_platform_admin`
  (`exam_link_forbidden`); the lesson course is a platform course (`modules/service.is_platform_course`) with
  `template_key IS NULL` and no `sandbox_for_template_id` (`exam_link_not_allowed`); the target exists, is not
  deleted, is a platform course and `is_exam_prep(target)` (`exam_link_target_invalid`). `null` clears. The exam
  course itself never gets a link (it is exam-prep, so `exam_link_not_allowed`). ORT template lock is unaffected
  (`template_locked` applies to the exam course, which is never written here).
- Why a column and not `courses.settings["exam_course_id"]` (the `exam_date` pattern): the sidebar queries *by*
  it (all lesson courses of exam X) and a deleted exam must detach its courses; a FK with an index does both,
  a JSON key does neither on SQLite.

### 2.3 API

| Route | Policy | Shape |
|---|---|---|
| `PATCH /courses/{id}` + `exam_course_id: uuid \| null` (`CourseUpdateIn`) | `course.manage` + rules §2.2 | `CourseOut.exam_course_id` (all shapes incl. staff) |
| `GET /courses/{id}/lesson-courses` (new; `route_inventory.py` policy "enrolled or staff of the exam course") | `exam_prep.require_exam_prep(course)` (404 otherwise); caller enrolled (students, test students) or staff | `LessonCourseOut[]` (≤ 20, ordered by `published_at`): `id, title, cover_url, is_platform_course, lessons_count, duration_s, enrolled: bool, progress: {done,total} \| null (enrolled only, from the stored facts as `HomeProgressOut`), has_paid_modules: bool, next_item: ItemLinkOut \| null (enrolled; = up_next's link)`. Rows: `status = published`, `deleted_at IS NULL`, `exam_course_id = id`; visibility is ignored (attached courses are listed for the exam's students even if `private`; join still goes through the normal join rules). One statement for rows, one for progress. Allow-list: no join code, no roster |
| `HomeCourseOut` + `exam_course_id` | existing | the shell knows which exam a lesson course belongs to (switcher chip stays on the exam while inside a lesson course) |
| `POST /courses/{id}/join` | unchanged | joining an attached course; open platform courses join in one tap (S2 one-tap join) |

### 2.4 Sidebar and switcher

Groups (desktop; phone "Ещё" sheet gets the same rows): `Главная · Тесты · Практика · Аналитика` (as today),
**УРОКИ**: the exam course's own "Уроки" row when it has a lesson (today's rule, keeps lessons.spec), then one row
per `LessonCourseOut` (icon `GraduationCap`, title, right side: `done/total` ring when enrolled, nothing otherwise),
then `Сохранённые`. Up to 8 rows shown, then "Все уроки" → `/courses/{exam}/lessons` (new small page listing the
cards; S2) only when more than 8.

| Student has | Sidebar |
|---|---|
| 0 exam courses | as today: Главная, Каталог. Joined lesson courses are plain general courses (cards on the home, `CourseSidebar` frame) |
| 1 exam course | no chips, exam title under the brand; УРОКИ lists its lesson courses |
| 2 exam courses | chips ORT ru / ORT ky; УРОКИ lists the current chip's lesson courses; switching chips swaps the group |
| teacher (non-exam) courses | not in the sidebar (unchanged); cards under "Другие курсы" on the home |
| inside a lesson course | current chip = its `exam_course_id` (from `HomeCourseOut`/`CourseOut`); the lesson course's row is `aria-current` |

Row link: enrolled → `/courses/{lc}/modules` (overview, L1); not enrolled → `/courses/catalog/{lc}` (`CourseLanding`
joins and pushes `/courses/{lc}`, which opens the overview). No client-side auto-join.

What the switcher stores: unchanged, `localStorage["ort_student_course"]` holds the exam id; the URL carries the
course. New: `useStudentShellData` maps `pathCourseId` → exam via `exam_course_id` before choosing `current`. The
`sessionStorage` cache key `ort_student_shell` is versioned (`ort_student_shell_v2`) so stale shapes are dropped.
Lesson-course rows are cached per exam like `features`.

### 2.5 Frame rules (`layout.tsx`)

`isExamShellCourse(course)` (`lib/lms/templates.ts`) = `templateUi(course).studentLayout === "exam_prep" ||
course.exam_course_id != null`. The exam-prep branch of `layout.tsx:117-130` and SF-1 (`LmsShell` lobby/result in the
reading column) use it, so an attached lesson course has no `CourseSidebar`, no breadcrumbs, and its lobby, player,
result and review look like the exam's. `courses/[courseId]/page.tsx` for such a course → `StudentSyllabus` (exists via
`features.modules`); with no lesson yet → the overview's empty state (`modules.overview.emptyTitle`). Staff frames are
untouched. A lesson course the student joined whose exam he left: `exam_course_id` still set → exam shell, chip falls
back to the first exam or none; acceptable (the sidebar then shows Главная/Каталог and the course keeps its own
title row).

### 2.6 Teacher / admin surface

- Course settings (`/courses/{c}/settings`, platform courses only, caller platform admin): select **"Экзамен"** with
  the platform's exam courses, "—" clears. S3: one request, `GET /platform/courses?exam_prep=true` (platform admins
  only; live platform courses whose template has the exam-prep layout, the same rule as the link target; no new
  route), replacing S2's catalog read plus one `getCourse` per row. Help text: "Курс появится в разделе Уроки у студентов этого
  экзамена". Keys `courses.settings.examLink.*` (en/ky/ru).
- Teacher course page: a quiet line under the title "Уроки экзамена: ОРТ (на русском)" when attached.
- Admin → Courses list: column "Экзамен" (item 5 may restyle; S2 adds the field only).
- Lesson course pattern for the owner: one course per masterclass and language, cover, modules = topics, items =
  video / page / file / test, Pro per module.

### 2.7 Decisions to record (`PRODUCT_DECISIONS.md`)

D1 attach by `courses.exam_course_id` (§2.1). D2 the exam's own modules keep the "Уроки" row; lesson courses are rows
of the same group. D3 in the exam shell, pages and files reach students only through lessons. D4 Pro on tests stays a
platform-admin action; Pro on modules stays on the outline. D5 practice sets stay on Практика only. D6 lesson-course
tests do not enter the exam's Тесты or analytics (they live in their syllabus); later if the owner wants it.

## 3. E2E: `frontend/e2e/teacher-to-student.spec.ts`

Seed (`frontend/e2e/seed_backend.py`, new row `item3`, written after every ORT row, same pattern as `seed_modules`):
`lesson_course_id` (platform admin `POST /courses` with the ORT ru course's `organization_id`, title "Мастеркласс
E2E", published, `PATCH exam_course_id = <ORT ru>`), `student` (new user, joined ORT ru only), `exam_course_id`.
`helpers.ts` `Seed.item3`. The spec builds content via the API in `beforeAll` as `seed().admin` (the `api()` helper of
`lessons.spec.ts`, moved to `helpers.ts`), and cleans up in `afterAll` (unpublish is enough; ORT specs never read the
lesson course).

| Step | Teacher (API or page) | Student page asserted (ru, 1440 and 375) | Shot slug |
|---|---|---|---|
| 1 | course exists, attached | sidebar group УРОКИ has "Мастеркласс E2E" (not enrolled, no ring); home has no "Другие курсы" card for it | `01-create-course`, `02-publish-course` |
| 2 | module 1 "Математика I": video (YouTube, 6 min), page, file (PDF upload), test (quiz, published); module 2 "Аналогии": video, page; module 2 Pro (`access_tier = paid`) | click the row → catalog landing → "Присоединиться" → overview: cover banner, "Начать курс", "Пройдено 0 из 6", two groups, module 2 gold chip, no href/video id in its rows (the lessons.spec leak check) | `06-module`, `16-pro-module` |
| 3 | — | lesson page video: outline aside, no third-party request before the tap (route stub), view recorded on play; "Следующий урок" → page lesson inline; file lesson download card; test row → lobby in the exam shell (no `CourseSidebar`, `aria-label` of the student nav present) | `07-video`, `08-page`, `09-file`, `11-module-test` |
| 4 | — | home: "Продолжить урок" strip names the first unviewed lesson of the masterclass (G1) | `g1-home-continue` |
| 5 | teacher unpublishes module 1 item "video" | syllabus loses the row; totals recount | `12-unpublish-module` |
| 6 | announcement published in the lesson course | home side list shows it; its page has the student header, not `StudentCourseHeader` (G2) | `13-announcement` |
| 7 | switch chip (seed a second exam enrolment: join ORT ky via API in the test) | УРОКИ group is empty for ORT ky, back to ru shows the masterclass; chip stays on ru while inside the masterclass | `switcher` |
| 8 | teacher screens for pairs: `/courses/{lc}` outline, settings "Экзамен", assessments list, `/admin/access` | — | `*-teacher-1440-ru` |
| guard | — | `ort.spec.ts`, `lessons.spec.ts`, `student-shell.spec.ts` unchanged and green; `ort-visual` baselines unchanged | — |

Assertions use `tr("ru", key)` (no hard-coded text), `settle()`, `noHorizontalScroll` at 375. Shots only with
`ITEM3_SHOTS`. Shot names: `<slug>-teacher-1440-ru.png`, `<slug>-student-1440-ru.png`, `<slug>-student-375-ru.png`.

**As built (S5, 2026-11-08)**: the seed row `item3` is the lesson course as a **draft without the link** (platform
organization, open enrollment, `visibility = catalog`) plus the ORT (Russian) student, so no other spec ever sees it;
the spec does the rest in the browser as the platform admin: cover (Settings → Обложка), publish and the exam link
(Settings → Доступ и Pro), both modules through «+ Добавить» (video dialog, page inline + page editor, PDF upload,
quiz inline + quiz editor), the new test made free on Admin → Pro → Тесты (tests of platform courses start Pro), the
Pro lock, the module switches, an announcement, one lesson unpublished (a course with students cannot be unpublished,
`has_students`). The student joins from the catalog landing (one tap), so step 7 (switcher) is left to
`student-shell.spec.ts`; the D6 check (exam Тесты without the lesson test) is added. Cleanup: `DELETE` the course.

## 4. Slices (ordered; one implementer per slice in a worktree off `lms`)

| # | Model | Scope | Files | Tests | Risks |
|---|---|---|---|---|---|
| S1 | Opus | Backend link + list | `alembic/versions/0027_exam_course_link.py`, `courses/models.py`, `courses/schemas.py` (`CourseUpdateIn`, `CourseOut`, `exam_course_id`), `courses/service.py` (rules §2.2), new `courses/lesson_courses.py` or `exam_prep/service.py:lesson_courses` + route in `exam_prep/router.py`, `home/schemas.py` + `home/service.py` (`exam_course_id` on cards), `core/route_inventory.py` | `tests/lms/test_exam_course_link.py`: admin links, teacher 422, non-platform 422, target not exam-prep 422, self 422, clear; list: not enrolled 403, unpublished hidden, `enrolled`/`progress`, no join code in the body (allow-list test), ORT seed unchanged (`tests/lms/test_ort_seed*`), `alembic check`, `test_migrations.py` | Neon backup before deploy; keep one statement for progress; `is_platform_course` per request |
| S2 | Opus | Shell, frame, settings | `student/useStudentShellData.ts` (lesson rows, exam from `exam_course_id`, cache v2), `lib/lms/studentNav.ts`, `student/StudentShell.tsx` (УРОКИ group, ring), `lib/lms/templates.ts` (`isExamShellCourse`), `courses/[courseId]/layout.tsx`, `LmsShell.tsx` (SF-1 condition), `courses/[courseId]/page.tsx`, settings page select, `lib/lms/courses.ts` types, `en/ky/ru.json` (`student.nav.lessonCourses`, `student.nav.allLessons`, `courses.settings.examLink.*`) | `npx tsc --noEmit`, parity script, unit test for `studentNavLinks` (exists? else add `lib/lms/__tests__`), e2e `student-shell.spec.ts` still green | the layout condition must not touch staff frames or the player route (SF-1 invariant); ORT baselines re-run |
| S3 | Opus | Home strip, announcements header, dead code | `home/ExamPrepHome.tsx` (strip from `modules_next` filtered to current exam + its lesson courses; `HomeModuleNextOut.link`), `layout.tsx` (`ownTitle` includes `/announcements`), `announcements/AnnouncementsView.tsx` (`StudentPageHeader` for students), delete `examPrep/ExamPrepPage.tsx` after `grep -rl`, keys `home.prep.continueLesson.*` | `student-home.spec.ts` extended (strip present/absent), tsc, parity | `modules_next` rules unchanged (server); strip hidden when empty |
| S4 | Sonnet | Text and styling to the reference pattern | `StudentSyllabus.tsx` (duration and done chips, module header spacing), `LessonView.tsx` (outline width, "Следующий урок" primary), empty-module hint in `ModuleOutlineEditor.tsx` (D3 text), practice editor hint (D5), `en/ky/ru.json` | tsc, parity, `lessons.spec.ts` green, UX check 375/1440/1920 ru by the orchestrator | no behaviour change; no new components |
| S5 | Opus | E2E + screenshot pairs + docs | `e2e/seed_backend.py` (`item3` row), `e2e/helpers.ts` (`Seed.item3`, shared `api()`), `e2e/teacher-to-student.spec.ts`, `docs/phases/STAFF_FEEDBACK_screens/item3/*.png`, this doc's shots column confirmed, `PRODUCT_DECISIONS.md` D1–D6, `HANDOFF_NEXT_AGENT.md`, `AGENTS.md` head `0027` | the spec; full e2e suite; backend suite | seed order: after every ORT row (ORT specs see the course as seeded) |

Order: S1 → S2 → (S3 ∥ S4) → S5. Merge each to `lms` after its Fable review and the ORT gate (`ort.spec.ts`,
`ort-visual.spec.ts` baselines, scores unchanged); `main` after S5 with the Neon backup for 0027.

## 5. Risks and open questions (defaults in effect)

| # | Risk / question | Default |
|---|---|---|
| R1 | Attached `private` courses are listed to exam students (§2.3) although not in the catalog | intended: attachment is the listing; the catalog landing still works by id |
| R2 | A student enrolled in a lesson course but in no exam course | exam shell without chips (§2.5); the course keeps working |
| R3 | Lesson-course tests outside exam analytics (D6) | accepted; revisit when the owner asks for "lesson test scores in analytics" |
| R4 | Who may attach: platform admin only | yes until platform-org teachers exist as a role (`PRODUCT_DECISIONS.md`) |
| R5 | More than 8 lesson courses per exam | "Все уроки" page, S2; the endpoint caps at 20 |
| R6 | Cache shape change in `sessionStorage` | key versioned (`_v2`) |
| Q1 | Should the exam course's own "Уроки" row be renamed "Уроки экзамена" once lesson courses exist? | no rename now (lessons.spec and keys unchanged); decide with the owner after the first masterclass |
| Q2 | Olympiad / НЦТ exams: new templates with `student_layout = "exam_prep"`; lesson courses attach the same way | nothing else needed in this design |
