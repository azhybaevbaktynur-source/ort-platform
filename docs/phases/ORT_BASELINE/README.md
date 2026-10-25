# ORT screenshot baselines

The approved "after" images of the ORT screens (PHASE_6_DESIGN section 6, decision A3). The browser suite in
`frontend/e2e/` walks the real ORT exam and compares every screen with the PNG here, **after** its DOM
assertions (section order and count, timer, palette count and states, comparison columns A/B and answers A-D,
numbered passage lines, result card with the scaled score and five section rows).

## Files

`<screen>-<viewport>-<lang>.png`, viewport `phone` = 375x812, `desktop` = 1440x900, device scale factor 1.

| Screen | What is shown | Viewports / languages |
|---|---|---|
| `lobby` | assessment lobby, full page (rules, five sections with counts) | phone + desktop, ru + ky |
| `comparison` | math_1 question 1: Column A / Column B card, answer A chosen | same |
| `flagged-palette` | question 2 shown; palette: #1 answered + flagged, #2 current, #3 empty | same |
| `section-end` | "finish section" dialog (no-return warning, counts) | same |
| `passage` | reading question 1 with the line-numbered passage | same |
| `submit` | "finish test" dialog in grammar (last section) | same |
| `result` | the result card only (raw score, scaled grade, section table) | same |
| `review` | the answer review, scrolled to its title | same |
| `teacher-bank` | ORT bank `tsoomo19` question list | phone + desktop, ru |
| `teacher-question-comparison` | comparison question editor, full page | same |
| `teacher-passage` | passage editor (viewport: the textarea grows to ~10,000 px) | same |
| `teacher-import` | CSV / zip import page, full page | same |
| `teacher-builder` | `ort_main` builder (publish panel, settings, five sections) | same |
| `teacher-publish` | publish panel after "Validate" (element only) | same |
| `teacher-attempts` | staff attempts list with the one seeded submitted attempt | same |

46 images, about 3.4 MB.

**Platforms.** Fonts are system fonts, so images are per rendering platform: the files in this folder are the
reviewed macOS set (system Google Chrome, `channel: "chrome"`). Other platforms use a subfolder named after
`process.platform`: CI (`ubuntu-latest`, Playwright chromium) compares with `linux/`. While `linux/` is not
committed, the CI job (`ORT_BASELINE_RECORD_MISSING=1`) records the images instead of failing and uploads them
as the artifact `ort-e2e-recorded`; commit that artifact's PNGs into `linux/` (reviewed like any baseline
update) to switch the comparison on. DOM assertions always run.

## Data

`scripts/e2e_backend.sh` starts a scratch backend: `env -i` from an empty directory under `/tmp` (so
`backend/.env` is never read), fresh SQLite, `LMS_STORAGE_DRIVER=db`, `EMAIL_PROVIDER=console`, a random
`SECRET_KEY`, `ORT_SEED_SAMPLES=false`. `frontend/e2e/seed_backend.py` seeds through the API: admin
(register + emailed code from the log + `make_admin.py` + `python -m app.lms.ort.seed` for the ORT co-teacher
enrollment), seven students ("Student 01".."Student 07", random passwords per run), the `tsoomo19.zip` bundle
imported as `full_main` into ORT (Russian), and two published `ort_main` exams with the same 19 items
(math_1 3 comparison, math_2 2, analogies 2, reading the 10 questions of the first passage, grammar 2): "ОРТ E2E"
for the student walks (one student per walk) and "ОРТ E2E staff" for the teacher screens with one seeded
submitted attempt, so no screen depends on test order.

## Run

```bash
# once: build the frontend against the scratch backend, in a copy (never inside frontend/ while a dev server runs)
rsync -a --exclude node_modules --exclude .next frontend/ /tmp/ort_e2e_fe/ && ln -s "$PWD/frontend/node_modules" /tmp/ort_e2e_fe/node_modules
(cd /tmp/ort_e2e_fe && NEXT_PUBLIC_API_URL=http://127.0.0.1:8765 npx next build)

cd frontend
E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test                    # both specs (about 1.5 min)
E2E_WEB_DIR=/tmp/ort_e2e_fe npx playwright test e2e/ort.spec.ts    # DOM walk only (ru + ky)
```

Variables: `E2E_WEB_DIR` (folder with the `.next` build; default `frontend/`), `E2E_DIR` (scratch, default
`/tmp/ort_e2e`, must be under `/tmp`), `E2E_API_PORT` (8765), `E2E_WEB_PORT` (3765), `E2E_PYTHON` (python with
the backend requirements; default `backend/venv/bin/python`, in a git worktree point it at the main repo's venv).
Both servers are started and stopped by Playwright (`reuseExistingServer: false`), so every run starts from an
empty database. Mismatches leave `<name>-actual.png`, `-expected.png` and `-diff.png` in `$E2E_DIR/diffs/`.

## Comparison

- `pixelmatch`, per-pixel threshold 0.1, anti-aliased pixels not counted (`includeAA: false`); a screen fails
  when more than **0.5 %** of its pixels differ, or when its size differs.
- Masks (painted `#FF00FF` before comparing): the timer (`role="timer"`, digits change every second), the
  "submitted" date on the result, the "submitted" column and any date/time text on the staff attempts list.
  Ids appear only in URLs. Animations are disabled, the caret hidden, the pointer parked at (0, 0), and every
  shot waits for network idle, fonts and two animation frames.
- Locale `ru-RU`, time zone UTC, light colour scheme.

## Updating a baseline

Only for an allowed visual change (`docs/UX_GUIDELINES.md` section 6) or a deliberate ORT change approved by the
owner. Never to make a failing run green without looking.

1. Before changing code, copy the affected PNGs (the "before").
2. Make the change, then `E2E_WEB_DIR=... UPDATE_BASELINES=1 npx playwright test e2e/ort-visual.spec.ts`
   (or `npm run e2e:update`) and rerun without `UPDATE_BASELINES` to prove zero diffs.
3. Commit the new PNGs in the same PR as the change, with the before/after images side by side in the PR
   description (or `docs/phases/PHASE_N_screens/`). The orchestrator reviews every baseline diff; the DOM
   assertions must still pass unchanged.
4. If the change also affects Linux, replace `linux/` from the CI artifact of that PR.
