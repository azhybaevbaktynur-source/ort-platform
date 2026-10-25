# UX guidelines

**Status**: owner rule since 2026-10-24. Every phase passes a UX gate against this file (see §7). Short on purpose: if a screen breaks a rule here, it is a finding.

---

## 1. Four areas, four audiences

| Area | Who | Goal of the UI |
|---|---|---|
| Student | Teenagers (14+), often on a phone, often on a slow connection | Simple and motivating: always clear what to do next |
| Teaching | Teachers and assistants in their courses | Get work done fast: build, publish, grade |
| Organization admin | A school or center admin | Manage teachers and courses of one organization |
| Platform admin | The owner | See and control everything; rare but powerful actions |

One person can be in several areas (a teacher who studies in another course). The header shows only the areas the person has. Switching areas never needs a new login.

## 2. Students

- **The home screen answers "what should I do next?"** It shows the next exam or assignment (with a due date), anything in progress ("Continue"), and the latest results. Little else. No dense dashboards, no statistics tables.
- **One main action per screen.** It is the only filled (primary) button. Everything else is secondary or a link.
- **Plain, friendly language.** "Start the exam", not "Initiate attempt". Say what happens next: "You have 2 attempts. The timer starts when you press Start."
- **Clear progress.** Show where the student is (section 2 of 5, 12 of 30 answered, time left) and what is done (completed, score released or not yet).
- **Small celebrations without noise.** A short, positive message for a finished exam, a personal best, or a completed module. No confetti during an exam, no sounds, nothing that delays the next action.
- **Never punish by surprise.** Warn before anything that cannot be undone (submit, leave a section, the timer ending), in one clear dialog.
- **Exams are calm.** The exam player shows the question, the answer options, the timer, the palette and the save state. Nothing else competes for attention.

## 3. Mobile-first

- Design for **375 px width first**, then desktop (1440 px). Every screen must work at 375 px: no horizontal scroll, no text cut off, touch targets at least 44 × 44 px, buttons reachable with a thumb.
- **Slow connections**: show the page shell immediately and load data after it. Never leave a blank screen. Keep pages light: no large images on student screens, lazy-load lists. Autosave and submit must clearly show "saving", "saved" and "offline, will retry".
- Tables on a phone become stacked cards or keep 2–3 key columns, with details behind a tap.

## 4. Teachers and admins

- More information is fine, but **organized**: a stable navigation (area → section → page), page titles that say where you are, and breadcrumbs inside a course.
- **Lists are tables with search, filters and sorting**, plus pagination for anything that can grow. Show the count ("124 questions").
- **No hidden features.** Every action is a visible button or menu item with a label. No action only on hover, double-click or a secret shortcut. Keyboard shortcuts are extras.
- **Bulk actions** where teachers repeat work (add many questions, move items, release grades).
- **Dangerous actions** (delete, unpublish with attempts, remove a teacher) need a confirmation that names the object and the effect.

## 5. Everywhere

**One design system.** Phase 6 creates it in `frontend/src/components/ui/`. Pages use these components instead of re-styling raw elements:

| Token / component | Rule |
|---|---|
| Colors | Brand blue (`brand-*`) for primary actions and links; slate for text and borders; green success, amber warning, red error; gold only for achievements (for example the ORT golden certificate). Text contrast at least 4.5:1 (WCAG AA). |
| Type | One font family. Sizes: page title, section title, body (16 px on a phone), small (meta, help). Line height comfortable for Cyrillic. |
| Spacing | A 4 px scale (Tailwind default); the same padding for cards, the same gap between sections. |
| Components | `Button` (primary / secondary / danger / link), `Input`, `Select`, `Textarea`, `Checkbox`, `Card`, `Table`, `Tabs`, `Dialog`, `Badge`, `EmptyState`, `ErrorState`, `Skeleton` (loading), `Toast`, `PageHeader`, `Pagination`. |

**States every screen must have:**
- **Loading**: a skeleton or spinner with text in the page's layout, never a blank page.
- **Empty**: what this place is for, plus the next step ("No courses yet. Join a course with a code from your teacher." + a button).
- **Error**: what happened and what to do. Never a bare "Something went wrong". Examples:
  - offline: "No connection. Your answers are saved on this device and will be sent when you are back online."
  - not found: a friendly page with a way back;
  - no permission: who to ask.

  Always offer a Retry button when retrying can help.

**Accessibility basics:**
- every input has a visible label;
- every icon-only button has an `aria-label`;
- focus is visible, and everything works with the keyboard (Tab, Enter, Esc closes dialogs);
- color is never the only signal (a flagged item also has an icon; a wrong answer also has text);
- dialogs trap focus and return it when they close.

**Three languages:**
- Every string lives in `en.json`, `ky.json` and `ru.json`.
- Layouts must fit Russian and Kyrgyz texts, which are often 30–40 % longer than English: buttons wrap or grow and never cut text off; no fixed-width labels.
- Test the longest language (usually ky or ru) at 375 px.

**Writing:**
- short sentences;
- the same word for the same thing everywhere (one glossary per language: course, assessment/exam, attempt, grade);
- glossary (decided Phase 6b, S9; use these words, never a synonym):
  - en: course, assessment (exam for ORT), attempt, grade, teacher, student, organization;
  - ky: курс, тапшырма (ЖРТ: сынак), аракет, баа, мугалим (never "окутуучу"), окуучу, уюм;
  - ru: курс, задание (ОРТ: экзамен), попытка, оценка, **преподаватель** (never "учитель"), ученик, организация.
- Phase 7a (assignments): the gradable unit is the **assignment**, and a quiz is one kind of assignment. Tabs and
  lists say **"Assignments" / "Тапшырмалар" / "Задания"** for all of them and **"Quizzes" / "Тесттер" / "Тесты"**
  for timed tests only; the ORT exam stays "ORT exam" / "ЖРТ сынагы" / "Экзамен ОРТ". Kinds: "Text answer" /
  "Текст жооп" / "Текстовый ответ", "File upload" / "Файл жүктөө" / "Загрузка файла", "Offline work" /
  "Сайттан тышкаркы иш" / "Работа вне сайта". Handing in: "hand in" / "тапшыруу" / "сдать".
- no technical words in student UI (no "snapshot", "version", "enrollment", "payload").

## 6. ORT exam player

The ORT experience must not change (`PRODUCT_DECISIONS.md`, owner decisions 2026-10-24). It covers the comparison card, line-numbered passages, LaTeX, section timers, forward-only sections, the palette, flags and autosave.

- **Allowed without asking** (keeps exam fidelity), always with before/after screenshots:
  - readability;
  - phone layout;
  - accessibility;
  - clearer timer, palette and flag states;
  - loading and autosave feedback;
  - error messages.
- **Not allowed without the owner**: anything that changes how the exam works or makes it differ from the real ORT (navigation rules, timing, question layout, scoring). Such ideas go to `docs/ORT_PLAYER_IDEAS.md` for the owner's decision.

## 7. UX gate (every phase, before merge)

1. Screenshot every new or changed screen at 375 px and 1440 px. Student screens are shot in all three languages; teacher and admin screens at least in ru.
2. Run the `ux-reviewer` agent on the screenshots and the changed code.
3. Fix the findings. Re-shoot the fixed screens.
4. Save the final screenshots (JPEG, compressed) in `docs/phases/PHASE_N_screens/`, with a short `INDEX.md`.
5. UX reviews never wait for the owner: fix and continue. The owner looks at the saved screenshots when they want.
