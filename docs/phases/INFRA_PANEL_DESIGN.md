# Infrastructure panel "Система → Сервисы" (design, 2026-11-09, Fable; owner round item 5)

Owner brief: one admin page showing, per service, the plan, usage against plan limits, warnings at 80 %, last update,
a link to the provider dashboard, "not connected" until a key exists; keys only on the backend; cache 15–30 min with a
manual refresh; plus "how many full 6,000-student exams still fit in the database" and a monthly cost estimate from
`docs/COSTS.md`. Sources: `DISCUSSION_ADMIN_CENTER.md` §8 (D in a light form: real health, banner), `COSTS.md`,
`CAPACITY_REVIEW.md` §6 (R2 arithmetic), `app/lms/files/usage.py`, `platform_admin/storage_service.py`,
`platform_admin/health.py`, `platform_admin/overview.py` (60 s in-process cache precedent), `AdminShell.tsx`
(group `system`: Storage, Health, Audit log, Security, Data requests). Provider facts below were read from the public
docs on 2026-11-09 (URLs cited); numbers marked *verify* were not found in an official page.

## 1. Page
Route `/[lang]/admin/services`, nav group `system`, first item (before Storage). Policy: `platform_admin` (the DB
flag + the existing MFA gate of `require_platform_admin`; nothing new). Layout: a header with "Обновлено 12:40 ·
[Обновить]" and the cost line; then one card per service in a 1 / 2 / 3-column grid (375 / 1440 / 1920):

```
+-----------------------------------------------+
| Neon · база данных              план Free     |
| Хранилище   41 МБ из 1 ГБ        [####      ] |
| Compute     6.6 из 100 CU-ч      [#         ] |
| Ветки       4 из 10              [####      ] |
| Экзаменов на 6 000 учеников ещё поместится: 4 |
| Обновлено 12:40 · Открыть панель Neon ↗       |
+-----------------------------------------------+
```
Card states: `ok` (quiet), `warning` (amber, any metric ≥ 80 % of its limit or a provider flag such as "sleeps"),
`error` (red line "Не удалось получить данные: таймаут", the previous snapshot stays visible with its time),
`not_connected` (grey, "Не подключено: задайте NEON_API_KEY на сервере", dashboard link still shown). A metric
without a limit shows the value and "лимит не публикуется". All strings in `en/ky/ru.json` under `infra.*`.

## 2. Providers: exact calls, tokens, limits

| Service | Token to create (owner) | Env (backend only) | Calls per refresh | Limits shown |
|---|---|---|---|---|
| Neon | Console → Account/Org → API keys → **project-scoped key** for `noisy-sound-20763725` (Editor on that project only; Neon has no read-only keys, project scoping is the narrowest) | `NEON_API_KEY`, `NEON_PROJECT_ID` (default `noisy-sound-20763725`) | `GET https://console.neon.tech/api/v2/projects/{id}` (`owner.subscription_type`, `owner.branches_limit`, `branch_logical_size_limit_bytes`, `compute_time_seconds`, `active_time_seconds`, `data_transfer_bytes`, `consumption_period_start/end`, `history_retention_seconds`, `default_endpoint_settings.autoscaling_limit_max_cu`); `GET …/projects/{id}/branches` (`logical_size` per branch, count) | storage = default branch `logical_size` vs `branch_logical_size_limit_bytes` (1 GiB on Free; verified on this project); compute = `compute_time_seconds/3600` vs 100 CU-h/month (Free, plans page); branches = count vs `branches_limit`; history window; max CU |
| Render | Dashboard → Account settings → API keys (account-wide; scoped keys are early access by form, no read-only mode) | `RENDER_API_KEY`, `RENDER_SERVICE_ID` | `GET https://api.render.com/v1/services/{id}` (`serviceDetails.plan`, `serviceDetails.region`, `suspended`, `autoDeployTrigger`, `serviceDetails.url`); `GET …/services/{id}/deploys?limit=1` (`deploy.status`, `commit.id`, `commit.message`, `finishedAt`) | plan, instance, "sleeps when idle" = `plan == "free"`; last deploy + commit compared with `/health` of our own API (already shows the running commit) |
| Vercel | Account → Settings → Tokens: scope = the team/account that owns the project, expiration 1 year (Vercel tokens have no read-only flag; scope + expiry are the narrowing) | `VERCEL_TOKEN`, `VERCEL_PROJECT_ID`, `VERCEL_TEAM_ID` (empty for a personal Hobby account) | `GET https://api.vercel.com/v9/projects/{id}[?teamId]`; `GET /v7/deployments?projectId=&target=production&limit=1[&teamId]` (`readyState`, `meta.githubCommitSha`, `created`); `GET /v2/teams/{teamId}` (`billing.plan` ∈ hobby/pro/enterprise) or `GET /v2/user` for a personal account | plan, last production deployment state and commit. Usage: `GET /v1/billing/charges` (FOCUS data) exists but Hobby has no billing cycle; the card shows plan + deployment and links to the usage dashboard. No 80 % metric for Vercel |
| Cloudflare R2 | Dashboard → My profile → API tokens → Create custom token: permission **Account · Account Analytics · Read** only, account resource = our account, optional IP filter, TTL 1 year | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` (reuse `R2_ACCOUNT_ID` when empty) | `POST https://api.cloudflare.com/client/v4/graphql` with two queries filtered `accountTag`, `date_geq = first of month`: `r2OperationsAdaptiveGroups { sum { requests } dimensions { actionType actionStatus bucketName } }`; `r2StorageAdaptiveGroups(limit:1, orderBy:[datetime_DESC]) { max { payloadSize metadataSize objectCount } }` | Class A = sum of requests whose `actionType` ∈ {ListBuckets, PutBucket, ListObjects, PutObject, CopyObject, CompleteMultipartUpload, CreateMultipartUpload, ListMultipartUploads, UploadPart, UploadPartCopy, ListParts, Put*Config}; Class B = {HeadBucket, HeadObject, GetObject, UsageSummary, Get*Config}; storage = `payloadSize + metadataSize` vs 10,000,000,000 B; ops vs 1,000,000 / 10,000,000 |
| Email (Brevo) | Brevo → SMTP & API → API keys (Brevo keys are not scoped; create a second key named "ort-panel" so it can be revoked alone) | reuse `BREVO_API_KEY`, `EMAIL_PROVIDER` | `GET https://api.brevo.com/v3/account` (`plan[].type`, `plan[].creditsType = sendLimit`, `plan[].credits`); `GET /v3/smtp/statistics/aggregatedReport?days=1` (`requests`, `delivered`, `hardBounces`, `blocked`) | sends today (`requests`) vs 300/day on Free (help centre; the API does not return the daily cap: constant `EMAIL_DAILY_LIMIT_FREE = 300`, shown as "лимит Free"); remaining credits |
| Email (Resend) | Resend → API keys → **Full access** key named "ort-panel" (`/usage` is not covered by a sending-only key; *verify*) | reuse `RESEND_API_KEY` | `GET https://api.resend.com/usage` → `emails.daily.{used,limit,sent,resets_at}`, `emails.monthly.{used,limit}`; `limit` is null on a paid plan | daily used vs limit (100/day, 3,000/month on Free) |
| SMTP / console | none | — | no call | card "Статистика недоступна для SMTP" |

Rate limits (per provider, far above one refresh per 20 min): Neon: not published for reads (key creation 10 r/s);
Render: "All other GET: 400 / minute", `Ratelimit-*` headers, 429 + `Retry-After`; Vercel: per-endpoint-group limits
on the Rate Limits page (not read here), 429 with headers; Cloudflare GraphQL: 300 queries / 5 min per user,
adaptive datasets keep ≥ 31 days, a query spans ≤ 31 days; Brevo: `GET /v3/account` falls under "all other
endpoints: 100 RPH", `/v3/smtp/statistics/*` 300 RPH (General tier); Resend: 5–10 requests/second account-wide.
Our budget: ≤ 12 provider requests per refresh, ≤ 3 refreshes per hour automatic + 6 manual → < 150 requests/hour.

**R2 source of truth.** Our counters (`storage_usage`, `storage_monthly_usage`) count what the backend wrote and
only the backend's own operations; public image GETs through `R2_PUBLIC_BASE_URL` are *estimated*
(`class_b_estimated`). Cloudflare's dataset counts every billed operation and the real stored bytes (dedup hits,
deleted smoke objects). Rule: **Cloudflare is the source of truth when connected**; the card shows both columns
("по Cloudflare" / "по нашему счётчику") and the 80 % warning uses the larger of the two. The upload guard
(`STORAGE_WARN_BYTES` / `STORAGE_HARD_BYTES`) keeps using our counter: it must work without a token and inside the
upload transaction. A gap > 20 % between the two storage figures shows warning `counter_drift`.

Sources: Neon plans https://neon.com/docs/introduction/plans, usage fields
https://neon.com/docs/introduction/usage-calculations, keys https://neon.com/docs/manage/api-keys (consumption
history API "requires a paid plan"); Render https://api-docs.render.com/reference/list-services,
…/list-deploys, …/rate-limiting, https://render.com/docs/api; Vercel https://vercel.com/docs/rest-api,
…/deployments/list-deployments, …/teams/get-a-team; Cloudflare https://developers.cloudflare.com/r2/pricing/,
https://developers.cloudflare.com/r2/platform/metrics-analytics/,
https://developers.cloudflare.com/analytics/graphql-api/limits/,
…/getting-started/authentication/api-token-auth/; Brevo https://developers.brevo.com/reference/getaccount,
…/getaggregatedsmtpreport, https://developers.brevo.com/docs/api-limits,
https://help.brevo.com/hc/en-us/articles/208580669; Resend https://resend.com/docs/api-reference/usage/retrieve-usage,
https://resend.com/docs/knowledge-base/resend-sending-limits.

## 3. Exams that fit (database)
Measured on production 2026-11-09 (read-only SQL via the Neon MCP): 14 attempts, 50 sections, 1,360 items;
`pg_total_relation_size`: `attempt_items` 327,680 B (heap 172,032 + indexes 114,688), `attempts` 212,992 B
(13 heap rows, index pages dominate at this size), `attempt_sections` 57,344 B; `pg_database_size` 17 MB; Neon
`logical_size` of `production` 41,451,520 B; limit `branch_logical_size_limit_bytes` 1,073,741,824 (Free).
Per item: 327,680 / 1,360 ≈ **241 B** (heap 126 + index 84, plus page slack), consistent with PHASE_3's
"≈ 0.2 GB per 6,000 × 150 exam" (222 B/item).

Formula (computed by the backend on each refresh, one SQL statement, `pg_class` only):
```
item_b    = total_size(attempt_items)    / max(count(attempt_items), 1)      floor 200 B, fallback 241 B when count < 1,000
section_b = total_size(attempt_sections) / max(count(attempt_sections), 1)   fallback 400 B when count < 1,000
attempt_b = total_size(attempts)         / max(count(attempts), 1)           fallback 1,500 B when count < 1,000
exam_b    = 6,000 × (attempt_b + 5 × section_b + 150 × item_b)              ≈ 6,000 × 37.6 KB ≈ 0.226 GB today
headroom  = limit_b − used_b    limit_b = Neon branch_logical_size_limit_bytes (else 1,073,741,824), used_b = Neon logical_size (else pg_database_size × 1.3)
fits      = floor(0.9 × headroom / exam_b)          (10 % kept for WAL/vacuum slack and other tables)
```
Today: floor(0.9 × (1,073,741,824 − 41,451,520) / 226,000,000) = **4 full exams** on the Free plan. The card shows
`fits`, the per-exam estimate, and "на Launch лимит снимается (0.35 $/ГБ-мес)". Row counts < 1,000 switch to the
fallbacks so index page minimums do not inflate the estimate; the card says "оценка" until counts pass 1,000.
Neon suspends writes above the cap but deletes nothing (plans page); the 6-hour history window
(`history_retention_seconds = 21600`) is shown next to it as the restore window.

## 4. Monthly cost estimate
Least fragile: **static data in code**, `app/lms/infra/costs.py`: `COST_ROWS = [(service, plan, usd_per_month |
None, note_key, source="docs/COSTS.md 2026-11-09")]` mirroring the table in `docs/COSTS.md` (Render Free 0, Neon Free 0,
Vercel Hobby 0, R2 free tier 0, email Free 0, Sentry off 0; "next plan" column: Render Starter 7, Neon Launch
pay-as-you-go, Vercel Pro 20/seat, all marked unverified). The card sums the "current" column (0 $ today), lists the
rows, and links to `docs/COSTS.md`. A test asserts every `COST_ROWS` service name appears in `docs/COSTS.md` so the
two cannot drift silently. Parsing the Markdown table was rejected (free-text cells like "about $7/month
(unverified)").

## 5. Backend
`app/lms/infra/` (new package): `models.py`, `providers/{neon,render,vercel,cloudflare,email}.py`, `service.py`,
`capacity.py` (§3), `costs.py` (§4), `router.py`, `policies.py`, `schemas.py`.

**Cache: a DB table, not in-process.** Render runs one uvicorn worker, but the free instance sleeps and every
deploy restarts it: an in-process cache (as `overview.py`) would show "not loaded" after each cold start and lose
"last update"; the owner opens this page rarely, mostly right after a deploy. One table, migration **`0031_infra`**:
`infra_snapshots(provider varchar(16) PK, status varchar(16) not null, fetched_at timestamptz null, payload JSON
not null default '{}', error varchar(500) null, duration_ms int null, updated_at timestamptz not null)`. No personal
data, no secrets (payload = the allow-listed fields of §2 only; the provider modules return typed dataclasses, never
raw responses). SQLite `create_all` picks it up. Downgrade drops the table.

Flow: `GET /platform/infra` reads the rows; providers whose `fetched_at` is older than `INFRA_TTL_SECONDS` (default
1200 = 20 min) or missing are refreshed **synchronously and concurrently** (`concurrent.futures.ThreadPoolExecutor`
with `httpx.Client(timeout=5.0)`; total bound 6 s), then the rows are upserted and returned. Double refresh guard: a
refresh first does `UPDATE infra_snapshots SET status='refreshing', updated_at=now WHERE provider=? AND (status <>
'refreshing' OR updated_at < now − 60 s)`; rowcount 0 → someone else is refreshing, serve the stored row. Not
connected (empty env) → row `status='not_connected'`, no call. Errors (timeout, 4xx/5xx, schema mismatch) →
`status='error'`, `error` = short code + HTTP status (never the response body or URL with the token), previous
`payload`/`fetched_at` kept. `POST /platform/infra/refresh` forces all providers (ignores TTL), rate limit
`infra_refresh_1h` 6/h per admin (`ratelimit.Limit`, like `storage_smoke_1h`), audited `infra.refresh`
(target_type `user`, target the admin, details: providers refreshed, statuses, durations). Logging: one line per
provider at INFO with status and duration; keys never logged. `capacity.py` runs its SQL on every GET (cheap, 3
`pg_class` rows) and reads Neon's figures from the Neon snapshot. Settings in `config.py` (names only):
`NEON_API_KEY`, `NEON_PROJECT_ID`, `RENDER_API_KEY`, `RENDER_SERVICE_ID`, `VERCEL_TOKEN`, `VERCEL_PROJECT_ID`,
`VERCEL_TEAM_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `INFRA_TTL_SECONDS`, `INFRA_REFRESH_RATE_PER_HOUR`,
`INFRA_DASHBOARD_URLS` not needed: dashboard links are constants per provider (Neon console project URL built from
`NEON_PROJECT_ID`, Render `https://dashboard.render.com/web/{RENDER_SERVICE_ID}`, Vercel, Cloudflare R2, Brevo/Resend).

Schema `InfraOut`: `{generated_at, ttl_seconds, cards: [{provider, status, plan, fetched_at, duration_ms, error_code,
dashboard_url, metrics: [{key, value, limit, unit, percent, level}], flags: [{key, level}]}], capacity: {fits,
exam_bytes, used_bytes, limit_bytes, estimated, history_seconds}, costs: {total_usd, rows: [...], source, as_of}}`.
`level` = `ok` (< 80 %), `warning` (≥ 80 %), `critical` (≥ 95 %), computed server-side so every client agrees.
Route inventory (`infra/policies.py`, merged like `PLATFORM_POLICIES`): `("GET", "/api/v1/platform/infra"):
"platform_admin"`, `("POST", "/api/v1/platform/infra/refresh"): "platform_admin"  # + rate limit 6/h, audited`.
Isolation test: both routes 403 for teachers, org admins and students (`tests/lms/isolation.py`).

Interaction with existing pieces: `/admin/storage` stays (upload guard, smoke test); the R2 card links to it. The
overview's `HealthLine` gains nothing now; a later slice may add "Сервисы: 1 предупреждение" to Needs attention
when any card is `warning` (read from the same table, no provider call).

## 6. Frontend
`/[lang]/admin/services/page.tsx` inside `AdminShell`; `components/lms/admin/infra/{ServiceCard,MetricBar,
CapacityCard,CostCard}.tsx`; `lib/lms/infra.ts` (types + `getInfra`, `refreshInfra`). The refresh button disables
while in flight and shows the 429 message from `lms.errors.rate_limited`. Mascot none; amber/red only from the
`level` values; the Pro gold is not used here. UX check 375 / 1440 / 1920 ru by the orchestrator.

## 7. Tests (mocked HTTP; no network in the suite)
- Provider modules: `httpx.MockTransport` fixtures with recorded-shape JSON for each call (success, 401, 429 with
  `Retry-After`, timeout, malformed body) → typed result or `ProviderError(code)`; the Cloudflare class A/B
  classification table; Brevo/Resend selection by `EMAIL_PROVIDER`; SMTP → `unavailable`.
- Service: not connected when env empty (no transport call); TTL respected (fresh row → no call); stale → one call
  per stale provider; error keeps the previous payload and time; `refreshing` guard (second caller serves the stored
  row); manual refresh ignores TTL, rate limit 6/h, audit event with providers and statuses; payload contains none
  of the configured key strings (assert the token value never appears in the JSON or logs via `caplog`).
- Capacity: formula with fallbacks (counts < 1,000) and with measured sizes (> 1,000, fixture inserts rows on
  SQLite: sizes come from a `size_provider` hook, PG uses `pg_total_relation_size`); `fits` monotone in headroom.
- Costs: every `COST_ROWS` service appears in `docs/COSTS.md`.
- Migration `tests/test_migration_0031.py` (pattern of 0025): table exists, empty, PK, down/up idempotent; SQLite +
  PG with `ALEMBIC_TEST_DATABASE_URL`.
- Route inventory, isolation, i18n parity, tsc; e2e `admin-services.spec.ts` with the API mocked by Playwright
  routes: not connected, warning at 85 %, error with previous data, refresh button.

## 8. Slices
- **I5a (Opus, backend)**: migration 0031 + test; `app/lms/infra/*`; config names; policies; audit action; tests of
  §7. Gate: full backend suite on a scratch DB, `alembic check` on PG, Neon backup branch before deploy (migration).
- **I5b (Sonnet, frontend)**: page, cards, `infra.ts`, i18n keys `infra.*`, e2e. Gate: tsc, parity, e2e, UX check.
- Owner after deploy: create the five tokens of §2 and set the env vars in Render; the page shows "not connected"
  until then and the orchestrator verifies each card turns `ok` after the owner's confirmation.

## 9. Proposed decisions
- D-I5-1 Cache in a DB table (`infra_snapshots`, 0031), TTL 20 min, synchronous concurrent refresh bounded at 6 s.
- D-I5-2 Cloudflare analytics is the R2 source of truth for display; our counter stays the upload guard; both shown.
- D-I5-3 Neon: project-scoped key (no read-only keys exist); Render: account key (scoped keys are early access);
  Vercel: team-scoped token with expiry; Cloudflare: Account Analytics Read only; email: a separate key per panel.
- D-I5-4 Exams-that-fit formula of §3 with fallbacks below 1,000 rows and a 10 % reserve; today ≈ 4 exams on Free.
- D-I5-5 Costs are static rows in code mirroring `docs/COSTS.md`, with a drift test; no Markdown parsing.
- D-I5-6 Vercel usage is not shown (Hobby has no billing cycle); plan + last production deployment + dashboard link.
- Open for the owner: whether to show the Needs-attention line on the overview (§5 last paragraph) now or later.
