# Runbook: verify the client IP chain, then enforce IP rate limits

Design: `docs/phases/PHASE_11_DESIGN.md` §5.3, findings F1 and F3. Until this is done every IP rule only counts and logs (`RATE_LIMIT_IP_ENFORCE=False`). Per-email and per-user rules are always on.

**Why not just turn it on.** `client_ip` takes the entry `RATE_LIMIT_PROXY_HOPS` from the right of `X-Forwarded-For`. Too large a value and a client chooses its own address by sending the header. Too small and it returns a proxy's address, so all students share one bucket and one school's typos block logins for everyone. Only a request through the real chain tells which.

## 0. Before deploying Phase 11

```bash
API=https://ort-platform-w77q.onrender.com
```

**a. Production must not use the public default `SECRET_KEY`**: Phase 11 refuses to start on it (a failed start keeps the old instance running, but the deploy does not go through). The default is in `config.py`; this signs a token for a user that does not exist, so it reaches no account.

```bash
TOKEN=$(backend/venv/bin/python -c 'import jwt,time; print(jwt.encode({"sub":"usr_probe_none","exp":int(time.time())+60},"ort_secret_jwt_key_2026_super_secure_academic_prep",algorithm="HS256"))')
curl -s "$API/api/v1/auth/me" -H "Authorization: Bearer $TOKEN"
```

| Answer | Meaning |
|---|---|
| `Invalid or expired token` | A real key is set. Go on. |
| `User account not found` | **Stop.** Production signs with the public default, and anyone can forge a login. Set `SECRET_KEY` on Render first (this logs everyone out; `SECRET_KEY_PREVIOUS` must not be the default). |

**b. Render environment** (dashboard): `ACCESS_TOKEN_EXPIRE_MINUTES`, `RATE_LIMIT_PROXY_HOPS` and `RATE_LIMIT_IP_ENFORCE` should be unset, or they override the defaults in `config.py`.

## 1. Probe (temporary, never stays on `main`)

Phase 11 must already be live, frontend included (auth calls direct, see step 4). The patch adds `GET /api/v1/diag/ip`, public, 120 per minute across all callers, showing only the caller's own chain.

```bash
git checkout main && git pull
git apply docs/runbooks/ip_probe.patch
git commit -am "TEMP: IP probe, removed by the next commit (docs/runbooks/IP_CHAIN.md)"
git push origin main
PROBE_SHA=$(git rev-parse HEAD)
# wait until the deploy is live
until curl -s https://ort-platform-w77q.onrender.com/health | grep -q "${PROBE_SHA:0:7}"; do sleep 15; done
```

## 2. Read the chain

From your computer, and once more from another network (a phone hotspot):

```bash
API=https://ort-platform-w77q.onrender.com
curl -s https://ifconfig.me; echo
curl -s "$API/api/v1/diag/ip"; echo
curl -s -H "X-Forwarded-For: 1.2.3.4" "$API/api/v1/diag/ip"; echo
curl -s -H "X-Forwarded-For: 1.2.3.4, 5.6.7.8" "$API/api/v1/diag/ip"; echo
```

`by_hops` shows what each value of `RATE_LIMIT_PROXY_HOPS` would give, so one deploy is enough. **The right value `n`**: in all three calls and on both networks, `by_hops[n]` is that network's real address (`ifconfig.me`), and it is never `1.2.3.4` or `5.6.7.8`.

Record the outputs (addresses masked to the first two groups) at the end of this file.

Also record the same-origin path, for the note below: `curl -s https://<vercel-domain>/api/v1/diag/ip`.

**No such `n`?** Do not flip. Run step 3 without the two config lines, keep log-only, and add a line to the owner list in `LAUNCH_CHECKLIST.md`. The `headers` field shows what else the chain offers (`true-client-ip`, `cf-connecting-ip`, `x-real-ip`); using one is a code change that needs its own spoof check.

## 3. Flip and remove the probe in one commit

```bash
git revert --no-commit "$PROBE_SHA"
HOPS=<the n you found>
python3 - "$HOPS" <<'PY'
import re, sys
p = "backend/app/core/config.py"
s = open(p, encoding="utf-8").read()
s, a = re.subn(r"RATE_LIMIT_PROXY_HOPS: int = \d+", f"RATE_LIMIT_PROXY_HOPS: int = {sys.argv[1]}", s)
s, b = re.subn(r"RATE_LIMIT_IP_ENFORCE: bool = False", "RATE_LIMIT_IP_ENFORCE: bool = True", s)
assert a == 1 and b == 1
open(p, "w", encoding="utf-8").write(s)
PY
# suite on a scratch database (AGENTS.md section 5); tests set the switch themselves
git add -A backend/app docs/runbooks/IP_CHAIN.md
git commit -m "Enforce IP rate limits: proxy hops verified, probe removed (docs/runbooks/IP_CHAIN.md)"
git push origin main
```

**Check with a test bucket.** Wrong reset tokens touch no account, and the 31st call in a 10-minute window should answer 429. This blocks only reset-password, only from your address, for at most 10 minutes.

```bash
API=https://ort-platform-w77q.onrender.com
for i in $(seq 1 31); do
  curl -s -o /dev/null -w "%{http_code} " -X POST "$API/api/v1/auth/reset-password" \
    -H "Content-Type: application/json" -d '{"token":"probe-'"$i"'","new_password":"not-a-real-reset-1"}'
done; echo
# still 429 with a made-up address: the header cannot dodge the limit
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$API/api/v1/auth/reset-password" \
  -H "X-Forwarded-For: 1.2.3.4" -H "Content-Type: application/json" -d '{"token":"probe-x","new_password":"not-a-real-reset-1"}'
curl -s -o /dev/null -w "%{http_code}\n" "$API/api/v1/diag/ip"   # 404: the probe is gone
```

Expect thirty `400`, then `429`, `429`, `404`. Then sign in normally from the same network: login uses its own bucket.

## Kill switch

Render, Environment: `RATE_LIMIT_IP_ENFORCE=false`, save (restarts the service). IP rules go back to count and log. Email and user rules stay on. Use it at once if a school reports `rate_limited` at login during an exam morning. Logs show `rate limit (log-only) rule=...` afterwards, so the size of the problem stays visible.

## What each limit can and cannot stop

- **An open exam: nothing.** Autosave, submit, state and content go through none of these rules (`test_full_limits_never_touch_an_open_attempt`). Autosave has its own in-process token bucket, unchanged.
- **Logins behind one school address.** Successes write nothing and count nothing. Only failed passwords count, 300 per 10 minutes per address. A correct password is refused only once that address has had 300 failures in the current window.
- **All-count rules**: `register_ip_1h` 120 per hour and `forgot_ip_1h` 60 per hour count every request, so a school registering a whole year group on one address in one hour reaches them once enforced. Registering in smaller groups avoids it; raise them if a school does.
- **The limiter failing**: on the auth routes a limiter that cannot reach its table lets the request through and logs a warning.

## Auth calls go directly to the API

The design (§5.3) said no real student uses the same-origin Vercel path. That was wrong when written: `auth-context.tsx` and the forgot and reset pages called `/api/v1/auth/*` relatively, so **every login went through Vercel**, and every student's login would have resolved to a few Vercel addresses. Phase 11 S4 moves them to `API_BASE_URL`, like all other calls. Only `/auth/me` and `/auth/ping` still use the rewrite, and they have no IP rule.

The same-origin path stays open as a second route and resolves to a Vercel address. Nothing rate-limited uses it from the app; a caller using it directly only exhausts that shared bucket, and the email rules still hold.

## Recorded results

<!-- date, hops found, masked outputs of step 2 -->
Not run yet.
