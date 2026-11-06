# Admin control center: review and suggestions

For the owner (Step 3 of the 2026-11-03 feedback). Review only: nothing here is built. Everything below was checked against the code on 2026-11-03, the main claims twice. Your details may change this: treat it as a starting point for them.

## 1. In short

**The biggest risk isn't a missing screen. It's that the platform is controlled by one password.** There is no second login factor, only one admin, and adding another admin needs direct database access. If your password or email is stolen, someone else controls everything, and nothing inside the app can lock them out.

My suggestion, in order:
1. **Protect control itself** (section 4, part A): two-step login, a spare admin account, sessions you can end.
2. **Handle one person's problem** (part B): find anyone, see their state, and fix it without touching the database.
3. **Handle a harmful course** (part C): look at it and take down just what's wrong.
4. **Run an exam day** (part D): see who is in the exam, whether the system is healthy, and tell everyone something.
5. **Set up and move things** (part E): schools, handing courses over, the two teacher actions you asked for in Q6.

Parts A–D should be done before real students arrive. All of it runs on what you already have, with no new paid service.

## 2. What you can do today

| Area | You can | You can't |
|---|---|---|
| **Overview** | See waiting applications and the storage level | See anything else: users, activity, health |
| **Users** | Search by email start or name; disable and enable; grant or revoke teacher; see their courses | See age, consent state or last login; change an email; end sessions without disabling; trigger a password reset |
| **Teacher applications** | Read them with full details; approve; reject | Search them |
| **Organizations** | Create; suspend and resume; manage members; grant templates | Create a school and invite its admin in one step |
| **Courses** | List; see the roster; delete and restore; hide from the catalog; change owner within the same organization | **Open the content; remove one page, file or announcement; move to another organization** |
| **Exams, attempts, grades** | Nothing across the platform. Teachers fix scores and void attempts | See whether a student's attempt exists; see who is in an exam now |
| **Privacy** | Handle data requests | Correct an age band: the function exists but **has no screen**. Look up parent links. Start an export for someone |
| **Audit log** | Filter by action, person and type of object | Filter by date; search; export |
| **Storage** | See totals; run the R2 check | See what uses the space, below organization level |
| **System** | Nothing in the app | See real health. **`/health` says "database: connected" without checking the database.** It only proves the server started |
| **Messages** | Nothing | Tell all users anything: no banner, no announcement above course level |

## 3. What happens in real incidents today

| Incident | What you can do today | The problem |
|---|---|---|
| **Your account is stolen** | Nothing in the app. You can't be disabled, and there's no second factor. Only rotating `SECRET_KEY` on Render, or `make_admin.py` with database access | **The worst case. Also: `make_admin.py --revoke` can remove the last admin** |
| A teacher's account is stolen | Disable it (ends their sessions) | You can't see recent logins, or end sessions without locking them out |
| A student typed the wrong email | Nothing. **No screen anywhere can change an email** | They are stuck; a new account loses their courses |
| A student says "my exam answers were lost" | Nothing: you can't see that attempt exists. Only the teacher can | You run the platform but can't answer them |
| A teacher posts something harmful | Hide or delete the whole course, or freeze the teacher | **You can't open it to check first,** and removing one bad page isn't possible. There's no way for anyone to report it |
| Exam day | Watch `/health`, which doesn't check the database | No count of who is in an exam, no health view, no way to tell everyone "we know about the problem" |
| A teacher leaves | Change the owner, only to someone already in that organization | Can't hand over all their courses at once |
| An independent teacher joins a school | Nothing | **Their courses can't move to the school** |
| A school signs up | Create it, then invite the admin separately | Works, in several steps. One school setting does nothing: default catalog visibility |
| You revoke the wrong teacher | Grant again, which restores everything | Students were frozen meanwhile, and the teacher got two emails |
| An approved teacher turns out to be a minor | Age correction has no screen, and it doesn't touch their teacher status | You'd never notice the conflict |
| Spam sign-ups | The limit of 120 per hour per address | Can't see or clean up accounts that never confirmed their email |
| A parent asks about their child's data | Handle a request the family already filed | Can't check whether a parent link exists |

**Correction to what I told you about revoking.** A freeze stops new tests, hand-ins and joins, but **a student already inside a test can finish and submit**, because attempts don't check for a frozen organization. That is the safe behaviour, and I'd keep it.

## 4. What I suggest building

### Part A: protect control (first, before anything else)
- **Two-step login for platform admins:** an authenticator app code at login, plus printed recovery codes. No phone or SMS needed, so no cost.
- **A spare admin account,** used only in an emergency, with its details kept offline. And `make_admin.py` refuses to remove the last admin.
- **"End all sessions"** for any user, and for yourself on every device.
- **Every admin action names who did it, with a reason.** Mostly true already; the audit log gets date filters and export.
- **Real health:** database, email and storage actually tested, shown to you only. The public `/health` stays cheap and honest.

### Part B: one person's problem
**A person page** that answers "what's going on with this account?":
- Age band, consent state, last login, email confirmed or not, teacher state, courses, parent links.
- Actions: change email (with a confirmation to the new address and a notice to the old one), send a password reset, end sessions, correct age, disable and enable.
- Better search, and a filter for never-confirmed accounts, with cleanup.
- **Attempt lookup:** that attempt exists, its status, when it started, how many answers were saved, without showing the answers. This lets you answer "my answers were lost", and tell the teacher what to do. Fixing scores stays with teachers.

### Part C: a harmful course
- **Read-only look inside any course's content:** pages, files, announcements, quizzes. Needs a reason, is recorded, and excludes students' answers and grades.
- **Take down one item,** with a reason shown to the teacher, instead of the whole course.
- **A "report" button** for students and parents, feeding your queue. This needs your contact details and lawyer's view first.

### Part D: exam day
- **Live panel:** students in an exam now, per exam; recent failures; how busy the server is.
- **Banner to everyone,** or to one course's students: "We know about the problem". Never shown inside the exam player unless you explicitly choose, since exam screens must not change.
- No mass email for now: the provider's limits are unknown (`docs/COSTS.md`).

### Part E: set up and move
- **The two teacher actions from Q6.** "Stop new courses" (students carry on) and "Freeze" (everything stops), each saying who is affected first. The first needs a new flag on the person, checked wherever courses are created, and it must not touch the organization's status, because that's what freezes students.
- **"Create school + invite its admin"** as one step.
- **Move a course to another organization,** and **hand over all of one teacher's courses.**
- **An "Attention" list on the overview:** applications, data requests, storage warnings, approved teachers who are minors, frozen teachers with students. One place to start the day.
- **Teachers** as its own list, separate from organizations, so personal organizations don't clutter it. The demo teacher stays out.
- Fix or remove the "default catalog visibility" setting.

### How the center would look
**Overview** (attention list, numbers, health) · **People** · **Teachers** (with applications) · **Organizations** · **Courses** · **Exam templates** · **Exam day** · **Privacy** · **Audit log** · **System** (storage, health, checks). Today's menu reorganized around the jobs above, with Exam day added.

## 5. What I'd keep out, or fence in

| Idea | My view | Why |
|---|---|---|
| **Logging in as a user** | **No, for now.** Use the person page and the attempt lookup | It shows minors' private data, and it would pass the checks that protect exams and consent. If ever added: read-only, time-limited, recorded, never for exams |
| **Editing grades or attempts as admin** | **No** | Grades are an append-only record. The teacher's existing correction, with a reason, stays the only way. If you must, make yourself course staff, which is visible and recorded |
| **Bulk actions** (disable all, revoke all) | **No, for now** | One mistake would freeze many students. Hand-over of one teacher's courses is the one exception |
| **Permanent delete from the center** | **Only through privacy requests** | Courses stay restorable. Files in R2 can't be restored |
| **Showing an applicant's or student's phone or age everywhere** | Only where needed, and viewing is recorded | Minors' data; the lawyer's view applies |
| **Changing ORT exam rules from the center** | **No** | Your rule: ORT doesn't change |

## 6. Your decisions

| # | Question | My default |
|---|---|---|
| A1 | Build in the order A → B → C → D → E? | Yes |
| A2 | Two-step login required for platform admins? | Yes, required |
| A3 | A spare emergency admin account? | Yes. You keep its details offline. I never see them |
| A4 | Let yourself read course content, with a reason and a record? | Yes, content only, never students' answers or grades |
| A5 | Logging in as a user? | No |
| A6 | A report button for students and parents? | Yes, but after your contact details and the lawyer's review |
| A7 | When an approved teacher turns out to be a minor? | Put it on your attention list. No automatic revoke, since that would freeze their students |
| A8 | "Stop new courses": in their own courses only, or in schools too? | Own courses only. A school decides for itself |
| A9 | Email changes: can users do it themselves? | Yes, with confirmation at the new address and a notice to the old one. You can also do it for them |

Tell me what you'd add or change: you said you'd send your own details for this step, and they take priority over this list.

## 7. Small things found on the way

Not urgent, but they shouldn't get lost. I'd do them within part A or B:
- `make_admin.py` also makes the person an approved teacher, skipping the new age and disabled checks.
- Enabling a user doesn't check whether their data was already deleted through a privacy request.
- `PATCH` for course template locks exists with no screen, and two cleanup tools have no screen: test-student files and old practice data.

## 8. Revision 2026-11-06: the new direction
The owner chose individual students first, ORT first, free and paid exams, and tutors and schools later (`ROADMAP_EXAM_PREP.md`). The facts above were rechecked: no admin code changed since 2026-11-03. What the new direction changes:
- **Order:** A (protect control) → B (person page) **together with payments control** → D in a light form (real health, banner) → C → E. Teachers are few for now, so C and E wait; E returns with tutors and schools.
- **New, A10:** payments control: see a student's access and codes, grant or extend access with a reason, create code batches, see how many were used. Every action is recorded.
- **New, A11:** for the AI chat when it comes: a monthly cost limit and an off switch on the admin page.
- **A8** has no effect until tutors and schools return.
- Defaults A1–A7 and A9 stand. A2 and A3 are built in S1; A9 in S4.
