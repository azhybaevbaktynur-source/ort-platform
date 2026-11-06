# Course lessons: one course experience on top of modules (problem 5)

**Status**: design, 2026-11-07 (architect on Fable). Source: `STUDENT_UI_FEEDBACK_2026-11-07.md` problem 5,
`STUDENT_UI_FIX_PLAN.md` §5 and §10, `STUDENT_UI_DESIGN.md` §1.1 and §3.5, `PHASE_8A.md`. Reference: the reference
app's course screen (`docs/oneprep_design/`, not reproduced). Base: `lms` b2682d1, alembic head `0023_person`.

**Principle (owner)**: improve the existing architecture. Modules → items (`page`, `file`, `assignment`, `url`,
`header`), requirements, the evaluator, `item_progress` facts, the gate (`modules/gate.py`), the S3 access `Gate`
(`access/service.py`) and the U7 lesson page stay. Two columns are added, nothing is rewritten. ORT exams, player,
scoring and imports are untouched; ORT preset exams stay exempt from every module check (`_ort_exempt`).

## 1. Decisions

| # | Decision |
|---|---|
| L1 | `/courses/{c}/modules` is the **course overview** for students of every course (exam-prep and teacher courses): cover banner, "Продолжить курс", progress, syllabus by modules, about card. Same components everywhere; the shell differs (exam-prep: app sidebar; teacher course: `CourseSidebar` inside the student shell). A course with `home_kind = modules` opens here. |
| L2 | **Lesson** = a published `page`, `file` or `url` item of a published module. A `url` item whose address passes `modules/video.py` is a **video** lesson (kind label "Видео"), otherwise a **link**. Tests (`assignment` items) are steps of the syllabus, not lessons: they link to the lobby. |
| L3 | **Lesson page** `/courses/{c}/modules/{m}/items/{i}` (exists, U7) serves `url` (video/link) and `file` items and, new, `page` items (content rendered inline from `GET /pages/{id}`; `/pages/{id}` keeps working and redirects to the lesson page when `?from=module`). Outline aside on desktop, collapsible on phone, prev/next + "Следующий урок". |
| L4 | **Done** is decided on the server only (§4). No requirement on a lesson → done on view (auto). `mark_done` requirement → the button "Отметить как пройденный" (today's `POST …/done`). Other requirements as today. |
| L5 | **Pro modules**: `course_modules.access_tier` `free|paid`, default `free`. Effective only where the S3 `Gate` is effective (platform-organization course, student without an active pass, not a test student, not staff). Locked rows reveal no URL, video id, page id, file id or due date. Content routes refuse with the same 403 `access_required` as paid tests. |
| L6 | **Duration**: `module_items.duration_s` int null, set by the teacher in minutes (1–600). No YouTube/Vimeo calls. Module and course totals are sums over published items. |
| L7 | **Sidebar** (exam-prep): the "Видеоуроки" entry becomes **"Уроки"** → overview; shown when the course has at least one lesson (L2). **Тесты** stays the test library (all published assessments). A test placed in a module appears in both (ordered path vs library), never twice in the syllabus. |
| L8 | One migration **`0024_course_lessons`** (down `0023_person`), additive, no data step. Problems 6 and 7 add their own (`0025…`, `0026…`), per the §10 override. |
| L9 | Teacher editing keeps today's model and endpoints; the editor gets a visual pass (§6) and two fields. |
| L10 | Default cover when `cover_url` is absent (problem 7 not yet built): the shared `CourseCover` component (gradient from the student palette, subject mark); problem 7 adds the `cover_url` prop. |

## 2. Data (exactly)

Migration `backend/alembic/versions/0024_course_lessons.py`, `revision = "0024_course_lessons"`,
`down_revision = "0023_person"`:
- `module_items.duration_s` INTEGER NULL, CHECK `duration_s IS NULL OR (duration_s >= 60 AND duration_s <= 36000)`
  (name `duration_s_range`);
- `course_modules.access_tier` VARCHAR(8) NOT NULL DEFAULT `'free'`, CHECK `access_tier IN ('free','paid')`
  (name `access_tier_valid`).
Downgrade drops both. Models (`modules/models.py`) mirror the columns (`alembic check` clean, SQLite `create_all`).
`ids.py`: `MODULE_TIERS = ("free", "paid")`, `DURATION_S_MIN = 60`, `DURATION_S_MAX = 36000`,
`REASON_ACCESS = "access_required"`. No other table changes. Neon backup branch before the deploy (§0 of the fix plan).

## 3. API changes (no new routes except none; fields only)

Staff (`content.manage`):
- `ModuleIn` / `ModuleUpdateIn` + `access_tier: free|paid` (optional on update; never null). `ModuleStaffOut` +
  `access_tier`, `duration_s` (sum of published items), `lessons_count`.
- `ItemIn` / `ItemUpdateIn` + `duration_s: int | null` (multiple of 60 not required; the UI sends minutes × 60;
  422 `validation_failed` outside the range; `null` clears; refused on `header` and `assignment` items with 422,
  `loc=["duration_s"]`). `ItemStaffOut` + `duration_s`.
Student shape (`GET /courses/{c}/modules`, the facts routes, `progress/{eid}`), allow-list extended deliberately:
- `ItemStudentOut` + `duration_s`, `done: bool`, `locked_reason: null | "module" | "access_required"`. A row with
  `locked_reason = access_required` has `locked = true`, no `link`, no `video`, no `due_at` (the existing branch in
  `service._item_student_out` that strips a locked row; the tier check sets `locked` before it).
- `ModuleStudentOut` + `access_tier`, `access_locked: bool` (tier lock applies to this caller), `done`, `total`,
  `duration_s`. `state` and `lock_reasons` stay what the evaluator says (the tier is orthogonal, §5).
- `ModulesStudentOut` + `progress: {done, total, duration_s}` and `up_next` generalised (§4).
- `HomeCourseFeaturesOut.modules` now means "has at least one lesson" (EXISTS extended with a join on published
  non-header `page|file|url` items); `course_features` the same. Name unchanged.
- Pages: `GET /courses/{c}/pages/{id}` student path and course-file download: 403 `access_required` when every
  visible module item referencing the target sits in a tier-locked module (§5). Quiz lobby/start/hand-in inside such a
  module: the same, through `gate.require_access(assignment=…)` → the lobby shows the existing lock (`can_start`
  false, `reason = access_required`).
- Facts `POST …/view` and `…/done`: 403 `access_required` on a tier-locked item (checked in `facts._open_item`
  next to the 423).
Error order in one request: 404 (not visible) → 403 `access_required` → 423 `module_locked`. One statement
(`access.service.course_gate`) per request, only when the course has a `paid` module (skip otherwise).

## 4. Progress rules (server is the source of truth)

Per visible non-header item of a published module, `done` is:
- requirement present → `ItemEval.met` (`mark_done` = the checkbox; `view` = a `viewed` fact; `submit`/`min_*` =
  submissions, as today);
- no requirement, kind `page|file|url` → a `viewed` fact exists for (enrollment, item);
- no requirement, kind `assignment` → a submission of the assignment in `SUBMIT_MET_STATES` exists (the evaluator's
  `mem.subs`; the loader must cover assignment items without a requirement, to verify in F5a);
- locked (module or tier) → `done` is still reported truthfully (a student may have finished a module before a pass
  ended); locked rows just carry no destination.
When the client records a view (`POST …/view`, idempotent): video → on the play tap (not on page open); page →
on open; file → on the download click; link → on the open click. So "done" means the student reached the content.
Module `done/total` and course `progress` count the same rows (headers and unpublished items excluded; tests inside
modules included). The label is "Пройдено 3 из 23" (no noun). Module `state` keeps the evaluator's semantics
(requirements only; a module without requirements is `completed` once open, as in 8a) and still drives prerequisites
and the sequential rule; the bar is informational.
`up_next` ("Продолжить"): the first visible non-header item in course order that is not locked (module or tier) and
not done; none when everything open is done. For items with requirements this equals today's rule; for lessons
without requirements it now includes unviewed ones (the home "up next" card inherits this; its tests are updated).
Overview CTA: `up_next` present → "Продолжить курс" (first visit: "Начать курс"); none and a tier-locked item
remains → "Открыть доступ" (gold); none and nothing locked → "Курс пройден" with "Повторить с начала" (first item).

## 5. Pro modules: authorization

- Decided once per request by `Gate.gated` (`access/service.course_gate`): platform course and no active pass and
  not a test student. Staff (`teacher`, `assistant`), previews, org admins of the platform org (platform admins) and
  guardians' observer outline are never tier-locked; non-platform courses ignore the column (the switch is hidden
  there, the API still stores it).
- Outline: tier-locked module → every item `locked = true, locked_reason = access_required` (module lock reasons win
  when the module is also `locked` by rules: `locked_reason = module`), `access_locked = true` on the module.
- `gate.require_access` gains the tier step after the ORT exemption and the "referenced by a live item" check and
  before the module evaluation: if every live, published item referencing the target lies in a `paid` module and the
  caller is gated → `access_required()`. A target referenced by a free module too stays open (same "any open
  reference" rule as the module gate). `url` items have no content route: the outline is the only place, covered.
- The lesson page never builds an embed or an anchor from client state: it renders a lock card when `locked` and
  shows "Открыть доступ" (`/courses/{c}/unlock`) when `locked_reason = access_required`, the module reason otherwise.
- ORT preset exams inside a paid module: exempt as today (their own `access_tier` governs them; ORT unchanged).
- Prerequisite chains: a free student cannot complete a paid module, so a later free module requiring it stays
  locked with "Finish A first". Honest; the editor warns ("Pro module as prerequisite of a free module").

## 6. Teacher editor (today's model, better design; no new endpoints)

Per module header: drag handle, title (inline edit), "N уроков · 48 мин", **Pro switch** (platform courses only, gold
pill when on; confirm text: "Студенты без доступа увидят только названия"), publish switch (existing toggle), menu
(unlock date, sequential, completion mode, prerequisites, duplicate, delete: today's dialogs). Per item row: kind
icon (Видео / Ссылка / Страница / Файл / Тест / Заголовок), title, duration chip ("6 мин", click → inline minutes
field; hidden on tests and headers), requirement chip, publish toggle, ↑ ↓ buttons (always rendered, visible on
hover/focus; keyboard path exists), drag on ≥ lg (exists). "Добавить" row under each module with five buttons:
**Видео** (dialog: URL field with a client-side "YouTube/Vimeo detected" hint using a TS port of `parse_video`'s
rules, title, minutes; server stays the judge), **Страница** / **Файл** / **Тест** (today's `AddItemDialog` tabs; the
test tab keeps "New quiz"), **Ссылка** (today's inline URL form + minutes). Reorder stays `PUT …/items/order` and
`PUT …/modules/order`. The editor never computes locks; warnings come from `ModuleStaffOut.warnings` plus one
client-side warning for the prerequisite case in §5.

## 7. Layouts (ru)

### 7.1 Overview `/courses/{c}/modules`
```
1440                                                              375
┌ sidebar ┬──────────────────────────────────────────────────────┐ ┌──────────────────────────┐
│         │ ┌ cover 16:9 banner (cover_url or CourseCover) ─────┐ │ │ cover banner (16:9)      │
│ Главная │ │ ОРТ (на русском)         [Продолжить курс →]     │ │ │ ОРТ (на русском)         │
│ Тесты   │ │ Пройдено 3 из 23 ▮▮▮▯▯▯▯▯ 13 % · ≈ 4 ч 10 мин    │ │ │ [Продолжить курс →]      │
│ Аналит. │ └───────────────────────────────────────────────────┘ │ │ 3 из 23 ▮▮▯▯▯ 13 %      │
│ Сохран. │ ┌ Программа ──────────────────────┐ ┌ О курсе ─────┐ │ │ Программа                │
│ УРОКИ   │ │ ▾ 1 Математика I  1/5 · 32 мин  │ │ описание…    │ │ │ ▾ 1 Математика I 1/5     │
│ Уроки   │ │   ✓ Сравнение величин   ▶ 6 мин │ │ Русский      │ │ │   ✓ Сравнение… ▶ 6 мин   │
│  ↳ Мат. │ │   ○ Приёмы сравнения    ▶ 8 мин │ │ 5 модулей    │ │ │   ○ Приёмы…    ▶ 8 мин   │
│ ПРАКТИКА│ │   ○ Разбор 10 задач     ▤ 10 мин│ │ 23 урока     │ │ │   ○ Разбор…    ▤ 10 мин  │
│ Тесты   │ │   ○ Тест: Математика I  ✎ тест  │ │ 4 теста      │ │ │   ○ Тест…      ✎        │
│ Практика│ │ ▸ 2 Математика II 0/6 · 41 мин  │ │ [mascot]     │ │ │ ▸ 2 Математика II 0/6    │
│         │ │ ▸ 3 Аналогии  🔒 Pro  0/4       │ └──────────────┘ │ │ ▸ 3 Аналогии 🔒 Pro      │
│ ★ Pro   │ │ ▸ 4 Чтение    🔒 после модуля 3 │                  │ │ О курсе (compact card)   │
└─────────┴─┴─────────────────────────────────┴──────────────────┘ └──────────────────────────┘
```
Grid ≥ 1024: content 1fr + about 320 px; modules are `details` groups, the current one open. Row = status mark (✓ /
○ / 🔒), title (2 lines max), kind icon + duration or "тест". A Pro module shows the gold pill and a greyed row list
(titles and durations only). Teacher courses: identical, inside the course sidebar.

### 7.2 Lesson page `/courses/{c}/modules/{m}/items/{i}`
```
1440                                                              375
┌ sidebar ┬───────────────────────────────────┬──────────────────┐ ┌──────────────────────────┐
│         │ ‹ Программа · Математика I · 2/5  │ Программа курса  │ │ ‹ Математика I · 2/5     │
│         │ Приёмы быстрого сравнения  ▶ 8 мин│ ▾ 1 Математика I │ │ Приёмы быстрого сравнения│
│         │ ┌ navy card ▶ (click-to-load) ──┐ │  ✓ Сравнение …   │ │ ┌ ▶ player card ───────┐ │
│         │ │          16:9                 │ │  ● Приёмы …      │ │ │        16:9          │ │
│         │ └───────────────────────────────┘ │  ○ Разбор …      │ │ └──────────────────────┘ │
│         │ [Отметить как пройденный] (if req)│  ○ Тест …        │ │ ▸ Программа курса (2/5)  │
│         │ описание урока / page body / file │ ▸ 2 Математика II│ │ page body / file card    │
│         │ ← Сравнение величин   Следующий → │ ▸ 3 Аналогии 🔒  │ ├──────────────────────────┤
│         │                                   │ (sticky, scroll) │ │ ← Назад  [Следующий →]   │ sticky
└─────────┴───────────────────────────────────┴──────────────────┘ └──────────────────────────┘
```
Aside 320 px sticky; only the current module open. Phone: the outline is a collapsible under the content; a sticky
bottom bar holds prev / "Следующий урок" (next locked → the lock pill, disabled). Locked lesson: the lock card with
the reason and "Открыть доступ" or "К программе"; no iframe, no anchor.

### 7.3 Teacher editor (course page, modules outline)
```
1440                                                              375
┌ ≡ 1 Математика I  5 уроков · 32 мин   [Pro ○] [Опубл. ●]  ⋯  ┐ ┌ ≡ 1 Математика I     ⋯ ┐
│   ≡ ▶ Сравнение величин        [6 мин] [треб.] [●] ↑ ↓   ⋯  │ │ 5 уроков · 32 мин       │
│   ≡ ▤ Разбор 10 задач          [10 мин]        [●] ↑ ↓   ⋯  │ │ [Pro ○] [Опубл. ●]      │
│   ≡ ✎ Тест: Математика I               [≥ 60%] [●] ↑ ↓   ⋯  │ │ ▶ Сравнение…  6 мин  ⋯  │
│   + Видео  + Страница  + Файл  + Тест  + Ссылка              │ │ ▤ Разбор…    10 мин  ⋯  │
├──────────────────────────────────────────────────────────────┤ │ ✎ Тест…       ≥60%   ⋯  │
│ ≡ 2 Математика II …                                          │ │ + Добавить ▾            │
```
Phone: ↑ ↓ live in the row menu (⋯) together with duration, publish and delete; no drag.

## 8. Frontend pieces

- `StudentSyllabus.tsx` → the overview (banner block, progress block, syllabus list, about card); `StudentModulesView`
  stays for org admins / observers. `LessonView.tsx` gets the aside/collapsible (`LessonOutline`), the page kind and
  the sticky pager; `lessons.ts` gains `isDone`, `nextOpen`, `formatDuration`; `lessonNav.ts` unchanged.
- `components/lms/course/CourseCover.tsx` (default cover; problem 7 reuses it). `components/lms/modules/
  ProLockCard.tsx` reuses the lock overlay component of the Тесты page (gold pill).
- `StudentShell`: `student.nav.lessons` label becomes "Уроки" (ky "Сабактар", en "Lessons"); icon stays.
- `ModuleOutlineEditor.tsx`, `AddItemDialog.tsx`, `OutlineDialogs.tsx`: §6; `lib/lms/video.ts` (TS parse hint).
- Keys under `modules.overview.*`, `modules.lesson.*`, `modules.editor.*`, `modules.tier.*`, in en/ky/ru; parity.

## 9. Tests

Backend (SQLite scratch; PG parity in CI):
- `tests/test_migration_0024.py`: upgrade from 0023 adds both columns with defaults/CHECKs; downgrade drops them;
  existing rows read `access_tier = free`, `duration_s = null`.
- `test_modules_api.py` (+): `duration_s` accepted on page/file/url, 422 on header/assignment, out of range, null
  clears; `access_tier` create/patch/default; `ModuleStaffOut.duration_s`/`lessons_count` sums; template-locked ORT
  course: modules editing as in 8a (no change).
- `test_modules_tier_lock.py` (new, `access_support` + `modules_support`): platform course, student without a pass:
  every row of a `paid` module is `locked`, `locked_reason = access_required`, no `link`/`video`/`due_at`, title,
  kind and `duration_s` present; the raw JSON of the outline contains neither the stored URL, the video id, the page
  id nor the file id (string search); `POST view`/`done` → 403 `access_required`; `GET /pages/{id}` → 403 when
  referenced only by the paid module, 200 when a free module also references it; file download → 403; quiz lobby in
  the paid module → `can_start false, reason access_required`, start → 403; ORT preset exam in the paid module →
  startable; with an active pass → everything open; expired pass → locked again; test student, teacher, assistant,
  platform admin → open; non-platform course with a `paid` module → open; `paid` + rules-locked module →
  `locked_reason = module`, 423 on facts.
- `test_modules_progress.py` (new): done definitions per kind (view fact, mark_done tick/untick, submission), headers
  and unpublished excluded, module `done/total/duration_s`, course `progress`, `up_next` = first open not-done item
  (none when complete), `view` recorded once (idempotent), `progress/{eid}` staff read returns the same numbers.
- `test_home*.py`: `features.modules` false for a published module with only a header, true with one lesson.
- `test_modules_serializers.py`: allow-list snapshot updated (new fields only, nothing else leaks).
Frontend: `npx tsc --noEmit`; `scripts/check_i18n_parity.py`; e2e `lessons.spec.ts` extended (overview continue →
first unviewed lesson, play tap records the view, "Следующий урок", page lesson inline, Pro module: pill, no iframe,
no `href` to the URL, unlock link; teacher: add video with minutes, keyboard reorder, Pro switch, publish). ORT suite
(`ort`, `ort-visual`) unchanged and green. UX check 375 / 1440 / 1920 ru by the orchestrator.

## 10. Slices

| Slice | Model | Content | Gate |
|---|---|---|---|
| F5a | Opus | migration 0024, models, ids, schemas, service (duration, tier, done/progress/up_next, tier lock in outline, gate and facts), pages/files/assessments through `require_access`, home features, all backend tests | SQLite suite green; PG `alembic upgrade head && alembic check`; migration tests; route inventory |
| F5b | Opus | student overview, lesson page (aside/collapsible, page kind, pager), `CourseCover`, Pro lock card, sidebar label, view-on-engagement, e2e | tsc, parity, `lessons`, `student-shell`, ORT e2e |
| F5c | Opus | teacher editor pass (§6), video dialog with TS hint, minutes chip, Pro switch, ↑ ↓, prerequisite warning, e2e | tsc, parity, `modules` e2e |
| F5d | Sonnet | ky/ru wording, empty states (mascot: no lessons yet / all done), spacing, the orchestrator's UX-check fixes | parity, tsc |
Deploy after F5a–F5c together (one Neon backup `backup-2026-11-0x-before-0024`), F5d may follow without a migration.

## 11. Risks

- `up_next` semantics change touches the home card and its tests (deliberate; listed in §4).
- View-on-play for video changes when a `view` requirement is met (later than page open); no production course uses
  lesson requirements yet (every course `home_kind = assignments` at 8a deploy; confirm in F5a with one query).
- Tier check adds one statement per request only in courses with a `paid` module; the outline already evaluates.
- Prerequisite chains across Pro modules (§5) can lock free modules; warning in the editor, no server rule.
- `require_access` is shared by assignments, pages, files and attempt start: the tier step must keep the ORT exemption
  first and the "any open reference" rule; the tier-lock test file covers each caller.
- Problem 7 lands after 5: the banner uses the default cover until `cover_url` exists (L10); no coupling in code.
- Allow-list schemas: every new student field is added on purpose; the serializer snapshot test guards leaks.

## 12. Open questions (defaults in effect)

- Q1 "Уроки" vs "Видеоуроки" as the sidebar label: default "Уроки" (lessons are also pages and files).
- Q2 Should a teacher be able to make a module Pro in a non-platform course once tutors can sell courses? Default:
  hidden now; the column is ready.
- Q3 Count tests inside modules in "Пройдено N из M"? Default yes (they are steps of the path).
