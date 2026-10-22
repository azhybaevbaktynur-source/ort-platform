# Phase 1 — Courses, enrollment, authorization

**Status**: done 2026-10-22 on branch `phase-1/courses`, merged into `lms` (not `main`; phases 1–4 ship at the Phase 5 cutover). Design and all decisions: `PHASE_1_DESIGN.md`.

## What changed

- **Schema** (Alembic `0002_phase1_courses`): `users` += `is_platform_admin`, `teacher_status`, `locale`, `age_band`, `disabled_at`/`disabled_by_id`/`disabled_reason`; new `courses`, `enrollments`, `enrollment_events`, `teacher_requests`, `admin_audit_log`, `rate_limit_buckets`. Data step: `role='admin'` → platform admin + approved teacher.
- **Authorization** (`app/core/authz.py`): enrollment role resolver (active only, request-cached, prefetch for lists), status gates, SQL scopes (`app/lms/courses/scopes.py`), route-inventory policies for every new route.
- **Teachers** (`app/lms/teachers/`): `/me/lms`, teacher requests (one pending, 3/24 h).
- **Courses & enrollments** (`app/lms/courses/`, `app/lms/enrollments/`): create (owner enrollment in the same transaction; approved teachers only), update, lifecycle (publish/unpublish/conclude/reopen), soft delete/restore, ownership transfer, join by code (one transaction, row lock, identical failures, rate-limited), leave, roster, add staff, role change, remove; events log.
- **Platform admin** (`app/lms/platform_admin/`, `/api/v1/platform/*`): summary, teacher requests, users (search, teacher status, disable/enable), course moderation (delete/restore/unlist/relist/transfer, audited roster view), audit log. Platform admin flag read from the DB; every mutation audited.
- **Account disable**: 401 on every API (old and new), login 403 `account_disabled`.
- **Rate limiter** (`app/lms/core/ratelimit.py`): DB-backed, own connection pool; IP rule log-only until the proxy chain is verified.
- **Frontend**: `/[lang]/courses/...` (my courses, create, join, course home/people/settings, trash, become-a-teacher), `/[lang]/admin/...` (overview, teacher requests, users, courses, audit log); LMS client with typed errors; `safeRedirect` for login/register `?redirect=`. Trilingual (516 keys).
- **Reviews**: architect review of S1 (connection-pool deadlock in the rate limiter, IP spoofing, owner email leak, key truncation, cleanup locking, cache key types — all fixed) and a security review of the whole phase (admin takedown undone by owner, open redirect, ownership/join races, crafted cursor 500, add-staff email enumeration, duplicate add-staff 500 — all fixed).

## How to verify

```bash
cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" venv/bin/python -m pytest -q -p no:cacheprovider -W ignore
# Postgres concurrency (join limit, duplicate joins, rate limiter, transfer/leave and unpublish/join races):
DATABASE_URL=postgresql+psycopg2://postgres@localhost:55432/<db> LMS_PG_TEST_DATABASE_URL=postgresql+psycopg2://postgres@localhost:55432/<db> PGTZ=UTC venv/bin/python -m pytest tests/lms/test_pg_concurrency.py
```
End-to-end: `tests/lms/test_phase1_flow.py` (request teacher → approve → create → publish → join → remove → rejoin revives row → regenerate code → conclude → delete → restore). Matrix: `tests/lms/test_course_matrix.py` (routes × statuses × actors). Isolation: `tests/lms/test_isolation_suite.py`.

Manual: run backend + frontend, register two users, `make_admin.py` one of them, request teacher access with the other, approve in `/[lang]/admin/teacher-requests`, create a course in `/[lang]/courses/new`, publish, join from a third account with the code.

## Deferred / notes

- **Q1**: verify the real `X-Forwarded-For` chain (Vercel rewrite → Render) and then set `RATE_LIMIT_IP_ENFORCE=True` with the right `RATE_LIMIT_PROXY_HOPS`.
- Staff are added directly by email (no invite-accept); consider invite-accept in Phase 7.
- Local SQLite dev DBs created before Phase 1 lack the new user columns: run once with `RUN_MIGRATIONS=1` (verified) or recreate.
- A national ORT course must keep `enrollment_limit` empty (a limit serializes joins on the course row).
- `make_admin.py` sets the platform-admin flag but not teacher approval for newly promoted admins; they can approve themselves in the admin area.
