# Student area redesign: design and slice plan

**Status**: design, 2026-11-06 (owner: "the student dashboard is still bad and dull; take the reference app's page design,
organisation, colours, contours, analytics page and video courses"). Scope: the student area only. Teacher, organization
and platform areas keep the current `AppHeader` shell (decision §8.1). ORT lobby, player, result and review keep their
frames to the pixel (AGENTS.md §6.9). No code in this document; the slices in §6 are the build order.

What we take from the reference app: a dark left sidebar with a white-pill active item and small-caps group labels, an exam
switcher at the top of it, flat white cards with a 1 px border and no shadow, generous whitespace, tinted pill tags per
subject, big plain numbers in stat tiles, three-band accuracy bars, a calendar heatmap, blurred "unlock" overlays, a
gold "unlock" pill, and a course syllabus with a progress bar and an "about" side card. What we do not take: its name,
logo, mascot, illustrations, its blue, and its AI-credit metering.

Current screens (ru, before): the home is a title "Панель" over two course cards and an empty page; the ORT page is three
white tiles, a pale "next" band, a line chart with one point, five grey bars and two test cards. Nothing greets the
student, nothing shows activity, and every card has the same weight.

## 1. Tokens

Fonts: **Inter** (variable, 400–700) through `next/font/google` with subsets `latin`, `cyrillic`, `cyrillic-ext`
(Kyrgyz ң ө ү are U+04A2/04E8/04AE, in `cyrillic-ext`; without that subset they fall back). Self-hosted at build by
Next, served from `/_next/static` (CSP `font-src 'self'` already allows it), `display: "swap"`, about 2 × 45 kB woff2.
DM Sans was checked and rejected: Google serves it with `latin` and `latin-ext` only. The font is applied by a class on
the student shell only, **never on `<html>` and never on the `AppHeader` frame**: teacher/admin areas and the lobby and
attempt routes keep the system stack (§2.4), so the ORT baseline screenshots stay identical.

| Token (Tailwind / CSS var) | Value | Use |
|---|---|---|
| `bg` / `--c-bg` | `#f8fafc` (slate-50) | page background (unchanged) |
| `surface` / `--c-surface` | `#ffffff` | cards, sidebar pills, inputs |
| `border` / `--c-border` | `#e2e8f0` (slate-200); subtle `#f1f5f9` | card borders, dividers |
| `ink` text | 900 `#0f172a`, 700 `#334155`, 500 `#64748b` | title, body, meta (unchanged slate) |
| `brand` | 50 `#eff6ff`, 100 `#dbeafe`, 200 `#bfdbfe`, 600 `#2563eb`, 700 `#1d4ed8`, 800 `#1e40af` | primary button, links, focus ring, the Next card tint (unchanged) |
| `navy` (sidebar) | 800 `#1b2a4a`, 900 `#13203a`; hover `rgba(255,255,255,.08)`; group label `rgba(255,255,255,.62)`; icon `rgba(255,255,255,.72)`; active pill `#ffffff` with text `#1b2a4a` | the student sidebar, the phone top bar's brand mark, the "More" sheet header. Our own deep navy (the mascot's outline), not the reference's teal |
| `tag.math1` | bg `#e0f2fe` fg `#075985` | section pill "Математика I" |
| `tag.math2` | bg `#e0e7ff` fg `#3730a3` | "Математика II" |
| `tag.analogies` | bg `#ede9fe` fg `#5b21b6` | "Аналогии" |
| `tag.reading` | bg `#ccfbf1` fg `#115e59` | "Чтение" |
| `tag.grammar` | bg `#ffedd5` fg `#9a3412` | "Грамматика" |
| `acc.low` / `mid` / `high` | `#f43f5e` / `#f59e0b` / `#10b981`; text `#be123c` / `#b45309` / `#047857` | accuracy bands < 60 %, 60–84 %, ≥ 85 % (always with the number, colour is never the only signal) |
| `heat.0…4` | `#eef2f7`, `#c7d7fb`, `#8fb0f6`, `#4f82ee`, `#1d4ed8` | activity heatmap (0, 1–4, 5–14, 15–29, 30+ answers a day) |
| `chart.1…5` | `#2563eb`, `#10b981`, `#f97316`, `#8b5cf6`, `#f59e0b` | bars and lines; correct = chart.2, wrong = `acc.low` |
| `gold` | pill bg gradient `#fef3c7 → #fde68a`, border `#fcd34d`, text `#78350f` | "Открыть все экзамены" pill, paid badges, achievements (existing `gold-*` scale) |
| `success` / `warning` / `danger` | emerald / amber / red 600 and 700 (unchanged) | states |
| radius | `sm` 8 px, `control` 12 px (buttons, inputs, sidebar pills), `card` 16 px, `pill` 9999 | |
| spacing | 4 px scale; card padding 16 px (phone) / 20 px; section gap 24 px; sidebar 264 px; phone top bar 56 px; bottom tab bar 64 px + `env(safe-area-inset-bottom)`; content max 1200 px | |
| shadow | none on cards; `shadow-lg` only on popovers and the phone sheet | flat design |
| type | title 24/32 bold (28/36 from `lg`), section 18/28 semibold, body 16/24 (15/22 from `lg` optional), small 14/20, meta 12/16, stat number 32/36 bold `tabular-nums` | |
| lock overlay | `backdrop-filter: blur(6px)`, white at 72 %, centred icon + title + one line + gold pill | locked analytics or lessons |

Tailwind: add `navy`, `tag`, `acc`, `heat`, `chart` under `theme.extend.colors`, `fontFamily.sans = ["var(--font-inter)", ...system stack]`
and `fontFamily.system = [system stack]`; the same values as `:root` CSS variables in `globals.css` so the service worker's
offline page and the sanitizer-rendered pages use them too. No dark mode.

### 1.1 Owner palette: "Sky and teal" (owner 2026-11-06, replaces the grey/navy values above for the student frame)
The owner found the grey look dull and chose this palette. It applies **only inside the student frame** (a class on the
`StudentShell` root overrides CSS variables); teacher/admin frames, the ORT lobby and attempt routes keep today's colours
(ORT parity). `brand` becomes CSS-variable driven (`rgb(var(--brand-600) / <alpha-value>)`, defaults = today's blue).

| Token | Value |
|---|---|
| sidebar | gradient `#0E4A6B → #13698F`; active pill white, text `#0E4A6B`; hover white 10 % |
| page bg | `#EEF6FC` |
| home hero | gradient `#DFF1FF → #F5FBFF` with the mascot |
| primary (`brand` in the student frame) | 600 `#1E7BEA`, 700 `#1764C4`, 50 `#EAF4FE`, 100 `#D4E9FD` |
| accent | violet `#7C3AED` (the main "Начать тест" call and highlights) |
| unlock | gold `#FDE68A` / `#F59E0B` (unchanged) |
| stat tile icons | on pastel: blue `#DBEAFE/#1D4ED8`, green `#DCFCE7/#15803D`, violet `#EDE9FE/#6D28D9`, orange `#FFEDD5/#C2410C` |
| correct / wrong | `#16A34A` / `#EF4444` |

Built (2026-11-07): `.student-theme` in `globals.css` on the `StudentShell` root; `brand-600` is `#1A70D8` (the owner's
`#1E7BEA` gives white button text only 4.1:1, so it became `brand-500`); `navy-800` is `#0E4A6B` inside the frame;
group labels white 80 % (4.5:1 at the gradient's light end). Teacher/admin/ORT frames keep `:root` = the old blue.

## 2. Shell

### 2.1 Where it applies
`LmsShell` picks the frame from `activeArea`: `learning` → the new `StudentShell`; every other area → the current
`AppHeader` frame. A teacher's `/courses?view=learning` is therefore the student shell too. Exception (§2.4): the ORT
lobby and attempt routes render the current frame regardless.

### 2.2 Desktop (≥ 1024 px): sidebar, ru labels
```
┌──────────────────┬─────────────────────────────────────────┐
│ ▣ Платформа      │  (content, max 1200 px, 32 px gutters)  │
│ [ОРТ рус][ОРТ кы]│                                         │
│ [+]              │                                         │
│ ● Главная        │                                         │
│   Аналитика      │                                         │
│   Сохранённые    │                                         │
│ УРОКИ            │                                         │
│   Видеоуроки     │                                         │
│   ↳ Математика   │ (first 5 published lesson modules)      │
│ ПРАКТИКА         │                                         │
│   Тесты          │                                         │
│   Практика       │                                         │
│   Мои ошибки     │                                         │
│                  │                                         │
│ ◔ Начало работы 2/4                                        │
│ ★ Открыть все экзамены   (gold pill; or "Доступ до 31 мая")│
│ ⇩ Установить приложение  (hidden when installed)           │
│ ДРУГИЕ РАЗДЕЛЫ: Преподавание · Админ-панель (only if held) │
│ (●) Имя Фамилия  ⚙  → язык, Конфиденциальность, Выйти      │
└──────────────────┴─────────────────────────────────────────┘
```
- The **exam switcher** lists the student's exam-prep courses (`HomeCourseOut.student_layout == "exam_prep"`, §4.1) as
  chips; "+" opens `/courses/catalog`. The chosen one is the **current course** (`localStorage`, default: the last
  opened; one course: no chips, its title under the brand). Every per-course link uses its id. A student with no
  exam-prep course sees only Главная, Сохранённые and the bottom block; Главная then shows the join cards.
- Links: Главная `/courses`; Аналитика `/courses/{c}/progress`; Сохранённые `/courses/{c}/saved`; Видеоуроки
  `/courses/{c}/modules` (sub-links `#module-{id}`); Тесты `/courses/{c}/tests`; Практика `/courses/{c}/practice`;
  Мои ошибки `/courses/{c}/progress?tab=mistakes`. Items appear only when the course has them (`features`).
- Keys: `student.nav.*` (`home`, `analytics`, `saved`, `lessonsGroup`, `lessons`, `practiceGroup`, `tests`,
  `practice`, `mistakes`, `gettingStarted`, `otherAreas`); ky: Башкы бет, Аналитика, Сакталгандар, САБАКТАР,
  Видеосабактар, МАШЫГУУ, Тесттер, Машыгуу, Менин каталарым, Баштоо, Башка бөлүмдөр.
- The course sidebar (`CourseSidebar`: Курс, Задания, Оценки, Преподаватели, Мой прогресс) is **not shown** inside
  exam-prep courses (the app sidebar replaces it); teacher-made courses keep it inside the new shell. The breadcrumb
  "Мои курсы › ОРТ" and the "Покинуть курс" link move to the course's Тесты page footer.

### 2.3 Phone (< 1024 px): top bar + bottom tab bar + "More" sheet (decision: tab bar, not a drawer)
Teenagers on Android with the PWA installed: a bottom bar is thumb-reachable and reads as an app; a drawer hides
everything behind one tap. Top bar 56 px: brand mark, current course chip (tap: switcher sheet), avatar (account sheet).
Bottom bar 64 px, five fixed slots: **Главная · Тесты · Практика · Аналитика · Ещё** (icon + 11 px label, 44 px
targets, `aria-current`). "Ещё" opens a bottom sheet with the rest of §2.2 (Видеоуроки, Сохранённые, Мои ошибки, Начало
работы, Открыть все экзамены, Установить, other areas, language, Выйти). `<main>` gets `padding-bottom: 80px +
safe-area`. Without an exam-prep course the bar shows Главная · Каталог · Ещё.

### 2.4 ORT frames (must not change)
`/courses/{id}/assessments/{aid}` (lobby) and `/courses/{id}/attempts/**` (player, result, review) render exactly the
current frame: `AppHeader`, course frame, `EXAM_COLUMN_*`, system font, no sidebar and no bottom bar. `LmsShell`
decides by path before the area rule. The baseline suite (`docs/phases/ORT_BASELINE/`) is the proof.

## 3. Pages

Data below is one request each unless stated; every page has skeleton, empty (mascot), error with retry; nothing
horizontal-scrolls at 375 px; the one primary button per screen is brand-600.

### 3.1 Главная `/courses` (exam-prep student)
Purpose: "what should I do next, and how am I doing". Sources: `GET /me/home` (courses, todo, results),
`GET /courses/{c}/exam-prep` (exam_date, goal, latest, history, sections, next, needs_pass), `GET /courses/{c}/my/activity?days=30`
(§4.2, streak and heatmap; the page renders without it). Free: all of it. Locked: none; the unlock card shows only
while `needs_pass`.
```
1440                                                     375
┌─────────────────────────────┬───────────────────────┐  ┌────────────────────┐
│ Добрый день, Айбек  [🐆]    │ [30 дн][07 ч][59 мин] │  │ Добрый день, Айбек │
│ До ОРТ 30 дней · 6 декабря  │ до экзамена ✎          │  │ 30 дн  07 ч  59 мин│
├─────────────────────────────┴───────────────────────┤  ├────────────────────┤
│ СЛЕДУЮЩИЙ ШАГ  Пробный тест 2  [Начать тест →]      │  │ СЛЕДУЮЩИЙ ШАГ      │
├─────────────────────────┬───────────────────────────┤  │ … [Начать тест →]  │
│ Серия: 3 дня 🔥  M T W …│ Текущий 68 · Цель 200 ✎   │  ├────────────────────┤
│ (last 7 days dots)      │ (stat tiles)              │  │ 3 дня 🔥 ● ● ○ ● … │
├─────────────────────────┴───────────────────────────┤  │ 68 → 200           │
│ ★ Откройте все экзамены (gold card, mascot, ✓ list) │  │ ★ Откройте все …   │
├─────────────────────────┬───────────────────────────┤  │ Разделы (5 bars)   │
│ Разделы (5 tag+bar rows)│ Продолжить урок ▶ 3/23    │  │ Продолжить урок    │
├─────────────────────────┴───────────────────────────┤  │ Мои курсы (row)    │
│ Мои курсы: [ОРТ кырг] [Курс преподавателя] [+]      │  └────────────────────┘
└─────────────────────────────────────────────────────┘
```
Greeting by hour (`home.greeting.morning|afternoon|evening`), mascot `hello`/`celebrating` (personal best). The countdown
is three tiles (days, hours, minutes; "Сегодня" on the day). Students without an exam-prep course keep the current
dashboard (course cards, К выполнению, results, platform courses) restyled in the new tokens.

### 3.2 Тесты `/courses/{c}/tests` (new route; `/courses/{c}` redirects here for exam-prep courses)
Purpose: the library. Sources: `GET /courses/{c}/exam-prep` (sources, library_total, needs_pass), `GET …/exam-prep/library`
(paginated). Layout: title "Тесты · 12", filter chips (source modules, statuses), then cards in a 3 / 2 / 1 grid:
status pill (Не начат / В процессе / Пройден), title, "Вопросов 150 · 3 ч 35 мин", best score, primary "Начать" or
"Продолжить" or secondary "Результат". Paid cards without a pass: a lock pill "Платный", blurred score area, button
"Открыть доступ" to `/unlock`. Free: free tests and the result review. Footer: Покинуть курс.

### 3.3 Аналитика `/courses/{c}/progress` (relabelled; same route)
Purpose: the reference's analytics page on our data. Sources: `GET /courses/{c}/my/progress` (trend, by_section,
by_topic, open_mistakes), `GET /courses/{c}/my/activity?days=` (§4.2), `GET …/my/saved` count (§4.3).
```
1440                                                       375
┌ Аналитика           [30 дней ▾] [Интервал: день ▾] ┐     ┌ Аналитика  [30 д ▾]┐
│ [Вопросов 240] [Точность 64 %] [Сохранено 5] [Серия 3] │ │ 2×2 tiles          │
├────────────────────────────────────────────────────┤     ├────────────────────┤
│ 5 слабых тем      01 Уравнения · math2 · 11 отв. 38 % → Практика │ list     │
├────────────────────────────────────────────────────┤     ├────────────────────┤
│ Активность: bars per day, correct green over wrong red │ │ bars (scroll-x only│
├─────────────────────────┬──────────────────────────┤     │ inside the card)   │
│ Математика: topic rows  │ Язык: topic rows         │     │ stacked cards      │
│ ● ≥85 ● 60–84 ● <60     │ meters + %               │     │                    │
├─────────────────────────┴──────────────────────────┤     ├────────────────────┤
│ Время занятий в день (stacked by section, avg line) │     │ …                  │
│ Самое активное время (24 h bars) · Сессии (7 дней)  │     │                    │
├────────────────────────────────────────────────────┤     ├────────────────────┤
│ Моя активность: month grids heatmap, "240 ответов"  │     │ 3 months, scroll-x │
└────────────────────────────────────────────────────┘     └────────────────────┘
```
Topic rows show the section tag, attempts, a three-band meter and the percent; "Практика →" starts practice of that
section/topic (`PracticeDialog` prefilled). Free vs locked: **free by default** (D8); the design keeps a `locked`
prop on the weak-topics and by-topic cards so the owner can switch them to the blurred overlay later without a layout
change. Tab `?tab=mistakes` is the existing mistakes notebook (`MistakesList`) restyled.

### 3.4 Сохранённые `/courses/{c}/saved`
Tabs: Сохранённые (questions the student flagged during tests, from `attempt_items.flagged`) · Ошибки (the mistakes
notebook). Each row: section tag, test title, date, the question stem (two lines), "Открыть" to the review item
(`/attempts/{id}/result#item-{n}`). Source: `GET /courses/{c}/my/saved` (§4.3). Empty state: mascot `thinking`,
"Отмечайте вопросы флажком во время теста, они появятся здесь". Free. "Save from the review page" needs a table and
comes later (§7).

### 3.5 Видеоуроки `/courses/{c}/modules` (Masterclass)
Purpose: the syllabus. Source: `GET /courses/{c}/my/modules` (modules, items, progress, locks) plus `video` (§4.4).
```
1440                                             375
┌ Видеоуроки · ОРТ (на русском)    [Обзор|Программа] ┐  ┌ Видеоуроки            ┐
│ Готовы начать? Первый урок…        [Начать курс →] │  │ [Начать курс →]       │
│ Ваш прогресс ▮▮▮▯▯▯▯ 3 из 23 уроков  12 %          │  │ прогресс bar          │
│ ─ Математика I · 5 уроков · 1/5 ─────────── [⌃]    │  │ О курсе (compact)     │
│   ✓ Что такое сравнение величин        ▶ 6:40      │  │ Математика I 1/5      │
│   ○ Приёмы быстрого сравнения          ▶ 8:10      │  │  ✓ …  ▶              │
│   ○ Разбор 10 задач                    ▤ страница  │  │  ○ …                 │
│   🔒 Аналогии (откроется после …)                   │  │ …                     │
├────────────────────────────────┬───────────────────┤  └───────────────────────┘
│                                │ О курсе: модулей 5│
│                                │ уроков 23 · язык  │
│                                │ RU · [mascot]     │
└────────────────────────────────┴───────────────────┘
```
Lesson page `/courses/{c}/modules/{m}/items/{i}` (new; for `url` items with `video`): title, the click-to-load player
(a navy card with a play button; the iframe `https://www.youtube-nocookie.com/embed/{id}` or `https://player.vimeo.com/video/{id}`
loads only after the tap, so nothing is fetched from a third party before the student chooses), the item's module and
position, "Отметить как пройденный" (mark_done requirement) or an automatic view record, prev/next lesson. Page items
keep `/pages/{id}` and get the same prev/next footer. Free: all lessons for now (D9). Hosting: unlisted videos on the
owner's YouTube channel (free; R2 video would cost money and is not proposed).

### 3.6 Практика `/courses/{c}/practice`, Открыть доступ `/unlock`, Начало работы
Practice: the existing list restyled (section tags, "N вопросов", last result). `/unlock`: the existing form inside
the new shell with the gold header card. Начало работы: a client-side checklist (цель поставлена, первый тест пройден,
практика сделана, приложение установлено) in the sidebar pill and a small home card until all four are done.

## 4. Backend additions (no migration)

4.1 `HomeCourseOut.student_layout: "exam_prep" | "general"` (from `exam_prep.layout.is_exam_prep`), so the shell knows
the exam-prep courses. Tests: a platform ORT course reports `exam_prep`, a teacher course `general`.

4.2 `GET /courses/{id}/my/activity?days=7|30|90|365` → `ActivityOut { streak_current, streak_longest, totals {answered,
correct, accuracy}, days [{date, answered, correct, wrong, study_seconds, by_section {key: seconds}}], by_hour [24],
sessions [{started_at, ended_at, answered, correct}] (last 7 days, a gap over 30 min starts a new session, at most 50),
heatmap [{date, answered}] (all time, at most 366 entries) }`. Source: `attempt_items.answered_at` joined to the
caller's non-preview attempts of the course; dates in `Asia/Bishkek`; `study_seconds` = sum of gaps between consecutive
answers inside one attempt, each gap capped at 10 min. Policy: enrolled student, own data only (test students too);
never other students; one grouped query per call; route listed in `route_inventory.py`. Tests: streak over midnight
Bishkek, the 10-min cap, preview attempts excluded, another student gets 403, `days` outside the set → 422.

4.3 `GET /courses/{id}/my/saved?cursor&limit≤50` → flagged items of the caller's submitted attempts, newest first,
`MistakeOut` shape (keyed only when the grade is released). Tests: unreleased result carries no key, flags of other
students never appear, pagination.

4.4 `ItemStudentOut.video: {provider: "youtube"|"vimeo", id} | null` for `url` items whose host is in
`app/lms/modules/video.py` (`youtube.com`, `www.youtube.com`, `youtu.be`, `youtube-nocookie.com`, `vimeo.com`,
`player.vimeo.com`); the id is validated (`[A-Za-z0-9_-]{11}` / digits), everything else stays a plain link. The teacher
side does not change (a video is a URL item). Frontend CSP: `frame-src 'self' blob: https://www.youtube-nocookie.com
https://player.vimeo.com`; `img-src` unchanged (no thumbnails from third parties). The pages sanitizer stays as it is.

4.5 Practice from a topic: `PracticeDialog` already takes section/topic; no backend change.

## 5. Slices (build order; one Opus implementer per slice in a worktree)

Each slice: trilingual keys (`scripts/check_i18n_parity.py`), `npx tsc --noEmit`, backend tests against a scratch DB
where touched, the ORT baseline run (`frontend/e2e` bluebook and exam-prep specs) and the **UX check** at 375 / 1440 /
1920 in ru by the orchestrator (screens in `docs/phases/STUDENT_UI_screens/`).

| # | Slice | Delivers | Acceptance |
|---|---|---|---|
| U1 | Tokens and primitives | `tailwind.config.ts`, `globals.css`, Inter via `next/font` scoped to the shells; new `ui/`: `SectionTag`, `Meter` (three-band), `Heatmap`, `LockOverlay`, `GoldPill`, `Countdown`, `SidebarNav`, `TabBar`, `Sheet` | Storybook-free demo page under `/dev`; ORT baseline identical (system font on lobby and attempts); first-load JS grows ≤ 15 kB gzip |
| U2 | Student shell | `StudentShell` (sidebar, phone top bar, tab bar, More sheet, exam switcher, account), `LmsShell` rule (§2.1, §2.4), course sidebar hidden in exam-prep courses, `student_layout` (§4.1) | every current student page renders inside it unchanged; teacher/admin frames untouched; keyboard and `aria-current` on nav; 375 no overflow; baseline identical |
| U3 | Home | §3.1 for exam-prep students; the generic home restyled; greeting, countdown tiles, Next, streak strip (reads §4.2 when present, else hidden), unlock card, section rows, continue lesson, courses row | 2–3 requests in parallel, skeleton first; empty states with mascot; personal best celebration kept |
| U4 | Tests page | `/courses/{c}/tests` (§3.2), redirect from `/courses/{c}` for exam-prep courses, lock states, chips | lobby link unchanged; paid card → `/unlock`; `exam-prep.spec.ts` updated |
| U5 | Backend activity and saved | §4.2, §4.3, route inventory, tests (SQLite and PG) | query count 1–2 per endpoint; 403 for others; timezone tests |
| U6 | Analytics page | §3.3 and the mistakes tab; charts as inline SVG/CSS (no chart library); period selector | works with zero data; 375 charts scroll only inside their card; colours never the only signal |
| U7 | Lessons | §3.5 syllabus and lesson page, §4.4 `video`, CSP, click-to-load player, prev/next, sidebar sub-links | a YouTube `url` item plays after a tap; a non-allowlisted URL stays a link; no third-party request before the tap (network log) |
| U8 | Saved page and getting started | §3.4, the checklist (sidebar pill + home card), install entry, practice list restyle, `/unlock` in the shell | checklist items derive from existing data only |
| U9 | Polish and gate | 1920 layout, ky/ru long-text pass at 375, `PRODUCT_DECISIONS.md` entries, `HANDOFF_NEXT_AGENT.md`, screens index, Lighthouse on a 4× CPU / Slow 4G profile | LCP of Главная ≤ the S5 number (2.37 s) + 0.3 s; i18n parity; full SQLite suite green |

Order: U1 + U2 as one slice → (U3, U4, U5 in parallel) → (U6, U7 in parallel, U6 after U5) → U8 → U9. U5 and U7's backend part are
the only backend work.

### 5.1 Coherence pass (owner 2026-11-06: "it must look natural, not a combined made-up thing; we don't need every feature of the reference")
After the palette (§1.1), a Fable review of all student screens together (one product, not pages side by side), then the
fixes in U9. Already decided: (a) mistakes live in one place, "Сохранённые" with tabs Сохранённые · Ошибки (no separate
"Мои ошибки" nav item, no mistakes tab on Аналитика); (b) unlock: sidebar pill always, home card only for students
without results, lock pills only on paid tests; (c) analytics cards that need history (active hour, sessions, study time)
appear only after enough activity; (d) one header pattern (title, course subtitle, at most one action); (e) one primary
button per screen. Not built from the reference: daily questions, study planner, credits, question rush, vocab.

## 6. Free and locked (summary)
Free: home, countdown, goal, Next, the free test(s) and their review, practice where `practice_free`, lessons (D9),
saved and mistakes, analytics (D8). Locked: paid tests (lock pill, blurred score, "Открыть доступ"), the Next card
skips them (already). With a pass: the gold pill becomes "Доступ до {date}" (secondary style). Lock overlays are a
component, so moving a card behind the pass is a one-line change later.

## 7. Now vs later
Now: streaks and activity (derived, §4.2), saved from flags (§4.3), video lessons via URL items (§4.4), getting-started
checklist (client). Later, after content exists: daily questions (needs a free practice pool and a deterministic
pick), the study planner (needs lessons and a plan model), "save this question" from the review page (new table
`saved_questions`), lesson tiers (module `access_tier`, one migration), AI tutor (S6, D5): its sidebar slot is
"Помощник" under Главная, shown only when the feature flag is on; its page is the chat layout of the reference app
(centred prompt list, input at the bottom) and it never appears on attempt routes.

## 8. Decisions and risks
8.1 Agent decision: teacher, organization and platform areas keep `AppHeader` now; they get the sidebar after the
student launch (record in `PRODUCT_DECISIONS.md`). Reason: the owner's focus is students and the course sidebar already
navigates teacher courses.
8.2 Owner decisions (defaults apply until answered): **D8** analytics free (default) or partly behind the pass;
**D9** lessons free until there is enough content (default), then a module tier; **D10** video on the owner's YouTube
channel as unlisted videos through the no-cookie player (default yes; Vimeo also allowed).
8.3 Risks: (a) ORT parity: the font and the shell are scoped by route; the baseline run is the gate for U1, U2, U4.
(b) Phone bottom bar covering content: `<main>` padding and the sheet's focus trap; checked at 375. (c) JS budget on
low-end Android: no chart library, Inter ≤ 90 kB, lazy routes; measured in U9. (d) Thin content on production (one
published test, no lessons): every empty state must still look designed (mascot, next step); the slices ship with
that in mind. (e) `activity` cost at 6,000 students: one grouped query, bounded output; add an index on
`attempt_items(answered_at)` only if PG `EXPLAIN` in U5 shows a seq scan.
