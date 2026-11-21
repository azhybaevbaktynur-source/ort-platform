# Lesson videos hosted on the platform (content studio request R8, 2026-11-22)

Source: `~/ort-content-studio/state/platform_requests.md` § R8. Problem: paid-module videos as unlisted YouTube links
can be shared. Goal: MP4 in the PRIVATE R2 bucket, played only through short-lived signed URLs for users who may see
the module. Not DRM: no shareable link, no download button. YouTube/Vimeo `url` items stay as they are.

## Cost check (R2 free tier, hard rule 5)
- Storage: ~5 MB per 3–4 min video, ru course ≈ 0.8–1.5 GB, ky the same. Counted by the existing guard
  (`files/usage.store_blob`: warn 8.0 GB, refuse 9.5 GB). Both languages fit; the guard refuses before any charge.
- Egress: R2 has no egress fee. Playback GETs go from the browser straight to R2 (presigned), so Render bandwidth is
  not used.
- Class B operations (reads): free 10 M/month. A view is a few range requests. At today's scale this is far below
  the limit; at thousands of daily viewers it could pass 10 M (≈ $0.36 per extra million). Flagged to the owner;
  nothing paid is enabled. Cloudflare Stream / Bunny are not needed.

## Contract

### V1. Storage and migration `0036_course_videos`
Table `course_videos`: `id`, `course_id` FK, `asset_id` FK → `assets` (private visibility, mime `video/mp4`, the
existing asset row type so dedup, usage and deletion work as for course files; extend asset validation for MP4),
`title` (≤300), `size_bytes`, `sha256`, `duration_s` (int), `width`, `height`, `captions_asset_id` FK nullable
(`text/vtt`, private), `created_by_id`, timestamps, soft delete. `module_items.video_id` FK nullable; item kind
`video` (`ItemKind` gains `"video"`; target field `video_id`; check constraint like the other kinds if they have one).
Additive DDL only.

### V2. Staff API (`A.CONTENT_MANAGE`, not in a sandbox)
- `POST /courses/{c}/videos` multipart `file` (+ optional `title`): ≤ 50 MB (setting `LMS_VIDEO_MAX_BYTES`), MP4 only:
  `ftyp` box first with an MP4 brand, a `moov` box, an `avc1` sample entry (H.264); audio, if any, `mp4a`. Else 422
  `video_invalid`; too big 413 `payload_too_large`; storage guard as today (`storage_full`). Duration, width, height
  read from `mvhd`/`tkhd` in pure Python (no ffmpeg). SHA-256 dedup within the course (same file → the existing row,
  200). → `VideoOut {id, title, size_bytes, sha256, duration_s, width, height, has_captions, created_at}` (201).
- `GET /courses/{c}/videos` (paginated, `limit`/cursor), `GET /courses/{c}/videos/{v}`, `PATCH …/{v}` (title),
  `DELETE …/{v}` (soft; 409 `video_in_use` while a live item points to it).
- `PUT /courses/{c}/videos/{v}/captions` body `text/vtt` ≤ 200 KB, must start with `WEBVTT` (else 422
  `captions_invalid`); `DELETE …/captions`.
- Module items: `POST /courses/{c}/modules/{m}/items` `{kind:"video", video_id, title?}`; replace the file of an item
  = `PATCH …/items/{i}` `{video_id}` (same item, progress facts kept).

### V3. Playback (student, staff, test student)
- `GET /courses/{c}/modules/{m}/items/{i}/play` → `{url, expires_at, duration_s, width, height, captions_url}`.
  Same visibility as the item for the caller: enrolled (or staff / Student view), module and item published, not
  locked by a module rule and not Pro-locked (`locked_reason`) → else 403 `item_locked`; outsiders 404. R2 driver:
  `presigned_get(key, ttl, …, content_type="video/mp4", attachment=False)` (inline), TTL setting
  `LMS_VIDEO_URL_TTL_S` = 1200. `db`/`local` drivers: a backend stream URL with an HMAC token (`exp`, video id) that
  supports HTTP `Range` (206), so seeking works in dev and tests; the token is checked, never the session.
- `captions_url`: `GET /courses/{c}/modules/{m}/items/{i}/captions.vtt` through the API (`text/vtt`, same checks),
  so `<track>` needs no CORS on R2. Null without captions.
- Rate limit `/play` like other per-user reads. Audit nothing (reads).
- `ItemStudentOut` for a video item: `video_file: {duration_s, has_captions}` on unlocked rows only; `duration_s` of
  the item = the video's. Done: the existing `viewed` fact (the client sends it at ≥ 90 % watched or on «Просмотрено»).

### V4. Frontend
- CSP (`frontend/next.config.ts`): `media-src 'self' https://*.r2.cloudflarestorage.com` plus `API_ORIGIN` (dev stream).
- `LessonView`: a `video` item renders an HTML5 `<video>` (controls, `controlsList="nodownload"`,
  `disablePictureInPicture` off, `preload="metadata"`, `playsInline`, context menu suppressed on the element), a speed
  menu 0.75 / 1 / 1.25 / 1.5 / 2, captions track when `captions_url`, position remembered per item (localStorage,
  try/catch) and restored; on a playback error or near `expires_at`, fetch `/play` again and resume at the same time.
  At ≥ 90 % of the duration send the view fact once; a «Просмотрено» button sends it too. Pager and outline as for pages.
- Staff module outline: video items listed with title and duration, movable/deletable like other items; an
  «Видео» entry in «Добавить» that uploads an MP4 (progress bar) and adds the item. Staff preview plays it.
- All strings in en/ky/ru.

## Acceptance
A paid-module video plays for an entitled student; 403 for a student without Pro and for a locked module; 404 for an
outsider; the signed URL stops working after expiry (R2: presign TTL; dev: token `exp`); R2 usage includes videos;
over 50 MB or a non-MP4 is refused; Range requests return 206 on the dev stream; done after 90 %.

## Slices
| slice | owns |
|---|---|
| `lv-a-backend` | migration 0036, `course_videos` package (or inside `course_files`), MP4 probe, routes + route inventory, module item kind, play/captions/stream endpoints, settings, tests |
| `lv-b-frontend` | CSP, video player in `LessonView`, staff outline + upload, types, i18n |

## Results (2026-11-22)
Branch `lesson-videos` (slices `lv-a-backend`, `lv-b-frontend`, e2e `lv-e2e`), migration `0036_course_videos`.
- Routes as V2/V3 plus `GET /courses/{c}/videos/{v}/stream?token=` (dev/test drivers only; 404 on R2). Errors: 422
  `video_invalid`/`captions_invalid`, 413 `payload_too_large`/`course_videos_quota`, 411 `length_required`, 507
  `storage_full`, 409 `video_in_use`, 403 `item_locked` (`details.reason` module | access_required), 403
  `video_token_invalid`, 416. A student gets 404 (not 403) for an unpublished item.
- Security review (Fable, read-only): authz of `/play` mirrors the syllabus; token HMAC domain-separated, bound to
  video + exp. Fixed: per-course cap `LMS_VIDEO_COURSE_MAX_BYTES` = 3 GB (videos are outside the 200 MB per-user asset
  quota, so one course could otherwise fill R2), ftyp brand scan bounded, no dev stream on R2. Left: CSP admits any
  `*.r2.cloudflarestorage.com` host (not an exfil path).
- Frontend: `LessonVideo` (speed, captions via an authenticated fetch → blob URL, so CSP `media-src` has `blob:`),
  position memory, URL refresh before expiry, view fact at 90 % or «Просмотрено»; staff «Видео» dialog uploads MP4 with
  progress. Item `duration_s` is stored only for 60–36000 s; the API reports the video's own duration.
- Checks: SQLite + PG suites, `alembic check`, migration tests, tsc, parity, `next build`, `e2e/lesson-video.spec.ts`
  (3 runs; fixture `e2e/fixtures/lesson-video.mp4`, 20 s), `lessons.spec.ts`, `lesson-course.spec.ts`.
  Screens: `LESSON_VIDEOS_screens/`.
- Production check (content studio, 2026-11-22): a real 223 s, 5.45 MB, 1280×720 video with captions uploaded;
  staff `/play` gave an R2 signed URL; a ranged GET returned 206 `video/mp4`; captions 200; re-upload deduped. A HEAD on
  the signed URL is 403 (signed for GET only; browsers use GET). Student-mode playback and the non-Pro 403 wait for
  the owner's UI check.
- Open: home «next» card does not list video items; CI Chromium may not play H.264 (playback steps skip there).
