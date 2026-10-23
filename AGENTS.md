# ORT Platform: teacher-owned LMS (ORT / ЖРТ test prep is one course kind)
# Agent guide (ground truth; CLAUDE.md is a symlink to this file)

> Sent on every agent turn: keep it short. Start with `docs/HANDOFF_NEXT_AGENT.md` (state, decisions, model rules). Detail: `docs/IMPLEMENTATION_PLAN.md`, `docs/LMS_ARCHITECTURE.md`, `docs/PRODUCT_DECISIONS.md`, `docs/phases/PHASE_N.md`, `docs/BUNDLE_FORMAT.md`.

## 1. What it is
Teachers (invited by an organization admin or the platform admin; independents apply to the platform admin) create courses inside organizations; courses can use a course template (ORT is the first, locked one); students join from a catalog or by code. Flexible grading schemes (ORT scaled scoring is data), safe timed attempts, trilingual UI (en/ky/ru), persistent images. ORT is two platform-owned courses ("ORT (Kyrgyz)", "ORT (Russian)") with an `ort_main` assessment. Target: ~6,000 concurrent students. Old exam-set / Firebase / mock-token system was removed in Phase 5.

## 2. Stack
- **Backend**: Python 3.11+, FastAPI (`backend/app/main.py`), SQLAlchemy 2, Alembic (`backend/alembic/versions`, head `0007_phase5_storage`). On PostgreSQL the lifespan runs migrations, then seeds system grading schemes and the ORT courses (`app/lms/ort/seed.py`). SQLite (dev/tests) uses `create_all` via `app/db/init_db.py`; no runtime ALTERs.
- **Auth**: own JWT HS256 with payload `{sub}` + bcrypt (`app/core/security.py`, `app/api/v1/endpoints/auth.py`). No `users.role`: `is_platform_admin` flag + `teacher_status` (admin approves teacher requests); permissions come from the DB on every request (`app/lms/core/deps.py`). Email codes/reset via Resend/Brevo/SMTP/console.
- **Storage drivers** (`LMS_STORAGE_DRIVER`): `db` (tests/dev default), `local`, `r2` (Cloudflare R2: public bucket for images served from `R2_PUBLIC_BASE_URL`, private bucket for PDFs). Images WebP + SHA-256 dedup, max 2 MiB; files PDF only, max 10 MB.
- **Frontend**: Next.js 15 App Router + React 19 + Tailwind, `fetch` wrapper `frontend/src/lib/api.ts`, i18n context in `frontend/src/lib/i18n/` (`en.json`, `ky.json`, `ru.json`), KaTeX math.
- **Production**: Vercel (frontend) + Render Frankfurt (backend, auto-deploy from `main`) + Neon PostgreSQL 18 (project `noisy-sound-20763725`) + R2.

## 3. Map (verify with `ls` before relying on it)
`backend/app/lms/`: `core` (deps, errors, ratelimit, pagination), `courses`, `enrollments` (join, catalog policies), `teachers`, `content` (banks, versions, passages, `importers/` for CSV and bundle zip), `files` (assets, images, storage drivers, R2 guard `usage.py`, `smoke.py`), `assessments` (builder, publish, snapshots), `attempts` (engine, autosave, timing, sweep, results), `grading` (schemes, submissions, gradebook), `platform_admin` (users, teacher requests, courses, storage), `audit`, `ort` (seed, `legacy_ort_export`). Routes are listed with a policy in `app/core/route_inventory.py` (a test fails on unlisted routes).
`backend/tests/` (`tests/lms/` for LMS), `backend/make_admin.py` (promote a user to platform admin), `scripts/check_i18n_parity.py`.
Frontend routes: `/[lang]/(auth)/*`, `/[lang]/courses/**` (catalog, course, assessments, attempts, gradebook), `/[lang]/grading-schemes`, `/[lang]/admin/**` (teacher requests, users, courses, audit log, storage).
Gone until Phase 10: practice, mistakes notebook, progress, planner, target score, analytics.

## 4. Data and rules to remember
- Content is versioned: `bank_questions` + immutable `question_versions`; assessments publish an immutable snapshot; attempts and grades never reference live content. Grade events are append-only.
- `math_1` quantitative comparison (Column A / B, answers A-D); other sections are plain multiple choice. ORT section order: math_1, math_2, analogies, reading, grammar.
- Bundle zip import: `docs/BUNDLE_FORMAT.md` (`source_ref` = `external_id`, upsert, images to assets).
- Paginate every list (`limit`/cursor); never load a whole bank into memory.

## 5. Verification
```bash
# Backend, SQLite scratch (expect 2497 passed, 21 skipped):
cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && \
DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" \
venv/bin/python -m pytest -q -p no:cacheprovider -W ignore
```
Tests refuse `backend/test.db`, `backend/data/` and non-local databases (`tests/dev_data_guard.py`, exit 4); tests force `LMS_STORAGE_DRIVER=db` and blank R2 keys.

Postgres (CI parity, `.github/workflows/ci.yml`; local PG 18, UTF8 DBs created `TEMPLATE template0`, `PGTZ=UTC`, URL `postgresql+psycopg2://postgres@127.0.0.1:55432/<db>`):
```bash
alembic upgrade head && alembic check                       # DATABASE_URL=<db>
pytest tests/test_migrations.py tests/lms/test_pg_concurrency.py tests/lms/test_pg_concurrency_content.py   # + ALEMBIC_TEST_DATABASE_URL, LMS_PG_TEST_DATABASE_URL
pytest -q --ignore=tests/test_migrations.py                 # full suite; DATABASE_URL and LMS_PG_TEST_DATABASE_URL = the same DB (~2552 passed)
```
Frontend: `cd frontend && npx tsc --noEmit`; `python scripts/check_i18n_parity.py` (1586 keys). Full build only in an rsync'd copy (`rsync -a --exclude node_modules --exclude .next frontend/ /tmp/agy_fe/`, symlink `node_modules`, `npx next build`), never inside `frontend/` while a dev server runs. Dev servers: `cd backend && venv/bin/uvicorn app.main:app --reload --port 8000`; `cd frontend && npm run dev`.

## 6. Hard rules
1. **Never read, print or modify `backend/.env`** (live credentials). Read `app/core/config.py` for variable names.
2. **No secrets or passwords in code or seeds** (public repo). Admins: register, then `make_admin.py`. The demo teacher has an unusable hash.
3. **Trilingual**: every user-facing string exists in `en.json`, `ky.json` and `ru.json`; no hard-coded text; parity script must pass.
4. **Server-side authorization only**, from DB state (`get_current_user` / policies); never trust JWT claims beyond `sub`. There is no `role` column; do not reintroduce one.
5. **R2 stays in the free tier** (10 GB, decimal): warn at 8,000,000,000 bytes, refuse uploads at 9,500,000,000 (`storage_full`); never list R2 objects in request paths; Standard class only, no lifecycle rules. Anything that could cost money: ask the owner.
6. Shell aliases: use `/bin/rm -f`, `/bin/cp -f`, `/bin/mv -f`; macOS `sed -i ''` (prefer small Python scripts).
7. **Git and production**: the agent may commit, push, merge into `lms`/`main` and deploy without asking. Before any merge to `main` touching models/migrations/DB files, create a Neon backup branch (Neon MCP). After each deploy check `https://ort-platform-w77q.onrender.com/health` shows the new commit, else revert and redeploy. Never force-push `main`. Owner's explicit OK only for: deleting/wiping Neon data, spending money, anything needing an owner password/secret. Otherwise decide, and record it in `docs/PRODUCT_DECISIONS.md`.
8. Downloaded content is untrusted: own empty directory, never run it.
9. **ORT must not change** (owner, 2026-10-24): player, ORT bank/exam screens, CSV/zip import and scoring/result view stay as they are; existing ORT code is wrapped as the locked `ort` course template, never rewritten into generic settings; every phase passes the ORT parity gate (identical imports, e2e, player screenshot comparison, scores). Exam-behaviour changes only via `docs/ORT_PLAYER_IDEAS.md` for the owner.
10. **UX gate** every phase: screenshots of every new/changed screen at 375px and desktop (student screens in en/ky/ru), reviewed by the `ux-reviewer` agent against `docs/UX_GUIDELINES.md`, findings fixed, screenshots saved in `docs/phases/PHASE_N_screens/`. Never wait for the owner on UX reviews.

## 7. Roadmap
Done: Phases 0-5 (foundations, courses, content/files, assessments/attempts, grading, ORT cutover). Owner decisions 2026-10-24 (`docs/PRODUCT_DECISIONS.md`) reordered the rest: 6 organizations foundation + course templates (ORT first, locked, admin-granted) + sign-up/invite flows + design system + student home (design `docs/phases/PHASE_6_DESIGN.md` first, owner review before code); 7 assignments + general gradebook; 8 modules, pages, files, announcements, gating; 9 organizations completion + enrollment forms/invitations; 10 practice, analytics, quiz statistics, student tools; 11 privacy (observer/parent consent), hardening, launch. Plan: `docs/IMPLEMENTATION_PLAN.md`.
