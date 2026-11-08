# Performance audit: speed and flicker (owner round 2026-11-09, item 1)

Architect: Fable. Measured 2026-11-09 on the owner's brief in `OWNER_FEEDBACK_2026-11-09.md` (item 1). Everything
below was measured, not guessed; every number names the method that produced it so the implementers repeat it
after their slices (§7). Before = `fe4a1e8` (the state before the 2026-11-08 deploy), after = `989054d` (what is
deployed; `main` `ba21af4` adds only docs).

## 1. Summary

1. **The wrong-shell flash is real and is not new.** On a cold tab (no `sessionStorage`, that is: right after
   signing in, in a new tab, or after the browser dropped the session) `/ky/courses` for a teacher renders the
   student frame (dark sidebar, Башкы бет / Каталог) and then the teacher header. The measurement sees it as
   `student-skeleton → student → header` on both builds (§3.2). It comes from the Student UI shell of 2026-11-07:
   `LmsShell` decides the frame from `MeOut` (`/me/lms`); until that answer arrives `coursesDefault` is `learning`,
   so `studentFrame` is true for everyone. The 2026-11-08 deploy made the flash longer and busier (§4) but did not
   create it. With `sessionStorage` warm (every later tab switch in the same tab) the frame is right from the first
   signed-in render, but the pre-auth skeleton is still the student one for teachers (`student-skeleton → header`)
   because the cached profile is read in an effect, one render too late.
2. **What the deploy added**: one more request on every student page (`/courses/{exam}/lesson-courses`), a
   duplicate `GET /courses?role=teaching` on the teacher list (the list remounts when `noLearning` flips after
   `MeOut` arrives), two more queries in `/me/lms`, the Learning pill appearing and disappearing in the teacher
   header (`hideLearning` is known only after `MeOut`), and +2 to +5 kB first-load JS per route (§3.1). None of
   these is large alone; together with the per-request cost of the free hosting (next point) they add up.
3. **The dominating cost in production is per request, not per query.** Locally every endpoint answers in 20 to 80 ms
   with 2 to 17 queries and no N+1 (§3.3; query counts do not grow with rows). On Neon every hot query runs in well
   under a millisecond and every predicate has an index (§3.4). But a warm `GET /health` on Render Free takes
   270 to 390 ms to first byte from a European client (connect 13 ms), `/api/v1/auth/ping` 300 to 380 ms, and the
   Vercel rewrite hop (`/api/v1/*` on the frontend origin, used by `/auth/me`) 380 ms (§3.5). Render Free is 0.1 CPU:
   requests that run "in parallel" in the browser are serialised on the server. The student home makes 10 API
   requests in 2 rounds, the teacher course page 7 in 2, the admin overview 7 in 3 rounds; on production each round
   costs roughly 0.4 to 0.8 s plus CORS preflights (the frontend calls the backend cross-origin; a preflight per
   new URL, cached 10 min). Fewer requests and fewer rounds are worth more than any query tuning.
4. **Cold starts** (§3.5): Render Free spins the service down after 15 minutes without traffic and needs about a
   minute to come back; the uptime workflow pings every 30 minutes, so the service sleeps roughly half the time and
   the first visitor after a quiet quarter-hour waits for it. Neon Free suspends the compute after 5 minutes without
   a connection and resumes in a few hundred milliseconds; the backend's sweep is request-driven, so Neon sleeps
   whenever nobody uses the site for 5 minutes even while Render is awake. Removing them costs about $7/month
   (Render Starter) and about $20/month (Neon Launch, scale-to-zero off), details and sources in §3.5.
5. **Bundle**: no large library reaches the first screen except the translation dictionary: one language is a
   91 to 93 kB gzip chunk (388 to 396 kB raw) loaded on every cold visit, about 1.8 s alone on the Slow 4G profile.
   KaTeX (76 kB gzip) is only on content routes (bank, player, grading schemes, exam templates). Dependencies are
   lean (`katex`, `lucide-react`, `qrcode`, Next, React).

Fix design in §5, slices in §6. Target after the slices: no frame swap on any page (the measurement's `swap`
column reads `no` everywhere), one API round before first content on warm loads, at most two on cold loads, and
first content under 400 ms on the laptop profile for every main page.

## 2. Method (reproducible)

- **Builds**: `git worktree add --detach <scratch>/wt_before fe4a1e8` and `wt_after 989054d`; `rsync -a --exclude
  node_modules --exclude .next` of `frontend/` into `<scratch>/fe_before|fe_after`, `node_modules` symlinked from the
  main checkout, `NEXT_PUBLIC_API_URL=http://127.0.0.1:8831 npx next build`. JS per route = the "First Load JS"
  column of the build output; chunk contents and gzip sizes from `.next/app-build-manifest.json` and
  `.next/static/chunks` (gzip level 6 in Python).
- **Backend**: the e2e scratch backend (`scripts/e2e_backend.sh`, SQLite, seeded by `frontend/e2e/seed_backend.py`)
  from this branch (= after + the Server-Timing header) on `E2E_API_PORT=8831`, `E2E_WEB_ORIGIN=http://127.0.0.1:3031`,
  `E2E_DIR=<scratch>/e2e`. The same backend served both frontend builds, so the before/after comparison isolates the
  frontend; backend changes of 2026-11-08 are measured separately as query counts (§3.3).
- **Browser**: `frontend/e2e/perf-waterfall.spec.ts` with `frontend/playwright.perf.config.ts` (system Chrome,
  headless, ru-RU), §7. Users from the seed: student `students["flow-ru"]` in ORT (Russian), teacher
  `course_nav.teacher` (approved, owns one course, enrolled nowhere as a student: the owner's own situation),
  admin `admin`. Pages: `/ru/login`, student home `/ru/courses`, tests `/ru/courses/{ort}/tests`, analytics
  `/ru/courses/{ort}/progress`, teacher list `/ru/courses`, course page `/ru/courses/{course}`, admin `/ru/admin`.
  Profiles: laptop 1440x900, no throttling; phone 390x844, CDP 4x CPU slowdown, 400 kbit/s both ways, 400 ms RTT.
  Modes: cold (new browser context: empty cache, empty `sessionStorage`), client (a click on a shell link to the next
  page, in the same tab), warm (a second full load in the same context). "First content" = the first moment `<main>`
  has more than 40 characters of text and no skeleton (`.animate-pulse`) or loading status inside it. "Frames seen"
  = the sequence of frames a MutationObserver saw: `student-skeleton` (the pre-auth student frame), `student` (the
  `<aside>` sidebar shell), `header-skeleton` (`data-testid=areas-loading`), `header` (the app header), `none`.
  "API depth" = the longest chain of API requests each starting after another one ended. One run per cell; the
  laptop numbers vary by about ±30 % between runs (the machine was also building and testing), the phone numbers
  are dominated by the network emulation and are stable to ±10 %.
- **Backend timing**: `backend/app/core/server_timing.py` (this branch) adds `Server-Timing: total;dur=<ms>,
  db;dur=<ms>;desc="n=<queries>"` to every answer; the browser measurement records it per request. The SQL text per
  endpoint came from a SQLAlchemy `before_cursor_execute` listener around `TestClient` calls against the seeded
  database (`sqlcap.py`, in the scratch directory, not committed).
- **Neon**: read-only `EXPLAIN (ANALYZE, BUFFERS)` on SELECTs through the Neon MCP `run_sql` on the production branch
  `br-cool-firefly-b227gbuy`; `pg_stat_user_tables` and `pg_indexes` for sizes and indexes. No writes, no DDL.
- **Production**: `curl -w` from the architect's machine (connect time to Render 13 to 22 ms, so a European
  vantage point); the public pages with the same Playwright script and `PERF_PUBLIC_ONLY=1` against
  `https://ort-platform-nu.vercel.app`. Logged-in production numbers cannot be produced without the owner's
  password; they come from the after-deploy check (§7).

## 3. Measurements

### 3.1 JS per route (`next build`, "First Load JS")

| route | before | after | note |
|---|---|---|---|
| shared by all routes | 104 kB | 104 kB | `b0594ffd` 54.2 kB + `7956` 46.7 kB (React, Next runtime, i18n context) |
| `/[lang]/login` | 148 kB | 150 kB | |
| `/[lang]/courses` (student home, teacher list) | 166 kB | 171 kB | +5 kB: LessonCourses strip, org switcher, teacher notice |
| `/[lang]/courses/[courseId]` (course page) | 216 kB | 218 kB | |
| `/[lang]/courses/[courseId]/tests` | 144 kB | 146 kB | |
| `/[lang]/courses/[courseId]/progress` (analytics) | 150 kB | 152 kB | |
| `/[lang]/admin` | 149 kB | 151 kB | |
| `/[lang]/courses/new` | 144 kB | 156 kB | +12 kB: cover picker, language fields, preview |
| `/[lang]/courses/[courseId]/settings` | 162 kB | 170 kB | +8 kB: settings sections |
| `/[lang]/exam-templates/[templateId]` | 304 kB | 307 kB | KaTeX + constructor; unchanged design |
| `/[lang]/courses/[courseId]/attempts/[attemptId]` (ORT player) | 243 kB | 245 kB | ORT, not touched |
| `/[lang]/grading-schemes/[schemeId]` | 235 kB | 238 kB | KaTeX through `CurveForm` |

Every route grew by 2 to 5 kB (shared UI additions: `OverflowMenu`, `LockToggle`, grouped `AreaShell`, header
switcher). Nothing moved a large library into the first screen. Not in the table but loaded on every cold visit: the
language dictionary, a lazy chunk per language (`489`, `3622`, `9059` in the after build): **91 to 93 kB gzip, 388 to
396 kB raw each**. Raw JS transferred on a cold load (sum of script bodies the browser fetched): login 958 kB,
student home 1,098 kB, teacher list 1,230 kB, admin 1,392 kB; the dictionary is about 40 % of the login page's
bytes. KaTeX (`79477eb0`, 76 kB gzip) is reached only through `components/math/MathRenderer.tsx`, imported by the
bank, player, review, grading-scheme and passage components, never by the shells or the home pages.

### 3.2 Waterfalls per page

Full tables (every request with start/end, status and Server-Timing) are in `<E2E_DIR>/perf/before.md`,
`after.md` and the JSON next to them; the script prints them. The columns below: API requests on the load, API
depth (sequential rounds), first content, frames seen, swap.

**Laptop profile** (1440 px, no throttling; `before-laptop` and `after-laptop2` runs, back to back on the same
machine at load average ~10, so ±30 % per cell; the structure columns are exact):

| page | mode | API before → after | depth before → after | first content before → after (ms) | settled before → after (ms) | frames seen (after) | swap |
|---|---|---|---|---|---|---|---|
| login | cold | 1 → 1 | 1 → 1 | 188 → 583 | 608 → 1208 | none | no |
| login | warm | 1 → 1 | 1 → 1 | 62 → 93 | 228 → 347 | none | no |
| student-home | cold | 9 → 10 | 2 → 3 | 966 → 1295 | 997 → 1323 | student-skeleton → student | no |
| student-home | client | 3 → 3 | 2 → 2 | 94 → 296 | 297 → 950 | - | no |
| student-home | warm | 9 → 10 | 1 → 1 | 356 → 772 | 1241 → 876 | student-skeleton → student | no |
| student-tests | cold | 9 → 10 | 2 → 2 | 504 → 877 | 534 → 954 | student-skeleton → student | no |
| student-tests | client | 3 → 3 | 1 → 1 | 72 → 35 | 207 → 132 | - | no |
| student-tests | warm | 9 → 10 | 2 → 2 | 452 → 271 | 487 → 296 | student-skeleton → student | no |
| student-analytics | cold | 10 → 11 | 2 → 2 | 776 → 360 | 819 → 377 | student-skeleton → student | no |
| student-analytics | client | 4 → 4 | 1 → 1 | 209 → 98 | 238 → 125 | - | no |
| student-analytics | warm | 10 → 11 | 2 → 2 | 357 → 308 | 381 → 327 | student-skeleton → student | no |
| teacher-courses | cold | 6 → 7 | 2 → 2 | 260 → 221 | 374 → 279 | student-skeleton → student → header | YES |
| teacher-courses | client | 4 → 4 | 2 → 2 | 47 → 81 | 216 → 277 | - | no |
| teacher-courses | warm | 5 → 5 | 1 → 1 | 226 → 142 | 276 → 207 | student-skeleton → header | YES |
| teacher-course | cold | 7 → 7 | 2 → 2 | 351 → 376 | 362 → 412 | student-skeleton → header-skeleton → header | YES |
| teacher-course | client | 3 → 3 | 1 → 1 | 43 → 46 | 279 → 209 | - | no |
| teacher-course | warm | 7 → 7 | 2 → 2 | 259 → 317 | 271 → 345 | student-skeleton → header | YES |
| admin-overview | cold | 6 → 7 | 3 → 3 | 325 → 937 | 427 → 1136 | header-skeleton → header | no |
| admin-overview | client | 1 → 1 | 1 → 1 | 101 → 244 | 159 → 420 | - | no |
| admin-overview | warm | 6 → 7 | 2 → 2 | 227 → 419 | 233 → 490 | header-skeleton → header | no |

**Phone profile** (390 px, 4x CPU, 400 kbit/s, 400 ms RTT; `before` and `after` runs; network-bound, ±10 %):

| page | mode | API before → after | depth before → after | first content before → after (ms) | settled before → after (ms) | frames seen (after) | swap |
|---|---|---|---|---|---|---|---|
| login | cold | 1 → 1 | 1 → 1 | 1287 → 1419 | 7923 → 9476 | none | no |
| login | warm | 1 → 1 | 1 → 1 | 78 → 1259 | 853 → 2686 | none | no |
| student-home | cold | 9 → 10 | 2 → 2 | 11342 → 12522 | 11940 → 13219 | student-skeleton → student | no |
| student-home | client | 3 → 3 | 2 → 2 | 544 → 616 | 2018 → 2311 | - | no |
| student-home | warm | 9 → 10 | 1 → 1 | 1184 → 3041 | 1577 → 3702 | student-skeleton → student | no |
| student-tests | cold | 9 → 10 | 2 → 2 | 10941 → 15232 | 11799 → 15780 | student-skeleton → student | no |
| student-tests | client | 3 → 3 | 1 → 1 | 578 → 684 | 1666 → 2032 | - | no |
| student-tests | warm | 9 → 10 | 2 → 2 | 1725 → 2599 | 2300 → 3307 | student-skeleton → student | no |
| student-analytics | cold | 10 → 11 | 2 → 2 | 11811 → 12078 | 12317 → 12609 | student-skeleton → student | no |
| student-analytics | client | 4 → 4 | 1 → 1 | 996 → 1136 | 1622 → 1634 | - | no |
| student-analytics | warm | 10 → 11 | 2 → 2 | 1688 → 2377 | 2316 → 3018 | student-skeleton → student | no |
| teacher-courses | cold | 6 → 7 | 2 → 2 | 10509 → 10978 | 11157 → 12079 | student-skeleton → student → header | YES |
| teacher-courses | client | 4 → 4 | 2 → 2 | 559 → 649 | 1648 → 2294 | - | no |
| teacher-courses | warm | 5 → 5 | 1 → 1 | 882 → 1228 | 1336 → 1722 | student-skeleton → header | YES |
| teacher-course | cold | 7 → 7 | 2 → 2 | 12968 → 13112 | 13342 → 14190 | student-skeleton → header-skeleton → header | YES |
| teacher-course | client | 3 → 3 | 1 → 1 | 563 → 604 | 1732 → 2149 | - | no |
| teacher-course | warm | 7 → 7 | 2 → 2 | 1642 → 2069 | 1717 → 2317 | student-skeleton → header | YES |
| admin-overview | cold | 6 → 7 | 3 → 3 | 10411 → 10832 | 10742 → 12353 | header-skeleton → header | no |
| admin-overview | client | 1 → 1 | 1 → 1 | 1072 → 1130 | 2609 → 1795 | - | no |
| admin-overview | warm | 6 → 7 | 2 → 2 | 1563 → 1760 | 1702 → 2118 | header-skeleton → header | no |

Mode `client` = a click on a shell link to the next page (tests, analytics, home, the course, people, users);
its first content counts from the click. Frames are not recorded for client navigations (the frame does not
change).

What the laptop cold waterfalls show (after build; before differs only where noted):

- **Student home** (10 API requests, depth 2). Round 1 at ~220 ms, all in parallel: `/auth/me` (auth context's
  background profile refresh), `/me/privacy` (home banner), `/me/home`, `/me/lms`, `/me/home/courses?limit=50`
  (student shell). Round 2 after `/me/lms` and the course list: `/me/invitations?limit=1` (banner),
  `/courses/{exam}/exam-prep`, `/courses/{exam}/my/activity`, `/courses/{exam}/lesson-courses` (new 2026-11-08),
  `/me/access`. First content waits for `/me/home` and `exam-prep` (the home shows `PrepSkeleton` until the
  exam-prep answer). Before: 9 requests (no lesson-courses).
- **Tests page** (10, depth 2): round 1 `/auth/me`, `/courses/{id}` (course layout), `/me/lms`, `/me/home/courses`;
  round 2 `lesson-courses`, `/me/access`, `/me/invitations`, `exam-prep` **twice** (`TestsPage` and the
  getting-started checklist both ask), `exam-prep/library`. Same duplicate before.
- **Analytics** (11, depth 2): round 1 as tests; round 2 `my/saved`, `my/progress`, `my/activity`, `exam-prep`,
  `lesson-courses`, `/me/access`, `/me/invitations`.
- **Teacher list** (7, depth 2; before 6): round 1 `/auth/me`, `/me/privacy`, `/courses?role=teaching`, `/me/lms`,
  **`/me/home/courses`** (the student shell's hook runs because the student frame is rendered first; it is useless
  for this teacher); round 2 `/me/invitations` and **`/courses?role=teaching` again** (after: `TeachingList`
  remounts when `noLearning` becomes true). Frames: `student-skeleton → student → header`.
- **Course page, teacher** (7, depth 2): round 1 `/auth/me`, `/courses/{id}`, `/me/lms`; round 2 (after the layout
  has the course) `modules/unsorted`, `modules`, `todo`, `/me/invitations`. Frames: `student-skeleton →
  header-skeleton → header`: a teacher's course page waits for the course's own area declaration.
- **Admin overview** (7, depth 3): round 1 `/auth/me`, `/me/lms`; round 2 (AdminShell renders children only once
  `MeOut` is there) `/me/invitations`, `/platform/summary`; round 3 (the page) `/platform/overview`,
  `/platform/access/overview`, `/platform/health`.
- **Client navigation** (sidebar link, same tab): 3 to 4 API requests, depth 1 to 2, JS 0 to 90 kB (route chunk).
  The shell data is served from `sessionStorage` and refreshed; the page's own requests run at once.
- **Login** (1 request `/auth/ping`, the "server awake" probe). Phone cold: settled at ~7.9 s, almost all JS download.
- **Phone cold loads settle at 10 to 13 s** on both builds: about 1.1 MB of raw JS (roughly 350 kB gzip) over
  400 kbit/s plus 400 ms per round trip. Warm phone loads settle in 1.4 to 2.1 s; the API rounds (2 × 400 ms RTT
  plus server) are what remains.

### 3.3 Backend: Server-Timing per endpoint and query counts

Median over every load of the after build, laptop profile, quiet machine (`after-laptop` run); SQLite, so the
absolute milliseconds are the app's own CPU time, not Neon's. Query counts are exact and the same on PostgreSQL.

| route | total ms | db ms | queries | note |
|---|---|---|---|---|
| GET /me/home | 77 | 21 | 17 | home strips (modules next, due, news, applications, teacher request) |
| GET /courses/{id}/exam-prep | 77 | 23 | 11 | goal, scheme, history, modules with tests, pass check |
| GET /courses/{id} | 62 | 14 | 8 | user loaded twice (deps + layout) |
| GET /courses | 56 | 7 | 3 | list + one card-stats statement for the page |
| GET /me/home/courses | 56 | 16 | 6 | list + 4 per-page statements (due, modules, features, cards) |
| GET /me/privacy | 51 | 20 | 5 | |
| GET /me/lms | 48 | 18 | 6 | user, learns EXISTS (new), org member (is_teacher), org admins, guardian; + teacher_requests when learns=false (new) |
| GET /courses/{id}/modules/unsorted | 48 | 8 | 9 | |
| GET /me/access | 46 | 6 | 3 | |
| GET /courses/{id}/todo | 45 | 19 | 7 | |
| GET /courses/{id}/lesson-courses | 70 (cold) / 42 | 6 | 4 | new 2026-11-08; one statement for the rows |
| GET /courses/{id}/modules | 36 | 6 | 7 | |
| GET /me/invitations | 31 | 2 | 2 | on every page (banner) |
| GET /platform/overview | 28 | 11 | 5 | cached 60 s server-side |
| GET /auth/me | 63 (cold) / 25 | 2 | 2 | on every page (auth context refresh) |

- **No N+1**: every endpoint's statement count is fixed (the per-page statements of the course lists use `IN (...)`
  over the page; `/me/home` is 17 statements for any number of courses). Verified with the SQL capture: the only
  repeated statement is the `users` row (loaded by `get_lms_user` and again by a service that re-reads the user),
  at most x2.
- **Over-fetching**: `GET /courses/{id}` and the list endpoints select every column of `courses` (about 40,
  including `settings`, `template_settings`, `catalog_search`); harmless at this size, noted for later.
- **Per-page fixed cost**: `/auth/me` + `/me/lms` + `/me/invitations` (+ `/me/privacy` on the home, + `/me/access`
  and `/me/home/courses` in the student shell) = 4 to 6 requests of "who am I and what is my menu" on every cold
  page, 13 to 24 queries. These are the requests to merge (§5.2).
- **First call after a process start is slow because of lazy imports**: service functions import modules inside the
  function body (`from app.lms.access import plans` and the like); the first request of each endpoint after a
  cold start pays those imports (observed 300 ms to 2 s for `/me/access` in the capture script right after import,
  47 ms afterwards). On Render this happens after every spin-up.

### 3.4 Neon (production, read-only)

Production is small: `users` 18, `enrollments` 33, `courses` 11, `attempts` 14, `attempt_items` 1,360 live rows.
`EXPLAIN (ANALYZE, BUFFERS)` on the four hot shell queries (the `has_student_enrollments` EXISTS, the
`/me/home/courses` list, the `/courses?role=teaching` list, `admin_organizations`) with the busiest real user id:
execution 0.04 to 0.14 ms, 2 to 17 shared buffer hits, no disk reads. The planner chooses sequential scans on
`enrollments`, `courses`, `users` and `organizations` because the tables fit in one or two 8 kB pages, which is
the correct plan at this size; `organization_members` already uses `ix_organization_members_user_id_state`. Every
predicate these queries filter on has a covering index for when the tables grow: `ix_enrollments_user_id_state`
(user_id, state), `ix_enrollments_course_id_role_state`, `ix_courses_exam_course_id` (lesson courses),
`ix_courses_organization_id_status_deleted_at`, `ix_access_passes_user_id_ends_at`, `ix_guardian_links_guardian_user_id`,
`ix_teacher_requests_user_id`, `ix_module_progress_enrollment_id`. Migration 0027 left no gap here.

**No new index is justified now (no migration 0028).** One candidate for later, when `enrollments` has tens of
thousands of rows: a partial index `(user_id) WHERE role = 'student' AND state = 'active' AND is_test_student IS
FALSE` for the `has_student_enrollments` probe; the existing `(user_id, state)` index will serve it until then.
`pg_stat_statements` is not installed on the production database, so there is no slow-query history to read; the
Server-Timing header gives that per request from now on.

### 3.5 Cold starts, production per-request floor, plan costs

Warm production floors, `curl`, European vantage point (connect 13 to 22 ms to Render, TLS +15 ms):

| request | TTFB | note |
|---|---|---|
| Render `GET /health` (no DB) x5 | 0.27, 0.27, 0.28, 0.39, 0.57 s | the app itself answers this in ~10 ms locally |
| Render `GET /api/v1/auth/ping` (1 query) x3 | 0.30, 0.37, 0.38 s | |
| Render `POST /api/v1/auth/login` (bad password) x2 | 0.83, 1.35 s | bcrypt by design |
| Vercel `GET /ru/login` (static HTML) x3 | 0.07, 0.23, 0.42 s | edge cache |
| Vercel rewrite `GET /api/v1/auth/ping` → Render x2 | 0.38, 0.38 s | the path `/auth/me` takes (`auth-context.tsx` fetches a relative `/api/v1/auth/me`) |

So one API round trip in production costs about 0.3 s when the service is awake and the request is alone; with
the 0.1 CPU of the Free instance, ten parallel requests from one page queue behind each other.

**Render cold start.** Render Free "spins down a Free web service that goes 15 minutes without receiving any inbound
traffic" and waking it "takes about one minute" (render.com/docs/free, read 2026-11-09). The repository's uptime
workflow (`.github/workflows/uptime.yml`) requests `/health` every 30 minutes, so the service alternates: awake for
15 minutes after each ping, asleep for the next 15; a visitor in the asleep half waits for the spin-up. Measured
during this audit: the probe at 15:58 UTC (28 minutes after the 15:30 ping, 18 minutes after the last audit
request) found the service still awake (`/health` 0.35 s, then 0.28 s), so something else had requested it in the
meantime (the schedule drifts, other visitors): the ~60 s spin-up was not caught in the audit window. It is the
documented behaviour and the owner has seen it; the Render dashboard's event log shows every spin-down/spin-up
with a timestamp, and the Server-Timing header will make a woken request recognisable (a TTFB of tens of seconds
with a `total` of a few milliseconds).

**Neon cold start.** The project `noisy-sound-20763725` is on `free_v3`, compute 0.25 to 2 CU, `suspend_timeout_seconds:
0` (= the plan's default, "after 5 minutes"); Neon's documentation says a suspended compute reactivates "within a
few hundred milliseconds" of the next query and that on the Free plan this "cannot be turned off"
(neon.com/docs/introduction/scale-to-zero, read 2026-11-09). The backend's attempt sweep is scheduled by incoming
requests (`app/lms/attempts/sweep.py`), not by a timer, so nothing touches the database while nobody uses the site
and the compute suspends 5 minutes after the last request even when Render is awake. The uptime ping does not open a
database connection (`/health` reports `"database":"not_checked"`), so it does not keep Neon awake either.
Measured during this audit: at the same probe the first database-touching request after the quiet period took **0.97 s** to first byte
(`GET /api/v1/auth/ping`, one query) against 0.31 s and 0.33 s for the next two: the Neon resume plus a new
connection cost about **0.65 s**, once, on the first request after 5 idle minutes.

**What removes each cold start and what it costs** (prices read 2026-11-09; the owner decides, nothing was changed):

| cold start | change | monthly price | source |
|---|---|---|---|
| Render spin-down (≈60 s) | move the web service to the Starter compute plan (`0.5c-512mb`, 0.5 CPU, 512 MB); paid instances never spin down and the URL stays | **$7/month** per service (third-party price tables, consistent across sources, the official pricing page draws prices client-side and could not be read by the fetch tool; verify in the Render dashboard before paying) | render.com/docs/free ("upgrade your service to any paid compute plan"), render.com/docs/compute-plans (plan ids and sizes), activepieces.com/blog/render-pricing-2026-free-tier-workers-total-cost, livemy.app/blog/render-pricing (prices) |
| Render spin-down, cheaper but partial | shorten the uptime ping to every 10 minutes (GitHub cron may delay or skip runs) | $0 | keeps the service awake most of the time; still 0.1 CPU, still sleeps when GitHub skips |
| Neon suspend (≈0.5 to 1 s on the first request after 5 idle minutes) | Neon Launch plan with scale-to-zero turned off: pay per use, 0.25 CU always on = 0.25 × 730 h × $0.106 ≈ $19.4 + storage $0.35/GB-month (database is under 1 GB) | **≈ $20/month** | neon.com/pricing and neon.com/docs/introduction/plans (Launch $0.106/CU-hour, $0.35/GB-month, "Scale to zero ... can be disabled" on paid plans) |
| Neon suspend, cheaper | keep Free; add a database touch to the ping (the ping would have to run every <5 minutes; 0.25 CU always on is ≈180 CU-hours/month, above the Free plan's 100 CU-hours) | not viable 24/7 on Free | neon.com/pricing (100 CU-hours per project) |

Recommendation: Render Starter ($7) removes the only cold start users notice (a minute); Neon's half-second resume
once per quiet 5 minutes is tolerable until there are paying students; the Server-Timing header (`db` part) will show
it in production as a single slow first request. Both together ≈ $27/month.

### 3.6 Production public pages

`https://ort-platform-nu.vercel.app`, same script, `PERF_PUBLIC_ONLY=1`, 2026-11-09, no sign-in:

| page | profile | mode | requests | API | API depth | first content | settled | JS kB | frames seen | swap |
|---|---|---|---|---|---|---|---|---|---|---|
| landing | laptop | cold | 37 | 0 | 0 | 992 | 1884 | 955 | header | no |
| landing | laptop | warm | 37 | 0 | 0 | 41 | 144 | 955 | header | no |
| login | laptop | cold | 31 | 1 | 1 | 208 | 716 | 959 | none | no |
| login | laptop | warm | 31 | 1 | 1 | 51 | 1239 | 959 | none | no |
| landing | phone | cold | 38 | 0 | 0 | 2763 | 14623 | 955 | header | no |
| landing | phone | warm | 38 | 0 | 0 | 176 | 957 | 955 | header | no |
| login | phone | cold | 31 | 1 | 1 | 1349 | 7912 | 959 | none | no |
| login | phone | warm | 31 | 1 | 1 | 112 | 827 | 959 | none | no |

- The login page's one API call (`GET /auth/ping`, the "server is awake" probe) took 342 ms on the laptop profile
  (started at 374 ms, done at 716 ms) with the Render service awake: the production per-request floor of §3.5 seen
  from the browser.
- Landing cold on the phone profile settles at 14.6 s (hero images and the dictionary), first content at 2.8 s; login
  cold 7.9 s to settle (JS), first content 1.3 s. Warm loads: 0.8 to 1.0 s to settle, content under 200 ms.
- Logged-in production numbers are not in this audit (no owner password); the after-deploy check records them
  (§7).

## 4. What got worse on 2026-11-08 and why

| change | commit / file | effect measured |
|---|---|---|
| `TeachingList` moved between two parents when `noLearning` flips (`<TeachingList noLearning/>` vs inside `<TabPanel>`) | item 2, `frontend/src/app/[lang]/courses/page.tsx` lines 162-172 | `GET /courses?role=teaching` twice on every cold teacher list load (6 → 7 API requests), the list skeleton shows twice |
| `hideLearning` depends on `me.has_student_enrollments` | item 2, `LmsShell.tsx` `hideLearning`, `areas` | the Learning pill is drawn, then removed when `MeOut` arrives (one more visible shift for teachers after the student→header swap) |
| `/me/lms` runs `has_student_enrollments` and, for teachers without enrollments, `approved_notice` (`teacher_requests`) | item 2, `backend/app/lms/teachers/router.py` `_me`, `service.py` | 4 → 6 queries on the request every page waits for; +~5 ms locally, one more round trip to Neon in production |
| a listener reloads `/me/lms` on `ort:lms-me-stale` | item 2, `useLmsMe.tsx`, `meStale.ts` | correct and cheap (only after join/leave); not a regression |
| student shell asks `/courses/{exam}/lesson-courses` per exam course | item 3, `useStudentShellData.ts` `loadLessons` | +1 API request (4 queries) on every student page, in round 2 |
| `/me/home` gained `is_video`, `exam_course_id` and a per-course row_number scan | item 3, `home/service.py` | no measurable change (17 statements before and after) |
| org switcher for admins, `useCurrentOrg` | item 4, `LmsShell.tsx`, `currentOrg.ts` | no request, no measurable change |
| `/platform/overview`, admin shell cards | item 5, `AdminShell.tsx`, `admin/page.tsx` | one more request on the admin overview (6 → 7); the depth was already 3 before (`/me/lms` → shell `summary` → page), the page now waits for the shell's `summary` before `overview`, `access/overview` and `health` |
| +2 to +5 kB first-load JS on every route, +12 kB on `/courses/new`, +8 kB on settings | items 0 to 5 | §3.1 |

The flash itself predates the deploy (`student-skeleton → student → header` on `fe4a1e8` too, §3.2). The owner saw it
"since the last deploy" because the deploy made the wrong frame live longer and do more (the duplicate list load,
the extra shell requests, the pill shift) and because item 2 changed what the correct teacher header looks like, so
the swap became more noticeable.

## 5. Fix design

Principles: improve the existing architecture (the `LmsShell` / `useLmsMe` / `useStudentShellData` trio stays; no
new state library), ORT player and ORT screens unchanged, trilingual strings for anything visible, server-side
authorization unchanged (caches draw menus; every request is still authorised on the server).

### 5.1 The shell is decided once, before anything is rendered

**Shell kinds**: `student` (sidebar + tab bar), `app` (the `AppHeader` frame for teachers, organization admins,
platform admins, guardians on their areas), `player` (no chrome), `neutral` (a loading frame with no sidebar, no
areas: brand bar + content skeleton; used only when nothing is known).

**Which `/me/lms` fields decide it** (and nothing else): `is_teacher`, `can_create_courses`, `is_platform_admin`,
`has_student_enrollments`, plus the URL (`rest`, `?view=`) and the course layout's declaration for course pages.
Pure function, new file `frontend/src/lib/lms/shellKind.ts`:

```
shellKindFor({ rest, view, declared, me }):
  player route                              → "player"
  me == null                                → "neutral"
  area = areaFromUrl(rest, view, coursesDefault(me))   // the existing rule, moved here unchanged
  area != "learning"                        → "app"
  course page and (teaches(me)) and declared == null    → "neutral"   // today: awaitingCourseArea
  course page and declared == "teaching"    → "app"
  otherwise                                 → "student"
teaches(me) = me.is_teacher || me.can_create_courses || me.is_platform_admin
coursesDefault(me) = teaches-and-not-only-admin rule exactly as LmsShell computes it today
```

`hideLearning` stays a header detail (it changes the pills, not the frame) and must not flip the frame.

**Where `me` comes from at render time**: the session cache, read synchronously. Today `useLmsMeLoader` already keeps
`MeOut` in memory and `sessionStorage` (`ort_lms_me`, keyed by the token's tail) but reads it only once `enabled`
is true, which happens after the auth context's effect; the first client render has `me == null` and the pre-auth
branch guesses from `userProfile` (also null on the first render). Change: extract the cache into
`frontend/src/lib/lms/meCache.ts` (`readCachedMe(): MeOut | null`, `writeCachedMe`, same key and token rule), and
let `LmsShell` call `readCachedMe()` in a `useSyncExternalStore`-style read with a server snapshot of `null`, so:

- server render and the first client render: `me == null` → `neutral` frame (hydration-safe);
- the next render (same tick, after hydration, before any paint of content): cached `me` → the right frame;
- no cache (first sign-in, new tab): `neutral` frame until `/me/lms` answers, then the right frame, once.

The `neutral` frame replaces today's two pre-auth skeletons (the student one with the dark sidebar and the header one
with `AreaPillsSkeleton`): a 56 px white top bar with the brand and a round avatar placeholder, then the content
skeleton; it must look acceptable as the first frame of both shells (no sidebar strip, no pills). On `lg` the
student shell then slides its sidebar in; that is one change, not a swap.

**A background refresh that would change the kind is applied on the next navigation, never mid-page.**
`LmsShell` latches `shellKind` per `pathname`: `const [latched, setLatched] = useState<{ path, kind }>()`; it
recomputes when `pathname` changes, when `me` goes from `null` to a value (the cold case), or when the user
triggers `reload` (the `ort:lms-me-stale` event after join/leave is such a trigger: the page that joined keeps its
frame, the next page gets the new one). A fresh `/me/lms` that differs from the cache while the kind stays the
same (for example `admin_organizations` changed) updates the header content immediately, as today. Login writes
nothing; the first `/me/lms` after login fills the cache. Sign-out and a 401 clear it (already so).

**`/courses` for teachers**: `courses/page.tsx` renders one `TeachingList` instance whatever `noLearning` is (the
tabs are hidden or shown around it; `noLearning` toggles only the `Tabs`, not the list's parent), so the list loads
once. `hasTeaching` there uses the cached `me` first (same `readCachedMe`), the profile only as a fallback.

**Course pages of teachers**: the layout's course answer decides `declared`; until it arrives the kind is `neutral`
(today `awaitingCourseArea` already prevents the student frame; keep that, but through `shellKindFor`). With the SWR
cache of §5.2 the course answer is usually cached, so the frame is right at once on repeat visits.

**Test**: `shellKind.check.ts` (same style as `studentNav.check.ts`) with the cases: student cold/warm, teacher
without enrollments on `/courses` with and without `?view=`, teacher with enrollments, admin on `/admin`, teacher
on a course page before and after declaration, player route. E2E `frontend/e2e/shell-stable.spec.ts`: the
MutationObserver from the perf script as a helper; for teacher, student and admin, cold and warm, assert the frame
sequence contains at most one of `student` / `header` and never both; also assert no `aside` appears for the
teacher at any time and no `header` (app) for the student.

### 5.2 Fewer requests, parallel, cached (stale-while-revalidate), prefetch, no reloads

**One bootstrap request for the shell.** New backend route `GET /me/bootstrap` (module
`backend/app/lms/home/bootstrap.py`, router mounted next to `/me/home`, policy `authenticated` in the route
inventory) composing existing service functions, read-only, 12 to 18 queries total (today 13 to 24 across 4 to 6
requests):

```
BootstrapOut {
  me: MeOut                               # teachers.router._me (unchanged)
  pending_invitations: int                # home.service._pending_invitations
  privacy: PrivacyBannerState             # what /me/privacy's banner needs (reconsent due, data request pending), not the full page
  student: {                              # only when me.has_student_enrollments or the profile has no teaching
    courses: HomeCourseOut[]              #   home.service first page, limit 50 (today /me/home/courses?limit=50)
    access: MyAccessOut                   #   access.router._my_access
    lesson_courses: { [exam_course_id]: LessonCourseOut[] }   # courses.lesson_courses for every exam-prep course in `courses` (≤ 20 each)
  } | null
}
```

Nothing new is computed; the client keeps its per-token `sessionStorage` cache and the same shapes
(`useStudentShellData`'s `Cache` gets filled from one answer). `/me/lms`, `/me/home/courses`, `/me/access`,
`/me/invitations`, `/me/privacy`, `/courses/{exam}/lesson-courses` stay for the pages that use them alone and for
older clients; the shell stops calling them on load. Effect per cold student page: 10 → 5 requests (bootstrap,
`/me/home`, `exam-prep`, `my/activity`, plus `/auth/me` until §5.2c), depth 2 → 1 on warm loads (the cached
bootstrap gives the course id at once) and 2 on cold loads (bootstrap, then the page's requests). Teacher list:
7 → 3 (bootstrap, `/courses?role=teaching`, `/auth/me`). Admin overview: 7 → 5, depth 3 → 2.

**A small in-house SWR cache, no library.** `frontend/src/lib/lms/swr.ts` (~120 lines, under 1.5 kB gzip; a
library such as `swr` is 4 to 5 kB gzip and would be the only one of its kind in the bundle, so not worth it):

```
cached<T>(key, fetcher, { ttl = 30_000, storage = "session" | "memory", token = activeToken() }): Promise<T>
  // returns the stored value at once when fresh; when stale returns it and refetches in the background;
  // in-flight requests are shared (two components asking the same key cause one request);
  // keyed by token tail like the existing caches; a 401 or sign-out clears everything
useCached<T>(key, fetcher, opts): { data, stale, error, refresh }   // thin hook over cached(), useSyncExternalStore
invalidate(prefix)
```

Rules: use it for `GET /me/bootstrap` (ttl 60 s; the stale event from `meStale.ts` calls `invalidate("bootstrap")`
+ refresh), `GET /courses/{id}` (ttl 60 s; the course layout reads it, so switching tabs inside a course no longer
re-asks the course), `GET /courses/{id}/exam-prep` (ttl 30 s; removes the duplicate on the tests page and the
getting-started checklist reads the same entry), `/platform/summary` (ttl 60 s). Mutations that change those
answers call `invalidate` (join/leave: already signal `meStale`; goal change on exam-prep: `invalidate("exam-prep:")`;
course settings save: `invalidate("course:" + id)`). Attempt, grading and content endpoints are never cached
(attempts and grades must stay exact; ORT untouched).

**Parallel page requests.** Where a page needs the course only for its id or its template, start the page's requests
at mount with the id from the URL and let the layout's course answer arrive in parallel: `TeacherCoursePage`
(`modules`, `modules/unsorted`, `todo`), `TestsPage` (`exam-prep`, `exam-prep/library`), analytics
(`my/saved`, `my/progress`, `my/activity`). With the cached course this already happens on warm loads; on cold loads
it removes one round. A 403 for a student who hits a staff endpoint is impossible there because those pages render
only inside the declared area; where a page truly needs the course (the template decides which component renders)
it keeps waiting. Admin overview: `AdminShell` renders children as soon as the cached `me` says admin (no spinner
when cached) and the overview page fires `/platform/overview`, `/platform/access/overview`, `/platform/health`
together with the shell's `/platform/summary`.

**`/auth/me` on every page.** `auth-context.tsx` refreshes the cached profile on every load through the Vercel
rewrite (380 ms in production, see §3.5). Keep the refresh but (a) call the backend origin directly like every other
request (`API_BASE_URL`), and (b) run it after first paint (`requestIdleCallback` or a 2 s timer) and skip it when
the stored profile is younger than 10 minutes. The LMS pages never wait for it.

**Prefetch main links.** Next's `<Link>` already prefetches route chunks for links in the viewport in production;
keep it (do not add `prefetch={false}` to shell links). Add data prefetch on hover/focus for the shell's main links:
`onMouseEnter`/`onFocus` call `cached()` for the target page's cheap, side-effect-free GETs (`exam-prep` for Тесты,
`my/progress` for Аналитика, `courses?role=teaching` for Обучение). Bounded to the shell's own links.

**Hard navigations found** (`window.location.*` in `frontend/src`): `StudentShell.tsx:429` full reload after leaving
a course (replace with `router.replace` + `invalidate("bootstrap")`, the cache rules above make it unnecessary);
`lib/api.ts:66,75,82` entering/leaving Student view (intentional: another token, everything must reset; keep);
`lib/api.ts:118` the privacy gate redirect (keep); `PwaProvider.tsx:101` the service-worker update reload (keep);
`courseFiles.ts:63`, `assignments.ts:117` file downloads (keep). Tab switches in both shells are `<Link>`s already.

### 5.3 Backend

- `GET /me/bootstrap` (above). Composition only; each part keeps its own tests, plus one test that the bootstrap
  answer equals the parts' answers for a student, a teacher and an admin (same user, same request time).
- Lazy imports: a `warm_up()` in the lifespan imports the modules that service functions import lazily
  (`app.lms.access.plans`, `settings`, `app.lms.modules.service`, `app.lms.exam_prep.layout`, …) so the first request
  after a spin-up does not pay them. One function, one test that it imports without error.
- `Server-Timing` stays (this branch): per-request total, db time, query count; the Vercel frontend can read it
  (`expose_headers`), developer tools show it (`Timing-Allow-Origin`).
- No index change (§3.4). The `users` row is loaded twice on `/courses/{id}` (`get_lms_user` and the layout's
  service) and `/me/lms` could use one statement for `is_teacher` + `admin_organizations`; both are 1 to 2 ms on
  Neon and not worth a slice now.
- Over-fetching: `CourseOut` for the student shell needs ~10 of the ~40 `courses` columns; leave as is until
  payload sizes matter (they are under 10 kB).

### 5.4 Bundle

- The language dictionary is the only big first-screen asset (91 to 93 kB gzip per language). Split each language's
  JSON at build time into `core` (keys under `common.*`, `shell.*`, `student.*`, `home.*`, `examPrep.*`, `access.*`,
  `auth.*`, `landing.*`, `privacy.*`, `lms.common.*`, `courses.list.*`) and `staff` (everything else: editors,
  admin, org, grading, modules editor, exam templates), both generated from the same `en.json`/`ky.json`/`ru.json`
  (the parity script and the source files do not change; a small generator in `frontend/scripts/` writes
  `src/lib/i18n/generated/<lang>.core.json` and `.staff.json`, ignored by git, run from `prebuild`). The i18n context
  loads `core` as today and `staff` lazily when a key outside `core` is asked (`t()` returns the key's fallback for
  one render and triggers the load; a `useStaffDictionary()` call in `AreaShell`/`AdminShell`/`OrgShell`/the course
  staff layout preloads it so staff never see fallbacks). Expected: the student and public pages drop 55 to 65 kB
  gzip (about 1.2 s on the Slow 4G profile), staff pages unchanged. Measure with the script's "JS kB" column.
- KaTeX: already confined to content routes. Nothing to do for the first screen.
- Nothing else qualifies: no chart, editor or date library is in the bundle.

## 6. Slices

All slices run in parallel except where noted; strict file ownership; each ends by re-running the measurement
(§7) and pasting its before/after rows into §8 of this document.

### S1 Shell decided once (Opus)

Files: `frontend/src/lib/lms/shellKind.ts` (new), `shellKind.check.ts` (new), `frontend/src/lib/lms/meCache.ts`
(new: the cache code moved out of `useLmsMe.tsx`, same key `ort_lms_me`, same token rule; `useLmsMe.tsx` keeps its
exports and imports the cache: **the only edit to `useLmsMe.tsx` in this slice**), `frontend/src/components/lms/LmsShell.tsx`
(neutral frame, `shellKindFor`, latch per pathname, remove the two pre-auth skeleton variants), `frontend/src/components/ui/AppHeader.tsx`
(only if the neutral bar needs a shared `NeutralTopBar` export), `frontend/src/app/[lang]/courses/page.tsx` (one
`TeachingList` instance; cached `me` for `hasTeaching`), `frontend/e2e/shell-stable.spec.ts` (new), i18n: the
neutral frame reuses `lms.common.loading`, no new strings expected.
Tests: `shellKind.check.ts` cases from §5.1; e2e `shell-stable.spec.ts` (teacher, student, admin; cold and warm;
1440 and 390 px) green; `header-areas.spec.ts`, `student-shell.spec.ts`, `student-home.spec.ts`, `course-nav.spec.ts`
unchanged and green; `npx tsc --noEmit`.
Measure: `frames seen` has no `student → header` or `header → student` on any row; teacher list API requests
7 → 6 (one `/courses`) before S2 lands.
Must land first: S2 and S3 import `meCache.ts` and `shellKind.ts`; they may start on their backend/other files at
once and rebase.

### S2 Bootstrap request and SWR cache (Opus)

Files: backend `app/lms/home/bootstrap.py` (new), `app/lms/home/router.py` (mount), `app/lms/home/schemas.py`
(`BootstrapOut`), `app/core/route_inventory.py` (one line), `tests/lms/test_bootstrap.py` (new), `app/main.py`
lifespan `warm_up()` (one call; module `app/core/warmup.py` new). Frontend: `src/lib/lms/swr.ts` (new),
`src/lib/lms/bootstrap.ts` (new: the fetcher and the shape), `src/lib/lms/useLmsMe.tsx` (the loader reads
`bootstrap.me` through `swr`; `reload` and the stale listener invalidate it; exports unchanged),
`src/components/lms/student/useStudentShellData.ts` (courses, access, lesson courses from the bootstrap; `forget`,
`loadCourses` keep working through `invalidate`), `src/components/lms/PendingInvitationsBanner.tsx` and
`src/components/privacy/PrivacyBanner.tsx` (read the bootstrap fields; keep their own request only when rendered
outside `LmsShell`), `src/lib/auth-context.tsx` (`/auth/me` via `API_BASE_URL`, deferred, skipped when fresh),
`src/components/lms/student/StudentShell.tsx` line 429 (`router.replace` + invalidate instead of
`window.location.assign`), `src/app/[lang]/courses/[courseId]/layout.tsx` (course through `swr`).
Tests: backend `test_bootstrap.py` (student / teacher / admin answers equal the parts; a revoked teacher; 401 without
a token; the route is in the inventory with policy `authenticated`); frontend `swr.check.ts` (fresh / stale /
in-flight dedup / token change / invalidate); e2e `student-shell.spec.ts`, `student-home.spec.ts`, `exam-prep.spec.ts`
(join → the shell shows the course without a reload), `teacher-to-student.spec.ts`, `privacy.spec.ts` green;
backend suite green (`~4529 passed`).
Measure: student home cold 10 → ≤ 6 API requests, warm depth 1; teacher list 7 → ≤ 3; "first content" warm ≤ 250 ms
laptop; phone warm settled ≤ 1.2 s.

### S3 Page waterfalls (Opus)

Files: `src/components/lms/home/ExamPrepHome.tsx` (render the course header and the strips' frames before
`exam-prep` arrives; skeleton only inside the numbers; `exam-prep` through `swr`), `src/components/lms/examPrep/TestsPage.tsx`
and `src/components/lms/student/gettingStarted.tsx` (`exam-prep` through `swr`: one request), `src/components/lms/course/TeacherCoursePage.tsx`
(fire `modules`, `modules/unsorted`, `todo` at mount), `src/components/lms/progress/*` analytics page container
(fire its three requests at mount), `src/components/lms/admin/AdminShell.tsx` (no spinner when `me` is cached;
`/platform/summary` not awaited before children), `src/app/[lang]/admin/page.tsx` (parallel requests), shell link
hover prefetch in `src/components/lms/student/StudentShell.tsx` (nav links only; S2 owns line 429, coordinate the
one file by landing S2's one-line change first) and `src/components/ui/AppHeader.tsx` sections (after S1).
Tests: e2e `student-analytics.spec.ts`, `exam-prep.spec.ts`, `course-nav.spec.ts`, `admin-overview.spec.ts` green;
`tsc`.
Measure: API depth cold ≤ 2 on every page, admin overview 3 → 2; tests page duplicate `exam-prep` gone (10 → 9
before S2, ≤ 5 after); student home first content cold laptop ≤ 600 ms (today ~1.4 s).

### S4 Dictionary split (Sonnet)

Files: `frontend/scripts/split_dictionaries.mjs` (new), `package.json` (`prebuild`), `src/lib/i18n/context.tsx`,
`src/lib/i18n/dictionaries/{en,ky,ru}.tsx`, `src/lib/i18n/lazy-json.d.ts`, `.gitignore` (generated files), a
`useStaffDictionary()` call in `AreaShell.tsx`, `AdminShell.tsx`, `OrgShell.tsx` and the course staff layout.
Rules: `en.json`/`ky.json`/`ru.json` stay the single source; `scripts/check_i18n_parity.py` unchanged and green;
no key renamed.
Tests: `tsc`; parity script; e2e `header-areas.spec.ts`, `admin-overview.spec.ts`, `quiz-editor.spec.ts` (staff
strings present, no raw keys visible: add one assertion that no text matches `/^[a-z]+(\.[a-zA-Z]+)+$/` on the
admin and quiz-editor screens), `student-home.spec.ts`.
Measure: "JS kB" of login and student pages −200 kB raw or more; phone cold login settled 7.9 s → ≤ 6.5 s.

### S0 (done on this branch, Fable)

`backend/app/core/server_timing.py` + `main.py` wiring + `tests/test_server_timing.py`; `frontend/e2e/perf-waterfall.spec.ts`
+ `frontend/playwright.perf.config.ts`; this document.

Order: S1 → (S2 ∥ S3 ∥ S4). S2's backend part can start immediately. Hosting plan changes (§3.5) are the owner's.

## 7. Measurement script

`frontend/e2e/perf-waterfall.spec.ts`, run with its own config so that no server is started by Playwright
(the same backend serves both builds one after another). Not part of CI (`test.skip` without `PERF_RUN`; the
default `playwright.config.ts` run skips it).

```bash
# 1. scratch backend from this branch (seeded; wipes E2E_DIR)
E2E_DIR=/tmp/ort_perf E2E_API_PORT=8831 E2E_WEB_ORIGIN=http://127.0.0.1:3031 bash scripts/e2e_backend.sh &
# 2. a production build of the frontend to measure, served on 3031
rsync -a --exclude node_modules --exclude .next frontend/ /tmp/ort_perf_fe/ && ln -s "$PWD/frontend/node_modules" /tmp/ort_perf_fe/node_modules
(cd /tmp/ort_perf_fe && NEXT_PUBLIC_API_URL=http://127.0.0.1:8831 npx next build && npx next start -H 127.0.0.1 -p 3031 &)
# 3. the measurement (both profiles; PERF_PROFILES=laptop for a quick run; PERF_RUNS=3 for medians)
cd frontend && PERF_RUN=1 PERF_LABEL=after-S2 PERF_WEB=http://127.0.0.1:3031 E2E_DIR=/tmp/ort_perf \
  npx playwright test -c playwright.perf.config.ts e2e/perf-waterfall.spec.ts
# → /tmp/ort_perf/perf/after-S2.md (+ .json): page table, per-page API waterfall, Server-Timing per route
# 4. production public pages (no sign-in)
PERF_RUN=1 PERF_PUBLIC_ONLY=1 PERF_LABEL=prod PERF_WEB=https://ort-platform-nu.vercel.app E2E_DIR=/tmp/ort_perf \
  npx playwright test -c playwright.perf.config.ts e2e/perf-waterfall.spec.ts
```

After deploy: open the site signed in as the owner with developer tools → Network; every API answer carries
`Server-Timing` (Chrome shows it in the Timing tab); compare `total` with the request's TTFB to split app time from
Render's proxy and cold start. Record the production per-page numbers in §8.

## 8. Before / after per slice

Filled in by the implementers (rows copied from the script's page table; laptop and phone, cold and warm).

| page | profile | mode | before (this audit) API / depth / first content | after S1 | after S2+S3 | after S4 |
|---|---|---|---|---|---|---|
| (to fill) | | | | | | |
