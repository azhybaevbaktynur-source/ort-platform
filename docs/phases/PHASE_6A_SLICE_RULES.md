# Phase 6a slice rules (for implementer agents)

Read this, then `docs/phases/PHASE_6_DESIGN.md` (the sections your brief names), then only the code you need.

- Work ONLY in your own git worktree (you were started in one). First: `git checkout -b phase-6/<slice>` (name in your brief) from the commit your brief names. Commit there, push with `git push -u origin <branch>`. Never touch `main`, `lms` or `phase-6a` directly; the orchestrator merges.
- Own only the files your brief lists. Shared files: add ONE delimited block (`# --- Phase 6 S<n> begin/end ---`, or `{/* --- Phase 6 S<n> --- */}` in TSX) instead of editing other lines. `backend/app/core/route_inventory.py` and `backend/app/core/config.py` belong to S1; S3 adds its routes in one delimited block. i18n JSON (`frontend/src/lib/i18n/{en,ky,ru}.json`): add only the top-level groups your brief names, at the END of the file.
- **ORT must not change** (`AGENTS.md` §6 rule 9): ORT code is wrapped, never rewritten. ORT importer files stay byte-for-byte except what the brief names. If something would change ORT behaviour, stop and report.
- NEVER read, print or modify `backend/.env`. No secrets or passwords in code (public repo). Rules: `AGENTS.md` §6.
- `rm/cp/mv` are aliased interactive: use `/bin/rm -f`, `/bin/cp -f`, `/bin/mv -f`. macOS `sed -i ''`; prefer small Python scripts for edits.
- Tests, scratch only. Unique scratch dir `/tmp/agy_p6_<slice>`. In your worktree's `backend/`:
  `/bin/rm -rf /tmp/agy_p6_<slice> && /bin/mkdir -p /tmp/agy_p6_<slice>/up && DATABASE_URL="sqlite:////tmp/agy_p6_<slice>/t.db" LOCAL_UPLOAD_DIR="/tmp/agy_p6_<slice>/up" /Users/baktynurazhybaev/ort-platform/backend/venv/bin/python -m pytest -q -p no:cacheprovider -W ignore`
  (the venv lives in the main repo; run python from there with cwd = your worktree's `backend/`).
- Postgres 18 runs locally: `postgresql+psycopg2://postgres@localhost:55432/<db>` (trust auth). Create your own DBs prefixed with your slice, e.g. `/opt/homebrew/opt/postgresql@18/bin/psql -h localhost -p 55432 -U postgres -d postgres -c "CREATE DATABASE p6s1_suite ENCODING 'UTF8' TEMPLATE template0"`. Use `PGTZ=UTC`. PG suites as in `.github/workflows/ci.yml` and `AGENTS.md` §5 (`ALEMBIC_TEST_DATABASE_URL`, `LMS_PG_TEST_DATABASE_URL`). Drop your DBs when done.
- Frontend: `cd frontend && npx tsc --noEmit` in your worktree (symlink `node_modules` from `/Users/baktynurazhybaev/ort-platform/frontend/node_modules` if missing). Full build: rsync your `frontend/` to `/tmp/agy_p6_<slice>_fe` (exclude node_modules, .next), symlink node_modules, `npx next build`. Never build inside the main repo's `frontend/`. i18n parity: `python scripts/check_i18n_parity.py`.
- Run only the tests you need while developing; the full SQLite suite once before your final commit (baseline 2497 passed, 21 skipped). Keep output short (`| tail -20`).
- Final reply (≤ 250 words): branch + commit, what changed, test counts (SQLite and PG), anything left undone or any deviation from the design and why.
