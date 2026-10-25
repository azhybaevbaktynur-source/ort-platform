# Phase 6a: organizations foundation, course templates (ORT first), invitations

**Status**: built and verified on branch `phase-6a` (2026-10-25); deploy and owner checkpoint follow. Design: `docs/phases/PHASE_6_DESIGN.md` (approved 2026-10-25). Decisions taken while building: `docs/PRODUCT_DECISIONS.md` "Phase 6a implementation decisions" (I1–I11). Slice rules: `PHASE_6A_SLICE_RULES.md`.

## What changed

| Area | Change |
|---|---|
| Organizations | New tables `organizations`, `organization_members` (org_admin / teacher), `organization_template_grants`, `invitations`; `courses.organization_id` + template columns; `question_banks.organization_id`. Migration `0008_phase6_organizations` (data steps per design §4) and the same steps in the lifespan bootstrap (`app/lms/organizations/bootstrap.py`). Platform organization (placeholder name "Platform", slug `platform`; rename later in the admin area). Each approved independent teacher gets a personal organization (they are its org admin); banks are never shared between them. |
| Authorization | Org admins: read-only inside their organization's courses (student views, no answer keys, attempts or grades) plus student roster management and ownership transfer to members; full teacher powers only through the audited "Join as teacher". Suspended organizations are read-only (attempts already started may finish). Course creation is decided by organization membership (`can_create_courses`); new policy names `org_admin`, `course_creator`, `public+ratelimit`. |
| Course templates | Code registry `app/lms/templates/` (`ort`, general). ORT is wrapped, not rewritten: it imports the existing ORT constants, importer profiles and scheme versions. ORT presets and ORT import formats exist only in ORT courses; ORT structure (sections, order, timers, navigation, scheme) is locked (409 `template_locked`) and greyed out in the UI with "Fixed by the ORT template". Only platform admins grant the ORT template (per organization) and toggle the lock. |
| Invitations | Org admins / the platform admin invite teachers and org admins; course owners invite co-teachers/assistants without an account. Email "{inviter} via Platform", Reply-To = the inviter, link with the email prefilled; 14 days, single use, one 404 shape, rate limits; accept by link or from "My invitations". |
| Sign-up | No teacher choice; neutral texts and emails (no "ORT preparation"); "I am a teacher" → `/teacher-access` (ask your administrator, or apply as an independent teacher). |
| Pages | Platform admin: Organizations list + detail (Summary, Admins, Teachers, Courses, Usage, Templates, Log), suspend/resume, user detail "Organizations and roles", course transfer with a user picker. Org admin area `/[lang]/org/[orgId]` (overview, teachers + invite, courses + create with owner, course summary + join as teacher). Invite accept page. Pending-invitation banner. |
| Fixes | H2 (all API datetimes as UTC `Z`; the frontend reads timezone-less strings as UTC), A10 (ORT subject key aliases), students no longer see the grading-scheme library, general courses show no ORT hints/options, phone header fits 375 px in ru/ky. |

## ORT review (design §6)

**Function unchanged** — proven by:
- `tests/lms/test_ort_import_golden.py`: the ORT CSV and the `tsoomo19.zip` bundle import to exactly the frozen pre-6a questions, versions, content hashes, sections, passages and images (fixtures generated before any 6a change); re-importing the zip is a no-op.
- `tests/lms/test_ort_e2e_api.py`: comparison item, autosave, forward-only sections, section timer boundary, submit, scaled score / percentile / five section rows / golden certificate with today's numbers.
- `test_ort_parity.py`, `test_ort_seed.py`, `test_ort_cutover_flow.py` unchanged and green; CI job `ort-parity`.
- Browser walkthrough (`PHASE_6_screens/6a/WALKTHROUGH.md`): CSV + zip import (default `full_main`), `ort_main` exam with the five sections in order, publish, student join → lobby → comparison → flag → section-end dialog → numbered passage → submit → result. 18/18 steps pass.

**Look**: ORT player screens (`6a/student-14` … `student-25`) compared side by side with the pre-6a `audit/` images by the ux-reviewer: unchanged except the header (phone overflow found and fixed) and one phone wrap on the result review card in Kyrgyz (layout only; before/after `6a/ort-review-before-phone-ky.jpg` / `ort-review-after-phone-ky.jpg`). Teacher side: locked controls greyed out with the note; question editing unchanged.

**Visible to ORT teachers** (owner-approved lock list A7, decision I1): sections of ORT preset exams can no longer be added, removed, reordered or retimed, navigation and grading scheme are fixed.

## How to verify

```bash
# SQLite (AGENTS.md §5): 2629+ passed, 23 skipped. PG full suite green; alembic head 0008_phase6_organizations, `alembic check` clean.
```
Rehearsal on a copy of production (Neon branch `backup-2026-10-25-before-phase6a`, restored locally): `alembic upgrade head` + lifespan + `backend/scripts/rehearse_0008.py` → all checks pass (both ORT courses in the platform organization, template `ort` v1 locked, one grant, owner = the owner's account, demo teacher kept as system co-teacher, 0 courses/banks without organization).

UX gate: `docs/phases/PHASE_6_screens/6a/` (INDEX.md), ux-reviewer findings fixed in two rounds; 6b items listed below.

## Deferred

- To 6b (design system, `AppHeader` with area switcher, student home): staff header height and tab rows on phones, admin sub-nav clipping, badge/button styles, org overview tiles as links, general course home copy, `/teacher-access` status wording, consistent dialog component.
- Org setting `teachers_can_create_courses` UI beyond the toggle, contact email for organizations, departments, shared org banks, student invitations → Phase 9.
- SQLite-only: admin user search by Cyrillic name (PostgreSQL is fine).
- `docs/BUNDLE_FORMAT.md` still lists the old subject keys (they remain accepted as aliases).

## Owner items

- Render: if `EMAIL_FROM_NAME` is set to an ORT-branded value, emails keep that sender name; the code default is now "Platform".
- Rename the platform organization when the final name is chosen (admin → Organizations → Platform → Edit).
- Neon: branch limit (10) reached; deleting old backup branches needs your OK.
