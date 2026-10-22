# Phase 2 — Files and content library

**Status**: done 2026-10-22 on branch `phase-2/content`, merged into `lms` (not `main`; ships at the Phase 5 cutover). Design and decisions: `PHASE_2_DESIGN.md`; highlights in `PRODUCT_DECISIONS.md` ("Phase 2").

## What changed

- **Schema** (Alembic `0003_phase2_content`): `assets`, `asset_blobs`, `question_banks`, `translation_groups`, `passages` + `passage_versions`, `bank_questions` + `question_versions` (old `questions` table untouched until Phase 5).
- **Files** (`app/lms/files/`): `BlobStorage` with `local`, `db` (Postgres, production default for now) and `r2` drivers (R2 needs owner keys); image validation by content, WebP re-encode, EXIF strip, 12 MP cap, one encode at a time; per-owner dedupe; quotas; public media route `/api/v1/media/{sha}.webp` (immutable caching, nosniff, CSP); owner-only private content route; `scripts/copy_blobs.py`; lazy orphan sweep.
- **Question types** (`app/lms/content/types/`): single_choice, multiple_answers, true_false, comparison (ORT math_1), numeric, short_text, essay — each with validation, an allowlisted `student_view`, `key_view` and `score()`.
- **Content API** (`app/lms/content/`): banks, versioned questions and passages (immutable versions, stale-save 409, revert = new version), translation groups, preview, soft delete/restore, move; 30 routes in the permission matrix.
- **Importer** (`app/lms/content/importers/`): CSV and ort-digitizer bundle parsers ported from the old code (parity tests against the old parsers), one bank per source per course, dry-run preview, conflict rules (teacher edits are never silently overwritten), idempotent re-import, bounded memory, zero stored images on failure.
- **Frontend**: course tab "Question bank" (`/[lang]/courses/[courseId]/bank/...`): bank list, question list with search/filters, per-type editor with KaTeX preview and image picker, passages, version history and revert, translations, import page with dry-run report. 841 i18n keys (en/ky/ru).
- **Reviews**: security review of files/content (image-decode memory blowup, quota bypass via delete, private assets in content, upload body before cap, lock ordering, passage races, URL encoding, KaTeX limits) and of the importer (parsing memory DoS, lost teacher edits under concurrency, orphan blobs, peak memory, zip central-directory cost, manifest caps, preview cost, tag wipe) — all fixed with tests.

## How to verify

```bash
cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" venv/bin/python -m pytest -q -p no:cacheprovider -W ignore
# Postgres: DBs with ENCODING 'UTF8' TEMPLATE template0, PGCLIENTENCODING=UTF8, PGTZ=UTC; set DATABASE_URL and LMS_PG_TEST_DATABASE_URL to PG
venv/bin/python -m pytest tests/lms/test_pg_concurrency_content.py
```
Exit criteria: `tests/lms/test_phase2_flow.py::test_phase2_flow` (end to end, incl. tsoomo19-style bundle and restart), `tests/lms/test_import_api.py::test_case1_db_level_and_case9_idempotent`, `tests/lms/test_asset_persistence.py`, `tests/lms/test_import_parity.py`.

## Deferred / owner input

- **R2 keys (owner secret)**: Cloudflare account, bucket(s) (public + separate private), API token, account id; later a Cloudflare-DNS domain for a public image CDN (D2). Until then production stores images in Postgres (`db` driver, 300 MiB cap).
- Verify on staging whether Vercel caches `/api/v1/media/*` through the rewrite (`x-vercel-cache`).
- Personal library banks UI, bank copy between courses, passage translations, choice-level images in the import format, matching/ordering types, admin purge of blobs (Phase 9).
- Local dev DBs need `RUN_MIGRATIONS=1` once (or recreate) for the new tables.
