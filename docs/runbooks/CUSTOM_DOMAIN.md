# Custom domain: one short session

Owner round 2026-11-13, item 7. The domain and the platform name are **not decided**; nothing here is live. When the owner
gives them, this checklist moves the whole platform in one session (about 1–2 hours of work, plus DNS and certificate
waits). Placeholders: `<domain>` (for example `example.kg`), `<platform name>`.

Today: frontend `https://ort-platform-nu.vercel.app` (Vercel), backend `https://ort-platform-w77q.onrender.com` (Render
Frankfurt), public images on an `r2.dev` address (`R2_PUBLIC_BASE_URL`), email from the owner's personal address.

**Target (decided, `PRODUCT_DECISIONS.md` "Domain and email readiness"):**

| What | Address | Why |
|---|---|---|
| Site | `https://<domain>` (canonical), `https://www.<domain>` redirects to it | Short address for students; Vercel serves both |
| Backend | `https://api.<domain>` (Render custom domain, CNAME, DNS only) | Same site as the frontend; Google's consent screen and redirect URI show our domain, not `onrender.com`; the host can move later without touching Google, Vercel or the PWA. Keep `onrender.com` enabled as a fallback |
| Images | `https://img.<domain>` (R2 custom domain on the public bucket) | r2.dev is rate-limited and has no cache (Admin → Storage warns about it); free on Cloudflare |
| Email | `noreply@<domain>` (Brevo), `support@<domain>` forwarded (Cloudflare Email Routing) | `EMAIL_DOMAIN.md` |
| DNS | Cloudflare (free plan), the registrar only points the nameservers there | Email Routing and the R2 custom domain both require the zone on Cloudflare |

Who does what: **[owner]** = needs the owner (paying, registrar, a dashboard login the agent does not have, Google Cloud
Console). **[agent]** = an agent can do it (code, Vercel MCP, Neon MCP, docs); Render env changes need the Render
dashboard (or the Render MCP when it connects).

## 0. Before the session

- [owner] Decide the name and the domain; buy the domain at a registrar (`.kg` names: a registrar accredited for `.kg`;
  Cloudflare Registrar does not sell `.kg`). Paying is the owner's action.
- [agent] Read `GOOGLE_SIGN_IN.md`, `EMAIL_DOMAIN.md`, `IP_CHAIN.md`, `SERVICE_WORKER.md` once.
- [agent] Write down the current values (privately, not in the repo) of every variable this runbook changes, for the rollback.
- Pick a quiet hour: users signed in on the old address are signed out once (the token lives in the browser storage of
  the old origin), and an installed app (PWA) must be reinstalled from the new address.

## 1. DNS on Cloudflare [owner]

1. Cloudflare → Add a site → `<domain>` → Free plan. Cloudflare imports existing records (a new domain has none).
2. At the registrar: replace the nameservers with the two Cloudflare gives. Wait until Cloudflare says "Active"
   (minutes to 24 h; `.kg` can be slower).
3. Cloudflare → SSL/TLS → mode **Full (strict)**.

Verify: `dig +short NS <domain>` shows the Cloudflare nameservers.
Rollback: nothing points to the domain yet; nothing to undo.

## 2. Frontend on Vercel

1. [owner or agent via Vercel MCP] Vercel → project → Settings → **Domains** → add `<domain>` and `www.<domain>`; set
   `www.<domain>` to **redirect (308) to `<domain>`**.
2. [owner] Cloudflare DNS, both **DNS only** (grey cloud; Vercel issues its own certificate and must see the requests):
   - `A` `@` → the IP Vercel shows for this project (often `76.76.21.21`; newer projects show another address: copy it);
   - `CNAME` `www` → the target Vercel shows (`cname.vercel-dns.com` or a project-specific `*.vercel-dns-*.com`).
   Remove any `AAAA` record for `@` or `www`.
3. [agent] Vercel → Settings → Environment Variables (Production), then **redeploy** (`NEXT_PUBLIC_*` values are built in):
   - `NEXT_PUBLIC_API_URL` = `https://api.<domain>` (step 3 must be live first; until then keep the onrender address);
   - `BACKEND_INTERNAL_URL` (if set) = the same, or leave the onrender address (server-side rewrite only);
   - `NEXT_PUBLIC_R2_PUBLIC_BASE_URL` = `https://img.<domain>` (CSP `img-src`/`connect-src`; set it **before** step 4
     switches the backend, `next.config.ts` keeps `https://*.r2.dev` allowed so old image URLs keep loading).
4. [agent] Redirect the old address: add to `frontend/vercel.json` (commit, deploy):
   ```json
   "redirects": [
     { "source": "/:path*", "has": [{ "type": "host", "value": "ort-platform-nu.vercel.app" }],
       "destination": "https://<domain>/:path*", "permanent": true }
   ]
   ```
   The host condition matches only the production `vercel.app` name, so preview deployments keep working. Path and query
   are kept: invitation, password-reset and email-change links already sent (they carry the old `FRONTEND_URL`) still work.
   Do this **after** steps 3 and 5 (CORS and `FRONTEND_URL`) are live, else the redirected site cannot reach the API.
5. Nothing else in the frontend holds a host: `manifest.ts` uses relative `start_url`, `scope`, `id`; the service worker
   (`public/sw.js`) is per origin and installs fresh on the new domain (no version bump needed); the CSP takes its
   origins from the env above. There is no `metadataBase`, sitemap or canonical link yet (3c landing page: add them from
   one `NEXT_PUBLIC_SITE_URL` when it is built).

Verify: `https://<domain>/ru/login` loads with a valid certificate; `https://www.<domain>/ru/login` and
`https://ort-platform-nu.vercel.app/ru/login?x=1` both answer 308 to `https://<domain>/ru/login(?x=1)`; browser console has
no CSP errors on a course page with images.
Rollback: remove the `redirects` block (redeploy); set the env back and redeploy. The `vercel.app` address never stops
working while the redirect is removed.

## 3. Backend address on Render

1. [owner] Render → backend service → Settings → **Custom Domains → Add** `api.<domain>`. The Hobby workspace includes
   2 custom domains (more cost $0.25/month each: ask the owner before adding a third).
2. [owner] Cloudflare DNS: `CNAME` `api` → `ort-platform-w77q.onrender.com`, **DNS only** (grey cloud). Render's
   Cloudflare guide allows "Proxied" after the certificate is issued; we keep DNS only, because a Cloudflare proxy adds a
   hop to `X-Forwarded-For` and `RATE_LIMIT_PROXY_HOPS` (see `IP_CHAIN.md`) would have to be measured again. No `AAAA`.
3. Render → Verify → wait for "Certificate issued".
4. Keep **Render Subdomain enabled** (the default). It is the fallback, and the uptime/maintenance workflows can keep using
   it until step 8.

Verify: `curl -s https://api.<domain>/health` shows the same `commit` as `https://ort-platform-w77q.onrender.com/health`.
Rollback: point `NEXT_PUBLIC_API_URL` back to the onrender address (redeploy Vercel); the custom domain can stay.

## 4. Backend environment on Render [agent with the Render dashboard; one save = one redeploy]

Change all of them in one edit, then save once:

| Variable | New value | Note |
|---|---|---|
| `ALLOWED_ORIGINS` | `https://<domain>,https://www.<domain>,https://ort-platform-nu.vercel.app` | CORS. This one wins; `BACKEND_CORS_ORIGINS` is read only when `ALLOWED_ORIGINS` is empty. Keep the old origin until the redirect (step 2.4) has run a week, then remove it |
| `FRONTEND_URL` | `https://<domain>` | Links in every email (reset, email change, invitations, enrollment forms, teacher and catalog emails) and the Google sign-in return address |
| `OAUTH_PUBLIC_BASE_URL` | `https://api.<domain>` | Google `redirect_uri` = this + `/api/v1/auth/google/callback`. Change only together with step 5 |
| `R2_PUBLIC_BASE_URL` | `https://img.<domain>` | Only after step 6 is Active |
| `EMAIL_FROM`, `EMAIL_PROVIDER`, `EMAIL_FROM_NAME` | see `EMAIL_DOMAIN.md` step 5 | Only after Brevo shows the domain authenticated |

No cookie needs a domain change: sign-in uses a bearer token, and the only cookie (the Google sign-in flow cookie) is
host-only on the API origin, `SameSite=Lax`, with `api.<domain>` same-site with `<domain>`. No `TrustedHost` list exists.

Verify: sign in on `https://<domain>` (password); the Network tab shows API calls to `https://api.<domain>` with
`access-control-allow-origin: https://<domain>`.
Rollback: put back the old values from step 0 and save.

## 5. Google sign-in [owner: Google Cloud Console]

Cross-reference `GOOGLE_SIGN_IN.md`.

1. Google Cloud Console → APIs & Services → Credentials → the OAuth client → **Authorized redirect URIs → add**
   `https://api.<domain>/api/v1/auth/google/callback`. Keep the onrender URI until the switch has worked for a week.
2. **Authorized JavaScript origins**: not used by our server-side flow (no Google script runs in the browser); add
   `https://<domain>` anyway only if Google asks for it.
3. OAuth consent screen → Branding → **Authorized domains**: add `<domain>`; set the home page and privacy policy links to
   `https://<domain>/ru` and `https://<domain>/ru/privacy`, and the app name to `<platform name>`. Google may ask to verify
   domain ownership through Search Console (a TXT record on Cloudflare).
4. Then step 4's `OAUTH_PUBLIC_BASE_URL` (one save).

Verify: `GOOGLE_SIGN_IN.md` "What to check" 1–4 with the new addresses (`redirect_uri_mismatch` = step 1 missing or a typo).
Rollback: set `OAUTH_PUBLIC_BASE_URL` back to the onrender origin (its URI is still listed at Google).

## 6. Images: R2 custom domain [owner: Cloudflare dashboard]

1. Cloudflare → R2 → the public bucket (`R2_BUCKET`) → Settings → **Custom Domains → Add** `img.<domain>` → Connect. The
   zone must be in the same Cloudflare account as the bucket (it is, after step 1). Wait for **Active**. Free; no
   lifecycle rules, Standard class (AGENTS.md hard rule 5).
2. [agent] Set `NEXT_PUBLIC_R2_PUBLIC_BASE_URL` on Vercel (step 2.3) and redeploy **first**, then `R2_PUBLIC_BASE_URL`
   on Render (step 4).
3. **Keep the bucket's `r2.dev` public access enabled.** Image URLs of questions, covers and assets are computed at read
   time (`files/storage.py` `media_url`, never stored), so they switch to `img.<domain>` at once. But Pages and
   Announcements store the author's Markdown and the rendered HTML (`pages.body_md`/`body_html`,
   `announcements.body_md`/`body_html`) with the full image URL of the time of upload: those keep the `r2.dev` address.
   They keep loading while `r2.dev` stays enabled (`next.config.ts` always allows `https://*.r2.dev`). One catch: the page
   sanitizer accepts only the current `R2_PUBLIC_BASE_URL` (and `/api/v1/media/`), so **re-saving** an old page or
   announcement would drop its `r2.dev` images. So, in the same session:
4. [agent] Rewrite the stored addresses once (Neon backup branch first, `backup-YYYY-MM-DD-before-img-domain`):
   ```sql
   -- <old> = the current R2_PUBLIC_BASE_URL without trailing slash, e.g. https://pub-xxxx.r2.dev
   SELECT count(*) FROM pages WHERE body_md LIKE '%<old>/%';
   SELECT count(*) FROM announcements WHERE body_md LIKE '%<old>/%';
   UPDATE pages SET body_md = replace(body_md, '<old>/', 'https://img.<domain>/'),
                    body_html = replace(body_html, '<old>/', 'https://img.<domain>/') WHERE body_md LIKE '%<old>/%' OR body_html LIKE '%<old>/%';
   UPDATE announcements SET body_md = replace(body_md, '<old>/', 'https://img.<domain>/'),
                            body_html = replace(body_html, '<old>/', 'https://img.<domain>/') WHERE body_md LIKE '%<old>/%' OR body_html LIKE '%<old>/%';
   ```
   The HTML is the server's own sanitized output; swapping one trusted prefix for another keeps it valid. `rev` is not
   bumped on purpose (no edit conflict for an author with the page open).
5. Only weeks later, and after the counts above are 0: optionally disable `r2.dev` public access.

Verify: Admin → Storage → "Run R2 check" passes and no longer warns about `r2.dev`; a question image and a course cover
load from `img.<domain>`; an old page with an image still shows it; `curl -I https://img.<domain>/img/<sha>.webp` = 200.
Rollback: set `R2_PUBLIC_BASE_URL` back to the `r2.dev` address (computed URLs follow at once). If step 4 ran, run the same
`UPDATE` with the two addresses swapped, or restore the two tables from the backup branch.

## 7. Email

`EMAIL_DOMAIN.md`, all of it (Brevo domain, one SPF record, DMARC `p=none`, Email Routing for `support@`, Render env,
header check). It can run before the rest: it only needs step 1.

## 8. Health check, uptime and maintenance workflows [agent; GitHub]

1. GitHub → repo → Settings → Secrets and variables → Actions → **Variables**: `API_ORIGIN` = `https://api.<domain>`,
   `WEB_ORIGIN` = `https://<domain>`. The workflows `uptime.yml` and `maintenance.yml` read them and fall back to today's
   addresses when they are not set, so no code change is needed.
2. If an outside pinger keeps Render awake (UptimeRobot or a Cloudflare Worker, `FIX_ROUND_2026-11-12.md` finding),
   point it at `https://api.<domain>/health`.
3. The deploy check (AGENTS.md hard rule 7, `DEPLOY.md` step 4) may keep using the onrender `/health` (same service);
   update the address in `AGENTS.md`, `DEPLOY.md`, `ROLLBACK.md`, `INCIDENT.md` in the docs commit (step 10).

Verify: Actions → Uptime → Run workflow → green; Maintenance → Run workflow (dry run) → green.
Rollback: delete the two variables.

## 9. Platform name (if it changed)

One commit: `common.appName` in `en.json`, `ky.json`, `ru.json` (also the installed app's name, `manifest.ts`),
`APP_NAME` in `backend/app/services/email_service.py`, `MFA_ISSUER` in `config.py` (shown in authenticator apps; existing
entries keep the old label until re-enrolled), `PROJECT_NAME` (API docs title). Google consent screen name: step 5.3.
Brevo sender name: `EMAIL_DOMAIN.md` step 5.

## 10. After the session

- [agent] Docs that name the old hosts (update the live instructions, leave historical phase docs as they are):
  `AGENTS.md` (§6 rule 7), `docs/HANDOFF_NEXT_AGENT.md`, `docs/runbooks/DEPLOY.md`, `GOOGLE_SIGN_IN.md`, `INCIDENT.md`,
  `IP_CHAIN.md`, `MAINTENANCE.md`; historical only: `PRODUCT_DECISIONS.md`, `phases/AUTH_SOCIAL_DESIGN.md`,
  `CHECKPOINT_8B.md`, `PERFORMANCE_AUDIT.md`, `PHASE_11_DESIGN.md`, `PHASE_5_DESIGN.md`.
- Code and tests with hosts: `.github/workflows/uptime.yml`, `maintenance.yml` (from repository variables since
  2026-11-13, fallback = today's hosts); `backend/tests/lms/test_storage_guard.py` and `frontend/e2e/security.spec.ts` use
  made-up `pub-*.r2.dev` addresses as fixtures (keep them; they test the r2.dev warning and the CSP);
  `backend/app/lms/files/smoke.py` recognises `r2.dev` on purpose. The e2e suite runs on `127.0.0.1` only.
- One week later: remove `https://ort-platform-nu.vercel.app` from `ALLOWED_ORIGINS` (the redirect never needs CORS) and
  the onrender redirect URI at Google. Keep the Render subdomain enabled.
- Record the domain and the date in `PRODUCT_DECISIONS.md` and `HANDOFF_NEXT_AGENT.md`.

## Order on the day (summary)

1 DNS → 7 email records (can start early) → 3 Render custom domain → 6 R2 custom domain → 2.1–2.3 Vercel domain and env
(redeploy) → 5.1–5.3 Google URIs → 4 Render env (one save) → 6.4 SQL rewrite → 2.4 `vercel.app` redirect → 8 workflow
variables → 9 name → 10 docs. After each step, its "Verify"; on failure, its "Rollback".

## Sources (checked 2026-11-13)

- Vercel, add a custom domain: https://vercel.com/docs/domains/working-with-domains/add-a-domain
- Vercel, redirects (host condition): https://vercel.com/docs/routing/redirects ;
  deploying and redirecting domains: https://vercel.com/docs/domains/working-with-domains/deploying-and-redirecting
- Render, custom domains (plan limits, AAAA, Render subdomain): https://render.com/docs/custom-domains
- Render, Cloudflare DNS (CNAME, DNS only, Full mode): https://render.com/docs/configure-cloudflare-dns
- Cloudflare R2, public buckets and custom domains: https://developers.cloudflare.com/r2/buckets/public-buckets/
- Cloudflare Email Routing: https://developers.cloudflare.com/email-routing/get-started/enable-email-routing/
