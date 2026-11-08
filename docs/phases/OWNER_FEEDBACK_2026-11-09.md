# Owner feedback round 2026-11-09

Verbatim brief (the reference app is not named in repo docs). Results table at the end.

> Owner feedback after the last deploy, 2026-11-09. Same rules (improve, don't destroy; ORT behavior unchanged). Architect on Fable for the performance analysis and designs; implementers on Opus for performance, auth and data work, Sonnet for styling. Order: 1 → 4 → 3 → 2 → 5. No stops; one review list at the end.
>
> 1. SPEED AND FLICKER (top priority). Since the last deploy, switching tabs and signing in feel slow and glitchy:
>    - /ky/courses first renders with the student sidebar (Башкы бет, Каталог…) and then switches to the teacher header (Окутуу, Уюм, Админ панели): the wrong shell flashes.
>    - Pages show long skeletons before content appears.
>    Measure first, don't guess, and write docs/phases/PERFORMANCE_AUDIT.md: network waterfall per main page (login, student home, tests, analytics, teacher course list, course page, admin overview), number of requests and whether they run in sequence, time to first content, JS bundle size per route compared with before the last deploy, backend timings per endpoint (add Server-Timing), slow queries (EXPLAIN on Neon), and how much is Render/Neon cold start (Render Free sleeps; Neon free compute suspends when idle). Find what got worse in the last deploy (compare commits).
>    Then fix:
>    - The shell must be decided once, before rendering: from a cached /me (kept in the session and refreshed in the background) or server-side; never render one shell and swap to another. Show a neutral loading frame instead.
>    - Run independent requests in parallel; cache /me and other rarely changing data between tab switches (stale-while-revalidate); prefetch the main links; no full reload between tabs.
>    - Remove waterfalls, N+1 queries and over-fetching; add indexes where EXPLAIN shows scans; trim the JS bundle (lazy-load heavy parts, no big libraries on the first screen).
>    - Cold starts: measure them and tell me what Render/Neon plan change would remove them and what it costs. Don't change plans yourself.
>    Report before/after numbers for every main page (laptop and a slow phone profile).
>
> 4. PHONE ACCOUNT PANEL: on a phone, the "Аккаунт" sheet opens only partly: only "Конфиденциальность" is visible and "Выйти" is hidden behind the browser's bottom bar. Fix: use dynamic viewport height (dvh) and safe-area insets, a max height with internal scrolling, and keep "Выйти" always visible. Check every bottom sheet and the tab bar the same way. Test in Safari on iPhone and Chrome on Android sizes (Playwright WebKit and Chromium mobile emulation), for students and teachers.
>
> 3. SIGN-UP AND LOGIN REDESIGN (no questionnaire before sign-up):
>    - Modern split screen: left the form (title, short subtitle, "Continue with Google", "Continue with Apple", "or", name + email + password, one primary button, link to login); right a large friendly illustration with our snow leopard mascot in a calm mountain scene in the student palette (from the mascot images and simple SVG shapes, no copied artwork). Phone: the illustration becomes a small header. Same style for login and forgot password. en/ky/ru. No Microsoft.
>    - Google sign-in: standard server-side OAuth (state + PKCE, verified email only). Same email as an existing account: link only if the Google email is verified, otherwise refuse with a clear message. New users still go through the age/consent rules. Platform admins keep their two-step login; Google never skips it. Tell me exactly what to create in Google Cloud Console (OAuth client, redirect URLs for the Vercel and local addresses) and the env var names; I'll set the values in Render and backend/.env. Hide the button until the keys exist.
>    - Apple sign-in: build it ready but switched off (needs a paid Apple Developer account); list what I'd need to create.
>    - Tests: linking, unverified email refusal, admin two-step login, hidden buttons without keys, rate limits.
>
> 2. PRO INCLUDES COURSES: like the reference app, Pro unlocks all paid tests AND all lesson courses (masterclasses) with their materials. The course owner can mark modules as Pro; the first module or first lessons stay free as a preview. Students see a "Pro" badge on locked modules and lessons, with the unlock bar on course pages. The Pro offer page lists what's included (tests, courses, analytics). Staff, previews and Student view are never locked. Update SUBSCRIPTION_DESIGN.md.
>
> 5. INFRASTRUCTURE PANEL in the admin area (the idea from the admin-center discussion, section 8): one page "System → Services" showing, per service, the current plan, usage against plan limits and warnings at 80 %:
>    - Neon: plan, storage used vs limit, branches used vs limit, compute usage;
>    - Render: plan and instance, last deploy and commit, health, whether it sleeps;
>    - Vercel: plan, last deployment, usage where the API provides it;
>    - R2: storage used vs 10 GB free, Class A and Class B operations this month vs free limits (reuse the existing usage tracking);
>    - Email provider: sends today vs daily limit, if the API provides it;
>    - plus how many full 6,000-student exams still fit in the database, and a monthly cost estimate from docs/COSTS.md.
>    Use each provider's API with read-only keys stored only on the backend; cache results (refresh every 15–30 minutes, manual refresh button); never send keys to the browser. Where an API gives no usage, show what is known and a link to that dashboard. Tell me exactly which read-only tokens to create (Neon API key, Render API key, Vercel token, Cloudflare API token with R2 analytics read, email provider key) and the env var names; I'll set them in Render. Show "not connected" until a key exists.
>
> When done, give me one short review list (URLs, what to try, and the before/after speed numbers).

## Plan

| Item | Design (Fable) | Build |
|---|---|---|
| 1 Speed and flicker | `PERFORMANCE_AUDIT.md` (measurements, regression, fix slices, cold-start costs) | Opus |
| 4 Phone account panel | small, no design doc | Sonnet |
| 3 Sign-up / login, Google, Apple | `AUTH_SOCIAL_DESIGN.md` | Opus (auth), Sonnet (screens) |
| 2 Pro includes courses | `SUBSCRIPTION_DESIGN.md` update | Opus (data), Sonnet (badges) |
| 5 Infrastructure panel | `INFRA_PANEL_DESIGN.md` | Opus |

## Results

All items deployed 2026-11-09: main 09741b3 (Render /health 09741b3, Vercel SW 09741b32fcad, Neon head 0031_infra; backup branch backup-2026-11-09-before-identities-infra-0031). CI green on d0ae28d; local ORT + ORT pixel gate 10/10.

| Item | Result | Docs |
|---|---|---|
| 1 Speed and flicker | Shell decided once (no swaps), `/me/bootstrap` + SWR cache, page waterfalls removed, nav prefetch, dictionary split, Server-Timing. Final table §9 | `PERFORMANCE_AUDIT.md` |
| 4 Phone sheets | dvh + safe-area, pinned sign-out, WebKit + Android e2e | screens `OWNER_FEEDBACK_2026-11-09_screens/item4/` |
| 3 Sign-up / login, Google, Apple | Split-screen auth, Google OAuth (PKCE, verified email, browser-bound ticket, MFA kept), Apple built and off, hidden buttons without keys | `AUTH_SOCIAL_DESIGN.md`, `runbooks/GOOGLE_SIGN_IN.md` |
| 2 Pro includes courses | Unlock bar, Pro badges, offer lists courses, first-module warning, endpoint matrix | `SUBSCRIPTION_DESIGN.md` §12 |
| 5 Services panel | Админ-панель → Система → Сервисы, "not connected" until keys | `INFRA_PANEL_DESIGN.md` |
