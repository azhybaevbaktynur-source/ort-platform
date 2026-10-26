# Phase 6b: design system, app header with areas, student home, ORT player part 1

**Status**: **deployed 2026-10-25** (`main` 89050a4; Render /health and Vercel verified; no database changes). Owner checkpoint: waiting for the owner's OK before Phase 7a. Design: `docs/phases/PHASE_6_DESIGN.md` §8 (approved). Decisions while building: `docs/PRODUCT_DECISIONS.md` "Phase 6b implementation decisions" (J1–J7). Slice rules: `PHASE_6B_SLICE_RULES.md`.

## What changed

| Area | Change |
|---|---|
| Design system | `frontend/src/components/ui/`: Button (primary / secondary / danger / danger outline / link, loading), IconButton, Input, Textarea, Select, Checkbox, Switch, Card, Table (sorting, count, cursor pagination, stacked cards under 640 px), Tabs / TabsNav (scrollable), Dialog + ConfirmDialog + ReasonDialog (focus trap, Esc, focus return, object and effect named), Badge, EmptyState, ErrorState (Retry), Skeleton, Toast, PageHeader (breadcrumbs, one primary), DescriptionList, StatTile, UserPicker, FilterBar, Pagination, MenuButton. Tokens in `tailwind.config.ts` (brand, slate, success/warning/danger, gold for achievements only). Dev-only showcase `/[lang]/dev/ui`. |
| Header and areas | `AppHeader`: brand from the platform name, an area switcher showing only the person's areas (Learning, Teaching, Organization, Platform), an account menu (language, "I am a teacher" only for non-teachers, log out). One row on phones (57 px). `AreaShell`: side navigation on desktop, scrollable tabs on phones, for the platform-admin and organization areas. Browser tab title per language. `<html lang>` follows the UI language. |
| Student home | `/[lang]/courses` for students answers "what next?": one primary button (Continue / Start next / Join with code), Continue, Next up, Latest results (Personal best badge), My courses; skeleton loading, error with Retry; empty state for a new student. Data from one call `GET /me/home` (8 queries, any number of courses). Catalog on its own page `/[lang]/courses/catalog`. |
| Student course screens | Course frame with breadcrumbs and scrollable tabs; assessment cards with status (not started / in progress / submitted / graded / closed), due date, duration, attempts left and one next action; no dead end after the last attempt; new grade state "Not started" ("Не начато" / "Башталган эмес"). |
| Staff screens | Teaching screens inside courses (builder, sections, publish panel, banks, question/passage editors, import, people, gradebook, staff attempts, course home "Next step") and all platform-admin and organization-admin screens moved onto the design system: phone tables as cards, one primary per page, dialogs naming object and effect, audit details in a dialog, plurals in Russian, localized storage units. |
| ORT player part 1 | `docs/ORT_PLAYER_IDEAS.md` Part 1 and bugs (status table there): additive palette states with legend, 44 px touch targets, labelled timer, consistent dialog wording, phone palette as a bottom sheet with a pinned "Finish section", passage fold and phone readability, one typeface, shortcuts independent of keyboard layout, short offline/saving messages, loading skeleton, lobby explains what Start does, result page opens with the scaled score and fits phones, review grouped by section with an "only mistakes" filter (off by default). |
| Writing | Glossary: ru "преподаватель", ky "мугалим", en "teacher" (`UX_GUIDELINES.md` §5); no hard-coded strings on the auth pages. |

## ORT review (design §6)

**Function unchanged** — proven by:
- Backend ORT tests unchanged and green (`test_ort_import_golden.py`, `test_ort_e2e_api.py`, `test_ort_parity.py`, `test_ort_seed.py`, `test_ort_cutover_flow.py`).
- **New ORT browser suite** (`frontend/e2e/`, Playwright): lobby → start → comparison item (Column A/B) → flag → palette states → section-end dialog → numbered passage → submit → result (scaled score, five section rows), in ru and ky, phone and desktop, plus teacher screens; DOM assertions on section order, timer, palette, comparison columns, numbered lines and result cards. Runs in CI on every push (job `ort-e2e`).
- **Screenshot baselines** `docs/phases/ORT_BASELINE/` (approved "after" images; pixel comparison at 0.5 % tolerance, run locally at every phase gate). Every changed baseline has a before/after pair in `docs/phases/PHASE_6_screens/6b/ort-*-{before,after}*.jpg`.

**Look** (allowed, no owner decision needed; UX reviewer confirmed every pair is look/layout/accessibility only): see the ORT player row above. Visible differences for students: on phones the question list and "Finish section" open from a "Questions n/total" button in the header (finishing early takes one extra tap; the last question keeps its finish button); the result page shows the scaled score first; the review is grouped by section.

**Waiting for the owner** (not implemented): P8, Kyrgyz comparison answer labels in sentence case (changes the answer wording students read).

## How to verify

```bash
# Backend (AGENTS.md §5): SQLite ~2651 passed, 23 skipped; PG green.
# ORT browser suite (docs/phases/ORT_BASELINE/README.md):
#   build the frontend in a copy with NEXT_PUBLIC_API_URL=http://127.0.0.1:8765, then in frontend/:
#   E2E_WEB_DIR=<build dir> E2E_PYTHON=<repo>/backend/venv/bin/python npx playwright test
```
UX gate: `docs/phases/PHASE_6_screens/6b/` (INDEX.md, sections S5a, S5b, S5c, S6b, S7b, S11a, S11b, S12), two ux-reviewer passes, findings fixed. Security review: no blockers; CI now has read-only repository permissions.

## Deferred

- Course settings (one save bar), question/passage editor internals, people-page role select, remaining raw elements → Phase 7 sweep; audit-log human labels (M3) → Phase 7.
- Gold vs warning colour distinction, "started" line for several in-progress attempts, lazy KaTeX in long reviews.
- Linux screenshot baselines for CI (CI records them as an artifact; pixel comparison stays local).

## Owner items

- P8 (above).
- Neon branch limit (10) reached; deleting old backups needs your OK.

## Post-deploy production check (2026-10-26)

- Render `/health` = 89050a4, Neon at `0008_phase6_organizations` (latest). 6a data unchanged: one organization ("Platform", active) holding both ORT courses (template `ort` v1, locked, owned by the owner's account, demo teacher kept as system co-teacher) and the owner's draft course; 0 courses and 0 banks without an organization (2 banks, both in ORT (Russian)); 0 personal organizations because there is no independent teacher yet (the only approved teacher is the owner, a platform admin); 299 question versions and 3 attempts, as in PHASE_6A.md.
- Logged-out browser pass on Vercel (phone + desktop): landing, login, register, forgot/reset password, invalid invitation page (en/ky/ru friendly message; the only console entry is the intended 404 of the token lookup), and 15 logged-in routes redirecting to login with `redirect=`. Found and fixed (`4771318`, frontend only): the landing header made `/ru`, `/ky`, `/en` 433–533 px wide on phones; auth pages had no `<h1>`. After the fix 36/36 checks pass at 320/375/414 px.
- Render deploys only on backend changes; a frontend-only commit leaves `/health` on the previous commit (expected).
