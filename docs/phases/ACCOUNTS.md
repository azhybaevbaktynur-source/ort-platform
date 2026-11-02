# Accounts and teacher sign-up (Step 2; owner accepted the defaults Q1–Q7 of `docs/DISCUSSION_ACCOUNTS.md`, 2026-11-03)

Read `docs/DISCUSSION_ACCOUNTS.md` first: it says why. ORT behaviour and screens don't change. All strings en/ky/ru. No role column. Everything below is server-enforced; the frontend only reflects it.

## A. Data: migration `0019_teacher_applications` (additive)
`teacher_requests` gains nullable `applicant_name` (200), `school` (200), `subject` (200), `phone` (32), `phone_purge_after` (timestamptz). Old rows keep `message`. No other table. Mirror the model; `alembic check` clean.

Privacy: add each column to `app/lms/privacy/registry.py` (phone as contact data, nulled on anonymize, likewise name, school and subject), and to the export. Never put the phone or the name in audit details or logs. Test: registry coverage, export includes own values, anonymize nulls them, audit row has no phone.

## B. API
`POST /me/teacher-requests` body (extra fields forbidden):
`applicant_name` 1–200, `school` 1–200, `subject` 1–200 (trimmed, no control characters), `phone` (5–32 chars of digits, spaces, `+ - ( )`, at least 5 digits), `message` optional up to 2000, `age_confirmed` bool, `policy_version_ids` optional list.

Order: rate limit (existing `TEACHER_REQUEST_24H`) → `already_teacher` 409 → `request_pending` 409 → wait after a rejection: latest request `rejected` with `decided_at` under 7 days ago gives 409 `reapply_wait`, details `{available_at}` (constant `REAPPLY_WAIT_DAYS = 7`; a later approval or revoke doesn't count as a rejection) → age: `users.age_band` `under_14` or `14_17` gives 403 `teacher_age_required`; `18_plus` passes; NULL needs `age_confirmed = true` and valid `policy_version_ids` (`privacy.accepted_policies`), then `privacy.apply_age_band(..., source="teacher_application")` under the user lock, in the same transaction; otherwise 422 `age_confirmation_required`. Never lowers or overwrites a set band. `POST` stays behind the consent gate and stays refused for test students.

`GET /me/teacher-requests` rows gain the four fields and `reapply_available_at` (rejected rows only).

Admin queue rows gain `applicant_name`, `school`, `subject`, `phone`, `teaches_at` (names of active root organizations of kind `school` or `platform` where the applicant is a member, max 5, one query). Applying and approving don't change memberships; nothing is cancelled automatically when a school invitation is accepted.

`GET /me/lms`: `admin_organizations` excludes `kind = personal` (suspended schools stay listed, as today).
`GET /me/organizations` rows gain `kind`.
`GET /me/home` gains `teacher_application`: null, or `{status: pending|approved|rejected|revoked, decided_at, reason, reapply_available_at}`. Shown when pending; decided within the last 14 days; or `users.teacher_status = revoked`. One indexed query. Reason is what the person already sees today.
`POST /org/{id}/invitations`: on a `personal` organization 409 `personal_org_no_members`. Existing open invitations stay acceptable. Course staff invitations are untouched. Platform admin member routes untouched.
`GET /courses/{id}` for staff gains `can_import_roster`: caller is org admin of the course's organization (tree rule) and the course is not a sandbox or locked-template (ORT) course.
`GET /platform/users/{id}` gains `revoke_impact: {students, courses}`: distinct active students (never test students or previews) and non-deleted courses in the user's personal organization.

Add routes to `route_inventory` only if new ones appear; none are planned.

## C. Decisions and emails
`approve`, `reject`, `set_teacher_status(approved|revoked)`:
- Email the person in `users.locale`: approved (link to create a course), rejected (with reason, and when they can reapply), revoked (plain statement). Trilingual, through the existing email service and its pattern in `invitations`. Sent after commit; a send failure never undoes or fails the decision (log without the address). Never to a disabled account or a test student.
- Rejection sets `phone_purge_after = now + 90 days`. Revoke sets it on the person's latest approved request. Re-approval clears it.

Purge job: `phone_purge_after <= now` nulls `phone` and the timestamp. Follow `app/lms/enrollment_forms/purge.py` and how it is scheduled. Idempotent; test it.

Revoke itself keeps today's behaviour (freeze). Step 3 proposes the second action.

## D. Frontend
**New `/[lang]/for-teachers/apply`** (public shell, `components/landing/PublicShell.tsx`):
- Signed out, three steps on one page: account (name, email, password, "I am 18 or older", policies as on `/register`, `ageBand = 18_plus`) → email code → application (school, subject, phone, name prefilled, optional message). Use the same register and verify calls as `/register`.
- 400 "already registered" from register: "This email is registered: log in to continue" with `/login?redirect=` back here. Keep the entered form data out of URLs.
- Signed in, skip to the application; a NULL age band shows the 18+ confirmation and policies; `14_17`/`under_14` shows a plain refusal; approved shows a link to Teaching; pending shows the status with the application's details; rejected in the wait shows the date; revoked may apply again.
- Leaving before the application means a normal account, and returning here continues.

`/for-teachers`: its main button goes to `/apply`; remove wording that names the menu item. Help page: one answer on becoming a teacher. Landing unchanged otherwise.

**New `/[lang]/invitations`** in `LmsShell`: the Accept list from `teacher-access` (same calls, including `rememberAccepted` and `INVITATIONS_CHANGED_EVENT`), an empty state otherwise. `PendingInvitationsBanner` links here and hides here.

**Redirects:** `/teacher-access` and `/courses/become-teacher` → `/for-teachers/apply`. Delete `TeacherRequestPanel`.

**Remove for students:** the account-menu link (`canRequestTeacher` in `LmsShell`), the button in `grading-schemes`, the link in `courses/new`. Those two pages keep a plain "teachers only" message with a way back.

**Dashboard:** one line from `teacher_application` (like `PendingApplicationsLine`): pending; approved with a link to Teaching; rejected with the reason and the reapply date; revoked with a link to apply. **Teaching list:** the same notice for a revoked teacher, stating honestly that their courses are read-only and students can't start or hand in; correct `teacherRequest.revokedBody`-style wording, which claims courses stay available.

**Organization area hidden for personal:** `/org` picker filters out `kind = personal` (for non-platform-admins). `OrgShell`: a non-platform-admin on a personal organization goes to `/courses?view=teaching`. Course and template pickers (`courses/new`, `SaveAsTemplateDialog`, `ExamTemplatesPage`) label a personal organization "Мои курсы" / i18n, not the person's name.

**Exam templates in Teaching:** also list organization-scope templates of the person's own personal organization (2 exist on production), with the same actions they have today.

**Roster import in People:** when `can_import_roster`, a secondary action on the course's People page opens the existing `RosterImportWizard` with this course as the target and the student kind. Same org routes. The org page keeps working for schools. Not on ORT.

**Admin:** Teacher requests shows name, school, subject, phone, email, "already teaches at", and the old message when present. The revoke confirmation on the user page states `revoke_impact` ("N students in M courses will be frozen: they can't start tests or hand in work") and asks for a reason.

## E. Tests
Backend: `/me/lms` per person in the discussion's table; apply matrix (fields, each age band, NULL band with and without confirmation, policies, rate limit, duplicate, reject wait with date, after revoke, school teacher applying, test student refused, consent gate); emails (all decisions, not to disabled, failure doesn't break the decision); refused personal invitations and still-acceptable old one; purge; privacy; `revoke_impact` excludes test students; `can_import_roster` matrix; authorization of org routes unchanged; home key sets.

Browser, `frontend/e2e/teacher-signup.spec.ts`: new person through all three steps; existing student; email already registered; pending and rejected states; approve and the header change; no teacher link anywhere for a student; invitation accept from `/invitations`; roster import from People; independent teacher: no Organization tab, `/org/{id}` redirects; personal templates listed. Update `header-areas.spec.ts`, `security.spec.ts`, `landing.spec.ts` and any spec using the old pages. ORT specs and pixel baselines stay unchanged.
