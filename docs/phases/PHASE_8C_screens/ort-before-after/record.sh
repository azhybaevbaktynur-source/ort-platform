#!/usr/bin/env bash
# Phase 8c S4a (PHASE_8C_DESIGN section 11): record the frame-affected ORT screens from the base (origin/lms, "before")
# and from the current checkout ("after"), then build side-by-side images (compare.mjs).
#
#   bash docs/phases/PHASE_8C_screens/ort-before-after/record.sh [before|after|compare|all]   (default all)
#
# Needs: frontend/node_modules (a symlink is fine), node, system Chrome, E2E_PYTHON (python with the backend requirements;
# in a git worktree point it at the main repo's venv). Never touches docs/phases/ORT_BASELINE/: both runs use
# ORT_BASELINE_DIR + ORT_BASELINE_RECORD_MISSING=1 with empty folders (before/ and after/ next to this script).
# Env: SKIP_BUILD=1 (reuse the frontend builds under $WORK), BASE_REF (origin/lms), WORK (/tmp/ort_8c_ba), E2E_API_PORT (8871), E2E_WEB_PORT (3871).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
HERE="$ROOT/docs/phases/PHASE_8C_screens/ort-before-after"
BASE_REF="${BASE_REF:-origin/lms}"
WORK="${WORK:-/tmp/ort_8c_ba}"
API_PORT="${E2E_API_PORT:-8871}"
WEB_PORT="${E2E_WEB_PORT:-3871}"
STEP="${1:-all}"
mkdir -p "$WORK"

build() { # $1 = name, $2 = source folder (a frontend copy)
  [[ "${SKIP_BUILD:-}" == "1" && -d "$WORK/fe_$1/.next" ]] && return 0
  local dest="$WORK/fe_$1"
  /bin/rm -rf "$dest"; mkdir -p "$dest"
  rsync -a --exclude node_modules --exclude .next "$2/" "$dest/"
  ln -s "$ROOT/frontend/node_modules" "$dest/node_modules"
  (cd "$dest" && NEXT_PUBLIC_API_URL="http://127.0.0.1:$API_PORT" npx next build >"$WORK/build_$1.log" 2>&1) \
    || { tail -30 "$WORK/build_$1.log"; exit 1; }
}

record() { # $1 = before|after
  local out="$HERE/$1"
  /bin/rm -rf "$out"; mkdir -p "$out"
  (cd "$ROOT/frontend" && E2E_DIR="$WORK/e2e_$1" E2E_API_PORT="$API_PORT" E2E_WEB_PORT="$WEB_PORT" \
    E2E_WEB_DIR="$WORK/fe_$1" ORT_BASELINE_DIR="$out" ORT_BASELINE_RECORD_MISSING=1 \
    npx playwright test e2e/ort-visual.spec.ts)
}

if [[ "$STEP" == "before" || "$STEP" == "all" ]]; then
  if [[ "${SKIP_BUILD:-}" != "1" || ! -d "$WORK/base_src/frontend" ]]; then
    /bin/rm -rf "$WORK/base_src"; mkdir -p "$WORK/base_src"
    git -C "$ROOT" archive "$BASE_REF" frontend | tar -x -C "$WORK/base_src"
  fi
  build before "$WORK/base_src/frontend"
  record before
fi
if [[ "$STEP" == "after" || "$STEP" == "all" ]]; then
  build after "$ROOT/frontend"
  record after
fi
if [[ "$STEP" == "compare" || "$STEP" == "all" ]]; then
  node "$HERE/compare.mjs"
fi
