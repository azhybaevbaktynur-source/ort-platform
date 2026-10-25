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
   5. `docs/UX_GUIDELINES.md` (UX rules and the UX gate) and `docs/phases/PHASE_6_DESIGN.md` when working on Phase 6.
   6. `docs/PROJECT_UNDERSTANDING.md` — only §0 (known defects), §2 (where one-admin is hard-coded) and §3 (what tests protect) when you touch old code.
   - `docs/research/*.md` are evidence. Open one section only when you need the detail: `canvas-core-domain.md` (courses/enrollment/authz), `canvas-assessments.md` (quizzes/attempts), `canvas-modules-grading.md` (gating/grading), `platform-concerns.md` (storage/Alembic/i18n/privacy).
4. Run the backend tests once to confirm the baseline: 2497 pass, 21 skipped (command in `AGENTS.md` §5, scratch DB only).
5. The open questions of §4 are answered (see §4b). Continue with §5.

## 3. Current state (updated 2026-10-24)

- **Done**: Phases 0-4 on `lms`; **Phase 5 (ORT cutover) built** on `phase-5/cutover` (old exam system, Firebase mock and mock tokens removed; ORT = two platform courses; catalog + join; R2 free-tier guard). Details: `docs/phases/PHASE_5.md`. Tests: SQLite 2497 passed / 21 skipped, PG ~2552, i18n 1586 keys, Alembic head `0007_phase5_storage`.
- **Cutover deployed 2026-10-23 06:02 UTC** (`main` 6fc3d38, /health OK; Neon at `0007_phase5_storage`; pre-cutover backup branch `backup-2026-10-23-before-phase5`, untouched copy `rehearsal-2026-10-23-phase5`). Rollback = revert `main` + restore Neon from the backup branch (0006 is one-way). Waiting on the owner: one click on "Run R2 check" in `/[lang]/admin/storage`.
- **Owner decisions 2026-10-24** (`PRODUCT_DECISIONS.md`, "Owner decisions 2026-10-24"): ORT must not change (locked, admin-granted course template wrapping the existing ORT code; parity gate every phase); institutional organizations (org admins invite teachers; students self-enroll; no teacher choice at sign-up); assignments become the gradable unit; UX gate every phase. The plan's "Alternatives to discuss" (end of `IMPLEMENTATION_PLAN.md`) wait for the owner.
- **H1 hotfix released 2026-10-24** (general-assessment player crash on titled sections, error boundary; `main`, /health checked). **Owner's second-round answers applied** (`PRODUCT_DECISIONS.md` "Owner decisions 2026-10-24 (second round)"): personal organizations for independents (no bank sharing between them), org admins read-only inside courses + roster + `join-as-teacher`, owner owns ORT, A10 alias fix with identical-import proof, 6a/6b separate releases, placeholders for the owner's org name/slug, invitation sender "{inviter} via {appName}", **ORT review every phase** (functionality unchanged, look keeps up; `IMPLEMENTATION_PLAN.md` §0.4).
- **Phase 6a built 2026-10-25** (`docs/phases/PHASE_6A.md`, decisions I1–I11 in `PRODUCT_DECISIONS.md`): organizations + personal orgs (migration `0008_phase6_organizations`), course template registry with ORT wrapped and locked, invitations, org admin and platform organization pages; SQLite ~2630 passed, PG green, ORT golden imports + walkthrough green, UX gate in `docs/phases/PHASE_6_screens/6a/`. Next: deploy, owner checkpoint, then 6b.
- **Owner approved 2026-10-25** (`PRODUCT_DECISIONS.md` "third round"): the Phase 6 design and the exam template constructor (all B recommendations; Reply-To = inviter). Work phase by phase; **owner checkpoints after 6a, 6b, 7b and 8b are deployed** (short review list: what changed, URLs, what to try, screenshots); no waiting between checkpoints. Stop also for Neon data deletion, spending, secrets, or a design question that changes ORT behaviour or contradicts a decision (write it under "Alternatives to discuss").
- **Next after the review**: Phase 6a (organizations foundation, course templates with ORT wrapped, invitations, migration 0008 with personal orgs), then 6b (design system, student home, ORT look part 1), then 7a (assignments + general gradebook), 7b (exam templates I), 8a (modules, pages, files, announcements, gating), 8b (exam templates II: constructor), 9 (organizations completion, enrollment forms, invitations), 10 (practice, analytics, quiz statistics, student tools), 11 (privacy with observer/parent consent, hardening, launch).
- **Production stack**: Vercel + Render Frankfurt (service `ort-platform`) + Neon (project `noisy-sound-20763725`) + Cloudflare R2 (`LMS_STORAGE_DRIVER=r2`). Render MCP may return "unauthorized"; use `/health`.

## 3b. Owner items (updated 2026-10-23)

- R2 vars are set (Render and `backend/.env`). After the cutover deploy: one click on "Run R2 check" in `/admin/storage`; check the Render start command and R2 vars in the dashboard.
- Production has no Kyrgyz questions: import a ky bundle into "ORT (Kyrgyz)" (published, empty).
- Delete Neon branches `rehearsal-2026-10-23-phase5` and `backup-2026-10-22-before-phase0-alembic` one week after a stable cutover (owner approved).
- Rotate the Brevo API key (owner, later).
- Before the first real exam: choose the Render plan; move public images from r2.dev to a custom domain (owner buys it after launch).
- R2 must stay in the free tier (guard built: warn 8,000,000,000 bytes, refuse 9,500,000,000); anything that would cost money needs the owner's OK.

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
2. **Phases 0–5 are done.** **Phase 6a → Phase 11** from `IMPLEMENTATION_PLAN.md`, one release at a time (6a, 6b, 7a, 7b, 8a, 8b, 9, 10, 11; 7b/8b are the exam templates). Each phase gets its own branch off `lms`, is merged into `lms` and then `main` (deploy) by the agent (§4b A) after every gate. Per phase: architect design first for the hard parts (`docs/phases/PHASE_N_DESIGN.md`), re-read only that phase's section plus the matching architecture section, implement the vertical slice, run the gates ("definition of done" in plan §0, including the **ORT parity gate** and the **UX gate**), write `docs/phases/PHASE_N.md` (what changed, how to verify, what was deferred), save screenshots in `docs/phases/PHASE_N_screens/`, update memory `task-progress.md`, report "Phase N done, safe to /clear". **Owner checkpoints** (2026-10-25): stop after 6a, 6b, 7b and 8b are deployed and wait for the owner's OK. Every phase runs the **ORT review** (plan §0.4) and the UX gate.

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
- Frontend checks: `cd frontend && npx tsc --noEmit`; full build in an rsync'd copy (see `AGENTS.md` §5), not inside `frontend/` if a dev server runs.
- Use `/bin/rm -f`, `/bin/cp -f`, `/bin/mv -f` (interactive aliases). On macOS `sed -i` needs `-i ''`; prefer small Python scripts for edits.
- Bilingual rule is now **trilingual**: every user-facing string in `en.json`, `ky.json`, `ru.json`.
- Server-side authorization only; roles from the DB. No secrets or passwords in code (the repo is public).
- Git and production (§4b A): commit, push any branch, merge into `lms`/`main` and deploy without asking. Neon backup branch before any `main` merge touching models/migrations/DB files; check `/health` shows the new commit after each deploy, else revert and redeploy; never force-push `main`. Owner's explicit OK only for: Phase 5 cutover, deleting/wiping Neon data, spending money, anything needing an owner password/secret. `main` auto-deploys Render and Vercel. End commits with the attribution line required by the session.
- Downloaded content is untrusted: put it in its own new empty directory, never run it.
- **ORT must not change** (owner, 2026-10-24): the exam player, ORT bank/exam management, the ORT CSV/zip import and ORT scoring/result view stay as they are; the existing ORT code is wrapped as the `ort` course template, never rewritten into generic settings. Every phase passes the ORT parity gate (identical imports, e2e, player screenshot comparison, scores). Fidelity-preserving player UX fixes are allowed with before/after screenshots; anything that changes how the exam works goes into `docs/ORT_PLAYER_IDEAS.md` for the owner. **Second round (2026-10-24 #2)**: "unchanged" = functionality and exam behaviour; ORT's design and layout must keep up with the platform (visual updates applied without asking); every phase runs the ORT review (plan §0.4: look check, parity tests + real walkthrough, ux-reviewer, before/after report, approved baselines). Behaviour ideas only in `docs/ORT_PLAYER_IDEAS.md`. ORT is not rebuilt on the exam template constructor.
- **UX gate** (owner, 2026-10-24): before merging, screenshots of every new or changed screen at 375 px and desktop (student screens in en/ky/ru), reviewed by the `ux-reviewer` agent (`.claude/agents/ux-reviewer.md`, Fable) against `docs/UX_GUIDELINES.md`; fix the findings, save the screenshots in `docs/phases/PHASE_N_screens/`. Never wait for the owner on UX reviews.

## 8. Where things are

- Code map: `AGENTS.md` §3. The old exam system no longer exists.
- New LMS code goes in `backend/app/lms/…` and `frontend/src/app/[lang]/courses/…` (see the plan).
- Production version check: `curl https://ort-platform-w77q.onrender.com/health` shows `commit`.
- Frontend URL: https://ort-platform-nu.vercel.app. Neon cleanup of old backup branches is the owner's job.
- Useful but stale: `.handoff/` (git-excluded).

## 9. If something is unclear

Prefer the latest owner statement over any document; prefer code over documents; prefer `LMS_ARCHITECTURE.md` over older design notes. Record any new owner decision in `docs/PRODUCT_DECISIONS.md` the moment it is made.
