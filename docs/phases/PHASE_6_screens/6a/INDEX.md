# Phase 6a UX-gate screenshots (branch `phase-6a`, 2026-10-25)

212 JPEG files (quality 70, full page unless the name starts with `header-` or is a `student-17`/`student-25` viewport shot), 12.7 MB. Viewports: desktop 1440x900, phone 375x812 (`isMobile`, deviceScaleFactor 1). A phone image wider than 375 px means the page overflowed horizontally (see WALKTHROUGH.md, finding F1).

Re-shot after the UX fixes F1-F5 (branch `phase-6/s7-uxfix`): all `student-*`, `header-*` and `teacher-01..05` shots and `ort-teacher-05`. The ORT player shots (`student-14` ... `student-25`) come from a second student with the same name (Нурлан Абдыкадыров, `nurlan.ort@example.com`), because the first one had used the exam's only attempt. Phone images are now 375 px wide, except `student-24-result-ort-phone-ky` (399 px: review row label in `ReviewItemCard`, an older issue that the header overflow used to hide) and `ort-teacher-14-question-editor-comparison-phone-ru` (511 px: question editor tab row, not re-shot).
Round 2 re-shoot (branch `phase-6/s8-uxfix2`, scratch backend 8018 / frontend 3018): `invite-07`, `invite-08` (+ new phone shot), new `invite-09`, `admin-02-org-detail-{admins,teachers,templates,log}`, new `admin-02b`/`admin-02c` (template grant confirm / revoke reason dialog), `admin-03`, `admin-04`, new `admin-06-audit-log`, `orgadmin-03`, `orgadmin-04`, `orgadmin-09` (now as the org admin Гульнара, added as org admin of Центр «Билим»), `student-04`, `student-24`/`student-25`, `teacher-04`, `ort-teacher-14`, and `ort-review-before-phone-ky` (399 px) / `ort-review-after-phone-ky` (375 px). Measured `document.documentElement.scrollWidth` = 375 at 375 px on every re-shot phone screen.
Name: `<area>-<nn>-<screen>-<viewport>-<lang>.jpg`; ORT player names (`student-14` ... `student-25`) match the pre-6a audit in `../audit/` so they can be compared side by side.

Setup: scratch SQLite backend (port 8015, `env -i`, `LMS_STORAGE_DRIVER=db`, `ORT_SEED_SAMPLES=false`, console email) and a production build of the frontend (port 3015) from an rsync'd copy. Data: platform admin Бакыт Осмонов (ORT owner); org «Школа №1» with org admin Гульнара Токтогулова (invited by the platform admin), teachers Айгуль Садыкова (new account through `/invite/{token}`) and Эрлан Мамытов (existing account through the invite page); course «Биология 9 класс» (owner Эрлан, created by the org admin in the UI) with student Нурлан Абдыкадыров; «Математика 7 класс» (owner Айгуль); org «Центр «Билим»» (suspended during the run); independent teacher Тимур Иманалиев (approved request, personal org); Мээрим Жумабаева has a pending teacher invitation. ORT (Russian): CSV + zip imported and an `ort_main` exam built and published in the UI, taken and submitted by Нурлан.

Placeholders: `{ORU}` ORT (Russian) course, `{org}` Школа №1, `{org2}` Центр «Билим», `{course}` Биология 9 класс, `{exam}` ORT exam, `{a}` general assessment, `{attempt}`, `{token}`, `{user}`, `{q}` comparison question, `{passage}`.

| File | Screen | Route | Viewport | Lang | Role |
|---|---|---|---|---|---|
| admin-01-organizations-desktop-ru.jpg | Organizations list (one suspended) | `/ru/admin/organizations` | 1440x900 | ru | platform admin |
| admin-01-organizations-phone-ru.jpg | Organizations list (one suspended) | `/ru/admin/organizations` | 375x812 | ru | platform admin |
| admin-01b-create-org-dialog-desktop-ru.jpg | Create organization dialog (slug auto) | `/ru/admin/organizations` | 1440x900 | ru | platform admin |
| admin-02-org-detail-admins-desktop-ru.jpg | Organization detail, tab Администраторы (Школа №1) | `/ru/admin/organizations/{org}` | 1440x900 | ru | platform admin |
| admin-02-org-detail-admins-phone-ru.jpg | Organization detail, tab Администраторы (Школа №1) | `/ru/admin/organizations/{org}` | 375x812 | ru | platform admin |
| admin-02-org-detail-courses-desktop-ru.jpg | Organization detail, tab Курсы (Школа №1) | `/ru/admin/organizations/{org}` | 1440x900 | ru | platform admin |
| admin-02-org-detail-courses-phone-ru.jpg | Organization detail, tab Курсы (Школа №1) | `/ru/admin/organizations/{org}` | 375x812 | ru | platform admin |
| admin-02-org-detail-log-after-suspend-desktop-ru.jpg | Organization log tab after suspend (Центр «Билим») | `/ru/admin/organizations/{org2}` | 1440x900 | ru | platform admin |
| admin-02-org-detail-log-desktop-ru.jpg | Organization detail, tab Журнал (Школа №1) | `/ru/admin/organizations/{org}` | 1440x900 | ru | platform admin |
| admin-02-org-detail-log-phone-ru.jpg | Organization detail, tab Журнал (Школа №1) | `/ru/admin/organizations/{org}` | 375x812 | ru | platform admin |
| admin-02-org-detail-summary-desktop-ru.jpg | Organization detail, tab Сводка (Школа №1) | `/ru/admin/organizations/{org}` | 1440x900 | ru | platform admin |
| admin-02-org-detail-summary-phone-ru.jpg | Organization detail, tab Сводка (Школа №1) | `/ru/admin/organizations/{org}` | 375x812 | ru | platform admin |
| admin-02-org-detail-teachers-desktop-ru.jpg | Organization detail, tab Преподаватели (Школа №1) | `/ru/admin/organizations/{org}` | 1440x900 | ru | platform admin |
| admin-02-org-detail-teachers-phone-ru.jpg | Organization detail, tab Преподаватели (Школа №1) | `/ru/admin/organizations/{org}` | 375x812 | ru | platform admin |
| admin-02-org-detail-templates-desktop-ru.jpg | Organization detail, tab Шаблоны (Школа №1) | `/ru/admin/organizations/{org}` | 1440x900 | ru | platform admin |
| admin-02-org-detail-templates-phone-ru.jpg | Organization detail, tab Шаблоны (Школа №1) | `/ru/admin/organizations/{org}` | 375x812 | ru | platform admin |
| admin-02-org-detail-usage-desktop-ru.jpg | Organization detail, tab Использование (Школа №1) | `/ru/admin/organizations/{org}` | 1440x900 | ru | platform admin |
| admin-02-org-detail-usage-phone-ru.jpg | Organization detail, tab Использование (Школа №1) | `/ru/admin/organizations/{org}` | 375x812 | ru | platform admin |
| admin-03-suspend-dialog-desktop-ru.jpg | Suspend organization dialog (reason, effect named) | `/ru/admin/organizations/{org2}` | 1440x900 | ru | platform admin |
| admin-03-suspend-dialog-phone-ru.jpg | Suspend organization dialog (reason, effect named) | `/ru/admin/organizations/{org2}` | 375x812 | ru | platform admin |
| admin-03b-org-suspended-desktop-ru.jpg | Organization detail after suspending | `/ru/admin/organizations/{org2}` | 1440x900 | ru | platform admin |
| admin-04-user-detail-orgs-desktop-ru.jpg | Admin user detail with 'Organizations and roles' (Эрлан Мамытов) | `/ru/admin/users/{user}` | 1440x900 | ru | platform admin |
| admin-04-user-detail-orgs-phone-ru.jpg | Admin user detail with 'Organizations and roles' (Эрлан Мамытов) | `/ru/admin/users/{user}` | 375x812 | ru | platform admin |
| admin-05-course-transfer-picker-desktop-ru.jpg | Admin course detail: ownership transfer with UserPicker open | `/ru/admin/courses/{course}` | 1440x900 | ru | platform admin |
| admin-05-course-transfer-picker-phone-ru.jpg | Admin course detail: ownership transfer with UserPicker open | `/ru/admin/courses/{course}` | 375x812 | ru | platform admin |
| admin-05b-course-transfer-confirm-desktop-ru.jpg | Transfer confirmation dialog | `/ru/admin/courses/{course}` | 1440x900 | ru | platform admin |
| header-indie-teacher-desktop-ru.jpg | Header: indie-teacher (viewport of /ru/courses) | `/ru/courses` | 1440x900 | ru | indie-teacher |
| header-indie-teacher-phone-ru.jpg | Header: indie-teacher (viewport of /ru/courses) | `/ru/courses` | 375x812 | ru | indie-teacher |
| header-orgadmin-desktop-ru.jpg | Header: orgadmin (viewport of /ru/courses) | `/ru/courses` | 1440x900 | ru | orgadmin |
| header-orgadmin-phone-ru.jpg | Header: orgadmin (viewport of /ru/courses) | `/ru/courses` | 375x812 | ru | orgadmin |
| header-platformadmin-desktop-ru.jpg | Header: platformadmin (viewport of /ru/courses) | `/ru/courses` | 1440x900 | ru | platformadmin |
| header-platformadmin-phone-ru.jpg | Header: platformadmin (viewport of /ru/courses) | `/ru/courses` | 375x812 | ru | platformadmin |
| header-student-desktop-en.jpg | Header: student (viewport) | `/en/courses` | 1440x900 | en | student |
| header-student-desktop-ky.jpg | Header: student (viewport) | `/ky/courses` | 1440x900 | ky | student |
| header-student-desktop-ru.jpg | Header: student (viewport) | `/ru/courses` | 1440x900 | ru | student |
| header-student-phone-en.jpg | Header: student (viewport) | `/en/courses` | 375x812 | en | student |
| header-student-phone-ky.jpg | Header: student (viewport) | `/ky/courses` | 375x812 | ky | student |
| header-student-phone-ru.jpg | Header: student (viewport) | `/ru/courses` | 375x812 | ru | student |
| header-teacher-desktop-ru.jpg | Header: teacher (viewport of /ru/courses) | `/ru/courses` | 1440x900 | ru | teacher |
| header-teacher-phone-ru.jpg | Header: teacher (viewport of /ru/courses) | `/ru/courses` | 375x812 | ru | teacher |
| invite-01-logged-out-desktop-en.jpg | Invite accept page, logged out (login / create account) | `/en/invite/{token}` | 1440x900 | en | anonymous |
| invite-01-logged-out-desktop-ky.jpg | Invite accept page, logged out (login / create account) | `/ky/invite/{token}` | 1440x900 | ky | anonymous |
| invite-01-logged-out-desktop-ru.jpg | Invite accept page, logged out (login / create account) | `/ru/invite/{token}` | 1440x900 | ru | anonymous |
| invite-01-logged-out-phone-en.jpg | Invite accept page, logged out (login / create account) | `/en/invite/{token}` | 375x812 | en | anonymous |
| invite-01-logged-out-phone-ky.jpg | Invite accept page, logged out (login / create account) | `/ky/invite/{token}` | 375x812 | ky | anonymous |
| invite-01-logged-out-phone-ru.jpg | Invite accept page, logged out (login / create account) | `/ru/invite/{token}` | 375x812 | ru | anonymous |
| invite-02-logged-in-accepting-desktop-en.jpg | Invite accept page, logged in with the invited email (accepting) | `/en/invite/{token}` | 1440x900 | en | existing user |
| invite-02-logged-in-accepting-desktop-ky.jpg | Invite accept page, logged in with the invited email (accepting) | `/ky/invite/{token}` | 1440x900 | ky | existing user |
| invite-02-logged-in-accepting-desktop-ru.jpg | Invite accept page, logged in with the invited email (accepting) | `/ru/invite/{token}` | 1440x900 | ru | existing user |
| invite-02-logged-in-accepting-phone-en.jpg | Invite accept page, logged in with the invited email (accepting) | `/en/invite/{token}` | 375x812 | en | existing user |
| invite-02-logged-in-accepting-phone-ky.jpg | Invite accept page, logged in with the invited email (accepting) | `/ky/invite/{token}` | 375x812 | ky | existing user |
| invite-02-logged-in-accepting-phone-ru.jpg | Invite accept page, logged in with the invited email (accepting) | `/ru/invite/{token}` | 375x812 | ru | existing user |
| invite-03-mismatch-desktop-en.jpg | Invite accept page, logged in with a different email (mismatch) | `/en/invite/{token}` | 1440x900 | en | student |
| invite-03-mismatch-desktop-ky.jpg | Invite accept page, logged in with a different email (mismatch) | `/ky/invite/{token}` | 1440x900 | ky | student |
| invite-03-mismatch-desktop-ru.jpg | Invite accept page, logged in with a different email (mismatch) | `/ru/invite/{token}` | 1440x900 | ru | student |
| invite-03-mismatch-phone-en.jpg | Invite accept page, logged in with a different email (mismatch) | `/en/invite/{token}` | 375x812 | en | student |
| invite-03-mismatch-phone-ky.jpg | Invite accept page, logged in with a different email (mismatch) | `/ky/invite/{token}` | 375x812 | ky | student |
| invite-03-mismatch-phone-ru.jpg | Invite accept page, logged in with a different email (mismatch) | `/ru/invite/{token}` | 375x812 | ru | student |
| invite-04-unknown-expired-desktop-en.jpg | Invite accept page, unknown/expired/revoked token (one shape) | `/en/invite/{token}` | 1440x900 | en | anonymous |
| invite-04-unknown-expired-desktop-ky.jpg | Invite accept page, unknown/expired/revoked token (one shape) | `/ky/invite/{token}` | 1440x900 | ky | anonymous |
| invite-04-unknown-expired-desktop-ru.jpg | Invite accept page, unknown/expired/revoked token (one shape) | `/ru/invite/{token}` | 1440x900 | ru | anonymous |
| invite-04-unknown-expired-phone-en.jpg | Invite accept page, unknown/expired/revoked token (one shape) | `/en/invite/{token}` | 375x812 | en | anonymous |
| invite-04-unknown-expired-phone-ky.jpg | Invite accept page, unknown/expired/revoked token (one shape) | `/ky/invite/{token}` | 375x812 | ky | anonymous |
| invite-04-unknown-expired-phone-ru.jpg | Invite accept page, unknown/expired/revoked token (one shape) | `/ru/invite/{token}` | 375x812 | ru | anonymous |
| invite-05-register-from-invite-desktop-ru.jpg | Register page opened from an invitation (redirect back) | `/ru/register?redirect=%2Fru%2Finvite%2F{token}` | 1440x900 | ru | anonymous |
| invite-06-register-code-desktop-ru.jpg | Register from invitation: email code step | `/ru/register?redirect=%2Fru%2Finvite%2F{token}` | 1440x900 | ru | anonymous |
| invite-07-after-accept-new-account-desktop-ru.jpg | Landing after accepting as a new account | `/ru/courses` | 1440x900 | ru | teacher (new) |
| invite-08-after-accept-existing-desktop-ru.jpg | Landing after accepting with an existing account | `/ru/courses` | 1440x900 | ru | teacher (existing) |
| orgadmin-01-overview-desktop-ru.jpg | Org admin overview (tiles, pending invitations) | `/ru/org/{org}` | 1440x900 | ru | org admin |
| orgadmin-01-overview-phone-ru.jpg | Org admin overview (tiles, pending invitations) | `/ru/org/{org}` | 375x812 | ru | org admin |
| orgadmin-02-teachers-desktop-ru.jpg | Org teachers + invitations | `/ru/org/{org}/teachers` | 1440x900 | ru | org admin |
| orgadmin-02-teachers-phone-ru.jpg | Org teachers + invitations | `/ru/org/{org}/teachers` | 375x812 | ru | org admin |
| orgadmin-03-invite-dialog-desktop-ru.jpg | Invite teacher dialog | `/ru/org/{org}/teachers` | 1440x900 | ru | org admin |
| orgadmin-03-invite-dialog-phone-ru.jpg | Invite teacher dialog | `/ru/org/{org}/teachers` | 375x812 | ru | org admin |
| orgadmin-03b-invite-dialog-filled-desktop-ru.jpg | Invite teacher dialog, filled | `/ru/org/{org}/teachers` | 1440x900 | ru | org admin |
| orgadmin-03c-invite-sent-desktop-ru.jpg | Teachers page after sending an invitation | `/ru/org/{org}/teachers` | 1440x900 | ru | org admin |
| orgadmin-04-remove-dialog-desktop-ru.jpg | Remove teacher dialog | `/ru/org/{org}/teachers` | 1440x900 | ru | org admin |
| orgadmin-04-remove-dialog-phone-ru.jpg | Remove teacher dialog | `/ru/org/{org}/teachers` | 375x812 | ru | org admin |
| orgadmin-05-courses-desktop-ru.jpg | Org courses | `/ru/org/{org}/courses` | 1440x900 | ru | org admin |
| orgadmin-05-courses-phone-ru.jpg | Org courses | `/ru/org/{org}/courses` | 375x812 | ru | org admin |
| orgadmin-06-create-course-desktop-ru.jpg | Create course page (org admin) | `/ru/org/{org}/courses/new` | 1440x900 | ru | org admin |
| orgadmin-06-create-course-phone-ru.jpg | Create course page (org admin) | `/ru/org/{org}/courses/new` | 375x812 | ru | org admin |
| orgadmin-06b-create-course-filled-desktop-ru.jpg | Create course page, filled (owner picked) | `/ru/org/{org}/courses/new` | 1440x900 | ru | org admin |
| orgadmin-07-course-summary-desktop-ru.jpg | Org course summary (staff, assign owner, open, join as teacher) | `/ru/org/{org}/courses/{course}` | 1440x900 | ru | org admin |
| orgadmin-07-course-summary-phone-ru.jpg | Org course summary (staff, assign owner, open, join as teacher) | `/ru/org/{org}/courses/{course}` | 375x812 | ru | org admin |
| orgadmin-08-join-as-teacher-dialog-desktop-ru.jpg | Join as teacher confirmation | `/ru/org/{org}/courses/{course}` | 1440x900 | ru | org admin |
| orgadmin-08-join-as-teacher-dialog-phone-ru.jpg | Join as teacher confirmation | `/ru/org/{org}/courses/{course}` | 375x812 | ru | org admin |
| orgadmin-08b-after-join-as-teacher-desktop-ru.jpg | Course summary after joining as teacher | `/ru/org/{org}/courses/{course}` | 1440x900 | ru | org admin |
| orgadmin-09-suspended-banner-desktop-ru.jpg | Org area of a suspended organization (amber banner, writes disabled) | `/ru/org/{org2}` | 1440x900 | ru | org admin |
| orgadmin-09-suspended-banner-phone-ru.jpg | Org area of a suspended organization (amber banner, writes disabled) | `/ru/org/{org2}` | 375x812 | ru | org admin |
| ort-teacher-00-course-home-desktop-ru.jpg | ORT course home (staff) | `/ru/courses/{ORU}` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-00-course-home-phone-ru.jpg | ORT course home (staff) | `/ru/courses/{ORU}` | 375x812 | ru | platform admin (ORT owner) |
| ort-teacher-01-import-page-desktop-ru.jpg | ORT import page (format select present, default full_main) | `/ru/courses/{ORU}/bank/import` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-01-import-page-phone-ru.jpg | ORT import page (format select present) | `/ru/courses/{ORU}/bank/import` | 375x812 | ru | platform admin (ORT owner) |
| ort-teacher-02a-import-preview-desktop-ru.jpg | Import preview: CSV sample_ort_questions_ru.csv | `/ru/courses/{ORU}/bank/import` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-02b-import-done-desktop-ru.jpg | Import finished: CSV sample_ort_questions_ru.csv | `/ru/courses/{ORU}/bank/import` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-03a-import-preview-desktop-ru.jpg | Import preview: bundle zip tsoomo19.zip | `/ru/courses/{ORU}/bank/import` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-03b-import-done-desktop-ru.jpg | Import finished: bundle zip tsoomo19.zip | `/ru/courses/{ORU}/bank/import` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-04-bank-list-desktop-ru.jpg | ORT bank list after both imports | `/ru/courses/{ORU}/bank` | 1440x900 | ru | platform admin |
| ort-teacher-04-bank-list-phone-ru.jpg | ORT bank list after both imports | `/ru/courses/{ORU}/bank` | 375x812 | ru | platform admin |
| ort-teacher-05-create-assessment-dialog-desktop-ru.jpg | ORT course: create assessment dialog with ORT presets | `/ru/courses/{ORU}/assessments` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-05-create-assessment-dialog-phone-ru.jpg | ORT course: create assessment dialog with ORT presets | `/ru/courses/{ORU}/assessments` | 375x812 | ru | platform admin (ORT owner) |
| ort-teacher-05b-assessments-list-desktop-ru.jpg | ORT course assessments list | `/ru/courses/{ORU}/assessments` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-05b-assessments-list-phone-ru.jpg | ORT course assessments list | `/ru/courses/{ORU}/assessments` | 375x812 | ru | platform admin (ORT owner) |
| ort-teacher-06-builder-empty-desktop-ru.jpg | ORT exam builder after creation (five sections) | `/ru/courses/{ORU}/assessments/{exam}/edit` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-07-add-questions-dialog-desktop-ru.jpg | ORT builder: add questions dialog (bank tsoomo19, section math_1) | `/ru/courses/{ORU}/assessments/{exam}/edit` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-08-builder-filled-desktop-ru.jpg | ORT exam builder with items (locked section controls greyed) | `/ru/courses/{ORU}/assessments/{exam}/edit` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-08-builder-filled-phone-ru.jpg | ORT exam builder with items (locked section controls greyed) | `/ru/courses/{ORU}/assessments/{exam}/edit` | 375x812 | ru | platform admin (ORT owner) |
| ort-teacher-09-builder-settings-locked-desktop-ru.jpg | ORT builder settings open: navigation, grading scheme, sections locked with 'Задано шаблоном ОРТ' | `/ru/courses/{ORU}/assessments/{exam}/edit` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-09-builder-settings-locked-phone-ru.jpg | ORT builder settings open: navigation, grading scheme, sections locked with 'Задано шаблоном ОРТ' | `/ru/courses/{ORU}/assessments/{exam}/edit` | 375x812 | ru | platform admin (ORT owner) |
| ort-teacher-10-validate-desktop-ru.jpg | ORT builder: validation result | `/ru/courses/{ORU}/assessments/{exam}/edit` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-12-published-desktop-ru.jpg | ORT exam after publishing | `/ru/courses/{ORU}/assessments/{exam}/edit` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-13-course-settings-desktop-ru.jpg | ORT course settings (template locked) | `/ru/courses/{ORU}/settings` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-13-course-settings-phone-ru.jpg | ORT course settings (template locked) | `/ru/courses/{ORU}/settings` | 375x812 | ru | platform admin (ORT owner) |
| ort-teacher-14-question-editor-comparison-desktop-ru.jpg | ORT question editor (comparison) | `/ru/courses/{ORU}/bank/q/{q}` | 1440x900 | ru | platform admin (ORT owner) |
| ort-teacher-14-question-editor-comparison-phone-ru.jpg | ORT question editor (comparison) | `/ru/courses/{ORU}/bank/q/{q}` | 375x812 | ru | platform admin (ORT owner) |
| ort-teacher-15-question-saved-desktop-ru.jpg | ORT question editor after saving an edit | `/ru/courses/{ORU}/bank/q/{q}` | 1440x900 | ru | platform admin (ORT owner) |
| public-01-login-desktop-en.jpg | Login (neutral texts, brand placeholder) | `/en/login` | 1440x900 | en | anonymous |
| public-01-login-desktop-ky.jpg | Login (neutral texts, brand placeholder) | `/ky/login` | 1440x900 | ky | anonymous |
| public-01-login-desktop-ru.jpg | Login (neutral texts, brand placeholder) | `/ru/login` | 1440x900 | ru | anonymous |
| public-01-login-phone-en.jpg | Login (neutral texts, brand placeholder) | `/en/login` | 375x812 | en | anonymous |
| public-01-login-phone-ky.jpg | Login (neutral texts, brand placeholder) | `/ky/login` | 375x812 | ky | anonymous |
| public-01-login-phone-ru.jpg | Login (neutral texts, brand placeholder) | `/ru/login` | 375x812 | ru | anonymous |
| public-02-register-desktop-en.jpg | Register (neutral texts, brand placeholder) | `/en/register` | 1440x900 | en | anonymous |
| public-02-register-desktop-ky.jpg | Register (neutral texts, brand placeholder) | `/ky/register` | 1440x900 | ky | anonymous |
| public-02-register-desktop-ru.jpg | Register (neutral texts, brand placeholder) | `/ru/register` | 1440x900 | ru | anonymous |
| public-02-register-phone-en.jpg | Register (neutral texts, brand placeholder) | `/en/register` | 375x812 | en | anonymous |
| public-02-register-phone-ky.jpg | Register (neutral texts, brand placeholder) | `/ky/register` | 375x812 | ky | anonymous |
| public-02-register-phone-ru.jpg | Register (neutral texts, brand placeholder) | `/ru/register` | 375x812 | ru | anonymous |
| public-03-forgot-password-desktop-en.jpg | Forgot password (neutral texts, brand placeholder) | `/en/forgot-password` | 1440x900 | en | anonymous |
| public-03-forgot-password-desktop-ky.jpg | Forgot password (neutral texts, brand placeholder) | `/ky/forgot-password` | 1440x900 | ky | anonymous |
| public-03-forgot-password-desktop-ru.jpg | Forgot password (neutral texts, brand placeholder) | `/ru/forgot-password` | 1440x900 | ru | anonymous |
| public-03-forgot-password-phone-en.jpg | Forgot password (neutral texts, brand placeholder) | `/en/forgot-password` | 375x812 | en | anonymous |
| public-03-forgot-password-phone-ky.jpg | Forgot password (neutral texts, brand placeholder) | `/ky/forgot-password` | 375x812 | ky | anonymous |
| public-03-forgot-password-phone-ru.jpg | Forgot password (neutral texts, brand placeholder) | `/ru/forgot-password` | 375x812 | ru | anonymous |
| student-01-my-courses-desktop-en.jpg | Student course list with header | `/en/courses` | 1440x900 | en | student |
| student-01-my-courses-desktop-ky.jpg | Student course list with header | `/ky/courses` | 1440x900 | ky | student |
| student-01-my-courses-desktop-ru.jpg | Student course list with header | `/ru/courses` | 1440x900 | ru | student |
| student-01-my-courses-phone-en.jpg | Student course list with header | `/en/courses` | 375x812 | en | student |
| student-01-my-courses-phone-ky.jpg | Student course list with header | `/ky/courses` | 375x812 | ky | student |
| student-01-my-courses-phone-ru.jpg | Student course list with header | `/ru/courses` | 375x812 | ru | student |
| student-02-teacher-access-desktop-en.jpg | /teacher-access (ask your administrator / apply) | `/en/teacher-access` | 1440x900 | en | student |
| student-02-teacher-access-desktop-ky.jpg | /teacher-access (ask your administrator / apply) | `/ky/teacher-access` | 1440x900 | ky | student |
| student-02-teacher-access-desktop-ru.jpg | /teacher-access (ask your administrator / apply) | `/ru/teacher-access` | 1440x900 | ru | student |
| student-02-teacher-access-phone-en.jpg | /teacher-access (ask your administrator / apply) | `/en/teacher-access` | 375x812 | en | student |
| student-02-teacher-access-phone-ky.jpg | /teacher-access (ask your administrator / apply) | `/ky/teacher-access` | 375x812 | ky | student |
| student-02-teacher-access-phone-ru.jpg | /teacher-access (ask your administrator / apply) | `/ru/teacher-access` | 375x812 | ru | student |
| student-03-grading-schemes-no-permission-desktop-en.jpg | Grading schemes as a student (no-permission state) | `/en/grading-schemes` | 1440x900 | en | student |
| student-03-grading-schemes-no-permission-desktop-ky.jpg | Grading schemes as a student (no-permission state) | `/ky/grading-schemes` | 1440x900 | ky | student |
| student-03-grading-schemes-no-permission-desktop-ru.jpg | Grading schemes as a student (no-permission state) | `/ru/grading-schemes` | 1440x900 | ru | student |
| student-03-grading-schemes-no-permission-phone-en.jpg | Grading schemes as a student (no-permission state) | `/en/grading-schemes` | 375x812 | en | student |
| student-03-grading-schemes-no-permission-phone-ky.jpg | Grading schemes as a student (no-permission state) | `/ky/grading-schemes` | 375x812 | ky | student |
| student-03-grading-schemes-no-permission-phone-ru.jpg | Grading schemes as a student (no-permission state) | `/ru/grading-schemes` | 375x812 | ru | student |
| student-04-pending-invitation-banner-desktop-en.jpg | Pending invitation banner after login | `/en/courses` | 1440x900 | en | student with pending invitation |
| student-04-pending-invitation-banner-desktop-ky.jpg | Pending invitation banner after login | `/ky/courses` | 1440x900 | ky | student with pending invitation |
| student-04-pending-invitation-banner-desktop-ru.jpg | Pending invitation banner after login | `/ru/courses` | 1440x900 | ru | student with pending invitation |
| student-04-pending-invitation-banner-phone-en.jpg | Pending invitation banner after login | `/en/courses` | 375x812 | en | student with pending invitation |
| student-04-pending-invitation-banner-phone-ky.jpg | Pending invitation banner after login | `/ky/courses` | 375x812 | ky | student with pending invitation |
| student-04-pending-invitation-banner-phone-ru.jpg | Pending invitation banner after login | `/ru/courses` | 375x812 | ru | student with pending invitation |
| student-04b-pending-invitation-open-desktop-ru.jpg | After clicking 'Посмотреть приглашения' | `/ru/teacher-access` | 1440x900 | ru | student with pending invitation |
| student-05-general-lobby-desktop-ru.jpg | General assessment lobby | `/ru/courses/{course}/assessments/{a}` | 1440x900 | ru | student |
| student-06-general-player-plain-passage-desktop-en.jpg | General player: question with a plain passage | `/en/courses/{course}/attempts/{attempt}` | 1440x900 | en | student |
| student-06-general-player-plain-passage-desktop-ky.jpg | General player: question with a plain passage | `/ky/courses/{course}/attempts/{attempt}` | 1440x900 | ky | student |
| student-06-general-player-plain-passage-desktop-ru.jpg | General player: question with a plain passage | `/ru/courses/{course}/attempts/{attempt}` | 1440x900 | ru | student |
| student-06-general-player-plain-passage-phone-en.jpg | General player: question with a plain passage | `/en/courses/{course}/attempts/{attempt}` | 375x812 | en | student |
| student-06-general-player-plain-passage-phone-ky.jpg | General player: question with a plain passage | `/ky/courses/{course}/attempts/{attempt}` | 375x812 | ky | student |
| student-06-general-player-plain-passage-phone-ru.jpg | General player: question with a plain passage | `/ru/courses/{course}/attempts/{attempt}` | 375x812 | ru | student |
| student-14-lobby-ort-desktop-ky.jpg | ORT exam lobby | `/ky/courses/{ORU}/assessments/{exam}` | 1440x900 | ky | student |
| student-14-lobby-ort-desktop-ru.jpg | ORT exam lobby | `/ru/courses/{ORU}/assessments/{exam}` | 1440x900 | ru | student |
| student-14-lobby-ort-phone-ky.jpg | ORT exam lobby | `/ky/courses/{ORU}/assessments/{exam}` | 375x812 | ky | student |
| student-14-lobby-ort-phone-ru.jpg | ORT exam lobby | `/ru/courses/{ORU}/assessments/{exam}` | 375x812 | ru | student |
| student-15-player-comparison-desktop-ky.jpg | ORT player: math_1 comparison question (Column A / B) | `/ky/courses/{ORU}/attempts/{attempt}` | 1440x900 | ky | student |
| student-15-player-comparison-desktop-ru.jpg | ORT player: math_1 comparison question (Column A / B) | `/ru/courses/{ORU}/attempts/{attempt}` | 1440x900 | ru | student |
| student-15-player-comparison-phone-ky.jpg | ORT player: math_1 comparison question (Column A / B) | `/ky/courses/{ORU}/attempts/{attempt}` | 375x812 | ky | student |
| student-15-player-comparison-phone-ru.jpg | ORT player: math_1 comparison question (Column A / B) | `/ru/courses/{ORU}/attempts/{attempt}` | 375x812 | ru | student |
| student-16-player-flagged-desktop-ky.jpg | ORT player: flagged question 3, palette states | `/ky/courses/{ORU}/attempts/{attempt}` | 1440x900 | ky | student |
| student-16-player-flagged-desktop-ru.jpg | ORT player: answered + flagged question, palette states | `/ru/courses/{ORU}/attempts/{attempt}` | 1440x900 | ru | student |
| student-16-player-flagged-phone-ky.jpg | ORT player: flagged question 3, palette states | `/ky/courses/{ORU}/attempts/{attempt}` | 375x812 | ky | student |
| student-16-player-flagged-phone-ru.jpg | ORT player: flagged question 3, palette states | `/ru/courses/{ORU}/attempts/{attempt}` | 375x812 | ru | student |
| student-17-player-palette-phone-ky.jpg | ORT player on phone: question palette (viewport scrolled to it) | `/ky/courses/{ORU}/attempts/{attempt}` | 375x812 | ky | student |
| student-17-player-palette-phone-ru.jpg | ORT player on phone: question palette (viewport scrolled to it) | `/ru/courses/{ORU}/attempts/{attempt}` | 375x812 | ru | student |
| student-18-section-end-dialog-desktop-ky.jpg | Finish-section confirmation (forward-only) | `/ky/courses/{ORU}/attempts/{attempt}` | 1440x900 | ky | student |
| student-18-section-end-dialog-desktop-ru.jpg | Finish-section confirmation (forward-only) | `/ru/courses/{ORU}/attempts/{attempt}` | 1440x900 | ru | student |
| student-18-section-end-dialog-phone-ky.jpg | Finish-section confirmation (forward-only) | `/ky/courses/{ORU}/attempts/{attempt}` | 375x812 | ky | student |
| student-18-section-end-dialog-phone-ru.jpg | Finish-section confirmation (forward-only) | `/ru/courses/{ORU}/attempts/{attempt}` | 375x812 | ru | student |
| student-21-player-passage-desktop-ky.jpg | ORT player: reading question with its numbered passage | `/ky/courses/{ORU}/attempts/{attempt}` | 1440x900 | ky | student |
| student-21-player-passage-desktop-ru.jpg | ORT player: reading question with its numbered passage | `/ru/courses/{ORU}/attempts/{attempt}` | 1440x900 | ru | student |
| student-21-player-passage-phone-ky.jpg | ORT player: reading question with its numbered passage | `/ky/courses/{ORU}/attempts/{attempt}` | 375x812 | ky | student |
| student-21-player-passage-phone-ru.jpg | ORT player: reading question with its numbered passage | `/ru/courses/{ORU}/attempts/{attempt}` | 375x812 | ru | student |
| student-22-player-grammar-desktop-ru.jpg | ORT player: grammar (last) section | `/ru/courses/{ORU}/attempts/{attempt}` | 1440x900 | ru | student |
| student-23-submit-dialog-desktop-ky.jpg | Finish test confirmation dialog | `/ky/courses/{ORU}/attempts/{attempt}` | 1440x900 | ky | student |
| student-23-submit-dialog-desktop-ru.jpg | Finish test confirmation dialog | `/ru/courses/{ORU}/attempts/{attempt}` | 1440x900 | ru | student |
| student-23-submit-dialog-phone-ky.jpg | Finish test confirmation dialog | `/ky/courses/{ORU}/attempts/{attempt}` | 375x812 | ky | student |
| student-23-submit-dialog-phone-ru.jpg | Finish test confirmation dialog | `/ru/courses/{ORU}/attempts/{attempt}` | 375x812 | ru | student |
| student-24-result-ort-desktop-ky.jpg | ORT result: scaled score, sections, review below | `/ky/courses/{ORU}/attempts/{attempt}/result` | 1440x900 | ky | student |
| student-24-result-ort-desktop-ru.jpg | ORT result: scaled score, sections, review below | `/ru/courses/{ORU}/attempts/{attempt}/result` | 1440x900 | ru | student |
| student-24-result-ort-phone-ky.jpg | ORT result: scaled score, sections, review below | `/ky/courses/{ORU}/attempts/{attempt}/result` | 375x812 | ky | student |
| student-24-result-ort-phone-ru.jpg | ORT result: scaled score, sections, review below | `/ru/courses/{ORU}/attempts/{attempt}/result` | 375x812 | ru | student |
| student-25-review-ort-desktop-ky.jpg | ORT result: item review (viewport scrolled to the review list) | `/ky/courses/{ORU}/attempts/{attempt}/result` | 1440x900 | ky | student |
| student-25-review-ort-desktop-ru.jpg | ORT result: item review (viewport scrolled to the review list) | `/ru/courses/{ORU}/attempts/{attempt}/result` | 1440x900 | ru | student |
| student-25-review-ort-phone-ky.jpg | ORT result: item review (viewport scrolled to the review list) | `/ky/courses/{ORU}/attempts/{attempt}/result` | 375x812 | ky | student |
| student-25-review-ort-phone-ru.jpg | ORT result: item review (viewport scrolled to the review list) | `/ru/courses/{ORU}/attempts/{attempt}/result` | 375x812 | ru | student |
| teacher-01-general-course-home-desktop-ru.jpg | General course home (teacher) | `/ru/courses/{course}` | 1440x900 | ru | teacher (general course owner) |
| teacher-01-general-course-home-phone-ru.jpg | General course home (teacher) | `/ru/courses/{course}` | 375x812 | ru | teacher (general course owner) |
| teacher-02-general-create-assessment-dialog-desktop-ru.jpg | General course: create assessment dialog (no ORT options) | `/ru/courses/{course}/assessments` | 1440x900 | ru | teacher (general course owner) |
| teacher-02-general-create-assessment-dialog-phone-ru.jpg | General course: create assessment dialog (no ORT options) | `/ru/courses/{course}/assessments` | 375x812 | ru | teacher (general course owner) |
| teacher-03-general-import-panel-desktop-ru.jpg | General course: import panel (no format select) | `/ru/courses/{course}/bank/import` | 1440x900 | ru | teacher (general course owner) |
| teacher-03-general-import-panel-phone-ru.jpg | General course: import panel (no format select) | `/ru/courses/{course}/bank/import` | 375x812 | ru | teacher (general course owner) |
| teacher-04-general-passage-desktop-ru.jpg | General course: passage editor/preview (plain passage) | `/ru/courses/{course}/bank/p/{passage}` | 1440x900 | ru | teacher (general course owner) |
| teacher-04-general-passage-phone-ru.jpg | General course: passage editor/preview (plain passage) | `/ru/courses/{course}/bank/p/{passage}` | 375x812 | ru | teacher (general course owner) |
| teacher-05-grading-schemes-desktop-ru.jpg | Grading schemes as a teacher | `/ru/grading-schemes` | 1440x900 | ru | teacher (general course owner) |
| teacher-05-grading-schemes-phone-ru.jpg | Grading schemes as a teacher | `/ru/grading-schemes` | 375x812 | ru | teacher (general course owner) |
| admin-02b-template-grant-confirm-desktop-ru.jpg | Grant template: simple confirm naming the organization | `/ru/admin/organizations/{org}` | 1440x900 | ru | platform admin |
| admin-02b-template-grant-confirm-phone-ru.jpg | Grant template: simple confirm naming the organization | `/ru/admin/organizations/{org}` | 375x812 | ru | platform admin |
| admin-02c-template-revoke-reason-dialog-desktop-ru.jpg | Revoke template: reason dialog (organization and effect named) | `/ru/admin/organizations/{org}` | 1440x900 | ru | platform admin |
| admin-02c-template-revoke-reason-dialog-phone-ru.jpg | Revoke template: reason dialog (organization and effect named) | `/ru/admin/organizations/{org}` | 375x812 | ru | platform admin |
| admin-06-audit-log-desktop-ru.jpg | Platform audit log | `/ru/admin/audit-log` | 1440x900 | ru | platform admin |
| admin-06-audit-log-phone-ru.jpg | Platform audit log (stacked cards, details behind a tap) | `/ru/admin/audit-log` | 375x812 | ru | platform admin |
| invite-08-after-accept-existing-phone-ru.jpg | Landing after accepting with an existing account (confirmation shown once) | `/ru/courses` | 375x812 | ru | teacher (org) |
| invite-09-org-teacher-courses-desktop-ru.jpg | Org teacher's /courses after reload (no confirmation, Teaching tab) | `/ru/courses` | 1440x900 | ru | teacher (org) |
| ort-review-before-phone-ky.jpg | ORT result review before the ReviewItemCard wrap fix (399 px) | `/ky/courses/{ORU}/attempts/{attempt}/result` | 375x812 | ky | student |
| ort-review-after-phone-ky.jpg | ORT result review after the ReviewItemCard wrap fix (375 px) | `/ky/courses/{ORU}/attempts/{attempt}/result` | 375x812 | ky | student |
