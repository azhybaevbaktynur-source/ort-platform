# ORT before / after (Phase 8c, PHASE_8C_DESIGN section 11)

Evidence for the ORT parity gate of Phase 8c: the frame around the ORT teacher screens and the student lobby changes
(course tab bar -> sidebar / drawer); everything inside it must not. **`docs/phases/ORT_BASELINE/` is not touched here.**
The orchestrator approves the re-record in S4b and copies the new PNGs into `ORT_BASELINE/` with a dated README note.

## Files

- `before/<screen>.png`: recorded with `e2e/ort-visual.spec.ts` against a build of `origin/lms` (8b deployed, no 8c).
- `after/<screen>.png`: same spec against the current branch.
- `sbs-<screen>.png`: before (left) and after (right) side by side, magenta gap between.
- `differences.txt`: every screen with its pixel ratio under the harness rule (pixelmatch, threshold 0.1, anti-aliasing
  ignored; more than 0.5 % of the pixels or a different size = changed).
- `record.sh` (build both frontends, record both sets, compare) and `compare.mjs` (pair, classify, side by side).
  `before/` and `after/` keep only the changed screens; unchanged screens are listed in `differences.txt`.

Run: `E2E_PYTHON=<main repo>/backend/venv/bin/python bash docs/phases/PHASE_8C_screens/ort-before-after/record.sh`
(`SKIP_BUILD=1` reuses the builds in `/tmp/ort_8c_ba`; ports 8871 / 3871; steps `before`, `after`, `compare`).
The "after" set was recorded on the S1 shell only; **re-record it after S2 and S3 are merged** (S4b).

## The 17 changed screens (frame only)

| Screen | Viewports / languages | What changes |
|---|---|---|
| `lobby` | phone + desktop, ru + ky (4) | student frame: sidebar / course menu, narrower content column |
| `teacher-attempts`, `teacher-bank`, `teacher-builder`, `teacher-import`, `teacher-passage`, `teacher-question-comparison` | phone + desktop, ru (12) | tab bar -> sidebar (desktop) / "Course menu" button (phone) |
| `teacher-publish` | desktop, ru (1; element capture, the panel is narrower next to the sidebar) | width of the element |

Everything else (`comparison`, `flagged-palette`, `passage`, `section-end`, `submit`, `result`, `review`,
`player-loading`, `teacher-publish-phone`) is pixel-identical under the harness rule: the player is outside the
frame and `/attempts/**` keeps the full-width column.

Review checklist for S4b: inside the content region the DOM assertions pass unchanged (`ort.spec.ts`,
`ort-visual.spec.ts` DOM part) and the content elements (builder cards, bank table, attempts table, lobby card) are
the same, only moved.
