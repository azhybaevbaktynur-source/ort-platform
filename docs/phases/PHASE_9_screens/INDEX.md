# Phase 9 UX-gate screens

Written by the e2e walks `frontend/e2e/org-admin.spec.ts` and `frontend/e2e/catalog-apply.spec.ts` (`uxShots`, full page, JPEG). File name: `<screen>-<lang>-<375|1440>.jpg` (375×812 phone, 1440×900 desktop). Staff screens in ru and en, student screens in ru, ky and en; a state that exists only once in a walk (a just-sent result) is in the language of the walk. Toasts are hidden. Fixed sticky bars may overlap content in full-page shots (a screenshot artefact).

## Org admin (org area)

| Screen | Languages | What it shows |
|---|---|---|
| `org-departments-empty` | ru, en | Departments, before any department (empty state) |
| `org-department-create-dialog` | ru, en | New department dialog (name, short address) |
| `org-departments` | ru, en | Department tree: the organization and two departments, row menus |
| `org-department-move-dialog` | ru, en | Move department dialog |
| `org-course-department` | ru, en | Org course summary: new Department card (S5 fix), course moved into «Математика» |
| `org-settings` | ru, en | Organization settings (bank sharing on, student invitations, retention, defaults) |
| `org-overview-usage` | ru, en | Overview with usage tiles and the By department table |
| `org-shared-banks` | ru, en | Shared banks list (the shared «Алгебра E2E») |
| `org-admin-shared-bank` | ru, en | Org admin in the shared bank's home course: can edit questions, no bank delete |
| `org-roster-upload` | ru, en | Roster import step 1: file, who, course, CSV format help |
| `org-roster-dryrun` | ru, en | Roster import step 2: dry-run report (students: 2 ready, 1 invalid) |
| `org-roster-applied` | ru | Roster import step 3: applied (2 invited) |
| `org-roster-again` | ru | Same file again: everything already invited, nothing to send |
| `org-roster-dryrun-teachers` | en | Teacher import into «Языки»: dry run |
| `org-roster-applied-teachers` | en | Teacher import applied: 1 added (account), 1 invited |

## Course staff

| Screen | Languages | What it shows |
|---|---|---|
| `course-bank-share-menu` | ru, en | Bank page «More actions»: Share with organization |
| `course-bank-unshare-menu` | ru, en | Bank page after sharing: Stop sharing |
| `course-bank-picker` | ru, en | Question banks: «From my organization» picker in another course |
| `course-bank-copied` | ru, en | Question banks after «Copy into this course» |
| `course-people-roster` | ru, en | People → Roster tab, «Invite students» primary action |
| `course-invite-dialog` | ru, en | Invite students dialog (two addresses) |
| `course-invite-result` | ru | Invite students result |
| `course-people-invitations` | ru, en | People → Invitations after resend and revoke |
| `course-form-builder-empty` | ru, en | Enrollment form, none yet |
| `course-form-builder-edit` | ru, en | Form builder, Edit tab (one field, draft) |
| `course-form-builder-preview` | ru, en | Form builder, Preview tab |
| `course-form-builder-versions` | ru, en | Form builder with versions (v1 answered/retired, v2 active) |
| `course-settings-enrollment` | ru, en | Settings → Enrollment: application mode, catalog switch, form link |
| `course-applications-inbox` | ru, en | People → Applications inbox (pending) |
| `course-application-panel` | ru, en | Application panel: answers, note, approve / reject |
| `course-application-approved` | ru | Application panel after approval with a note |
| `course-applications-decided` | ru, en | Applications inbox, all statuses (approved, rejected, withdrawn) |
| `ort-people-tabs` | ru | ORT course People: Roster and Invitations tabs, no Applications (design 9) |

## Platform admin

| Screen | Languages | What it shows |
|---|---|---|
| `admin-org-summary` | ru, en | Organization summary (settings fields) |
| `admin-org-departments` | ru, en | Organization Departments tab (read, suspend / resume per department) |

## Student

| Screen | Languages | What it shows |
|---|---|---|
| `student-catalog` | ru, ky, en | Catalog with search and filters |
| `student-catalog-search` | ru, ky, en | Catalog search result with the mode badge |
| `student-landing-form` | ru, ky, en | Course landing, application mode |
| `student-apply` | ru, ky, en | Apply form with the privacy note |
| `student-apply-errors` | ru, ky, en | Apply form, required field missing |
| `student-apply-sent` | ru | Application sent |
| `student-landing-pending` | ru, ky, en | Landing with the pending application and Withdraw |
| `student-home-pending` | ru, ky, en | Home with the «Pending applications» line |
| `student-landing-approved` | ru, ky, en | Landing after approval: Open course and the teacher's note (S5 fix) |
| `student-landing-withdrawn` | ru, ky, en | Landing after withdrawing: Apply again |
| `student-landing-rejected` | ru, ky, en | Landing after rejection with the teacher's note |
| `student-landing-auto` | ru, ky, en | Landing, automatic approval mode |
| `student-apply-approved` | ru | form_auto: approved at once |
| `student-invite-accept` | ru, ky, en | Student invitation accept page (signed out) |
| `student-invite-joined` | ru | After accepting: the course |

204 images.

## Re-taken after the UX-gate fixes (branch `phase-9-ux`)

138 images were re-shot with the same names. They come from the same walks, run after the fixes.

| Screens | What changed |
|---|---|
| `student-apply-errors` | The error box has the title «Check the form» |
| `student-apply` | New ru privacy note |
| `org-admin-shared-bank` | Org admin inside a course: Teaching area, Question banks in the sidebar, breadcrumb back to the organization's course page, no Settings and no Student view |
| `course-settings-enrollment` | Design-system Select for the enrollment mode; the join-code hint names the real reason (draft, application mode, open, closed) |
| `course-form-builder-edit`, `-preview`, `-versions` | Save and Activate in one row on phones; «Delete draft» is in the header's «More actions» menu |
| `course-application-panel`, `course-application-approved` | The application panel is full screen on phones (`Dialog size="full"`) |
| `course-people-invitations` | Revoked invitation cards have no empty action row |
| `course-people-roster`, `course-applications-inbox`, `course-applications-decided`, `org-shared-banks` | English plural count line («1 result») |
| `admin-org-summary`, `org-settings` | «In the catalog» label; enrollment mode names from the shared glossary |
| `org-departments-empty`, `org-departments`, `org-department-move-dialog` | English plurals in the department counts («1 course · 0 members») |
| `org-department-create-dialog` | Primary button «Create» |
| `course-bank-copied` | The copied bank's title is localized («(копия)») |
| `org-roster-upload` | «Choose file» button with the chosen file's name |
| `student-catalog`, `student-catalog-search` | Mode badge names from the glossary; «{n} courses» under the filters after a search |
| `student-landing-form`, `-auto`, `-approved`, `-withdrawn`, `-rejected` | Mode badge names from the glossary |
| `student-landing-pending` | No «How to join» card while the application is pending |
