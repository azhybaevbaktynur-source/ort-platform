# Lesson course structure and page design (content studio requests R1–R7, 2026-11-22)

Source: `~/ort-content-studio/state/platform_requests.md` § «2026-11-22» (owner-approved 2026-11-22; owner reviewed the
draft lesson course «Подготовка к ОРТ (рус.)»). Background: `~/ort-content-studio/docs/research/PLATFORM_GAPS.md`,
`LESSON_DESIGN.md` §F. This file is the contract between the slices below. Existing quizzes keep today's behaviour.

## Contract

### C1. `assessments.placement` (migration `0035_assessment_placement`)
- Column `placement VARCHAR(16) NOT NULL DEFAULT 'tests'` (server default `'tests'`), values `tests | lesson`.
  Check constraint `placement_valid`: `placement IN ('tests','lesson')`; check `placement_lesson_plain`:
  `placement = 'tests' OR (preset = 'none' AND NOT is_practice)`. Additive, short DDL (hot table rules, HANDOFF §7).
- Set on create: `AssessmentCreateIn.placement: Literal["tests","lesson"] = "tests"` (so
  `POST /courses/{c}/modules/{m}/quiz` body `quiz.placement` and `POST /courses/{c}/assignments` quiz body take it);
  `AssessmentUpdateIn.placement: Optional[...]` (PATCH `/courses/{c}/assessments/{a}`). A preset or practice assessment
  with `lesson` → 422 `placement_not_allowed`. Changing placement does not need a new version (it is not snapshot
  content); it is allowed on a published assessment.
- When placement becomes `lesson`, `omit_from_total` is set to true (lesson quizzes are practice, not grades; R4).
- Returned as `placement` in: staff assessment out, student assessment out (`GET /courses/{c}/assessments/{a}` as a
  student), `AssignmentStaffOut`/student assignment out (`placement` of the quiz's assessment, null for hand-ins),
  `ItemLinkOut.placement` (module student items of a quiz), staff `ItemTargetOut.placement`.

### C2. Where a lesson quiz is NOT listed (backend)
`placement = 'lesson'` is excluded from: `features.tests` (`courses/service.py` `f_quizzes`, and `f_exam_tests` via
`exam_prep/service._visible_test` + every library count/list using it), the student assignments list
(`assignments/scopes.student_list`), home `next_up` / `todo` / `in_progress` / course-card resume
(`home/service.py`), the student «Оценки» (`grading/gradebook.my_grades`: rows and total). Staff gradebook unchanged.
Unchanged: module items, gating, requirements, `done`, attempts, review, mistakes, saved, progress/analytics reads.
New flag `features.lesson_quizzes`: EXISTS a published, live quiz assignment with `placement = 'lesson'` held by a
published live item of a published live module of the course. Frontend type `CourseFeatures.lesson_quizzes?: boolean`.

### C3. Frontend lessons flow (R2, R3, R4)
- `LessonView`: an assignment item whose `link.placement === "lesson"` is not forwarded to the lobby. It renders a quiz
  card inside the lesson body: title, «N вопросов» (from the student assessment out), best result % (requirement
  `best_score_percent` or the student's attempts), ✓ when `done`, one button «Начать» / «Ещё раз» that starts the
  attempt the same way the lobby does and opens the player with `?return=<this lesson URL>`. Locked rows, access codes,
  no attempts left: show the lobby's message and keep the lobby link as fallback. Outline aside and pager stay.
- Result page of an attempt whose assessment has `placement = "lesson"`: parent tab Уроки (`tabOfPath` cannot know it
  from the path; use the `return` query param pointing under `/modules` or `/lessons`, or the assessment's placement),
  primary button «Следующий урок» (next syllabus row after the quiz's item, from the same module list LessonView uses),
  link back to the lesson page; review/explanations as today.
- `shownTabs`: Тесты = `tests || hand_ins || practice` (unchanged); Повторение (`saved`) = `tests || lesson_quizzes`;
  Аналитика = `tests || hand_ins || lesson_quizzes`. Аналитика of a course without tests: the analytics blocks that
  need tests stay hidden unless `lesson_quizzes`; «Оценки» block is hidden when `my_grades` has no rows.
- Overview «Следующий шаг» and «Тестов: N» already read the assignments list (now without lesson quizzes); check it.

### C4. Option letters (R5)
Display map A→А, B→Б, C→В, D→Г, E→Д when the content language is `ru` or `ky`; Latin for `en`. Player
(`playerUtils.letter`, `ItemView` single/multiple/comparison), staff previews (`StudentPreview`, `SimpleFields`,
`ChoiceFields`), review (`ReviewItemCard`: add the letter badge before each choice). Stored keys and keyboard keys unchanged.

### C5. Page renderer (R6 server part)
`pages/render.py` recognises (after Markdown, before nh3, as a treeprocessor; nh3 stays the trust boundary):
1. top-level `<hr>` splits the body into `<section class="lesson-card">` parts (only when at least one top-level `hr`);
2. blockquote whose first paragraph starts with `<strong>LABEL</strong>` (label trimmed of `.:?!` and spaces,
   case-insensitive) → `<aside class="callout callout--key|tip|trap|recall" role="note"><p class="callout__label">Label</p>…`
   (the label is removed from the first paragraph);
3. `Проверь себя` → `aside.callout.callout--check`; from the first paragraph starting with `<strong>Ответ</strong>`
   (`.`/`:` trimmed) to the end of the blockquote → `<details><summary>Показать ответ</summary>…</details>`;
4. `Почему так` → `<details class="why"><summary>Почему так?</summary>…</details>`;
5. `Разбор` → `<div class="worked">`: task paragraph(s), the ordered list gets `class="worked__steps"`, the paragraph
   starting `<strong>Ответ</strong>` gets `class="worked__answer"`, a nested `Ловушка` paragraph becomes a trap callout;
6. a paragraph containing only an `<img>` with a `title` → `<figure><img …><figcaption>title</figcaption></figure>`.
Labels ru and ky (configurable table in `pages/ids.py`, ky pending a native check): Главное/Негизгиси → key,
Приём/Прием/Ыкма → tip, Ловушка/Тузак → trap, Вспомни/Эсиңе түшүр → recall, Проверь себя/Өзүңдү текшер → check,
Ответ/Жообу → answer, Почему так/Эмне үчүн → why, Разбор/Талдоо → worked. Summary text follows the label's language
(ru «Показать ответ», ky «Жоопту көрсөт»). Unknown label: plain blockquote.
nh3: tags `section aside figure figcaption details summary div` added; `class` allowed only on
`section aside p ol div details` with exactly the values `lesson-card callout callout--key callout--tip callout--trap
callout--recall callout--check callout__label why worked worked__steps worked__answer` (each class token checked;
anything else dropped); `role` only `note` on `aside`. Author-typed `<details>`, `<aside>`, `class=` lose their
classes, and raw `<details>`/`<aside>`/`<section>`/`<div>` typed by authors are stripped (escape or remove raw HTML
of these tags before Markdown, so only the server creates them).

### C6. Page CSS and view fixes (R6 client part, R7)
`.page-body` values from the request F2 (Noto Sans via `next/font/google`, self-hosted, subsets latin, cyrillic,
cyrillic-ext; 18 px ≥ 640 px, 17 px below; 40 rem text column; callout colours; `details` summaries ≥ 44 px, chevron,
«Скрыть ответ» when open via CSS `details[open] > summary`; print opens details via `@media print`). KaTeX sizes.
Images centred (`display:block; margin:0 auto 1rem`). Staff Preview tab: `PageView` in preview mode omits its title.
Contrast ≥ 4.5:1. Mobile 360 px: no page scroll; tables and display math scroll in their block.

## Slices (each in its own worktree and branch, from `lms`)
| slice | requests | owns |
|---|---|---|
| `lc-a-placement` (backend) | R1, R4 server, C1, C2 | migration 0035, assessments models/schemas/builder, assignments, modules schemas/service (link placement), courses features, exam_prep, home, grading `my_grades`, route inventory if needed, tests |
| `lc-b-renderer` (backend) | R6 server, C5 | `pages/render.py`, `pages/ids.py`, page tests and golden |
| `lc-c-lessons` (frontend) | R2, R3, R4 client, C3 | `LessonView`, result page, `courseTabs`, analytics tab, types for features/placement, i18n keys it adds |
| `lc-d-display` (frontend) | R5, R6 CSS, R7, C4, C6 | player, previews, review card, `globals.css` `.page-body`, `lib/fonts.ts`, `SafeHtml`, `PageView`, i18n keys it adds |

## Results (2026-11-22)
Merged on branch `lesson-course` (slices `lc-a-placement`, `lc-b-renderer`, `lc-c-lessons`, `lc-d-display`, e2e `lc-e2e`).
- R1/C1–C2: migration `0035_assessment_placement`; `placement` on assessment, assignment, lobby and module item outputs;
  `features.lesson_quizzes`. Also excluded: course card `tests_count`/paid flag (`courses/cover.py`), exam-prep resume.
  Not filtered: the student `GET /courses/{c}/assessments` list and home `modules_next` links (no test listing there).
  Locked syllabus rows carry no `link.placement`. A placement-only PATCH needs no new version.
- R2/R3: `LessonQuizCard` in the lesson body (start without lobby, `?return=` the lesson); result page declares its
  parent tab (`course/ParentTab.tsx`) as Уроки from the return path or the placement; «Следующий урок» primary.
  Tabs: Повторение = tests ∨ lesson_quizzes, Аналитика = tests ∨ hand_ins ∨ lesson_quizzes.
- R4: student «Оценки» rows and total leave lesson quizzes out; the block hides when it has no rows (and analytics is shown).
- R5: `lib/lms/optionLabel.ts` (А Б В Г Д for ru/ky) in player, previews and review (new letter badge). aria-labels in
  previews stay Latin (e2e selectors). ORT player screenshots now show Cyrillic letters by design.
- R6: renderer components as C5 (a `Разбор` also gets a `callout__label` paragraph); author HTML for the new tags is
  stripped; Noto Sans on `.page-body`; «Скрыть ответ» swapped by `SafeHtml` on toggle (interface language); details
  print open. Pages that already used `---` now show screen cards (announcements too).
- R7: preview tab shows the title once; images centred. Optional Markdown in quiz explanations: not done.
- Fixed on the way: the review drew a correct pick red when the answer key is hidden (since 2026-10-22); «Разобрать
  ошибки» hidden on a full score; the lesson quiz card no longer repeats the page title.
- Checks: SQLite + PG suites, `alembic check`, migration tests, tsc, i18n parity, `*.check.ts`, `next build`,
  `e2e/lesson-course.spec.ts` (2 runs), `lessons.spec.ts`, `bluebook-player.spec.ts`. Screens: `LESSON_COURSE_screens/`.
- Open: Kyrgyz labels need a native check (`pages/ids.py`); on phones the Повторение tab sits at the edge of the
  scrolling tab row; no staff UI switch for `placement` yet (API only).
