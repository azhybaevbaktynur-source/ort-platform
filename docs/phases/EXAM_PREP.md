# Exam-prep roadmap: results (`ROADMAP_EXAM_PREP.md`)

## S2 exam-prep home and ORT page: deployed 2026-11-06 (`main` d13fde2, migration `0020_exam_goals`)
- Student home: "От платформы" lists open platform courses the student isn't in, one-tap join; with no own courses a quiet "join by code / catalog" line replaces the big empty state.
- ORT course (template `ort`) opens for students on the exam-prep page: goal strip (days to the exam date, target score, latest scaled score), Next card right under it, score history (inline SVG), five section bars, test library with module titles as the source filter ("Other" for tests outside modules). Teachers keep the old page; the player and result page are unchanged (ORT baselines identical).
- Exam date: course setting `exam_date`, staff edit it on the course settings page (exam-prep courses only). Target score: table `exam_goals`, 60–245, in the privacy registry.
- Agent decisions: module titles are the source filter (no new teacher field, owner: no teacher tools); platform-kind organizations show `common.appName` on cards.

## S1 protect control: deployed 2026-11-06 (`main` 3846718, migration `0021_admin_mfa`)
- Two-step login (authenticator app, RFC 6238) for platform admins; required (`ADMIN_MFA_REQUIRED`, default true): an admin without it is refused everywhere except the setup page and auth basics until set up. Setup and confirm need the current password; an email goes out on enable, new recovery codes and `make_admin.py --reset-2fa`. 10 one-time recovery codes.
- Make or remove a platform admin from the user page (own code + reason, audited, last admin protected); end any user's sessions; admin-only health card; public `/health` says `database: not_checked`.
- Security review (Fable) findings fixed before deploy: gate covered only `/platform/*`, enrollment hijack, removal deadlock, burst brute force.
- Tests at deploy: SQLite 4201 passed; PG 4288 passed; migrations 15; CI green (7 jobs).
- Owner action: on the next visit to the admin panel, set up two-step login (an authenticator app such as Google Authenticator), keep the recovery codes offline; then create the spare admin (A3).

## S3 free and paid exams: deployed 2026-11-06 (`main` 7dbe770, migration `0022_access`)
- Platform-course tests have a tier (free/paid); new tests in platform courses start paid, every existing test was set free; practice in existing platform courses starts free (`practice_free` true) so nothing locked on deploy. The owner switches tiers on Admin → Доступ → Платные экзамены.
- A pass (scope `all`) unlocks every paid exam; it comes from an activation code (Admin → Доступ → batches: duration or end date, a note such as the price; codes copied/revealed one by one, marked as sold with a note, CSV export; all audited) or an admin grant on the user page (reason, max 400 days). Students redeem on `/unlock`; locked cards show "Платный" and a lock; the exam-prep Next card skips locked tests.
- Rules from the design and the security review: a timed attempt finishes after a pass ends, an untimed one waits (answers kept); test students and staff never locked; per-user row lock on redeem/grant; Bishkek end of day; no-benefit codes refused; buyer note erased on revoke and 90 days after redemption; redeem network limit always on; revoke shifts later passes; `python -m app.lms.access.rekey` after a key rotation.
- Owner to fill: `access.howToPay` (how to pay, e.g. QR transfer and contact), now a placeholder.
- Tests at deploy: SQLite 4239, PG 4329, migration/concurrency 49, CI green.

## S4 person page: deployed 2026-11-06 (`main` e48715d, migration `0023_person`)
- Admin users list: search by any part of email or name; filters: email not confirmed, blocked, platform admins, exam access; last login column.
- Person page: last login (set on sign-in, email-code verify and the two-step step, not on refresh), email confirmed, age band, consent, parent links, exam access (S3), attempt lookup (course, test, status, times, saved answers; never answers or scores, decision A4).
- Actions with a reason, audited: password reset email, age-band correction, email change, cancel a pending change. Email change (A9): link to the new address (24 h, single use, keyed hash), notice to the old one (also when an admin starts it), sessions end on confirm; self-service on `/privacy` with the password (admins also give the two-step code); refused for platform admins by others and for disabled accounts; a pending admin-started change dies if the person becomes an admin.
- Security review (Fable) findings fixed before deploy; trigram index for user search deferred (tiny table; comment in `users_service.py`).
- CI: the Postgres suite now reports failing tests as annotations (an intermittent failure was seen twice and passed on rerun).
- Tests at deploy: SQLite 4281, PG 4371, CI green.
