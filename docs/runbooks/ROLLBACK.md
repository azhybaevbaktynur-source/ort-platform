# Rollback
**Code only (no migration in the bad deploy)**
1. `git revert <bad commit>` on `main` (or a revert of the merge: `git revert -m 1 <merge>`), push. Never force-push `main`.
2. Wait for Render, check `/health` shows the revert commit.
3. Frontend: in Vercel, promote the previous good deployment (Deployments, Promote) or revert the same way.

**A migration ran**
1. Do not downgrade by hand on production. Stop and tell the owner.
2. If data is wrong or lost: restore from the backup branch made before the merge (`RESTORE.md`). Writes made after the backup are lost; say so to the owner before switching.
3. A forward fix migration is safer than a downgrade when the schema is only additive.

After a rollback: write what happened in `INCIDENT.md` form and fix on a branch.
