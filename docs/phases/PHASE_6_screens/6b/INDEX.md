# Phase 6b UX-gate screenshots

## S5a design system (`frontend/src/components/ui/`, branch `phase-6/s5a-ui`, 2026-10-25)

66 JPEG files (quality 72). Showcase page `/[lang]/dev/ui` (development only, `notFound()` in production), shot with playwright-core + Chrome against `next dev` from an rsync'd copy. Section shots are element screenshots of one `<section>`; `dialog-*` and `toasts-*` are viewport shots. Viewports: phone 375x812 (`isMobile`, deviceScaleFactor 1), desktop 1440x900. Measured `document.documentElement.scrollWidth` = 375 at 375 px (ru, ky, en), also after opening dialogs, toasts, the picker and the table states. Keyboard checks in the same run: focus moves into the dialog, Esc closes it and focus returns to the opener, Tab stays inside the dialog, ConfirmDialog starts on Cancel.

| File | Shows | Route | Viewport | Lang |
|---|---|---|---|---|
| ui-badges-desktop-ru.jpg | Badge tones neutral / info / success / warning / danger / system | `/ru/dev/ui` | 1440x900 | ru |
| ui-badges-phone-ru.jpg | Badge tones neutral / info / success / warning / danger / system | `/ru/dev/ui` | 375x812 | ru |
| ui-buttons-desktop-ru.jpg | Button variants, sizes, loading (spinner + aria-busy), disabled; LinkButton; IconButton | `/ru/dev/ui` | 1440x900 | ru |
| ui-buttons-phone-ky.jpg | Button variants, sizes, loading (spinner + aria-busy), disabled; LinkButton; IconButton | `/ky/dev/ui` | 375x812 | ky |
| ui-buttons-phone-ru.jpg | Button variants, sizes, loading (spinner + aria-busy), disabled; LinkButton; IconButton | `/ru/dev/ui` | 375x812 | ru |
| ui-cards-desktop-ru.jpg | Card with actions, StatTile (plain, link, gold), DescriptionList (stacked 2-col, columns) | `/ru/dev/ui` | 1440x900 | ru |
| ui-cards-phone-ky.jpg | Card with actions, StatTile (plain, link, gold), DescriptionList (stacked 2-col, columns) | `/ky/dev/ui` | 375x812 | ky |
| ui-cards-phone-ru.jpg | Card with actions, StatTile (plain, link, gold), DescriptionList (stacked 2-col, columns) | `/ru/dev/ui` | 375x812 | ru |
| ui-dialog-confirm-desktop-ky.jpg | ConfirmDialog danger: object + effect, focus starts on Cancel (ring shown after Tab cycling) | `/ky/dev/ui` | 1440x900 | ky |
| ui-dialog-confirm-desktop-ru.jpg | ConfirmDialog danger: object + effect, focus starts on Cancel (ring shown after Tab cycling) | `/ru/dev/ui` | 1440x900 | ru |
| ui-dialog-confirm-phone-ky.jpg | ConfirmDialog danger: object + effect, focus starts on Cancel (ring shown after Tab cycling) | `/ky/dev/ui` | 375x812 | ky |
| ui-dialog-confirm-phone-ru.jpg | ConfirmDialog danger: object + effect, focus starts on Cancel (ring shown after Tab cycling) | `/ru/dev/ui` | 375x812 | ru |
| ui-dialog-form-desktop-ky.jpg | Dialog with a field (focus on the input; footer primary on top on phones) | `/ky/dev/ui` | 1440x900 | ky |
| ui-dialog-form-desktop-ru.jpg | Dialog with a field (focus on the input; footer primary on top on phones) | `/ru/dev/ui` | 1440x900 | ru |
| ui-dialog-form-phone-ky.jpg | Dialog with a field (focus on the input; footer primary on top on phones) | `/ky/dev/ui` | 375x812 | ky |
| ui-dialog-form-phone-ru.jpg | Dialog with a field (focus on the input; footer primary on top on phones) | `/ru/dev/ui` | 375x812 | ru |
| ui-dialog-reason-error-desktop-ky.jpg | ReasonDialog: confirm without a reason shows the field error | `/ky/dev/ui` | 1440x900 | ky |
| ui-dialog-reason-error-desktop-ru.jpg | ReasonDialog: confirm without a reason shows the field error | `/ru/dev/ui` | 1440x900 | ru |
| ui-dialog-reason-error-phone-ky.jpg | ReasonDialog: confirm without a reason shows the field error | `/ky/dev/ui` | 375x812 | ky |
| ui-dialog-reason-error-phone-ru.jpg | ReasonDialog: confirm without a reason shows the field error | `/ru/dev/ui` | 375x812 | ru |
| ui-dialogs-desktop-ru.jpg | Dialog launchers | `/ru/dev/ui` | 1440x900 | ru |
| ui-dialogs-phone-ru.jpg | Dialog launchers | `/ru/dev/ui` | 375x812 | ru |
| ui-fields-desktop-ky.jpg | Input / Textarea / Select / Checkbox / Switch with hint, error, optional, disabled, busy | `/ky/dev/ui` | 1440x900 | ky |
| ui-fields-desktop-ru.jpg | Input / Textarea / Select / Checkbox / Switch with hint, error, optional, disabled, busy | `/ru/dev/ui` | 1440x900 | ru |
| ui-fields-phone-ky.jpg | Input / Textarea / Select / Checkbox / Switch with hint, error, optional, disabled, busy | `/ky/dev/ui` | 375x812 | ky |
| ui-fields-phone-ru.jpg | Input / Textarea / Select / Checkbox / Switch with hint, error, optional, disabled, busy | `/ru/dev/ui` | 375x812 | ru |
| ui-header-desktop-ky.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/ky/dev/ui` | 1440x900 | ky |
| ui-header-desktop-ru.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/ru/dev/ui` | 1440x900 | ru |
| ui-header-phone-en.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/en/dev/ui` | 375x812 | en |
| ui-header-phone-ky.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/ky/dev/ui` | 375x812 | ky |
| ui-header-phone-ru.jpg | PageHeader: breadcrumbs, title + badge, description, one primary + secondary group | `/ru/dev/ui` | 375x812 | ru |
| ui-picker-desktop-ru.jpg | UserPicker (empty) | `/ru/dev/ui` | 1440x900 | ru |
| ui-picker-open-desktop-ky.jpg | UserPicker with results, first option active (ArrowDown) | `/ky/dev/ui` | 1440x900 | ky |
| ui-picker-open-desktop-ru.jpg | UserPicker with results, first option active (ArrowDown) | `/ru/dev/ui` | 1440x900 | ru |
| ui-picker-open-phone-ky.jpg | UserPicker with results, first option active (ArrowDown) | `/ky/dev/ui` | 375x812 | ky |
| ui-picker-open-phone-ru.jpg | UserPicker with results, first option active (ArrowDown) | `/ru/dev/ui` | 375x812 | ru |
| ui-picker-phone-ru.jpg | UserPicker (empty) | `/ru/dev/ui` | 375x812 | ru |
| ui-states-desktop-ru.jpg | EmptyState, ErrorState (page and inline, retrying), Skeleton, LoadingState | `/ru/dev/ui` | 1440x900 | ru |
| ui-states-phone-ky.jpg | EmptyState, ErrorState (page and inline, retrying), Skeleton, LoadingState | `/ky/dev/ui` | 375x812 | ky |
| ui-states-phone-ru.jpg | EmptyState, ErrorState (page and inline, retrying), Skeleton, LoadingState | `/ru/dev/ui` | 375x812 | ru |
| ui-table-desktop-ky.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/ky/dev/ui` | 1440x900 | ky |
| ui-table-desktop-ru.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/ru/dev/ui` | 1440x900 | ru |
| ui-table-empty-desktop-ky.jpg | Table empty state (EmptyState + action) | `/ky/dev/ui` | 1440x900 | ky |
| ui-table-empty-desktop-ru.jpg | Table empty state (EmptyState + action) | `/ru/dev/ui` | 1440x900 | ru |
| ui-table-empty-phone-ky.jpg | Table empty state (EmptyState + action) | `/ky/dev/ui` | 375x812 | ky |
| ui-table-empty-phone-ru.jpg | Table empty state (EmptyState + action) | `/ru/dev/ui` | 375x812 | ru |
| ui-table-error-desktop-ky.jpg | Table error state (ErrorState + Retry) | `/ky/dev/ui` | 1440x900 | ky |
| ui-table-error-desktop-ru.jpg | Table error state (ErrorState + Retry) | `/ru/dev/ui` | 1440x900 | ru |
| ui-table-error-phone-ky.jpg | Table error state (ErrorState + Retry) | `/ky/dev/ui` | 375x812 | ky |
| ui-table-error-phone-ru.jpg | Table error state (ErrorState + Retry) | `/ru/dev/ui` | 375x812 | ru |
| ui-table-loading-desktop-ky.jpg | Table loading skeleton | `/ky/dev/ui` | 1440x900 | ky |
| ui-table-loading-desktop-ru.jpg | Table loading skeleton | `/ru/dev/ui` | 1440x900 | ru |
| ui-table-loading-phone-ky.jpg | Table loading skeleton | `/ky/dev/ui` | 375x812 | ky |
| ui-table-loading-phone-ru.jpg | Table loading skeleton | `/ru/dev/ui` | 375x812 | ru |
| ui-table-phone-en.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/en/dev/ui` | 375x812 | en |
| ui-table-phone-ky.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/ky/dev/ui` | 375x812 | ky |
| ui-table-phone-ru.jpg | Table: FilterBar search + status filter, count line, sort, cursor Pagination; stacked cards on phones | `/ru/dev/ui` | 375x812 | ru |
| ui-tabs-desktop-ru.jpg | Tabs (role=tablist, overflow fade, counts, disabled tab) and TabsNav (links) | `/ru/dev/ui` | 1440x900 | ru |
| ui-tabs-phone-ky.jpg | Tabs (role=tablist, overflow fade, counts, disabled tab) and TabsNav (links) | `/ky/dev/ui` | 375x812 | ky |
| ui-tabs-phone-ru.jpg | Tabs (role=tablist, overflow fade, counts, disabled tab) and TabsNav (links) | `/ru/dev/ui` | 375x812 | ru |
| ui-toasts-desktop-ky.jpg | Toasts (success + error) in the polite live region | `/ky/dev/ui` | 1440x900 | ky |
| ui-toasts-desktop-ru.jpg | Toasts (success + error) in the polite live region | `/ru/dev/ui` | 1440x900 | ru |
| ui-toasts-phone-ky.jpg | Toasts (success + error) in the polite live region | `/ky/dev/ui` | 375x812 | ky |
| ui-toasts-phone-ru.jpg | Toasts (success + error) in the polite live region | `/ru/dev/ui` | 375x812 | ru |
| ui-tokens-desktop-ru.jpg | Color tokens (brand, slate, success, warning, danger, gold) and type scale | `/ru/dev/ui` | 1440x900 | ru |
| ui-tokens-phone-ru.jpg | Color tokens (brand, slate, success, warning, danger, gold) and type scale | `/ru/dev/ui` | 375x812 | ru |

## S7b

ORT player part 1 (`docs/ORT_PLAYER_IDEAS.md` Bugs + Part 1). Every changed ORT baseline as a pair: `before` = the S7a
baseline, `after` = the new approved baseline in `docs/phases/ORT_BASELINE/` (macOS, system Chrome; phone 375x812,
desktop 1440x900; ru + ky). Exam behaviour unchanged: the DOM walk (`frontend/e2e/ort.spec.ts`) passes with the same
assertions (section order, timer, palette count and states, comparison columns A/B with answers A-D, numbered
passage lines, result card with five section rows).

| Files (`ort-<screen>-<viewport>-<lang>-{before,after}.jpg`) | What changed | Part 1 IDs |
|---|---|---|
| `ort-lobby-{phone,desktop}-{ru,ky}` | "Start test" button with the hint "the section 1 timer starts at once" under it; on phones the start row is sticky at the bottom of the screen (in the full-page shot it floats over the middle, where the 812 px viewport ends); attempts value "0 из 1" without the repeated word; section rows as a two-column grid with the meta on one line | L1, L2, L3 |
| `ort-comparison-{phone,desktop}-{ru,ky}` | Sans-serif stem and choices (one family); 44 px answer rows and flag button on phones; timer label "Left in section" on desktop; phones: "Questions 1/3" button in the header opens the palette sheet, the palette and the outline finish button are no longer below the question; design-system Prev/Next buttons | P1, P3, P4, P7 |
| `ort-flagged-palette-{phone,desktop}-{ru,ky}` | Additive palette states: green fill = answered, grey = not, ring = current, amber dot = flagged (also on the current question); legend shows the dot, 12 px text; phones: the palette is the bottom sheet (focus trap, Esc, finish action inside), 44 px buttons; amber dot on the header button when something is flagged | P1, P2, P3, cross-cutting (legend size) |
| `ort-section-end-{phone,desktop}-{ru,ky}` | Phase 6 `Dialog` (focus trap, Esc, focus return); confirm says "Finish section" like the button that opened it; red only for the no-return sentence, counts neutral; full-width stacked buttons on phones | P5, cross-cutting (colors, components) |
| `ort-passage-{phone,desktop}-{ru,ky}` | Phones / tablets: sticky "Text" bar above the passage folds the text away and back (open by default, remembered per passage); line numbers unchanged; desktop side by side as before | P6 |
| `ort-submit-{phone,desktop}-{ru,ky}` | Same `Dialog` treatment as the section-end dialog; the "cannot change answers" sentence in red | P5, cross-cutting |
| `ort-result-{phone,desktop}-{ru,ky}` | "Test finished. Your result:" line; scaled grade card first, raw points as a small line under it; "Counts toward your grade" / "Points" instead of jargon; `Badge` components; section table without a minimum width (nothing cut at 375 px), short "Scale" header on phones, percentile on its own line in the total row | R1, R2, R3, B4 |
| `ort-review-{phone,desktop}-{ru,ky}` | Review grouped by section (folding groups, all open, "1 of 3 correct" per section) and an "Only mistakes and unanswered" filter (off by default); every card unchanged in content; sans-serif text; correctness `Badge` with an icon | R4, P7, cross-cutting |

Not in a baseline: the loading skeleton of the player and of a section (P11), the save pill texts (P10), keyboard
shortcuts with `e.code` (P9), the timer's warning icon and bold digits under five minutes (P4). The phone result
page is checked to be no wider than the viewport (B4) in `ort-visual.spec.ts`.
