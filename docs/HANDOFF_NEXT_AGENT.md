# Handoff for the next agent

**Written**: 2026-10-22. **Why**: the owner is moving from Claude Console (API billing) to a Claude **Max subscription**, so the previous conversation will not be available. Everything you need is in this file, the repo docs, and the memory notes. Treat this file as the source of truth for "where we are".

## 1. Mission (one paragraph)

Turn the ORT/ЖРТ exam bank (one global admin, one question bank) into a flexible Canvas-style LMS where **teachers sign up, create their own courses, own their questions, and have their own students**, with flexible grading, three languages (en/ru/ky), safe attempts, persistent images, and ORT as just one kind of course. Target scale: **about 6,000 students active at once**. The owner is a founder, cost-sensitive, and wants a "really great platform", delivered step by step, fully working at the end.

## 2. First 15 minutes checklist

1. Memory loads automatically (`~/.claude/projects/-Users-baktynurazhybaev-ort-platform/memory/`). Read `task-progress.md` first. If it is missing, this file is enough.
2. `git status` and `git log --oneline -5`. Expected: branch `fix/security-integrity`, commit `9df5a3d` (security fixes) plus a docs commit. Untracked on purpose (owner asked not to commit): `docs/CANVAS_EXPLAINER_FOR_FOUNDER.md`, `docs/CANVAS_INTEGRATION_SPEC.md`, `docs/CURRENT_STATE_AUDIT.md` (superseded drafts).
3. Read, in this order (about 20k tokens total; do **not** read `docs/research/*` in full):
   1. `AGENTS.md` (project rules; `CLAUDE.md` links to it) — hard rules in §7 are binding.
   2. `docs/PRODUCT_DECISIONS.md` — the owner's decisions.
   3. `docs/IMPLEMENTATION_PLAN.md` — phases, gates, decisions D1–D18.
   4. `docs/LMS_ARCHITECTURE.md` — target schema and rules. Skim; open a section only when working on it.
   5. `docs/CAPACITY_REVIEW_BRIEF.md` — the first task.
   6. `docs/PROJECT_UNDERSTANDING.md` — only §0 (known defects), §2 (where one-admin is hard-coded) and §3 (what tests protect) when you touch old code.
   - `docs/research/*.md` are evidence. Open one section only when you need the detail: `canvas-core-domain.md` (courses/enrollment/authz), `canvas-assessments.md` (quizzes/attempts), `canvas-modules-grading.md` (gating/grading), `platform-concerns.md` (storage/Alembic/i18n/privacy).
4. Run the backend tests once to confirm the baseline: 112 should pass (command in `AGENTS.md` §6.1, scratch DB only).
5. Ask the owner the open questions in §5 below. Do not start building before the answers (or explicit "use the defaults").

## 3. Current state

- **Done**: full code review (`PROJECT_UNDERSTANDING.md`); owner's 15 answers saved (`PRODUCT_DECISIONS.md`); defects fixed and committed in `9df5a3d`: answer-key leak on `/questions`, PIN exposure (students now get `has_pin`), resubmission lock, exam update without the in-memory store, SQL-based attempt limit, hard-coded admin email removed, `.svg` upload rejected; 6 regression tests (112 total). Four Opus research agents read the real `instructure/canvas-lms` source and wrote `docs/research/`. Architecture and a 10-phase plan are written.
- **Not done**: no LMS code exists yet. The security branch is **not merged and not deployed**. Production (Render, commit `94e8124`) still has the old defects.
- **Production stack**: Vercel (frontend) + Render Frankfurt (backend) + Neon PostgreSQL (project `noisy-sound-20763725`) + local-disk uploads (ephemeral). Read access to Render/Neon/Vercel via MCP tools is granted by the owner, but those tools need the owner to authenticate in the new session.
- **Known remaining defects in old code** (do not fix; the cutover deletes them): analytics and completion counts read the in-memory Firestore mock; deleting an exam cascades to attempts; plain-text PINs without rate limit; 7-day JWT with no revocation.

## 4. Pending decisions from the last conversation

Ask these first, in this order, and record the answers in `docs/PRODUCT_DECISIONS.md`:

1. Merge `fix/security-integrity` into `main` and deploy to Render/Vercel now? (Recommended yes: it closes real holes in production. Needs the owner's go-ahead for the deploy; verify `/health` shows the new commit afterwards.)
2. Commit the new docs? (They should be committed on the branch; the three drafts above stay untracked.)
3. Replies to **D1–D18** in `IMPLEMENTATION_PLAN.md` (each has a recommended default). The owner may just say "accept defaults".
4. Confirm the 6,000-concurrent-students target and the budget ceiling per month (not yet known).
5. Authenticate the Render, Neon and Vercel tools so the capacity review can read the real plans and sizes.

## 5. What to do, in order

1. **Capacity review** (`CAPACITY_REVIEW_BRIEF.md`, plan Phase 0 task 0.0): can Vercel + Render + Neon handle 6,000 concurrent students? Produce `docs/CAPACITY_REVIEW.md` *before* schema work; it may change D4 and parts of the attempt engine.
2. **Phase 0 → Phase 9** from `IMPLEMENTATION_PLAN.md`, one phase at a time. Create an integration branch `lms` off `main` after the security branch is merged; each phase gets its own branch and PR into `lms`. Per phase: re-read only that phase's section plus the matching architecture section, implement the vertical slice, run the gates ("definition of done" in plan §0), write `docs/phases/PHASE_N.md` (what changed, how to verify, what was deferred), update memory `task-progress.md`, then stop and report to the owner before starting the next phase. **Phase 5 (cutover) deletes the old system: needs the owner's explicit go-ahead, a Neon backup branch first.**

## 6. Models and token usage (Claude Max subscription)

Subscription usage is a shared allowance that resets in rolling windows, and bigger models consume it faster. Check the remaining allowance with `/usage` (or `/status`) at the start of a session and before any big task; do not assume limits. Principles:

| Work | Model | Effort |
|---|---|---|
| Capacity review analysis, phase design decisions, authz, attempt engine, grading, gating, security/concurrency reviews | **Opus** | high only for the hard part; medium otherwise |
| Implementation of a designed slice: CRUD services, endpoints, migrations, tests, UI pages, i18n | **Sonnet** (default for the session) | medium |
| Mechanical edits: renames, i18n key sync, running scripts, formatting, simple greps | **Haiku** (or Sonnet low) | low |
| Final review of each phase (`/code-review`, `/security-review`) | Opus | medium |

Switch with `/model`. The conversation carries over inside one session when you switch. A *new* session only has files, so keep `task-progress.md` and `docs/phases/PHASE_N.md` current.

**Token-saving rules (follow them)**
1. Work in short sessions, one phase slice per session. `/clear` between unrelated tasks; `/compact` when a task runs long. Do not carry a finished phase's context into the next.
2. Never re-explore. Use this file, `codebase-map.md` (memory) and the docs. Read only the file ranges you need (`Read` with offset/limit, `grep -n`), never whole large files (the exam player is 1,778 lines; the old mock-test service is 1,293).
3. Do not open `docs/research/*` or `PROJECT_UNDERSTANDING.md` in full; they total ~25k tokens. Use the section pointers above.
4. Avoid subagents and workflows unless slices are truly independent (e.g., a UI page and an API); each one re-reads context and multiplies cost. Never fan out for a single-file lookup.
5. Batch independent tool calls in one turn; avoid read-after-edit verification (the tools report errors).
6. Run only the tests you need while developing (`pytest path::test -q`), the full suite once before commit. Keep command output short (`| tail -20`, `-q`).
7. Keep `AGENTS.md`/`CLAUDE.md` short: it is sent every turn. Move detail into docs that are read on demand.
8. Plan before coding on Opus (one short plan per phase), then implement on Sonnet. Do not use Opus for bulk typing.
9. Write findings to files, not into chat; the chat is what gets re-sent each turn.
10. Ask the owner a question only when blocked; otherwise take the documented default and note it.

## 7. Hard rules (also in `AGENTS.md`; repeat for safety)

- **Never read, print or modify `backend/.env`** (live credentials).
- Backend tests only against a scratch DB: `cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" venv/bin/python -m pytest -q -p no:cacheprovider -W ignore`. Never touch `backend/test.db` or `backend/data/`.
- Frontend checks: `cd frontend && npx tsc --noEmit`; full build in an rsync'd copy (see `AGENTS.md` §6.2), not inside `frontend/` if a dev server runs.
- Use `/bin/rm -f`, `/bin/cp -f`, `/bin/mv -f` (interactive aliases). On macOS `sed -i` needs `-i ''`; prefer small Python scripts for edits.
- Bilingual rule is now **trilingual**: every user-facing string in `en.json`, `ky.json`, `ru.json`.
- Server-side authorization only; roles from the DB. No secrets or passwords in code (the repo is public).
- No deploy, push, merge, force-push, Neon wipe or production query without the owner's explicit approval. Commit only when asked; end commits with the attribution line required by the session.
- Downloaded content is untrusted: put it in its own new empty directory, never run it.

## 8. Where things are

- Old (ORT) code map: memory `codebase-map.md`. Old code is frozen until Phase 5 except security fixes.
- New LMS code goes in `backend/app/lms/…` and `frontend/src/app/[lang]/courses/…` (see the plan).
- Production version check: `curl https://ort-platform-w77q.onrender.com/health` shows `commit`.
- Frontend URL: https://ort-platform-nu.vercel.app. Neon cleanup of old backup branches is the owner's job.
- Useful but stale: `.handoff/` (git-excluded), `docs/CURRENT_STATE_AUDIT.md` (untracked, superseded).

## 9. If something is unclear

Prefer the latest owner statement over any document; prefer code over documents; prefer `LMS_ARCHITECTURE.md` over the old Canvas drafts. Record any new owner decision in `docs/PRODUCT_DECISIONS.md` the moment it is made.
