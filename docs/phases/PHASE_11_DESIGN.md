# Phase 11: design (parents, privacy, hardening, performance, operations, launch)
Scope: `IMPLEMENTATION_PLAN.md` "Phase 11", D5, D17. Rules: `AGENTS.md` §6. Style: `UX_REWORK_DESIGN.md` (short labels, no explanatory paragraphs, `AreaShell`). UX check per `AGENTS.md` §6.10. Free-tier tools only.

## 0. Invariants
1. **ORT does not change.** No file under the player, scoring or ORT screens is edited. The privacy gate never stops an open attempt: autosave, submit and state stay allowed for every account.
2. **Zero writes to `grade_events`, `attempts`, `attempt_sections`, `attempt_items`, `attempt_grades`.** Deleting a user changes the `users` row and mutable side tables only. The PG triggers stay as they are.
3. **Authorization from DB state.** The guardian link, consent state and age band are read from rows on every request. The only new JWT claim, `tv`, can only reject a token; it never grants anything.
4. **Test students are outside all of this**: `consent_state='exempt'`, denied by the existing allow-list on every new route, never in queues or exports.
5. **Nothing legal is decided here.** Policy text ships as `draft_legal_review` and shows a "Draft: awaiting legal review" badge in en, ky and ru. Age cutoff, due days, retention and "anonymized enough" are defaults in config or data, listed in §9.
6. **Destructive runs need the owner's first OK** (`AGENTS.md` §6.7): practice retention and the test-student file sweep default to off or dry run.

## 1. Findings that change the plan

| # | Finding | Effect |
|---|---|---|
| F1 | **The browser calls Render directly.** The production client bundle contains `https://ort-platform-w77q.onrender.com` (`NEXT_PUBLIC_API_URL`, `lib/apiBase.ts`). The Vercel rewrite is not in the path, so `RATE_LIMIT_PROXY_HOPS=2` rests on a wrong assumption. | Flipping `RATE_LIMIT_IP_ENFORCE` today gives either `parts[-2]` = attacker-controlled or, with one XFF entry, Render's proxy IP, so **all students share one bucket**. Do not flip before the probe (§5.3). |
| F2 | **`/auth/login` has no rate limit** (`endpoints/auth.py:233`). Nor do `/register`, `/forgot-password`, `/reset-password` beyond per-account cooldowns. | §5.1. |
| F3 | **Two IP rules count successes**: `access_code_ip_10m` 100 tries per IP and assessment; `invite_lookup_ip_10m` 60. One school behind NAT hits both. | Raise to 2000 and 600 before enforcing (§5.1). |
| F4 | `enrollments.role` as `observer` (plan wording) would enter every roster, count and gating query, and a parent links to a student, not a course. | Separate `guardian_links` table; a parent has **no enrollment** and so no course access at all. Record the deviation in `PRODUCT_DECISIONS.md`. |
| F5 | Hand-in files survive soft delete on purpose (`assignments/files.py:185`). | Erasure needs its own path: `erase_asset` (§3.4), shared with the test-student sweep. |

**Naming.** Code word `guardian`, UI word "Parent" (`guardian.*` i18n keys, `/[lang]/parent`). `observer` in `lib/lms/nav.ts` stays the org-admin read-only sidebar role and is not renamed (`nav.check.ts`, no behaviour gain). New code never uses `observer`; `enrollments.role_valid` is unchanged. Add one comment in `nav.ts`: "not the parent role, see `guardian`".

## 2. Migration `0017_phase11_privacy` (down_revision `0016_phase10_practice_analytics`)
Additive. `ADD COLUMN ... DEFAULT` is instant on PG.

| Table | Columns |
|---|---|
| `users` (changed) | `consent_state VARCHAR(20) NOT NULL DEFAULT 'legacy'` CHECK in `legacy, ok, pending_guardian, exempt`; `consent_due_at timestamptz NULL`; `deleted_at timestamptz NULL`; `token_version INT NOT NULL DEFAULT 0`. Data step: `consent_state='exempt' WHERE is_test_student`. `age_band` already exists with the right CHECK |
| `assets` (changed) | `erased_at timestamptz NULL` |
| `policy_versions` (new, immutable) | `id` uuid PK; `kind` CHECK in `privacy, terms, guardian_consent`; `version INT`; `status` CHECK in `draft_legal_review, approved`; `body_en, body_ky, body_ru TEXT NOT NULL`; `sha256 VARCHAR(64)`; `requires_reconsent BOOL NOT NULL`; `effective_at`, `created_at` timestamptz; UNIQUE `(kind, version)` |
| `consent_records` (new, append-only: PG trigger honouring `lms.allow_grade_purge`, ORM guard) | `id` uuid PK; `user_id` FK RESTRICT (the person it concerns); `granted_by_id` FK RESTRICT; `policy_version_id` FK RESTRICT; `kind`; `action` CHECK in `granted, withdrawn`; `locale VARCHAR(2)`; `source` CHECK in `signup, prompt, guardian, admin`; `created_at`; index `ix_consent_records_user_kind (user_id, kind, created_at)` |
| `guardian_pairing_codes` (new) | `id` uuid PK; `student_user_id` FK RESTRICT; `code_hash VARCHAR(64) UNIQUE`; `expires_at`, `consumed_at`, `revoked_at`, `created_at`; partial UNIQUE `uq_pairing_open (student_user_id) WHERE consumed_at IS NULL AND revoked_at IS NULL` |
| `guardian_links` (new) | `id` uuid PK; `guardian_user_id`, `student_user_id` FK RESTRICT; `created_at`; `revoked_at`; `revoked_by_id` FK SET NULL; CHECK guardian <> student; partial UNIQUE `uq_guardian_active (guardian_user_id, student_user_id) WHERE revoked_at IS NULL`; indexes on both ids |
| `data_requests` (new) | `id` uuid PK; `user_id` FK RESTRICT; `requested_by_id` FK RESTRICT; `kind` CHECK in `export, delete`; `status` CHECK in `pending, completed, rejected, cancelled`; `requested_at`, `due_at`, `completed_at`; `handled_by_id` FK SET NULL; `reject_code VARCHAR(40)`; partial UNIQUE `uq_data_request_open (user_id, kind) WHERE status='pending'`; index `(status, due_at)` |

New performance indexes go in a separate `0018_phase11_indexes`, only if §6.1 proves them. Never on `attempt_items` (Phase 10 invariant).

Config (`core/config.py`): `PRIVACY_UNDER14_GATE=True`, `PRIVACY_LEGACY_DEADLINE=None`, `PRIVACY_LEGACY_GRACE_DAYS=30`, `DATA_REQUEST_DUE_DAYS=30`, `GUARDIAN_PAIRING_TTL_HOURS=24`, `PRACTICE_RETENTION_DAYS=0` (0 = off), `SECRET_KEY_PREVIOUS=""`, `SENTRY_DSN=""`, `LOG_SAMPLE_2XX=0.1`.

## 3. Privacy (package `backend/app/lms/privacy/`)
### 3.1 Policies
`privacy/policies/{privacy,terms,guardian_consent}.{en,ky,ru}.md` plus `manifest.json` (`{kind: {version, status, requires_reconsent}}`). `ensure_policies()` runs in the lifespan and in test setup, and inserts a new row when the manifest version is new; an existing row is never edited. The owner's legal sign-off is a new manifest version with `status='approved'` and `requires_reconsent=true`. No admin editor.

### 3.2 Sign-up by age band
`POST /auth/register` gains `ageBand` (required, else 422 `age_band_required`) and `policyVersionIds`:

| Band | Effect |
|---|---|
| `18_plus`, `14_17` | Must send the current `privacy` and `terms` ids (else 422 `policy_not_accepted`); writes `consent_records` (`source='signup'`); `consent_state='ok'` |
| `under_14` | No acceptance by the child; `consent_state='pending_guardian'`, `consent_due_at=now`; after email verification only the gate's routes work |

The band is one choice of three buttons, never a birth date (data minimisation). A user cannot change a set band; `POST /admin/privacy/users/{id}/age-band` corrects mistakes, audited.

### 3.3 Gate
`get_lms_user` (`core/deps.py`) gains one branch after the test-student one, reading only columns already loaded (no new query, autosave unaffected):

```python
if privacy_gate.is_gated(user, now):   # pending_guardian and consent_due_at <= now and PRIVACY_UNDER14_GATE
    privacy_gate.enforce(request, user) # or legacy past PRIVACY_LEGACY_DEADLINE
```

`privacy/gate.py` is deny by default on route templates, like `student_view/allowlist.py`. Allowed: `/auth/me`, `/auth/refresh`, `/auth/logout-all`, `/me/privacy*`, `/me/guardians*`, `/privacy/policies/current`, and open-attempt state, autosave and submit. Denied routes give 403 `consent_required`; the frontend sends the user to `/[lang]/privacy`. Starting an attempt and joining a course are denied.

**Existing accounts (`legacy`) are safe**: nothing is restricted. They see one small banner on the home page: "Confirm your age" → `/privacy`. `POST /me/privacy/age-band` works only while the band is NULL and writes the consents. A legacy user choosing `under_14` gets `pending_guardian` with `consent_due_at = now + PRIVACY_LEGACY_GRACE_DAYS`, so nobody loses access overnight. `PRIVACY_LEGACY_DEADLINE` stays `None` until the owner sets it. A legacy user reconsents the same way when `requires_reconsent` is true, also via banner.

API:
```
GET    /privacy/policies/current?locale=  public  [{id, kind, version, status, body}]
GET    /me/privacy                                {age_band, consent_state, consent_due_at, needs:[{kind, policy_version_id}], requests:[...]}
POST   /me/privacy/age-band                       {age_band, policy_version_ids}      409 age_band_set
POST   /me/privacy/consents                       {policy_version_ids}                refused for under_14
POST   /me/privacy/requests                       {kind, password?}  201              delete needs password; 409 request_open
GET    /me/privacy/requests/{id}/download         streamed JSON; export only; completes the request
DELETE /me/privacy/requests/{id}                  cancel while pending
GET    /admin/privacy/requests?status=&cursor=&limit=     oldest due_at first, with overdue flag
POST   /admin/privacy/requests/{id}/execute               delete only; 409 with a code below
POST   /admin/privacy/requests/{id}/reject                {reject_code}
POST   /admin/privacy/users/{id}/age-band                 audited
```

Export is built on demand from the registry, one user's rows, streamed; nothing is stored, so no R2 use. It holds own profile, enrollments, grades, own answers, hand-in text and a list of hand-in file names (files stay downloadable through existing routes), consents and requests. Limit 3 per 24 h. Never other students' rows.

### 3.4 Delete = anonymize in place (`privacy/anonymize.py`)
Runs in one transaction under `SELECT users ... FOR UPDATE`. Refused with 409 for `delete_blocked_platform_admin`, `delete_blocked_owns_courses` (admin transfers first), `delete_blocked_open_attempts` (an open attempt ends first; timed ones are swept), and `delete_blocked_test_student`.

The `users` row stays as a tombstone, so RESTRICT FKs on `attempts.user_id` and the rest hold and nothing immutable is touched. `users.id` is random (`usr_<uuid hex>`), so it reveals nothing.

| Target | Action |
|---|---|
| `users` | `email='deleted-<random hex>@deleted.invalid'`; `display_name`, `phone`, `locale`, `age_band`, reset and email-code fields NULL; `password_hash` unusable; `deleted_at`, `disabled_at=now`, `disabled_reason='account_deleted'`; `teacher_status='none'`; `token_version+1`; `consent_state='exempt'` |
| `enrollments` | `state='removed'`, `invite_token_hash` NULL, plus event `removed` with `{"reason":"account_deleted"}`. Roster and gradebook drop them; `counted_attempt` does not read `state`, so statistics stay |
| `enrollment_accommodations.note`, `assignment_overrides.note` | NULL (may be medical) |
| `assignment_submissions` | `body_text=''` (satisfies `text_body_valid`); `asset_id` stays. The one exception to hand-ins being append-only, in this function only |
| `assets` of those hand-ins | `files.service.erase_asset`: `erased_at`, `original_filename='erased'`, excluded from the refcount in `delete_unreferenced_blobs` (blob and R2 object go when unreferenced; usage ledger updated). Hand-in download returns 410 `asset_erased` |
| `submissions.feedback_text`, `feedback_asset_id`, `override_reason`, `submission_rubric_scores.comment` | NULL (mutable; written about the person, not needed for statistics) |
| `enrollment_applications` | `answers='{}'`, `decision_note` NULL |
| `invitations` | `email='deleted@deleted.invalid'`, `message` NULL, for rows of that email |
| `teacher_requests.message, reason` | NULL |
| `admin_audit_log` | `details` keys `email`, `display_name` removed where target is this user; `ip_hash` NULL |
| `course_goals`, open `guardian_pairing_codes` | Delete, revoke |
| `guardian_links` | Revoke both directions. A student losing their consent holder gets `pending_guardian` with grace |
| **Kept unchanged** | `attempts`, `attempt_items` (including `response`, `feedback`), `attempt_grades`, `grade_events` (including `reason`), `course_grades`, `consent_records`, `data_requests` |

`grade_events.reason`, free-text `attempt_items.response` and teacher `attempt_items.feedback` could name a person; they stay because rows are immutable. Listed for the lawyer (§9). `legacy_ort_export.payload`: S1 must check whether it holds user data and register it. Erased data stays in Neon history until the restore window passes: state that window in the runbook.

### 3.5 Personal-data registry (`privacy/registry.py`)
`Entry(table, column, category, action, exported)`; `action` in `null, scrub, keep_tombstone, keep_immutable, delete_row, erase_file, none`. `NOT_PERSONAL` lists columns the scan matches but which hold no personal data. `python -m app.lms.privacy.registry --markdown > docs/PERSONAL_DATA.md` gives the owner and lawyer one table; CI checks the file is current.

## 4. Parents (package `backend/app/lms/guardian/`)
Each link is one student; a parent with two children has two links, each from its own code. Caps: 4 active guardians per student, 10 students per guardian (409 `guardian_limit`).

```
# Student
POST   /me/guardians/pairing-code   201 {code, expires_at}   8 chars, Crockford base32; previous open code revoked; 5/h
GET    /me/guardians                [{id, guardian_name, created_at, holds_consent}]
DELETE /me/guardians/{link_id}      204; 409 guardian_holds_consent for an under-14's only consent holder
# Parent (any verified account with age_band = 18_plus, else 403 guardian_must_be_adult)
POST   /guardian/links              {code} 201 {id, student_name, needs_consent}; 404 invalid_code for every bad code; 409 already_linked
GET    /guardian/links
DELETE /guardian/links/{id}         204; also withdraws this parent's consent
POST   /guardian/links/{id}/consent {policy_version_id} 201   under-14 only: consent_records + consent_state='ok'
DELETE /guardian/links/{id}/consent 204   withdrawn: if no consent holder is left, pending_guardian, due now
POST   /guardian/links/{id}/delete-request 201   under-14 and consent holder only; no export for parents
# Read-only, all 404 unless the link is active, the student is not deleted or a test student
GET    /guardian/links/{id}/courses                                   {items, next_cursor}
GET    /guardian/links/{id}/courses/{course_id}/grades
GET    /guardian/links/{id}/due?limit=                                max 50
GET    /guardian/links/{id}/courses/{course_id}/announcements?cursor=&limit=
```

**Read path.** `guardian/service.py` loads the link, then calls the student's own code with the student's context: `gradebook.my_grades`, `announcements.service.list_announcements`, `home.service._listable_rows`. So hidden grades, unpublished items and modules stay hidden exactly as for the student. **Output is an allow-list projection**, never the source schema: `GuardianGradeOut`: `title, due_at, state, points, possible, percent, label`. No `hand_in`, feedback, rubric comments, attempt or assessment ids. `GuardianDueOut`: `course_title, title, kind, due_at`. `GuardianAnnouncementOut`: `title, body_html, published_at`. The course total is projected the same way.

A course outside the student's active student enrollments is 404. While an under-14's consent is pending, read routes return 403 `consent_required` and the parent sees only the consent screen.

**Concurrency.** Redeem: one `UPDATE guardian_pairing_codes SET consumed_at=now WHERE code_hash=:h AND consumed_at IS NULL AND revoked_at IS NULL AND expires_at>now RETURNING student_user_id`, then lock the student row, check caps, insert the link. A failed cap rolls back the consume. Every consent or link change locks the student's `users` row first (`FOR UPDATE`), so two withdrawals cannot leave `ok` with no holder. Deletion takes the same lock, so a link cannot appear on a tombstone.

`AppHeader` shows a "Parent" area when `GET /auth/me` returns `is_guardian` (one indexed query, on that route only). Without a link, the entry is on `/privacy` and on the register screen ("I'm a parent" after the age step, then `/parent`).

## 5. Security
### 5.1 Rate limits (`core/ratelimit.py`)

| Route | Rule (key, limit, window) | Counts |
|---|---|---|
| `/auth/login` | `login_email_fail_10m` hashed email 10/600; `login_email_fail_24h` 50/86400; `login_ip_fail_10m` 300/600 IP | failures; the check runs before bcrypt |
| `/auth/register` | `register_ip_1h` 120/3600 IP; existing email cooldown | all |
| `/auth/verify-email` | `verify_ip_fail_10m` 60/600 IP; existing `email_code_attempts` | failures |
| `/auth/forgot-password`, `/auth/resend-code` | `forgot_email_1h` 5/3600; `forgot_ip_1h` 60/3600 IP | all |
| `/auth/reset-password` | `reset_ip_fail_10m` 30/600 IP | failures |
| `/me/guardians/pairing-code` | `pair_create_user_1h` 5/3600 | all |
| `/guardian/links` | `pair_redeem_user_10m` 10/600, `pair_redeem_user_24h` 30/86400, `pair_redeem_ip_fail_10m` 60/600 IP | failures |
| access code, invite lookup (F3) | `access_code_ip_10m` → 2000, `invite_lookup_ip_10m` → 600 | existing |
| Others (join, apply, invite accept, access code per user) | Already covered | |

Also on login: run a dummy `verify_password` for an unknown email so timing does not reveal accounts. Successful logins write nothing, so the exam-start burst costs one read. A guessing-coverage test parametrises every route above and asserts 429.

### 5.2 JWT
- Lifetime 7 days → **3 days, rolling**. `POST /auth/refresh` (Bearer, reads DB state) returns a new token. `<TokenRefresh/>` in `app/[lang]/layout.tsx` calls it once per load when the token is older than 12 h. An exam of under 6 h opened after any page load cannot expire. No call inside the player. Tokens issued earlier stay valid until they expire: no mass logout.
- **Revocation**: `users.token_version`; token claim `tv`, missing = 0; `get_lms_user` compares with the row already loaded (no new query). Bumped by reset-password, `POST /auth/logout-all`, admin disable, anonymize. `sub` stays the only identity.
- **Rotation**: decode tries `SECRET_KEY`, then `SECRET_KEY_PREVIOUS`, so rotating does not log everyone out. Test: production start refuses `DEFAULT_SECRET_KEY`; add the refusal if it is missing. Owner performs the rotation.

### 5.3 `RATE_LIMIT_IP_ENFORCE` after verifying XFF
1. Deploy a temporary public `GET /api/v1/diag/ip` → `{resolved_ip, xff_parts, hops, enforce}` (own chain only, IP-limited, in `route_inventory`).
2. From a known IP (`curl ifconfig.me`), and once more from another network, call it directly and with `X-Forwarded-For: 1.2.3.4`. The right `RATE_LIMIT_PROXY_HOPS` is the value where `resolved_ip` is the real IP and never `1.2.3.4`. Record the output in `docs/runbooks/IP_CHAIN.md`.
3. Change the defaults in `config.py` (`RATE_LIMIT_PROXY_HOPS=<found>`, `RATE_LIMIT_IP_ENFORCE=True`) and delete the probe in one commit. Check after deploy with a test bucket. Kill switch: env `RATE_LIMIT_IP_ENFORCE=false`. If the probe shows no spoof-proof value, keep log-only and add it to the owner list.

The same-origin Vercel path stays open as a second route and resolves to a Vercel IP; no real student uses it, so it can only exhaust its own bucket. Noted in the runbook.

### 5.4 HttpOnly cookies: **no, stay on Bearer**
`*.vercel.app` to `*.onrender.com` is cross-site, so the cookie is third-party and Safari blocks it. Sending everything through the rewrite would put 300 writes/s of autosave on Vercel's free tier and add a hop to every exam request. Student view needs a per-tab token; a cookie is per browser. Bearer has no CSRF exposure; cookies would add CSRF work on every write. A session migration during the exam-sensitive launch risks lost answers.

Compensation: 3-day tokens, revocation, CSP, the server sanitizer. Revisit when the owner buys a custom domain (`api.` and `app.` on one site make cookies first-party). Record in `PRODUCT_DECISIONS.md`.

### 5.5 CSP and headers
`next.config.ts` `headers()`, enforced on all pages:
`default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: <R2_PUBLIC>; font-src 'self' data:; connect-src 'self' <API origin> <R2_PUBLIC>; media-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; frame-src 'self' blob:`
plus `X-Content-Type-Options`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`. HSTS already comes from Vercel.

`'unsafe-inline'` in `script-src` is a deliberate limit: nonces force dynamic rendering on every page and spend the free function allowance. The five `dangerouslySetInnerHTML` files are reviewed in S4 (each must render server-sanitized or KaTeX output only). e2e fails on any CSP violation: `helpers.ts` listens for console `Content Security Policy` errors, so `ort`, `ort-visual` and `bluebook-player` prove no player regression.

Backend pure-ASGI middleware `core/security_headers.py`: `X-Content-Type-Options: nosniff`, `Cache-Control: no-store` on authenticated JSON, `Content-Security-Policy: default-src 'none'; sandbox` on file downloads.

### 5.6 Other
- **Dependency audit**: CI job `audit` (`pip-audit -r backend/requirements.txt`, `npm audit --omit=dev --audit-level=high`) plus `.github/dependabot.yml`; findings fixed in S4 or recorded as accepted with reasons in `docs/SECURITY_AUDIT.md`.
- **Test-student files**: `student_view/sweep.py` `sweep_retired_files(db, limit, apply)`: hand-in assets of enrollments with `is_test_student` and `state='removed'`, via `erase_asset`, 200 per run. `POST /admin/storage/test-student-files/sweep {apply: false}` returns `{files, bytes}`. Apply on production needs the owner's first OK.
- **Flaky test**: `test_ip_failure_limit_counts_failures_only`: `monkeypatch.setattr(ratelimit, "_now", lambda: FIXED)`, because 122 calls can straddle the window. Same fix anywhere `test_ratelimit.py` has the same shape.
- **Full `/security-review`**: gate after S1–S6 (§12).

## 6. Performance
All runs are local Postgres, free. **Never against Neon production** (compute hours); `mcp__neon__list_slow_queries` read-only is allowed as a hint.

1. **EXPLAIN review.** `loadtest/perf_seed.py` (6,000 students, 200 courses, 5 ORT-sized assessments of 150 items, 900k `attempt_items`, 200k grade events, 50k practice attempts, test students mixed in). `loadtest/explain_review.py` runs `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` on the SQL of `statistics.service` (refresh, summary), `analytics.service` and `org_service`, `progress.service.mistakes` and `progress`, `home.service.home`; output in `loadtest/results/explain_phase11/`. Fail if > 200 ms on a warm cache or a Seq Scan on `attempts`, `attempt_items`, `enrollments`, `submissions` with more than 1% of rows read. Report: `docs/phases/PHASE_11_EXPLAIN.md`. Fixes first by query change, then by `0018` (`CREATE INDEX CONCURRENTLY`; the migration runs outside a transaction).
2. **Load script.** Reuse `loadtest/exam_seed.py`, `exam_load.py`, `exam_verify.py`; add `loadtest/mixed_load.py` (home, notebook, statistics and analytics reads during steady autosave). Report `docs/phases/PHASE_11_LOADTEST.md` states the size reached on this machine and that it **does not prove 6,000 students**.
3. **Practice retention.** `practice/retention.py` `sweep(db, *, days, limit=500, apply)`: `attempts` where `is_practice` and `submitted_at < now - days`, keeping the newest per `(user_id, assessment_id)`; deletes items, sections, attempt in that order, batches, `FOR UPDATE SKIP LOCKED`. Only practice rows (test: a graded attempt is never selected, trigger or not). `POST /admin/storage/practice-retention/sweep {apply: false}` returns `{attempts, items, approx_bytes}`. `PRACTICE_RETENTION_DAYS=0` makes apply return 409 `retention_off`; suggested value 365, owner's OK needed. A mistake older than the window may leave the notebook: tested and documented.

## 7. Operations

| Item | How (free) | Who |
|---|---|---|
| Structured logs | `core/logging.py` JSON formatter; pure-ASGI `core/request_log.py`: `request_id`, route template, status, ms, `user_id`. Never email, IP, query string or body. 5xx and > 1 s always, 2xx sampled by `LOG_SAMPLE_2XX` | Agent |
| Error tracking | `sentry-sdk`, active only when `SENTRY_DSN` is set; `send_default_pii=False`, scrubbing on; off by default | Agent writes; owner creates the free account, sets the DSN and accepts the cross-border point |
| Uptime | `.github/workflows/uptime.yml`, cron every 30 min (free on a public repo): `/health` with 90 s timeout and the frontend `/ru/login`; failure opens or updates one GitHub issue | Agent |
| Runbooks | `docs/runbooks/DEPLOY.md`, `ROLLBACK.md`, `RESTORE.md`, `INCIDENT.md`, `IP_CHAIN.md` | Agent |
| Restore drill | `scripts/restore_drill.py` (`DRILL_DATABASE_URL` env, never printed): `alembic current` = head, row counts of key tables, one student read through local `uvicorn`, no row contents in output. Neon branch at a past timestamp; report `docs/runbooks/RESTORE_DRILL.md` with time taken and the real history window. R2 has no restore: stated as a gap | Agent runs it; the branch count is 8/10, and deleting a drill branch needs the owner's OK |
| Cost review | `docs/COSTS.md`: each service, plan, free limit, current use from Neon and Vercel tools (Render when its MCP works, else the owner reads it), date read. Options at 6,000 students as questions, no purchase | Agent writes; owner decides |
| Launch checklist | `docs/LAUNCH_CHECKLIST.md`: tick boxes in two groups, each linking to proof. Exit criteria from the plan | Agent writes; owner signs |

## 8. Agent can do, owner must do or decide
**Agent can do**: everything in §2–§7 in code, with drafts of wording; restore drill; local load test; IP probe and flip; dependency fixes; CSP; uptime; docs; final `/security-review` and fixes.

**Owner must do or decide** (each is a line in `LAUNCH_CHECKLIST.md`):

| Item | Blocks launch? |
|---|---|
| Legal review of policy wording, age cutoff, due days, "anonymized enough" (§3.4), cross-border basis (Neon, Render, Vercel, R2, Sentry outside Kyrgyzstan) | Yes |
| Paid Render plan and Neon compute for 6,000 | Yes, for an exam at that size |
| Full 6,000-student load test on paid infrastructure (script is ready) | Yes, for an exam at that size |
| Rotate `SECRET_KEY` and any owner-held keys | Yes |
| Custom domain for R2 / site | No |
| Sentry free account and DSN | No (logs work without) |
| First production apply: test-student file sweep; practice retention value and first apply | No |
| Delete drill branch or an old one (Neon 8/10) | Only if branches run out |
| Set `PRIVACY_LEGACY_DEADLINE` after legal review | No |
| Sign the checklist | Yes |

## 9. Owner questions with safe defaults (block nothing)

| # | Question | Default until answered |
|---|---|---|
| 11-Q1 | Under-14 cutoff is D5's; correct in law? | 14, data-driven in one constant |
| 11-Q2 | New under-14 sign-ups restricted before legal review? | Yes: strictest, reversible (`PRIVACY_UNDER14_GATE`) |
| 11-Q3 | Deadline for existing accounts? | None; banner only |
| 11-Q4 | Request due days? | 30 |
| 11-Q5 | Is a tombstone with immutable free text anonymous enough? | Yes for now; flagged for the lawyer |
| 11-Q6 | Practice retention? | Off; suggest 365 days |
| 11-Q7 | Email the person when a request completes? | No email: their address is gone, and free send quota is saved |
| 11-Q8 | Parent sees feedback text? | No: grades, due dates, announcements only |
| 11-Q9 | 14–17 students can remove a parent at any time? | Yes |
| 11-Q10 | Restore window long enough on the free plan? | Record what Neon gives; no purchase |

## 10. Quality
Most golden journeys exist in `frontend/e2e/`. **Missing, and only these:**
- `parent.spec.ts`: student generates a code, parent signs up and links, sees grades, due dates and announcements, no answers; under-14 blocked, parent consents, unblocked; student and parent revoke (S2).
- `privacy.spec.ts`: sign-up in each band, legacy banner, export download, delete request executed by admin (S3).
- `org-admin.spec.ts`: add one test **org admin invites a teacher, teacher accepts**. Existing specs invite students and roster-import teachers only (S3).

Final ORT review: `ort`, `ort-visual`, `bluebook-player` zero diffs. UX check per `AGENTS.md` §6.10 on changed screens.

## 11. Screens (current shell, short labels)

| Route | Content |
|---|---|
| `(auth)/register` | First step: three age buttons; `Parent` link; policy checkbox with links (not for under-14) |
| `/[lang]/policies/[kind]` | Policy body; `Draft: awaiting legal review` badge |
| `/[lang]/privacy` | My data: age, consents, Parents list, `Get code`, `Download my data`, `Delete account`. Under-14 pending: code big at top, nothing else needed |
| `/[lang]/parent` | Enter code; linked students |
| `/[lang]/parent/[linkId]` | Tabs `Grades`, `Due`, `Announcements`; or a consent screen when needed. Remove link |
| `/[lang]/admin/privacy` | Request table: person, kind, due, overdue, `Run`, `Reject` |
| Home banner | `Confirm your age` |

## 12. Slices
Order: **S1 alone → S2, S3, S4, S5 in parallel → S6 → gate.** Separate top-level i18n namespaces per slice; the later slice merges JSON conflicts. Every slice runs: SQLite suite, the Postgres suite (`AGENTS.md` §5), `alembic check`, parity script, `tsc`. Scratch DB and upload dir only.

### S1 Privacy backend (**Opus**: anonymization and gate are the riskiest code; no Fable, this design settles the hard choices)
- **Owns**: `alembic/versions/0017_phase11_privacy.py`; `app/models/user.py`; `app/lms/files/models.py`, `files/service.py` (`erase_asset`, refcount); `assignments/files.py` (410); `app/lms/privacy/**` (models, policies, manifest, seed, service, router, gate, anonymize, registry, schemas); `app/lms/guardian/models.py` (tables only); `core/deps.py` (gate branch); `api/v1/endpoints/auth.py` and its schema (register only); `app/main.py` (seed, routers); `route_inventory.py`; `student_view/service.py` (`exempt`); **stubs for the parallel slices, so they never edit shared wiring**: empty routers and policy dicts in `guardian/router.py`, `guardian/policies.py`, `practice/retention_router.py`, `student_view/sweep_router.py`, `core/security_policies.py`, all imported by `main.py` and `route_inventory.py`; `is_guardian` in `_profile`; `tests/lms/isolation.py` (**all five new tables**, policy reseed); `tests/auth_helpers.py`, `tests/test_auth_flow.py`, `tests/test_auth_emails.py`, `tests/lms/test_student_view.py`, `tests/lms/test_security_s5.py`, `frontend/e2e/seed_backend.py` (register call only); `docs/PERSONAL_DATA.md`; draft policy text in en, ky, ru.
- **Tests** `tests/lms/test_privacy.py`, `test_privacy_gate.py`, `test_anonymize.py`, `test_pd_registry.py`: Every band at register; legacy path; gate allows autosave and submit on an open attempt and refuses start and join. Gate and exempt: test student denied on every new route; no new query in `get_lms_user` (count queries). **Sentinel**: fill every registered column with `PII-SENTINEL`, anonymize, scan every text and JSON column; only `keep_immutable` entries may still hold it. **Statistics equal** before and after: `statistics`, `analytics` and gradebook-excluding outputs. PG: anonymize runs without `lms.allow_grade_purge`; `grade_events` and attempt row hashes identical; `consent_records` refuses UPDATE and DELETE. Registry: every FK to `users.id` and every text or JSON column matching the name scan is registered or in `NOT_PERSONAL`, else fail. Export holds only own rows; blocked delete codes; request due date; re-register with the same email after deletion.

### S2 Parents (**Opus**: authorization and projection)
- **Owns**: `app/lms/guardian/{router,service,schemas,policies}.py`; `frontend/src/app/[lang]/parent/**`; `frontend/src/components/guardian/**`; `lib/lms/nav.ts` (comment only); `guardian.*` i18n; `frontend/e2e/parent.spec.ts`; `tests/lms/test_guardian.py`, plus additions in `tests/lms/test_pg_concurrency.py`.
- **Tests**: Another parent, a revoked link, a deleted student and a test student all give 404. **Response keys are exactly the allow-list** on all routes (no `hand_in`, `feedback`, `attempt`). Hidden grades hidden; no course access for the parent (`/courses/{id}/...` 403 or 404). Under-14 rules; adult check; caps; code expiry, single use, enumeration gives one 404 shape, limits give 429. PG: two parents redeem one code, one link; two withdrawals, state correct. **Note**: reads home and gradebook functions, edits none. If one needs a parameter, that is a coordinated edit reported to the orchestrator.

### S3 Privacy screens (**Opus**: Kyrgyz and Russian wording, gate states; layout simple)
- **Owns**: `(auth)/register/**`; `app/[lang]/privacy/**`, `policies/**`, `admin/privacy/**`; `components/privacy/**`; `components/lms/LmsShell.tsx` (banner, not on player paths); `components/ui/AppHeader.tsx` (Parent area); `lib/api.ts` (`consent_required` redirect); `privacy.*` i18n; `frontend/e2e/privacy.spec.ts`; one test in `org-admin.spec.ts`.
- **Tests**: e2e above; `helpers.ts` not touched; parity; ORT e2e zero diffs.

### S4 Security (**Opus**: auth and limits are exam-critical)
- **Owns**: `core/ratelimit.py`; `core/security.py`; `core/deps.py` (`tv`, `client_ip`, rebased after S1); `core/config.py`; `core/security_headers.py`; `api/v1/endpoints/auth.py` (limits, refresh, logout-all; rebased after S1); `core/security_policies.py`; `accommodations/service.py`, `invitations/service.py` (F3 values); `student_view/sweep.py`, `student_view/sweep_router.py`; `frontend/next.config.ts`; `frontend/src/lib/tokenRefresh.ts`; `frontend/src/app/[lang]/layout.tsx`; `frontend/e2e/helpers.ts` (CSP listener); `.github/workflows/ci.yml` (audit job); `.github/dependabot.yml`; `docs/SECURITY_AUDIT.md`; `docs/runbooks/IP_CHAIN.md`; `test_enrollments_api.py` (flaky fix). `app/main.py` gets one line by S4 (headers), then S6.
- **Tests** `tests/lms/test_security_11.py`: guessing coverage; login failures only, no writes on success; `tv` mismatch 401, missing `tv` accepted; reset-password revokes; `SECRET_KEY_PREVIOUS` accepted; refresh refused for a disabled user; `client_ip` table with each XFF shape; sweep dry run and apply; repeat of the flaky test 20 times.
- **After merge** (orchestrator): the three steps in §5.3 on production.

### S5 Performance (**Opus**: query plans need judgement)
- **Owns**: `loadtest/perf_seed.py`, `explain_review.py`, `mixed_load.py`; `backend/app/lms/practice/retention.py`, `practice/retention_router.py`; `alembic/versions/0018_phase11_indexes.py` if proven; query changes in `statistics/service.py`, `analytics/service.py`, `analytics/org_service.py`, `progress/service.py`, `home/service.py`; `docs/phases/PHASE_11_EXPLAIN.md`, `PHASE_11_LOADTEST.md`; `tests/lms/test_practice_retention.py`.
- **Tests**: retention selects practice only and keeps the newest; off gives 409; before-and-after API output equal for every changed query.

### S6 Operations and launch docs (**Sonnet**: well-defined, no decisions left)
Runs after S1–S5 so that the checklist and runbooks cite real results.
- **Owns**: `core/logging.py`; `core/request_log.py`; `core/sentry.py`; `app/main.py` (two lines); `requirements.txt` (`sentry-sdk`); `.github/workflows/uptime.yml`; `scripts/restore_drill.py`; `docs/runbooks/**` except `IP_CHAIN.md`; `docs/COSTS.md`; `docs/LAUNCH_CHECKLIST.md`; `docs/PRODUCT_DECISIONS.md` (Phase 11 entries: F4, §5.4, §9 defaults); `AGENTS.md` and `HANDOFF_NEXT_AGENT.md` state lines; `tests/test_request_log.py`.
- **Tests**: log line has no email, IP or query string (fixture with a sentinel email); SDK not started without a DSN; drill script on a local DB.

### Gate (orchestrator, **Opus**)
`/security-review` on the phase diff; fix findings. ORT parity (imports, e2e, screenshots, scores). UX check. Neon backup branch before merging migrations to `main`. Restore drill. Then stop for the owner before launch.
