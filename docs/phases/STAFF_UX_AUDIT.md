# Staff UX audit: teacher and admin areas (owner item 5, 2026-11-08)

**Status**: audit and design, branch `fb8-5-audit`, docs only. Source: `STAFF_FEEDBACK_2026-11-08.md` item 5. Rules: `UX_GUIDELINES.md` §4–5, `AGENTS.md` §6. Out of scope: student area, ORT player and exam/bank/builder screens (frame only, as in 8c), Admin → Organizations pages (item 4, `ADMIN_ORGS_DESIGN.md`; only a menu slot here), teacher "Learning" hiding (item 2, parallel).

Paths below are relative to `frontend/src/` unless they start with `backend/`.

## 0. Principles (apply to every staff screen)

| Rule | Meaning |
|---|---|
| One header pattern | `PageHeader`: title, one-line subtitle, **one** primary button, everything else in a "⋯" `OverflowMenu`. No second button row, no action chips in headers. |
| Lists are tables | `Table` (compact density) with count line, search/filter slot, cursor pagination; stacked cards only under 640 px (already built into `Table`). No `<ul>` of cards for staff lists. |
| Width per page type | `STAFF_WIDTH.list` 1200 px, `.form` 720 px, `.formPreview` 1120 px (720 form + 360 preview), `.reading` 48rem. Nothing stretches to 1600 px except tables. |
| Compact density | Cards `padding="sm"` (16 px), table cells `py-2`, 14 px text, 44 px targets kept on phones through `min-h-11` only below `sm`. |
| State, not icons | "Hidden from students", "Draft", "Pro" are `Badge`s with text (icon optional). No icon-only state markers in navigation. |
| Dangerous in "⋯", last, red | Delete / trash / regenerate live in the overflow menu, `danger: true` (already how `OutlineMenu` draws them). |

## 1. Shared staff primitives (slice S0, everything else builds on these)

| Primitive | Today | Change | File |
|---|---|---|---|
| `PageHeader` | exists; `primaryAction`, `secondaryActions`, `badge`, `breadcrumbs` | add `overflow?: MenuGroup[]` + `onOverflow` → renders an `OverflowMenu` "⋯" right of the primary; `secondaryActions` kept but documented "at most one" | `components/ui/PageHeader.tsx` |
| `OverflowMenu` ("⋯") | exists as `components/lms/modules/OutlineMenu.tsx` (icon/button trigger, groups, danger-last, phone bottom sheet, full keyboard model) | move to `components/ui/OverflowMenu.tsx` (same API, export `MenuGroup`, `OverflowMenuItem`); keep `OutlineMenu.tsx` as a re-export so ORT-adjacent imports do not move | `components/ui/OverflowMenu.tsx`, `components/lms/modules/OutlineMenu.tsx`, `components/ui/index.ts` |
| `Table` (compact) | exists; cells `px-3 py-3`, cards on phones | add `density?: "default" \| "compact"` (`py-2`, `text-sm`, header `py-2`); staff tables pass `compact` | `components/ui/Table.tsx` |
| `Badge` | exists, 6 tones | no change; conventions: hidden = `neutral` + `EyeOff` + text, Pro = `warning`-tone gold variant already in `GoldPill` | — |
| Sub-nav | `TabsNav` exists (links, `aria-current`, scroll fade) | no change; used for Settings sections and Content tabs | `components/ui/Tabs.tsx` |
| `Switch` | exists, 44 px row with left label | add `size?: "md" \| "sm"` (sm: 20 × 36 px track, no row padding) and `hideLabel` (label becomes `sr-only`) for row toggles | `components/ui/Switch.tsx` |
| Grouped side nav | `AreaShell` flat `items` | `AreaNavItem.group?: string`; `AreaShell` renders group labels (small caps, like `SidebarNav`) when any item has a group; org area passes none → unchanged | `components/ui/AreaShell.tsx` |
| Width tokens | `SHELL_WIDTH` only | `export const STAFF_WIDTH = { list: "max-w-[1200px]", form: "max-w-[720px]", formPreview: "max-w-[1120px]", reading: "max-w-3xl" }` | `components/ui/shellWidth.ts`, `index.ts` |
| `StatTile` | exists (`min-h-[5.5rem]`, 2xl value) | add `size="sm"` (compact metrics row: `p-3`, `text-xl`) | `components/ui/StatTile.tsx` |
| `LockIconToggle` | — (Pro pill in `EditorParts.ProSwitch`) | new: `IconButton`-sized `role="switch"` with `Lock`/`LockOpen`, gold when on, `title` + `aria-label` tooltip text | `components/ui/LockToggle.tsx` |

i18n for S0: `ui.overflow` ("More actions" / "Башка аракеттер" / "Другие действия"; reuse `coursePage.moreActions` text), `ui.hidden` ("Hidden" / "Жашырылган" / "Скрыто"), `ui.pro.locked` / `ui.pro.unlocked` tooltips.

## 2. Teacher course page and course menu

### Current state
| Where | What | File |
|---|---|---|
| Sidebar | 11 links for a teacher: Course, Announcements, Assignments, Grades, People, Question banks, Settings, Files, Practice, Analytics (+ Progress/Saved for students); order is history, not use | `lib/lms/nav.ts:62-95`, `components/lms/course/CourseSidebar.tsx` |
| Sidebar | `EyeOff` marker ("crossed eye") on Announcements / Files / Practice when nothing is published | `CourseSidebar.tsx:49`, `components/ui/AreaShell.tsx:714-717` |
| Course page | general course: module outline + "Not in modules" + To do column; ORT: exam card list (`StaffAssessmentList embedded`) **then** a collapsible "Course structure" with the whole outline under it: one long page | `components/lms/course/TeacherCoursePage.tsx:62-93` |
| Assessments | `<ul>` of cards, 3–5 badges per row, 3 action buttons per row (Edit / Publish / Delete), "Show trash" as a header button next to "New assessment" | `components/lms/assessments/StaffAssessmentList.tsx:101-112, 123-180` |
| Course bar | crumb + title + status + template badge + "Student view" button; the course page has no `PageHeader` | `components/lms/course/StaffCourseUi.tsx:45-83` |

### Fix
**Course menu (teacher, assistant):** five sections, then "More".

| Section | Route(s) | Active when | Contains |
|---|---|---|---|
| Content | `/courses/{id}` (Structure), `/courses/{id}/assignments` (Assignments tab) | base, `/modules/**`, `/pages/**`, `/assignments/**`, `/assessments/**`, `/attempts/**` | Structure tab = module outline (today's `ModuleOutlineEditor` + `UnsortedGroup`); Assignments tab = compact table of quizzes and assignments; ORT course: tabs are **Exams** (default) and **Structure** |
| Students | `/people` | `/people/**` | roster, invitations, applications, join code (as today) |
| Grades | `/grades` | `/grades/**` | gradebook |
| Analytics | `/analytics` | `/analytics/**` | course analytics |
| Settings | `/settings` | `/settings/**` | teacher only (A13 stays) |
| More (group label) | `/announcements`, `/files`, `/practice`, `/bank` | each own prefix | Announcements, Files, Practice, Question banks |

- `nav.ts`: `CourseNavItem` gains `group?: "main" \| "more"`; order as above; `hiddenFromStudents` stays in the data (students' link hiding is unchanged) but `CourseSidebar` **no longer passes a `marker`**. The hidden state is shown once, on the page itself: `PageHeader badge={<Badge tone="neutral" icon={<EyeOff/>}>{t("ui.hidden")}</Badge>}` on Announcements, Files and Practice while `features.x` is false (files: `components/lms/courseFiles/CourseFilesView.tsx`, announcements: `components/lms/announcements/AnnouncementsView.tsx`, practice staff page: `app/[lang]/courses/[courseId]/practice/page.tsx`).
- Student / observer sidebars: same `nav.ts` function, unchanged items (Course, Assignments, Grades, People, Progress, Saved, …); only staff get groups. `hiddenAreaFor` unchanged.
- **Content tabs** (`components/lms/course/ContentTabs.tsx`, `TabsNav`): rendered by `TeacherCoursePage` and by `app/[lang]/courses/[courseId]/assignments/page.tsx` so both routes show the same tab row under the course bar. ORT: `/courses/{id}` shows the Exams tab (the exam table) and the Structure tab is the outline; no collapsible, no `sessionStorage` key (`STRUCTURE_KEY` removed); the `#m-…` deep link opens the Structure tab.
- **Assessment table** (`StaffAssessmentList` → `Table density="compact"`): columns Title (primary; status `Badge` inline), Status, Attempts (`in_progress / submitted`), Available (from–until, `nowrap`, `hideOnMobile`), Actions (`OverflowMenu`: Edit, Publish/Unpublish, Access code…, Delete (danger); trash view: Restore). Version and "unpublished changes" stay as a second line under the title only when present; the access-code key icon becomes a column-less `Badge` under the title. Count line = `countText`. Header: `PageHeader`-less inside tabs: an `h2` row with the one primary "New assessment" and a "⋯" with **Show trash / Hide trash**.
- **Content header "⋯"** (one per page, right of the primary "New module"): Expand all / Collapse all, Progress, Re-apply requirements, Show deleted modules. These already exist in `ModuleOutlineEditor` `moreGroups`; no new behaviour.
- **To do** column: unchanged (xl right column / one line below xl).
- Course bar: unchanged content; "Student view" stays its only button.

### Backend
None. `features` flags, `/todo`, assessments list already carry what the table needs.

### Tests
- `frontend/e2e/course-nav.spec.ts`: sidebar labels and groups, no `EyeOff` marker, badge on Announcements/Files pages, `/assignments` shows the Content tab row, student sidebar unchanged, drawer on phones.
- `phase8c-screens.spec.ts`, `ux-rework-screens.spec.ts`, `landing-screens.spec.ts` (`RECORD_LANDING=1`, the teacher course screenshot): re-record.
- `ort.spec.ts` / `ort-visual.spec.ts`: the teacher course page frame shots change (exam list becomes a table); re-record **frame** baselines with before/after images in `PHASE_FB8_screens/ort-before-after/`; player, lobby, result and review stay pixel-identical (assert zero diff).

## 3. Module editor

### Current state
| Problem | File |
|---|---|
| Add row per module: five dashed quick-add buttons (video, page, file, test, link) **plus** an "Ещё" menu = six controls per module | `components/lms/modules/ModuleOutlineEditor.tsx:544-553, 820-834` |
| Drag handle invisible until hover (`lg:opacity-0`), so reorder is undiscoverable; UX rule "no action only on hover" | `ModuleOutlineEditor.tsx:126-135` |
| Pro: a gold pill with star + mini switch and text "Pro" inside a `role=switch` button; heavy, unclear it is a toggle | `components/lms/modules/EditorParts.tsx:121-141` |
| Publish: icon-only toggle (filled check vs dashed circle), state readable only via tooltip | `ModuleOutlineEditor.tsx:105-121` |
| Module header row holds Pro + publish + "⋯" + drag + chevron: five controls | `ModuleOutlineEditor.tsx:640-696` |

### Fix
| Control | New |
|---|---|
| Add | one `OverflowMenu trigger="button" variant="secondary" size="sm"` labelled "+ Добавить" per module (and one in the empty module state). Groups: **Урок**: video, page, file, link; **Проверка**: test (ORT course: ORT exam), assignment; **Ещё**: header, existing item. `quickAdds` row removed; `addGroups` reused. Phone: same menu, already a bottom sheet. |
| Reorder | drag handle visible at `lg` (`text-slate-300`, `hover:text-slate-600`), hidden below `lg`; `MoveButtons` keep keyboard/phone path (no change). `aria-hidden` stays (menu "Move" entries are the accessible path). |
| Pro | `LockToggle` (S0): `Lock` gold when `access_tier === "paid"`, `LockOpen` slate when free; `title`/`aria-label` = "Pro: только по подписке. Нажмите, чтобы открыть всем" / "Бесплатно. Нажмите, чтобы сделать Pro"; platform courses only (as today). `ProSwitch` deleted. |
| Publish | `Switch size="sm" hideLabel` (`role="switch"`, label "Опубликован: {title}"); modules and items. Toast and the requirement warning dialog unchanged. |
| Row order | module header: chevron · title + meta · `LockToggle` (platform) · `Switch` · "⋯" · drag. Item row: icon · title + meta · duration chip · `Switch` · "⋯" · drag; `MoveButtons` stay hidden under `lg`. |
| Draft text | keep "Черновик" meta text next to the title (state is text, not only the switch colour). |

### Backend
None (`published`, `access_tier` toggles exist).

### Tests
- `modules-editor.spec.ts`, `modules.spec.ts`, `lessons.spec.ts`: locators for `data-move`, quick-add buttons → the "+ Добавить" menu; publish via `role=switch`; Pro via `LockToggle` `aria-label`.
- Unit-ish: `nav.check.ts` unchanged.

## 4. Create course

### Current state (`app/[lang]/courses/new/page.tsx`)
| Problem | Lines |
|---|---|
| Raw `<form>` card `max-w-3xl`, raw `<select>`/`<input>`/`<button>` (not design-system), `<h1>` inside the card, no `PageHeader` | 93-136 |
| `LanguagePicker`: three checkboxes **and** a default-language radio group before the title field; most courses have one language | `components/lms/LanguagePicker.tsx` |
| `LocalizedTextInput`: EN/RU/KY chips over every field with no explanation; chip text is a code, empty translations only announced to screen readers | `components/lms/LocalizedTextInput.tsx:49-60` |
| No template choice (ORT template is granted per organization but the form cannot pick it; `CourseCreateIn.template_key` exists in `lib/lms/types.ts:397`) | — |
| No cover, no catalog visibility; the right half of a 1440 px screen is empty | — |

### Fix
Layout `STAFF_WIDTH.formPreview`, `lg:grid-cols-[minmax(0,720px)_360px]`, preview sticky (`lg:sticky lg:top-6`), stacked under the form on phones (preview first, 16:9 cover height capped at 160 px).

| Field | Control | Notes |
|---|---|---|
| Organization | `Select` | only when `orgs.length > 1` (as today) |
| Template | `Select`: "Без шаблона" + granted templates (ORT) | shown only when the chosen organization has grants; sends `template_key`; a locked template note under it (`templates.lockedHint`) |
| Main language | `Select` ru / ky / en, default = UI language | replaces checkboxes + radios |
| Add translations | `Disclosure` "Добавить переводы" → `Checkbox` per other language | opening it turns the title/description fields into tabbed inputs |
| Title, description | `LocalizedTextInput` | chips only when `languages.length > 1`; chip text = language name + "(основной)" / "(пусто)" visible, `aria-selected`; a hint line "Пустой перевод показывает текст основного языка" (matches `pickLocalized` fallback) |
| Cover | `CoverPicker` (file chosen locally, 16:9 crop as in `CourseCoverSection`; "Обложка по умолчанию" otherwise) | on submit: create → `PUT cover` with the existing endpoint → redirect; a cover failure shows a toast and lands on Settings → Cover |
| Enrollment | `Select` mode + `Input` limit + `Switch` "Показывать в каталоге" | same options as settings |
| Preview | `CourseCard` fed with live values (`cover_url` = object URL or null, `languages`, `title`, `description`, organization name) | `headingLevel={2}`, `href={null}` |
| Footer | `Button` primary "Создать курс", `LinkButton` secondary Cancel | `PageHeader` above: "Новый курс", subtitle "Название и язык можно изменить позже" |

`LanguagePicker.tsx` is deleted after Settings (section 5) moves to the same `LanguageFields` component (`components/lms/course/form/LanguageFields.tsx`).

### Backend
- `GET /me/organizations` rows gain `template_keys: string[]` (granted templates, `app/lms/templates/service.py: granted_templates`, one query per row; a teacher has ≤ a handful of organizations). Course creation with `template_key` already exists (`backend/app/lms/courses/schemas.py:55`).
- Test: `tests/lms/test_me_organizations_templates.py` (granted key listed, ungranted not, personal organization has none).

### Tests
- New `frontend/e2e/course-create.spec.ts`: single-language create, add translation, template select appears only with a grant, preview updates, cover uploaded after create (console storage driver `db`).
- `teacher-signup.spec.ts` (`courses/new` teacher-only message): selector check only.

## 5. Course settings

### Current state (`app/[lang]/courses/[courseId]/settings/page.tsx`, 323 lines, one column `max-w-3xl`)
Stacked cards in this order: General (languages, title, description), Cover (`CourseCoverSection`, 284 lines with its own previews), Course home, Exam date, Enrollment (join code + mode + limit + catalog + form link), Grading scheme, Lifecycle, Danger zone (`Disclosure`). Each card has its own Save; the page scrolls ~4 screens; lifecycle (publish/unpublish) is buried below grading.

### Fix
`TabsNav` sub-nav under `PageHeader` ("Настройки курса", subtitle = course name), sections as `?section=` links (deep-linkable, one page file, each section its own component in `components/lms/course/settings/`):

| Section | Content | Preview column |
|---|---|---|
| General (default) | `LanguageFields` (main language + translations), title, description, Course home (`CourseHomeSection`), exam date (exam-prep courses) | `CourseCard` live preview (sticky, ≥ `lg`) |
| Cover | `CourseCoverSection` (upload, crop, default) | the same card preview (replaces the section's own card/banner previews) |
| Enrollment | join code + regenerate (in "⋯"), mode, limit, catalog switch, enrollment form link, active students count | none |
| Access / Pro | course status with the lifecycle buttons (Publish primary; Unpublish / Conclude in "⋯"); platform courses: Pro notes and links to Admin → Pro → Paid exams and "practice is free" (read-only here; the server owns them); other courses: one line "Pro is available on platform courses" | none |
| Grading | `CourseGradingSection` (needs its own tab: it is a large form; **deviation from the owner's five**, see decision D-FB8-5-3) | none |
| Danger zone | transfer ownership, delete; owner only; red title | none |

Form width `STAFF_WIDTH.form` (720 px); with preview the grid is `formPreview`. Each section keeps its own Save (sticky save bar stays deferred, UX T28). `Disclosure` no longer wraps Danger zone (it is its own tab). The `settings/enrollment-form` sub-page is unchanged and keeps linking back to `?section=enrollment`.

### Backend
None.

### Tests
- `course-cover.spec.ts` (cover section now under `?section=cover`), `catalog-apply.spec.ts` (visibility switch under `?section=enrollment`), `exam-prep.spec.ts` if it sets the exam date in settings: update locators.
- New cases in `course-create.spec.ts` or a `course-settings.spec.ts`: tab deep links, save per section, danger tab only for the owner.

## 6. Admin overview

### Current state (`app/[lang]/admin/page.tsx`)
Two `StatTile`s (pending requests, storage level) in a 4-column grid (two empty slots), then the access reveal alert and "recent exams" card, then a full `HealthCard` (4 rows + commit) always expanded. No user, student or Pro numbers anywhere; the owner opens Users / Pro / Storage to find them.

### Fix
```
PageHeader "Обзор"  (primary: none; ⋯: Проверить состояние, Открыть журнал)
Metrics row (4 × StatTile size=sm): Пользователи · Активные ученики (7 дней) · Pro-подписчики · Тестов за неделю
Needs attention (Card, compact list; each row = icon, text, count badge, link):
  Заявки преподавателей (N) → /admin/teacher-requests          [only if N > 0]
  Хранилище: предупреждение / заполнено → /admin/storage        [only if level != ok]
  Раскрытия кодов за час (N) → /admin/access/vouchers           [only if reveal_alert]
  Проверки состояния: N с ошибкой → /admin/health               [only if health.ok = false]
  (empty state: one line "Всё в порядке")
Quick actions (LinkButton secondary row): Новый курс платформы · Выдать Pro · Создать коды · Экспорт журнала
Status line: ● Система в порядке · коммит abc1234 · Подробнее → /admin/health   (HealthCard moves to that page)
Recent exams card (existing RecentExamsCard compact) below.
```

### Backend: `GET /platform/overview` (new, platform admin only; `/summary` stays light because `AdminShell` calls it on every admin page)

| Field | Query | Cost at 6,000 students |
|---|---|---|
| `users_total` | `count(*) from users where deleted_at is null and is_test_student = false` | seq scan ≤ 10k rows, < 5 ms |
| `active_students_7d` | `count(distinct a.user_id) from attempts a join users u on u.id = a.user_id where a.started_at >= now - 7d and a.is_preview = false and u.is_test_student = false` | no index on `started_at`; ~120k attempt rows → seq scan ~20–40 ms. Acceptable for a page the owner opens; add `Index("ix_attempts_started_at", "started_at")` in a later migration only if prod `EXPLAIN` shows > 100 ms |
| `pro_active` | `access.admin.pro_summary(db, now)["active"]` (existing grouped-chain statement) | already used by Admin → Pro |
| `attempts_submitted_7d` | `count(*) from attempts where submitted_at >= now - 7d and is_preview = false and is_practice = false and status in ('submitted','needs_review','graded')` | same scan; "this week" = last 7 days (decision D-FB8-5-4) |
| `pending_teacher_requests`, `storage_level` | as `/summary` | existing |
| `reveals_last_hour`, `reveal_alert` | `access.admin.reveals_last_hour` | existing |

Response cached 60 s per process (same pattern as `storage_service.summary`), so repeated reloads do not re-scan. Add to `app/core/route_inventory.py` with the platform-admin policy. Health stays `GET /platform/health` (separate, slower: email/storage probes), fetched only on `/admin/health` and for the status line (one call on the overview; the line shows a skeleton until it answers).

Tests: `backend/tests/lms/test_platform_overview.py`: 403 for non-admins, counts exclude previews, practice, test students, deleted users; 7-day window boundaries; cache invalidation by clock; inventory test covers the new route. Frontend: new `frontend/e2e/admin-overview.spec.ts` (metrics render, attention rows appear with a pending request, health line collapsed, details page), `admin-security-screens.spec.ts` re-recorded if it shots the overview.

## 7. Admin menu

### Current state (`components/lms/admin/AdminShell.tsx:76-88`)
Eleven flat links: Overview, Organizations, Teacher requests, Users, Courses, Exam templates, Access, Audit log, Storage, Privacy, Security. "Access" hides four tabs (Pro users, Vouchers, Paid exams, Settings).

### Fix (`AreaShell` groups from S0)
| Group | Items → route |
|---|---|
| (none) | Overview → `/admin` |
| People | Users → `/admin/users`; Teacher requests (count) → `/admin/teacher-requests` |
| Content | Organizations → `/admin/organizations` (pages owned by item 4); Courses → `/admin/courses`; Exam templates → `/admin/exam-templates` |
| Pro | Plans and settings → `/admin/access/settings`; Pro users → `/admin/access`; Gift codes → `/admin/access/vouchers`; Paid exams → `/admin/access/exams` (fourth item; deviation D-FB8-5-5) |
| System | Storage → `/admin/storage`; Health → `/admin/health` (new page: the full `HealthCard`); Audit log → `/admin/audit-log`; Security → `/admin/security`; Data requests → `/admin/privacy` |

`AccessTabs` (`components/lms/access/AdminAccessUi.tsx:15`) is removed from the four access pages (the side nav now distinguishes them); each page gets its own `PageHeader` title matching the menu label. The MFA gate keeps filtering to Security only (`mustEnroll`). Phones: `TabsNav` row flattens the groups (labels only), as today.

Tests: `admin-mfa-gate.spec.ts` (nav filtered), `access.spec.ts` (navigation by sidebar instead of tabs), `header-areas.spec.ts` (unchanged header; sanity), new health page in `admin-overview.spec.ts`.

## 8. Everywhere: findings by file

| # | File | Issue | Fix |
|---|---|---|---|
| E1 | `app/[lang]/courses/new/page.tsx:93-136` | raw inputs/selects/buttons, `<h1>` in card, no `PageHeader` | section 4 |
| E2 | `components/lms/assessments/StaffAssessmentList.tsx:123-180` | card list, 3 buttons/row, badges wrap on 375 px | table + "⋯" (section 2) |
| E3 | `app/[lang]/admin/teacher-requests/page.tsx:123-166` | `<ul>` of `Card`s with `DescriptionList`; 6 fields and 2 buttons per request; 20 requests = 10 screens | `Table density="compact"`: Name (primary), School, Subject, Teaches at, Submitted (`nowrap`), Actions ("⋯": Approve, Reject, Open user); a row click expands phone/message/email in a `Sheet`; tabs Pending/Decided stay |
| E4 | `app/[lang]/admin/page.tsx:36-43` | 2 tiles in a 4-column grid, half the row empty; `HealthCard` always open | section 6 |
| E5 | `components/lms/admin/AdminShell.tsx:76-88` | flat 11-item menu | section 7 |
| E6 | `app/[lang]/courses/[courseId]/settings/page.tsx` | 8 stacked cards, 4 screens tall, half-empty right side ≥ 1280 px | section 5 |
| E7 | `components/lms/course/CourseSidebar.tsx:49`, `components/ui/AreaShell.tsx:714-717` | crossed-eye markers in navigation (icon-only state) | badge on the page (section 2); `AreaNavItem.marker` kept in the type for the org area, unused by courses |
| E8 | `components/lms/modules/ModuleOutlineEditor.tsx:820-834` | six add controls per module | section 3 |
| E9 | `app/[lang]/admin/access/*/page.tsx` + `AccessTabs` | tabs inside a section inside a flat menu (two navigation levels for four pages) | menu group "Pro" replaces the tabs (section 7) |
| E10 | `app/[lang]/admin/{users,courses,privacy,organizations}/page.tsx`, `audit-log` | tables already; cells `py-3`, full 1600 px width, filters in a separate card row | `density="compact"`, `STAFF_WIDTH.list`, filters in the `Table` `search` slot (`FilterBar`) |
| E11 | `app/[lang]/admin/users/[userId]/page.tsx`, `courses/[courseId]/page.tsx`, `security/page.tsx` | 2 `PageHeader`s per page (page + a section header) | one `PageHeader`; section titles are `Card title` (h2) |
| E12 | `app/[lang]/courses/[courseId]/people/page.tsx`, `grades`, `analytics`, `bank/page.tsx` | headers fine (`PageHeader`), but width unbounded and `secondaryActions` hold 2–3 buttons (People: invite, import, applications) | `STAFF_WIDTH.list`; keep one primary (People: "Пригласить"), rest in "⋯" |
| E13 | `app/[lang]/courses/trash/page.tsx:` `<h1>` raw, card list | `PageHeader` + `CourseCard` grid as the teaching list (item 1 owns card size) |
| E14 | `components/lms/course/StaffCourseUi.tsx:62-80` | course bar duplicates breadcrumbs that `PageHeader` also renders on sub-pages (two crumb rows on People/Grades) | sub-pages pass no `breadcrumbs`; the bar is the single crumb row |
| E15 | `components/lms/admin/HealthCard.tsx` | 4 rows + commit always visible on the overview | status line on the overview; full card on `/admin/health` |

Phone (375 px): all of the above keep `Table` cards and the course drawer; "⋯" menus are bottom sheets already. Check ru at 375 / 1440 / 1920 per `AGENTS.md` §6.10 after each slice.

## 9. Backend changes (summary)

| Change | Where | Migration | Tests |
|---|---|---|---|
| `GET /platform/overview` (counts above, 60 s cache) | `backend/app/lms/platform_admin/overview.py`, `router.py`, `schemas.py`, `app/core/route_inventory.py` | none (index on `attempts.started_at` deferred until measured) | `tests/lms/test_platform_overview.py` |
| `template_keys` on `GET /me/organizations` rows | `backend/app/lms/organizations/` schema + service, `templates/service.granted_templates` | none | `tests/lms/test_me_organizations_templates.py` |
| Nothing else | publish, `access_tier`, cover upload, assessments trash, `/todo`, `features` already exist | | |

## 10. Implementation slices

S0 lands first (everyone imports it). S1–S5 run in parallel after S0; S6 after S1–S5 (touches only files no other slice owns, but waits so screenshots are final). S7 is the gate.

| Slice | Model | Owns (exclusively) | Tests / e2e |
|---|---|---|---|
| **S0 primitives** | Opus | `components/ui/{OverflowMenu,PageHeader,Table,Switch,AreaShell,StatTile,LockToggle,shellWidth,index}.tsx/ts`, `components/lms/modules/OutlineMenu.tsx` (re-export), i18n keys `ui.*` in `en/ky/ru.json` | `tsc`, i18n parity; no e2e change (API additive) |
| **S1 course menu + Content** | Opus | `lib/lms/nav.ts`, `nav.check.ts`, `components/lms/course/{CourseSidebar,TeacherCoursePage,ContentTabs,StaffCourseUi}.tsx`, `components/lms/assessments/StaffAssessmentList.tsx`, `app/[lang]/courses/[courseId]/{page,assignments/page,announcements/page,files/page,practice/page}.tsx`, `components/lms/courseFiles/CourseFilesView.tsx`, `components/lms/announcements/AnnouncementsView.tsx`, i18n `courseNav.*`, `assessments.list.*` | `course-nav`, `phase8c-screens`, `ux-rework-screens`, `landing-screens` (re-record), `ort`/`ort-visual` frame baselines (before/after saved; player zero diff), `student-links` (student sidebar unchanged) |
| **S2 module editor** | Opus | `components/lms/modules/{ModuleOutlineEditor,EditorParts}.tsx`, i18n `modules.editor.*` | `modules-editor`, `modules`, `lessons` |
| **S3 create + settings** | Opus (form data, template, cover-after-create); Sonnet pass for styling/text | `app/[lang]/courses/new/page.tsx`, `app/[lang]/courses/[courseId]/settings/page.tsx`, new `components/lms/course/form/{LanguageFields,CoverPicker,CoursePreview}.tsx`, `components/lms/course/settings/*.tsx`, `components/lms/{LocalizedTextInput,LanguagePicker}.tsx`, `components/lms/course/CourseCoverSection.tsx`, `lib/lms/organizations.ts` (type), backend `organizations` schema/service + test, i18n `courses.create.*`, `courses.settings.*` | new `course-create.spec.ts`, `course-cover`, `catalog-apply`, `exam-prep` (settings locators), backend `test_me_organizations_templates.py` |
| **S4 admin overview + endpoint** | Opus | backend `platform_admin/{overview,router,schemas}.py`, `route_inventory.py`, `tests/lms/test_platform_overview.py`; `app/[lang]/admin/page.tsx`, `app/[lang]/admin/health/page.tsx`, `components/lms/admin/{MetricsRow,NeedsAttention,HealthLine,HealthCard}.tsx`, `lib/lms/admin.ts`, i18n `platformAdmin.overview.*`, `adminHealth.*` | backend test; new `admin-overview.spec.ts`; `admin-security-screens` re-record |
| **S5 admin menu** | Sonnet | `components/lms/admin/AdminShell.tsx`, `components/lms/access/AdminAccessUi.tsx` (remove `AccessTabs`), `app/[lang]/admin/access/{page,vouchers,exams,settings}/page.tsx` headers only, i18n `platformAdmin.nav.*`, `access.admin.*` | `admin-mfa-gate`, `access`, `header-areas` |
| **S6 density sweep** | Sonnet | `app/[lang]/admin/{teacher-requests,users,users/[userId],courses,courses/[courseId],audit-log,storage,privacy,security}/page.tsx`, `app/[lang]/courses/[courseId]/{people,grades,analytics,bank}/page.tsx` (width + header only), `app/[lang]/courses/trash/page.tsx`, `components/lms/gradebook/StaffGradebook.tsx`, `components/lms/analytics/CourseAnalytics.tsx` (density prop only) | `person`, `privacy`, `teacher-signup` (requests table), `org-admin` sanity; screenshots |
| **S7 gate** | orchestrator | `docs/phases/PHASE_FB8_screens/`, `PRODUCT_DECISIONS.md`, `HANDOFF_NEXT_AGENT.md` | ru screenshots 375 / 1440 / 1920 of every changed page; full SQLite + PG suites; ORT parity (imports diff, e2e, pixel compare) |

Conflict notes: `components/ui/index.ts` is S0-only; S1–S6 import, never edit it. `ru/ky/en.json` is shared: each slice adds keys only under its own prefixes listed above; parity script runs per slice. `AreaShell.tsx` is S0-only; S5 passes `group`, S1 passes groups via `CourseSidebar`.

## 11. Decisions to record (`PRODUCT_DECISIONS.md`)

| Id | Decision |
|---|---|
| D-FB8-5-1 | Course menu = Content, Students, Grades, Analytics, Settings + "More" (Announcements, Files, Practice, Question banks). Assignments is a tab of Content, not a menu item; its URL stays `/assignments`. |
| D-FB8-5-2 | "Hidden from students" is a text badge on the page header of the hidden area, never an icon in navigation. |
| D-FB8-5-3 | Course settings get six sections: the owner's five plus Grading (the grading scheme form is too large for General). Owner may fold it into General. |
| D-FB8-5-4 | Overview metrics: "active students" = distinct non-test users with a non-preview attempt started in the last 7 days; "tests this week" = non-preview, non-practice attempts submitted in the last 7 days. Both from a new `GET /platform/overview`, cached 60 s, no new index yet. |
| D-FB8-5-5 | Admin menu groups as the owner listed; "Paid exams" is a fourth Pro item (it is the assessment tier toggle, not a course). Health gets its own page under System. |
| D-FB8-5-6 | Create course: one main language + optional translations; template select only when the organization holds a grant; cover is picked in the form and uploaded right after creation. |
| D-FB8-5-7 | ORT teacher course page: the exam list is a compact table on the default "Exams" tab; the structure is the second tab. Exam content, builder, bank, import, player and results are unchanged; frame baselines are re-recorded with before/after images. |

## 12. Open questions (do not block; defaults chosen above)

1. Should Grading be its own settings section (default) or a Disclosure under General?
2. "Tests taken this week": calendar week (Mon–Sun, Bishkek time) or rolling 7 days (default)?
3. Teacher-request rows: expand details in a `Sheet` (default) or link to the user page only?
