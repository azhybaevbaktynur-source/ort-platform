# Exam player in Bluebook style (owner, 2026-11-01): design

Owner decision: overrides the earlier "no layout change" rule for the ORT player. **Exam rules, timing, forward-only sections, scoring, autosave and imports stay exactly the same. Frontend only: no backend, API or snapshot change.** Same layout for ORT and general exams. Result and answer-review pages after the exam don't change.

## Layout (`components/lms/player/`)
- Full width (`w-full`, with side gutters); the right palette column and the phone palette sheet go.
- **Top bar**: left: section name + "Directions" dropdown (section instructions; replaces the instructions `<details>`; hidden when a section has none). Center: timer + "Hide"/"Show" button. Right: save status ("Saved") + "More" menu (what lived on the screen and isn't an exam action: keyboard shortcuts, leave/back link if present). No student name. Exam title may go in "More".
- **Bottom bar**, fixed: left "Back" (only where navigation allows, same rule as today); center "Question 1 of 30 ▾" opening a popup: question-number grid (same groups, states and forward-only locks as today's palette), legend (Current, Unanswered, For review), "Go to review page" button; right "Next". On the last question of a section "Next" opens the review page. Content needs bottom padding so nothing sits under the bar.
- **Question header**: number + "Mark for review" (bookmark), replacing "Пометить" (same flag API, `F` hotkey stays).
- **Review page** (client-side view inside the player, not a route): at the end of each section: all its questions with their state; tap to jump (only where navigation allows); "Завершить раздел" (or "Завершить тест" on the last section) moves here, out of the main screen, and opens **today's confirmation dialogs unchanged**, no-return warning included. A single-section general exam gets the same page with "Завершить тест".
- **Reading with a passage**: from `lg`, split screen: passage left (with ORT line numbers, same component), question and answers right, each scrolling independently; a draggable divider (`role="separator"`, arrow keys work, clamp about 30–70 %, position remembered per tab). Below `lg`, passage and question stack vertically; the bottom bar stays fixed.
- **Math I comparison**: Column A / Column B stay side by side above the answers, as now.
- **Scrolling display mode** (general, 8b): same top and bottom bars; the popup jumps by scrolling; "Back"/"Next" move between questions or sections as that mode allows today. Keep its behaviour.
- **Practice** (Phase 10): "Проверить" stays under the question; practice has no timer, so the center shows today's "no time limit" text.
- Preview banner and Student view banner keep working above the top bar.

## Behaviour that must not change
Timer values and expiry; existing time warnings; forward-only sections and locks; autosave and its error states; offline notice; flag state; hotkeys (arrows, F, 1-5, A-E; ignored while typing or with the popup open); time-up and closed flows; attempt resume; section close and submit calls; focus return and Esc on the popup; a11y labels in all three languages.

Decisions: "Hide" is view-only and per attempt tab; a hidden timer shows itself again in the last 5 minutes and time-up behaves as today. Answer-elimination toggle: **not built**; it goes in `docs/ORT_PLAYER_IDEAS.md` (it needs persistence and hotkey decisions to be right).

## Proof
Backend untouched: ORT parity job, golden and scoring tests stay green with no change. `frontend/e2e/ort.spec.ts` keeps every behaviour assertion (section order and counts, timer, flag and answer state, comparison columns, line numbers, forward-only, result); `ort-exam.ts` helpers follow the new controls. New approved baselines for the player screens only (lobby, result, answer review and teacher screens must not change); add `review-page`.

## Report
Deployed 2026-11-02 (`main` 10c0855, frontend only, no backend file changed). 52 browser tests passed, ORT DOM walk green, zero pixel differences against the new baselines; CI six jobs green, including ORT parity. Only one `ort.spec` assertion changed, on phones: "Finish" pinned in the sheet became "Go to review" pinned, and focus returns to Finish. New approved baselines: comparison, flagged palette, passage, section end, submit, review page, and the general one-per-page and scrolling screens, viewed by the orchestrator. Lobby, result, answer review and teacher screens unchanged.
Production (QA student, practice set, ru, 375 / 1440 / 1920): top bar, question popup, review page, no sideways scroll, no page errors. Timed ORT sections, the passage split and forward-only flow were verified locally only (the QA student isn't enrolled in ORT).
Choices: questions capped at `max-w-4xl` with bars full width; Directions closed by default; the Student view banner also shows inside the player.
