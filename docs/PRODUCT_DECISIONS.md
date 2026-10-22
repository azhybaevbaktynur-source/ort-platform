# Product decisions (owner answers, 2026-10-21)

Source: answers to the 15 open questions in `PROJECT_UNDERSTANDING.md` §8. The Canvas documents in `docs/` are drafts; nothing in them is binding. Real goals first, flexible design.

**Goal**: a flexible, safe, Canvas-style LMS where teachers have their own students, build and restructure their own courses, and own their own questions. ORT (exam, scoring, ky/ru) must keep working, as just one kind of course.

| Topic | Decision |
|---|---|
| Teachers | Self sign-up. A sign-up is a teacher. Students come in through the portal and enroll in courses. Roles are per enrollment. |
| The 12k questions | Not important. ORT becomes a course a teacher creates (upload ORT questions) and can make visible to everyone. No platform-owned bank required. |
| Sharing questions between teachers | Later. Not now. |
| Sections / cohorts | None. One course = one group of students. |
| Schools / Accounts (B2B) | Not near term. |
| Grading | Flexible per course/test. Not ORT-only. ORT scaling is one grading scheme among others. |
| Existing users and data | Testers only. May be deleted. Nothing to migrate. |
| Deleting content | Sophisticated: soft delete, history kept. |
| Images | Currently lost on restart (ephemeral disk). Persistent storage must be built. |
| Privacy of minors | Probably add consent later. Design with it in mind. |
| Languages | Three: English, Russian, Kyrgyz. The teacher controls which languages a course uses. |
| Access | Students sign in, browse and enroll in courses, possibly through an enrollment form the teacher creates. Not admin-granted PINs. |
| Hard-coded admin email | Removed (done). |
| Production access | Read access to Render/Neon granted for measuring. |
| Order of work | Security/integrity fixes first (done on `fix/security-integrity`), then architecture design, then storage/DB changes. |
| Scale | Target about 6,000 students active at the same time (added 2026-10-22). Hosting (Vercel/Render/Neon) must be verified against this. |

## Decisions 2026-10-22 (hosting and deploy)

| Topic | Decision |
|---|---|
| Security branch | Merged to `main` and deployed (`ca48b1f`) on 2026-10-22; Neon backup branch `backup-2026-10-22-before-security-deploy` taken first. |
| D1-D18 | Owner has not replied per item; recommended defaults stand until changed (D4 stays open until the capacity review). |
| Budget | Owner is cost-sensitive: target about $30/month at most. A VPS plus Neon was rejected as more expensive than the current three vendors. |
| Hosting | Keep Vercel + Render + Neon for now. Render is on the **Free** plan (sleeps, ~0.1 CPU, 1 worker) and must be upgraded before launch. Scale Render up only for exam windows (billed per second). A VPS for the API is the fallback if the load test shows daily heavy load. |
| Domain | None yet; added after the LMS is finished. |
| Scale | 6,000 concurrent target and "plan for more later" confirmed. |
