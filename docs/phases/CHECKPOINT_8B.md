# Owner checkpoint after 8b (2026-10-28)

What changed since the checkpoint after 7b, what to try, and the open questions. Every open question already has a safe default in effect; answer only where you want something different.

## 1. What shipped
| Phase | What you can see | Report |
|---|---|---|
| 7c Quiz editor | Write questions inside the quiz (Canvas-style cards, type dropdown in the card, draft autosave, "Done"); quiz banks; edit scope "only this quiz / all quizzes"; collapsed cards show the correct answer | `PHASE_7C.md`, screens `PHASE_7C_screens/` |
| 8a Course structure | Modules with requirements, prerequisites, unlock dates and gating; Markdown pages with formulas; PDF course files; announcements; course home (modules / page / assignments); "up next" and announcements on the student home | `PHASE_8A.md`, screens `PHASE_8A_screens/` |
| 8b Exam templates II | Visual constructor (structure, scoring with live table, display, sample questions with real preview, versions with diff, lock, promote); scrolling display mode; display settings on quizzes | `PHASE_8B.md`, screens `PHASE_8B_screens/` |

ORT: unchanged in behaviour in all three phases (player, import, scoring, result); ORT student screenshots identical; staff now see the new course tabs in ORT courses (8a-Q5).

## 2. What to try (production: https://ort-platform-nu.vercel.app)
1. As a teacher in a general course: Assessments → new quiz → write 3 questions of different types in the cards → Publish. Edit one question that is also used in another quiz and see the "only this quiz / all quizzes" choice.
2. Modules tab: create two modules, put a page and the quiz in the first, set "minimum 80 %" on the quiz and make module 2 require module 1; publish; open as a student (another account) and see the lock reasons.
3. Pages: write a page with a heading, a list and a formula `$\frac{1}{2}$`; Files: upload a PDF; Announcements: post one and see it on the student home.
4. Exam templates (organization admin area or Teaching → exam templates): build a two-section template, write sample questions, click Preview, publish, then create an exam from it as a teacher; try display mode "scrolling".

## 3. Open questions (defaults in effect)
| # | Question | Default |
|---|---|---|
| 8b-Q1 | Sample questions of a template | One hidden sandbox course per template |
| 8b-Q2 | Who may preview a template | Its managers only |
| 8b-Q3 | Scrolling window | 30 questions, one section at a time |
| 8b-Q4 | Constructor saving | Autosave |
| 8b-Q5 | ORT-style scaled result page on general quizzes | Allowed |
| 8b-Q6 | Move ORT onto the constructor | No, ORT stays on presets |
| 8a-Q1 | Module locks on ORT exams | Never (ORT exam always startable) |
| 8a-Q2 | Home of new general courses | Modules |
| 8a-Q3 | Page format | Markdown with formulas |
| 8a-Q4 | Course files budget | 500 MiB per course (R2 free tier) |
| 8a-Q5 | Modules/pages/files/announcements inside ORT courses | Allowed; students see them only when published |
| 7a-Q1 | Extra time for accommodated students on ORT exams | Not applied |
| 7a-Q2 | Upload storage | 5 MB per student file, per-course cap |
| 7a-Q3 | Who sets accommodations | Course teachers |
| 7a-Q4 | Access codes on ORT exams | Not allowed |
| 7a-Q5 | Homework inside ORT courses | Not allowed |
| 7a-Q6 | ORT gradebook "total %" column | Unchanged |
| 7b-Q1 | "Save as template" on ORT exams | Refused |
| P8 | Kyrgyz comparison answer labels in sentence case | See `ORT_PLAYER_IDEAS.md` |

## 4. Known limitations
- 7c: a new question written inside a quiz-bank passage appears outside the passage block in the editor (students see it correctly).
- Phone course tabs open scrolled so the first tab is hidden (older course header).
- The grading-scheme detail page scrolls sideways at 375 px because a wide formula in the parameter editor (Phase 4 screen, older).
- Before the first real exam: Render plan and a custom domain for R2 (owner decision, costs money).

## 5. Next phases (plan)
9 organizations completion and enrollment forms → 10 practice, analytics, quiz statistics, new question types (matching, fill-in-the-blank, ordering) → 11 privacy (parent consent), hardening, launch.
