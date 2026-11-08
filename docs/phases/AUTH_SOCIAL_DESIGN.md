# Sign-up and login redesign, Google and Apple sign-in (owner round 2026-11-09, item 3)

Design only; nothing here is built yet. Brief: `docs/phases/OWNER_FEEDBACK_2026-11-09.md` item 3. Ground rules as always:
ORT untouched, every string in `en.json` / `ky.json` / `ru.json`, authorization from the database, no secrets in the
repository, `backend/.env` never read by an agent. Env names in section 7 are the only thing the owner has to set.

Reading order for the implementers: section 0 (how it fits today's auth), then your slice in section 10, then the parts
of sections 1–9 it names.

## 0. Today, and what changes

Today (`backend/app/api/v1/endpoints/auth.py`): the browser POSTs JSON to `/auth/login`, `/auth/verify-email` or
`/auth/mfa` and receives `TokenResponse {access_token, user}`; `auth-context.tsx` `finishLogin()` puts the token in
`localStorage["ort_token"]`. Every password sign-in ends in `_sign_in(user)` (`auth.py:159`), which answers
**403 `mfa_required` + challenge** for an account with two-step login and a token otherwise. Sign-up (`/auth/register`)
needs `ageBand` and the accepted policy ids; `privacy.apply_age_band(..., source="signup")` sets `consent_state`
(`pending_guardian` under 14, which the consent gate in `core/deps.get_lms_user` enforces from the first request).
`users.password_hash` is NOT NULL; accounts without a usable password use `UNUSABLE_PASSWORD_HASH = "!"`
(`privacy/anonymize.py:46`, `ort/seed.py:65`).

What this design adds, in one sentence: Google (and, switched off, Apple) prove *who the person is* on the backend; the
result is a short-lived signed **login ticket** that the browser trades at `POST /auth/oauth/complete` for exactly the
same `TokenResponse` (or the same `mfa_required` challenge) that `/auth/login` gives today. Nothing downstream of
`_sign_in` changes: MFA, `last_login_at`, token versions, the consent gate and the student/teacher shells all see an
ordinary sign-in.

```
browser                     backend (Render)                           Google
  |  GET /auth/google/start  |                                            |
  |------------------------->| state, PKCE verifier, nonce -> cookie       |
  |  302 accounts.google.com |------------------------------------------->|
  |                          |         (user picks an account)            |
  |  GET /auth/google/callback?code&state   <------------------------------|
  |------------------------->| cookie == state? code+verifier -> tokens    |
  |                          | verify ID token (JWKS), email_verified     |
  |                          | DB: identity / verified email / new        |
  |  302 FRONTEND/{lang}/oauth-callback#t=<ticket>&r=<redirect>           |
  |                                                                       |
  |  POST /auth/oauth/complete {ticket[, ageBand, policyVersionIds, displayName]}
  |------------------------->| ticket valid? recompute mode from DB        |
  |  200 TokenResponse  |  403 mfa_required  |  422 oauth_profile_required|
```

## 1. Google: server-side authorization code flow

### 1.1 Routes (all on the backend, `app/lms/oauth/`)

| Route | Policy (`route_inventory`) | Purpose |
|---|---|---|
| `GET /api/v1/auth/providers` | `public` | `{"google": bool, "apple": bool}`: which buttons to show (section 7.2) |
| `GET /api/v1/auth/google/start?lang=ru&redirect=/ru/courses/x` | `public+ratelimit` | sets the flow cookie, 302 to Google |
| `GET /api/v1/auth/google/callback?code&state` (or `?error=access_denied&state`) | `public+ratelimit` | checks the cookie, exchanges the code, verifies the ID token, decides login / link / sign-up, 302 to the frontend |
| `POST /api/v1/auth/oauth/complete` | `public+ratelimit` | trades the ticket for a session (section 1.6) |
| `GET /api/v1/auth/apple/start`, `POST /api/v1/auth/apple/callback` | `public+ratelimit` | section 6; 404 `oauth_not_configured` while off |

All plain `def` (worker thread, like the rest of `auth.py`). New package `app/lms/oauth/` (`service.py`, `google.py`,
`apple.py`, `tickets.py`, `router.py`, `policies.py` with `OAUTH_POLICIES` merged into `ROUTE_POLICIES`), router mounted
under `/auth` next to the existing one. `auth.py` itself changes in one place: `_sign_in` and `_token_response` become
importable (they already are; no move).

### 1.2 `start`

1. Refuse 404 `oauth_not_configured` unless `google_enabled()` (section 7.1).
2. Rate limit `OAUTH_START_IP_10M` (every hit counts).
3. `lang` must be `en|ky|ru` (default `ky`); `redirect` must pass the server-side copy of the frontend's `safeRedirect`
   rule (starts with `/`, not `//` or `/\`, no control or non-ASCII characters, at most 512 chars), else dropped. It
   lives only in our cookie, never in Google's `state`.
4. Generate `state` (32 random bytes, urlsafe), PKCE `code_verifier` (43–128 chars, urlsafe), `nonce` (32 random bytes).
   `code_challenge = base64url(sha256(verifier))`, method `S256`.
5. Set cookie `ort_oauth` = **encrypted and authenticated** blob (AES-GCM with a key derived from `SECRET_KEY`, the same
   `_derive(secret, purpose)` HKDF helper `app/lms/mfa/service.py:72` uses; purpose `b"oauth-flow"`; the previous
   SECRET_KEY is tried too, as everywhere) of `{provider:"google", state, verifier, nonce_hash: sha256(nonce), lang,
   redirect, exp: now+600}`. Attributes: `HttpOnly; Path=/api/v1/auth; SameSite=Lax; Max-Age=600; Secure` (Secure
   omitted when the request scheme is `http` **and** `not is_production()`, so `http://127.0.0.1:8000` works locally).
   The cookie is set on the Render origin and read back on the Render origin; the Vercel frontend never sees it.
6. 302 to `https://accounts.google.com/o/oauth2/v2/auth` with `client_id, redirect_uri = {OAUTH_PUBLIC_BASE_URL}/api/v1/auth/google/callback,
   response_type=code, scope="openid email profile", state, nonce, code_challenge, code_challenge_method=S256,
   prompt=select_account, access_type=online`. No `include_granted_scopes`, no refresh token, no `hd`.

**Why a cookie and not a table.** The whole point of `state` is to bind the callback to the browser that started the
flow; only a cookie does that. A DB row keyed by `state` would still need a cookie to say "this browser owns that row",
so it would add a table, a cleanup job and a Neon round trip without adding security. The cookie is encrypted, so the
PKCE verifier never travels in clear, and signed, so it cannot be forged; it expires in 10 minutes. No new table for the
flow. (The identity link itself does need a table: section 2.)

### 1.3 `callback`

Order matters; every refusal is a 302 to `{FRONTEND_URL}/{lang}/login?oauth_error=<code>` (section 1.7), **never** a page
rendered by the backend and never a URL carrying an email, name or token.

1. Rate limit `OAUTH_CALLBACK_IP_10M` (every hit counts, before anything else).
2. Read and decrypt the cookie; missing, expired, undecryptable, or `provider != "google"` → `oauth_expired`. Delete the
   cookie in the same response (every exit of `callback` clears it: one cookie, one callback).
3. `state` query param must equal the cookie's `state` (`hmac.compare_digest`) → else `oauth_state_mismatch`.
4. `error=access_denied` (the person pressed Cancel) → `oauth_denied`; any other `error` → `oauth_provider_error`.
5. POST `https://oauth2.googleapis.com/token` with `code, client_id, client_secret, redirect_uri (identical string),
   grant_type=authorization_code, code_verifier`; `httpx` (already a dependency), timeout 8 s, no retries. Non-200 or no
   `id_token` → `oauth_provider_error` (the body is never logged; the status code is).
6. Verify the ID token with PyJWT + `cryptography` (both present): `jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs",
   cache_keys=True, lifespan=21600)` held as a module singleton; on an unknown `kid` the client fetches again at most
   once (PyJWKClient does this). `jwt.decode(id_token, key, algorithms=["RS256"], audience=GOOGLE_OAUTH_CLIENT_ID,
   issuer=["https://accounts.google.com", "accounts.google.com"], leeway=60, options={"require": ["exp","iat","sub","aud","iss"]})`.
   Then `sha256(claims["nonce"]) == cookie.nonce_hash` (constant-time), else `oauth_state_mismatch`.
7. **`claims.get("email_verified") is True` and `claims.get("email")` present**, else `oauth_email_unverified`. We never
   match or create anything on an unverified email. (Google sends `email_verified` as a boolean; a string `"true"` is
   refused on purpose: for Google it is always a boolean.)
8. Decide the mode (section 2.3) in one transaction and build the ticket (section 1.5).
9. 302 to `{FRONTEND_URL}/{lang}/oauth-callback#t=<ticket>&r=<redirect>` (`r` only when the cookie had one).

Why the backend owns the callback URL: Google must redirect to the party that holds the client secret and the PKCE
verifier cookie, and that is Render. A frontend callback (Vercel) would have to forward `code` + `state` to the backend
and could not present the cookie, so the binding to the browser would be lost or would need the Next.js server to hold
secrets, which it does not today. Google redirect URIs therefore point at `https://ort-platform-w77q.onrender.com`.

### 1.4 How the session reaches the frontend (different origins)

The frontend is on Vercel, the backend on Render; a cookie set by Render is not readable on Vercel, and a session JWT in
a URL query string would land in Vercel's request logs, browser history and any `Referer`. Comparison with today: the
login token comes back in a **POST response body** and is stored by JS in `localStorage`. The design keeps that:

- the callback redirect carries only a **ticket in the URL fragment** (`#t=...`). Fragments are never sent to any server
  (not to Vercel, not in `Referer`, not in Render logs), so nothing is logged. The callback page reads `location.hash`
  and immediately `history.replaceState`s it away, so it does not stay in history either;
- the ticket is not a session: it is a 10-minute, single-purpose HS256 JWT (section 1.5). `get_lms_user` already rejects
  any token with a `typ` claim (`deps.py:56`), so a ticket presented as a Bearer token is refused;
- the browser POSTs the ticket to `/auth/oauth/complete` and receives the **same `TokenResponse`** as `/auth/login`.
  `auth-context.tsx` gets one new function `completeOAuth(ticket, extras?)` that calls `finishLogin(data)`.

Alternatives rejected: (a) session JWT in the fragment: works for plain users but then the MFA challenge and the
new-user age step would need a second, different handoff; one ticket, one POST covers all three. (b) a one-time code in
the query string plus a DB table: logged by Vercel, needs a table and cleanup, no gain over the fragment.

### 1.5 The ticket (`app/lms/oauth/tickets.py`)

HS256 JWT, key `_derive(SECRET_KEY, b"oauth-ticket")` (previous key accepted for reading), claims:
`{typ:"oauth_ticket", jti, iat, exp: iat+600, provider, sub, email, name, mode: "login"|"link"|"signup", uid?}`.
`email` and `name` are in the ticket so the callback page can show "Signed in with Google as …" and prefill the name
without another request; the frontend reads the payload the way `tokenRefresh.ts` reads `exp` (base64 decode, no
verification: display only). `mode` is a hint for the UI; `complete` **recomputes** it from the database (section 1.6).
No replay store: a ticket is harmless to replay by its owner (same person, same session) and lives only in the fragment
of the person's own browser for at most 10 minutes; someone who can read it can read `localStorage` too. Same reasoning
as the MFA challenge, which is also a stateless JWT.

### 1.6 `POST /auth/oauth/complete`

Body `{ticket, ageBand?, policyVersionIds?, displayName?}` (extra fields forbidden). Steps:

1. Rate limits: `OAUTH_COMPLETE_IP_10M` every hit; failures also on `OAUTH_COMPLETE_IP_FAIL_10M` (`_check_failures` first,
   `record_failures` on 401/422, the `auth.py` pattern).
2. Decode the ticket (signature, `exp`, `typ`), else 401 `oauth_ticket_invalid`.
3. Recompute the mode in a transaction:
   - identity `(provider, sub)` exists → **login** with its user;
   - else a user with `email == ticket.email` (lowercased) exists, not deleted, not a test student → **link**;
   - else → **signup**.
   The ticket's `mode` is ignored; two tabs or a replay cannot create a second account or re-link.
4. **login**: user `deleted_at` → 401 `oauth_ticket_invalid`; `disabled_at` → 403 `account_disabled` (today's code);
   update `user_identities.last_login_at` and, if the provider's email changed, `user_identities.email` (never
   `users.email`); then `return _sign_in(user)`. **This is where Google joins the MFA gate:** `_sign_in` answers 403
   `mfa_required` + challenge for a platform admin (or anyone) with two-step login; the browser shows the existing
   `MfaStep` and finishes with `POST /auth/mfa` exactly as after a password. `ADMIN_MFA_REQUIRED` enrolment
   (`mfa_gate.must_enroll`) is unchanged because it runs in `get_lms_user` on the first authenticated request.
5. **link**: lock the user row (`privacy._lock_user` style `SELECT … FOR UPDATE`); disabled → 403 `account_disabled`
   (no link written); insert the identity; if `users.email_verified` is False (an unconfirmed self-registration), the
   mailbox owner has now proven the address through Google but the stored password was chosen by *someone* who never
   confirmed it: set `password_hash = UNUSABLE_PASSWORD_HASH`, clear `email_code_*`, `email_verified = True`,
   `token_version += 1` (the person sets a password later with "Forgot password", which works for any account with a
   verified email). Audit `auth.identity.linked` (actor = user, target user, details `{provider}`; never the email).
   Then `_sign_in(user)`. Existing password users keep password login: nothing touches a usable `password_hash`.
6. **signup**: `ageBand` missing → 422 `oauth_profile_required` (the UI then shows the age step; a first POST without
   extras is the normal way to learn the mode). With extras: validate exactly as `/auth/register` does
   (`ageBand in AGE_BANDS` else 422 `age_band_required`; `privacy.accepted_policies(db, band, ids)` else 422
   `policy_not_accepted`; `displayName` trimmed, 1–200 chars, default = Google `name` or the local part of the email).
   Create `User(id="usr_…", email, password_hash=UNUSABLE_PASSWORD_HASH, email_verified=True, display_name, locale=lang,
   created_at)`, `privacy.apply_age_band(db, user, band, accepted, source="signup", locale=lang, due_at=privacy.now())`,
   insert the identity, commit. On `IntegrityError` (two tabs raced): rollback, reselect by `(provider, sub)` and
   continue as **login**. Audit `auth.identity.signup` (details `{provider, age_band}`). Then `_sign_in(user)` (a brand
   new account never has MFA, so this is a token). Under 14: the response is a token as for email sign-up, and the
   frontend goes to `/{lang}/privacy`, where the gate keeps the account until a parent consents (unchanged).
7. Response: `TokenResponse` (200), or 403 `mfa_required`, or the 4xx codes above. `last_login_at` is set by `_sign_in`.

### 1.7 Error codes (frontend `auth.errors.<code>` keys; section 8.5)

`oauth_not_configured`, `oauth_expired`, `oauth_state_mismatch`, `oauth_denied`, `oauth_provider_error`,
`oauth_email_unverified`, `oauth_ticket_invalid`, `oauth_profile_required` (never shown; it switches the UI to the age
step), plus today's `account_disabled`, `age_band_required`, `policy_not_accepted`, `rate_limited`, `mfa_required`.
The login page reads `?oauth_error=` once, shows the translated text in its existing alert and strips the parameter.

## 2. Account linking: `user_identities`

### 2.1 Why a table, not columns on `users`

`users` is loaded on every request (`get_lms_user` does `db.get(User, id)`); two providers times (subject, email,
linked_at, last_login_at) would add eight nullable columns to that hot row for a feature most students will not use.
A table gives the two constraints the rules need (one account per provider subject; one provider link per user) as
plain UNIQUE constraints, fits the privacy registry's `delete_row` action for FK tables, and adds Apple with no schema
change. Chosen: table.

### 2.2 Schema, migration `0029_user_identities`

```
user_identities
  id              uuid PK
  user_id         varchar(64) NOT NULL  FK users.id ON DELETE CASCADE
  provider        varchar(16) NOT NULL  CHECK (provider IN ('google','apple'))
  subject         varchar(255) NOT NULL          -- the provider's stable user id (`sub`), never the email
  email           varchar(320) NULL              -- the provider's email at link time, lowercased; informational
  email_verified  boolean NOT NULL               -- always true today (a false value is never written; kept for audit)
  linked_at       timestamptz NOT NULL
  last_login_at   timestamptz NULL
UNIQUE (provider, subject)       -- uq_user_identities_provider_subject
UNIQUE (user_id, provider)       -- uq_user_identities_user_provider: one Google account per user (decision D3)
```

Additive, no data step, downgrade drops the table. `down_revision` = the head at merge time: `0028_…` if the
performance design's index migration lands first, else `0027_exam_course_link`; the implementer checks `alembic heads`
before writing it. Model in `app/lms/oauth/models.py`, imported where the other LMS models are so SQLite `create_all`
sees it. Privacy registry (`app/lms/privacy/registry.py`): `Entry("user_identities", "email", "contact", "delete_row", True)`,
`Entry("user_identities", "subject", "identifier (provider)", "delete_row")`, `*_refs("user_identities", "user_id", action="delete_row")`;
anonymize deletes the rows; the export lists `provider, linked_at, last_login_at` (not the subject).

### 2.3 Rules (also the test matrix of section 9)

| Google says | Database has | Result |
|---|---|---|
| `sub` S | identity (google, S) → user U | sign in as U (`_sign_in`: MFA if enabled). U disabled → refuse `account_disabled`. U deleted → `oauth_ticket_invalid` |
| verified email E, no identity | user with email E, verified | link, sign in |
| verified email E, no identity | user with email E, **unverified** self-registration | link, drop the unconfirmed password (1.6 step 5), sign in |
| verified email E, no identity | user with email E, disabled | refuse `account_disabled`, no link, audit `auth.identity.refused` (actor = that user) |
| verified email E, no identity | user is a test student | treated as no match → sign-up (its emails are synthetic; cannot happen with a real Google account) |
| verified email E, no identity | nobody | sign-up after the age step |
| `email_verified` false or missing | anything | refuse `oauth_email_unverified` at the callback; nothing is read from the database |
| `sub` S, email changed at Google | identity (google, S) | sign in; `user_identities.email` updated; `users.email` unchanged |

Never: match on an unverified email, change `users.email` from a provider, lower an age band, issue a session to a
disabled account, link while disabled. Password users keep their password; Google-only users can add one via "Forgot
password" (their email is verified). Unlinking and linking a second provider from the person page are **deferred**
(decision D8); the admin user page may list the providers (section 10, integration slice, optional).

## 3. New users through Google: age and consent

Exactly the rules of `/auth/register`, applied at `complete` (section 1.6 step 6), with the same helpers
(`privacy.AGE_BANDS`, `accepted_policies`, `apply_age_band(source="signup")`). What is stored: `users.age_band`,
`consent_state` (`ok`, or `pending_guardian` with `consent_due_at = now` under 14), `consent_records` for privacy and
terms (14+), `locale`. Not stored: Google's picture, locale or `hd`. The name comes from Google's `name` claim and is
**editable** on the step before the account exists; afterwards it is the ordinary `display_name`.

The extra screen (frontend `/{lang}/oauth-callback`, section 8.3): "Almost done" with the Google email as a read-only
line, the name field prefilled, the age row (the same three bands as the sign-up form), the policy checkbox from 14 up,
one button. "I am a parent" link → `18_plus`, then `/{lang}/parent`, as on `/register`. Under 14 → `/{lang}/privacy`.

## 4. Platform admins and two-step login

Google changes nothing about MFA because the only path to a token is `_sign_in` → (`mfa_required` → `POST /auth/mfa`) →
`_token_response`. Concretely, in section 1.6 step 4 the call `return _sign_in(user)` is the join point; the frontend
callback page handles 403 `mfa_required` by rendering the existing `MfaStep` with `details.challenge`, as `login/page.tsx:51`
does. An admin who has not enrolled yet still gets 403 `mfa_enrollment_required` from `get_lms_user` on admin routes.
Tests in section 9 prove an admin with MFA never receives a token from `/auth/oauth/complete` and that the ticket
cannot be used as a Bearer token.

## 5. Rate limits, audit, route policies

Rate limits (`app/lms/core/ratelimit.py`, next to the Phase 11 S4 block):

```
OAUTH_START_IP_10M        = Limit("oauth_start_ip_10m", 60, 600, is_ip_rule=True)     # every hit
OAUTH_CALLBACK_IP_10M     = Limit("oauth_callback_ip_10m", 60, 600, is_ip_rule=True)  # every hit (Google round trips cost us a token call)
OAUTH_COMPLETE_IP_10M     = Limit("oauth_complete_ip_10m", 120, 600, is_ip_rule=True) # every hit
OAUTH_COMPLETE_IP_FAIL_10M= Limit("oauth_complete_ip_fail_10m", 30, 600, is_ip_rule=True)  # failures only (bad ticket, bad profile)
```
A school signing in from one address: 60 Google sign-ins per 10 minutes per address is the ceiling; password login is
unaffected by these buckets. The `/auth/mfa` step keeps its own rules.

Audit (`audit.record`, actor required): `auth.identity.linked` (actor = the user, details `{provider}`),
`auth.identity.signup` (`{provider, age_band}`), `auth.identity.refused` (`{provider, reason: "disabled"}`, only when a
user row exists). Ordinary Google logins are not audited, like password logins (`last_login_at` only). Never an email,
name or subject in `details`. Refusals without a user (unverified email, state mismatch) get a request log line with
the code only (`core/request_log.py` already drops query strings and bodies, so the authorization code is never logged).

Route policies: section 1.1 table; `POLICY_NAMES` already has `public` and `public+ratelimit`; `tests/test_route_inventory`
style gate passes once `OAUTH_POLICIES` is merged. The consent gate (`privacy/gate.py GATE_ROUTES`) needs no entry: these
routes are unauthenticated.

## 6. Apple: built, switched off

Same `user_identities` table (`provider='apple'`), same ticket, same `complete`. Differences:

- **Flag**: `APPLE_SIGN_IN_ENABLED` (default `false`) **and** all four Apple settings present; otherwise `/auth/providers`
  says `apple: false`, the start route answers 404 `oauth_not_configured`, the button is not rendered.
- **Authorize**: `https://appleid.apple.com/auth/authorize` with `response_type=code` (not the hybrid `code id_token`:
  the ID token comes from the token endpoint, as with Google), `response_mode=form_post` (required by Apple whenever
  `scope` has `name` or `email`), `scope="name email"`, `state`, `nonce`; PKCE is sent the same way as for Google.
- **Callback is a POST** (`application/x-www-form-urlencoded`: `code, state, id_token?, user?`). A cross-site POST does not
  carry a `SameSite=Lax` cookie, so the Apple flow cookie is `SameSite=None; Secure` (hence https only: no local Apple
  testing without a tunnel; the unit tests cover it). Everything else (state, nonce, code exchange) as Google.
- **Client secret** is a JWT the backend signs per request with the `.p8` key: ES256, `iss=APPLE_TEAM_ID`,
  `sub=APPLE_CLIENT_ID` (the Services ID), `aud=https://appleid.apple.com`, `iat`, `exp=iat+300`, header `kid=APPLE_KEY_ID`.
  Token endpoint `https://appleid.apple.com/auth/token`; JWKS `https://appleid.apple.com/auth/keys`; issuer
  `https://appleid.apple.com`; audience = Services ID.
- **Email**: `email_verified` may arrive as the string `"true"` → accept `True` or `"true"`. `is_private_email` → a relay
  address `…@privaterelay.appleid.com`: it never matches an existing account (fine: a new account), and our emails reach
  it only if the sending domain is registered with Apple (owner list below). Store the relay address as `users.email`.
- **Name only on the first callback** (`user` form field, JSON `{name:{firstName,lastName}, email}`); later callbacks have
  none. The callback puts it in the ticket's `name`; the signup step shows it editable. Nothing else needs it.
- **Account deletion rule**: Apple requires apps to offer sign-in revocation; our privacy deletion request covers the
  account, and the identity row is deleted with it (registry `delete_row`). Calling Apple's revoke endpoint is deferred.

Owner must create in a paid Apple Developer Program account (yearly fee; **do not buy before the owner says so**):
1. Certificates, Identifiers & Profiles → Identifiers → **App ID** (type App, e.g. `kg.ortplatform.web`), capability
   "Sign in with Apple" enabled (primary).
2. Identifiers → **Services ID** (this is `APPLE_CLIENT_ID`, e.g. `kg.ortplatform.web.signin`), "Sign in with Apple"
   configured with: primary App ID = the one above; **Domains**: `ort-platform-w77q.onrender.com`; **Return URLs**:
   `https://ort-platform-w77q.onrender.com/api/v1/auth/apple/callback`. (Apple refuses `http://` and `localhost`.)
3. Keys → **Key** with "Sign in with Apple" enabled, linked to the App ID; download the `.p8` **once** (Apple never shows
   it again) → `APPLE_PRIVATE_KEY`; note the **Key ID** → `APPLE_KEY_ID`.
4. Membership page → **Team ID** → `APPLE_TEAM_ID`.
5. Optional, for emails to relay addresses: Services → "Sign in with Apple for Email Communication" → register the
   sending domain (`EMAIL_FROM`'s domain) and the from address; SPF must pass.
6. When a custom domain replaces the Render address, update Domains and Return URLs (step 2) and `OAUTH_PUBLIC_BASE_URL`.

## 7. Configuration and the owner's Google Cloud Console steps

### 7.1 Env vars (backend only; `app/core/config.py`; nothing with a secret ever reaches the browser)

```
OAUTH_PUBLIC_BASE_URL: str = ""            # the backend's own public origin, e.g. https://ort-platform-w77q.onrender.com
                                           # (local: http://127.0.0.1:8000). redirect_uri = this + /api/v1/auth/<p>/callback.
                                           # Explicit on purpose: never derived from Host/X-Forwarded headers.
GOOGLE_SIGN_IN_ENABLED: bool = True        # the switch; effective only with the two values below
GOOGLE_OAUTH_CLIENT_ID: str = ""
GOOGLE_OAUTH_CLIENT_SECRET: str = ""
APPLE_SIGN_IN_ENABLED: bool = False
APPLE_CLIENT_ID: str = ""                  # Services ID
APPLE_TEAM_ID: str = ""
APPLE_KEY_ID: str = ""
APPLE_PRIVATE_KEY: str = ""                # .p8 PEM; newlines as \n in Render's env editor
OAUTH_FLOW_TTL_SECONDS: int = 600          # the cookie and the ticket
# test and e2e hooks, refused in production unless they are the defaults (like refuse_unsafe_secret_keys):
GOOGLE_OAUTH_AUTHORIZE_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_JWKS_URL: str = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_OAUTH_ISSUERS: str = "https://accounts.google.com,accounts.google.com"
```
`google_enabled() = GOOGLE_SIGN_IN_ENABLED and CLIENT_ID and CLIENT_SECRET and OAUTH_PUBLIC_BASE_URL and FRONTEND_URL`;
`apple_enabled()` likewise with the four Apple values. `FRONTEND_URL` (exists) is the only allowed redirect base after
the callback. A startup check (next to `refuse_unsafe_secret_keys`) refuses production with non-default Google URLs.
`.env.example`, if the repo has one, gains the names with empty values; `backend/.env` is the owner's.

### 7.2 `GET /auth/providers`

`{"google": true|false, "apple": true|false}`; `Cache-Control: public, max-age=300`. The frontend fetches it once per
page load of the auth screens (cached in module memory for the tab) and renders only the buttons that are `true`. With
no keys set, the screens look exactly as if the feature did not exist: no "or" divider either (section 8).

### 7.3 Google Cloud Console, step by step (owner)

1. `console.cloud.google.com` → project selector → **New project** "ORT Platform" (or reuse one).
2. **APIs & Services → OAuth consent screen** (Google now calls it "Google Auth Platform → Branding / Audience"):
   User type **External**; app name "ORT Platform" (what the Google screen shows), user support email = the owner's,
   developer contact = the owner's. App logo optional (adding one can trigger a review: skip for now).
   **Scopes**: add `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile` only (all non-sensitive: no
   verification review needed). **Audience**: while **Testing**, only the listed **test users** (up to 100 addresses) can
   sign in: add the owner's and the testers' Gmail addresses. For launch press **Publish app**; with these three scopes
   Google publishes without review. Caveat to check in the console: the branding's home page / privacy policy URLs
   must be on an **authorized domain** the owner controls; `vercel.app` and `onrender.com` cannot be verified as the
   owner's domain. If Google insists, the consent screen shows the Render host as the app's identity until a custom
   domain exists; sign-in still works. (Open question Q2.)
3. **Credentials → Create credentials → OAuth client ID**, application type **Web application**, name "ORT backend".
   **Authorized JavaScript origins** (not used by this server-side flow, harmless to add for future browser-side use):
   `https://ort-platform-nu.vercel.app`, `http://localhost:3000`.
   **Authorized redirect URIs** (exact strings; these are what the backend sends as `redirect_uri`):
   - `https://ort-platform-w77q.onrender.com/api/v1/auth/google/callback`
   - `http://127.0.0.1:8000/api/v1/auth/google/callback`
   - `http://localhost:8000/api/v1/auth/google/callback`
4. Copy the **Client ID** and **Client secret**. Render → the backend service → Environment:
   `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `OAUTH_PUBLIC_BASE_URL=https://ort-platform-w77q.onrender.com`
   (`FRONTEND_URL` must already be `https://ort-platform-nu.vercel.app`). Local `backend/.env`: the same two keys (a
   separate "local" OAuth client is cleaner but the same client works since both redirect URIs are listed),
   `OAUTH_PUBLIC_BASE_URL=http://127.0.0.1:8000`, `FRONTEND_URL=http://localhost:3000`.
5. Check: `GET https://ort-platform-w77q.onrender.com/api/v1/auth/providers` answers `{"google": true, "apple": false}`
   and the button appears on `/ru/login`.

Nothing in the frontend needs the client ID: `NEXT_PUBLIC_*` gains no variable.

## 8. UI

### 8.1 Layout: `components/auth/AuthSplit.tsx`

One shared component for `/register`, `/login`, `/forgot-password`, `/reset-password`, `/confirm-email` and the new
`/oauth-callback`. Desktop (≥ 1024 px): two columns; **left** the form column (max width 440 px, centred vertically,
`AuthHeader`'s language switcher top-right of the column, brand mark top-left); **right** `AuthIllustration` filling the
column. 1440 and 1920 px: the illustration scales with `viewBox`, the form column stays 440 px. **Phone (< 1024 px)**:
the illustration is a header band of about 140 px (mountain ridge and a small mascot, `Mascot size={72}`), the form
below with 16 px gutters. No horizontal scroll at 375 px. Light theme only, as the rest of the auth pages.

### 8.2 `components/auth/AuthIllustration.tsx`

Inline SVG, student palette (`docs/phases/STUDENT_UI_DESIGN.md` §1.1): sky gradient `#DFF1FF → #F5FBFF`, far ridge
`#13698F` at 35 % opacity, near ridge `#0E4A6B → #13698F` gradient, snow caps `#FFFFFF`, a soft sun `#FDE68A` with a
`#F59E0B` rim at 30 %, two cloud shapes white at 70 %, a ground band `#EAF4FE`, a few `#D4E9FD` dots as stars/snow. Simple
`path`/`circle`/`ellipse` shapes only; nothing copied. The mascot (`components/ui/Mascot.tsx`, `public/mascot/*.webp`)
sits on the ground band, `pose` per screen: `hello` on sign-up, `reading` on login, `thinking` on forgot/reset password,
`encouraging` on the Google "Almost done" step, `celebrating` on confirm-email. Decorative: `alt=""`, `aria-hidden` on
the SVG. `prefers-reduced-motion`: no animation at all (none planned anyway). `eager` on the auth pages (first paint).

### 8.3 The form column, per screen

- **Sign-up** `/register`: title `auth.signUpTitle`, subtitle `auth.signUpSubtitle`; `Continue with Google` and (when on)
  `Continue with Apple` as full-width secondary buttons with the provider mark (inline SVG, monochrome is acceptable;
  Google's own brand rules allow the standard "G" at the left), an "or" divider, then **name, email, password**, the age
  row, the policy checkbox (14+), one primary button `auth.signUpButton`, the link to login, the "I am a parent" link
  under the form. The phone field is removed (D6). The age pre-screen (`AgeButtons` before the form, `register/page.tsx:106`)
  is gone: **the form is the first thing on the page**. Why the age question stays at all: `/auth/register` needs the band
  and the under-14 gate must hold from the first request (PHASE_11 design); asking it afterwards would create accounts
  with no band and no gate. It becomes one compact row inside the form (three pills, `privacy.age.*` texts), not a
  questionnaire. The email code step (`VerifyEmailStep`) stays as step 2 inside the same column.
  Provider button = `<a href="{API}/api/v1/auth/google/start?lang=..&redirect=..">` rendered as a button: a link, not a
  form POST, because the frontend CSP has `form-action 'self'` (`next.config.ts:35`) and a cross-origin form would be
  blocked; a navigation is not subject to it.
- **Login** `/login`: title, subtitle, provider buttons, "or", email + password, "Forgot password?" right-aligned, one
  primary button, link to sign-up. `MfaStep` and `VerifyEmailStep` render inside the same column as today. Shows
  `?oauth_error=` once (section 1.7).
- **Forgot password**: title, subtitle, email, one button, back-to-login link; no provider buttons (a Google-only user
  is told, in the subtitle, that a Google account can simply continue with Google).
- **Google callback** `/oauth-callback` (new, `(auth)` group): reads `#t` and `#r`, strips the hash, POSTs the ticket
  with no extras. 200 → session, go to `safeRedirect(r)` or `/{lang}/courses` (under 14 → `/{lang}/privacy`). 403
  `mfa_required` → `MfaStep`. 422 `oauth_profile_required` → **"Almost done"**: `Signed in with Google as {email}`,
  name (prefilled, editable), age row, policies, parent link, one button → POST again with extras. Any other error →
  the alert with a "Back to login" link. No ticket in the hash → straight to `/login`. While waiting: the illustration
  and `auth.oauth.finishing`.

Reused as is: `SignUpFields` (`SignUpNameInput`, `SignUpEmailInput`, `SignUpPasswordInput`, `PolicyAcceptField`,
`useOwnPolicies`), `AgeButtons` (restyled to a row; or a new `AgeRow` if the button variant is too large),
`VerifyEmailStep`, `MfaStep`, `safeRedirect`, `useBackendWarmup`.

### 8.4 "No questionnaire before sign-up": what the current page asks, and where it goes

| Today, before or in the form | After |
|---|---|
| Age band screen before the form ("How old are you?" three big buttons + "I am a parent") | one inline row inside the form; parent link under the form |
| Name, **phone**, email, password | name, email, password; phone removed (the schema already allows no phone) |
| Policy checkbox (14+) | unchanged, inside the form |
| Nothing else is asked before the form; the help/onboarding pages after sign-in are untouched | — |

### 8.5 i18n keys (all three files; parity script must pass)

```
auth.continueWithGoogle, auth.continueWithApple, auth.orDivider, auth.parentCta,
auth.ageRowLabel,                       # "Your age" (the three values reuse privacy.age.under_14 / 14_17 / 18_plus)
auth.forgotGoogleHint,                  # "Signed up with Google? Just continue with Google on the login page."
auth.oauth.finishing, auth.oauth.completeTitle, auth.oauth.completeSubtitle, auth.oauth.signedInAs,
auth.oauth.useAnotherAccount, auth.oauth.backToLogin,
auth.errors.oauth_not_configured, auth.errors.oauth_expired, auth.errors.oauth_state_mismatch,
auth.errors.oauth_denied, auth.errors.oauth_provider_error, auth.errors.oauth_email_unverified,
auth.errors.oauth_ticket_invalid
```
Removed keys: none required (`auth.phone*` may stay for the person page). Google's and Apple's names appear only inside
these strings as product names, which their brand guidelines require verbatim ("Continue with Google").

## 9. Tests

Backend (`tests/lms/test_oauth_google.py`, `test_oauth_apple.py`, `test_oauth_ui_contract.py`), SQLite scratch DB as
always. Google is mocked at the HTTP layer: `app/lms/oauth/google.py` gets its `httpx.Client` from a module factory the
tests monkeypatch with `httpx.MockTransport`; the test generates an RSA key, serves it as JWKS at the (overridden)
JWKS URL and signs ID tokens with it; `PyJWKClient` is given the same transport (or the JWKS fetch is routed through
the same factory). `settings` overridden with `monkeypatch.setattr(settings, ...)`.

1. `start`: 404 without keys; with keys 302 to the authorize URL with `code_challenge_method=S256`, `state`, `nonce`,
   `prompt=select_account`; the cookie is HttpOnly, Lax, Path `/api/v1/auth`, decryptable, and holds `sha256(nonce)`
   not the nonce; a bad `redirect` (`//evil`, `https://x`, `/a\u0000`) is dropped; `lang` defaults to `ky`.
2. `callback` state mismatch (wrong `state`, missing cookie, cookie from another provider, expired cookie) → 302
   `…/login?oauth_error=oauth_state_mismatch` / `oauth_expired`, cookie cleared, no token call made.
3. Replayed code: a second callback with the same `code` and a fresh start cookie → the mocked token endpoint answers
   400 `invalid_grant` → `oauth_provider_error`; and a second callback with the **same cookie** fails on state (cookie
   already cleared by the first response).
4. ID token checks: wrong `aud`, wrong `iss`, expired, unknown `kid` (after one refetch), wrong `nonce`, `alg=HS256`
   signed with the client secret (algorithm confusion) → each refused.
5. `email_verified` false / missing → `oauth_email_unverified`; no identity and no user written; no DB read of users.
6. Linking: existing verified password user → identity row, token, password still works afterwards; existing
   **unverified** self-registration → identity row, `password_hash == "!"`, `email_verified` True, old token rejected
   (token_version bumped); disabled user → `account_disabled`, no identity, audit `auth.identity.refused`;
   same Google `sub` returning with a changed email → signs in as the same user, `users.email` unchanged.
7. Sign-up: first `complete` → 422 `oauth_profile_required`; with `ageBand=14_17` + current policy ids → user created,
   `consent_state=ok`, consents recorded with `source="signup"`, `email_verified=True`, `password_hash="!"`, `display_name`
   from the body; `under_14` → `pending_guardian` and the gate blocks `/me/home` as for email sign-up; bad band → 422
   `age_band_required`; missing policies → `policy_not_accepted`; two concurrent completes of one signup ticket →
   one user.
8. Admin two-step: a platform admin with MFA enabled linked to Google → `complete` answers 403 `mfa_required` with a
   challenge, never a token; `POST /auth/mfa` then works; a ticket used as `Authorization: Bearer` → 401.
9. Rate limits: 61st `start` from one address in 10 minutes → 429 with `Retry-After`; 31 bad tickets → 429; successful
   completes do not count on the failure rule.
10. `/auth/providers`: `{google:false, apple:false}` without keys; `google:true` with keys; `apple` stays false with
    Apple keys but `APPLE_SIGN_IN_ENABLED=false`.
11. Apple: `form_post` callback with `user` JSON on the first login puts the name in the ticket; `email_verified="true"`
    accepted; client secret JWT has `alg=ES256`, `kid`, `iss/sub/aud`, `exp ≤ 300 s`; cookie `SameSite=None; Secure`.
12. Route inventory and privacy registry tests pass (new routes listed; `user_identities` registered; anonymize deletes
    the rows; export lists provider and dates only).
13. Production refusal: `is_production()` with a non-default `GOOGLE_OAUTH_TOKEN_URL` raises at startup.

Browser (`frontend/e2e/auth-screens.spec.ts`, `frontend/e2e/oauth-google.spec.ts`): the e2e backend
(`scripts/e2e_backend.sh`) also starts `scripts/e2e_oauth_stub.py` (a small `http.server` on 127.0.0.1 with `/authorize`
→ immediate 302 back with a code, `/token`, `/certs`, keys generated at start, the email and `email_verified` chosen by
query parameters of `/authorize`) and points the four `GOOGLE_OAUTH_*_URL` settings at it. Specs: buttons hidden when the
backend has no keys (second backend instance already exists for `ADMIN_MFA_REQUIRED`; reuse the pattern) and visible
with keys; new user → stub → "Almost done" → age → home; existing password user → signs in, then password login still
works; unverified-email stub → login page shows the translated refusal; admin with MFA → `MfaStep` appears after the
Google round trip; `redirect` preserved through the flow; screens at 375 / 1440 / 1920 in ru for register, login,
forgot-password, callback-step via `expectScreen`. ORT specs and pixel baselines untouched.

## 10. Slices and file ownership

**Slice A, backend auth (Opus)** — owns: `backend/app/lms/oauth/**` (new), `backend/alembic/versions/0029_user_identities.py`,
`backend/app/core/config.py` (new settings block only), `backend/app/lms/core/ratelimit.py` (new constants only),
`backend/app/core/route_inventory.py` (merge `OAUTH_POLICIES`), `backend/app/lms/privacy/registry.py` and the export
(the three entries), the model import list, `backend/tests/lms/test_oauth_*.py`, `scripts/e2e_oauth_stub.py` and the
lines in `scripts/e2e_backend.sh` that start it. Does not touch `auth.py` except, if needed, making `_sign_in` public
by name (`sign_in`) with the old name kept. Acceptance: section 9 items 1–13 green; SQLite full suite; Postgres
`alembic upgrade head && alembic check`; `AGENTS.md` §6.1 scratch DB only.

**Slice B, frontend screens (Sonnet)** — owns: `frontend/src/components/auth/AuthSplit.tsx`, `AuthIllustration.tsx`,
`ProviderButtons.tsx`, `AgeRow.tsx`; the five existing `(auth)` pages' layout changes; the new
`frontend/src/app/[lang]/(auth)/oauth-callback/page.tsx`; `auth-context.tsx` (`completeOAuth` only); the i18n keys of
section 8.5 in all three files; `frontend/e2e/auth-screens.spec.ts`. Builds against the contract in sections 1.6–1.7
and 7.2 (can start before slice A lands by mocking `/auth/providers` and `/auth/oauth/complete` in Playwright routes).
Acceptance: `npx tsc --noEmit`, parity script, screens at 375 / 1440 / 1920 ru checked by the orchestrator (AGENTS.md
§6 rule 10), no horizontal scroll at 375.

**Slice C, integration (Opus, after A and B)** — owns: `frontend/e2e/oauth-google.spec.ts` against the stub, the
admin user page's optional "Sign-in methods" line (`platform_admin/users_service.py` + `schemas.py` + the page), the
`docs/phases/EXAM_PREP.md`-style results section at the end of this file, `docs/PRODUCT_DECISIONS.md` entries copied from
section 12, `docs/runbooks/` one page "Google sign-in: keys, rotation, what to check", `.env.example` names. Runs the
full SQLite and Postgres suites and the browser suite; Neon backup branch before merging `0029` to `main` (AGENTS.md §6
rule 7; Neon is at 10/10 branches per ACCOUNTS.md §G: the owner's OK is needed to delete an old backup branch first).

## 11. Security review notes

- **Login CSRF** (attacker makes the victim's browser finish the attacker's Google flow, so the victim works inside the
  attacker's account): the callback requires our cookie, set only by `start` in the victim's own browser, and its `state`
  must equal the query `state`; an attacker cannot set that cookie cross-site. The ticket then arrives in a fragment of a
  page the attacker never controls.
- **Open redirect**: the only redirect targets are `GOOGLE_OAUTH_AUTHORIZE_URL` (configuration) and
  `FRONTEND_URL + fixed path`; the person's `redirect` is validated server-side, stored in our cookie (never in Google's
  `state`), passed in the fragment and validated again by `safeRedirect` before `router.push`.
- **Account takeover through unverified email**: `email_verified` must be exactly `True` (Google) before any lookup; an
  unconfirmed self-registration that gets linked loses its unconfirmed password and its old tokens (1.6 step 5);
  `users.email` is never rewritten from a provider claim.
- **Token leakage in URLs, referrers, logs**: no session token or ticket ever in a query string; the ticket is in a
  fragment (not sent to servers, not in `Referer`, removed from history by `replaceState`); request logging already drops
  query strings and bodies (`core/request_log.py`), so the authorization `code` is not logged, and the code is useless
  without the client secret and the PKCE verifier (cookie, encrypted); the frontend sends `Referrer-Policy:
  strict-origin-when-cross-origin` (`next.config.ts:45`).
- **Code interception / mix-up / replay**: PKCE S256 binds the code to the verifier in our cookie; one callback route per
  provider and `iss` verified; `nonce` ties the ID token to this flow; the authorization code is single-use at Google.
- **ID token forgery**: RS256 only (`algorithms=["RS256"]`), keys from Google's JWKS over https, `aud` = our client id,
  `exp` with 60 s leeway, `iat` required.
- **Disabled, deleted, test accounts**: checked at `complete` from the database, after the lock, before any write; the
  same `account_disabled` code as password login; test students never match.
- **Cookie scope**: `Path=/api/v1/auth`, HttpOnly, 10 min, encrypted; a leaked cookie without the authorization code is
  useless, and a leaked code without the cookie is useless.
- **Secrets**: client secret and `.p8` key only in Render / `backend/.env`; `GET /auth/providers` exposes booleans only;
  no `NEXT_PUBLIC_` variable; the Apple client-secret JWT lives 5 minutes.
- **Denial of service**: start and callback are per-address limited; a Google outage makes `callback` fail fast (8 s
  timeout, no retry) and password login is unaffected; the JWKS cache survives a JWKS outage for its lifespan.
- **Residual risks**: a ticket replay by its owner within 10 minutes (harmless by construction); an attacker with XSS
  reads the fragment, but also `localStorage` today, so this adds no new class; Apple relay addresses make account
  recovery by email depend on the owner registering the sending domain with Apple.

## 12. Decisions (for `docs/PRODUCT_DECISIONS.md`)

- **D1** Google sign-in uses the server-side authorization-code flow with PKCE S256, state and nonce; the callback URL is
  on the backend (Render); the session reaches the Vercel frontend through a 10-minute signed ticket in the URL
  fragment, traded at `POST /auth/oauth/complete` for the same `TokenResponse` as password login.
- **D2** Flow state (state, PKCE verifier, nonce hash, lang, redirect) lives in an encrypted, HttpOnly, 10-minute cookie
  on the backend origin; no database table for the flow.
- **D3** Linked identities are stored in a new table `user_identities` (migration `0029_user_identities`), one row per
  (provider, subject), at most one identity per provider per user. Never columns on `users`.
- **D4** An existing account is linked by email only when the provider marks the email verified; an unverified claim is
  refused with a clear message and nothing is read or written. Linking to an unconfirmed self-registration discards its
  unconfirmed password and old tokens. `users.email` never changes from a provider claim.
- **D5** New Google users pass exactly the email sign-up age and consent rules, on an "Almost done" step after the Google
  round trip; the Google name is editable there; Google-only accounts have no password until the person sets one via
  "Forgot password".
- **D6** Sign-up asks for name, email and password; the phone field is removed from sign-up; the age question moves from
  a screen before the form to one row inside it; the parent link moves under the form.
- **D7** Platform admins' two-step login is unchanged: every social sign-in ends in `_sign_in`, which issues the MFA
  challenge instead of a token.
- **D8** Deferred: unlinking a provider, linking a second provider from the person page, Apple's revoke endpoint,
  calling the Apple account-deletion API.
- **D9** Apple sign-in is built behind `APPLE_SIGN_IN_ENABLED=false`; buying the Apple Developer Program membership is
  the owner's decision (money).
- **D10** Provider buttons are rendered only when `GET /auth/providers` says the provider is configured; no frontend
  variable holds a client id.
- **D11** No Microsoft or other providers.

## 13. Open questions for the owner

- **Q1** Apple Developer Program: pay now (then the owner follows section 6) or leave Apple off at launch?
- **Q2** Google consent screen branding needs a domain the owner can verify; `vercel.app`/`onrender.com` cannot be. Is a
  custom domain planned before launch? Until then the Google screen may show the Render host name.
- **Q3** Keep sign-in with Google in Testing mode (test users only) during the review round, then Publish on launch day?
  (Proposed: yes.)
