# Phase 9: organizations completion, enrollment forms, invitations

**Status**: built on `phase-9`, 2026-11-01. Deploy details are at the end.

**References**
- Design: `PHASE_9_DESIGN.md`.
- Decisions: `PRODUCT_DECISIONS.md`, section "Phase 9 decisions". It covers owner questions 9-Q1 to 9-Q8 (defaults in effect) and P9-1 to P9-9.

Everything is built inside the 8c navigation shell. There is no new sidebar link.

## What organizations get
- **Departments.** An organization holds departments up to two levels deep. Organization admins also manage everything below them, and courses can be moved between departments. A department can't be deleted while it still has sub-departments, courses, banks or templates. Suspending an organization or a department makes everything below it read-only.
- **Organization settings.** Bank sharing on or off, catalog defaults, how long application answers are kept (30–90 days), and whether teachers may invite students.
- **Usage overview.** Usage counts are broken down by department.
- **Shared question banks.**
  - A course's teachers can share one of the course's banks with the whole organization.
  - Every teacher in the organization can copy a shared bank into their own course ("From my organization").
  - Organization admins can edit the content of shared banks. They cannot delete them or share a private bank.
  - Quiz banks, sandbox banks, personal organizations and ORT courses never share.
- **Roster import** (CSV, at most 500 rows):
  - A dry run comes first; nothing is sent until the admin confirms.
  - Students receive invitations and are never enrolled by force. Teachers who already have accounts are added directly; the rest are invited.
  - Importing the same file again changes nothing.
  - No passwords are accepted, and the uploaded file is not stored.
- **Platform admin.** A new Departments tab, with suspend and resume per department.

## What teachers get
- **People tabs.** People now has the tabs Roster · Invitations · Applications.
- **Student invitations by email.** At most 50 per request. Teachers can resend and revoke them; invitations expire after 14 days.
- **Enrollment forms.** Built under Settings → Enrollment with an Edit tab, a Preview tab and versions. A form is immutable once anyone has answered it; changes go into a new version.
- **Course enrollment modes.**
  - open
  - with a join code
  - by application, approved by the teacher
  - by application, with immediate entry
  - closed

  A "Show in the catalog" switch controls whether the course appears in the catalog.
- **Applications inbox.** Teachers approve or reject with a note. The note is visible to the student on the course page and is emailed only when the teacher ticks the box.

## What students get
- **Catalog.** Search with filters for language, organization and enrollment mode.
- **Course landing page.** Shows how to join, or the student's application status, with the teacher's note.
- **Application form.** Comes with a privacy note.
- **Home page.** Shows a line for pending applications.
- **Invitation accept page.** The email address is shown masked.

## Privacy (minors)
- **Who sees answers.** Form answers are visible only to the course's teachers and to the applicant. They never appear in logs, audit rows, error details, exports or admin views.
- **Purge.** Answers are deleted 30–90 days after a rejection, a withdrawal, the student leaving the course, or the course being deleted. The purge runs during normal traffic, because production has no scheduler. An internal endpoint is ready for a free scheduler later.

## ORT
- **Unchanged:** the ORT exam, player, bank, import and results.
- **Refused on ORT courses:** form modes and bank sharing.
- **Allowed on ORT courses:** student invitations.
- **Checks:** ORT screenshots show zero diffs, and the importers diff is empty.

## Schema
Migration `0014_phase9_organizations_forms`:
- organizations gain `kind`, `path`, `depth` and validated settings;
- `question_banks` gains `visibility` (quiz banks always private), `shared_at` / `shared_by` and `copied_from_bank_id`;
- new tables: `organization_roster_imports`, `enrollment_forms`, `enrollment_form_fields`, `enrollment_applications`;
- invitations accept the role `student`;
- courses gain `catalog_search`.

The backfill was checked on production-shaped data.

## Reviews
- **Security review of S1** (architect): two medium and six low findings.
  - The two mediums: bank rights followed the bank's own organization instead of the course's, and a department's suspension was ignored.
  - All were fixed in `phase-9-fix1`. The fixes also stopped organization admins from deleting or restoring banks.
- **Final security review** (architect): one medium and four low findings.
  - The medium: suspension was not inherited on some writes.
  - The lows: a race during approval, form re-validation at submit, the roster import budget, and roster import logging.
  - One design detail was also fixed: banks are copied only within the same organization tree.
  - All were fixed in `phase-9-fix2`, including suspension of a middle department.
- **Integration (S5).** The walkthrough found two bugs, both fixed: courses could not be moved into a department, and the note on an approved application was not shown.
- **UX gate** (ux-reviewer): 5 major and 12 minor findings, fixed in `phase-9-ux`. Screens are in `PHASE_9_screens/` (see `INDEX.md`).

## Tests
- **Backend:**
  - `test_org_tree_s1.py`, `test_can_edit_bank_s1.py`, `test_course_modes_s1.py`
  - `test_org_departments_s2.py`, `test_shared_banks_s2.py`
  - `test_roster_import.py`, `test_student_invitations.py`
  - forms, applications, PII and purge tests, plus `test_pg_concurrency_applications.py` (6 races)
  - `test_phase9_fix1.py`, `test_phase9_fix2.py`
  - `tests/test_migration_0014.py`
- **Frontend:**
  - `frontend/e2e/org-admin.spec.ts`: departments, sharing, copy, roster import, invitations, Student view, ORT.
  - `frontend/e2e/catalog-apply.spec.ts`: form, catalog, landing, apply, approve or reject, withdraw, `form_auto`.

## Deploy
- Gates on merged `phase-9` (f40609f): SQLite 3623 passed / 45 skipped; PG 3698 passed / 24 skipped; fresh PG `alembic upgrade head && alembic check` clean; PG migration tests 42 passed; importers diff empty; i18n parity OK (4265 keys); `tsc` clean; `next build` OK; e2e (9 specs incl. `org-admin`, `catalog-apply`, `ort`, `ort-visual`) green twice, ORT zero diffs.
- Read-only production preflight before the migration: 1 organization (no parents), 4 banks (1 quiz bank), 3 courses, 0 invitations.
- Neon backup branch `backup-2026-11-01-before-phase9` (`br-gentle-pine-b2devg4p`) — **Neon branches now 10/10**: the next migration deploy needs the owner's OK to delete an old backup.
- `phase-9` → `lms` (21ec372) → `main` (636d14a). `/health` = 636d14a; Neon `alembic_version` = `0014_phase9_organizations_forms`; backfill verified (platform org kind/depth, all banks private, every course has `catalog_search`); data intact (300 question versions, 2 ORT exams).
