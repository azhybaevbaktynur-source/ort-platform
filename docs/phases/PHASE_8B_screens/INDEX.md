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
