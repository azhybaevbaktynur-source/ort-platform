# Owner feedback round, 2026-11-08 (verbatim brief)

Owner feedback round, 2026-11-08. Same rules: improve the existing architecture, don't destroy it; ORT behavior unchanged; reference app stays unnamed. Architect on Fable for audits and designs; implementers on Opus for data, permissions, routing and course structure, Sonnet for styling and text. Write each audit/design into docs, record decisions in PRODUCT_DECISIONS.md, then build. No stops between items; one review list at the end.

0. Neon: delete old backup branches, keeping the production branch and the 2 most recent backups. Never delete the production branch. Report which branches you deleted.

1. Catalog cards are too big (at 1440 px only 2 cards fit and the cover is very tall). Grid: 4 columns ≥1600 px, 3 at 1200–1599, 2 at 768–1199, 1 on phones; max card width about 360 px; lower cover (about 16:7 or a fixed 140–160 px height). Same card size on home and "my courses".

2. Remove "Learning" for teachers: the "Learning" area in the header, the "Teaching / Learning" tabs and "Join with code" on the teacher's course list are shown only if the user has at least one student enrollment. A teacher with no student enrollments sees only Teaching (and Organization/Admin if they hold them). Student view stays as it is.

3. Teacher course → student view audit, then rebuild like the reference app:
   - Trace end to end and write docs/phases/TEACHER_TO_STUDENT_MAP.md: for every teacher action (create course, assessment, module, video, page, file, link, ORT exam, announcement, practice, publish/unpublish, Pro toggle) where exactly it appears for the student (sidebar, home, tests page, course page, lesson page), with a screenshot pair. List everything that doesn't appear, appears in the wrong place, or appears twice.
   - Structure like the reference app: the exam switcher at the top of the student sidebar (ORT ru / ORT ky, later olympiads and НЦТ); under it a group of lesson courses ("masterclass"), each with overview (cover banner, "continue", progress), syllabus (modules with lessons, durations, done state) and the lesson page (video, outline on the side, next lesson); a practice group with tests. Decide with the architect how lesson courses attach to an exam (e.g. separate courses linked to an exam key vs. modules inside the exam course), pick the option that changes least, and document it.
   - Test with a real example: create a lesson course with 2 modules (video, page, file, test), publish, check every student page; add this as an e2e test.

4. Super admin control of organizations: as platform admin I must be able to see and manage every organization. Build:
   - Admin → Organizations: table with name, type (school / personal / platform), status, number of teachers, courses, students, storage, created; search and filters.
   - Organization detail page for the platform admin: overview, teachers, courses, students, usage, template grants, settings, suspend/reactivate; and an "Open as org admin" button that opens the org admin area for that organization (actions audited as platform admin).
   - The "Organization" area in the header shows an organization switcher when the user can manage more than one organization.

5. Teacher and admin usability audit and rebuild. Write docs/phases/STAFF_UX_AUDIT.md (Fable) with concrete problems and fixes, then build. Start from these:
   - Teacher course page: today 11 menu items, crossed-eye icons, the assessments list and the course structure stacked on one long page. Rebuild as clear sections: Content (modules with lessons and tests), Students, Grades, Analytics, Settings; Announcements, Files, Practice and Question banks inside Content or under "More". Remove the crossed-eye icons (show "hidden" as a small badge only where relevant). "Show trash" moves into a "⋯" menu. Assessments as a compact table (title, status, attempts, actions in "⋯").
   - Module editor: one "+ Add" dropdown (video, page, file, test, link) instead of six buttons; drag handles for reorder; Pro as a lock icon with a tooltip; publish as a toggle.
   - Create course: compact form with a live card preview filling the right side: title, main language (one select; "add translations" as an advanced option instead of checkboxes plus a default radio), description, cover, enrollment, template (ORT only if granted). Explain or remove the EN/RU chips over fields.
   - Course settings: sections with a small sub-nav: General, Cover, Enrollment, Access/Pro, Danger zone; form width about 720 px with a preview on the side.
   - Admin overview: a metrics row (users, active students in 7 days, Pro subscribers, tests taken this week), an "Needs attention" list (teacher requests, storage, code reveals, failed checks), quick actions; System health collapsed into a small status line with "details".
   - Admin menu grouped: People (Users, Teacher requests), Content (Organizations, Courses, Exam templates), Pro (Plans and settings, Pro users, Gift codes), System (Storage, Health, Audit log, Security, Data requests).
   - Everywhere in staff areas: compact density, tables for lists, one page header pattern (title, subtitle, one primary action, the rest in "⋯"), max content width per page type, no huge empty half-screens.
   Check every changed page at 1440 and 1920 and on a phone.

When all is deployed, give me one short review list (URLs and what to try) for 0–5.

## Results (agent, 2026-11-08)

| Item | What was built | Docs | Deployed |
|---|---|---|---|
| 0 | Neon: kept production + 2 newest backups; 7 old backups deleted (names in `PRODUCT_DECISIONS.md`) | — | done |
| 1 | One course grid: 1/2/3/4 columns at <768/768/1200/1600 px, cards ≤360 px, 150 px cover; the home grid follows its own column (256–360 px) | — | bc4e090 |
| 2 | Learning area, Teaching/Learning tabs and «Войти по коду» only for users with a student enrollment (`/me/lms has_student_enrollments`) | — | bc4e090 |
| 3 | Lesson courses are separate platform courses linked to an exam (`courses.exam_course_id`, migration 0027); УРОКИ group in the student sidebar, lessons in the exam shell, home «Уроки» + «Продолжить урок», exam link in course settings; e2e `teacher-to-student.spec.ts` with screenshot pairs | `TEACHER_TO_STUDENT_MAP.md` | c9ca5f1, 989054d |
| 4 | Admin → Организации table (type, status, teachers, courses, students, storage), detail page (students, settings, suspend with counts, platform org protected), «Открыть как администратор организации» with `acting_as` audit and strip, header organization switcher | `ADMIN_ORGS_DESIGN.md` | c9ca5f1 |
| 5 | Staff primitives; course menu Содержание/Ученики/Оценки/Аналитика/Настройки + «Ещё»; compact assessments table; module editor «+ Добавить»; create course with live card; settings sections; admin overview + /admin/health; grouped admin menu; density sweep | `STAFF_UX_AUDIT.md` | c9ca5f1, 989054d |

Screens: `STAFF_FEEDBACK_screens/item1..5/`. Neon: 4/10 branches (backup before 0027 kept).
