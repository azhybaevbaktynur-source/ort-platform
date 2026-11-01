# Restore the database (Neon)
Neon keeps a short history on the free plan. **How long is not recorded in the repo: read it in the Neon console (project, Settings, Restore window) and write it in `RESTORE_DRILL.md`.** Backup branches made before each deploy are the safer copy.

**Make a restore point branch**
1. Neon console, project `noisy-sound-20763725`, Branches, create a branch from production at the wanted time (or from a `backup-...` branch). Branch count is 8 of 10 now: delete nothing without the owner's OK.
2. Copy its connection string. Do not paste it in chat, commits or logs.

**Check it before using it** (read-only):
```bash
DRILL_DATABASE_URL='<branch connection string>' backend/venv/bin/python scripts/restore_drill.py
```
It checks the Alembic revision equals the code's head, key table row counts, and that one student can open `/me/home` through a local server. It prints no row contents and never prints the URL. Exit 0 = PASS.

**Switch production to the branch** (owner decides; this is the only step that changes production)
1. Set `DATABASE_URL` on Render to the branch string (or restore production to the branch in Neon).
2. Check `/health`, log in with a QA account.
3. Tell users which recent work may be lost (everything after the restore time).

**Gap: R2 has no restore.** Images and PDFs in R2 are not versioned. A deleted object is gone; the database only holds names and hashes. Treat the R2 bucket as not backed up until the owner chooses an option (`docs/COSTS.md`).

**Also not restored**: JWT secret and other env vars live in Render, not in the database.
