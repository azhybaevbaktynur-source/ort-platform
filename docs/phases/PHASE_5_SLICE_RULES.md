# Phase 5 slice rules (for implementer agents)

Read this, then `docs/phases/PHASE_5_DESIGN.md` (your slice's sections), then only the code you need.

- Work ONLY in your own git worktree (you were started in one). First: `git checkout -b phase-5/<slice-branch>` (name given in your brief). Commit there, push with `git push -u origin <branch>`. Never touch `main`, `lms` or `phase-5/cutover` directly; the orchestrator merges.
- Own only the files listed for your slice in design §10. `backend/app/core/config.py` and `backend/app/core/route_inventory.py` belong to S2; other slices add ONE clearly delimited block (`# --- Phase 5 S3 begin/end ---`) instead of editing other lines. i18n JSON (`frontend/src/lib/i18n/{en,ky,ru}.json`): S3 adds only the top-level group `catalog`, S4 only `storage` (+ `files.errors.storage_full` is S4's), S5 everything else. Add new top-level groups at the END of the file so merges stay simple.
- NEVER read, print or modify `backend/.env`. No secrets or passwords in code (public repo). Rules: `AGENTS.md` §7.
- `rm/cp/mv` are aliased interactive: use `/bin/rm -f`, `/bin/cp -f`, `/bin/mv -f`. macOS `sed -i ''`; prefer small Python scripts for edits.
- Tests, scratch only. Pick a unique scratch dir `/tmp/agy_p5_<slice>` (e.g. `/tmp/agy_p5_s3`). In your worktree's `backend/`:
  `/bin/rm -rf /tmp/agy_p5_<slice> && /bin/mkdir -p /tmp/agy_p5_<slice>/up && DATABASE_URL="sqlite:////tmp/agy_p5_<slice>/t.db" LOCAL_UPLOAD_DIR="/tmp/agy_p5_<slice>/up" <main-repo>/backend/venv/bin/python -m pytest -q -p no:cacheprovider -W ignore`
  (the venv lives in the main repo `/Users/baktynurazhybaev/ort-platform/backend/venv`; run python from there with cwd = your worktree's `backend/`).
- Postgres 18 is running locally: `postgresql+psycopg2://postgres@localhost:55432/<db>` (trust auth). Create your own DBs prefixed with your slice, e.g. `/opt/homebrew/opt/postgresql@18/bin/psql -h localhost -p 55432 -U postgres -d postgres -c "CREATE DATABASE p5s3_suite ENCODING 'UTF8' TEMPLATE template0"`. Use `PGTZ=UTC`. PG suites as in `.github/workflows/ci.yml` (`ALEMBIC_TEST_DATABASE_URL`, `LMS_PG_TEST_DATABASE_URL`). Drop your DBs when done.
- Frontend: `cd frontend && npx tsc --noEmit` in your worktree (symlink `node_modules` from the main repo `frontend/node_modules` if missing). Full build: rsync your `frontend/` to `/tmp/agy_p5_<slice>_fe`, symlink node_modules, `npx next build`. Never build inside the main repo's `frontend/`.
- i18n parity: every user-facing string in en, ky and ru (check the parity script used by CI).
- Run only the tests you need while developing; the full SQLite suite once before your final commit. Keep output short (`| tail -20`).
- Final reply (≤ 200 words): branch + commit, what changed, test counts (SQLite and PG), anything left undone or any deviation from the design and why.
