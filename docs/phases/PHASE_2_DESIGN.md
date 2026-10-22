# Phase 2 design: files and content library

**Status**: design for implementation, 2026-10-22 (architect). Builds on `phase-1/courses` as it exists (`app/core/authz.py`, `app/lms/core/*`, `app/lms/courses/*`, Alembic `0002_phase1_courses`).
**Sources**: `IMPLEMENTATION_PLAN.md` Phase 2 + section 0 gates + D2/D3/D15, `LMS_ARCHITECTURE.md` sections 4 and 9, `BUNDLE_FORMAT.md`, `PRODUCT_DECISIONS.md` (upload limits 2026-10-22).
**Rule for implementers**: anything not stated here is out of scope. If a brief and this doc disagree, ask the orchestrator. Old code (`app/services/*`, `app/models/*`, old endpoints, old pages) is **frozen**: read it, copy from it, never edit it.

---

## 1. Decisions (defaults taken; record them in `PRODUCT_DECISIONS.md` at merge)

| # | Decision | Reason |
|---|---|---|
| P2-1 | Storage driver chosen by `LMS_STORAGE_DRIVER ∈ {local, db, r2}`. Tests: `local` (tmp dir). Production now: **`db`** (table `asset_blobs`, bytea). `r2` (`R2StorageService`, boto3 S3 API) once the owner supplies keys; `scripts/copy_blobs.py --from db --to r2` copies blobs (idempotent, content-addressed). | No R2 keys yet; Render disk is ephemeral; Neon survives restarts. Switching drivers changes no content rows (P2-2). |
| P2-2 | Public image URL = `media_url(sha256)`, computed at **read** time, never stored: `{MEDIA_BASE_URL}/{sha256}.webp` (default `/api/v1/media`, served by the backend route); with `r2` and `R2_PUBLIC_BASE_URL` set: `{R2_PUBLIC_BASE_URL}/img/{sha256}.webp` (CDN, backend not involved). `sha256` = hash of the **stored** WebP bytes. | Content-addressed URLs are unguessable without the image (D3) and immutable, so they can be cached forever; one function switches all URLs when the CDN domain (D2) arrives. |
| P2-3 | Storage keys: public `img/{sha}.webp`, private `priv/{sha}.webp`. `/media/{name}` accepts only `^[0-9a-f]{64}\.webp$` and maps to `img/` keys, so private blobs are unreachable through it. Private content: `GET /assets/{id}/content`, owner only in Phase 2; `r2` → 302 to a presigned GET (300 s); `db`/`local` → stream with `Cache-Control: private, no-store`. | D3 "signed URLs for private files"; Phase 2 ships the route and test; student uploads come in later phases. |
| P2-4 | Image limits: input formats PNG, JPEG, GIF, WEBP **by content** (reuse `validate_image_bytes`); no SVG/HEIC/TIFF/BMP. Raw cap 5 MiB for direct upload (Phase 0 decision), 10 MiB per image inside bundles. Reject if `width*height > 40 MP` **before** decoding pixels. Downscale longest side to 1600 px. Stored-size cap 2 MiB after encode. | Line diagrams rarely exceed 800 px; caps protect Render's 512 MB RAM and Neon's 0.5 GB. |
| P2-5 | Always re-encode to WebP with Pillow: `ImageOps.exif_transpose`, first frame only for GIF/animated WebP, mode → RGB/RGBA, **no** `exif`/`icc_profile`/`xmp` passed (metadata stripped). Source PNG/GIF/lossless WebP → `lossless=True, quality=80, method=4`; JPEG/lossy WebP → `quality=82, method=4`. | One output type; strips EXIF/GPS and polyglot trailers; lossless keeps diagram pixels exact (test asserts pixel equality for tsoomo19). |
| P2-6 | Dedupe: one `assets` row per `(owner_id, source_sha256, visibility)` where `source_sha256` = hash of the **uploaded** bytes (matches the bundle manifest); re-upload returns the same row (revives it if soft-deleted). Blobs are global and keyed by stored hash, so two teachers uploading the same picture share one blob. Soft delete only hides an asset from the picker: it is still served while immutable versions reference it. No blob GC in Phase 2 (Phase 9: purge/takedown tool). Quotas: `ASSET_QUOTA_BYTES_PER_USER` 200 MiB (sum of non-deleted stored bytes), and with driver `db` a global `ASSET_DB_MAX_TOTAL_BYTES` 300 MiB. | Plan: "sha256 dedupe per owner, soft delete"; history must keep rendering. |
| P2-7 | New question table is **`bank_questions`** (class `BankQuestion`), because the old `questions` table and class `Question` live until Phase 5. Other tables use the architecture names: `assets`, `asset_blobs`, `question_banks`, `passages`, `passage_versions`, `question_versions`, `translation_groups`. | No name clash in the DB or in SQLAlchemy's class registry. |
| P2-8 | Banks are always **course-scoped** in the Phase 2 API (`course_id NOT NULL` enforced by the service; the column is nullable for a later personal library, whose rule is "owner only"). `owner_id` = creator (kept if they leave the course; authority comes from the course). | The UI lives in the course; one authz hop; personal library and bank copy are later features. |
| P2-9 | Authz: every content route requires `content.read_admin` (read) or `content.manage` (write) on the course. Teachers and assistants hold both; students hold neither (403). Status gates from `decide()`: draft/published OK; **concluded = read-only** (reopen to edit); deleted course 404. No student-facing content route exists in Phase 2; the `student_view` serializer is used by the staff preview route and by Phase 3. | Plan: only course teachers/assistants edit; students never see keys. |
| P2-10 | **Versions**: every content change inserts an immutable `question_versions` / `passage_versions` row (`version_no = current + 1`, under a row lock) and moves `current_version_id`. A save whose `content_hash` equals the current one creates nothing (`unchanged: true`). Revert = new version copying an old one (`origin='revert'`). Versions are never updated or deleted (ORM `before_update`/`before_delete` listeners raise; no API). | Quizzes/attempts (Phase 3) reference version ids, so edits never change history. |
| P2-11 | Versioned content: `type, stem, data, explanation, default_points, image`. **Not** versioned (mutable row metadata): `topic, difficulty, section, tags, position, q_num, passage_id, translation_group_id`. `language` is fixed at creation. | Metadata drives filters/ordering; Phase 3 snapshots pin passage versions at publish. |
| P2-12 | Optimistic concurrency: a content save carries `base_version_id`; if it differs from `current_version_id` → 409 `version_conflict` with `details.current_version_id`. | Co-teachers editing the same question never silently overwrite each other. |
| P2-13 | Delete: question/passage/bank = soft delete (`deleted_at`, `deleted_by_id`), restore allowed, no hard delete via API. A deleted question keeps its versions; published quizzes and attempts that reference its versions keep working; the Phase 3 builder hides deleted questions and refuses to publish a draft item pointing at one. Deleting a bank hides its questions and passages without touching their rows. Deleting a passage is refused while live questions link to it (409 `passage_in_use`). | "Soft delete, history kept" (owner decision); attempts are sacred. |
| P2-14 | Translations (D15): monolingual questions linked by `translation_groups`. At most one live question per language per group (partial unique index). All members must be in banks of the **same course** and of the **same type** at link time. Variants are graded and counted separately. Passages have no translation groups in Phase 2 (each variant links its own passage). | Architecture section 4; ky and ru ORT exams are different item sets. |
| P2-15 | Text format "ORT rich text v1": plain text with `$…$`/`$$…$$` LaTeX and only `<u>`, `<b>` tags, rendered by the existing escape-first `renderRichText` (`MathRenderer.tsx`). Server stores text as given after: `\r\n`→`\n`, NUL and other C0 controls (except `\n\t`) removed, length caps (stem 20 000, choice 2 000, explanation 20 000, passage body 100 000, passage title 300). No server HTML sanitizer needed because no client renders raw HTML; any future HTML renderer must sanitize. | Matches today's renderer exactly (bundle acceptance test 12). |
| P2-16 | Image references inside content are `ImageRef = {"asset_id": uuid, "sha256": hex}`; clients send only `image_asset_id`; the service fills `sha256` from the asset row. Readers build URLs from `sha256` with **no join**. A ref is accepted if the asset is non-deleted and owned by the actor, **or** the same `asset_id` is already in the base version (carried over) or in the version being reverted to. | Zero extra queries for 6,000 readers; co-teachers can re-save each other's questions; guessing another teacher's asset id gives 422 `asset_not_usable`. |
| P2-17 | Import scope (deviation from plan's "source_ref unique per owner"): a manifest bundle maps to exactly one bank per `(course_id, source_id)` (partial unique among live banks); `source_ref` (= manifest `external_id`) is unique **per bank** (soft-deleted rows included). Importing the same source into a second course creates a second, independent bank. | "Per owner" would make a re-import into course 2 silently update course 1's bank; per-course scoping still fixes today's global collision (two teachers never collide). |
| P2-18 | Import conflict rules (rows matched by `source_ref` in the source's bank): identical content → `unchanged` (no version); different content and the question's `current_version_id == imported_version_id` → new version `origin='import'` (`updated`); the teacher edited it since the last import → **conflict**: `on_conflict=skip` (default) keeps the teacher's version and warns `question_edited_locally`; `on_conflict=overwrite` adds an import version (history keeps both). Soft-deleted matches are skipped with warning `question_deleted_skipped` (teacher's delete wins). Questions of that source missing from the new bundle are kept and warned (`questions_missing_from_bundle`, as today). Metadata (`position, q_num, section, topic, difficulty, source_meta`) is refreshed on `created/updated/unchanged` rows, not on skipped ones. Same rules for passages. | BUNDLE_FORMAT section 5.7 plus protection of teacher edits. |
| P2-19 | Import targets: manifest bundles always go to their source bank (created on first import, title = `source_id`). Manifest-less bundles and plain CSV go to `target_bank_id` if given (allowed only when the upload contains exactly one manifest-less bundle or is a CSV) and are appended; otherwise a new bank titled after the CSV file name or bundle folder. Plain inserts, no upsert (as today). | Matches BUNDLE_FORMAT; CSV has no stable ids. |
| P2-20 | Import mode: `exam_type ∈ {full_main, subject, practice_bank}` applies the **ORT preset** (section must be a known ORT section incl. aliases; `math_1` ⇒ both columns and `correct ∈ A–D`; other sections ⇒ no columns; 4-option rows A–D, 5-option rows A–E). `exam_type` empty = **general** mode: `section` is a free optional label (≤ 40 chars), no section rules. In both modes a row with columns becomes `comparison` (both columns required), otherwise `single_choice` with choices `A..D(E)` (ids are the letters) and `correct` must name a non-empty option. Language: manifest `language` wins, else the request's; it must be in `course.languages` (`language_not_in_course`). | Plan: preset only when `exam_type` is given; quiz-section rules arrive in Phase 3. |
| P2-21 | `image_url` in imports must resolve to a file inside the zip. `http(s)://` and `/uploads/...` values are **errors** (`image_external_url`), deviating from BUNDLE_FORMAT section 6. Bare names in a plain CSV keep today's error (`image_not_included`). | No hot-linking (third-party tracking of minors, link rot) and no SSRF; old `/uploads` files are ephemeral. |
| P2-22 | Import limits (settings): upload 50 MiB compressed (`Content-Length` checked first, then streamed count), 150 MiB uncompressed, 5 000 zip entries, 5 000 rows, 1 000 distinct images. Rate limit `content_import_1h` 60 per user per hour (preview and commit both count); `asset_upload_1h` 300 per user per hour. | Render Free has 512 MB RAM; BUNDLE_FORMAT's 200 MB would not fit with image decoding. Real sources are 0.2–5 MB. |
| P2-23 | Port by **copy**: the zip reader, CSV parser/aliases/`validate_row` logic and bundle discovery are copied into `app/lms/content/importers/` with the old schemas (`QuestionCreate`, `SectionType`, Firestore) removed. Old modules are not imported by new code. A temporary parity test runs old and new parsers on the same fixtures and is deleted at Phase 5. | Phase 5 deletes the old code; `csv_service` imports the Firestore mock at import time. |
| P2-24 | Preview is stateless: the client uploads the file again to commit; commit re-validates everything; any error → nothing saved. Both return `200` with an `ImportReport` (`ok`, `committed`). | Same flow as today's `BundleImportPanel`; no temp storage. |
| P2-25 | Order: `position` is an integer per bank; list order is `(position, id)`. Import sets `position` = 1-based CSV row index (CSV append: `max(position) + row index`). New questions get `max + 1` (bank row locked). Move up/down swaps positions with the nearest live neighbor in the same bank **and same `section`**. `q_num` stores the printed number. | Ports `test_question_order` semantics without the old section-rank sort (the CSV order already is document order). |
| P2-26 | `comparison` stores only `column_a`, `column_b`, `correct ∈ {A,B,C,D}`; the four labels (A greater, B greater, equal, cannot be determined) are app i18n, not data. | Architecture section 4. |

## 2. Schema and migration

Conventions as Phase 1: SQLAlchemy 2.0 `Mapped`, `UUIDPKMixin`, `TimestampMixin`, `SoftDeleteMixin`, `JSONType`; user FKs `String(64)`; constraint names are short suffixes (naming convention adds prefixes); partial indexes carry both `postgresql_where=` and `sqlite_where=`. All models in `app/lms/content/models.py` except `Asset`/`AssetBlob` in `app/lms/files/models.py`; `app/lms/models.py` imports them all.

### 2.1 `assets`
`id`, `owner_id` FK users RESTRICT not null, `course_id` uuid FK courses SET NULL null (course of first upload, informational), `kind String(8)` CHECK `IN ('image')`, `visibility String(8)` CHECK `IN ('public','private')` default `public`, `source_sha256 String(64)` not null, `sha256 String(64)` not null, `storage_key String(200)` not null, `mime String(64)` not null (`image/webp`), `bytes Integer` not null (stored), `source_bytes Integer` not null, `width Integer`, `height Integer`, `original_filename String(255)` null (basename only, display only), timestamps, soft delete (`deleted_by_id` FK users SET NULL).
Constraints: `UNIQUE(owner_id, source_sha256, visibility)` (`uq_assets_owner_source`); CHECK `bytes > 0`. Indexes: `(owner_id, created_at)`, `(sha256)`.

### 2.2 `asset_blobs` (driver `db` only; created everywhere)
`key String(200)` PK, `sha256 String(64)` not null, `mime String(64)` not null, `size Integer` not null, `data LargeBinary` not null (bytea), `created_at`. PG only in the migration: `ALTER TABLE asset_blobs ALTER COLUMN data SET STORAGE EXTERNAL` (WebP is incompressible; skips pglz attempts).

### 2.3 `question_banks`
`id`, `owner_id` FK users RESTRICT, `course_id` FK courses RESTRICT null, `title String(200)` not null, `description Text` null, `source_id String(120)` null, `default_language String(2)` null CHECK `IN ('en','ru','ky')`, timestamps, soft delete.
Indexes: partial unique `(course_id, source_id) WHERE source_id IS NOT NULL AND course_id IS NOT NULL AND deleted_at IS NULL` (`uq_question_banks_course_source`); `(course_id, deleted_at, created_at)`; `(owner_id)`.

### 2.4 `translation_groups`
`id`, `course_id` FK courses RESTRICT null, `created_by_id` FK users SET NULL null, `created_at`. Index `(course_id)`.

### 2.5 `passages` / `passage_versions`
`passages`: `id`, `bank_id` FK question_banks RESTRICT not null, `language String(2)` CHECK, `current_version_id` FK passage_versions (**`use_alter=True`**, name `fk_passages_current_version_id`) null, `imported_version_id` FK passage_versions (use_alter, `fk_passages_imported_version_id`) null, `source_ref String(200)` null, timestamps, soft delete. Indexes: partial unique `(bank_id, source_ref) WHERE source_ref IS NOT NULL`; `(bank_id, deleted_at)`.
`passage_versions`: `id`, `passage_id` FK passages RESTRICT, `version_no Integer`, `language String(2)`, `title String(300)` null, `body Text` not null, `image JSONType` null (ImageRef), `content_hash String(64)` not null, `origin String(8)` CHECK `IN ('create','edit','import','revert')`, `created_at`, `created_by_id` FK users SET NULL null. `UNIQUE(passage_id, version_no)`.

### 2.6 `bank_questions`
`id`, `bank_id` FK question_banks RESTRICT not null, `passage_id` FK passages RESTRICT null, `translation_group_id` FK translation_groups SET NULL null, `current_version_id` FK question_versions (use_alter, `fk_bank_questions_current_version_id`) null, `imported_version_id` FK question_versions (use_alter, `fk_bank_questions_imported_version_id`) null, `type String(24)` (mirror of current version), `language String(2)`, `topic String(200)` null, `difficulty String(8)` null, `section String(40)` null, `tags JSONType` not null default `[]`, `position Integer` not null, `q_num String(16)` null, `source_ref String(200)` null, `source_meta JSONType` null (`{"fixed": bool, "source_page": int}`), `search_text Text` not null default `''`, timestamps, soft delete.
CHECKs: `type IN ('single_choice','multiple_answers','true_false','comparison','numeric','short_text','essay')`, `language IN ('en','ru','ky')`, `difficulty IS NULL OR difficulty IN ('easy','medium','hard')`.
Indexes: partial unique `(bank_id, source_ref) WHERE source_ref IS NOT NULL` (`uq_bank_questions_source_ref`); partial unique `(translation_group_id, language) WHERE translation_group_id IS NOT NULL AND deleted_at IS NULL` (`uq_bank_questions_group_language`); `(bank_id, position, id)`; `(passage_id)`; `(translation_group_id)`.
Invariant (service + test): after commit every question has a non-null `current_version_id` whose `question_id` is itself and whose `type`/`language` equal the row's.

### 2.7 `question_versions`
`id`, `question_id` FK bank_questions RESTRICT, `version_no Integer`, `language String(2)`, `type String(24)`, `schema_version SmallInteger` default 1, `stem Text` not null default `''`, `data JSONType` not null, `explanation Text` null, `default_points Numeric(8,2)` not null default 1, `image JSONType` null (ImageRef), `content_hash String(64)` not null, `origin String(8)` (same CHECK as passages), `created_at`, `created_by_id` FK users SET NULL null.
`UNIQUE(question_id, version_no)`; CHECK `default_points >= 0 AND default_points <= 1000`; CHECK on `type`.
`content_hash` = sha256 of canonical JSON (`sort_keys`, no spaces) of `{type, schema_version, language, stem, data (with ImageRefs reduced to asset_id), explanation, default_points as str, image asset_id}`.

### 2.8 Alembic `0003_phase2_content` (down_revision `0002_phase1_courses`)
Upgrade: create `assets`, `asset_blobs`, `question_banks`, `translation_groups`, `passages` (without the two version FKs), `passage_versions`, `bank_questions` (without the two version FKs), `question_versions`; then `with op.batch_alter_table("passages")` / `("bank_questions")`: `create_foreign_key` for the four `use_alter` FKs (names as above); PG-only `SET STORAGE EXTERNAL`. Downgrade: drop the four FKs in batch mode, then tables in reverse order. `alembic check` must be clean (every index/constraint/FK name in both model and migration). Tests' scratch DB uses `create_all` (SQLite tolerates forward FK references).
`tests/lms/conftest.py` cleanup (append, FK-safe): `UPDATE bank_questions SET current_version_id=NULL, imported_version_id=NULL`, `UPDATE passages SET current_version_id=NULL, imported_version_id=NULL`, then delete `question_versions, bank_questions, passage_versions, passages, translation_groups, question_banks, assets, asset_blobs` before the Phase 1 tables; also reset the storage singleton and media LRU.

### 2.9 Size budget (Neon free ≈ 0.5 GB)
Per question with one version: row + `search_text` ≈ 1.5 KB, version (stem ~0.3 KB, data ~0.6 KB, explanation ~0.3 KB, JSONB overhead) ≈ 1.3 KB, indexes ≈ 0.5 KB → **≈ 3.5 MB per 1,000 questions**, +1.3 MB per 1,000 edits. Passages ≈ 3 KB per version, about one per 6 reading questions. Images: tsoomo19 has 14 images per 150 questions and the whole zip is 258 KB, so ≈ 10–15 KB per lossless WebP → **≈ 1–1.5 MB per 1,000 questions**; a figure-heavy subject (half the questions, 30 KB each) ≈ 15 MB. Total **5–20 MB per 1,000 questions**: 0.5 GB holds roughly 25k–100k questions; `ASSET_DB_MAX_TOTAL_BYTES=300 MiB` keeps headroom for attempts. Before merging to production, check the current Neon size with the Neon MCP.

## 3. Services

Conventions as Phase 1 section 3: services take `db` and the acting `User`/`AuthzContext`, own the transaction (one `commit` at the end, `LMSError` before it). Row locks via `with_for_update()` (proven only on PG). All bulk reads use `IN` lists chunked by 500.

### 3.1 Storage (`app/lms/files/storage.py`)
```python
class BlobStorage(ABC):                      # sync; LMS routes are sync def
    def put(self, key: str, data: bytes, mime: str) -> None      # idempotent; never overwrites an existing key
    def exists(self, key: str) -> bool
    def get(self, key: str) -> Optional[bytes]
    def public_url(self, key: str) -> Optional[str]              # None => served by /media
    def presigned_get(self, key: str, ttl: int, filename: str) -> Optional[str]  # None => stream it
class LocalBlobStorage(BlobStorage)    # dir = LMS_LOCAL_STORAGE_DIR or {LOCAL_UPLOAD_DIR}/lms; atomic write (tmp + os.replace)
class DbBlobStorage(BlobStorage)       # own connection: `with engine.begin()`; INSERT .. ON CONFLICT (key) DO NOTHING (pg/sqlite dialect insert)
class R2StorageService(BlobStorage)    # boto3.client("s3", endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                                       #   region_name="auto", config=Config(signature_version="s3v4")); client injectable for tests
    # put: head_object first (skip if present), put_object(Bucket, Key, Body, ContentType, CacheControl="public, max-age=31536000, immutable")
    # exists: head_object, ClientError 404/NoSuchKey -> False; presigned_get: generate_presigned_url("get_object", ..., ResponseContentDisposition)
def get_blob_storage() -> BlobStorage        # process singleton from settings; r2 with missing settings -> RuntimeError at startup
def media_url(sha256: str) -> str            # P2-2; the ONLY place URLs are built
```
Rule: `put` is called **before** the request session writes anything (SQLite file lock; same rule as `ratelimit.hit`). Orphan blobs after a failed transaction are harmless. Startup logs a warning when driver is `local` and the database is Postgres.

### 3.2 Images and assets (`app/lms/files/images.py`, `service.py`)
```python
@dataclass
class EncodedImage: source_sha256: str; sha256: str; data: bytes; width: int; height: int; source_bytes: int
def encode_image(raw: bytes, *, max_bytes: int) -> EncodedImage
    # validate_image_bytes(raw, max_bytes) (reused, read-only import from app.services.image_validation)
    # pixel check from header (Image.open(...).size) before load -> ValueError("too_many_pixels")
    # P2-5 pipeline; stored size > 2 MiB -> ValueError("too_large_after_encode")
def ingest_image(db, actor: User, raw: bytes, *, course_id, visibility="public", filename=None,
                 max_bytes=settings.ASSET_MAX_UPLOAD_BYTES, encoded: EncodedImage | None = None) -> tuple[Asset, bool]
    # 1. existing = (owner, source_sha256, visibility) -> revive if deleted, return (asset, True)   [no encode]
    # 2. quota checks (P2-6) -> Conflict("storage_quota_exceeded") / LMSError 507 "storage_full"
    # 3. if encoded is None: encode + storage.put(key, data, "image/webp")   [before any session write]
    #    if encoded is given (importer): the caller already called storage.put in its step 3; no put here
    # 4. insert Asset; flush; on IntegrityError (race) rollback-to-savepoint and return the winner row
    # Does NOT commit (callers: upload route commits; importer commits its own transaction).
def resolve_image_ref(db, actor, asset_id, *, carried: set[UUID]) -> dict       # P2-16 -> {"asset_id","sha256"}; else ValidationFailed("asset_not_usable")
def resolve_image_refs(db, actor, ids: Iterable[UUID], *, carried) -> dict[UUID, dict]   # one query
def list_my_assets(db, actor, cursor, limit) / soft_delete_asset(db, actor, asset_id)
```
Upload route: `Content-Length` > cap + 64 KiB → 413 before reading; then streamed read with running count (copy `upload.py` loop) → 413 `image_too_large`; `ValueError` → 400 `image_invalid` / `image_too_many_pixels`; rate limit `asset_upload_1h` via `ratelimit.enforce` **before** any write.

### 3.3 Media route (`app/lms/files/media.py`)
`GET /api/v1/media/{name}`: regex check → 404 `not_found`; `If-None-Match` equal to `"{sha}"` → 304; else bytes from an in-process thread-safe LRU (`MEDIA_CACHE_BYTES` 64 MiB, OrderedDict + lock) or `storage.get("img/"+name)` → 404 if missing. Headers: `Content-Type: image/webp`, `ETag: "{sha}"`, `Cache-Control: public, max-age=31536000, immutable`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'`, `Content-Disposition: inline`. Must not be gzip-compressed (test; if `GZipMiddleware` compresses it, exclude the path). No auth, no DB session for cache hits.
Scale: browsers cache forever; Vercel's rewrite may cache at the edge (open question Q2); the LRU makes Neon see each image about once per worker. When `R2_PUBLIC_BASE_URL` exists, URLs bypass the backend entirely.

### 3.4 Question type registry (`app/lms/content/types/`)
```python
class QuestionType(ABC):
    name: str; schema_version: int = 1
    Data: type[BaseModel]          # stored in question_versions.data (extra="forbid")
    Response: type[BaseModel]      # Phase 3 autosave payload (extra="forbid")
    def validate(self, raw: dict) -> dict                        # Data(**raw).model_dump(mode="json"); ValidationFailed("invalid_question_data", details=[{loc,msg}])
    def student_view(self, data: dict) -> dict                    # built from STUDENT_KEYS only; image refs -> {"url": media_url(sha)}
    def key_view(self, data: dict) -> dict                        # correct answer for post-submit review (Phase 3/4)
    def score(self, data: dict, response: dict | None, max_points: Decimal) -> ScoreResult
    def search_strings(self, data: dict) -> list[str]
    def image_refs(self, data: dict) -> list[dict]
@dataclass(frozen=True)
class ScoreResult: points: Optional[Decimal]; max_points: Decimal; correct: Optional[bool]; needs_review: bool
REGISTRY: dict[str, QuestionType]; def get_type(name) -> QuestionType   # unknown -> ValidationFailed("unsupported_type")
```
| type | `Data` | `Response` | `student_view` keys | score |
|---|---|---|---|---|
| single_choice | `choices[2..10]: {id (1–8 chars [A-Za-z0-9_]), text, image?: ImageRef}` unique ids, `correct: id ∈ ids`, `shuffle: bool=False` | `{choice_id: str\|None}` | `choices[{id,text,image_url?}]`, `shuffle` | full if equal else 0 |
| multiple_answers | same `choices`, `correct: [id]` (≥1, unique, ⊆ ids), `scoring: all_or_nothing\|partial` | `{choice_ids: [str]}` | `choices`, `shuffle` | all_or_nothing: exact set; partial: `max * max(0, (right − wrong) / len(correct))`, 2 dp |
| true_false | `correct: bool` | `{value: bool\|None}` | `{}` | equal |
| comparison | `column_a`, `column_b` (non-empty), `correct ∈ A..D` | `{choice: A..D\|None}` | `column_a, column_b` | equal |
| numeric | `answers[1..10]: {kind:"exact", value:str, margin:str="0"} \| {kind:"range", min:str, max:str}` (Decimal strings, finite, margin ≥ 0, min ≤ max) | `{value: str}` | `{}` | parse: strip, remove spaces, `,`→`.`, `−`→`-`, `Decimal`, finite; any answer matches → full |
| short_text | `answers[1..20]: str` (non-empty after normalize), `case_sensitive: bool=False` | `{text: str ≤ 500}` | `{}` | `norm(x)`: NFKC, collapse whitespace, strip, casefold unless case_sensitive, map look-alikes `а→a е→e о→o р→p с→c у→y х→x к→k і→i ј→j ѕ→s` (Kyrgyz `ү ө ң` untouched); equal to any |
| essay | `word_limit: int\|None (1..5000)`, `rubric_note: str\|None` (staff only) | `{text: str ≤ 20000}` | `word_limit` | blank → 0 (not review); else `points=None, needs_review=True` |
Empty/None response → 0 points, `correct=False`, never an exception. Common student payload wrapper (`repository.student_question(version)`): `{id: version_id, type, language, stem, image_url, data: student_view(...)}` — never `explanation`, `default_points` is allowed (`points`).

### 3.5 Content repository (`app/lms/content/repository.py`) — the one place that joins through versions
```python
def load_bank(db, course_id, bank_id, *, include_deleted=False, for_update=False) -> QuestionBank   # bank.course_id must equal course_id else NotFound("bank_not_found")
def load_question(db, course_id, question_id, *, include_deleted=False, for_update=False) -> BankQuestion  # JOIN bank; bank deleted -> 404
def load_passage(...) -> Passage
def question_list_stmt(bank_id, f: QuestionFilter) -> Select   # (BankQuestion, QuestionVersion.stem, QuestionVersion.version_no) JOIN current version; filters type/language/section/topic/difficulty/tag/passage_id/deleted; q -> search_text LIKE '%'||casefold(q)||'%' ESCAPE
def load_versions(db, version_ids) -> dict[UUID, QuestionVersion]        # chunked IN; for Phase 3 snapshots
def load_passage_versions(db, ids) -> dict[UUID, PassageVersion]
def student_question(v: QuestionVersion) -> dict / student_passage(pv) -> dict   # pure, no DB
```
N+1 guard: building student payloads for 150 versions + their passages = ≤ 2 queries (test counts with `before_cursor_execute`).

### 3.6 Content service (`app/lms/content/service.py`)
```python
def create_bank(db, ctx, course, data: BankCreateIn) -> QuestionBank
def update_bank / soft_delete_bank / restore_bank(...)        # restore: live bank with same (course, source_id) -> Conflict("source_conflict")
def create_question(db, ctx, course, bank, data: QuestionCreateIn, *, origin="create") -> BankQuestion
    # lock bank row; validate type data; resolve refs (carried=∅); position = max+1;
    # insert question (current NULL) -> flush -> insert version 1 -> flush -> set current_version_id, type, search_text; commit
def update_question(db, ctx, course, question_id, data: QuestionUpdateIn) -> tuple[BankQuestion, bool]  # (q, unchanged)
    # load_question(for_update=True); meta-only patch allowed without base_version_id;
    # content: base_version_id check (P2-12); carried = refs of current version; hash compare (P2-10); new version; commit
def revert_question(db, ctx, course, question_id, version_id, base_version_id) -> BankQuestion
def soft_delete_question / restore_question(...)               # restore into deleted bank -> 409 bank_deleted; group-language clash -> 409 translation_language_taken
def move_question(db, ctx, course, question_id, direction) -> BankQuestion   # P2-25; no neighbor -> 409 invalid_move
def add_translation(db, ctx, course, question_id, data: TranslationCreateIn) -> BankQuestion
    # language ∈ course.languages and != source language; create group if none (same tx); copy current content as version 1 of the new question
    # (origin "create"), same bank unless bank_id given (must be a live bank of this course); IntegrityError on group-language index -> 409 translation_language_taken
def link_translation(db, ctx, course, question_id, other_id) -> None   # same course, same type, other ungrouped or same group; languages distinct
def unlink_translation(db, ctx, course, question_id) -> None
def create_passage / update_passage / revert_passage / soft_delete_passage / restore_passage   # same version rules; delete in use -> 409 passage_in_use
def new_question_version(db, q, content: dict, *, actor_id, origin) -> QuestionVersion   # shared by service and importer; no commit
def new_passage_version(db, p, content: dict, *, actor_id, origin) -> PassageVersion
```
`search_text` = casefold of `stem + search_strings(data) + topic + q_num`, joined by `\n`, truncated to 8 000 chars; rewritten on every version and meta change.

### 3.7 Importer (`app/lms/content/importers/`)
```
zipsafe.py   copy of _SafeZip + BundleError; limits from settings (P2-22)
ort_csv.py   copy of parse_csv_content, get_field_value (+ "_en" legacy suffix), SECTION/DIFFICULTY/COLUMN aliases,
             CYRILLIC_TO_LATIN_OPTION, row validation -> ImportRow | list[ImportIssue]; no QuestionCreate, no Firestore
bundle.py    copy of _find_bundles, _parse_bundle, _check_image, _resolve_image -> list[ParsedBundle]; image sha check
             against manifest uses the ORIGINAL bytes; then encode_image(max_bytes=10 MiB) -> issue image_invalid / image_too_many_pixels
rules.py     ORT preset (P2-20); ORT_SECTIONS copied from app.schemas.question.SectionType values
mapping.py   ImportRow -> (type, content dict, meta dict, passage key)
service.py   preview(db, ctx, course, raw, filename, opts) -> ImportReport ; commit(...) -> ImportReport
schemas.py   ImportOptions, ImportIssue, ImportBankSummary, ImportReport
```
`ImportRow`: `row, section, topic, difficulty, stem, column_a, column_b, options{A..E}, correct, passage_text, image (ResolvedImage: source bytes, source_sha256, EncodedImage) | None, explanation, tags, external_id, q_num, fixed, source_page`.
Commit algorithm:
1. `ratelimit.enforce(content_import_1h)`; `require(ctx, CONTENT_MANAGE, course)`.
2. Parse + validate everything (pure, no DB). Any error → report `ok=false`, nothing written.
3. For each distinct `source_sha256`: skip if the actor already owns a live public asset with it; else `storage.put` the encoded bytes (before any session write).
4. One transaction: per bundle lock or create the bank (`IntegrityError` on the partial unique → 409 `import_busy`); **inside the lock** load existing questions/passages by `source_ref` (chunked) and plan per row (P2-18); `ingest_image(..., encoded=...)` for asset rows; passages first (one per distinct normalized `passage_text` per bundle, in first-appearance order; `source_ref = "{first external_id}#passage"` with a manifest), then questions via `new_question_version`; set `imported_version_id` on created/updated rows; positions/meta per P2-18/P2-25; commit.
5. Report. Preview runs steps 1–2 plus the read-only plan without locks.
`ImportReport` (snake_case): `ok, committed, banks: [ImportBankSummary{root, source_id, has_manifest, language, bank_id?, bank_title, bank_exists, question_count, sections{}, created{}, updated{}, unchanged{}, conflicts{}, skipped_deleted{}, images}], errors: [ImportIssue{severity, code, message, bundle?, file?, row?, column?, params}], warnings, images_total, images_new, images_existing`. Issue codes = every code raised in `bundle_service.py` (`BundleError` and `_Issues`: `zip_*`, `no_bundle_found`, `manifest_*`, `questions_file_missing`, `multiple_question_csvs`, `csv_*`, `row_invalid`, `correct_option_not_allowed`, `duplicate_external_id`, `duplicate_source_id`, `image_missing|ambiguous|sha_mismatch|invalid|too_large|unused`, `questions_missing_from_bundle`, `storage_error`, `database_error`; grep the file for the exact list; `firestore_mirror_failed` is dropped) plus new `image_not_included` (plain CSV bare name), `image_external_url`, `image_too_many_pixels`, `too_many_rows`, `too_many_images`, `language_not_in_course`, `question_edited_locally`, `question_deleted_skipped`, `target_bank_not_allowed`.

## 4. Authorization additions

- No new actions. Content routes use existing `A.CONTENT_READ_ADMIN` and `A.CONTENT_MANAGE` with Phase 1 `decide()` gates (P2-9). `A.CONTENT_READ` (students) is unused until Phase 3.
- Pattern in every content route: `course = svc.load_course(db, course_id)` → `require(ctx, action, course)` → `repository.load_*(db, course.id, child_id)` which 404s when the child belongs to another course or a deleted bank (anti-IDOR). Never load the child first.
- Assets: `POST /courses/{id}/assets` needs `CONTENT_MANAGE` on that course (so assistants can upload). `/assets*` routes act on `owner_id == user.id` only (404 otherwise). `/media/*` is public by design (P2-2).
- Row rules in services: asset usability (P2-16), translation scope (same course, same type), bank target belongs to course, restore conflicts.
- Platform admins: no bypass (P1-12).
- Route inventory: add `public` to `POLICY_NAMES`; merge `CONTENT_POLICIES`, `IMPORT_POLICIES`, `ASSET_POLICIES`, `MEDIA_POLICIES` into `ROUTE_POLICIES`. Policy strings used: `course:content.read_admin`, `course:content.manage`, `course:content.manage+ratelimit`, `authenticated`, `public`.

## 5. API (all under `/api/v1`; LMS error shape; snake_case)

Routers: `app/lms/content/router.py` (prefix `/courses`, banks/questions/passages/translations), `app/lms/content/import_router.py` (prefix `/courses`), `app/lms/files/router.py` (`/courses/{id}/assets` and `/assets`), `app/lms/files/media.py` (`/media`). `{c}` = `course_id`. List routes return `PageOut[T]` with cursor (`limit` ≤ 100).

| method | path | in → out | policy | errors |
|---|---|---|---|---|
| GET | `/courses/{c}/banks?deleted=false` | → `PageOut[BankOut{id,title,description,source_id,default_language,question_count,passage_count,created_at,updated_at,deleted_at}]` (counts via one grouped subquery) | course:content.read_admin | course_not_found |
| POST | `/courses/{c}/banks` | `BankCreateIn{title 1..200, description?, default_language?∈course.languages}` → `BankOut` 201 | course:content.manage | validation_failed, language_not_in_course |
| GET | `/courses/{c}/banks/{b}` | → `BankOut` | course:content.read_admin | bank_not_found |
| PATCH | `/courses/{c}/banks/{b}` | `BankUpdateIn{title?, description?, default_language?}` → `BankOut` | course:content.manage | bank_not_found |
| DELETE | `/courses/{c}/banks/{b}` | → 204 | course:content.manage | bank_not_found, already_deleted |
| POST | `/courses/{c}/banks/{b}/restore` | → `BankOut` | course:content.manage | not_deleted, source_conflict |
| GET | `/courses/{c}/banks/{b}/questions?q&type&language&section&topic&difficulty&tag&passage_id&deleted&cursor&limit` | → `PageOut[QuestionSummaryOut{id,bank_id,type,language,topic,difficulty,section,tags,position,q_num,stem_excerpt(≤200),has_image,passage_id,translation_group_id,version_no,updated_at,deleted_at}]`, order `(position,id)` asc | course:content.read_admin | bank_not_found, invalid_cursor |
| POST | `/courses/{c}/banks/{b}/questions` | `QuestionCreateIn{type, language, stem, data, explanation?, default_points=1, image_asset_id?, topic?, difficulty?, section?, tags[]≤20, passage_id?}` → `QuestionStaffOut` 201 | course:content.manage | invalid_question_data, unsupported_type, asset_not_usable, language_not_in_course, passage_not_found |
| GET | `/courses/{c}/questions/{q}` | → `QuestionStaffOut{...summary, current_version: VersionOut, passage?: PassageSummaryOut, translations: [{question_id, language, bank_id}]}` | course:content.read_admin | question_not_found |
| PATCH | `/courses/{c}/questions/{q}` | `QuestionUpdateIn{base_version_id?, content?: {type, stem, data, explanation?, default_points, image_asset_id?} (full replacement), meta?: {topic?, difficulty?, section?, tags?, passage_id?}}` → `QuestionStaffOut` + `unchanged: bool` | course:content.manage | version_conflict, invalid_question_data, asset_not_usable, question_not_found |
| DELETE | `/courses/{c}/questions/{q}` | → 204 | course:content.manage | question_not_found, already_deleted |
| POST | `/courses/{c}/questions/{q}/restore` | → `QuestionStaffOut` | course:content.manage | not_deleted, bank_deleted, translation_language_taken |
| POST | `/courses/{c}/questions/{q}/move` | `{direction: up\|down}` → `QuestionSummaryOut` | course:content.manage | invalid_move |
| GET | `/courses/{c}/questions/{q}/versions` | → `PageOut[VersionSummaryOut{id,version_no,type,origin,created_at,created_by_name}]` (desc) | course:content.read_admin | question_not_found |
| GET | `/courses/{c}/questions/{q}/versions/{v}` | → `VersionOut{id,version_no,type,language,stem,data (with image urls),explanation,default_points,image{asset_id,url}?,origin,created_at,created_by_name}` | course:content.read_admin | version_not_found |
| POST | `/courses/{c}/questions/{q}/versions/{v}/revert` | `{base_version_id}` → `QuestionStaffOut` | course:content.manage | version_conflict, version_not_found |
| GET | `/courses/{c}/questions/{q}/preview?version_id=` | → `StudentQuestionOut{id,type,language,stem,image_url,points,data}` + `passage?: StudentPassageOut{id,title,body,image_url}` | course:content.read_admin | question_not_found, version_not_found |
| GET | `/courses/{c}/questions/{q}/translations` | → `[QuestionSummaryOut]` | course:content.read_admin | question_not_found |
| POST | `/courses/{c}/questions/{q}/translations` | `TranslationCreateIn{language, bank_id?}` → `QuestionStaffOut` 201 | course:content.manage | translation_language_taken, language_not_in_course, bank_not_found |
| POST | `/courses/{c}/questions/{q}/translation-link` | `{question_id}` → 204 | course:content.manage | translation_scope_mismatch, translation_type_mismatch, translation_language_taken |
| DELETE | `/courses/{c}/questions/{q}/translation-link` | → 204 | course:content.manage | question_not_found |
| GET | `/courses/{c}/banks/{b}/passages?deleted&cursor&limit` | → `PageOut[PassageSummaryOut{id,language,title,body_excerpt,question_count,version_no,updated_at,deleted_at}]` | course:content.read_admin | bank_not_found |
| POST | `/courses/{c}/banks/{b}/passages` | `PassageCreateIn{language, title?, body, image_asset_id?}` → `PassageOut` 201 | course:content.manage | asset_not_usable |
| GET | `/courses/{c}/passages/{p}` | → `PassageOut{...summary, current_version, questions: [QuestionSummaryOut]}` | course:content.read_admin | passage_not_found |
| PATCH | `/courses/{c}/passages/{p}` | `{base_version_id, title?, body, image_asset_id?}` → `PassageOut` | course:content.manage | version_conflict |
| DELETE / POST restore | `/courses/{c}/passages/{p}` / `.../restore` | → 204 / `PassageOut` | course:content.manage | passage_in_use, not_deleted |
| GET | `/courses/{c}/passages/{p}/versions` (+ `/{v}`, `/{v}/revert` POST) | as questions | read_admin / manage | version_not_found |
| POST | `/courses/{c}/imports/preview` | multipart `file`, `language`, `exam_type?`, `target_bank_id?` → `ImportReport` | course:content.manage+ratelimit | file_too_large (413), rate_limited |
| POST | `/courses/{c}/imports` | same + `on_conflict=skip\|overwrite` → `ImportReport` | course:content.manage+ratelimit | file_too_large, import_busy, rate_limited |
| POST | `/courses/{c}/assets` | multipart `file`, `visibility=public` → `AssetOut{id,url?,mime,bytes,width,height,sha256,original_filename,created_at,deduplicated}` 201/200 | course:content.manage+ratelimit | image_invalid (400), image_too_large (413), image_too_many_pixels (400), storage_quota_exceeded (409), storage_full (507) |
| GET | `/assets?cursor&limit` | → `PageOut[AssetOut]` (mine, live) | authenticated | — |
| DELETE | `/assets/{a}` | → 204 | authenticated | asset_not_found |
| GET | `/assets/{a}/content` | → bytes or 302 (P2-3) | authenticated | asset_not_found |
| GET | `/media/{name}` | → `image/webp` / 304 | public | not_found |

New `lms.errors.*` codes: `bank_not_found, question_not_found, passage_not_found, version_not_found, asset_not_found, version_conflict, invalid_question_data, unsupported_type, asset_not_usable, image_invalid, image_too_large, image_too_many_pixels, storage_quota_exceeded, storage_full, language_not_in_course, translation_language_taken, translation_scope_mismatch, translation_type_mismatch, source_conflict, bank_deleted, passage_in_use, invalid_move, import_busy, file_too_large`.
Staff `data` in `QuestionStaffOut`/`VersionOut` includes the key (staff only) and image refs expanded to `{asset_id, url}`.

## 6. Frontend

Routes under `frontend/src/app/[lang]/courses/[courseId]/` (inside the Phase 1 `CourseContext` layout; client components; hide for students, server decides):

| path | content |
|---|---|
| `bank/page.tsx` | bank list (cards: title, source, counts, updated), create bank dialog, trash toggle + restore, "Import" button |
| `bank/[bankId]/page.tsx` | toolbar: search (debounced 300 ms), filters (type, language, section — ORT codes shown via existing `sections.*` labels, topic, difficulty, tag, deleted); list rows with `MathRenderer` excerpt, type/language badges, translation and image icons, position, move up/down, delete/restore; `Pager`; "New question" (type picker); tab to passages |
| `bank/[bankId]/new/page.tsx?type=` | `QuestionEditor` in create mode |
| `bank/q/[questionId]/page.tsx` | `QuestionEditor` with tabs **Edit · Preview · History · Translations**. Save sends `base_version_id`; 409 `version_conflict` → dialog "changed by someone else" with Reload; `unchanged` → toast "no changes" |
| `bank/[bankId]/passages/page.tsx`, `bank/p/[passageId]/page.tsx` | passage list; editor (title, body textarea with `[N]` line-marker help, preview via existing `components/exam/NumberedPassage.tsx` + `MathRenderer`, image, linked questions, history) |
| `bank/import/page.tsx` | import (below) |

Components (`frontend/src/components/lms/content/`): `QuestionEditor` (meta fields + type fields + `RichTextField` stem + `ImagePicker` + points + explanation + passage selector), `types/{SingleChoiceFields, MultipleAnswersFields, TrueFalseFields, ComparisonFields, NumericFields, ShortTextFields, EssayFields}.tsx` (choices add/remove/reorder, mark correct, letters as default ids), `RichTextField` (textarea + live `MathRenderer` preview + buttons inserting `$…$`, `<u></u>`, `<b></b>`), `ImagePicker` (file input, drag-drop and paste → `POST /courses/{c}/assets`; shows "already uploaded" when `deduplicated`; "my images" grid from `GET /assets`; remove), `StudentPreview` (renders `StudentQuestionOut`; reuse `components/exam/ComparisonQuestionCard.tsx` / `QuestionCard.tsx` read-only if their props fit, else a small local renderer; comparison labels from `bank.types.comparison.labels.A..D`), `VersionHistory` (list + side-by-side render of a selected version vs current + Revert), `TranslationPanel` (variants by language, "Add translation" for each missing course language, link existing by search, unlink), `BankFilters`, `QuestionRow`.
Import (`components/lms/content/import/`): `ImportPanel` (file `.zip`/`.csv`; language select limited to `course.languages`; format select ORT main / ORT subject / ORT practice / General → `exam_type`; target bank select for CSV; conflict policy radio; Check → preview; Confirm → commit; result links to banks), `ImportReportView` (port of `BundleImportPanel` rendering: per-bank section table with created/updated/unchanged/conflicts/skipped, images new/existing, issues table row/column/message mapped by `bank.import.issues.<code>` with `message` fallback).
Lib: `lib/lms/content.ts` (banks, questions, passages, versions, translations, assets: `uploadAsset(courseId, file)` uses `FormData` with `getAuthHeader()` and parses LMS errors like `lmsFetch`), `lib/lms/contentTypes.ts` (TS mirrors of section 5 schemas and per-type `data` unions), `lib/lms/contentImport.ts` (`previewImport`, `commitImport`). `CourseTabs.tsx`: add one "Question bank" tab (`bank.tab`) when the user is staff.
i18n (en/ky/ru, parity): `bank.*` (tab, list, filters, editor, types incl. `types.comparison.labels.A..D` copied from today's ky/ru option texts, history, translations, passages, assets, preview), `bank.import.*` (copy wording from `bundleImport.*` and add new codes), new `lms.errors.*` codes. Old `bundleImport.*` keys stay for the old page.

## 7. Test plan

Location `backend/tests/lms/`, scratch DB per `AGENTS.md` 6.1; storage driver `local` in a tmp dir via fixture (and `db` where stated). Factories (append to `tests/lms/factories.py`): `make_bank(db, course, owner, **kw)`, `make_question(db, bank, actor, type="single_choice", **kw)`, `png_bytes(w, h, color)`, `jpeg_with_exif()`.

1. **Registry unit** `test_question_types.py`: table-driven `score()` per type (correct, wrong, empty, None, malformed response → 0 not exception; partial formula incl. floor at 0; numeric comma/space/minus-sign/margin/range edges; short_text Cyrillic look-alikes, case-sensitive flag, Kyrgyz letters not folded; essay needs_review); `validate()` rejects duplicate choice ids, correct not in choices, non-finite numerics, min > max, unknown keys.
2. **Serializer contracts** `test_content_serializers.py`: for every type, data seeded with sentinel strings in every key-only field (`correct`, `answers`, `margin`, `scoring`, `case_sensitive`, `rubric_note`, explanation) → `student_question()` JSON contains none of the sentinels and exact key sets equal an explicit table in the test; `StudentQuestionOut`/`StudentPassageOut` exact keys; `/preview` response passes the same checks.
3. **Versioning** `test_versioning.py`: create → v1; edit → v2, v1 row byte-identical (stem, data, hash); identical save → `unchanged`, no row; stale `base_version_id` → 409; meta-only patch → no version; revert → v3 equals v1 content; ORM update/delete of a version raises; invariant check (current version belongs to question, type/language mirror) after every service call; asset carried over from base version accepted for a co-teacher who does not own it; new foreign asset → 422.
4. **Banks/questions/passages/translations API** `test_banks_api.py`, `test_questions_api.py`, `test_passages_api.py`, `test_translations.py`: CRUD, filters + search (Cyrillic `q`), keyset pagination stable across pages, move within section, delete/restore (bank restore source conflict, passage in use), translation add/link/unlink rules and the group-language unique race (sequential on SQLite).
5. **Matrix** `test_content_matrix.py`: actors O, T, AS, S, R, X, P (Phase 1 7.2) × statuses draft/published/concluded/deleted over every content, import and asset route: staff 2xx on draft/published; writes 403 for staff on concluded, reads 200; S 403; R, X, P 404; deleted 404.
6. **Isolation** `test_content_isolation.py`: TA/TB with CA/CB: every CB bank/question/passage/version id used under `/courses/{CA}/…` → 404; TA attaching TB's asset id → 422; `/assets/{TB asset}` → 404 for TA; import into CA never touches CB's bank of the same source; banks list exact per course.
7. **Storage and assets** `test_storage_drivers.py` (local and db drivers: put idempotent, get, exists, `public_url` None, private keys; R2 with `botocore.stub.Stubber`: put calls `head_object` then `put_object` with `ContentType` and immutable `CacheControl`, existing key skips put, 404 → exists False, presigned URL contains key and expiry; `media_url` switches with settings), `test_assets_api.py` (upload → WebP, dedupe returns same id with `deduplicated`, revive soft-deleted, quota 409, db global cap 507, rate limit 429), `test_media_route.py` (200 headers exact, 304 on `If-None-Match`, bad names / `priv` content → 404, no `content-encoding: gzip`, soft-deleted asset still served, LRU hit does no DB query).
8. **Upload abuse corpus** `test_upload_abuse.py` (via API): renamed `MZ` executable `.png` → 400; HTML → 400; SVG with `<script>` → 400; 5 MiB + 1 → 413 (and an oversize `Content-Length` → 413 without reading); PNG header claiming 20000×20000 → 400 `image_too_many_pixels`; truncated PNG → 400; empty → 400; PNG with appended HTML/ZIP trailer → 201 and stored bytes contain no trailer and decode as WebP; JPEG with EXIF GPS + orientation 6 → stored WebP has empty EXIF and rotated dimensions; animated GIF → single frame; CMYK JPEG and 16-bit PNG → accepted; filename `../../x.png` → `original_filename == "x.png"` and never used as a key; lying `Content-Type` ignored.
9. **Persistence across restart** `test_asset_persistence.py`: driver `db`: upload, then dispose the engine, reset the storage singleton and LRU, re-create the app client → `/media/{sha}` returns identical bytes; same for `local` with a new storage instance on the same dir. Integration flow repeats it after a bundle import.
10. **Ported import tests** `test_import_bundle.py`: all 12 BUNDLE_FORMAT acceptance cases against `/courses/{c}/imports(/preview)` with the original fixture `tests/fixtures/bundles/tsoomo19.zip` (case 1: 150 questions, 30 per section, one bank `source_id=tsoomo19`, language `ru` from manifest, 14 assets; q3 is `comparison` with both columns and an image whose stored WebP has **pixel-identical** RGBA to the source PNG; positions `math_1:1` first and `grammar:30` last; case 9: second import → `unchanged` 150, still 14 assets/blobs, version_no 1 everywhere; corrected re-upload → exactly one v2; case 11: plain CSV without images imports, rows with `https://` or `/uploads/` images → `image_external_url`; 11b bare names → 14 `image_not_included`, 136 valid; case 12: reading passage bodies keep line breaks and `[5]` markers byte-exact, `<u>` kept in grammar stems, `$…$` untouched) plus zip-slip, newer format version, not-a-zip and empty zip, sha mismatch and invalid image (with and without manifest), unused image warning, manifest row mismatch, missing-from-reupload warning, wrong correct option; every failure leaves zero rows and zero blobs. New: conflict rules P2-18 (teacher-edited → skipped with warning; `overwrite` → new version; deleted → skipped), `target_bank_id` rules, `language_not_in_course`, limits (`too_many_rows`, oversize 413), rate limit.
11. **Ported CSV/rule/order tests** `test_import_csv.py` (every `test_csv_ingestion` case re-expressed: valid/invalid, alias normalization, id column ignored, language injection, legacy bilingual columns, Cyrillic correct option, never crashes on junk, comparison parsing, sample CSVs contain math_1 comparisons), `test_import_rules.py` (`test_math_section_rule` CSV case under ORT preset with the same `(row, field)` error set; the same CSV in general mode imports all four rows except the `E` comparison row), `test_import_order.py` (positions and `q_num` from a bundle; CSV append keeps row order after existing; list is in `(position,id)` order regardless of insertion order; move up/down stays within section).
12. **Parity (temporary)** `test_import_parity.py`: old `CsvService.validate_csv` vs new parser on the sample CSVs and fixture rows → same valid-row count and same `(row, field)` error set under ORT preset; old `BundleService.preview` vs new preview on the fixture and on the safety variants → same error codes. Deleted at Phase 5.
13. **PG concurrency** (`LMS_PG_TEST_DATABASE_URL`, `test_pg_concurrency_content.py`): 10 threads save the same question with the same base → exactly one new version, others 409; 10 threads upload the same image as one owner → one asset row, one blob; two imports of the same source into one course → one bank, other 409 `import_busy` or a clean second pass; two `add_translation` with the same language → one 201, one 409.
14. **Migration** (append to `tests/test_migrations.py`, PG): `0002 → 0003 → 0002 → 0003` clean; `alembic check` clean.
15. **N+1** `test_content_queries.py`: question list page of 100 = 1 query (+1 count if any); student payload for 150 versions with passages ≤ 2 queries.
16. **Route inventory**: all new routes listed; every policy string valid.
17. **Integration** `test_phase2_flow.py`: teacher creates course → imports tsoomo19 → edits a question (v2) → adds a `ky` translation → links a passage → previews as student (no key) → restart (P2 test 9 steps) → images and versions intact.
Frontend: `tsc --noEmit`, isolated `next build`, i18n parity; manual scripted check: import preview/commit, editor per type with KaTeX preview, image paste, version revert, translation add.

## 8. Slices

| slice | owns (only these files) | depends on | must pass |
|---|---|---|---|
| **C1 Schema** (Sonnet; architect reviews) | `app/lms/content/{__init__,models}.py`, `app/lms/files/{__init__,models}.py`, `app/lms/models.py` (imports), `alembic/versions/0003_phase2_content.py`, `app/core/config.py` (all Phase 2 settings), `backend/.env.example` (names only, no values), `requirements.txt` (`boto3`), `app/core/route_inventory.py` (`public` + merges), `app/api/v1/router.py` (wire four routers), empty stub routers + `policies.py` for content, import, files, media; `tests/lms/conftest.py` (cleanup), `tests/lms/factories.py` (append), `tests/test_migrations.py` (append), `tests/lms/test_phase2_constraints.py` | Phase 1 merged into `lms` | full suite on SQLite; migration + `alembic check` on PG |
| **C2 Type registry** | `app/lms/content/types/**`, `app/lms/content/richtext.py`, `tests/lms/test_question_types.py`, registry part of `test_content_serializers.py` | none (pure; start immediately) | its tests |
| **C3 Files** | `app/lms/files/{storage,images,service,schemas,router,media,policies,scopes}.py`, `scripts/copy_blobs.py`, `tests/lms/test_{storage_drivers,assets_api,media_route,upload_abuse,asset_persistence}.py`, asset part of `test_pg_concurrency_content.py` | C1 | its tests, route inventory, full suite |
| **C4 Content service/API** | `app/lms/content/{repository,service,schemas,router,policies}.py`, `tests/lms/test_{versioning,banks_api,questions_api,passages_api,translations,content_matrix,content_isolation,content_queries}.py`, API part of `test_content_serializers.py`, content part of `test_pg_concurrency_content.py` | C1, C2; C3's `resolve_image_refs`/`media_url` (signatures fixed here; stub until C3 lands) | its tests, route inventory, full suite |
| **C5 Importer** | `app/lms/content/importers/**`, `app/lms/content/{import_router,import_policies}.py`, `tests/lms/test_import_{bundle,csv,rules,order,parity}.py`, import part of `test_pg_concurrency_content.py` | C1; parsing modules in parallel with C3/C4; writer needs C3 `ingest_image`/`encode_image` and C4 `new_question_version`/`new_passage_version` | its tests, full suite |
| **C6 Frontend bank + editor** | `frontend/src/lib/lms/{content,contentTypes}.ts`, `frontend/src/components/lms/content/**` except `import/`, `frontend/src/app/[lang]/courses/[courseId]/bank/**` except `import/`, `components/lms/CourseTabs.tsx` (one tab), i18n `bank.*` except `bank.import.*`, new `lms.errors.*` | this contract; live check after C4 | `tsc`, isolated `next build`, i18n parity |
| **C7 Frontend import** | `frontend/src/lib/lms/contentImport.ts`, `components/lms/content/import/**`, `app/[lang]/courses/[courseId]/bank/import/page.tsx`, i18n `bank.import.*` | C6's `contentTypes.ts` (C6 commits it first, within its first hour) | same |
| **Integration** (orchestrator + implementer) | `tests/lms/test_phase2_flow.py`, `docs/phases/PHASE_2.md`, `PRODUCT_DECISIONS.md` (P2 decisions), i18n merge, Render env `LMS_STORAGE_DRIVER=db` on the staging/lms deploy | all | section 0 gates; `/code-review` |

Parallelism: C1 and C2 start at once; after C1: C3, C4, C5 (parsers) in parallel; C5's writer after C3+C4; C6 from the start against this contract, C7 after C6's types.

## 9. Risks and open questions

- **Q1 (owner secret) R2**: Cloudflare account, bucket `ort-lms-media`, API token (Object Read & Write on that bucket), `R2_ACCOUNT_ID`, and later a Cloudflare-DNS domain for `R2_PUBLIC_BASE_URL` (D2). Until then driver `db`. Do not use `r2.dev` public URLs for production (rate-limited by Cloudflare).
- **Q2 Edge caching**: verify on staging whether Vercel caches `/api/v1/media/*` responses proxied by the rewrite (look for `x-vercel-cache: HIT`). If not, 6,000 students × ~14 images hit Render once each per browser (LRU keeps Neon out). Mitigations in order: R2 + domain; Phase 3 start payload lists image URLs so the client preloads during the lobby; scale Render for exam windows.
- **Q3 Neon size**: measure current usage before merge; the `ASSET_DB_MAX_TOTAL_BYTES` default may need lowering.
- **Risk: Render Free RAM (512 MB)** during imports with many images: limits P2-22, encode images one by one and drop source bytes after encoding; a 1,000-image import may approach request timeouts — report and suggest splitting.
- **Risk: takedown**: soft-deleting an asset does not stop serving it (P2-6). A platform-admin purge (delete blob, accept broken history) is a Phase 9 item; until then an operator can delete the blob row/object manually.
- **Risk: deviations** P2-17 (source scope per course), P2-21 (no external image URLs) change BUNDLE_FORMAT behavior; confirm with the owner only if they object (defaults taken per rule A).
- **Risk: SQLite cannot prove locking** (same as Phase 1); CI must set `LMS_PG_TEST_DATABASE_URL`.
- **Risk: Pillow version drift** changes encoded bytes for the same source; dedupe keys on `source_sha256`, so this only creates a second blob, never a broken reference.
- **Deferred**: personal library banks (course_id NULL) UI, bank copy between courses, passage translation groups, choice-level images in the import format, matching/ordering/fill-blank types, blob GC, private file UI.
