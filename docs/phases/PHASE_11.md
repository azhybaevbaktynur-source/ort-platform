# Phase 11: report

Deployed 2026-11-02 (`main` 10454b4, migrations 0017, 0018; backup branch `backup-2026-11-02-before-phase11` br-floral-heart-b2opj8d8, holding a branch-only role `rehearsal_p11`). Design: `PHASE_11_DESIGN.md`. **Launch has not happened: it waits for the owner and `docs/LAUNCH_CHECKLIST.md`.**

## What shipped
- Parents: pairing code from the student, separate `guardian_links` (no course access), grades, due dates and announcements only; revoke at once.
- Privacy: age band at sign-up (one of three choices), under-14 gate until guardian consent, policy versions marked as a draft awaiting legal review, consent records, export and delete requests, delete = anonymize in place, personal-data registry. Existing accounts: `legacy`, nothing restricted, a banner only. The gate never stops an open attempt.
- Security: rate limits on login, register, reset, verify, pairing; IP rules enforced with the verified chain (`runbooks/IP_CHAIN.md`); token revocation (`tv`), refresh and log out everywhere; 3-day token default; production refuses the public default key; CSP and security headers; dependency audit (one low `katex` finding accepted).
- Performance: EXPLAIN review, two indexes, retention tool off by default, load test script (`PHASE_11_EXPLAIN.md`, `PHASE_11_LOADTEST.md`).
- Operations: JSON masked logs in production, optional Sentry (off), uptime workflow, runbooks, restore drill, cost notes, launch checklist.

## Checks
- SQLite 4030 passed, 49 skipped; PG 4116 passed, 25 skipped before the IP flip (CI re-ran it after); migration tests 15; `alembic check` clean; CI seven jobs green; browser suite passed, zero ORT differences after approving one general phone baseline.
- **Rehearsal on a production copy**: migrations ran through startup in production mode; attempts, attempt items and grade events hash identical before and after; all real accounts `legacy`. Local copy deleted.
- **Production**: data unchanged; sign-up refuses a missing age band; security headers present; 40 of 40 browser checks (register, policies, student home, privacy, course, teacher, parent; no CSP blocks). IP rules after the flip: 30 ordinary answers then 429 on reset-password, 429 with a made-up `X-Forwarded-For`, probe 404, normal login 200. QA accounts disabled afterwards.
- Security review (Fable): one medium, fixed (login lockout by email now per email and address); one low, fixed (erased assets unreadable); one operational (flip order), followed.

## Caught at the gate
- JSON logging masked the address the dev console email needs, which broke every browser test at seeding. Logs are JSON in production only.
- The request log trusted an unverified token's user id; now only a signed one.
- The restore drill's server would have loaded `backend/.env`; it now runs outside `backend/`.
- Local Postgres in `/tmp` was wiped by macOS mid-gate (not a code problem); re-created.

## Not proven or not done
- **6,000 students is not proven**: locally 3,000 savers were good (p95 249 ms), a repeat stalled about 90 s, 6,000 saturated (p50 14 s, nothing lost). The full test needs paid infrastructure.
- IP chain verified from one network plus Vercel's path, not from a phone hotspot.
- Live parent pairing and under-14 consent: covered by tests and local browser specs, not walked on production (no real inbox).
- Agent-written ky and ru text is not reviewed by a native speaker; legal wording is a draft.
- A whole-school sign-up from one address hits `register_ip_1h` (120 per hour); kill switch in `IP_CHAIN.md`.
- Student-facing follow-ups: a child can cancel a parent's delete request; a parent's due list caps at 20.
- Neon history window unread; R2 has no restore.
