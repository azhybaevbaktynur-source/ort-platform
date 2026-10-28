# Phase 7c proposal: quiz editor (write questions inside the quiz)

**Status**: **approved by the owner 2026-10-28** (decisions 7c-1…7c-9 in `PRODUCT_DECISIONS.md`; this file is updated to match them). Inserted before Phase 8a. Exact design: `PHASE_7C_DESIGN.md`.
**Trigger**: owner's Canvas screenshots in `docs/example_canvas_quiz/` (Classic Quizzes: quiz → Questions tab → "+ New Question", type dropdown inside the question card, points, rich-text stem, answers with "Correct answer" / "Possible answer", "+ Add another answer", "Update question"; also "+ New Question Group" and "Find Questions").

## 1. The problem today

To put one multiple-choice question into a new quiz, a teacher must:

1. Open the **Bank** tab, create a bank.
2. In the bank, open the "New question" menu and pick the type **before** seeing any editor (`bank/[bankId]/page.tsx:78`); the type is locked after the first save (`QuestionEditor.tsx:91`).
3. Write the question on its own page, save.
4. Go to **Assessments**, create the quiz, open the editor.
5. Create a **section** (items cannot exist without one).
6. Open "Add items", search the bank, tick the question, add.
7. Set points on the item row.

That is ~7 steps across 3 screens, and the teacher never sees the quiz as students will while writing it. A bank is useful for reuse and random draws, but it must not be the only way in.

## 2. What others do (research)

| Product | Where questions live | Edit inside the quiz |
|---|---|---|
| Canvas Classic (screenshots) | Quiz questions are **copies** of bank questions (`quiz_questions.question_data`); a question written in the quiz is silently copied into an "Unfiled questions" bank | Edits the copy; the sync heuristics caused long-lived bugs (`docs/research/canvas-assessments.md` §1.3, §1.8) |
| Canvas New Quizzes | Item banks; bank items are **linked**, not copied | Editing in the bank changes every quiz using it; editing from inside a quiz does **not** propagate. Universities publish guides warning about this (duplicate the bank first) |
| Moodle 5.0 (2025) | Every quiz gets its **own private question bank**; reusable questions go in separate "shared banks"; a quiz can mix both | Questions are edited in place; new versions, quizzes may pin a version or use "always latest" |

Lesson: the modern answer is **one store of questions** (no copies) + a private bank per quiz + shared banks for reuse. Copies are what Canvas moved away from.

## 3. Recommended data approach: one store, linked, never duplicated

We already have the right foundation: `bank_questions` + immutable `question_versions`; a published quiz is an immutable snapshot pinned to version ids; attempts never read live content. So linking is safe: **editing a question never changes what students already see or took**; it only reaches students when the teacher republishes.

- **No new question table.** A question written inside a quiz is a normal `bank_questions` row.
- **Quiz bank** (like Moodle 5): each general assessment gets its own bank, created on first use (`question_banks.assessment_id` nullable FK; shared banks keep `assessment_id IS NULL`). It is listed in the Bank tab under "Quiz banks" with the quiz name, so nothing is hidden. Deleting the quiz soft-deletes its bank with it (restorable).
- **Reuse**: questions from shared banks are added by link ("Find questions"). A quiz-bank question can be "Moved to a shared bank" or "Copied to a shared bank" later.
- **Edit scope** (7c-2), asked once when the teacher finishes editing a question inside a quiz:
  - used only in this quiz → save a new version, nothing to ask;
  - used in other quizzes too → one dialog: **"Update in all N quizzes"** or **"Change only in this quiz"** (makes a copy in the quiz bank and repoints this item). The dialog states that **published quizzes change only after they are republished**. If the teacher cannot edit the source bank, only "Change only in this quiz" is offered. This removes the Canvas New Quizzes trap where the teacher cannot tell which behaviour they get.
- **Type change** (7c-5): if the question is used in another quiz or in any published version, changing its type always creates a **new question in this quiz only**; the old question stays as it was. Otherwise the type change is part of the next version.
- Past attempts, grades and published versions are untouched in every case (existing snapshot rules). Regrading stays the explicit teacher action it is today.
- **Sections become optional** (7c-6): a new quiz gets one hidden default section; when the teacher adds a second section, the existing questions visibly become **"Section 1"**. ORT and template exams keep their sections and locks.

Rejected: a separate quiz-question table that copies bank questions. It duplicates content, doubles storage and search, and needs sync code; Canvas's own code shows the cost.

## 4. Quiz editor design (teacher)

One page per quiz with tabs **Questions · Settings · Preview**, publish bar on top (status, total points, "unpublished changes", Publish).

- **Question list as cards.** Collapsed card: number, type chip, points, first line of the stem, correct answer marked. Click → the card expands into the editor in place (no page change). One card open at a time.
- **"+ Add question"** at the bottom and a small "+" between cards (insert here). New card opens with **Multiple choice** selected and the cursor in the stem; the **type is a dropdown inside the card** and can be changed while editing (text and choices carried over where the shapes match: single ↔ multiple answers ↔ true/false).
- **Answers**: one row per answer, a radio/checkbox to mark correct (green), Enter adds the next answer, Backspace on an empty answer removes it, drag to reorder, math and image buttons as today (KaTeX, ImagePicker).
- **Saving is hybrid** (7c-4): typing autosaves a **draft per card** on the server (debounced, "Draft saved" indicator; nothing is lost if the browser closes, the draft reopens on return). A **question version** is created only when the card is closed or **"Done"** is clicked; the scope dialog (7c-2) appears at that moment, once. No version per autosave. Validation errors shown on the card, not in a toast; a card with errors stays open as a draft.
- **Card actions**: duplicate, move up/down/drag, delete (undo for 10 s), "Save to shared bank".
- **"Find questions"**: a side drawer (full screen on 375 px) with the existing bank filters, multi-select, "Add N".
- **"Random group"**: "pick N from bank X (filter)" as one card (existing `pick` items).
- **Passage**: "Add passage" card; questions inside it are indented under it (existing `parent_item_id`).
- **Bulk entry (optional, later)**: "Paste questions as text" using the 7b general import format.
- **Mobile 375 px**: cards full width, editor stacked, sticky publish bar; all touch targets ≥ 44 px.
- **Bank tab stays** for teachers who build large banks (ORT style); its "New question" also opens the editor with the type dropdown inside instead of a pre-menu.

Student side: unchanged (same player, same snapshot).

## 5. ORT and templates

- ORT courses keep their bank, import and exam screens exactly as now (hard rule 9). The new editor is for general assessments; ORT assessments open the current screens.
- Template-created exams respect `structure_locked` and the template's allowed types per section (the type dropdown only offers allowed types).
- Phase 8b's template constructor reuses the same card editor for its live preview.

## 6. Scope and slices (size M)

- **S1 backend**: `question_banks.assessment_id` + per-card draft storage + migration; auto quiz bank; default hidden section; create question + version + item in one transaction; draft autosave (no version); "Done" = new version with `scope=all|this` (copy + repoint), type-change rule 7c-5; usage count per question; move/copy to shared bank; route inventory + tests (authz, concurrency, snapshot unchanged, ORT parity). Exact names in `PHASE_7C_DESIGN.md`.
- **S2 frontend**: card-based editor, type switch with carry-over, draft autosave + "Done", find drawer, scope dialog, "Section 1" on second section, Bank tab "Quiz banks" group, i18n en/ky/ru.
- **S3 integration + UX gate** (375 px + desktop, ux-reviewer), ORT review, deploy.

## 7. Owner decisions (2026-10-28, recorded as 7c-1…7c-9 in `PRODUCT_DECISIONS.md`)

1. Editing a question used in other quizzes: ask "Update in all N quizzes / Change only in this quiz"; the dialog says published quizzes change only after republishing; without edit rights on the source bank only "Change only in this quiz".
2. Quiz banks: visible in the Bank tab under "Quiz banks".
3. Saving: hybrid (draft autosave per card, version on close/"Done", scope asked then, once).
4. New question types (matching, fill-in-the-blank, ordering): Phase 10; then they appear in this editor's type dropdown and in the 7b general import format.
5. Order: 7c before 8a; next checkpoint after 8b.
6. Type change on a question used elsewhere or in a published version → new question in this quiz only.
7. Second section added → existing questions visibly become "Section 1".
8. ORT screens unchanged; ORT review and UX gate as usual.

Sources: [Moodle question banks (5.0)](https://docs.moodle.org/500/en/Question_banks), [Moodle: question banks in upgraded sites](https://docs.moodle.org/en/Question_banks_in_upgraded_sites), [Temple: New Quizzes item-bank editing](https://foxonline.temple.edu/?p=395), [Cedarville: item banks](https://ctl.cedarville.edu/wp/top-three-things-to-know-about-new-quiz-item-banks/), [Ohio: question banks and item banks](https://help.ohio.edu/TDClient/30/Portal/KB/Article/1259/Canvas-Question-Banks-and-Item-Banks).
