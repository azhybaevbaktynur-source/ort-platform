# Admin → Organizations: platform-admin control of every organization (design)

Owner item 4 (2026-11-08). Design only; nothing here is built. Checked against `lms` on 2026-11-08 (head `0026_course_cover`).
Related: `docs/DISCUSSION_ADMIN_CENTER.md` (part E, A4, A5), `docs/phases/PHASE_6_DESIGN.md` §2.2–2.3, §3, `docs/phases/PHASE_9.md`.

**Summary.** Most of the item already exists: the organizations table, the detail page with suspend/resume, members, courses, departments, template grants and a per-organization log, and server-side platform-admin access to every `/org/{id}` route. What is missing: type and student/storage columns and a type filter on the table, a Students tab, an editable Settings tab, the **"Open as org admin"** button with an audit marker and an on-screen marker, and the header switcher for a platform admin inside a foreign organization. **No migration is needed.**

## 1. What exists today, what is missing

| Owner wants | Today | Gap | Where |
|---|---|---|---|
| Table: name, type, status, teachers, courses, students, storage, created | Name, status, org admins, teachers, courses, created; search on name/slug; status filter | **Type column and filter, students, storage**; departments are listed as rows next to roots (no `kind`/`depth` filter) | `backend/app/lms/platform_admin/organizations_router.py:37-46`, `organizations_service.py:14-45`, `frontend/src/app/[lang]/admin/organizations/page.tsx:33-48` |
| Counts without N+1 | Two grouped statements per page (members by role, live courses) | Add two more grouped statements (students, storage); roll departments up into their root | `organizations_service.py:27-45` |
| Detail: overview | Summary tab: tiles from `GET .../usage` (single organization, not its departments) + read-only settings disclosure | Usage must be the **subtree** roll-up (`tree_usage`) like the org-admin overview | `organizations_router.py:120-123` uses `org_svc.usage`; org admin uses `org_usage.tree_usage` (`organizations/router.py:42`) |
| Detail: teachers | Admins tab + Teachers tab (add by user id, remove with reason) | None | `OrgMembersTab`, routes `.../members` |
| Detail: courses | Courses tab (live/deleted), links to admin course page | None | `.../courses`, `OrgCoursesTab` |
| Detail: students | Nothing: students are only a number | **New endpoint + tab** | — |
| Detail: usage | Merged into Summary | Keep merged; add per-department rows (`by_department`) | `TreeUsageOut` exists for `/org/{id}/usage` |
| Detail: template grants | Templates tab (grant/revoke, audited) | None | `OrgTemplatesTab` |
| Detail: settings | `PATCH /platform/organizations/{id}` accepts `name`, `slug`, `settings` (validated, root only, audited with before/after); UI edits only name and slug | **Settings editor in the UI** (same fields as `/org/{id}/settings`) | `organizations/service.py:224-253`, `settings.py`, `frontend/.../admin/organizations/[orgId]/page.tsx:296-333` |
| Suspend / reactivate | `POST .../suspend`, `.../resume` with reason, audited; departments too | **The platform organization can be suspended today** (nothing refuses it); the UI dialog names the effect only partly | `organizations/service.py:254-268` |
| "Open as org admin" | Server side already works: `load_org_for_admin` admits `is_platform_admin` on every `/org/{id}` route; `/org/{id}` returns `my_role: null` for the admin | **No button; no audit marker; no on-screen marker**; `OrgShell` makes a suspended organization read-only for the admin too although the server allows the writes; Shared banks tab 404s for the admin by design | `organizations/service.py:151-165`, `OrgShell.tsx:85-102`, `shared_banks.py:114-126` |
| Audit as platform admin | `admin_audit_log.actor_id` is the admin; nothing says the actor was **not** a member of the organization | **`details.acting_as`** | `audit/service.py:13-33` |
| Header: switcher when the user manages > 1 organization | Exists: `/me/lms.admin_organizations` (org-admin memberships, personal excluded, ≤ 100) → one pill, or a pill with choices and the `/org` picker | The platform admin inside a foreign `/org/{id}` has no active choice and no "platform admin" marker | `teachers/service.py:29-48`, `LmsShell.tsx:165-196`, `org/page.tsx` |

Verified facts used below: `is_org_admin` walks the ancestor path (`tree.is_org_admin_in_tree`); `can()` lets the platform admin through a suspended organization (`core/authz.py:112-113`); a student with an open attempt may finish it in a suspended organization (`DISCUSSION_ADMIN_CENTER.md` §3 correction); the platform organization has the fixed id `platform_org_id()` and `kind = 'platform'` (`organizations/ids.py`, `defaults.py:31-42`); `make_admin.py` and `admins.py` give every platform admin an `org_admin` membership in the platform organization, so the Organization area already shows it to them.

## 2. Design

### 2.1 List: `GET /platform/organizations` (extended, same route)

| Parameter | Values | Rule |
|---|---|---|
| `q` | ≤ 100 chars | As today: `lower(name) LIKE` / `lower(slug) LIKE` (escaped). Also matches an org-admin **email prefix**? No: keep name/slug (email search lives in Users). |
| `status` | `active` / `suspended` | As today |
| `kind` | `school` / `personal` / `platform` | New. Default **roots only** (`depth = 0`): departments never appear as rows (they are inside their school). `kind=department` is refused (422). |
| `sort` | `created_desc` (default) / `name_asc` | Keyset as today (`paginate_rows`, `sort_col` + `id` tiebreak); `name_asc` sorts on `lower(name)` with `id` tiebreak. |
| `cursor`, `limit` | `clamp_limit` (default 25, max 100) | Never a full scan; the page query is `SELECT organizations WHERE deleted_at IS NULL AND depth = 0 [AND filters] ORDER BY … LIMIT n+1`. |

**Row** `OrganizationAdminRowOut` gains `students: int`, `storage_bytes: int`, `departments: int`. Every count is a **subtree roll-up keyed by the root segment** `substr(path, 1, 32)` (a root's path is its own id), so a school's departments count into the school. Exactly **five grouped statements per page**, each with `WHERE root_hex IN (:page_roots)`:

| Count | Statement (one per page) |
|---|---|
| `org_admins`, `teachers` | `SELECT substr(o.path,1,32), m.role, count(DISTINCT m.user_id) FROM organization_members m JOIN organizations o ON o.id = m.organization_id WHERE m.state='active' AND o.deleted_at IS NULL AND substr(o.path,1,32) IN (…) GROUP BY 1, 2` |
| `courses` | `SELECT substr(o.path,1,32), count(*) FROM courses c JOIN organizations o … WHERE c.deleted_at IS NULL AND c.sandbox_for_template_id IS NULL … GROUP BY 1` |
| `students` | `SELECT substr(o.path,1,32), count(DISTINCT e.user_id) FROM enrollments e JOIN courses c ON c.id = e.course_id JOIN organizations o … WHERE e.role='student' AND e.state='active' AND e.is_test_student IS FALSE AND c.deleted_at IS NULL AND sandbox IS NULL … GROUP BY 1` |
| `storage_bytes` | `SELECT substr(o.path,1,32), sum(a.bytes) FROM assets a JOIN organization_members m ON m.user_id = a.owner_id AND m.state='active' JOIN organizations o … WHERE a.deleted_at IS NULL … GROUP BY 1` — owner-based approximation, same definition as `tree_usage` (a user in two organizations counts in both; documented in the UI tooltip `organizations.usage.storageNote`). |
| `departments` | `SELECT substr(o.path,1,32), count(*) - 1 FROM organizations o WHERE o.deleted_at IS NULL AND substr(o.path,1,32) IN (…) GROUP BY 1` |

Indexes already cover these: `ix_courses_organization_id_status_deleted_at`, `ix_enrollments_course_id_role_state`, `ix_assets_owner_id_created_at`, `ix_organization_members_user_id_state`, `ix_organizations_path` (pattern ops). `substr(path,1,32)` on ≤ 100 rows of a page is cheap; no new index. Implementation: one helper `root_hex(col) = func.substr(col, 1, 32)` in `organizations/tree.py`, reused by `tree_usage`.

### 2.2 Detail endpoints (prefix `/platform/organizations/{id}`)

| Route | Change | Notes |
|---|---|---|
| `GET /` | Row with the five counts (same `admin_rows`, one organization) + `is_protected: bool` (`kind == 'platform'`) | UI hides Suspend for a protected organization |
| `GET /usage` | Returns `TreeUsageOut` (subtree + `by_department`, + `course_files_bytes`) instead of the single-organization `usage()` | Reuse `org_usage.tree_usage`; `UsageOut` stays a subset, so the frontend type only gains fields |
| `GET /students` **new** | `PageOut[OrgStudentOut]`: `user: UserBrief`, `courses: int`, `first_enrolled_at`, `last_active_enrollment_at`. One statement: aggregate subquery over active student enrollments in the subtree's live courses, `GROUP BY user_id`, joined to `users`; keyset on `(lower(display_name), user_id)`; `q` on name/email prefix (≤ 100). Links to the person page `/admin/users/{id}`. | No age, consent, phone or form answers here (minors; `PHASE_9.md` privacy). The person page already shows what the admin may see. |
| `GET /courses` | Add `q` (title) and `status` filter; counts stay in the row | Existing `org_courses_query` |
| `PATCH /` | Unchanged API; `kind == 'platform'`: `slug` change refused 409 `platform_org_protected` | Settings editing is UI work (§2.6) |
| `POST /suspend` | `kind == 'platform'` → 409 `platform_org_protected`. Response adds `affected: {courses, students, departments}` (the row counts) so the dialog names the effect; the UI shows it before confirm via `GET /`. | See §2.3 |
| `POST /resume` | Personal organization of a user whose `teacher_status == 'revoked'` or `disabled_at` set → 409 `owner_not_eligible` (resuming it would silently re-enable a revoked teacher; the right path is "grant teacher" on the person page, which calls `ensure_personal_org`). | `organizations/service.py:168-193` |
| `GET /members`, `POST /members`, `DELETE /members/{uid}`, `GET /departments`, `GET/PUT/DELETE /templates…` | Unchanged | |

Every new/changed route is added to `platform_admin/organizations_policies.py` with policy `platform_admin` (route inventory test).

### 2.3 Suspend / reactivate semantics (what already holds, made explicit)

| Who | Suspended root or department (inherited down the `path`) |
|---|---|
| Students | Courses stay listed on Home and in course lists; results and content readable (`READ_ONLY_ACTIONS`); **no attempt start, no hand-in, no join** (join by code answers like a wrong code; catalog hides the courses, `scopes._catalog_select`); an **open attempt may be finished and submitted** (attempts do not check organization status: kept, it is the safe behaviour). |
| Teachers | Everything read-only (`can()` refuses every non-read action with 403 `organization_suspended`); no course creation, no bank writes, no imports, no invitations (`invitations/service.py:164`, `roster.py:297`). |
| Org admins | `/org/{id}` opens with the amber banner, all writes 403 (`load_org_for_admin(write=True)`); settings, departments, moves refused. |
| Platform admin | Reads and writes everywhere (`load_org_for_admin` skips the check for `is_platform_admin`; `can()` too). |
| Catalog / landing | Courses of the organization **and of its departments** vanish (root status joined, `scopes.py:95-103`). |
| Resume | Clears `suspended_at`, `suspended_reason`; everything above reverses at once; nothing else changes (enrollments, attempts, grades untouched). |

**Invariants added by this design**
1. The **platform organization is never suspended** (`kind == 'platform'` → 409 `platform_org_protected`, enforced in `set_suspended`, not only in the route). Reason: the two ORT courses and every platform-owned paid exam live there; a suspension would pull ORT out of the catalog and block every attempt start (rule 6.9).
2. `ensure_platform_org` (lifespan bootstrap) is insert-only and never resets `status`: fine, but a test asserts the platform organization stays `active` after `set_suspended` is refused.
3. A personal organization can be suspended by the admin (it is how a revoke works today); resuming one is allowed only when the owner is still an eligible teacher (§2.2).

### 2.4 "Open as org admin"

**Authorization (server).** No new mechanism. Every `/org/{id}/**` route resolves `load_org_for_admin(db, user, id)`: active org admin of the organization or an ancestor, **or `users.is_platform_admin`** read from the row loaded by `get_lms_user` on this request. Nothing is passed from the client: no header, no query flag, no JWT claim. Audit: `test_organizations_authz.py::test_org_admin_routes` already covers the admin path for the Phase 6 routes; this item adds a sweep over every `org_admin`-policy route in the inventory (§3).

Routes a platform admin **cannot** use inside `/org/{id}` and why (kept):

| Route | Answer | Reason |
|---|---|---|
| `GET /org/{id}/shared-banks*` | 404 (`shared_banks.reader_root`) | Content reading by the admin is decision A4 (needs reason + record) and is not part of this item. The org shell hides the Shared banks nav item when `acting_as == 'platform_admin'`. |
| `GET /org/{id}/analytics/*` | Allowed (uses `load_org_for_admin`) | Aggregates, no answers |
| Writes into a **suspended** organization | Allowed | Platform admin bypass by design; the shell shows the suspended banner but keeps actions enabled for the admin (today it disables them: `OrgShell.tsx:85`). |

**Audit.** `GET /org/{id}` gains `acting_as: "org_admin" | "platform_admin"` (derived: `is_org_admin(...)` → `org_admin`, else the caller must be the platform admin). Every org-scoped write records the same word: `audit.record(..., details={..., "acting_as": acting_as})`. Implementation: one helper `org_svc.acting_as(db, user, org) -> str` (one SQL: `is_org_admin`, ancestor-aware; `"platform_admin"` only when the caller is not an admin of the tree and `user.is_platform_admin` is set). `load_org_for_admin` calls it once and returns it as a second value (`org, acting = load_org_for_admin(...)`), so the org routers pass it into the services that write audit rows: `organizations/service.py`, `invitations/service.py`, `organizations/roster.py`, department writes in `tree.py`/`service.py`, org-admin course creation in `courses/service.py`, org-scoped exam-template writes. Services keep an `acting_as: str = "org_admin"` keyword default so no other caller changes. The `platform_admin/*` routes write `acting_as: "platform_admin"` always. Rule: **`acting_as` is computed from DB memberships at write time, never from the UI.** `AuditTable` shows a small neutral badge "as platform admin" when `details.acting_as == 'platform_admin'`; the audit log gets a filter `acting_as` (query parameter on `GET /platform/audit-log`, `details->>'acting_as'` on PG, `json_extract` on SQLite, both via `JSONType` helpers already used for `details.organization_id` filtering in the per-organization Log tab).

**UI marker (acting as platform admin).** In `OrgShell`, when `org.acting_as === 'platform_admin'`:
- a persistent strip under the header (brand-tinted, not amber: amber stays for "suspended"): "You are viewing {org} as platform admin. Actions are recorded as platform admin." with a link "Back to Admin → Organizations";
- the area label in the shell's sidebar reads "Organization · platform admin";
- the browser tab title gets the same suffix;
- the Shared banks nav item is hidden; the Suspended banner stays but `readOnly` is `org.status === 'suspended' && org.acting_as !== 'platform_admin'`.

**Button.** Detail page header, secondary button "Open as org admin" → `/{lang}/org/{id}`; disabled with a tooltip for a personal organization whose owner is disabled (nothing to manage) — otherwise always enabled. The log tab shows the admin's actions like any other (they are, with the badge).

### 2.5 Header organization switcher

| Case | Today | Design |
|---|---|---|
| User administers 1 organization (memberships, personal excluded) | One "Organization" pill → `/org/{id}` | Unchanged |
| User administers 2+ | Pill "Organizations" with a dropdown of choices (desktop) / list (phone) + `/org` picker | Unchanged; `/org` picker already redirects when exactly one |
| Platform admin | Member of the platform organization → pill "Organization" → platform org | Unchanged for memberships. **Plus:** while the URL is `/org/{id}` and `id` is **not** in `admin_organizations`, the Organization pill shows that organization as the active choice with the label "{name} · platform admin". The name comes from `OrgShell`'s loaded `GET /org/{id}` through a tiny client store (`frontend/src/lib/lms/currentOrg.ts`, `useSyncExternalStore`; set/cleared by `OrgShell`), so the header makes no extra request. The dropdown also lists "All organizations → Admin" linking to `/admin/organizations`. |
| Where the selection lives | URL `/org/{orgId}` | Unchanged: no cookie, no local storage; the URL is the state. |

`admin_organizations` stays membership-based (≤ `ME_ORGANIZATIONS_MAX = 100`); the platform admin never gets every organization in the header (hundreds of rows do not belong in a menu): they pick in Admin → Organizations.

### 2.6 Frontend pages

| Page | Change |
|---|---|
| `/admin/organizations` | Columns: Name (+ slug muted), **Type** (badge: School / Personal / Platform), Status, Teachers, Courses, **Students**, **Storage** (bytes formatter from `storage.units`), Created. Filters: search, Status, **Type**; sort toggle Created / Name. Departments count shown as "+ N departments" under the name when > 0. |
| `/admin/organizations/[orgId]` | Header: name, type badge, status, "Edit", **"Open as org admin"**, more-menu Suspend/Resume (hidden when `is_protected`). Tabs: Summary (tiles from `TreeUsageOut`, per-department table), Admins, Teachers, Courses (+ search/status), **Students** (new), Departments, Templates, **Settings** (new: the same form as `/org/[orgId]/settings`, posting `PATCH /platform/organizations/{id}` `{settings}`; disabled with a note for a department: "Settings live on the root"), Log (+ `acting_as` badge). |
| `OrgShell` | `acting_as` strip, label, hidden Shared banks, `readOnly` rule, `currentOrg` store. |
| `LmsShell` / `AppHeader` | Active foreign-org choice (§2.5). |
| `AuditTable` | `acting_as` badge; audit-log page filter. |
| i18n | New keys in `en.json`, `ky.json`, `ru.json` under `organizations.admin.*`, `organizations.kind.*`, `organizations.org.actingAsPlatformAdmin*`, `platformAdmin.audit.actingAs*`, error codes `platform_org_protected`, `owner_not_eligible`. Parity script must pass. |

### 2.7 Migration

**None.** `organizations.status` (`active`/`suspended`), `kind`, `path`, `depth`, `suspended_at/_reason` already exist (migrations 0008, 0014); `admin_audit_log.details` is JSON, so `acting_as` needs no column; no new table, index or constraint. `alembic check` stays clean because no model changes. If a later item wants an "archived" status, that is its own migration (CHECK `status_valid` would need widening) — explicitly out of scope here.

## 3. Security review of the authorization changes

| # | Point | Verdict / requirement |
|---|---|---|
| S1 | Platform-admin access to `/org/{id}` | Already server-side from `users.is_platform_admin` loaded per request (`get_lms_user`); nothing new is trusted from the client. The button is navigation only. |
| S2 | `acting_as` | Derived in the service from `OrganizationMember` rows (ancestor-aware) at write time; written into `details`, not into a column, and never read back for permission decisions. A test asserts a forged request body/header cannot set it. |
| S3 | New `GET /platform/organizations/{id}/students` | Policy `platform_admin` (inventory + `require_platform_admin` → MFA gate when `ADMIN_MFA_REQUIRED`). Payload: `UserBrief` + counts only. Isolation test: an org admin of A gets 403 on it; via `/org/A/**` no route lists B's students (no student route exists on `/org`; stays so). |
| S4 | Platform organization guard | In `set_suspended` (service), so the roster/other callers cannot bypass it through a different route. Test: suspend → 409, row still `active`, ORT courses still in the catalog. |
| S5 | Resume of a personal organization | Refused for a revoked/disabled owner (otherwise an admin could, by mistake, re-enable a revoked teacher's course creation without the teacher-grant path and its audit row). |
| S6 | Counts queries | Parameters are page ids only (`IN (:roots)`), no user text in the grouped statements; `q` goes through `like_escape`. `limit` clamped at 100. |
| S7 | No role column | Nothing adds one; `kind` is a property of the organization, not of a user. |
| S8 | Suspended-organization bypass widened in the UI only | The server already allowed it; enabling the buttons for the admin changes nothing server-side. Each such write carries `acting_as: platform_admin`. |
| S9 | Tests isolation (`tests/lms/isolation.py`) | No new tables → `reset_lms_state` needs no change; `admin_audit_log` is already truncated. |
| S10 | Request logs | Unchanged (`user_id` only); `acting_as` is not logged there. |
| S11 | Shared banks for the admin | Stays 404 (content reading is A4, separate decision); the shell hides the link so the admin does not hit a dead end. |

## 4. Implementation slices

| Slice | Content | Files | Model | Tests |
|---|---|---|---|---|
| **A. Backend list + counts** | `kind`, roots-only default, `sort`; `admin_rows` with five root-keyed grouped statements; `students`, `storage_bytes`, `departments` in the row; `tree.root_hex`; `GET /usage` → `tree_usage`; `GET /courses` `q`/`status` | `backend/app/lms/platform_admin/organizations_service.py`, `organizations_router.py`, `organizations_policies.py`, `backend/app/lms/organizations/schemas.py`, `tree.py`, `usage.py` | Opus | `tests/lms/test_platform_orgs_list.py`: filters, roots only, `kind=department` 422, counts roll up departments, **exact statement count per page** (SQLAlchemy event counter, as `test_helpers_one_query_each`), cursor stability on `name_asc` ties |
| **B. Backend guards + students + acting_as** | `platform_org_protected`, `owner_not_eligible`; `GET /students`; `acting_as` in `GET /org/{id}` and in every org-scoped audit write; audit-log `acting_as` filter | `organizations/service.py`, `organizations/router.py`, `invitations/service.py`, `organizations/roster.py`, `courses/service.py` (org-admin create), `exam_templates` org writes, `platform_admin/router.py` + `users_service.audit_stmt`, `platform_admin/organizations_router.py` | Opus | `tests/lms/test_platform_orgs_control.py`: platform org suspend 409 + ORT still in catalog; personal resume rules; students page isolation (S3); `acting_as` for member vs. admin on `remove_member`, `patch_settings`, `create_department`, invitation create; forged `acting_as` ignored; inventory test green; `test_org_isolation.py` extended with the students route |
| **C. Admin UI** | Table columns/filters/sort; detail header with "Open as org admin"; Students tab; Settings tab (reuse the org settings form component); Summary per-department table; Log badge; audit-log filter | `frontend/src/app/[lang]/admin/organizations/page.tsx`, `[orgId]/page.tsx`, `frontend/src/components/lms/org/admin/*`, `components/lms/admin/AuditTable.tsx`, `frontend/src/lib/lms/organizations.ts`, i18n ×3 | Opus (data wiring, routing), Sonnet (table styling, texts in three languages) | `tsc`, parity script; e2e smoke in `frontend/e2e/org-admin.spec.ts` (admin opens a school as org admin, sees the strip, performs one audited action, badge visible in Log) |
| **D. Org shell + header** | `acting_as` strip/label/readOnly rule/hidden Shared banks; `currentOrg` store; header active foreign-org choice + "All organizations" link | `frontend/src/components/lms/org/OrgShell.tsx`, `frontend/src/components/lms/LmsShell.tsx`, `frontend/src/components/ui/AppHeader.tsx`, `frontend/src/lib/lms/currentOrg.ts`, i18n ×3 | Opus (store, header logic), Sonnet (strip styling, texts) | `tsc`; e2e in the same spec; UX check 375/1440/1920 ru (rule 6.10) on `/admin/organizations`, the detail page, and `/org/{id}` as admin |
| **E. Docs + gate** | `docs/phases/ADMIN_ORGS.md` (what shipped), `PRODUCT_DECISIONS.md` (D-ORG-1..3 below), `HANDOFF_NEXT_AGENT.md`; ORT parity gate (importers diff, e2e `ort`, screenshots) | docs | Sonnet | Full SQLite suite; PG suite + `alembic check` (no migration expected) |

Order A → B → C → D → E; A and B can run in parallel (different files except `organizations/schemas.py`: A owns it). C depends on A+B; D on B.

## 5. Decisions to record (`PRODUCT_DECISIONS.md`)

| # | Decision | Default |
|---|---|---|
| D-ORG-1 | The platform organization cannot be suspended. | Yes (rule 6.9: ORT must not change) |
| D-ORG-2 | A platform admin inside `/org/{id}` keeps full org-admin powers, including in a suspended organization; every write is recorded with `acting_as: platform_admin`; no shared-bank content (A4 pending). | Yes |
| D-ORG-3 | The header never lists every organization for the platform admin; Admin → Organizations is the entry point; the current foreign organization appears as the active choice while open. | Yes |
| D-ORG-4 | The Students tab shows name, email and counts only; everything else stays on the person page. | Yes |
| D-ORG-5 | Resuming a personal organization whose owner is revoked or disabled is refused (use "grant teacher"). | Yes |

## 6. Open questions

1. Storage per organization is owner-based (members' assets) as everywhere else today; a member of two organizations counts twice. Exact attribution needs `assets.organization_id`, which is a migration and a backfill: not in this item.
2. `name_asc` keyset sorts on `lower(name)`; two organizations with the same name order by id. Acceptable.
3. Whether the "acting as platform admin" strip should also appear inside course pages the admin opens from the organization (course routes use `can()`, not `load_org_for_admin`): proposed no; the course pages already show the admin's read-only role.
