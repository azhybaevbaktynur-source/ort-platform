# UX rework: report

Deployed 2026-11-01: `main` ace2476, migration `0015_test_student`, Neon verified (existing data unchanged), Vercel READY. Backup branch `backup-2026-11-01-before-ux-rework` (br-restless-violet-b24js0e2). Decisions: `PRODUCT_DECISIONS.md` UR-1…8, PUR-1…7. Design: `UX_REWORK_DESIGN.md`. Screens: `UX_REWORK_screens/{before,after}`.

## What changed (whole platform)
- Width: shell up to 1600 px; side nav + wide main area; forms left-aligned; exam screens keep their column.
- Student course home: modules view whenever published modules exist; a chosen home page shows above the modules.
- Student dashboard: course cards + to-do list; hero and "Что дальше" removed.
- Teacher course page: inline new module, rename and add; "Не в модулях" one collapsed row; To do panel replaced by a small "На проверку" list; join code moved to People; legend removed.
- Org and platform admin: tiles, disclosures, rare and dangerous actions in "…".
- Student view: real test-student session (banner, reset, leave); 8c `X-View-As` removed.

## Checks
- SQLite 3672 passed, 47 skipped; PG 3749 passed, 25 skipped; migrations and concurrency 36 passed; `alembic check` clean; tsc and i18n parity clean.
- CI: six jobs green on 4ad00b0. **An earlier run on 55e3348 failed `backend-sqlite`; the next commit was docs only, and the same commit passed locally on a clean checkout, so it is intermittent. Cause not found (CI logs need sign-in).** The test isn't identified.
- Browser suite local: all pass, including ORT DOM walk and pixel comparison.
- Security review (Fable, read-only): no High or Medium. Low: concurrent resets can leave one teacher's tab with a dead token (falls back to the teacher view); retired test students' hand-in files are never swept (Phase 11 hardening list).
- Production browser check at 375 / 1440 / 1920 px, ru: 49 of 50 scripted checks passed; the one failure was a wrong URL in the script, rechecked by hand on `/people` and `/gradebook`: test student absent, real QA student present. Hand-in, reset, old token dead, refused outside the course, teacher still signed in after leaving: all pass.

## ORT review
Exam behaviour, import and scoring unchanged: `ort.spec`, `ort-visual`, parity job, golden tests pass. Player, result and review pixel-identical. Nine desktop baselines re-recorded for the wider shell, viewed and layout only: lobby (ru, ky), teacher bank, builder, publish, import, passage, question, attempts. ORT (Russian) students now get the modules home (PUR-7); ORT (Kyrgyz) keeps today's home. ORT screens on production were not walked as a student: the QA student isn't enrolled there, to keep QA out of real course counts.

## Production QA data (agent, 2026-11-01)
Added directly with SQL because the agent has no production login: users `agent-qa-teacher@example.com` (`teacher_status = approved`, personal organization, as admin approval would write) and `agent-qa-student@example.com`, both `email_verified`; random passwords kept only in the session scratchpad. Through the API: private course "QA: проверка интерфейса (агент)" (63e9565c-f609-48ce-bf56-897764d0e373) with its test students. To be disabled (`disabled_at`) after the Phase 10 production check. Deleting them needs the owner's OK.

## Follow-ups
Settings page still has several save buttons (older carry-over). Roster role select stays visible per row. Inline titles save one language; the dialogs edit all three.
