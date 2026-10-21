# Platform concerns: how Canvas and other LMSs handle them, and what we should do

**Written**: 2026-10-21. **Scope**: files, API conventions, multilingual content, storage, migrations, authorization, i18n data model, enrollment forms, minors' privacy.
**Method**: web sources (accessed 2026-10-21; page dates given where shown), plus a sparse read-only clone of `instructure/canvas-lms` (master, 2026-10-21) in `/tmp/canvas_research/platform/canvas` (files read: `app/models/attachment.rb`, `app/models/course.rb`, `lib/api.rb`, `config/locales/locales.yml`). Nothing was run or installed. **[unverified]** marks claims I could not confirm from a primary source.

---

## 1. Canvas: files, API versioning/pagination, multilingual content

### Findings
**Files.** Canvas stores every file as an `Attachment` row with a polymorphic `context` (course, user, group…) (`attachment.rb:81`). Identical content is deduplicated: a copy points at the original through `root_attachment_id`, found by MD5 (`attachment.rb:118, 403-408`). Deletion is a state change (`file_state`: `available`, `hidden`, `deleted`; `attachment.rb:1766`), plus a "replace content" path for true removal (`destroy_content_and_replace`, `:1827`). Bytes sit in a **private** S3 bucket (`s3_access: "private"`, `:191`) or Instructure's file service (inst-fs). Users never get a permanent bucket URL: the app checks permission at `/files/:id/download?verifier=…` and redirects to a signed URL whose TTL defaults to **1 day** (`url_ttl`, `:1005-1009`; `public_url`, `:973`). Uploads use 3 steps: announce (name, size, type) → POST bytes straight to a signed `upload_url` (may be S3; signature valid 30 min) → confirm ([File Uploads API](https://canvas.instructure.com/doc/api/file.file_uploads.html)).

**API versioning.** Canvas has only ever had `/api/v1`. Changes are additive and announced in a community changelog. The old docs page now points to the [Instructure developer portal](https://developerdocs.instructure.com/services/canvas) ([changelog stub](https://canvas.instructure.com/doc/api/file.changelog.html)). I did not find a written versioning policy **[unverified]**.

**Pagination.** Canvas puts pagination in an RFC 5988 `Link` header (`current/next/prev/first/last`). `last` is left out when counting is expensive, and clients must treat the URLs as opaque ([Pagination](https://canvas.instructure.com/doc/api/file.pagination.html)). In code: `PER_PAGE = 10`, `MAX_PER_PAGE = 100`, values clamped (`lib/api.rb:22-23, 399-402`). Canvas also uses bookmark (keyset) pagination for some collections **[unverified: from memory]**.

**Multilingual content.**
- **Canvas** has one *course locale*, which sets both the interface language and the content's `lang` attribute, so you cannot separate them ([community, Developers Group](https://community.canvaslms.com/t5/Developers-Group/language-tagging-content-versus-setting-course-locale/ba-p/611688)). There is no built-in way to hold several languages of the same content. Instructure offers AI translation only for Inbox/Discussions/Announcements, as a feature preview ([Canvas blog](https://community.canvaslms.com/t5/Canvas-LMS-Blog/Inbox-and-Discussion-Translation-in-Canvas/bc-p/618312)). The usual workaround is a separate translated course (export/import of a Common Cartridge). Canvas's `locales.yml` lists `ru` but not `ky`, so we would have to translate Kyrgyz ourselves anyway.
- **Moodle** keeps every language inline in the same field and filters at render time: `<span lang="xx" class="multilang">` or `{mlang xx}…{mlang}` ([Multi-language content filter](https://docs.moodle.org/35/en/Multi-language_content_filter); the docs warn about performance). A course can also force a single language **[from memory]**.
- **Open edX** runs one course per language today. Keeping translations inside one run is only a proposal ([OEPM proposal](https://openedx.atlassian.net/wiki/spaces/OEPM/pages/5028118539/Proposed+Multilingual+Courses); [forum](https://discuss.openedx.org/t/how-to-run-multilingual-identical-courses/7456)).

### Recommendation
- **Files**: copy Canvas's model in small form (see §2): a `files` table, content-hash dedupe, soft-delete state, and authorization checked before any signed URL is issued.
- **API**: keep `/api/v1` and make only additive changes. Our only client is our own frontend, so a v2 would cost more than it saves. Paginate list endpoints with **keyset cursors in the response body** (`{items, next_cursor}`, default 25, max 100), because our `fetch` wrapper reads JSON more easily than `Link` headers. Offset paging stays acceptable for small teacher tables. Remove the duplicate `/exams` and `/mock-tests/exam-sets` routers as part of the redesign.
- **Languages**: support translations inside one course (the Moodle idea), but store them as structured data, not markup inside HTML (§5).

**Rejected**: Moodle-style inline `{mlang}` markup (no per-language validation, hard to edit, leaks into search and exports). Open edX's course-per-language (duplicates authoring, splits enrollments and analytics). Canvas's single locale (fails the "teacher picks 1–3 languages" requirement).

---

## 2. File and image storage

### Findings (prices checked 2026-10-21)
| Option | Storage | Egress | Other | Fit |
|---|---|---|---|---|
| **Cloudflare R2** ([pricing](https://developers.cloudflare.com/r2/pricing/), updated 2026-10-01) | $0.015/GB-mo; **10 GB-mo free** | **$0** | Writes $4.50/M (1M free), reads $0.36/M (10M free); S3 API | Best |
| **AWS S3** (Frankfurt; third-party figures, [Upstash 2026](https://upstash.com/blog/aws-s3-pricing-explained-2026)) | ~$0.0245/GB-mo | 100 GB/mo free, then ~$0.09/GB (US-East rate; Frankfurt not confirmed) | IAM setup | Good, costs more once traffic grows |
| **Supabase Storage** ([pricing](https://supabase.com/pricing.md)) | Free 1 GB; Pro 100 GB then $0.021/GB | Free 5 GB; Pro 250 GB then $0.09/GB | Image transforms not on Free; Pro is $25/mo | Adds a vendor we don't otherwise use |
| **Neon bytea** ([pricing](https://neon.com/pricing)) | $0.35/GB-mo (23x R2); Free plan **1 GB per project for the whole DB** | 5 GB (Free) / 500 GB (Launch) | Every image request goes through Render and wakes Neon compute (uses CU-hours); makes backups/branches bigger | Poor |
| **Render disk** ([docs](https://render.com/docs/disks)) | $0.25/GB *provisioned* ([staff post](https://community.render.com/t/disk-usage-time-and-payment-price/15770), date unknown, **[unverified current]**) | Through backend | Paid instance only; **one instance; no zero-downtime deploys**; daily snapshot | Poor |
| **Neon Object Storage** ([docs](https://neon.com/docs/storage/overview)) | 5 GB/project on Free | ? | Private preview/beta, path-style only, limited regions | Not yet |

**Signed URLs on R2**: GET/HEAD/PUT/DELETE, no POST form uploads. Expiry up to 7 days. They work **only on the S3 API domain, not on custom domains**. Content-Type can be fixed in the signature ([presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)). **Public serving**: the `r2.dev` host is rate-limited and for non-production use only. Production public access and CDN caching need a custom domain whose DNS is on Cloudflare (a CNAME setup is possible) ([public buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/)).

**Image optimization**:
- Vercel image optimization: Hobby includes 5K transformations/month. Hobby is "non-commercial personal use only", and over the limit new images fail with 402 ([Vercel](https://vercel.com/docs/image-optimization/limits-and-pricing), updated 2026-08-11).
- Cloudflare Images on R2 originals: 5,000 unique transformations/month free, then $0.50/1K ([pricing](https://developers.cloudflare.com/images/pricing)).

**Our code**: `upload.py` checks the file extension only (no content check, no size cap). Images are written under random names. `bundle_service` already writes SHA-256 keys. `CloudStorageService` is a stub that only logs.

**Worked example** (assumption: 5,000 images of ~150 KB after re-encoding, 500 active students viewing ~300 images a month):
- Size: 0.75 GB stored, ~22.5 GB/month delivered.
- R2: **$0/month** (inside the free tier).
- S3: ~$0.02/month, since egress stays under the 100 GB free allowance. At 1 TB/month delivered, S3 ≈ $81/month vs R2 $0.
- Neon bytea: $0.26/month in storage, but the images alone use 75% of the Free plan's database limit, and the traffic keeps compute awake.

### Recommendation
1. **Cloudflare R2, server-side upload first.**
   - Add `R2StorageService(BaseStorageService)` using boto3 (`endpoint_url=https://<account>.r2.cloudflarestorage.com`, `region_name="auto"`), called through `run_in_threadpool`.
   - Extend the interface with `delete(key)`, `presign_get(key, ttl)` and, later, `presign_put`.
   - `LocalStorageService` stays for dev and tests.
   - Nothing needs migrating: production images are already lost, and bundles can be re-imported.
2. **Process images at upload with Pillow** (already a dependency):
   - Check the real format with `Image.open().verify()`.
   - Cap size at 10 MB, and cap dimensions at around 2000 px on the long side.
   - **Strip EXIF**, which can include GPS location (matters for minors).
   - Re-encode to WebP, keeping PNG for line diagrams if WebP harms them. Optionally store one smaller width.
   - Store under `sha256` keys. This costs nothing at runtime and needs no Vercel or Cloudflare transformations.
3. **Two access classes**:
   - **Public content media** (question and page images): immutable SHA-256 keys served from `media.<our-domain>` through the Cloudflare CDN with `Cache-Control: public, max-age=31536000, immutable`. URLs can be guessed only if someone already has the file's hash. The risk: if a course is private, anyone who obtains an image URL can view that image.
   - **Private media** (enrollment-form uploads, data exports, later student submissions): the backend checks permission, then returns a 5–15 min presigned GET (the Canvas pattern).
4. **Schema**: a `files` table holding:
   - `id, sha256, storage_key, bucket, mime, size_bytes, width, height`
   - `owner_user_id`, `course_id` (nullable), `access` (`public|private`)
   - `created_at, deleted_at`

   Content rows reference `file_id` through a foreign key, not a URL string. A periodic job removes R2 objects with no live references after N days (soft delete first, as in Canvas).
5. Later, if uploads get large (video, PDFs): add browser-direct presigned PUT, then a `confirm` call that re-validates the file (Canvas's 3 steps).

**Rejected**:
- Neon bytea: storage costs 23x more, it uses up the Free plan's DB limit, and it puts image traffic on the DB and API.
- Render disk: blocks scaling and zero-downtime deploys, and needs a paid instance.
- Supabase: an extra vendor, and Pro costs $25/month.
- S3: fine, but egress is billed. R2 speaks the same API, so switching later is trivial.
- Vercel `next/image` for user content: Hobby forbids commercial use and has a 402 cliff.
- Neon Object Storage: still in preview.

---

## 3. Alembic adoption

### Findings
- **Autogenerate limits** (Alembic 1.20 [docs](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)):
  - Table and column renames show up as drop + add.
  - Unnamed constraints are unreliable; Enum types on non-native backends are hard to detect; sequences are not detected.
  - Server-default comparison is off by default and inexact.
  - CHECK constraints are compared by name only. Expression changes are never detected, and all of them must be named.
  - The docs advise a `naming_convention` on `MetaData`.
  - `alembic check` (since 1.9) fails when models and migrations differ, which suits CI.
- **SQLite** cannot ALTER most things. Alembic's batch mode (`render_as_batch=True`) rebuilds the table by copying it. Foreign keys must be named, `PRAGMA foreign_keys` must be off during the rebuild, and unnamed CHECKs are dropped with a warning ([batch](https://alembic.sqlalchemy.org/en/latest/batch.html)).
- **pytest-alembic** has built-in tests: `test_single_head_revision`, `test_upgrade`, `test_model_definitions_match_ddl`, `test_up_down_consistency` ([PyPI](https://pypi.org/project/pytest-alembic/), [running](https://pytest-alembic.readthedocs.io/en/latest/running.html)).
- **Render** pre-deploy commands run migrations before the new version goes live and cancel the deploy if they fail. Paid services only. A user reports up to a ~1 min gap between migration and the new instances, so migrations must stay backward compatible ([changelog 2023-10-11](https://render.com/changelog/predeploy-command), [feedback](https://feedback.render.com/features/p/release-phase-script)).

### Recommendation
1. **Baseline on an empty database.** Production data is testers only (`PRODUCT_DECISIONS.md`).
   - Finish the Phase-1 models.
   - Set a `naming_convention` on `Base.metadata`.
   - Autogenerate `0001_baseline` against an **empty Postgres**, then review it by hand.
   - On Neon: `pg_dump` for safety, drop the schema, run `alembic upgrade head`.

   No `stamp` is needed, and the old runtime `ALTER` helpers (`user_migrations.py`, `attempt_migrations.py`, `question_order_migration.py`, the inline code in `init_db.py`) are deleted. Seeding becomes an explicit command, not something that runs on every boot.
2. **Migrations run as a step, never at import.** Use a Render pre-deploy command `alembic upgrade head` if the service is on a paid plan. Otherwise run it in the start command before `uvicorn` (single instance only). Use the expand → deploy → contract pattern for breaking changes.
3. **Postgres is the reference database for migrations.**
   - CI (GitHub Actions `postgres:16` service): `alembic upgrade head` → `alembic check` → pytest-alembic's four tests → the app test suite on that database.
   - Optionally, before risky deploys, run `upgrade head` on a Neon branch of production (copy-on-write, free).
   - SQLite stays usable for fast local unit tests via `create_all`, with `render_as_batch=True` so dev migrations still work. Postgres-only features (JSONB operators, partial indexes) must have a SQLite fallback or be skipped in SQLite tests.
4. **Rules for writing migrations**:
   - Every constraint is named.
   - Enums are stored as `String` + named CHECK, which stays portable.
   - Renames are edited by hand.
   - Data migrations go in their own revision and are tested.
   - No ORM model imports inside migrations.

**Rejected**: stamping a baseline onto the current production schema (keeps drift from runtime ALTERs, and the data is disposable). Running `upgrade` on app startup (races once there are several workers). SQLite-only CI (hides Postgres DDL failures).

---

## 4. Authorization (per resource, per enrollment)

### Findings
- **Canvas** keeps its rules in its own code: `set_policy do given { |user| … }; can :read … end` blocks on each model (`course.rb:2101-2171`), with role overrides at account level. Examples: unenrolled users read public courses, active enrollments get `read_as_member`, and grading-scheme rights depend on `manage`. A policy module inside the app is the proven pattern.
- **Oso** open-source library: deprecated 2023-12-18, kept alive for critical fixes, development moved to Oso Cloud ([Oso changelog](https://www.osohq.com/docs/oss/project/changelogs.html)).
- **pycasbin**: active, 2.8.0 released 2026-02 ([mirror](https://simple-repository.app.cern.ch/project/pycasbin)). Its policies are role/permission *tuples*. "Teacher of *this* course" needs either a policy row per enrollment, kept in sync with our tables, or custom matcher functions. It also does not filter SQL list queries.
- **Zanzibar-style services** (SpiceDB, OpenFGA, Cerbos): separate deployed services. Too much infrastructure for our size **[general knowledge]**.

### Recommendation
Build **our own small policy module** (`app/authz/`):
- `Actor` = user loaded from the DB (already done by `get_current_user`) + `platform_role` (`user | platform_admin`).
- `can(actor, action, resource) -> bool`. Actions are an enum (`course.read`, `course.edit`, `quiz.take`, `quiz.grade`, `enrollment.review`, `file.read`, …). The rules come from `course.owner_id`, `enrollments(role, state)`, `course.visibility` and soft-delete state.
- **Scoping for list queries**: `visible_courses(actor) -> Select`, `editable_banks(actor)`. Lists filter in SQL, never after fetching rows (this also satisfies the "no unbounded reads" rule).
- **FastAPI dependencies** that load the resource *through its parent* (`/courses/{cid}/quizzes/{qid}` must match `quiz.course_id == cid`) and call `can`. If the actor may not see the resource, return **404**; if they can see it but not act, 403. This prevents probing for IDs.
- Response models chosen by permission: students never get `correct_option`/`explanation` before review is allowed.

**Cross-tenant tests** (write before the endpoints):
- A fixture world: teachers A and B, each with a course, bank, quiz, file and attempt. Student SA enrolled in A, SB in B, SN enrolled nowhere, plus a pending applicant. All tokens are real JWTs (`ALLOW_MOCK_TOKENS=false`).
- **A route inventory test** walks `app.routes` and fails if any route lacks an entry in an `AUTHZ_MATRIX` (actor → expected status). New endpoints therefore cannot skip the review.
- Matrix tests per route × actor. Also assert that list responses contain **none** of the other tenant's IDs, and that nested-ID swaps (A's course, B's quiz ID) return 404.

**Rejected**: Casbin (two sources of truth for enrollment, no query filtering), Oso OSS (deprecated), hosted Zanzibar services (cost, latency, operations), Postgres row-level security as the main mechanism (does not work on SQLite dev, is awkward with pooled Neon connections; possible as a second layer later).

---

## 5. i18n data model for user-authored content (en/ru/ky)

### Options (Rails Mobility's backends list them well: [Mobility](https://github.com/shioyama/mobility))
| Pattern | Pros | Cons |
|---|---|---|
| **A. Column per language** (`title_en/_ru/_ky`) | Simple, typed, indexable | A migration per new language; wide tables |
| **B. JSON per field** (`title = {"ru": "...", "ky": "..."}`) | One row; any language set; works in SQLite JSON and PG JSONB; easy to fall back | Validation lives in the app; harder to index or search per language; two people editing different languages overwrite each other at row level |
| **C. Translation table** per entity (`page_translations(page_id, lang, title, body, status)`) | Real constraints; per-language status/review/history; can be queried | Joins; more tables |
| **D. Key-value table** shared by all entities | Generic | Polymorphic, no foreign keys, many joins |
| **E. Variant rows** (one row per language, linked by `translation_group_id`) | Each language edited, versioned and graded on its own | Grouping logic; duplicated non-text fields |

### Recommendation
- **`Course.languages`** (ordered list, a subset of `en|ru|ky`, at least 1) + `default_language`. Each enrollment stores a `content_language`, chosen from the course's languages.
- **Short metadata** (course/module/quiz titles, descriptions, instructions, enrollment-form labels and options): **pattern B**, a `LocalizedText` JSON type validated by Pydantic. Keys must be a subset of `course.languages`, and the default language is required. Read fallback: requested language → course default → first available.
- **Assessable content and long pages** (questions, passages, page bodies): **pattern E**. A `Question` stays monolingual, as today, plus a nullable `translation_group_id`. A quiz item points to the group, and the attempt records the **exact variant ID and language** in its snapshot. Reasons: ORT ky and ru tests are different question sets, not translations; statistics and grading are per variant; editing a Russian question must not change Kyrgyz history.
- UI strings: add `en.json` next to `ky.json`/`ru.json`, plus a CI check that all three have the same keys.

**Rejected**: A (adding a language would need a migration), D (no integrity), C everywhere (too heavy for titles, but it is the upgrade path if per-language review workflows are needed), inline markup (§1).

---

## 6. Enrollment form (custom registration questions)

### Findings
- **Canvas Catalog** lets admins add "user defined fields". They are collected at sign-up, optionally per enrollment since the 2024-06-10 release, inherited by sub-catalogs, and shown in enrollment analytics ([guide](https://community.canvaslms.com/t5/Canvas-Catalog/How-do-I-add-user-defined-fields-to-customize-catalog/ta-p/1775), [release note](https://community.canvaslms.com/t5/Canvas-Catalog-Releases/Catalog-Release-Notes-2024-06-10/ta-p/604762)).
- **Moodle `enrol_apply`**: the applicant fills in profile fields, the teacher approves or cancels, and the applicant is emailed and enrolled ([plugin](https://moodle.org/plugins/view.php?id=325)). `enrol_gapply` adds a waitlist status.

### Recommendation (schema)
- `courses.enrollment_mode`: `open | form_auto | form_review | invite_code | closed`.
- `enrollment_forms(id, course_id, version, status draft|active|retired)`. A version becomes **immutable once it has answers**; editing creates a new version.
- `enrollment_form_fields(id, form_id, key, type, label LocalizedText, help LocalizedText, options JSON, required, position, pii_category none|contact|identity)`. Types: `short_text, long_text, single_choice, multi_choice, number, date, email, phone`. **No file fields and no free "sensitive" categories in v1.** Health, ethnicity and religion are special-category data under Kyrgyz and GDPR-style rules.
- `enrollment_applications(id, course_id, user_id, form_id, status pending|approved|rejected|withdrawn, answers JSON {key: value}, submitted_at, decided_by, decided_at, purge_after)`. Unique `(course_id, user_id)` for open applications. Approval creates the `enrollments` row.
- **PII handling**:
  - Answers are visible only to that course's teachers (`can(enrollment.review)`).
  - Never logged, never in analytics exports.
  - The form shows its purpose text (who sees the answers, for how long).
  - Rejected or withdrawn applications get `purge_after` = +30–90 days, then answers are cleared by a job.
  - Unenrolling clears the answers after the same period.
  - Applications are rate-limited per user.

**Rejected**: storing answers in user profile columns (leaks across courses, as Moodle profile fields do), and a generic forms engine (logic and branching are not needed).

---

## 7. Privacy for minors (affects schema only; **not legal advice**)

### Findings
- **Kyrgyzstan.** The Law "On Personal Information" (2008) was replaced by the **Digital Code (No. 178, signed 2025-07-31, in force 2026-02-08)**, according to [ICNL guidance, Aug 2025](https://www.icnl.org/wp-content/uploads/KG-Personal-Data-Guidance-Note_August-2025_eng.pdf) and [ICNL Digital Code guidance (RU), Feb 2026](https://www.icnl.org/wp-content/uploads/KG-Personal-Data-Guidance-Note_Digital-Code_February-10-2026_RU.pdf). As summarized by ICNL (secondary source; I did not read the official text):
  - **Art. 81 (children):** processing only in the child's best interest with strong safeguards. Unless another legal basis applies, a **legal representative's consent** is required. **Children aged 14+ may consent themselves** within their civil capacity. Consent must be in simple language a child understands.
  - **Consent (art. 79):** separate per purpose; invalid if hidden among other requests or written unclearly. It may be electronic (checkbox/button) **if reliable proof is stored**, and can be withdrawn at any time.
  - **Deletion (art. 83):** "without undue delay" once data is no longer needed, consent is withdrawn, or an objection is upheld. **Objections must be decided in writing within 7 working days**, and processing is suspended meanwhile.
  - **Cross-border transfer (art. 89):** free to countries on the regulator's adequacy list, otherwise needs consent, a contract or another basis. Our whole stack (Neon/Render in Frankfurt, Vercel, Cloudflare, Resend/Brevo) is outside Kyrgyzstan. Whether a published list exists, and covers Germany, is **unverified**.
  - The Digital Code removes the data-holder registration duty. Fines for violations exist (Code on Offenses, from 2025-11-23).
  - A 72-hour breach-notice rule is reported only by a secondary site ([Siberson](https://www.siberson.com/central-asia-caucasus-data-security-compliance.html)) **[unverified]**.
- **GDPR patterns** (general knowledge): age of digital consent 13–16 depending on country; proof of consent; access/export, rectification, erasure; data minimization.

### Recommendation (schema now; features later)
- `users.birth_year_month` (or an age-band attestation `age_band: under_14|14_17|adult`), collected at sign-up. Under 14 → account is `pending_guardian_consent` with limited features.
- `consent_records` (append-only): `user_id, purpose (terms|privacy|cross_border|marketing|guardian), policy_version_id, granted_by self|guardian, guardian_name, guardian_contact, method checkbox|email_confirm, granted_at, withdrawn_at, evidence JSON (ua, ip_hash)`.
- `policy_versions(id, kind, language, content_sha256, published_at)`, in all three languages.
- `data_requests(user_id, type export|erase|rectify|object, status, due_at, completed_at, handled_by)`, with `due_at` set to support the 7-working-day objection deadline.
- **Personal-data registry in code**: one mapping table → PII columns (users, consent, enrollment answers, attempts, files with `owner_user_id`). Export and erase jobs both use it, and a test fails if a model gets a PII-like column that is not registered.
- **Soft delete vs erasure**: teacher content is soft-deleted (history kept). Users are **deactivated, then anonymized** after a grace period: PII cleared, attempts kept against a tombstone ID only if course statistics need them.
- Data minimization: no phone/display name unless needed; EXIF stripped (§2); no answer payloads in logs (`print()` in `mock_tests.py` must go).

**Rejected**: storing full birth date or national ID (more than needed), and boolean "accepted terms" columns on `users` (no version or proof, cannot be withdrawn).

---

## Decisions the owner must make (priority order)

1. **Can we wipe Neon and start from an Alembic baseline?** Recommended yes; testers only. This unblocks everything else.
2. **Storage vendor and domain**: approve Cloudflare R2, and decide whether we have or will buy a domain whose DNS can be on Cloudflare (needed for a public CDN media host; without one, all images go through presigned or backend URLs).
3. **Course image privacy**: is "public URL if you know the hash" acceptable for content images of private courses, or must every image be signed per request (slower, no CDN cache)?
4. **Render plan**: paid (pre-deploy migrations, no spin-down) or free (migrations in the start command)? Also confirm whether Vercel Hobby's non-commercial clause applies to us.
5. **Minimum age and guardian flow**: allow under-14 sign-ups (needs a guardian consent flow) or require 14+ at launch? A lawyer should confirm Art. 81 and the cross-border basis for EU hosting.
6. **Language model**: approve "JSON for titles, variant rows for questions and pages", and whether a student can switch content language inside a course.
7. **Enrollment modes for v1**: which of `open / form_auto / form_review / invite_code` to ship, and how long to keep application answers (30, 60, 90 days).
8. **Authorization**: approve our own policy module plus the route-inventory test as a merge requirement.
9. **Retention of deleted users' attempts**: anonymize and keep for course statistics, or delete completely.
