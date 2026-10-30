# Phase 8c design: teacher navigation redesign (course sidebar, course page, one page per object, Student view)

**Status**: architect draft 2026-10-31 (Fable), base `origin/lms` 5bf0861 (8b deployed + approved proposal v3). Binding: `PHASE_8C_NAVIGATION_PROPOSAL.md` decisions 8c-1…8c-8 and §7 review notes; `PRODUCT_DECISIONS.md` (8c, 8a, 8b); `IMPLEMENTATION_PLAN.md` Phase 8c; `UX_GUIDELINES.md`. Precedent: `PHASE_8A_DESIGN.md`. Owner update 2026-10-31: **no pause for a teacher test**; S2–S4 run straight after S1, one release after S4; the teacher-test script (§16) is an optional check whose findings become a follow-up slice.

---

## 1. Scope and non-goals

In: a short left course sidebar for staff and students (phone drawer), auto-hide of empty areas for students, removal of the Teaching sub-menu inside courses, a teacher Course page = modules outline + "Unsorted" + To do panel with the grouped "+ Add" menu and lighter row controls, removal of the Tests list (quiz filter in Assignments), one page with tabs for assignments and pages, a read-only Student view, redirects for old URLs, new ORT frame baselines. Mostly frontend; backend adds three read endpoints and one module duplicate endpoint (§7). **No migration** (§6.3).

Out: Settings → Navigation (hide/reorder links), Reports (none exist; Phase 10), a test-student account (§6), module copy between courses, any change to the ORT player, bank, builder, import, result content (§11), any change to the 7c quiz editor beyond a Close target (§5.3), announcement or file features.

### 1.1 Invariants

1. Navigation is computed from `CourseOut` (role, `features`, `home_kind`, template) on the client; the server stays authoritative for every list (a hidden link hides nothing the server would return).
2. Student view never writes: no `module_progress`, `item_progress`, `submissions`, `attempts` (other than `is_preview`), audit or enrollment row is created or changed by a request carrying `X-View-As: student`.
3. The header downgrades only a real `teacher|assistant` role; students, org admins, platform admins and sandbox staff are unaffected (the header is ignored, never an error).
4. Every student-shaped payload in Student view is produced by the same serializer a student gets (8a invariant 9 applies unchanged).
5. Every old URL in §4.2 resolves to a working page for every role; no 404 is introduced by this phase.
6. ORT content screens are byte-identical in DOM inside the content region; only the frame around them changes (§11).
7. Every object page can be closed with one control that leads to a validated same-site path (§5.3).
8. The outline remains one document (8a caps); Unsorted and To do are paginated or capped (`LIMIT`) and never load a whole course's submissions.

---

## 2. Shell (S1)

### 2.1 Sidebar component

`components/lms/course/CourseSidebar.tsx`, built on the existing `AreaShell` (`components/ui/AreaShell.tsx`: side nav from `md`, 224 px, active bar, counts). `AreaShell` gains `phone: "tabs" | "drawer"` (default `tabs`, so the admin and org areas do not change). In `drawer` mode phones (< `md`) show one full-width button "Course menu · *Active link*" (`aria-expanded`, `aria-controls`) that opens a left sheet (`Dialog` primitives: focus trap, Esc, backdrop) listing the links; choosing a link closes it. The course layout (`app/[lang]/courses/[courseId]/layout.tsx`) wraps `children` in `<CourseSidebar>` for every role except: sandbox courses (unchanged: no frame) and **`/attempts/**`** (player and result pages: the player is already `fixed inset-0`; the result and review pages keep today's full-width column so the ORT `result`/`review` baselines stay pixel-identical, §11). The old `CourseTabs` and `StudentCourseTabs` are deleted.

### 2.2 Links and active-state rules (`base = /{lang}/courses/{id}`)

| # | Link | Href | Who | Active when `pathname` … |
|---|---|---|---|---|
| 1 | Course | `base` | all | `=== base`; staff also `/modules`, `/pages/**` (pages are reached from the course page); students on `home_kind = page` also `/pages/{home_page_id}` |
| 2 | Announcements | `base/announcements` | all (students: `features.announcements`) | starts with `/announcements` |
| 3 | Assignments | `base/assignments` | all | starts with `/assignments`, `/assessments` (quiz builder, lobby, attempts list, ORT builder) or `/attempts` (staff attempt detail reached from results) |
| 4 | Grades | `base/grades` | all | starts with `/grades` |
| 5 | People | `base/people` (students: label "Teachers", as today) | all | starts with `/people` |
| 6 | Question banks | `base/bank` | teacher, assistant | starts with `/bank` |
| 7 | Settings | `base/settings` | teacher | starts with `/settings` |
| 8 | Files | `base/files` | staff always; students: `features.files` | starts with `/files` |

Students: `/modules` keeps Course active (`home_kind = modules`) or Course too when reached from the home page strip; `/pages/{id}` keeps Course active (pages open from modules). Org admins (read-only observers) get the student list plus Question banks hidden, Settings hidden. The list is one function `courseNavItems(course, role, pathname, t)` with a unit test table over every route in `app/[lang]/courses/[courseId]/**` (§14).

**Files decision (recommendation, default in effect)**: keep Files as the eighth link for staff. Reason: 8a built a per-course library with folders, quota bar and trash that has no other home; without the link the only way to the quota and the trash is the "+ Add → file" picker. Students see it only with published files (auto-hide), so student menus stay at 5–6 links. Revisit at the S4 UX review; demoting it means moving the upload dialog and quota bar into the Unsorted group header (one-day change, no backend).

### 2.3 Auto-hide and the "not available" page

Flags come from the existing `CourseOut.features {modules, files, announcements}` (8a, three EXISTS); nothing new is needed for the eight links. Students: links 2 and 8 appear only when their flag is true. Staff see every link; a link whose flag is false carries an `EyeOff` icon with `aria-label`/tooltip "Hidden from students: no published content" (`courseNav.hiddenFromStudents`), and a short help line under the sidebar: "Links marked ⊘ are hidden from students until something is published." Students opening a hidden area by URL (`/announcements`, `/files` with the flag false) get `AreaUnavailable` (`EmptyState` variant: "Not available yet. Your teacher has not published anything here." + "Back to course"), rendered by the layout before the page, so the list components never run for them. The server already returns only published rows, so this is a courtesy page, not a security boundary.

### 2.4 Course title line and Student view button

`StaffCourseBar` keeps the "My courses ›" crumb, the title, the status and template badges and gains a right-aligned secondary button **"Student view"** (`Eye` icon; teacher and assistant; hidden in sandbox courses). On the Course page the bar's title is the page `<h1>`; on every other page it is a link as today and the page owns its `<h1>`. In Student view (§6) the whole frame switches to the student frame (`StudentCourseHeader` + student sidebar) under a sticky amber banner "You are viewing this course as a new student would. Nothing you do here is saved. · **Leave student view**" (`role="status"`).

### 2.5 Teaching sub-menu removal, Trash, Reports

`AreaDeclareContext` value becomes `{ area, hideSections }`; the course layout declares `{ area: "teaching" | "learning", hideSections: true }`, and `LmsShell` passes `sections` to `AppHeader` only when not hidden (desktop second row and phone menu both). Outside courses the Teaching row (Courses · Create · Grading schemes · Exam templates) is unchanged. **Trash**: no link. Deleted assignments keep the "Show trash" toggle in Assignments, deleted pages the checkbox in `/pages`, deleted modules the "Deleted" section of the outline, deleted courses `/courses/trash` (Teaching area). **Reports**: nothing exists; no placeholder link; Phase 10 adds a Settings sub-page or a ninth link (hidden for students) if needed.

---

## 3. Course page for teachers (S2)

### 3.1 Layout

Route `app/[lang]/courses/[courseId]/page.tsx`, staff branch → `TeacherCoursePage` (`components/lms/course/TeacherCoursePage.tsx`): desktop `lg:grid lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-8`; left the outline, right the To do panel (`lg:sticky lg:top-6`). Below `lg` the To do panel collapses to one line above the outline (§3.5). No dashboard cards, no "Next step" text, no About card (the description lives in Settings). `StaffCourseHome.tsx` is deleted; `teaching.nextStep*`/`teaching.createAssessment` keys are removed. The staff `/modules` route redirects to the Course page (§4.2); students keep `/modules`.

### 3.2 Outline (reuse)

`ModuleOutlineEditor` is refactored, not rewritten: it loses its own `PageHeader` (prop `embedded`), keeps `GET _C/modules` (one document, 100 modules × 200 items cap from 8a), dialogs (`OutlineDialogs`), warnings, prerequisites, requirement picker, progress drawer, re-apply, the deleted section. Toolbar above the modules: "New module" (primary), "Expand all / Collapse all", and for empty courses the 8a empty state with "New module" and "Add existing items" (opens the Unsorted group). Module cards are collapsible (`<details>`-like, state in `sessionStorage` per course).

### 3.3 "+ Add" per module

One `MenuButton` "+ Add" in each module header and after the last item. Groups and order (most used first inside each group):

| Group | Items | What happens |
|---|---|---|
| Content | Page · File · Link · Header | `AddItemDialog` opens with `initialKind` preselected and the kind radio hidden. **Page**: picker of existing pages plus "New page" → `/pages/new?module={mid}&from={course}`; on save `PageEditor` calls `POST _C/modules/{mid}/items {kind: page}` then returns to `from#m-{mid}`. **File**: picker plus "Upload" (the 8a upload dialog inline; after upload the item is added). **Link**, **Header**: as today. |
| Assessment | Quiz · Assignment | **Quiz**: title + languages (as today's "New quiz" radio) → `POST _C/modules/{mid}/quiz` → `router.push(/assessments/{assessment_id}/edit?from=/{lang}/courses/{id}%23m-{mid})`; the 7c editor's Close returns there (§5.3). **Assignment**: picker of existing assignments plus "New assignment" → `AssignmentEditorDialog` (exists) → item added → `/assignments/{id}?tab=settings&from=…`. |

ORT courses: the Assessment group shows "ORT exam" (opens the existing `CreateAssessmentDialog` with the ORT presets, then adds the item) instead of "Quiz" (7a: non-quiz assignments stay out of ORT courses; `assignments.service` already refuses them with 409). Nothing in the ORT builder changes.

### 3.4 "Unsorted" group

Last group of the outline, always present for staff (collapsed when empty with "Everything is in a module"). It holds **live targets no live item of a live module references**: (a) assignments of every kind (quizzes included; ORT preset exams included only in general courses, since ORT courses show the exam list instead, §3.7), (b) pages, one row per `translation_group_id` with language chips, (c) course files. Not counted: announcements, headers, links, deleted targets, targets referenced only from deleted modules or deleted items (they are invisible to students, so they are unsorted). Each row: kind icon, title, draft badge, "⋯" menu with "Move to module…" (`AddItemDialog` in move mode: pick a module and position → `POST _C/modules/{mid}/items`), "Open", "Delete". Data: `GET _C/modules/unsorted` (§7.1), 20 rows per kind with "Show more" per kind; the group header shows the three totals and links "All pages" (`/pages`) and "All files" (`/files`).

### 3.5 To do panel

`GET _C/todo` (§7.2). Sections, each omitted when empty: **To grade**: up to 10 assignments with `needs_grading > 0`, oldest waiting first, each a link to `/assignments/{id}?tab=submissions&filter=to_grade` (never to Grades), plus "N more" → `/assignments?needs_grading=1`. **Drafts**: up to 10 unpublished assignments/quizzes (link to the object page, quizzes to `/assessments/{aid}/edit`) and the count of unpublished modules (link scrolls to the first). **Join code** (teacher only): `JoinCodeDisplay` + the inactive hint as today, "Manage enrollment" → Settings. **Students**: "N active students" → People. Phones: one line `"{toGrade} to grade · {drafts} drafts"` as a button (`aria-expanded`) that expands the panel in place; the line shows "Nothing to do" when both are zero. The panel refreshes on focus and after grading actions (`router.refresh` is not needed: the panel owns a `reload`).

### 3.6 Lighter controls (per module and per item row)

| Control | Replaces | Behaviour |
|---|---|---|
| Publish icon (`IconButton`: filled green `CircleCheck` = published, dashed `Circle` = draft) | `Switch` | Click toggles `PATCH … {published}`; `aria-pressed`, `aria-label` "Published / Draft: *title*", tooltip. Publishing a module with unpublished targets keeps the 8a `publishWarn` dialog. Color is never the only signal (icon shape differs). |
| One "⋯" menu | up/down `IconButton`s + "Actions" menu | Module: Edit settings · Prerequisites · Duplicate · Move up · Move down · Reapply rules · Student progress · Delete. Item: Edit · Requirement · Move up · Move down · Move to… · Open / Edit quiz · Delete. |
| Drag handle (`GripVertical`, pointer devices ≥ `lg`) | — | Native HTML5 drag and drop (no new dependency): modules → `PUT _C/modules/order`; items within a module → `PUT …/items/order`; across modules → `PUT …/items/{iid}/move`. Keyboard, phones and assistive tech use the menu's Move entries. Optimistic reorder, revert on error with a toast. |

Result: about 2 visible controls per row (publish icon, "⋯") plus the handle on desktop. The 8a e2e selectors `modules.editor.actions` (menu button label) and `modules.editor.addItem` keep their keys (§12).

### 3.7 Student course page and ORT courses

Students: unchanged (8c-8): `home_kind` `modules` → `StudentModulesView` (fallback to `StudentCourseHome`), `page` → `PageView`, `assignments` → `StudentCourseHome`. ORT courses (`templateUi(course).locked && key === "ort"`): the teacher Course page shows **today's exam list** (`StaffAssessmentList` moved, not rewritten: same component, same create dialog with ORT presets, same publish flow, `?new=1` honoured) with the To do panel, and below it a collapsed "Course structure" section with the outline editor (8a-Q5 allows modules in ORT courses). The exam list's screen content is byte-identical; only the frame around it changes.

---

## 4. Removal of the Tests list and redirects (S1 for the shell, S4 for the rest)

### 4.1 Where things go

Quizzes live in Assignments (`StaffAssignmentList` already has the kind filter; it becomes URL-driven: `?kind=quiz|text|file|none`, `?published=yes|no`, `?category=`, `?needs_grading=1`, `?new=quiz|text|file|none`) and in Modules. "New" in Assignments opens `AssignmentEditorDialog` (kind preselected from `?new=`); in ORT courses the list keeps hiding "New" (`ortOnly`) and the ORT exam is created from the Course page. Entries into `assessments/*` that stay: `/assessments/{aid}/edit` (7c quiz editor and the ORT section builder, reached from the assignment row, the module item menu "Edit quiz" and the Course page), `/assessments/{aid}` (students: lobby; staff: detail with publish panel and versions, reached from the quiz's Details tab "Publishing"), `/assessments/{aid}/attempts[/{attemptId}]` (results, reached from the quiz's Results tab, §5.2). `StaffAssessmentList` survives only inside the ORT Course page; `StudentAssessmentList` is deleted (students had the Assignments entry since 7a).

### 4.2 Redirects (one mechanism: route-level, in the old route's `page.tsx`)

All course pages are client components with role-dependent targets, so every redirect is a `router.replace` in a tiny client page after `useCourse()` (one render of `LoadingState`), never `next.config` (it cannot see the role and would also catch `/assessments/{id}`). Query strings are carried over.

| Old URL | New URL | Who |
|---|---|---|
| `/assessments` | `/assignments?kind=quiz` | all roles |
| `/assessments?new=1` | general: `/assignments?new=quiz`; ORT: `/` (Course page, exam list) + `?new=1` | staff |
| `/modules` | `/` (Course page) | staff only; students and org admins keep `/modules` |
| `/assignments/{id}/edit` | `/assignments/{id}?tab=settings` | staff |
| `/assignments/{id}/grade` | `/assignments/{id}?tab=submissions` (+ `filter`) | staff |
| `/assignments/{id}` | unchanged for students; staff now land on the object page (today's `router.replace` to `/edit` is removed) | — |
| `/pages/{id}/edit` | `/pages/{id}?tab=edit` | staff |
| `/pages/{id}` | staff: object page (default tab `edit`); students: `PageView` as today | — |

No other "Tests" path ever existed. The old route files stay as redirect stubs for one phase (removed in Phase 9 kickoff); `useTabCrumbs("assessments", …)` callers switch to the Assignments crumb.

---

## 5. One page per object (S3)

### 5.1 Assignment `/assignments/{id}` (staff)

`components/lms/assignments/AssignmentPage.tsx`: `PageHeader` (title, kind badge, publish state, due date; primary action "Publish"/"Unpublish" for non-quiz kinds; quizzes publish in the builder as today) + `Tabs` (`?tab=`, default `details`):

| Tab | Content | Source |
|---|---|---|
| Details | read-only summary (`DescriptionList`: kind, due/until, points, category, release state, counts submitted / needs grading / graded / released), "Used in modules: M1, M3" (from `GET _C/modules`, cached in the layout), student-facing description (`body_html`); quizzes: primary "Edit questions" → `/assessments/{aid}/edit?from=…`, secondary "Publishing and versions" → `/assessments/{aid}` | new, small |
| Submissions and grading (non-quiz) / Results (quiz) | `GradingScreen` with `filter` from `?filter=`; quizzes: `StaffAttemptList` with an `assessmentId` prop (today it reads `useParams`) | existing |
| Settings | `AssignmentEditor` (form) | existing |

`AssignmentEditor` loses its "Grade" and "Open quiz builder" buttons (they live in the header and Details). Students keep `StudentAssignmentView` on the same URL.

### 5.2 Page `/pages/{id}` (staff) and quiz

`components/lms/pages/PageObject.tsx`: tabs **Edit** (`PageEditor` as today, variants chips, autosave status) and **Preview** (`PageView` of the saved `body_html`, with the language variant switcher). `/pages/new` stays the creation route (`?module=`, `?lang=`, `?group=`, `?from=`). **Quiz**: 7c editor unchanged (Questions · Settings · Preview); "Results" is a header link to `/assessments/{aid}/attempts` (no new tab, so the ORT section builder at the same route is untouched).

### 5.3 Close and `from`

One rule: a **`from` query parameter**, not history (history is unreliable after a dialog-driven create followed by `router.push`, and after a reload). `from` is a same-site path validated exactly like 8b's `?return=` (P8B-10: `/<lang>/…`, no scheme, no `//`); `lib/lms/nav.ts::safeFrom(param, fallback)` is shared by the quiz editor, the assignment page, the page object and the ORT builder. Fallbacks: assignment → `/assignments`; page → Course page; quiz → `/assignments?kind=quiz`. Every link into an object from the Course page, Assignments list, To do panel and module menus appends `from`; the Close/Back control of each object page is the one secondary button at the top left ("Back to *Course*" / "Back to *Assignments*", label derived from the `from` path). Fragment `#m-{moduleId}` scrolls the outline to the module.

---

## 6. Student view (S1 backend + frame)

### 6.1 Options

| | (a) hidden per-course test-student account (Canvas) | (b) read-only staff preview of student payloads (**chosen**) |
|---|---|---|
| Correctness | Fully realistic: real enrollment, attempts, hand-ins, progress, gating state after actions | Realistic for everything a *new* student sees: outline, locks and reasons, pages, files, assignments, lobby, grades (empty). Cannot "complete" items to see later states (teachers use the progress drawer for a real student instead) |
| Data isolation | Needs exclusion in rosters, `active_student_count`, enrollment limit, gradebook, statistics, `/me/home` of nobody, module progress counts, emails, audit, platform user lists, catalog counts, Phase 10 analytics; one missed path = a ghost student in a grade export | Nothing is written: no row exists to leak |
| Schema | `users.test_student_for_course_id` (or an `enrollments.is_test` flag) + `uq_enrollments_course_id_user_id` keeps teachers from a second enrollment → a synthetic user per course, migration, seed, reset endpoint, GDPR-style deletion rules | None |
| Effort / risk | L, high (touches every list) | S, low (one context flag, one header, serializers already allow-listed by 8a invariant 9) |

Default **(b)**. Reconsider (a) in Phase 10 if teachers need to test completion flows end to end.

### 6.2 Mechanism

Frontend: the Student view button sets `sessionStorage["studentView:{courseId}"] = "1"` and reloads the course; `lib/api.ts` adds header `X-View-As: student` to every request whose path starts with `/api/v1/courses/{courseId}/` while the flag is set (never to other courses, `/me/*`, platform routes). The layout then receives a `CourseStudentOut` and renders the student frame + banner (§2.4); "Leave student view" clears the flag and reloads. URLs do not change, so deep links keep working and the mode ends with the tab.

Backend (`core/authz.py`, `core/deps.py`): `get_authz` reads the header; `AuthzContext.view_as_student = True`. `role_for(course_id)`: when the real role is `teacher|assistant` (not org admin, not platform admin, not sandbox) and `view_as_student` → returns `"student"` and remembers `real_role`. `decide()` is called with `course_status="published"` for GET requests in this mode (the real role already reads drafts; students never could), so a draft course can be previewed. **Writes are refused**: any non-GET request with the header → 403 `student_view_read_only`, except `POST _A/preview` (already a staff preview path, evaluated with the real role). Effects: `assignments.service.is_staff` → false, so student shapes are produced; `modules.outline_for` → the student branch with **`evaluate(..., persist=False, enrollment=None)`**: a new evaluator entry point that computes states for an enrollment with no facts and no submissions (invariant 5 holds: no progress row for staff); `gate.require_access` evaluates the same way (locked pages/quizzes answer 423 as for a new student); `/grades` → own grades of an enrollment with no submissions (empty state); `/people` → the "Teachers" list; hand-in form → the frontend hides the form and shows "Student view: hand-ins are off" (the server would 403 anyway); mark done / view facts → hidden, 403 if forced; quiz lobby "Start" → `startPreview` → the existing preview attempt (`is_preview`, never counted, never graded, never in gradebooks or progress, 8b P8B-2) opens the player, whose own `?return=` leads back. `/me/home`, course lists, invitations: untouched (no header). Audit: none (reads only).

### 6.3 Migration

None. No column, no flag; `view_as_student` is request state only.

---

## 7. Backend API (policies in each package's `policies.py`, inventory block `# --- Phase 8c S1 ---`)

| Method, path | Policy | Result |
|---|---|---|
| `GET _C/modules/unsorted?kind=&cursor=&limit=` | `course:content.read_admin` (staff and org admins; students 403) | `UnsortedOut{assignments, pages, files: UnsortedPage{items, next_cursor, total}}`; with `kind` only that page. Items: `UnsortedItemOut{kind: assignment|page|file, id, title (LocalizedText for assignments, str otherwise), published, assignment_kind?, assessment_id?, language?, translation_group_id?, variants?: [{id, language}], folder?, updated_at}` |
| `GET _C/todo` | `course:content.manage` (teacher, assistant) | `TodoOut{to_grade: [TodoGradeOut{assignment_id, title, kind, needs_grading, oldest_submitted_at}] (≤ 10), to_grade_total, drafts: [TodoDraftOut{assignment_id, title, kind, assessment_id?, updated_at}] (≤ 10), drafts_total, unpublished_modules, first_unpublished_module_id?, active_students, join_code? (teacher only), join_code_active}` |
| `POST _C/modules/{mid}/duplicate` | `course:content.manage` | `ModuleStaffOut` of the copy: title + " (copy)" in every language, `published=false`, `unlock_at`/`sequential`/`completion_mode` copied, items and requirements copied (same targets), prerequisites not copied, placed after the original; caps enforced (422 `limit_reached`); under `lock_course` |
| header `X-View-As: student` on any `_C/**` GET | real role must be staff (else ignored) | student shapes; non-GET → 403 `student_view_read_only` (except `POST _A/preview`) |

### 7.1 Authorization matrix (server-side, roles from the DB)

| Request | Teacher | Assistant | Student | Org admin (A13) | Platform admin (not enrolled) | Other course |
|---|---|---|---|---|---|---|
| `GET modules/unsorted` | staff shape | staff shape | 403 | 200 (read_admin, same shape: titles and publish state only) | 404 | 404 |
| `GET todo` | full, with `join_code` | full, no `join_code` | 403 | 403 | 404 | 404 |
| `POST modules/{mid}/duplicate` | yes | yes | 403 | 403 | 404 | 404 |
| any `GET _C/**` + `X-View-As: student` | student shape, drafts readable | student shape | header ignored | header ignored | header ignored | 404 |
| any non-GET `_C/**` + header | 403 `student_view_read_only` | 403 | header ignored (normal rules) | header ignored | header ignored | 404 |
| `POST _A/preview` + header | 201 (real role) | 201 | 403 (as today) | 403 | 404 | 404 |

Concluded courses: the three GET routes follow `CONCLUDED_ACTIONS` (reads allowed), `duplicate` is refused like every content write.

Query bounds (6,000 concurrent students never hit these: they are staff routes, but each must be O(page)): unsorted = three `SELECT … WHERE NOT EXISTS (SELECT 1 FROM module_items mi JOIN course_modules m … WHERE mi.deleted_at IS NULL AND m.deleted_at IS NULL AND mi.<target>_id = t.id)` with the 8a indexes `ix_module_items_{assignment,page,file}_id`, cursor on (`position|title`, `id`), `limit ≤ 50`; totals are three `COUNT(*)` with the same predicate (each table is capped: assignments by `MAX_PAGE` paging, pages/files by course caps). To do = one grouped query `submissions.state = 'pending_review'` joined to live published assignments of the course (`LIMIT 10` after `ORDER BY min(submitted_at)`), one `COUNT`, one draft query (`LIMIT 10`), one `COUNT`, one `COUNT` over modules, `active_student_count` as today. Duplicate = bounded by 200 items. Student view adds no queries (same code paths as a student). Error ids: `student_view_read_only` (403), reuse `limit_reached`.

---

## 8. Frontend components and file map

New: `components/lms/course/{CourseSidebar,TeacherCoursePage,TodoPanel,UnsortedGroup,StudentViewBanner,AreaUnavailable}.tsx`, `components/lms/assignments/AssignmentPage.tsx`, `components/lms/pages/PageObject.tsx`, `lib/lms/nav.ts` (`courseNavItems`, `safeFrom`), `lib/lms/todo.ts`, `lib/lms/unsorted.ts`. Changed: `layout.tsx` (frame switch, `/attempts/**` exclusion, Student view), `page.tsx` (staff → `TeacherCoursePage`), `AreaShell.tsx` (`phone` mode), `LmsShell.tsx` + `AppHeader.tsx` (`hideSections`), `StaffCourseUi.tsx` (bar button, `useTabCrumbs`), `ModuleOutlineEditor.tsx` + `OutlineDialogs.tsx` + `AddItemDialog.tsx` (`embedded`, `initialKind`, move mode, menus, publish icon, drag), `StaffAssignmentList.tsx` (URL filters, `?new=`), `AssignmentEditor.tsx` (buttons removed), `GradingScreen.tsx` (`filter` prop), `StaffAttemptList.tsx` (`assessmentId` prop), `PageEditor.tsx` (`?module=`, `from`), `QuizEditor.tsx` + `SectionBuilder.tsx` (Close target via `safeFrom`, Results link), `lib/api.ts` (view-as header), `lib/lms/types.ts`. Deleted: `CourseTabs.tsx`, `StudentCourseTabs` (in `StudentCourseFrame.tsx`), `StaffCourseHome.tsx`, `StudentAssessmentList.tsx`; old route files become redirect stubs (§4.2).

---

## 9. i18n groups (en, ky, ru; parity script)

`courseNav.*` (link labels reuse existing keys: `courses.home.tab` → relabelled "Course" / "Курс" / "Курс", `announcements.title`, `assignments.tab`, `gradebook.tab`, `courses.people.tab(Student)`, `bank.tab` → "Question banks" / "Суроолор банктары" / "Банки вопросов", `courses.settings.tab`, `courseFiles.title`; new: `courseNav.menu` "Course menu", `courseNav.hiddenFromStudents`, `courseNav.hiddenHelp`, `courseNav.unavailable.{title,body,back}`), `studentView.*` (`button`, `banner`, `leave`, `handInsOff`, `readOnlyError`), `coursePage.*` (`add`, `addGroups.{content,assessment}`, `addItems.{page,file,link,header,quiz,assignment,ortExam}`, `unsorted.{title,empty,moveTo,allPages,allFiles,more}`, `structure` for the ORT section), `todo.*` (`title`, `toGrade`, `toGradeLine`, `drafts`, `unpublishedModules`, `students`, `nothing`, `more`), `modules.editor.*` additions (`publishedIcon`, `draftIcon`, `duplicate`, `dragHandle`, `moveTo`), `assignments.page.*` (`tabs.{details,submissions,results,settings}`, `usedIn`, `editQuestions`, `publishing`, `backTo`), `pages.object.tabs.{edit,preview}`, `errors.student_view_read_only`. Glossary unchanged (UX §5): "assignment"/"тапшырма"/"задание", "quiz"/"тест"/"тест", "преподаватель" never "учитель". Removed keys: `teaching.nextStep*`, `teaching.createAssessment`, `teaching.addQuestions`, `assignments.tabQuizzes` (kept only as the kind filter label value `assignments.kinds.quiz`).

---

## 10. Mobile (375 px)

Sidebar = "Course menu" button + sheet (44 px rows, ky/ru labels wrap). Course page: To do one-liner, then modules; module header = title + publish icon + "⋯" (no drag handle); item rows = icon + title on one line, meta line below; "+ Add" is a full-width button at the end of each module; the grouped menu is a bottom sheet with group headings. Unsorted rows stack. Assignment page tabs scroll horizontally (`Tabs` already does), the Submissions table keeps the 7a stacked cards. Student view banner wraps to two lines, "Leave" stays reachable. No horizontal scroll check in the modules e2e stays on.

---

## 11. ORT

**Changes (frame only, approved visual update 8c-7)**: the course tab bar becomes the sidebar/drawer around the ORT bank, question editor, passage editor, import page, section builder and staff attempts list; the ORT teacher Course page shows the exam list (same component) with the To do panel. **Pixel-identical (must)**: the player (all screens: `fixed inset-0`, outside the frame), the result card and the review (`/attempts/**` is excluded from the sidebar frame, §2.1), the publish panel element, the ORT bank list content, question/passage editors content, import page content, builder content (`SectionBuilder` untouched: no tabs added), exam list content, scoring and imports (`git diff --stat -- backend/app/lms/content/importers/ backend/app/lms/attempts/ backend/app/lms/ort/` empty).

**Re-baseline plan (S4)**: screens whose full-page or viewport capture includes the frame: `lobby` (phone + desktop, ru + ky: the student frame changes and the desktop content column narrows next to the sidebar), `teacher-bank`, `teacher-question-comparison`, `teacher-passage`, `teacher-import`, `teacher-builder`, `teacher-attempts` (phone + desktop, ru) = 16 images. Procedure: run `ort-visual.spec.ts` on the base commit and on the 8c branch with `ORT_BASELINE_RECORD_MISSING=1` into two folders; produce side-by-side before/after images in `docs/phases/PHASE_8C_screens/ort-before-after/`; the architect checks that inside the content region the DOM assertions and the masked diff of the content element (builder cards, bank table, attempts table, lobby card) are zero; the orchestrator approves and copies the new PNGs into `docs/phases/ORT_BASELINE/` with a dated note in its README. `result`, `review`, `publish` and the five player screens must pass against the **existing** baselines with zero diff (no re-record allowed).

---

## 12. e2e impact (`frontend/e2e/`)

| Spec | Change |
|---|---|
| `ort.spec.ts` | none (player, lobby DOM, result); the lobby URL `/assessments/{id}` stays |
| `ort-visual.spec.ts` | URLs unchanged (`/bank/**`, `/assessments/{id}/edit`, `/assessments/{id}/attempts` all still exist); baselines re-recorded per §11 |
| `quiz-editor.spec.ts` | line 77–85: `goto(/assessments)` + `assessments.list.create` dialog → the redirect lands on `/assignments?kind=quiz`; the spec is updated to click `assignments.list.create` and fill `AssignmentEditorDialog` (kind quiz), or to use "+ Add → Quiz" on the Course page; `editUrl` and the student lobby visit (line 235) unchanged |
| `modules.spec.ts` | `tp.goto(base/modules)` → staff redirect to `base`; selectors `modules.editor.newModule`, `modules.settings.*`, `modules.add.title`, `modules.editor.actions` (now the "⋯" menu label, key kept), `modules.editor.addItem` (now the "+ Add" button label, key kept; the dialog opens with the kind preselected, so `addItem(tp, M2, kind)` picks the kind from the menu first), `modules.add.newQuiz` → menu item; the student parts (`sp.goto(base/modules)`, tabs appearing with published content) now assert the sidebar links instead of tabs |
| `exam-constructor.spec.ts`, `scrolling-player.spec.ts` | none (templates area and player) |
| new `course-nav.spec.ts` | redirects table §4.2 (each old URL lands on the new one with the query kept), sidebar auto-hide for a student before/after publishing an announcement, Student view banner + 403 on a forced write, To do link lands on the Submissions tab with `to_grade` |

Redirect stubs keep every spec green through the transition; CI job `ort-e2e` runs the DOM assertions as before.

---

## 13. Slices, ownership, models, parallelism, release

Branch `phase-8c` off `lms`; slice branches `phase-8c-s<n>-<name>`; delimited blocks `# --- Phase 8c S<n> begin/end ---` in shared files; the orchestrator merges and reviews every diff. **S1 is a short foundation; S2, S3 and S4a run in parallel after it; S4b integrates. No pause: one release after S4.**

| Slice | Model | Scope | Owns (exclusive) |
|---|---|---|---|
| **S1** shell + backend reads (first, alone, 1–2 days) | opus; architect (fable) reviews `authz.py` view-as and the evaluator `persist=False` entry before merge | §2, §6 backend, §7 (`unsorted`, `todo`, `duplicate`, header), inventory block, i18n `courseNav.*`/`studentView.*`, redirect stubs for `/assessments` and staff `/modules` (§4.2 rows 1–3), `useTabCrumbs` change | backend: `core/authz.py`, `core/deps.py`, `modules/{service,evaluator,gate,schemas,policies,router}.py` (new functions only), `assignments/todo.py` (new), `assignments/{schemas,policies,router}.py` 8c blocks, `courses/policies.py`; frontend: `layout.tsx`, `CourseSidebar.tsx`, `AreaShell.tsx`, `LmsShell.tsx`, `AppHeader.tsx`, `StaffCourseUi.tsx`, `StudentCourseFrame.tsx`, `StudentViewBanner.tsx`, `AreaUnavailable.tsx`, `lib/api.ts`, `lib/lms/nav.ts`, `lib/lms/{todo,unsorted}.ts`, `assessments/page.tsx`, `modules/page.tsx`, `CourseTabs.tsx` (delete) |
| **S2** course page | opus | §3 all: `TeacherCoursePage`, `TodoPanel`, `UnsortedGroup`, outline refactor (embedded, menus, publish icon, drag, duplicate), grouped "+ Add", ORT Course page, `page.tsx` staff branch, i18n `coursePage.*`/`todo.*`/`modules.editor.*` | `components/lms/course/{TeacherCoursePage,TodoPanel,UnsortedGroup}.tsx`, `components/lms/modules/**`, `app/[lang]/courses/[courseId]/page.tsx`, `StaffCourseHome.tsx` (delete), `StaffAssessmentList.tsx` (move into the ORT Course page), `StudentAssessmentList.tsx` (delete) |
| **S3** one-page objects | opus (sonnet for i18n and the Details tab) | §5: `AssignmentPage`, `PageObject`, redirect stubs §4.2 rows 4–8, `StaffAssignmentList` URL filters and `?new=`, `GradingScreen`/`StaffAttemptList` props, `AssignmentEditor` buttons, `PageEditor` `?module=`/`from`, `QuizEditor`/`SectionBuilder` Close via `safeFrom` (Close only; the ORT builder's content is untouched), i18n `assignments.page.*`/`pages.object.*` | `app/[lang]/courses/[courseId]/{assignments,pages}/**`, `assessments/[assessmentId]/**` (Close only), `components/lms/{assignments,pages,quiz}/**`, `components/lms/assessments/SectionBuilder.tsx` (Close only), `components/lms/results/StaffAttemptList.tsx` |
| **S4a** e2e and baselines (parallel with S2/S3, rebased on them at the end) | sonnet | §12 spec updates, `course-nav.spec.ts`, §11 before/after recording script and folder | `frontend/e2e/**`, `docs/phases/PHASE_8C_screens/ort-before-after/**` |
| **S4b** integration and gates | orchestrator + ux-reviewer (fable) + architect security review (fable) | contracts, full suites SQLite + PG, route inventory, ORT review §11 (baseline approval), UX gate §15, `/security-review` (view-as header: write refusal, org admin and platform admin never downgraded, draft-course read scope, `from` validation, unsorted/todo isolation), i18n parity, `next build` in the rsync copy, `PHASE_8C.md`, `PRODUCT_DECISIONS.md` (§17), `HANDOFF_NEXT_AGENT.md`, Neon backup branch, merge `lms` → `main`, `/health` check | docs, CI |

Interfaces fixed by S1 so S2/S3 code against them: `courseNavItems`, `safeFrom`, `UnsortedOut`/`TodoOut` TypeScript types in `lib/lms/types.ts`, the `from` convention, the `X-View-As` header. S2 and S3 share no file (S2 owns `modules/**` and the course `page.tsx`; S3 owns `assignments/**`, `pages/**`, `quiz/**`). The only cross-slice touch is `AddItemDialog` (S2) linking to `/pages/new?module=` (S3 implements the parameter; until then the page is created without the item and S2's picker adds it).

**Walkthrough (S4b, dated in `PHASE_8C.md`)**: teacher creates a general course → Course page empty state → "New module" M1, M2 → "+ Add → Page" in M1 (new page, saved, back on the Course page at M1) → "+ Add → Quiz" in M2 (editor opens, two questions, Back lands on M2) → "+ Add → Assignment" (text) in M2 → publish M1 and M2 with the icons → an existing unsorted file moved into M1 from the Unsorted group → Student view: M1 open, M2 open, quiz lobby Start opens a preview attempt, hand-in form shows the off notice, Leave → student (real) hands in → To do shows "1 to grade" → link lands on Submissions `to_grade` → grade → To do empty → phone (375 px): drawer, To do one-liner, "+ Add" sheet. ORT course: Course page shows the exam list, "New ORT exam" works, builder and attempts open from the Assignments link, sidebar visible, `ort-visual` content regions unchanged.

**Release**: nothing deploys after S1 or S2. One release after S4b: `phase-8c` → `lms` → `main` (models unchanged, but the Neon backup branch is still taken because the release carries the 8c backend). The optional teacher test (§16) runs in production after this release; findings become slice **S5 follow-ups** (sonnet/opus by size).

---

## 14. Tests (`backend/tests/lms/`, scratch SQLite + PG parity; frontend `tsc`, unit, e2e)

- `test_course_nav_backend.py`: `GET _C/modules/unsorted` — assignment in a module not listed; in a deleted module listed; in a deleted item listed; page group with one variant referenced not listed; file listed; quizzes listed with `assessment_id`; ORT preset exam listed in a general course; student 403; org admin 200 (read_admin); cross-course 404; pagination per kind with `total`; `kind=` single page.
- `test_todo.py`: counts per assignment match `assignments.service.counts`; ordering by oldest `submitted_at`; `LIMIT 10` + `to_grade_total`; drafts exclude deleted; `join_code` only for teachers; assistant 200; student 403; concluded course 200 (read) — policy table test.
- `test_module_duplicate.py`: copy semantics (§7), caps, prerequisites not copied, rules_version bump, `lock_course`, PG concurrency with a reorder.
- `test_student_view.py` (table: action × role × method): header ignored for students, org admins, platform admins, sandbox; teacher GET → student shapes (`is_staff` false, no `rules_version`, no `body_md`, no warnings, no unpublished rows: the 8a serializer contract tests run with the header on); draft course readable in view; every non-GET under `_C/**` → 403 `student_view_read_only` with no DB change (row counts before/after); `POST _A/preview` allowed; gate 423 for a locked page in view; **no `module_progress`/`item_progress`/`submissions` row for the staff enrollment after a full walk** (invariant 5); `/me/home` of the teacher unchanged.
- Updates: `test_route_inventory` (new entries), `test_modules_api.py` (duplicate), `test_assignments_api.py` (list filters unchanged), `test_serializer_contracts.py` (view-as variant).
- Frontend: `lib/lms/nav.test.ts` (`courseNavItems` over every route × role; `safeFrom` rejects `//`, schemes, other langs), e2e §12, `tsc --noEmit`, `check_i18n_parity.py`.

---

## 15. UX gate screens (`docs/phases/PHASE_8C_screens/`, 375 px + 1440 px; student screens en/ky/ru, teacher ru)

Teacher: Course page (empty course; filled with 3 modules, Unsorted group with 3 kinds, To do with items and empty), "+ Add" menu open (desktop and phone sheet), module "⋯" menu, drag state, phone drawer open, sidebar with a hidden-from-students mark, Assignments with `kind=quiz` filter, assignment page (Details, Submissions `to_grade`, Settings), page object (Edit, Preview), quiz editor with the Back control, Student view banner over the course page and the lobby, ORT teacher Course page (exam list + To do), ORT builder inside the new frame. Student: course page (`modules`, `page`, `assignments` homes), sidebar with and without Announcements/Files, "Not available yet" page, phone drawer, lobby in the new frame.

---

## 16. Teacher test script (optional, after the release; findings → S5)

Give one or two teachers a published general course with two modules and ask them to, without help: (1) add a quiz to Module 2 and reach its questions; (2) add a page to Module 1; (3) find where three waiting submissions are graded, and grade one; (4) see the course as a student and come back; (5) publish a draft module; (6) move an unsorted file into Module 1; (7) find the join code; (8) find the question bank. Record for each task: done alone / needed a hint / failed, the first wrong click, and the time. A task failed by both teachers is an S5 item.

---

## 17. Decisions taken here (to `PRODUCT_DECISIONS.md` as P8C-1 … when applied)

| # | Decision |
|---|---|
| P8C-1 | Student view is a read-only staff preview (`X-View-As: student`; role downgraded in `AuthzContext` for GETs, writes 403, no persistence, evaluator in `persist=False` mode with no facts); no test-student account, no migration. |
| P8C-2 | Files stays the eighth sidebar link for staff; students see it only with published files. |
| P8C-3 | Redirects are route-level (`router.replace` in the old route's page after the course loads); `next.config` gets none. |
| P8C-4 | Objects close via a validated `from` path (same rule as the player's `return`), never via history. |
| P8C-5 | "Unsorted" = live assignments, pages (by translation group) and files not referenced by a live item of a live module. |
| P8C-6 | Drag and drop uses native HTML5 events on desktop; the "⋯" menu is the only path on phones and keyboards; no new dependency. |
| P8C-7 | The Tests list is gone; `/assessments/{id}*` routes stay (lobby, publish/versions, builder, results); ORT exams are created from the ORT Course page (exam list) only. |
| P8C-8 | `/attempts/**` renders without the course sidebar, so the ORT result and review stay pixel-identical. |
| P8C-9 | Module duplicate is the one new write endpoint (items and requirements copied as a draft; prerequisites not). |

---

## 18. Alternatives to discuss (owner; none blocks, defaults in effect)

| # | Question | Options | Default |
|---|---|---|---|
| **Q1** | Student view fidelity: teachers cannot complete items or hand in to see later states. | (a) read-only preview (built); (b) later add a test-student account (Canvas) with the isolation work of §6.1. | **(a)** |
| **Q2** | Files link. | (a) keep for staff, auto-hidden for students (built); (b) remove; files only via "+ Add" and the Unsorted group. | **(a)** |
| **Q3** | Grades link for students in courses without any graded work. | (a) always shown (built; the page has an empty state); (b) auto-hide until a grade is released (needs a fourth `features` flag). | **(a)** |
| **Q4** | ORT teacher Course page order. | (a) exam list first, collapsed modules section below (built); (b) modules first. | **(a)** |
| **Q5** | "+ Add" order inside Assessment. | (a) Quiz, Assignment (quizzes are the most used item in this product); (b) Assignment, Quiz as listed in 8c-2. | **(a)** |
