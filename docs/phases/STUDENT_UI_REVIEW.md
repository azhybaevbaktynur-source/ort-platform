# Student area: coherence review (U9 input)

Review of branch `lms` 52751f5 against `STUDENT_UI_DESIGN.md` §1.1 and §5.1, judged as one product a 16-year-old
opens on a cheap Android phone (375 px first; 1440 checked). Screens: home (new / with results), Тесты (locked / with
results), Сохранённые, Практика, Открыть доступ, Аналитика, Видеоуроки, the "Начало работы" sheet. ORT lobby, player
and result are out of scope. Sizes: small = under half a day, medium = about a day. MUST = before release.

## Verdict in one paragraph

The shell (sidebar, tab bar, header pattern, palette) is coherent and looks like one app. What breaks the "natural"
feel is the home: under the exam-prep dashboard the old LMS dashboard is still stacked (course grid with dark banners,
"Найти курс в каталоге", "От платформы", "Войти по коду"), and for a new student the dashboard itself is five cards
that all say "nothing yet" (streak, score, sections) or compete for the first action (Next, Начало работы, Поставить
цель, Откройте все экзамены). Тесты still ends with breadcrumbs and "Покинуть курс". The fixes below are mostly
removals and merges; nothing needs a new feature.

## Ranked fixes

### MUST

1. **Remove the course grids from the exam-prep home** (medium). `ExamPrepHome.tsx` `CoursesRow` (lines 238–254,
   rendered at 346), `PlatformCourses.tsx`, `StudentHome.tsx` 266–275. The student's own ORT course appears as a
   dark-banner card ("Платформа / Русский") under its own dashboard, then a dashed "+" card, then "От платформы" with
   another banner card and "Записаться". Three card styles, two headings, and the only content a new student scrolls
   into is a course list. The exam switcher (sidebar "+" and the phone course chip) already covers switching and
   joining. Keep: nothing on the home. Move "Войти по коду", the catalog link and the other platform course into the
   exam-switcher sheet (`StudentShell.tsx` `sheet === "exam"`), as rows under the current course.
2. **Drop breadcrumbs and "Покинуть курс" from Тесты** (small). `TestsPage.tsx` 284–300 (`<footer>` with the
   breadcrumb `<nav>` and `LeaveCourseLink`), `ExamPrepPage.tsx` 68, `StudentCourseFrame.tsx` 22 for students. The
   sidebar and tab bar are the navigation; "Мои курсы › ОРТ › Тесты" is a teacher-LMS path and "Покинуть курс" is a
   destructive link on a list page. Keep leaving possible: one row "Покинуть курс" in the account sheet (gear /
   avatar) or in the exam-switcher sheet under the course, with the same confirm dialog.
3. **One getting-started surface, not three** (small). `gettingStarted.tsx` `GettingStartedCard` and
   `ExamPrepHome.tsx` 334. The card on the home, the sidebar pill "Начало работы 0/2" and the sheet show the same two
   items; "Поставьте цель" duplicates the "Поставить цель" button in the score tile, "Пройдите первый тест"
   duplicates the Next card's "Начать тест". Keep the sidebar/More pill with the sheet (quiet, disappears when done);
   delete the home card.
4. **Collapse the empty-state home of a new student** (medium). `ExamPrepHome.tsx` `ScoreTiles` (119–162),
   `SectionRows` (193–218), `StreakCard.tsx` 58. Before the first result the home shows: a streak card with seven
   empty circles and "Ответьте сегодня…", a score tile "Балл появится после первого…", a goal tile with a button, a
   "Разделы" card "Разделы появятся после…". Four cards explain their own absence. Rule: hide `SectionRows` until
   `history.length > 0`; before the first result render score and goal as one slim row (`Балл: — · Цель: — ✎`)
   instead of two tiles; keep the streak card (it is the one thing a new student can act on today).
5. **Make the sidebar identical on every page** (small). `useStudentShellData.ts` 160–169 (`features` fetched
   lazily per course, `fetchIfMissing`), `StudentShell.tsx` 305–312. On Главная for "ОРТ (на русском)" there is no
   "Уроки / Видеоуроки" group; on Видеоуроки it appears with module sub-links; "Практика" also depends on the lazy
   fetch. A student sees menu items come and go. Return `features` with the course list (one call, the `/me/home`
   course objects already carry `features`) and render the same groups everywhere; drop the module sub-links (desktop
   only, invisible on the phone, so the two shells disagree).
6. **Same order in the sidebar and the tab bar** (small). `StudentShell.tsx` 305–312 vs 398. Sidebar: Главная ·
   Аналитика · Сохранённые · Уроки · Тесты · Практика. Tab bar: Главная · Тесты · Практика · Аналитика · Ещё. Use
   the tab-bar order in both: Главная, Тесты, Практика, Аналитика, then Видеоуроки, Сохранённые. Tests are what the
   student came for; Аналитика second from last.
7. **One name and one place for each number** (small). Home tile says "Текущий балл 106 из 245"; Тесты tiles say
   "Последний балл 106 / Лучший балл 106 / Моя цель —" (`TestsPage.tsx` 111–113); the streak is shown as "Серия
   занятий 1 день подряд · Рекорд: 1" (home), "Серия 1 день · Рекорд: 1 день" (analytics tile) and "Моя активность
   · Серия: 1 · рекорд: 1" (heatmap subtitle, `MonthHeatmap.tsx`). Remove the three tiles from Тесты (it is a list;
   the numbers live on the home and in Аналитика), call it "Последний балл" everywhere, and drop the heatmap subtitle.
8. **Four lock signals on one test card** (small). `TestsPage.tsx` 140–150: "Не начат" chip + gold "Платный" chip +
   blurred box with lock icon and "Нужен доступ" + gold "Открыть доступ" pill. Keep the "Платный" chip and the pill;
   drop "Не начат" on locked cards and the "Нужен доступ" label inside the overlay (the blur and the icon are enough).
9. **Unlock card on the home: one line, not a brochure** (small). `ExamPrepHome.tsx` `UnlockCard` (166–186). The
   three bullets repeat `/unlock` word for word, and on 1440 the card has a second leopard next to the hero's. Reduce
   to title, one sentence and the pill; no mascot; bullets stay on `/unlock` only.
10. **Decide what the violet accent is for** (small). `NextCard` `accent` (home "Начать тест" is violet) but Тесты
    "Начать", Видеоуроки "Начать курс" and `/unlock` "Активировать" are blue. Violet appears once in the whole product,
    so it reads as a stray colour, not as the accent. Either use it for every "start / continue" primary
    (`TestsPage.tsx` 131, `StudentSyllabus.tsx` start banner) and blue for the rest, or drop the accent and let the
    Next card stand out by its tinted background alone. Recommendation: drop it; the palette already has the gold pill
    as the one special colour.
11. **Analytics shows too much for too little data** (medium). `AnalyticsOverview.tsx`, `TopicCards.tsx` (legend at
    125 repeated under both cards), `MonthHeatmap.tsx`, `ActivityCards.tsx`. With 19 answers the page renders four
    tiles, "5 слабых тем" where every topic is "Слабо" from 1–4 answers, a bar chart with one bar, ten topic rows at
    0 %/100 % from a single answer, and an eight-month heatmap with one square. Apply §5.1 (c) to all of it: a topic
    needs ≥ 5 answers before it is graded (else "Мало данных", grey), "слабые темы" appear only when ≥ 3 topics
    qualify, the heatmap shows 3 months on the phone and only after 7 active days, the band legend appears once
    under the last card.
12. **Hero system message** (small). `ExamPrepHome.tsx` 90: "Дата экзамена пока не назначена. Отсчёт появится
    здесь, когда она будет известна." sits inside the greeting of a new student. Hide it; show the countdown tiles
    only when a date exists (the design's ✎ for the student's own date is LATER).

### LATER

13. Merge the four `/unlock` cards (`app/[lang]/unlock/page.tsx`: "Ваш доступ", "Введите код", "Что входит", "Как
    оплатить") into one: status line, included list, code field, payment sentence; drop "К моим курсам" (small).
14. Видеоуроки "О курсе" side card (`StudentSyllabus.tsx`): "Язык: Русский" tells the student nothing; replace the
    card with the design's progress line "0 из 3 уроков" and bar under the start banner, no side card on the phone
    (small).
15. Card styles: `CourseCard` (`rounded-2xl shadow-sm hover:shadow-md`, coloured band) and the dashed `CatalogCard`
    are the only shadowed / dashed cards left; once item 1 lands they are gone from the student area. The
    `EmptyState` dashed border can stay as the one "empty" style (small, after 1).
16. Selector styles: Сохранённые uses underline tabs, Тесты uses filled chips. Tabs = views, chips = filters is a
    defensible rule; write it down in the design doc so the next page does not invent a third (no code).
17. Sidebar brand "Платформа" with a graduation cap is a placeholder; the product needs its name before launch (owner).
18. Streak copy "{count} дня подряд" fallback for `other` should be "дней" (ru plural rule check, `ru.json`
    `home.prep.streak.days`) (small).

## Keep (works, do not touch)

- The shell: gradient sidebar with the white active pill and small-caps group labels, the phone top bar with the
  course chip and the five-slot tab bar, and the gold pill as the single "money" colour everywhere (sidebar, test
  card, Next card). It is the part that already feels like one app.
- The page header pattern (`StudentPageHeader`: title, course subtitle, at most one action) on Тесты, Аналитика,
  Сохранённые, Видеоуроки, Практика, and the greeting band following the same layout.
- The section tags (tinted pills per section) used identically in home "Разделы", analytics "слабые темы" and the
  topic cards, and the three-band accuracy colours; the empty states with the mascot (Сохранённые, Практика) are
  short and friendly.
