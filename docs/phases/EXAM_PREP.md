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
