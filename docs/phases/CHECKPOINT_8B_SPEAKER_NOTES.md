# Speaker notes: checkpoint after 8b (7c, 8a, 8b)

Companion to `CHECKPOINT_8B.md`. Spoken walk-through, about 15 minutes. Production: https://ort-platform-nu.vercel.app. Have two accounts ready: a teacher in a general course and a student enrolled in it. Screenshots for each step are in `PHASE_7C_screens/`, `PHASE_8A_screens/`, `PHASE_8B_screens/` if you present offline.

---

## 1. Opening (1 min)

- Since the last checkpoint, three releases went live: the quiz editor (7c), course structure (8a) and the exam template builder (8b).
- ORT works exactly as before in all three: same exam, same import, same scoring, same result page. Student ORT screens are pixel-identical; staff only see new course tabs.
- Every release passed the full test suites, an ORT comparison, a security review and a design review; everything they found was fixed before release.

## 2. Quiz editor, 7c (4 min)

**Say:** "Before, a teacher had to create a question bank, write questions there, then come back and add them to the quiz. Now you write questions directly in the quiz, like in Canvas."

**Show** (teacher → course → Assessments → new quiz):
1. Click "New question". A card opens with the type dropdown inside it; switch between multiple choice and true/false and the text stays.
2. Type answers; Enter adds the next one; click the radio to mark the correct answer.
3. Close the browser tab mid-typing, reopen: the text is still there (it is saved as a draft while you type).
4. Click "Done": the card collapses and shows the correct answer in green.
5. Open a question that is also used in another quiz, change it, click Done: the dialog asks "Change only in this quiz" or "Update in all quizzes", and says published quizzes change only after you republish.

**Point out:** questions written in a quiz live in that quiz's own bank (Bank tab → "Quiz banks"); to reuse one elsewhere, move or copy it to a shared bank. Nothing is duplicated behind the scenes.

## 3. Course structure, 8a (4 min)

**Say:** "Courses can now be a guided path, not just a list of assignments."

**Show** (teacher → Modules tab):
1. Create two modules. In module 1 add a page and the quiz; set "minimum 80 %" on the quiz.
2. In module 2 set "requires module 1". Publish both.
3. Switch to the student: module 2 shows as locked with the reason in plain words ("Finish module 1 first"). Take the quiz with a good score: module 2 opens.
4. Pages: show a page with a heading, a list and a formula. Files: upload a PDF. Announcements: post one; it appears on the student's home page.
5. Settings → course home: the course can open on Modules, a page, or the assignments list.

**Point out:** the ORT exam is never locked by modules; inside a locked module it stays available from Assignments.

## 4. Exam template builder, 8b (4 min)

**Say:** "Organizations can design their own exam formats, the way ORT is structured, without code."

**Show** (organization admin → Exam templates → new template):
1. Structure: two sections, time limits, allowed question types.
2. Scoring: pick a grading scheme; the score table updates live.
3. Display: one question per page or the new scrolling mode (a whole section as one list).
4. Sample questions: write two questions, click "Preview": the real student player opens; "Back to the template" returns.
5. Versions: publish, change something, see the difference between versions; lock it so teachers cannot change the structure.
6. As a teacher: "Create from template", add questions, publish; as a student, take it in scrolling mode.

**Point out:** a new template version never changes exams already created from the old one.

## 5. Decisions needed (2 min)

**Say:** "Nineteen questions are open; each already has a safe default, so nothing is blocked. Please answer only where you want something different." The four worth a look:
- 8a-Q5: staff see the new tabs inside ORT courses; students only once something is published. Keep?
- 8a-Q2: new general courses open on Modules. Keep, or default to the assignments list?
- 8b-Q2: only a template's managers can preview its sample questions. Should every teacher be able to preview?
- 7a-Q1: extra time for accommodated students does not apply on ORT exams. Keep?

Full list: `CHECKPOINT_8B.md` §3.

## 6. Housekeeping and next (1 min)

- Neon free plan: 9 of 10 branches used. Need an OK to delete one old backup, proposed `backup-2026-10-23-before-phase5` (the owner previously cleared it for deletion after 30 October).
- Known limitations: a new question inside a quiz-bank passage shows outside the passage block in the editor (students see it correctly); phone course tabs open scrolled; the grading-scheme detail page scrolls sideways on phones because of a wide formula; one flaky rate-limit test to fix.
- Before the first real exam: Render plan and a custom domain for file storage (costs money, owner decision).
- Next after your OK: Phase 9 (organizations completion, enrollment forms), then 10 (practice, analytics, new question types), then 11 (parent consent, hardening, launch).
