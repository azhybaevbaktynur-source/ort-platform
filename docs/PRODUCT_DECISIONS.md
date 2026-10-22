# Product decisions (owner answers, 2026-10-21)

Source: answers to the 15 open questions in `PROJECT_UNDERSTANDING.md` §8. The Canvas documents in `docs/` are drafts; nothing in them is binding. Real goals first, flexible design.

**Goal**: a flexible, safe, Canvas-style LMS where teachers have their own students, build and restructure their own courses, and own their own questions. ORT (exam, scoring, ky/ru) must keep working, as just one kind of course.

| Topic | Decision |
|---|---|
| Teachers | **Superseded 2026-10-22**: see "Decisions 2026-10-22 (teachers)" below. Originally: self sign-up, a sign-up is a teacher. Roles stay per enrollment. |
| The 12k questions | Not important. ORT becomes a course a teacher creates (upload ORT questions) and can make visible to everyone. No platform-owned bank required. |
| Sharing questions between teachers | Later. Not now. |
| Sections / cohorts | None. One course = one group of students. |
| Schools / Accounts (B2B) | Not near term. |
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
| Who can create courses | Only **admin-approved teachers**. Everyone who signs up is a student. A user may request teacher access; a platform admin approves or rejects it. Revocable. (Replaces self sign-up as teacher and D10.) |
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
