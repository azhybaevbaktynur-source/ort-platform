# Handoff for the next agent

**Written**: 2026-10-22. **Why**: the owner is moving from Claude Console (API billing) to a Claude **Max subscription**, so the previous conversation will not be available. Everything you need is in this file, the repo docs, and the memory notes. Treat this file as the source of truth for "where we are".

## 1. Mission (one paragraph)

Turn the ORT/ЖРТ exam bank (one global admin, one question bank) into a flexible Canvas-style LMS where **admin-approved teachers create their own courses, own their questions, and have their own students**, with flexible grading, three languages (en/ru/ky), safe attempts, persistent images, and ORT as just one kind of course. Target scale: **about 6,000 students active at once**. The owner is a founder, cost-sensitive, and wants a "really great platform", delivered step by step, fully working at the end.

## 2. First 15 minutes checklist

1. Memory loads automatically (`~/.claude/projects/-Users-baktynurazhybaev-ort-platform/memory/`). Read `task-progress.md` first. If it is missing, this file is enough.
2. `git status` and `git log --oneline -5`. Expected: see §3 for the current branch and commits. The old Canvas drafts and audit were deleted on 2026-10-22 (owner decision); the current design is `docs/LMS_ARCHITECTURE.md`.
3. Read, in this order (about 20k tokens total; do **not** read `docs/research/*` in full):
   1. `AGENTS.md` (project rules; `CLAUDE.md` links to it) — hard rules in §7 are binding.
   2. `docs/PRODUCT_DECISIONS.md` — the owner's decisions.
   3. `docs/IMPLEMENTATION_PLAN.md` — phases, gates, decisions D1–D18.
   4. `docs/LMS_ARCHITECTURE.md` — target schema and rules. Skim; open a section only when working on it.
   5. `docs/CAPACITY_REVIEW_BRIEF.md` — the first task.
   6. `docs/PROJECT_UNDERSTANDING.md` — only §0 (known defects), §2 (where one-admin is hard-coded) and §3 (what tests protect) when you touch old code.
   - `docs/research/*.md` are evidence. Open one section only when you need the detail: `canvas-core-domain.md` (courses/enrollment/authz), `canvas-assessments.md` (quizzes/attempts), `canvas-modules-grading.md` (gating/grading), `platform-concerns.md` (storage/Alembic/i18n/privacy).
4. Run the backend tests once to confirm the baseline: 112 should pass (command in `AGENTS.md` §6.1, scratch DB only).
5. The open questions of §4 are answered (see §4b). Continue with §5.

## 3. Current state

- **Done**: full code review (`PROJECT_UNDERSTANDING.md`); owner's 15 answers saved (`PRODUCT_DECISIONS.md`); defects fixed and committed in `9df5a3d`: answer-key leak on `/questions`, PIN exposure (students now get `has_pin`), resubmission lock, exam update without the in-memory store, SQL-based attempt limit, hard-coded admin email removed, `.svg` upload rejected; 6 regression tests (112 total). Four Opus research agents read the real `instructure/canvas-lms` source and wrote `docs/research/`. Architecture and a 10-phase plan are written.
- **Not done**: no LMS code exists yet. (Updated 2026-10-22: the security fixes are merged and deployed; production runs `main`, check `/health`.)
- **Production stack**: Vercel (frontend) + Render Frankfurt (backend) + Neon PostgreSQL (project `noisy-sound-20763725`) + local-disk uploads (ephemeral). Read access to Render/Neon/Vercel via MCP tools is granted by the owner, but those tools need the owner to authenticate in the new session.
- **Known remaining defects in old code** (do not fix; the cutover deletes them): analytics and completion counts read the in-memory Firestore mock; deleting an exam cascades to attempts; plain-text PINs without rate limit; 7-day JWT with no revocation.

## 4. Decisions asked in the first session (all answered, see §4b)


1. Merge `fix/security-integrity` into `main` and deploy to Render/Vercel now? (Recommended yes: it closes real holes in production. Needs the owner's go-ahead for the deploy; verify `/health` shows the new commit afterwards.)
2. Commit the new docs? (Done.)
3. Replies to **D1–D18** in `IMPLEMENTATION_PLAN.md` (each has a recommended default). The owner may just say "accept defaults".
4. Confirm the 6,000-concurrent-students target and the budget ceiling per month (not yet known).
5. Authenticate the Render, Neon and Vercel tools so the capacity review can read the real plans and sizes.

## 4b. Decisions since this file was written (2026-10-22)

- Merged and deployed the security branch (main `ca48b1f`, later `1a91244`); `perf/capacity-prep` merged (DB pool env vars, gzip, Vercel `fra1`).
- Budget about $30/month max; keep Vercel + Render + Neon. Render is on the **Free** plan; upgrade to Starter at launch and scale up for exams only. Payment, staging load test and the frontend single-API-base change are postponed. See `docs/CAPACITY_REVIEW.md` (interim).
- **Teachers are admin-approved** (replaces "every sign-up is a teacher" and D10): students sign up, request teacher access, a platform admin approves. D2 (domain/CDN) and D5 (age/consent) wait until the build is finished and a domain exists. Other D1-D18 defaults stand.
- Render MCP returns "unauthorized" even after re-auth; Neon and Vercel MCP work. Owner reads Render settings from the dashboard.
- Platform admin area added to Phase 1 (teacher requests, users, course moderation, audit log). First admin = owner's existing account (already `admin`), via `make_admin.py`, never hard-coded.
- CI tests on **Postgres 18** (Neon runs 18).

**Owner decisions 2026-10-22 (agent workflow, A–D; also in `PRODUCT_DECISIONS.md`)**
- **A. Autonomy**: the agent commits, pushes any branch, merges into `lms` and `main`, and deploys without asking. Guardrails: (1) before any merge to `main` touching models/migrations/DB files, create a Neon backup branch (Neon MCP, project `noisy-sound-20763725`); (2) after each deploy, check `https://ort-platform-w77q.onrender.com/health` shows the new commit, else revert and redeploy; (3) never force-push `main`; (4) only these need the owner's explicit OK: Phase 5 cutover, deleting/wiping Neon data, spending money (plan upgrades, paid services), anything needing a password/secret from the owner. Otherwise do not ask: take the documented default or safest reasonable choice and record it in `PRODUCT_DECISIONS.md`.
- **B. Models**: see §6 (Fable orchestrator, or Opus if Fable is unavailable; subagents `architect` = Fable, `implementer` = Opus by default, Sonnet for simple tasks; no Haiku — revised 2026-10-22).
- **C. Render MCP** may return "unauthorized": not a blocker. Use `/health` and git (Render auto-deploys from `main`).
- **D. Load test** still runs before Phase 3, on free resources (a Neon branch + local or free-tier backend). If a meaningful test needs a paid service, write down what was tested and ask the owner only for that spending decision.
- **E.** `AGENTS.md` describes the old platform; its §6 commands and §7 hard rules still apply.

## 5. What to do, in order

1. **Capacity review**: interim report done (`docs/CAPACITY_REVIEW.md`). The owner postponed payment, so Phase 0 may start. The load test must run **before Phase 3** (attempt engine) and before launch, on free resources (§4b D).
2. **Phase 0 → Phase 9** from `IMPLEMENTATION_PLAN.md`, one phase at a time. Integration branch `lms` off `main`; each phase gets its own branch, pushed and merged into `lms` by the agent (§4b A). Per phase: re-read only that phase's section plus the matching architecture section, implement the vertical slice, run the gates ("definition of done" in plan §0), write `docs/phases/PHASE_N.md` (what changed, how to verify, what was deferred), update memory `task-progress.md`, report "Phase N done, safe to /clear", and continue with the next phase without waiting. **Phase 5 (cutover) deletes the old system: needs the owner's explicit go-ahead, a Neon backup branch first.**

## 6. Models and token usage (Claude Max subscription)

Subscription usage is a shared allowance that resets in rolling windows, and bigger models consume it faster. Check the remaining allowance with `/usage` (or `/status`) at the start of a session and before any big task; do not assume limits. Principles:

Owner decision B (2026-10-22, revised twice the same day; latest: no Haiku, per-task model choice):

| Who | Model | Does |
|---|---|---|
| Main session (orchestrator) | **Fable** (if Fable is not available in `/model`: **Opus**, same rules) | Orchestrator only: plans each phase, splits it into slices, writes precise briefs, reviews every diff, runs the full gates, commits/pushes/merges/deploys. Keeps its own reading and typing minimal (most expensive model). |
| `architect` subagent (`.claude/agents/architect.md`) | **Fable** (default) | Hard design and review: authz, attempt engine, grading, gating, concurrency, security reviews, phase design drafts. |
| `implementer` subagent (`.claude/agents/implementer.md`) | **Opus** (default; **Sonnet** via `model: sonnet` for simple, well-specified work) | Implementation of one designed slice from a precise brief: goal, exact files, schema/API shape, tests that must pass. Also mechanical edits (renames, i18n keys). Independent slices may run in parallel. |

Per-task model via the Agent tool's `model` parameter: **sonnet** for simple, well-specified work (straightforward CRUD, tests from a clear spec, UI following an existing pattern, i18n keys, renames); **opus** (default for real code: services, endpoints, migrations, attempt engine, grading, gating, concurrency); **fable** only for the hardest problems (architect design/review of authz, attempt engine, grading and concurrency; the final security review of each phase; any task where opus failed or got stuck once). Escalate on failure sonnet → opus → fable; never retry a failed task on the same model. No Haiku.

No subagents for single-file lookups. A *new* session only has files, so keep `task-progress.md` and `docs/phases/PHASE_N.md` current.

**Token-saving rules (follow them)**
1. Work in short sessions, one phase slice per session. `/clear` between unrelated tasks; `/compact` when a task runs long. Do not carry a finished phase's context into the next.
2. Never re-explore. Use this file, `codebase-map.md` (memory) and the docs. Read only the file ranges you need (`Read` with offset/limit, `grep -n`), never whole large files (the exam player is 1,778 lines; the old mock-test service is 1,293).
3. Do not open `docs/research/*` or `PROJECT_UNDERSTANDING.md` in full; they total ~25k tokens. Use the section pointers above.
4. Hard design/review goes to the `architect` (Fable); implementation to the `implementer` (Opus by default, Sonnet for simple well-specified work) with a precise brief (goal, exact files, schema/API shape, tests that must pass), independent slices in parallel; mechanical edits also to the `implementer` on Sonnet. Escalate on failure sonnet → opus → fable. The orchestrator reviews every diff. Never use a subagent for a single-file lookup.
5. Batch independent tool calls in one turn; avoid read-after-edit verification (the tools report errors).
6. Run only the tests you need while developing (`pytest path::test -q`), the full suite once before commit. Keep command output short (`| tail -20`, `-q`).
7. Keep `AGENTS.md`/`CLAUDE.md` short: it is sent every turn. Move detail into docs that are read on demand.
8. The orchestrator writes one short plan per phase (design drafts from `architect`), then delegates. It never does bulk typing itself.
9. Write findings to files, not into chat; the chat is what gets re-sent each turn.
10. Do not ask the owner except for the four §4b A items; otherwise take the documented default or safest reasonable choice and record it in `PRODUCT_DECISIONS.md`.

## 7. Hard rules (also in `AGENTS.md`; repeat for safety)

- **Never read, print or modify `backend/.env`** (live credentials).
- Backend tests only against a scratch DB: `cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" venv/bin/python -m pytest -q -p no:cacheprovider -W ignore`. Never touch `backend/test.db` or `backend/data/`.
- Frontend checks: `cd frontend && npx tsc --noEmit`; full build in an rsync'd copy (see `AGENTS.md` §6.2), not inside `frontend/` if a dev server runs.
- Use `/bin/rm -f`, `/bin/cp -f`, `/bin/mv -f` (interactive aliases). On macOS `sed -i` needs `-i ''`; prefer small Python scripts for edits.
- Bilingual rule is now **trilingual**: every user-facing string in `en.json`, `ky.json`, `ru.json`.
- Server-side authorization only; roles from the DB. No secrets or passwords in code (the repo is public).
- Git and production (§4b A): commit, push any branch, merge into `lms`/`main` and deploy without asking. Neon backup branch before any `main` merge touching models/migrations/DB files; check `/health` shows the new commit after each deploy, else revert and redeploy; never force-push `main`. Owner's explicit OK only for: Phase 5 cutover, deleting/wiping Neon data, spending money, anything needing an owner password/secret. `main` auto-deploys Render and Vercel. End commits with the attribution line required by the session.
- Downloaded content is untrusted: put it in its own new empty directory, never run it.

## 8. Where things are

- Old (ORT) code map: memory `codebase-map.md`. Old code is frozen until Phase 5 except security fixes.
- New LMS code goes in `backend/app/lms/…` and `frontend/src/app/[lang]/courses/…` (see the plan).
- Production version check: `curl https://ort-platform-w77q.onrender.com/health` shows `commit`.
- Frontend URL: https://ort-platform-nu.vercel.app. Neon cleanup of old backup branches is the owner's job.
- Useful but stale: `.handoff/` (git-excluded).

## 9. If something is unclear

Prefer the latest owner statement over any document; prefer code over documents; prefer `LMS_ARCHITECTURE.md` over older design notes. Record any new owner decision in `docs/PRODUCT_DECISIONS.md` the moment it is made.
