# Google sign-in: keys, rotation, what to check
Design: `docs/phases/AUTH_SOCIAL_DESIGN.md` (sections 1, 7). Code: `backend/app/lms/oauth/`. The button appears only when the
backend says so (`GET /api/v1/auth/providers`); the frontend holds no Google value at all.

**The keys (backend only, never in the frontend, never in the repository)**
| Name | Value | Secret |
|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | Google Cloud Console → Credentials → OAuth client "ORT backend" (Web application) → Client ID | no, but keep it on the backend |
| `GOOGLE_OAUTH_CLIENT_SECRET` | same client → Client secret | **yes** |
| `OAUTH_PUBLIC_BASE_URL` | the backend's own origin: `https://ort-platform-w77q.onrender.com` (local `http://127.0.0.1:8000`) | no |
| `FRONTEND_URL` | already set: `https://ort-platform-nu.vercel.app` (local `http://localhost:3000`) | no |
| `GOOGLE_SIGN_IN_ENABLED` | the switch, default `true`; effective only with the three values above | no |

Never set `GOOGLE_OAUTH_AUTHORIZE_URL`, `GOOGLE_OAUTH_TOKEN_URL`, `GOOGLE_OAUTH_JWKS_URL` or `GOOGLE_OAUTH_ISSUERS` outside the
e2e suite: production refuses to start when any of them differs from Google's own (`config.refuse_unsafe_oauth_urls`).
No `NEXT_PUBLIC_*` variable and nothing in Vercel is needed.

**Where to set them**
1. Production: Render → the backend service → Environment → add the names above → Save (Render redeploys).
2. Local: the owner adds the same names to `backend/.env` (agents never open that file). `backend/.env.example` lists the
   names without values.
3. The Google client must list the exact redirect URIs (Credentials → the client → Authorized redirect URIs):
   `https://ort-platform-w77q.onrender.com/api/v1/auth/google/callback`, `http://127.0.0.1:8000/api/v1/auth/google/callback`,
   `http://localhost:8000/api/v1/auth/google/callback`. A custom domain later: add its URI and change `OAUTH_PUBLIC_BASE_URL`.
4. While the consent screen is in **Testing**, only its listed test users can sign in (up to 100). Publish the app on
   launch day (scopes `openid email profile` only: no Google review).

**What to check after setting or changing a key**
1. `GET https://ort-platform-w77q.onrender.com/api/v1/auth/providers` answers `{"google": true, "apple": false}`.
2. `/ru/login` shows "Продолжить через Google"; pressing it reaches Google's account chooser (not an error page from Google).
   `redirect_uri_mismatch` at Google = step 3 above or `OAUTH_PUBLIC_BASE_URL` is wrong.
3. Sign in with a test Google account: you land signed in (or on "Почти готово" for a new person). Back on the login page
   with "Сервис не смог выполнить вход. Попробуйте ещё раз." (`oauth_provider_error`) = the token call failed: usually a wrong or rotated secret. The Render log has
   the status code only (never the body, never the code).
4. A platform admin with two-step login still gets the code step after Google.

**Rotation (the secret leaked, or routinely)**
1. Google Cloud Console → Credentials → the client → **Add secret** (Google keeps two secrets valid at once).
2. Put the new secret in Render (`GOOGLE_OAUTH_CLIENT_SECRET`) and in `backend/.env`; wait for the redeploy; run the checks.
3. Back in the console, **disable**, then **delete** the old secret. Sessions are not affected: our own JWTs do not
   depend on Google's secret. A leaked client ID alone is harmless; a new client means new redirect URIs (step 3 above).
4. `SECRET_KEY` rotation (our own key) also invalidates Google sign-ins that are mid-flow (10 minutes at most);
   `SECRET_KEY_PREVIOUS` keeps them working during the switch, as for every other token.

**How to switch it off**
- Quick: Render → `GOOGLE_SIGN_IN_ENABLED=false` → redeploy. The button disappears (within 5 minutes of browser cache of
  `/auth/providers`), `start` answers 404 `oauth_not_configured`, a person mid-flow lands on the login page with a message.
- Removing `GOOGLE_OAUTH_CLIENT_SECRET` has the same effect.
- People who signed up with Google only keep their accounts and can sign in with a password after "Забыли пароль?"
  (their email is verified). Linked identities stay in `user_identities` and work again when Google is switched back on.
- Stopping it at Google's side (delete the OAuth client) breaks only Google sign-in; password login is unaffected.

**Apple** is built but off (`APPLE_SIGN_IN_ENABLED=false`); turning it on needs the paid Apple Developer Program (owner's
decision) and the four Apple values of design section 6.
