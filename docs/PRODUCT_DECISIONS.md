# Product decisions (owner answers, 2026-10-21)

Source: answers to the 15 open questions in `PROJECT_UNDERSTANDING.md` §8. The Canvas documents in `docs/` are drafts; nothing in them is binding. Real goals first, flexible design.

**Goal**: a flexible, safe, Canvas-style LMS where teachers have their own students, build and restructure their own courses, and own their own questions. ORT (exam, scoring, ky/ru) must keep working, as just one kind of course.

| Topic | Decision |
|---|---|
| Teachers | **Superseded 2026-10-22**: see "Decisions 2026-10-22 (teachers)" below. Originally: self sign-up, a sign-up is a teacher. Roles stay per enrollment. |
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
| Production access | Read access to Render/Neon granted for measuring. (Extended 2026-10-22: see "agent workflow" A below.) |
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

## Decisions 2026-10-22 (teachers)

| Topic | Decision |
|---|---|
| Who can create courses | Only **admin-approved teachers**. Everyone who signs up is a student. A user may request teacher access; a platform admin approves or rejects it. Revocable. (Replaces self sign-up as teacher and D10.) |
| Age (D5) | Not a problem for course creation, because an admin verifies every teacher first. Student minimum age and consent wording are deferred. |
| D2 (domain/CDN) and D5 (age/consent) | Postponed until the overall build is finished and a domain exists. |
| Platform admin | Approves teacher requests (and does support/moderation). Role is read from the database on every request. |
| Admin area | A platform admin page: teacher requests, users, course moderation, audit log. |
| First admin | The owner's existing account (already `admin` in production). Set via `make_admin.py`, never hard-coded. |

## Decisions 2026-10-22 (agent workflow)

| Topic | Decision |
|---|---|
| A. Autonomy | The agent may commit, push any branch, merge into `lms` and `main`, and deploy without asking. Guardrails: (1) before any merge to `main` touching models/migrations/DB files, create a Neon backup branch (Neon MCP, project `noisy-sound-20763725`); (2) after each deploy, check `https://ort-platform-w77q.onrender.com/health` shows the new commit, else revert and redeploy; (3) never force-push `main`; (4) only these need the owner's explicit OK: Phase 5 cutover, deleting/wiping Neon data, spending money (plan upgrades, paid services), anything needing a password/secret from the owner. Otherwise the agent does not ask: it takes the documented default or safest reasonable choice and records it here. |
| B. Models | Main session on **Opus** as orchestrator: plans each phase, design decisions, reviews every subagent diff, authz/attempt-engine/grading reviews, runs the gates, commits/pushes/merges/deploys. Bulk implementation goes to a **Sonnet** subagent `implementer` with precise briefs (goal, exact files, schema/API shape, tests that must pass); independent slices may run in parallel. Optional **Haiku** subagent `helper` for mechanical edits. No subagents for single-file lookups. |
| C. Render MCP | May return "unauthorized"; not a blocker. Use `/health` and git (Render auto-deploys from `main`). |
| D. Load test | Still must run before Phase 3, on free resources (a Neon branch + local or free-tier backend). If a meaningful test needs a paid service, write down what was tested and ask the owner only for that spending decision. |
| E. `AGENTS.md` | Describes the old platform; its §6 commands and §7 hard rules still apply. Current plan and rules: `HANDOFF_NEXT_AGENT.md`. |
| Production access | Supersedes "read access only" above: write access within rule A. |