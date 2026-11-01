# Restore drill report
Status: **passed 2026-11-02** (agent), on a dump of the backup branch restored to local Postgres, then migrated to head. That proves dump, restore, migrate and read. It is **not** a switch of production onto a Neon branch: nobody has rehearsed that step.

| Item | Result |
|---|---|
| Date | 2026-11-02 |
| Branch made from (time) | `backup-2026-11-02-before-phase11` (production at 2026-11-01 18:49 UTC) |
| Neon history window on this plan (from console) | Unknown: needs the owner to read it in the console |
| Alembic current equals head | Yes, `0018_phase11_indexes` |
| Row counts looked right | Yes: 16 users, 7 courses, 10 attempts, 909 attempt items, 304 question versions, 27 assets |
| Student read through local server | Yes, `GET /me/home` 200 |
| Time taken | Script 3.2 s; dump and restore under a minute |
| Attempt data unchanged by migrations | Yes: attempts, attempt items and grade events hash identical before and after |
| Local copy of production data | Deleted after the drill |
| Branch deleted afterwards | No: it is the backup before the Phase 11 deploy. It holds a branch-only role `rehearsal_p11` |
