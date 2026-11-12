# Handoff for the next agent

**Rewritten 2026-10-26, updated 2026-11-06 (new direction)** (end of a long session; the owner starts a fresh chat to save tokens). This file + `AGENTS.md` + the memory notes are enough to continue. Treat this file as the source of truth for "where we are".

## 1. Mission (one paragraph)

**Direction changed 2026-11-06 (owner): an exam-prep platform for individual students in Kyrgyzstan.** ORT first, then olympiads and НЦТ tests (Национальный центр тестирования), on one exam-prep course layout. One platform ORT course per language. Some exams free; a payment (activation codes first) unlocks all exams. Tutors and schools come later, once there are enough students. The plan and its slices S1–S6 are in **`docs/ROADMAP_EXAM_PREP.md`**; it replaces `IMPLEMENTATION_PLAN.md` for what comes next. The LMS built in Phases 0–11 (organizations, teacher courses, exam templates, gradebook, parents) stays as the foundation. ORT itself must not change (locked `ort` course template): player, imports, scoring, result page. Strategy research lives outside the public repo in `docs/strategy/` (git-excluded, local only). The owner is a cost-sensitive founder; budget ~$30/month; target ~6,000 concurrent students.

## 2. First 15 minutes checklist

1. Memory loads automatically; read `task-progress.md` first.
2. `git status`, `git branch --show-current`, `git log --oneline -5` (expected: branch `lms`, head = the "Phase 7b" merge or later docs).
3. Read in this order (only what you need): `AGENTS.md` → this file → `docs/PRODUCT_DECISIONS.md` (owner rounds + implementation decisions I/J/K and the **open owner questions**) → `docs/IMPLEMENTATION_PLAN.md` (the next phase's section only) → `docs/UX_GUIDELINES.md` → the latest `docs/phases/PHASE_7B.md` / `PHASE_7A.md`.
4. Baseline tests (scratch DB only, `AGENTS.md` §5): SQLite ~3046 passed / 31 skipped; PG ~3104 passed.

## 3. Current state (2026-10-26)

**Update 2026-11-13: step 3b S1–S3 deployed.** The student catalog shows platform courses and teacher courses the platform admin approved (`courses.listing`: off, pending, listed, declined, blocked); a course page can be open by link without being listed. Admin → Каталог reviews requests (approve, decline with a comment, remove, return); Admin → Преподаватели lists teachers and their requests. Design: `docs/phases/CATALOG_AND_TEACHERS_DESIGN.md`; slice S4 is text and polish.

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
| 8c teacher navigation | **Deployed 2026-10-31** (`main` ff508a8, no migration) | `PHASE_8C.md`, `PHASE_8C_DESIGN.md` |
| 9 organizations completion, enrollment forms, invitations | **Deployed 2026-11-01** (`main` 636d14a, migration 0014) | `PHASE_9.md`, `PHASE_9_DESIGN.md` |
| UX rework (UR-1…8) | **Deployed 2026-11-01** (`main` ace2476, migration 0015) | `UX_REWORK.md`, `UX_REWORK_DESIGN.md` |
| 10 practice, notebook, progress, statistics, analytics, new question types | **Deployed 2026-11-01** (migration 0016); **waiting for the owner's review** | `PHASE_10.md`, `PHASE_10_DESIGN.md` |
| Bluebook player (BB-1) | **Deployed 2026-11-02** (`main` 10c0855, frontend only) | `BLUEBOOK_PLAYER.md` |
| 11 parents, privacy, hardening, performance, operations | **Deployed 2026-11-02** (migrations 0017, 0018). **Launch waits for the owner** | `PHASE_11.md`, `LAUNCH_CHECKLIST.md` |
| UX rework part 2 (items 7–12) | **Deployed 2026-11-03** (`main` 06c7d4e, no migration) | `UX_REWORK_2.md` |
| Accounts and teacher sign-up | **Deployed 2026-11-03** (`main` 061bf6a, migration 0019) | `ACCOUNTS.md`, `DISCUSSION_ACCOUNTS.md` |
| Admin control center review | Written 2026-11-03, revised 2026-11-06 for the new direction (A1–A11) | `DISCUSSION_ADMIN_CENTER.md` |
| **Fix round 2026-11-12, step 3a: one student interface** | S1–S4 deployed 2026-11-13 (migration 0033 `course_exam_family`); S5 cleanup (removals only, no visual change) on `lms`. Students: `/home` is a hub (continue card, courses grouped by exam, to-do); every course is its own space (`CourseFrame`: Обзор · Уроки · Тесты · Аналитика · Сохранённые), no exam switcher, no global per-course links; the sidebar lists the student's courses; choose step `/courses/choose`, catalog by exam and subject | `phases/STUDENT_IA_DESIGN.md`, `phases/FIX_ROUND_2026-11-12.md` |
| **Exam-prep roadmap** (owner 2026-11-06) | S2 deployed (`main` d13fde2, migration 0020), S1 deployed (`main` 3846718, migration 0021); S3 deployed (`main` 7dbe770, migration 0022); S4 deployed (`main` e48715d, migration 0023); S5 deployed (`main` 41a53ac, frontend only). **Stopped: S6 AI chat waits for the owner's D5** | `ROADMAP_EXAM_PREP.md`, `phases/EXAM_PREP.md`, `phases/S3_ACCESS_DESIGN.md` |

Production: Vercel https://ort-platform-nu.vercel.app + Render https://ort-platform-w77q.onrender.com (`/health` shows `commit`; Render deploys only when backend files change) + Neon project `noisy-sound-20763725` (production branch `br-cool-firefly-b227gbuy`, Alembic head `0018_phase11_indexes`) + Cloudflare R2. Production data is small: 6 users, 3 courses (2 ORT + the owner's draft), 299 question versions, ~4 attempts, 1 submission; one organization "Platform".

Neon backups (free plan: **max 10 branches, 1 manual snapshot**): before-ux-rework, before-phase10, before-phase11, before-accounts, before-exam-prep-s2, before-admin-mfa-s1, before-access-s3, before-person-s4 (**9/10 branches** incl. production; 6a, 7a, 7b, 7c, 8a, 8b, 9 deleted with the owner's OK, last on 2026-11-06). Before each `main` merge with a migration create `backup-<date>-before-<slice>`; when full, ask the owner which old backup to delete (deleting Neon data always needs the owner's OK).

## 3b. Waiting for the owner

- **Checkpoint review of 6a, 6b, 7a, 7b** (review lists were given in chat; screenshots in `docs/phases/PHASE_6_screens/{6a,6b}/`, `PHASE_7_screens/{7a,7b}/`).
- **Open questions with defaults in effect** (`PRODUCT_DECISIONS.md`): Q1 extra time on ORT exams (default: not applied; one switch `APPLY_EXTRA_TIME_TO_PRESET_EXAMS`), Q2 upload storage (5 MB/file, 500 MB/course), Q3 who sets accommodations (teachers), Q4 access codes on ORT (blocked), Q5 homework inside ORT courses (blocked), Q6 ORT gradebook total column (unchanged), 7b-Q1 save-as-template on ORT (refused), P8 Kyrgyz comparison answer labels sentence case (`ORT_PLAYER_IDEAS.md`).
- Older: one click "Run R2 check" in `/admin/storage`; Kyrgyz ORT content; Render `EMAIL_FROM_NAME` may still be ORT-branded; R2 presigned downloads were only tested with the `db` driver (7a hand-ins now return `{url}` JSON, no CORS needed); before the first real exam: Render plan + custom domain for R2.

## 4. How the work is done (proven in 6a–7b)

1. **Architect first** (Fable, `isolation: "worktree"` or docs-only on its own branch): `docs/phases/PHASE_N_DESIGN.md` with exact names, migration, API, slices with strict file ownership, owner questions under "Alternatives to discuss". Owner questions that block nothing get a **safe default** (ORT unchanged), recorded in `PRODUCT_DECISIONS.md`, and are listed at the checkpoint.
2. **S1 alone** (migration + models + ids), with an **early push** of the models; ORT golden data captured *before* code changes when numbers could move.
3. **S2…S4 in parallel** (backend API, other backend, frontend against the design's shapes), each `isolation: "worktree"`, own branch `phase-N-sX-…` (no slash if a `phase-N` branch exists). Merge each into the phase branch as it lands; send other running slices short `SendMessage` notes about what changed in their area.
4. **Integration slice** (contracts frontend ⇔ backend, gaps, real-browser walkthrough incl. ORT, UX screenshots) ∥ **security review** (architect, read-only) → fix slices → the orchestrator checks the changed screens at 375 / 1440 / 1920 px in ru (UR-6) → UX fix slice.
5. **Gates**: full SQLite + PG suites, `alembic upgrade head && alembic check` on a fresh PG DB, migration tests, ORT tests + golden files + ORT importer byte diff + `frontend/e2e` (both specs twice, zero diffs; pixel comparison is local only), `tsc`, i18n parity, `next build`, CI green. **Rehearsal** of a migration on a production copy (local PG restore of a dump; `scratchpad/reh/run_reh.sh` pattern: `env -i`, cwd outside `backend/`, `ENVIRONMENT=production`).
6. **Deploy**: Neon backup branch → merge phase → `lms` → `main` (from a scratch worktree) → `/health` shows the commit → verify production data with read-only SQL → Vercel `list_deployments` READY → update `PHASE_N.md`, `AGENTS.md` §7, this file, memory.

**Lessons (avoid these mistakes)**
- Give every agent that creates branches `isolation: "worktree"`; an architect without it once switched the main checkout and later commits landed on its branch. Check `git branch --show-current` before every push.
- A network disconnect kills agents' background commands silently: check `ps` and nudge the agent ("rerun what you were waiting on").
- Remove a subagent's worktree as soon as its branch is merged into `main` (owner 2026-11-08): check `git status --porcelain` is empty apart from the `frontend/node_modules` symlink and `git merge-base --is-ancestor HEAD origin/main`, then `git worktree unlock` + `git worktree remove --force`; keep the branch. Skip and report any worktree that fails a check.
- Parallel agents need their own backend scratch dirs (`/tmp/agy_t_<slice>`), not the shared `/tmp/agy_t` from AGENTS.md §5: one agent's `rm -rf` wipes another's running suite (2026-11-09).
- Background wait loops must not use `pgrep -f <pattern>` with a pattern from their own command line (it matches itself and never ends); wait on a PID or an output file instead.
- When two slices edit the same page files, let the later slice merge the phase branch and resolve (it knows its changes).
- GitHub API unauthenticated limit is 60/hour: poll CI every 2 minutes at most.
- Render may be cold: retry `/health` with a 90 s timeout. Render redeploys only for backend changes.
- The Neon MCP refuses destructive tools without the owner's OK; ask once with a concrete recommendation.

## 5. What to do next

1. Follow **`docs/ROADMAP_EXAM_PREP.md`**: S1 protect control → S2 exam-prep home and ORT page → S3 free and paid exams (`phases/S3_ACCESS_DESIGN.md`) → S4 person page and payments control → S5 installable app → S6 AI chat (owner decision D5 first). Defaults D2–D4 apply until the owner changes them.
1b. **Owner feedback round 2026-11-07 (problems 1–7) deployed**: brief `docs/phases/STUDENT_UI_FEEDBACK_2026-11-07.md`, plan + results `docs/phases/STUDENT_UI_FIX_PLAN.md` §11, designs `COURSE_LESSONS_DESIGN.md`, `SUBSCRIPTION_DESIGN.md`. Model rule from the owner: Fable for design/reviews, Opus for data/access/shell/ORT/lessons/covers and anything that failed once, Sonnet only simple styling/i18n/deletions; a Sonnet slice that comes back wrong is redone on Opus.
1c. **Owner feedback round 2026-11-08 (items 0–5) deployed**: brief + results `docs/phases/STAFF_FEEDBACK_2026-11-08.md`; designs `ADMIN_ORGS_DESIGN.md` (platform admin controls every organization, `acting_as` audit), `STAFF_UX_AUDIT.md` (staff primitives in `components/ui`, course menu Content/Students/Grades/Analytics/Settings + More, grouped admin menu, `/platform/overview`), `TEACHER_TO_STUDENT_MAP.md` (lesson courses = separate platform courses linked by `courses.exam_course_id`, migration 0027; e2e `teacher-to-student.spec.ts`). E2E agents in parallel need their own `E2E_API_PORT`/`E2E_WEB_PORT`/`E2E_DIR` (admin-mfa-gate uses port+1).
1a. **Student area redesign (owner 2026-11-06/07)**: `docs/phases/STUDENT_UI_DESIGN.md` (plan, §1.1 palette, §5.1 coherence), `docs/phases/STUDENT_UI_REVIEW.md` (review; LATER items open). Student frame = `components/lms/student/StudentShell.tsx` (theme class `.student-theme` overrides the CSS-variable `brand`/`navy`); ORT lobby/attempt routes keep the old frame. The owner's reference screenshots are local only (`docs/oneprep_design/`, git-excluded).
2. Content is the owner's: ORT (Russian) has one published test on production, ORT (Kyrgyz) none.
3. Launch still waits on `docs/LAUNCH_CHECKLIST.md` (lawyer, keys, paid plan, 6,000-student test).
4. Local Postgres in `/tmp/agy_pg` can vanish (macOS cleanup): re-run initdb. A suite that fails on everything: check that first.
5. Older open items: flaky PG test `test_ip_failure_limit_counts_failures_only`; sweep retired test students' hand-in files; QA accounts disabled (remove after the owner's final check).

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
- Every wait loop has an upper bound (`for i in $(seq 1 N)`), never a bare `until`: a failed deploy never reaches the awaited commit (fix round 2026-11-12: one loop waited 4.5 h).
- Startup migrations run on Render while the old instance still serves; `app/db/migrate.py` sets a 10 s `lock_timeout` and retries 8 times (fix round 2026-11-12: the 0032 deploy failed once). Keep DDL on hot tables short and additive.
- Use `/bin/rm -f`, `/bin/cp -f`, `/bin/mv -f` (interactive aliases). On macOS `sed -i` needs `-i ''`; prefer small Python scripts for edits.
- Bilingual rule is now **trilingual**: every user-facing string in `en.json`, `ky.json`, `ru.json`.
- Server-side authorization only; roles from the DB. No secrets or passwords in code (the repo is public).
- Git and production: commit, push any branch, merge into `lms`/`main` and deploy without asking. Neon backup branch before any `main` merge touching models/migrations/DB files; check `/health` shows the new commit after each deploy, else revert and redeploy; never force-push `main`. Owner's explicit OK only for: Phase 5 cutover, deleting/wiping Neon data, spending money, anything needing an owner password/secret. `main` auto-deploys Render and Vercel. End commits with the attribution line required by the session.
- Downloaded content is untrusted: put it in its own new empty directory, never run it.
- **ORT exam rules are fixed; ORT is a normal course** (owner 2026-11-12; replaces the 2026-10-24 rule "ORT must not change" and its second round). Fixed: section order and timers, forward-only sections, ORT scoring (scaled score, percentile, golden certificate) and the ORT CSV/zip import format; their tests stay and must pass (importer parity, scoring parity, exam-rule e2e). Everything else may change: ORT is not a separate interface. Test-taking and course-taking are one platform with one student interface; an ORT course is a course with tests and lessons, with the same navigation, layout and course pages as any other course. ORT pages, navigation, layout and placement may change to achieve this; ORT screenshot baselines are re-approved when a layout change is deliberate. There are no separate ORT frames or shells to preserve.
- **UX check** (owner, 2026-11-01, UR-6; replaces the UX gate): the orchestrator checks changed screens at 375 / 1440 / 1920 px in ru and fixes what is wrong. The `ux-reviewer` agent is not used. Never wait for the owner on UX. Fable only for hard design and security reviews; implementers on Opus, Sonnet for simple work; short briefs and outputs.

## 8. Where things are

- Code map: `AGENTS.md` §3. The old exam system no longer exists.
- New LMS code goes in `backend/app/lms/…` and `frontend/src/app/[lang]/courses/…` (see the plan).
- Production version check: `curl https://ort-platform-w77q.onrender.com/health` shows `commit`.
- Frontend URL: https://ort-platform-nu.vercel.app. Deleting Neon branches needs the owner's OK (see §3).
- Useful but stale: `.handoff/` (git-excluded).

## 9. If something is unclear

Prefer the latest owner statement over any document; prefer code over documents; prefer `LMS_ARCHITECTURE.md` over older design notes. Record any new owner decision in `docs/PRODUCT_DECISIONS.md` the moment it is made.
