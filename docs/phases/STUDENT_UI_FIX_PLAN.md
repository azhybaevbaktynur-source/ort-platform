# Student UI fix plan: the owner's 7 problems (2026-11-07)

**Brief**: `STUDENT_UI_FEEDBACK_2026-11-07.md` (verbatim). Base: `lms` 3630c96 = production `main` be6070e + docs.
Rule: improve the existing architecture; ORT **behaviour** (timers, sections, scoring, imports) stays identical,
its **look** may change (new frames, tokens, font). The reference app is only ever called "the reference app".
Model rule (brief): Opus for data, migrations, analytics counting, access, shell/routing, result page, lessons,
covers, ORT-related code and anything that failed once; Sonnet only for tokens, styling, keys, renames, deletion of
code Opus identified. Build order 1 → 7, each with tests, ORT review and deploy. No code in this document.

## 0. Migrations and deploys (Neon has one free backup slot)

| Problem | Schema change | Migration |
|---|---|---|
| 1, 2, 3, 4 | none (4 adds an optional query parameter and response fields only) | no |
| 5 | `module_items.duration_s` int null; `course_modules.access_tier` varchar(8) not null default `free` | yes |
| 6 | `access_passes.plan` varchar(16) null (`month_1`, `month_3`, `season`, null = legacy code/grant) | yes |
| 7 | `courses.cover_asset_id` uuid null, FK `assets.id` on delete set null | yes |

Decision: **one migration `0024_student_fix` (head after `0023_person`), shipped with problem 5's deploy, carrying
all four additive nullable/defaulted columns**, no data steps. One Neon backup branch (`backup-2026-11-0x-before-0024`),
one rehearsal `alembic upgrade head && alembic check` on a fresh PG, one `tests/test_migration_0024.py`. Problems 6
and 7 then deploy without a migration (so yes, 6 and 7 can share a deploy if they finish together; they do not need
to). If 5 slips, 6 and 7 still ship their columns in the same single migration, created by whichever is first.
Nothing existing is rewritten: passes keep `source` (`code` / `admin` / `payment`); modules default `free`.

## 1. Sidebar spacing

**Cause** (not empty headings; empty groups are already filtered): `frontend/src/components/ui/SidebarNav.tsx:91`
`<nav className="space-y-4">` puts 16 px between groups, items get 2 px (`space-y-0.5`, line 100);
`frontend/src/components/lms/student/StudentShell.tsx:97-101` `useMenuGroups` splits the menu into two
**unlabelled** groups `main` (Главная, Тесты, Практика, Аналитика) and `more` (Видеоуроки, Сохранённые), so the
boundary above Видеоуроки / Сохранённые is 16 px. On the phone the "More" sheet shows only the `more` group (line
419), so there the gap is invisible.
**Fix**: `SidebarNav` applies the group gap only before a group that has a `label` (a labelled group gets
`mt-4`; unlabelled groups continue the 2 px rhythm); `useMenuGroups` returns one group for exam-prep students. The
"Начало работы" pill, gold pill and account block (`mt-auto space-y-3`, line 340) stay as they are.
**Files**: `SidebarNav.tsx`, `StudentShell.tsx`. **Tests**: `frontend/e2e/student-shell.spec.ts`: the vertical
distance between consecutive nav links is equal (bounding boxes) at 1440 and 1920; tab bar unchanged at 375.
**Risk**: none for ORT. **Slice F1 (Sonnet)**.

## 2. Exam pages in the student shell (replaces `STUDENT_UI_DESIGN.md` §2.4)

**Cause**: `frontend/src/components/lms/LmsShell.tsx:74-80` (`ORT_FRAME`, `isOrtFrame`) sends the lobby and every
`/attempts/**` route to the `AppHeader` frame; `LmsShell.tsx:176-177` wraps attempt pages in `EXAM_COLUMN_*`;
`app/[lang]/courses/[courseId]/layout.tsx:95-115` (`attemptsPage`) renders `StudentCourseHeader` **with
breadcrumbs** above result and review, and `layout.tsx:122` (`!lobby`) sends the lobby into `CourseSidebar`
(Курс, Задания, Оценки, Преподаватели, Мой прогресс, Сохранённые); the lobby page
`assessments/[assessmentId]/page.tsx:12` uses staff `useTabCrumbs`; `StudentResult.tsx:62-65` links "Назад к
заданиям" (`results.back`) to the assignments list. Fonts: `tailwind.config.ts:94-96` resolve `font-sans` to the
system stack outside `STUDENT_FRAME` (`StudentShell.tsx:39` sets `inter.variable` + `.student-theme`).

### 2.1 New rule §2.4 (owner decision)
- For an **exam-prep student** (role `student`, `templateUi(course).studentLayout === "exam_prep"`, test students
  included): lobby `/courses/{c}/assessments/{a}`, result `/courses/{c}/attempts/{id}/result` and the review on it
  render **inside `StudentShell`** (sidebar / tab bar, Inter, `.student-theme`), content in a reading column
  (max 880 px) inside `STUDENT_MAIN`; no course header, no breadcrumbs, no course sidebar.
- The **player** `/courses/{c}/attempts/{id}` (exact path) renders with **no chrome at all**: `LmsShell` wraps it
  in a full-viewport `div` carrying only `inter.variable` + `student-theme font-sans` (no `lg:pl-[264px]`, no
  tab-bar padding, no banners). `PlayerShell` and every player component stay untouched; they only inherit the
  CSS variables and the font. Bluebook layout and behaviour unchanged.
- Staff frames (`AppHeader` + `StaffCourseBar`), staff preview of attempts, and students of **general** (teacher)
  courses keep today's frames; the general student course keeps `CourseSidebar` inside the student shell (§2.2).
- `LmsShell`: `isOrtFrame` becomes `isPlayerRoute`; the lobby/result follow the normal area rule (they already wait
  for the course declaration). `layout.tsx`: delete the `lobby` exception and the student `header` on
  `attemptsPage`; the exam-prep branch covers lobby, result and review.

### 2.2 Result page redesign (exam-prep students; general quizzes get the same components with points/percent)
Data: `AttemptResultOut` (`raw_score`, `points_possible`, `sections`, `grade`: `display_value`, `scale_min/max`,
`percentile`, `passed`, `thresholds`, `sections[].display_value`, `is_kept`, `released`) and `ReviewOut`; one extra
read `GET /courses/{c}/exam-prep` for `next` (the "next test"). Nothing is computed client-side; all numbers are
the server's (ORT scoring untouched).
1. Header: "Результат" + test title + date; back link "К тестам" (`/courses/{c}/tests`), not "Назад к заданиям".
2. Hero card: mascot left (`celebrating` ≥ 80 % raw ratio, `hello` 50–79 %, `encouraging` < 50 %; keep
   `data-testid="result-mascot"`), big scaled score (48/56 bold, tabular), line "из 245 · шкала ОРТ 60–245" from
   `scale_min/max`, meaning line by scaled value (copy only, keys `results.meaning.*`): < 110 "Старт: ниже
   большинства участников", 110–149 "Ниже среднего (среднее по шкале 150)", 150–189 "Выше среднего", ≥ 190
   "Высокий результат", golden-certificate badge when the server flag `thresholds.golden_certificate` is on.
   Percentile shown as "Выше, чем N % участников (модель шкалы)" only when `percentile` > 0.
3. **Zero raw (D6)**: `backend/app/lms/grading/registry.py:125-134` `_zero` returns value 0, percentile 0.0 and
   `passed=False` (seeds: `grading/seeds.py:45` `zero_raw {value 0, percentile 0.0}`). The page shows "0" and one
   plain sentence: "Ни одного верного ответа, поэтому балл 0. Шкала ОРТ начинается с 60: первый верный ответ даёт
   не меньше 60 баллов." No percentile, no "Незачёт". Scoring data is not changed (parity).
4. Labels removed for students: "Незачёт/Зачёт" (`GradeBadge.tsx:71-73` renders it whenever `passed` is not
   null; fix in the registry: `_zero` sets `passed=None` unless the version has `pass_threshold_percent`, and
   `GradeBadge` shows pass/fail only for schemes that define it; update `tests/lms/test_grading_registry.py`),
   "Идёт в зачёт" (`showKept=false` on student pages; staff views keep it), "Процентиль 0.0" (hidden when null or 0).
5. Section breakdown: five rows in ORT order: neutral section tag, raw "12 / 30", scaled value, a thin brand bar
   of the raw ratio; "Всего" row. Same `result.sections` + `grade.sections` as `OrtResultView` today.
6. Actions: primary "Разобрать ошибки" (scrolls to the review, turns "only mistakes" on); secondary "Следующий
   тест" → the lobby of `exam-prep.next` or `/tests` when none. One primary per screen.
7. Review: `ReviewList`/`ReviewItemCard` unchanged in content; cards restyled with tokens; each card gets
   `id="item-{n}"` (needed by problem 3); after the review loads, the page scrolls to `location.hash`.
8. Lobby: `LobbyView` restyled (tokens, one primary "Начать"), `MyAttemptsPanel` restyled as the attempts list of
   that test; staff `useTabCrumbs` only for staff.
9. Not-available / in-progress / void states keep their logic, restyled.

### 2.3 ORT baselines and behaviour guards
- **Re-approved (look changes)**: every student image in `docs/phases/ORT_BASELINE/`: `lobby`, `comparison`,
  `flagged-palette`, `review-page`, `section-end`, `passage`, `submit`, `result`, `review` × phone/desktop ×
  ru/ky (32) + `player-loading-phone-ru` (33 files). Teacher images (`teacher-*`) **unchanged** and must still match.
  Before/after pairs go to `docs/phases/STUDENT_UI_FIX_screens/ort-review/`, dated note in `ORT_BASELINE/README.md`.
- **Behaviour guards (must stay green, unchanged)**: `frontend/e2e/ort.spec.ts` (lobby → result DOM assertions:
  section order and counts, timer, palette states, comparison columns, passage line numbers, result card raw 2/19,
  five section rows, review headings count), `bluebook-player.spec.ts`, `scrolling-player.spec.ts`,
  `exam-prep.spec.ts`; backend `tests/lms/test_ort_parity.py`, `test_ort_e2e_api.py`, `test_ort_gradebook_golden.py`,
  `test_ort_import_golden.py`, `test_ort_seed.py`, `test_grading_scoring.py`, `test_attempt_ported.py`; importers diff
  empty. `ort-exam.ts` `assertResult` keeps working: the region `results.title`, the group `results.grade.title`, the
  caption `results.grade.sectionsTitle` and the "overall" row keep their accessible names.
- Risk: the player inherits `--brand-*` from `.student-theme` (sky blue instead of Tailwind blue) and Inter; the
  `review-page` and dialogs are the only player screens with brand colour. Timer, autosave and section-close logic
  have no CSS dependency. The test-student (Student view) preview goes through the same frame.

### 2.4 Removals (after 2.1–2.2 land; the Opus implementer confirms each with `grep -rl` before deleting)
`ORT_FRAME`/`isOrtFrame` and the `EXAM_COLUMN_*` wrapper (`LmsShell.tsx:74-80, 176-177`); the `lobby` exception
and the student `header` on `attemptsPage` (`layout.tsx:95-115, 122`); the `breadcrumbs` prop of
`StudentCourseHeader` (`StudentCourseFrame.tsx:13`, then only general courses use the header); `useTabCrumbs` on the
student lobby; `OrtResultView.tsx` (its table moves into the new section breakdown; `GradeBadge` stays for staff and
general schemes); `results.back` on student pages (`results.backToTests` instead); `e2e/student-shell.spec.ts:40`
assertion that the lobby keeps the old header → inverted; `STUDENT_UI_DESIGN.md` §2.4 text → replaced by this
section. Kept on purpose: `StudentHome.tsx` (students without an exam-prep course), `PlatformCourses.tsx` (rows in
the exam sheet and the admin page), `MyAttemptsPanel` (the only list of previous attempts of one test).

**F2a confirmed list (2026-11-07, `grep -rl` over `frontend/src`, `frontend/e2e`, docs; branch `fix-f2`)**
- Already gone in F2a/F2b (replaced, nothing left for F2c): `ORT_FRAME`/`isOrtFrame` (now `isPlayerRoute` +
  `PLAYER_FRAME` in `LmsShell.tsx`); the `lobby` exception and the exam-prep student `header` on `attemptsPage`
  (`layout.tsx`: the exam-prep branch runs first and covers lobby, result and review); `useTabCrumbs` on the student
  lobby (moved into `StaffOverview` in `assessments/[assessmentId]/page.tsx`); `ResultMascot` in `StudentResult.tsx`
  (the cub is in `ExamResultHero`); `e2e/student-shell.spec.ts:40` inverted (lobby inside the student shell).
- **Delete in F2c**: `components/lms/results/OrtResultView.tsx` (no importer left: `ResultSummary` uses
  `SectionBreakdown`; the only other hit is a comment in `ResultSummary.tsx`). No i18n key becomes orphaned with it
  (`results.grade.scaledShort/scaled/raw/overall/sectionsTitle` are read by `SectionBreakdown`, `results.grade.percentile`
  by `GradeBadge`).
- **Stale comments/docs to rewrite in F2c**: `StudentShell.tsx:33` ("never uses this frame on the ORT lobby and
  attempt routes (§2.4)"), `lib/fonts.ts:5-10` (lobby/attempt frames keep the system font), `tailwind.config.ts:19`
  (same), `styles/globals.css:68-69` (same), `STUDENT_UI_DESIGN.md` lines 25, 79 and §2.4 (line 128) → point to this
  section (SF-1).
- **Not removable as planned (keep, with reason)**: `EXAM_COLUMN_OUTER/INNER` (`ui/shellWidth.ts`, `LmsShell.tsx`):
  still the column of result/review pages outside the student shell (staff previews, template sandbox, a teacher
  awaiting the course's area) = "staff keep today's frames"; `StudentCourseHeader`'s `breadcrumbs` prop: exam-prep
  course pages outside the own-title list in `layout.tsx` (e.g. `/grades`, `/pages/{id}`) still render it with
  `breadcrumbs={false}`; dropping the prop needs those pages to get their own title first (F4b/F5 decision, not F2c);
  `results.back`: general-course students keep "Назад к заданию" to the lobby (guarded by
  `e2e/scrolling-player.spec.ts:273`); exam-prep students get `results.backToTests`.

**Files**: `LmsShell.tsx`, `courses/[courseId]/layout.tsx`, `assessments/[assessmentId]/page.tsx`,
`attempts/[attemptId]/result/page.tsx`, `results/StudentResult.tsx`, `ResultSummary.tsx`, `GradeBadge.tsx`,
`ReviewItemCard.tsx` (id only), new `results/ExamResultHero.tsx`, `results/SectionBreakdown.tsx`,
`assessments/LobbyView.tsx`, `home/MyAttemptsPanel.tsx`, `grading/registry.py`, `en/ky/ru.json`.
**Tests**: new `e2e/student-result.spec.ts` (hero, zero-raw sentence, no "Незачёт"/"Идёт в зачёт"/"Процентиль 0.0"
for an empty attempt, actions, `.student-theme` on lobby/result, player root without sidebar/tab bar at 375 and
1440); ORT suite re-recorded; `test_grading_registry.py` zero-raw `passed`; full SQLite suite.
**Slices**: **F2a (Opus)** shell/routing rule + layout + removals list; **F2b (Opus)** result page + registry
change + lobby restyle; **F2c (Sonnet)** deletions and key clean-up from F2a's list; ORT re-record + review by the
orchestrator.

## 3. Links from Сохранённые → Ошибки and from every new page

**Cause**: fixed by 2 for the frame. The anchor: `components/lms/progress/SavedPage.tsx:90` links
`/attempts/{id}/result#item-{n}` but no element on the result page has `id="item-…"` (`ReviewItemCard.tsx` has no
id; `ScrollingItems.tsx:25` `section#item-<pos>` is the player). The review also loads after the page, so even
an existing id would not scroll. `MistakesList.tsx` links `/result` without an anchor.
**Fix**: 2.2 item 7 (ids + scroll-after-load, "only mistakes" off when a hash targets a correct item); `MistakesList`
rows get `#item-{position}` too. **Every link from the new pages, verified one by one** (all lead to a
`.student-theme` page after 2): home Next card → lobby; "Продолжить урок" → `/modules/{m}/items/{i}`; Мои курсы rows
and the exam sheet → `/courses/catalog`, `/courses/join`, `/unlock`; Тесты cards → lobby, "Результат" →
`/attempts/{id}/result`, locked → `/unlock`; Аналитика weak topic "Практика" → `PracticeDialog`, empty state →
`/courses/{c}` (redirects to `/tests`); Сохранённые → result anchor; Видеоуроки → lesson pages, `/pages/{id}`;
Практика list → practice lobby (`/assessments/{a}`); account sheet → `/privacy`, `/me` (person page), language.
**Test**: `e2e/student-links.spec.ts`: for each new page, every internal `a[href]` is visited and the document root
contains `.student-theme` (or is the player route); the saved-item link lands with the target card in view
(`student-saved.spec.ts:139` extended). **Slice F3 (Opus, small, together with F2b)**.

## 4. Colours and analytics data

### 4.1 Calm colour system (student area only; concrete tokens)
- **One brand blue**: the `.student-theme` scale (`globals.css:89-103`, 600 `#1a70d8`) for every primary button,
  link, focus ring, active state, progress bar, "В процессе" pill (brand-50 / brand-700) and all chart bars that
  are not accuracy. Sidebar gradient unchanged.
- **Gold only for money**: `GoldPill` (unlock / "Доступ до"), the "Платный"/"Pro" chip, the golden-certificate
  badge. Nowhere else (drop the gold streak flame tint).
- **Section tags neutral**: `SectionTag` gets one tone: bg `#eef2f7`, text `#334155`, border none; the
  `tag.math1…grammar` map in `tailwind.config.ts` and `STUDENT_UI_DESIGN.md` §1 is removed. The current section
  of a page may use brand-50 / brand-800 as the one subtle tint.
- **Colour only for accuracy**: keep `acc.low/mid/high` (`#f43f5e` / `#f59e0b` / `#10b981`, text `#be123c` /
  `#b45309` / `#047857`) on meters, rings and the percent number; always next to the number and the band word.
  Correct / wrong in the activity bars: `acc.high` and hatched `acc.low` (as now).
- **Removed hues**: violet, teal, orange: `StatTile iconTone` (`AnalyticsOverview.tsx:115-123` blue/green/
  violet/orange → one brand tone), `analyticsData.ts:19-25` `SECTION_FILL` five hues → a brand ramp
  (700/500/300/200/100, legend keeps the names), `chart.3/4/5` tokens deleted, `NextCard` violet accent (review
  10) deleted, `courseColor.ts` bands deleted in 7, status pills: "Не начат" neutral, "Пройден" success-50/700.
- **Heatmap** keeps its blue ramp (`heat.0…4`). Danger red only for errors, deadlines and the low band.
- Apply across: `ExamPrepHome.tsx`, `StreakCard.tsx`, `TestsPage.tsx`, `AnalyticsOverview.tsx`, `TopicCards.tsx`
  (`RING`), `ActivityCards.tsx`, `MonthHeatmap.tsx`, `SavedPage.tsx`, `StudentSyllabus.tsx`, `unlock/page.tsx`,
  `GoldPill`, `SectionTag`, `tailwind.config.ts`, `globals.css`; record the token table in `STUDENT_UI_DESIGN.md` §1.

### 4.2 Data bug: "Вопросов решено 1, верно 0 из 1" vs "40 ответов" in weak topics
**Cause** (two different definitions and two different periods):
1. The tiles read `activity.totals` (`AnalyticsOverview.tsx:102-103`): `backend/app/lms/progress/service.py:358-450`
   `activity()` counts items with `answered_at` set, **in the selected period** (7/30/90/365 days,
   `submitted_at >= start`), in **every** non-preview attempt (in progress included); correct/wrong only for final
   visible attempts; `partial` counts as wrong (`_WRONG`, line 34).
2. Weak topics and topic cards read `progress.by_topic` (`AnalyticsOverview.tsx:138, 141`):
   `service.py:186-236` `progress()` is **all time**, final attempts only, and **counts blank items as answers**
   (line 208: "`pending` items are not counted, `unanswered` are"; the filter is `correctness != 'pending'`, so
   `unanswered` rows, which have `answered_at` null, enter the per-topic totals with weight 0). An ORT attempt
   submitted with one chosen answer therefore gives "1 решён" on top and 39 "answers" at 0 % in the topics.
**Fix: one definition, one period, one query family** (`progress/service.py`; Opus):
- *Answer* = an `attempt_items` row with `answered_at` not null, in a **final** (`graded`/`needs_review`), non-preview
  attempt of the course whose assessment results are visible (`visible_assessments`). In-progress attempts count
  nowhere (the ORT attempt is timed and becomes final by itself); blank items count nowhere.
- *Correct* = `correctness == 'correct'` + 0.5 × `partial`; *graded* = answers whose correctness is not `pending`;
  accuracy = correct / graded. Same weights in `progress.by_section`, `by_topic`, `activity.days.correct/wrong`
  (`wrong` = incorrect + partial, `correct` keeps the 0.5 rule in the accuracy only) and `activity.totals`.
- *Period*: `GET /courses/{c}/my/progress?days=7|30|90|365` (optional; absent = all time for the home and the goal).
  The analytics page passes the same `days` to both calls; tiles, weak topics, activity bars, topic cards and
  study time all use it and say "за 30 дней". Streak, heatmap and `open_mistakes` are all time and labelled so.
- Invariant to test: for the same user, course and period, `sum(by_topic.total)` = `sum(by_section.total)` =
  `activity.totals.answered` (topics without a `topic` value go to an "Без темы" bucket so the sums match).
**Tests** (`tests/lms/test_progress.py`, `test_activity_saved.py`): blank items counted nowhere; an in-progress
attempt counted nowhere until final; partial = 0.5; the sum invariant on SQLite and PG; `days` filter on
`progress`; invalid `days` → 422; another student 403 (unchanged).

### 4.3 Minimum data before anything is rated
Server-side constants in `progress/service.py` and fields on the schema (one rule for every client):
`TopicStat.rated` = graded ≥ **5**; `SectionStat.rated` = graded ≥ **10**; `ProgressOut.weak_topics_ready` =
≥ 3 rated topics. Frontend: unrated topic rows show "Мало данных · 3 из 5 ответов" in grey (no band, no percent);
the weak-topics card renders only when `weak_topics_ready`, else the "Пока мало данных" mascot card with "Ответьте ещё
N вопросов, и здесь появятся слабые темы"; section rows on the home follow `SectionStat.rated`. Remove the
duplicate client threshold in `analyticsData.ts` (`isGraded`, `weakestTopics`) in favour of the fields.

### 4.4 Teacher analytics review (same eyes), with fixes in this step
- **T1 Two means for one quiz**: `backend/app/lms/analytics/service.py:222-233` `quiz_rollup` averages **every
  counted attempt**; `statistics/compute.py:27-35` uses the **first counted attempt per student**. The quizzes tab
  and the quiz statistics page show different "Средний %" for the same test. Fix: `quiz_rollup` uses the first
  counted attempt per student (same CTE), label "по первой попытке" in both places.
- **T2 "Missing" without a due date**: `service.py:214` `missing = … if past else 0`; exam-prep assignments have no
  due date, so the column shows a confident "0". Fix: `missing` null when there is no due date, "—" in the table.
- **T3 Two columns for the same state**: `modules_page` (`service.py:170-178`) shows "Доступен" (`unlocked`) and
  "Не начат" (no progress row) side by side; a teacher reads them as different things. Fix: "Не начат" =
  `not_started + unlocked`; columns: завершили, начали, не начали, заблокировано.
- **T4 Spread tile**: `QuizStatsView.tsx:88` "Разброс" (standard deviation) means nothing to a teacher. Fix: show
  "Учеников" (distinct students) in its place; stddev stays in the API.
- **T5 Score distribution is submissions-only** (`service.py:112-130`): correct for both kinds since
  `assignments/sync.py` creates assignment rows for quizzes; keep, but the overview tile says "по сданным работам".
- **T6 ORT scaled mean** is missing from every teacher view (raw % only). LATER: a scaled mean column when the
  assessment has a `piecewise_curve` scheme (server value), not in this step.
Tests: `tests/lms/test_analytics.py` (first-attempt mean equals the statistics mean; `missing` null without due;
module column arithmetic), `test_quiz_statistics.py` unchanged.

**Slices**: **F4a (Opus)** counting fix, `days` on progress, rated fields, teacher analytics T1–T3 + tests;
**F4b (Sonnet)** tokens and colour sweep, T4/T5 labels, keys; **F4c (Sonnet)** "not enough data" states on the
analytics page and the home per 4.3 (well-specified by F4a's fields).

## 5. Courses with lessons (outline; full design in `COURSE_LESSONS_DESIGN.md`, written before building)

**Problem**: the reference app has video courses next to tests (overview with "continue", progress, syllabus with
durations, about card, lesson page with the outline aside and "next lesson"). We have modules, items (`page`,
`file`, `assignment`/quiz, `url` with `video`, `header`; `modules/models.py:94-99`), requirements, gating, `item_progress`,
the student syllabus (`StudentSyllabus.tsx`), `LessonView.tsx`, `VideoPlayer.tsx`, `lessonNav.ts` (U7), but no
lesson durations, no course overview, no Pro tier on lessons.
**Constraints**: data changes minimal (two columns, §0); teacher editing stays today's model
(`ModuleOutlineEditor`, `AddItemDialog`); ORT tests are never gated by modules (8a); lessons free until content
exists (D9), the tier only switches a module to Pro; cover from 7 is the overview banner.
**Key decisions to write up**: (a) one course experience for exam-prep and teacher courses: `/courses/{c}/modules`
becomes the **course overview** (hero with cover, "Продолжить" = first incomplete item, progress bar "3 из 23",
syllabus grouped by module with duration per lesson and per module, about card = description + language + counts);
(b) lesson page `/modules/{m}/items/{i}` for `url` (video), `page` and `file` items: content, module outline aside
(desktop) / collapsible (phone), prev/next, "Отметить как пройденный" (existing `mark_done`); quiz items link to
the lobby; (c) `duration_s` entered by the teacher (minutes field; optional; YouTube gives none without an API key);
(d) `access_tier` on the module: `paid` modules show the lock overlay + gold pill for students without a pass
(server: `ItemStudentOut.locked_reason = access_required`, the page/file/url endpoints refuse with
`access_required` like paid exams; staff and test students never locked); (e) sidebar: "Уроки" item appears when
the course has published modules with lessons; Тесты stay the test library; the overview lists tests only as
"Тест" rows inside modules; (f) teacher editor: a visual pass (add video / page / file / test buttons in a module,
drag reorder, publish switch per module) without new endpoints.
**Tests**: `tests/lms/test_modules_*` extended (duration, tier lock, staff bypass), `e2e/lessons.spec.ts`
extended (overview, continue, next lesson, locked module), `test_migration_0024.py`.
**Slices**: **F5a (Opus)** migration 0024 + backend (duration, tier, overview endpoint data) ; **F5b (Opus)**
student overview + lesson page; **F5c (Opus)** teacher editor pass; **F5d (Sonnet)** keys, spacing, empty states.

## 6. Subscription instead of code-first (outline; full design in `SUBSCRIPTION_DESIGN.md`)

**Problem**: S3 (`S3_ACCESS_DESIGN.md`) is code-first: batches, codes, reveal, CSV, `/unlock` with a code field.
The owner wants Free vs Pro with plans; codes only as optional vouchers; a simple "grant Pro" for admins.
**What stays** (no data loss): `access_passes` (start, end, source, revoke; `access/service.py` row lock, extension
arithmetic, resume rules §7), `activation_codes`/`batches`, `assessments.access_tier`, `practice_free`, the
`access_required` checks in the attempt engine, the countdown (independent of access already).
**Key decisions**: (a) plans are configuration, not a table: `PRO_PLANS` = `month_1` (30 days), `month_3` (90),
`season` (ends 31 May Bishkek, `ends_on` semantics); prices and "how to pay" text are admin-editable copy
(`access.howToPay`, placeholder until the owner fills it); (b) `access_passes.plan` records which plan a pass came
from (null for legacy); (c) student `/unlock` becomes `/pro`: one card "Бесплатно / Pro" with the included list
(all tests, practice, lessons marked Pro, analytics stays free per D8), the three plans, "Как оплатить" text, a
voucher field folded under "У меня есть код"; the sidebar gold pill links there; (d) admin: `/admin/access` →
"Pro": grant (user search, plan or end date, reason), list of Pro users with end dates and source, renew (= grant
extending), cancel (= revoke with reason), expiring-in-14-days filter; codes move to a second tab "Ваучеры" with
batch create / list / revoke only (reveal, CSV, given-note stay in the API, hidden behind "Ещё"); (e) `GET
/me/access` adds `plan`, `days_left`; (f) `source = payment` reserved for the provider slice.
**Automatic payment (design only; needs the owner's contract and keys)**: providers to research for Kyrgyzstan,
each with: contract and KYC, fees, hosted page vs API, webhook/callback and signature, refunds, recurring
(auto-renew) support, test environment: **MBank** (QR / "MBank Business" API), **O!Dengi / O!Bank** wallet,
**Elsom** (Elcart's wallet), **Balance.kg**, **Pay24**, **Umai**, **Элкарт** card acquiring through a local bank
(Optima, Demir, KICB, Bakai) with Visa/Mastercard, **PayBox.money** and **Freedom Pay** (Kazakh gateways that
serve KG merchants), and the national QR standard. Expectation to verify: most local wallets give a hosted
payment page with a signed callback and **no** auto-renewal; recurring charges exist only on card acquiring. The
design proposes: one `payments` table (provider, external id, amount, status, pass_id, raw callback), an
idempotent webhook endpoint, manual renewal first (a reminder 7 days before `ends_at`), auto-renew later.
**Tests**: `tests/lms/test_access.py`, `test_access_code.py` extended (plan recorded, grant by plan, legacy pass
untouched, renew extends, cancel audited), isolation; e2e `access.spec.ts` for `/pro` and the admin screens.
**Slices**: **F6a (Opus)** plans, `plan` column (already in 0024), service + admin API; **F6b (Opus)** `/pro`
page + admin "Pro" screen; **F6c (Sonnet)** copy, keys, voucher tab styling.

## 7. Catalog and course cards with cover images

**Cause**: `components/lms/course/CourseCard.tsx:93` paints a band with `courseColor(course.id)`
(`lib/lms/courseColor.ts`: eight saturated hues keyed by a hash, dark teal/green/violet among them) and stacks
badges, organization line, language line, full two-line description and a large outline action with equal
weight; `CatalogView.tsx:136-137` and `catalog/CatalogFilters.tsx` expose organization and enrollment-mode
filters to students; `CatalogCourseOut` (`courses/schemas.py:386-395`) carries no counts and no `is_platform_course`.
### 7.1 Cover image (backend, Opus)
- Column `courses.cover_asset_id` (§0). Upload `POST /courses/{c}/cover` (multipart, JPG/PNG/WebP, ≤ 2 MiB:
  `ASSET_MAX_UPLOAD_BYTES`) → `files/service.py:248` `ingest_image(... visibility="public", course_id=c)`: existing
  validation (`image_validation.py`), WebP re-encode, SHA-256 dedup, R2 public bucket under the existing
  `blob_key(sha, "public")` path served from `R2_PUBLIC_BASE_URL` (`media.py` for db/local), the free-tier guard
  (`usage.py`, `storage_full`) and the per-user quota. Server-side centre crop to **16:9, 1280 × 720** before
  encoding (one new step in `images.py`, reused nowhere else); `DELETE /courses/{c}/cover` clears the column (the
  asset is soft-deleted through the existing path). Policy: course owner / teacher with settings rights; platform
  admins for platform courses (`template_locked` ORT courses allow **only** the cover). `CourseOut`,
  `CatalogCourseOut`, `HomeCourseOut` add `cover_url` (null when none). Audit entry `course.cover_set/cleared`.
- Default cover when `cover_url` is null: generated client-side from the course id: a soft gradient from the
  student palette (brand-100 → brand-50 with a navy-800 10 % shape), a subject icon chosen by `template_key`
  (ORT: a sigma/graduation mark) or the mascot small in the corner; no dark colours; `courseColor.ts` deleted.
  The ORT courses ship with a pleasant default of this kind; the owner replaces it later through settings.
- Settings UI: "Обложка" block in `courses/[courseId]/settings/page.tsx`: current cover (default preview), file
  picker, a 16:9 preview with a simple vertical/horizontal offset slider (offset sent as `focus_x/focus_y`
  0–1 for the server crop), Save / Remove. Keys trilingual.
### 7.2 One `CourseCard` (used by catalog, home rows, "my courses", teaching list and trash)
Cover 16:9 on top (`img` with `loading="lazy"`, default cover component otherwise); title ≤ 2 lines; one meta line
"Русский · 12 тестов · 23 урока" (counts from the server: published assessments and published lesson items,
`CatalogCourseOut.tests_count`, `lessons_count`, one grouped query per page, never N+1); teacher or organization
name only when `!is_platform_course`; description ≤ 2 lines, replaced by a progress bar (`done / total` lessons,
brand) for joined courses; badges only when they matter: "Pro" (gold, platform course with paid tests), "По коду",
"Заявка"; no "Открыт для всех", no "Платформа", no status badge for students. One action: primary "Записаться" or
"Открыть" (joined); the staff list keeps its own secondary controls in the action slot.
### 7.3 Catalog page for students
Search + language chips only; organization and enrollment-mode filters move under "Ещё фильтры" (collapsed,
desktop only) and are dropped from the phone; grid `lg:3 / sm:2 / 1`; designed empty state with the mascot
(`thinking`) and the "Войти по коду" link; result count line kept. Teachers' view of the catalog unchanged.
**Risks**: ORT courses are `template_locked`: the cover endpoint must be the one allowed write; `catalog_search`
and `CATALOG_COURSE_KEYS` allow-list extended deliberately (tests assert no join code leaks). R2 usage grows by at
most ~150 kB per course.
**Tests**: `tests/lms/test_courses_api.py` (cover upload, crop size, dedup, remove, permissions incl. locked ORT and
platform admin, 413 over 2 MiB, non-image refused), `test_catalog.py` (counts, `cover_url`, allow-list), files
tests for the R2 guard path; e2e `course-cards.spec.ts` and `catalog-apply.spec.ts` updated; UX check 375/1440/1920.
**Slices**: **F7a (Opus)** backend cover + counts + schema; **F7b (Opus)** settings upload UI with preview;
**F7c (Sonnet)** `CourseCard` and catalog restyle, default cover component, deletions (`courseColor.ts`, old
badges), keys.

## 8. Slice list (build order, model per slice)

| # | Slice | Model | Needs |
|---|---|---|---|
| F1 | Sidebar group gap | Sonnet | — |
| F2a | Shell rule: lobby/result in StudentShell, player chrome-less; layout clean-up; removal list | Opus | — |
| F2b | Result page redesign, registry zero-raw `passed`, lobby/attempts restyle, review ids + hash scroll (3) | Opus | F2a |
| F2c | Delete what F2a listed; keys | Sonnet | F2b |
| ORT | Re-record 33 student baselines, before/after review, behaviour suites green | orchestrator | F2c |
| F3 | Link audit e2e (`student-links.spec.ts`), MistakesList anchors | Opus | F2b |
| F4a | Counting fix, `days` on progress, rated fields, teacher analytics T1–T3, tests | Opus | — |
| F4b | Colour tokens and sweep, T4/T5 labels | Sonnet | F2c |
| F4c | "Not enough data" states on analytics and home | Sonnet | F4a |
| F5 | `COURSE_LESSONS_DESIGN.md` (architect) → F5a migration 0024 + backend, F5b student pages, F5c teacher editor | Opus | F4 |
| F5d | Lessons keys and polish | Sonnet | F5b |
| F6 | `SUBSCRIPTION_DESIGN.md` (architect) → F6a service/admin API, F6b `/pro` + admin screen | Opus | 0024 |
| F6c | Copy, keys, voucher tab | Sonnet | F6b |
| F7a | Cover backend + counts | Opus | 0024 |
| F7b | Settings upload with preview | Opus | F7a |
| F7c | CourseCard, catalog, default cover, deletions | Sonnet | F7a |

Each slice: trilingual keys (`scripts/check_i18n_parity.py`), `npx tsc --noEmit`, backend tests on a scratch DB,
ORT suites where the frame or tokens changed, UX check at 375/1440/1920 in ru by the orchestrator. Deploys: after
1, after 2+3 (with the ORT review), after 4, after 5 (migration 0024, Neon backup first), after 6, after 7. A
Sonnet slice that comes back wrong is redone on Opus, never retried on Sonnet.

## 9. Decisions to record in `PRODUCT_DECISIONS.md`
- SF-1 Lobby, result and review live in the student shell; the player is chrome-less with the student tokens;
  ORT baselines re-approved (owner 2026-11-07, replaces §2.4).
- SF-2 Analytics: one definition (answers in submitted tests), one period per page, rated from 5 / 10 answers.
- SF-3 Colour: one blue, gold = money, neutral section tags, colour only for accuracy.
- SF-4 One migration 0024 for problems 5–7 (one Neon backup).
- SF-5 Subscription plans as configuration on `access_passes`; codes become vouchers; payment provider later.
- SF-6 Course covers: public R2, 16:9, generated default; `courseColor` retired.

## 10. Orchestrator overrides (2026-11-07)
- 2.2 item 4: **no change to `grading/registry.py`** (ORT scoring data and stored grades stay identical). "Незачёт/Зачёт"
  is hidden on student exam-prep result pages in the presentation layer (`GradeBadge` gets a `showPass` prop; student
  exam-prep pages pass false; staff and general schemes unchanged).
- 2.2 item 2: no hard-coded claims about ORT statistics ("среднее 150" etc.). The meaning line uses only server data:
  the scale (`scale_min/max`), the percentile when > 0, and thresholds configured on the server (e.g. golden
  certificate). Otherwise neutral text.
- §0: migrations are not pre-merged ahead of their designs. Each of 5, 6, 7 adds its own additive migration when its
  design is written; a Neon backup before each (owner OK 2026-11-07 to delete old backups).
