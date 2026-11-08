#!/usr/bin/env bash
# Scratch backend for the ORT browser e2e suite (frontend/e2e, docs/phases/ORT_BASELINE/README.md).
#
# Starts FastAPI on a fresh SQLite database with `env -i` from an empty directory outside backend/, so
# backend/.env (live credentials) is never loaded, seeds deterministic data through the API
# (frontend/e2e/seed_backend.py) and keeps the server in the foreground until it is stopped.
# Playwright's webServer runs this script and waits for /health; the global setup then waits for
# $E2E_DIR/seed.json, which the seed writes last.
#
# Env (all optional):
#   E2E_DIR         scratch directory, wiped on start   (default /tmp/ort_e2e)
#   E2E_API_PORT    backend port                        (default 8765)
#   E2E_WEB_ORIGIN  frontend origin allowed by CORS     (default http://127.0.0.1:3765)
#   E2E_PYTHON      python with backend requirements    (default backend/venv/bin/python, else python3)
#   E2E_OAUTH_STUB_PORT  Google sign-in stub port       (default E2E_API_PORT+2; scripts/e2e_oauth_stub.py;
#                   E2E_API_PORT+1 is the --mfa-required server of admin-mfa-gate.spec.ts)
#
# S1 admin security: `e2e_backend.sh --mfa-required <port>` starts a second server on the same scratch database and
# signing key with ADMIN_MFA_REQUIRED=true, in the foreground, without wiping or seeding anything. Only
# frontend/e2e/admin-mfa-gate.spec.ts uses it (it sends its own page's API calls there); every other spec keeps the main
# server, where the requirement is off.
#
# Social sign-in (docs/phases/AUTH_SOCIAL_DESIGN.md 9): the main server signs in with Google through
# scripts/e2e_oauth_stub.py (a throwaway client secret per run); the --mfa-required server has no Google keys, so
# `GET /auth/providers` there says {"google": false} (the "buttons hidden" spec).
set -euo pipefail
MFA_REQUIRED_PORT=""
if [[ "${1:-}" == "--mfa-required" ]]; then
  MFA_REQUIRED_PORT="${2:?port}"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
E2E_DIR="${E2E_DIR:-/tmp/ort_e2e}"
PORT="${E2E_API_PORT:-8765}"
WEB_ORIGIN="${E2E_WEB_ORIGIN:-http://127.0.0.1:3765}"
if [[ -n "${E2E_PYTHON:-}" ]]; then
  PY="$E2E_PYTHON"
elif [[ -x "$ROOT/backend/venv/bin/python" ]]; then
  PY="$ROOT/backend/venv/bin/python"
else
  PY="python3"
fi
PY="$(command -v "$PY")"   # absolute: env -i below has a minimal PATH

case "$E2E_DIR" in
  *..*|*/) echo "e2e_backend: E2E_DIR must not contain '..' or end with '/' (got $E2E_DIR)" >&2; exit 2 ;;
esac
case "$E2E_DIR" in
  /tmp/?*|/private/tmp/?*|"${RUNNER_TEMP:-/nonexistent}"/?*) ;;
  *) echo "e2e_backend: E2E_DIR must be under /tmp (got $E2E_DIR)" >&2; exit 2 ;;
esac
if [[ -n "$MFA_REQUIRED_PORT" ]]; then
  SECRET_KEY="$(cat "$E2E_DIR/cwd/secret_key")"  # the main server's throwaway key: the same tokens work on both
else
  /bin/rm -rf "$E2E_DIR"
  mkdir -p "$E2E_DIR/up" "$E2E_DIR/cwd"
  # A throwaway signing key per run (never a real secret, never written to the repo; kept in the scratch dir only)
  SECRET_KEY="e2e-$("$PY" -c 'import secrets; print(secrets.token_hex(24))')"
  (umask 077; printf '%s' "$SECRET_KEY" > "$E2E_DIR/cwd/secret_key")
fi

run_env=(
  env -i
  PATH="/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:$(dirname "$PY")"
  HOME="$E2E_DIR/cwd"
  LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
  PYTHONPATH="$ROOT/backend"
  ENVIRONMENT=development
  DATABASE_URL="sqlite:///$E2E_DIR/e2e.db"
  LOCAL_UPLOAD_DIR="$E2E_DIR/up"
  LMS_STORAGE_DRIVER=db
  R2_ACCOUNT_ID= R2_ACCESS_KEY_ID= R2_SECRET_ACCESS_KEY=
  EMAIL_PROVIDER=console
  EMAIL_CONSOLE_SHOW_PRIVATE=true  # S4: email-change links are private emails; the spec reads them from the log
  RATE_LIMIT_IP_ENFORCE=false
  ADMIN_MFA_REQUIRED=false  # S1: the seeded admins have no two-step login; admin-mfa.spec.ts sets it up for its own
  SECRET_KEY="$SECRET_KEY"
  ORT_SEED_SAMPLES=false
  ALLOWED_ORIGINS="$WEB_ORIGIN"
  BACKEND_CORS_ORIGINS="$WEB_ORIGIN"
  FRONTEND_URL="$WEB_ORIGIN"
)

cd "$E2E_DIR/cwd"   # no .env here: settings read only the variables above
if [[ -n "$MFA_REQUIRED_PORT" ]]; then
  exec "${run_env[@]}" ADMIN_MFA_REQUIRED=true "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$MFA_REQUIRED_PORT" \
    --log-level warning >>"$E2E_DIR/backend_mfa_required.log" 2>&1
fi
# --- social sign-in begin --- the Google stub and the main server's Google settings (never on production: the
# backend refuses non-default Google URLs there)
OAUTH_PORT="${E2E_OAUTH_STUB_PORT:-${E2E_OAUTH_PORT:-$((PORT + 2))}}"  # E2E_OAUTH_PORT: the earlier name
OAUTH_CLIENT_ID="e2e-client.apps.example"
OAUTH_CLIENT_SECRET="e2e-$("$PY" -c 'import secrets; print(secrets.token_hex(24))')"
API_ORIGIN="http://127.0.0.1:$PORT"
OAUTH_ORIGIN="http://127.0.0.1:$OAUTH_PORT"
"${run_env[@]}" E2E_OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" "$PY" "$ROOT/scripts/e2e_oauth_stub.py" \
  --port "$OAUTH_PORT" --client-id "$OAUTH_CLIENT_ID" --redirect-uri "$API_ORIGIN/api/v1/auth/google/callback" \
  >"$E2E_DIR/oauth_stub.log" 2>&1 &
STUB_PID=$!
google_env=(
  OAUTH_PUBLIC_BASE_URL="$API_ORIGIN"
  GOOGLE_OAUTH_CLIENT_ID="$OAUTH_CLIENT_ID"
  GOOGLE_OAUTH_CLIENT_SECRET="$OAUTH_CLIENT_SECRET"
  GOOGLE_OAUTH_AUTHORIZE_URL="$OAUTH_ORIGIN/authorize"
  GOOGLE_OAUTH_TOKEN_URL="$OAUTH_ORIGIN/token"
  GOOGLE_OAUTH_JWKS_URL="$OAUTH_ORIGIN/certs"
  GOOGLE_OAUTH_ISSUERS="$OAUTH_ORIGIN"
)
# --- social sign-in end ---
"${run_env[@]}" "${google_env[@]}" "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning \
  >"$E2E_DIR/backend.log" 2>&1 &
API_PID=$!
cleanup() {
  kill "$API_PID" "$STUB_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
  wait "$STUB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 40); do
  if curl -fsS "$OAUTH_ORIGIN/certs" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$STUB_PID" 2>/dev/null; then echo "e2e_backend: oauth stub exited" >&2; cat "$E2E_DIR/oauth_stub.log" >&2; exit 1; fi
  sleep 0.25
done

for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$API_PID" 2>/dev/null; then echo "e2e_backend: backend exited" >&2; cat "$E2E_DIR/backend.log" >&2; exit 1; fi
  sleep 0.5
done

# seed output also kept in $E2E_DIR/seed.log (CI prints it as an annotation on failure: scripts/ci_log_annotations.py)
if ! "${run_env[@]}" "$PY" "$ROOT/frontend/e2e/seed_backend.py" --api "http://127.0.0.1:$PORT" \
    --log "$E2E_DIR/backend.log" --out "$E2E_DIR/seed.json" --root "$ROOT" >"$E2E_DIR/seed.log" 2>&1; then
  echo "e2e_backend: seeding failed; seed log:" >&2
  tail -50 "$E2E_DIR/seed.log" >&2
  echo "e2e_backend: backend log:" >&2
  tail -50 "$E2E_DIR/backend.log" >&2
  exit 1
fi
cat "$E2E_DIR/seed.log"
echo "e2e_backend: ready on http://127.0.0.1:$PORT (seed: $E2E_DIR/seed.json)"
wait "$API_PID"
