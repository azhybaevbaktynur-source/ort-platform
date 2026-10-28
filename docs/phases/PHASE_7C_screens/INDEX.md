# Phase 7c UX gate screenshots

Quiz editor (PHASE_7C_DESIGN 12). First taken by the S5 integration slice; every screen changed by the **UX fix slice**
(branch `phase-7c-ux`, findings 1-17 of the UX review) was re-taken on 2026-10-28 against a scratch backend
(`scripts/e2e_backend.sh`, seed `frontend/e2e/seed_backend.py`, plus quizzes built through the API by a one-off
Playwright script) and a production build (`next start`), system Chrome, device scale factor 1. Viewports: `desktop` =
1440x900, `phone` = 375x812 (full page where the height is larger). Teacher screens in en and ru, the main editor screen
also in ky; student screens in en, ky and ru at both sizes. Course content is Russian in every language. Stubbed:
`scope-dialog-all-disabled` (commit response with `can_update_all=false`, the Phase 9 case) and `version-conflict`
(a 409 `version_conflict` response); everything else is real data.

URLs: `/<lang>/courses/<general course>/assessments/<quiz>/edit` for the editor screens (quiz named in the table),
`/<lang>/courses/<course>/assessments/<quiz>` (lobby) and `/<lang>/courses/<course>/attempts/<attempt>` (player).

80 images, 7.2 MB.

| File | What | Change | Quiz / page | Size | Lang |
|---|---|---|---|---|---|
| `editor-empty-desktop-en.png` | Quiz editor, empty quiz: empty state with primary 'New question' and 'Add from a bank'; Publish secondary while the quiz has 0 questions | UX fix 14 | Новый квиз | 1440x900 | en |
| `editor-empty-desktop-ru.png` | Quiz editor, empty quiz: empty state with primary 'New question' and 'Add from a bank'; Publish secondary while the quiz has 0 questions | UX fix 14 | Новый квиз | 1440x900 | ru |
| `editor-empty-phone-en.png` | Quiz editor, empty quiz: empty state with primary 'New question' and 'Add from a bank'; Publish secondary while the quiz has 0 questions | UX fix 14 | Новый квиз | 375x812 | en |
| `editor-empty-phone-ru.png` | Quiz editor, empty quiz: empty state with primary 'New question' and 'Add from a bank'; Publish secondary while the quiz has 0 questions | UX fix 14 | Новый квиз | 375x812 | ru |
| `editor-cards-desktop-en.png` | Collapsed cards: five types with correct answers, 'Only in this quiz' on quiz-bank cards (the quiz also has shared-bank cards), two shared cards; tab count = publish bar count | UX fix 9, 10 | Квиз с карточками | 1440x1659 | en |
| `editor-cards-desktop-ky.png` | Collapsed cards: five types with correct answers, 'Only in this quiz' on quiz-bank cards (the quiz also has shared-bank cards), two shared cards; tab count = publish bar count | UX fix 9, 10 | Квиз с карточками | 1440x1659 | ky |
| `editor-cards-desktop-ru.png` | Collapsed cards: five types with correct answers, 'Only in this quiz' on quiz-bank cards (the quiz also has shared-bank cards), two shared cards; tab count = publish bar count | UX fix 9, 10 | Квиз с карточками | 1440x1659 | ru |
| `editor-cards-phone-en.png` | Collapsed cards: five types with correct answers, 'Only in this quiz' on quiz-bank cards (the quiz also has shared-bank cards), two shared cards; tab count = publish bar count | UX fix 9, 10 | Квиз с карточками | 375x2058 | en |
| `editor-cards-phone-ky.png` | Collapsed cards: five types with correct answers, 'Only in this quiz' on quiz-bank cards (the quiz also has shared-bank cards), two shared cards; tab count = publish bar count | UX fix 9, 10 | Квиз с карточками | 375x2028 | ky |
| `editor-cards-phone-ru.png` | Collapsed cards: five types with correct answers, 'Only in this quiz' on quiz-bank cards (the quiz also has shared-bank cards), two shared cards; tab count = publish bar count | UX fix 9, 10 | Квиз с карточками | 375x2084 | ru |
| `card-open-desktop-en.png` | Open multiple-choice card, compact: no inner boxes, no language row (one-language quiz), preview only for math/markup, one line per answer (correct mark, letter, growing text, image/move/remove actions; a menu on phones), 'Add image' button, answer and explanation toolbars only on focus | UX fix 1, 13 | Квиз с карточками | 1440x2448 | en |
| `card-open-desktop-ru.png` | Open multiple-choice card, compact: no inner boxes, no language row (one-language quiz), preview only for math/markup, one line per answer (correct mark, letter, growing text, image/move/remove actions; a menu on phones), 'Add image' button, answer and explanation toolbars only on focus | UX fix 1, 13 | Квиз с карточками | 1440x2448 | ru |
| `card-open-phone-en.png` | Open multiple-choice card, compact: no inner boxes, no language row (one-language quiz), preview only for math/markup, one line per answer (correct mark, letter, growing text, image/move/remove actions; a menu on phones), 'Add image' button, answer and explanation toolbars only on focus | UX fix 1, 13 | Квиз с карточками | 375x3072 | en |
| `card-open-phone-ru.png` | Open multiple-choice card, compact: no inner boxes, no language row (one-language quiz), preview only for math/markup, one line per answer (correct mark, letter, growing text, image/move/remove actions; a menu on phones), 'Add image' button, answer and explanation toolbars only on focus | UX fix 1, 13 | Квиз с карточками | 375x3138 | ru |
| `card-errors-desktop-en.png` | Done with an empty question text: the error under the field (aria-describedby), field focused and scrolled to, one line 'Fix the highlighted fields' at Done | UX fix 2 | Квиз с карточками | 1440x900 | en |
| `card-errors-desktop-ru.png` | Done with an empty question text: the error under the field (aria-describedby), field focused and scrolled to, one line 'Fix the highlighted fields' at Done | UX fix 2 | Квиз с карточками | 1440x900 | ru |
| `card-errors-phone-en.png` | Done with an empty question text: the error under the field (aria-describedby), field focused and scrolled to, one line 'Fix the highlighted fields' at Done | UX fix 2 | Квиз с карточками | 375x812 | en |
| `card-errors-phone-ru.png` | Done with an empty question text: the error under the field (aria-describedby), field focused and scrolled to, one line 'Fix the highlighted fields' at Done | UX fix 2 | Квиз с карточками | 375x812 | ru |
| `draft-chips-desktop-en.png` | Card with a draft that has errors and the publish bar note 'unfinished edits (saved as a draft)'; 'Check for problems' | UX fix 3, 15 | Квиз с карточками | 1440x900 | en |
| `draft-chips-desktop-ru.png` | Card with a draft that has errors and the publish bar note 'unfinished edits (saved as a draft)'; 'Check for problems' | UX fix 3, 15 | Квиз с карточками | 1440x900 | ru |
| `draft-chips-phone-en.png` | Card with a draft that has errors and the publish bar note 'unfinished edits (saved as a draft)'; 'Check for problems' | UX fix 3, 15 | Квиз с карточками | 375x812 | en |
| `draft-chips-phone-ru.png` | Card with a draft that has errors and the publish bar note 'unfinished edits (saved as a draft)'; 'Check for problems' | UX fix 3, 15 | Квиз с карточками | 375x812 | ru |
| `publish-drafts-confirm-desktop-en.png` | Publish with unfinished drafts: 'Publish without the unfinished edits?', each item prefixed with its card label | UX fix 3 | Квиз с карточками | 1440x900 | en |
| `publish-drafts-confirm-desktop-ru.png` | Publish with unfinished drafts: 'Publish without the unfinished edits?', each item prefixed with its card label | UX fix 3 | Квиз с карточками | 1440x900 | ru |
| `publish-drafts-confirm-phone-en.png` | Publish with unfinished drafts: 'Publish without the unfinished edits?', each item prefixed with its card label | UX fix 3 | Квиз с карточками | 375x812 | en |
| `publish-drafts-confirm-phone-ru.png` | Publish with unfinished drafts: 'Publish without the unfinished edits?', each item prefixed with its card label | UX fix 3 | Квиз с карточками | 375x812 | ru |
| `scope-dialog-desktop-en.png` | Scope dialog: 'Change only in this quiz' primary, 'Update in all 2 quizzes' secondary | UX fix 11 | Квиз с карточками | 1440x900 | en |
| `scope-dialog-desktop-ru.png` | Scope dialog: 'Change only in this quiz' primary, 'Update in all 2 quizzes' secondary | UX fix 11 | Квиз с карточками | 1440x900 | ru |
| `scope-dialog-phone-en.png` | Scope dialog: 'Change only in this quiz' primary, 'Update in all 2 quizzes' secondary | UX fix 11 | Квиз с карточками | 375x812 | en |
| `scope-dialog-phone-ru.png` | Scope dialog: 'Change only in this quiz' primary, 'Update in all 2 quizzes' secondary | UX fix 11 | Квиз с карточками | 375x812 | ru |
| `scope-dialog-all-disabled-desktop-en.png` | Scope dialog when 'all' is not possible (stubbed can_update_all=false): the button is hidden, the reason stays | UX fix 11 | Квиз с карточками | 1440x900 | en |
| `scope-dialog-all-disabled-desktop-ru.png` | Scope dialog when 'all' is not possible (stubbed can_update_all=false): the button is hidden, the reason stays | UX fix 11 | Квиз с карточками | 1440x900 | ru |
| `scope-dialog-all-disabled-phone-en.png` | Scope dialog when 'all' is not possible (stubbed can_update_all=false): the button is hidden, the reason stays | UX fix 11 | Квиз с карточками | 375x812 | en |
| `scope-dialog-all-disabled-phone-ru.png` | Scope dialog when 'all' is not possible (stubbed can_update_all=false): the button is hidden, the reason stays | UX fix 11 | Квиз с карточками | 375x812 | ru |
| `scope-dialog-passage-child-desktop-en.png` | Scope dialog for a passage child: 'Update in all' primary, 'only this quiz' disabled with its reason | UX fix 11 | Квиз с разделами | 1440x900 | en |
| `scope-dialog-passage-child-desktop-ru.png` | Scope dialog for a passage child: 'Update in all' primary, 'only this quiz' disabled with its reason | UX fix 11 | Квиз с разделами | 1440x900 | ru |
| `scope-dialog-passage-child-phone-en.png` | Scope dialog for a passage child: 'Update in all' primary, 'only this quiz' disabled with its reason | UX fix 11 | Квиз с разделами | 375x812 | en |
| `scope-dialog-passage-child-phone-ru.png` | Scope dialog for a passage child: 'Update in all' primary, 'only this quiz' disabled with its reason | UX fix 11 | Квиз с разделами | 375x812 | ru |
| `version-conflict-desktop-en.png` | Version conflict (stubbed 409): body ends with 'Your draft is kept until you choose'; closing with X keeps the draft | UX fix 17 | Квиз с карточками | 1440x900 | en |
| `version-conflict-desktop-ru.png` | Version conflict (stubbed 409): body ends with 'Your draft is kept until you choose'; closing with X keeps the draft | UX fix 17 | Квиз с карточками | 1440x900 | ru |
| `version-conflict-phone-en.png` | Version conflict (stubbed 409): body ends with 'Your draft is kept until you choose'; closing with X keeps the draft | UX fix 17 | Квиз с карточками | 375x812 | en |
| `version-conflict-phone-ru.png` | Version conflict (stubbed 409): body ends with 'Your draft is kept until you choose'; closing with X keeps the draft | UX fix 17 | Квиз с карточками | 375x812 | ru |
| `find-questions-desktop-en.png` | Find questions: title 'Find questions', search on top, filters behind 'Filters' on phones, new translation hint, sticky footer with 'Add selected' | UX fix 7 | Квиз с карточками | 1440x900 | en |
| `find-questions-desktop-ru.png` | Find questions: title 'Find questions', search on top, filters behind 'Filters' on phones, new translation hint, sticky footer with 'Add selected' | UX fix 7 | Квиз с карточками | 1440x900 | ru |
| `find-questions-phone-en.png` | Find questions: title 'Find questions', search on top, filters behind 'Filters' on phones, new translation hint, sticky footer with 'Add selected' | UX fix 7 | Квиз с карточками | 375x812 | en |
| `find-questions-phone-ru.png` | Find questions: title 'Find questions', search on top, filters behind 'Filters' on phones, new translation hint, sticky footer with 'Add selected' | UX fix 7 | Квиз с карточками | 375x812 | ru |
| `sections-desktop-en.png` | Two sections; passage block with a shared child; random group card with 'Points per question' (placeholder 1) | UX fix 12 | Квиз с разделами | 1440x1303 | en |
| `sections-desktop-ru.png` | Two sections; passage block with a shared child; random group card with 'Points per question' (placeholder 1) | UX fix 12 | Квиз с разделами | 1440x1303 | ru |
| `sections-phone-en.png` | Two sections; passage block with a shared child; random group card with 'Points per question' (placeholder 1) | UX fix 12 | Квиз с разделами | 375x1734 | en |
| `sections-phone-ru.png` | Two sections; passage block with a shared child; random group card with 'Points per question' (placeholder 1) | UX fix 12 | Квиз с разделами | 375x1764 | ru |
| `passage-child-open-desktop-en.png` | Open passage child from a shared bank used by another quiz (compact card, 'applies to all' note) | UX fix 1 | Квиз с разделами | 1440x900 | en |
| `passage-child-open-desktop-ru.png` | Open passage child from a shared bank used by another quiz (compact card, 'applies to all' note) | UX fix 1 | Квиз с разделами | 1440x900 | ru |
| `passage-child-open-phone-en.png` | Open passage child from a shared bank used by another quiz (compact card, 'applies to all' note) | UX fix 1 | Квиз с разделами | 375x812 | en |
| `passage-child-open-phone-ru.png` | Open passage child from a shared bank used by another quiz (compact card, 'applies to all' note) | UX fix 1 | Квиз с разделами | 375x812 | ru |
| `move-to-bank-desktop-en.png` | Move or copy to a shared bank: usage note in the singular, 'Used in 1 quiz; the link is kept.' | UX fix 16 | Bank tab, quiz bank of 'Квиз с карточками' | 1440x900 | en |
| `move-to-bank-desktop-ru.png` | Move or copy to a shared bank: usage note in the singular, 'Used in 1 quiz; the link is kept.' | UX fix 16 | Bank tab, quiz bank of 'Квиз с карточками' | 1440x900 | ru |
| `move-to-bank-phone-en.png` | Move or copy to a shared bank: usage note in the singular, 'Used in 1 quiz; the link is kept.' | UX fix 16 | Bank tab, quiz bank of 'Квиз с карточками' | 375x812 | en |
| `move-to-bank-phone-ru.png` | Move or copy to a shared bank: usage note in the singular, 'Used in 1 quiz; the link is kept.' | UX fix 16 | Bank tab, quiz bank of 'Квиз с карточками' | 375x812 | ru |
| `student-lobby-desktop-en.png` | Student lobby of a one-section quiz: the 'Sections' card is hidden | UX fix 5 | Квиз для ученика | 1440x900 | en |
| `student-lobby-desktop-ky.png` | Student lobby of a one-section quiz: the 'Sections' card is hidden | UX fix 5 | Квиз для ученика | 1440x900 | ky |
| `student-lobby-desktop-ru.png` | Student lobby of a one-section quiz: the 'Sections' card is hidden | UX fix 5 | Квиз для ученика | 1440x900 | ru |
| `student-lobby-phone-en.png` | Student lobby of a one-section quiz: the 'Sections' card is hidden | UX fix 5 | Квиз для ученика | 375x812 | en |
| `student-lobby-phone-ky.png` | Student lobby of a one-section quiz: the 'Sections' card is hidden | UX fix 5 | Квиз для ученика | 375x812 | ky |
| `student-lobby-phone-ru.png` | Student lobby of a one-section quiz: the 'Sections' card is hidden | UX fix 5 | Квиз для ученика | 375x812 | ru |
| `student-question-desktop-en.png` | Student player of a one-section quiz: the header shows the quiz title instead of 'Section 1'; 'No time limit' and 'Saved' wrap instead of overlapping at 375 px | UX fix 5, 6 | Квиз для ученика | 1440x900 | en |
| `student-question-desktop-ky.png` | Student player of a one-section quiz: the header shows the quiz title instead of 'Section 1'; 'No time limit' and 'Saved' wrap instead of overlapping at 375 px | UX fix 5, 6 | Квиз для ученика | 1440x900 | ky |
| `student-question-desktop-ru.png` | Student player of a one-section quiz: the header shows the quiz title instead of 'Section 1'; 'No time limit' and 'Saved' wrap instead of overlapping at 375 px | UX fix 5, 6 | Квиз для ученика | 1440x900 | ru |
| `student-question-phone-en.png` | Student player of a one-section quiz: the header shows the quiz title instead of 'Section 1'; 'No time limit' and 'Saved' wrap instead of overlapping at 375 px | UX fix 5, 6 | Квиз для ученика | 375x812 | en |
| `student-question-phone-ky.png` | Student player of a one-section quiz: the header shows the quiz title instead of 'Section 1'; 'No time limit' and 'Saved' wrap instead of overlapping at 375 px | UX fix 5, 6 | Квиз для ученика | 375x812 | ky |
| `student-question-phone-ru.png` | Student player of a one-section quiz: the header shows the quiz title instead of 'Section 1'; 'No time limit' and 'Saved' wrap instead of overlapping at 375 px | UX fix 5, 6 | Квиз для ученика | 375x812 | ru |

Unchanged by the UX fix slice (S5 images; the Bank tab is not touched):

| File | What | URL | Size | Lang |
|---|---|---|---|---|
| `bank-quiz-banks-desktop-en.png` | Bank tab: 'Shared banks' and 'Quiz banks' groups | `/en/courses/5b49a2b5-bb91-40ae-af9c-5615ba8e4671/bank` | 1440x900 (full page) | en |
| `bank-quiz-banks-desktop-ru.png` | Bank tab: 'Shared banks' and 'Quiz banks' groups | `/ru/courses/5b49a2b5-bb91-40ae-af9c-5615ba8e4671/bank` | 1440x900 (full page) | ru |
| `bank-quiz-banks-phone-en.png` | Bank tab: 'Shared banks' and 'Quiz banks' groups | `/en/courses/5b49a2b5-bb91-40ae-af9c-5615ba8e4671/bank` | 375x812 (full page) | en |
| `bank-quiz-banks-phone-ru.png` | Bank tab: 'Shared banks' and 'Quiz banks' groups | `/ru/courses/5b49a2b5-bb91-40ae-af9c-5615ba8e4671/bank` | 375x812 (full page) | ru |
| `bank-new-question-general-desktop-en.png` | Shared bank of a general course: 'New question' is a plain button (type chosen in the form) | `/en/courses/5b49a2b5-bb91-40ae-af9c-5615ba8e4671/bank/50a38d0d-1d29-49ed-a88e-6b0cec669658` | 1440x900 | en |
| `bank-new-question-general-desktop-ru.png` | Shared bank of a general course: 'New question' is a plain button (type chosen in the form) | `/ru/courses/5b49a2b5-bb91-40ae-af9c-5615ba8e4671/bank/50a38d0d-1d29-49ed-a88e-6b0cec669658` | 1440x900 | ru |
| `bank-new-question-general-phone-en.png` | Shared bank of a general course: 'New question' is a plain button (type chosen in the form) | `/en/courses/5b49a2b5-bb91-40ae-af9c-5615ba8e4671/bank/50a38d0d-1d29-49ed-a88e-6b0cec669658` | 375x812 | en |
| `bank-new-question-general-phone-ru.png` | Shared bank of a general course: 'New question' is a plain button (type chosen in the form) | `/ru/courses/5b49a2b5-bb91-40ae-af9c-5615ba8e4671/bank/50a38d0d-1d29-49ed-a88e-6b0cec669658` | 375x812 | ru |
| `bank-new-question-ort-desktop-ru.png` | ORT (Russian) bank: 'New question' stays a type menu (unchanged) | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/bank/533f43fc-b212-4ea9-bb52-d9e95705e4e8` | 1440x900 | ru |
| `bank-new-question-ort-phone-ru.png` | ORT (Russian) bank: 'New question' stays a type menu (unchanged) | `/ru/courses/f2a2186b-f8b4-5c06-af1f-7205b865c48f/bank/533f43fc-b212-4ea9-bb52-d9e95705e4e8` | 375x812 | ru |
