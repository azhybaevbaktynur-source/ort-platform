# Platform strategy study: from prototype to a professional product

**Date:** 2026-11-14. **Status:** a study, not a plan in force. Nothing in production was changed; nothing here is decided until the owner decides. **Not legal or tax advice:** every statement about Kyrgyz law, tax or contracts must be confirmed by a Kyrgyz lawyer and accountant before launch of paid access.

Evidence: our own measurements (`docs/phases/PERFORMANCE_AUDIT.md`, `PHASE_11_LOADTEST.md`, `PHASE_3_LOADTEST.md`, `docs/LOAD_TEST_PRE_PHASE3.md`, `DB_STORAGE_REVIEW.md`, `CAPACITY_REVIEW.md`), the code paths that decide scale (`backend/app/lms/attempts/`, `core/ratelimit.py`, `db/session.py`, `lms/infra/`, the workflows, the service worker), and four research notes (comparables, hosting, data services, security/law/payments) whose facts were re-checked on the vendors' own pages where a recommendation depends on them. Sources are numbered at the end and cited inline like [12]. **UNVERIFIED** marks a fact that could not be confirmed on an official page. Web content was treated as untrusted data.

The owner's brief is Appendix A, verbatim.

---

## Summary for the owner (one page)

**Where we are.** The platform runs on four free plans: Vercel (site), Render (server, Frankfurt), Neon (database, Frankfurt) and Cloudflare R2 (images). Everything works, and the design of the exam engine is sound: in every load test, including the ones where the server collapsed, **not one saved answer was lost**. But the free plans are for testing, not for real students:

- The Render server **falls asleep** after 15 minutes and takes about a minute to wake. It has a tenth of a CPU. Measured capacity is roughly **150–250 students saving answers at once**, not 6,000.
- The database keeps only **6 hours of history** for an undo, and if it moves more than 5 GB of data in a month it is **switched off** until the next month.
- Vercel's free plan is **for personal, non-commercial use only** [1]. The day we charge money, we must be on a paid plan or another host.
- **6,000 students at once is not proven.** We tested on a laptop; the laptop saturated at about 3,000–3,750 students. The real servers were never load-tested.

**What to do, in order (Stage 1, about $30 a month):**
1. Buy the domain (`.kg` at cctld.kg, about 2,600 som the first year [58]) and put its DNS on Cloudflare (free). Images move off the rate-limited `r2.dev` address; the API gets a free firewall and rate limits. *Owner: buying and the registrar account.*
2. Pay Render **Starter, $7/month** [11]: no more sleeping. For exam days switch to a bigger size for a few hours (billed per second; a 3-hour window on a 4-CPU size costs under a dollar).
3. Pay Vercel **Pro, $20/month** [2][3] *or* move the site to Cloudflare Workers for $5 (one to two days of agent work). Either makes paid exams allowed.
4. Keep Neon free until the first paying student, but start a **weekly encrypted copy of the database to a second vendor** (Backblaze B2, free at our size [45]) and keep the monthly restore drill.
5. Switch on the free error tracker (Sentry, EU region [60]) and a free outside uptime monitor (UptimeRobot [62]); GitHub's own schedule is disabled after 60 days without commits [65].
6. **Run the 6,000-student load test on the real Frankfurt servers** (script exists; cost a few dollars). Until then, promise 3,000, not 6,000.
7. Fix four small things in code now so growth stays cheap (section 5.3): the attempt-sweep lock that can leak behind Neon's pooler, email sending inside requests, a Dockerfile for portability, and answers that survive a dead network until the student is back online.

**What it costs later.** Stage 2 (thousands of students, paying users): about **$200–300/month**: Render Pro workspace with two servers that scale automatically, Neon Launch always on, Cloudflare Pro, Sentry, a paid email tier. Stage 3 (tens of thousands, several exams, schools): about **$900–2,000/month**, mostly database with a 99.95 % guarantee and more servers. In every stage the pieces are the same, so there is no rebuild: we add servers and pay for guarantees.

**What we recommend not doing early:** Kubernetes, microservices, our own servers (VPS) for the database, multi-region, a separate cache (Redis) before there are two servers, webcam proctoring, Cloudflare Business or Enterprise, a dedicated email IP. Every large platform that tried these did so at hundreds of engineers; a three-engineer company (Magoosh) runs 5 million users on exactly our shape: one app, one Postgres, one job queue [100].

**Security, plainly.** The code does the right things (server-side permissions, hashed passwords, two-step login for admins, immutable exam snapshots, answers never sent to the browser, an audit log). The gaps are around it: no staging environment, no firewall in front of the API, IP rate limits only logging, backups on one vendor, no 72-hour regulator-notification step in the incident runbook, and the consent texts not yet checked against the **new Digital Code** (the 2008 personal-data law was repealed on 2026-02-05 [67][68]). Children's data in Kyrgyzstan needs consent: the student's own from 14, a parent's under 14 [67].

**Decisions only the owner can make** (section 7.5): spend money (any paid plan); buy the domain and own the registrar login; register a business (ИП or ОсОО) and choose a tax regime; sign a payment-provider contract (Finik, Freedom Pay or a bank; Stripe and Google Play billing are not available to a Kyrgyz business [85][72]); hire a Kyrgyz lawyer to review consent, the user agreement, refunds and cross-border hosting; choose the Sentry data region (irreversible) and where off-vendor backups live; whether minors may pay themselves; whether to publish an Android app at all (it would have to be free with no purchase links [73]).

---

## 1. Where we are

### 1.1 The map

```
Student's phone/laptop (Kyrgyzstan, ~91 ms to Frankfurt [23])
   |                         |                              |
   v                         v                              v
Vercel (Next.js 15,     Render Frankfurt              Cloudflare R2 public bucket
 functions pinned        FastAPI, 1 worker,            (WebP images, immutable,
 to fra1; Hobby)         Free plan, sleeps)            served from an r2.dev URL)
                              |
                              v
                        Neon Postgres 18 (Frankfurt, Free, 0.25-2 CU, 10 branches)

Email: Brevo (HTTPS API, free, from the owner's personal address) [48]
CI/uptime/maintenance: GitHub Actions (public repo; cron every 10 min and daily 04:30 UTC)
Error tracking: Sentry wired, OFF (no DSN). Logs: JSON lines on Render (short retention).
DNS/domain: none yet (vercel.app and onrender.com addresses). Payments: none yet (activation codes).
```

The browser calls the API directly (`NEXT_PUBLIC_API_URL`), so exam traffic does not pass through Vercel. The app has no Vercel-specific feature (no middleware, `next/image`, Server Actions or ISR), which keeps the frontend portable (hosting note §0; `frontend/next.config.ts`).

### 1.2 Rating per part

Scale: **good / fair / weak / no-go**. "Breaking limit" is where the part stops serving; "measured" says whether we have a number of our own.

| Part | Security | Speed | Reliability | Cost now | Breaking limit (our numbers) | Measured? |
|---|---|---|---|---|---|---|
| **Render Free (API)** | fair: Cloudflare L3/L4 DDoS shield [15], no WAF, no L7 rate limit except ours | **weak**: ≈0.27 s proxy floor per request, 60 s wake-up [audit §3.5, §10.1] | **no-go for exams**: sleeps after 15 idle min, "may restart at any time" [12], 1 instance | $0 | ≈30–45 light requests/s, 1.2 logins/s (bcrypt 83 ms), ≈150–250 students in steady autosave (`PHASE_3_LOADTEST.md` §7, extrapolated from a laptop) | Partly: per-request floor and cold start measured in production; capacity extrapolated, never load-tested on Render |
| **FastAPI app (code)** | good: DB roles per request, bcrypt, admin MFA, audit log, immutable snapshots, keys never sent to the browser | good: 2–8 ms app time per endpoint, 2–21 statements, no N+1 except the audit log [audit §10.1] | good: admission gate stops the pool deadlock; 0 lost answers in every run | – | Laptop: ≈170–200 req/s saturation; 3,000 students healthy, 3,750+ falls behind (`PHASE_11_LOADTEST.md`); autosave 3.2 ms CPU, start 21 ms, submit 10.6 ms per request (`PHASE_3_LOADTEST.md` §4) | Yes, locally; never on paid infrastructure |
| **Neon Free (DB)** | fair: TLS, no IP allow-list (Scale only) [30] | good: hot queries 0.04–0.14 ms, ≈3 ms per statement from Render [audit §3.4, §10.1]; 0.65 s resume after 5 idle min | **weak**: 6 h restore window, 1 GB storage, **5 GB/month egress then compute suspended** [30]; no SLA | $0 (8.9 CU-h of 100 used in 12 days; 41.6 MB of 1 GiB) | DB CPU is not the limit (500 autosaves/s at ≈2 ms, 421 starts/s, 800 pooled connections OK: `LOAD_TEST_PRE_PHASE3.md` §2). Storage is: ≈0.2 GB per 6,000×150 exam, so **≈4 full exams fit** in 1 GiB (`DB_STORAGE_REVIEW.md`) | Yes (DB-level, on a Neon branch) |
| **Vercel Hobby (site)** | good: automatic DDoS, 3 WAF rules, 1 rate-limit rule [2][6] | good: static pages 0.07–0.4 s from Europe [audit §3.5]; **rewrite path to Render 0.8–2.8 s** (one warm-up call still uses it) | fair: hard caps pause the feature for up to 30 days instead of billing [2] | $0 | 1 M CDN requests, 100 GB transfer, 1 M function calls per month [2]; **non-commercial use only** [1] | Partly (public pages measured; logged-in pages not on production) |
| **Cloudflare R2** | good: content-addressed keys, private bucket for PDFs, presigned downloads | good when cached; **r2.dev is rate-limited and uncached** [43] | fair: no versioning, **no backup**, no restore (`runbooks/RESTORE.md`) | $0 (app guard: warn 8 GB, refuse 9.5 GB) | 10 M Class B reads/month ≈ **104 sittings of 6,000 students** if every image read hits R2 (`CAPACITY_REVIEW.md` §6); a burst of 96,000 image GETs on r2.dev may be throttled | Arithmetic only; never load-tested |
| **Email (Brevo free)** | fair: sends from a personal address, no own domain, no DMARC yet | fair: **sent inside the request** for sign-up codes and resets (`auth.py:127`, 10 s HTTP timeout) | weak: **300 emails/day** [48, UNVERIFIED on Brevo's page]; a 6,000-roster invitation day cannot be sent | $0 | 300/day | Not measured |
| **DNS / domain** | none: addresses belong to Vercel and Render; no firewall we control | – | fair: a vendor change means a new address for every student and PWA reinstall (`runbooks/CUSTOM_DOMAIN.md`) | $0 | – | – |
| **CI/CD (GitHub Actions)** | fair: `permissions: contents: read`, actions pinned by tag not SHA; CodeQL/Dependabot/secret-scan state not visible from the repo | good: free, unlimited on a public repo [64] | fair: deploys straight from `main` with no staging; Render redeploy on CI pass **UNVERIFIED** | $0 | Scheduled workflows **disabled after 60 days without repository activity** [65] | – |
| **Monitoring** | – | – | **weak**: uptime = a GitHub cron every 10 min (also our keep-awake); Sentry off; logs 1 h (Vercel) / short (Render Hobby) | $0 | The cron is best-effort ("may be delayed or skipped", workflow comment) and dies with inactivity [65] | – |
| **Backups** | fair | – | **weak**: Neon 6 h window + manual branches (7–9 of 10 slots used); restore drill passed once on 2026-11-02 (dump→local→migrate), never a production switch; **R2 not backed up**; env/secrets only in Render | $0 | 10 branch slots | Drill: yes, once |
| **Payments** | – | – | none exist (activation codes only) | $0 | – | – |

### 1.3 What we measured and what we never measured

**Measured (ours):**
- Database statement costs on a Neon branch through the pooler: autosave UPDATE ≈2 ms server time at 500/s; attempt start (150 rows, one CTE) 421/s at 200 connections; submit scoring 0.1 ms; 800 pooled connections accepted (`LOAD_TEST_PRE_PHASE3.md` §2).
- API CPU per request on an M1 core: autosave 3.2 ms (3 answers), start 20.9 ms, submit 10.6 ms, content 1.9 ms, login 83 ms (bcrypt) (`PHASE_3_LOADTEST.md` §4; `LOAD_TEST_PRE_PHASE3.md` §3.2).
- Full ORT exam simulation, 6,000 virtual students, local Postgres, 2–4 workers: integrity perfect in every run (0 lost, 0 double grades, all finalized); latency acceptable at 3,000 (autosave p95 22 ms, start 40 ms, submit 94 ms), CPU-saturated at 6,000 on the laptop (`PHASE_3_LOADTEST.md` §5, §11).
- Mixed load (saving students plus readers): healthy at 3,000 (save p95 249 ms), falls behind at ≈3,750, saturated at 6,000 (save p50 14 s); one unexplained 90 s stall at 3,000 (`PHASE_11_LOADTEST.md`).
- Production per-request floor ≈0.27 s (Render proxy + Free instance), Render cold start ≈60 s, Neon resume ≈0.65 s, Vercel rewrite hop 0.8–2.8 s; per-endpoint statement counts (`PERFORMANCE_AUDIT.md` §3.5, §10.1).
- Production data size 41.6 MB; ≈4 full exams fit in the free 1 GiB (`DB_STORAGE_REVIEW.md`).
- Restore drill: dump, restore, migrate, read, 3.2 s script time (`runbooks/RESTORE_DRILL.md`).

**Never measured (say so to anyone who asks about 6,000):**
- Any load on Render, Neon and Vercel together (the laptop shared CPU with the generator; `PHASE_11_LOADTEST.md` "What local measurements cannot tell us").
- Network and TLS from Kyrgyz mobile networks; real browsers loading images from R2; the r2.dev throttle.
- A login burst (tests minted tokens, skipping bcrypt).
- Neon autoscaling under a burst (the free max is 2 CU) and whether `max_connections` changes live with autoscale (**UNVERIFIED**, [31] ties it to the compute size).
- Render bandwidth per exam (Hobby includes 5 GB/month, then $0.15/GB [11]).
- The cause of the 90 s stall at 3,000.
- Logged-in page timings in production (no owner password used by agents).
- Email deliverability to mail.ru, Yandex and Gmail from our address (no own domain yet).

### 1.4 Code findings that decide scalability (read for this study)

| Finding | Where | Effect | Verdict |
|---|---|---|---|
| **Attempt sweep takes a session-level advisory lock and then commits** on a dedicated pooled connection; the unlock runs later on the same client connection | `backend/app/lms/attempts/sweep.py:106-132` | Behind a transaction-mode pooler (Neon `-pooler` host, which PgBouncer runs in transaction mode [31]) the server connection is returned to the pool at `commit()`; the later `pg_advisory_unlock` may run on a different server connection and the lock stays held on the first one until that server connection closes. Neon lists session-level advisory locks as **not supported** through the pooler [31]. Later sweeps then return 0 ("someone else holds it") for minutes to hours. Expired attempts still finalize lazily when a student or teacher opens them and by the daily maintenance job (`runbooks/MAINTENANCE.md` task 1), so the failure is **silent and degraded, not data loss**. The ORT seed and migrations use `pg_try_advisory_xact_lock`, which is pooler-safe | **Confirmed from the code.** Whether production `DATABASE_URL` is the pooled host is UNVERIFIED (env not read, by rule); the design docs tell us to use it. Fix (not done here): hold `pg_try_advisory_xact_lock` inside one open transaction for the whole sweep, or give the sweep engine a direct (non-pooler) URL, plus one Postgres test that runs two sweeps through a transaction-mode pooler. About half a day |
| DB-backed fixed-window rate limiter with its own 2+3 connection pool | `core/ratelimit.py` | Works across workers and instances without Redis (good). Each counted event is one upsert | Keep. IP rules are **log-only** until `RATE_LIMIT_IP_ENFORCE` (runbook `IP_CHAIN.md`) |
| Pools per worker: app 5+5, rate limit 2+3, sweep 2 = up to ≈17 connections per worker | `db/session.py`, comments | 3 instances × 4 workers ≈ 200 client connections: fine for PgBouncer (10,000) [31], too many for a direct 0.25 CU endpoint (112) | Always the pooled URL for the app; the direct URL only for Alembic and dumps |
| Admission gate per process (B1 fix) | `core/admission.py` | Excess requests wait in the event loop, 503 `server_busy` after 20 s; removed the pool deadlock | Keep; it is why overload degrades instead of collapsing |
| In-process state: autosave token bucket, sweep `_last_scheduled`, admin overview cache (60 s), payload/plan LRU caches, `_dummy_hash` | `attempts/autosave.py`, `sweep.py`, `platform_admin/overview.py`, `assessments/cache.py` | All per process. With N instances the autosave per-user bucket allows N× the intended rate, the sweep may run N× as often, caches are warmed N times. None is a correctness problem (DB guards are authoritative); the immutable payload cache is exactly right for a CDN later | Acceptable for horizontal scaling; note the N× bucket. No Redis needed until measured |
| `pool_pre_ping=True`, `pool_recycle=300`, statement timeout only via startup option (rejected by the pooler) | `db/session.py` | Survives Neon's suspend; no per-statement cap in production | Add `SET LOCAL statement_timeout` per transaction instead (pooler-safe) |
| Sign-up code and password-reset emails are sent **synchronously inside the request** (HTTP call, 10 s timeout) | `api/v1/endpoints/auth.py:127`, `:464`; `services/email_service.py` | A slow provider holds a worker thread and a DB connection per request during a sign-up surge. Invitations already use `BackgroundTasks` after commit | Move to `BackgroundTasks` or an outbox table drained by the maintenance route |
| Service worker caches only the shell and `/_next/static`; never API or pages; update toast never on exam routes; kill-switch runbook exists | `frontend/public/sw.js`, `runbooks/SERVICE_WORKER.md` | Safe for exams; no offline answer buffer | Keep. An offline answer queue is a separate, deliberate feature (section 5.3) |
| R2 usage guard: atomic reservation on its own connection; no list calls; monthly Class A/B counters; estimated Class B for exams | `files/usage.py` | Keeps R2 in the free tier by construction | Keep; count a backup bucket too if it lands in the same account |
| Uptime cron every 10 min doubles as the Render keep-awake (≈720 of 750 free hours) | `.github/workflows/uptime.yml` | Single point: GitHub delays, skips, and disables schedules after 60 idle days [65] | Add an external monitor; stop depending on it once Render is paid |
| Maintenance job (daily 04:30 UTC) behind a shared token; safe tasks also run from the admin overview every 12 h | `maintenance.yml`, `runbooks/MAINTENANCE.md` | Good design: bounded, idempotent, DB-backed | Keep |
| Services panel (`/platform/infra`, `/platform/health`) stores provider snapshots in `infra_snapshots` with a TTL; provider keys unset in production ("not connected") | `lms/infra/service.py`, `capacity.py`, `costs.py` | The panel can show Neon/Render/Vercel/R2 usage once read-only keys are set; cost rows mirror `docs/COSTS.md` and are marked unverified | Set read-only keys (owner) so the panel becomes the capacity dashboard |
| Startup: Alembic with 10 s lock timeout × 8 retries, seeds, import warm-up; no Dockerfile or `render.yaml` | `db/migrate.py`, `core/warmup.py` | Zero-downtime deploys work on Render; moving hosts needs a Dockerfile | Add a Dockerfile now (no behaviour change) |

---

## 2. How others do it

Source quality: [P] primary (the company's own blog, docs or statement), [V] vendor case study, [S] press or third party. Details and more cases are in the comparables research note; this table keeps what matters for us.

| Who | Scale | Stack in production | What broke, and why | Copy | Don't copy |
|---|---|---|---|---|---|
| **Canvas LMS** (Instructure) [92][103] | thousands of schools | Rails monolith on AWS, Postgres sharded with Switchman (pgbouncer-safe, schema-qualified queries), Redis cache, **Postgres-backed job queue** (inst-jobs, "tens of millions of jobs a day"), S3 + CloudFront, public annual pentest since 2011 [P] | 2021-03: a code update overwhelmed a shared service (3 h). **2026-05: data breach during finals**; Canvas offline a day, exams postponed [S] | One Postgres, a DB-backed job queue, workers apart from web, a CDN, outside pentests, a change freeze at exam time | Sharding, multi-region |
| **Moodle** (official docs) [93][94] | up to 3.5 M users per site | Several web nodes behind a balancer, one DB, Redis for cache and sessions, read replicas since 3.9 (80–90 % of DB load on large sites) [P] | "The worst possible scenario is a large class all starting a timed quiz at exactly the same time" [P]. UniSA 2020: a **login surge before 09:00** (30 s waits) and **one bad query** in a block turned 1 s pages into 10 s; six weeks of load tests to 9,000 concurrent [S] | Load-test the exact start spike including login; hunt the one bad query; open a waiting page early; Redis only with more than one node | Self-run DB clustering ("needs expert support") |
| **Khan Academy** [95] | 20–30 M monthly | Google App Engine autoscaling, Datastore, Memcache, Fastly CDN in front of everything, YouTube for video [P] | 2.5× traffic in two weeks (2020): fine; the slowdowns came from **deploys**. CTO: "autoscaling is expensive", "hooked in tightly" [S] | CDN in front, offload media, freeze deploys in a surge, ask providers for quota early | NoSQL lock-in; a 3-year monolith-to-services rewrite |
| **Edmodo** [96] | 25× growth in 3 weeks (2020), 5 M DB queries/s | Percona MySQL replicas on AWS, Docker in auto-scaling groups [P slides] | **Connections broke first**: raising `max_connections` stopped working at ≈2 M QPS; ProxySQL pooling added "a little before the last moment"; **one UPDATE was 16 % of all writes** and was cut 6× | Pool connections before you need them; find the hottest write (ours is autosave); keep a kill switch | 450 database servers |
| **Duolingo** (Super Bowl ad) [97] | 4 M pushes in minutes | Pre-scaled 5,000 workers hours ahead; 3 load-test rounds; a human on the trigger [S of P talk] | nothing: the pattern worked | For a known-time peak, pre-scale on a calendar and keep a person on the switch | 500 microservices on Kubernetes |
| **College Board Bluebook** (digital SAT/AP) [98] | 268,000 per sitting | The test is **downloaded to the device 1–5 days before**; answers saved on the device; late submit from the same device [P] | 2025-03: a **misconfigured setting** auto-submitted ≈10,000 tests early; 2025-05: a **security setting** blocked AP Psychology logins at the start. Both configuration, not capacity [P/S] | Content on the device before the clock starts; answers survive a dead network; idempotent late submit; extend the start and offer make-ups | Native lockdown apps |
| **State testing failures** (Texas STAAR 2021, Tennessee TNReady 2018, NAPLAN 2019) [107][108] | 250,000+ | – | Vendor "database problems" (STAAR); an **unauthorized software change during the test window** (TNReady, no cyber-attack found); a misconfigured firewall (NAPLAN) [P/S] | Written change freeze during exam windows | – |
| **Magoosh** (GRE/GMAT prep) [100] | 5 M+ registered, **3 engineers** | Rails + React + Postgres, Resque/Redis jobs [S, UNVERIFIED-direct] | – | **This is our shape.** A small team on a monolith is normal at millions of users | – |
| **PhysicsWallah** (JEE/NEET) [101] | 2 M daily | AWS, CloudFront with a private S3 origin, **WAF + Shield**, later separate prod and non-prod accounts, GuardDuty, cross-account backups [V] | Day-1 crash in 2020 (40,000 logins at once). Before the retrofit: prod and non-prod in one account, no reliable backups, no alerting. "Millions" of malicious requests a day | The retrofit checklist: separate prod and staging, tested backups, alerting, WAF, private origin behind the CDN | 100k-concurrent live-video infrastructure |
| **Testbook** (India) [102] | 3.2 M students | GCP instance groups up to 2,000 VMs [V] | **100–200× spikes when an exam is announced** and when results come out, not only at exam start | Expect the spike at announcement and results, not only during the test | 2,000-VM fleets |
| **Uchi.ru** (Russia, K-12) [99] | 30k → 240k peak users in weeks (2020) | Own servers + cloud; Postgres with PgBouncer; Redis [P] | Cloud **region quotas**; alerting became noise; **PgBouncer on the DB host ate 20–25 % CPU** (moved off); a single Redis was CPU-bound on one core; the log pipeline dropped logs | A ready pre-mortem: ask Render and Neon about limits before the big day; keep alerts few; don't trust a single cache core | Self-run data centres |
| **Kundelik.kz**, Uzbek registration portals [104] | 2.2 M users day 1 | – | Two outages on the first remote-learning day (infrastructure settled 2–3 days before); **daily DDoS** at term start; Uzbek portals overloaded by bots from the same IPs [S] | National-exam moments draw bots and DDoS: edge WAF, bot checks on sign-up | – |
| **Sirius / All-Russian Olympiad** [106] | 320k+ students | Managed Postgres + Redis + Kubernetes on Yandex Cloud [V]; each subject open **one day, 08:00–20:00 local, per region**; "only saved answers are checked" [P memo] | – | **Spread the start for free** (wide windows for practice, staggered cohorts for a mock ORT day); server timer authoritative | Kubernetes |
| **Aknet (KG ISP), 2021** [105] | – | – | Subscribers lost access to **all .kg sites** for a day; cause unknown [S] | Autosave must survive the last mile; a `.com`/`.app` mirror domain is a cheap hedge | – |

**Lessons that apply to us** (each is used in sections 5–7):

1. **Almost every exam-day failure was a change, a configuration or one bad query, not raw capacity** (Bluebook ×2, TNReady, Canvas 2021, UniSA, Edmodo's one UPDATE). Rule: a written change freeze during exam windows; a staging environment; profile the hottest queries before buying hardware.
2. **Connections break first, then the pooler, then the cache; CPU last** (Edmodo, Uchi.ru). We already use a transaction pooler and small per-worker pools; keep every query pooler-safe (the sweep lock is the one exception, section 1.4).
3. **The start is the peak and login is part of it** (Moodle, UniSA, MESH, AP Psychology). Spread it: wide windows for practice, staggered cohorts for synchronized mock days, an open countdown page 15–30 minutes early, pre-issued tokens (bcrypt is 83 ms per login on our server).
4. **Load the content before the clock starts and make it static** (Bluebook, Khan, ETS 80 % edge offload). Our snapshots are immutable and already have an ETag and gzip cache; serve section payloads and images from the CDN domain.
5. **Answers must survive a dead network** (Bluebook, Canvas, Moodle, the Aknet outage). Local queue, batched autosave, idempotent late submit, server timer stays authoritative.
6. **Batch the hottest write.** Autosave is our "16 % UPDATE". Today: 1–5 answers per request every 15–25 s, one conditional UPDATE per answer. Good; keep it that way and never write per keystroke.
7. **A small team on a monolith is normal at millions of users** (Magoosh). Do not split services, adopt Kubernetes, shard or go multi-region.
8. **Add only what fixes a measured limit**: a Postgres-backed job queue before any broker; Redis only with several instances; read replicas only after caching (exam traffic is write-heavy).
9. **Pre-scale on a calendar** (Duolingo, Edmodo) and ask providers about limits in advance (Uchi.ru). Render bills per second; Neon autoscales.
10. **National-exam moments attract bots and DDoS** (Kundelik, Uzbek portals, Khan's 17,000 % spike). An edge WAF and rate limits in front of the API, bot checks on sign-up.
11. **A breach at exam time is worse than an outage** (Canvas 2026). Retrofit early what PhysicsWallah had to retrofit.
12. **Degrade, don't die**: feature flags to shed statistics, analytics and catalog under load while login, start, autosave and submit keep working.

---

## 3. Options per layer

Stage shorthand: **S0** now ($0), **S1** launch (hundreds, ≈$30/month), **S2** thousands and paying users, **S3** tens of thousands, several exams, schools. Prices in USD excluding VAT, from the vendors' pages on 2026-11-14 unless marked. "Move effort" is agent working time from today's code. "Founder burden" is what one founder working through an agent must keep doing.

### 3.0 Facts that shape every layer

- **Latency from Bishkek** (one measuring host per city, indicative) [23]: Moscow 50 ms, Helsinki 63, Almaty 72, **Frankfurt 91**, Warsaw 91, Amsterdam 96, London 127, Singapore 233, Mumbai 235. Asian regions are 2.5× worse. **Frankfurt is right**, and the backend and database must stay in the same region: each API request makes several database round trips, so a split (API in Helsinki, DB in Frankfurt) is a net loss.
- **Cloudflare has a point of presence in Bishkek** (and Almaty, Astana, Dushanbe) [24]; Vercel, Fly, Railway, Render have nothing in Central Asia [7][17][18]. This helps cached static content and TLS, not the API.
- **No data-localisation requirement** was found in the Digital Code (section 4.3): hosting abroad is allowed with the right consent and contracts. Local hosting (one commercial data centre in Bishkek, not Uptime-certified; PS Cloud Almaty; Yandex Cloud's single zone in Karaganda) would only matter if the law changed, and would cost us Neon-quality managed Postgres (hosting note §3.1).

### 3.1 Frontend hosting

| | Vercel Hobby (now) | Vercel Pro | Cloudflare Workers + OpenNext | Netlify | Self-hosted (Docker on a VPS behind Cloudflare) |
|---|---|---|---|---|---|
| Commercial use | **No** (Terms §4: "personal or non-commercial use") [1] | Yes | Yes (Free "for personal or hobby projects that aren't business-critical"; Paid is fine) [25][53] | Yes (UNVERIFIED on Free) | Yes |
| S0 / S1 / S2 / S3 | $0 / not allowed once paid / – / – | – / **$20** incl. $20 usage credit / $20–40 est. / $40–150 est. (Flat Rate CDN tiers $20, $100, $300) [3][4] | $5 Paid minimum (Free gives 10 ms CPU per request, too tight for SSR) / $5 / $5–10 / $10–30 est. [25] | $0 (300 credits ≈ 20 deploys) / $9–20 / $20+ / $50+ [27] | ≈€17–20 (shared box) / same / €20–40 / €40–100 + ops time [21] |
| Limits | 1 M CDN requests, 100 GB, 1 M function calls, 4 h CPU; features pause up to 30 days when exceeded [2] | 10 M requests, 1 TB; overage $2/1M requests, $0.15/GB; spend cap with optional hard pause [3][5] | 10 M requests + 30 M CPU-ms included, then $0.30/1M and $0.02/1M CPU-ms; static assets free and unlimited [25] | Credit-based: every production deploy costs credits (bad for an agent that deploys often) [27] | Fixed box |
| Latency for KG | functions pinned to fra1; PoP in Europe [7] | same | **Bishkek PoP** for static; SSR runs at the nearest Cloudflare compute [24] | UNVERIFIED (default US East unless changed) | Cloudflare in front: Bishkek PoP for static |
| Security | auto DDoS, 3 WAF rules, 1 rate-limit rule, 10 IP blocks [2][6] | 40 WAF rules, rate limiting from $0.50/1M, 40 IP blocks; OWASP managed ruleset Enterprise only [6] | unmetered DDoS, Free managed ruleset; Pro $20–25 adds OWASP and 2 rate-limit rules [53][54][55] | basic rules | all via Cloudflare |
| Next.js 15 fidelity | reference | reference | high, adapter follows Next releases; workerd runtime, not Node [26] | high, adapter | full on one instance [28] |
| Lock-in | low (we use no Vercel-only feature) | low | low–medium (adapter) | low | none |
| Move effort | – | 0 (plan upgrade) | 1–2 days (adapter, `wrangler.toml`, CI, DNS) | 1 day | 2–4 days + runbooks |
| Founder burden | none | none | low–medium | low | **high** (patching, TLS, deploys, logs) |

Verdict: at S1 **Vercel Pro ($20, zero effort)** or **Cloudflare Workers ($5, 1–2 days, Bishkek PoP, same vendor as R2 and DNS)**. Both solve the same problem (commercial use allowed). Netlify adds nothing. Self-hosting is the founder's time, not money. Do not proxy Vercel through Cloudflare (Vercel's own guidance: breaks its firewall and bot signals) [8]; proxy only the API and image hosts.

### 3.2 Backend hosting (one FastAPI service; the database stays on Neon Frankfurt)

| | Render (now) | Fly.io | Railway | Google Cloud Run | AWS ECS Express / Fargate | Hetzner / DigitalOcean VPS |
|---|---|---|---|---|---|---|
| Plan change to know | **2026-04-23: new workspace plans**; legacy workspaces moved 2026-08-01. Hobby $0, **Pro $25 flat** (was $19/seat), Scale $499. Included bandwidth **5 GB / 25 GB / 1 TB**, overage $0.15/GB. **Autoscaling needs Pro** [9][10][11] | no free tier for new orgs; bills under $5 waived [17] | Hobby $5, Pro $20/workspace + usage (≈$20/vCPU-month, $10/GB-month) [18] | request-based or instance-based billing; free tier 180k vCPU-s + 2 M requests/month [20] | **App Runner closed to new customers 2026-04-30**; AWS points to ECS Express [19] | Hetzner raised prices twice in 2026 (CPX22 2 vCPU/4 GB now €16.99 Helsinki / €19.99 Nuremberg) [21][110]; DO 2 vCPU/4 GB $24 [22] |
| S0 | Free: sleeps 15 min, ≈60 s wake, "may restart any time", 750 h/month [12] | ≈$0 | $1 credit | free tier covers light use | – | – |
| S1 (hundreds) | **Starter $7** (0.5 CPU/512 MB) or Standard $25 (1 CPU/2 GB) [11] | ≈$8–30 | $5 + $20–40 | ≈$0–15 request-based; ≈$45 with a min instance (est., UNVERIFIED rates) | ≈$55 est. (Fargate + ALB) | €17–24 |
| S2 (thousands, paying) | **Pro $25 + 2–4× Standard = $75–125** with autoscaling | 2–4× performance-1x ≈ $76–152 | $20 + $80–160 | ≈$60–150 est. | ≈$100–200 est. | 2 boxes + LB ≈ €80–110 est. |
| S3 (tens of thousands) | Pro + 4–10× Standard/2c-4g = $200–900 | $300–800 est. | $300–900 est. | $200–700 est., best for rare large peaks (scale to zero, fast autoscale) | $300–1,000 est. | €150–400 + heavy ops |
| Frankfurt | **yes** | yes (+15 %) | **no** (Amsterdam) | yes (Tier 2), Finland Tier 1 | yes | yes |
| Autoscaling | Pro, CPU/memory, up to 100 instances [13] | autostop pool + metrics app | manual replicas | automatic, scale to zero | yes | DIY |
| Zero-downtime deploys | yes, health-checked [14] | yes | yes | yes (revisions) | yes | DIY |
| WAF / L7 | **none** (L3/L4 only) [15][16] | none | none | Cloud Armor (extra) | AWS WAF (extra) | via Cloudflare |
| Staging | preview envs (full-stack on Pro), 2 envs on Hobby | second app | environments | revision tags | separate service | second box |
| Lock-in | low (plain Python; a Dockerfile makes it fully portable) | low | low | low–medium (IAM, registry) | medium–high | none |
| Move effort | – | 1–2 days | 1 day | 2–3 days | 4–7 days | 3–5 days + runbooks |
| Founder burden | **low** | low–medium | low | medium | **high** | **high** |

Verdict: **Render stays** for S1–S2. It is next to Neon, deploys without downtime, and is the lowest burden. Two caveats: an exam must never run on the Free instance, and autoscaling needs the $25 Pro workspace. Cloud Run is the strongest "big cloud" option for S3 if peaks are large and rare; a VPS is cheaper only in money, not in the founder's nights. Never App Runner.

### 3.3 Database (connection pooling, read replicas, backups)

| | Neon (now) | Supabase | AWS RDS (Frankfurt) | Azure Flexible Server | DigitalOcean Managed PG | Self-managed on a VPS |
|---|---|---|---|---|---|---|
| S1 $/month | Free $0, or **Launch ≈$15–20** (0.25–2 CU, scale to zero on, 7-day restore) [29][30] | Pro $25 (+$10 Micro compute credit) [36] | t4g.micro/small single-AZ $14–27 (no HA) [37] | B1ms ≈$14.5 [data note §1.3] | 1 GiB $15.15 (22 connections) [39] | €6–10 |
| S2 | Launch always on 0.5–4 CU ≈$45–80; Scale (SLA, IP allow, 30-day restore) ≈$90–170 | $130–175 with PITR add-on ($100 per 7 days) [36] | Multi-AZ small/medium $54–110 [37] | $58–116 | $30–60 + standby | €15–40 |
| S3 | Scale, 2 CU primary always on + 1 replica + 20–50 GB ≈ **$500–600** | $300–450 | m7g.large Multi-AZ + replica $300–470 | $250–500 (UNVERIFIED) | $200–400 | €60–150 |
| Restore window (PITR) | **Free 6 h** (1 GB change cap); Launch 7 days; Scale 30 days; $0.20/GB-month of history [30] | Pro daily backups 7 days; PITR add-on $100/month per 7 days [36] | up to 35 days (UNVERIFIED) | built in | 7 days | DIY (pgBackRest [41]) |
| Pooling | built-in PgBouncer, 10,000 clients, pool = 0.9 × max_connections (0.25 CU: 112; 1 CU: 450) [31] | Supavisor (transaction mode) | RDS Proxy or own PgBouncer | built-in (UNVERIFIED) | PgBouncer, small limits | DIY |
| Read replicas | same storage, created in seconds, billed as compute, async [32] | Small compute and up | yes | yes | limited by edition [39] | DIY (Patroni = big step) |
| Scale to zero | Free: forced after 5 min; Launch: optional; Scale: 1 min to never [33] | pauses after 1 week on Free | no | no | no | – |
| SLA | **Scale only, 99.95 %** [34] | Enterprise only | Multi-AZ | yes | yes (UNVERIFIED) | none |
| Egress | Free **5 GB/month, then compute suspended** [30]; paid 500 GB | 5 GB / 250 GB | per GB | per GB | – | 20 TB (Hetzner) |
| Region | eu-central-1 Frankfurt [35] | Frankfurt | Frankfurt | Germany West Central | FRA1 (UNVERIFIED) | Helsinki/Nuremberg |
| Lock-in | low (plain Postgres 18; `pg_dump`, logical replication) | low–medium (if Auth/Storage/RLS were used; we use none) | low | low | low | none |
| Founder burden | **very low** (branches for previews and pre-deploy backups) | low | medium (IAM, VPC, upgrades) | medium | low–medium | **high** (3–6 h/month plus incident nights) |

Pooling details that matter for our code: psycopg2 sends no server-side prepared statements (pooler-safe); we use `SET LOCAL` only; the seed uses transaction-level advisory locks; **the sweep's session-level lock is the one unsafe statement** (section 1.4). Keep the SQLAlchemy pool small per worker, `pool_pre_ping=True`, and run Alembic and dumps on the direct URL.

Verdict: **Neon** at every stage: Launch before the first real students (the 6-hour window and the egress suspension are not acceptable with real users), Scale when paying users or a contract need the 99.95 % SLA, an IP allow-list or 30-day restore. RDS/Aurora only if a school or government contract demands a hyperscaler. Never self-managed before S3, and then only for a strong reason.

### 3.4 Files and CDN

| | Cloudflare R2 (now) | Bunny Storage + CDN | S3 + CloudFront | Backblaze B2 |
|---|---|---|---|---|
| Storage | 10 GB free, then $0.015/GB-month [42] | $0.01–0.02/GB per region [46] | ≈$0.0245/GB (UNVERIFIED) | $6.95/TB-month, 10 GB free [45] |
| Egress | **free** | $0.01/GB EU, $0.03 Asia; $1/month minimum | Free tier 1 TB + 10 M requests, then $0.085/GB EU [47] | free up to 3× storage, free via Cloudflare |
| PoP near KG | **Bishkek** [24] | Almaty, Istanbul (not Bishkek) | UNVERIFIED | via a CDN |
| Our use | images (WebP, SHA-256 keys, immutable), PDFs in a private bucket | – | – | **backup target** (different vendor) |
| Cost per stage | $0 through S2 (10 GB holds thousands of exams); S3 ≈$1–5 unless video | – | – | $0 at our size |

The one must-do before the first big exam: **a custom image domain on our own Cloudflare zone** (`img.<domain>`) with "cache everything". r2.dev is rate-limited and uncached [43]; with a cached custom domain the 96,000 image reads of a 6,000-student sitting are served by Cloudflare's cache instead of counting against the 10 M Class B reads. R2 has no object versioning; bucket locks exist (irreversible retention, an owner decision) [44]. Video lessons must not go to R2 (use YouTube unlisted, Cloudflare Stream or Bunny Stream; not priced here).

### 3.5 Email

| Provider | Free | Paid entry | Notes |
|---|---|---|---|
| **Brevo** (now) | **300/day** (≈9,000/month; third-party summaries, Brevo's page did not render: UNVERIFIED) [48] | Starter ≈$9/month for 5,000 (UNVERIFIED) | enough for sign-up codes at S1; **a 6,000-student roster invitation day cannot be sent** |
| Resend | 3,000/month, 100/day [49] | Pro $20 = 50,000 | simplest API; already supported by `EMAIL_PROVIDER` |
| Amazon SES | $200 credits for new accounts | $0.10 per 1,000 [50] | cheapest at volume; AWS account and sandbox exit needed |
| Postmark | 100/month | $15 for 10,000 [51] | best transactional reputation; separate message streams |

Deliverability: Gmail requires SPF or DKIM, valid reverse DNS, TLS and a spam rate under 0.3 %; senders over 5,000/day to Gmail need SPF **and** DKIM **and** DMARC with aligned From [52]; enforcement tightened in November 2025 [52]. Mail.ru and Yandex (common in Kyrgyzstan) have postmaster tools; register after launch (UNVERIFIED thresholds). All of it needs **our own sending domain** (`runbooks/EMAIL_DOMAIN.md`), so email quality is tied to buying the domain. Use a subdomain for transactional mail so marketing can never hurt sign-in codes. Trigger to pay: any day over 250 sends or the first bulk roster import.

### 3.6 Domain and DNS

- **.kg**: registry AsiaInfo under ICANN, registrar portal cctld.kg; second-level name **2,612.88 som first year, 2,351.82 som/year renewal** (≈$30 / $27 at ≈87 som per USD, rate UNVERIFIED); registrant needs a personal ID on cctld.kg; at least 2 name servers in different networks (Cloudflare satisfies this); **not renewed within 30 days of expiry = cancelled** [58]. **Cloudflare Registrar does not sell .kg** [59]; buy at cctld.kg, then point the name servers at Cloudflare Free (full setup works with any registrar).
- **Cloudflare plans** [53][54][55][57]: Free $0 (unmetered DDoS, Free managed WAF ruleset, **1 rate-limit rule, IP only, 10 s window**, 70 rules, no health checks); Pro $20/month annual or $25 monthly (Cloudflare managed ruleset + OWASP, 2 rate-limit rules up to 1 min / 1 h, 10 health checks, 225 rules); Business $200–250 (100 % uptime SLA, 5 rate rules with **NAT support**, 50 health checks); Waiting Room is Business and above [56].
- **Shared-IP caution for Kyrgyzstan**: schools and mobile carriers put many students behind one public IP (carrier-grade NAT; UNVERIFIED but likely). Edge IP-only limits (Cloudflare Free/Pro, Vercel) can block a whole classroom on exam day. Keep edge limits generous (floods only) and the real limits in the app per account and per attempt (which is what `core/ratelimit.py` does).
- Route 53: $0.50 per zone, no WAF or CDN; no advantage for us. A second `.com`/`.app` at Cloudflare Registrar (at cost; price UNVERIFIED) is a cheap hedge against a `.kg` registry or ISP incident (the 2021 Aknet case [105]).
- Stage cost: S0–S2 Cloudflare Free + domain ≈$2.5/month; S2–S3 Cloudflare Pro $20–25 when managed rulesets and health checks are wanted; Business only if a contract demands an SLA.

### 3.7 Monitoring, error tracking, uptime, logs

| Tool | Free | Paid | Fit |
|---|---|---|---|
| **Sentry** | Developer: 1 user, 5k errors, 1 uptime monitor, 30-day lookback; **EU data region (Frankfurt) chosen at org creation, irreversible** [60] | Team $26/month annual (unlimited users, 50k errors, 90 days) | already wired (`SENTRY_DSN`), scrubber drops request data and user block (`core/sentry.py`); choose EU for minors' data (owner) |
| UptimeRobot | 50 monitors, 5-min interval, "personal and commercial", 1 status page [62] | Solo $9–10 (60 s) | the independent pinger we lack |
| Better Stack | 10 monitors, heartbeats, status page, 3 GB logs for 3 days [61] | $29–34/month | status page for exam days; log drain |
| Grafana Cloud | 10k series, 50 GB logs, 14-day retention, 3 users [63] | Pro $19 + usage | S3: pool saturation, autosave p95, DB connections |
| Cloudflare Health Checks | none on Free [57] | Pro 10 | with a proxied zone |
| GitHub cron (now) | free on a public repo [64] | – | best-effort; disabled after 60 idle days [65] |

Our request logs are already JSON with `request_id`, route and timing, without emails, IPs or answers (`runbooks/INCIDENT.md`); `Server-Timing` is on every response. Instrument once with OpenTelemetry so Sentry, Grafana or Better Stack are interchangeable (low lock-in).

### 3.8 Backups

| Layer | Now | Option | Cost | Restore |
|---|---|---|---|---|
| Neon built-in | Free: 6 h window, 1 GB change cap, 1 manual snapshot; manual backup branches before deploys (7–9 of 10 slots) [30] | Launch 7 days / Scale 30 days, $0.20/GB-month of history; scheduled snapshots $0.09/GB-month | S1 under $1/month for a 1–2 GB DB | minutes (branch from a timestamp) |
| Independent logical dump | **none** | nightly or weekly `pg_dump -Fc` from GitHub Actions, **encrypted before upload** (the repo and its logs are public), to **Backblaze B2** (different vendor and account) [45] | $0 at our size | `pg_restore` into a new Neon branch or local PG 18; `scripts/restore_drill.py` checks it |
| R2 objects | **not backed up**, no versioning | nightly `rclone copy` to B2 (content-addressed keys are append-only) or an R2 bucket lock (irreversible; owner) [44] | $0 under 10 GB | `rclone copy` back |
| Env and secrets | Render env only | the owner keeps an offline encrypted copy (password manager) | $0 | manual |

Caveat on Neon Free: a daily dump of a few hundred MB could exhaust the 5 GB egress and **suspend production** [30]. At today's 42 MB a weekly dump is safe; go daily after Launch. Practice: 3-2-1 (provider PITR + an independent encrypted copy on another vendor + a monthly restore drill written into `runbooks/RESTORE_DRILL.md`). The one drill we did restored to a laptop; **switching production to a Neon branch has never been rehearsed** (`RESTORE_DRILL.md`).

### 3.9 Payments for Kyrgyzstan

Facts [85][86][87][88][89][90][91]:

- **Stripe is not available** to Kyrgyz businesses [85]. **Google Play billing is not available**: Kyrgyzstan supports developer registration but not merchant registration [72], and Play's payments policy requires Play billing for education subscriptions and forbids steering to other payment methods inside the app [73]. **Paddle** does not list KG as unsupported (5 % + $0.50; products under $10 need bespoke pricing; cards only, no local wallets): useful for diaspora buyers later, not for students in Bishkek [86].
- Local providers (every one requires a registered ИП or ОсОО; an individual cannot accept business payments):

| Provider | Accepts | Fee (public) | Integration | Notes |
|---|---|---|---|---|
| **Finik** (Quickpay; NBKR "significant payment system"; Visa payment facilitator) | QR from any KG banking app (ELQR), payment links, Visa | QR **2 %**, Visa from 4 %; no monthly fee | SDK/API key, about one working day; KKM receipts | ИП can open online; KGS only; max 1 M som per payment; no recurring found [87] |
| **Freedom Pay KG** (ex-PayBox) | Visa/MC/Elcart, MegaPay, Balance, O!Dengi, MBANK, Optima24, ELQR, Apple/Google Pay | not published ("2–3 %" press, UNVERIFIED) | Merchant API with **MD5 signature** (weak; verify webhooks plus a server-side status poll); test mode; saved cards, "regular payments" | the broadest coverage and the only one found with card-on-file [88] |
| **GoPay** (with Bakai Bank) | QR, payment links from 20+ bank apps | from 1 % | REST + webhooks; automatic fiscal receipts | cards not mentioned [89] |
| **MBANK MKassa**, **O!Dengi**, **ELSOM**, bank acquiring (Optima, Bakai, KICB, Demir…) | QR, cards with 3-D Secure | 1.5–2.8 % + monthly fees (blog estimates, UNVERIFIED) | bank gateway, 4–8 weeks | MBANK is the most used consumer app in KG [90][91] |

- **Recurring billing reality**: QR and wallet payments are one-off push payments; there is no auto-renew. Card-on-file exists only through card acquiring with tokenisation (Freedom Pay). So the realistic model is **prepaid passes** (1 month, 3 months, "until ORT 2027") with reminders to renew by QR, and optional card auto-renew later. This also fits the Digital Code: **consumers may cancel a digital service at any time and get a pro-rata refund** (Art. 116(4)), and price or term changes need **one month's notice** (Art. 114) [67]. Do not sell "no refund" passes.
- Implementation must-haves: server-side order creation; webhook signature check plus a status poll; idempotency keys; entitlement only after a confirmed payment; a ledger and a reconciliation report against payouts; refunds; fiscal receipts through the provider; a dedicated business bank account (needed for the e-commerce tax regime, see 4.3); no card data on our servers (hosted page).
- **Owner decisions**: ИП or ОсОО; tax regime (2 % e-commerce tax, single tax from 3 %, general regime, or High Technology Park residency: all UNVERIFIED for online exam prep; accountant); which provider contract; whether minors may pay themselves (Civil Code capacity; lawyer).

### 3.10 CI/CD and environments

- GitHub Actions is free and unmetered on a public repo (standard runners) [64]; if the repo ever goes private, the full suite twice per push would eat the 2,000 free minutes quickly (UNVERIFIED per-run minutes).
- Risk: **scheduled workflows are disabled after 60 days without repository activity** [65] (confirmed on GitHub's page). Our uptime monitor and daily maintenance both run on schedules. Mitigation: an external pinger, and a Render cron job or an in-app scheduler once Render is paid.
- Gaps: deploys go straight from `main`; no staging environment; Render "auto-deploy after CI checks pass" is UNVERIFIED (check the dashboard). Every option gives a cheap staging: Render preview environments (full-stack on Pro), a Vercel preview or custom environment, a **Neon branch per staging** with synthetic data (never real minors' data).

---

## 4. Security

This chapter is written for a public repository: it names gaps and fixes, not bypass steps, and no secret names with values.

### 4.1 Threat model for our case

| Asset or threat | Who and why | What we have | What is missing (ranked in 4.5) |
|---|---|---|---|
| **Minors' personal data** (names, emails, scores, parents' links) | curiosity, resale, extortion; a breach becomes public in the regulator's incident register [68] | DB-side permissions on every request, no role in the JWT, audit log, logs without PII, Sentry scrubber, privacy requests and deletion (Phase 11) | staging with no real data; independent encrypted backups; Sentry EU region; consent texts aligned to the Digital Code; 72 h regulator notice in the incident runbook |
| **Paid access** (passes, activation codes) | sharing one paid account among many; forged codes; refund abuse | codes hashed and sealed with the server key; `access` module with rate limits | payment webhooks with signature **and** status poll; ledger and reconciliation; concurrent-session limit per paid account; pro-rata refund rule (law) |
| **Exam integrity** (leaked questions, cheating, timer games) | students, tutors selling answers | immutable snapshots; answer keys never sent to the browser (payload built from student views only); server-side deadlines and grace; forward-only sections; shuffled choices; one active attempt; grading idempotent | item pools and randomised order where the exam format allows (ORT itself is fixed); delayed result release for a synchronized mock day; watermark with user id on images; anomaly flags for review (speed, identical sequences, many accounts from one device). **Not** worth it: screenshot prevention, lockdown browsers, webcam or AI proctoring (biometrics would trigger an impact assessment under Art. 82 [67], cost money and lose parents' trust) |
| **Account takeover** | credential stuffing with leaked passwords; phishing of a teacher or admin who can see hundreds of minors | bcrypt (configurable rounds), per-email+IP and per-email failure limits, generic errors, email codes rate-limited, **two-step login for platform admins**, session ending for a stolen admin session, Google sign-in (OIDC), key rotation with a previous key | MFA for org admins and teachers (OWASP's layered order: MFA first, then graduated per-IP limits, CAPTCHA only on suspicious attempts [83]); breached-password check (HIBP range API, free, k-anonymity [84]); password length per NIST 63B-4 (15+ without MFA, 8+ with; no forced rotation) [81]; IP limits enforced once the proxy chain is verified (`IP_CHAIN.md`) |
| **Exam-day DDoS and bots** | attention around national exam dates (Kundelik, Uzbek portals [104]); competitors; bored students | Render's L3/L4 shield [15]; Vercel's automatic DDoS mitigation [2]; in-app rate limits (DB-backed, per account); admission gate (overload degrades to 503s, not a crash) | **no WAF or L7 rate limit in front of the API**; needs our own domain on Cloudflare with the API proxied; an "Attack Mode" switch documented; bot check on sign-up; feature flags to shed non-essential routes |
| **Leaked secrets** | a key in a commit, a log, a chat, a screenshot; a stolen laptop | the app refuses to start on the public default key in production (`IP_CHAIN.md`); rotation runbook with `SECRET_KEY_PREVIOUS`; secrets only in Render/Vercel env; GitHub secret scanning is on by default for public repos [66] | push protection and CodeQL enabled (state not visible from the repo); a one-time **full-history secret scan** (gitleaks/trufflehog), rotating anything found; hardware keys or passkeys on every provider account; scoped, expiring tokens for CI and the agent; separate keys per environment |
| **Public repository** | attackers read authz, rate-limit and seed code | this is fine as long as there is no secret and no security by obscurity; the code already assumes that | pin GitHub Actions by commit SHA; least-privilege `permissions:`; branch protection on `main`; a `SECURITY.md` with a contact; Dependabot and dependency review in CI (free on public repos [66]) |
| **Supply chain** (OWASP Top 10:2025 A03 [79]) | a malicious npm or pip release | lean dependency set (audit §1.5) | Dependabot; dependency review; lockfile discipline |
| **Availability** | Render sleep/restart; Neon suspension on egress; GitHub cron disable; a single founder | runbooks for incident, rollback, restore, maintenance, service worker | paid Render; Neon Launch; external uptime monitor; staging; a written exam-day runbook with a fallback (extend the window, reopen attempts, status message in three languages) |

### 4.2 What a professional setup needs, per stage

| Control | S0 now | S1 launch | S2 paying users | S3 schools |
|---|---|---|---|---|
| WAF and rate limiting | in-app only | Cloudflare Free in front of `api.<domain>` and `img.<domain>`; 1 edge rule for floods; in-app per-account limits; IP limits enforced after the chain check | Cloudflare Pro (managed + OWASP rulesets, 2 rate rules, health checks) [55][54] | Pro, or Business if an SLA is contractual; NAT-aware rate rules |
| Secrets | Render/Vercel env; owner password manager | + hardware key or passkey on GitHub, Vercel, Render, Neon, Cloudflare, registrar, email, Google Cloud; registrar lock; full-history scan; rotation schedule | + separate keys per environment (staging/prod); Doppler or Infisical free tier if more than one person [109] | + quarterly rotation; break-glass procedure |
| Backups with tested restores | Neon 6 h + manual branches; one drill done | Neon Launch 7 days; weekly encrypted dump to B2; R2 → B2 copy; **monthly drill** written down | daily dumps, 30-day retention; rehearse a production switch to a branch once | Neon Scale 30 days; quarterly full DR drill |
| Audit logs | app audit log (exists) | + admin MFA events (exist) | + log retention 30 days off-platform (Better Stack/Grafana) | + Render audit logs (Pro) |
| Dependency and vulnerability scanning | unknown | Dependabot, CodeQL, dependency review, secret push protection (all free) [66] | same + a yearly outside review (price UNVERIFIED; typically thousands of USD; owner) | annual outside pentest (Canvas publishes theirs [92]) |
| Incident response | `INCIDENT.md` (5 minutes, exam, after) | + **72-hour regulator notification** step and templates in ky/ru/en; vendor contacts; the 48-hour processor clause in vendor DPAs [67] | + status page; on-call phone alerts | + tabletop exercise before each exam season |
| Staging separate from production | none | Render preview env + Vercel preview + a Neon branch with **synthetic** data; deploy only after CI | same, promoted by a button | same |
| Least privilege | one owner identity everywhere | agent/CI tokens scoped and expiring; Neon roles: app (DML), migrations (DDL), read-only analytics; R2 bucket-scoped tokens | same | + named people and roles when a team exists |
| Standards to aim at | – | OWASP ASVS 5.0 L1 across the app, L2 for auth, session, access control and payments [78]; CIS Controls v8.1 IG1, about 30 of the 56 safeguards apply to a one-founder SaaS [80] | same | same + SOC 2-style evidence if a contract asks |

### 4.3 Kyrgyz law (a lawyer must confirm every line)

- **The 2008 personal-data law (No. 58) lost force on 2026-02-05.** Personal data is now governed by **Chapter 11 of the Digital Code** (Law No. 178 of 2025-07-31), Articles 77–91 [67][68][70][71]. Older blog posts and the DLA Piper country page describe the old law; treat them as outdated.
- **Regulator**: the State Agency for Personal Data Protection under the Cabinet of Ministers (dpa.gov.kg), set up by Resolution No. 46 of 2026-01-30; it inspects, fines and keeps a **public register of incidents** [68][69]. **No registration of data holders is needed now** (the old registry is archived; a new "registry of record owners" is being prepared, mandatory status UNVERIFIED) [68][69].
- **Children (Art. 81)** [67]: processing a child's data outside listed public-interest cases needs **consent of the legal representative**; **children aged 14 and over may consent themselves within their civil capacity**; information must be in language a child understands. "Contract" and "legitimate interest" are not listed bases for children, so for every user under 18 we rely on consent: the student's own at 14–17, a parent's under 14. Our Phase 11 flow (age 14, parent/observer consent) matches this shape; the texts must be re-read against the Code (they still say "Draft: awaiting legal review", `LAUNCH_CHECKLIST.md`). Whether a 14–17-year-old can **pay** alone is a Civil Code capacity question: UNVERIFIED; safer that a parent or adult pays or confirms.
- **Consent (Art. 79)** [67]: voluntary, specific, informed, separate from other requests, in plain language; **void** if bundled or in complex language; withdrawal as easy as giving. Bundled consent and excessive collection are offences (5,000 som individuals / 10,000 som legal entities, ICNL [68]).
- **Cross-border transfer (Art. 89)** [67]: **no general data-localisation requirement found.** Transfers to "adequate" countries cannot be restricted; **the regulator's list currently marks only Kyrgyzstan as compliant, every other country "unknown"** (dpa.gov.kg, 2026-11-14) [69]. So Vercel, Render, Neon, Cloudflare, Brevo and Google sign-in all need a non-adequacy basis: the clean design is **one separate, plain-language consent step covering processing and hosting abroad**, given by the student (14+) or the parent (under 14), recorded with date and version [68]. Processors need a written contract (Art. 86); the vendors' DPAs are the practical form (Render has a GDPR DPA on all plans [10]).
- **Incidents (Art. 63)** [67]: notify the regulator **within 72 hours of discovery** of any incident affecting digital resilience or users' rights; processors must notify us within **48 hours**; the notice lists description, number of users, contact, consequences, measures. Not notifying is an offence since 2025-11-23 (secondary source). Notifying affected users directly is not found in the text: do it anyway.
- **Digital services and consumers (Arts. 114–116)** [67]: a user agreement is mandatory; keep records for the term **plus 3 years**; changes need **one month's notice** and a refund right; the provider must identify itself (legal name, contacts); **cancellation at any time with a pro-rata refund** (Art. 116(4)); free basic support; deletion of records after leaving.
- **Fines** (Code of Offences, ICNL) [68]: processing without a basis or storing without protection 65,000 som (≈$750), cross-border breach 65,000 som, refusing a subject's data 25,000 som. Small in money; **the public incident register and parents' trust are the real cost**.
- **Impact assessment (Art. 82)**: mandatory for automated decisions with significant effect and systematic monitoring. Ordinary scoring is probably outside; **AI chat, adaptive recommendations and any webcam proctoring could trigger it** [67][68].
- **Children's information safety (Law No. 176 of 2023-08-09)**: bans harmful content for children; relevant only with user-generated content or AI chat (moderate or keep off for minors) [secondary, UNVERIFIED in the official text].
- **Business and tax (accountant must confirm)**: ИП registers through the tax service; ОсОО through the Ministry of Justice (new procedure since April 2026). E-commerce tax 2 % quarterly through a **dedicated bank account**; single tax from 3 % after the August 2026 amendments; High Technology Park residency exempts profit tax, VAT and sales tax (eligibility of online education UNVERIFIED). Fiscal receipts (KKM) depend on regime and method; Finik and GoPay advertise built-in receipts [90]. Collecting money for tutors or schools later may need a payment-organisation licence from the National Bank (UNVERIFIED): use the provider's split or payout product rather than holding funds.

**Questions for the lawyer** (verbatim from the research note, section F): (1) can 14–17-year-olds buy a paid plan alone; (2) is "contract" usable for minors' data or is consent the only basis; (3) is consent sufficient for US/EU hosting while the adequacy list shows "unknown", or are contractual clauses also expected; (4) will the new registry of record owners be mandatory; (5) which tax regime fits online exam prep and is a KKM receipt needed per online payment; (6) is a licence needed to collect payments for tutors or schools; (7) is Government Resolution 760 (2017) on security levels still in force and which level applies.

### 4.4 App stores and children's data

- **Google Play**: Kyrgyzstan **can register as a developer but not as a merchant** [72] (confirmed on Google's page: "Kyrgyzstan ✔ ✘"). Play billing is required for education subscriptions and steering to outside payment is forbidden [73]. So a Play app from a Kyrgyz entity must be **free, with no purchase UI and no "buy on our website" links**; web buyers log in and use it. Whether reviewers accept zero mention of pricing is UNVERIFIED (common practice). Alternatives: a foreign entity in a merchant country (Kazakhstan is ✔; a big owner decision), or **stay an installable web app (PWA), where web payments are unrestricted**: this is what we have today.
- Families policy applies when any target audience includes children: no thin webview of a website; disclose all data collected from children including through SDKs; no advertising ID; only approved SDKs; neutral age screen for mixed audiences [74]. Declare 13–15, 16–17 and 18+ honestly; do not market to under-13s. The data-safety form must match the privacy policy; **in-app and web account deletion** are mandatory (enforced since 2024-05-31) [75]; new personal developer accounts must run a closed test with 12 testers for 14 days [76].
- **Apple**: do not use the Kids Category for a 14–17 exam-prep app; subscriptions must use in-app purchase (3.1.1); repackaged websites are rejected (4.2); account deletion required (5.1.1(v)) [77]. Apple payouts to Kyrgyzstan: UNVERIFIED.
- Reference standards, not binding here: COPPA (under 13, verifiable parental consent, 2025 amendments) and GDPR Art. 8 (digital age of consent 13–16). Kyrgyzstan's 14 sits inside that range.

### 4.5 Our gaps, ranked

1. **Consent and legal texts against the Digital Code** (Arts. 79, 81, 89): one separate plain-language consent (ky/ru/en) covering processing and hosting abroad; self-consent at 14+, parent under 14; versioned records; withdrawal; privacy policy, user agreement and public offer rewritten from Law 58 to the Code. *Blocks launch; lawyer.*
2. **No firewall in front of the API and IP rate limits in log-only mode.** Needs the domain on Cloudflare, the API and image hosts proxied, the IP-chain check (`IP_CHAIN.md`) and then enforcement. *Before the first exam with more than a few hundred students.*
3. **Backups on one vendor with a 6-hour window, R2 not backed up, no production-switch rehearsal.** Neon Launch, encrypted off-vendor dumps, R2 copy, monthly drill. *Before real students.*
4. **No staging environment; deploys straight from `main`.** Render preview + Vercel preview + Neon branch with synthetic data. *S1.*
5. **Incident runbook lacks the 72-hour regulator step**, templates and a vendor contact sheet. *S1, one afternoon.*
6. **MFA only for platform admins.** Extend to org admins and teachers (they see many minors); hardware keys or passkeys on all cloud accounts; registrar lock. *S1.*
7. **GitHub security switches not confirmed**: push protection, CodeQL, Dependabot, dependency review, branch protection, Actions pinned by SHA, full-history secret scan. *S0, free.*
8. **Email sent inside requests and from a personal address without DMARC.** Background sending, own domain, SPF/DKIM/DMARC. *S1 with the domain.*
9. **Exam integrity extras** for a synchronized mock day: delayed results, watermark, anomaly flags, per-user limits on content fetches. Honest positioning: practice, not proctored. *S2.*
10. **Payments** (entity, provider, prepaid passes, pro-rata refunds, receipts) and the **Play Store plan** (free consumption-only app or PWA only; account deletion paths). *S2; owner decisions first.*
11. **Named person responsible for personal data** and a record of processing operations (Art. 88; mandatory above 10 employees, good practice now). *S1, a document.*

---

## 5. Scalability

### 5.1 What limits growth today

| Limit | Evidence | Breaks at |
|---|---|---|
| **One Render Free instance, 0.1 CPU, sleeps** | audit §3.5, §10.1; `PHASE_3_LOADTEST.md` §7 | ≈30–45 light requests/s; ≈150–250 students in steady autosave; 1.2 logins/s; 60 s cold start |
| **Python CPU per request (GIL)** | autosave 3.2 ms, start 21 ms, submit 10.6 ms, login 83 ms per request on an M1 core (`PHASE_3_LOADTEST.md` §4); per-request cost doubles at saturation | 6,000 students need ≈1.1 core steady, +0.4 at start, ≈2.1 cores for the deadline minute on M1 terms; a Render CPU is ≈0.5–0.7 of that core; size for ≤60 % CPU |
| **Deadline submit burst** | 6,000 × 10.6 ms = 64 CPU-s in one minute; submits queued past grace drop late body answers (finding B2) | one core-minute per 6,000 submits |
| **Login burst** | bcrypt 83 ms; 6,000 logins = 500 core-seconds | a national start without staggering |
| **Pre-ASGI queueing hidden from app metrics** | client latency 10–20 s above server p95 at saturation (`PHASE_3_LOADTEST.md` §5, §8) | any saturated instance; watch the proxy's times, not only `Server-Timing` |
| **Database connections** | up to ≈17 per worker; direct endpoint 112 at 0.25 CU; pooled 10,000 [31] | only if someone uses the direct URL for the app |
| **Database storage** | ≈0.2 GB per 6,000×150 exam; Free 1 GiB ≈ 4 exams (`DB_STORAGE_REVIEW.md`) | the 4th full exam on Free |
| **Neon egress** | Free 5 GB/month then compute suspended [30] | a few large dumps or exports |
| **Neon compute** | DB CPU ≈0.05 CU at 6,000 (estimate); DB is "not what was waiting" in stalls (`PHASE_11_LOADTEST.md`) | not a limit; connections and storage are |
| **r2.dev image host** | rate-limited, uncached [43]; 96,000 GETs per sitting | the first big sitting |
| **Email** | 300/day [48]; synchronous sends | the first roster invitation day; a sign-up surge |
| **In-process state** | autosave bucket, sweep interval, overview cache (section 1.4) | N instances allow N× the per-user autosave rate; harmless |
| **Sweep lock behind the pooler** | section 1.4 | silent degradation; lazy finalization covers it |
| **Uptime cron as keep-awake** | `uptime.yml`; disabled after 60 idle days [65] | any quiet period |
| **Statement counts on the student home** | 21 + 18 + 15 = 54 statements for one cold home (audit §10.1) | only under load (≈3 ms each on Render) |

### 5.2 Standard fixes and when they apply

| Fix | Solves | Cost | When |
|---|---|---|---|
| **Paid always-on instance; bigger size for exam windows** (Render bills per second; a plan switch is a redeploy of a few minutes) | sleep, 0.1 CPU | $7 Starter; $25 Standard; $85 Pro (2 CPU); $175 Pro Plus (4 CPU) per month-rate, cents per hour [11] | S1 now; windows from the first exam with more than ≈800 students |
| **Horizontal scaling** (2–4 Standard instances behind Render's balancer; autoscaling on CPU) | one instance's CPU ceiling; the deadline burst | Render Pro $25 + instances | S2 |
| **Connection pooling** (Neon's pooled endpoint; small per-worker pools) | connection exhaustion (Edmodo's failure) | $0 | already; keep |
| **CDN for content** (section payloads and images from `img.<domain>` with immutable caching) | API CPU and R2 reads at the start | $0 with the domain | S1 |
| **Spread the start** (wide windows for practice, staggered cohorts for a mock day, countdown page 15–30 min early, pre-issued tokens) | login and start bursts | $0 (policy) | S1 |
| **Queue for background work** (Postgres-backed outbox: emails, exports, statistics refresh, grading jobs) | synchronous work in requests | $0 (a table + the maintenance route or a Render cron) | S1–S2 |
| **Caching** (browser SWR exists; CDN for immutable content; a shared cache only with several instances) | repeat reads | $0 now; Redis later ≈$10–30 | S2+ only if measured |
| **Read replicas** (Neon, same storage, created in seconds [32]) | statistics and analytics competing with exams | billed compute ≈$30–160 | S2–S3, only after caching; exam traffic is write-heavy |
| **Degraded mode** (feature flags to shed statistics, analytics, catalog, recommendations) | keeping login/start/autosave/submit alive under stress | small code | S1 |
| **Pre-scale on a calendar and ask providers about limits** | quotas (Uchi.ru), cold caches | $0 plus a few dollars per exam | before each big exam |
| **Load test on paid Frankfurt infrastructure** | the unknown real limit | a few dollars: Pro Plus for 3 h ≈$0.70, Neon Launch compute ≈$1–3, a generator VM ≈€1 | S1, first |

### 5.3 Code changes to make now so growth stays cheap

Each is small, keeps behaviour, and removes a cliff later.

1. **Sweep lock** (`attempts/sweep.py`): replace the session-level lock with `pg_try_advisory_xact_lock` held inside one open transaction for the whole sweep (or a direct-URL engine for the sweep only); add a Postgres test that runs two sweeps through a transaction-mode pooler. *Half a day.* Solves a silent skip behind Neon's pooler.
2. **Email off the request path** (`auth.py:127`, `:464`): `BackgroundTasks` after commit, or an outbox table drained by the maintenance route with retries. *Half a day.* Solves held threads and connections during a sign-up surge, and provider outages becoming sign-up failures.
3. **Dockerfile + `render.yaml`** (no behaviour change). *Two hours.* Solves portability: moving to Fly, Cloud Run or a VPS becomes a day, not a week.
4. **Offline answer buffer and idempotent late submit** in the player: queue answers locally, flush in batches, retry, and let a submit after the deadline report `saved`/`rejected` positions (finding B2). *2–3 days.* Solves the Kyrgyz last-mile problem and the deadline-burst data drop.
5. **Content from the CDN**: once `img.<domain>` exists, serve the per-section student payload (already immutable, gzipped, ETagged) as a cacheable file keyed by version and language; the API then only serves start, autosave and submit on exam day. *1–2 days after the domain.* Solves start-burst CPU and r2.dev throttling.
6. **Statement budget on hot student routes** (bootstrap/home/exam-prep: 54 statements) with the `IN (...)` folding already used by the staff outline. *1 day.* Solves per-request DB time under load.
7. **Pooler-safe statement timeout** (`SET LOCAL statement_timeout` per transaction) and `DB_POOL_TIMEOUT` 2–3 s. *Two hours.* Solves one slow query holding a worker for minutes.
8. **Feature flags for degraded mode** (`platform_settings` already exists): shed statistics, analytics, catalog, recommendations. *1 day.* Solves "degrade, don't die".
9. **Services panel keys** (read-only Neon, Render, Vercel, Cloudflare tokens; owner) so `/platform/infra` shows real usage and capacity. *Owner, an hour.* Solves flying blind on limits.
10. **Independent encrypted backup job** (weekly dump to B2 from Actions with the secret only in GitHub Secrets; R2 `rclone` copy) and a monthly drill entry. *Half a day.* Solves single-vendor backups.
11. **Exam-day runbook**: change freeze, pre-scale checklist, Attack Mode switch, status message in three languages, extend-window and reopen-attempt steps, who decides. *Half a day, a document.*
12. **Not now**: Redis, microservices, read replicas, Kubernetes, a message broker, multi-region, a rewrite in Go. None fixes a measured limit.

---

## 6. Stages, not one jump

Monthly costs are list prices on 2026-11-14 excluding VAT; "est." is our arithmetic. Capacity figures come from our laptop tests extrapolated to Render CPU (`PHASE_3_LOADTEST.md` §7) and must be replaced by the Frankfurt load test.

### Stage 0: now, testing, $0

| | |
|---|---|
| Setup | Vercel Hobby (fra1), Render Free (Frankfurt), Neon Free (0.25–2 CU, Frankfurt), R2 free on r2.dev, Brevo free from a personal address, GitHub Actions for CI, uptime and maintenance, Sentry off |
| Handles | the owner, QA accounts, a handful of students; ≈150–250 students in steady autosave at best; a 60 s wake-up after 15 idle minutes |
| Security level | code controls good; no firewall, no staging, backups 6 h on one vendor, IP limits log-only |
| Migrations | none |
| Do now anyway ($0) | GitHub security switches (4.5 item 7); full-history secret scan; the code changes 1, 2, 3, 7 of 5.3; the 72 h step in `INCIDENT.md`; external uptime monitor (UptimeRobot free); Sentry Developer in the EU region (owner creates the org) |
| **Move up when** | the first real students are invited, or any exam is announced with a date, or money is about to be charged |

### Stage 1: launch, hundreds of students, about $30/month

| | |
|---|---|
| Setup | **Domain** `.kg` at cctld.kg (≈2,600 som/year [58]) with DNS on **Cloudflare Free**: site DNS-only on Vercel, `api.<domain>` and `img.<domain>` proxied (WAF free ruleset, 1 flood rule) · **Render Starter $7** (no sleep; switch to Standard/Pro/Pro Plus per second for exam windows) · **Vercel Pro $20** (commercial use allowed) **or** Cloudflare Workers $5 after a 1–2 day move · **Neon Free** until the first paying student, with a **weekly encrypted dump to Backblaze B2** ($0) and an R2 copy · Brevo free on `noreply.<domain>` with SPF/DKIM/DMARC · Sentry Developer (EU) · UptimeRobot free · GitHub Actions |
| Cost | $7 + $20 + ≈$2.5 domain = **≈$29.5/month** (or ≈$14.5 with Cloudflare Workers). Exam windows: cents to a dollar each |
| Handles | hundreds of students daily; an exam of **≈800–1,100 students** on Starter, **≈1,600–2,300** on Standard, **≈3,200–4,600** on Pro (2 CPU), **6,000 with headroom on Pro Plus (4 CPU)** per our extrapolation (`PHASE_3_LOADTEST.md` §7); **to be confirmed by the Frankfurt load test, which is the first task of this stage** |
| Security level | WAF and DDoS at the edge for API and images; IP limits enforced after the chain check; staging (Render preview + Vercel preview + Neon branch, synthetic data); hardware keys on all accounts; MFA for teachers and org admins; consent flow aligned to the Code (lawyer); incident runbook with the 72 h step; monthly restore drill |
| Migrations and risk | **Domain switch** (`runbooks/CUSTOM_DOMAIN.md`, 1–2 hours plus DNS waits): students signed in on the old address are signed out once; the PWA must be reinstalled. Low risk, reversible by DNS. **Render plan** change: a redeploy, seconds of overlap, zero downtime [14]. **Vercel Pro**: a billing change. **Cloudflare Workers** (if chosen): 1–2 days, medium-low risk because no Vercel-only features are used; keep Vercel as the rollback for two weeks |
| Code | 5.3 items 4, 5, 6, 8, 10, 11 |
| **Move up when** | the first paid pass is sold (Neon Launch the same week); or a single exam is expected above ≈2,000 students; or Brevo sends pass 250/day; or the first abuse or credential-stuffing incident; or Render bandwidth nears 5 GB/month; or p95 autosave in a real exam passes 500 ms |

### Stage 2: thousands of students, paying users

| | |
|---|---|
| Setup | **Render Pro workspace $25 + 2× Standard ($50) with autoscaling** (or 1× Pro $85), pre-scaled to 3–4 instances for exam windows · **Neon Launch always on, 0.5–4 CU, 7-day restore** ≈$45–80 (Scale ≈$90–170 if the SLA or IP allow-list is needed) · Vercel Pro $20 (or Workers $5–10) · **Cloudflare Pro $20–25** (managed + OWASP rulesets, 2 rate rules, health checks) · **Sentry Team $26** · UptimeRobot Solo $9 or Better Stack $29 (1-minute checks, status page for exam days) · **email paid**: Resend Pro $20 or Brevo paid ≈$9 or SES ≈$1–5 · daily encrypted dumps, 30-day retention · payments: Finik or Freedom Pay contract (fees 1–4 % of sales) |
| Cost | **≈$200–300/month** before payment fees |
| Handles | thousands of daily users; **3,000–6,000 in one exam window with pre-scaling** (to be proven); roster invitations of thousands per day; results and announcement spikes (Testbook's lesson) |
| Security level | ASVS L1 app-wide, L2 on auth, access and payments [78]; staging for every deploy; secrets per environment; yearly outside review; 30-day logs off-platform; Neon roles split; payment webhooks signed and polled; concurrent-session limit on paid accounts |
| Migrations and risk | Neon Free → Launch: a plan change, no data move, no downtime. Single → several instances: the per-process autosave bucket becomes N× (acceptable), sweep runs N× (harmless after the lock fix). Cloudflare Pro: a plan change. Payments: new code and a contract; test mode first |
| Code | Postgres-backed outbox for emails, exports and statistics refresh; payment ledger and reconciliation; item pools, delayed results and anomaly flags for mock days; feature flags in use |
| **Move up when** | a school or government asks for an SLA, a DPA with specific clauses or a hyperscaler; or more than one incident per quarter is caused by the database; or several exams run in the same window; or Neon storage passes 50 % of the plan's comfort; or revenue justifies $1,000/month |

### Stage 3: tens of thousands, several exams (ORT, НЦТ, olympiads), schools

| | |
|---|---|
| Setup | Render Pro + **4–10 Standard/2c-4g instances autoscaled** $200–900 (or Cloud Run in Frankfurt/Finland for rare huge peaks, $200–700 est.) · **Neon Scale**: 2 CU primary always on + 1 read replica for statistics/analytics + 20–50 GB + 30-day restore ≈ **$500–600**, 99.95 % SLA [34] · Vercel Pro + Flat Rate CDN tier $40–150 or Workers $10–30 · Cloudflare Pro, Business $200–250 only if an SLA is contractual · Sentry Team/Business $26–89 · Grafana Cloud $19+ for pool saturation and autosave p95 · SES or Postmark $20–50 · annual outside pentest (owner budget) |
| Cost | **≈$900–2,000/month** |
| Handles | tens of thousands daily; several concurrent exam windows with pre-scaling; school rosters; per-exam statistics on a replica |
| Security level | SOC 2-style evidence if contracts ask; quarterly rotation; tabletop exercise per season; NAT-aware edge rate rules |
| Migrations and risk | Neon Launch → Scale: a plan change. Adding a replica: seconds, no copy [32]. Render → Cloud Run (only if chosen): Dockerfile exists from Stage 0, 2–3 days, run both for a week behind DNS. A hyperscaler database only under contract: `pg_dump`/logical replication, a weekend, rehearsed on staging first |
| Code | read-only mode for statistics on the replica; per-exam capacity dashboard; cost per active student tracked monthly (Duolingo's habit [97]) |
| Never here either | self-managed Postgres, Aurora [38] unless a contract forces AWS, Kubernetes, microservices, multi-region, sharding |

---

## 7. Recommendation

### 7.1 Three complete end states

| | **A. Managed PaaS (stay the course)** | **B. Cloudflare-heavy edge** | **C. One hyperscaler (Google Cloud)** |
|---|---|---|---|
| Frontend | Vercel Pro | Cloudflare Workers + OpenNext | Cloud Run (Next.js in Docker) or keep Vercel |
| Backend | Render (Pro workspace, autoscaled Standard instances) | Render (same) | Cloud Run europe-west3/north1, Cloud Armor WAF |
| Database | Neon Launch → Scale | Neon Launch → Scale | Cloud SQL / AlloyDB, or keep Neon |
| Files, CDN, DNS, WAF | Cloudflare Free → Pro (R2, zone, WAF) | Cloudflare (everything on one vendor) | Cloud Storage + Cloud CDN, or keep R2 |
| Email | Brevo → Resend/SES | same | SES or Postmark |
| Monitoring | Sentry EU + UptimeRobot/Better Stack → Grafana | same | Cloud Monitoring + Sentry |
| Payments | Finik or Freedom Pay | same | same |
| S1 / S2 / S3 $/month | ≈$30 / $200–300 / $900–2,000 | ≈$15 / $180–280 / $850–1,900 | ≈$45–60 / $250–400 / $1,000–2,500 est. |
| Latency for KG | Frankfurt API and DB; Vercel edge for static | **Bishkek PoP** for static; Frankfurt API and DB | Frankfurt or Helsinki (63 ms) for everything if Neon moves too (UNVERIFIED gain) |
| Security | Vercel + Cloudflare edge; Render has no WAF of its own | one WAF vendor for site, API and images | Cloud Armor, IAM, Secret Manager, VPC: strongest, most to configure |
| Lock-in | low everywhere (plain Python, plain Postgres, no Vercel-only features) | low–medium (OpenNext adapter) | medium (IAM, registry, Cloud SQL) |
| Move effort from today | 0 code; plan changes and the domain | 1–2 days for the frontend; rest same as A | 4–7 days; a new account, billing, IAM |
| Founder burden | **lowest** | low–medium (adapter upgrades follow Next.js releases) | medium–high |
| Best for | S1–S2 and most of S3 | the same, if the Vercel bill grows or the Bishkek PoP proves worth it | contracts that demand a hyperscaler; very large rare peaks |

### 7.2 The pick

**End state A**, with B's frontend swap as an optional cost cut and C only if a contract demands it.

Reasons: (1) it changes **no code and no vendor** today, only plans and the domain, so there is no migration risk during launch; (2) every piece is already in our runbooks and the agent operates them well; (3) it is the shape that proven small teams run at millions of users (section 2); (4) lock-in stays low, so B or C remain open: the Dockerfile and the absence of Vercel-only features are the insurance; (5) the money follows usage: $30, then $200–300 only when students pay, then $900–2,000 only with schools.

Why not B first: it saves $15/month at S1 and more at S3, but costs 1–2 days now and a different runtime (workerd, not Node) during launch, when the frontend changes weekly. Do it in a quiet month at S2 if the Vercel bill or the Bishkek latency gives a reason. Why not C: the burden is the founder's time, which is the scarcest resource, and nothing in our measurements needs it.

### 7.3 What to do first (order)

1. **Stage 0 hygiene, $0, this week**: GitHub security switches and a full-history secret scan [66]; the sweep lock, background email, Dockerfile and statement-timeout changes (5.3); the 72 h step and templates in `INCIDENT.md` (NIST 800-61r3 as the frame [82]); UptimeRobot; Sentry Developer in the EU region (owner creates the org).
2. **Owner buys the domain and pays Render Starter and Vercel Pro** (or approves the Workers move). Agent runs `CUSTOM_DOMAIN.md` and `EMAIL_DOMAIN.md`; proxies API and images through Cloudflare; runs the IP-chain check and enforces IP limits.
3. **Frankfurt load test** with the existing scripts on Render Pro Plus for a few hours against a Neon branch (a few dollars). Record the real limit per plan size in `PHASE_11_LOADTEST.md`. Until then, promise 3,000.
4. **Lawyer**: consent, user agreement, public offer, cross-border basis, refunds, the seven questions in 4.3. In parallel: encrypted off-vendor backups and the monthly drill; staging; MFA for staff.
5. **Payments** (needs the entity and a contract): prepaid passes, Finik or Freedom Pay in test mode, ledger, refunds, receipts. Neon Launch the week the first pass is sold.
6. **Mock-exam day runbook and rehearsal**: pre-scale, change freeze, staggered cohorts, countdown page, status message, fallback. Run one mock day with real students at a size the load test has proven.

### 7.4 What never to do early

Kubernetes; microservices or a rewrite in another language; self-managed Postgres (Patroni, pgBackRest on a VPS [41]); Aurora or any hyperscaler database without a contract that demands it [38]; Redis before two instances and a measured need; read replicas before caching; a message broker (Kafka, RabbitMQ) for emails; multi-region or a Kyrgyz/Kazakh data centre without a legal requirement; Cloudflare Business/Enterprise or a dedicated email IP; webcam or AI proctoring; a native Android app with purchases (not possible from Kyrgyzstan anyway [72]); Aiven or other managed Postgres migrations for marginal savings [40]; "servers in 10 cities" claims; buying capacity before the load test says what we need.

### 7.5 Decisions only the owner can make

| Decision | Why only the owner | When |
|---|---|---|
| Spend money: Render Starter ($7), Vercel Pro ($20) or the Workers move, later Neon Launch (≈$15–80), Cloudflare Pro, Sentry Team, email tier, Render Pro | money | S1 now; the rest at the triggers |
| Buy the `.kg` domain (cctld.kg needs the owner's personal ID), own the registrar login, set renewal reminders (30-day cancellation cliff [58]); optionally a `.com`/`.app` hedge | contract, identity, money | S1 |
| Register a business (ИП or ОсОО), choose the tax regime, open the dedicated bank account | legal, tax | before any paid pass |
| Sign a payment-provider contract (Finik, Freedom Pay, GoPay or a bank) and decide whether minors may pay themselves | contract, legal | before paid access |
| Hire a Kyrgyz lawyer for the consent flow, user agreement, public offer, cross-border basis, refunds, incident duties; an accountant for tax and receipts | legal | before launch |
| Sentry data region (EU; irreversible) and the Sentry org owner | legal (minors' data), irreversible | S0–S1 |
| Where off-vendor backups live (a Backblaze account holds minors' data; who keeps the encryption key) | legal, custody | S1 |
| R2 bucket lock (irreversible retention) | irreversible | optional |
| Hardware security keys for all provider accounts (≈$25–60 each, two) | money, custody | S1 |
| Publish an Android app at all (free, consumption-only, no purchase links) or stay PWA-only; a foreign entity for Play billing | legal, strategy | S2 |
| Annual outside security review budget | money | S2 |
| Which comparables' policies to adopt: staggered mock-day cohorts, result release timing, honest "practice, not proctored" positioning of the golden certificate | product | S1–S2 |

---

## Glossary

- **Autoscaling**: the host adds or removes server instances automatically when CPU or memory crosses a threshold. On Render it needs the Pro workspace.
- **Cold start**: the delay when a sleeping service or database wakes for the first request (Render Free ≈60 s; Neon ≈0.65 s).
- **CDN / PoP**: a content delivery network keeps copies of static files in many cities (points of presence); Cloudflare has one in Bishkek.
- **CU (compute unit)**: Neon's unit of database power (1 CU ≈ 1 vCPU and 4 GB RAM); billed per hour of use.
- **Connection pooling / PgBouncer / transaction mode**: a proxy that lets thousands of app connections share a few hundred database connections; in transaction mode a database connection is lent only for one transaction, so anything that assumes "the same connection for the whole session" (session advisory locks, `SET`, `LISTEN`) breaks.
- **Advisory lock**: a Postgres lock the application chooses by number; "session-level" lasts until the connection closes, "transaction-level" (`_xact_`) ends with the transaction.
- **DPA**: data processing agreement, the written contract with a vendor that processes personal data for us (Digital Code Art. 86).
- **DDoS**: flooding a site with traffic so real users cannot get through. L3/L4 is network flooding; L7 is application-level (fake logins, heavy requests).
- **WAF**: web application firewall; filters malicious requests (injection, bots, floods) before they reach the server.
- **Rate limiting**: allowing at most N requests per key (IP, account, attempt) per window.
- **CGNAT / shared IP**: a mobile carrier or school puts many devices behind one public address; an IP-only limit then blocks all of them.
- **PITR / restore window**: point-in-time recovery; how far back in time the database can be rewound (Neon Free 6 hours, Launch 7 days, Scale 30 days).
- **Read replica**: a read-only copy of the database that serves reports and analytics so the primary handles writes.
- **Outbox / job queue**: a table of work to do later (send an email, build a report), processed by a background job instead of inside the user's request.
- **Idempotent**: safe to repeat; submitting the same answer twice leaves one result.
- **Staging**: a copy of the system with fake data where changes are tried before production.
- **MFA / passkey / hardware key**: a second factor for sign-in; passkeys and hardware keys resist phishing.
- **SLA**: a contractual uptime promise with credits when missed (Neon Scale 99.95 %; Cloudflare Business 100 %).
- **PWA / TWA**: an installable web app; a TWA wraps it as an Android app.
- **ELQR**: Kyrgyzstan's national QR payment standard, accepted by all banking apps.
- **ASVS, CIS IG1, OWASP Top 10**: checklists of security requirements used to say "how secure" without hand-waving.
- **Bcrypt rounds**: the cost of a password hash; higher is safer and slower (ours ≈83 ms per login).
- **Admission gate**: our middleware that admits only N requests at a time into the app so overload becomes a short wait or a 503 instead of a deadlock.

---

## Sources

All accessed 2026-11-14 unless a page date is given. Vendor pages were read as untrusted data.

1. Vercel Terms of Service, §4 Hobby plan ("personal or non-commercial use"), updated 2026-10-19. https://vercel.com/legal/terms
2. Vercel Hobby plan docs (included usage, caps, WAF rules), updated 2026-09-14. https://vercel.com/docs/plans/hobby
3. Vercel pricing. https://vercel.com/pricing
4. Vercel changelog, Flat Rate CDN GA, 2026-09-08. https://vercel.com/changelog/flat-rate-cdn-is-now-ga-for-pro-teams
5. Vercel blog, new Pro pricing, 2025-09-09. https://vercel.com/blog/new-pro-pricing-plan
6. Vercel Firewall docs, updated 2026-09-10. https://vercel.com/docs/vercel-firewall
7. Vercel regions, updated 2026-08-11. https://vercel.com/docs/regions
8. Vercel guide: using Cloudflare with Vercel (do not proxy), updated 2026-11-13. https://vercel.com/kb/guide/cloudflare-with-vercel
9. Render changelog, "Updated plans for Render workspaces", 2026-04-23 (Pro $25 flat, legacy move 2026-08-01). https://render.com/changelog/updated-plans-for-render-workspaces
10. Render docs, new workspace plans (autoscaling on Pro and higher). https://render.com/docs/new-workspace-plans
11. Render pricing (Hobby $0 / Pro $25 / Scale $499; bandwidth 5 GB / 25 GB / 1 TB, $0.15/GB; compute Starter $7 … 4 CPU $175–350). https://render.com/pricing
12. Render docs, Free instances (15 min spin-down, ≈1 min wake, 750 h, may restart). https://render.com/docs/free
13. Render docs, scaling. https://render.com/docs/scaling
14. Render docs, deploys (zero downtime). https://render.com/docs/deploys
15. Render docs, DDoS protection. https://render.com/docs/ddos-protection
16. Render feedback, WAF feature request (open). https://feedback.render.com/features/p/web-application-firewall
17. Fly.io pricing and regions. https://docs.fly.io/about/pricing ; https://docs.fly.io/reference/regions
18. Railway pricing. https://railway.com/pricing
19. AWS App Runner availability change (closed to new customers 2026-04-30). https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html
20. Google Cloud Run pricing and locations. https://cloud.google.com/run/pricing ; https://docs.cloud.google.com/run/docs/locations
21. Hetzner Cloud, Regular Performance prices. https://www.hetzner.com/cloud/regular-performance
22. DigitalOcean Droplets pricing. https://www.digitalocean.com/pricing/droplets
23. WonderNetwork, pings from Bishkek, data checked 2026-11-13. https://wondernetwork.com/pings/Bishkek
24. Cloudflare network map (Bishkek PoP). https://www.cloudflare.com/network/
25. Cloudflare Workers pricing, updated 2026-11-13. https://developers.cloudflare.com/workers/platform/pricing/
26. OpenNext for Cloudflare (Next.js support). https://opennext.js.org/cloudflare
27. Netlify pricing. https://www.netlify.com/pricing/
28. Next.js self-hosting guide, updated 2026-10-15. https://nextjs.org/docs/app/guides/self-hosting
29. Neon pricing, updated 2026-11-04. https://neon.com/pricing
30. Neon plans (Free: 6 h restore, 1 GB, 5 GB egress then compute suspended, 100 CU-h; Launch 7 days $0.106/CU-h; Scale 30 days $0.222/CU-h), updated 2026-11-12. https://neon.com/docs/introduction/plans
31. Neon connection pooling (unsupported through the pooler incl. session-level advisory locks; max_client_conn 10,000; pool = 0.9 × max_connections), updated 2026-10-19. https://neon.com/docs/connect/connection-pooling
32. Neon read replicas, updated 2026-08-26. https://neon.com/docs/introduction/read-replicas
33. Neon scale to zero, updated 2026-11-04. https://neon.com/docs/introduction/scale-to-zero
34. Neon Business SLA (99.95 %), updated 2026-10-23. https://neon.com/neon-business-sla
35. Neon regions, updated 2026-10-14. https://neon.com/docs/introduction/regions
36. Supabase pricing and backups. https://supabase.com/pricing ; https://supabase.com/docs/guides/platform/backups
37. AWS RDS for PostgreSQL pricing (eu-central-1 price list). https://aws.amazon.com/rds/postgresql/pricing/
38. AWS Aurora pricing and Serverless v2 auto-pause. https://aws.amazon.com/rds/aurora/pricing/ ; https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html
39. DigitalOcean Managed PostgreSQL pricing and limits, limits updated 2026-11-05. https://www.digitalocean.com/pricing/managed-databases ; https://docs.digitalocean.com/products/databases/postgresql/details/limits/
40. Aiven for PostgreSQL pricing. https://aiven.io/pricing?product=pg
41. pgBackRest. https://pgbackrest.org/
42. Cloudflare R2 pricing, updated 2026-10-30. https://developers.cloudflare.com/r2/pricing/
43. Cloudflare R2 public buckets (r2.dev rate-limited, not for production), updated 2026-11-12. https://developers.cloudflare.com/r2/buckets/public-buckets/
44. Cloudflare R2 bucket locks, updated 2026-08-27. https://developers.cloudflare.com/r2/buckets/bucket-locks/
45. Backblaze B2 pricing. https://www.backblaze.com/cloud-storage/pricing
46. Bunny.net pricing and network. https://bunny.net/pricing/ ; https://bunny.net/network/
47. AWS CloudFront pricing. https://aws.amazon.com/cloudfront/pricing/
48. Brevo free plan 300 emails/day: third-party summaries (Brevo's pricing page did not render for the fetch tool; UNVERIFIED on the official page). https://www.emailtooltester.com/en/reviews/sendinblue/pricing/ ; https://www.sendx.io/blog/brevo-pricing-plans-costs-alternatives-2026
49. Resend pricing. https://resend.com/pricing
50. Amazon SES pricing. https://aws.amazon.com/ses/pricing/
51. Postmark pricing. https://postmarkapp.com/pricing
52. Google, email sender guidelines (SPF/DKIM/DMARC, 5,000/day rule). https://support.google.com/a/answer/81126 ; enforcement note https://www.spamresource.com/2025/11/google-warns-sender-requirements.html (2025-11)
53. Cloudflare plans (Free/Pro/Business). https://www.cloudflare.com/plans/network-cdn/
54. Cloudflare rate-limiting rules per plan, updated 2026-08-25. https://developers.cloudflare.com/waf/rate-limiting-rules/
55. Cloudflare WAF managed rules, updated 2026-09-08. https://developers.cloudflare.com/waf/managed-rules/
56. Cloudflare Waiting Room (Business and above), updated 2026-04-16. https://developers.cloudflare.com/waiting-room/
57. Cloudflare Health Checks, updated 2026-08-14. https://developers.cloudflare.com/health-checks/
58. cctld.kg tariffs and service regulations (.kg registry). https://www.cctld.kg/ru/tariffs ; https://www.cctld.kg/ru/service-regulations
59. Cloudflare Registrar TLD policies (no .kg). https://www.cloudflare.com/tld-policies/
60. Sentry pricing and data storage location (EU region, irreversible). https://sentry.io/pricing/ ; https://docs.sentry.io/organization/data-storage-location/
61. Better Stack pricing. https://betterstack.com/pricing
62. UptimeRobot pricing. https://uptimerobot.com/pricing/
63. Grafana Cloud pricing. https://grafana.com/pricing/
64. GitHub Actions billing (free for public repositories). https://docs.github.com/en/billing/concepts/product-billing/github-actions
65. GitHub docs, disabling and enabling workflows ("In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days"). https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows
66. GitHub Advanced Security features free for public repositories (secret scanning, push protection, CodeQL, dependency review). https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security ; https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/about-dependency-review
67. Digital Code of the Kyrgyz Republic (Law No. 178 of 2025-07-31), Arts. 63, 79, 81, 82, 86, 88, 89, 114–117, text on zakon.kg; official text cbd.minjust.gov.kg/3-48/edition/35412/ru. https://zakon.kg/law/digital-codex-kr/
68. ICNL, guidance note on the Digital Code's personal-data provisions (RU), 2026-02-10. https://www.icnl.org/wp-content/uploads/KG-Personal-Data-Guidance-Note_Digital-Code_February-10-2026_RU.pdf ; English note, 2025-08: https://www.icnl.org/wp-content/uploads/KG-Personal-Data-Guidance-Note_August-2025_eng.pdf
69. State Agency for Personal Data Protection (dpa.gov.kg): archived registry, adequacy list (only Kyrgyzstan "compliant"), model processor contract. https://dpa.gov.kg
70. 24.kg, parliament approves personal-data bill, 2026-05-14. https://24.kg/vlast/373786_parlament_odobril_zakonoproekt_ozaschite_personalnyih_dannyih/
71. Invest Compass (NIA / Baker Tilly), personal data in Kyrgyzstan, data as of June 2026. https://invest.gov.kg/en/invest-compass/assets/personal-data
72. Google Play Console help, supported locations for developer and merchant registration (Kyrgyzstan: developer ✔, merchant ✘). https://support.google.com/googleplay/android-developer/answer/9306917
73. Google Play payments policy. https://support.google.com/googleplay/android-developer/answer/9858738
74. Google Play Families policy. https://support.google.com/googleplay/android-developer/answer/9893335
75. Google Play account deletion requirement. https://support.google.com/googleplay/android-developer/answer/13327111
76. Google Play closed-testing requirement for new personal accounts. https://support.google.com/googleplay/android-developer/answer/14151465
77. Apple App Store Review Guidelines. https://developer.apple.com/app-store/review/guidelines/
78. OWASP ASVS 5.0.0 (May 2025). https://github.com/OWASP/ASVS
79. OWASP Top 10:2025. https://top10.owasp.org/2025
80. CIS Controls v8.1, Implementation Group 1. https://www.cisecurity.org/controls/implementation-groups/ig1
81. NIST SP 800-63B-4, authenticators (final 2025-07-31). https://pages.nist.gov/800-63-4/sp800-63b/authenticators
82. NIST SP 800-61r3, incident response (2025-04). https://csrc.nist.gov/pubs/sp/800/61/r3/final
83. OWASP Credential Stuffing Prevention Cheat Sheet. https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
84. Have I Been Pwned, Pwned Passwords range API (free, k-anonymity). https://haveibeenpwned.com/API/v3
85. Stripe, supported countries (Kyrgyzstan absent). https://stripe.com/global
86. Paddle, supported countries and pricing. https://www.paddle.com/help/start/intro-to-paddle/which-countries-are-supported-by-paddle ; https://www.paddle.com/pricing
87. Finik (Quickpay LLC). https://www.finik.kg/
88. Freedom Pay KG, merchant API. https://freedompay.kg/ ; https://freedompay.kg/docs-en/merchant-api/intro
89. GoPay acquiring. https://gopay.kg/ekvayring
90. economist.kg: ELQR turnover 2026-02-11; MKassa 2024-09-23; opening an online business 2026-08-13; single-tax rates 2026-08-08. https://economist.kg
91. aunimeda.com, payment integration in Kyrgyzstan (MBank, Elcart), published 2026-03-28, updated 2026-07-01. https://aunimeda.com/kg/blog/integraciya-platezhej-na-sajte-kyrgyzstan-mbank-elcart
92. Canvas LMS: Production Start wiki (edited 2026-05-26), Switchman README, inst-jobs; 2021 public pentest. https://github.com/instructure/canvas-lms/wiki/Production-Start ; https://github.com/instructure/switchman ; https://www.ruby-toolbox.com/projects/inst-jobs ; https://www.instructure.com/sites/default/files/file/2021-08/Instructure%202021%20Penetration%20Test%20Results.pdf
93. Moodle docs: Performance FAQ (edited 2022-09-15), Performance recommendations (edited 2023-08-16), Large installations (edited 2025-05-01). https://docs.moodle.org/400/en/Performance_FAQ ; https://docs.moodle.org/400/en/Performance_recommendations
94. iTnews, "How the University of South Australia scaled its systems for all online exams", 2020-11-09. https://www.itnews.com.au/news/how-the-university-of-south-australia-scaled-its-systems-for-all-online-exams-555544
95. Khan Academy blog, "How Khan Academy Successfully Handled 2.5x Traffic in a Week", 2020-05-09; The Next Platform, CTO interview, 2021-05-12. https://blog.khanacademy.org/how-khan-academy-successfully-handled-2-5x-traffic-in-a-week/ ; https://www.nextplatform.com/cloud/2021/05/12/serverless-veteran-khan-academy-on-pros-cons/
96. Percona Live ONLINE 2021, Edmodo, "Pandemic: A Tale of 25x Growth in Three Weeks" (slides). https://percona.com/sites/default/files/presentations/Pandemic%20-%20A%20Tale%20of%2025x%20Growth%20in%20Three%20Weeks.pdf
97. InfoQ, Duolingo Super Bowl notifications (QCon London), 2024-04-10; Duolingo FinOps blog. https://www.infoq.com/news/2024/04/qcon-london-duolingo-super-bowl/ ; https://blog.duolingo.com/finops
98. College Board: Bluebook help (answers saved on device, late submit); AP Psychology technical issue statement, 2025-05-16; GovTech on the March 2025 SAT early-submit, 2025-03-18. https://bluebook.collegeboard.org/help-center/what-if-students-answers-arent-submitted ; https://newsroom.collegeboard.org/technical-issue-impacting-ap-psychology-exams-may-16 ; https://govtech.com/education/k-12/some-sats-rescheduled-after-bluebook-app-glitch
99. Habr, Uchi.ru CTO on the 2020 traffic surge, 2020-04-27. https://habr.com/ru/post/498906
100. Medium, "How 3 Magoosh Engineers Support 5 Million Users" (page returned 403; title and summary from the search index, UNVERIFIED-direct). https://medium.com/magoosh-stories/how-3-magoosh-engineers-support-5-million-users-and-still-sleep-at-night-d4f28123fd8
101. AWS case study PhysicsWallah; OpsTree case study (separate accounts, backups, 100k concurrent). https://aws.amazon.com/solutions/case-studies/physics-wallah/ ; https://opstree.com/case-study/eliminating-downtime-and-enabling-100k-concurrent-users-for-physicswallah/
102. Google Cloud case study, Testbook (100–200× spikes). https://www.casestudies.com/company/google-cloud-platform/case-study/testbook-leveling-the-playing-field-for-millions-of-students-in-tier-3-and-4-cities-with-technology
103. PBS/AP, Canvas back online after cyberattack during finals, 2026-05-08. https://www.pbs.org/newshour/nation/canvas-system-used-by-thousands-of-schools-is-back-online-after-a-cyberattack-created-chaos
104. Kursiv, Kundelik outages on the first remote-learning day, 2020-04-06; Informburo, daily DDoS on Kundelik and BilimLand, 2020-09-16; kun.uz on the xorijdaish.uz overload, 2025-01-20. https://kz.kursiv.media/2020-04-06/v-pervyy-den-distancionnogo-obucheniya-ne-oboshlos-bez-sboev-v-kundelike/ ; https://informburo.kz/novosti/hakerskie-ataki-na-sayty-bilimland-i-kundelikkz-registriruyut-kazhdyy-den-111347.html ; https://kun.uz/en/news/2025/01/20/technical-issues-and-alleged-third-party-interference-halt-uk-seasonal-work-program-for-uzbeks
105. economist.kg, Aknet subscribers lose access to .kg sites, 2021-06-15. https://economist.kg/novosti/2021/06/15/u-provajdera-aknet-proizoshel-sboj-abonentam-nedostupny-sajty-v-zone-kg.md
106. Sirius (uts.sirius.online) participant memo, school stage of the All-Russian Olympiad, 2025 (one-day windows per region; only saved answers count); Yandex Cloud case, TalentTech olympiad platform, 2021-01-28. https://school.tver.ru/system/documents/files/000/010/873/original/1758523650.pdf ; https://yandex.cloud/ru-kz/cases/talenttech
107. Chalkbeat, "There was no cyber attack", TNReady investigation, 2018-06-20; Tennessee Comptroller audit, 2018-12-19. https://chalkbeat.org/posts/tn/2018/06/20/there-was-no-cyber-attack-investigator-says-of-tennessees-online-testing-shutdown/ ; https://comptroller.tn.gov/news/2018/12/19/new-audit-examines-tnready-testing-failures-.html
108. Texas Education Agency statement on STAAR online disruptions, 2021-04; iTnews on NAPLAN 2019 firewall. https://content.govdelivery.com/accounts/TXTEA/bulletins/2cb7a29 ; https://www.itnews.com.au/news/firewall-blamed-for-naplan-online-glitches-525160
109. Doppler pricing; Infisical pricing; 1Password pricing. https://www.doppler.com/pricing ; https://infisical.com/pricing ; https://1password.com/pricing/password-manager
110. Hetzner 2026 price increases: Tom's Hardware (April 2026, up to 37 %); WZ-IT on the June 2026 CPX increase. https://www.tomshardware.com/tech-industry/hetzner-to-raise-prices-by-up-to-37-percent-from-april-1 ; https://wz-it.com/en/blog/hetzner-price-increase-june-2026-cpx-ccx-alternatives/

Internal evidence (not numbered): `docs/phases/PERFORMANCE_AUDIT.md` (§1, §3.4, §3.5, §10), `docs/phases/PHASE_11_LOADTEST.md`, `docs/phases/PHASE_3_LOADTEST.md`, `docs/LOAD_TEST_PRE_PHASE3.md`, `docs/CAPACITY_REVIEW.md`, `docs/phases/DB_STORAGE_REVIEW.md`, `docs/COSTS.md`, `docs/LAUNCH_CHECKLIST.md`, `docs/runbooks/*.md`, `docs/phases/FIX_ROUND_2026-11-12.md`, `docs/HANDOFF_NEXT_AGENT.md`; code: `backend/app/lms/attempts/{sweep,autosave,timing,engine}.py`, `backend/app/lms/core/{ratelimit,admission}.py`, `backend/app/db/session.py`, `backend/app/core/{config,security,warmup,sentry}.py`, `backend/app/lms/infra/`, `backend/app/lms/platform_admin/{health,overview}.py`, `backend/app/lms/files/usage.py`, `backend/app/services/email_service.py`, `backend/app/api/v1/endpoints/auth.py`, `frontend/public/sw.js`, `.github/workflows/{ci,uptime,maintenance}.yml`.

---

## Appendix A: the owner's brief (verbatim)

> Later task (we will return to 3c we are working on domain now but you need to do this task for now ): research and evaluation for the platform's next, professional stage. This is a study, not a build. Architect on Fable. Use the internet: official docs, pricing pages, engineering blogs and case studies; cite every source with its date. Write docs/PLATFORM_STRATEGY.md and stop for my decision. Change nothing in production.
>
> Goal: we are moving from a prototype to a professional product. It must be secure, and it must be able to grow beyond the current target (about 6,000 students at once) without a rebuild each time. Judge our whole setup, not only Vercel: frontend host, backend host, database, file storage, email, domain and DNS, CI/CD, monitoring, backups, payments.
>
> 1. Where we are: an honest map of the current stack and architecture, each part rated for security, speed, reliability, cost and the limit where it breaks (students at once, data size, requests per second). Use our own measurements (load tests, PERFORMANCE_AUDIT.md, services panel) and say what was never measured.
>
> 2. How others do it: research how comparable products run in production, at small and large scale: exam and test-prep platforms and LMSs (Canvas, Moodle, Khan Academy, exam-prep startups, and regional ones if published). What they use for hosting, database, caching, queues, CDN, exam-time peaks, security and monitoring, and what a small team should and shouldn't copy.
>
> 3. Options per layer, compared from current sources, at least three each where real choices exist:
>    - frontend hosting (Vercel, Cloudflare, Netlify, self-hosted);
>    - backend hosting (Render, Fly.io, Railway, a cloud provider's managed containers, a VPS);
>    - database (Neon, Supabase, a cloud provider's managed Postgres, self-managed), including connection pooling, read replicas and backups;
>    - files and CDN, email, DNS, monitoring and error tracking, payments for Kyrgyzstan.
>    For each: price at each stage below, limits, speed for users in Kyrgyzstan (regions, latency), security features, lock-in, effort to move, and the maintenance burden for one founder working through an agent.
>
> 4. Security as its own chapter: a threat model for our case (minors' data, paid access, exam integrity, account takeover, DDoS on exam day, leaked secrets, a public repo). What a professional setup needs at each stage: WAF and rate limiting, secrets management, backups with tested restores, audit logs, dependency and vulnerability scanning, incident response, staging separate from production, least-privilege access. What Kyrgyz law and the app stores require for children's data. List our current gaps, ranked.
>
> 5. Scalability: what in our architecture limits growth (single backend instance, database connections, autosave writes, cold starts, in-memory state, synchronous work that should be queued) and the standard fixes (horizontal scaling, pooling, caching, queues, read replicas, CDN). Which fixes need code changes now so later growth is cheap.
>
> 6. Stages, not one jump: propose a path with clear triggers for moving to the next stage:
>    - Stage 0: now, testing, $0;
>    - Stage 1: launch, hundreds of students, about $30/month;
>    - Stage 2: thousands of students and paying users;
>    - Stage 3: tens of thousands and several exams (ORT, НЦТ, olympiads), schools.
>    For each stage: the full setup, monthly cost, what it handles, the security level, what must be migrated and how risky that is, and the signal that tells us to move up (usage numbers, revenue, incidents).
>
> 7. Recommendation: 2–3 complete end-state setups compared in one table, your pick with reasons, what to do first, what never to do early (over-engineering), and the decisions only I can make (money, contracts, legal).
>
> Rules: prefer boring, proven technology; every recommendation must say what it costs and what problem it solves; mark facts you could not verify; keep the document readable for a non-engineer, with a one-page summary on top.
