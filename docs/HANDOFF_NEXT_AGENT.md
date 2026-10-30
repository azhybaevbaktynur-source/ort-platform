# Handoff for the next agent

**Rewritten 2026-10-26** (end of a long session; the owner starts a fresh chat to save tokens). This file + `AGENTS.md` + the memory notes are enough to continue. Treat this file as the source of truth for "where we are".

## 1. Mission (one paragraph)

A teacher-owned, Canvas-style LMS where ORT/ЖРТ test prep is one course kind: organizations (schools, centers, personal orgs for independent teachers) with org admins; admin-approved or invited teachers create courses; students join by code or catalog; assignments (quiz, text, file, oral) with a general gradebook; exam templates; flexible grading; three languages (en/ky/ru); safe timed attempts; target ~6,000 concurrent students. ORT itself must not change (locked `ort` course template). The owner is a cost-sensitive founder; budget ~$30/month.

## 2. First 15 minutes checklist

1. Memory loads automatically; read `task-progress.md` first.
2. `git status`, `git branch --show-current`, `git log --oneline -5` (expected: branch `lms`, head = the "Phase 7b" merge or later docs).
3. Read in this order (only what you need): `AGENTS.md` → this file → `docs/PRODUCT_DECISIONS.md` (owner rounds + implementation decisions I/J/K and the **open owner questions**) → `docs/IMPLEMENTATION_PLAN.md` (the next phase's section only) → `docs/UX_GUIDELINES.md` → the latest `docs/phases/PHASE_7B.md` / `PHASE_7A.md`.
4. Baseline tests (scratch DB only, `AGENTS.md` §5): SQLite ~3046 passed / 31 skipped; PG ~3104 passed.

## 3. Current state (2026-10-26)

| Phase | State | Docs |
|---|---|---|
| 0–5 | Done, deployed (ORT cutover 2026-10-23) | `docs/phases/PHASE_0..5.md` |
| 6a organizations, course templates (ORT locked), invitations | Deployed 2026-10-25 (`main` 77923cf, migration 0008) | `PHASE_6A.md` |
| 6b design system, AppHeader with areas, student home, ORT player part 1, ORT browser suite | Deployed 2026-10-25 (`main` 89050a4) + landing fix 4771318 | `PHASE_6B.md` |
| 7a assignments, hand-ins, manual grading, general gradebook, accommodations, access codes | Deployed 2026-10-26 (`main` 95b040f, migration 0009) | `PHASE_7A.md`, `PHASE_7A_DESIGN.md` |
| 7b exam templates I (templates + versions, create from template, save as template, general import format, block catalog) | **Deployed 2026-10-26** (`main` 77c5b32, migration 0010) — verify `/health` + Neon if the previous session could not | `PHASE_7B.md`, `PHASE_7B_DESIGN.md`, `EXAM_TEMPLATES_DESIGN.md` |
| Owner checkpoint after 7b | Closed 2026-10-28 (owner approved 7c and continuing to 8a) | `PRODUCT_DECISIONS.md` 7c-9 |
| 7c quiz editor (owner, 2026-10-28) | **Deployed 2026-10-28** (`main` 0177705, migration 0011) | `PHASE_7C.md`, `PHASE_7C_DESIGN.md`, `PHASE_7C_PROPOSAL.md` |
| 8a modules, pages, files, announcements, gating | **Deployed 2026-10-28** (`main` 027d408, migration 0012) | `PHASE_8A.md`, `PHASE_8A_DESIGN.md` |
| 8b exam templates II | **Deployed 2026-10-28** (`main` b716d78, migration 0013) | `PHASE_8B.md`, `PHASE_8B_DESIGN.md` |
| Owner checkpoint after 8b | Closed 2026-10-31: owner asked for a navigation redesign first (8c) | `CHECKPOINT_8B.md`, `PHASE_8C_NAVIGATION_PROPOSAL.md` |
| **8c teacher navigation** | **In progress** (design first; slices 1–4 without pause, one deploy) | `PHASE_8C_NAVIGATION_PROPOSAL.md` |
| Next | 8a modules, pages, files, announcements, gating → 8b exam templates II (visual constructor, scrolling display mode; **checkpoint after 8b**) → 9 → 10 → 11 | `IMPLEMENTATION_PLAN.md` |

Production: Vercel https://ort-platform-nu.vercel.app + Render https://ort-platform-w77q.onrender.com (`/health` shows `commit`; Render deploys only when backend files change) + Neon project `noisy-sound-20763725` (production branch `br-cool-firefly-b227gbuy`, Alembic head `0013_phase8b_template_sandbox`) + Cloudflare R2. Production data is small: 6 users, 3 courses (2 ORT + the owner's draft), 299 question versions, ~4 attempts, 1 submission; one organization "Platform".

Neon backups (free plan: **max 10 branches, 1 manual snapshot — both nearly full**): `backup-2026-10-23-before-phase5` (pre-cutover; owner: delete ≥ 2026-10-30), `backup-2026-10-25-before-phase6a`, `backup-2026-10-26-before-phase7a`, `backup-2026-10-26-before-phase7b`, `backup-2026-10-28-before-phase7c`, `backup-2026-10-28-before-phase8a`, `backup-2026-10-28-before-phase8b`, snapshot `before-phase6a-deploy-2026-10-25`. Before each `main` merge with a migration create `backup-<date>-before-<phase>`; when full, ask the owner which old backup to delete (owner OK'd deleting obsolete ones on 2026-10-26; deleting Neon data always needs the owner's OK).

## 3b. Waiting for the owner

- **Checkpoint review of 6a, 6b, 7a, 7b** (review lists were given in chat; screenshots in `docs/phases/PHASE_6_screens/{6a,6b}/`, `PHASE_7_screens/{7a,7b}/`).
- **Open questions with defaults in effect** (`PRODUCT_DECISIONS.md`): Q1 extra time on ORT exams (default: not applied; one switch `APPLY_EXTRA_TIME_TO_PRESET_EXAMS`), Q2 upload storage (5 MB/file, 500 MB/course), Q3 who sets accommodations (teachers), Q4 access codes on ORT (blocked), Q5 homework inside ORT courses (blocked), Q6 ORT gradebook total column (unchanged), 7b-Q1 save-as-template on ORT (refused), P8 Kyrgyz comparison answer labels sentence case (`ORT_PLAYER_IDEAS.md`).
- Older: one click "Run R2 check" in `/admin/storage`; Kyrgyz ORT content; Render `EMAIL_FROM_NAME` may still be ORT-branded; R2 presigned downloads were only tested with the `db` driver (7a hand-ins now return `{url}` JSON, no CORS needed); before the first real exam: Render plan + custom domain for R2.

## 4. How the work is done (proven in 6a–7b)

1. **Architect first** (Fable, `isolation: "worktree"` or docs-only on its own branch): `docs/phases/PHASE_N_DESIGN.md` with exact names, migration, API, slices with strict file ownership, owner questions under "Alternatives to discuss". Owner questions that block nothing get a **safe default** (ORT unchanged), recorded in `PRODUCT_DECISIONS.md`, and are listed at the checkpoint.
2. **S1 alone** (migration + models + ids), with an **early push** of the models; ORT golden data captured *before* code changes when numbers could move.
3. **S2…S4 in parallel** (backend API, other backend, frontend against the design's shapes), each `isolation: "worktree"`, own branch `phase-N-sX-…` (no slash if a `phase-N` branch exists). Merge each into the phase branch as it lands; send other running slices short `SendMessage` notes about what changed in their area.
4. **Integration slice** (contracts frontend ⇔ backend, gaps, real-browser walkthrough incl. ORT, UX screenshots) ∥ **security review** (architect, read-only) → fix slices → **ux-reviewer** (Fable) on the screenshots → UX fix slice.
5. **Gates**: full SQLite + PG suites, `alembic upgrade head && alembic check` on a fresh PG DB, migration tests, ORT tests + golden files + ORT importer byte diff + `frontend/e2e` (both specs twice, zero diffs; pixel comparison is local only), `tsc`, i18n parity, `next build`, CI green. **Rehearsal** of a migration on a production copy (local PG restore of a dump; `scratchpad/reh/run_reh.sh` pattern: `env -i`, cwd outside `backend/`, `ENVIRONMENT=production`).
6. **Deploy**: Neon backup branch → merge phase → `lms` → `main` (from a scratch worktree) → `/health` shows the commit → verify production data with read-only SQL → Vercel `list_deployments` READY → update `PHASE_N.md`, `AGENTS.md` §7, this file, memory.

**Lessons (avoid these mistakes)**
- Give every agent that creates branches `isolation: "worktree"`; an architect without it once switched the main checkout and later commits landed on its branch. Check `git branch --show-current` before every push.
- A network disconnect kills agents' background commands silently: check `ps` and nudge the agent ("rerun what you were waiting on").
- When two slices edit the same page files, let the later slice merge the phase branch and resolve (it knows its changes).
- GitHub API unauthenticated limit is 60/hour: poll CI every 2 minutes at most.
- Render may be cold: retry `/health` with a 90 s timeout. Render redeploys only for backend changes.
- The Neon MCP refuses destructive tools without the owner's OK; ask once with a concrete recommendation.

## 5. What to do next

1. Phase 8c (design `docs/phases/PHASE_8C_DESIGN.md`): slices 1–4 straight through, one deploy (8c-9: no pause; optional owner teacher test afterwards). Exit criteria in `IMPLEMENTATION_PLAN.md` Phase 8c.
2. Open checkpoint questions (`CHECKPOINT_8B.md` §3) keep their defaults; apply answers when the owner gives them.
3. Fix the flaky PG test `tests/lms/test_enrollments_api.py::test_ip_failure_limit_counts_failures_only`.
4. Neon branches 9/10: ask the owner before the next migration deploy which old backup to delete.
5. Then Phase 9, built inside the 8c shell.

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
10. Do not ask the owner except for: Neon data deletion, spending money, owner secrets, a design question that changes ORT behaviour or contradicts a decision, and the phase checkpoints (after 6a, 6b, 7b, 8b). Otherwise take the documented default or safest reasonable choice and record it in `PRODUCT_DECISIONS.md`.

## 7. Hard rules (also in `AGENTS.md`; repeat for safety)

- **Never read, print or modify `backend/.env`** (live credentials).
- Backend tests only against a scratch DB: `cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" venv/bin/python -m pytest -q -p no:cacheprovider -W ignore`. Never touch `backend/test.db` or `backend/data/`.
- Frontend checks: `cd frontend && npx tsc --noEmit`; full build in an rsync'd copy (see `AGENTS.md` §5), not inside `frontend/` if a dev server runs.
- Use `/bin/rm -f`, `/bin/cp -f`, `/bin/mv -f` (interactive aliases). On macOS `sed -i` needs `-i ''`; prefer small Python scripts for edits.
- Bilingual rule is now **trilingual**: every user-facing string in `en.json`, `ky.json`, `ru.json`.
- Server-side authorization only; roles from the DB. No secrets or passwords in code (the repo is public).
- Git and production: commit, push any branch, merge into `lms`/`main` and deploy without asking. Neon backup branch before any `main` merge touching models/migrations/DB files; check `/health` shows the new commit after each deploy, else revert and redeploy; never force-push `main`. Owner's explicit OK only for: Phase 5 cutover, deleting/wiping Neon data, spending money, anything needing an owner password/secret. `main` auto-deploys Render and Vercel. End commits with the attribution line required by the session.
- Downloaded content is untrusted: put it in its own new empty directory, never run it.
- **ORT must not change** (owner, 2026-10-24): the exam player, ORT bank/exam management, the ORT CSV/zip import and ORT scoring/result view stay as they are; the existing ORT code is wrapped as the `ort` course template, never rewritten into generic settings. Every phase passes the ORT parity gate (identical imports, e2e, player screenshot comparison, scores). Fidelity-preserving player UX fixes are allowed with before/after screenshots; anything that changes how the exam works goes into `docs/ORT_PLAYER_IDEAS.md` for the owner. **Second round (2026-10-24 #2)**: "unchanged" = functionality and exam behaviour; ORT's design and layout must keep up with the platform (visual updates applied without asking); every phase runs the ORT review (plan §0.4: look check, parity tests + real walkthrough, ux-reviewer, before/after report, approved baselines). Behaviour ideas only in `docs/ORT_PLAYER_IDEAS.md`. ORT is not rebuilt on the exam template constructor.
- **UX gate** (owner, 2026-10-24): before merging, screenshots of every new or changed screen at 375 px and desktop (student screens in en/ky/ru), reviewed by the `ux-reviewer` agent (`.claude/agents/ux-reviewer.md`, Fable) against `docs/UX_GUIDELINES.md`; fix the findings, save the screenshots in `docs/phases/PHASE_N_screens/`. Never wait for the owner on UX reviews.

## 8. Where things are

- Code map: `AGENTS.md` §3. The old exam system no longer exists.
- New LMS code goes in `backend/app/lms/…` and `frontend/src/app/[lang]/courses/…` (see the plan).
- Production version check: `curl https://ort-platform-w77q.onrender.com/health` shows `commit`.
- Frontend URL: https://ort-platform-nu.vercel.app. Deleting Neon branches needs the owner's OK (see §3).
- Useful but stale: `.handoff/` (git-excluded).

## 9. If something is unclear

Prefer the latest owner statement over any document; prefer code over documents; prefer `LMS_ARCHITECTURE.md` over older design notes. Record any new owner decision in `docs/PRODUCT_DECISIONS.md` the moment it is made.
