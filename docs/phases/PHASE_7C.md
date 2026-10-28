# Phase 7c: quiz editor (write questions inside the quiz)

**Status**: built 2026-10-28 on `phase-7c`; deploy details at the end. Proposal and owner decisions: `PHASE_7C_PROPOSAL.md`, `PRODUCT_DECISIONS.md` (7c-1…7c-9, P7C-1…P7C-14). Design: `PHASE_7C_DESIGN.md` (+ §16 amendment).

## What a teacher gets
- A general quiz opens in a **card editor** (Questions · Settings · Preview, publish bar with question count and points). "+ New question" at the end and "+" between cards; the question type is a dropdown inside the card; answers are one line each with a radio/checkbox for the correct one; Enter adds an answer, Backspace in an empty one removes it; "Add image" and the formatting toolbar appear on demand.
- **Hybrid saving**: typing autosaves a draft per card (survives closing the browser, keepalive flush on page hide); a question version is created only on "Done" or when a valid card is closed.
- **Edit scope**: a question also used by other quizzes asks once, on Done: "Change only in this quiz" (primary) or "Update in all N quizzes"; the dialog says published quizzes change only after they are republished. A type change on a question used elsewhere or already published always makes a new question in this quiz only.
- **Quiz banks**: questions written in a quiz live in that quiz's own bank (one store, no copies). Quiz banks are private to their quiz; reuse goes through "Move or copy to a shared bank" in the Bank tab, where quiz banks are listed under "Quiz banks".
- **Find questions** (shared banks only), random groups ("points per question"), passages, collapsed cards with the correct answer, "Used in N quizzes" / "Shared bank" / "Only in this quiz" chips, inline validation under each field, "Section 1" only when a second section is added; students never see a heading for the hidden default section.
- Bank tab "New question" in general courses is a plain button (type chosen inside the editor).

## ORT
Unchanged. ORT preset exams keep today's builder (`SectionBuilder`, moved verbatim) and refuse quiz-editor writes (409 `template_locked`); the ORT bank keeps its type menu; importers untouched; `ort.spec.ts` and `ort-visual.spec.ts` zero diffs on every run (S5 ×3, UX slice ×1); ORT backend tests green.

## Schema
Migration `0011_phase7c_quiz_editor`: `question_banks.assessment_id` (+ partial unique, CHECKs), table `question_drafts`. No data steps; downgrade refused once quiz banks exist.

## Reviews
- **Security review** (architect): H1 quiz-bank leak through translation links, M1 passage detach on commit, M2 draft lost after section move, M3 unbounded usage scan, L1 draft image ids — all fixed with regression tests (`phase-7c-fix1`). L3 (a new card inside a quiz-bank passage is committed as a top-level item) left as a known limitation: such passages are reachable only through the Bank tab.
- **UX gate** (ux-reviewer): 8 major + 9 minor findings, all fixed (`phase-7c-ux`); screenshots in `PHASE_7C_screens/` (`INDEX.md`). Not fixed: phone course tabs open scrolled (pre-existing course header).

## Tests
Backend: `tests/lms/test_quiz_editor_*.py` (drafts, commit, scope, type change, usage, bank ops, quiz banks, isolation, publish with drafts, correct summary), `test_pg_concurrency_quiz_editor.py` (5 races), `tests/test_migration_0011.py`. Frontend: `frontend/e2e/quiz-editor.spec.ts` (teacher writes five types, scope both ways, sections, draft survives closing the browser, publish with unfinished draft, student takes it, second quiz unchanged, Bank tab move).
Gate results: see "Deploy" below.

## Deploy
(filled in after the gates and the deploy)
