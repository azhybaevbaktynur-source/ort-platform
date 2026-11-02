# UX rework, part 2 (owner feedback 2026-11-03, items 7–12)

Same rules as `UX_REWORK.md`: orchestrator checks changed screens at 375 / 1440 / 1920 px in ru, ORT behaviour unchanged, stop for the owner's review when done. Step 2 (`docs/DISCUSSION_ACCOUNTS.md`) only after the owner's OK.

## Item 7 and 12: one cause
Reproduced locally by delaying the API: `Учёба / Преподавание / Админ-панель` and "—" on the cards. Every area has its own layout, so moving between areas mounted a new shell that started empty; the menu and the cards drew before the answers arrived, and a failed call was swallowed and stayed that way.
- `GET /me/lms` now also returns `admin_organizations` and `is_guardian`: the whole menu comes from one answer. The separate `/me/organizations` call in the shell is gone.
- The answer is kept per token (memory + this tab's `sessionStorage`) and refreshed in the background. It only draws the menu; the server still decides every permission.
- First visit: placeholders, never a partial menu. Removed the rule that added "Родитель" only on `/parent`; pairing reloads the account instead.
- `GET /platform/summary` also returns `storage_level`: both overview cards come from one answer, with a loading state, one automatic retry, then an error with a retry button. Never "—".
- Test: `frontend/e2e/header-areas.spec.ts`, `backend/tests/lms/test_me_areas.py`.

## Item 9: mascot
`scripts/mascot_crop.py` cuts `docs/mascot/mascot_sheet.png` into `frontend/public/mascot/<pose>.webp|png`. `components/ui/Mascot.tsx`: `pose`, `size`, lazy, empty alt. Dropping `public/mascot/<pose>.svg` replaces a pose at the next build with no code change (`next.config.ts`). `EmptyState` has a `mascot` prop.

## Item 8: landing
`app/[lang]/page.tsx`, `components/landing/*`, new public pages `for-teachers`, `about`, `help`, `contacts`. Screenshots in `public/landing/<name>-<lang>.webp` come from real screens: `RECORD_LANDING=1 ... npx playwright test e2e/landing-screens.spec.ts` (`seed_landing`: fictional school). Re-record when the dashboard, player or teacher course page changes visibly.

## Item 10: name
`common.appName` in `en.json`, `ky.json`, `ru.json`: one line per language. Everything uses it.

## Item 11: course card
`components/lms/course/CourseCard.tsx` is the only card (dashboard, catalog, teaching list, trash). `GET /me/home/courses` pages the dashboard's "show all". `useGradeListText` + `grade_max` for grades in lists. Decisions: `PRODUCT_DECISIONS.md` UR2-*.

## Results
See the end of this file after deployment.

