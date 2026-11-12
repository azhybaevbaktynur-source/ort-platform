# Catalog and teachers without a school (fix round 2026-11-12, step 3b)

**Status**: design only (architect on Fable, 2026-11-12). Base: `lms` 15fffb8. Owner brief: `FIX_ROUND_2026-11-12.md`
step 3b. Owner decisions in force: teachers and students are separate accounts (teachers never enrol, 1b built the
403 `teacher_cannot_enroll`); personal organizations stay internal (`ACCOUNTS.md` Q1); ORT and platform courses stay
in the catalog (D-ORG-1); direction "individual students first, ORT first" (`ROADMAP_EXAM_PREP.md`). Consistent with
step 3a (`STUDENT_IA_DESIGN.md` §2.1: Каталог is a global student item at `/courses/catalog`, `CatalogView` unchanged
there; this design changes what the list contains, not the page).

Production, measured read-only on the Neon triage branch (2026-11-12): 4 organizations (1 platform, 3 personal, all
active); 22 accounts (1 platform admin, 4 approved teachers, 17 others), 2 teacher requests (both approved), 6 real
learners. Courses in the catalog today: the 2 ORT courses (platform, open, 11 enrolments) **and 2 courses of
independent teachers** (one `invite_code`, one `open`, 1 student each). Also: 1 teacher course blocked by the admin
(`unlisted_by_admin_at`, 3 students), 2 published private teacher courses (4 students), 2 drafts, 3 enrollment forms
(all draft, none active).

## 1. How it works today, and what is confusing

| # | Today | Where | Why it confuses |
|---|---|---|---|
| T1 | The catalog is **every published course with `visibility = 'catalog'`** in an active organization tree, whoever owns it; the only admin control is reactive (`unlist` after the fact) | `courses/scopes.py:88-104` (`_catalog_select`), teacher switch `EnrollmentSection.tsx:98-100` → `courses/service.py:265-268` (refuses only after an admin unlist); admin `platform_admin/courses_router.py:121-134`, `courses/service.py:582-592` | A new student opens Каталог and sees a test course of an unknown tutor next to ORT. Nobody approved it. The owner already unlisted one such course by hand (`PRODUCT_DECISIONS.md` 2026-11-06) |
| T2 | Approving a teacher **creates a personal organization** (fixed id, slug `t-…`, name = display name at that moment, `org_admin` membership, `teachers_can_create_courses` on) in the same transaction; revoke suspends it | `teachers/service.py:293, 359-369, 382-389`; `organizations/service.py:214-237`; `organizations/defaults.py:63-81` | Correct as a data model (every course and bank needs an organization; A1 isolation), wrong as a **presentation**: the admin sees an "organization" appear |
| T3 | Admin → Organizations lists personal organizations as rows («Личная»), with the person's old display name as the name, and the detail page offers members, templates, suspend/resume for them | `platform_admin/organizations_service.py:23-37`, `admin/organizations/page.tsx:21, 52`, `admin/organizations/[orgId]/page.tsx:124`; D-ORG-5 guards only resume | "Organization" wording for a person; `name` is never updated after a rename (`defaults.py:73` sets it on insert only); member management of a one-person organization is meaningless (invitations already refuse: `personal_org_no_members`) |
| T4 | The person page shows teacher status, grant/revoke and `revoke_impact`, but not whether the person is independent or at a school, nor courses / students / catalog listings | `admin/users/[userId]/page.tsx:138, 184, 265`; `ACCOUNTS.md` B | The admin has no single list of teachers; the Teacher requests queue (`admin/teacher-requests/page.tsx`) is the only place that says "independent" (`teaches_at` empty) |
| T5 | The teacher side already hides the organization: `admin_organizations` excludes personal (`teachers/service.py:29-48`), `/org/{id}` redirects (`OrgShell.tsx:54-58`, `org/page.tsx:27`), pickers say «Мои курсы» (`lib/lms/organizations.ts:338-341`), cards hide the name (`courses/schemas.py:231-233`) | | Done well; one leftover: the error `organizations.errors.personal_org_no_members` talks about "организацию" |
| T6 | People who teach open the catalog in the app frame: no «Записаться», «Открыть» only where they are staff; the landing offers «Режим ученика» | `CatalogView.tsx:45-46, 109-115`, `CourseLanding.tsx:140-146`; Teaching list link `courses/page.tsx:105-111` | Fine after 1b; it still reads like a place to do something |
| T7 | Platform courses reach students on the home («От платформы») by organization, not through the catalog | `home/service.py:251-261` (`platform_org_id()`) | Good: the catalog rule below cannot hide ORT from anyone |
| T8 | Form modes require `visibility = 'catalog'` because the landing 404s for private courses | `courses/service.py:352-375` (`form_needs_catalog`), landing scope `catalog_router.py:102-105` | With an approval step, a form-mode course would be unreachable until approved; the "link access" model in §2.2 fixes this |

## 2. Catalog rules

### 2.1 What a student sees by default
**Platform courses, plus teacher courses whose listing the platform admin approved.** Nothing else. Concretely the
list scope (`_catalog_select`) becomes: published, not deleted, organization tree active, `listing = 'listed'`.
Platform-organization courses get `listing = 'listed'` automatically when the platform admin turns the catalog switch
on (the admin is the approver, no queue). ORT is therefore unaffected (D-ORG-1).

Ordering and cards unchanged (`published_at` keyset, `CatalogCardOut`); a listed teacher course keeps its mode badge
(«По коду» / «Открыт для всех» / «По заявке»): "listed" and "how to join" stay separate, as the owner asked.

### 2.2 Two switches: link access and listing (better than one "visibility" switch)
Today `visibility` means "in the catalog". Split it:

| Setting | Column | Who | Meaning |
|---|---|---|---|
| **Доступ по ссылке** (link access) | `visibility` (`private` / `catalog`, unchanged values) | course staff | The landing `/courses/catalog/{id}` opens for any signed-in student with the link; open join and form applications work from it. Private = landing 404, join by code only (today's behaviour) |
| **В каталоге** (listing) | `listing` (new: `off` / `pending` / `listed` / `declined` / `blocked`) | staff request, platform admin decides | The course appears in the catalog list and search |

So "join by code or link" is the default for every teacher course without any review, and the catalog list is the
only thing that needs approval. The landing uses a `linkable` scope (published, not deleted, tree active,
`visibility = 'catalog'`, `listing != 'blocked'`); the list uses `listed`. `form_needs_catalog` keeps its meaning
("the landing must be reachable") and no longer depends on the admin. The UI copy for the first switch changes from
«Показывать в каталоге» to «Страница курса открыта по ссылке».

### 2.3 Listing state machine (`courses.listing`)

```
off ──request──▶ pending ──approve──▶ listed ──block──▶ blocked
 ▲                 │  │                 │  ▲               │
 │   withdraw      │  └──decline──▶ declined ──request──┘   relist (admin)
 └─────────────────┘                                        └──▶ listed
```

| Transition | Who | Preconditions | Effects |
|---|---|---|---|
| request (`off`/`declined` → `pending`) | course owner, course teacher with `course:roster.manage` (the same right that edits enrollment settings), org admin of the tree; never a test student, never on a sandbox or template-locked course | `status = published`, `visibility = catalog`, title and description in the default language non-empty, cover or ≥ 1 published assignment/lesson (`listing_incomplete` 422 lists what is missing) | `listing_requested_at = now`, audit `course.listing.request`; ≤ 1 pending per course, ≤ 20 requests per teacher per day (`RateLimit` as `TEACHER_REQUEST_24H`) |
| withdraw (`pending` → `off`) | same | | audit |
| approve (`pending` → `listed`) | platform admin | | `listing_decided_at/by`, note optional; email to the owner (trilingual, `send_email(private=True)` as decisions in `teachers/emails.py`) |
| decline (`pending` → `declined`) | platform admin | note required (≤ 500) | note stored in `listing_note`, shown to course staff only, emailed |
| block (`listed`/`pending`/`off` → `blocked`) | platform admin | reason (today's `unlist`) | course leaves list **and** landing; staff cannot request; audit `course.unlist` (name kept) |
| relist (`blocked` → `listed`) | platform admin | | audit `course.relist` |
| platform switch | platform admin on a platform-tree course | `visibility` → `catalog` | `listing = listed` directly (no queue); `visibility` → `private` sets `off` |
| unpublish / conclude / delete | staff | | course leaves the list by scope; **`listing` is kept**, so republish or restore returns it without a new review |
| visibility → private while `listed`/`pending` | staff | | `listing = off` (a course nobody can open by link cannot be listed); the UI warns before saving |
| revoke teacher / suspend organization | admin | | hidden by the organization join (today); `listing` kept, returns on re-grant (D10) |

**Re-review after approval:** none automatically. Title, description, cover and enrollment mode edits after approval
set `listing_content_changed_at`; the admin catalog page shows «изменён после одобрения» when it is later than
`listing_decided_at`, with a one-click re-check (approve again clears the marker) or block. Reason: the owner cannot
review every typo, and an automatic drop to `pending` would hide a listed course on a title fix (that is exactly the
"hiding courses" risk in §5).

### 2.4 What the admin sees
New page **Админ → Каталог** (`/admin/catalog`), tabs **Заявки** (pending, count in the admin overview as a tile
«Заявки в каталог») · **В каталоге** (listed; platform courses too, marked «Платформа») · **Отклонённые и снятые**.
Row: cover, title, owner (link to the person page), «Независимый преподаватель» or the school name, mode, students,
tests / lessons, requested or decided at, the content-changed marker. Actions: Открыть (the public landing as the admin
sees it, with «Режим ученика» already on `CourseLanding`), Одобрить, Отклонить (note), Снять (reason), Вернуть.
Admin → Courses keeps its detail page; its «Снять с каталога» / «Вернуть» become block / relist of this state.

### 2.5 Teachers in the catalog
Unchanged from 1b, with wording: the page for people who teach is a **preview** («Так каталог видят ученики»), no
join actions, «Открыть» on courses they staff, «Режим ученика» on the landing. The Teaching list link
«Каталог курсов» (`courses/page.tsx:105-111`) goes; the catalog block in course settings (§2.6) links to the preview
instead. Teachers never enrol (1b, backend 403 stays).

### 2.6 What the teacher sees in course settings (Записи → new block «Каталог платформы»)
`off`: «Курс не показан в каталоге. Ученики приходят по коду {code} или по ссылке.» + [Предложить в каталог]
(disabled with the missing items when `listing_incomplete`). `pending`: «На проверке с {date}» + [Отозвать].
`listed`: «В каталоге с {date}» + [Убрать из каталога] (= withdraw to `off`). `declined`: «Отклонено {date}: {note}»
+ [Отправить снова]. `blocked`: «Снят администратором платформы {date}», no button. The join code and modes stay as
today above it.

### 2.7 Public catalog / SEO
Not in this step. The catalog needs a login (`get_authz`, `catalog_router.py:72-78`), and the landing page design
(step 3c) is the right public surface for the platform exams. If the owner wants SEO for approved teacher courses
later: `GET /public/catalog` returning only `listed` cards without `my_enrollment`, and a static `/{lang}/catalog`
page in `PublicShell`; the approval step makes that safe, which it is not today (D5).

## 3. Independent teachers

### 3.1 Data model: keep personal organizations, change the presentation (recommended)
Options considered:

| Option | Cost | Verdict |
|---|---|---|
| **A. Keep `kind = 'personal'` rows; the admin UI never calls them organizations** | small (UI + two list filters + one new read endpoint) | **Recommended.** `courses.organization_id NOT NULL`, bank ownership, `creator_organizations`, template grants, usage, suspension on revoke, P9-2 isolation ("personal organizations can never share") and `test_org_isolation.py` all rest on the row. The row is an implementation detail; only the admin ever saw it |
| B. `users.is_independent_teacher` + nullable `organization_id` on courses and banks | large: every scope joins `organizations` (`scopes.py:94-103`, `home/service.py:117`, access gates), the course move, shared banks, suspension inheritance, 30+ tests | No: rewrites authorization for a wording problem |
| C. One shared "Независимые преподаватели" organization | medium | No: breaks A1 ("banks must never be shared between independent teachers"), per-teacher suspension and `revoke_impact` |

### 3.2 Admin area
- **Админ → Организации** lists **schools and the platform only** (`organizations_query` default `kind IN ('school',
  'platform')`; the «Личная» filter option goes; the overview tile «Организации» counts the same). The detail page of
  a personal organization redirects to the person page; `GET /platform/organizations/{id}` keeps working for scripts.
- **New Админ → Преподаватели** (`/admin/teachers`), tabs **Преподаватели · Заявки** (the Teacher requests page moves
  under the second tab; `/admin/teacher-requests` redirects). `GET /platform/teachers?q=&kind=independent|school&
  status=approved|revoked`: one row per person who is `teacher_status in (approved, revoked)` or holds an active
  `teacher`/`org_admin` membership in a school. Columns: name / email (link to the person page), **Где преподаёт**
  («Независимый преподаватель» when the person has no active school membership, else school names, ≤ 3), status
  badge (`UserStatusBadge kind="teacher"`), courses (live, owned or staffed), students (distinct active, no test
  students), в каталоге (listed courses), last sign-in, since (approval date). Five grouped statements per page keyed
  by user id, like `admin_rows` (`organizations_service.py:64-118`), never N+1.
- **Person page** gains a «Преподавание» card: «Независимый преподаватель с {date}» or the schools; courses, students,
  listed courses with links to Admin → Courses `?owner_id=` and Admin → Каталог; grant / revoke stay (`revoke_impact`
  unchanged). The organizations card hides the personal row.
- **Audit**: `teacher_request.approve` details keep `organization_id` (it is the real record); the audit log viewer
  labels a personal organization target as «личное пространство преподавателя» instead of its slug.
- Wording rule (en/ky/ru): the admin UI says **независимый преподаватель / independent teacher / көз карандысыз
  мугалим**, never "personal organization"; the i18n key `organizations.kind.personal` stays only for the badge inside
  the audit viewer.

### 3.3 What the teacher sees
Nothing about organizations (already true, T5). Checks added to `e2e/role-links.spec.ts`: the independent teacher's
Teaching pages, course settings, new-course page and exam templates contain no «организац» text; the only exception is
an invitation banner from a school. The `personal_org_no_members` message is reworded («В ваши курсы преподавателей
приглашают на странице курса «Участники»»).

### 3.4 Joining a school later, suspension, revoke
- A school invitation accepted by an independent teacher adds a school membership; the personal organization stays.
  `courses/new` then shows the existing picker («Мои курсы» vs the school); existing courses stay personal unless the
  platform admin moves them (`move_course`, target never personal). Removed from the school later: back to
  independent, nothing to migrate. The Teachers list shows both («Независимый · Школа №1»).
- Revoke (`set_teacher_status revoked`): personal organization suspended (today), courses read-only, out of the
  catalog list and landing by the organization join, school memberships untouched (the school admin's call).
  Re-grant resumes it; `listing` values are kept (D10).
- Q6 of `ACCOUNTS.md` («stop new courses» vs «freeze») stays open; this design does not add actions.

## 4. Data, API, i18n

### 4.1 Migration `0033_course_listing` (additive except one drop)
`courses`: `listing VARCHAR(16) NOT NULL DEFAULT 'off'` with CHECK `listing IN ('off','pending','listed','declined',
'blocked')`; `listing_requested_at`, `listing_decided_at`, `listing_content_changed_at` timestamptz NULL;
`listing_decided_by_id` VARCHAR(64) FK `users.id` ON DELETE SET NULL; `listing_note` VARCHAR(500) NULL.
Index `ix_courses_listing_published_at (listing, published_at)` (the catalog page query). Drop `unlisted_by_admin_at`
after the backfill (model, `AdminCourseOut.unlisted_by_admin_at`, `CourseStaffOut.unlisted_by_admin`, the settings
hint and `lms.errors.unlisted_by_admin` go with it; `unlisted_by_admin` in the staff payload becomes
`listing.state == 'blocked'`).

Backfill (bounded UPDATEs, in the migration):
1. `unlisted_by_admin_at IS NOT NULL` → `blocked`, `listing_decided_at = unlisted_by_admin_at` (1 course on production).
2. `visibility = 'catalog'` and organization path inside the platform tree → `listed`, `listing_decided_at = published_at`
   (the 2 ORT courses).
3. `visibility = 'catalog'`, published, any other tree → **`pending`**, `listing_requested_at = published_at`
   (2 courses; the owner approves or declines them in Admin → Каталог on deploy day; D2).
4. Everything else stays `off`.
`alembic check` clean; SQLite via `create_all` with the same defaults; `tests/test_migrations.py` covers the
backfill on PG with a fixture of the four cases. Neon backup branch before the merge (rule 7; delete the oldest after).

### 4.2 API
| Route | Policy | Change |
|---|---|---|
| `GET /catalog/courses` | `authenticated` | scope = listed (§2.1) |
| `GET /catalog/courses/{id}` | `authenticated` | scope = linkable (§2.2); payload gains `is_listed: bool` |
| `GET /courses/{id}` (staff) | unchanged | gains `listing: {state, requested_at, decided_at, note, content_changed}`; `unlisted_by_admin` removed |
| `PATCH /courses/{id}` | unchanged | `visibility` transitions of §2.3; the platform switch rule |
| `POST /courses/{id}/listing/request`, `.../withdraw` | `course:roster.manage` (new rows in `courses/policies.py`, inventory) | §2.3 |
| `GET /platform/catalog?state=` | `platform_admin` | admin rows (course, owner brief, teacher kind, counts, marker); five statements per page |
| `POST /platform/courses/{id}/listing/approve`, `.../decline` | `platform_admin` | note optional / required |
| `POST /platform/courses/{id}/unlist`, `.../relist` | `platform_admin` | kept; now block / relist |
| `GET /platform/teachers` | `platform_admin` | §3.2 |
| `GET /platform/organizations` | `platform_admin` | default excludes `personal`; `kind=personal` refused 422 |
| `GET /platform/overview` | `platform_admin` | tile `catalog_pending: int` |
Errors (`courses/ids.py`): `listing_incomplete` 422 (details: missing items), `listing_state` 409 (wrong transition),
`listing_blocked` 409, `listing_rate_limited` 429, `listing_note_required` 422. Rate-limit keys in `core/ratelimit.py`.
The note never appears in student payloads, logs, audit details (only its length) or exports.

### 4.3 i18n (en, ky, ru; parity script)
`catalog.listing.{title,off,pending,listed,declined,blocked,request,withdraw,resend,incomplete.*,linkAccess,
linkAccessHint,previewNote}`, `platformAdmin.catalog.{title,tabs.*,columns.*,approve,decline,declineNote,block,relist,
changedSince,empty.*,toast.*}`, `platformAdmin.teachers.{title,tabs.*,columns.*,independent,at,empty,filters.*}`,
`person.teaching.*`, `organizations.errors.personal_org_no_members` (reworded), `platformAdmin.overview.catalogPending`,
emails `email.listing.{approved,declined}.*`. Removed: `lms.errors.unlisted_by_admin`, `enrollmentForm.settings.catalog*`
(replaced by the link-access copy), `organizations.admin.anyKind` option «Личная».

## 5. Build slices, tests, rollout

| # | Slice (model) | Content | Tests |
|---|---|---|---|
| S1 | Listing state and catalog scope (Opus) | migration 0033 + backfill, model, `listing` service (`courses/listing.py`: transitions, preconditions, rate limit, audit, emails), catalog list/landing scopes, staff payload, `PATCH` visibility rules, `set_unlisted` → block/relist, admin `GET /platform/catalog` + approve/decline, overview tile; inventory rows | `tests/lms/test_catalog_listing.py`: **visibility matrix** (student, teacher of the course, other teacher, org admin, platform admin, test student × platform/personal/school course × 5 states × published/draft × org active/suspended → in list? landing? open join? code join? form apply?); state machine incl. every 409; `listing_incomplete` details; rate limit; note privacy (not in catalog/landing/home/student course payloads, audit has no text); isolation (teacher B cannot request/withdraw A's course, org admin only in own tree); platform switch sets `listed`; unpublish keeps `listing`; backfill cases on PG (`test_migrations.py`); `test_catalog.py` two-statement bound kept; `test_pg_concurrency` untouched |
| S2 | Teacher settings and admin catalog page (Opus) | settings block §2.6, link-access copy, catalog preview wording for teachers, Teaching-list link removed; `/admin/catalog` page with tabs, landing preview link, dialogs; admin overview tile; Admin → Courses buttons mapped | e2e `catalog-listing.spec.ts` (teacher requests → admin approves → student sees it; decline note visible to the teacher only; blocked course has no button), `role-links.spec.ts` (+ `/admin/catalog`, Teaching list without the catalog link), `catalog.spec.ts` (student sees platform + listed only), 375/1440/1920 ru screens |
| S3 | Admin Teachers page and organizations filter (Opus) | `GET /platform/teachers`, `/admin/teachers` with the requests tab, redirect from `/admin/teacher-requests`, organizations list without personal rows, personal detail → person page, person «Преподавание» card, audit viewer label, `personal_org_no_members` text | `tests/lms/test_platform_teachers.py` (rows per person kind, counts exclude test students and deleted courses, five statements per page, `q`, filters, authz 403 for non-admins), `test_platform_orgs_list.py` (no personal by default, `kind=personal` 422), e2e `admin-teachers.spec.ts`, `role-links.spec.ts` (independent teacher: no «организац» text) |
| S4 | Text and polish (Sonnet) | ky/en strings, empty states, emails copy, `docs/HANDOFF_NEXT_AGENT.md`, `PRODUCT_DECISIONS.md`, screenshots `CATALOG_screens/` | parity script, screenshot pass |

**Rollout without hiding courses students already have.** Enrolled students never depend on the catalog
(`courses_visible_to` joins enrolments, `scopes.py:60-65`; the home lists enrolments), so no student loses a course.
The two teacher courses in the catalog today become `pending` at migration time and vanish from the *list* until the
owner decides; their landings stay reachable by link (`visibility = catalog`), open join and codes keep working. The
orchestrator opens Admin → Каталог right after the deploy and the owner decides the two rows (or S1 ships with D2 =
grandfather, see below). ORT: unchanged rows, `listed` by backfill, D-ORG-1 test asserts the platform tree is always
listed when its switch is on. Rollback: S2–S4 are UI; S1's migration downgrade restores `unlisted_by_admin_at` from
`blocked` and sets `visibility = catalog` for `listed`/`pending`.

## 6. Owner decisions (recommendation first) and better ideas

| # | Decision | Recommendation |
|---|---|---|
| D1 | Catalog default | **Platform courses + approved teacher listings** (the owner's suggestion), as §2.1 |
| D2 | The 2 teacher courses in the catalog today | **Become `pending`**, decided by the owner on deploy day (one screen, two rows). Alternative: grandfather them as `listed` and review later: zero disruption but the catalog stays unreviewed for a while |
| D3 | Link access for unlisted courses (§2.2) | **Yes**: a teacher can share the course page without a review (like an unlisted video); forms and open join keep working; the catalog list is the only reviewed surface. Alternative: keep "private or catalog" only, then form modes need approval first |
| D4 | Independent teachers' data model | **Keep personal organizations internally, never show the word** (§3.1 A) |
| D5 | Public signed-out catalog / SEO | **Not now**; the 3c landing markets the platform exams; `GET /public/catalog` of listed courses later if wanted |
| D6 | Edits after approval | **Marker, no automatic re-review** (§2.3); automatic `pending` on edits would hide listed courses on small fixes |
| D7 | Catalog for people who teach | **Read-only preview** (already built by 1b) with a note; no join; the Teaching list link goes |
| D8 | Decline note | **Required (≤ 500), visible to course staff, emailed**; never to students |
| D9 | Admin → Преподаватели replaces the Teacher requests page URL | **Yes** (tabs Преподаватели · Заявки; the old URL redirects) |
| D10 | Listings on revoke / re-grant | **Kept** (the admin blocks individual courses when needed); alternative: revoke resets `listed` → `off` |
| D11 | Listing preconditions (`listing_incomplete`: description, cover or ≥ 1 published test/lesson) | **Yes**: keeps the owner's queue free of empty courses; the message tells the teacher what to add |

**Better ideas (beyond the brief):**
1. **Two switches instead of one** (§2.2): "open by link" is the teacher's, "in the catalog" is the owner's. It keeps
   join-by-code/link untouched, keeps enrollment forms working without review, and gives every teacher a shareable
   course page today.
2. **Admin → Преподаватели as the single list of people who teach** (independent and school teachers together, with
   the requests as a tab), instead of reading teachers off organization rows. The personal organization becomes
   invisible everywhere except the audit log.
3. **Pending listings as an overview tile**, not an email: the owner already opens Admin daily; the tile counts
   `pending` with one indexed query.
4. **Catalog card «Платформа» / teacher name only**: no "verified" badges; the fact that a teacher course is listed
   already means the owner approved it.
5. **Not recommended:** a separate `catalog_listings` table (one row per course, the state belongs on the course and
   joins would double the catalog query); automatic re-review on every edit; hiding `listing` behind `settings` JSON
   (not indexable, not checkable).
