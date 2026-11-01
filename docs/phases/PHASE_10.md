# Phase 10: report

Deployed 2026-11-01 (`main` cce135d, then the follow-up below; migration `0016_phase10_practice_analytics`, Neon verified, existing content intact; backup branch `backup-2026-11-01-before-phase10` br-winter-king-b2tpkg6h). Design: `PHASE_10_DESIGN.md`. Screens: `PHASE_10_screens/`.

## What shipped
- Question types matching, fill-in-the-blank, ordering: partial credit, player, quiz editor and bank editor, bank filter, builder pickers, general import format with template examples, block catalog.
- Practice sets (own sidebar page): unlimited attempts, Check with key and explanation, no grades.
- Mistakes notebook, progress and per-course goal ("Мой прогресс").
- Quiz statistics: accuracy, discrimination, time per item, distractors, distribution, per version.
- Course and organization analytics ("Аналитика").
All aggregates exclude previews, void attempts and test students.

## Checks
- SQLite 3792 passed, 47 skipped; PG 3871 passed, 25 skipped; migration tests 15 passed; `alembic check` clean; tsc and i18n parity clean; CI green.
- Security review (Fable, read-only): nothing High or Medium. No key leak before Check; Check refuses non-practice attempts; graded and ORT attempts unchanged; no cross-course or cross-org reads.
- Production (QA accounts, general course, ru): question types saved, no key before Check, partial credit and key after Check, practice absent from the gradebook, notebook fills, student refused analytics; practice, progress, analytics, statistics pages at 375 / 1440 / 1920 with no sideways scroll, error state or page error.
- Local only, not on production: the player for the new types, question editor fields, org analytics. The follow-up (bank filter and builder pickers) was checked locally by spec and on production only for deployment.

## ORT review
Exam behaviour, import and scoring unchanged: `ort.spec`, `ort-visual` with zero baseline changes, parity job, golden tests. ORT refuses the new types in the bank, quiz, import and shared copy; its type lists stay seven. **New for ORT students**: a "Мой прогресс" sidebar link, and "Практика" once someone publishes a set. Not walked as a student on production.

## Mistakes along the way
- Agents' SQLite runs hid a Postgres-only failure: new tables were missing from the test cleanup list, 440 errors. Fixed in `tests/lms/isolation.py`; no product impact.
- 8d63bf5's message overstates the gap: general courses could always create the new types in the editor; only the bank filter and builder pickers lacked them.

## Follow-ups
- Statistics "#" shows the same number for questions drawn from one pool.
- Flag button still shows on practice items; staff also see "Начать" on practice rows.
- Per-item time is approximate (gaps between saved answers). Query budgets were tested at small scale, not at 6,000 students: Phase 11 load test.
- Practice grows `attempt_items` (design estimate ~44 M rows a year at 6,000 students, one set a day). Retention decided in Phase 11; any Neon cost goes to the owner first.
- ru/ky strings written by agents and not reviewed by a native speaker.
- Unidentified intermittent `backend-sqlite` CI failure seen once during the rework (55e3348).

## Production QA data
`agent-qa-teacher@example.com`, `agent-qa-student@example.com`, their test student and the private QA course (63e9565c-f609-48ce-bf56-897764d0e373, with a question bank and practice set) are disabled (`disabled_at`), not deleted. The two accounts were created by SQL for this verification (`UX_REWORK.md`). Deleting needs the owner's OK.
