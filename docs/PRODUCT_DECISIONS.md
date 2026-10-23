# Product decisions (owner answers, 2026-10-21)

Source: answers to the 15 open questions in `PROJECT_UNDERSTANDING.md` §8. The Canvas documents in `docs/` are drafts; nothing in them is binding. Real goals first, flexible design.

**Goal**: a flexible, safe, Canvas-style LMS where teachers have their own students, build and restructure their own courses, and own their own questions. ORT (exam, scoring, ky/ru) must keep working, as just one kind of course.

| Topic | Decision |
|---|---|
| Teachers | **Superseded 2026-10-22**: see "Decisions 2026-10-22 (teachers)" below. Originally: self sign-up, a sign-up is a teacher. Roles stay per enrollment. |
| The 12k questions | Not important. ORT becomes a course a teacher creates (upload ORT questions) and can make visible to everyone. No platform-owned bank required. |
| Sharing questions between teachers | **Superseded 2026-10-24**: shared question banks per organization (Phase 9). Originally: later. |
| Sections / cohorts | None. One course = one group of students. |
| Schools / Accounts (B2B) | **Superseded 2026-10-24**: organizations from Phase 6 (see "Owner decisions 2026-10-24"). Originally: not near term. |
| Grading | Flexible per course/test. Not ORT-only. ORT scaling is one grading scheme among others. |
| Existing users and data | Testers only. May be deleted. Nothing to migrate. |
| Deleting content | Sophisticated: soft delete, history kept. |
| Images | Currently lost on restart (ephemeral disk). Persistent storage must be built. |
| Privacy of minors | Probably add consent later. Design with it in mind. |
| Languages | Three: English, Russian, Kyrgyz. The teacher controls which languages a course uses. |
| Access | Students sign in, browse and enroll in courses, possibly through an enrollment form the teacher creates. Not admin-granted PINs. |
| Hard-coded admin email | Removed (done). |
| Production access | Read access to Render/Neon granted for measuring. (Extended 2026-10-22: see "agent workflow" A below.) |
| Order of work | Security/integrity fixes first (done on `fix/security-integrity`), then architecture design, then storage/DB changes. |
| Scale | Target about 6,000 students active at the same time (added 2026-10-22). Hosting (Vercel/Render/Neon) must be verified against this. |

## Decisions 2026-10-22 (hosting and deploy)

| Topic | Decision |
|---|---|
| Security branch | Merged to `main` and deployed (`ca48b1f`) on 2026-10-22; Neon backup branch `backup-2026-10-22-before-security-deploy` taken first. |
| D1-D18 | Owner has not replied per item; recommended defaults stand until changed (D4 stays open until the capacity review). |
| Budget | Owner is cost-sensitive: target about $30/month at most. A VPS plus Neon was rejected as more expensive than the current three vendors. |
| Hosting | Keep Vercel + Render + Neon for now. Render is on the **Free** plan (sleeps, ~0.1 CPU, 1 worker) and must be upgraded before launch. Scale Render up only for exam windows (billed per second). A VPS for the API is the fallback if the load test shows daily heavy load. |
| Domain | None yet; added after the LMS is finished. |
| Scale | 6,000 concurrent target and "plan for more later" confirmed. |

## Decisions 2026-10-22 (teachers)

| Topic | Decision |
|---|---|
| Who can create courses | **Partly superseded 2026-10-24** (see below): teachers now arrive by invitation from an org admin or platform admin; the request flow stays only for independent teachers; course creation is an organization setting. Original (2026-10-22): only admin-approved teachers; everyone who signs up is a student; a user may request teacher access; a platform admin approves or rejects it. Revocable. |
| Age (D5) | Not a problem for course creation, because an admin verifies every teacher first. Student minimum age and consent wording are deferred. |
| D2 (domain/CDN) and D5 (age/consent) | Postponed until the overall build is finished and a domain exists. |
| Platform admin | Approves teacher requests (and does support/moderation). Role is read from the database on every request. |
| Admin area | A platform admin page: teacher requests, users, course moderation, audit log. |
| First admin | The owner's existing account (already `admin` in production). Set via `make_admin.py`, never hard-coded. |

## Decisions 2026-10-22 (agent workflow)

| Topic | Decision |
|---|---|
| A. Autonomy | The agent may commit, push any branch, merge into `lms` and `main`, and deploy without asking. Guardrails: (1) before any merge to `main` touching models/migrations/DB files, create a Neon backup branch (Neon MCP, project `noisy-sound-20763725`); (2) after each deploy, check `https://ort-platform-w77q.onrender.com/health` shows the new commit, else revert and redeploy; (3) never force-push `main`; (4) only these need the owner's explicit OK: Phase 5 cutover, deleting/wiping Neon data, spending money (plan upgrades, paid services), anything needing a password/secret from the owner. Otherwise the agent does not ask: it takes the documented default or safest reasonable choice and records it here. |
| B. Models (revised 2026-10-22) | Main session on **Fable**, orchestrator only: plans each phase, splits it into slices, writes precise briefs, reviews every diff, runs the full gates, commits/pushes/merges/deploys; keeps its own reading and typing minimal. If Fable is not available in `/model`, the main session runs on **Opus** with the same rules. Subagents: `architect` (**Opus**) for hard design and review (authz, attempt engine, grading, gating, concurrency, security, phase design drafts); `implementer` (**Sonnet**) for bulk implementation from briefs (goal, exact files, schema/API shape, tests that must pass), independent slices in parallel; `helper` (**Haiku**) for mechanical edits. No subagents for single-file lookups. |
| B2. Models (second revision, 2026-10-22; replaces the subagent part of B) | No Haiku; `helper` agent deleted, mechanical edits go to `implementer` on Sonnet. Defaults: `implementer` = **Opus**, `architect` = **Fable**. Per-task model via the Agent tool's `model` parameter: **sonnet** for simple, well-specified work (straightforward CRUD, tests from a clear spec, UI following an existing pattern, i18n keys, renames); **opus** (default for real code: services, endpoints, migrations, attempt engine, grading, gating, concurrency); **fable** only for the hardest problems (architect design/review of authz, attempt engine, grading and concurrency; the final security review of each phase; any task where opus failed or got stuck once). Escalate on failure sonnet → opus → fable; never retry a failed task on the same model. No Haiku. Main-session rule unchanged. |
| C. Render MCP | May return "unauthorized"; not a blocker. Use `/health` and git (Render auto-deploys from `main`). |
| D. Load test | Still must run before Phase 3, on free resources (a Neon branch + local or free-tier backend). If a meaningful test needs a paid service, write down what was tested and ask the owner only for that spending decision. |
| E. `AGENTS.md` | Describes the old platform; its §6 commands and §7 hard rules still apply. Current plan and rules: `HANDOFF_NEXT_AGENT.md`. |
| Production access | Supersedes "read access only" above: write access within rule A. |
## Decisions 2026-10-22 (Phase 0, agent defaults)

| Topic | Decision |
|---|---|
| Migrations on the Free plan | Render Free has no pre-deploy hook, so Alembic runs at app startup (Postgres only), in one transaction under `pg_advisory_xact_lock`. Production Neon is stamped `0001_baseline` on first start. Move to a pre-deploy command when Render is upgraded (D4). |
| Phase 0 to `main` | Phase 0 has no user-visible LMS features but contains hardening and the Alembic stamp, so it is merged to `main` too (after a Neon backup branch). Phases 1–4 stay on `lms` until the Phase 5 cutover, per the plan's strangler strategy. |
| Postgres driver | URLs are pinned to `postgresql+psycopg2://` (SQLAlchemy 2.1 defaults to psycopg 3). |
| English in old pages | Old pages keep their inline ky/ru strings; English shows the non-ky branch until the cutover deletes them. Language buttons show endonyms (Кыргызча, Русский, English). |
| Upload limits | Images only (PNG/JPEG/GIF/WEBP by content), 5 MiB cap, 400 for invalid content, 413 for oversize. |

## Decisions 2026-10-22 (Phase 1, agent defaults)

The full list is P1-1 … P1-23 in `docs/phases/PHASE_1_DESIGN.md` §1. Highlights:

| Topic | Decision |
|---|---|
| Join code | 8 characters, no look-alikes (31-symbol alphabet), shown as `ABCD-EFGH`; works only while published, mode `invite_code`, not deleted. Every join failure returns the same 404. |
| Enrollment modes | Phase 1 supports `invite_code` and `closed`; `open` and form modes come with the catalog (Phase 7). |
| Class limit | Counts active students only. |
| Roster privacy | Students see only staff names; never other students or emails. |
| Owner powers | Only the owner deletes, restores, transfers ownership, or adds/removes/demotes teachers. Owner restores only courses they deleted themselves; an admin takedown is restored only by an admin (security review). |
| Teacher revoke | Blocks new courses and receiving ownership; existing courses stay manageable (P1-10). Admin can moderate them. |
| Platform admin | Script-only grant (`make_admin.py`); all admin power goes through audited `/api/v1/platform/*`; no bypass inside `/courses`. |
| Rate limits | DB-backed fixed windows, own small connection pool. Per-user join limits enforced; the per-IP rule is **log-only** (`RATE_LIMIT_IP_ENFORCE=False`) until the real Vercel→Render `X-Forwarded-For` chain is verified. |
| Add staff | Every miss returns the same `user_not_found` (no email enumeration). Invite-accept for staff is a Phase 7 candidate. |
| Errors | New endpoints (incl. request validation) use `{"error":{code,message,details}}`; old endpoints keep `detail`. |

## Decisions 2026-10-22 (Phase 2, agent defaults)

Full list: P2-* in `docs/phases/PHASE_2_DESIGN.md` §1. Highlights and review outcomes:

| Topic | Decision |
|---|---|
| Image storage | Driver setting `LMS_STORAGE_DRIVER=local|db|r2`. Production uses `db` (Postgres `asset_blobs`) until the owner provides Cloudflare R2 keys; `scripts/copy_blobs.py` moves blobs later. Global db cap 300 MiB, 200 MiB per user. |
| Image URLs | Content-hashed `/api/v1/media/{sha}.webp`, immutable cache headers; built at read time, never stored. |
| Image processing | PNG/JPEG/GIF/WEBP by content only, no SVG; ≤ 12 MP (lowered from 40 MP after a memory review: Render Free has 512 MB), downscaled to 1600 px, re-encoded to WebP (lossless for PNG/GIF), EXIF stripped; one encode at a time per process. |
| Private files | Content may reference only public assets. Private files need a separate R2 bucket (`R2_PRIVATE_BUCKET`); never stored in the public bucket. |
| Quota | Deleting an asset does not free quota (blobs are kept for history). |
| Versioning | Every content edit creates an immutable version; stale saves get 409; revert creates a new version; metadata (topic, section, position, tags) is not versioned. |
| Delete | Soft delete; versions used by quizzes/attempts keep working; a passage in use cannot be deleted. |
| Import scope (P2-17) | `source_ref` is unique per bank and one bank per source per course (plan said "per owner"; changed so re-importing into a second course never touches the first). |
| External images (P2-21) | Import rejects `http(s)` and `/uploads` image URLs (no hotlinking/SSRF). |
| Import conflicts | A question edited by a teacher since its last import is skipped with a warning unless "overwrite" is chosen; deleted matches are skipped; questions missing from a new bundle are kept. Re-import never changes tags. |
| Import safety | One import at a time per process (409 `import_busy`); a failed import stores no images; orphan blobs older than 1 h are swept; uploads need `Content-Length`. |

## Decisions 2026-10-22 (Phase 3, agent defaults)

Full list: P3-1 … P3-30 in `docs/phases/PHASE_3_DESIGN.md` §1. Highlights and review outcomes:

| Topic | Decision |
|---|---|
| Publishing | Publish freezes every item to question/passage version ids per language (immutable snapshot). Republish makes a new version only if the snapshot changed; in-flight attempts keep their version; publishing over existing attempts needs a confirm (D9). |
| Timing | Server-owned deadlines with per-section deadlines and a 45 s grace (D8). Forward-only sections: the next section starts at the old deadline. |
| Exam integrity | Forward-only exams (ORT) deliver content one section at a time; students cannot read later sections early. Content responses are revalidated on every load (`no-cache` + ETag), never replayed from the browser cache. |
| Autosave | One conditional single-row UPDATE per answer, up to 20 answers per request, ordered by client time; nothing is saved after grading. Pending answers in the browser are keyed per user and cleared on logout. |
| Submit | One-shot: exactly one request grades. Submit locks the attempt and then all items in order (prevents a deadlock with autosave found in review). |
| Submit outcome (B2) | `SubmitOut` reports every answer in the submit body: `saved` (positions stored) and `rejected` (`position` + `reason`; reasons are the autosave codes plus `deadline` and `already_submitted`). A submit processed after deadline + 45 s grace rejects all body answers as `deadline` (autosaved answers are still graded). A repeat submit reports body answers identical to the stored value as saved, others as `already_submitted` (`deadline` if the attempt was finalized by timeout/sweep, `attempt_closed` if the course closed). In the last 60 s before a deadline the player sends each change at once and re-sends anything unsaved every 5 s; the result page shows a dismissible notice with the count of unsaved answers per reason. |
| Results policy | `never` / `after_submit` / `after_close`. `after_close` releases answers only after the end time plus grace and when no student is still writing; it requires an end date. |
| Robustness | Malformed answers score 0 instead of failing grading; the expiry sweep skips attempts that failed recently; request bodies are size-capped (256 KiB attempts, 1 MiB elsewhere, uploads/imports their own limits). |
| Capacity | One database connection per request (fixed the load-test pool starvation). Load-test findings and plan sizing: `docs/LOAD_TEST_PRE_PHASE3.md`, `docs/phases/PHASE_3_LOADTEST.md`. A national exam needs a paid Render plan for the exam window and more Neon storage (owner decision; nothing bought). |
| Admission cap (B1) | Each API process admits at most N requests at a time (`LMS_ADMISSION_LIMIT`, 0 = auto: min(thread tokens, `DB_POOL_SIZE` + `DB_MAX_OVERFLOW`), minus 1 off Postgres where the sweep shares the app pool). The rest wait in the event loop without a thread or connection; after `LMS_ADMISSION_WAIT_SECONDS` (default 20) they get 503 `server_busy` with `Retry-After: 2` and `details.retry_after_seconds`, which the attempt client retries. `/health`, `/uploads`, CORS preflights are not gated. N is logged at startup. Fixes the pool/threadpool deadlock under overload. |
| Exam-window plan (owner, 2026-10-23) | Deferred: the owner has the Render plan estimates (`PHASE_3_LOADTEST.md` §7; 6,000 students ≈ 4 CPUs) and will choose the plan before the first large exam. Until then Render stays on Free. |

## Decisions 2026-10-23 (Phase 4, agent defaults)

Full list: P4-1 … in `docs/phases/PHASE_4_DESIGN.md` §1. Resolved during the build:

| Topic | Decision |
|---|---|
| ORT parity | System ORT schemes reproduce the old scoring exactly (every N 1–200, every raw): scaled score, percentile, golden certificate. Percentile at/below the scale minimum gets the block minimum, at/above the maximum gets the block maximum; clamp before rounding. |
| Scheme rules | Bands, pass/fail and pass thresholds compare the percent rounded like the displayed value. Points never show more than `possible`. Lookup: fractional raw maps to the row with the largest `raw_from` ≤ raw; gaps up to 1 point allowed, overlaps refused. Param numbers within ±100,000; curve exponents in (0, 10]; percentile decimals 0 or 1; preview ≤ 1,001 raws. |
| Scheme library | Deleted schemes are hidden (restore only by the owner); a teacher check and a write rate limit apply to every scheme write. |
| Course grading | `grading_changed_at` moves only when a grading value really changes. Course grading PUT is a full replace. Category delete is soft and refused while a live assessment uses it. GET warns about uncategorized assessments and all-zero weights (weighted mode). |
| Body caps | 64 KiB on course grading settings, categories and submission edits; scheme versions (lookup tables up to 1,000 rows) and grade release (up to 5,000 ids) keep the global 1 MiB cap. |
| Seeding | System schemes are seeded idempotently at startup; a seeding failure is logged, not fatal. |
| Assistants | Assistants can override, excuse, void, release and regrade (they inherit grade management; only roster, publish, delete and transfer stay teacher-only). |
| Removed students | Their submissions and totals are kept but hidden from the gradebook (active roster only); re-adding the student shows them again. |
| Unrelease | Refused (409 `grade_release_auto`) when the assessment releases grades automatically; switch it to manual first. |
| Late policy | Changing the course late policy marks late submissions for regrade; scheme and total-mode edits do not (totals are computed on read). |
| Stale grades | One definition shared by the gradebook "out of date" count and regrade: other scheme version, grading settings changed after computing, late policy changed (late ones only), or an attempt grade missing/old. |
| Everything voided | A submission whose attempts are all voided has state `no_attempts` (shown as pending to the student, ignored in totals). |
| Deleted assessments | Grade detail stays readable for staff; grade changes on a deleted assessment return 404. |
| Integrity | Grade events are append-only and scheme versions immutable, enforced by the ORM and by PostgreSQL triggers. Existing graded attempts get submissions when 0005 runs. |

## Owner decisions 2026-10-23 (after Phase 4)

| Topic | Decision |
|---|---|
| Phase 5 cutover | Approved by the owner. Neon backup branch first. |
| R2 storage | Owner set the R2 vars in Render and `backend/.env` (buckets `ort-uploads` public, `ort-private` private; `LMS_STORAGE_DRIVER=r2`). Verify a real upload/read at cutover. Tests never use R2 (forced `db` driver, blank keys). |
| Test safety | Tests refuse `backend/test.db`, `backend/data/` and non-local databases (`tests/dev_data_guard.py`). Dev `test.db` reseeded from the sample CSVs. |
| Neon branches | `loadtest-2026-10-22` deleted. `backup-2026-10-22-before-phase0-alembic` kept until one week after a stable Phase 5, then deleted. |
| Brevo key | Never committed (checked all refs). Owner rotates it later; `.env.example` holds a placeholder. |
| Render plan | Chosen by the owner before the first real exam. |
| R2 free tier (owner req. 8) | R2 stays in the free tier, enforced by the app: stored-bytes tracking (admin warning at 8 GB, uploads refused at 9.5 GB), images max 2 MB, other files max 10 MB, WebP + SHA-256 dedup, immutable 1-year caching of content-addressed public images served from R2 (not the backend), no list operations in request paths, Standard class only, admin monthly usage estimate, free-tier exam count in `CAPACITY_REVIEW.md`. Built in Phase 5. Anything exceeding the free tier needs the owner's OK. |
| R2 public URL | No domain purchase now: public images use the r2.dev address. Before the first large exam, switch to a custom domain the owner buys after launch (r2.dev is rate-limited). |

## Decisions 2026-10-23 (Phase 5, agent defaults; full table in `phases/PHASE_5_DESIGN.md`)

| Id | Decision as applied |
|---|---|
| P5-1 | No wipe: `users` rows kept; one revision drops old tables and columns; the `role='admin'` owner becomes platform admin + approved teacher before `role` is dropped. Old attempts and access rows are dropped. |
| P5-2 | Conversion = export inside revision 0006 (`legacy_ort_export`), import at startup by `ensure_ort_courses()` through the existing Phase 2 importer and Phase 3 builder; idempotent. Questions in no exam set are exported too, one `legacy_unassigned_<lang>` practice_bank row per language (bank only). |
| P5-3 | Missing `/uploads` images are dropped; the question is kept, tagged `missing_image`, counted and logged. |
| P5-4 | One platform course per language ("ORT (Kyrgyz)", "ORT (Russian)"), fixed ids, published, catalog, open enrollment. Production ky course starts empty; dev/test seed samples. |
| P5-5 | Minimal catalog and one-click join now (`GET /catalog/courses`, `POST /courses/{id}/join`); Phase 7 extends. |
| P5-6 | Demo teacher with unusable password hash and disabled flag; every platform admin is co-teacher of both ORT courses. As applied: the seed adds the admin enrollment only when the admin has no enrollment row in that course; an existing row is never revived, so an admin who left or was removed stays out. |
| P5-7 | `exam_set` becomes `ort_main`/`ort_subject` assessment (section times from the old sections, attempts kept, highest score, results after submit); PIN dropped; `practice_bank` sets become banks only. |
| P5-8 | Revision 0006 downgrade raises; rollback = Neon backup branch + previous `main` commit. |
| P5-9 | Mock tokens, `MOCK_USERS`, Firebase fallback and header-less dev user removed; tests mint real JWTs. |
| P5-10 | Old user columns `role, target_score, exams_taken, current_score, starting_score` dropped. |
| P5-11 | R2 guard counts bytes ever written; warn/refuse thresholds below; images 2 MiB, PDF-only files 10 MB (private bucket, owner download); Class B reads estimated at read time. |
| P5-12 | R2 smoke check: admin button in `/[lang]/admin/storage` and CLI (put, head, public read, delete of a 1-px WebP). |
| P5-13 | Brief deploy overlap (old instance vs migrated DB) accepted; tester traffic only. |

Accepted deviations from the design:
- `legacy_ort_export.exam_set_id` is `String(200)`.
- The ORT seed lock is `pg_try_advisory_xact_lock` on a separate connection that holds its transaction (not a session lock, because of Neon's pooler).
- 0006's users batch has no `naming_convention`; reflection keeps names and tests assert them.
- Demo teacher login answers 401 (unusable hash); disabled accounts get no reset token and reset is refused (forgot/reset check `disabled_at`).
- The catalog requires `published_at IS NOT NULL`; catalog/join route policies live in `app/lms/enrollments/policies.py`.
- Storage limits are decimal: warn 8,000,000,000 bytes, refuse 9,500,000,000 bytes (9.5 GiB would be about 10.2 GB, above the free tier).
- `image_validation.py` moved into `app/lms/files/`; `attempts/bodycap.py` exempts the `files` upload route (it streams its own 10 MiB cap); the smoke audit row uses `target_type='user'`.
- Production has no Kyrgyz questions: "ORT (Kyrgyz)" stays empty until a ky bundle is imported (owner informed).
- Post-cutover fix: `NEXT_PUBLIC_API_URL` on Vercel is the bare Render origin, so every client now normalizes it once (`frontend/src/lib/apiBase.ts`, appends `/api/v1` like `next.config.ts`). A 401 on `/me/lms` (expired or pre-cutover token) signs out and goes to login. The LMS header shows role-aware links (admin, create course, grading schemes, become teacher), the account name and sign out; a missing course shows a friendly "course not found" page.

## Owner decisions 2026-10-24 (answers to `docs/DISCUSSION.md`, planning rules)

Source: the owner's written answers of 2026-10-24 (verbatim copy kept by the orchestrator). The owner says these ideas are not final: where the agents see a simpler, cheaper or safer option, it goes into "Alternatives to discuss" (`IMPLEMENTATION_PLAN.md`, end of file, and the Phase 6 design), never silently applied; the owner decides. Order of work: review the whole plan (done in this update), then UX guidelines and audit, then the Phase 6 design, then stop for the owner's review. No feature code before that review.

### A. ORT must not change (hard rule for every phase)

| Topic | Decision |
|---|---|
| ORT experience | Kept exactly as it is now: exam player (comparison card, line-numbered passages, LaTeX, section timers, forward-only sections, palette, flags, autosave), ORT question bank and exam management, ORT CSV and zip bundle import (same files, same screens, same results), ORT scoring and result view (scaled scores, percentiles, section breakdown, golden certificate). |
| Course templates | A general "course template" feature; ORT is its first template. A template covers the whole course: structure and default banks, importer profile, question types and passage options, ready-made exams with section structure, timing and navigation rules, grading scheme, result view. The existing ORT code stays as it is and becomes part of the ORT template; the database records only which template a course uses and its settings. ORT logic is **not** rewritten into generic settings or simplified. General courses get general versions; new exam types reuse general pieces and get new code only for truly new formats. No ORT-specific checks spread through the code. |
| Locked templates | A template can be locked; courses using it cannot change the exam structure. A teacher in an ORT course sees the same upload, bank, exam and result screens as today. |
| ORT template permission | Granted only by platform admins to selected organizations or teachers; other teachers do not see it. (Per-teacher grants: Alternatives A1.) |
| Proof every phase | The same CSV/zip files import identically; ORT exams look and behave the same (end-to-end tests plus screenshot comparisons of the exam player); ORT scores match. Written into the plan's definition of done as the ORT parity gate. |

### B. Accounts and organizations: institutional Canvas, not Free for Teacher

| Topic | Decision |
|---|---|
| Q1/Q2 sign-up | Students sign up themselves (join code or open catalog). Teachers do not pick "teacher" at sign-up; they come in by invitation from an org admin or a platform admin. Independent teachers may apply to the platform admin: the current request flow is kept only for that. (Replaces the 2026-10-22 "request teacher access" default and DISCUSSION option B.) |
| Q3 co-teachers | Course owners add co-teachers and assistants to their own course themselves. |
| Q4 organizations | Phase 6 builds only the foundation: `organizations` table, every course and bank belongs to an organization, `org_admin` role, a small org admin area (teachers: invite/remove; courses list). Start with one organization the owner owns holding both ORT courses, plus a default organization for independent teachers. Nullable `parent_id` for later departments; no tree management, roster CSV import or org settings beyond "teachers can create courses" (off by default) in Phase 6. |
| Platform admin area | Manages organizations: create, edit, suspend; assign and remove org admins; see each organization's teachers, courses and usage; grant or remove course templates such as ORT. |
| Four areas | Platform admin (owner), organization admin, teaching, student. (Implemented as navigation; per-course roles stay the authority: Alternatives A8.) |
| Institutional exam features | For the exam-related phases: shared question banks per organization (Phase 9), availability windows (exist), access codes (Phase 7), per-student accommodations with extra time and extra attempts (Phase 7), quiz statistics (Phase 10). |

### C. Other answers

| Topic | Decision |
|---|---|
| Q5 platform name | Not decided. A placeholder in i18n so the final name is a one-line change. |
| Q6 phase order | The new order is accepted, with the organization foundation inside Phase 6: 6 organizations foundation + course templates + sign-up/invite flows + design system + student home; 7 assignments + general gradebook; 8 course structure (modules, pages, files, announcements, gating); 9 organizations completion + enrollment forms/invitations; 10 practice, analytics, quiz statistics, student tools; 11 privacy (observer/parent with consent), hardening, launch. |
| Q7 submission types | None (manual grade), text, file (PDF/image). Media and links later. |
| Q8 announcements/discussions | Announcements yes (Phase 8). Discussions later. |
| Q9 parents | Observer accounts with Phase 11 privacy, tied to under-14 consent. |
| Q10 ORT result view and line numbers | ORT keeps them through the ORT template; they are not the default for every course. |

### D. UI/UX quality (applies from now on)

| Topic | Decision |
|---|---|
| ux-reviewer agent | `.claude/agents/ux-reviewer.md` (model: fable) reviews screens from screenshots and code against `docs/UX_GUIDELINES.md` and reports concrete problems (screen, what is wrong, why it hurts the user, the fix). |
| UX guidelines | `docs/UX_GUIDELINES.md`, short and practical. Students: very simple and motivating; the home screen answers "what should I do next?" (next exam or assignment, due dates, recent results) and little else; one main action per screen, no dense dashboards, plain friendly language, clear progress, small celebrations without noise. Mobile-first: everything works on a phone over a slow connection; test at 375 px and desktop. Teachers and admins: more information is fine but organized: clear navigation, tables with search and filters, no hidden features. Everywhere: one consistent design system (colors, type, spacing, components), helpful empty states and error messages (never a bare "Something went wrong"), loading states, accessibility basics (contrast, keyboard, labels), layouts that fit the longer Russian and Kyrgyz texts. |
| UX audit now | Current pages (student, teacher, admin; desktop and phone screenshots); findings and fixes go into the plan: design system and student home in Phase 6, the rest where it fits. |
| UX gate every phase | Before merging: screenshots of every new or changed screen (phone and desktop, all three languages for student screens), ux-reviewer check, fixes, screenshots saved in `docs/phases/PHASE_N_screens/`. |
| ORT exam player ideas | ux-reviewer proposes improvements in `docs/ORT_PLAYER_IDEAS.md`. Fidelity-preserving ones are done without asking (readability, phone layout, accessibility, clearer timer/palette/flag states, loading and autosave feedback, error messages) with before/after screenshots. Anything that changes how the exam works (navigation rules, timing, question layout, scoring, anything differing from the real ORT) goes only into the ideas file for the owner's decision. |
| No waiting | UX reviews never wait for the owner: fix the findings and continue; the owner looks at the saved screenshots when they want. |

### E/F. Process

| Topic | Decision |
|---|---|
| E. Plan review | Done 2026-10-24 by the architect on Fable: `IMPLEMENTATION_PLAN.md` Phases 6–11, `LMS_ARCHITECTURE.md`, this file and the handoff updated for organizations, course templates, assignments, modules, enrollment, privacy and UX gates. |
| F. Phase 6 design | `docs/phases/PHASE_6_DESIGN.md`: organization and permission tables, platform admin and org admin pages; migration of existing users and the two ORT courses; the course template design and exactly which ORT code becomes the ORT template, with the tests that prove nothing changed; sign-up and invite flows; UX audit results and the student home plan; "Alternatives to discuss". The agent stops there for the owner's review. |
