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
