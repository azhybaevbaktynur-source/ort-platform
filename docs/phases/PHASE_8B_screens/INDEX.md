# Phase 8b screens

## S3: scrolling player and display settings

All written by `frontend/e2e/scrolling-player.spec.ts`. The UX-gate screenshots come from
`PHASE8B_SCREENS_DIR=docs/phases/PHASE_8B_screens` and the test "UX-gate screenshots". Viewports are `phone`
(375x812) and `desktop` (1440x900), on macOS with system Chrome. The data is the `seed_scrolling` course: "Длинный тест E2E" has
48 items (section 1 with 45, section 2 with a numbered passage, two questions and one more question). Its content is
in Russian, and the UI language is the one in the file name. Before the shots, questions 1, 2, 3 and 5 are
answered and question 2 is flagged.

| File | Screen |
|---|---|
| `scrolling-top-{desktop,phone}-{ru,ky,en}.png` | Top of section 1. Window 1–30, sticky footer "Show the next 15", item 1 current, desktop palette beside it. |
| `scrolling-mid-{desktop,phone}-{ru,ky,en}.png` | Mid-scroll at question 12. On desktop, reached by a palette click; the sticky palette highlights 12. On phone, reached by scrolling; the header counter reads 12/48. |
| `scrolling-footer-{desktop,phone}-{ru,ky,en}.png` | End of window 1 with the window footer. |
| `scrolling-sheet-phone-{ru,ky,en}.png` | Phone palette sheet (unchanged component). Both sections are shown, with answered and flagged states. |
| `scrolling-passage-{desktop,phone}-{ru,ky,en}.png` | Section 2 after "Next section": the passage once above its questions (numbered lines), plus the footer "Finish test". |
| `result-{desktop,phone}-{ru,ky,en}.png` | General result page (`result_view` inherited: general). |
| `review-passage-{desktop,phone}-{ru,ky,en}.png` | Review card with the numbered passage opened (`passage_display` from the review payload). |
| `settings-display-{desktop,phone}-{ru,en}.png` | Teacher, quiz editor Settings tab: the "Display" group (layout radios, reading texts, result page with the course default). |

Total: 43 screenshots in this folder.

### `general-player/` (pixel baselines)

The test "general player baselines" compares these on every run, with the same comparison as `ORT_BASELINE`
(timer masked). `UPDATE_BASELINES=1` re-records them; run that spec alone when you do. Other platforms
use a subfolder named after `process.platform`, which CI records with `ORT_BASELINE_RECORD_MISSING=1`.

| File | Screen |
|---|---|
| `scrolling-top-{desktop,phone}-ru.png` | Scrolling player, top of section 1, nothing answered. |
| `one-per-page-{desktop,phone}-ru.png` | One-per-page general player, question 1 of 3 (regression shot: unchanged layout). |

## S5: exam-template constructor, preview, teacher "Create from template"

All written by `frontend/e2e/exam-constructor.spec.ts` with `PHASE8B_SCREENS_DIR=docs/phases/PHASE_8B_screens`: the
walk test writes the three `*-desktop-ru` preview/locked shots, the test "UX-gate screenshots" writes the rest after
the walk. Viewports `phone` (375x812) and `desktop` (1440x900), macOS, system Chrome. Data: the `seed_constructor`
organization "Школа E2E"; the walk's organization template "Вступительный тест E2E" (v2: three sections, forward-only,
scrolling, ORT main scheme, ORT-style result, lock scope "sections"), its sample quiz, and the teacher's exam
"Вступительный тест, 9 класс" built from v1. Content is Russian; the UI language is the one in the file name.
Admin and teacher screens are ru + en; the student result is ru + ky + en.

| File | Screen |
|---|---|
| `ctor-list-{desktop,phone}-{ru,en}.png` | Org area, exam template list: organization and teacher templates; a teacher's template reads "Teacher's" (not "Mine"). |
| `ctor-structure-{desktop,phone}-{ru,en}.png` | Constructor header (scope, status, v2, Publish / Preview / More) and the Structure tab (general settings). |
| `ctor-section-{desktop,phone}-{ru,en}.png` | Structure tab: section 2 expanded (title, instructions, time, counts, allowed types, passages numbered, key). |
| `ctor-scoring-{desktop,phone}-{ru,en}.png` | Scoring tab: system scheme "ORT main test" with the live preview table. |
| `ctor-display-{desktop,phone}-{ru,en}.png` | Display tab: display mode cards with illustrations (scrolling chosen), passage display per section. |
| `ctor-lockscope-{desktop,phone}-{ru,en}.png` | Display tab: lock scope checklist with the plain-language effect of each key ("sections" ticked). |
| `ctor-sample-{desktop,phone}-{ru,en}.png` | Sample questions tab: note, "Preview as student" launcher, the 7c card editor per section (read-only headers). |
| `ctor-sample-gate-{desktop,phone}-{ru,en}.png` | Sample tab of a new template before the sandbox exists (language choice, "Start writing sample questions"). |
| `ctor-preview-not-ready-{desktop,phone}-{ru,en}.png` | "Preview as student" with empty sections: `preview_not_ready` message and the per-section issues. |
| `ctor-diff-{desktop,phone}-{ru,en}.png` | Versions tab, DiffView v1 -> v2 (element): summary chips, section 1 time changed, section 3 added; phone stacks before/after. |
| `ctor-publish-dialog-{desktop,phone}-{ru,en}.png` | Publish confirmation of a new template ("becomes version v1"). |
| `ctor-lock-dialog-{desktop,phone}-{ru,en}.png` | Lock dialog with the optional reason. |
| `ctor-promote-dialog-{desktop,phone}-{ru,en}.png` | Org admin, a teacher's template: "Move the template to the organization?" dialog. |
| `ctor-conflict-{desktop,phone}-{ru,en}.png` | Draft conflict (saved meanwhile elsewhere): template wording, keep my changes / take the saved version. |
| `ctor-issues-{desktop,phone}-{ru,en}.png` | Validation: a section with no question type; "Not saved: 1 problem" and the issues bar with "Go to". |
| `ctor-locked-desktop-ru.png` | Locked template, read-only for its owner (note points to More -> Unlock), right after locking (toast). |
| `ctor-preview-player-desktop-ru.png` | The preview attempt in the real general player: amber preview banner, scrolling, forward-only section timer. |
| `ctor-preview-result-desktop-ru.png` | Preview result (ORT-style, section names from the template) without the sandbox course frame; "Back" returns to the Sample tab. |
| `teacher-create-from-template-{desktop,phone}-{ru,en}.png` | Teacher, Assignments -> New -> Quiz with the template picker (v2): locked structure line, sections summary. |
| `teacher-template-exam-{desktop,phone}-{ru,en}.png` | Teacher's card editor of the exam built from the locked template: locked-sections note, "Add section" disabled. |
| `tpl-result-ort-{desktop,phone}-{ru,ky,en}.png` | Student, result of the template exam (general quiz, `result_view = ort`): scaled grade, section names from the template. |

S5 total: 77 screenshots (120 in this folder with S3's 43, plus `general-player/`).
