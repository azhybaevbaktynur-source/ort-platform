# Phase 8c: teacher navigation redesign (final decisions), then Phase 9

**Status**: **approved by the owner 2026-10-31** (revised proposal v3; replaces v1 of 2026-10-30 and v2). Decisions 8c-1…8c-6 are recorded in `PRODUCT_DECISIONS.md`. The design is in `PHASE_8C_DESIGN.md`.
**Trigger**: after 8b the owner found teacher navigation hard: every task needs going "inside each step".

## 1. Problems to fix

1. **Too many layers.** There are four navigation layers before any content: header areas, Teaching sub-menu, breadcrumb and 11 course tabs.
2. **Duplicate creation paths.** The same thing is created in three places: Assignments, Tests and Modules. Since 7a a quiz is an assignment, so "Tests" is a duplicate list.
3. **The course home is a dashboard, not the course.** Its "Next step" text still describes the pre-7c flow.
4. **Chains of pages.** Every object goes list → detail → edit → back → grade.
5. **Visual noise on lists.** Each module row has a publish switch, up and down arrows and an "Actions" menu. That is about 4 controls per row, and about 40 on a page with 5 modules.

## 2. What the research says (summary)

- **Canvas.** Canvas schools advise a short course menu. Too many links make a course cluttered, and most default links go unused. Assignments, Quizzes and Pages are best reached through Modules. Canvas needs "hide and reorder" mainly because its default menu is long.
- **Moodle's add menu.** Moodle groups everything that can be added into one "add an activity or resource" menu. It is grouped by purpose (assessment, collaboration, communication, interactive content, resources) and has favourites. Since 4.4, items can be added anywhere in a section.
- **Moodle's secondary menus.** Moodle 4 users report that hiding tools in secondary menus makes sub-pages hard to find. Tools must stay easy to find.
- **Comparisons.** Direct comparisons of Canvas and Moodle ease of use are mixed and old. No study tests this exact combination, so a teacher test is part of the plan.

## 3. Final decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Course menu | **Short left sidebar, 7 to 8 links** (Canvas placement, short list). No "More" menu. No Settings → Navigation page in 8c |
| 2 | Adding content | **"+ Add" inside each module** with one grouped menu (Moodle style). Pages and Files are created here |
| 3 | Teacher course home | **Modules outline (organised course structure) plus a To do panel.** Items in no module appear in an "Unsorted" group at the bottom |
| 4 | Separate "Tests" list | **Removed.** Quizzes stay in Assignments (with a "Type: quiz" filter) and in Modules |
| 5 | Edit mode | **None.** All functions always available. Only a **Student view** button is added |
| 6 | Order | **Phase 8c first, then continue with Phase 9** |

## 4. Design

### 4.1 Left sidebar (short)

1. **Course**: modules outline plus To do panel. It replaces Home and Modules.
2. **Announcements**
3. **Assignments**: all assignments, quizzes included, with a "Type: quiz" filter. Used for grading and overview.
4. **Grades**
5. **People**
6. **Question banks**
7. **Settings** (teacher only)
8. **Files** (optional): keep only if teachers need one library of all files. Decide at the slice 1 review.

Notes:
- **Where Pages, Trash and Reports live.** Pages are reached from the course page and "+ Add". Trash and Reports live inside Settings (Reports later) or in the To do panel, not as sidebar links.
- **Auto-hide for students.** A link to an area with no published content (for example no announcements) is not shown to students. Teachers still see it, marked "hidden from students". A direct URL to a hidden area shows a friendly "not available" message.
- **Phones.** The sidebar becomes a "Course menu" button that opens a drawer.
- **Postponed: Settings → Navigation** (hide/reorder links per course). With 7 to 8 links it is not needed. Postponing it also removes the per-course settings field and the migration. Revisit if teachers ask, or when Phase 9 adds many links.

### 4.2 Course page

- **Main area**: the modules outline.
- **"+ Add" per module** opens one grouped menu:
  - Content: page, file, link, header.
  - Assessment: assignment, quiz.
  - The most used items are shown first. Creating a quiz opens its question builder directly.
- **"Unsorted" group** at the bottom holds items not in any module.
- **To do panel** on the right:
  - Things to grade, linking straight to the submissions that need grading (not to the Grades page).
  - Draft quizzes and assignments.
  - The join code.
  - On phones it collapses to one line ("3 to grade · 1 draft") that expands on tap.
- No dashboard cards and no "Next step" text.

### 4.3 Controls without edit mode

All functions stay available. Only the display is lighter:
- **Publish state**: one small icon that shows published or draft and toggles on click.
- **One "⋯" menu** per module or item: edit, duplicate, move up, move down, move to…, delete.
- **Drag handle** for reordering. The menu items are the non-drag alternative (phones, keyboard, accessibility).
- **Result**: about 10 visible controls on a 5-module page instead of about 40. This is a display choice and is cheap to adjust later.

### 4.4 One page per object

- **Quiz**: Questions · Settings · Results · Preview (already done in 7c).
- **Assignment**: Details · Submissions and grading · Settings.
- **Page**: Edit · Preview.
- Closing an object returns to the place in the course you came from.
- **One way to create each thing.** "+ Add" in a module is the main way and "New" in the list pages is the second way. Both open the same editor.

### 4.5 Student view

A button in the course title line. It shows the course as a student sees it, without logging in as one.

### 4.6 ORT courses

ORT courses use the same shell. Their content stays as is: the exam assignments list, ORT bank, exam builder, import, player and results keep their screens and behaviour, and are reached from the sidebar. The ORT review and screenshot comparison run as in every phase.

## 5. Plan

### Phase 8c: teacher navigation (size M, mostly frontend)

Reuses the 8a modules outline and the 7c editor.

**Backend** (small, no migration expected):
- An "Unsorted items" list for the outline.
- A To do summary (counts and links).
- A per-area "has published content" check for auto-hiding links.

**Slices**:
1. **Course shell**: short left sidebar, auto-hide for students, Student view button, phone drawer, removal of the Teaching sub-menu inside courses, removal of the "Tests" list, decision on the Files link.
2. **Course page**: modules outline with the grouped "+ Add" menu, the Unsorted group, the To do panel, and lighter item controls ("⋯" menu, publish icon, drag plus menu alternative).
3. **One-page objects** for assignments and pages (the quiz is already done).
4. **Integration**: ORT review; redirects for old URLs (`/assessments`, `/assignments`, the old Tests path) so bookmarks and e2e tests keep working; UX gate; deploy.

**Teacher test** (after slice 2, before slice 3). Give one or two real teachers tasks such as:
- "add a quiz to Module 2"
- "add a page"
- "find where to grade submissions"
- "see the course as a student"

Note where they get stuck and adjust before building slice 3.

**Exit criteria for 8c** (all required before Phase 9 starts):
- Slices 1 to 4 deployed.
- Teacher test done and findings addressed.
- UX gate passed, with the ORT review and screenshot comparison done.
- Old URLs redirect and e2e tests pass.

### Phase 9: continues after 8c

- Phase 9 scope is unchanged from the roadmap. It starts only when the 8c exit criteria are met.
- Every new Phase 9 screen is built inside the new shell. It adds its own sidebar link (hidden for students while empty) or its own "+ Add" item, and objects follow the one-page-with-tabs pattern.
- Any Phase 9 item that planned to use the old Tests list, the 11-tab layout or the dashboard home is adjusted to the new structure at Phase 9 kickoff.
- If Phase 9 adds enough links to make the sidebar long again, add Settings → Navigation (hide/reorder) then.

## 6. Risks

- **Clutter returns.** Always-visible controls can bring it back. Keep to one "⋯" menu per row and review at the teacher test.
- **Pages and Files get harder to find.** Moving them into "+ Add" risks this. The Unsorted group, the Files link decision and the teacher test cover it.
- **Hidden tools.** Moodle 4 users complain when tools are hidden in secondary menus. Keep Question banks and Grades in the main sidebar.

## 7. Agent review notes (2026-10-31, accepted with the plan)

1. **Student view** is the only technically non-trivial item. To show the course "as a student sees it", the server has to answer as a student would, including module locks and hidden areas. The design picks between a hidden per-course test-student account (Canvas approach) and a read-only staff preview of student payloads. The default is the simplest safe option, chosen in `PHASE_8C_DESIGN.md`.
2. **The teacher test needs the owner.** Slices 1–2 are built and deployed first. The agent then pauses for the owner to run the test with real teachers, then builds slices 3–4.
3. **"Course" is role-specific.** Teachers always see the modules outline (or, in ORT courses, today's exam list). Students keep the course home chosen in Settings (8a `home_kind`: modules, page or assignments).
4. **ORT.** The course frame around ORT screens changes to the sidebar, which is an approved visual update with before/after screenshots. The ORT player, bank, builder, import and results keep their screens and behaviour.

## 8. Sources

- [Canvas: manage course navigation links (Cornell)](https://learn.canvas.cornell.edu/managing-course-navigation-links)
- [Cleanup course navigation (SUNY Geneseo)](https://wp.geneseo.edu/etc/?p=83)
- [Removing unused menu items (Boston College)](https://cdil.bc.edu/tools/canvas/canvas-design/canvas-templates/removing-unused-menu-items)
- [Canvas navigation cleanup (Indiana University)](https://ittrainingcontent.iu.edu/training/a11y-canvas/files/pc/pb-nav-cleanup.c.html)
- [Moodle activity chooser](https://docs.moodle.org/405/en/Activity_chooser)
- [Moodle 4.4 add anywhere in a section](https://lead.mic.ul.ie/moodle/add-activity-or-resource-changes)
- [Moodle 4.0 navigation improvements](https://docs.moodle.org/dev/Moodle_4.0_navigation_improvements)
- [Moodle tracker MDL-74921](https://tracker-old.moodle.org/browse/MDL-74921)
- [Oxford Brookes Moodle 4 student survey](https://www.brookes.ac.uk/students/news/2024/03/your-feedback-on-the-new-moodle)
