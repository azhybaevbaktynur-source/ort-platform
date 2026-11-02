# Accounts, teachers and organizations: discussion

For the owner's decision (Step 2 of the 2026-11-03 feedback). Analysis only: nothing here is built. Facts were checked against the code and, read-only, against production on 2026-11-03, and an independent review then checked every claim against the code; its corrections are included. "Tested" means I ran that behaviour in a scratch test.

## 1. Recommendation in short

1. **Keep personal organizations inside the system, and stop showing them.** The "Organization" area appears only for schools, centers and the platform organization.
2. **Add a teacher sign-up:** "I'm a teacher" → account → application (name, school, subject, phone) → pending → you approve or reject, and the applicant gets an email either way.
3. **Remove "become a teacher" from everything a student sees.** A student who really is a teacher applies from the public "For teachers" page, signed in, with the same form.
4. **Do not add a teacher or student account type.** One person, one account. What they see comes from what they actually do.

Nothing is deleted and no existing course or grade changes. Seven decisions are yours (section 6). **The one that matters most for control of the platform is Q6: today, revoking a teacher also freezes their students.**

## 2. How it works today

### Three separate things decide what someone is
| What | Where it lives | What it really means |
|---|---|---|
| `users.teacher_status` (`none`, `pending`, `approved`, `revoked`) | users table | Only the state of an **independent** teacher's application. A school teacher stays `none`. |
| `organization_members` (`org_admin` or `teacher`) | per organization | The real permission: `can_create_courses` comes from here, not from `teacher_status`. |
| `enrollments` (`student`, `assistant`, `teacher`) | per course | What the person can do in that course. |

The header reads these: Teaching appears if they teach or can create courses (or are platform admin), Organization if they are `org_admin` anywhere, Admin if `is_platform_admin`.

### What happens when you approve a student
1. The student opens the account menu → "Я преподаватель" (`/teacher-access`), and sends an optional free-text message. `POST /me/teacher-requests` stores it and sets `teacher_status = pending`.
2. You approve it in Admin → Teacher requests.
3. In one transaction: `teacher_status = approved`, a **personal organization** is created (fixed id from the user id, named after them, `kind = personal`), and they become its `org_admin`.
4. Being `org_admin` is what gives them "create course", and it is also what makes the **Organization** area appear. **That is the confusing tab you saw: it is a side effect, not a decision.**

No email is sent at step 3 or on rejection. The applicant finds out only by reopening `/teacher-access`.

### Other ways in
- **School invitation:** an org admin invites by email and the person accepts. They become a member with `teacher_status` still `none`, and see Teaching but no Organization area.
- **Course co-teacher invitation:** the person becomes staff of that course only; no organization membership.
- **You setting the status directly:** Admin → user page.
- **Platform admin:** gets the platform organization, not a personal one.

### Why personal organizations exist
Every course must belong to an organization (`courses.organization_id`). Banks, templates, settings, suspension, usage counts and audit all hang off it. A personal organization lets an independent teacher use all of that without special cases.

### Production today
18 users (8 of them test students, 6 disabled). 1 platform organization, 2 personal (one belongs to the disabled QA teacher), **no schools yet**. 3 courses in the platform organization, 5 in personal ones. Personal organizations with more than one member: 0. 1 teacher request ever. 14 users have no age band (older accounts).

## 3. Problems

### A teacher's view
1. **An "Organization" area they never asked for.** Its pages make sense for a school (Teachers, Departments, Shared banks, Roster import, Settings). For one person, most are empty or refuse to work.
2. **No word after applying.** No email on approval or rejection, and no notice on the dashboard.
3. **The form asks nothing useful.** One optional text box, so you approve on very little information.
4. **No proper way in.** A teacher must first register as if a student, then find a menu item.

### A student's view
5. **"Я преподаватель" is in every student's account menu.** "Схемы оценивания" and the "create course" page also offer it.
6. **A student's application is not limited by age.** Tested: a 14–17 account can apply. An under-14 is stopped by the consent gate, but only until a guardian consents.

### Bugs and gaps found while checking
7. **Revoking a teacher freezes their students.** A revoke suspends the personal organization, and a suspended organization is read-only for everyone except you. So the teacher's students can't start a test or hand in work, nobody can join, and the courses leave the catalog. The confirmation doesn't say so, and the page only tells the teacher that existing courses "stay available". See Q6.
8. **A revoked teacher keeps the Organization area and loses the way back.** Tested: after revoke, `is_teacher` is still true and the suspended personal organization is still listed. The menu link is shown only when `is_teacher` is false, so it disappears, although the page text says they can apply again. Applying by direct URL does work.
9. **"Personal" does not mean "one person".** Tested: the owner of a personal organization can invite another teacher, or even another **org admin**, from the Organization area. This is real: production has one such teacher invitation from a personal organization, still open, to someone with no account yet.
10. **Hiding the area would strand two things.** Roster import exists only there. And organization-level exam templates are listed only there: the Teaching page shows only a teacher's own, and **production has 2 such templates in personal organizations.** Section 5 handles both.
11. **A personal organization shows up by the person's name in pickers.** A teacher in both a school and their own organization chooses between "School" and their own name when creating a course.
12. **An independent teacher who joins a school cannot bring their courses.** A course can move only inside one organization's tree. Not part of this decision: it belongs in the admin control center.
13. **Applications and school invitations don't know about each other.** Accepting a school invitation leaves a pending application in your queue, and approving it still creates a personal organization. A school teacher can also apply and get one.
14. **Anyone rejected can reapply at once,** up to 3 times a day. Harmless now, but once decisions send emails this becomes repeat queue entries and repeat emails.
15. **A school setting that does nothing.** "Default catalog visibility" for new courses is saved but never read: every new course starts private. Not part of this decision, but school admins will trust it. It should be fixed or removed.
16. **`/teacher-access` does three jobs:** status, application, and the Accept buttons for invitations. The invitation banner links there, so **it cannot simply be deleted**: invited people would lose that way to accept.

## 4. Options

### A. What to do about personal organizations
| Option | Effect | Risk | Verdict |
|---|---|---|---|
| A1. Leave as is | Nothing changes, the confusion stays | None | No |
| A2. **Keep internally, hide by kind** | Organization area never shows for `kind = personal`; same behaviour for everyone | Low: one rule in `/me/lms`, plus moving roster import | **Recommended** |
| A3. Hide when the organization has one member | Your wording, but the tab would appear the moment a co-teacher joins, and disappear again when they leave | Low, but confusing | No |
| A4. Remove personal organizations | Cleanest on paper; `organization_id` becomes optional and every rule built on it needs a "no organization" case: permissions, banks, templates, settings, suspension, usage | High, on production data, for no visible gain over A2 | No |

A2 instead of your suggested "single-teacher" rule, because the area should depend on what kind of organization it is, not on how many people are in it.

### B. How a teacher signs up
| Option | How | Verdict |
|---|---|---|
| B1. Application form only, kept in the student flow | Better form, same hidden entry | No: doesn't solve "no proper way in" |
| B2. **One sign-up page with three steps** | `/for-teachers/apply`: account → email code → application. Uses today's register and verify routes unchanged | **Recommended** |
| B3. Application first, account created on approval | Nothing to clean up after rejections, but you'd store a password or send set-password links, the email isn't proven when you review, and the application needs its own anti-spam | No |

With B2 your queue only ever holds people who proved their email. Someone who leaves after entering the email code has a normal account and continues from the same page after logging in. Someone who leaves before the code has no usable account yet: they register again or ask for a new code, as any sign-up does today.

### C. How an existing student account applies
Same page, signed in: the account steps are skipped and the email is already known. The way there is the public site: footer "Преподавателям", the landing page's "Я преподаватель", and an answer in Help. Once the links listed in section 5 are removed, nothing inside the signed-in app points to it for a student. School invitations keep working as they do now and need no application.

An email that already has an account gets "this email is registered: log in to continue". That is how sign-up already answers today, so it reveals nothing new.

### D. Separate teacher and student account types: rejected
It looks simpler, but teachers also learn, a person can be a student in one course and an assistant in another, and it would mean a role column the project deliberately removed, or two accounts per person. Capabilities from real data stay the single source of truth.

## 5. What changes if you accept

### What each person sees
| Person | Learning | Teaching | Organization | Admin | Parent |
|---|---|---|---|---|---|
| Student | yes (menu hidden, only one area) | | | | |
| Student with application pending | yes, plus a one-line status | | | | |
| Independent teacher | yes | yes | **no (changed)** | | |
| School teacher | yes | yes | | | |
| School admin | yes | yes | yes | | |
| Platform admin | yes | yes | yes (platform organization) | yes | |
| Parent | as above | | | | yes |

A revoked independent teacher: Teaching stays, because they still own courses, with a clear notice and a link to apply again. What happens to their students is Q6.

### Data (one additive migration, `0019`)
- `teacher_requests` gains `applicant_name`, `school`, `subject`, `phone`. All optional at database level, required by the new form. Old requests keep their `message`.
- No change to users, organizations, courses or grades. No personal organization is touched.
- A Neon backup before deploy, as always. That uses the last free branch slot (9 of 10 today).

### Privacy, because a phone number is personal data
- The new columns join `privacy/registry.py`, so export and anonymize cover them. A test already fails if a column isn't listed.
- The phone is shown only to the platform admin, and never written to the audit log or to logs.
- Keeping it after a decision is your call (Q3).
- New personal data means the lawyer's list in `LAUNCH_CHECKLIST.md` gets one more line.

### Backend
- `/me/lms`: `admin_organizations` leaves out `kind = personal`. The header reads that one answer (item 7, Step 1).
- `POST /me/teacher-requests`: new fields, the age rule (Q2), the wait after a rejection (Q7), same rate limit.
- Emails on approve and reject, in the person's language, through the existing email service; never to a disabled account. Test students can't apply, as today.
- The queue shows "already teaches at X" when the applicant has a school membership. You decide; nothing is cancelled automatically.
- Organization invitations refused for personal organizations (`personal_org_no_members`). Course co-teacher invitations keep working: they are the legitimate way to share one course.
- `MyOrganizationOut` gains `kind`, so the course and template pickers say "Мои курсы" rather than the person's name, and the `/org` picker leaves personal organizations out (problem 11).
- A small cleanup job for Q3, like the one for enrollment applications: nothing deletes decided requests today.
- Admin queue returns the new fields.

### Pages
- **New:** `/for-teachers/apply`. `/for-teachers` gets the real button.
- **New:** a small invitations page holding the Accept buttons now on `/teacher-access`; the banner points there.
- **Redirects:** `/teacher-access` and `/courses/become-teacher` go to `/for-teachers/apply`, so old links keep working.
- **Removed:** "Я преподаватель" from the account menu, the grading schemes page and the "create course" page, plus the wording on `/for-teachers` that names that menu item.
- **Dashboard line:** "Заявка на рассмотрении" while pending; approved or rejected (with your reason) once decided, with a link to apply again.
- **Roster import** moves to a course's People page for whoever administers that course's organization. The same import keeps working for schools.
- **Exam templates in Teaching** also list the templates of the teacher's own personal organization, so the 2 in production stay reachable with no data change.
- **`/org/{personal id}`** typed by hand sends the teacher to Teaching. The platform admin can still open it.
- **Admin → Teacher requests:** shows name, school, subject, phone, and the email.

### What an independent teacher loses
| Today in the Organization area | After |
|---|---|
| Roster import | Moves to the course's People page |
| Courses list | Teaching area already has it |
| Exam templates | Teaching area already has it |
| Exam templates at organization level | Teaching area lists them too (new) |
| Teachers, invitations | Course People page, per course |
| Analytics across all their courses | **Lost for now.** Per-course analytics stay; can be added to Teaching later if wanted |
| Setting: how long enrollment applications are kept | **Lost as a setting.** The stored value keeps applying (30 days by default) |
| Setting: default catalog visibility | Nothing lost: it never had any effect (problem 15). Each course has its own |
| Setting: student invitations on or off | **Lost as a setting.** Stays on |
| Removing a member who accepted a personal-organization invitation | Only you could do it. No such member exists today |
| Departments, shared banks | Never worked for personal organizations |

### Tests
- **Backend:** `/me/lms` for each person in the table; applying (fields, age, rate limit, duplicate, after rejection, after revoke); emails, and none to disabled accounts; refused invitations; export, anonymize and the cleanup job with the new columns; phone absent from audit and logs; permission rules unchanged for org routes; route list updated; test students still refused; applying stays behind the consent gate.
- **Browser:** full sign-up walk (new person; existing student; email already registered); header for each person; no teacher link anywhere for a student; invitation accept from the new page; roster import from People; ORT specs and pixel baselines unchanged.
- **Rehearsal on a copy of production,** before deploy: the migration, then a check that the one active teacher keeps all their courses and loses only the tab.

### Effect on production on the day
One real person changes: your approved teacher loses the Organization tab and keeps everything else except the items marked "lost" above. Students lose the menu item. Nobody is logged out.

## 6. Your decisions

| # | Question | My default |
|---|---|---|
| Q1 | Accept the recommendation (A2, B2, C, no account types)? | Yes |
| Q2 | Minimum age to apply as an independent teacher? | **18+.** The form asks for confirmation; accounts with no age band set it there; a known 14–17 or under-14 account is refused. School invitations aren't limited: the school answers for them. Limits: this is a person's own statement, and someone who turns 18 needs you to change their age band |
| Q3 | How long to keep the applicant's phone? | 90 days after a rejection; while they remain a teacher if approved |
| Q4 | Required fields? | Name, school, subject, phone required. Independent tutors write "Частный преподаватель" as the school. Message optional |
| Q5 | Should a teacher be able to use the platform as a student while waiting? | Yes: it's a normal account until you decide |
| **Q6** | **What should revoking a teacher do to their students?** | **Offer two separate actions.** "Stop new courses": the teacher can't create courses, and existing courses and students carry on. "Freeze": today's behaviour, for abuse: everything read-only. Until Step 3 builds them, keep today's freeze, and make the confirmation state how many students are affected |
| Q7 | How long before someone rejected can reapply? | 7 days, and the page shows the date |

## 7. Open points to check before building
- **The open invitation from a personal organization** (section 3, item 9): if accepted, that person joins the teacher's personal organization, and the new rule wouldn't undo it. It can expire by itself, be revoked, or stay. I'd revoke it only with your OK, since your teacher sent it, and tell the teacher.
- **Email volume:** the provider's free limit isn't known (`docs/COSTS.md`). A few emails per application is tiny, but school-wide sign-ups aren't covered by this.
- **The demo teacher** is `approved` and disabled, and owns no personal organization. Any list of teachers must leave it out.
- **Platform organization in the header:** you see both "Организация" and "Админ-панель". I left it, since you listed that menu as correct. It may fold into the admin control center in Step 3.

## 8. Why this matters for the admin control center (Step 3)
Whichever way you decide, these are what the control center would build on:
- A **Teachers** view separate from **Organizations**: independent teachers, school teachers and applications, without personal organizations cluttering the organization list.
- **Applications with real data** and a recorded decision.
- **Two levels of teacher action** (Q6), each saying who is affected before you confirm.
- **Moving a course between organizations** (problem 12).
- A single rule for "what is this person", already computed in one place and shown to you the way the header shows it to them.
