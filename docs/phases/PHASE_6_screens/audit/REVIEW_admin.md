# UX audit: platform admin area (current app, branch `lms`, 2026-10-24)

Reviewed: `admin-01` … `admin-11` (desktop 1440 + phone 375, ru) against `docs/UX_GUIDELINES.md`; code in `frontend/src/app/[lang]/admin/**` and `frontend/src/components/lms/admin/**` (plus the shared `ConfirmDialog`, `Pager`, `LmsShell` they depend on).

Totals: 1 blocker, 8 major, 10 minor.

## What works well (keep)

- Every destructive action goes through `ReasonDialog` with a labelled, required reason; the reason then shows up in the audit log and in the user's request history. Good accountability loop.
- Pending-request badge in the side nav and on the overview card; filters on teacher requests are a proper `role="group"` with `aria-pressed`.
- Error and empty states exist on every list (`ErrorMessage` with Retry, dashed empty card). The roster notice "viewing the roster is written to the audit log" is honest and good.
- Storage page explains the R2 free-tier rule in plain words and has a level bar.

## Findings: platform admin (most severe first)

### B1. Blocker: ownership transfer needs a raw user ID that the UI never shows
- **Screen**: `admin-07-course-detail-*`, `admin-08-*` (`/ru/admin/courses/{id}`).
- **Problem**: the "Владение" card says "Вставьте его ID со страницы пользователей", but the users list and user detail show name and email only; the ID exists only in the URL bar. `courses/[courseId]/page.tsx:129-137`.
- **Why it hurts**: the owner cannot complete the transfer from the UI as designed; copying a URL fragment is error-prone and the confirm dialog (`:171-175`, no `body`) does not even echo who the new owner is.
- **Fix**: replace the input with a `UserPicker` (combobox calling `listUsers({ q, teacher_status: "approved" })`, excluding disabled users and the current owner), and give the transfer dialog a body: "Курс «{course}» перейдёт от {old} к {new}." Also show the user ID as a copyable meta line on user detail for support cases.

### M1. Major: on a phone, ~45 % of the first screen is navigation, and the admin sub-nav is cut off
- **Screen**: every `admin-*-phone-ru.jpg`.
- **Problem**: the global header wraps into 5 rows (7 links + account + languages), then the admin nav is a horizontal strip whose third item is cut ("Поль…") with no fade or scroll hint. The page title starts at y≈390 of 812. `LmsShell.tsx:78-99` (`flex-wrap`), `AdminShell.tsx:48` (`overflow-x-auto`, no affordance).
- **Why it hurts**: the owner on a phone scrolls past two menus before any content; a hidden nav item is a "hidden feature" (§4).
- **Fix**: below `md`, collapse the global nav into a menu button (drawer); in `AdminShell` render the section list as a `Select` labelled "Раздел" or a snap-scrolling tab bar with an edge fade and `scrollIntoView` on the active item. Same shell should serve the org admin area (see proposal).

### M2. Major: users table on a phone hides the account badges and the action column
- **Screen**: `admin-03-users-phone-ru.jpg`.
- **Problem**: only "Пользователь" and "Статус преподавателя" fit; "Аккаунт", "Создан" and "Заблокировать" are off-screen in a scroll container with no hint. No count, no sort. `users/page.tsx:102-140`.
- **Why it hurts**: the admin cannot see who is blocked or an admin without sideways scrolling; §3 says tables become cards or keep 2–3 key columns with details behind a tap.
- **Fix**: a `Table` component with a card renderer below `md` (name + email, badges row, created date, link to detail). Move the row-level "Заблокировать" to the detail page (keep the list calm: eight red buttons on one screen today). Show "{n} пользователей" above the table; add sort by created/name.

### M3. Major: the audit log speaks in IDs and JSON
- **Screen**: `admin-09-audit-log-*`.
- **Problem**: "Объект" shows `teacher_request 9fd29d22-…`, "Детали" shows `{"user_id":"usr_07…","from":"pending","to":"approved"}`; filter "Действие" is free text with placeholder `course.delete`, "ID исполнителя" requires a raw ID. On a phone only three columns are visible. `AuditTable.tsx:38-40`, `audit-log/page.tsx:46-50`.
- **Why it hurts**: the one person who reads this cannot tell which teacher or course it was about without cross-referencing IDs; a free-text action filter needs memorising internal keys.
- **Fix**: backend returns `target_label` (display name / course title) and the table links it to `/admin/users/{id}` or `/admin/courses/{id}`; render `details` as a small key/value list with translated keys (`from → to` as "На рассмотрении → Подтверждён"). Filters: `Select` of actions from the `platformAdmin.auditActions.*` dictionary, actor via `UserPicker`, plus a date range. Phone: card per entry (when, who, action, object).

### M4. Major: delete / hide / restore dialogs do not name the course or the effect
- **Screen**: `admin-07`, `admin-08` (dialogs not shot; code).
- **Problem**: `ReasonDialog` gets a title only (`courses/[courseId]/page.tsx:171-175`); the delete dialog for the ORT (Russian) course looks exactly like the one for an empty draft.
- **Why it hurts**: §4 requires confirmations that name the object and the effect; a mis-click here can remove a course with active students.
- **Fix**: pass `body` per action: delete "Курс «{title}» ({n} учеников) попадёт в корзину; ученики потеряют доступ." / unlist "Курс исчезнет из каталога; текущие ученики сохраняют доступ." / restore. For platform-owned ORT courses show a warning badge and require typing the course name.

### M5. Major: the ORT system account looks like an ordinary user that can be unblocked or stripped of teacher rights
- **Screen**: `admin-03-users-*` (row "ORT, ort-demo@platform.invalid", "Подтверждён" + "Заблокирован" + "Разблокировать"), `admin-08` owner link "ORT".
- **Problem**: `users/page.tsx:115` only protects self and platform admins. One click enables login for a system account with an unusable hash; "Отозвать доступ преподавателя" on its detail would orphan the ORT courses.
- **Why it hurts**: data-integrity risk on the platform's flagship courses; the state combination "approved teacher + blocked" is confusing to read.
- **Fix**: mark system users (`is_system` or by the `platform.invalid` domain) with a "Системный аккаунт" badge, hide enable/disable/revoke for them, and show "Платформа" instead of "ORT" as the owner on course rows and cards (`admin-11` "Учитель: ORT").

### M6. Major: dialogs do not trap or return focus
- **Screen**: all admin pages (code).
- **Problem**: `ConfirmDialog.tsx:34-43` focuses Cancel and handles Esc but Tab leaves the dialog into the page behind, and focus is not returned to the button that opened it.
- **Why it hurts**: §5 accessibility basics; keyboard users lose their place after every confirm.
- **Fix**: render through a native `<dialog>` with `showModal()` (free focus trap + Esc) or add a small trap, and restore `document.activeElement` on close. This becomes the design-system `Dialog`.

### M7. Major: teacher-request card shows "На рассмотрении" twice
- **Screen**: `admin-02-teacher-requests-*`.
- **Problem**: `teacher-requests/page.tsx:105-106` renders the user's teacher status badge and the request status badge; for a pending request they are the same words.
- **Why it hurts**: looks like a bug, hides the one case where the two differ (request approved, teacher later revoked).
- **Fix**: show only the request status; show the teacher-status badge only when it differs from what the request implies (e.g. "Доступ отозван"), with a prefix "Сейчас:".

### M8. Major: a bare "Нет" badge on user detail
- **Screen**: `admin-04-user-detail-student-*`.
- **Problem**: the card opens with a grey badge "Нет" with no label (`users/[userId]/page.tsx:77`); it is the teacher-status value without its column header.
- **Fix**: render a labelled description row "Преподаватель: нет" or a "Ученик" badge; keep badges only for pending/approved/revoked/admin/blocked.

### Minor (platform admin)
- m1. Courses list: "Пометки" column is empty for every row (`courses/page.tsx:70`); no "kind" (platform ORT vs teacher course), no link to open the course as it looks to teachers. Add "Открыть курс" on course detail.
- m2. Roster shows the raw enrollment `state` ("active") (`courses/[courseId]/page.tsx:161`); translate via `courses.enrollmentState.*`.
- m3. Overview duplicates the nav as four cards with one number; add a storage tile (level + used GB) and pending counts for each section so it reads as a dashboard (`admin/page.tsx:22-30`).
- m4. "Активные записи: 2" is jargon; say "Записан на курсов: 2".
- m5. Loading is bare "Загрузка…" text everywhere; no success feedback after Approve/Block (the card just disappears from the "pending" filter). Use `Skeleton` rows and a `Toast` ("Заявка одобрена").
- m6. Three different selected-state styles on one screen: side-nav pill, filter pill and "Мои курсы" underline tabs; filled green Approve while the primary colour is brand blue. One `Tabs` + `Button` primary.
- m7. Native unstyled checkbox and select (`users/page.tsx:86-92`); replace with `Checkbox`/`Select`.
- m8. Search inputs have fixed `w-64` (`users/page.tsx:82`, `courses/page.tsx:49`); fine at 375 but use `w-full sm:w-64` so ky/ru placeholders never clip.
- m9. Storage page shows the raw driver value "db" and long uppercase labels that wrap to three lines on a phone; use sentence-case small labels, translate the driver.
- m10. Created/decided timestamps are UTC-naive strings rendered as local time (INDEX bug 2); fix the API serialisation (append `Z`/offset) before the audit log is trusted.

## Cross-cutting design-system issues

- **Colors**: green filled buttons (Approve), emerald/amber/red outlined buttons and brand-blue primaries coexist; define `Button` variants primary (brand), secondary (slate outline), danger (red), and a `warning` only as a Badge, not a button.
- **Type/spacing**: consistent (`text-2xl` title, `text-sm` body, `rounded-2xl` cards) but page titles sit on the page, not in a `PageHeader` with actions; phone body text in tables is 14 px (guideline: 16 px on a phone).
- **Components missing**: `Table` with mobile card mode + count + sort, `Dialog` with focus trap, `Tabs`, `Select`, `Checkbox`, `Skeleton`, `Toast`, `PageHeader`, `UserPicker` (combobox), `DescriptionList`, `StatTile`.
- **States**: loading is text only; no toast on success; list counts absent; "load more" without total.
- **i18n**: all strings are keyed; but ky/ru were not shot for admin (ru only, as allowed). The sub-nav strip will clip ky labels even more than ru.

## Proposal: Phase 6 admin areas

### Shell (shared by platform admin and org admin)
`AreaShell` generalises `AdminShell`: desktop = 224 px side nav + content; phone = `Select` "Раздел" (or snap tab bar with edge fade) under a compact header. The global header collapses to a menu button below `md` and shows an area switcher ("Мои курсы / Организация / Платформа") only for areas the person has (§1).

### Platform admin `/[lang]/admin`
| Page | Content | Reuse |
|---|---|---|
| Обзор | StatTiles: pending requests, organizations, teachers, courses, storage level; last 5 audit entries | overview + `AuditTable` compact |
| Организации (new) | Table: name, status badge (active/suspended), admins, teachers, courses, created; search; primary "Создать организацию" → Dialog (name, languages, contact email) | users table pattern |
| Организация `[orgId]` (new) | PageHeader: name, status, actions "Изменить", "Приостановить/Возобновить" (ReasonDialog naming the org and the effect: teachers cannot log in to courses). Tabs: **Сводка** (DescriptionList: counts, storage bytes, created) · **Админы** (table + "Назначить админа" via UserPicker, row "Снять" ReasonDialog) · **Преподаватели** (users table filtered by org, read-only, link to user) · **Курсы** (admin courses table filtered by org) · **Шаблоны** (list of course templates, e.g. ORT (ky), ORT (ru), each with a Switch "Доступен" + ConfirmDialog) · **Журнал** (AuditTable filtered by org) | existing tables, `UserPicker`, `Tabs` |
| Заявки преподавателей | as now, + organization column/filter; fix M7 | keep |
| Пользователи | as now, + organization column/filter, card mode on phone, actions moved to detail; system-account badge (M5) | keep |
| Пользователь `[userId]` | as now, + "Организация и роль" row and "Добавить в организацию" (Select org, role) | keep |
| Курсы | as now, + Organization and Kind columns, filters | keep |
| Курс `[courseId]` | as now, transfer via UserPicker (B1), dialog bodies (M4), "Открыть курс" | keep |
| Журнал действий | fix M3 (labels, links, selects, date range, phone cards) | keep |
| Хранилище | as now, + "По организациям" table (bytes, objects) | keep |

Phone: all tables in card mode; the primary action lives in `PageHeader` (top, full-width button); dialogs are `max-w-md` and already fit 375.

### Org admin `/[lang]/org` (switcher if a person admins several)
| Page | Content |
|---|---|
| Обзор | Org name; StatTiles teachers / courses / students; pending invitations list; primary "Пригласить преподавателя" |
| Преподаватели | Table: name, email, status badge (активен / приглашён / заблокирован), courses count. Primary "Пригласить преподавателя" → Dialog (email, message). Row actions on detail: "Отозвать приглашение", "Удалить из организации" (ReasonDialog: "{name} потеряет доступ к {n} курсам организации; курсы останутся, назначьте другого преподавателя"). Phone: cards. |
| Курсы | Table: title, teacher, status, students; primary "Создать курс" → page `/org/courses/new` (title ky/ru, language, optional template from the org's granted templates such as ORT, teacher via picker of org teachers). Row link to course page. |
| Курс `[courseId]` | Summary (DescriptionList), staff list, "Назначить преподавателя" (Dialog with org-teacher picker, role), "Открыть курс" (teacher view, read-only for org admin unless also staff). Reuse the platform-admin course detail layout with the moderation actions removed. |
| Настройки | Org name, default language, contact; read-only fields the platform admin controls (status, templates) shown as info. |

Shared components to build in `frontend/src/components/ui/` for both areas: `AreaShell`, `PageHeader`, `Table` (desktop table / phone cards, count, sort, `Pagination`), `Tabs`, `Badge` (status variants incl. "system"), `Dialog` + `ReasonDialog`, `UserPicker` (combobox with async search), `Select`, `Checkbox`, `Switch`, `DescriptionList`, `StatTile`, `EmptyState`, `Skeleton`, `Toast`, `Button` (primary/secondary/danger/link).

## ORT player ideas (owner decision)
None from this area.
