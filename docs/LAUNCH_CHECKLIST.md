# Launch checklist (for the owner)
Plain words. **Blocks launch** means we should not open to real students until it is done. Nothing here was decided for you: the agent only filled in safe defaults.

## Read this first: 6,000 students is NOT proven
We tested on a laptop, not on the real servers (`docs/phases/PHASE_11_LOADTEST.md`).
- 3,000 students saving answers: good (typical save 17 ms, 95 in 100 under 249 ms).
- The same 3,000 test run again: it **stalled for about 90 seconds**. We did not find why.
- 6,000 students: the server was **saturated** (typical save 14 seconds). No answer was lost (0 lost), but 14 seconds is not usable.
- So the size is **not proven**. It needs a full test on paid servers near Frankfurt. The script is ready.

## A. Must be done before launch (blocks)
- [ ] Lawyer reads the policy wording, the age limit, the days to answer a data request, and what counts as "anonymous enough". Also the basis for storing data abroad (Neon, Render, Vercel, R2, Sentry). Policy text says "Draft: awaiting legal review" until then.
- [ ] Change the secret key (`SECRET_KEY`) and any other keys you hold. Everyone gets logged out once.
- [ ] Pay for a bigger Render plan and more Neon power **if** one exam will have thousands of students. Prices: `docs/COSTS.md` (many are unknown).
- [ ] Run the full 6,000-student test on those paid servers. Without it, do not promise 6,000.
- [ ] Give the platform its name (the site now says "Платформа") and a public contact address for the Contacts page (it now says details will come). Each is one line for the agent to change.
- [ ] Sign this checklist.

## B. Does not block launch
- [ ] Own web address for the site and for images.
- [ ] Free Sentry account and its DSN (error reports). Logs work without it. Sentry is outside Kyrgyzstan: part of the legal point above.
- [ ] First real run of: removing files of test students, and the practice-history retention (both stay off until you say so).
- [ ] Delete an old Neon backup branch (we use 9 of 10). Only needed if branches run out.
- [ ] Set `PRIVACY_LEGACY_DEADLINE` (cut-off for old accounts) after the lawyer.
- [ ] Read how long Neon keeps history (Neon console) and write it in `docs/runbooks/RESTORE_DRILL.md`. The restore drill itself passed on 2026-11-02.

## Before a big sign-up day
Only 120 sign-ups per hour are allowed from one internet address. If a whole school signs up together from one network, some will wait. Tell the agent before such a day: the limit is easy to raise.

## C. Questions with a default (nothing waits for you)
Confirm or change each. The default is already in use.

| # | Question | Default now |
|---|---|---|
| 11-Q1 | Is 14 the right age limit in law? | 14 |
| 11-Q2 | New sign-ups under 14 limited until the lawyer says OK? | Yes |
| 11-Q3 | Deadline for old accounts to accept? | None, only a banner |
| 11-Q4 | Days to answer a data request? | 30 |
| 11-Q5 | Is a deleted account with its fixed free text anonymous enough? | Yes for now, the lawyer checks |
| 11-Q6 | Delete old practice attempts? | Off (we suggest 365 days) |
| 11-Q7 | Email the person when their request is done? | No (their address is gone) |
| 11-Q8 | Parent sees teacher feedback text? | No: grades, due dates, announcements only |
| 11-Q9 | Students 14-17 can remove a parent any time? | Yes |
| 11-Q10 | Is the free Neon restore window long enough? | Record what Neon gives, buy nothing |

## D. What is already in place
- Error logs without emails, IPs, passwords or answers (tested).
- Site check every 30 minutes on GitHub (opens an issue if the site is down).
- Runbooks: `docs/runbooks/` (deploy, rollback, restore, incident).
- Not covered: images and PDFs in R2 cannot be restored if deleted.

Signed: ______________  Date: ______________
