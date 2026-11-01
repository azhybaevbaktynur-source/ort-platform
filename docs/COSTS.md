# Costs (Phase 11 review)
Only what the repo and docs show. **No service dashboard was read for this file** (no live Neon, Vercel or Render reading; Render's MCP is not connected). Anything not in the repo is marked **unknown**. Prices below come from `docs/CAPACITY_REVIEW.md` §4, which itself calls them unverified; re-check on each provider's pricing page before buying.

| Service | Plan (source) | Free limit | Current use | Price if upgraded |
|---|---|---|---|---|
| Render (API) | Free, Frankfurt, 1 worker, ~0.1 CPU, 512 MB, sleeps when idle (`CAPACITY_REVIEW.md` §1, owner, older than this phase: re-check) | unknown (not recorded) | unknown | Starter about $7/month (unverified); Standard about $25, Pro about $85, per-second billing (unverified) |
| Neon (database) | `free_v3`, 0.25-2 CU, Postgres 18, 10-branch limit, 1 manual snapshot (`CAPACITY_REVIEW.md` §1; `HANDOFF_NEXT_AGENT.md`) | storage and compute-hours: unknown. Branches: 10 | 8 of 10 branches (2026-11-02, `HANDOFF_NEXT_AGENT.md`). Data small (6 users, ~299 question versions at last note) | $0-15 per month for the next plan (unverified) |
| Vercel (frontend) | Hobby, region `fra1` (`CAPACITY_REVIEW.md`) | unknown | unknown | Hobby is non-commercial: re-check before charging anyone; Pro $20 per seat (unverified) |
| Cloudflare R2 | Standard class, free tier (`CAPACITY_REVIEW.md` §R2) | 10 GB stored, 1,000,000 Class A, 10,000,000 Class B operations per month | The app counts bytes (`storage_usage`); warn at 8,000,000,000 B, refuse at 9,500,000,000 B. The current value is in `/admin/storage`; not read here | Unknown beyond the free tier; R2 has no spending cap, hence the app limits |
| Resend / Brevo / SMTP (email) | One provider chosen by env (`EMAIL_PROVIDER`) | unknown | unknown | unknown |
| GitHub (CI, uptime) | Public repo, GitHub-hosted runners | Free for public repos | CI plus one uptime run every 30 minutes | None expected |
| Sentry | Not used until `SENTRY_DSN` is set | unknown | Off | unknown |

## At 6,000 students: questions, nothing bought
1. Render needs a paid plan for an exam of that size (the free plan sleeps and is far below the measured local limit). Which plan, and always on or only around exams? Price: unknown until the owner reads Render's pricing.
2. Neon free compute (max 2 CU) is not proven for exam bursts (`CAPACITY_REVIEW.md` finding 6). Upgrade for exam periods only?
3. Vercel Hobby is for non-commercial use. Will the platform charge anyone?
4. R2 backup: R2 has no restore (`runbooks/RESTORE.md`). Accept the gap, or pay for a second copy? Price: unknown.
5. Neon history window on the free plan: read it in the console and record it in `runbooks/RESTORE_DRILL.md`. A longer window may cost money: unknown.
6. Email quota at 6,000 invitations or notices: free send quota of the chosen provider is unknown.
