# Subscription (Free vs Pro) instead of code-first access (design, 2026-11-07, Fable)

Problem 6 of `STUDENT_UI_FEEDBACK_2026-11-07.md`; outline in `STUDENT_UI_FIX_PLAN.md` §6, overrides §10. Replaces the
*screens* of `S3_ACCESS_DESIGN.md`; its rules (§1), data (§2), code mechanics (§3) and review changes (§7) stay in force.
The repo is public: the reference app is called "the reference app".

## 1. Principles
1. **Pro is an active `access_passes` chain.** No new entitlement model: "Pro" = `service.chain()` says active. A plan
   is only the *length* a pass was bought or granted with. Everything that checks access today (`require_start`,
   `check_resume`, `course_gate`, practice, Pro lessons from problem 5) keeps calling the same functions.
2. **Plans are configuration, not rows**: `PRO_PLANS` in `access/plans.py` = `month_1` (30 days), `month_3` (90 days),
   `season` (ends at the end of the season-end day, Asia/Bishkek). Prices and "how to pay" are owner-edited settings.
3. **Nothing existing changes meaning**: passes, batches, codes, `source` values, the 400-day cap, extension arithmetic,
   revoke shifting, `ends_on` semantics, rate limits, privacy rules. Codes become "vouchers" in the UI only.
4. The exam date countdown (`exam_prep.layout.exam_date_of`, per course) is untouched and never reads access. The season
   end is a *separate* setting: the owner may put it after the last ORT sitting of the year.
5. Server-side authorization only; every admin write audited with a reason where the body has one.

## 2. Data (one additive migration)
- `access_passes.plan` varchar(16) **null**, check `plan IS NULL OR plan IN ('month_1','month_3','season')`. Null for
  every existing row (legacy, code-redeemed and admin passes with days/date). Set only by new grants/payments by plan.
- `platform_settings` (new, key/value, one row per key): `key` varchar(64) PK, `value` JSON not null, `updated_at`,
  `updated_by_id` FK users SET NULL. Keys used here: `pro_season_end` (`{"date": "2027-05-31"}`), `pro_prices`
  (`{"month_1": 990, "month_3": 2490, "season": null}` KGS, null = "price on request"), `pro_how_to_pay`
  (`{"ru": "...", "ky": "...", "en": "..."}`; empty string → the i18n placeholder `access.howToPay`). No rows are
  inserted by the migration; defaults live in `plans.py` (season end default = 31 May of the next season year, computed:
  31 May of this year if today ≤ 31 May else next year). SQLite `create_all` picks the table up automatically.
- Nothing else. No change to `activation_code_batches`, `activation_codes`, `assessments.access_tier`, `practice_free`.
- **Numbering (§10 override: each problem adds its own migration).** `COURSE_LESSONS_DESIGN.md` is not written yet; if
  problem 5 lands `0024_lessons` first (slice order F5 → F6 in §8), this is **`0025_pro`**, else `0024_pro`. Recommend
  **not merging** with 0024: independent downgrade, independent Neon backup, and this one may deploy before lessons
  if F5 slips. The implementer takes the number from `alembic heads` at build time; `AGENTS.md` §2 head updated.
- Downgrade drops `access_passes.plan` and `platform_settings` (plan labels and the owner's texts are lost; passes are not).

**Migration test `tests/test_migration_0025.py`** (pattern of `test_migration_0023.py`, on the fixture DB migrated
through 0022/0023): seed 3 passes (code / admin / one revoked), 1 batch with 3 codes (unused, given, redeemed) *before*
upgrading; after upgrade: identical row counts, every column of every pre-existing row byte-equal to the snapshot taken
before (compare dict-of-rows), `plan` is NULL everywhere, the CHECK rejects `plan='week'`, the redeemed code still links
to its pass, `platform_settings` exists and is empty; down → the column and table are gone and the snapshot still
matches; up again → same. Runs on SQLite always and on PostgreSQL with `ALEMBIC_TEST_DATABASE_URL`.

## 3. Service (`access/service.py`, `access/plans.py`, `access/settings.py`)
- `plans.resolve(plan, settings, now) -> (days | ends_on)`: `month_1`→days 30, `month_3`→days 90, `season`→`ends_on` =
  season end. `season` whose end is not after today → `ValidationFailed season_ended` (UI hides the plan then).
- `grant(..., plan | days | ends_on, reason)`: exactly one of the three (`grant_length_required` otherwise). Plan is
  resolved to days/ends_on and then **the existing code path runs unchanged**: user row `FOR UPDATE` (§7.2 of S3),
  `extend()` from the current chain end, `grant_no_benefit`, 400-day cap, `source='admin'`, audit `access.grant`
  (details gain `plan`). The new pass stores `plan`. "Renew" in the UI is this call: an active chain is extended
  from its end, an expired one starts now.
- `cancel_pro(db, admin, user_id, reason)`: lock user; select every pass of the user with `revoked_at IS NULL AND
  ends_at > now` `FOR UPDATE`; set `revoked_at/by`; one audit event `access.pro_cancel` (details: pass ids,
  unused seconds). No shifting (nothing remains to shift). Second call → `Conflict pro_not_active`. Per-pass
  `revoke_pass` stays for partial cases (refund of one purchase).
- `status()` adds `plan` (of the pass that ends the chain), `days_left` (ceil of the remaining time, 0 when inactive),
  `source` (same pass). One query as today (`_open_passes` already loads what is needed; add `plan`, `source` columns).
- `offer(db, user_id, now)`: plans with price, length text inputs (days or season end), and `new_ends_at` = what the
  chain end would be after buying it (uses `extend()` on the already loaded passes; `season` omitted when it adds
  nothing or has ended), `how_to_pay[lang]`, `season_end`. Two queries (settings rows + the user's open passes).
- `settings.get_pro(db)` / `settings.put_pro(db, admin, body, request)`: validate `season_end` within
  [today, today + 400 days] (so the season plan never breaks the cap), prices integers 0..1,000,000 or null, texts
  ≤ 2000 chars per language; upsert the three rows in one transaction; audit `access.settings_update` with old/new.
- **Pro list query** (`admin.list_pro`): one SELECT over `access_passes` filtered `revoked_at IS NULL`, grouped by
  `user_id` with `max(ends_at)` as the chain end (invariant: a user's non-revoked passes form one unbroken chain,
  because `extend()` starts at the latest end and `revoke_pass` shifts later passes back; a test asserts it), joined to
  `users` for name/email, plus a lateral/subquery for the plan and source of the pass with that max `ends_at`.
  Filters: `status=active|expiring|expired` (expiring = ends within 14 days; expired = chain end in the last 90 days),
  `q` (name/email prefix, as the users list does), cursor on `(ends_at, user_id)`, `limit` ≤ 100. Never loads passes
  of all users into memory.
- Invariants: `plan IS NULL` ⇒ legacy or custom length; `source='code'` ⇒ `plan IS NULL` (codes have their own length);
  `source='payment'` reserved for §9 (no code writes it yet; the CHECK already allows it).

## 4. API (`access/policies.py` gains the rows; `route_inventory` test fails on unlisted routes)
Student (`authenticated`):
- `GET /me/access` → `+ plan, days_left, source` (the shell pill keeps this one light call).
- `GET /me/access/offer` → `{plans:[{id, days|season_end, price_kgs|null, new_ends_at}], how_to_pay, season_end,
  status:{active, ends_at, plan}}`. Not rate limited (read, two queries).
- `POST /me/access/redeem` unchanged (voucher field on `/pro`).
Platform admin (`platform_admin`, two-step login):
- `POST /platform/users/{user_id}/access/grant` body `{plan?|days?|ends_on?, reason}`; `GET …/access` adds `plan` per pass.
- `POST /platform/users/{user_id}/access/cancel` `{reason}` (new).
- `GET /platform/access/pro?status&q&cursor&limit` (new) → rows `{user_id, name, email, ends_at, days_left, plan,
  source, started_at}`; `GET /platform/access/pro/summary` → counts active / expiring 14d / expired 90d (three
  COUNTs with the same grouped subquery), used by the overview card.
- `GET /platform/access/settings`, `PUT /platform/access/settings` (new; audited).
- Batches/codes/exams/courses endpoints: unchanged paths and policies (reveal > 20/h attention item stays).
Errors (all three languages under `lms.errors.*`): `season_ended`, `pro_not_active`, `settings_invalid`, plus the
existing `grant_no_benefit`, `grant_too_long`, `grant_length_required`, `code_invalid`, `code_no_benefit`.

## 5. Authz, audit, privacy
- Student endpoints read only the caller's rows (`user.id` from `get_lms_user`); the offer never includes other users.
- Admin endpoints: `require_platform_admin` (DB flag, S1 two-step). No org admin or teacher can grant or list Pro.
- Audit actions: `access.grant` (+plan), `access.pro_cancel`, `access.settings_update`; existing `access.redeem`,
  `access.pass_revoke`, batch/code events unchanged. Reasons required on grant, cancel, revoke.
- Privacy: `plan` joins the `access_passes` export section; anonymize unchanged (passes stay tombstones, `reason`
  emptied); `platform_settings` holds no personal data. `tests/lms/isolation.py` gets `/me/access/offer`.

## 6. Student screens
`/[lang]/unlock` becomes a redirect to `/[lang]/pro` (page-level `redirect`, keeps old links from e-mails and the
shell); `UnlockCallout` → `ProCallout` (same slot, new copy); the StudentShell pill: gold "Pro" (no pass) or quiet
"Pro до 31 мая" (`access.pill.*` keys); `LockOverlay` and `NextCard` link to `/pro`. The three plans are three
selectable cards; choosing one only reveals the "how to pay" text with the chosen plan and its price (no payment
yet). The voucher field is folded under a disclosure "У меня есть код". Analytics stays free (D8) and is not listed.

```
375 px  /pro                                    1440 px  /pro
+-----------------------------------+           +-------------------------------------------------------------+
| Pro                               |           | Pro                                                          |
| Все тесты, практика и уроки Pro   |           | Все тесты, практика и уроки Pro до конца сезона              |
| [ Pro до 31 мая 2027 · 203 дня ]  |           +------------------------------+------------------------------+
+-----------------------------------+           | Бесплатно        | Pro       | Выберите план                 |
| Бесплатно      | Pro              |           |  ✓ бесплатные    | ✓ все     |  ( ) 1 месяц     990 с        |
|  ✓ беспл.тесты | ✓ все тесты      |           |    тесты         |   тесты   |  (•) 3 месяца   2490 с        |
|  ✓ аналитика   | ✓ практика       |           |  ✓ аналитика     | ✓ практика|  ( ) до конца сезона  31 мая  |
|  ✓ результаты  | ✓ уроки Pro      |           |  ✓ результаты    | ✓ уроки   |  Новая дата окончания: 5 фев  |
+-----------------------------------+           |                  |   Pro     |-------------------------------|
| Выберите план                     |           |                  |           | Как оплатить                  |
| (•) 1 месяц           990 с       |           +------------------------------+ {how_to_pay text, pre-line}   |
| ( ) 3 месяца         2490 с       |           | Статус: Pro до 31 мая 2027   | План: 3 месяца, 2490 с        |
| ( ) до конца сезона   31 мая      |           | Осталось 203 дня             |                               |
| Новая дата окончания: 5 фев 2027  |           +------------------------------+-------------------------------+
+-----------------------------------+           | ▸ У меня есть код   [XXXX-XXXX-XXXX] [Активировать]           |
| Как оплатить                      |           +-------------------------------------------------------------+
| {how_to_pay text}                 |           Mascot in the Pro column header on ≥1024 px; gold only on the Pro
+-----------------------------------+           column border and the pill (SF-3); exam countdown is NOT here.
| ▸ У меня есть код                 |
+-----------------------------------+
```

## 7. Admin screens (`/admin/access`, tabs: **Pro** · Ваучеры · Экзамены · Настройки)
- **Pro** (default tab): summary chips (active / expiring 14 d / expired 90 d), filter segmented control, search,
  table (person → person page, ends, days left, plan, source), row actions "Продлить" (grant dialog with the plan
  preselected = last plan) and "Отменить" (reason dialog, danger). Header action **"Выдать Pro"**: user search (reuse
  the person search of the users list), plan radio (1 month / 3 months / season / custom: days or end date), reason,
  preview line "Pro до {new_ends_at}" computed client-side from the row's end (server re-checks).
- **Ваучеры**: today's batches list and batch page, simplified: create / list / revoke / copy a code / mark given; CSV
  export and reveal moved under a "Ещё" menu (API unchanged). Length options in the create dialog: the three plans or
  custom. Batches still create codes with `duration_days`/`ends_on`; redeemed passes keep `plan NULL`.
- **Экзамены**: unchanged. **Настройки**: season end (date), three prices, "how to pay" per language (three textareas,
  ru required, ky/en optional → fallback to ru text at read time), save with a toast; audited.
- Person page (S4): `UserAccessSection` keeps its pass table (+ plan column) and gets the same "Выдать Pro" and
  "Отменить Pro" dialogs.

```
375 px  /admin/access (Pro)                     1440 px  /admin/access (Pro)
+-----------------------------------+           +-------------------------------------------------------------+
| Доступ ‹ Админ          [Выдать] |           | Доступ                                         [ Выдать Pro ] |
| [Pro] [Ваучеры] [Экз.] [Настр.]   |           | [Pro] [Ваучеры] [Экзамены] [Настройки]                       |
| Активно 128 · Истекает 9 · Ист. 40|           | Активно 128   Истекает за 14 дней 9   Истекло за 90 дней 40  |
| [Активные v] [поиск...........]   |           | (Активные | Истекают | Истекли)   [поиск по имени/почте ..]  |
+-----------------------------------+           +----------+--------------+---------+------+---------+---------+
| Айгерим А.         до 31 мая 2027 |           | Человек  | Pro до       | Осталось| План | Источник| Действия|
| 3 месяца · вручную  · 203 дня     |           | Айгерим А| 31 мая 2027  | 203 дня | 3 мес| вручную | Продлить|
|           [Продлить]  [Отменить]  |           | Бакыт К. | 12 ноя 2026  | 5 дней  | —    | ваучер  | Отменить|
| Бакыт К.           до 12 ноя 2026 |           | …                                                            |
| — · ваучер · 5 дней               |           +-------------------------------------------------------------+
+-----------------------------------+           | Показать ещё                                                 |
```

## 8. Tests (backend `tests/lms/test_access.py`, `test_access_pro.py` new, `test_pg_concurrency_access.py`, e2e)
- Plans: `month_1`/`month_3` give 30/90 days from the chain end; `season` ends at Bishkek end of the season-end day;
  `season` not later than the current end → `grant_no_benefit`; season end passed → `season_ended`; exactly one of
  plan/days/ends_on; legacy grant by days still works with `plan NULL`; audit details carry `plan`.
- Status: `plan`, `days_left`, `source` of the chain-ending pass; inactive → 0 / null; offer `new_ends_at` per plan.
- Cancel: every open pass revoked, one audit event, attempts in progress on timed exams still resume (§7.1), untimed
  refused; second cancel → `pro_not_active`; per-pass revoke still shifts later passes.
- List: grouping gives the chain end; filters and cursor; `q`; a student with only revoked passes is not listed as
  active; chain invariant test (grant, grant, revoke middle → one contiguous run).
- Settings: validation bounds, upsert, audit old/new, text fallback to the i18n placeholder, ky/en fallback to ru.
- Migration test of §2. Route inventory, isolation (`/me/access/offer`, `/platform/access/pro` only for admins),
  rate limit on redeem unchanged, privacy export includes `plan`.
- PostgreSQL (`pg` fixture): concurrent grant by two admins → no overlap, total = sum of days; grant + cancel at once
  → either cancelled then granted (active) or granted then cancelled (inactive), never a half state; redeem + grant
  (existing) still green.
- ORT parity: a Pro student and a free test behave exactly as in `docs/phases/ORT_BASELINE/` (no player change).
- Frontend: `npx tsc --noEmit`, i18n parity, e2e `access.spec.ts`: `/unlock` → `/pro`, plan selection shows the text,
  voucher redeem, admin grant/renew/cancel flow, settings save; UX check at 375/1440/1920 in ru by the orchestrator.

## 9. Automatic online payment (design only; needs the owner's contract and keys)
Research 2026-11-07 (web; little is public, every row must be confirmed with the provider's sales desk). Common to
all: a registered seller (ИП or ОсОО) with a Kyrgyz bank account, a merchant contract, settlement to that account.

| Provider | What it is | Needs / integration | Fees (public?) | Recurring | Sandbox |
|---|---|---|---|---|---|
| **Freedom Pay (ex-PayBox.money)** | Aggregator serving KG: cards (Visa/MC/Элкарт), wallets, terminals under one contract (`freedompay.kg`) | Legal entity/ИП + local bank account; hosted page `init_payment` → redirect; signed `result_url` callback (server to server) + `success/failure` URLs; status query; refunds by API/cabinet | Not public for KG; per-transaction % | Recurring profiles (`pg_recurring_start`, lifetime) documented for cards | Test mode exists (cards, mobile commerce) |
| **Finik (ELQR QR)** | QR payment app on the national ELQR standard; dynamic QR and payment links; API (`accountId`, `x-api-key`, idempotent `requestId`) | Corporate account via finik.kg; API keys from their reps; callback on payment; fixed commission, no subscription | Not public | No (QR is pay-once) | Unknown; ask |
| **MBank / MKassa** | Largest retail bank; MKassa = QR/POS/"remote request" for merchants | Settlement account at MBank; MKassa onboarding online; no public API docs found for a website checkout | QR promo 0 % at times | No | No public info |
| **O!Dengi / O!Business** | Mobile-operator wallet; O!Business QR for ИП | Agreement with O!; QR acceptance (claimed no commission for ИП, 2026-01); website API docs not public | Not public | No | Unknown |
| **Elsom, Balance.kg, Pay24** | Wallet (Elsom), wallet/bills (Balance), payment system + 17 partner banks and terminals (Pay24) | Pay24 has a merchant API (used by shop plugins); Elsom/Balance = service listing (student pays by account id), no proper webhook found | Not public | No | Unknown |
| **Bank acquiring (Optima, Demir, KICB, Bakai)** | Card internet-acquiring, Visa/MC/Элкарт, 3-D Secure | Bank contract (KICB publishes its internet-acquiring rules); bank-provided gateway, callbacks per bank; refunds via bank | Negotiated, ~2–3 % typical, not public | Card-on-file where the bank's gateway supports it | Per bank |

**Recommendation**: (1) **Freedom Pay** first: one contract covers cards and the local wallets, hosted page (no PCI
scope), signed callback, refunds, documented recurring profiles, test mode; the owner needs an ИП/ОсОО, a bank account
and the merchant id + secret. (2) **Finik (ELQR QR)** second, because students and parents pay by QR from any bank app;
pay-once, fixed fee, no recurring. Do **not** build bank-by-bank integrations. Manual renewal first (e-mail reminder
7 days before `ends_at`, through the existing mail transport); auto-renew only after Freedom Pay confirms recurring
for KG merchants and the owner accepts the dunning rules.

**Integration shape (future slice F6d, not now)**: table `payments` (id, user_id, plan, amount_kgs, currency,
provider, provider_order_id unique per provider, status `created|pending|paid|failed|refunded|expired`, pass_id null,
raw_callback JSON, created_at, paid_at, refunded_at). `POST /me/pro/checkout {plan}` creates `created`, calls the
provider's init with our order id, stores the provider id, returns the redirect URL (rate limited 10/h). Webhook
`POST /payments/{provider}/callback` (public, unauthenticated route, policy `webhook+signature`): verify the signature
and the amount against the row, load the payment `FOR UPDATE` after the **user row lock of §7.2**, if already `paid`
answer OK (idempotent replay), else mark `paid`, `grant` with `source='payment'`, `plan`, `code_id NULL`, link
`pass_id`, audit `access.payment` (no actor; payment id), one transaction. Reconciliation: a sweep marks `pending`
older than 24 h by querying the provider's status endpoint. Refund = admin revokes the pass (reason) and refunds in
the provider cabinet; the payment row becomes `refunded`. Secrets only as env names in `config.py`
(`PAYMENT_PROVIDER`, `FREEDOMPAY_MERCHANT_ID`, `FREEDOMPAY_SECRET_KEY`); never in the repo. The `/pro` plan cards get
a "Оплатить" button only when `PAYMENT_PROVIDER` is set; until then the "how to pay" text stays the path.

## 10. Slices (model per slice; Opus for anything touching data)
- **F6a (Opus)** migration `00NN_pro` + migration test; `plans.py`, `settings.py`; service changes (grant by plan,
  cancel, status/offer, list, summary); schemas, router, policies; audit actions; privacy export; backend tests incl.
  PG concurrency. Gate: full backend suite on a scratch DB, `alembic check` on PG, Neon backup branch before deploy.
- **F6b (Opus)** `/pro` page, `/unlock` redirect, `ProCallout`, pill, lock links; admin tabs Pro + Настройки, person
  page dialogs; `frontend/src/lib/lms/access.ts` types; e2e `access.spec.ts`. Gate: tsc, parity, e2e, UX check.
- **F6c (Sonnet)** copy and keys in `en/ky/ru.json` (`access.pro.*`, `access.pill.*`, `access.admin.pro.*`,
  `access.admin.settings.*`, errors), voucher tab reshuffle ("Ещё" menu), styling. Redo on Opus if wrong.
- F6d (later, Opus, after the owner signs a provider contract): §9.

## 11. Risks and open questions
- A user with many legacy passes: `_open_passes` is bounded (`PASS_SCAN_MAX` 200); fine.
- "Season" plan near the season end adds little; the offer hides it when `new_ends_at` ≤ current end, and the server
  refuses `grant_no_benefit`. The default season end (31 May) is a guess until the owner sets it in Настройки.
- `plan NULL` rows show "—" in the list; sources show "ваучер / вручную / оплата". No backfill of `plan` (we cannot
  know which plan a legacy pass was; guessing would change meaning).
- The i18n placeholder `access.howToPay` stays as the fallback so the page is never empty.
- Pro lessons (problem 5) must call `course_gate` / `has_active_pass` from `access/service.py`; the lessons design owns
  its lock column, not this one.
- Open for the owner: prices; season end; whether the "Отменить" action should refund (today: revoke only, refund
  outside the platform, both audited; S3 §7.8).
