# Deploy
Production: Vercel (frontend), Render Frankfurt (backend, auto-deploy from `main`), Neon (database). Render redeploys only when backend files change.

1. Tests green: SQLite suite, Postgres suite, `alembic check`, `python scripts/check_i18n_parity.py`, `cd frontend && npx tsc --noEmit`.
2. If the merge touches models or migrations: create a Neon backup branch first (`backup-YYYY-MM-DD-before-<phase>`). Neon free plan allows 10 branches; deleting one needs the owner's OK.
3. Merge into `main` (never force-push). The backend migrates on start (PostgreSQL), then seeds.
4. Wait for Render. Open `https://ort-platform-w77q.onrender.com/health` (cold start can take up to 90 s). The `commit` field must show the new commit. If not after 10 min, see `ROLLBACK.md`.
5. Check Vercel shows the matching frontend deployment, then open `/ru/login` and log in with a QA account.
6. Read-only check of production data (row counts) if a migration ran.
7. Note the deploy in `docs/HANDOFF_NEXT_AGENT.md`.
